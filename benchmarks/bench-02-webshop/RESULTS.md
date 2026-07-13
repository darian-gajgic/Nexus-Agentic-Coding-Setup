# Bench-02 Results — real-world webshop benchmark

Status: ✅ COMPLETE — all three arms finished; blind reviews + live functional pass + synthesis done 2026-07-13 (analysis session). Full report: `COMPARISON-REPORT.md`. Rows marked *(analysis)* were filled by the analysis session's live functional pass, not the operator.

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
| Fable 5 direct | 8/10 *(analysis)* | 2/3 (P2 ⚠ no budget input, ≈€1,485) | 59 ✅ | 8 (VALID) | 0 | 34.1 min | 7,108,026 | $16.48 | **2nd — 43/50 blind** |
| Opus 4.8 direct | 7/10 *(analysis)* | 1/3 + honest refusals (P2 ⚠ explicit over-cap; P3 ❌ no image models) | 68 ✅ | 9 (VALID .pptx — PDF note not reproducible, see Note 7) | 0 | 51.3 min | 14,521,076 | $13.71 | **1st — 44/50 blind** |
| Nexus run 1 (Smart, no SR) | 6/10 *(analysis)* | 0–1/3 (P1 ⚠ $31k "budget" build; P2 ❌ 26× over; P3 ❌) | 58 ✅ | 5 (VALID, generic content) | 3 (Deep Plan interview) | ~2.5–3.3 h active (23 h span; see Arm 3) | 73.0M GLM + 13.6M frontier | **$241.23** | **3rd — 28/50 blind** |

Early cost observation: Fable 5 used half the tokens of Opus 4.8 but cost MORE in API-equivalent $ (2× per-token rates) — compare dollars, not tokens.

## Arm 1 — Fable 5 (app: Python/FastAPI + vanilla frontend + python-pptx; folder `fable5/`)

started at: 22:22 — finished at: 22:59 (transcript wall-clock 34.1 min)

### Q&A log (every question it asked; A = your answer; mark off-sheet answers)

None — proceeded without asking any questions (all gaps filled by its own assumptions).

### Functional checklist (Phase E)

| # | Check | Result (✅/❌ + note) *(analysis session, live)* |
|---|---|---|
| 1 | README install commands work as written | ⚠ steps 2–5 exact & correct; step 1 `cd .../opus48` is wrong post-rename (folder-swap artifact, Note 7) |
| 2 | App starts per README | ✅ (`.venv/bin/python app.py`, port 5000) |
| 3 | Catalog browsable; ≥40 products | ✅ count: 59 via /api/products |
| 4 | Categories cover GPU/CPU/board/RAM/PSU/storage/cooling/case | ✅ all 8 (12/7/8/8/6/7/6/5) |
| 5 | Products are real with plausible specs (eyeball) | ✅ blind reviewer web-verified 10/10 sampled; no fabrications; minor: CPU tdp_w=package power, A6000 refurb priced rich, **USD not EUR** |
| 6 | P1 (Llama 70B): complete list, no sanity flag | ✅ 2×RTX 3090 = 48 GB vs 46.8 GB (Q4_K_M stated), 1500 W PSU for 1055 W load, $4,451, alternatives offered |
| 7 | P2 (starter, 1200 €): complete, respects budget | ⚠ complete $1,610 (≈€1,485) build, but **no budget input exists in the API/UI** and no cheaper alternative surfaced → sanity flag marginal |
| 8 | P3 (Flux + 13B): complete, no sanity flag | ✅ FLUX known → 1×3090 24 GB, $2,608 (covers a 13B chat model too) |
| 9 | PPTX generated per recommendation & downloads | ✅ /api/guide.pptx, correct MIME |
| 10 | pptx_check.py: VALID, slides match a real setup guide | ✅ VALID SLIDES=8 — tailored: parts+reasons, assembly, Ollama commands, power/care |

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
| 1 | README install commands work | yes (⚠ step-1 `cd fable5` now wrong post-rename — swap artifact, Note 7) |
| 2 | App starts | yes |
| 3 | Catalog ≥40 | count: 68 |
| 4 | Category coverage | 8 |
| 5 | Real products, plausible specs | ✅ *(analysis)* blind reviewer web-verified 8/8 sampled, specs exact; ⚠ price epochs mixed (RAM crisis-priced, SSD/used-3090 pre-crisis) |
| 6 | P1 | ✅ *(analysis)* 2×3090 refurb €4,113, Q4_K_M + q8_0 KV stated, 15/15 checks, honest multi-GPU/refurb warnings, 3 alternatives |
| 7 | P2 | ⚠ *(analysis)* persona free-text not matched (asks for a model name + suggestions); with "Llama 3 8B"+budgetEur 1200 → €1,685, over cap but **explicitly states no complete system fits under €1,200** |
| 8 | P3 | ❌ *(analysis)* KB has 20 LLMs, no image models — Flux cannot be answered |
| 9 | PPTX generated & downloads | ✅ *(analysis)* /api/deck returns a real .pptx (correct MIME; UI saves `ai-rig-setup-<model>.pptx`). **PDF claim not reproducible — no PDF code path exists; see Note 7** |
| 10 | pptx_check.py VALID | ✅ VALID SLIDES=9, 1 media — copy-paste driver/Ollama commands, KV-cache flags, honest caveats, alternatives |

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
created at: 00:16 — tasks held stopped 00:16→00:25 for environment cleanup (gateway restart, old-run purge) — dispatch started: 00:25 — finished at: **23:09 (Jul 13)**.
**Timing (reconstructed from dispatch records):** 21 dispatches summing **3.25 h of active model time** (operator estimate ~2.5 h — some dispatch overlap from stall-recovery). The 23 h span is NOT working time: gaps 02:17→12:51 (overnight stall + operator fix), 13:09→14:53, 15:06→20:31. Stage completions: spec 01:16, implement 20:31, review 21:33, fix 22:19, acceptance 23:09. Deliverable: branch `nexus/0bf075d2` @ `70819ff` in `~/Projects/benchmark3`.
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

