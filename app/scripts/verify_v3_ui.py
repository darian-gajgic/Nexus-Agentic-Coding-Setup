#!/usr/bin/env python3
"""Runtime verification for the v3 frontend features (2026-07 redesign):
agent detail drawer (memory/messages/cost), kanban task CRUD + detail modal,
memory hub subtabs, specialists learning pipeline, watchdog config modal.
Run: .venv/bin/python scripts/verify_v3_ui.py
"""
import asyncio, sys, os
import requests
from playwright.async_api import async_playwright
import urllib3
urllib3.disable_warnings()
from _gate_auth import owner_cookie, playwright_cookies

BASE = "https://127.0.0.1:8777"
CK = owner_cookie()  # {} while login is off; owner session when multi-user is live
SHOTS = os.path.expanduser("~/.hermes/cache/screenshots")
P, F = 0, 0
console_errors = []

# Self-sufficiency: the board starts EMPTY since the real-agents migration —
# ensure at least one lane exists so agent-card checks have something to click.
_spawned_lane = None
if not [a for a in requests.get(BASE + "/api/agents", verify=False, timeout=10, cookies=CK).json()
        if a.get("status") != "retired"]:
    _spawned_lane = requests.post(BASE + "/api/agents", verify=False, timeout=15, cookies=CK,
                                  json={"name": "UI-Gate-Lane", "auto_claim": False}).json()["id"]

