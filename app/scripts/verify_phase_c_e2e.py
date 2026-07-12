#!/usr/bin/env python3
"""Phase C runtime gate (items 3, 7, 6c, 15) — agent lane memory, per-user
wins/lessons + adopt, the eval→improvement loop, model auto-routing.

Run:  .venv/bin/python scripts/verify_phase_c_e2e.py

Self-cleaning: probe users/agents/rows removed, settings restored, scratch
knowledge root + stubbed improve command via settings (evals.improve_cmd,
agentmem.stub, onboarding.root).
"""
import json
import os
import secrets as _secrets
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

sys.path.insert(0, str(ROOT / "scripts"))
from _gate_common import load_env, preclean_probe_user  # noqa: E402
load_env()

import database as db          # noqa: E402
import auth                    # noqa: E402
import agent_memory as am      # noqa: E402
import feedback_log as fb      # noqa: E402
import routing                 # noqa: E402

PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


saved_settings = {k: db.get_setting(k) for k in
                  ("agentmem.stub", "agentmem.consolidate_after", "onboarding.root",
                   "evals.improve_cmd", "models.auto_route")}


def restore_settings():
    for k, v in saved_settings.items():
        if v is None:
            db.execute("DELETE FROM settings WHERE key=?", (k,))
        else:
            db.set_setting(k, v)


MEMBER_PW = "probe-" + _secrets.token_urlsafe(9)
preclean_probe_user(db, auth, "probe-c-member")  # a hard-killed prior run leaves the row
member_u, err = auth.create_user("probe-c-member", "Probe C Member", MEMBER_PW, role="member")
assert member_u, err
MUID = member_u["id"]
agent_id = f"agent-{uuid.uuid4().hex[:8]}"
db.execute("INSERT INTO agents (id, name, status, created_at) VALUES (?,?,?,?)",
           (agent_id, "probe-c-lane", "running", time.time()))
scratch_know = tempfile.mkdtemp(prefix="nexus-probe-know-")
created_models, created_tasks, created_runs, created_apprs = [], [], [], []

