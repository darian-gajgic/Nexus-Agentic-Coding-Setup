---
name: parallel-delegated-build
description: "Orchestrate a big project through SPEC → PLAN → IMPLEMENT (parallel delegated subagents) → VERIFY → ADVERSARIAL REVIEW using Hermes native delegation. The orchestrator (me) coordinates isolated subagents so the user doesn't juggle CLIs. Configured safe: max_concurrent_children=3, flat depth, auto-compression on."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [agentic-coding, delegation, parallel-work, spec-driven, orchestration]
    related_skills: [agentic-coding-harness, plan, test-driven-development, requesting-code-review]
---

# Parallel Delegated Build

Use when the user wants me (Hermes) to run a whole feature/project through the disciplined loop
myself, spawning parallel subagents for the implementation instead of shelling out to glm/claude
manually or writing every file in the main context.

## Why

Per METR's 2025 study, the #1 productivity tax on AI-assisted dev is the developer's cognitive load
from context-switching between tools and reviewing unverified output. The fix is to have ONE
orchestrator coordinate the work and hand back verified results. I AM that orchestrator — I have
native async subagent delegation (delegate_task), isolated contexts, and a real terminal. Using it
keeps the user in the driver's seat while I handle the tedious multi-agent coordination.

This is the Hermes-native analog of Claude Code Dynamic Workflows / BMAD / glm-ultra, but it runs
inside this conversation with no extra CLI and no extra license.

## Preconditions (safety)

