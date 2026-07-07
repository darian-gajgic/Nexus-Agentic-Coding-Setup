---
name: runtime-verification
description: "Mandatory integration testing for any project with a runtime component (web UI, API client, SSE/websocket, streaming pipeline). Static gates (syntax/lint/function-presence) cannot catch contract drift. Use BEFORE declaring a runtime feature done."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [testing, integration-tests, playwright, verification, runtime, quality-gates]
    related_skills: [agentic-coding-harness, test-driven-development]
---

# Runtime Verification

Use when finishing any feature with a runtime component. The static verify gate (syntax, lint,
function-presence) is necessary but NOT sufficient — it cannot detect that a backend and frontend
disagree on event names, that an endpoint returns a different shape than the caller parses, or that
a video element's src is set before it's loaded. Those are contract-drift bugs and they are the #1
cause of "shipped broken, all gates green."

## The rule

Any feature whose correctness depends on runtime behavior MUST have an integration test that
drives the REAL flow and asserts on observable behavior, not just HTTP status codes. Run it
before calling the feature done. If no such test exists, write one first.

## How (Playwright MCP)

The Playwright MCP server exposes browser_* tools (browser_navigate, browser_snapshot,
browser_click, browser_take_screenshot, browser_type). Use them to:

1. Navigate to the running app (start it first; localhost or HTTPS).
2. Drive the real user action (click, type, submit).
3. Assert on OBSERVABLE state: did the reply render in the DOM? did the video reach readyState 4?
   did the state label transition? — NOT just "the endpoint returned 200".
4. Capture console errors and failed network requests — a clean console is part of done.

For a Python-based test script, use the `playwright` package directly (see the nexus-agent-os
verify_jarvis_e2e.py pattern: sample observable state over time, assert state transitions occurred,
screenshot evidence to ~/.hermes/cache/screenshots/).

### Match the user's REAL environment, not a sanitized one

A green from a test that runs in a sanitized environment is **worse than no test** — it
manufactures the false confidence that lets you ship "verified" fixes that fail on contact
with the real browser/server. Before trusting a pass, audit every launch flag, mock, and stub
in the test path and confirm none suppresses the restriction the bug lives in. Then re-run the
FINAL verification pass with the real restrictions ON.

Common sanitizing flags that hide entire bug classes (never set these during the final pass):
- `--autoplay-policy=no-user-gesture-required` — hides Chrome's autoplay rejection of unmuted
  media on follow-up clips (the lip-sync freeze bug).
- `--disable-web-security` — hides CORS failures.
- `--ignore-certificate-errors` — hides TLS/cert issues (fine for localhost dev, fatal if left on).
- `--use-fake-ui-for-media-stream` — bypasses the real permission prompt; fine to *start* a test
  but it hides permission-denied failures.

This is the single most expensive mistake in runtime verification: the loop goes green, you
declare done, the user runs it and it's broken, and you waste N iterations "fixing" code while
the sanitized test never could have caught the bug. See `references/browser-media-playback.md`
for the concrete autoplay-policy case.

### Gate ordering: build and dev server share the build cache (Next.js, and similar)

Most JS-framework dev servers (`next dev`, `vite`, `nuxt`) and their production build commands
(`next build`, `vite build`) write to the **same** build-output directory (`.next`, `.vite`, etc.).
Running the build command while a dev server is live is a silent corruption: the build wipes and
regenerates the on-disk chunks while the dev server still holds the old chunks in memory. The dev
server then serves stale references to chunks that no longer exist on disk, and EVERY route starts
returning HTTP 500 with a webpack error like `Cannot find module './276.js'` in the runtime. The
code is fine; the verification harness has poisoned itself.

Symptom signature (how to tell this from a real code bug):
- Routes were 200 a moment ago, then went 500 **immediately after** a `next build` step, with no
  code change in between.
- The 500's response JSON contains `Cannot find module './NNN.js'` pointing at the build-output
  webpack runtime — a missing-chunk error, not an application error.
- The **build itself exited 0** and the unit tests passed. Only the routes served by the dev
  server are broken.
- Restarting the dev server (or clearing `.next` and restarting) restores 200s.

The fix is gate **ordering**, not more debugging. When a verification run needs both a dev server
(for e2e) and a production build:

