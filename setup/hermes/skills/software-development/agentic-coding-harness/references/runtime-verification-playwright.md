# Runtime verification with Playwright (Layer-2 gate)

The concrete pattern that caught the "Jarvis doesn't respond" bug (2026-07-03) — a backend↔frontend
SSE event-name mismatch that passed every static gate. Static gates check that code is well-formed;
this checks that the feature actually WORKS end-to-end.

## Why this exists

A static gate (syntax + function-presence + asset-refs) will pass on code where:
- The backend emits `event: assistant.delta` but the frontend handles `text_delta`.
- An async `video.play()` fires before `loadeddata` and silently rejects.
- An endpoint returns HTTP 200 with an empty/wrong-shaped body.
- A permission/API (getUserMedia, autoplay) is unavailable in the real context.

None of these are syntax errors. All of them break the feature. The only way to catch them is to
run the real path and assert on observable behavior.

## Setup (one-time per project)

```bash
cd <project>
.venv/bin/pip install playwright
.venv/bin/playwright install chromium   # ~115MB, one-time
```

If a headless Chrome is already present (e.g. `~/.agent-browser/browsers/chrome-*/chrome`), you can
point Playwright at it with `executable_path=` — but the bundled chromium-headless-shell is simpler.

## The diagnostic script pattern

Save as `scripts/diag_<feature>.py`. Run with `.venv/bin/python scripts/diag_<feature>.py`.
The key is to capture console messages, page errors, and failed network requests, AND assert on
the DOM/network state after triggering the action.

```python
import time, json
from playwright.sync_api import sync_playwright

console_msgs, page_errors, failed_reqs, api_calls = [], [], [], []

with sync_playwright() as p:
    # --ignore-certificate-errors + ignore_https_errors for self-signed HTTPS (local dev)
    b = p.chromium.launch(headless=True, args=[
        "--ignore-certificate-errors",
        "--autoplay-policy=no-user-gesture-required",  # so video.play() works headless
    ])
    pg = b.new_page(ignore_https_errors=True, viewport={"width": 1280, "height": 900})

    pg.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.on("requestfailed", lambda r: failed_reqs.append(f"{r.method} {r.url} :: {r.failure}"))
    pg.on("response", lambda r: api_calls.append(f"{r.status} {r.url}")
          if "/api/" in r.url else None)

    pg.goto("https://localhost:PORT", wait_until="networkidle", timeout=15000)
    time.sleep(2)
    # ...trigger the feature: fill input, click button, etc.
    pg.fill("#input", "test"); pg.press("#input", "Enter")
    time.sleep(12)  # let async streams complete

    # ASSERT on observable state, not on absence-of-errors:
    state = pg.evaluate("""() => ({
        feed: document.querySelector('#feed')?.innerHTML,
        videoReady: document.querySelector('video')?.readyState,  # 4 = HAVE_ENOUGH_DATA
        stateLabel: document.querySelector('#state')?.textContent,
    })""")
    pg.screenshot(path="/tmp/feature-diag.png")
    b.close()

# The assertions that catch contract bugs:
assert page_errors == [], f"JS errors: {page_errors}"
assert "<div class='reply'>" in state["feed"], "reply did not render"
assert state["videoReady"] == 4, "video never reached playable state"
assert any("POST" in c and "/api/speak" in c and "200" in c for c in api_calls), "speak endpoint not hit"
```

## What each assertion catches

- **`page_errors == []`** — uncaught JS exceptions (the `assistant.delta` mismatch threw nothing; the
  handler just silently didn't match. So this alone is NOT enough — that's why the DOM assertion matters.)
- **DOM content assertion** — the reply/feed actually rendered text. This is what caught the SSE bug:
  the feed was empty despite no errors.
- **`videoReady == 4`** — an async video element actually loaded and could play (catches the
  play-before-loaded race and autoplay-policy failures).
- **network assertion** — the expected endpoint was hit with the expected status (catches "returned
  200 but empty body" when paired with the DOM assertion).

## Driving the browser WITHOUT Playwright (quick screenshot only)

For a one-off "what does the page look like right now" when Playwright isn't installed, a headless
Chrome screenshot works (but can't assert on state):

```bash
~/.agent-browser/browsers/chrome-*/chrome --headless=new --no-sandbox --disable-gpu \
  --window-size=1280,900 --virtual-time-budget=5000 \
  --screenshot=/tmp/page.png http://localhost:PORT
```

This is weaker than the Playwright pattern (no console capture, no interaction, no assertions) but
useful for a fast visual check. Prefer the Playwright script for any "is this feature done" verdict.

## Capturing the raw backend contract (the ground truth)

When a runtime test fails, confirm whether it's a frontend-handling bug or a backend-contract bug by
capturing the raw wire format:

```bash
curl -s -N -X POST http://localhost:PORT/api/stream \
  -H "Content-Type: application/json" -d '{"input":"test"}' | head -20
```

This prints the raw SSE (or whatever protocol). If the event names here don't match what the frontend
switches on, that's the bug — fix the handler to match the real event names. This step is what
pinpointed `assistant.delta` vs `text_delta`.

## Rule of thumb

If a feature has a UI, an API contract, an async stream, or a permission/autoplay dependency, a
static-green gate is not evidence it works. Write the 20-line Playwright script. The first bug it
catches pays for the setup forever.
