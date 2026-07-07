---
name: project-ledger
description: "Use when a project will span multiple sessions or outlive the context window — maintain durable project state on the kanban board plus a re-groundable LEDGER.md spine so state survives compression, session reset, and goal changes. Records objective, acceptance criteria, decisions, open threads, and next action, and rehydrates them at session start. Don't use for in-session throwaway task lists (use the todo toolset)."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [durable-state, kanban, memory, continuity, manager]
    related_skills: [project-orchestration, goal-drift-discipline, parallel-delegated-build]
---

# Project Ledger

## Overview

Context is volatile: compression fires at `0.5` with `protect_last_n: 20`, and a session reset can wipe the working window. A long project whose spine lives only in context loses that spine mid-flight. This skill externalizes the spine to a **file** — a `LEDGER.md` plus a durable kanban board — so the file, not the context window, is the source of truth. Rehydrate from it on entry; write to it before you move on.

**Core principle:** if losing the context window would lose the project, the project isn't written down yet.

## When to Use

**Use for:**
- Any project spanning multiple sessions or likely to outlive one context window
- Big complex builds/deliverables where losing the thread is expensive
- Work handed back and forth with a subagent fleet (`project-orchestration`)

**Don't use for:**
- In-session throwaway task lists → the `todo` toolset
- A one-shot task finished this turn

## The Ledger

Keep one `LEDGER.md` per project (in the workspace, e.g. `.hermes/<project>/LEDGER.md`) with these fixed sections:

```
# <Project> — Ledger
## Objective            (one sentence: what "done" means)
## Acceptance Criteria  (checkable conditions)
## Decisions Log        (dated: what was decided and why)
## Open Threads         (unresolved questions/blockers)
## Next Action          (the single next concrete step)
## Done                 (completed milestones)
```

Pair it with a durable kanban board for task-level state (kanban is SQLite-backed and survives sessions; the ledger holds the narrative spine that todo/kanban can't).

## Rules

### 1. Write the delta before continuing
After every meaningful step — a decision, a completed subtask, a new blocker — update the relevant ledger section **before** starting the next step.
**Done when:** the ledger reflects the latest state; nothing important lives only in the current context.

### 2. Rehydrate on entry
At session start, or immediately after a compression/reset event, re-read the ledger to reload objective, criteria, open threads, and next action.
**Done when:** you can state the objective and the next action from the ledger without scrolling context.

### 3. Register the location
Store the ledger path in `memory` (supermemory) so a fresh session can find it.
**Done when:** "where is the ledger for <project>" is answerable from memory.

### 4. Keep Next Action true
There is exactly one **Next Action**, and it is current. Update it whenever the situation changes.
**Done when:** the Next Action is the thing you'd actually do next, not a stale leftover.

## Common Pitfalls

1. **State only in context.** The exact failure mode this skill prevents. Write it down.
2. **Duplicating `todo`.** The ledger is the narrative spine (objective, decisions, threads), not a task list. Let kanban/todo hold tasks.
3. **A stale Next Action.** A wrong "next step" is worse than none — it sends the next session the wrong way.
4. **Decisions without a reason.** Log *why*, or you'll relitigate it next session.

## Verification Checklist

- [ ] One `LEDGER.md` per project with the six fixed sections
- [ ] Durable kanban board paired for task-level state
- [ ] Ledger updated with the delta before moving to the next step
- [ ] Ledger re-read at session start / after compression
- [ ] Ledger path stored in `memory`
- [ ] Exactly one current Next Action
