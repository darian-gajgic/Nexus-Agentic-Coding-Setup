"""NEXUS verify gate — Super Result (grounded critic loop), end to end.

Exercises the WHOLE feature against the LIVE service with a stubbed critic
(settings key super.critic_cmd — restored in finally, same contract as the
judge gates): critic run → auto-comments (source/anchors) → retry drain →
closed auto-round → convergence escalation → round-cap escalation → SHIP
quiet-stop → open-mode checkpoint → approve/reject semantics → workflow
cascade → revalidate reconciler repair. Self-cleaning.

The loop transitions are driven by the REAL in-server sweep (20 s cadence),
so this gate takes a few minutes. Probe tasks carry a dependency on a parked
backlog task, so no live agent lane ever claims them after a retry.

Run:  .venv/bin/python scripts/verify_super_result_e2e.py
"""
import json
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "scripts"))
os.chdir(APP)

import httpx  # noqa: E402
import database as db  # noqa: E402
from _gate_auth import owner_cookie  # noqa: E402

BASE = "https://127.0.0.1:8777"
SWEEP_WAIT = 75  # ≥3 sweep cycles of margin

c = httpx.Client(base_url=BASE, verify=False, cookies=owner_cookie(), timeout=30)
PASS = FAIL = 0
made_tasks: list = []
made_wfs: list = []
stub_dir = tempfile.mkdtemp(prefix="sr-gate-")
orig_cmd = db.get_setting("super.critic_cmd")
orig_frontier_max = db.get_setting("frontier.max_concurrent")
orig_frontier_backoff = db.get_setting("frontier.quota_backoff_until")
orig_frontier_consec = db.get_setting("frontier.quota_consecutive")
made_dirs: list = []  # scratch dirs to remove in the finally block


def chk(name, cond):
    global PASS, FAIL
    print(("  PASS  " if cond else "  FAIL  ") + name, flush=True)
    PASS, FAIL = PASS + (1 if cond else 0), FAIL + (0 if cond else 1)


def write_stub(name, findings_js, verdict="REVISE"):
    """A canned critic that validates the sandbox contract, then prints
    sentinel JSON. findings_js may embed $RANDOM for per-round variation."""
    fp = Path(stub_dir) / name
    fp.write_text(f"""#!/usr/bin/env bash
set -euo pipefail
FILE="${{1:?}}"; DOMAIN="${{2:?}}"; SANDBOX="${{3:?}}"
[ -f "$SANDBOX/_critic_context/context.json" ] || exit 1
[ -f "$FILE" ] || exit 1
cat <<EOF
NEXUS_CRITIC_JSON_BEGIN
{{"verdict": "{verdict}", "confidence": 0.9, "summary": "gate stub",
 "findings": [{findings_js}],
 "contradictions": [], "missing": [],
 "revision_brief": "Gate stub brief: fix the findings.",
 "learning_note": "gate stub note"}}
NEXUS_CRITIC_JSON_END
EOF
""")
    fp.chmod(fp.stat().st_mode | stat.S_IEXEC)
    return str(fp)


def write_raw_stub(name, body):
    """An arbitrary bash critic (for the quota / garbage / concurrency probes
    that must NOT emit valid sentinel JSON, or must record timing)."""
    fp = Path(stub_dir) / name
    fp.write_text("#!/usr/bin/env bash\n" + body)
    fp.chmod(fp.stat().st_mode | stat.S_IEXEC)
    return str(fp)


def make_plain(title, parked_dep):
    """A NON-super_result task with a workspace + deliverable — critiquable via
    the /critic endpoint directly, but invisible to the sweep (so parallel POST
    tests aren't polluted by sweep-dispatched critics)."""
    tid = c.post("/api/tasks", json={"title": title, "description": "SR gate plain",
                                     "status": "review",
                                     "depends_on": [parked_dep]}).json()["id"]
    made_tasks.append(tid)
    ws = APP / "workspaces" / tid
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "deliverable.md").write_text("gate probe line one\nline two\n")
    db.execute("UPDATE tasks SET dispatch_state='completed', workspace_path=?, "
               "updated_at=? WHERE id=?", (str(ws), time.time(), tid))
    return tid


