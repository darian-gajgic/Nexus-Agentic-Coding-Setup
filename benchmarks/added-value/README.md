# Added-value benchmark — Nexus vs plain Claude Code vs raw GLM-5.2

Answers, with pre-registered criteria: **does Nexus add value, what improves, and by how much?**
Read `PREREGISTRATION.md` first — it defines the arms, blinding, metrics, and locked thresholds.
**Commit this directory BEFORE the first run** so the thresholds are provably locked.

## Prerequisites
- Nexus server running (`systemctl --user status nexus`), and for Arm A `task` mode: **at least one active agent lane** (Agents tab) — dispatch is queue-only, a lane executes it.
- `claude` CLI authenticated (subscription). Arm B + the Claude judge run in a **clean config dir** (`claude-home/`, built automatically: credentials + model pin only — no CLAUDE.md, no memory). If preflight fails on Arm B, your install keeps credentials somewhere other than `~/.claude/.credentials.json` — copy the right file into `claude-home/` manually.
- `GLM_API_KEY` (or `ZAI_API_KEY`) present in `~/.hermes/.env` (Arm C + GLM judge call `https://api.z.ai/api/coding/paas/v4` directly).
- Run **off-peak** (GLM quota burns ~3x at peak; Claude session windows are finite — every stage is resumable, so batches are fine).

## Run it (5 stages, all resumable / idempotent)
```bash
cd ~/Nexus-Agentic-Coding-Setup/benchmarks/added-value

python3 01_collect.py  --run run1                  # corpus → briefs.jsonl (instant, free)
python3 02_generate.py --run run1 --preflight      # connectivity checks, generates nothing
python3 02_generate.py --run run1                  # the 3 arms (the long, token-costing stage)
python3 03_blind.py    --run run1                  # blinded packets + private mapping
python3 04_judge.py    --run run1                  # 2 judge families + pairwise, blind
python3 05_report.py   --run run1 --sample         # 5 packets for YOUR blind review — do first
python3 05_report.py   --run run1                  # unblind + RESULTS.md verdicts
```
Useful flags: `02 --arm B` (one arm at a time), `--limit 5` (smoke run — use a scratch `--run smoke1` so run1 stays complete), `--redo-errors` (retry failures), `04 --only pairwise`.

## What you get
`runs/run1/RESULTS.md`: YES/NO against the three locked thresholds (added value vs Claude Code; harness value vs raw GLM; falsification check), per-arm score/cost/time table, **cost per rubric point**, top dimension deltas (the "what improves"), grounding-flag counts, judge-family agreement, exclusions. `summary.json` holds the same machine-readable.

## Cost & time (rough)
27 briefs × 3 arms ≈ 81 generations + 162 absolute judgments + 108 pairwise ≈ 350 model calls.
Arm A task mode is the slow one (super-result critic rounds; up to 1 h/case timeout — expect several hours wall time, mostly unattended). Arm C ≈ cents. Arm B + judges ride the Claude subscription (session-window limited; the scripts stop cleanly on "session limit" and resume). GLM side: expect a noticeable bite out of a coding-plan window — off-peak strongly advised.

## Interpreting Arm A modes
`config.json → arm_a_mode`:
- `task` (default) = the full product (framing + grounded critic + retry loop). This is the claim being tested.
- `evals` = framing-only single pass (cheaper; understates Nexus). RESULTS.md labels which mode ran — don't compare across modes.

## Cleanup / hygiene
- Arm A task mode leaves `[BENCH]`-titled tasks on the board (kept as audit evidence; delete from the Kanban when done).
- Benchmark session tokens minted for API auth are not auto-destroyed (same-machine trust, like the verify gates); they expire with normal session hygiene.
- `runs/` and `claude-home*/` are gitignored — commit the harness + PREREGISTRATION, not artifacts. Copy the final `RESULTS.md` somewhere permanent (e.g. `~/knowledge/research/`) when a run completes.

## Honest limitations
n=1 per brief/arm; business-deliverable corpus only (no coding tasks — that's phase 2 with test-suite ground truth); judge families overlap generator families (mitigated by two families + order-swapped pairwise + your 5-packet human review, not eliminated); Arm B deliberately has no business brain — the report says how much of any win is context vs orchestration cannot be separated in this design.
