# Bench-03 Results — marketing campaign benchmark

Status: ⬜ not run yet. Fill while following RUNBOOK.md. Log live.

## Config

| | |
|---|---|
| Date run | |
| Claude Code version | |
| Nexus commit | |
| Prompt variant (same for ALL arms) | PROMPT-B / PROMPT-A |
| Nexus config | Super Result OFF, 🚀 Full Auto, 🧠 Smart |
| Symmetry rule respected (no project attach, empty dirs) | |

## Scoreboard

Functional = ✅ count from the arm's checklist. Sources = verified real / total spot-checked. Posts = ready-to-post pieces with copy + visual. Tokens & $: cost scripts as in bench-02.

| Arm | Functional | Sources ok | Posts ready | Questions asked | Wall-clock | Tokens | API-equiv $ | Judge rank |
|---|---|---|---|---|---|---|---|---|
| Fable 5 direct | /10 | | | | | | | |
| Opus 4.8 direct | /10 | | | | | | | |
| Nexus (Smart, no SR) | /10 | | | | | | | |

## Functional checklist (fill one per arm; rows anchored on the marketing RUBRIC's objective gates)

Copy this block three times below — Arm 1 (Fable 5), Arm 2 (Opus 4.8), Arm 3 (Nexus).

| # | Check | Result (✅/❌ + evidence) |
|---|---|---|
| 1 | Overview/index doc exists, inventories everything, states usage order + own decisions | |
| 2 | Strategy names a measurable objective AND a specific audience segment (gates 1+4) | |
| 3 | Step-by-step guide executable by a non-marketer (numbered, tools named, realistic hours) | |
| 4 | "Why this strategy" backed by ≥3 real checkable sources/examples | |
| 5 | ≥5 ready-to-post pieces with FINAL copy in the market's language (if asked → German) | |
| 6 | Every post has a usable visual asset and/or an exact image-generation prompt | |
| 7 | One primary CTA per asset; zero placeholder debris (`{{`/TODO/lorem) (gates 2+10) | |
| 8 | Nothing fabricated: stats carry source+year, no invented testimonials (gate 6) — spot-checked | |
| 9 | Budget/channel plan fits the constraints (if asked → 500 €/mo + 5–8 h/wk; else documented assumption) | |
| 10 | Measurement plan: KPIs named + how to track them | |

### Arm 1 — Fable 5
started at: — finished at:
Q&A log:
1. Q: — A:

(checklist)

Raw captures:
```
```

### Arm 2 — Opus 4.8
started at: — finished at:
Q&A log:
1. Q: — A:

(checklist)

Raw captures:
```
```

### Arm 3 — Nexus
started at: — finished at:
Tool's own suggested spend profile / Deep Plan offered?:
Workflow or task (id):
Interventions:
Q&A log:
1. Q: — A:

(checklist)

Raw captures (collect_nexus.py output incl. ledger):
```
```

## Judge verdict (blind, Fable 5 — rubric gates + 5 axes + web source verification)

```
(gate results, scores, ranking)

mapping: X= Y= Z=
```

## Caveats (binding)

- n = 1 per arm — first impression, no decisions (C-10). Same interactive-protocol caveats as bench-02 (identical info only via asking; operator not blind; wall-clock soft).
- Compare dollars, not tokens.
- Both Claude arms load the machine's global CLAUDE.md, which points to `~/knowledge` (the business brain); Nexus has the same knowledge via its per-user framing. Arms are compared as configured whole systems — that's intentional, note anything an arm actually did with it.
- Judge: Fable 5 self-preference applies; the RUBRIC gate results and your source spot-checks are the objective backbone, the axis scores are color.
- Image generation: no arm has a real image model; "visuals" are graded as usable-asset-or-exact-prompt, per the brief/answer-sheet fallback.

## Verdict (fill after analysis)

- Quality:
- Research depth:
- Cost:
- vs bench-02 picture (does the tool's value show more in content/research than code?):
- Go/no-go for a Balanced / SR run of bench-03:
