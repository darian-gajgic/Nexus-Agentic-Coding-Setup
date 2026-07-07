#!/usr/bin/env python3
"""Runtime integration test for Agentic OS capabilities (SPEC-AGENTIC.md verification).

v2: self-sufficient — provisions its own agents and task (the seeded demo data
is gone since the real-agents migration), and cleans up after itself.
"""
import json, time, sys, requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://127.0.0.1:8777"
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

# --- setup: two lanes (auto_claim OFF so they never grab our test task) + a task ---
spawned = []
agents = [a for a in get("/api/agents").json() if a.get("status") != "retired"]
while len(agents) < 2:
    a = post("/api/agents", json={"name": f"E2E-Agentic-{len(spawned)+1}",
                                  "auto_claim": False}).json()
    spawned.append(a["id"]); agents.append(a)
A, B = agents[0]["id"], agents[1]["id"]
task = post("/api/tasks", json={"title": "agentic e2e probe", "status": "todo"}).json()
tid = task["id"]

print("=== 1. Atomic task claiming ===")
ok("has a claimable task", tid is not None)
r1 = post(f"/api/tasks/{tid}/claim", json={"agent_id": A}).json()
ok("claim by A succeeds", r1.get("ok") and r1["task"]["claimed_by"] == A)
r2 = post(f"/api/tasks/{tid}/claim", json={"agent_id": B})
ok("claim by B -> 409", r2.status_code == 409, str(r2.status_code))
ok("409 names owner", r2.json().get("owner") == A)
r3 = post(f"/api/tasks/{tid}/release", json={"agent_id": A})
ok("release by A ok", r3.status_code == 200)
ok("task back to todo", r3.json()["task"]["status"] == "todo")

print("=== 2. Plan-Execute-Verify ===")
r = post("/api/verify", json={"command":"python3 -c \"print(42)\"","kind":"static"}).json()
ok("verify run executes", r.get("passed") is True)
ok("run row persisted", r.get("run",{}).get("passed")==1)
r = post("/api/verify", json={"command":"python3 -c \"raise SystemExit(1)\"","kind":"runtime","task_id":tid}).json()
ok("verify failing captured", r.get("passed") is False)
t = next(x for x in get("/api/tasks").json() if x["id"]==tid)
ok("task verify_status=failing", t.get("verify_status")=="failing", t.get("verify_status"))
runs = get("/api/verify/runs").json()["runs"]
ok("verify runs listed", len(runs)>=2)

print("=== 3. Approval gates ===")
r = post("/api/approvals", json={"agent_id":A,"action_type":"deploy","description":"deploy v2 to prod","risk_level":"high"}).json()
aid = r["id"]
ok("approval created pending", r.get("status")=="pending")
pend = get("/api/approvals", params={"status":"pending"}).json()["approvals"]
ok("pending list includes it", any(a["id"]==aid for a in pend))
r = patch(f"/api/approvals/{aid}", json={"status":"approved","decided_by":"operator"}).json()
ok("approval approved", r.get("status")=="approved")
pend = get("/api/approvals", params={"status":"pending"}).json()["approvals"]
ok("pending count decremented", not any(a["id"]==aid for a in pend))

print("=== 4. Watchdog status ===")
r = get("/api/watchdog/status").json()
ok("watchdog config returned", "config" in r and "interval_s" in r["config"])
ok("recent_actions is a list", isinstance(r.get("recent_actions"), list))

print("=== 5. Agent memory ===")
r = post(f"/api/agents/{A}/memory", json={"scope":"lts","kind":"summary","content":"OAuth2 flow is nearly done"}).json()
mid = r["id"]
ok("memory added", mid and r.get("content"))
mem = get(f"/api/agents/{A}/memory").json()["memory"]
ok("memory listed", any(m["id"]==mid for m in mem))
ctx = get(f"/api/agents/{A}/memory/context").json()
ok("context blob has lts_summary", "lts_summary" in ctx and "OAuth2" in ctx["lts_summary"])
dele(f"/api/agents/{A}/memory/{mid}")
ok("memory deleted", mid not in [m["id"] for m in get(f"/api/agents/{A}/memory").json()["memory"]])

print("=== 6. Cron scheduler ===")
r = post("/api/scheduler", json={"name":"test-tick","cron_expr":"*/1 * * * *","action":"health check"}).json()
jid = r["id"]
ok("job created", jid and r.get("next_run") is not None)
jobs = get("/api/scheduler").json()["jobs"]
ok("job listed", any(j["id"]==jid for j in jobs))
r = patch(f"/api/scheduler/{jid}", json={"enabled":False}).json()
ok("job disabled", r.get("enabled")==0)
dele(f"/api/scheduler/{jid}")
ok("job deleted", jid not in [j["id"] for j in get("/api/scheduler").json()["jobs"]])

print("=== 7. Cost guardrails ===")
r = get(f"/api/agents/{A}/cost").json()
ok("cost endpoint returns tokens", "tokens_in" in r and "projected_usd" in r)
ok("cost has projection >= 0", r["projected_usd"]>=0)

print("=== 8. Inter-agent messaging ===")
r = post(f"/api/agents/{B}/message", json={"from_agent":A,"content":"please handle the ETL"}).json()
msg_id = r["id"]
ok("message sent", msg_id and r.get("to_agent")==B)
msgs = get(f"/api/agents/{B}/messages").json()["messages"]
ok("message listed for B", any(m["id"]==msg_id for m in msgs))

print("=== 9. Worktree endpoint (no-repo path) ===")
r = post(f"/api/agents/{A}/worktree", json={"repo_path":"/tmp"})
ok("worktree rejects non-repo with 400", r.status_code==400, str(r.status_code))

# --- cleanup ---
dele(f"/api/tasks/{tid}")
for aid_ in spawned:
    post(f"/api/agents/{aid_}/retire")
    dele(f"/api/agents/{aid_}")

print(f"\n=== RESULT: {P} passed, {F} failed ===")
sys.exit(1 if F else 0)