| # | Check | Result *(analysis session, live)* |
|---|---|---|
| 1 | README install commands work | ✅ work as written (only arm without a path artifact) |
| 2 | App starts | ✅ uvicorn per README |
| 3 | Catalog ≥40 | ✅ count: 58 |
| 4 | Category coverage | ✅ all 8 (11/9/8/5/7/5/6/7) |
| 5 | Real products, plausible specs | ⚠ blind reviewer found **2 fabricated coolers** (Noctua "NH-U9 TR5-SP6 (sTR5/SP5)" nonexistent; Dynatron L3 mis-specced as SP5/LGA4677 400 W), X13SAE-F RAM slots wrong (8 claimed, 4 real), prices = stale launch MSRPs in USD (RTX 5090 $1,999 vs €3,700+ street; 32 GB DDR5 $119 vs €400+) |
| 6 | P1 | ⚠ complete + VRAM-sufficient (94 GB ≥ 43 GB) and all 4 checks pass — but "budget" = **1× H100 NVL $30,000, total $31,023**; balanced identical; premium = 3×H100+A100 = **$106,243** (pads to exactly 4 GPUs per SPEC R11b); passive datacenter card in a consumer B650 tower |
| 7 | P2 | ❌ budget tier for Llama 3 8B (5 GB demand) = same **$31,023 H100 build** — 26× the €1,200 budget; catalog's own $499 RTX 4060 Ti 16GB would satisfy it; every budget/balanced build in the shop is $31,023 |
| 8 | P3 | ❌ `unknown_model` — KB is 10 text LLMs (2024-era: Llama 3, Qwen2, Phi-3, Gemma 2, DeepSeek-V2), no image models |
| 9 | PPTX generated & downloads | ✅ /api/guide returns real .pptx |
| 10 | pptx_check.py VALID | ✅ VALID SLIDES=5 — but generic content (same assembly/software text for every build; "Install Ubuntu 22.04") |

Own tests: 99/99 pytest + acceptance suite (its pipeline verdict: PASS). Green tests coexisted with all of the above — the suite pins spec compliance, not product sense.

### Raw captures (collect_nexus.py full output incl. ledger)

```
--- workflow wf-0bf075d2: local-ai-hardware-webshop [active] ---
wall-clock (first task created -> last completed): 1385.4 min   <-- span, NOT active time; see Timing above
  task-ebf6f61a [done] Spec & plan          ledger: glm 16,957,672 tok $49.18 | frontier 2,798,057 tok $8.02  | $57.20
  task-b4cc3b5c [done] Implement + tests    ledger: glm 24,980,107 tok $72.44 | frontier 3,232,883 tok $8.15  | $80.60
  task-c632f050 [done] Code review          ledger: glm  4,556,366 tok $13.21 | frontier 2,649,558 tok $5.31  | $18.52
  task-3c91a001 [done] Fix review findings  ledger: glm 13,661,661 tok $39.62 | frontier 3,325,470 tok $4.51  | $44.13
  task-96f60f53 [done] Acceptance verify    ledger: glm 12,875,955 tok $37.34 | frontier 1,588,815 tok $3.44  | $40.78
--- workflow cost ledger (API-equivalent USD) ---
{ "tasks": 5, "glm_tokens": 73031761, "glm_usd": 211.7921,
  "frontier_tokens": 13594783, "frontier_usd": 29.4399,
  "total_usd": 241.232, "currency": "API-equivalent USD" }
Judge rounds: spec 2 versions; implement SHIP r1; review REVISE,REVISE,SHIP; fix REVISE,SHIP; acceptance REVISE,SHIP.
```

