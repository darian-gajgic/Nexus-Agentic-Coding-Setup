#!/usr/bin/env python3
"""Runtime gate: REAL Hermes dispatch (SPEC-REAL-AGENTS.md §7).

S2 scope — the worker process is the sole executor:
  1-3  claim mechanics, feature flag, queue-only dispatch
  4    happy path: worker executes a REAL api_* session; deliverable + tokens + transcript
  5    per-task budget exceeded -> blocked_budget (no GLM spend)
  6    quota storm (injected 429) -> blocked_quota + backoff; cleared -> auto-retry completes
  7    resume: kill the worker mid-stream -> watchdog restarts -> same session finishes
  8    retire: terminal lifecycle -> no respawn (zombie prevention)

Needs the nexus server AND hermes-gateway running. GLM-dependent steps use
trivially cheap prompts. Total cost per full run: a few thousand tokens.
"""
import json, os, signal, sqlite3, sys, time, pathlib, requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://127.0.0.1:8777"
ROOT = pathlib.Path(__file__).resolve().parent.parent
P, F = 0, 0

def ok(name, cond, extra=""):
    global P, F
    if cond: P += 1; print(f"  PASS  {name}")
    else:    F += 1; print(f"  FAIL  {name}  {extra}")

from _gate_auth import owner_cookie  # noqa: E402 — same-dir import
CK = owner_cookie()  # {} while login is off; owner session when multi-user is live

def post(path, **kw): return requests.post(BASE+path, timeout=35, verify=False, cookies=CK, **kw)
def patch(path, **kw): return requests.patch(BASE+path, timeout=10, verify=False, cookies=CK, **kw)
def get(path, **kw):  return requests.get(BASE+path, timeout=10, verify=False, cookies=CK, **kw)
def dele(path, **kw): return requests.delete(BASE+path, timeout=10, verify=False, cookies=CK, **kw)

def task_by_id(tid):
    return next((x for x in get("/api/tasks").json() if x["id"] == tid), {})

def wait_state(tid, states, timeout_s):
    deadline = time.time() + timeout_s
    t = {}
    while time.time() < deadline:
        t = task_by_id(tid)
        if t.get("dispatch_state") in states:
            return t
        time.sleep(2)
    return t

def clear_quota_keys():
    patch("/api/settings", json={"dispatch.quota_backoff_until": "0",
                                 "dispatch.quota_consecutive": "0",
                                 "dispatch.force_429": "0"})

print("=== 0. Preflight ===")
ok("nexus server up", get("/api/health").json().get("status") == "ok")
js = get("/api/jarvis/status").json()
ok("hermes API reachable", js.get("connected") is True, str(js))
if not js.get("connected"):
    print("ABORT: hermes-gateway/API not reachable — start it, then re-run.")
    sys.exit(1)
prev_flag = get("/api/settings", params={"prefix": "dispatch.enabled"}).json()["settings"] \
    .get("dispatch.enabled", "0")
# Captured up front so the janitor can restore it on ANY exit — a crashed run
# once left the stub wired in for 3 days and every "frontier judge" verdict was
# the same canned REVISE (2026-07-08 → 11). A captured value that already
# points at the stub is litter from an earlier crash: restore to "" (registry
# back-to-default = the real cjudge), never re-pin the stub.
_pj = get("/api/settings", params={"prefix": "judge.cmd"}).json()["settings"] \
    .get("judge.cmd", "")
prev_judge_cmd = "" if "judge_stub" in _pj else _pj
clear_quota_keys()

import atexit  # noqa: E402


def _janitor():
    """Crash-proof cleanup (runs on ANY exit, incl. mid-run exceptions):
    leftover probe tasks are CLAIMABLE work — crashed runs littered the
    operator's board for days and workers zombie-dispatched deleted probes
    (2026-07-09). Also heals litter from historic crashed runs."""
    try:
        for t in get("/api/tasks").json():
            title = str(t.get("title") or "")
            if title.startswith("E2E ") and title.endswith("probe"):
                dele(f"/api/tasks/{t['id']}")
        for a in get("/api/agents").json():
            if str(a.get("name") or "").startswith("E2E-"):
                post(f"/api/agents/{a['id']}/retire")
                dele(f"/api/agents/{a['id']}")
        clear_quota_keys()
        patch("/api/settings", json={"dispatch.enabled": prev_flag,
                                     "judge.cmd": prev_judge_cmd})
    except Exception:
        pass


