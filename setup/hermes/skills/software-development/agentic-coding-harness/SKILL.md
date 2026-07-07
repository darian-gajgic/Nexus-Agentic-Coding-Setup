---
name: agentic-coding-harness
description: "Wire a spec → implement → verify loop into any project so autonomous coding agents (GLM/Claude Code/etc.) produce client-grade output with minimal human review. Creates the automated, blocking verify-gate that is the #1 error-reducer."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [agentic-coding, quality-gates, verify-loop, spec-driven, automation, error-reduction]
    related_skills: [plan, test-driven-development, requesting-code-review, systematic-debugging]
---

# Agentic Coding Harness

Use this skill when onboarding a project for autonomous agent development, when agent output has
too many bugs, or when the user wants "the professional setup" so agents can finish big projects
without hand-holding.

## Priority order (USER-SPECIFIED — governs all decisions in this skill)

1. **RESULT QUALITY is priority #1.** Correctness first, always. Never trade a better result for
   fewer tokens or lower cost. When in doubt between two approaches, pick the one more likely to
   produce correct, client-grade output.
2. Token / cost optimization is SECONDARY — worth doing but never at the expense of result quality.
3. Verify-loop is non-negotiable (see below) — it is what protects quality.

This was stated explicitly by the user when reviewing the toolchain (2026-07-03). Carry it into
every tool-config and model-routing decision: a cheaper config that degrades results is the wrong
choice for this user.

## Why this exists

Bad agentic output is almost never the model. It is the absence of a disciplined
**plan → implement → verify** loop. The single highest-leverage fix is an automated, **blocking**
verify-gate that runs after every edit and blocks the agent from proceeding until the code passes.
This is the consensus across Anthropic Engineering, GitHub, Microsoft, and Martin Fowler (2025-26).

A well-engineered harness makes a weaker model outperform a strong model with no harness. This is
exactly why developers get great results from GLM-5.2 alone.

The empirical case is stark: METR found experienced devs were **19% slower** with AI tools on their
own repos (cognitive load of reviewing output); New Relic found AI code grades higher in review but
causes **~1.7x more prod incidents** because reviewers don't execute it. Only automated execution
catches what eyeballs miss. See `references/agentic-coding-landscape.md` for the full tool map,
cost model, and the user's installed toolchain. For self-hosting Paperclip specifically, see
`references/paperclip-selfhost-setup.md` (non-trivial gotchas).

## Research discipline (when surveying the coding-tool space)

When the user asks to research/survey the agentic-coding tool landscape, follow the
`technology-landscape-research` skill (wide-before-deep, name specific tools, cost-vs-free
breakdown, per-item status verdict). That skill generalizes the methodology; this one just
points to it.

## The 6 pillars of a professional agentic setup

1. **Spec-driven dev** — write a behavior spec (SPEC.md) BEFORE code. Shared source of truth.
2. **Plan-first, written to a file** — never let the agent keep the plan only in its head.
3. **Verify-loop (automated, blocking)** — typecheck + lint + tests run after every edit; BLOCK until green.
4. **Context engineering** — project rules (AGENTS.md / CLAUDE.md) committed: build/test/lint commands, conventions, in/out of scope.
5. **Parallel agents in git worktrees** — each agent its own isolated checkout, no conflicts.
6. **Subagent delegation + adversarial review** — a SEPARATE fresh-context agent verifies against the spec. Never trust a self-reported "done".

Pillars 1,2,5,6 are about *organization*. Pillar 3 (the verify-gate) is the one most commonly
MISSING and the one that directly stops bugs. This skill focuses on wiring it in.

## The verify-gate has TWO layers — static is necessary but NOT sufficient

**The hardest-learned lesson (2026-07-03, Jarvis build):** a project shipped with syntax + function-presence + asset-ref gates all green, yet the #1 feature was COMPLETELY BROKEN. Root cause: the backend streamed SSE events named `assistant.delta`, but the frontend handler only matched `text_delta`. Every reply was silently dropped. No static gate can catch a backend↔frontend contract mismatch — the code is syntactically perfect and every function exists. The user called it "worse than before." 

