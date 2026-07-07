---
name: web-dashboard-apps
description: "Build self-contained real-time web dashboards and monitoring tools (FastAPI + SQLite backend, vanilla JS + Chart.js frontend) with live data, kanban boards, agent metrics, and incremental DOM updates."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [dashboard, monitoring, fastapi, vanilla-js, chartjs, realtime, websocket, sqlite, web-app, single-page]
    related_skills: [claude-design, popular-web-designs]
---

# Web Dashboard Apps

Build self-contained, real-time web dashboards and monitoring tools — the kind with live-updating stat cards, kanban boards, agent/worker fleet views, resource gauges, and Chart.js graphs. Zero external infrastructure: no Docker, no Postgres, no Redis. Just Python + SQLite + vanilla JS.

## When To Use

- User asks for a dashboard, monitoring tool, mission control, or agent OS
- User wants a kanban board with real-time task tracking
- User needs to monitor processes, agents, services, or system metrics in a browser
- User wants a single-page web app with live data updates
- The deliverable is a functional web application, not a design mockup

## When NOT To Use

- One-off design artifact / landing page → `claude-design`
- Throwaway UI variant comparison → `sketch`
- Diagrams/architecture → `excalidraw` or `architecture-diagram`
- The user needs a production-scale app with auth, multi-tenancy, k8s → build properly in their repo stack

## Architecture

```
Python backend (single process)
├── FastAPI app          — REST API + WebSocket
├── SQLite (WAL mode)    — persistent storage, no external DB
├── Background threads   — metrics collection, heartbeat monitoring
└── Static files         — index.html, app.js, style.css served by FastAPI

Vanilla JS frontend (no build step, no framework)
├── SPA router           — view switching via innerHTML
├── Polling loop         — setInterval(tick, 3000) for data refresh
├── WebSocket            — real-time push for instant updates
└── Chart.js (CDN)       — live-updating graphs
```

## Backend Pattern

### FastAPI + SQLite setup

```python
# database.py — thread-local SQLite connections with WAL
import sqlite3, threading
_local = threading.local()

def get_conn():
    if not hasattr(_local, "conn"):
        conn = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn
```

### Schema migration for existing DBs

When adding columns to a table that already exists, check and ALTER:

```python
existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(agents)").fetchall()}
for col, typedef in [("tokens_in", "INTEGER DEFAULT 0"), ("current_task", "TEXT DEFAULT ''")]:
    if col not in existing_cols:
        conn.execute(f"ALTER TABLE agents ADD COLUMN {col} {typedef}")
```

### Enriched list endpoints

Attach computed/joined fields server-side so the frontend doesn't have to:

```python
def list_agents_enriched():
    agents = db.query_all("SELECT * FROM agents ORDER BY started_at DESC")
    for a in agents:
        # join program name
        prog = db.query_one("SELECT name FROM programs WHERE id = ?", (a["program_id"],))
        a["program_name"] = prog["name"] if prog else None
        # latest metric sample
        m = db.query_one("SELECT cpu, memory_mb FROM metrics WHERE agent_id = ? ORDER BY ts DESC LIMIT 1", (a["id"],))
        a["cpu"] = m["cpu"] if m else 0.0
    return agents
```

### Background metrics thread

```python
def metrics_loop(stop_event):
    while not stop_event.is_set():
        try:
            collect_metrics()  # psutil for system + per-process
        except Exception as e:
            print(f"[metrics] error: {e}", file=sys.stderr)
        stop_event.wait(3)  # 3-second interval
```

### WebSocket broadcast manager

```python
class ConnectionManager:
    def __init__(self):
        self.active = []
    async def connect(self, ws):
        await ws.accept()
        self.active.append(ws)
    async def broadcast(self, data):
        dead = []
        for ws in self.active:
            try: await ws.send_json(data)
            except: dead.append(ws)
        for ws in dead: self.active.remove(ws)
```

### Real worker subprocesses

Spawn actual OS processes for agents/workers so metrics and heartbeats are real:

```python
proc = subprocess.Popen(
    [sys.executable, str(WORKER_SCRIPT), agent_id, name],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    env={**os.environ, "NEXUS_AGENT_ID": agent_id},
)
```

The worker script connects to the same SQLite DB, updates heartbeats, logs activity, and simulates token consumption — making the dashboard data genuinely live.

