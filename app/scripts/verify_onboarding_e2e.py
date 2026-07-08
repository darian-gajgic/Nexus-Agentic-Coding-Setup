#!/usr/bin/env python
"""Onboarding runtime gate (docs/SPEC-ONBOARDING.md) — schema, per-user
answers, apply/render/git, framing path resolution.

Runs against the LIVE server with settings `onboarding.root` redirected to a
scratch knowledge repo (restored afterwards). The owner's REAL saved answers
are backed up and restored — the gate leaves no trace.

Run: .venv/bin/python scripts/verify_onboarding_e2e.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import auth  # noqa: E402
import database as db  # noqa: E402

BASE = "https://127.0.0.1:8777"
PASS = FAIL = 0
CLEANUP = []


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def client_for(user_id):
    token = auth.create_session(user_id, "onb-gate")
    CLEANUP.append(lambda t=token: auth.destroy_session(t))
    c = httpx.Client(base_url=BASE, verify=False, timeout=30)
    c.cookies.set("nexus_session", token)
    return c


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
    return r.returncode, (r.stdout + r.stderr).strip()


def main():
    # ── scratch knowledge repo + settings redirect ──
    tmp = Path(tempfile.mkdtemp(prefix="nexus-onb-gate-"))
    CLEANUP.append(lambda: shutil.rmtree(tmp, ignore_errors=True))
    shutil.copytree(os.path.expanduser("~/knowledge/templates"), tmp / "templates")
    git(tmp, "init", "-b", "main")
    git(tmp, "add", "-A")
    git(tmp, "-c", "user.name=g", "-c", "user.email=g@local", "commit", "-m", "init")
    prev_root = db.get_setting("onboarding.root", None)
    db.set_setting("onboarding.root", str(tmp))
    CLEANUP.append(lambda: (db.set_setting("onboarding.root", prev_root) if prev_root
                            else db.execute("DELETE FROM settings WHERE key='onboarding.root'")))

    # ── back up + clear the owner's REAL answers (restored at exit) ──
    saved_rows = db.query_all("SELECT * FROM onboarding_answers WHERE user_id='u_owner'")
    saved_state = db.query_all("SELECT * FROM onboarding_state WHERE user_id='u_owner'")

    def _restore_owner():
        db.execute("DELETE FROM onboarding_answers WHERE user_id='u_owner'")
        db.execute("DELETE FROM onboarding_state WHERE user_id='u_owner'")
        for r in saved_rows:
            db.execute("INSERT INTO onboarding_answers (user_id, slot_id, answer, na, updated_at) "
                       "VALUES (?,?,?,?,?)", (r["user_id"], r["slot_id"], r["answer"], r["na"], r["updated_at"]))
        for r in saved_state:
            db.execute("INSERT INTO onboarding_state (user_id, applied_at, target_dir) "
                       "VALUES (?,?,?)", (r["user_id"], r["applied_at"], r["target_dir"]))
    CLEANUP.append(_restore_owner)
    db.execute("DELETE FROM onboarding_answers WHERE user_id='u_owner'")
    db.execute("DELETE FROM onboarding_state WHERE user_id='u_owner'")

    owner = client_for("u_owner")
    uid2 = f"u_onbprobe{uuid.uuid4().hex[:6]}"
    db.execute("INSERT INTO users (id, username, display_name, password_hash, role, active, "
               "created_at) VALUES (?,?,?,?, 'member', 1, ?)",
               (uid2, f"onbprobe-{uid2[-4:]}", "onb probe", "!", time.time()))
    CLEANUP.append(lambda: (db.execute("DELETE FROM auth_sessions WHERE user_id=?", (uid2,)),
                            db.execute("DELETE FROM onboarding_answers WHERE user_id=?", (uid2,)),
                            db.execute("DELETE FROM onboarding_state WHERE user_id=?", (uid2,)),
                            db.execute("DELETE FROM users WHERE id=?", (uid2,))))
    member = client_for(uid2)

    # ═══ schema ═══
    print("═══ schema + explanations ═══")
    d = owner.get("/api/onboarding").json()
    ok("37 slots in 11 sections", d["total"] == 37 and len(d["sections"]) == 11,
       f"{d['total']}/{len(d['sections'])}")
    ok("every section carries an impact explanation",
       all((s.get("explain") or "").strip() and (s.get("file_intro") or "").strip()
           for s in d["sections"]))
    ok("owner targets the canonical root", d["is_owner"] and d["target_dir"] == str(tmp),
       d["target_dir"])
    dm = member.get("/api/onboarding").json()
    ok("member targets a personal overlay",
       not dm["is_owner"] and dm["target_dir"] == str(tmp / "users" / uid2), dm["target_dir"])

    # ═══ answers: save / resume / un-answer / isolation ═══
    print("═══ answers per user ═══")
    r = owner.post("/api/onboarding/answers", json={"answers": {
        "context:00": {"text": "A: dev + music, B: content + shop ops", "na": False},
        "context:01": {"text": "10h/week each", "na": False},
        "style:00": {"text": "", "na": True},
    }})
    ok("owner saves 3 answers", r.status_code == 200 and r.json()["answered"] == 3, r.text[:120])
    ok("unknown slot rejected", owner.post("/api/onboarding/answers",
       json={"answers": {"bogus:99": {"text": "x"}}}).status_code == 400)
    d = owner.get("/api/onboarding").json()
    ok("resume shows saved text",
       d["answers"]["context:00"]["text"].startswith("A: dev") and d["answers"]["style:00"]["na"])
    ok("member sees NONE of the owner's answers",
       member.get("/api/onboarding").json()["answered"] == 0)
    member.post("/api/onboarding/answers", json={"answers": {
        "context:00": {"text": "member-only venture", "na": False}}})
    ok("owner sees none of the member's answers",
       owner.get("/api/onboarding").json()["answers"]["context:00"]["text"].startswith("A: dev"))
    r = owner.post("/api/onboarding/answers", json={"answers": {
        "context:01": {"text": "", "na": False}}})
    ok("empty text un-answers the slot", r.json()["removed"] == 1
       and owner.get("/api/onboarding").json()["answered"] == 2)

    # ═══ status endpoint (per-user, historical shape) ═══
    print("═══ status ═══")
    s = owner.get("/api/onboarding-status").json()
    ok("status keeps the historical shape", all(k in s for k in ("files", "total", "done", "cta")))
    ok("owner status = template minus answers (no file yet)", s["total"] == 35, s["total"])
    ok("member status independent", member.get("/api/onboarding-status").json()["total"] == 36)

    # ═══ apply: render + git ═══
    print("═══ apply ═══")
    (tmp / "scratchnote.md").write_text("dirty tree\n")  # apply must snapshot this first
    r = owner.post("/api/onboarding/apply")
    a = r.json()
    ok("owner apply writes canonical files", r.status_code == 200
       and (tmp / "BUSINESS-CONTEXT.md").is_file() and (tmp / "STYLE-VOICE.md").is_file(), r.text[:150])
    ok("replaced/remaining accounted", a["replaced"] == 2 and a["remaining"] == 35, str(a)[:120])
    text = (tmp / "BUSINESS-CONTEXT.md").read_text()
    ok("answer rendered verbatim", "A: dev + music, B: content + shop ops" in text)
    ok("n/a rendered as marked", "marked not applicable" in (tmp / "STYLE-VOICE.md").read_text())
    ok("doc-mention of the slot syntax preserved", "`{{FILL: ...}}`" in text)
    code, log = git(tmp, "log", "--oneline", "-5")
    ok("git: onboarding commit present", "onboarding(" in log, log)
    ok("git: dirty tree snapshotted FIRST", "pre-onboarding snapshot" in log, log)
    ok("owner status now counts the FILE (file truth)",
       owner.get("/api/onboarding-status").json()["total"] == 35)

    r = member.post("/api/onboarding/apply")
    ok("member apply writes the overlay", r.status_code == 200
       and (tmp / "users" / uid2 / "BUSINESS-CONTEXT.md").is_file(), r.text[:150])
    ok("member's answer only in THEIR file",
       "member-only venture" in (tmp / "users" / uid2 / "BUSINESS-CONTEXT.md").read_text()
       and "member-only venture" not in (tmp / "BUSINESS-CONTEXT.md").read_text())

    # ═══ framing resolution ═══
    print("═══ framing paths ═══")
    import hermes_dispatch as hd
    kp_owner = hd._knowledge_paths({"user_id": "u_owner"})
    kp_member = hd._knowledge_paths({"user_id": uid2})
    kp_ghost = hd._knowledge_paths({"user_id": "u_never_onboarded"})
    ok("owner task reads canonical", kp_owner["context"] == str(tmp / "BUSINESS-CONTEXT.md"))
    ok("member task reads THEIR overlay",
       kp_member["context"] == str(tmp / "users" / uid2 / "BUSINESS-CONTEXT.md"), kp_member["context"])
    ok("user without overlay falls back to canonical",
       kp_ghost["context"] == str(tmp / "BUSINESS-CONTEXT.md"))
    framing = hd.build_framing({"id": "t", "title": "probe", "domain": "marketing",
                                "user_id": uid2}, Path("/tmp"))
    ok("member framing names the overlay path", str(tmp / "users" / uid2) in framing)

    print(f"\n{'='*46}\n  ONBOARDING E2E: {PASS} passed, {FAIL} failed\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        rc = main()
    finally:
        for fn in reversed(CLEANUP):
            try:
                fn()
            except Exception as e:
                print(f"  (cleanup: {e})")
    sys.exit(rc)