The METR / New Relic data already predicted this: AI code grades HIGH in review but causes ~1.7x prod incidents because reviewers (human OR static-analyzer) don't EXECUTE it. **Only runtime execution catches contract drift.** Therefore a real verify-gate is two layers:

### Layer 1 — STATIC gate (fast, every edit): blocks syntax/import/integrity errors
- `scripts/verify.sh` + `.claude/check.sh` + git pre-commit (templates below).
- Catches: syntax errors, deleted includes, missing functions the UI calls, debug leftovers.
- Runs in <2s, fires after every edit. This is the floor, not the ceiling.

### Layer 2 — RUNTIME gate (per-feature, before "done"): blocks contract/logic bugs
- A script that actually EXERCISES the feature end-to-end and asserts on observable behavior.
- For a web UI: drive it with Playwright — load the page, trigger the action, assert the DOM changed / the endpoint returned the expected shape / the SSE stream yielded the expected events.
- For an API: curl the endpoint with a real payload and assert on the response body, not just the status code.
- For a pipeline: feed real input through and assert the output (a face detector on an image output, a known-phrase round-trip through STT→TTS, etc.).
- This is what catches: SSE event-name mismatches, silent JSON shape drift, autoplay/permission failures, race conditions in async playback, empty-response bugs that return HTTP 200.

**RULE: a static gate passing is NEVER sufficient evidence a feature works.** Before declaring any interactive/contract-heavy feature done, write (or run) a Layer-2 runtime test that exercises the real path. If the project has no runtime test for the feature, that's the gap to close FIRST — it is more important than any code change. See `references/runtime-verification-playwright.md` for the concrete pattern that caught the Jarvis SSE bug, including the headless-browser + console/network-capture script template.

**Orchestrator autonomy (user-stated, 2026-07-03):** the user's #1 frustration across the whole build was being handed an unverified result to test themselves ("cant you test and verify it yourself? This should be your job, only present me the final result"). The rule: self-verify STATIC + RUNTIME before presenting any "done" result; if a capability to test is missing, INSTALL it (`pip install playwright`; `ollama pull llava` for local vision) rather than delegating the test back to the user; exhaust every objective check (endpoint shape, DOM update, face-detector on a frame, pixel-diff for animation) and only then — clearly labeled as the one subjective residue — hand the genuinely-judgment-call parts to the user. Never present an unverified build as a finished one. For the local-vision path when the hosted vision API isn't billable, see `references/local-vision-fallback.md`.

## The universal STATIC gate (Layer 1)

The static gate must be editor-agnostic — it must fire for EVERY path into the repo (glm, Anthropic,
manual edits). A single git `pre-commit` hook achieves this. Layer a fast per-edit hook on top for
the tools that support it.

### What to create in the target project

1. `scripts/verify.sh` — the full check: syntax sweep, lint, typecheck, focused tests, static-asset
   refs, function-integrity (do the functions the code calls still exist?), and API smoke tests if a
   server is running. ~0.3-2s for the static parts.
2. `.claude/check.sh` — a FAST (<2s) subset (syntax + refs + integrity, no server curls) that the
   `~/.claude` PostToolUse auto-verify hook auto-discovers and runs after every Write|Edit, blocking
   on failure and feeding the error back so the agent self-corrects.
3. `.git/hooks/pre-commit` — runs verify.sh (+ browser smoke if playwright + server present); blocks
   the commit. This is the net that catches everything regardless of editor.

### Pitfalls (learned from the Jarvis failure)

- The `~/.claude/hooks/test-check.js` verify hook is **opt-in per project**: it only fires if
  `<project>/.claude/check.sh` exists. If that file is absent, the #1 error-reducer is SILENTLY OFF.
  Always confirm the check.sh file exists and is executable, and run it once by hand to prove it
  blocks a deliberate error.
- Optional deps (e.g. playwright) must SKIP gracefully when absent, not block. A missing optional
  tool should never turn into a false gate failure.
- `cp`/`mv`/`git stash` in a pre-commit hook must restore on EXIT (trap) or you corrupt the worktree.
- Make the per-edit gate fast. Server curls and full test suites belong in the pre-commit hook or CI,
  not the per-edit loop, or the agent stalls on every keystroke.
