#!/usr/bin/env python3
"""Screenshot every non-JARVIS tab and report console errors per tab.

Usage: .venv/bin/python scripts/screenshot_all_tabs.py [outdir-suffix]
Saves to ~/.hermes/cache/screenshots/nexus-<suffix>/<view>.png
"""
import asyncio, sys, os
from playwright.async_api import async_playwright
from _gate_auth import playwright_cookies

BASE = "https://127.0.0.1:8777"
SUFFIX = sys.argv[1] if len(sys.argv) > 1 else "current"
SHOTS = os.path.expanduser(f"~/.hermes/cache/screenshots/nexus-{SUFFIX}")
os.makedirs(SHOTS, exist_ok=True)

VIEWS = ["dashboard", "tools", "skills", "projects", "usage", "observability",
         "memory", "specialists", "guardian", "kanban", "agents", "programs",
         "monitor", "agentic"]


async def main():
    errors = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1600, "height": 1000},
                                      ignore_https_errors=True)
        await page.context.add_cookies(playwright_cookies(BASE))
        current_view = ["boot"]
        page.on("console", lambda m: errors.setdefault(current_view[0], []).append(m.text)
                if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.setdefault(current_view[0], []).append(f"PAGEERROR: {e}"))

        await page.goto(BASE, wait_until="networkidle")
        for v in VIEWS:
            current_view[0] = v
            await page.click(f'a.nav-item[data-view="{v}"]')
            # slow views fetch on first entry; give them time
            await page.wait_for_timeout(2500)
            await page.screenshot(path=f"{SHOTS}/{v}.png", full_page=False)
            print(f"shot: {v}")
        await browser.close()

    print(f"\nsaved to {SHOTS}")
    bad = {k: v for k, v in errors.items() if v}
    if bad:
        print("\nCONSOLE ERRORS:")
        for k, v in bad.items():
            for e in v[:5]:
                print(f"  [{k}] {e[:200]}")
        sys.exit(1)
    print("no console errors")


asyncio.run(main())
