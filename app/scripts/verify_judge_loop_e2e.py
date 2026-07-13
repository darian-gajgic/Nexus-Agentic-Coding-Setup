#!/usr/bin/env python3
"""Judge-loop overhaul gate (2026-07-13): verdict recalibration parsing,
deterministic pre-gate, delta re-judge plumbing, targeted-rework retry
semantics (keep-session, [F#] ids), convergence + closure + reaper, review
round-pairs. In-process against the live DB (probe rows + settings restored,
temp workspaces under the system tmpdir). No LLM calls — judge.cmd is stubbed.

Run:  .venv/bin/python scripts/verify_judge_loop_e2e.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import database as db          # noqa: E402
import evals as ev             # noqa: E402
import loop_engine as le       # noqa: E402
import review                  # noqa: E402
import worktree as wt          # noqa: E402

db.init_db()  # idempotent — gate may run before the service migrated columns

PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


SENTINEL = """Gates table here.
VERDICT: {verdict}
Learning note: probe.
NEXUS_JUDGE_JSON_BEGIN
{{"verdict": "{verdict}",
 "findings": {findings},
 "revision_brief": "{brief}"}}
NEXUS_JUDGE_JSON_END
"""

FINDINGS = ('[{"severity": "critical", "file_path": "deliverable.md", "line_no": 2, '
            '"line_text": "line two content", "problem": "p1 is wrong", "fix": "do f1"}]')

saved = {k: db.get_setting(k) for k in
         ("judge.cmd", "judge.pregate", "judge.pregate_min_chars",
          "judge.delta_rejudge", "judge.max_runs",
          "dispatch.rework_continue_session", "dispatch.retry_slice_frac",
          "dispatch.rework_ceiling_mult")}
created_tasks = []
tmp = Path(tempfile.mkdtemp(prefix="nexus-judge-gate-"))


def mk(**kw):
    tid = f"task-{uuid.uuid4().hex[:8]}"
    created_tasks.append(tid)
    ws = tmp / tid
    ws.mkdir(parents=True, exist_ok=True)
    f = {"id": tid, "title": "probe judge loop", "description": "p", "status": "done",
         "priority": 2, "created_at": time.time(), "updated_at": time.time(),
         "user_id": "u_owner", "dispatch_state": "completed",
         "deliverable_type": "content", "domain": "marketing",
         "workspace_path": str(ws)}
    f.update(kw)
    db.execute(f"INSERT INTO tasks ({', '.join(f)}) VALUES ({','.join('?' * len(f))})",
               tuple(f.values()))
    return tid, ws


def cleanup_task_rows(tid):
    db.execute("DELETE FROM review_comments WHERE task_id=?", (tid,))
    db.execute("DELETE FROM frontier_ledger WHERE task_id=?", (tid,))
    db.execute("DELETE FROM approvals WHERE payload LIKE ?", (f'%"{tid}"%',))


try:
    # ── 1. parse_judge_metrics: recalibrated sentinel output ──
    print("=== 1. verdict parsing + finding keys ===")
    out = SENTINEL.format(verdict="REVISE", findings=FINDINGS, brief="[F1] do f1")
    m = ev.parse_judge_metrics(out)
    ok("verdict + numbered revision_brief parsed",
       m["verdict"] == "REVISE" and m.get("revision_brief") == "[F1] do f1")
    ok("finding keys computed (critic mirror, 12-hex)",
       len(m.get("_keys") or []) == 1 and len(m["_keys"][0]) == 12, str(m.get("_keys")))
    m2 = ev.parse_judge_metrics(SENTINEL.format(verdict="SHIP", findings="[]", brief=""))
    ok("SHIP with no findings carries no keys", m2["verdict"] == "SHIP" and not m2.get("_keys"))

    # ── 2. deterministic pre-gate ──
    print("=== 2. judge_pregate ===")
    db.set_setting("judge.pregate", "1")
    db.set_setting("judge.pregate_min_chars", "400")
    t_pg, ws_pg = mk()
    ok("missing deliverable fails", ev.judge_pregate(
        db.query_one("SELECT * FROM tasks WHERE id=?", (t_pg,))) != [])
    (ws_pg / "deliverable.md").write_text("# Stub\nTBD\n")
    fails = ev.judge_pregate(db.query_one("SELECT * FROM tasks WHERE id=?", (t_pg,)))
    ok("stub deliverable fails size + headings + placeholder",
       len(fails) >= 2, str(fails))
    (ws_pg / "deliverable.md").write_text(
        "# Report\n\n" + ("evidence line with real content here\n" * 30)
        + "\n## Decisions\n- one\n")
    ok("substantial deliverable passes", ev.judge_pregate(
        db.query_one("SELECT * FROM tasks WHERE id=?", (t_pg,))) == [])
    t_rp, ws_rp = mk(repo_path="/tmp/notreal")
    (ws_rp / "deliverable.md").write_text(
        "# Report\n\n" + ("evidence line with real content here\n" * 30))
    ok("repo task with no changes.diff fails",
       any("branch changes" in f for f in ev.judge_pregate(
           db.query_one("SELECT * FROM tasks WHERE id=?", (t_rp,)))))
    (ws_rp / "deliverable.md").write_text(
        "# Report\n\nreview was clean, NO-OP round.\n" + ("filler line\n" * 40))
    ok("declared NO-OP round is exempt from the empty-diff check",
       not any("branch changes" in f for f in ev.judge_pregate(
           db.query_one("SELECT * FROM tasks WHERE id=?", (t_rp,)))))
    db.set_setting("judge.pregate", "0")
    ok("pre-gate kill switch", ev.judge_pregate(
        db.query_one("SELECT * FROM tasks WHERE id=?", (t_rp,))) == [])
    db.set_setting("judge.pregate", "1")

    # ── 3. delta bundle: _build_judge_prior + run_judge_cmd env plumbing ──
    print("=== 3. delta re-judge plumbing ===")
    import server as srv
    t_dl, ws_dl = mk(judge_round=1)
    (ws_dl / "_judge").mkdir()
    (ws_dl / "_judge" / "round-1.json").write_text(json.dumps({
        "round": 1, "verdict": "REVISE", "ts": time.time() - 60,
        "findings": [{"severity": "critical", "file_path": "deliverable.md",
                      "line_no": 2, "problem": "p1 is wrong", "suggested_fix": "do f1"}],
        "revision_brief": "[F1] do f1", "keys": ["abc123def456"]}))
    (ws_dl / "deliverable.v1.md").write_text("# Report\nline two content\nold text\n")
    (ws_dl / "deliverable.md").write_text("# Report\nline two content fixed\nnew text\n")
    prior_path, prior_ts = srv._build_judge_prior(
        db.query_one("SELECT * FROM tasks WHERE id=?", (t_dl,)), 1)
    prior_txt = open(prior_path).read() if prior_path else ""
    ok("prior bundle built with [F1] fix-list + unified diff",
       prior_path and "[F1]" in prior_txt and "p1 is wrong" in prior_txt
       and "-line two content" in prior_txt and "+line two content fixed" in prior_txt,
       (prior_txt or "none")[:120])
    ok("prior_ts = round file ts", prior_ts and abs(prior_ts - (time.time() - 60)) < 5)
    t_nf, _ = mk(judge_round=1)
    ok("missing pieces → (None, None) full re-judge fallback",
       srv._build_judge_prior(db.query_one("SELECT * FROM tasks WHERE id=?", (t_nf,)), 1)
       == (None, None))
    # env plumbing through run_judge_cmd with a stub judge.cmd
    stub = tmp / "stub_judge.sh"
    stub.write_text("#!/usr/bin/env bash\n"
                    "echo \"PRIOR=${JUDGE_PRIOR:-none} ROUND=${JUDGE_ROUND:-none} "
                    "SPEC=${JUDGE_SPEC:-none} ARTS=${JUDGE_ARTIFACTS:-none}\"\n"
                    + f"cat <<'EOF'\n{SENTINEL.format(verdict='REVISE', findings=FINDINGS, brief='[F1] do f1')}\nEOF\n")
    stub.chmod(0o755)
    db.set_setting("judge.cmd", f"bash {stub} {{file}} {{domain}}")
    spec_probe = tmp / "SPEC-probe.md"
    spec_probe.write_text("# spec probe")
    out_full = ev.run_judge_cmd(str(ws_dl / "deliverable.md"), "marketing",
                                spec_path=str(spec_probe))
    ok("round 1: SPEC exported, no PRIOR",
       "SPEC=/" in out_full.replace("SPEC=", "SPEC=/", 1).replace("SPEC=/none", "SPEC=none")
       and "PRIOR=none" in out_full and "SPEC=none" not in out_full, out_full[:100])
    out_delta = ev.run_judge_cmd(str(ws_dl / "deliverable.md"), "marketing",
                                 spec_path=str(spec_probe), prior_path=prior_path,
                                 judge_round=2)
    ok("delta round: PRIOR + ROUND exported, SPEC omitted (bundle diet)",
       "PRIOR=none" not in out_delta and "ROUND=2" in out_delta
       and "SPEC=none" in out_delta, out_delta[:100])
    # artifact mtime filter
    art_src = tmp / "artsrc"
    art_src.mkdir()
    (art_src / "old.txt").write_text("old")
    os.utime(art_src / "old.txt", (time.time() - 3600, time.time() - 3600))
    (art_src / "new.txt").write_text("new")
    art_dst = tmp / "artdst"
    n = ev._copy_judge_artifacts([str(art_src)], art_dst, mtime_after=time.time() - 600)
    ok("artifact mtime filter copies only files touched since",
       n == 1 and (art_dst / "artsrc" / "new.txt").is_file()
       and not (art_dst / "artsrc" / "old.txt").exists())

    # ── 4. full _judge_thread drive on the stub: round persist + comments ──
    print("=== 4. judge thread: round state + tier + comments ===")
    t_j, ws_j = mk()
    (ws_j / "deliverable.md").write_text("# Report\nline two content\nmore text\n")
    db.execute("UPDATE tasks SET judge_verdict='running', judge_ts=? WHERE id=?",
               (time.time(), t_j))
    srv._judge_thread(t_j, str(ws_j / "deliverable.md"), "marketing")
    row = db.query_one("SELECT * FROM tasks WHERE id=?", (t_j,))
    ok("verdict stored with judge_round=1 + tier=frontier + keys",
       row["judge_verdict"] == "REVISE" and row["judge_round"] == 1
       and row["judge_tier"] == "frontier"
       and (json.loads(row["judge_keys"] or "{}").get("keys") or []),
       f"{row['judge_verdict']}/{row['judge_round']}/{row['judge_tier']}")
    ok("round-1.json memory written",
       (ws_j / "_judge" / "round-1.json").is_file())
    cmt = db.query_all("SELECT * FROM review_comments WHERE task_id=? AND status='open'",
                       (t_j,))
    ok("finding landed as an anchored judge comment (±2 validated)",
       len(cmt) == 1 and cmt[0]["source"] == "judge" and cmt[0]["line_no"] == 2,
       str([dict(c) for c in cmt])[:150])
    # crash-safety: inner raises → 'error', never stranded 'running'
    real_inner = srv._judge_thread_inner
    srv._judge_thread_inner = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
    t_cr, ws_cr = mk(judge_verdict="running", judge_ts=time.time())
    srv._judge_thread(t_cr, str(ws_cr / "nope.md"), "marketing")
    srv._judge_thread_inner = real_inner
    ok("judge thread crash → verdict 'error', not stranded 'running'",
       db.query_one("SELECT judge_verdict FROM tasks WHERE id=?",
                    (t_cr,))["judge_verdict"] == "error")
    # stale-'running' reaper
    t_st, _ = mk(judge_verdict="running", judge_ts=time.time() - 8000)
    t_sc, _ = mk(critic_verdict="running", critic_ts=time.time() - 8000)
    le._sweep_stale_frontier()
    ok("reaper: stale judge 'running' → 'interrupted' + re-judgeable (ts NULL)",
       db.query_one("SELECT judge_verdict, judge_ts FROM tasks WHERE id=?",
                    (t_st,))["judge_verdict"] == "interrupted"
       and db.query_one("SELECT judge_ts FROM tasks WHERE id=?", (t_st,))["judge_ts"] is None)
    ok("reaper: stale critic 'running' → 'error' (human checkpoint path)",
       db.query_one("SELECT critic_verdict FROM tasks WHERE id=?",
                    (t_sc,))["critic_verdict"] == "error")

    # ── 5. retry semantics: [F#] ids, keep-session, origins ──
    print("=== 5. targeted rework retry ===")
    db.set_setting("dispatch.rework_continue_session", "1")
    t_r, ws_r = mk(session_id="api_probe_sess", judge_verdict="REVISE",
                   judge_output=SENTINEL.format(verdict="REVISE", findings=FINDINGS,
                                                brief="[F1] do f1"))
    (ws_r / "deliverable.md").write_text("# Report\nline two content\n")
    db.execute("INSERT INTO review_comments (id, task_id, user_id, file_path, side, "
               "line_no, line_text, body, status, created_at, source) "
               "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
               (f"rc-{uuid.uuid4().hex[:12]}", t_r, "u_owner", "deliverable.md", "new",
                2, "line two content", "[CRITICAL] p1 is wrong", "open",
                time.time(), "judge"))
    srv._retry_task(t_r, None, origin="loop_judge")
    row = db.query_one("SELECT session_id, retry_feedback FROM tasks WHERE id=?", (t_r,))
    ok("first loop rework KEEPS its session (continue-session)",
       row["session_id"] == "api_probe_sess", str(row["session_id"]))
    ok("drained comments carry [F1] ids + judge fix-list brief",
       "[F1] [JUDGE]" in (row["retry_feedback"] or "")
       and "[F1] do f1" in (row["retry_feedback"] or ""),
       (row["retry_feedback"] or "")[:200])
    ok("comment consumed by the drain",
       db.query_one("SELECT COUNT(*) AS n FROM review_comments WHERE task_id=? "
                    "AND status='open'", (t_r,))["n"] == 0)
    # second rework (deliverable.v1.md now exists) → fresh session
    (ws_r / "deliverable.md").write_text("# Report v2\nline two content fixed\n")
    db.execute("UPDATE tasks SET session_id='api_probe_sess2', judge_verdict='REVISE', "
               "status='done', dispatch_state='completed' WHERE id=?", (t_r,))
    srv._retry_task(t_r, None, origin="loop_judge")
    ok("round ≥2 rework starts FRESH (session dropped)",
       db.query_one("SELECT session_id FROM tasks WHERE id=?", (t_r,))["session_id"] is None)
    t_op, ws_op = mk(session_id="api_probe_sess3", judge_verdict="REVISE")
    (ws_op / "deliverable.md").write_text("# R\n")
    srv._retry_task(t_op, "operator says fix it", origin="operator")
    ok("operator retry always starts fresh",
       db.query_one("SELECT session_id FROM tasks WHERE id=?", (t_op,))["session_id"] is None)

    # ── 6. convergence, closure card, reopen ──
    print("=== 6. closure + convergence + reopen ===")
    ok("_judge_keys_converged: keys ⊆ prev at round>1 only",
       le._judge_keys_converged({"judge_keys": json.dumps(
           {"round": 2, "keys": ["a", "b"], "prev": ["a", "b", "c"]})})
       and not le._judge_keys_converged({"judge_keys": json.dumps(
           {"round": 1, "keys": ["a"], "prev": []})})
       and not le._judge_keys_converged({"judge_keys": json.dumps(
           {"round": 2, "keys": ["x"], "prev": ["a"]})}))
    cfg = {"enabled": True, "mode": "closed", "auto_judge": True,
           "triggers": [{"id": "judge_revise", "enabled": True, "max_rounds": 2,
                         "used": 2}]}
    t_cl, _ = mk(judge_verdict="REVISE", judge_ts=time.time(),
                 loop_config=json.dumps(cfg))
    closed = le._close_judge_loop(db.query_one("SELECT * FROM tasks WHERE id=?", (t_cl,)),
                                  "task", t_cl, None, "automatic round cap reached")
    card = db.query_one("SELECT * FROM approvals WHERE status='pending' AND "
                        "action_type='deliverable' AND payload LIKE ?",
                        (f'%"task_id": "{t_cl}"%',))
    ok("closure files ONE pending deliverable decision card", closed and card,
       str(card and card["description"])[:100])
    trig = json.loads(db.query_one("SELECT loop_config FROM tasks WHERE id=?",
                                   (t_cl,))["loop_config"])["triggers"][0]
    ok("closure marks the trigger closed", le._judge_closed(trig, None))
    le._close_judge_loop(db.query_one("SELECT * FROM tasks WHERE id=?", (t_cl,)),
                         "task", t_cl, None, "again")
    n_cards = db.query_one("SELECT COUNT(*) AS n FROM approvals WHERE status='pending' "
                           "AND action_type='deliverable' AND payload LIKE ?",
                           (f'%"task_id": "{t_cl}"%',))["n"]
    ok("closure is idempotent while a card is pending", n_cards == 1)
    db.execute("UPDATE tasks SET judge_round=3, judge_keys='{}' WHERE id=?", (t_cl,))
    le.reopen_judge_loop(t_cl)
    trig = json.loads(db.query_one("SELECT loop_config FROM tasks WHERE id=?",
                                   (t_cl,))["loop_config"])["triggers"][0]
    row = db.query_one("SELECT judge_round, judge_keys FROM tasks WHERE id=?", (t_cl,))
    ok("operator reject re-arms: marker cleared + judge_round/keys reset",
       not le._judge_closed(trig, None) and row["judge_round"] == 0
       and row["judge_keys"] is None)
    t_scr, _ = mk(judge_verdict="REVISE", judge_ts=time.time(), judge_tier="screen",
                  loop_config=json.dumps(cfg))
    le._close_judge_loop(db.query_one("SELECT * FROM tasks WHERE id=?", (t_scr,)),
                         "task", t_scr, None, "screen cap", card=False)
    ok("screen closure = accept-with-notes (closed, NO card)",
       not db.query_one("SELECT 1 FROM approvals WHERE status='pending' AND "
                        "payload LIKE ?", (f'%"task_id": "{t_scr}"%',)))
    # 2026-07-13b: ANY operator retry door re-arms a closed family — observed
    # live (bench-02 implement): a manual ↻ after the cap left the family
    # closed, so the reworked version sat wearing a stale REVISE, unjudged.
    t_rearm, ws_rearm = mk(judge_verdict="REVISE", judge_ts=time.time(),
                           judge_round=4, judge_keys='{"round":4}',
                           loop_config=json.dumps(cfg))
    (ws_rearm / "deliverable.md").write_text("# R\n")
    loc = le._locate_judge_cfg(t_rearm)
    le._mutate_cfg_trigger(loc[0], loc[1], "judge_revise",
                           lambda t2: le._set_judge_closed(t2, loc[2], True))
    srv._retry_task(t_rearm, "operator wants a fresh try", origin="operator")
    trig_r = json.loads(db.query_one("SELECT loop_config FROM tasks WHERE id=?",
                                     (t_rearm,))["loop_config"])["triggers"][0]
    row_r = db.query_one("SELECT judge_round, judge_keys FROM tasks WHERE id=?", (t_rearm,))
    ok("operator ↻ retry re-arms a closed family (marker + round + keys reset)",
       not le._judge_closed(trig_r, None) and row_r["judge_round"] == 0
       and row_r["judge_keys"] is None)

    # ── 6b. preview runner: crashed-state surfacing + package launch ──
    print("=== 6b. preview crash surfacing + package detection ===")
    import app_runner as ar
    probe_ws = tmp / "prevws"
    probe_ws.mkdir()
    (probe_ws / "_preview.log").write_text("boom line 1\nModuleNotFoundError: x\n")
    with ar._lock:
        reg = ar._load()
        reg["gateprobe:x:y"] = {"task_id": "gateprobe:x:y", "pid": 999999983,
                                "port": 1, "type": "python", "label": "gate probe",
                                "url": "http://127.0.0.1:1",
                                "workspace": str(probe_ws),
                                "started_at": time.time(), "expires_at": time.time() + 60}
        ar._save(reg)
    try:
        inst = ar.instances("gateprobe:")
        ok("dead-pid preview surfaces as state='crashed' WITH the log tail "
           "(was silently skipped → 'not working, no error')",
           len(inst) == 1 and inst[0]["state"] == "crashed"
           and "ModuleNotFoundError" in (inst[0].get("log_tail") or ""),
           str(inst)[:120])
    finally:
        ar.stop_app("gateprobe:x:y")
    pkg_ws = tmp / "pkgws"
    (pkg_ws / "app").mkdir(parents=True)
    (pkg_ws / "app" / "__init__.py").write_text("")
    (pkg_ws / "app" / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n")
    (pkg_ws / "requirements.txt").write_text("fastapi\nuvicorn\n")
    det = ar.detect_app(str(pkg_ws))
    ok("package-shaped ASGI app detected: module launch from the ROOT + root "
       "requirements (was `python main.py` in the subdir → relative-import crash)",
       det and det["type"] == "python" and det.get("module") == "app.main"
       and det.get("asgi") == "app" and det.get("run_dir") == str(pkg_ws)
       and (det.get("reqs") or "").endswith("requirements.txt"), str(det))

    # ── 7. exemplar guard: screen SHIPs never qualify ──
    print("=== 7. screen tier guards ===")
    import hermes_dispatch as hd
    guard_sql = "COALESCE(judge_tier,'frontier') != 'screen'"
    src = open("hermes_dispatch.py").read()
    ok("golden_exemplars SQL excludes screen SHIPs", guard_sql in src)
    ok("auto-approve sweep excludes screen SHIPs",
       "judge_tier" in open("loop_engine.py").read().split("_sweep_auto_approve_ship")[1][:2000])

    # ── 8. review: round pairs + report entry + version selection ──
    print("=== 8. review round-over-round ===")
    repo = tmp / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "--allow-empty", "-q", "-m", "base"],
                   check=True, env={**os.environ, "GIT_AUTHOR_NAME": "g",
                                    "GIT_AUTHOR_EMAIL": "g@g", "GIT_COMMITTER_NAME": "g",
                                    "GIT_COMMITTER_EMAIL": "g@g"})
    (repo / "SPEC.md").write_text("v1 line\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "r1"],
                   check=True, env={**os.environ, "GIT_AUTHOR_NAME": "g",
                                    "GIT_AUTHOR_EMAIL": "g@g", "GIT_COMMITTER_NAME": "g",
                                    "GIT_COMMITTER_EMAIL": "g@g"})
    sha1 = wt.head_sha(str(repo))
    (repo / "SPEC.md").write_text("v1 line\nv2 addition\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "r2"],
                   check=True, env={**os.environ, "GIT_AUTHOR_NAME": "g",
                                    "GIT_AUTHOR_EMAIL": "g@g", "GIT_COMMITTER_NAME": "g",
                                    "GIT_COMMITTER_EMAIL": "g@g"})
    sha2 = wt.head_sha(str(repo))
    diff = wt.capture_diff_between(str(repo), sha1, sha2)
    ok("capture_diff_between: exact A→B round diff",
       "+v2 addition" in diff and "-v1 line" not in diff, diff[:120])
    ok("capture_diff_between rejects non-SHA input",
       wt.capture_diff_between(str(repo), "HEAD", sha2) == "")
    t_rev, ws_rev = mk(repo_path=str(repo))
    (ws_rev / "_history").mkdir()
    (ws_rev / "_history" / "rounds.json").write_text(json.dumps([
        {"round": 1, "head_sha": sha1, "ts": time.time() - 60},
        {"round": 2, "head_sha": sha2, "ts": time.time()}]))
    (ws_rev / "changes.diff").write_text(
        "diff --git a/SPEC.md b/SPEC.md\nnew file mode 100644\n--- /dev/null\n"
        "+++ b/SPEC.md\n@@ -0,0 +1,2 @@\n+v1 line\n+v2 addition\n")
    (ws_rev / "deliverable.md").write_text("# Report\nround two\n")
    # NOTE: the round pair diffs inside repo_path root (no worktree in this probe)
    r = review.build_task_review(db.query_one("SELECT * FROM tasks WHERE id=?", (t_rev,)))
    ok("repo review defaults to the ROUND pair once ≥2 rounds exist",
       r.get("selected") == "round" and any("round 1" in p["label"].lower()
                                            for p in r.get("pairs", [])),
       f"{r.get('selected')}/{r.get('pairs')}")
    ok("round diff shows only what the rework changed",
       any(f["path"] == "SPEC.md" and f["additions"] == 1 for f in r["files"]),
       str([(f['path'], f['additions']) for f in r['files']]))
    ok("report entry (deliverable.md) rides the repo review",
       any(f["path"] == "deliverable.md" for f in r["files"]))
    r_base = review.build_task_review(
        db.query_one("SELECT * FROM tasks WHERE id=?", (t_rev,)), pair="base")
    ok("pair=base still serves the whole-branch view",
       r_base.get("selected") == "base"
       and any(f["path"] == "SPEC.md" and f["additions"] == 2 for f in r_base["files"]))
    # workspace version selection
    t_wv, ws_wv = mk()
    (ws_wv / "_history" / "v1").mkdir(parents=True)
    (ws_wv / "_history" / "v1" / "out.md").write_text("alpha\n")
    (ws_wv / "_history" / "v2").mkdir(parents=True)
    (ws_wv / "_history" / "v2" / "out.md").write_text("alpha\nbeta\n")
    (ws_wv / "out.md").write_text("alpha\nbeta\ngamma\n")
    r_ws = review.build_task_review(db.query_one("SELECT * FROM tasks WHERE id=?", (t_wv,)),
                                    from_v="v1")
    ok("workspace ?from_v picks the comparison base",
       r_ws.get("selected_from") == "v1"
       and any(f["additions"] == 2 for f in r_ws["files"]),
       str([(f['path'], f['additions']) for f in r_ws['files']]))

finally:
    for k, v in saved.items():
        if v is None:
            db.execute("DELETE FROM settings WHERE key=?", (k,))
        else:
            db.set_setting(k, v)
    for tid in created_tasks:
        db.execute("DELETE FROM tasks WHERE id=?", (tid,))
        cleanup_task_rows(tid)
    db.execute("DELETE FROM activity WHERE message LIKE '%probe judge loop%'")
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{'ALL PASS' if not FAIL else 'FAILURES'}: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