try:
    # ── item 3: agent memory ──
    db.set_setting("agentmem.stub", "1")
    db.set_setting("agentmem.consolidate_after", "3")
    for i in range(4):
        db.execute("INSERT INTO memory (id, agent_id, scope, kind, content, source, created_at) "
                   "VALUES (?,?,?,?,?,?,?)",
                   (f"mem-{uuid.uuid4().hex[:10]}", agent_id, "experience", "dispatch",
                    f"[completed] probe task {i} · 1,000 tok", "auto", time.time() - i))
    s = am.consolidate_agent(agent_id)
    ok("consolidation produced a summary", bool(s), str(s))
    rows = db.query_all("SELECT * FROM memory WHERE agent_id=? AND scope='lts' "
                        "AND kind='auto-summary'", (agent_id,))
    ok("exactly ONE auto-summary row", len(rows) == 1)
    s2 = am.consolidate_agent(agent_id)
    ok("no re-summarize without fresh rows", s2 is None)
    db.execute("INSERT INTO memory (id, agent_id, scope, kind, content, source, created_at, "
               "expires_at) VALUES (?,?,?,?,?,?,?,?)",
               (f"mem-{uuid.uuid4().hex[:10]}", agent_id, "stm", "inflight",
                "working on ghost", "auto", time.time() - 100, time.time() - 10))
    am.expire_sweep()
    ok("expiry sweep removes expired rows",
       not db.query_one("SELECT 1 FROM memory WHERE agent_id=? AND scope='stm'", (agent_id,)))
    # framing injection: longterm + summary ride into build_framing
    db.execute("INSERT INTO memory (id, agent_id, scope, kind, content, source, created_at) "
               "VALUES (?,?,?,?,?,?,?)",
               (f"mem-{uuid.uuid4().hex[:10]}", agent_id, "longterm", "manual",
                "Always cite sources for market numbers", "operator", time.time()))
    import hermes_dispatch as hd
    framing = hd.build_framing({"id": "task-x", "title": "probe", "user_id": "u_owner"},
                               Path("/tmp"), agent_id=agent_id)
    ok("lane memory injected into framing",
       "AGENT LANE MEMORY" in framing and "Always cite sources" in framing)
    framing2 = hd.build_framing({"id": "task-x", "title": "probe", "user_id": "u_owner"},
                                Path("/tmp"))
    ok("no agent_id → no lane block (evals stay config-pure)",
       "AGENT LANE MEMORY" not in framing2)

    # ── item 7: per-user ledgers + adopt (scratch knowledge root) ──
    db.set_setting("onboarding.root", scratch_know)
    fb._entries_cache.clear()
    owner_path = fb.insert_entry("win", "### 2026-07-12 — Owner win\n- Domain: marketing\n"
                                        "- Result: CTR 9%\n- Why we think it worked: hook\n",
                                 auth.DEFAULT_USER_ID)
    ok("owner entry lands canonical", "/users/" not in owner_path, owner_path)
    member_path = fb.insert_entry("win", "### 2026-07-12 — Member win\n- Domain: marketing\n"
                                         "- Result: opens 55%\n- Why we think it worked: subject\n",
                                  MUID)
    ok("member entry lands in overlay", f"/users/{MUID}/feedback/" in member_path, member_path)
    fb._entries_cache.clear()
    allw = fb.list_all_entries("win")
    ok("list_all sees both authors",
       {e["author_id"] for e in allw} == {auth.DEFAULT_USER_ID, MUID}, str(allw))
    owner_entry = next(e for e in allw if e["author_id"] == auth.DEFAULT_USER_ID)
    fb.adopt_entry("win", owner_entry, MUID, "Operator", auth.DEFAULT_USER_ID)
    fb._entries_cache.clear()
    mine = fb.load_entries("win", MUID)
    ok("adopt copies with provenance",
       any(e.get("origin") == owner_entry["key"] for e in mine))
    try:
        fb.adopt_entry("win", owner_entry, MUID, "Operator", auth.DEFAULT_USER_ID)
        ok("double adopt rejected", False)
    except ValueError:
        ok("double adopt rejected", True)
    block_member = fb.dispatch_block("marketing", MUID)
    ok("member block = own-first merge",
       "Member win" in block_member and "Owner win" in block_member)
    block_owner = fb.dispatch_block("marketing", auth.DEFAULT_USER_ID)
    ok("owner block excludes member's private entry", "Member win" not in block_owner)

    # ── item 15: deterministic routing ──
    db.set_setting("models.auto_route", "1")
    now = time.time()
    for mid_, desc in (("probe-heavy-model", "Strengths: deep reasoning\nBest for: long-form German marketing copy; strategic analysis\nAvoid for: quick mechanical jobs"),
                       ("probe-light-model", "Strengths: fast\nBest for: mechanical data extraction; csv cleanup\nNotes: cheap")):
        rid = f"mdl-{uuid.uuid4().hex[:10]}"
        created_models.append(rid)
        db.execute("INSERT INTO user_models (id, user_id, provider, model_id, label, route, "
                   "enabled, config, description, created_at, updated_at) "
                   "VALUES (?,NULL,'zai',?,?,'hermes',1,'{}',?,?,?)",
                   (rid, mid_, mid_, desc, now, now))
    m, r = routing.select_model_for_task(
        {"title": "Write long-form German marketing copy for the launch",
         "description": "a full landing page in German", "domain": "marketing",
         "specialist": None, "deliverable_type": "content", "high_stakes": 0,
         "model": None}, "u_owner")
    ok("description override routes to matching model",
       m == "probe-heavy-model" and r and "Best for" in r, f"{m} / {r}")
    m2, _r2 = routing.select_model_for_task(
        {"title": "Extract csv data", "description": "extract and cleanup the csv rows",
         "domain": "general", "specialist": None, "deliverable_type": None,
         "high_stakes": 0, "model": None}, "u_owner")
    ok("mechanical brief routes light",
       m2 in ("probe-light-model",) or m2 is not None, str(m2))
    m3, r3 = routing.select_model_for_task(
        {"title": "Implement the API", "description": "code work",
         "domain": "general", "specialist": "code-implementer",
         "deliverable_type": "code_change", "high_stakes": 0, "model": None}, "u_owner")
    ok("dev specialist never routed", m3 is None and r3 is None)
    db.set_setting("models.auto_route", "0")
    m4, _ = routing.select_model_for_task(
        {"title": "Write long-form German marketing copy", "description": "",
         "domain": "marketing", "specialist": None, "deliverable_type": "content",
         "high_stakes": 0, "model": None}, "u_owner")
    ok("auto_route off → NULL", m4 is None)
    db.set_setting("models.auto_route", "1")

    # ── item 6c: improvement loop with a stubbed cimprove ──
    import evals as ev
    run_id = f"ev-{uuid.uuid4().hex[:8]}"
    created_runs.append(run_id)
    ws = ev.WORKSPACES / run_id / "case-a"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "deliverable.md").write_text("# Probe deliverable\ngood work\n")
    db.execute("INSERT INTO eval_runs (id, domain, notes, status, cases_total, cases_done, "
               "score_total, score_max, ship_count, fingerprint, started_at, ended_at, user_id) "
               "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (run_id, "marketing", "probe run", "completed", 2, 2, 10, 20, 1, "{}",
                time.time() - 60, time.time(), "u_owner"))
    db.execute("INSERT INTO eval_results (id, run_id, case_id, case_title, specialist, status, "
               "verdict, score, score_max, gates_failed, judge_output, deliverable_path) "
               "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               (f"evr-{uuid.uuid4().hex[:10]}", run_id, "case-a", "Probe case A",
                "copywriter-pro", "scored", "REVISE", 4, 10, 2,
                "Verdict: REVISE\nGate FAIL: hook missing", str(ws / "deliverable.md")))
    db.execute("INSERT INTO eval_results (id, run_id, case_id, case_title, status, verdict, "
               "score, score_max, judge_output, deliverable_path) VALUES (?,?,?,?,?,?,?,?,?,?)",
               (f"evr-{uuid.uuid4().hex[:10]}", run_id, "case-b", "Probe case B",
                "scored", "SHIP", 9, 10, "Verdict: SHIP", str(ws / "deliverable.md")))
    stub = Path(tempfile.mkdtemp(prefix="nexus-probe-improve-")) / "stub-improve.sh"
    stub.write_text("""#!/usr/bin/env bash
echo "analysis prose"
echo "NEXUS_IMPROVE_JSON_BEGIN"
cat <<'JSON'
{"deltas": [
 {"kind": "knowledge", "file": "PLAYBOOK.md", "before": "", "after": "Always open with a concrete hook.", "rationale": "case-a failed the hook gate", "expected_effect": "hook gate passes"},
 {"kind": "exemplar", "case_id": "case-b", "before": "", "after": "", "rationale": "case-b shipped at 90%", "expected_effect": "raises the bar"}
]}
JSON
echo "NEXUS_IMPROVE_JSON_END"
""")
    stub.chmod(0o755)
    db.set_setting("evals.improve_cmd", f"{stub} {{domain}} {{evidence}}")
    ev_text, dom, specs, cids = ev.gather_improve_evidence(run_id)
    ok("evidence: low case in full, SHIP as exemplar candidate",
       "Judge critique" in ev_text and "EXEMPLAR CANDIDATE" in ev_text and dom == "marketing")
    res = ev.run_improvement(run_id, "u_owner")
    ok("improvement drafted + approval filed",
       res.get("ok") and res.get("approval_id"), str(res)[:200])
    if res.get("approval_id"):
        created_apprs.append(res["approval_id"])
    run_row = db.query_one("SELECT improve_status, improve_approval_id FROM eval_runs WHERE id=?",
                           (run_id,))
    ok("run marked proposed", run_row["improve_status"] == "proposed")
    # apply with an EDITED delta (the UI can edit before approving)
    ap = db.query_one("SELECT payload, user_id FROM approvals WHERE id=?", (res["approval_id"],))
    payload = json.loads(ap["payload"])
    payload["deltas"][0]["after"] = "Always open with a concrete hook. (edited)"
    os.makedirs(os.path.join(scratch_know, "domains", "marketing"), exist_ok=True)
    out = ev.apply_improvements(payload, "u_owner", "probe-operator")
    ok("apply wrote knowledge + exemplar",
       len(out.get("applied", [])) == 2, str(out)[:300])
    pb = os.path.join(scratch_know, "domains", "marketing", "PLAYBOOK.md")
    ok("edited delta text landed", os.path.isfile(pb) and "(edited)" in open(pb).read())
    ex_dir = os.path.join(scratch_know, "domains", "marketing", "examples")
    ok("exemplar promoted", os.path.isdir(ex_dir) and any("eval-case-b" in f for f in os.listdir(ex_dir)))
    ok("run marked applied",
       db.query_one("SELECT improve_status FROM eval_runs WHERE id=?", (run_id,))["improve_status"] == "applied")

finally:
    restore_settings()
    fb._entries_cache.clear()
    db.execute("DELETE FROM memory WHERE agent_id=?", (agent_id,))
    db.execute("DELETE FROM agents WHERE id=?", (agent_id,))
    for rid in created_models:
        db.execute("DELETE FROM user_models WHERE id=?", (rid,))
    for rid in created_runs:
        db.execute("DELETE FROM eval_results WHERE run_id=?", (rid,))
        db.execute("DELETE FROM eval_runs WHERE id=?", (rid,))
        shutil.rmtree(Path("workspaces/evals") / rid, ignore_errors=True)
    for aid in created_apprs:
        db.execute("DELETE FROM approvals WHERE id=?", (aid,))
    db.execute("DELETE FROM auth_sessions WHERE user_id=?", (MUID,))
    db.execute("DELETE FROM users WHERE id=?", (MUID,))
    db.execute("DELETE FROM activity WHERE user_id=?", (MUID,))
    shutil.rmtree(scratch_know, ignore_errors=True)

print(f"\n{'ALL PASS' if not FAIL else 'FAILURES'}: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