atexit.register(_janitor)

print("=== 1. Real lane ===")
# defensive: remove lanes leaked by a previous CRASHED gate run
for a in get("/api/agents").json():
    if a["name"].startswith("E2E-"):
        post(f"/api/agents/{a['id']}/retire")
        dele(f"/api/agents/{a['id']}")
lane_obj = post("/api/agents", json={"name": "E2E-Lane", "auto_claim": False}).json()
lane = lane_obj["id"]
ok("lane spawned with real worker pid", bool(lane_obj.get("pid")), str(lane_obj)[:120])
other = post("/api/agents", json={"name": "E2E-Rival", "auto_claim": False}).json()["id"]

print("=== 2. Feature flag ===")
patch("/api/settings", json={"dispatch.enabled": "0"})
tA = post("/api/tasks", json={"title": "E2E dispatch probe",
                              "description": "Reply with exactly: OK",
                              "status": "todo", "domain": "general"}).json()["id"]
r = post(f"/api/tasks/{tA}/dispatch", json={"agent_id": lane})
ok("flag off -> 403", r.status_code == 403, str(r.status_code))
patch("/api/settings", json={"dispatch.enabled": "1"})

print("=== 3. Claim + queue mechanics ===")
r = post(f"/api/tasks/{tA}/dispatch", json={"agent_id": lane})
ok("dispatch accepted (queued)", r.status_code == 200 and r.json().get("ok") is True,
   f"{r.status_code} {r.text[:200]}")
ok("task claimed by lane", r.json()["task"]["claimed_by"] == lane)
r2 = post(f"/api/tasks/{tA}/claim", json={"agent_id": other})
ok("second claim -> 409", r2.status_code == 409, str(r2.status_code))
ok("409 names owner", r2.json().get("owner") == lane, str(r2.json()))
r3 = post(f"/api/tasks/{tA}/dispatch", json={"agent_id": lane})
ok("double dispatch -> 409", r3.status_code == 409, str(r3.status_code))

print("=== 4. Real session, real result (worker executes) ===")
t = wait_state(tA, ("completed", "failed", "blocked_quota", "blocked_budget"), 300)
ok("dispatch completed", t.get("dispatch_state") == "completed",
   f"state={t.get('dispatch_state')} err={t.get('dispatch_error')}")
sid = t.get("session_id") or ""
ok("real api_* session id", sid.startswith("api_"), sid)
ok("task landed in done", t.get("status") == "done", t.get("status"))
ok("real tokens recorded", (t.get("tokens_used") or 0) > 0, str(t.get("tokens_used")))
ws = t.get("workspace_path") or ""
deliv = pathlib.Path(ws) / "deliverable.md"
ok("deliverable.md exists", deliv.is_file(), ws)
ok("deliverable has content", deliv.is_file() and len(deliv.read_text().strip()) > 0)
tr = get(f"/api/tasks/{tA}/transcript").json()
ok("transcript >= 2 messages", len(tr.get("messages", [])) >= 2,
   f"n={len(tr.get('messages', []))} err={tr.get('error')}")
d = get("/api/dispatches", params={"task_id": tA}).json()["dispatches"]
ok("dispatch audit row completed", len(d) >= 1 and d[0]["state"] == "completed", str(d[:1]))

print("=== 5. Budget guardrail (no GLM spend) ===")
tB = post("/api/tasks", json={"title": "E2E budget probe", "description": "Reply OK",
                              "status": "todo", "budget_tokens": 1}).json()["id"]
post(f"/api/tasks/{tB}/claim", json={"agent_id": lane})
# Test fixture: emulate a task that already consumed tokens mid-flight (budgets
# cap ACCUMULATION — a fresh task at 0 tokens is always allowed a first turn).
con = sqlite3.connect(str(ROOT / "nexus.db")); con.execute(
    "UPDATE tasks SET tokens_used=5 WHERE id=?", (tB,)); con.commit(); con.close()
post(f"/api/tasks/{tB}/dispatch", json={"agent_id": lane})
t = wait_state(tB, ("blocked_budget", "completed", "failed"), 60)
ok("over-budget -> blocked_budget", t.get("dispatch_state") == "blocked_budget",
   t.get("dispatch_state"))

print("=== 6. Quota storm (injected 429) + auto-retry ===")
patch("/api/settings", json={"dispatch.force_429": "1"})
tC = post("/api/tasks", json={"title": "E2E quota probe",
                              "description": "Reply with exactly: OK",
                              "status": "todo"}).json()["id"]