FIXED_FINDING = ('{"severity": "high", "file_path": "workspace/deliverable.md", '
                 '"side": "new", "line_no": 1, "line_text": "", '
                 '"claim": "fixed claim", "evidence": "fixed evidence", '
                 '"problem": "fixed problem", "suggested_fix": "fixed fix"},'
                 '{"severity": "medium", "file_path": "workspace/deliverable.md", '
                 '"side": "new", "line_no": null, "line_text": "", '
                 '"claim": "fixed claim B", "evidence": "ev B", '
                 '"problem": "problem B", "suggested_fix": "fix B"}')
VARYING_FINDING = ('{"severity": "high", "file_path": "workspace/deliverable.md", '
                   '"side": "new", "line_no": 1, "line_text": "", '
                   '"claim": "varying claim $RANDOM-$RANDOM", "evidence": "ev", '
                   '"problem": "problem $RANDOM", "suggested_fix": "fix"}')

STUB_FIXED = write_stub("critic_fixed.sh", FIXED_FINDING)
STUB_VARY = write_stub("critic_vary.sh", VARYING_FINDING)
STUB_SHIP = write_stub("critic_ship.sh", "", verdict="SHIP")


def set_stub(path):
    db.set_setting("super.critic_cmd", f"{path} {{file}} {{domain}} {{sandbox}}")


def make_probe(title, parked_dep, loop_patch=None, mode=None):
    r = c.post("/api/tasks", json={"title": title, "description": "SR gate probe",
                                   "status": "review", "super_result": True,
                                   "depends_on": [parked_dep]})
    t = r.json()
    tid = t["id"]
    made_tasks.append(tid)
    ws = APP / "workspaces" / tid
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "deliverable.md").write_text("gate probe line one\nline two\n")
    if mode:
        d = c.post("/api/loop/design", json={"kind": "task", "id": tid, "mode": mode}).json()
        c.patch(f"/api/tasks/{tid}", json={"loop_config": d["loop_config"]})
    if loop_patch:
        cfg = json.loads(db.query_one("SELECT loop_config FROM tasks WHERE id=?", (tid,))["loop_config"])
        for trig in cfg.get("triggers") or []:
            if trig["id"] == "super_result":
                trig.update(loop_patch)
        c.patch(f"/api/tasks/{tid}", json={"loop_config": cfg})
    db.execute("UPDATE tasks SET dispatch_state='completed', workspace_path=?, "
               "updated_at=? WHERE id=?", (str(ws), time.time(), tid))
    return tid


def wait_for(fn, timeout=SWEEP_WAIT, step=2):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return None


def task_row(tid):
    return db.query_one("SELECT * FROM tasks WHERE id=?", (tid,))


def sr_approval(tid, status="pending"):
    return db.query_one(
        "SELECT * FROM approvals WHERE status=? AND action_type='super_result' "
        "AND payload LIKE ?", (status, f'%"task_id": "{tid}"%'))


def simulate_completion(tid):
    ws = APP / "workspaces" / tid
    (ws / "deliverable.md").write_text("gate probe line one\nline two\n")
    db.execute("UPDATE tasks SET status='review', dispatch_state='completed', "
               "claimed_by=NULL, updated_at=? WHERE id=?", (time.time(), tid))


