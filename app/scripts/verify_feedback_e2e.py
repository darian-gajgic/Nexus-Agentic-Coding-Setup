#!/usr/bin/env python
"""WIN/LESSON feedback-ledger runtime gate — the redesigned 🏆/📓 flow.

Covers: validation hard rules (win needs numbers, lesson needs a correction),
onboarding.root honored by the WRITER (split-brain fix), template bootstrap on
a missing ledger, newest-first insert order, promote-to-examples flow,
GET /api/feedback browser payload, the tolerant entry parser, the framing
excerpt (dispatch_block caps + kill switch) and its build_framing hook,
concurrent-write integrity, and the draft endpoint's deterministic 400.

Runs against the LIVE server with settings `onboarding.root` redirected to a
scratch knowledge root (restored afterwards) — the real ~/knowledge is never
touched. Run: .venv/bin/python scripts/verify_feedback_e2e.py
"""
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import auth  # noqa: E402
import database as db  # noqa: E402
import feedback_log as fbl  # noqa: E402
import hermes_dispatch as hd  # noqa: E402

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
    token = auth.create_session(user_id, "fb-gate")
    CLEANUP.append(lambda t=token: auth.destroy_session(t))
    c = httpx.Client(base_url=BASE, verify=False, timeout=60)
    c.cookies.set("nexus_session", token)
    return c


