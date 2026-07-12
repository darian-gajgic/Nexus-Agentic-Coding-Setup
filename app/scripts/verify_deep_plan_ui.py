#!/usr/bin/env python3
"""Runtime UI gate for Deep Plan mode (DEEP-PLAN-MODE-PLAN-2026-07-10 Step 10).

Drives the conversational planning UI in a real headless browser against the LIVE
server with the planning model stubbed via `plan.stub` (no LLM calls):
  - the recommendation soft gate (banner accept/deny) over the wizard flow;
  - the Deep Plan modal: two-pane render, family switcher, a turn, a direct spec edit;
  - Draft → the proposal modal with the Deep Plan banner + premortem annotations.

Run: .venv/bin/python scripts/verify_deep_plan_ui.py
"""
import asyncio
import sys
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
        P += 1; print(f"  PASS  {name}")
    else:
        F += 1; print(f"  FAIL  {name}  {extra}")


# a canned wizard response carrying a recommend_deep_plan triage (Step 3 banner)
REC_RESP = {
    "type": "workflow",
    "workflow": {"name": "probe", "goal": "probe goal", "domain": "software-engineering",
                 "tasks": [{"title": "Spec & plan", "description": "spec",
                            "domain": "software-engineering", "specialist": "tech-lead-orchestrator",
                            "high_stakes": False, "model": None, "priority": 2,
                            "budget_tokens": 2000000, "tags": [], "depends_on_idx": []}]},
    "assumptions": [], "repairs": [],
    "triage": {"complexity": 8, "ambiguity": 0.6, "recommend_deep_plan": True,
               "recommend_super_result": True, "reasons": ["multiple deliverables", "blast radius"],
               "family": "software"},
}


# Fable-5 checker finding N1: scope deletes to THIS gate's session goal — a full
# table wipe destroys the operator's real planning history mid-interview.
GATE_GOAL = "build a webshop and deploy it"


def _wipe_gate_sessions():
    db.execute("DELETE FROM plan_sessions WHERE goal=?", (GATE_GOAL,))


async def main():
    _wipe_gate_sessions()
    stub0 = db.get_setting("plan.stub", "0")
    db.set_setting("plan.stub", "1")
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1600, "height": 1000},
                                          ignore_https_errors=True)
            await page.context.add_cookies(playwright_cookies(BASE))
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append(f"PAGEERROR: {e}"))
            await page.goto(BASE, wait_until="networkidle")

            # ── Step 3: recommendation banner over the wizard flow ──
            await page.evaluate("(r) => handleWizardPlan('build a webshop and deploy it', r)", REC_RESP)
            await page.wait_for_selector("#dpAccept", timeout=5000)
            ok("recommendation banner renders (reasons + two buttons)",
               await page.locator("#dpDeny").count() == 1 and await page.locator("#dpAccept").count() == 1)
            # Deny → the normal proposal flow continues
            await page.click("#dpDeny")
            await page.wait_for_selector("#wfStages", timeout=5000)
            ok("deny → quick plan proposal renders", await page.locator("#wfCreateBtn").count() == 1)
            await page.evaluate("() => closeModal()")

            # ── Step 5: accept → the Deep Plan modal (two panes) ──
            await page.evaluate("(r) => { _deepPlanOffered.clear(); handleWizardPlan('build a webshop and deploy it', r); }", REC_RESP)
            await page.wait_for_selector("#dpAccept", timeout=5000)
            await page.click("#dpAccept")
            await page.wait_for_selector("#dpSpec .dp-slot", timeout=8000)
            ok("Deep Plan modal: conversation + spec panes render",
               await page.locator("#dpConvo").count() == 1 and await page.locator("#dpSpec .dp-slot").count() >= 3)
            ok("family switcher present", await page.locator("#dpFamily").count() == 1)

            # ── a turn ──
            await page.fill("#dpInput", "FastAPI + Postgres")
            await page.click("#dpSend")
            await page.wait_for_timeout(1200)
            ok("turn advances the interview (turn counter > 0)",
               "Turn 1" in (await page.locator("#dpConvo").inner_text())
               or "Turn 2" in (await page.locator("#dpConvo").inner_text()))

            # ── direct spec edit persists (PATCH /spec) ──
            slot = page.locator("#dpSpec .dp-slot").first
            await slot.fill("edited by ui gate")
            await page.wait_for_timeout(1100)  # debounce
            sid = await page.evaluate("() => deepPlan && deepPlan.session && deepPlan.session.id")
            row = db.query_one("SELECT spec_json FROM plan_sessions WHERE id=?", (sid,))
            ok("direct spec edit persisted to the session",
               bool(row) and "edited by ui gate" in (row.get("spec_json") or ""))

            # ── Draft → proposal modal with the Deep Plan banner + annotations ──
            await page.click("#dpDraft")
            await page.wait_for_selector("#wfStages", timeout=10000)
            body = await page.locator("#modalContent").inner_text()
            ok("draft → proposal modal renders with Deep Plan banner",
               "Deep Plan" in body and await page.locator("#dpSpecWarnings").count() == 1)
            # premortem auto-runs (stub) → an advisory annotation lands on a
            # task card. It renders as a `.plan-adv` row ("Advisory — …"); the
            # ⚠ prefix is stripped in the card template (batch-A relabel,
            # 5df5d26), so assert the rendered element, not the raw glyph.
            # (wait_for_function: the auto-revise chain re-renders annotations,
            # so a fixed sleep could sample the between-rounds gap)
            try:
                await page.wait_for_function(
                    "() => document.querySelectorAll('#wfStages .plan-adv').length > 0",
                    timeout=8000)
                ok("premortem annotation renders on a task card", True)
            except Exception:
                ok("premortem annotation renders on a task card", False)
            # Step 7: the re-run premortem button is available for a Deep-Plan proposal
            ok("Step 7 re-run premortem button renders",
               await page.locator("#wfRerunCritique").count() == 1)

            # ── Step 7b: the revise loop — findings fold back into the plan ──
            ok("revise button renders", await page.locator("#wfRevisePlan").count() == 1)
            try:
                await page.wait_for_function(
                    "() => planEd && planEd.autoRevised && "
                    "planEd.tasks.some(t => (t.description || '').includes('Addressed finding'))",
                    timeout=10000)
                ok("auto-revise folded the premortem findings into the plan", True)
            except Exception:
                ok("auto-revise folded the premortem findings into the plan", False)
            qs_text = await page.locator("#dpReviseQs").inner_text()
            ok("revision decision question renders for the operator", "[stub]" in qs_text)

            ok("no console errors", not console_errors, str(console_errors[:2]))
            await browser.close()
    finally:
        _wipe_gate_sessions()
        db.set_setting("plan.stub", stub0)

    print(f"\n{'='*44}")
    if F == 0:
        print(f"  ALL DEEP PLAN UI CHECKS PASSED: {P}/{P}")
        sys.exit(0)
    print(f"  {F} FAILED, {P} passed")
    sys.exit(1)


asyncio.run(main())