## Judge verdict (blind, Fable 5 — static review + web spot-checks)

```
Three blind Fable-5 reviewers, one per anonymized solution (letters shuffled, mapping
opened only after all reviews returned). Scores 1-10 per axis
(conformance / engine depth / data accuracy / SOTA+practices / polish):

  X = 9 / 9 / 8 / 8 / 9  = 43/50
  Y = 7 / 4 / 5 / 6 / 6  = 28/50
  Z = 9 / 9 / 8 / 9 / 9  = 44/50

Ranking: Z (Opus 4.8) > X (Fable 5) > Y (Nexus)  — near-tie at the top, big gap to Y.
Note: Fable-5 reviewers ranked the non-Fable solution first (self-preference did not
dominate). Full evidence tables in COMPARISON-REPORT.md.

mapping: X=fable5  Y=nexus  Z=opus48
```

## Final comparison

Run per `FINAL-COMPARISON.md` (two-phase: blind technical review first, then de-anonymized synthesis with costs). Executed 2026-07-13 in the analysis session (blind phase via three isolated subagent reviewers). Verdict:

```
1. Opus 4.8 direct  — 44/50 blind, $13.71, 51.3 min. Deepest engine (offload modeling,
   KV-precision search, calibrated tok/s, 15-check validation), current knowledge,
   cheapest. Weakness: no image models (P3 fails), mixed price epochs.
2. Fable 5 direct   — 43/50 blind, $16.48, 34.1 min. Broadest KB (27 models incl.
   FLUX/Whisper — only arm to pass P3), most consistent 2026 shortage pricing, fastest.
   Weakness: USD for a German client, no budget input, slightly shallower search.
3. Nexus run 1      — 28/50 blind, $241.23 API-equiv, ~2.5-3.3 h active. Real process
   discipline (README works as written, 99 green tests, auditable DECISIONS trail) but
   the product is not client-presentable: every "budget" build is a $31,023 H100 rig,
   premium pads to 4 GPUs ($106k-121k), 2 fabricated products, 2024-era model KB,
   no cart, skeletal deck. §7 criterion missed on both axes (quality < direct at ~15x
   the cost ceiling).

Root cause of the Nexus gap (full anatomy in COMPARISON-REPORT.md): the pipeline saw
the absurdity (review finding F3 "cost-disproportionate greedy") and buried it as "a
spec limitation... spec amendment decided by the operator" — no Decision card ever
reached the operator; the judge instead PINNED the bad rule (R11b) as a falsifiable
contract. Compliance machinery worked; product judgment had no seat at the table.
```

## Caveats (binding)