1. Clear the build cache once (`node` script that recursively `unlinkSync`/`rmdirSync` the `.next`
   dir — `rm -rf` and `node -e` are often blocked by shell security scanners; a small script file
   works).
2. Run unit tests (they don't touch the build cache).
3. Start the dev server, run the e2e tests against it.
4. **Kill the dev server and wait for the port to free** before the next step.
5. Run the production build — it now owns the build-output dir exclusively.

Equivalently: never run `next build` while `next dev` is running on the same project. If you need
both in one verification script, sequence them dev-then-build (or build-then-dev) with a clean
kill in between. (Hit 2026-07-07, webshop fix-up: a verification script ran `next build` as Gate 3
while the Gate-2 dev server was still live on :3001; the build succeeded but every route then
returned 500, and the e2e re-run "failed" — two iterations spent debugging a harness self-poisoning
before the sequencing was corrected. The fixes under test were correct all along; the build's route
table — which showed `/cart` present and `/checkout/cart` gone — was the trustworthy signal that got
ignored in favor of the corrupted dev server's 500s.)

### Playwright fill+blur fires before React commits state (stale-handler reads)

When a React input's filter/onBlur handler closes over component state (the common pattern:
`<input onChange={e => setMaxPrice(e.target.value)} onBlur={applyFilters} />` where `applyFilters`
reads `maxPrice` from state), Playwright's `fill('400')` followed immediately by `blur()` fires the
`onChange` and `onBlur` in the same microtask. React has not yet re-rendered with the new state, so
the `onBlur` handler reads the **stale, pre-typing** state value — the filter appears not to apply
(zero API requests captured, the full unfiltered list stays visible). This is NOT a bug in the
production code; it is a test-harness timing artifact.

Symptom signature:
- The test types into a field and triggers the handler, but **zero network requests** fire (inspect
  with `page.on('request', ...)`).
- A human typing the same value and clicking away (a slower, real-gesture cadence) sees the filter
  work correctly.
- Adding a `waitForTimeout(200-300)` between `fill()` and `blur()` makes the test pass — confirming
  the race.

Fix: after `fill()`, wait a tick for React to commit the state update BEFORE firing `blur()` (or
whatever triggers the stale-closure handler). Prefer a small `waitForTimeout` over
`waitForFunction` on the state, because React state isn't directly observable from the page — the
reliable signal is the request the handler fires, which you assert on next. Encapsulate this in a
helper (`setPriceFilter(testid, value)` = `fill` → `waitForTimeout(250)` → `blur` → wait for
loading-state to detach) so every field interaction in the suite gets it for free. (Hit
2026-07-07, webshop HIGH-1 regression: the price-filter e2e test `fill('400')`+`blur()` captured
zero requests and showed all 18 products; a 250ms wait before blur fixed it, and the test then
correctly discriminated the fixed code from the buggy code.)

## What to assert

- A user action produces the expected DOM change (not just a fetch fired).
- State transitions happen in the right order (idle → thinking → speaking → idle).
- Async resources load to a usable state (video readyState=4, image complete, audio playing).
- No uncaught page errors, no failed network requests during the flow.
- Multi-step flows chain correctly (streamed reply → TTS → visual render, all fire).

## Anti-patterns (do not call it done if)

- You only verified the endpoint returns 200 (it can 200 with empty/wrong body).
- You checked the function exists but never called it.
- You declared success based on "it should work" reasoning without running it.
- You couldn't run it because no browser automation was installed — INSTALL IT FIRST.
- **You edited the test/verify script this turn AND ran that same script as your evidence.** A test file you just modified is not independent verification — you may have written the bug into both the code and the assertion, or loosened the test to make it pass. When you've touched the project's canonical test (`verify.sh`, `verify_*_e2e.py`, etc.), produce a SEPARATE ad-hoc script under `/tmp` (e.g. `/tmp/hermes-verify-<topic>.py`) that asserts on the specific behavior you changed, and summarize it explicitly as ad-hoc verification — do not present the modified suite's green as the source of truth. (Hit 2026-07-05: widened a test's polling window to make it pass; the system correctly flagged the result as unverified until a standalone script was run.)
- **Your test harness uses a launch flag that DISABLES the restriction the bug lives in.** Browser-automation tools accept convenience flags that suppress real browser behavior — Playwright's `--autoplay-policy=no-user-gesture-required`, `--disable-web-security`, `--ignore-certificate-errors`. Each one hides an entire class of real-world failure. If you test video/audio playback, CORS, or TLS with the corresponding suppression flag set, your test will pass while the user's real browser silently fails. **Run the final verification pass with those flags OFF** so the test reproduces the user's actual restrictions. (Hit 2026-07-05: a JARVIS talking-head avatar froze on follow-up sentences in the real browser because Chrome's autoplay policy rejected unmuted `video.play()` after the user-gesture context expired — but 3+ iterations of headless tests "passed" because they all launched with `--autoplay-policy=no-user-gesture-required`. The fix — play the video MUTED (never blocked) and carry voice via a separate persistent `HTMLAudioElement` — only became findable once the flag was removed.)
- **You asserted on a transient state by polling for it, and the window was too short.** If a clip plays for 1-2 seconds and your poll interval is 1 second, you may sample before it starts and after it ends — never seeing the state you're asserting on. The check reports FAIL for a feature that actually works, and you burn iterations re-tuning thresholds. Prefer EVENT-based assertion (listen for `playing`/`ended`/`canplay` on the element and set a flag) over TIME-based polling (`currentTime > 0.3` sampled on a timer). When you must poll, match the interval to the event duration (sub-second for short clips) and sample at the boundary conditions, not the middle. (Hit 2026-07-05: a lip-sync clip too brief for the 1s poll passed event-based verification but failed 3 polling-based checks — the feature was working all along.)
- **You wrote the test from what the code does, not what the spec requires — so it inherits the code's gaps.** A test authored by reading the implementation and asserting on its observable behavior will pass for whatever the code happens to do, including the parts where it diverges from the requirement. This is how a spec says "confirmation page renders orderId, the list of purchased items, AND the total" and the test only checks orderId + total — because that's all the page showed, and the test was written to match the page. Write each test from the NUMBERED REQUIREMENT first, then run it against the implementation. If the test fails, either the code is wrong (fix the code) or the spec is wrong (amend the spec) — never silently narrow the test to match the code. Symptom: every test passes, the feature is incomplete, and the gap is invisible until a human or an independent reviewer reads the spec. (Hit 2026-07-06, webshop spec-vs-implementation review: R26's e2e test asserted orderId + total only; the spec also required the purchased-items list, which the confirmation page never rendered. The test was green. An independent fresh-context review caught it.)
- **Unit mismatch at a UI↔API (or any cross-layer) boundary, masked by a contract-level test that bypasses the UI.** When a UI label implies one unit ("Min Price ($)" → dollars) but the value crosses a layer boundary into a comparator that expects another unit (`price_cents >= ?` → cents), the feature is silently broken for every human user — AND every test that calls the lower layer directly with the correct unit passes. `?min_price=20000` in a curl/API test works perfectly; a human typing `200` in the dollar-labeled box gets garbage. Always trace at least one input from the UI label through every layer transformation to the final comparison, and write at least one end-to-end test that types into the real UI field and asserts on the real filtered result. The placeholder text is a tell: if the placeholder says `9999` and the cheapest real item is 14999 in the wire unit, the filter's own example value returns zero results. (Hit 2026-07-06, webshop: price filter labeled `$` with placeholder `9999`, sent raw to a cents API. R6's API-direct test with `min_price=20000` passed; the UI filter was unusable. Cheapest product 14999¢; placeholder `9999` → `price_cents <= 9999` → empty catalogue.)
- **Literal contract drift: route paths, testids, field names, or CSS selectors that the spec names verbatim were moved/renamed and the test followed.** A spec that says "the cart page at `/cart` with `data-testid=\"cart-page\"`" is naming a LITERAL contract, not suggesting a layout. When the implementation moves the page to `/checkout/cart` and the test navigates there too, every test passes — but a verifier running the spec's literal command (`navigate to /cart`) hits a 404. Treat spec-named routes, testids, URL paths, query-param names, and selector strings as exact-match contracts. When you must diverge (better architecture, naming), AMEND THE SPEC first; do not move the contract and move the test to follow. A quick check: grep the spec for quoted paths / testid literals / `data-testid=` / URL patterns, and confirm each one exists verbatim in the running app AND is what the test targets. (Hit 2026-07-06, webshop: R21 named `/cart` + `cart-page`; code shipped `/checkout/cart` + `cart-item`; e2e test targeted the moved route and passed; the spec's R21 verification command would 404.)

