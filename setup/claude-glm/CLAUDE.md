# GLM Claude Code — global instructions (isolated environment)

This is a SEPARATE Claude Code install running **GLM-5.2 via Z.ai**, isolated from the
primary Anthropic setup in its own config dir `~/.claude-glm`. It is launched with the
`glm` shell function.

## Model reality (read this)
- The backing model is **GLM-5.2** via Z.ai, running at **Max reasoning** (effort xhigh/max →
  GLM Max). **The native Workflow tool / dynamic orchestration IS enabled and works here**
  (verified empirically — the harness runs the JS workflow and fans out subagents on GLM).
  For substantive multi-step tasks, USE the Workflow tool: author a workflow that fans out
  subagents, adversarially verifies, and synthesizes — same as Anthropic ultracode. Toggle the
  full auto-orchestration mode with `/effort ultracode`. (Heavier deterministic alternative for
  whole-project builds: the external `glm-ultra` orchestrator with git worktrees + a converge loop.)
- **Built-in WebSearch/WebFetch are disabled** (nonessential traffic is off on the GLM key).
  Use the configured search MCP for web lookups.
- GLM follows long prose instructions less reliably than frontier Claude. Prefer small,
  explicit steps and lean on the deterministic hooks (auto-format, danger-guard) instead of
  trusting prose to be obeyed. **Never report a task as done without actually running its tests.**

## Workflow
- **Frontier spec handoff (preferred for non-trivial features):** the user runs `cspec "goal"` first —
  frontier Claude interviews them and writes SPEC.md. If a SPEC.md exists at the repo root, treat it
  as the authoritative requirements contract: do NOT re-interview, implement against it
  (implement -> review vs spec -> verify). No SPEC.md? Run `/spec` yourself.
- **Frontier review gate:** after tests pass on a non-trivial change, run `creview` via Bash — the
  script sanitizes its own environment, so it reaches the real Anthropic endpoint even from inside
  this session. Set the Bash tool timeout to 600000 ms (frontier review takes minutes). Fix its
  BLOCKING findings, re-run tests, then report. Max 2 creview rounds — if findings persist,
  surface them to the user instead of looping.
- Reuse existing code/utilities before writing new. Keep changes minimal and in the local style.
- Use the `implementer` subagent for a scoped subtask, `verifier` for diff review, and
  `reviewer` for an adversarial check against SPEC.md.
- User-facing product copy (UI text, emails, landing pages): read ~/knowledge/BUSINESS-CONTEXT.md
  and ~/knowledge/STYLE-VOICE.md first; the marketing/content playbooks in ~/knowledge/domains/
  define quality for those deliverables.

## Safety
- Secrets live in `~/.glm-agent/key.env` (chmod 600). Never print, cat, or commit secrets.
- **`glm` runs in bypass mode by default** (`--dangerously-skip-permissions`, opt-in 2026-07-03):
  it kills the auto-mode safety-classifier round-trip (≈halves Z.ai request volume → fewer 429s)
  and skips prompts. The PreToolUse **danger-guard hook**, the **deny-list**, and the **sudo-gate**
  still fire under bypass. Restore prompts+classifier with: `GLM_NO_BYPASS=1 glm`
- **In-session fan-out is capped** at `CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY=8` (Claude Code default
  10) to stay under Z.ai's ~10 concurrent-request tier. Override per-run: `GLM_CONCURRENCY=4 glm`
- A PreToolUse guardrail blocks `rm -rf`, disk destroyers, force-push, secret reads, and **writes**
  into `~/.claude-glm` / `~/.glm-agent`. **Reads** of `~/.claude-glm` (config/hooks/statusline) are
  allowed; `~/.glm-agent` reads stay blocked (it's secrets).
- `sudo` is gated by a timestamp window — ask the user to run `sudo -v` when you need it.