## CRITICAL: Incremental DOM Updates for Real-Time Views

**This is the single most important pattern. Getting it wrong causes the most common bug in vanilla JS dashboards.**

See `references/incremental-dom-updates.md` for the full pattern with code. Summary:

### The Bug (what NOT to do)

```javascript
// BROKEN: wipes entire DOM every 3 seconds
function render() {
  document.getElementById('content').innerHTML = viewAgents(); // destroys everything
  bindAgentCharts(); // recreates all charts from scratch
}
setInterval(tick, 3000); // tick calls render() → flicker, memory leak, broken animations
```

This destroys all Chart.js instances on every tick, causing:
- Chart flicker/jump on every refresh
- Memory leaks (orphaned Chart instances never destroyed)
- Broken CSS transitions and animations
- Lost scroll position and interaction state

### The Fix: Build Once, Patch In-Place

```javascript
let viewBuilt = false;

function renderAgentsView() {
  if (!viewBuilt) {
    // Full build — create DOM structure and charts once
    document.getElementById('content').innerHTML = buildAgentHTML(agents);
    buildAgentCharts(agents);  // create Chart.js instances
    viewBuilt = true;
  } else {
    // Incremental — patch text/values in-place, no innerHTML wipe
    updateAgentCardsInPlace(agents);
  }
}

function updateAgentCardsInPlace(agents) {
  for (const a of agents) {
    document.getElementById(`completed-${a.id}`).textContent = a.tasks_completed;
    document.getElementById(`cpu-${a.id}`).textContent = `${a.cpu.toFixed(1)}%`;
    updateAgentChart(a);  // chart.update('active') for smooth transition
  }
}
```

Key rules:
- **Never** call `innerHTML =` on a container that holds Chart.js canvases during a tick
- **Build once** on view switch, then **patch values** via `getElementById().textContent`
- **Persist chart instances** in a object keyed by agent ID; update data and call `chart.update('active')`
- **Force full rebuild** only when structure changes (new agent, deleted agent): set `viewBuilt = false`

## Frontend Layout

### Dark theme CSS variables

```css
:root {
  --bg: #0a0a0f;  --bg-2: #11111a;
  --panel: #161620;  --panel-2: #1c1c28;
  --border: #2a2a3a;  --text: #e4e4ef;
  --text-dim: #8888a0;  --text-faint: #555568;
  --accent: #7c5cff;  --accent-2: #5eead4;
  --green: #4ade80;  --yellow: #fbbf24;
  --red: #f87171;  --blue: #60a5fa;  --orange: #fb923c;
}
```

### Monospace font for technical dashboards

```css
body { font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', monospace; }
```

### Layout: sidebar + topbar + content

```
┌─────────┬──────────────────────────────┐
│ LOGO    │  Topbar (title, clock, btn)  │
│         ├──────────────────────────────┤
│ Nav     │                              │
│ items   │  Content (scrollable)        │
│         │                              │
│ Sys     │                              │
│ mini    │                              │
└─────────┴──────────────────────────────┘
```

## Common Views

1. **Dashboard** — stat cards (4-col grid), SVG resource gauges (CPU/MEM/DISK), status breakdowns, live activity feed, agent roster table
2. **Kanban** — 5-column drag-and-drop board (Backlog → Todo → In Progress → Review → Done), HTML5 DnD API
3. **Agent Fleet** — card grid with per-agent: status, current task, stats, token bars, sparkline charts, meta grid, controls
4. **Programs** — registered service catalog with run counts, durations, tags
5. **Monitor** — full-width Chart.js live graphs for system + per-agent metrics

## Token Usage Display

Dual-direction bar showing input vs output tokens:

```css
.token-bar-container { display: flex; height: 6px; border-radius: 3px; overflow: hidden; gap: 1px; }
.token-bar.in { background: var(--accent); }    /* input tokens */
.token-bar.out { background: var(--accent-2); }  /* output tokens */
```

Format helper for compact display: `1.2M`, `45.3K`, `890`.

## Kanban Drag-and-Drop (vanilla JS)