- Browser/runtime tests only run if the server is live — guard them so the gate still passes headless.
- **When you DELETE a file or component, update verify.sh the same edit.** A verify.sh that checks for `class JARVISAvatar in avatar.js` will FAIL after you delete avatar.js. Every refactoring that removes a file/function/endpoint must simultaneously remove its verify.sh check and add checks for the replacement. Run verify.sh immediately after the deletion to confirm.
- **PostToolUse hook latency matters.** Node.js hooks cost ~60ms per spawn (V8 startup); two hooks = ~120ms dead time on EVERY edit. Prefer a single bash hook that early-exits when there's no work — 13x faster. Never set per-edit-gate timeouts above 60s; slow checks belong in the pre-commit hook, not the edit loop. See `references/hook-latency-and-permissions.md`.
- **Permission-glob security: `./` anchors to root, use `**/` for depth.** A deny rule like `Read(./.env*)` only blocks `.env` in the CWD root — nested files (`project/subdir/.env`, `config/.env.production`) leak through the broader `Read(**)` allow. Always use `Read(**/.env*)` and enumerate `**/credentials*`, `**/secrets/**`, `**/key.env` patterns. Apply to BOTH `~/.claude/settings.json` AND `~/.claude-glm/settings.json`. Test with nested paths before trusting — see `references/hook-latency-and-permissions.md` for the verification script.
- **Ad-hoc verification scripts in /tmp get re-flagged by the change-tracker after deletion.** The system's "stale verification" reminder keys on changed paths and does not notice that you already deleted the temp script — so it keeps demanding fresh evidence for files that no longer exist, costing extra turns to re-prove. RULE: when you must write a /tmp verify script, (a) prefer in-place verification or a project-local scripts/ path instead; (b) if /tmp is unavoidable, make the script self-delete (`rm -f "$0"`) as its last line AND run the verification inline in the same terminal call that created it, so the path is never left dangling for the tracker to latch onto. Don't fight the tracker across multiple turns — collapse create+run+cleanup into one terminal turn where possible.

## Workflow to onboard a project

1. **Check what exists**: `ls scripts/verify.sh .claude/check.sh .git/hooks/pre-commit` in the project.
2. **Read the project's conventions** from its CLAUDE.md / AGENTS.md / README (build/test/lint commands).
3. **Create the three files** (templates below), tailored to the stack. For Python use `python -m py_compile`;
   for JS `node --check`; add function-integrity checks for the core entry points the UI calls.
4. `chmod +x` all three. Verify scripts is executable.
5. **Prove it blocks**: inject a deliberate syntax error, confirm BOTH gates return non-zero + a clear
   message; restore and confirm green. Never trust an unproven gate.
6. Commit the scripts and a CLAUDE.md/AGENTS.md documenting the commands and workflow.
7. Tell the user to run the full feature through the loop: spec → plan → implement (edits auto-gated)
   → reviewer subagent → commit (auto-gated).

## Template: .claude/check.sh (fast per-edit gate)

Tailor the extensions and integrity needles to the project. Keep it under ~2s.

```bash
#!/usr/bin/env bash
set -uo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
FILE="${1:-${CLAUDE_EDITED_FILE:-}}"
FAIL=0
# 1. syntax of the edited file
# 2. whole-project syntax sweep
# 3. static-asset reference integrity (catches deleted includes)
# 4. core-function integrity (catches deleting a fn callers depend on)
# 5. no debug leftovers
exit $FAIL
```

## Template: .git/hooks/pre-commit (editor-agnostic gate)

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
[ -x scripts/verify.sh ] && { bash scripts/verify.sh || { echo "❌ COMMIT BLOCKED"; exit 1; }; }
# optional browser gate: only if server live AND playwright installed
if curl -sf http://localhost:PORT/health >/dev/null 2>&1 && node -e "require.resolve('playwright')" 2>/dev/null; then
  node scripts/browser-verify.mjs || { echo "❌ COMMIT BLOCKED"; exit 1; }