post(f"/api/tasks/{tC}/dispatch", json={"agent_id": lane})
t = wait_state(tC, ("blocked_quota", "completed", "failed"), 60)
ok("injected 429 -> blocked_quota", t.get("dispatch_state") == "blocked_quota",
   t.get("dispatch_state"))
s = get("/api/settings", params={"prefix": "dispatch.quota"}).json()["settings"]
ok("backoff engaged", float(s.get("dispatch.quota_backoff_until", "0") or 0) > time.time(),
   str(s))
clear_quota_keys()  # storm over — the lane must retry the blocked task by itself
t = wait_state(tC, ("completed", "failed"), 300)
ok("blocked task auto-retried to completion", t.get("dispatch_state") == "completed",
   f"state={t.get('dispatch_state')} err={t.get('dispatch_error')}")

print("=== 7. Resume after worker death (R3) ===")
tD = post("/api/tasks", json={"title": "E2E resume probe",
                              "description": "Count from 1 to 120, one number per line. No commentary.",
                              "status": "todo"}).json()["id"]
post(f"/api/tasks/{tD}/dispatch", json={"agent_id": lane})
t = wait_state(tD, ("streaming",), 120)
ok("task streaming", t.get("dispatch_state") == "streaming", t.get("dispatch_state"))
sid_before = t.get("session_id")
pid = next(a["pid"] for a in get("/api/agents").json() if a["id"] == lane)
try:
    os.kill(pid, signal.SIGKILL)
    ok("worker killed mid-stream", True)
except Exception as e:
    ok("worker killed mid-stream", False, str(e))
t = wait_state(tD, ("completed", "failed", "blocked_quota"), 360)
ok("task finished despite death", t.get("dispatch_state") == "completed",
   f"state={t.get('dispatch_state')} err={t.get('dispatch_error')}")
ok("same session kept (context preserved)", t.get("session_id") == sid_before,
   f"{sid_before} -> {t.get('session_id')}")
lane_now = next(a for a in get("/api/agents").json() if a["id"] == lane)
ok("watchdog restarted the lane", lane_now.get("pid") and lane_now["pid"] != pid,
   str(lane_now.get("pid")))

print("=== 8. Retire = terminal, no respawn ===")
r = post(f"/api/agents/{lane}/retire")
ok("retire accepted", r.status_code == 200 and r.json().get("status") == "retired",
   r.text[:120])
time.sleep(25)  # > 2 watchdog sweeps
lane_now = next(a for a in get("/api/agents").json() if a["id"] == lane)
ok("still retired after 2+ sweeps", lane_now.get("status") == "retired",
   lane_now.get("status"))
ok("no zombie respawn (pid stays empty)", not lane_now.get("pid"), str(lane_now.get("pid")))

print("=== 8b. Health + quota + templates + onboarding (S4, no GLM) ===")
h = get("/api/health/full").json()
ids = {c["id"] for c in h.get("checks", [])}
ok("health panel covers all subsystems",
   {"gateway", "hermes_api", "qdrant", "langfuse", "ollama", "workers"} <= ids, str(ids))
ok("every red light has a fix command",
   all(c.get("fix") for c in h.get("checks", [])))
q = get("/api/quota").json()
ok("quota endpoint reports spend + backoff",
   "today_tokens" in q and "backoff_active" in q and "daily_cap" in q, str(q)[:120])
tpl = get("/api/templates").json()["templates"]
ok("templates load (5+)", len(tpl) >= 5, str(len(tpl)))
ok("templates carry domain+prefill", all(t.get("domain") and t.get("title") for t in tpl))
ob = get("/api/onboarding-status").json()
ok("onboarding status counts FILL slots", "total" in ob and "done" in ob, str(ob)[:120])

print("=== 8c. Orphan quiet-window floor (D1, no GLM) ===")
# orphan_run_state must never call a run 'dead' inside the stall cutoff + margin:
# a run surviving a stall-cut is already silent > stall at lane re-entry, so a
# quiet window ≤ stall would continue-turn into a LIVE run. Pure function of
# transcript age + settings — tested in-process with a stubbed transcript.
sys.path.insert(0, str(ROOT))
import hermes_dispatch as hd  # noqa: E402
_prev_qs = get("/api/settings", params={"prefix": "dispatch."}).json()["settings"]
_prev_quiet = _prev_qs.get("dispatch.resume_quiet_s", "")
_prev_stall = _prev_qs.get("dispatch.max_turn_stall_seconds", "")
_real_get_messages = hd.get_messages