try:
    print("═══ SUPER RESULT E2E (stubbed critic, live sweep) ═══", flush=True)
    server_src = (APP / "server.py").read_text()
    chk("B1: boot reset of orphaned critic runs present",
        "WHERE critic_verdict='running'" in server_src
        and "orphaned by restart" in server_src)

    # fast in-process unit checks (typing + N2 parse)
    import evals
    chk("detect_deliverable_type mapping",
        evals.detect_deliverable_type({"repo_path": "/x"}) == "code_change"
        and evals.detect_deliverable_type({"specialist": "web-researcher"}) == "research"
        and evals.detect_deliverable_type({"title": "Audit the flaky suite"}) == "analysis"
        and evals.detect_deliverable_type({"title": "Write the landing page"}) == "content")
    m = evals.parse_judge_metrics(
        'VERDICT: REVISE\nNEXUS_JUDGE_JSON_BEGIN\n{"verdict": "REVISE", "findings": '
        '[{"file_path": "deliverable.md", "line_no": 2, "line_text": "x", '
        '"problem": "p", "fix": "f"}], "revision_brief": "brief"}\nNEXUS_JUDGE_JSON_END')
    chk("N2: judge sentinel JSON parses (findings + brief)",
        len(m.get("findings") or []) == 1 and m.get("revision_brief") == "brief")

    r = c.post("/api/tasks", json={"title": "sr-gate bad dtype", "deliverable_type": "poem"})
    chk("deliverable_type validation → 400", r.status_code == 400)

    dep = c.post("/api/tasks", json={"title": "sr-gate parked dep",
                                     "description": "never done"}).json()["id"]
    made_tasks.append(dep)

    # ── closed loop: critique → auto-comments → auto-retry ──
    set_stub(STUB_FIXED)
    t1 = make_probe("sr-gate closed probe", dep)
    cfg = json.loads(task_row(t1)["loop_config"])
    chk("super_result flag designed its loop trigger",
        any(x["id"] == "super_result" for x in cfg["triggers"])
        and not any(x["id"] == "judge_revise" for x in cfg["triggers"]))
    chk("sweep ran the critic (REVISE)",
        bool(wait_for(lambda: task_row(t1).get("critic_verdict") == "REVISE")))
    rows = db.query_all("SELECT * FROM review_comments WHERE task_id=? AND status='open'", (t1,))
    chk("auto-comments filed with source='critic'",
        len(rows) == 2 and all(x["source"] == "critic" for x in rows))
    anchored = [x for x in rows if x.get("line_no") == 1]
    chk("line anchor validated against the real file",
        len(anchored) == 1 and anchored[0]["line_text"] == "gate probe line one")
    g = c.get(f"/api/tasks/{t1}/critic").json()
    chk("GET /critic: parsed payload + round + comment count",
        g["verdict"] == "REVISE" and g["round"] == 1
        and (g["parsed"] or {}).get("learning_note") == "gate stub note"
        and g["open_critic_comments"] == 2)
    chk("closed loop auto-retried with the revision brief",
        bool(wait_for(lambda: task_row(t1)["status"] == "todo")))
    t1row = task_row(t1)
    fb = t1row.get("retry_feedback") or ""
    chk("retry drained brief + [CRITIC] comments",
        "SUPER RESULT round 1/" in fb and "Gate stub brief" in fb and "[CRITIC]" in fb)
    chk("comments consumed (none open)",
        db.query_one("SELECT COUNT(*) n FROM review_comments WHERE task_id=? AND status='open'",
                     (t1,))["n"] == 0)

    # ── convergence: identical keys round 2 → escalation approval ──
    simulate_completion(t1)
    chk("critic round 2 ran",
        bool(wait_for(lambda: int(task_row(t1).get("critic_round") or 0) >= 2)))
    ap = wait_for(lambda: sr_approval(t1))
    chk("convergence escalated (no new findings)",
        bool(ap) and "no new findings" in (json.loads(ap["payload"]).get("reason") or ""))
    chk("no auto-retry on escalation", task_row(t1)["status"] == "review")

    # ── reject → rework with feedback, round bumped, approval expired path ──
    r = c.patch(f"/api/approvals/{ap['id']}", json={"status": "rejected",
                                                    "feedback": "gate says: fix it"})
    chk("checkpoint reject accepted", r.status_code == 200)
    t1row = task_row(t1)
    trig = next(x for x in json.loads(t1row["loop_config"])["triggers"]
                if x["id"] == "super_result")
    chk("reject → retried + round bumped + state re-armed",
        t1row["status"] == "todo" and "gate says: fix it" in (t1row.get("retry_feedback") or "")
        and int(trig.get("used") or 0) == 2 and not trig.get("state"))
    chk("no pending SR approval left after decision", not sr_approval(t1))

    # ── round cap: max_rounds=1 + varying findings → cap escalation ──
    set_stub(STUB_VARY)
    t2 = make_probe("sr-gate cap probe", dep, loop_patch={"max_rounds": 1})
    chk("cap probe: round 1 critique + auto-retry (1/1)",
        bool(wait_for(lambda: task_row(t2)["status"] == "todo", timeout=100)))
    simulate_completion(t2)
    ap2 = wait_for(lambda: sr_approval(t2), timeout=100)
    chk("round cap reached → escalation",
        bool(ap2) and "round cap" in (json.loads(ap2["payload"]).get("reason") or ""))

    # ── SHIP: quiet terminal state ──
    set_stub(STUB_SHIP)
    t3 = make_probe("sr-gate ship probe", dep)
    chk("SHIP verdict landed",
        bool(wait_for(lambda: task_row(t3).get("critic_verdict") == "SHIP")))
    chk("SHIP marked terminal 'done' state",
        bool(wait_for(lambda: (next((x for x in json.loads(task_row(t3)["loop_config"])
                                     ["triggers"] if x["id"] == "super_result"), {})
                               .get("state") or {}).get("kind") == "done")))
    chk("SHIP is quiet (no retry, no approval)",
        task_row(t3)["status"] == "review" and not sr_approval(t3))

    # ── open mode: checkpoint instead of retry; approve accepts ──
    set_stub(STUB_FIXED)
    t4 = make_probe("sr-gate open probe", dep, mode="open")
    ap4 = wait_for(lambda: sr_approval(t4), timeout=100)
    chk("open mode: checkpoint approval, no auto-retry",
        bool(ap4) and task_row(t4)["status"] == "review")
    r = c.patch(f"/api/approvals/{ap4['id']}", json={"status": "approved"})
    trig4 = wait_for(lambda: (next((x for x in json.loads(task_row(t4)["loop_config"])
                                    ["triggers"] if x["id"] == "super_result"), {})
                              .get("state") or {}).get("kind") == "done", timeout=15)
    chk("approve → mark_super_done", r.status_code == 200 and bool(trig4))

    # ── workflow cascade ──
    w = c.post("/api/workflows", json={"name": "sr-gate wf", "super_result": True}).json()
    made_wfs.append(w["id"])
    wrow = db.query_one("SELECT * FROM workflows WHERE id=?", (w["id"],))
    wcfg = json.loads(wrow["loop_config"] or "{}")
    chk("workflow create: flag + designed trigger",
        wrow["super_result"] == 1
        and any(x["id"] == "super_result" for x in wcfg.get("triggers") or []))
    member = c.post("/api/tasks", json={"title": "sr-gate wf member",
                                        "workflow_id": w["id"]}).json()["id"]
    made_tasks.append(member)
    c.patch(f"/api/workflows/{w['id']}", json={"super_result": True})
    chk("workflow PATCH cascades flag to member tasks",
        task_row(member)["super_result"] == 1)
    c.patch(f"/api/workflows/{w['id']}", json={"super_result": False})
    wrow = db.query_one("SELECT * FROM workflows WHERE id=?", (w["id"],))
    wcfg = json.loads(wrow["loop_config"] or "{}")
    chk("workflow flag OFF strips trigger + member flags",
        task_row(member)["super_result"] == 0
        and not any(x["id"] == "super_result" for x in wcfg.get("triggers") or []))

    # ── revalidate: fan-out reconciler repair + multi-reviewer wiring ──
    inv = lambda i: {"title": f"Investigate lens {i}", "description": "x" * 30,
                     "tags": ["investigation", "fanout"], "depends_on_idx": []}
    r = c.post("/api/tasks/wizard/revalidate",
               json={"name": "sr-gate audit", "tasks": [inv(1), inv(2), inv(3)]})
    tasks = r.json()["tasks"]
    rec = [t for t in tasks if "reconciler" in (t.get("tags") or [])]
    incoming = {x for t in tasks for x in t["depends_on_idx"]}
    sinks = [i for i in range(len(tasks)) if i not in incoming]
    chk("revalidate appends reconciler as unique sink",
        len(rec) == 1 and rec[0]["depends_on_idx"] == [0, 1, 2]
        and sinks == [tasks.index(rec[0])])
    chk("reconciler carries super_result + deliverable_type",
        rec[0].get("super_result") is True and rec[0].get("deliverable_type") == "analysis")
    coding = [
        {"title": "Spec", "description": "x" * 30, "specialist": "tech-lead-orchestrator",
         "domain": "software-engineering", "depends_on_idx": []},
        {"title": "Implement", "description": "x" * 30, "specialist": "code-implementer",
         "domain": "software-engineering", "depends_on_idx": [0]},
        {"title": "Review A", "description": "x" * 30, "specialist": "code-reviewer",
         "domain": "software-engineering", "depends_on_idx": [1]},
        {"title": "Review B", "description": "x" * 30, "specialist": "code-reviewer",
         "domain": "software-engineering", "depends_on_idx": [1]},
        {"title": "Fix findings", "description": "x" * 30, "specialist": "code-implementer",
         "domain": "software-engineering", "depends_on_idx": [1, 2]},
        {"title": "Acceptance verification", "description": "x" * 30,
         "specialist": "acceptance-verifier", "domain": "software-engineering",
         "high_stakes": True, "depends_on_idx": [0, 4]},
    ]
    r = c.post("/api/tasks/wizard/revalidate", json={"name": "sr-gate build", "tasks": coding})
    tasks = r.json()["tasks"]
    ra = next(i for i, t in enumerate(tasks) if t["title"].startswith("Review A"))
    rb = next(i for i, t in enumerate(tasks) if t["title"].startswith("Review B"))
    fx = next(i for i, t in enumerate(tasks) if t["title"].startswith("Fix"))
    vr = next(i for i, t in enumerate(tasks) if t["specialist"] == "acceptance-verifier")
    chk("multi-reviewer: fix + verifier gate on BOTH reviews",
        {ra, rb} <= set(tasks[fx]["depends_on_idx"])
        and {ra, rb} <= set(tasks[vr]["depends_on_idx"]))

    # ═══════════════════ Fixes 2026-07-10 — the 9-finding batch ═══════════════════
    print("─── FIXES 2026-07-10 regression checks ───", flush=True)

    # ── Finding 4: appended reconciler survives a wide fan-out (was truncated
    #    at tasks[:7] — the reconciler landed at index 8 and was dropped) ──
    wide = [{"title": f"Investigate lens {i}", "description": "x" * 30,
             "tags": ["investigation", "fanout"], "depends_on_idx": []}
            for i in range(7)]
    r = c.post("/api/tasks/wizard/revalidate",
               json={"name": "sr-gate wide fanout", "tasks": wide})
    wtasks = r.json()["tasks"]
    wrecs = [t for t in wtasks if "reconciler" in (t.get("tags") or [])]
    wincoming = {x for t in wtasks for x in t["depends_on_idx"]}
    wsinks = [i for i in range(len(wtasks)) if i not in wincoming]
    chk("finding 4: reconciler survives 7 raw fan-out tasks (not truncated)",
        len(wtasks) == 8 and len(wrecs) == 1
        and wrecs[0]["depends_on_idx"] == list(range(7))
        and wsinks == [wtasks.index(wrecs[0])])

    # ── Finding 5: create/attach into a super_result workflow inherits the flag
    #    (BOTH doors) — the inherited-loop sweep needs tasks.super_result=1 ──
    w5 = c.post("/api/workflows", json={"name": "sr-gate inherit wf",
                                        "super_result": True}).json()
    made_wfs.append(w5["id"])
    m_create = c.post("/api/tasks", json={"title": "sr inherit via create",
                                          "workflow_id": w5["id"]}).json()["id"]
    made_tasks.append(m_create)
    chk("finding 5a: create into SR workflow inherits the flag",
        task_row(m_create)["super_result"] == 1)
    m_attach = c.post("/api/tasks", json={"title": "sr inherit via patch"}).json()["id"]
    made_tasks.append(m_attach)
    before = task_row(m_attach)["super_result"]
    c.patch(f"/api/tasks/{m_attach}", json={"workflow_id": w5["id"]})
    chk("finding 5b: PATCH workflow_id into SR workflow inherits the flag",
        before == 0 and task_row(m_attach)["super_result"] == 1)

    # ── Finding 8: the /critic endpoint is a CAS — two concurrent POSTs on ONE
    #    task must produce exactly one 200 + one 409 (check-then-act let both
    #    through). A slow stub keeps the first run 'running' during the race. ──
    import threading as _threading
    conc_body = (
        'set -euo pipefail\n'
        'FILE="${1:?}"; DOMAIN="${2:?}"; SANDBOX="${3:?}"\n'
        f'D="{stub_dir}/conc"\n'
        'mkdir -p "$D"; touch "$D/active.$$"\n'
        'ls "$D"/active.* 2>/dev/null | wc -l >> "$D/peak.log"\n'
        'sleep 4\n'
        'rm -f "$D/active.$$"\n'
        'cat <<EOF\n'
        'NEXUS_CRITIC_JSON_BEGIN\n'
        '{"verdict":"SHIP","confidence":0.9,"summary":"conc","findings":[],'
        '"contradictions":[],"missing":[],"revision_brief":""}\n'
        'NEXUS_CRITIC_JSON_END\n'
        'EOF\n')
    STUB_CONC = write_raw_stub("critic_conc.sh", conc_body)
    set_stub(STUB_CONC)
    cas_tid = make_plain("sr-gate CAS probe", dep)
    cas_codes = {}

    def _post_critic(tid, key):
        cas_codes[key] = c.post(f"/api/tasks/{tid}/critic").status_code
    th1 = _threading.Thread(target=_post_critic, args=(cas_tid, "a"))
    th2 = _threading.Thread(target=_post_critic, args=(cas_tid, "b"))
    th1.start(); th2.start(); th1.join(); th2.join()
    chk("finding 8: concurrent /critic POSTs → exactly one 200, one 409 (CAS)",
        sorted(cas_codes.values()) == [200, 409])
    wait_for(lambda: task_row(cas_tid).get("critic_verdict") == "SHIP", timeout=30)

    # ── Finding 3a: the frontier semaphore caps concurrent critic subprocesses.
    #    Three parallel POSTs (distinct tasks) with frontier.max_concurrent=2 →
    #    the peak observed concurrency is exactly 2. ──
    db.set_setting("frontier.max_concurrent", "2")
    shutil.rmtree(Path(stub_dir) / "conc", ignore_errors=True)  # fresh peak.log
    conc_tids = [make_plain(f"sr-gate sem probe {i}", dep) for i in range(3)]
    sem_codes = []
    sem_threads = [_threading.Thread(target=lambda t=t: sem_codes.append(
        c.post(f"/api/tasks/{t}/critic").status_code)) for t in conc_tids]
    for th in sem_threads:
        th.start()
    for th in sem_threads:
        th.join()
    for t in conc_tids:
        wait_for(lambda t=t: task_row(t).get("critic_verdict") == "SHIP", timeout=40)
    peak_fp = Path(stub_dir) / "conc" / "peak.log"
    peaks = [int(x) for x in peak_fp.read_text().split()] if peak_fp.is_file() else []
    chk("finding 3a: frontier semaphore honored under 3 parallel critics (peak==2)",
        all(x == 200 for x in sem_codes) and bool(peaks) and max(peaks) == 2)

    # ── Finding 3b (in-process gate): a stronger, timing-free proof that the
    #    gate never exceeds its limit. ──
    import evals as _ev_gate
    _ev_gate.db.set_setting("frontier.max_concurrent", "3")
    _peak = {"n": 0, "cur": 0}
    _plock = _threading.Lock()

    def _use_gate():
        with _ev_gate._FRONTIER_GATE:
            with _plock:
                _peak["cur"] += 1
                _peak["n"] = max(_peak["n"], _peak["cur"])
            time.sleep(0.3)
            with _plock:
                _peak["cur"] -= 1
    gate_threads = [_threading.Thread(target=_use_gate) for _ in range(8)]
    for th in gate_threads:
        th.start()
    for th in gate_threads:
        th.join()
    chk("finding 3b: _FrontierGate never exceeds the configured limit (<=3)",
        1 <= _peak["n"] <= 3)
    db.set_setting("frontier.max_concurrent", "2")

    # ── Finding 6: an empty-findings REVISE is a contradiction → escalate (the
    #    old convergence guard let empty findings fall through to a retry). ──
    STUB_EMPTY = write_stub("critic_empty.sh", "", verdict="REVISE")
    set_stub(STUB_EMPTY)
    t6 = make_probe("sr-gate empty-findings probe", dep)
    ap6 = wait_for(lambda: sr_approval(t6), timeout=120)
    chk("finding 6: empty-findings REVISE escalates (not retried)",
        bool(ap6) and "no findings" in (json.loads(ap6["payload"]).get("reason") or "")
        and task_row(t6)["status"] == "review")

    # ── Finding 2: a genuine content error (no JSON, no quota signature) lands a
    #    terminal 'error' verdict + escalation — the row is NEVER left 'running'.
    #    Plus source-level guards for the catch-all + verdict-before-insert. ──
    STUB_GARBAGE = write_raw_stub("critic_garbage.sh",
                                  'echo "this is not json and mentions nothing special"\n'
                                  'exit 0\n')
    set_stub(STUB_GARBAGE)
    t2 = make_probe("sr-gate content-error probe", dep)
    chk("finding 2: content error → terminal 'error' verdict (never stranded 'running')",
        bool(wait_for(lambda: task_row(t2).get("critic_verdict") == "error", timeout=120)))
    ap2c = wait_for(lambda: sr_approval(t2), timeout=90)
    chk("finding 2: content error escalates to a human checkpoint",
        bool(ap2c) and "critic run failed" in (json.loads(ap2c["payload"]).get("reason") or ""))
    chk("finding 2: _critic_thread has a catch-all + verdict-before-insert ordering",
        "critic thread crashed" in server_src
        and "critic_verdict IS NULL OR critic_verdict='running'" in server_src
        and server_src.index("SET critic_verdict=?, critic_output=?, critic_json=?")
        < server_src.index("_insert_critic_comments(task, parsed, source=\"critic\")"))
    chk("finding 7: verdict-transition broadcasts are wired",
        "def broadcast_threadsafe" in server_src
        and "_broadcast_task_row(task_id, owner)" in server_src
        and "_broadcast_task(tid, t.get(\"user_id\"))" in
        (APP / "loop_engine.py").read_text())

    # ── Finding 1: UNSTUBBED build_critic_sandbox against a scratch repo whose
    #    task branch exists ONLY as origin/nexus/<slug> — the sandbox tree must
    #    contain the branch-only file (proving it checked out the task branch,
    #    not the base branch). ──
    import subprocess as _subp
    import worktree as _wt_gate
    # Same filesystem as the critic sandbox (app/workspaces/_critic): `git clone
    # --local` hardlinks the object store, which fails cross-device (e.g. /tmp
    # tmpfs → $HOME). Real repos + sandboxes always share a device.
    scratch = tempfile.mkdtemp(prefix="sr-gate-repo-", dir=str(APP / "workspaces"))
    made_dirs.append(scratch)

    def _g(*a, cwd=scratch):
        _subp.run(["git", "-C", cwd, *a], check=True, capture_output=True, text=True)
    _subp.run(["git", "init", "-q", scratch], check=True, capture_output=True)
    _g("config", "user.email", "gate@t"); _g("config", "user.name", "gate")
    _g("config", "commit.gpgsign", "false")
    (Path(scratch) / "base.txt").write_text("base only\n")
    _g("add", "-A"); _g("commit", "-q", "-m", "base")
    _g("branch", "-M", "main")
    info = _wt_gate.ensure_task_worktree(scratch, "sandbox01")  # branch nexus/sandbox01
    wtp = info["worktree_path"]
    (Path(wtp) / "branch_only.txt").write_text("only on the task branch\n")
    _g("add", "-A", cwd=wtp)
    _g("-c", "user.email=gate@t", "-c", "user.name=gate", "commit", "-q",
       "-m", "branch work", cwd=wtp)
    sbx_ws = Path(scratch) / "_ws"
    sbx_ws.mkdir()
    (sbx_ws / "deliverable.md").write_text("sandbox deliverable\n")
    sbx_task = {"id": "task-sandbox01", "repo_path": scratch,
                "workspace_path": str(sbx_ws), "domain": "", "title": "sandbox",
                "description": "critic sandbox branch test"}
    sandbox_root, _deliv = evals.build_critic_sandbox(sbx_task, round_no=1)
    made_dirs.append(str(sandbox_root))
    branch_file = sandbox_root / "repo" / "branch_only.txt"
    try:
        ctx = json.loads((sandbox_root / "_critic_context" / "context.json").read_text())
    except Exception:
        ctx = {}
    chk("finding 1: critic sandbox checks out the task branch (branch-only file present)",
        branch_file.is_file()
        and branch_file.read_text().strip() == "only on the task branch"
        and ctx.get("repo_branch") == "nexus/sandbox01")

    # ── Finding 3 (quota): a rate-limit failure leaves the task QUEUED (verdict
    #    cleared, NOT 'error') and DOES NOT escalate; a backoff window is set.
    #    Run last — it arms the frontier backoff (cleared in finally). ──
    STUB_QUOTA = write_raw_stub("critic_quota.sh",
                                'echo "API Error: 429 Too Many Requests — rate limit exceeded '
                                '(usage limit)"\nexit 1\n')
    db.set_setting("frontier.quota_backoff_until", "0")
    db.set_setting("frontier.quota_consecutive", "0")
    set_stub(STUB_QUOTA)
    tq = make_probe("sr-gate quota probe", dep)  # super_result → sweep dispatches it
    # the sweep runs the critic; the thread classifies the 429 as quota, arms
    # the backoff, and clears the verdict WITHOUT storing 'error' or escalating
    wait_for(lambda: float(db.get_setting("frontier.quota_backoff_until", "0") or 0)
             > time.time(), timeout=120)
    time.sleep(3)  # let the sweep settle (it must NOT escalate)
    qrow = task_row(tq)
    chk("finding 3 (quota): verdict is NOT 'error' (task stays queued/re-critiquable)",
        qrow.get("critic_verdict") not in ("error",))
    chk("finding 3 (quota): a frontier backoff window is armed",
        float(db.get_setting("frontier.quota_backoff_until", "0") or 0) > time.time())
    chk("finding 3 (quota): no super_result escalation raised on a quota hit",
        not sr_approval(tq))
