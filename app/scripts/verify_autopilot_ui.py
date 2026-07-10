#!/usr/bin/env python3
"""Runtime UI gate for Quality Autopilot (QUALITY-AUTOPILOT-PLAN-2026-07-10 Part 5).

The Part-5 Playwright row: "Decisions view renders cards + badge; manual view
sections; preset cards in wizard." Drives the three surfaces in a real headless
browser against the LIVE server, no LLM calls:
  - Decisions inbox (Q7b): a seeded pending high-risk approval renders as a card
    with a ★ recommendation and lights the nav badge.
  - User Manual (Q7c): the plain-language sections render (autopilot dials +
    Decisions inbox chapters present).
  - Autopilot preset cards (Q7a): the two-axis radio cards mount in BOTH the
    project proposal wizard and the task-create wizard.

Run: .venv/bin/python scripts/verify_autopilot_ui.py
"""
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

from playwright.async_api import async_playwright
import urllib3
urllib3.disable_warnings()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _gate_auth import playwright_cookies  # noqa: E402
import database as db  # noqa: E402

BASE = "https://127.0.0.1:8777"
P, F = 0, 0
console_errors = []
SEED = uuid.uuid4().hex[:6]
APPR_ID = f"apui-appr-{SEED}"
TASK_ID = f"apui-task-{SEED}"
HEADLINE = f"Deliverable ready for review (ui gate {SEED})"


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  PASS  {name}")
    else:
        F += 1
        print(f"  FAIL  {name}  {extra}")


TEST_PLAN = {
    "name": "apui probe project", "goal": "probe", "domain": "software-engineering",
    "tasks": [
        {"title": "Spec & plan", "description": "spec", "domain": "software-engineering",
         "specialist": "tech-lead-orchestrator", "high_stakes": False, "model": None,
         "priority": 2, "budget_tokens": 2000000, "tags": [], "depends_on_idx": []},
        {"title": "Implement + tests", "description": "impl", "domain": "software-engineering",
         "specialist": "code-implementer", "high_stakes": False, "model": None,
         "priority": 2, "budget_tokens": None, "tags": [], "depends_on_idx": [0]},
    ],
}


def _seed_decision():
    now = time.time()
    db.execute("INSERT INTO tasks (id, title, status, created_at, updated_at, user_id, "
               "judge_verdict) VALUES (?,?,?,?,?,?,?)",
               (TASK_ID, "apui deliverable", "review", now, now, "u_owner", "SHIP"))
    payload = json.dumps({"headline": HEADLINE, "recommendation": "Approve & ship",
                          "reasons": ["clean judge pass", "no open comments"],
                          "cost_hint": "another round ≈ 40k tokens", "task_id": TASK_ID})
    db.execute("INSERT INTO approvals (id, agent_id, action_type, description, payload, status, "
               "risk_level, requested_at, user_id) "
               "VALUES (?,?,?,?,?,?,?,?,?)",
               (APPR_ID, "a", "deliverable", "d", payload, "pending", "high", now, "u_owner"))


async def main():
    _seed_decision()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1600, "height": 1000},
                                      ignore_https_errors=True)
        await page.context.add_cookies(playwright_cookies(BASE))
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"PAGEERROR: {e}"))
        await page.goto(BASE, wait_until="networkidle")

        # ── Decisions inbox: cards + badge ──
        await page.evaluate("async () => { await loadDecisions(false); switchView('decisions'); }")
        await page.wait_for_selector("#content .view-intro", timeout=5000)
        intro = (await page.locator("#content .view-intro").first.inner_text()).lower()
        ok("decisions view intro renders", "inbox of decisions" in intro, intro[:80])
        await page.wait_for_selector(".agentic-row", timeout=5000)
        body = await page.locator("#content").inner_text()
        ok("seeded decision renders as a card", HEADLINE in body)
        ok("card carries the ★ recommendation action",
           await page.locator('.agentic-row button:has-text("Approve & ship")').count() >= 1)
        badge = page.locator("#decBadge")
        badge_txt = (await badge.inner_text()).strip() if await badge.count() else ""
        badge_vis = await badge.is_visible() if await badge.count() else False
        ok("nav Decisions badge shows the blocking count", badge_vis and badge_txt.isdigit()
           and int(badge_txt) >= 1, f"vis={badge_vis} txt={badge_txt!r}")

        # ── User Manual: plain-language sections ──
        await page.evaluate("() => switchView('manual')")
        await page.wait_for_selector(".manual-sec", timeout=5000)
        secs = await page.locator(".manual-sec").count()
        ok("manual renders its sections", secs >= 10, f"{secs}")
        mbody = await page.locator("#content").inner_text()
        ok("manual explains the Autopilot dials (Q7c)", "Autopilot — two simple dials" in mbody)
        ok("manual explains the Decisions inbox (Q7c)", "Your Decisions inbox" in mbody)
        ok("manual has a chapter table of contents",
           await page.locator('.manual-toc a[href="#m-quality"]').count() >= 1)

        # ── Autopilot preset cards in the PROJECT proposal wizard ──
        await page.evaluate("([wf]) => proposeWorkflowModal(wf, {assumptions: [], repairs: []})",
                            [TEST_PLAN])
        await page.wait_for_selector(".ap-card", timeout=5000)
        ok("project wizard mounts the two preset axes", await page.locator(".ap-axis").count() == 2)
        ok("project wizard renders all 6 preset cards (3 involvement + 3 spend)",
           await page.locator(".ap-card").count() == 6,
           f"{await page.locator('.ap-card').count()}")
        ok("project preset radios wired (involvement + spend)",
           await page.locator('input[name="wf-inv"]').count() == 3
           and await page.locator('input[name="wf-spend"]').count() == 3)
        await page.evaluate("() => closeModal()")

        # ── Autopilot preset cards in the TASK-create wizard ──
        await page.evaluate("() => showTaskModal('backlog')")
        await page.wait_for_selector("#m-task-title", timeout=5000)
        await page.wait_for_selector(".ap-card", timeout=5000)
        ok("task wizard renders all 6 preset cards",
           await page.locator(".ap-card").count() == 6,
           f"{await page.locator('.ap-card').count()}")
        ok("task preset radios wired (m-task prefix)",
           await page.locator('input[name="m-task-inv"]').count() == 3
           and await page.locator('input[name="m-task-spend"]').count() == 3)
        await page.evaluate("() => closeModal()")

        real_errors = [e for e in console_errors if "favicon" not in e]
        ok("no console errors", not real_errors, "; ".join(real_errors[:3])[:200])
        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        db.execute("DELETE FROM approvals WHERE id=?", (APPR_ID,))
        db.execute("DELETE FROM tasks WHERE id=?", (TASK_ID,))
    print(f"\n{'ALL PASSED' if F == 0 else 'FAILURES'}: {P} passed, {F} failed")
    sys.exit(1 if F else 0)