```javascript
$$('.task-card').forEach(card => {
  card.addEventListener('dragstart', () => { dragId = card.dataset.id; card.classList.add('dragging'); });
  card.addEventListener('dragend', () => card.classList.remove('dragging'));
});
$$('.col-body').forEach(col => {
  col.addEventListener('dragover', e => { e.preventDefault(); col.classList.add('drag-over'); });
  col.addEventListener('drop', async e => {
    e.preventDefault();
    await api('PATCH', `/api/tasks/${dragId}`, { status: col.dataset.col });
  });
});
```

## Serving and Launching

```python
# main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8777, log_level="info")
```

Run with: `cd project && python3 -m venv .venv && source .venv/bin/activate && pip install fastapi uvicorn[standard] psutil && python3 main.py`

## Dependencies

- `fastapi` — REST API + WebSocket
- `uvicorn[standard]` — ASGI server
- `psutil` — system and per-process metrics
- Chart.js 4.x via CDN (frontend only, no npm)
- Python stdlib: `sqlite3`, `subprocess`, `threading`, `json`, `uuid`

## SSE Streaming Chat (Agent/LLM Integration)

For dashboards that embed a chat interface to an LLM agent (JARVIS-style
assistant, copilot, etc.), use `fetch()` + `ReadableStream` to consume SSE from
your backend proxy. Do NOT use `EventSource` — it only supports GET, but SSE
chat endpoints need POST.

```javascript
async function streamChat(text) {
  const resp = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input: text }),
    signal: abortController.signal,  // AbortController for STOP button
  });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', eventName = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      if (line.startsWith('event: ')) eventName = line.slice(7).trim();
      else if (line.startsWith('data: ')) {
        handleSSE(eventName, line.slice(6));
        eventName = '';
      }
    }
  }
}
```

Handle MULTIPLE event name variants — different API versions and proxy layers
emit different names for the same concept. A robust handler covers all of them:
`text_delta`, `text`, `assistant.delta`, `content_block_delta`. Delta text may
be under `.delta.text`, `.text`, or `.delta` depending on source.

## Avatar (Two Approaches)

### Approach A: Video-Element Avatar with Neural Lip-Sync (PREFERRED for real-face avatars)

