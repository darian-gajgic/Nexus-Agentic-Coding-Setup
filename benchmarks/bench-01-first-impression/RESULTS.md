# Bench-01 Results — first-impression benchmark

Status: ⬜ not run yet. Fill this file while following RUNBOOK.md.

## Config

| | |
|---|---|
| Date run | |
| Claude Code version (`claude --version`) | |
| Nexus commit (`git -C ~/nexus-agent-os log -1 --oneline`) | |
| Task | `PROMPT.md` (gridcalc mini spreadsheet engine) |
| Arms | Fable-5-direct, Opus-4.8-direct, Nexus (SR ON, Full Auto + Optimal, model auto-routing) |

## Scoreboard

Sources: Acceptance = `grade.sh` SUMMARY (x/66). Own tests = grade.sh line. LOC = grade.sh line. Wall-clock = claude_session_cost.py line (arms 1–2) / created→completed from collect_nexus.py (arm 3). Tokens & $ = claude_session_cost.py TOTAL (arms 1–2) / collect_nexus.py ledger `total_usd` + glm/frontier tokens (arm 3). Judge rank = Phase F.

| Arm | Acceptance | Own tests | LOC | Wall-clock | Tokens (total) | API-equiv $ | Judge rank | Interventions/notes |
|---|---|---|---|---|---|---|---|---|
| Fable 5 direct | /66 | | | | | | | |
| Opus 4.8 direct | /66 | | | | | | | |
| Nexus (SR, Optimal) | /66 | | | | | | | |

## Arm 1 — raw captures (Fable 5)

```
(/cost output)

(/status usage line)

(claude_session_cost.py output)
```

## Arm 2 — raw captures (Opus 4.8)

```
(/cost output)

(/status usage line)

(claude_session_cost.py output)
```

## Arm 3 — raw captures (Nexus)

```
created at: 

(collect_nexus.py full output: task info + copied line + cost ledger)
```

## Judge verdict (blind, Fable 5)

```
(scores + ranking from Phase F)

mapping: X= Y= Z=
```

## Caveats (binding — from QUALITY-PROGRAM-MASTER-PLAN §7 / C-9 / C-10)

- **n = 1 per arm.** This run gives a first impression only: no win-rates, no CIs, no feature/pricing decisions may be made from it. The full Phase-8 campaign (≥3 seeds × ~12 tasks × 4 arms, exact binomial CIs) is what decides anything.
- **Compare dollars, not tokens** — Claude-5-generation tokenizers emit ~30% more tokens for the same text than GLM's; all $ figures here are API-equivalent comparisons, not bills (Claude arms run on subscription, GLM on the Z.AI plan; Nexus SR critic runs bill the Claude subscription too and appear in the `frontier_*` ledger fields).
- **Judge self-preference**: the qualitative judge is Fable 5 judging (among others) Fable 5 output; position-swapping does not remove self-preference (C-9). The objective acceptance score is the primary signal; the judge verdict is color.
- The two Claude arms carry a small equal overhead from the machine's global CLAUDE.md session-brief; the Nexus arm has its own framing overhead. Arms are compared as whole systems, by design.
- Nexus arm ran with Super Result ON (its headline quality loop) — expected to cost more than a direct pass; the question is whether quality justifies it (§7 success criterion: system quality ≥ direct at cost below one Fable-direct pass).

## Verdict (fill after analysis)

- Quality:
- Cost:
- First impression:
- Decision on running full Phase 8:
