---
name: meeting-capture
description: "Use after a call, meeting, or voice memo to turn audio or a transcript into structured, actionable notes. Transcribes audio with the local Whisper stt toolset, then extracts a fixed record — one-paragraph summary, decisions, action items with owner and deadline, open questions — and files action items to todo/kanban and the summary to memory. Don't use for enterprise Teams meeting pipelines (use teams-meeting-pipeline)."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [meetings, transcription, stt, action-items, assistant]
    related_skills: [teams-meeting-pipeline, obsidian, project-ledger]
---

# Meeting Capture

## Overview

The general, non-enterprise flow for turning a conversation into notes nothing falls out of. It rides tooling that already works on this machine — the local Whisper `stt` toolset, `todo`/`kanban`, and `memory` (supermemory) — so it delivers value with zero wiring. Every action item leaves with an owner and a date; the summary lands where a future session can recall it.

**Core principle:** a meeting whose action items aren't captured is a meeting you'll repeat.

## When to Use

**Use for:**
- A client/discovery call, standup, or any meeting you have audio or a transcript for
- A voice memo dumping ideas or decisions you want structured
- Turning a rambling recording into decisions + next actions

**Don't use for:**
- Enterprise Teams meetings with MS-Graph integration → `teams-meeting-pipeline`

## Steps

### 1. Ingest
If you have **audio**, transcribe it with the local Whisper `stt` toolset. If you already have a **transcript**, use it directly.
**Done when:** the full text of what was said is available.

### 2. Extract into the fixed template
Fill exactly these four sections — no more:
- **Summary** — one paragraph: what the meeting was about and its outcome.
- **Decisions** — bulleted; what was actually decided (not merely discussed).
- **Action items** — each as `- [ ] <task> — @<owner> — due <date>`. Owner and date are mandatory.
- **Open questions** — unresolved threads needing a follow-up.
**Done when:** every action item has an owner and a date, or is explicitly `@unassigned` / `due TBD` so it can't silently vanish.

### 3. File it
- Push each action item to `todo` (and to `kanban` if it belongs to a tracked project).
- Store the Summary + Decisions to `memory` so future sessions can recall "what did we decide with <client>".
- If an Obsidian vault is configured, also write a dated note (`obsidian` skill).
**Done when:** actions live in todo/kanban and the summary is in memory — not just printed once in chat.

## Common Pitfalls

1. **Action items without an owner or date.** These never happen. Force both; mark unassigned explicitly.
2. **Summarizing the discussion, not the decisions.** "We talked about pricing" is useless; "Decided: $X/mo, revisit Q3" is the record.
3. **Filing nowhere.** A note only in the chat scrollback is lost by next session. Push to todo/kanban/memory.
4. **Padding.** Four sections. Resist adding a fifth.

## Verification Checklist

- [ ] Audio transcribed via local `stt` (or transcript ingested)
- [ ] Summary is one paragraph
- [ ] Decisions listed separately from discussion
- [ ] Every action item has an owner and a due date (or explicit unassigned/TBD)
- [ ] Action items pushed to todo/kanban; summary stored to memory