def _fake_transcript(age_s):
    return [{"role": "user", "content": "working…", "timestamp": time.time() - age_s}]


try:
    patch("/api/settings", json={"dispatch.max_turn_stall_seconds": "900",
                                 "dispatch.resume_quiet_s": ""})
    hd.get_messages = lambda sid: _fake_transcript(900 - 60)
    ok("silent stall-60s -> active", hd.orphan_run_state({"session_id": "api_e2e_d1"}) == "active")
    hd.get_messages = lambda sid: _fake_transcript(900 + 400)
    ok("silent stall+400s -> dead", hd.orphan_run_state({"session_id": "api_e2e_d1"}) == "dead")
    patch("/api/settings", json={"dispatch.resume_quiet_s": "30"})
    hd.get_messages = lambda sid: _fake_transcript(950)
    ok("quiet=30 floored above stall (age 950 -> active)",
       hd.orphan_run_state({"session_id": "api_e2e_d1"}) == "active")
finally:
    hd.get_messages = _real_get_messages
    patch("/api/settings", json={"dispatch.resume_quiet_s": _prev_quiet,
                                 "dispatch.max_turn_stall_seconds": _prev_stall})

print("=== 9. Judge + approval flow (stubbed judge, no GLM) ===")
# Fixture: fabricate a COMPLETED high-stakes deliverable in 'review' (the state
# _finalize_result produces) so the R4 flow is testable at CI speed.
# assignee = the auto_claim=False gate lane, so the real fleet lanes never
# grab this fixture while it transits 'todo' (incl. after the retry below)
tE = post("/api/tasks", json={"title": "E2E judge probe", "status": "todo",
                              "domain": "marketing", "high_stakes": True,
                              "assignee_id": lane}).json()["id"]
ws_e = ROOT / "workspaces" / tE
ws_e.mkdir(parents=True, exist_ok=True)
(ws_e / "deliverable.md").write_text("# Hero section\nOur innovative solution helps teams.\n")
con = sqlite3.connect(str(ROOT / "nexus.db"))
con.execute("UPDATE tasks SET status='review', dispatch_state='completed', "
            "workspace_path=?, result_summary='stub' WHERE id=?", (str(ws_e), tE))
con.execute("DELETE FROM approvals WHERE id LIKE 'appr-e2estub%'")  # leftovers from prior runs
con.execute("INSERT INTO approvals (id, agent_id, action_type, description, payload, status, "
            "risk_level, requested_at, user_id) VALUES ('appr-e2estub', 'e2e', 'deliverable', "
            "'E2E judge probe review', ?, 'pending', 'high', 1, 'u_owner')",
            (json.dumps({"task_id": tE}),))
con.commit(); con.close()

# prev_judge_cmd was captured (and stub-sanitized) at preflight; the janitor
# restores it on any exit, the inline restore below handles the happy path.
patch("/api/settings", json={"judge.cmd": f"bash {ROOT}/scripts/judge_stub.sh {{file}} {{domain}}"})
r = post(f"/api/tasks/{tE}/judge")
ok("judge starts", r.status_code == 200, r.text[:150])
deadline = time.time() + 60
j = {}
while time.time() < deadline:
    j = get(f"/api/tasks/{tE}/judge").json()
    if not j.get("running"):
        break
    time.sleep(2)
ok("stub verdict parsed = REVISE", j.get("verdict") == "REVISE", str(j.get("verdict")))
ok("judge output stored", "Learning note" in (j.get("output") or ""), (j.get("output") or "")[:80])
files = get(f"/api/tasks/{tE}/files").json()["files"]
ok("files endpoint lists deliverable", any(f["name"] == "deliverable.md" for f in files), str(files))
r = get(f"/api/tasks/{tE}/files/deliverable.md")
ok("file download works", r.status_code == 200 and b"Hero section" in r.content)
r = get(f"/api/tasks/{tE}/files/..%2Fnexus.db")
ok("path traversal blocked", r.status_code in (403, 404), str(r.status_code))
# reject with feedback -> retry: back to todo, feedback attached, deliverable versioned
r = patch("/api/approvals/appr-e2estub", json={"status": "rejected", "decided_by": "e2e",
                                               "feedback": "headline names no outcome"})
