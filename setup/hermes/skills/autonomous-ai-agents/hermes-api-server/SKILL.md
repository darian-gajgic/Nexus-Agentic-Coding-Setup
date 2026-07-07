---
name: hermes-api-server
description: "Enable the Hermes Agent API server and build custom integrations (web UIs, dashboards, voice assistants) on top of its Sessions API with SSE streaming."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, api-server, integration, sse, web-ui, dashboard, rest-api]
    related_skills: [hermes-agent]
---

# Hermes API Server Integration

The Hermes Agent API Server is a REST + SSE endpoint that exposes the full
agent (sessions, streaming chat, tool events, approvals) to external
applications. It lets you build custom UIs — web dashboards, voice
assistants, IDE panels, mobile apps — that drive a real Hermes agent with
persistent memory, tools, and skills.

Load this skill when you need to:
- Enable and configure the Hermes API server
- Build a custom web UI or dashboard that talks to Hermes
- Stream agent responses (SSE) into a browser or app
- Manage sessions programmatically
- Proxy Hermes events through your own backend

For general Hermes setup, configuration, and CLI usage, load `hermes-agent`.

## Enabling the API Server

The API server runs as part of the gateway process. It is **off by default**.

```bash
# Method 1: config + env (recommended for scripting)
hermes config set api_server.enabled true

# Generate an API key and enable in one shot:
cat >> ~/.hermes/.env <<EOF
API_SERVER_ENABLED=true
API_SERVER_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
EOF

# Install and start the gateway service (runs the API server)
hermes gateway install
hermes gateway start

# Verify it's up
curl -s http://127.0.0.1:8642/health
# {"status": "ok", "platform": "hermes-agent", "version": "0.18.0"}
```

The API server binds to **127.0.0.1:8642** by default (loopback only —
LAN exposure is your responsibility via reverse proxy).

### Auth

Every request needs `Authorization: Bearer $API_SERVER_KEY`. The key lives
in `~/.hermes/.env`. When building external apps, load that file to get the
key — don't hardcode it.

### Checking status

```bash
hermes gateway status    # shows systemd service status
curl -s http://127.0.0.1:8642/health -H "Authorization: Bearer $API_SERVER_KEY"
```

## API Endpoints (verified against v0.18.0)

All return JSON unless noted. All need the Bearer token.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check (no token required) |
| GET | `/api/sessions?limit=N` | List recent sessions → `{"data": [...]}` |
| POST | `/api/sessions` | Create session: `{"title": "name"}` → `{"session": {"id": ...}}` |
| GET | `/api/sessions/{id}` | Get session details (404 if deleted) |
| GET | `/api/sessions/{id}/messages?limit=N` | Message history |
| POST | `/api/sessions/{id}/chat/stream` | **SSE streaming chat** (see below) |

### What does NOT exist (as of v0.18.0)

- `/api/skills` — no skills endpoint. Use `hermes skills list` CLI.
- `/v1/runs/{id}/stop` — run stop endpoint may not exist. To stop a run,
  abort the SSE connection from the client side.
- `/openapi.json`, `/docs` — no OpenAPI/Swagger docs served.

## SSE Streaming Chat Protocol

`POST /api/sessions/{id}/chat/stream` with body `{"input": "text"}` and
header `Accept: text/event-stream` returns a Server-Sent Events stream.

### Event sequence

```
event: run.started          → {"run_id": "run_...", "session_id": ...}
event: message.started      → {"message": {"id": "msg_...", "role": "assistant"}}
event: assistant.delta      → {"delta": "Hello"}              ← repeated, streamed text
event: tool.started         → {"tool_name": "web_search"}     ← agent is calling a tool
event: tool.progress        → {"tool_name": "_thinking", "delta": "..."}  ← internal reasoning
event: tool.completed       → {"tool_name": "web_search"}
event: assistant.completed  → {"content": "full response", "interrupted": false}
event: run.completed        → {"usage": {"input_tokens": N, "output_tokens": N, "total_tokens": N}}
event: done                 → stream closes
```

**Key events for UI:**
- `assistant.delta` — stream text token-by-token into a chat bubble
- `tool.started` — show "agent is working" indicator, display tool name
- `assistant.completed` — finalize the response text
- `run.completed` — get token usage for cost/display tracking
- Events with `tool_name` starting with `_` (e.g. `_thinking`) are internal —
  filter them out of the main activity feed

### Error events

If the session was deleted or the input fails, you get:
```
event: error
data: {"error": "..."}
```
On HTTP 404 for a session, recreate it with `POST /api/sessions`.

## Session Management Pattern

Sessions are persistent — they survive restarts. For a custom UI, store the
session ID and reuse it across conversations:

```python
import json
from pathlib import Path

STATE_FILE = Path("session_state.json")

def get_or_create_session(api_base, headers):
    """Get cached session ID or create a new one."""
    state = {}
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
    sid = state.get("session_id")
    if sid:
        # Verify it still exists
        r = requests.get(f"{api_base}/api/sessions/{sid}", headers=headers, timeout=5)
        if r.status_code == 200:
            return sid
    # Create new
    r = requests.post(f"{api_base}/api/sessions", headers=headers,
                      json={"title": "My App"}, timeout=10)
    r.raise_for_status()
    sid = (r.json().get("session") or r.json()).get("id")
    STATE_FILE.write_text(json.dumps({"session_id": sid}))
    return sid
```

