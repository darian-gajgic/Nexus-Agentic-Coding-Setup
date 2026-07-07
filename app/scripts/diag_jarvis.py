"""Diagnostic: load the Jarvis UI, capture console errors + failed network requests,
then screenshot the JARVIS view. This is the runtime test the static gate can't do."""
import time
import json
from playwright.sync_api import sync_playwright

console_msgs = []
page_errors = []
failed_reqs = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
    page.on("pageerror", lambda e: page_errors.append(f"PAGEERROR: {e}"))
    page.on("requestfailed", lambda r: failed_reqs.append(
        f"FAILED {r.method} {r.url} :: {r.failure}"))

    page.goto("http://localhost:8777", wait_until="networkidle", timeout=15000)
    time.sleep(3)

    # Try to navigate to the JARVIS view (click the nav item if present)
    try:
        # Look for a jarvis nav button/link
        for sel in ['text=JARVIS', 'text=Jarvis', '[data-view="jarvis"]', 'button:has-text("Jarvis")']:
            el = page.query_selector(sel)
            if el:
                el.click()
                print(f"clicked nav: {sel}")
                time.sleep(2)
                break
    except Exception as e:
        print(f"nav click: {e}")

    time.sleep(2)
    page.screenshot(path="/home/sinep/.hermes/cache/screenshots/jarvis-diag.png", full_page=False)

    # Dump the avatar area HTML so I can see what rendered
    avatar_html = page.evaluate("""() => {
        const w = document.querySelector('#jAvatarWrap');
        const vid = document.querySelector('#jAvatarVideo');
        return {
            avatarWrap: w ? w.innerHTML.substring(0,400) : 'NOT FOUND',
            videoEl: vid ? {src: vid.currentSrc, poster: vid.poster, className: vid.className, readyState: vid.readyState} : 'NOT FOUND',
            stateLabel: (document.querySelector('#jState')||{}).textContent || 'none',
            hermesStatus: (document.querySelector('#jHermesStatus')||{}).textContent || 'none',
            voiceStatus: (document.querySelector('#jVoiceStatus')||{}).textContent || 'none',
        };
    }""")

    browser.close()

print("\n===== CONSOLE MESSAGES (%d) =====" % len(console_msgs))
for m in console_msgs[:25]:
    print(m)
print("\n===== PAGE ERRORS (%d) =====" % len(page_errors))
for e in page_errors:
    print(e)
print("\n===== FAILED REQUESTS (%d) =====" % len(failed_reqs))
for r in failed_reqs:
    print(r)
print("\n===== AVATAR DOM STATE =====")
print(json.dumps(avatar_html, indent=2))
