"""Diagnostic 2: test the INTERACTIVE reply flow — type a message, capture what happens
with chat streaming, TTS, and lipsync. This catches the 'Jarvis not responding' bug."""
import time
import json
from playwright.sync_api import sync_playwright

console_msgs = []
page_errors = []
failed_reqs = []
network_reqs = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
    page.on("pageerror", lambda e: page_errors.append(f"PAGEERROR: {e}"))
    page.on("requestfailed", lambda r: failed_reqs.append(f"FAILED {r.method} {r.url} :: {r.failure}"))
    page.on("request", lambda r: network_reqs.append(f"{r.method} {r.url}") if any(x in r.url for x in ['/api/jarvis','/chat','/tts','/lipsync','/stt']) else None)
    page.on("response", lambda r: network_reqs.append(f"  -> {r.status} {r.url}") if any(x in r.url for x in ['/api/jarvis','/chat','/tts','/lipsync','/stt']) else None)

    page.goto("http://localhost:8777", wait_until="networkidle", timeout=15000)
    time.sleep(2)
    page.click('text=JARVIS')
    time.sleep(2)

    # Type a message and send
    inp = page.query_selector('#jInput')
    send = page.query_selector('#jSendBtn, button:has-text("Send"), [data-action="send"]')
    print(f"input found: {bool(inp)}, send btn found: {bool(send)}")
    if inp:
        inp.fill("Hello, can you hear me?")
        time.sleep(0.5)
        # Try clicking send, or pressing Enter
        if send:
            send.click()
            print("clicked send")
        else:
            inp.press("Enter")
            print("pressed Enter")

    # Watch the network + wait for a reply
    time.sleep(12)

    # Capture the chat transcript + state
    state = page.evaluate("""() => {
        const msgs = [...document.querySelectorAll('.jarvis-msg, .msg, [class*="message"]')].map(e => e.textContent.trim()).slice(-8);
        return {
            stateLabel: (document.querySelector('#jState')||{}).textContent || 'none',
            ttsCount: (document.querySelector('#jTtsCount')||{}).textContent || 'none',
            messages: msgs,
            inputVal: (document.querySelector('#jInput')||{}).value || '',
        };
    }""")
    page.screenshot(path="/home/sinep/.hermes/cache/screenshots/jarvis-after-msg.png")
    browser.close()

print("\n===== JARVIS API NETWORK ACTIVITY =====")
for r in network_reqs:
    print(r)
print("\n===== STATE AFTER MESSAGE =====")
print(json.dumps(state, indent=2))
print("\n===== NEW PAGE ERRORS =====")
for e in page_errors:
    print(e)
print("\n===== NEW CONSOLE ERRORS =====")
for m in console_msgs:
    if m.startswith("[error]") or m.startswith("[warning]"):
        print(m)