If the Hermes DB is reset, the old session ID returns 404. Handle this by
forcing a new session creation (delete the cached ID and retry).

## SSE Proxy Pattern (FastAPI → Browser)

Browsers can't use `EventSource` for POST requests. The pattern for a custom
web UI: your backend proxies the Hermes SSE stream, and the browser reads it
via `fetch()` + `ReadableStream`.

### Backend (FastAPI)

```python
from fastapi.responses import StreamingResponse
import httpx

@app.post("/api/chat/stream")
async def chat_stream(body: dict):
    session_id = await get_or_create_session()
    async def event_generator():
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{HERMES_API_BASE}/api/sessions/{session_id}/chat/stream",
                headers={**headers, "Accept": "text/event-stream"},
                json={"input": body["input"]},
                timeout=httpx.Timeout(240.0, connect=10.0),
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("event: ") or line.startswith("data: "):
                        yield line + "\n"
                    if line == "" and buffer:
                        yield "\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

### Frontend (browser JS)

```javascript
async function streamChat(text) {
    const resp = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({input: text}),
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let eventName = '';

    while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true});
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep partial line

        for (const line of lines) {
            if (line.startsWith('event: ')) {
                eventName = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
                const data = JSON.parse(line.slice(6));
                handleEvent(eventName, data);
                eventName = '';
            }
        }
    }
}
```

To stop a run mid-stream, use `AbortController`:

```javascript
const controller = new AbortController();
const resp = await fetch('/api/chat/stream', {..., signal: controller.signal});
// User clicks STOP:
controller.abort();
```

## Loading ~/.hermes/.env from External Apps

External applications need the `API_SERVER_KEY` to authenticate. Load it
from Hermes' .env file at startup:

```python
def load_hermes_env():
    for env_path in [os.path.expanduser("~/.hermes/.env"), ".env"]:
        if not os.path.exists(env_path):
            continue
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
```

Use `setdefault` so the caller's environment can override.

## Pitfalls

- **Gateway must be running.** The API server is part of the gateway process,
  not a standalone server. `hermes gateway install && hermes gateway start`.
- **Session 404 after DB reset.** If Hermes' state.db is wiped or the session
  is deleted, the old session ID returns 404. Always handle this by recreating.
- **No skills endpoint.** Don't waste time probing for `/api/skills`. Run
  `hermes skills list` as a subprocess and parse the output if you need skills
  in your UI.
- **SSE line encoding.** Set `resp.encoding = "utf-8"` when using `requests`
  for SSE — it defaults to latin-1 without a charset header, causing mojibake.
  With `httpx`, `aiter_lines()` handles encoding correctly.
- **Connection leaks.** Always close SSE responses in a `finally` block or via
  context manager. Leaked FDs will accumulate and crash the server.
- **Long timeouts.** Agent turns with tools can take 30-60+ seconds. Set
  generous read timeouts (240s) on the SSE connection.
- **Gateway dies on SSH logout.** Enable linger: `sudo loginctl enable-linger $USER`
  (or `hermes gateway install` does this automatically on systemd).
- **Voice pipeline needs python-multipart.** If adding mic/STT endpoints that
  use `UploadFile`, install `python-multipart` first, or the server crashes on
  startup with `RuntimeError: Form data requires "python-multipart"`.
- **GPU STT/TTS on Blackwell GPUs.** Running faster-whisper (ctranslate2, CUDA
  12) and Piper (onnxruntime-gpu, CUDA 13) in the same process requires careful
  library path setup — see `references/cuda-mixed-version.md`.
- **Orca screen reader on Linux/GNOME.** If `computer_use` is invoked during
  a session, it can trigger GNOME's Orca to narrate everything. See
  `references/linux-orca-pitfall.md`.

## Voice Pipeline Integration

To add real voice conversation (mic → STT → Hermes chat → TTS → avatar) to a
Hermes-powered UI, see `references/voice-pipeline.md` for the full architecture:
GPU-accelerated STT (faster-whisper) and TTS (Piper), sentence-buffered streaming
TTS playback, mic capture, and avatar animation state machine. For 3D avatars
with real lip-sync, see `web-dashboard-apps/references/threejs-avatar-pattern.md`.

## Verification

To verify the API server is working end-to-end:

```bash
API_KEY=$(grep API_SERVER_KEY ~/.hermes/.env | cut -d= -f2)

# Health check
curl -s http://127.0.0.1:8642/health -H "Authorization: Bearer $API_KEY"

# Create a session
SID=$(curl -s -X POST http://127.0.0.1:8642/api/sessions \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"title":"test"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['session']['id'])")

# Stream a chat turn (first 20 lines)
curl -sN http://127.0.0.1:8642/api/sessions/$SID/chat/stream \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"input":"Say hello"}' | head -20
```

## Reference: External Projects

- **eadmin2/jarvis_ai** — Iron-Man voice assistant + HUD built on the Hermes
  API Server. Voice pipeline (Whisper STT + ElevenLabs TTS) + holographic
  browser HUD. Good reference for the SSE proxy + session management pattern.
  The `server.py` HermesAPI class is a clean client implementation.
- **OpenJarvis** — Stanford local-first AI framework. Separate project, not
  Hermes-specific, but can import Hermes skills.