finally:
    db.set_setting("super.critic_cmd", orig_cmd)
    # Restore frontier backpressure settings (the quota probe arms a real
    # backoff window that would otherwise freeze the live critic sweep).
    for key, val in (("frontier.max_concurrent", orig_frontier_max),
                     ("frontier.quota_backoff_until", orig_frontier_backoff),
                     ("frontier.quota_consecutive", orig_frontier_consec)):
        if val in (None, ""):
            db.execute("DELETE FROM settings WHERE key=?", (key,))
        else:
            db.set_setting(key, val)
    for tid in made_tasks:
        db.execute("DELETE FROM tasks WHERE id=?", (tid,))
        db.execute("DELETE FROM review_comments WHERE task_id=?", (tid,))
        db.execute("DELETE FROM approvals WHERE payload LIKE ?", (f'%"task_id": "{tid}"%',))
        shutil.rmtree(APP / "workspaces" / tid, ignore_errors=True)
    for wid in made_wfs:
        db.execute("DELETE FROM workflows WHERE id=?", (wid,))
    shutil.rmtree(stub_dir, ignore_errors=True)
    for d in made_dirs:
        shutil.rmtree(d, ignore_errors=True)
    print(f"cleanup done; critic_cmd restored: {db.get_setting('super.critic_cmd')}; "
          f"frontier backoff cleared: {db.get_setting('frontier.quota_backoff_until')}",
          flush=True)

print(f"\n{'ALL CHECKS PASSED' if FAIL == 0 else 'FAILURES'}: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
