#!/usr/bin/env python3
"""Interaction test for the v3 frontend features (drawer, task modal, memory hub,
watchdog config, 3D hero, JARVIS still boots). Complements verify_agentic_playwright.py."""
import asyncio, sys, os
import requests
from playwright.async_api import async_playwright
import urllib3
urllib3.disable_warnings()
from _gate_auth import owner_cookie, playwright_cookies

BASE = "https://127.0.0.1:8777"
CK = owner_cookie()  # {} while login is off; owner session when multi-user is live
SHOTS = os.path.expanduser("~/.hermes/cache/screenshots/nexus-after")
os.makedirs(SHOTS, exist_ok=True)
P, F = 0, 0
console_errors = []

# Self-sufficiency: the board starts EMPTY since the real-agents migration —
# ensure at least one lane + one kanban card exist for the click-through checks.
_spawned_lane = None
if not [a for a in requests.get(BASE + "/api/agents", verify=False, timeout=10, cookies=CK).json()
        if a.get("status") != "retired"]:
    _spawned_lane = requests.post(BASE + "/api/agents", verify=False, timeout=15, cookies=CK,
                                  json={"name": "UI-Gate-Lane", "auto_claim": False}).json()["id"]
_spawned_task = None
if not requests.get(BASE + "/api/tasks", verify=False, timeout=10, cookies=CK).json():
    _spawned_task = requests.post(BASE + "/api/tasks", verify=False, timeout=15, cookies=CK,
                                  json={"title": "UI gate probe card",
                                        "status": "backlog"}).json()["id"]

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
        await page.wait_for_timeout(2500)

        # 1. Dashboard: galaxy hero mounted with a real WebGL canvas, now-strip
        # present (the hero is the memory galaxy since the 2026-07-08 dashboard
        # redesign — #nexus3d was the OLD constellation mount)
        ok("3D canvas present", await page.locator("#dashGalaxy").count() == 1)
        size = 0
        for _ in range(10):  # CDN module + WebGL init can lag
            size = await page.evaluate(
                "() => { const c = document.querySelector('#dashGalaxy canvas'); return c ? c.width : 0 }")
            if size > 0:
                break
            await page.wait_for_timeout(500)
        ok("3D canvas has WebGL-sized backing store", size > 0, f"width={size}")
        ok("now-running strip", await page.locator("#nowStrip .now-row").count() > 0)

        # 2. Agents: open drawer, walk all tabs
        await page.click('a.nav-item[data-view="agents"]')
        await page.wait_for_timeout(1200)
        await page.locator(".agent-card").first.click()
        await page.wait_for_timeout(800)
        ok("drawer opens", await page.locator("#drawer.open").count() == 1)
        for tab, probe in [("Memory", ".drawer-sec"), ("Messages", ".drawer-sec"), ("Cost", ".stat-card"), ("Overview", ".kv-row")]:
            await page.click(f'.dtab:has-text("{tab}")')
            try:  # wait-based: tab content is an async fetch, not a fixed 900ms
                await page.wait_for_selector(f"#drawerBody {probe}", timeout=6000, state="attached")
                ok(f"drawer tab {tab} renders", True)
            except Exception:
                ok(f"drawer tab {tab} renders", False, "probe never attached")
        await page.screenshot(path=f"{SHOTS}/x-drawer.png")
        # teach a memory through the drawer
        await page.click('.dtab:has-text("Memory")')
        await page.wait_for_timeout(700)
        await page.fill("#memAddInput", "e2e drawer memory test")
        await page.click('#drawerBody button:has-text("Add")')
        try:  # wait-based, not fixed-sleep (the add re-render is an async fetch)
            await page.wait_for_selector('.mem-item:has-text("e2e drawer memory test")', timeout=6000)
            ok("memory added via drawer", True)
        except Exception:
            ok("memory added via drawer", False, "item never rendered")
        # delete ALL matching rows — an earlier aborted run may have left one behind
        row = page.locator('.mem-item:has-text("e2e drawer memory test") button[title="Forget"]')
        for _ in range(5):
            if not await row.count():
                break
            await row.first.click()
            await page.wait_for_timeout(600)
        ok("memory deleted via drawer", await page.locator('#drawerBody:has-text("e2e drawer memory test")').count() == 0)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(400)
        ok("drawer closes on Escape", await page.locator("#drawer.open").count() == 0)

        # 3. Kanban: task detail modal opens with editable fields
        await page.click('a.nav-item[data-view="kanban"]')
        await page.wait_for_timeout(900)
        await page.locator(".task-card").first.click()
        await page.wait_for_timeout(600)
        ok("task detail modal opens", await page.locator("#td-title").count() == 1)
        ok("task detail has delete", await page.locator('button:has-text("Delete task")').count() == 1)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
        # filters exist
        ok("kanban filter bar", await page.locator("#kSearch").count() == 1 and await page.locator("#kAssignee").count() == 1)
        await page.fill("#kSearch", "zzz-no-match-zzz")
        await page.wait_for_timeout(500)
        ok("kanban search filters cards", await page.locator(".task-card").count() == 0)
        await page.fill("#kSearch", "")
        await page.wait_for_timeout(400)

        # 4. Memory hub subtabs
        await page.click('a.nav-item[data-view="memory"]')
        await page.wait_for_timeout(1500)
        for tab in ["Agent memory", "Specialist lessons", "Shared context", "Semantic"]:
            await page.click(f'.subtab:has-text("{tab}")')
            await page.wait_for_timeout(1200)
            ok(f"memory tab '{tab}' renders", await page.locator("#memTabBody").inner_text() != "")
        await page.screenshot(path=f"{SHOTS}/x-memoryhub.png")

        # 5. Agentic: watchdog config modal
        await page.click('a.nav-item[data-view="agentic"]')
        await page.wait_for_timeout(900)
        await page.click('button:has-text("Configure")')
        await page.wait_for_timeout(500)
        ok("watchdog modal opens", await page.locator("#wd-interval").count() == 1)
        await page.click('button:has-text("Save")')
        try:  # wait-based: the save round-trip outlives a fixed sleep under load
            await page.wait_for_selector('.toast:has-text("Watchdog config saved")', timeout=6000)
            ok("watchdog config saved (toast)", True)
        except Exception:
            ok("watchdog config saved (toast)", False, "toast never appeared")

        # 6. JARVIS still boots (no voice interaction)
        await page.click('a.nav-item[data-view="jarvis"]')
        await page.wait_for_timeout(4000)
        ok("jarvis view renders", await page.locator(".jarvis-layout").count() == 1)
        ok("jarvis avatar present", await page.locator("#jAvatarVideo, .avatar-wrap").count() > 0)
        await page.screenshot(path=f"{SHOTS}/x-jarvis.png")

        real_errors = [e for e in console_errors if "favicon" not in e]
        ok("no console errors", len(real_errors) == 0, str(real_errors[:3]))
        await browser.close()


asyncio.run(main())
if _spawned_lane:
    requests.post(f"{BASE}/api/agents/{_spawned_lane}/retire", verify=False, timeout=10, cookies=CK)
    requests.delete(f"{BASE}/api/agents/{_spawned_lane}", verify=False, timeout=10, cookies=CK)
if _spawned_task:
    requests.delete(f"{BASE}/api/tasks/{_spawned_task}", verify=False, timeout=10, cookies=CK)
print(f"\n=== V3 INTERACTION RESULT: {P} passed, {F} failed ===")
sys.exit(1 if F else 0)