- **n = 1 per arm per config.** First impression only — no feature/pricing decisions from this run (master plan C-10). The full Phase-8 campaign decides anything real.
- **Interactive protocol:** you answered questions live from ANSWER-SHEET. The information was identical and only obtainable by asking — but your presence means this is not a fully controlled experiment, and you know which arm is which (the judge session is the only blind element).
- **Compare dollars, not tokens** (tokenizer differences; all $ are API-equivalent comparisons, not bills — Claude arms bill the subscription, Nexus GLM the Z.AI plan; any Nexus frontier spend shows in the ledger's frontier fields).
- **Judge**: static review + web spot-checks only (operator did the live testing); Fable 5 judging Fable 5 output has self-preference — functional checklist + personas are the primary signal, judge is the quality/intelligence color.
- **Wall-clock** includes operator answer latency and, for Claude arms, permission-approval time — treat as soft signal.
- **The Nexus arm ran at a different commit than the Claude arms** (judge-scope fix `a7f782f` shipped between attempt 2 and attempt 3 — see Note 3). The Claude arms are unaffected (the fix touches only Nexus's judging harness), but strictly the "system under test" changed mid-benchmark; runs 2–3 stay on the fixed commit.
- **Runs 2–3** (Balanced, SR ON) compare against the SAME frozen Claude baselines; Nexus's learning loops mean later runs benefit from earlier ones — improvements are config + learning, not config alone.

## Verdict (filled 2026-07-13, analysis session)

- **Quality:** Opus 4.8 ≳ Fable 5 ≫ Nexus. The Claude arms are near-tied (44 vs 43/50 blind; Opus deeper engine, Fable broader KB + only P3 pass); Nexus (28/50) is not client-presentable: $31k "budget" builds, fabricated catalog entries, two-year-stale models, skeletal deck.
- **Cost:** Opus $13.71 < Fable $16.48 ≪ Nexus $241.23 (API-equivalent). Nexus = **17.6× Opus** for the weakest deliverable; its spec stage alone ($57.20) out-cost an entire direct run.
- **Questions/planning quality:** Nexus's interview was the only planning signal (3 good engineering questions → materially richer engine spec) but missed the product questions that mattered (which models, currency, what "budget" means) — and the richer spec was then squandered by a compliance-optimizing pipeline. The Claude arms asked nothing yet made mostly sensible, documented assumptions.
- **First impression vs the Claude arms:** a fresh customer would use either Claude arm's shop and might buy from it; the Nexus shop would lose them at the first recommendation. Nexus's visible strengths are process artifacts (SPEC/PLAN/DECISIONS, green suites) the customer never sees.
- **Go/no-go for run 2 (Balanced) and run 3 (SR):** **GO, gated.** First land tool fixes for the three defect classes config can't fix: (1) product-sanity judge axis (drive the app with personas, judge outcomes), (2) spec-level findings must raise operator Decision cards, (3) mandatory live web research + anti-fabrication spot-checks for data-bearing briefs. Then run 2/3 vs the SAME frozen Claude baselines, labeled "config + learning + tool fixes". Details: COMPARISON-REPORT.md recommendations 1–12.

## Notes:
1. Nexus attempt 1 aborted by operator (protocol errors: missed Q&A logging, approved spec before frontier judge verdict). Attempt 2 (project benchmark2) aborted after it surfaced the judge-scope defect (Note 3). **Attempt 3 = the scored run: project `benchmark3`, workflow `local-ai-hardware-webshop` (`wf-0bf075d2`).**

2. Error: SSE stream reset mid-spec-turn; non-terminal stall guard engaged; run continued and was harvested from transcript.

3. MAJOR TOOL FINDING (attempt 2): the high-stakes frontier judge was evidence-blind (saw only deliverable.md, none of the 16 produced artifacts) AND enforced whole-project SPEC criteria against single pipeline stages → unwinnable REVISE loop; its revision brief even pushed the spec stage into writing the whole app out-of-scope. Cost of discovering it: ~2 judge runs ($1.96, 440k Opus tokens) + roughly 10M GLM tokens across three spec rounds. **Fixed mid-benchmark (`a7f782f`: JUDGE_TASK stage contract + JUDGE_ARTIFACTS copy + cjudge scoping; verify.sh 452→455). Live-fire verification still pending: check the first attempt-3 judge verdict actually references the stage contract/artifacts.**

4. Timeout error on Deep Plan, planning draft turn exceeded the wall-clock cap, recovered via transcript.

5. Operator: persistent "critical hermes error" notifications — the tool must stop surfacing benign stream-reset tracebacks as critical errors; a production tool cannot look like it's crashing when it's working. **Queued as post-benchmark fixes:** (a) handle `ClientConnectionResetError` in the gateway's SSE writer gracefully (expected disconnect, not ERROR-level traceback); (b) task/project deletion must also stop already-orphaned Hermes-side runs (the benchmark2 zombie kept executing with a fallback cwd after deletion).

6. Folder-swap incident (see section above): Claude arms launched with crossed --model flags; verified and folders renamed; no data lost, attribution by model confirmed via transcripts + artifacts.

7. Post-analysis reconciliations (2026-07-13): (a) the Arm-2 "PDF, not PPTX" note could NOT be reproduced — `/api/deck` returns a valid 9-slide `.pptx` with correct MIME and the UI saves `*.pptx`; no PDF code path exists in the repo. Likely a swap-night mix-up; operator should re-check once. (b) Both Claude READMEs contain a `cd` to the folder they RAN in, which the post-incident rename made wrong (fable5's README says `cd .../opus48` and vice versa) — an incident artifact, not a model error; graded as ⚠ not ❌. (c) Operator's "deck looks old and cheap" vs blind reviewers' high deck scores: both true — content/structure is strong (esp. Opus), visual template design is plain in all three arms.

8. Nexus run overlapped further main-repo fixes on Jul 13 (judge-loop overhaul commits landed while attempt 3 ran) — system under test was not frozen; treat run-1 numbers as "at moving HEAD". Rule for runs 2–3: freeze the commit; a mid-run tool fix restarts (or taints) the run.