ok("reject decision accepted", r.status_code == 200, r.text[:120])
r = patch("/api/approvals/appr-e2estub", json={"status": "approved", "decided_by": "e2e"})
ok("second decision -> 409 (no side-effects rerun)", r.status_code == 409, str(r.status_code))
t = task_by_id(tE)
ok("rejected -> back to todo", t.get("status") == "todo", t.get("status"))
ok("retry feedback attached", "headline" in (t.get("retry_feedback") or ""), str(t.get("retry_feedback"))[:60])
ok("deliverable versioned", (ws_e / "deliverable.v1.md").is_file(),
   str(list(p.name for p in ws_e.iterdir())))
# approve path on a second fixture -> done
con = sqlite3.connect(str(ROOT / "nexus.db"))
con.execute("UPDATE tasks SET status='review', dispatch_state='completed' WHERE id=?", (tE,))
con.execute("INSERT INTO approvals (id, agent_id, action_type, description, payload, status, "
            "risk_level, requested_at, user_id) VALUES ('appr-e2estub2', 'e2e', 'deliverable', "
            "'E2E judge probe re-review', ?, 'pending', 'high', 2, 'u_owner')",
            (json.dumps({"task_id": tE}),))
con.commit(); con.close()
patch("/api/approvals/appr-e2estub2", json={"status": "approved", "decided_by": "e2e"})
t = task_by_id(tE)
ok("approved -> done (shipped)", t.get("status") == "done", t.get("status"))
# retry with NO feedback: judge findings attach automatically + stale approval expires
con = sqlite3.connect(str(ROOT / "nexus.db"))
con.execute("UPDATE tasks SET status='review', dispatch_state='completed', retry_feedback=NULL "
            "WHERE id=?", (tE,))
con.execute("INSERT INTO approvals (id, agent_id, action_type, description, payload, status, "
            "risk_level, requested_at, user_id) VALUES ('appr-e2estub3', 'e2e', 'deliverable', "
            "'E2E auto-feedback probe', ?, 'pending', 'high', 3, 'u_owner')",
            (json.dumps({"task_id": tE}),))
con.commit(); con.close()
post(f"/api/tasks/{tE}/retry", json={})
t = task_by_id(tE)
ok("retry auto-attaches judge findings", "judge findings" in (t.get("retry_feedback") or "").lower(),
   str(t.get("retry_feedback"))[:80])
ap3 = requests.get(BASE + "/api/approvals", params={"status": "expired"}, timeout=10, verify=False, cookies=CK).json()["approvals"]
ok("stale approval expired on retry", any(a["id"] == "appr-e2estub3" for a in ap3),
   str([a["id"] for a in ap3][:5]))
# WIN/LESSON: numbers are required for wins; entry lands in the file
r = post(f"/api/tasks/{tE}/feedback", json={"kind": "win", "note": "clear CTA"})
ok("WIN without numbers -> 400", r.status_code == 400, str(r.status_code))
r = post(f"/api/tasks/{tE}/feedback", json={"kind": "win", "note": "clear CTA",
                                            "numbers": "E2E-PROBE 12% CTR"})
ok("WIN logged", r.status_code == 200, r.text[:120])
wins_path = os.path.expanduser("~/knowledge/feedback/WINS.md")
wins = open(wins_path).read()
ok("WIN entry in WINS.md", "E2E-PROBE 12% CTR" in wins)
# scrub the probe entry from the real business file
import re as _regex
wins2 = _regex.sub(r"### \d{4}-\d{2}-\d{2} — E2E judge probe\n(?:- .*\n)*\n*", "", wins, count=1)
open(wins_path, "w").write(wins2)
ok("WIN probe entry scrubbed", "E2E-PROBE" not in open(wins_path).read())
patch("/api/settings", json={"judge.cmd": prev_judge_cmd})

print("=== Cleanup ===")
for tid in (tA, tB, tC, tD, tE):
    dele(f"/api/tasks/{tid}")
post(f"/api/agents/{other}/retire")
dele(f"/api/agents/{other}")
dele(f"/api/agents/{lane}")
clear_quota_keys()
patch("/api/settings", json={"dispatch.enabled": prev_flag})
ok("flag restored", get("/api/settings", params={"prefix": "dispatch.enabled"})
   .json()["settings"].get("dispatch.enabled") == prev_flag)

print(f"\n{'ALL PASSED' if F == 0 else 'FAILURES'}: {P} passed, {F} failed")
sys.exit(1 if F else 0)