When the avatar should show the user's **real face** with **neural lip-sync**
(Wav2Lip), use a `<video>` element — NOT Three.js. The video plays **MUTED**
(face only — muted video autoplay is never blocked by any browser), and the
voice comes from a separate persistent `HTMLAudioElement` (unlocked once by
the user's mic-click gesture). Both are fetched in parallel and started at the
same instant when both are ready, so voice and face stay in sync (the lip-sync
video is generated FROM the audio, so durations match by construction).

**Why NOT a single unmuted muxed MP4**: a single `<video muted=false>` playing
TTS+video together seems simpler and IS in sync — but Chrome's autoplay policy
silently rejects unmuted play() on follow-up clips (after the user-gesture
context expires), freezing the face. Headless tests using
--autoplay-policy=no-user-gesture-required mask this for 3+ iterations. The
muted-video + separate-audio split is REQUIRED, not optional. This is the
approach used in the Nexus JARVIS v2 (adopted 2026-07-03; corrected
2026-07-05 across three iterations — see the reference file's correction
history).

Key architecture:
- **`<video id="jAvatarVideo">`** — MUTED always (idle poster + talking face).
  playsInline, object-fit:cover, poster = reference face. Fills a circular
  .avatar-wrap container.
- **`<audio>` (persistent)** — one HTMLAudioElement created on first use and
  reused for every clip. Unlocked by the user gesture; carries the TTS voice.
- **Talking state (CORRECT pattern)**: for each TTS sentence, fetch the WAV
  (/tts) and the lip-sync MP4 (/talk) in parallel; when BOTH are ready, call
  video.play() (muted) and audio.play() at the same instant. Gate the start
  on both oncanplay handlers firing.
- **WRONG pattern #1 (desync)**: play /tts audio immediately and /lipsync
  - **WRONG pattern #1 (desync)**: play /tts audio immediately and /lipsync
    video seconds later on independent timers — produces "talks, face moves,
    talks, face moves." Do NOT use independent play timers.
  - **WRONG pattern #2 (autoplay freeze — this was the 3-iteration trap)**: merge
    into one muxed MP4 and play it UNMUTED. It seems elegant ("one source, can't
    drift") and IS in perfect sync — but Chrome's autoplay policy silently rejects
    unmuted `play()` on every clip after the first (the user-gesture context
    expires between clips). Headless tests launched with
    `--autoplay-policy=no-user-gesture-required` will PASS for 3+ iterations while
    the real browser freezes on every follow-up sentence. The muted-video +
    separate-audio split exists specifically to escape this trap. Do NOT use a
    single unmuted video under any circumstance.
- **Idle state**: video has no src; poster image shows with a CSS breathing
  animation (@keyframes avatarBreathe — subtle scale 1 to 1.015 + opacity
  0.97 to 1 over 4s) so it's never frozen.
- **Reference image is size-constrained**: Wav2Lip's face detector loads the
  full frame into GPU memory. The reference face image MUST be at most 512x512
  (known-good size). Dropping in a large raw image (e.g. an 882x1444 phone
  screenshot) OOMs the GPU with RuntimeError: Image too big to run face
  detection on GPU, causing HTTP 500 on /talk, while the static gate stays
  green. Normalize the image to 512x512 before installing it.
- **Graceful fallback**: if /talk (lip-sync) is unavailable, skip the video
  and play audio-only TTS (still no desync — single source). Never fall back
  to independent parallel play timers.
- **State classes**: idle, listening, thinking, talking on the video element
  drive border glow colors via CSS.
- **Conversation loop**: a toggle enables auto-re-listen after TTS finishes —
  call startRecording() from the TTS queue completion handler.
- **Cache-bust**: use `<script src="/static/app.js?v=N">` and bump N on each
  change, or the browser serves stale code and your fixes are invisible.

See references/video-avatar-lipsync.md for the full corrected implementation
(muted-video + separate-audio playback, the coordinated-start sync gate, the
/talk endpoint, the prefetch pipeline that avoids gaps between sentences,
robust repeated-src playback so follow-up clips do not freeze, the idle reset
after speaking, the 512x512 image normalization recipe, the autoplay + desync
pitfalls with the deprecated code, and voice-gender verification via
autocorrelation pitch tracking).

### Approach B: Three.js 3D Avatar (for procedural / holographic avatars)

For a procedural/holographic avatar (not a real face), Three.js via CDN works.
**Note: Approach B was replaced by Approach A in the Nexus project (2026-07-03)**
because the spec required the user's real face with neural lip-sync.

Avatar class API: `mount(container)`, `setMode(mode)`, `setAudioLevel(amp)`,
`dispose()`. See `references/threejs-avatar-pattern.md` for full code.

- **dispose() is critical**: call `renderer.setAnimationLoop(null)`, dispose all
  geometries/materials, remove the canvas. Without this, view switches leak WebGL
  contexts and the browser goes black after ~16 switches.

## Arc Reactor / Loading Animation (Canvas 2D)

A CSS-styled `<canvas>` with `requestAnimationFrame` loop draws rotating ring
segments, tick marks, and a pulsing radial gradient core. Colors shift by mode.
~60 lines of canvas 2D, no WebGL needed — cheap and portable.

## Pitfalls

- **NEVER wipe innerHTML on a container with Chart.js canvases during a polling tick** — this is the #1 bug. Use the incremental update pattern (see references).
- **PARALLEL SESSIONS can cause destructive edits.** If another agent/session is working on the same project files, NEVER truncate or overwrite files you didn't create. Before running `head -N file > clean.js && cp clean.js file`, check if the file has grown since you last read it. Use `git init` + commit as a safety net on multi-session projects. When in doubt, `cp file file.bak` before destructive ops.
- **DISPOSE Three.js resources on view switch.** Without explicit `dispose()`, WebGL contexts accumulate. Browsers cap at ~16 active contexts — after that, new canvases go black silently.
- **createMediaElementSource can only be called ONCE per Audio element.** If you re-use Audio elements across TTS sentences, create a fresh Audio element each time rather than trying to re-analyse an existing one.
- **Always use WAL mode** for SQLite when multiple threads/processes write concurrently.
- **Thread-local DB connections** — SQLite connections are not thread-safe by default; use `threading.local()`.
- **Chart.js needs explicit `responsive: true, maintainAspectRatio: false`** and a sized parent container, or charts render at 0 height.
- **Set `check_same_thread=False`** on SQLite connections used across FastAPI's async handlers.
- **Kill worker subprocesses** when stopping agents — use `os.kill(pid, signal.SIGTERM)` and handle `ProcessLookupError`.
- **Seed demo data on first run** so the dashboard isn't empty — check `COUNT(*)` before seeding.
- **Force a full view rebuild** (`viewBuilt = false`) when structural changes happen (agent spawned/deleted), not on every data tick.
- **When migrating avatar from Three.js to video element**, update EVERY reference: remove the `<script>` CDN tag from index.html, delete avatar.js, remove the `JARVISAvatar` class, remove `.avatar.setMode()` / `.avatar.setAudioLevel()` calls, and update `verify.sh` which may have a check for `class JARVISAvatar` in avatar.js. Also remove `createMediaElementSource` analyser code — the video element doesn't need it since the server does the lip-sync.
- **AVATAR A/V: muted video + separate persistent audio (the verified-correct pattern).** Never play TTS audio and lip-sync video as two parallel independent streams (desync), AND never play a single unmuted muxed MP4 (autoplay-blocked on follow-up clips in real browsers). The only pattern that survives both real Chrome autoplay AND stays in sync: play the avatar video **MUTED** (muted autoplay is never blocked, every clip) and carry the voice via a separate persistent `HTMLAudioElement` unlocked once by the user gesture. Fetch the WAV (/tts) and the lip-sync MP4 (/talk) in parallel; when BOTH are ready, call `video.play()` (muted) + `audio.play()` at the same instant. The lip-sync video is generated FROM the audio (Wav2Lip), so durations match by construction. The old "single unmuted muxed MP4" advice was WRONG — it works in tests but freezes in production because Chrome rejects unmuted `play()` after the gesture context expires. Full code + the autoplay test-without-mask rule in `references/video-avatar-lipsync.md`. (Corrected 2026-07-05 across 4 iterations — the prior doc version taught the broken unmuted-muxed pattern; the user's frustration about repeated breakage was directly caused by following it.)
- **Wav2Lip REFERENCE FACE IMAGE must be ≤512×512.** The face detector (S3FD) loads the full frame into GPU memory; a larger raw image (e.g. an 882×1444 phone screenshot dropped in as `reference.jpg`) triggers `RuntimeError: Image too big to run face detection on GPU` → HTTP 500 on the lip-sync endpoint, and the static verify gate stays green the whole time. When replacing the avatar image, normalize it first: downscale the shorter side to 512, center-crop to 512×512, re-encode as JPEG. Recipe in `references/video-avatar-lipsync.md`. (Hit 2026-07-05.)
- **VIDEO FREEZES ON FOLLOW-UP SENTENCES.** When you assign a new `video.src` to an element that just finished a clip, the browser frequently does NOT fire `oncanplay`, so `play()` never runs — the face freezes on the last frame while the new clip's audio track keeps playing. User reports: "first reply works, follow-up questions: audio plays but the image is not moving." Three defenses in `playTalkVideo`: (1) `video.pause()` + `video.currentTime = 0` BEFORE assigning the new src; (2) listen to BOTH `onloadeddata` and `oncanplay`; (3) null out all handlers in `finish()`. Code in `references/video-avatar-lipsync.md`. (Hit 2026-07-05.)
- **MULTI-SECOND GAPS BETWEEN SENTENCES** if you fetch `/talk` sequentially (fetch→play→fetch→play). The ~5s Wav2Lip render blocks between every sentence. Fix with a prefetch pipeline: start clip N+1's fetch BEFORE playing clip N, so render happens during playback. Code in `references/video-avatar-lipsync.md`. (Reported by user 2026-07-05: "he makes a very long break between sentences, it's not fluid.")
- **AVATAR STUCK ON LAST FRAME AFTER SPEAKING (mouth open).** `setMode('idle')` only swaps CSS classes — it does NOT reset the video element, so the face sits on the last frame (often mouth open) until the next message. You MUST also call `setIdleAvatar()` (removes src, `video.load()`, snaps to poster) when the TTS queue empties. (Reported by user 2026-07-05: "the mouth stays open the whole time until the next message, this looks bad.")
- **VOICE-GENDER VERIFICATION: use autocorrelation pitch tracking, NOT FFT.** To confirm a TTS voice swap changed gender, estimate the fundamental f0 (male 85-180 Hz, female 165-255 Hz). A naive FFT peak in the 60-300 Hz band picks up FORMANTS, not f0, and misreports a male voice (~168 Hz) as ~195-208 Hz — making you wrongly conclude the swap failed. Use the autocorrelation tracker in `scripts/verify_voice_pitch.py`. (Hit 2026-07-05.)
- **SIGNAL-STEALING between background loops** — if your dashboard has a metrics thread (every ~3s) AND a watchdog/healer thread (every ~10s) on the same rows, the faster loop must NOT resolve an ambiguous state into a terminal one the slower loop needs to act on. Concretely: a dead agent must be marked `crashed` (distinct, watchable), NOT silently `idle`/`stopped` — otherwise the watchdog never sees it to heal it. Generalize: two loops on shared state need an agreed signal vocabulary. (Hit in Nexus Agent OS, 2026-07-04.) See `agent-control-plane` for the full pattern.
- **ASYNC VIEW LOADERS: add a `fetched`/`loading` re-entry guard or you get a stack overflow.** The pattern `viewX() { if(!data) { loadX(); return 'loading'; } }` where `loadX()` does `data=null; loading=true; render()` → `render()` calls `viewX()` → `!data` is still true → `loadX()` again → **Maximum call stack size exceeded**. Fix: guard the loader itself with `if (state.loading) return;` at its top, and use a separate `fetched` flag in the view (set after the async completes) so `viewX()` only kicks off the load once. Right:
  ```javascript
  const state = { data: null, loading: false, fetched: false };
  async function loadX() {
    if (state.loading) return;          // re-entry guard — the fix
    state.loading = true; state.data = null; render();
    state.data = await api('GET','/api/x');
    state.loading = false; state.fetched = true; render();
  }
  function viewX() {
    if (!state.fetched) { loadX(); return '<div class="loading">…</div>'; }
    if (state.loading)  return '<div class="loading">…</div>';
    return /* real content from state.data */;
  }
  ```
  (Hit in Nexus Agent OS v2, 2026-07-04; all 4 async views stack-overflowed until guarded. Playwright caught it as repeated `pageerror: Maximum call stack size exceeded` + `ERR_INSUFFICIENT_RESOURCES`.)
- **PLAYWRIGHT: navigate between views WITHOUT reloading the page.** A test loop that does `page.goto('/')` + click for each view can fail to find data because `domcontentloaded` + a short wait isn't enough for the SPA's nav-click handlers to wire up after a fresh load. Load the page ONCE (`wait_until:"networkidle"` + ~800ms), then click nav items in sequence with waits between. The views that "fail" in a reload-loop test but "pass" in a single-load test are working correctly — the test harness was wrong.
- **restart_agent / restart_worker must preserve the ID** — naive `stop() + spawn()` mints a NEW id and leaves the old row dangling (status='stopped', pid=NULL), breaking every reference keyed to the old id (claimed tasks, memory, UI). Update the row in place and relaunch the worker with the SAME id; increment a `restart_count` column. Full code in `agent-control-plane`.
- **When the dashboard graduates into an agent control plane** (multi-agent coordination, self-healing, isolation, approval gates, cost guardrails, scheduling) → load `agent-control-plane`. This skill covers the dashboard stack; that one covers the fleet-OS capabilities layered on top.

## Reference Files

- `references/incremental-dom-updates.md` — Full code pattern for incremental DOM updates with Chart.js lifecycle management, including the build-once-patch-in-place technique, chart persistence, and edge cases.
- `references/video-avatar-lipsync.md` — Video-element avatar with neural lip-sync: the CORRECTED single-muxed-MP4 playback pattern (one `/talk` endpoint, one unmuted `<video>` — voice and face cannot drift), the deprecated dual-track pattern explained as a pitfall, the `/talk` server endpoint, the prefetch pipeline (no gaps between sentences), robust repeated-src playback (no freeze on follow-up clips), idle reset after speaking, idle breathing CSS, conversation loop, graceful audio-only fallback, and the 512×512 reference-image normalization recipe.
- `references/threejs-avatar-pattern.md` — Complete JARVISAvatar class code (Three.js head mesh, lip-sync analyser, mode states, dispose pattern) with copy-paste implementation.
- `scripts/verify_voice_pitch.py` — Verify a TTS voice swap changed gender (male 85-180 Hz / female 165-255 Hz) via an **autocorrelation** pitch tracker. Do NOT use FFT for this — it picks formants, not f0, and misreports male voices as female. Run against a WAV or a live `/talk` endpoint.
