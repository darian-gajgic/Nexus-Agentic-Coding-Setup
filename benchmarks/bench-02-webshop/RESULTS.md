# Bench-02 Results — real-world webshop benchmark

Status: 🟡 in progress — Arms 1+2 (Claude) FINISHED and cost-captured; Arm 3 (Nexus, attempt 3) running since 00:25. Phase E functional testing pending until all arms done.

## Config

| | |
|---|---|
| Date run | 2026-07-12 → 2026-07-13 (overnight) |
| Claude Code version | 2.1.207 |
| Nexus commit | `a7f782f` (incl. the judge-scope fix shipped MID-benchmark after attempt 2 — see Notes 3/6) |
| Prompt variant used (same for ALL arms) | PROMPT-B |
| Nexus run-1 config | Super Result OFF, 🚀 Full Auto, 🧠 Smart |
| Arms | Fable-5-direct (interactive), Opus-4.8-direct (interactive), Nexus |

## ⚠ Folder-swap incident (resolved — attribution verified)

The two Claude sessions were launched with crossed `--model` flags relative to their folders: the session in `~/benchmarks/bench-02/fable5/` actually ran `claude-opus-4-8` and vice versa. Verified three ways: transcript model IDs, the 68-product Node/Express app matching the operator's Arm-2 notes (incl. its PDF guide), and the Python/FastAPI app with `pptx_export.py` matching Arm-1's PowerPoint note. **All entries in this file are attributed BY MODEL (correct as written by the operator); the folders were renamed at 00:55 to match** — `fable5/` = the Python/FastAPI app (built by Fable 5), `opus48/` = the Node/Express app (built by Opus 4.8).

## Scoreboard

Functional score = count of ✅ in the arm's checklist below. Personas = how many of P1–P3 passed without a sanity flag. Tokens & $: claude_session_cost.py TOTAL (arms 1–2) / collect_nexus.py ledger (arm 3, GLM + frontier). Wall-clock from transcripts (arms 1–2). Questions asked = from the Q&A logs.

| Arm | Functional | Personas | Catalog size | PPTX slides | Questions asked | Wall-clock | Tokens | API-equiv $ | Judge rank |
|---|---|---|---|---|---|---|---|---|---|
| Fable 5 direct | /10 | /3 | ~59 (catalog.json, verify in Phase E) | | 0 | 34.1 min | 7,108,026 | $16.48 | |
| Opus 4.8 direct | /10 | /3 | 68 | (PDF, not PPTX — see notes) | 0 | 51.3 min | 14,521,076 | $13.71 | |
| Nexus run 1 (Smart, no SR) | /10 | /3 | | | 3 (Deep Plan interview) | | | | |

Early cost observation: Fable 5 used half the tokens of Opus 4.8 but cost MORE in API-equivalent $ (2× per-token rates) — compare dollars, not tokens.

## Arm 1 — Fable 5 (app: Python/FastAPI + vanilla frontend + python-pptx; folder `fable5/`)

started at: 22:22 — finished at: 22:59 (transcript wall-clock 34.1 min)

### Q&A log (every question it asked; A = your answer; mark off-sheet answers)

None — proceeded without asking any questions (all gaps filled by its own assumptions).

### Functional checklist (Phase E)

| # | Check | Result (✅/❌ + note) |
|---|---|---|
| 1 | README install commands work as written | |
| 2 | App starts per README | |
| 3 | Catalog browsable; ≥40 products | count: (~59 per catalog.json — verify) |
| 4 | Categories cover GPU/CPU/board/RAM/PSU/storage/cooling/case | |
| 5 | Products are real with plausible specs (eyeball) | |
| 6 | P1 (Llama 70B): complete list, no sanity flag | |
| 7 | P2 (starter, 1200 €): complete, respects budget | |
| 8 | P3 (Flux + 13B): complete, no sanity flag | |
| 9 | PPTX generated per recommendation & downloads | |
| 10 | pptx_check.py: VALID, slides match a real setup guide | SLIDES= |

### Result notes (operator):
No pictures of the products.
I cant click on a product for more detailes, just see price, a few tags and a description, not how you do a webshop.
The powerpoint does not look modern or well made, looks old and cheap, presenting this to a client would not be good.
The correctness of the numbers and specs need to be checked, I am not sure if they are correct.

### Raw captures

```
claude_session_cost.py (session 5f0f4495…):
model                            input    output    cache-rd  cache-w5m  cache-w1h       USD
claude-fable-5                     101    125411     6812801          0     169713   16.4786
TOTAL tokens=7108026  API-equivalent USD=16.4786  user-turns=83  wall-clock 34.1 min
```

## Arm 2 — Opus 4.8 (app: Node/Express; folder `opus48/`)

started at: 22:18 — finished at: 23:05 (transcript wall-clock 51.3 min)

### Q&A log

No questions asked.

### Functional checklist (same 10 rows)

| # | Check | Result |
|---|---|---|
| 1 | README install commands work | yes |
| 2 | App starts | yes |
| 3 | Catalog ≥40 | count: 68 |
| 4 | Category coverage | 8 |
| 5 | Real products, plausible specs | |
| 6 | P1 | |
| 7 | P2 | |
| 8 | P3 | |
| 9 | PPTX generated & downloads | ⚠ produces a PDF, not a PowerPoint — brief explicitly asked for PowerPoint |
| 10 | pptx_check.py VALID | n/a (PDF) |

### Result notes (operator):
No pictures of the products.
I cant click on a product for more detailes, just see price, a few tags and a description, not how you do a webshop.
The pdf does not look modern or well made, looks old and cheap, presenting this to a client would not be good.
The correctness of the numbers and specs need to be checked, I am not sure if they are correct.