Delegation config is explicitly bounded (verified 2026-07-03 in ~/.hermes/config.yaml):
- delegation.max_concurrent_children: 3  (at most 3 parallel subagents per batch)
- delegation.max_spawn_depth: 1  (flat — children can't spawn children; no runaway trees)
- delegation.max_iterations: 50
- compression: enabled at 50% context, protects last 20 messages

These are SAFE defaults. Do NOT raise them without explicit user approval. Delegation does NOT cause
terminal crashes — those are the gnome-terminal/VTE segfault bug, unrelated (verified: VTE peaked
450MB with 23Gi free, no OOM kills).

## The loop

### 1. SPEC (I do this with the user, in-context)
Resolve unknowns via clarify. Write SPEC.md at the project root: context & goal, numbered testable
requirements, files/interfaces to touch, out-of-scope, and an exact verification step. Get user
confirmation before implementing.

DECISION-FRAMING (important when the task has realistic technical constraints): surface the hard
constraints honestly BEFORE the user commits to an approach. If a requested technique has a
fundamental limitation (e.g. a neural model can't render 60fps in real-time — it renders offline
then plays), say so plainly and present 2-4 real options with tradeoffs, then let the user pick
with eyes open. This converts "you did the wrong thing" into "I chose this knowing the tradeoff"
and prevents the failure mode where the agent over-promises and under-delivers. Never hide a
technical limitation to make an option sound better. An honest "this can't do X, here's what it
CAN do" is more valuable than a plausible-looking commitment that will miss expectations.

### 2. PLAN (I write this to a file)
Use the `plan` skill. Break the spec into bite-sized tasks (2-5 min each), exact file paths,
complete code, TDD-ordered, with verification commands. Save under .hermes/plans/. This file is the
human review gate AND the source of truth the subagents work from.

### 3. IMPLEMENT (parallel delegated subagents)
Dispatch independent tasks via delegate_task (batch mode, up to 3 concurrent). Each subagent gets:
- The SPEC.md and plan file paths to read first.
- Its specific task goal + the exact files to touch.
- Instruction to run the project's verify gate (.claude/check.sh or scripts/verify.sh) and NOT
  report done until it passes.
- Instruction to respond in the user's language.
- For ML/setup tasks: explicit instruction to CHECK what deps are already installed before
  installing new ones (a subagent will happily `pip install dlib` and compile it for 4 minutes
  when cv2/OpenCV — sufficient for the task — was already present).

RULES:
- Only dispatch tasks that are INDEPENDENT (don't touch the same files) in parallel. If two tasks
  edit the same file, do them sequentially myself.
- One delegate_task call per task (or a batch of up to 3 truly independent ones).
- Subagents are leaf-role: they cannot delegate further or ask the user. Give them everything they
  need in the goal/context.
- BUDGET FOR THE ITERATION LIMIT. Leaf subagents have a finite turn/api-call budget (default ~50).
  A task that looks like one deliverable often has many setup sub-steps (each pip install, each
  long compile, each patch eats a turn). If a task is "install + configure + run + verify", the
  subagent frequently exhausts its budget on setup and never reaches the run/verify step — then
  reports "blocked" with the work 90% done. Prevent this by EITHER splitting into a "setup"
  subagent and a separate "execute+verify" subagent (each with a full budget), OR giving the
  setup-heavy task explicit priority ordering ("do the verification step FIRST if deps already
  exist; only install if missing"). Never let "completed" mean "setup done, verification not run".

### 4. VERIFY (I do this, not the subagent's self-report)
After subagents return, I do NOT trust their "done". I run the verify gate myself and read the real
output. Per New Relic 2026: AI code grades high in review but causes 1.7x runtime incidents — only
actual execution catches the bugs review misses. Treat "blocked before verification" as INCOMPLETE
and finish the verification step myself before reporting to the user.

CRITICAL — the verify gate is TWO LAYERS (see `agentic-coding-harness` skill):
- **Layer 1 (static):** syntax + function-presence + asset-refs. Fast, catches deletions/typos.
  A subagent returning "verify.sh passed 22/22" has ONLY proven Layer 1. That is NOT evidence the
  feature works. This exact gap shipped a feature where every reply was silently dropped (backend
  emitted `assistant.delta`, frontend handled `text_delta` — syntactically perfect, totally broken).
- **Layer 2 (runtime):** exercise the real path end-to-end and assert on observable behavior. For a
  web UI, drive Playwright (load page → trigger action → assert DOM changed + endpoint hit + no JS
  errors). For an API, curl a real payload and assert on the body, not just the status.

RULE for delegated interactive/contract-heavy features: do NOT report "done" to the user until you
have run a Layer-2 runtime test yourself (or confirmed the subagent wrote one and you re-ran it).
"verify.sh green" from a subagent is a floor, not a verdict. If you can't run the runtime test
(e.g. no browser tooling installed), INSTALL IT (`pip install playwright && playwright install
chromium` — one-time, ~115MB) rather than punting the test to the user. Never imply runtime
confidence you don't have.

## ORCHESTRATOR OWNS VERIFICATION END-TO-END (non-negotiable)

The user's #1 frustration this build (2026-07-03, stated plainly): **"cant you test and verify it
yourself? This should be your job, only present me the final result."** I had shipped frontend
changes I couldn't run, declared success on a green static gate, and then asked the user to open the
browser and check whether the feature worked. That is the failure mode to eliminate. The operating
rule:

- **Self-verify before presenting.** For every feature, complete the full verify loop (static AND
  runtime) yourself before showing the user a "done" result. The user should receive a final,
  working artifact — not a hypothesis they have to test.
- **Install the missing capability rather than delegating the test.** "I can't test this" is almost
  always "I haven't installed the tool to test this." No headless browser? `pip install playwright`.
  Need to SEE the output? install a local vision model (Ollama llava) or use an ffmpeg frame extract
  + deterministic check. The capability gap is a setup task, not a reason to hand the test back.
- **Exhaust objective verification, then distinguish what's left.** Run every check you can: does
  the endpoint return the right shape? does the DOM update? does a face detector find a face in the
  rendered frame? does a pixel-diff prove the avatar animates vs. stays static? Only the genuinely
  SUBJECTIVE residue (e.g. "is the lip-sync convincing to a human eye") is the user's to judge —
  and when you hand that over, label it explicitly as the one subjective thing, after you've proven
  everything objective.
- **Never present an unverified result as a finished one.** If you cannot fully verify, say so
  HONESTLY ("static passes, runtime not yet verified because X — I'll install Y and confirm") and go
  close the gap. Presenting an untested build to a user who expects a finished result is worse than
  the build being bad — it erodes trust in the whole setup.

### 5. ADVERSARIAL REVIEW (fresh-context subagent)
Spawn a reviewer subagent with fresh context: read SPEC.md, read the diff, map each requirement to
met/partial/missing. Do not let the implementer review its own work.

### 6. REPORT + COMMIT
Summarize for the user: what changed, verify result, review findings, follow-ups. Commit via git
(pre-commit gate runs automatically).

## When to use this vs alternatives

- Use THIS skill when: the project is substantial (5+ tasks), tasks are parallelizable, and the user
  wants me to own the coordination.
- Use `agentic-coding-harness` + manual edits when: the task is small or sequential.
- Use `glm`/`claude` CLI directly when: the user explicitly wants to drive a specific tool.

## Gotchas

- delegate_task returns immediately (async); results re-enter the conversation as separate messages.
  Don't block waiting — start independent work meanwhile, but serialize anything touching shared files.
- Subagent summaries are SELF-REPORTS. For any external side-effect (write, POST, publish), verify
  the handle (file path, URL, status) myself before telling the user it succeeded.
- Keep the per-subagent goal self-contained — subagents have NO memory of this conversation.

## Sizing subagents (learned from real use — see I-008/I-013)

- A subagent has a finite iteration budget (~50 api calls). A task with many setup steps
  (pip installs that each take a turn, long compiles like `pip install dlib`, multiple patches)
  will BURN THE BUDGET on setup and never reach the final execute/verify step.
- **Rule: one subagent = one coherent unit of work + a verifiable gate.** If a task has heavy
  setup, SPLIT it: a "setup" subagent that leaves artifacts on disk, then a separate "execute"
  subagent with a full budget for the actual work + verification. Do NOT mix sprawling setup
  with final execution in one dispatch.
- Always include a mandatory gate in the goal ("run X and report its exit code; do not report
  done if it fails"). A subagent with a clear pass/fail criterion completes reliably.

## Don't do these (learned the hard way)

- Don't use delegate_task to "check status" of a running delegation — it's for spawning workers,
  not introspection. Poll running delegations via filesystem ARTIFACTS (output files, logs) which
  are ground truth, not by spawning more subagents.
- Tell subagents to CHECK INSTALLED DEPENDENCIES FIRST before `pip install`-ing anything —
  they often re-install what's already there (e.g. building dlib from source when cv2 is present),
  wasting minutes of their limited budget.
- Don't trust a green static gate (syntax/lint/function-presence) as proof a feature works.
  Runtime/integration tests (Playwright for web UIs) are required to catch contract drift.
- PROVIDER CONCURRENCY CEILING: subagents share the same model provider as the orchestrator, and
  the limit is TIER-SPECIFIC, not one global number. On Z.AI (GLM-5.2): the regular model allows
  ~10 concurrent requests, but **GLM-5.2 TURBO is concurrency-1 (serial only)**. Count the total
  (Hermes delegation children + any parallel glm/claude CLI sessions + in-session tool-use) against
  the tier the subagents actually route to. Default 3 children + orchestrator + tool-use is safe on
  regular; on Turbo, ANY parallel child plus the orchestrator's own calls can 429. Keep delegate
  batches small (2-3) on regular; go fully serial (one at a time) on Turbo unless the user confirms
  they've raised the tier. Ask the user which tier/concurrency they have if unclear — it changes
  the fan-out math.
- CHECK STATUS VIA FILESYSTEM ARTIFACTS, not by spawning more subagents. To see whether a
  background delegation is progressing, poll the deliverables on disk (the expected output file,
  `ps aux | grep` for the process, `nvidia-smi` for GPU activity) — NOT by dispatching a
  "status check" delegate_task, which spawns a useless extra worker that just reports "not found".
  There is no clean status-introspection tool for running delegations; the artifacts ARE the status.
- Wav2Lip / ML-library setup tasks: the upstream repos are often years old and break on modern
  libs (e.g. librosa.filters.mel() became keyword-only; torch.load default changed; checkpoints
  may be TorchScript archives the code tries to load as state_dicts). Patching these is expected
  setup work, not a blocker — see references/wav2lip-setup.md for the concrete patches that worked
  once.
- ORCHESTRATOR/SUBAGENT SERVICE COLLISION: when the build involves a long-running server (uvicorn,
  node, etc.) that BOTH the orchestrator and a delegated subagent may start/stop/restart, they can
  kill each other's instance mid-verification. The classic failure: orchestrator runs an ad-hoc
  verify script, gets a spurious "endpoint failed" because the subagent (or the orchestrator's own
  earlier `pkill`) took the server down a moment ago, and the failure looks like a code bug when
  it's purely a process-lifecycle collision. RULE: the orchestrator owns the server lifecycle for
  the project. Before running any verification that hits a local endpoint, confirm the server is UP
  right now (curl health); if a subagent might restart it, serialize (don't verify while a subagent
  is active on the same project). Re-run the verify after confirming UP before declaring a failure.
  Distinguish "code defect" (reproduces with server up) from "process collision" (passes on re-run).
- STRUCTURAL VALIDATION WHEN VISION ISN'T AVAILABLE: if the task produces an image/video and the
  vision model isn't on the user's plan (GLM-5V-Turbo 429, or video files unsupported), don't give
  up on validating the output. Use a deterministic structural check instead: extract a frame with
  ffmpeg, run a face detector (dlib/cv2) on it — a detected face proves the model produced real
  content, not noise, without any vision API. See references/wav2lip-setup.md.
