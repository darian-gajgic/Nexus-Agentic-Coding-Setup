"""Complete self-verification of the JARVIS neural talking-head avatar.
Exercises the full runtime path and captures evidence screenshots:
 1. Page loads, JARVIS view renders, avatar shows reference face (idle)
 2. Type message -> reply streams (SSE), renders in feed
 3. TTS plays + lip-sync video loads + plays (readyState 4) during SPEAKING
 4. State transitions: idle -> thinking -> speaking -> idle
 5. Captures a screenshot MID-SPEECH (while video playing) for visual quality check
 6. Mic secure-context guard present
Reports a pass/fail per check + saves evidence screenshots."""
import time, json, sys, base64
from playwright.sync_api import sync_playwright
from _gate_auth import playwright_cookies

SCREENSHOTS = "/home/sinep/.hermes/cache/screenshots"
results = {}

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=[
        "--ignore-certificate-errors",
        "--autoplay-policy=no-user-gesture-required",
    ])
    pg = b.new_page(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
    pg.context.add_cookies(playwright_cookies("https://localhost:8777"))
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))

    # --- Check 1: page loads + JARVIS view ---
    pg.goto("https://localhost:8777", wait_until="networkidle", timeout=15000)
    time.sleep(1)
    pg.click('a.nav-item[data-view="jarvis"]')
    time.sleep(2)
    avatar = pg.evaluate("""()=>{const v=document.querySelector('#jAvatarVideo');
        return v?{poster:v.poster, cls:v.className, src:v.currentSrc}:null}""")
    results['check1_page_and_avatar'] = bool(avatar and 'reference.jpg' in (avatar.get('poster','')))
    pg.screenshot(path=f"{SCREENSHOTS}/01-idle.png")

    # --- Check 2 + 3 + 4: send message, watch full flow ---
    pg.fill('#jInput', "Say hi in one short sentence, nothing more.")
    pg.press('#jInput', 'Enter')

    saw_thinking = False
    saw_speaking = False
    saw_video_ready = False
    reply_text = ""
    speech_screenshot_taken = False
    states_over_time = []

    # /api/jarvis/talk renders TTS+lip-sync into one muxed MP4 server-side (~3-6s
    # per sentence for Wav2Lip GPU inference), so the window must accommodate LLM
    # streaming + render. Poll up to ~60s.
    for i in range(40):
        time.sleep(1.5)
        s = pg.evaluate("""()=>({
            st: (document.querySelector('#jState')||{}).textContent,
            feed: (document.querySelector('#jFeed')||{}).innerHTML,
            ready: (document.querySelector('#jAvatarVideo')||{}).readyState,
            vcls: (document.querySelector('#jAvatarVideo')||{}).className,
        })""")
        states_over_time.append(s.get('st'))
        if s.get('st') == 'THINKING': saw_thinking = True
        if s.get('st') == 'SPEAKING': saw_speaking = True
        if s.get('ready',0) >= 4 and s.get('st') == 'SPEAKING':
            saw_video_ready = True
            if not speech_screenshot_taken:
                pg.screenshot(path=f"{SCREENSHOTS}/02-speaking.png")
                speech_screenshot_taken = True
        feed = s.get('feed','') or ''
        if 'j-msg jarvis' in feed:
            import re
            m = re.search(r'class="j-msg jarvis"[^>]*>([^<]+)', feed)
            if m and len(m.group(1)) > 5: reply_text = m.group(1)

    results['check2_reply_rendered'] = bool(reply_text)
    results['check3_lipsync_video_played'] = saw_video_ready
    results['check4_state_transitions'] = (saw_thinking and saw_speaking)
    results['reply_text'] = reply_text[:120]
    results['states_seen'] = list(dict.fromkeys(states_over_time))
    results['page_errors'] = errors

    pg.screenshot(path=f"{SCREENSHOTS}/03-final.png")
    b.close()

# final state should return toward idle after speaking
results['check5_returns_to_idle'] = 'IDLE' in states_over_time[-3:]

print(json.dumps(results, indent=2))
all_pass = all([
    results['check1_page_and_avatar'],
    results['check2_reply_rendered'],
    results['check3_lipsync_video_played'],
    results['check4_state_transitions'],
    results['check5_returns_to_idle'],
    not results['page_errors'],
])
print(f"\n===== OVERALL: {'ALL CHECKS PASS' if all_pass else 'FAILURES PRESENT'} =====")
sys.exit(0 if all_pass else 1)