## When you can't run the real runtime (mock-based logic verification)

Sometimes the real runtime can't be exercised in-session — a GPU-resident ML model, audio
hardware, a database cluster, a cloud API requiring credentials. In that case, the branching
and control-flow LOGIC you changed is still testable in isolation by injecting fake objects
that record their call arguments. This proves your conditionals, state transitions, and
parameter passing are correct — but it does NOT prove the real contract holds (the native
call accepts the parameter, the audio format matches, etc.).

Always label this explicitly as **ad-hoc logic verification** and flag that the user must
still run the real end-to-end flow. See `references/mock-based-logic-verification.md` for
the full technique, including the mid-call state re-check pattern for mutable session state
changed by another thread during a non-cancellable blocking call.

### Serverless single-file HTML (browser games, canvas widgets, standalone tools)

A distinct class: the deliverable is one `.html` file with inline CSS+JS, no server, no
build step, no `node_modules`. The entire runtime IS the browser, so you CAN exercise it —
navigate to the `file://` path with `browser_navigate`, dispatch synthetic events on canvas
elements via `browser_console(expression=...)`, mutate state objects directly to test
rendering, and use `browser_vision` to confirm what actually painted. No Playwright Python
harness needed. See `references/serverless-single-file-html-verification.md` for the full
4-layer pipeline (static → load → interact → visual).