fi
echo "✅ pre-commit gate passed"; exit 0
```

## Reference: the proven GLM-coding harness

For wiring a coding agent onto a custom OpenAI-compatible endpoint (GLM/Z.AI, Ollama, vLLM),
see `references/aider-custom-endpoint.md` — the key-sourcing launcher pattern + architect-mode
config + the quality verdict. A copy-paste-ready launcher template is in
`templates/key-sourced-launcher.sh`. For VS Code + Cline + Memory Bank (the IDE path), see
`references/cline-vscode-setup.md`.

The user already has a sophisticated harness in `~/GLM-coding` + `~/.claude-glm` (2026-07):
- `~/.claude-glm/commands/spec.md` — `/spec` command: interview → SPEC.md → implement → review → verify.
- `~/.claude-glm/agents/` — subagents: implementer, verifier, reviewer, completeness, judge, test-integrity.
- `~/GLM-coding/scripts/parallel-agents.sh` — git-worktree fan-out (one agent per subtask, isolated).
- `~/GLM-coding/scripts/glm-ultra.py` — whole-project orchestrator with converge loop.
- `~/.claude-glm/hooks/` — auto-format (PostToolUse), danger-guard + sudo-gate (PreToolUse).

Both instances are now gated (2026-07-03):
- `~/.claude` — test-check.js (opt-in per project via `<proj>/.claude/check.sh`).
- `~/.claude-glm` — verify-check.sh (PostToolUse Write|Edit), same opt-in discovery, runs check.sh
  from the project root with cwd set. Mirrors test-check.js but parses file_path with jq like
  auto-format.sh. Builds the block payload with `jq -nc --arg` (NOT printf|jq, which breaks on
  newlines in error output) and MUST `cd "$projroot"` before running check.sh or relative globs fail.

As of 2026-07-04, the `~/.claude` PostToolUse gate was rewritten from two Node.js hooks
(syntax-check.js + test-check.js) into a single unified bash script (`post-edit-gate.sh`) that
early-exits in <5ms when there's nothing to do — 13x faster than spawning Node V8 on every edit.
The GLM verify-check.sh timeout was also lowered from 170s to 60s. See
`references/hook-latency-and-permissions.md` for the full pattern + benchmark + the copy-paste-ready
unified bash hook, plus the permission-glob security pitfall below.

GOTCHA when writing a bash PostToolUse verify hook: (1) parse stdin as JSON for file_path;
(2) walk up to find `<dir>/.claude/check.sh`; (3) run it with cwd=projectRoot (not the edited file's
dir); (4) on failure emit a {"decision":"block","reason":"..."} payload via `jq -nc --arg` and exit 0
(the decision lives in the payload, not the exit code) — Claude Code reads it and feeds reason back
to the agent. A copy-paste-ready, proven implementation is in `templates/verify-check.sh`. Do NOT
build the JSON with `printf | jq` — raw newlines in tool error output make invalid JSON and the
block decision is silently swallowed (hit and fixed in session).

## Remember

- The gate must be PROVEN to block bad edits before you trust it. Inject an error and watch it fail.
- Opt-in verify hooks silently do nothing if their trigger file is missing — always confirm the file.
- Editor-agnostic (git hook) + editor-native (per-edit check) = defense in depth.
- A weaker model + a real gate beats a strong model + no gate.
- **STATIC GATES CANNOT CATCH RUNTIME CONTRACT DRIFT.** A web UI whose #1 feature silently broke
  (SSE event-name mismatch) passed every syntax/lint/function-presence gate. Runtime/integration
  tests (Playwright for web) are mandatory, not optional, before declaring a feature done., before declaring a feature done.

## Keep an issues log when testing the setup itself

When a project's purpose is to stress-test the coding setup (not just ship a feature), maintain a
`SETUP-ISSUES.md` in the project root from the first problem onward. Each entry: ID, tag
([BUG]/[FRICTION]/[SETUP]), symptom, root cause, resolution, and a SETUP-ACTION (the durable
improvement to the harness/skill/config that prevents recurrence). Also record POSITIVE signals
(I-011 style) — when a subagent independently converges on the same diagnosis as the orchestrator,
that validates the harness is working and is worth noting.

This serves two goals the user stated explicitly (2026-07-03): (1) the meta-goal of a test build is
to expose setup weaknesses, not just produce the feature; (2) every friction point should be
captured "so we can fix it later or fix it when it appears, whatever you think is best." The log is
the input to future skill/memory/harness improvements — without it, the same friction recurs next
session and the lesson is lost. Treat capturing it as part of the work, not optional bookkeeping.
