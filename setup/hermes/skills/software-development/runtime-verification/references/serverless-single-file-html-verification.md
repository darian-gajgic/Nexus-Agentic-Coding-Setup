# Verifying serverless single-file HTML deliverables

## When this applies

The deliverable is a single self-contained `.html` file with inline CSS + JS — no server,
no build step, no `node_modules`, no network calls. Browser games, interactive widgets,
canvas visualizations, standalone tools. The user will open it via `file://` or double-click.
There is no canonical `verify.sh`, no backend to curl, no Playwright Python harness.

This is a distinct class from server-backed web apps (use the standard Playwright section in
the main SKILL.md) and from mock-based logic verification (no backend to mock — the entire
runtime IS the browser).

## The verification pipeline (4 layers)

```
STATIC (node --check + regex grep)
   ↓
LOAD   (browser_navigate to file:// path)
   ↓
INTERACT (browser_console expression= to inject state / dispatch events)
   ↓
VISUAL  (browser_vision to confirm what's actually painted)
```

Each layer catches a different bug class. Skipping any layer leaves a gap.

### Layer 1 — Static checks (fast, catches structural defects)

Write a throwaway Node script at `/tmp/hermes-verify-<topic>.js` that reads the HTML file
and runs regex checks. Run it with `node`. This is NOT the project's canonical suite — it's
an ad-hoc script you write fresh, matching the acceptance criteria.

```javascript
const fs = require('fs');
const html = fs.readFileSync('/path/to/index.html', 'utf8');
let pass = 0, fail = 0;
function check(name, cond, detail) {
  const ok = !!cond;
  console.log(`${ok ? '✅ PASS' : '❌ FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
  ok ? pass++ : fail++;
}

// Self-contained checks
const externalScripts = (html.match(/<script\s+src=/gi) || []).length;
check('A1: no external <script src>', externalScripts === 0, `found ${externalScripts}`);
const networkCalls = (html.match(/fetch\s*\(|XMLHttpRequest|WebSocket/gi) || []).length;
check('A1: no network calls', networkCalls === 0);

// Feature-presence checks (does the code contain the required functions?)
check('draw function exists', /function\s+draw/.test(html));
check('collision function exists', /function\s+checkCollisions/.test(html));

// JS syntax check
const jsMatch = html.match(/<script>([\s\S]*?)<\/script>/);
fs.writeFileSync('/tmp/hermes-verify-extract.js', jsMatch[1]);
// then: node --check /tmp/hermes-verify-extract.js
```

**Pitfall — regex false negatives on proximity checks.** A check like
`/doFlap[\s\S]{0,100}emitFire/` will FAIL if there's more than 100 chars of code between
the two (e.g. a `playFlapSound()` call in between). When a proximity check fails, inspect
the actual line numbers with `grep -n` before concluding the code is wrong — widen the
char budget in the regex rather than "fixing" non-existent code bugs.

### Layer 2 — Load verification (catches runtime/parse errors)

```python
# Navigate directly to the file path — no server needed
browser_navigate(url="file:///home/sinep/.../index.html")
```

Then immediately check console:
```python
browser_console()  # expect: total_errors: 0, total_messages: 0
```

If there are JS errors on load, they appear here. A clean console on load means the code
parsed and `init()`/`DOMContentLoaded` ran without throwing.

### Layer 3 — Interaction verification (catches logic/state-transition bugs)

This is where serverless HTML verification gets powerful. Use `browser_console(expression=...)`
to **directly manipulate game state and dispatch synthetic events**, bypassing the need for
precise pixel-clicking:

```javascript
// Start the game from a start screen
const c = document.getElementById('game');
c.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true, cancelable:true}));
return STATE.mode;  // → "playing"

// Flap on a schedule to test gameplay
const flap = () => c.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true, cancelable:true}));
setTimeout(flap, 400); setTimeout(flap, 900);

// Force game state to test display logic
STATE.score = 5;
STATE.mode = 'playing';
return STATE.mode + ' score=' + STATE.score;

// Verify restart works
STATE.mode = 'gameover';
STATE.gameOverT = 0;
c.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true, cancelable:true}));
return STATE.mode;  // → "playing" if restart logic works
```

**Key technique — synthetic event dispatch.** DOM elements don't always have clickable refs
in the accessibility snapshot (a `<canvas>` has no child elements). Dispatch `PointerEvent`
directly on the canvas element instead of using `browser_click`. This is more reliable for
canvas-based games and drawing tools.

**Key technique — direct state mutation.** Rather than trying to play perfectly (which an
agent can't do for most games), set `STATE.score`, `STATE.mode`, etc. directly to verify
that the RENDERING and STATE TRANSITIONS work correctly. E.g. set score=5 to verify the
score display renders the number, set mode='gameover' to verify the game-over screen.

**Browser security sandbox note.** `browser_console(expression=...)` is blocked from
accessing `localStorage` and other sensitive browser APIs by a sandbox guard. This is
correct behavior — verify localStorage logic via the static layer (regex) and via the
game-over screen showing "Best: N" after a scored round, not by calling localStorage directly.

### Layer 4 — Visual verification (catches "it renders but looks wrong")

```python
browser_vision(question="Does the start screen show a title, instructions, best score, and a dragon sprite?")
browser_vision(question="Is there a large score number displayed at top center during gameplay?")
```

The vision layer catches what layers 1-3 cannot:
- Colors/gradient are visible and correct
- Sprites actually render (a function existing in code ≠ pixels being drawn)
- Text is legible and not overlapping
- UI overlays appear at the right times

**Frame the question specifically.** "Describe what you see" is weaker than "Is the score
number '5' displayed at top center during gameplay?"

## Pitfalls

1. **Don't claim runtime verification based on static checks alone.** A 40/40 static pass
   means the code contains the right strings and parses cleanly — it does NOT mean the game
   renders or plays. Always run at least layers 1-3.

2. **Synthetic events must use the right type.** A canvas game listening for `pointerdown`
   won't respond to `browser_click` (which tries to find a DOM ref to click). Dispatch the
   exact event type the code listens for.

3. **Tab-switch dt spikes are invisible to a single screenshot.** If you're testing a game
   loop, verify the dt-clamp (`MAX_DT`) exists statically — you can't easily simulate a
   5-second tab switch in the browser tool.

4. **Score persistence across reloads needs a real reload.** If you want to verify
   localStorage, `browser_navigate` to the file again and check that `STATE.best` loads
   the previously saved value. (May be blocked by the sandbox — document the limitation.)

## Session provenance

- **2026-07-06**: Flappy Dragon — single-file HTML canvas game, 15 acceptance criteria.
  Verified with all 4 layers: 40/40 static checks, zero console errors on load, synthetic
  pointer events to drive start/play/gameover/restart, direct `STATE.score` mutation to
  verify score display, `browser_vision` to confirm visual rendering of start screen,
  gameplay, and game-over screen. One regex false negative (proximity check with too-tight
  char budget) caught and fixed in the ad-hoc script, not in the game code.