def main():
    # ── scratch knowledge root + settings redirect (restored) ──
    tmp = Path(tempfile.mkdtemp(prefix="nexus-fb-gate-"))
    CLEANUP.append(lambda: shutil.rmtree(tmp, ignore_errors=True))
    (tmp / "domains" / "e2edom").mkdir(parents=True)
    (tmp / "domains" / "e2edom" / "RUBRIC.md").write_text("# RUBRIC\n### 1. Gate one\n")
    for key in ("onboarding.root", "feedback.framing_enabled",
                "feedback.framing_max_entries", "feedback.framing_max_chars"):
        prev = db.get_setting(key, None)
        CLEANUP.append(lambda k=key, p=prev: (
            db.set_setting(k, p) if p is not None
            else db.execute("DELETE FROM settings WHERE key=?", (k,))))
    db.set_setting("onboarding.root", str(tmp))

    owner = client_for("u_owner")
    r = owner.get("/api/health")
    if r.status_code != 200:
        print(f"server not healthy ({r.status_code}) — start nexus first")
        sys.exit(1)

    # ── probe tasks: one with a domain+deliverable, one bare ──
    t1 = owner.post("/api/tasks", json={"title": "E2E feedback probe", "domain": "e2edom",
                                        "description": "feedback gate probe"}).json()
    t2 = owner.post("/api/tasks", json={"title": "E2E domainless probe"}).json()
    CLEANUP.append(lambda: [db.execute("DELETE FROM tasks WHERE id=?", (t["id"],))
                            for t in (t1, t2)])
    ws = tmp / "ws-probe"
    ws.mkdir()
    (ws / "deliverable.md").write_text("# Probe deliverable\n\nGATE-DELIV-CONTENT body.\n")
    for t in (t1, t2):
        db.execute("UPDATE tasks SET workspace_path=?, result_summary=? WHERE id=?",
                   (str(ws), "probe summary", t["id"]))

    print("═══ validation hard rules ═══")
    r = owner.post(f"/api/tasks/{t1['id']}/feedback", json={"kind": "win", "note": "x"})
    ok("WIN without numbers -> 400", r.status_code == 400, r.text[:100])
    r = owner.post(f"/api/tasks/{t1['id']}/feedback",
                   json={"kind": "lesson", "note": "expected x got y"})
    ok("LESSON without correction -> 400",
       r.status_code == 400 and "CORRECTION" in r.text, r.text[:120])
    r = owner.post(f"/api/tasks/{t1['id']}/feedback", json={"kind": "nope", "note": "x"})
    ok("bad kind -> 400", r.status_code == 400, r.text[:80])

    print("═══ writer: root redirect + bootstrap + ordering ═══")
    real_wins = os.path.expanduser("~/knowledge/feedback/WINS.md")
    real_before = open(real_wins).read() if os.path.isfile(real_wins) else ""
    r = owner.post(f"/api/tasks/{t1['id']}/feedback",
                   json={"kind": "win", "headline": "First probe win",
                         "note": "clear CTA\nstrong hook", "numbers": "GATE-9.9% CTR"})
    ok("WIN logged (200)", r.status_code == 200, r.text[:120])
    wins_path = tmp / "feedback" / "WINS.md"
    ok("ledger created at the REDIRECTED root", wins_path.is_file(), str(wins_path))
    body = wins_path.read_text() if wins_path.is_file() else ""
    ok("bootstrapped from the repo template",
       body.startswith("# WINS") and fbl.MARKER in body, body[:60])
    ok("entry present with one-lined note",
       "GATE-9.9% CTR" in body and "clear CTA; strong hook" in body)
    real_after = open(real_wins).read() if os.path.isfile(real_wins) else ""
    ok("real ~/knowledge untouched", "GATE-9.9% CTR" not in real_after
       and real_after == real_before)
    r = owner.post(f"/api/tasks/{t1['id']}/feedback",
                   json={"kind": "win", "headline": "Second probe win",
                         "note": "n2", "numbers": "GATE-2 sales"})
    body = wins_path.read_text()
    ok("newest-first insert", r.status_code == 200
       and 0 < body.find("Second probe win") < body.find("First probe win"))

    print("═══ LESSON entry ═══")
    r = owner.post(f"/api/tasks/{t1['id']}/feedback",
                   json={"kind": "lesson", "headline": "Probe lesson",
                         "note": "expected ad, got md file", "root_cause": "wrong template",
                         "correction": "add output-format line to PLAYBOOK.md intake section"})
    lessons = (tmp / "feedback" / "LESSONS.md").read_text()
    ok("LESSON logged with correction verbatim", r.status_code == 200
       and "- Correction: add output-format line to PLAYBOOK.md intake section" in lessons)
    ok("applied-where defaults to the task",
       f"- Applied where: Nexus task {t1['id']}" in lessons)

    print("═══ promote flow ═══")
    r = owner.post(f"/api/tasks/{t1['id']}/feedback",
                   json={"kind": "win", "headline": "Promoted probe win",
                         "note": "worked", "numbers": "GATE-3 signups", "promote": True})
    d = r.json() if r.status_code == 200 else {}
    dest = d.get("promoted_to") or ""
    ok("promote -> examples/ file", r.status_code == 200 and dest
       and dest.startswith(str(tmp / "domains" / "e2edom" / "examples"))
       and os.path.isfile(dest), r.text[:150])
    if dest and os.path.isfile(dest):
        pv = open(dest).read()
        ok("promoted file = provenance + deliverable",
           pv.startswith("<!-- promoted from Nexus task") and "GATE-DELIV-CONTENT" in pv)
    else:
        ok("promoted file = provenance + deliverable", False, "no file")
    ok("ledger marks the promotion",
       "Promote to examples/? yes (promoted" in wins_path.read_text())
    r = owner.post(f"/api/tasks/{t2['id']}/feedback",
                   json={"kind": "win", "note": "x", "numbers": "1", "promote": True})
    ok("promote without a domain -> 400", r.status_code == 400, r.text[:100])

    print("═══ GET /api/feedback (browser payload) ═══")
    d = owner.get("/api/feedback").json()
    ok("wins parsed with derived fields",
       any(e.get("headline") == "First probe win" and e.get("domain") == "e2edom"
           and e.get("task_id") == t1["id"] and e.get("date") for e in d.get("wins", [])),
       str(d.get("wins"))[:150])
    ok("lessons parsed", any(e.get("headline") == "Probe lesson"
                             for e in d.get("lessons", [])))
    ok("files exposed for the UI", d.get("files", {}).get("win") == str(wins_path))
    d2 = owner.get("/api/feedback", params={"domain": "nosuchdom"}).json()
    ok("domain filter", not d2.get("wins") and not d2.get("lessons"))

    print("═══ parser units ═══")
    crafted = ("# WINS\n\n## Template\n\n```\n### YYYY-MM-DD — <what>\n- Domain: <x>\n```\n"
               "\n---\n\n<!-- newest first -->\n\n"
               "### 2026-07-12 — Real entry\n- Domain: —\n- Result: 5\n"
               "  continued line\n\nnot a heading\n"
               "### bad heading without date\n- Domain: x\n")
    es = fbl.parse_entries(crafted)
    ok("template fence excluded + malformed heading skipped",
       len(es) == 1 and es[0]["headline"] == "Real entry", str(es)[:120])
    ok("em-dash domain -> None + continuation folded",
       es and es[0]["domain"] is None and ["Result", "5 continued line"] in es[0]["fields"])
    es2 = fbl.parse_entries("### 2026-01-01 - Hyphen variant\n- Domain: Marketing\n")
    ok("marker-less + hyphen heading + domain lowercased",
       len(es2) == 1 and es2[0]["domain"] == "marketing")

    print("═══ dispatch_block (framing excerpt) ═══")
    blk = fbl.dispatch_block("e2edom")
    ok("block carries WIN + LESSON excerpts",
       "FEEDBACK LEDGER" in blk and "[WIN" in blk and "[LESSON" in blk
       and "add output-format line" in blk, blk[:150])
    # a legacy placeholder lesson must be excluded
    owner.post(f"/api/tasks/{t1['id']}/feedback",
               json={"kind": "lesson", "headline": "Placeholder probe", "note": "x",
                     "correction": "to be decided — revisit this entry"})
    ok("'to be decided' lessons excluded",
       "Placeholder probe" not in fbl.dispatch_block("e2edom"))
    db.set_setting("feedback.framing_max_chars", "300")
    ok("size cap respected", len(fbl.dispatch_block("e2edom")) <= 300)
    db.set_setting("feedback.framing_max_chars", "1200")
    db.set_setting("feedback.framing_enabled", "0")
    ok("kill switch", fbl.dispatch_block("e2edom") == "")
    db.set_setting("feedback.framing_enabled", "1")
    ok("general/blank domains never inject",
       fbl.dispatch_block("general") == "" and fbl.dispatch_block("") == "")

    print("═══ build_framing hook ═══")
    t1row = db.query_one("SELECT * FROM tasks WHERE id=?", (t1["id"],))
    fr = hd.build_framing(t1row, ws)
    ok("domain task framing carries the ledger block",
       "FEEDBACK LEDGER" in fr and "[WIN" in fr, fr[-200:])
    t2row = db.query_one("SELECT * FROM tasks WHERE id=?", (t2["id"],))
    ok("domain-less framing does not", "FEEDBACK LEDGER" not in hd.build_framing(t2row, ws))

    print("═══ concurrent writes ═══")
    before = wins_path.read_text().count("### ")
    errs = []

    def _log(i):
        try:
            rr = owner.post(f"/api/tasks/{t1['id']}/feedback",
                            json={"kind": "win", "headline": f"Concurrent {i}",
                                  "note": "n", "numbers": f"GATE-c{i}"})
            if rr.status_code != 200:
                errs.append(rr.text[:80])
        except Exception as e:  # noqa: BLE001 — gate collects, main asserts
            errs.append(str(e)[:80])
    threads = [threading.Thread(target=_log, args=(i,)) for i in range(6)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    body = wins_path.read_text()
    ok("6 parallel logs all landed, none torn",
       not errs and body.count("### ") == before + 6 and body.startswith("# WINS"),
       f"errs={errs} count={body.count('### ')} vs {before}+6")

    print("═══ draft endpoint ═══")
    r = owner.post(f"/api/tasks/{t1['id']}/feedback/draft", json={"kind": "bogus"})
    ok("draft bad kind -> 400", r.status_code == 400, r.text[:80])
    # LLM smoke — tolerant: 200 (draft), 502/503 (gateway down / GLM load-shed)
    try:
        r = owner.post(f"/api/tasks/{t1['id']}/feedback/draft", json={"kind": "win"},
                       timeout=200)
        if r.status_code == 200:
            dr = r.json().get("draft", {})
            ok("draft smoke (200) — no invented numbers key",
               "numbers" not in dr and "result" not in dr, str(dr)[:150])
        else:
            ok("draft smoke (upstream unavailable tolerated)",
               r.status_code in (502, 503), f"{r.status_code} {r.text[:100]}")
    except Exception as e:  # noqa: BLE001
        ok("draft smoke (upstream unavailable tolerated)", True, str(e)[:80])


if __name__ == "__main__":
    try:
        main()
    finally:
        for fn in reversed(CLEANUP):
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                print(f"cleanup: {e}")
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