## Install prerequisites

If Playwright isn't available: `pip install playwright && playwright install chromium`. On headless/
Wayland, Playwright works without a display (unlike pixel-based screenshot tools). For pure browser
testing this is preferred over computer_use/cua-driver which breaks on Wayland compositors.

## Remember

Static gate green + runtime test green = done. Static gate green alone = not done. This is the
lesson from a real production failure where the #1 feature was silently broken and every static
check passed.

## References

- `references/mock-based-logic-verification.md` — when the real runtime can't run in-session (GPU
  models, audio hardware, cloud APIs): inject fakes that record call args, assert on branching logic,
  and flag the result as ad-hoc logic verification (not contract proof). Includes the mid-call
  state re-check pattern for non-cancellable blocking calls. Read when you changed control-flow
  logic in a service whose real dependencies can't be loaded.
- `references/browser-media-playback.md` — Chrome autoplay policy, the muted-video + separate-audio
  pattern for lip-sync/avatars, and how to test WITHOUT the `--autoplay-policy` flag that masks the
  bug. Read this before testing any video/audio/voice feature.
- `references/server-log-diagnosis.md` — when a bug reproduces for the user but NOT in your test
  harness, the production server logs reveal the real failing request. Covers intermittent 500s
  under concurrency, the double-work trap (calling a combined endpoint AND its components in
  parallel), and the idle-unload reload test. Read this before theorizing about an intermittent
  or load-dependent bug.
- `references/serverless-single-file-html-verification.md` — when the deliverable is a standalone
  `.html` file with no server, no build step, no backend (browser games, canvas widgets,
  interactive tools). 4-layer pipeline: static regex checks → `browser_navigate` to `file://` →
  `browser_console(expression=...)` for synthetic event dispatch and direct state mutation →
  `browser_vision` for visual confirmation. Read this before verifying any zero-dependency HTML
  deliverable.
- `references/stripe-webhook-testing-without-live-keys.md` — testing Stripe Checkout + webhook
  money-path logic (signature verify, idempotency, stock decrement, oversold rollback) WITHOUT
  live keys or the Stripe CLI. Mock `sessions.create` at the module boundary but use the REAL
  SDK's `generateTestHeaderString` + `constructEvent` to exercise HMAC verification locally.
  Includes the double-submit convergence mock pattern. Read this before testing any payment
  integration.
- `references/green-tests-hidden-bugs-spec-vs-code.md` — three bug classes where a full suite
  was green but the feature was wrong: test written from code-behavior not spec-requirement
  (missing confirmation items), unit mismatch at a UI↔API boundary masked by an API-direct
  test (dollar-labeled price filter feeding a cents API), and spec-named literals (route +
  testid) silently moved with the test following. Read this before signing off on any
  spec-driven build, or when every test passes but the feature "feels" incomplete.