### Raw captures

```
claude_session_cost.py (session 9ee96889…):
model                            input    output    cache-rd  cache-w5m  cache-w1h       USD
claude-opus-4-8                  17853    165136    14093448          0     244639   13.7108
TOTAL tokens=14521076  API-equivalent USD=13.7108  user-turns=83  wall-clock 51.3 min
```

## Arm 3 — Nexus run 1 (SR OFF, Full Auto, 🧠 Smart) — ATTEMPT 3 (the scored run)

Project `benchmark3`, workflow `local-ai-hardware-webshop` (`wf-0bf075d2`), 5-stage pipeline.
created at: 00:16 — tasks held stopped 00:16→00:25 for environment cleanup (gateway restart, old-run purge) — dispatch started: 00:25 — finished at:
(Subtract the 9-min hold from wall-clock.)
Suggested spend profile the tool proposed (before your Smart override): Smart
Deep Plan used: yes, clicked manually.
Interventions (blocked Decision cards you approved):

### Q&A log (wizard/interview questions)

1. Q: What tech stack should the demo use?
A: FastAPI (Python) backend + vanilla HTML/CSS/JS frontend, python-pptx for the deck

2. Q: How sophisticated should the recommendation engine's hardware math be?
A: Quantization-aware with tiered builds: compute VRAM at 4-bit/8-bit/FP16, offer budget/balanced/premium variants

3. Q: How strict should cross-part compatibility validation be in each recommendation?
A: Full checks: CPU socket↔motherboard, PSU wattage ≥ system draw, RAM type/speed↔motherboard, case GPU-length clearance

(Off-sheet note: these three answers go beyond the ANSWER-SHEET canon — they specify engine sophistication the Claude arms never got, because they never asked. That's the interactive protocol working as designed, but the comparison must weigh it: Nexus obtained a materially better spec through asking.)

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

## Final comparison

Run per `FINAL-COMPARISON.md` (fresh Fable 5 session, two-phase: blind technical review first, then de-anonymized synthesis with costs). Paste its verdict here:

```
```

## Caveats (binding)

- **n = 1 per arm per config.** First impression only — no feature/pricing decisions from this run (master plan C-10). The full Phase-8 campaign decides anything real.
- **Interactive protocol:** you answered questions live from ANSWER-SHEET. The information was identical and only obtainable by asking — but your presence means this is not a fully controlled experiment, and you know which arm is which (the judge session is the only blind element).
- **Compare dollars, not tokens** (tokenizer differences; all $ are API-equivalent comparisons, not bills — Claude arms bill the subscription, Nexus GLM the Z.AI plan; any Nexus frontier spend shows in the ledger's frontier fields).
- **Judge**: static review + web spot-checks only (operator did the live testing); Fable 5 judging Fable 5 output has self-preference — functional checklist + personas are the primary signal, judge is the quality/intelligence color.
- **Wall-clock** includes operator answer latency and, for Claude arms, permission-approval time — treat as soft signal.
- **The Nexus arm ran at a different commit than the Claude arms** (judge-scope fix `a7f782f` shipped between attempt 2 and attempt 3 — see Note 3). The Claude arms are unaffected (the fix touches only Nexus's judging harness), but strictly the "system under test" changed mid-benchmark; runs 2–3 stay on the fixed commit.
- **Runs 2–3** (Balanced, SR ON) compare against the SAME frozen Claude baselines; Nexus's learning loops mean later runs benefit from earlier ones — improvements are config + learning, not config alone.

## Verdict (fill after analysis)

- Quality:
- Cost:
- Questions/planning quality:
- First impression vs the Claude arms:
- Go/no-go for run 2 (Balanced) and run 3 (SR):

## Notes:
1. Nexus attempt 1 aborted by operator (protocol errors: missed Q&A logging, approved spec before frontier judge verdict). Attempt 2 (project benchmark2) aborted after it surfaced the judge-scope defect (Note 3). **Attempt 3 = the scored run: project `benchmark3`, workflow `local-ai-hardware-webshop` (`wf-0bf075d2`).**

2. Error: SSE stream reset mid-spec-turn; non-terminal stall guard engaged; run continued and was harvested from transcript.

3. MAJOR TOOL FINDING (attempt 2): the high-stakes frontier judge was evidence-blind (saw only deliverable.md, none of the 16 produced artifacts) AND enforced whole-project SPEC criteria against single pipeline stages → unwinnable REVISE loop; its revision brief even pushed the spec stage into writing the whole app out-of-scope. Cost of discovering it: ~2 judge runs ($1.96, 440k Opus tokens) + roughly 10M GLM tokens across three spec rounds. **Fixed mid-benchmark (`a7f782f`: JUDGE_TASK stage contract + JUDGE_ARTIFACTS copy + cjudge scoping; verify.sh 452→455). Live-fire verification still pending: check the first attempt-3 judge verdict actually references the stage contract/artifacts.**

4. Timeout error on Deep Plan, planning draft turn exceeded the wall-clock cap, recovered via transcript.

5. Operator: persistent "critical hermes error" notifications — the tool must stop surfacing benign stream-reset tracebacks as critical errors; a production tool cannot look like it's crashing when it's working. **Queued as post-benchmark fixes:** (a) handle `ClientConnectionResetError` in the gateway's SSE writer gracefully (expected disconnect, not ERROR-level traceback); (b) task/project deletion must also stop already-orphaned Hermes-side runs (the benchmark2 zombie kept executing with a fallback cwd after deletion).

6. Folder-swap incident (see section above): Claude arms launched with crossed --model flags; verified and folders renamed; no data lost, attribution by model confirmed via transcripts + artifacts.
