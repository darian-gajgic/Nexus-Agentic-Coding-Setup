# SSE Event Reference — Hermes API Server v0.18.0

Verified by live-streaming actual chat turns against the API server.

## Complete event flow for a single turn

Request: `POST /api/sessions/{id}/chat/stream` with `{"input": "..."}`

```
event: run.started
data: {"user_message": {"role": "user", "content": "..."}, "session_id": "...", "run_id": "run_...", "seq": 1, "ts": ...}

event: message.started
data: {"message": {"id": "msg_...", "role": "assistant"}, "session_id": "...", "run_id": "run_...", "seq": 2, "ts": ...}

event: assistant.delta
data: {"message_id": "msg_...", "delta": "Hello", "session_id": "...", "run_id": "run_...", "seq": 3, "ts": ...}

event: assistant.delta
data: {"message_id": "msg_...", "delta": " to", ...}

event: assistant.delta
data: {"message_id": "msg_...", "delta": " you!", ...}

event: tool.progress
data: {"message_id": "msg_...", "tool_name": "_thinking", "delta": "Hello to you!", ...}

event: assistant.completed
data: {"session_id": "...", "message_id": "msg_...", "content": "Hello to you!", "completed": true, "partial": false, "interrupted": false, "run_id": "run_...", "seq": 8, "ts": ...}

event: run.completed
data: {"session_id": "...", "message_id": "msg_...", "completed": true, "messages": [{"role": "assistant", "content": "...", "finish_reason": "stop", "reasoning": null}], "usage": {"input_tokens": 15031, "output_tokens": 6, "total_tokens": 15037}, "run_id": "run_...", "seq": 9, "ts": ...}

event: done
data: {"session_id": "...", "run_id": "run_...", "seq": 10, "ts": ...}
```

## Events with tools involved

When the agent calls tools (web_search, terminal, etc.), additional events
appear between `assistant.delta` chunks:

```
event: tool.started
data: {"tool_name": "web_search", "preview": "...", ...}

event: tool.progress
data: {"tool_name": "web_search", "delta": "...", ...}

event: tool.completed
data: {"tool_name": "web_search", ...}
```

### Internal tools (filter these)

Events with `tool_name` starting with `_` are internal reasoning steps:
- `_thinking` — the agent's chain-of-thought
- Other `_*` prefixed tools

Filter these out of user-facing activity feeds. They show up as
`tool.progress` events with a `delta` field.

## Event field glossary

| Field | Present in | Type | Meaning |
|-------|-----------|------|---------|
| `run_id` | most events | string | Unique ID for this turn. Use for stop/approval actions. |
| `session_id` | most events | string | The session this turn belongs to. |
| `message_id` | assistant.* events | string | The message being built. |
| `delta` | assistant.delta, tool.progress | string | Incremental text chunk — append to response. |
| `content` | assistant.completed | string | Full final response text. |
| `seq` | all events | int | Monotonic sequence number within the stream. |
| `ts` | all events | float | Unix timestamp. |
| `usage` | run.completed | object | `{input_tokens, output_tokens, total_tokens}`. |
| `interrupted` | assistant.completed | bool | True if the run was stopped mid-response. |

## Timing characteristics (observed)

- **Simple query** (no tools): ~7-10 seconds from POST to `run.completed`
- **With tools** (web search, etc.): 15-60+ seconds depending on tool calls
- **First token latency**: ~5-8 seconds (model warmup + reasoning)
- **Streaming granularity**: tokens arrive in 1-4 word chunks

Set client read timeouts to **240 seconds minimum** to avoid cutting off
tool-heavy turns.

## Session lifecycle

- Sessions persist across server restarts (stored in SQLite at `~/.hermes/state.db`)
- A session accumulates context — every message you send is added to its history
- There is no explicit "close session" — sessions just stop receiving new messages
- To get history: `GET /api/sessions/{id}/messages?limit=50`
- To start fresh: `POST /api/sessions` with a new title
- If the DB is reset, old session IDs return 404 — recreate
