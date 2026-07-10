# Quality-Program Orchestrator

Autonomous runner for `EXECUTION-RUNBOOK-2026-07-10.md` v2. It executes each runbook
phase as a **separate headless `claude -p` session** (implementation on Opus 4.8,
judging on Fable 5), verifies completion **deterministically** between phases, loops
judge REVISE rounds until SHIP, waits out CLI quota windows, and **stops at human
checkpoints** — the four places where the runbook genuinely needs your eyes.

## Quick start

```bash
cd ~/Nexus-Agentic-Coding-Setup
python3 orchestrator/run_program.py --dry-run   # see the step plan
python3 orchestrator/run_program.py             # start (stops at the Phase 0 plan for --ack)
python3 orchestrator/run_program.py --ack       # approve the shown checkpoint, continue
python3 orchestrator/run_program.py --status    # progress + cost so far
```

The runner is resumable at every step: state lives in `orchestrator/state.json`,
Ctrl-C is safe, and a rerun continues where it stopped. `--from phase3` rewinds the
state and immediately continues running from that step.

## Exit codes

| Code | Meaning | What you do |
|---|---|---|
| 0 | ran to the end of the available steps | nothing |
| 3 | **checkpoint** — banner printed | do the review it asks for, then `--ack` |
| 4 | **escalation** — `orchestrator/ESCALATION.md` written | read it, fix/arbitrate, rerun |
| 130 | interrupted | rerun to resume |

## The step plan

phase0 (commit hygiene, needs one `--ack` on its plan) → phase1 impl → phase2 judge
→ **CHECKPOINT** → phase3 impl → phase4 judge → **CHECKPOINT** → phase5 impl →
phase6 judge → **CHECKPOINT** → phase7 impl → phase7 judge → **CHECKPOINT (always
stops before the paid Phase 8)** → phase8 → final review checkpoint.

Phase prompts live in `orchestrator/prompts/` — verbatim from the runbook, one file
per session, editable. The runner appends a headless protocol to each: implementation
children must not ask questions (decisions are locked; master plan §5 wins), must
leave the tree committed, must end with `PHASE COMPLETE`/`PHASE PARTIAL`, and hand
off via `HANDOFF-<phase>.md` when context fills; judge children must not edit and
must end with a machine-parsable `VERDICT:` line.

## What the runner checks itself (no model involved)

After every implementation phase and every fix round:

1. `systemctl --user restart nexus` + HTTP probe of `https://127.0.0.1:8777`
2. the phase's gate suite (`verify.sh` + the e2e gates, incl. the ones the phase was
   supposed to *build* — a missing gate file fails the phase)
3. `git status` clean (orchestrator's own untracked state excluded)
4. the phase report exists (Phase 1: contains "Fixes 2026-07-10")

One remediation child gets a chance to fix red checks; if still red → escalation.
A judge that modifies the working tree → escalation (judges must not edit).

## Runbook rules honored

- **Rule 1 (one session at a time):** children run strictly sequentially. Do NOT run
  another implementation session against this repo while the runner is active.
- **Rule 6 (no design questions):** baked into the headless protocol suffix.
- **Rule 7 (handoff):** timeout/`PHASE PARTIAL` → up to 2 continuation sessions.
- **Rule 8 (deadlock):** after 3 judge rounds without SHIP the runner escalates and
  tells you to arbitrate via the planning conversation — it never referees design.
- **Rule 9 (post-phase checklist):** automated where deterministic; the "click around
  2 minutes" part is exactly what the checkpoints hand back to you.
- **Rule 10 (DB safety):** `app/nexus.db.bak-<phase>` before phases 1/3/5/7 (+ a
  pre-program backup in Phase 0).
- **Phase 0 / F1:** never `git add -A`; the runner classifies the dirty tree, commits
  program docs and stray root-level `.md`s separately, hard-stops on any other dirt.

## Quota handling & account switching

CLI usage-limit / rate-limit errors put the runner to sleep in 15-minute steps (up to
6 h per child, `QP_MAX_QUOTA_WAIT_S` to change) instead of failing — the same
backpressure lesson the program itself implements as its finding 3. Non-quota child
errors get one retry, then escalate.

**Nothing is lost on a limit hit.** Committed work is in git; the runner's position is
in `state.json` (saved after every step and judge round); the interrupted child's
on-disk edits stay put. After the sleep, an implementation child is re-spawned with
the **continuation prompt** (inspect `git log`/`git status`/HANDOFF-*.md, continue —
don't redo), so at most the current uncommitted sub-step gets re-derived. An
interrupted **judge** re-runs from scratch on purpose — a verdict must come from one
complete review; you lose only that judge run's tokens.

**Switching to another account** (e.g. a colleague's) works at any time, because
children read credentials fresh at every spawn and the runner never resumes CLI
sessions across children:

```bash
# in your own terminal, while the runner sleeps on quota (or after exit 4):
claude logout
claude login          # the other account
claude -p "ok"        # 5-second sanity check that headless auth works
```

- Runner still sleeping → the next 15-min probe picks up the new account by itself.
- Runner exited (quota-budget escalation, code 4) → restart with
  `python3 orchestrator/run_program.py --preflight` — it re-pings both models on the
  new account (the colleague's plan must include Opus 4.8 AND Fable 5), then resumes
  exactly where it stopped.
- Note: the login is machine-wide — Nexus's own cverify/cjudge frontier calls bill
  the switched account too until you switch back.

## Models, permissions, cost

- Models: `QP_IMPL_MODEL` (default `claude-opus-4-8`), `QP_JUDGE_MODEL` (default
  `claude-fable-5`). A preflight pings both once before anything runs.
- **Subscription-only billing:** children run on the `claude login` OAuth
  credentials; the runner strips `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` /
  `ANTHROPIC_BASE_URL` / Bedrock/Vertex flags from the child env, so a stray API key
  in the shell can never silently meter the run. The `total_cost_usd` figures in
  logs/`--status` are **API-equivalent accounting, not charges** — marginal Claude
  cost on a subscription is $0. The only metered spend is GLM (Z.ai) executor tokens:
  small smoke-test amounts in Phases 1–7, real spend only in Phase 8 (which always
  stops at a checkpoint first).
- Children run with `--permission-mode acceptEdits` + broad `--allowedTools` and a
  deny-list (`git push`, `gh`, `sudo`) — the same vetted pattern as `cverify`. That
  IS a full-autonomy grant to the child sessions; that's the deal you're making.
- Every child's JSON envelope (incl. `total_cost_usd`, API-equivalent) is stored in
  `orchestrator/logs/` and summed into `--status`.

## Files

```
orchestrator/
  run_program.py            the runner (stdlib only, python3)
  prompts/phase*-{impl,judge}.md   per-session prompts (runbook-verbatim, editable)
  MASTER-SESSION-PROMPT.md  optional: paste into a Claude session to supervise the runner
  state.json / logs/ / ESCALATION.md   runtime (gitignored)
```