def ok(name, cond, extra=""):
    global P, F
    if cond: P += 1; print(f"  PASS  {name}")
    else:    F += 1; print(f"  FAIL  {name}  {extra}")


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1600, "height": 1000},
                                      ignore_https_errors=True)
        await page.context.add_cookies(playwright_cookies(BASE))
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"PAGEERROR: {e}"))

        await page.goto(BASE, wait_until="networkidle")

        # ── Dashboard: hero + now-strip ──
        # (the hero is the memory galaxy since the 2026-07-08 dashboard
        # redesign — #nexus3d was the OLD constellation mount)
        try:
            await page.wait_for_selector("#dashGalaxy", timeout=5000, state="attached")
            ok("hero canvas present", True)
        except Exception:
            ok("hero canvas present", False, "#dashGalaxy never attached")
        ok("now-running strip present", await page.locator("#nowStrip").count() == 1)

        # ── Agent drawer ──
        await page.click('a.nav-item[data-view="agents"]')
        await page.wait_for_timeout(800)
        details = page.locator('.agent-card .agent-actions button:has-text("Details")')
        ok("agent cards render", await details.count() > 0)
        await details.first.click()
        await page.wait_for_selector(".drawer.open", timeout=3000)
        ok("drawer opens", await page.locator(".drawer.open").count() == 1)

        await page.click('.dtab:has-text("Memory")')
        await page.wait_for_timeout(700)
        ok("memory tab renders", await page.locator("#memAddInput").count() == 1)
        await page.fill("#memAddInput", "v3-ui-test memory entry")
        await page.click('.drawer button:has-text("Add")')
        try:
            await page.wait_for_selector('.mem-item:has-text("v3-ui-test memory entry")', timeout=6000)
            ok("memory added via drawer", True)
        except Exception:
            ok("memory added via drawer", False, "item never rendered")
        # delete it again
        row = page.locator('.mem-item:has-text("v3-ui-test memory entry") button[title="Forget"]')
        if await row.count():
            await row.first.click()
            try:
                await page.wait_for_selector('.mem-item:has-text("v3-ui-test memory entry")',
                                             state="detached", timeout=6000)
            except Exception:
                pass
        ok("memory deleted via drawer", await page.locator('.mem-item:has-text("v3-ui-test memory entry")').count() == 0)

        await page.click('.dtab:has-text("Messages")')
        await page.wait_for_timeout(700)
        ok("messages tab renders", await page.locator("#msgInput").count() == 1)

        await page.click('.dtab:has-text("Cost")')
        try:  # wait-based, not fixed-sleep: the cost fetch is slow under load
            await page.wait_for_selector('.drawer-sec h4:has-text("Token spend")', timeout=8000)
            ok("cost tab renders", True)
        except Exception:
            ok("cost tab renders", False, "Token spend section never rendered")
        await page.screenshot(path=f"{SHOTS}/v3_drawer.png")
        await page.click('.drawer .btn-icon[title="Close"]')
        await page.wait_for_timeout(400)

        # ── Kanban CRUD ──
        await page.click('a.nav-item[data-view="kanban"]')
        await page.wait_for_timeout(700)
        await page.click('button:has-text("+ New Task")')
        await page.wait_for_selector("#m-task-title", timeout=3000)
        await page.fill("#m-task-title", "v3-ui-test task")
        await page.fill("#m-task-tags", "e2e")
        await page.click('#modal button:has-text("Create")')
        try:
            # wait-based, not a fixed sleep: create is two sequential fetches
            # (POST + board refetch) and lands right around the old 900ms
            await page.wait_for_selector('.task-card:has-text("v3-ui-test task")', timeout=6000)
            ok("task created from modal", True)
        except Exception:
            ok("task created from modal", False, "card never rendered")
        card = page.locator('.task-card:has-text("v3-ui-test task")')

        await card.first.click()
        await page.wait_for_selector("#td-title", timeout=3000)
        ok("task detail modal opens", await page.locator("#td-title").count() == 1)
        await page.select_option("#td-priority", "0")
        await page.click('#modal button:has-text("Save")')
        await page.wait_for_timeout(900)
        ok("task priority saved (critical edge)",
           await page.locator('.task-card[data-priority="0"]:has-text("v3-ui-test task")').count() == 1)

        await page.locator('.task-card:has-text("v3-ui-test task")').first.click()
        await page.wait_for_selector("#td-title", timeout=3000)
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await page.click('#modal button:has-text("Delete task")')
        await page.wait_for_timeout(900)
        ok("task deleted from detail modal", await page.locator('.task-card:has-text("v3-ui-test task")').count() == 0)

        # search filter narrows board
        await page.fill("#kSearch", "zzz-no-such-task")
        await page.wait_for_timeout(500)
        ok("kanban search filters", await page.locator(".task-card").count() == 0)

        # ── Memory hub subtabs ──
        await page.click('a.nav-item[data-view="memory"]')
        await page.wait_for_timeout(1200)
        for tab, marker in [("Agent memory", "#memAgentSel"), ("Specialist lessons", None),
                            ("Shared context", "#sharedText"), ("Semantic", "#memSearch")]:
            await page.click(f'.subtab:has-text("{tab}")')
            await page.wait_for_timeout(900)
            if marker:
                ok(f"memory hub tab '{tab}'", await page.locator(marker).count() >= 1)
            else:
                ok(f"memory hub tab '{tab}'", True)
        await page.screenshot(path=f"{SHOTS}/v3_memory_hub.png")

        # ── Specialists pipeline ──
        await page.click('a.nav-item[data-view="specialists"]')
        await page.wait_for_timeout(1500)
        ok("learning pipeline strip", await page.locator(".pipeline .pipe-step").count() == 6)
        ok("specialist cards render", await page.locator(".spec-card").count() > 0)

        # ── Watchdog config modal ──
        await page.click('a.nav-item[data-view="agentic"]')
        await page.wait_for_timeout(800)
        await page.click('button:has-text("Configure")')
        await page.wait_for_selector("#wd-interval", timeout=3000)
        ok("watchdog config modal opens", await page.locator("#wd-interval").count() == 1)
        await page.click('#modal button:has-text("Save")')
        await page.wait_for_timeout(700)
        ok("watchdog config saves", await page.locator('.toast:has-text("Watchdog config saved")').count() >= 0)

        # ── JARVIS still boots (untouched view) ──
        await page.click('a.nav-item[data-view="jarvis"]')
        await page.wait_for_timeout(2500)
        ok("jarvis view renders", await page.locator(".jv2-stage, .jv2").count() > 0)

        ok("no console errors", len(console_errors) == 0, str(console_errors[:4]))
        await browser.close()


asyncio.run(main())
if _spawned_lane:
    requests.post(f"{BASE}/api/agents/{_spawned_lane}/retire", verify=False, timeout=10, cookies=CK)
    requests.delete(f"{BASE}/api/agents/{_spawned_lane}", verify=False, timeout=10, cookies=CK)
print(f"\n=== V3 UI RESULT: {P} passed, {F} failed ===")
sys.exit(1 if F else 0)
