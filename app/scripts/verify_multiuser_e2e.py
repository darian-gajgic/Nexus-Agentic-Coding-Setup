#!/usr/bin/env python3
"""Block 1 — multi-user ISOLATION PROBE (E2E, like the M3 client-isolation probe).

Proves, against the LIVE server + LIVE qdrant, that user B cannot see user A's
tasks / workflows / known issues / deliverables / activity / WS events /
JARVIS history / mem0 memories. Leaves the system exactly as it found it:
single-user, no owner password, probe rows and probe memories deleted.

Run:  .venv/bin/python scripts/verify_multiuser_e2e.py

Phases
  A  HTTP isolation      — two real users, two cookie jars, cross-checks on
                           every user-scoped surface + login gate + rate limit
  B  WS isolation        — task events go ONLY to the owner's socket
  C  Login UI            — Playwright: login screen renders (mobile viewport),
                           real UI sign-in as the probe user works
  D  mem0 isolation      — REAL provider code (Hermes venv) + REAL scopes file
                           + REAL qdrant: A's stamped memory is invisible in
                           B's session (read filter) — proven live vs qdrant;
                           unmapped sessions fall back to default_user (owner)
  E  Projects + memory   — the two gap fixes: a second user sees 0 projects
     views (gap fixes)     (filesystem scan is ownership-filtered, path
                           endpoints reject foreign repos) and 0 memories
                           (legacy qdrant backlog backfilled to u_owner)
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import secrets as _secrets
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import database as db  # noqa: E402

BASE = "https://127.0.0.1:8777"
HERMES_PY = os.path.expanduser("~/.hermes/hermes-agent/venv/bin/python")
SCOPES_FILE = os.path.expanduser("~/.hermes/client-scopes.json")
QDRANT = "http://localhost:6333"

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  PASS  {name}")
    else: FAIL += 1; print(f"  FAIL  {name}  {detail}")


OWNER_TEMP_PW = "probe-" + _secrets.token_urlsafe(9)
ALICE_PW = "probe-" + _secrets.token_urlsafe(9)
BOB_PW = "probe-" + _secrets.token_urlsafe(9)


def cleanup(single_user_start=True, owner_token=None):
    """Restore the PRE-PROBE state no matter what happened above: on a
    single-user machine that means back to no-login (password cleared);
    on a machine already running real multi-user (Block 1 live), real
    users, passwords and live sessions are left untouched — only probe
    artifacts (and the probe-minted owner session) are removed."""
    print("\n=== CLEANUP (restore pre-probe state) ===")
    import shutil
    # phase E probe project (real dir under ~/Projects + its ownership row)
    shutil.rmtree(os.path.expanduser("~/Projects/mu-probe-proj"), ignore_errors=True)
    db.execute("DELETE FROM project_owners WHERE path LIKE '%mu-probe%'")
    for t in db.query_all("SELECT id, workspace_path FROM tasks WHERE title LIKE 'mu-probe%'"):
        if t.get("workspace_path") and "/workspaces/" in t["workspace_path"]:
            shutil.rmtree(t["workspace_path"], ignore_errors=True)
        db.execute("DELETE FROM tasks WHERE id=?", (t["id"],))
    for w in db.query_all("SELECT id FROM workflows WHERE name LIKE 'mu-probe%'"):
        db.execute("DELETE FROM workflows WHERE id=?", (w["id"],))
    db.execute("DELETE FROM known_issues WHERE feedback LIKE 'mu-probe%'")
    probe_uids = [u["id"] for u in db.query_all(
        "SELECT id FROM users WHERE username LIKE 'probe-%'")]
    for uid in probe_uids:
        db.execute("DELETE FROM auth_sessions WHERE user_id=?", (uid,))
        db.execute("DELETE FROM users WHERE id=?", (uid,))
    if single_user_start:
        db.execute("UPDATE users SET password_hash='' WHERE id='u_owner'")
        db.execute("DELETE FROM auth_sessions")
    elif owner_token:
        import auth as _auth
        _auth.destroy_session(owner_token)
    # probe entries out of the scopes bridge file
    try:
        data = json.load(open(SCOPES_FILE))
        for k in ("sessions", "users", "updated"):
            data[k] = {s: v for s, v in (data.get(k) or {}).items()
                       if not s.startswith("mu-probe-")}
        # JARVIS sessions created for probe users
        for uid in probe_uids:
            data["users"] = {s: v for s, v in data["users"].items() if v != uid}
        json.dump(data, open(SCOPES_FILE, "w"), indent=1)
    except Exception as e:
        print("  (scopes file cleanup skipped:", str(e)[:60], ")")
    # probe users' JARVIS session ids out of jarvis_session.json
    try:
        jf = ROOT / "jarvis_session.json"
        j = json.loads(jf.read_text())
        j["sessions"] = {u: s for u, s in (j.get("sessions") or {}).items()
                         if u not in probe_uids}
        jf.write_text(json.dumps(j))
    except Exception:
        pass
    left = db.query_one("SELECT COUNT(*) n FROM users WHERE active=1")["n"]
    if single_user_start:
        print(f"  users left: {left} (expect 1) — owner password cleared, sessions dropped")
    else:
        print(f"  users left: {left} (real users) — probe rows removed, real sessions kept")


def new_client():
    return httpx.Client(base_url=BASE, verify=False, timeout=30)


def login(c, username, password):
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    return r.status_code == 200


def phase_a(single_user_start=True):
    print("\n=== A. HTTP isolation ===")
    import auth as _auth
    anon = new_client()
    owner_token = None

    if single_user_start:
        st = anon.get("/api/auth/state").json()
        ok("starts in single-user mode", st["auth_required"] is False and st["user"]["id"] == "u_owner",
           json.dumps(st)[:120])
        # owner (auto-identity) sets a password, then creates the two probe
        # users; setting the password mints the owner's session cookie (by
        # design — the auth flip must not log the acting admin out)
        r = anon.post("/api/auth/password", json={"current": "", "password": OWNER_TEMP_PW})
        ok("owner password set", r.status_code == 200, r.text[:100])
        owner = anon
    else:
        # machine already runs REAL multi-user (Block 1 live): never touch
        # the real password/sessions — mint the owner a direct session token
        st = anon.get("/api/auth/state").json()
        ok("multi-user already live (login wall up)",
           st["auth_required"] is True and st["user"] is None, json.dumps(st)[:120])
        owner = new_client()
        owner_token = _auth.create_session("u_owner", "mu-probe-owner")
        owner.cookies.set("nexus_session", owner_token)
        ok("owner session established (direct token, real password untouched)",
           (owner.get("/api/auth/state").json().get("user") or {}).get("id") == "u_owner")

    r = owner.post("/api/users", json={"username": "probe-alice", "display_name": "Probe Alice",
                                       "password": ALICE_PW, "role": "member"})
    ok("alice created", r.status_code == 200, r.text[:100])
    alice_id = r.json().get("id")
    r = owner.post("/api/users", json={"username": "probe-bob", "display_name": "Probe Bob",
                                       "password": BOB_PW, "role": "member"})
    ok("bob created", r.status_code == 200, r.text[:100])
    bob_id = r.json().get("id")

    time.sleep(2.2)  # auth_required micro-cache TTL
    if single_user_start:
        st = owner.get("/api/auth/state").json()
        ok("operator stays signed in through the flip",
           st["auth_required"] is True and (st.get("user") or {}).get("id") == "u_owner",
           json.dumps(st)[:120])
    fresh = new_client()
    st = fresh.get("/api/auth/state").json()
    ok("login now required", st["auth_required"] is True and st["user"] is None, json.dumps(st)[:120])
    r = fresh.get("/api/tasks")
    ok("anonymous API is 401", r.status_code == 401, f"{r.status_code}")
    r = fresh.get("/")
    ok("SPA shell still served (login screen host)", r.status_code == 200)

    # login throttle: 6 bad attempts lock the pair (username, ip)
    for _ in range(6):
        anon.post("/api/auth/login", json={"username": "probe-alice", "password": "wrong-pw"})
    r = anon.post("/api/auth/login", json={"username": "probe-alice", "password": ALICE_PW})
    ok("brute-force throttled (right pw refused after 6 misses)", r.status_code == 401)

    alice, bob = new_client(), new_client()
    ok("bob logs in (throttle is per username+ip)", login(bob, "probe-bob", BOB_PW))
    # alice's username is still throttled from the 6 misses above — establish
    # her session via a direct token (equivalent to a login before the misses)
    import auth as _auth
    tokenA = _auth.create_session(alice_id, "probe")
    alice.cookies.set("nexus_session", tokenA)
    ok("alice session established", alice.get("/api/auth/state").json()["user"]["id"] == alice_id)

    # per-user rows
    ta = alice.post("/api/tasks", json={"title": "mu-probe alice task"}).json()
    tb = bob.post("/api/tasks", json={"title": "mu-probe bob task"}).json()
    wa = alice.post("/api/workflows", json={"name": "mu-probe alice wf"}).json()
    ka = alice.post("/api/known-issues", json={"feedback": "mu-probe alice issue", "view": "probe"}).json()
    ok("rows created + stamped", ta.get("user_id") == alice_id and tb.get("user_id") == bob_id,
       f"{ta.get('user_id')} / {tb.get('user_id')}")

    bob_tasks = [t["id"] for t in bob.get("/api/tasks").json()]
    alice_tasks = [t["id"] for t in alice.get("/api/tasks").json()]
    ok("bob's board has no alice task", ta["id"] not in bob_tasks and tb["id"] in bob_tasks)
    ok("alice's board has no bob task", tb["id"] not in alice_tasks and ta["id"] in alice_tasks)

    ok("bob GET alice task = 404", bob.get(f"/api/tasks/{ta['id']}/transcript").status_code == 404)
    ok("bob PATCH alice task = 404", bob.patch(f"/api/tasks/{ta['id']}", json={"title": "hacked"}).status_code == 404)
    ok("bob DELETE alice task = 404", bob.delete(f"/api/tasks/{ta['id']}").status_code == 404)
    ok("bob files on alice task = 404", bob.get(f"/api/tasks/{ta['id']}/files").status_code == 404)
    ok("bob attachments on alice task hidden",
       bob.get(f"/api/tasks/{ta['id']}/attachments").json().get("attachments") == [])
    ok("bob judge on alice task = 404", bob.post(f"/api/tasks/{ta['id']}/judge").status_code == 404)
    ok("bob retry on alice task = 404", bob.post(f"/api/tasks/{ta['id']}/retry", json={}).status_code == 404)
    ok("bob review on alice task = 404", bob.get(f"/api/tasks/{ta['id']}/review").status_code == 404)

    bob_wfs = [w["id"] for w in bob.get("/api/workflows").json()["workflows"]]
    ok("bob's workflows exclude alice's", wa["id"] not in bob_wfs)
    ok("bob GET alice workflow = 404", bob.get(f"/api/workflows/{wa['id']}").status_code == 404)
    ok("bob PATCH alice workflow = 404", bob.patch(f"/api/workflows/{wa['id']}", json={"name": "x"}).status_code == 404)

    bob_kis = [i["id"] for i in bob.get("/api/known-issues").json()["issues"]]
    ok("bob's known-issues exclude alice's", ka.get("id") not in bob_kis)

    # cross-user REFERENCES are refused (would leak deliverables via
    # dependency injection / project views)
    r = bob.post("/api/tasks", json={"title": "mu-probe ref hijack", "workflow_id": wa["id"]})
    ok("bob cannot attach a task to alice's workflow", r.status_code == 404, f"{r.status_code}")
    r = bob.post("/api/tasks", json={"title": "mu-probe dep hijack", "depends_on": [ta["id"]]})
    ok("bob cannot depend on alice's task", r.status_code == 404, f"{r.status_code}")

    # deliverables: pin a workspace on alice's task (attachment upload sets
    # workspace_path), then drop a real deliverable file into it — attachments
    # alone are INPUT and rightly don't count as "produced output"
    r = alice.post(f"/api/tasks/{ta['id']}/attachments",
                   files={"file": ("mu-probe.txt", b"probe attachment", "text/plain")})
    ok("alice attachment uploads", r.status_code == 200, r.text[:80])
    ws = Path(db.query_one("SELECT workspace_path FROM tasks WHERE id=?",
                           (ta["id"],))["workspace_path"])
    (ws / "deliverable.md").write_text("mu-probe deliverable output\n")
    adel = [d["task_id"] for d in alice.get("/api/deliverables?limit=200").json()["deliverables"]]
    bdel = [d["task_id"] for d in bob.get("/api/deliverables?limit=200").json()["deliverables"]]
    ok("deliverables scoped", ta["id"] in adel and ta["id"] not in bdel,
       f"in_alice={ta['id'] in adel} in_bob={ta['id'] in bdel}")

    # activity: alice's task-created line is invisible to bob
    a_act = json.dumps(alice.get("/api/activity?limit=100").json())
    b_act = json.dumps(bob.get("/api/activity?limit=100").json())
    ok("activity scoped", ("mu-probe alice task" in a_act) and ("mu-probe alice task" not in b_act))

    # stats reflect own board only
    a_total = alice.get("/api/stats").json()["tasks"]["total"]
    b_total = bob.get("/api/stats").json()["tasks"]["total"]
    ok("stats count own tasks only", a_total != b_total or a_total <= 2,
       f"alice={a_total} bob={b_total}")

    # dispatches list scoped (empty for both, but must not 500)
    ok("dispatches endpoint scoped", bob.get(f"/api/dispatches?task_id={ta['id']}").json()["dispatches"] == [])

    # JARVIS: separate sessions per user; history is owner-only
    sa = alice.post("/api/jarvis/session").json().get("session_id")
    sb = bob.post("/api/jarvis/session").json().get("session_id")
    ok("per-user JARVIS sessions", bool(sa) and bool(sb) and sa != sb, f"{sa} vs {sb}")
    ok("bob cannot read alice's JARVIS history",
       bob.get(f"/api/jarvis/messages/{sa}").status_code == 404)
    ok("alice reads own JARVIS history",
       alice.get(f"/api/jarvis/messages/{sa}").status_code == 200)
    ok("member cannot browse all Hermes sessions",
       bob.get("/api/jarvis/sessions").json().get("sessions") == [])
    try:
        scopes = json.load(open(SCOPES_FILE))
        ok("JARVIS sessions user-scope-published",
           scopes.get("users", {}).get(sa) == alice_id and scopes.get("users", {}).get(sb) == bob_id)
    except Exception as e:
        ok("JARVIS sessions user-scope-published", False, str(e)[:80])

    # admin boundary
    ok("member cannot list users", bob.get("/api/users").status_code == 403)
    ok("member cannot create users", bob.post("/api/users", json={
        "username": "probe-eve", "display_name": "e", "password": "12345678"}).status_code == 403)
    ok("member cannot write settings", bob.patch("/api/settings", json={
        "dispatch.daily_cap": "1"}).status_code == 403)

    return alice_id, bob_id, alice, bob, ta, owner, owner_token


async def phase_b_ws(alice, bob, alice_id):
    print("\n=== B. WebSocket isolation ===")
    import ssl
    import websockets
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    ck_a = f"nexus_session={alice.cookies.get('nexus_session')}"
    ck_b = f"nexus_session={bob.cookies.get('nexus_session')}"
    uri = "wss://127.0.0.1:8777/ws"

    def hdr_kw(cookie):
        # websockets >=12 renamed extra_headers -> additional_headers
        import inspect
        params = inspect.signature(websockets.connect).parameters
        key = "additional_headers" if "additional_headers" in params else "extra_headers"
        return {key: {"Cookie": cookie}}

    try:
        wsa = await websockets.connect(uri, ssl=ssl_ctx, **hdr_kw(ck_a))
        wsb = await websockets.connect(uri, ssl=ssl_ctx, **hdr_kw(ck_b))
    except Exception as e:
        ok("ws connects with cookies", False, str(e)[:100])
        return
    ok("ws connects with cookies", True)

    # no cookie while auth is on -> rejected
    try:
        wsx = await websockets.connect(uri, ssl=ssl_ctx)
        # server closes with 4401; a recv should raise quickly
        await asyncio.wait_for(wsx.recv(), timeout=3)
        ok("anonymous ws rejected", False, "recv delivered data")
    except Exception:
        ok("anonymous ws rejected", True)

    t = alice.post("/api/tasks", json={"title": "mu-probe ws event task"}).json()

    got_a, got_b = [], []
    async def drain(sock, sink):
        try:
            while True:
                sink.append(json.loads(await asyncio.wait_for(sock.recv(), timeout=3)))
        except Exception:
            pass
    await asyncio.gather(drain(wsa, got_a), drain(wsb, got_b))
    a_hit = any(m.get("type") == "task_created" and "ws event task" in json.dumps(m) for m in got_a)
    b_hit = any("ws event task" in json.dumps(m) for m in got_b)
    ok("owner's socket got the task event", a_hit, f"{len(got_a)} msgs")
    ok("other user's socket did NOT", not b_hit, f"{len(got_b)} msgs")
    await wsa.close(); await wsb.close()
    alice.delete(f"/api/tasks/{t['id']}")


async def phase_c_login_ui():
    print("\n=== C. Login UI (Playwright, mobile viewport) ===")
    from playwright.async_api import async_playwright
    shots = os.path.expanduser("~/.hermes/cache/screenshots/nexus-mobile")
    os.makedirs(shots, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page(ignore_https_errors=True,
                                viewport={"width": 390, "height": 844})
        await page.goto(BASE, wait_until="networkidle")
        try:
            await page.wait_for_selector("#loginScreen", timeout=6000)
            ok("login screen renders", True)
        except Exception:
            ok("login screen renders", False)
            await b.close(); return
        ok("app shell hidden behind login",
           not await page.locator("#app").is_visible())
        await page.screenshot(path=f"{shots}/login.png")
        await page.fill("#loginUser", "probe-bob")
        await page.fill("#loginPass", BOB_PW)
        await page.click('#loginForm button[type="submit"]')
        try:
            await page.wait_for_selector("#userChip", timeout=10000)
            ok("UI sign-in lands in the app with user chip", True)
        except Exception:
            ok("UI sign-in lands in the app with user chip", False)
        await page.screenshot(path=f"{shots}/after-login.png")
        await b.close()


def phase_d_mem0(alice_id, bob_id):
    print("\n=== D. mem0 isolation (REAL provider vs REAL qdrant) ===")
    sid_a, sid_b = "mu-probe-session-A", "mu-probe-session-B"
    # publish the user scopes exactly like dispatch does
    import hermes_dispatch as hd
    hd.publish_session_scope(sid_a, user=alice_id)
    hd.publish_session_scope(sid_b, user=bob_id)
    scopes = json.load(open(SCOPES_FILE))
    ok("scopes published", scopes["users"].get(sid_a) == alice_id
       and scopes["users"].get(sid_b) == bob_id)

    fact = f"mu-probe-fact-{_secrets.token_hex(4)}: alice's favourite plant is a monstera"
    driver = f'''
import json, sys
sys.path.insert(0, "{os.path.expanduser('~/.hermes/hermes-agent')}")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "mem0_client_probe", "{os.path.expanduser('~/.hermes/plugins/mem0-client/__init__.py')}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

out = {{}}
pa = mod.ClientScopedMem0Provider(); pa.initialize("{sid_a}")
md = pa._write_metadata()
out["write_md_user"] = md.get("user")
res = pa._backend.add([{{"role": "user", "content": {fact!r}}}],
                      user_id=pa._user_id, agent_id=pa._agent_id,
                      infer=False, metadata=md)
out["add"] = True

pb = mod.ClientScopedMem0Provider(); pb.initialize("{sid_b}")
hits_b = pb._backend.search("favourite plant monstera",
                            filters={{"user_id": pb._user_id}}, top_k=10, rerank=False)
out["b_sees"] = ["mu-probe-fact" in json.dumps(h) for h in hits_b].count(True)

hits_a = pa._backend.search("favourite plant monstera",
                            filters={{"user_id": pa._user_id}}, top_k=10, rerank=False)
out["a_sees"] = ["mu-probe-fact" in json.dumps(h) for h in hits_a].count(True)

# UNMAPPED session (local CLI shape): resolves to the scopes-file
# default_user (the owner after the backfill migration) — so it must
# NOT see alice's user-tagged probe fact either
pc = mod.ClientScopedMem0Provider(); pc.initialize("mu-probe-unmapped")
out["unmapped_user"] = pc._user_now()
hits_c = pc._backend.search("favourite plant monstera",
                            filters={{"user_id": pc._user_id}}, top_k=10, rerank=False)
out["c_sees"] = ["mu-probe-fact" in json.dumps(h) for h in hits_c].count(True)

print("DRIVER_RESULT " + json.dumps(out))
'''
    r = subprocess.run([HERMES_PY, "-c", driver], capture_output=True, text=True, timeout=180)
    line = next((l for l in r.stdout.splitlines() if l.startswith("DRIVER_RESULT ")), None)
    if not line:
        ok("provider driver ran", False, (r.stderr or r.stdout)[-300:])
        return
    out = json.loads(line[len("DRIVER_RESULT "):])
    ok("provider driver ran", True)
    ok("write path stamps metadata.user", out.get("write_md_user") == alice_id,
       str(out.get("write_md_user")))
    ok("memory stored via real backend", out.get("add") is True)
    ok("user A finds their memory", out.get("a_sees", 0) >= 1, f"a_sees={out.get('a_sees')}")
    ok("user B's session filters it out (0 rows)", out.get("b_sees") == 0,
       f"b_sees={out.get('b_sees')}")
    ok("unmapped session resolves to the scopes-file default_user",
       out.get("unmapped_user") == scopes.get("default_user"),
       f"{out.get('unmapped_user')} vs {scopes.get('default_user')}")
    ok("unmapped (CLI) session cannot see A's tagged memory", out.get("c_sees") == 0,
       f"c_sees={out.get('c_sees')}")

    # cleanup + independent verification straight against qdrant:
    # find probe points by payload text, delete by id, verify gone
    # (delete-by-filter on ids — the M3 purge pattern)
    try:
        import urllib.request

        def _scroll(needle):
            req = urllib.request.Request(
                f"{QDRANT}/collections/mem0/points/scroll",
                data=json.dumps({"limit": 500, "with_payload": True}).encode(),
                headers={"Content-Type": "application/json"})
            pts = json.loads(urllib.request.urlopen(req, timeout=10).read())["result"]["points"]
            return [p for p in pts if needle in json.dumps(p.get("payload") or {})]

        this_run = _scroll(fact.split(":")[0])  # this run's unique token
        ok("probe row landed in qdrant (user-tagged)",
           len(this_run) >= 1 and all(
               (p.get("payload") or {}).get("user") == alice_id for p in this_run),
           f"{len(this_run)} rows")
        stale = _scroll("mu-probe-fact")  # anything probe-shaped, any run
        if stale:
            req = urllib.request.Request(
                f"{QDRANT}/collections/mem0/points/delete",
                data=json.dumps({"points": [p["id"] for p in stale]}).encode(),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
        time.sleep(1)
        ok("qdrant has no probe leftovers", len(_scroll("mu-probe-fact")) == 0)
    except Exception as e:
        ok("qdrant has no probe leftovers", False, str(e)[:80])


def phase_e_projects_memory(owner, alice, bob):
    """The two Block-1 gap fixes, proven live: (1) the Projects view / repo
    endpoints are ownership-scoped, (2) the legacy mem0 backlog is
    owner-tagged so a second user's memory views start empty."""
    print("\n=== E. Projects + memory views (gap fixes) ===")

    own = owner.get("/api/projects").json()["projects"]
    ok("owner sees the machine's projects", len(own) > 0, f"{len(own)} projects")
    bobp = bob.get("/api/projects").json()["projects"]
    ok("second user sees 0 projects", bobp == [], f"{len(bobp)} leaked")

    repo = next((p["path"] for p in own if p.get("is_repo")), None)
    ok("owner has a repo to probe with", bool(repo))
    if repo:
        r = bob.post("/api/projects/publish", json={"path": repo, "name": "mu-probe-hijack"})
        ok("foreign repo publish rejected", r.status_code == 400, f"{r.status_code}")
        r = bob.post("/api/projects/push", json={"path": repo})
        ok("foreign repo push rejected", r.status_code == 400, f"{r.status_code}")
        r = bob.post("/api/projects/tag", json={"path": repo, "tag": "v0.0", "message": "x"})
        ok("foreign repo tag rejected", r.status_code == 400, f"{r.status_code}")
        r = bob.get("/api/projects/history", params={"path": repo})
        ok("foreign repo history rejected", r.status_code == 400, f"{r.status_code}")
        r = bob.post("/api/tasks", json={"title": "mu-probe repo hijack", "repo_path": repo})
        ok("task create with a foreign repo rejected", r.status_code == 400, f"{r.status_code}")
        r = bob.post("/api/workflows", json={"name": "mu-probe wf hijack", "project_path": repo})
        ok("workflow create with a foreign project rejected", r.status_code == 400, f"{r.status_code}")

    # a second user's OWN project: created, visible to them alone
    r = alice.post("/api/projects/create-client", json={"name": "mu-probe-proj"})
    ok("second user creates their own project", r.status_code == 200 and r.json().get("ok"),
       r.text[:100])
    apaths = [p["path"] for p in alice.get("/api/projects").json()["projects"]]
    aproj = next((p for p in apaths if p.endswith("/mu-probe-proj")), None)
    ok("creator sees their new project", bool(aproj), f"{len(apaths)} visible")
    ok("other user does NOT see it", not any(
        "mu-probe-proj" in p["path"] for p in bob.get("/api/projects").json()["projects"]))
    ok("owner does NOT see it either", not any(
        "mu-probe-proj" in p["path"] for p in owner.get("/api/projects").json()["projects"]))
    if aproj:
        r = alice.get("/api/projects/history", params={"path": aproj})
        ok("creator can use their own project", r.status_code == 200, f"{r.status_code}")

    # memory views: legacy qdrant backlog is owner-tagged (one-time backfill),
    # so the second user starts EMPTY. Untagged rows are shared/global BY
    # DESIGN (shared-context, curator lessons) — if the ==0 check ever fails
    # right after intentionally adding a global memory, that is why.
    import urllib.request
    req = urllib.request.Request(
        f"{QDRANT}/collections/mem0/points/count",
        data=json.dumps({"exact": True,
                         "filter": {"must": [{"is_empty": {"key": "user"}}]}}).encode(),
        headers={"Content-Type": "application/json"})
    untagged = json.loads(urllib.request.urlopen(req, timeout=10).read())["result"]["count"]
    ok("legacy mem0 backlog fully owner-tagged (0 untagged in qdrant)", untagged == 0,
       f"{untagged} untagged")
    bmem = bob.get("/api/memory").json()
    ok("second user's memory list is empty", bmem.get("count") == 0,
       f"count={bmem.get('count')}")
    ok("second user sees exactly the global (untagged) rows",
       bmem.get("count") == untagged, f"{bmem.get('count')} vs {untagged} untagged")
    omem = owner.get("/api/memory").json()
    ok("owner still sees the legacy memories", (omem.get("count") or 0) >= 300,
       f"count={omem.get('count')}")
    b3d = bob.get("/api/memory3d?force=1").json()
    ok("second user's galaxy is empty", not b3d.get("nodes"),
       f"{len(b3d.get('nodes') or [])} nodes")


