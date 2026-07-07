#!/usr/bin/env python3
"""Runtime (Layer-2) verification for the Agentic OS frontend + API contract.

Drives the REAL browser via Playwright: loads the Agentic view, asserts it
renders all subsystem cards, exercises the approval flow from the UI (the exact
contract-drift class of bug that static gates miss — SSE/event-name mismatches).
Captures console errors as evidence.
"""
import asyncio, sys, os
from playwright.async_api import async_playwright
from _gate_auth import owner_cookie, playwright_cookies

BASE = "https://127.0.0.1:8777"
CK = owner_cookie()  # {} while login is off; owner session when multi-user is live
SHOTS = os.path.expanduser("~/.hermes/cache/screenshots")
os.makedirs(SHOTS, exist_ok=True)
P, F = 0, 0
console_errors = []

def ok(name, cond, extra=""):
    global P, F
    if cond: P += 1; print(f"  PASS  {name}")
    else:    F += 1; print(f"  FAIL  {name}  {extra}")


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900},
                                      ignore_https_errors=True)
        await page.context.add_cookies(playwright_cookies(BASE))
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"PAGEERROR: {e}"))

        await page.goto(BASE, wait_until="networkidle")
        ok("dashboard loads", await page.title() == "NEXUS — Agent OS")

        # Navigate to Agentic view
        await page.click('a.nav-item[data-view="agentic"]')
        await page.wait_for_timeout(800)
        ok("Agentic view renders", await page.locator('h3:has-text("Approval Gates")').count() > 0)
        ok("watchdog card present", await page.locator('h3:has-text("Self-Healing Watchdog")').count() > 0)
        ok("verify runs card present", await page.locator('h3:has-text("Verify Runs")').count() > 0)
        ok("scheduler card present", await page.locator('h3:has-text("Cron Scheduler")').count() > 0)
        ok("cost card present", await page.locator('h3:has-text("Cost Guardrails")').count() > 0)
        await page.screenshot(path=f"{SHOTS}/agentic_view.png")

        # Create an approval via API, then approve it from the UI
        import requests
        r = requests.post(f"{BASE}/api/approvals", verify=False, cookies=CK, json={
            "agent_id": "agent-alpha", "action_type": "deploy",
            "description": "deploy v3 to staging (e2e test)", "risk_level": "high"}).json()
        aid = r["id"]
        await page.wait_for_timeout(500)
        await load_agentic(page)
        ok("approval shows in UI", await page.locator(f'text=deploy v3 to staging').count() > 0)
        # click Approve on that row
        approve_btn = page.locator(f'div.agentic-row:has-text("deploy v3") button:has-text("Approve")')
        if await approve_btn.count() > 0:
            await approve_btn.first.click()
            await page.wait_for_timeout(800)
            ok("approval approved from UI", await page.locator(f'text=deploy v3 to staging').count() == 0)
        else:
            ok("approval approve button found", False, "no approve button")

        # Open the scheduler modal and create a job from the UI
        await page.click('button:has-text("+ Job")')
        await page.wait_for_selector('#jobModal input#jbName:visible', timeout=3000)
        await page.fill('#jbName', "e2e-job")
        await page.fill('#jbCron', "*/5 * * * *")
        await page.fill('#jbAction', "run tests")
        await page.click('#jobModal button:has-text("Create")')
        await page.wait_for_timeout(600)
        ok("scheduler job created from UI", await page.locator('text=e2e-job').count() > 0)
        # clean up
        jid = [j["id"] for j in requests.get(f"{BASE}/api/scheduler", verify=False, cookies=CK).json()["jobs"] if j["name"] == "e2e-job"]
        if jid: requests.delete(f"{BASE}/api/scheduler/{jid[0]}", verify=False, cookies=CK)

        # Kanban view shows claim/verify fields (the enhanced card)
        await page.click('a.nav-item[data-view="kanban"]')
        await page.wait_for_timeout(500)
        ok("kanban view renders", await page.locator('.kanban-board').count() > 0)
        await page.screenshot(path=f"{SHOTS}/kanban_view.png")

        # Check no console errors on any view
        ok("no console errors", len(console_errors) == 0, str(console_errors[:3]))

        await browser.close()

async def load_agentic(page):
    # trigger a tick-like refresh by re-entering the view
    await page.evaluate("loadAgenticData()")
    await page.wait_for_timeout(500)


asyncio.run(main())
print(f"\n=== RUNTIME RESULT: {P} passed, {F} failed ===")
print(f"screenshots: {SHOTS}/agentic_view.png, {SHOTS}/kanban_view.png")
sys.exit(1 if F else 0)
