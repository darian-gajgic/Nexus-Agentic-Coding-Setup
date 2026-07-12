# Bench-02 Results — real-world webshop benchmark

Status: ⬜ not run yet. Fill while following RUNBOOK.md. Log live, don't reconstruct.

## Config

| | |
|---|---|
| Date run | |
| Claude Code version | |
| Nexus commit | |
| Prompt variant used (same for ALL arms) | PROMPT-B / PROMPT-A |
| Nexus run-1 config | Super Result OFF, 🚀 Full Auto, 🧠 Smart |
| Arms | Fable-5-direct (interactive), Opus-4.8-direct (interactive), Nexus |

## Scoreboard

Functional score = count of ✅ in the arm's checklist below. Personas = how many of P1–P3 passed without a sanity flag. Tokens & $: claude_session_cost.py TOTAL (arms 1–2) / collect_nexus.py ledger (arm 3, GLM + frontier). Wall-clock includes your answer latency (same client, all arms). Questions asked = from the Q&A logs (a signal, not a score — judge axis 5 weighs how well gaps were handled).

| Arm | Functional | Personas | Catalog size | PPTX slides | Questions asked | Wall-clock | Tokens | API-equiv $ | Judge rank |
|---|---|---|---|---|---|---|---|---|---|
| Fable 5 direct | /10 | /3 | | | | | | | |
| Opus 4.8 direct | /10 | /3 | | | | | | | |
| Nexus run 1 (Smart, no SR) | /10 | /3 | | | | | | | |

## Arm 1 — Fable 5

started at: — finished at:

### Q&A log (every question it asked; A = your answer; mark off-sheet answers)

1. Q: — A:

### Functional checklist (Phase E)

| # | Check | Result (✅/❌ + note) |
|---|---|---|
| 1 | README install commands work as written | |
| 2 | App starts per README | |
| 3 | Catalog browsable; ≥40 products | count: |
| 4 | Categories cover GPU/CPU/board/RAM/PSU/storage/cooling/case | |
| 5 | Products are real with plausible specs (eyeball) | |
| 6 | P1 (Llama 70B): complete list, no sanity flag | |
| 7 | P2 (starter, 1200 €): complete, respects budget | |
| 8 | P3 (Flux + 13B): complete, no sanity flag | |
| 9 | PPTX generated per recommendation & downloads | |
| 10 | pptx_check.py: VALID, slides match a real setup guide | SLIDES= |

### Raw captures

```
(/cost)

(/status usage line)

(claude_session_cost.py output)
```

## Arm 2 — Opus 4.8

started at: — finished at:

### Q&A log

1. Q: — A:

### Functional checklist (same 10 rows)

| # | Check | Result |
|---|---|---|
| 1 | README install commands work | |
| 2 | App starts | |
| 3 | Catalog ≥40 | count: |
| 4 | Category coverage | |
| 5 | Real products, plausible specs | |
| 6 | P1 | |
| 7 | P2 | |
| 8 | P3 | |
| 9 | PPTX generated & downloads | |
| 10 | pptx_check.py VALID | SLIDES= |

### Raw captures

```
```

## Arm 3 — Nexus run 1 (SR OFF, Full Auto, 🧠 Smart)

started at: — finished at:
Suggested spend profile the tool proposed (before your Smart override):
Deep Plan used: yes/no (offered by tool / clicked manually / not offered)
Workflow or single task (id):
Interventions (blocked Decision cards you approved):

### Q&A log (wizard/interview questions)

1. Q: — A:

### Functional checklist (same 10 rows)

| # | Check | Result |
|---|---|---|
| 1 | README install commands work | |
| 2 | App starts | |
| 3 | Catalog ≥40 | count: |
| 4 | Category coverage | |
| 5 | Real products, plausible specs | |
| 6 | P1 | |
| 7 | P2 | |
| 8 | P3 | |
| 9 | PPTX generated & downloads | |
| 10 | pptx_check.py VALID | SLIDES= |

### Raw captures (collect_nexus.py full output incl. ledger)

```
```

## Judge verdict (blind, Fable 5 — static review + web spot-checks)

```
(scores + ranking)

mapping: X= Y= Z=
```

## Caveats (binding)

- **n = 1 per arm per config.** First impression only — no feature/pricing decisions from this run (master plan C-10). The full Phase-8 campaign decides anything real.
- **Interactive protocol:** you answered questions live from ANSWER-SHEET. The information was identical and only obtainable by asking — but your presence means this is not a fully controlled experiment, and you know which arm is which (the judge session is the only blind element).
- **Compare dollars, not tokens** (tokenizer differences; all $ are API-equivalent comparisons, not bills — Claude arms bill the subscription, Nexus GLM the Z.AI plan; any Nexus frontier spend shows in the ledger's frontier fields).
- **Judge**: static review + web spot-checks only (operator did the live testing); Fable 5 judging Fable 5 output has self-preference — functional checklist + personas are the primary signal, judge is the quality/intelligence color.
- **Wall-clock** includes operator answer latency and, for Claude arms, permission-approval time — treat as soft signal.
- **Runs 2–3** (Balanced, SR ON) compare against the SAME frozen Claude baselines; Nexus's learning loops mean later runs benefit from earlier ones — improvements are config + learning, not config alone.

## Verdict (fill after analysis)

- Quality:
- Cost:
- Questions/planning quality:
- First impression vs the Claude arms:
- Go/no-go for run 2 (Balanced) and run 3 (SR):