def main():
    print("=== Block 1 multi-user isolation probe ===")
    print(f"(owner temp password, in case of a crash: {OWNER_TEMP_PW} — "
          "or run scripts/auth_reset.py)")
    n = db.query_one("SELECT COUNT(*) n FROM users WHERE active=1")["n"]
    if n < 1 or db.query_all("SELECT 1 FROM users WHERE username LIKE 'probe-%'"):
        print(f"ABORT: unclean start state ({n} active users, probe leftovers?). "
              "Run scripts/auth_reset.py or remove probe-* users first.")
        sys.exit(2)
    single = n == 1
    if not single:
        print(f"({n} active users — real multi-user is live; probe preserves "
              "real users, passwords and sessions)")
    single_ctx = {"single": single, "owner_token": None}
    try:
        alice_id, bob_id, alice, bob, ta, owner, owner_token = phase_a(single)
        single_ctx["owner_token"] = owner_token
        asyncio.run(phase_b_ws(alice, bob, alice_id))
        asyncio.run(phase_c_login_ui())
        phase_d_mem0(alice_id, bob_id)
        phase_e_projects_memory(owner, alice, bob)
    finally:
        cleanup(single, single_ctx["owner_token"])
    time.sleep(2.2)  # let the auth micro-cache observe the restored state
    st = new_client().get("/api/auth/state").json()
    if single:
        ok("system restored to single-user (no login)", st["auth_required"] is False
           and (st.get("user") or {}).get("id") == "u_owner", json.dumps(st)[:120])
    else:
        ok("system left in real multi-user mode (login wall up)",
           st["auth_required"] is True and st["user"] is None, json.dumps(st)[:120])
    print(f"\n=== MULTI-USER ISOLATION RESULT: {PASS} passed, {FAIL} failed ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
