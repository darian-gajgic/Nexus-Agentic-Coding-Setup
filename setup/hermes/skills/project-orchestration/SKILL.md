---
name: project-orchestration
description: "Use when orchestrating any multi-step project whose deliverable is NOT code — a content-production pipeline, a research project, a business/ops task — where there is no verify.sh. Decomposes the goal into a written plan, delegates independent subtasks, verifies each non-code deliverable against explicit acceptance criteria, tracks state on the kanban board, and re-grounds against the original spec every few steps. Don't use for software builds (use parallel-delegated-build) or a no-execution plan file only (use plan)."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [orchestration, delegation, project-management, manager, tracking]
    related_skills: [parallel-delegated-build, plan, goal-drift-discipline, project-ledger]
---

# Project Orchestration (non-code)

## Overview

The domain-agnostic analog of `parallel-delegated-build`. That skill runs software projects behind a `verify.sh` gate; this one runs the projects with no compiler and no test suite — a content pipeline, a research deliverable, an ops/business task — with the same discipline: **SPEC → DECOMPOSE → DELEGATE → VERIFY → TRACK → REGROUND**. The hard part of non-code work is that "done" is a judgment call, so this skill forces explicit acceptance criteria and verification against them.

**Core principle:** with no compiler to say it's wrong, the acceptance criteria are the only thing between "delegated" and "actually correct." Write them first; never trust a subagent's self-report.

## When to Use

**Use for:**
- A content-production pipeline (research → outline → draft → edit → repurpose → schedule)
- A multi-step research project, ops task, or business deliverable
- Any project with independent workstreams worth running in parallel and no `verify.sh`

**Don't use for:**
- Software builds → `parallel-delegated-build`
- A plan you will not execute this turn → `plan`
- A single-step task (just do it)

## Steps

### 1. Spec
Write the objective and the **acceptance criteria** — the checkable conditions that make the deliverable "done" — to the project ledger/kanban (see `project-ledger`). Concrete beats vague: "3 platform posts, each within its limit, each a distinct hook" beats "good social posts."
**Done when:** a stranger could tell whether the finished work meets the criteria without asking you.

### 2. Decompose
Break the goal into subtasks; tag each **independent** (parallelizable) or **dependent** (needs a prior result).
**Done when:** every subtask is small enough to hand off with a one-paragraph brief, and its dependencies are explicit.

### 3. Delegate
Fan out independent subtasks via `delegate_task`, up to the live `delegation.max_concurrent_children`. Each brief carries the subtask's own acceptance criteria and a required output shape. **Never spawn a subagent just to check another's status** — poll the filesystem/kanban instead.
**Done when:** each independent subtask is dispatched with its own criteria; dependent ones are queued behind their prerequisites.

### 4. Verify (non-code)
Check each returned deliverable against **its** acceptance criteria yourself — re-read it, cross-check facts against a source (invoke `claim-verification` for fact-bearing work), compare a draft to the brief. A subagent reporting "done" is a claim, not evidence.
**Done when:** every deliverable is checked against its criteria and either accepted or returned with a specific fix — none accepted on the subagent's word.

### 5. Track
Move kanban cards as tasks progress; record decisions and blockers in the ledger.
**Done when:** the board reflects reality — no "in progress" card whose work is actually done or abandoned.

### 6. Reground
Every 3-5 steps, re-read the original spec and acceptance criteria to catch scope creep and silent drift (complements `goal-drift-discipline`).
**Done when:** the current work still maps to the original objective, or you've deliberately, explicitly changed the spec.

## Common Pitfalls

1. **Serial by default.** Independent subtasks run one at a time. Fan them out.
2. **Trusting self-reports.** "Subagent says done" is not verification. Check against criteria.
3. **Fuzzy acceptance criteria.** "Make it good" can't be verified. Make criteria checkable up front.
4. **Silent scope drift.** Ten steps later you're building something else. Reground on a cadence.
5. **A status-check subagent.** Spawning an agent to ask another how it's doing wastes budget and lies. Poll state directly.

## Verification Checklist

- [ ] Objective + checkable acceptance criteria written to the ledger/kanban
- [ ] Subtasks tagged independent vs dependent
- [ ] Independent subtasks fanned out within `max_concurrent_children`, each with its own criteria + output shape
- [ ] Every deliverable verified against its acceptance criteria (not the subagent's self-report)
- [ ] Kanban reflects real state; decisions/blockers logged
- [ ] Regrounded against the spec at least every 3-5 steps
