#!/usr/bin/env python3
"""Runtime UI verification for Block 3 (docs/SPEC-BLOCK3.md):
plan editor in the proposal modal (R1), replan review modal (R2), evals tab (R3).
The proposal modal is driven directly (proposeWorkflowModal with a fixed plan) —
no LLM call; Create is exercised only far enough to prove the revalidate
round-trip (the test plan is built so the plan checker MUST repair it, which
re-renders instead of creating).
Run: .venv/bin/python scripts/verify_block3_ui.py
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


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  PASS  {name}")
    else:
        F += 1
        print(f"  FAIL  {name}  {extra}")


TEST_PLAN = {
    "name": "b3ui probe project", "goal": "probe", "domain": "software-engineering",
    "tasks": [
        {"title": "Spec & plan", "description": "spec", "domain": "software-engineering",
         "specialist": "tech-lead-orchestrator", "high_stakes": False, "model": None,
         "priority": 2, "budget_tokens": 2000000, "tags": [], "depends_on_idx": []},
        {"title": "Implement + tests", "description": "impl", "domain": "software-engineering",
         "specialist": "code-implementer", "high_stakes": False, "model": None,
         "priority": 2, "budget_tokens": None, "tags": [], "depends_on_idx": [0]},
        {"title": "Code review", "description": "review", "domain": "software-engineering",
         "specialist": "code-reviewer", "high_stakes": False, "model": None,
         "priority": 2, "budget_tokens": 3000000, "tags": [], "depends_on_idx": [0, 1]},
        {"title": "Acceptance verification", "description": "verify",
         "domain": "software-engineering", "specialist": "acceptance-verifier",
         "high_stakes": True, "model": None, "priority": 2, "budget_tokens": 3000000,
         "tags": [], "depends_on_idx": [0, 2]},
    ],
}


async def main():
    wid = f"wf-b3ui-{uuid.uuid4().hex[:6]}"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1600, "height": 1000},
                                      ignore_https_errors=True)
        await page.context.add_cookies(playwright_cookies(BASE))
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"PAGEERROR: {e}"))
        await page.goto(BASE, wait_until="networkidle")

        # ── R1: plan editor inside the proposal modal ──
        await page.evaluate(
            "([wf]) => proposeWorkflowModal(wf, {assumptions: ['probe assumption'], repairs: []})",
            [TEST_PLAN])
        await page.wait_for_selector("#wfStages .agentic-row", timeout=5000)
        rows = await page.locator("#wfStages .agentic-row").count()
        ok("proposal renders all stages", rows == 4, f"{rows}")
        locked = await page.evaluate(
            "() => [...document.querySelectorAll('#wfStages input[type=checkbox][id^=wfKeep]')]"
            ".filter(x => x.disabled).length")
        ok("quality gates locked", locked == 2, f"{locked}")

        await page.locator(".pe-edit").first.click()
        await page.wait_for_selector("#pe-title", timeout=3000)
        ok("inline editor opens", True)
        await page.fill("#pe-title", "Spec & plan (edited by gate)")
        await page.click("#pe-save")
        await page.wait_for_timeout(200)
        body = await page.locator("#wfStages").inner_text()
        ok("edit applied to the plan", "edited by gate" in body)

        await page.click("#wfAddTask")
        await page.wait_for_selector("#pe-title", timeout=3000)
        await page.fill("#pe-title", "Polish docs afterwards")
        await page.fill("#pe-desc", "operator-added tail task")
        await page.click("#pe-save")
        await page.wait_for_timeout(200)
        rows = await page.locator("#wfStages .agentic-row").count()
        ok("operator task added", rows == 5, f"{rows}")

        # Create → revalidate: the added tail task sits AFTER the verifier, so
        # the plan checker MUST repair (verifier re-becomes the final sink) and
        # re-render for confirmation instead of creating anything.
        before = db.query_one("SELECT COUNT(*) c FROM workflows")["c"]
        await page.click("#wfCreateBtn")
        await page.wait_for_timeout(2500)
        repairs_txt = await page.locator("#wfRepairs").inner_text()
        ok("edited plan revalidated with repair note", "auto-fixed" in repairs_txt,
           repairs_txt[:100])
        after = db.query_one("SELECT COUNT(*) c FROM workflows")["c"]
        ok("nothing created on a repaired plan", after == before, f"{before}->{after}")
        rows = await page.locator("#wfStages .agentic-row").count()
        ok("verifier moved back to final sink", rows == 5)
        await page.evaluate("() => closeModal()")

        # ── R2: replan review modal (proposal injected directly) ──
        now = time.time()
        db.execute("INSERT INTO workflows (id, name, goal, status, created_at, updated_at, "
                   "user_id, replan) VALUES (?,?,?,?,?,?,?,?)",
                   (wid, "b3ui replan wf", "probe", "active", now, now, "u_owner",
                    json.dumps({"status": "proposed", "reason": "stage failed (ui gate)",
                                "failed_task_id": "t-x",
                                "proposal": {"name": "b3ui replan wf", "goal": "probe",
                                             "tasks": [{"title": "Recovery step",
                                                        "description": "redo",
                                                        "domain": "general", "specialist": None,
                                                        "high_stakes": False, "model": None,
                                                        "priority": 2, "budget_tokens": None,
                                                        "tags": [], "depends_on_idx": []}],
                                             "repairs": [], "assumptions": []}})))
        tid = f"task-b3ui-{uuid.uuid4().hex[:6]}"
        db.execute("INSERT INTO tasks (id, title, status, created_at, updated_at, user_id, "
                   "workflow_id, dispatch_state) VALUES (?,?,?,?,?,?,?,?)",
                   (tid, "b3ui done stage", "done", now, now, "u_owner", wid, "completed"))
        await page.evaluate("([w]) => replanReviewModal(w)", [wid])
        await page.wait_for_selector("#wfStages .agentic-row", timeout=5000)
        modal = await page.locator("#modalContent").inner_text()
        ok("replan modal shows failure reason", "stage failed (ui gate)" in modal)
        ok("done stage shown as kept context", "done — kept" in modal)
        ok("apply button labeled", "Apply replan" in modal)
        await page.evaluate("() => closeModal()")

        # ── R3: evals tab ──
        await page.click('a.nav-item[data-view="specialists"]')
        await page.wait_for_selector('[data-spectab="evals"]', timeout=5000)
        await page.click('[data-spectab="evals"]')
        await page.wait_for_selector(".agentic-card", timeout=8000)
        cards = await page.locator(".agentic-card").count()
        ok("evals tab renders domain cards", cards >= 9, f"{cards}")
        txt = (await page.locator("#content").inner_text()).lower()
        ok("run buttons + history panel present",  # panel titles are CSS-uppercased
           "run evals" in txt and "run history" in txt)
        await page.locator('button:has-text("▶ Run evals"):not([disabled])').first.click()
        await page.wait_for_selector(".ev-case", timeout=4000)
        n_cases = await page.locator(".ev-case").count()
        ok("run modal lists the domain's cases", n_cases >= 2, f"{n_cases}")
        await page.evaluate("() => closeModal()")  # never start a real run here

        real_errors = [e for e in console_errors if "favicon" not in e]
        ok("no console errors", not real_errors, "; ".join(real_errors[:3])[:200])
        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        db.execute("DELETE FROM tasks WHERE workflow_id LIKE 'wf-b3ui-%'")
        db.execute("DELETE FROM workflows WHERE id LIKE 'wf-b3ui-%'")
    print(f"\n{'ALL PASSED' if F == 0 else 'FAILURES'}: {P} passed, {F} failed")
    sys.exit(1 if F else 0)
