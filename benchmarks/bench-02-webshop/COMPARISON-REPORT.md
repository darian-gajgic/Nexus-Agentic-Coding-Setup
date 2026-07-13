# Bench-02 Final Comparison Report — real-world webshop benchmark

**Date of analysis:** 2026-07-13 (all three arms finished)
**Analysis session:** Fable 5 (this file), with three *blind* Fable-5 review subagents for Phase 1 (each saw only one anonymized solution + the brief; letters X/Y/Z shuffled by `prepare_judge.sh`)
**Protocol:** `FINAL-COMPARISON.md` (Phase 1 blind review → Phase 2 de-anonymized synthesis), plus a live functional pass (all three apps started and driven through the ANSWER-SHEET personas by this session)

## ⚠ Binding caveats — read first

- **n = 1 per arm.** Directional only. No feature/pricing/product decisions may be based on this run (master plan C-10). The full Phase-8 campaign decides anything real.
- **Self-preference:** the blind reviewers and this synthesis run on Fable 5, and one arm *is* Fable 5. Blinding limits but does not eliminate this. (As it turned out, the reviewers ranked the Opus arm #1, slightly ahead of the Fable arm — which argues the blind reviews were not simply self-flattering.)
- **The Nexus arm ran at a later commit than the Claude arms** (`a7f782f`, judge-scope fix shipped mid-benchmark), and further main-repo fixes were made *while attempt 3 was running*. The system under test was not frozen.
- **Wall-clock is soft** for all arms (operator answer latency, permission approvals, and for Nexus a ~10.5 h overnight stall + operator fix + re-drive).
- **Compare dollars, not tokens** — API-equivalent $; no arm was billed these amounts (Claude subscription / Z.AI plan).

---

# Phase 1 — blind technical review (scores by blind reviewers)

Letters as reviewed: **X** = `fable5` (Flask "CoreStack"), **Y** = `nexus` (FastAPI "Local AI Hardware Shop"), **Z** = `opus48` (Node/Express "AI-Rig Store"). Mapping was opened only after all three reviews returned.

## Score matrix (1–10 per axis)

| Axis | X (Fable 5) | Y (Nexus) | Z (Opus 4.8) |
|---|---|---|---|
| 1a Conformance | 9 | 7 | 9 |
| 1b Engine depth | 9 | **4** | 9 |
| 1c Data accuracy (web-verified) | 8 | **5** | 8 |
| 1d SOTA & practices (web-verified) | 8 | 6 | 9 |
| 1e Polish | 9 | 6 | 9 |
| **Total** | **43/50** | **28/50** | **44/50** |

## What the blind reviewers established (condensed; full evidence in their reports)

**X — Fable 5 / Flask "CoreStack" (59 products, 27-model KB).**
A genuine constraint solver: the reviewer reproduced the Llama-3-70B math by hand to the dollar (42.36 GB weights at the *empirically correct* 0.60 B/param Q4_K_M ratio, KV within 8% of the analytic figure, 2×RTX 3090 pick, 1500 W PSU with real 16-pin connector-count pruning, $4,451 total = README claim = screenshot). 10/10 sampled products exist with correct specs; prices track the verified July-2026 shortage market almost exactly — **but in USD for a German/EUR client**. Honest infeasibility for 405B/671B. 54 meaningful tests. Debits: README step 1 `cd` path is machine-specific (folder-swap artifact), no Llama 4 in KB, FLUX.1 labeled SOTA when FLUX.2 is out, CPU `tdp_w` holds package power, deps range-pinned.

**Y — Nexus / FastAPI "Local AI Hardware Shop" (58 products, 10-model KB).**
Real engine mechanics (sourced VRAM formula, 5 compat rules, tiered INT4/INT8/FP16) — but the GPU sort is **VRAM-DESC with no cost objective**, so *every* build in the shop leads with the $30,000 H100 NVL: a Phi-3-Mini "budget" build is $31,023 while the catalog's own $499 RTX 4060 Ti meets the demand; premium pads unconditionally to 4 GPUs (~$105–121k) per spec rule R11b. No PCIe-slot/platform rule → 4 passive datacenter cards "validate" onto a consumer B650 board with a $199 CPU and 32 GB RAM; ~20 server/HEDT catalog items are unreachable dead inventory. **Two fabricated cooler products** (a "Noctua NH-U9 TR5-SP6 (sTR5/SP5)" that doesn't exist; a "Dynatron L3 (SP5/LGA4677)" that is really a ≤195 W consumer cooler), one wrong mobo spec (X13SAE-F: 8 RAM slots claimed, 4 real), USD prices 2–4× off the mid-2026 German market (RTX 5090 at $1,999 launch-MSRP vs €3,700–4,000 street; 32 GB DDR5 at $119 vs €400–460 Speicherkrise), and a **two-generation-stale model KB** (Llama 3 / Qwen2 / Phi-3 / Gemma 2 / DeepSeek-V2; no image models at all). Strong test/process discipline (99 unit/integration tests + frozen acceptance suite, one-command `run_all.sh`) — which actively *defends* the flawed design because the spec froze it.

**Z — Opus 4.8 / Node "AI-Rig Store" (68 products, 20-model KB).**
The deepest engine: enumerates quant × KV-precision × GPU × count × platform (~300–900 candidates), models **partial offload** honestly, searches KV-cache precision because it buys fitting 70B on 2×24 GB (exactly how practitioners do it), calibrates tok/s against community reports (16 tok/s for the traced build; reviewer reproduced €4,113 to the euro), 15-check independent re-validation incl. PSU *connectors* and DIMM type. No fabricated products found; specs exact down to the WRX90E's x8-mode 7th slot. Debits: **price-epoch inconsistency** (RAM at crisis prices, SSDs/used-3090 at pre-crisis prices), a provable ~€100 greedy-platform miss on the flagship build, no Llama 4/Qwen3-Coder at the KB frontier, README `cd` artifact.

---

# Phase 2 — functional pass (this session, live), operator reconciliation, costs

## Functional checklist (Phase E, driven live via each app's API/UI paths)

| # | Check | Fable 5 | Opus 4.8 | Nexus |
|---|---|---|---|---|
| 1 | README install/start commands work as written | ⚠ steps fine, but step-1 `cd` points at the wrong folder (swap artifact) | ⚠ same artifact (`cd fable5`) | ✅ work as written |
| 2 | App starts per README | ✅ | ✅ | ✅ |
| 3 | Catalog browsable, ≥40 products | ✅ 59 | ✅ 68 | ✅ 58 |
| 4 | Categories cover all 8 | ✅ | ✅ | ✅ |
| 5 | Real products, plausible specs | ✅ 10/10 sampled web-verified | ✅ 8/8 sampled web-verified | ⚠ 2 fabricated coolers, 1 wrong spec, stale MSRP prices |
| 6 | P1 (Llama 3 70B) complete, no sanity flag | ✅ 2×3090 48 GB, Q4 stated, $4,451 | ✅ 2×3090, €4,113, 15/15 checks | ⚠ complete & VRAM-sufficient, but "budget"=$31,023 (H100 NVL), premium=$106,243 |
| 7 | P2 (starter, 1200 €) | ⚠ $1,610 (≈€1,485) — **no budget input exists**, no cheaper alt surfaced | ⚠ €1,685, over cap **but explicitly honest** ("no complete system fits under €1,200") | ❌ budget tier = **$31,023** (26× budget; $499 GPU in catalog would do) |
| 8 | P3 (Flux + 13B) | ✅ FLUX build $2,608 (24 GB covers a 13B too) | ❌ no image models in KB — cannot answer | ❌ `unknown_model` — no image models |
| 9 | PPTX generated per recommendation & downloads | ✅ | ✅ (real `.pptx` — see PDF note below) | ✅ |
| 10 | pptx_check.py | ✅ VALID SLIDES=8, tailored content | ✅ VALID SLIDES=9, 1 media, copy-paste commands + caveats | ✅ VALID SLIDES=5, generic assembly/software text, "Install Ubuntu 22.04" |

**Own test suites:** Fable 54/54 · Opus 34/34 · Nexus 99/99 (+ separate acceptance suite, PASS verdict in its pipeline). All green — note that green tests said nothing about the quality gap above.

**Personas without a sanity flag:** Fable 5 **2/3** (P2 marginal-over with no budget mechanism) · Opus 4.8 **1/3 + one honest-refusal** (P2 over cap but explicit; P3 no answer possible) · Nexus **0–1/3** (P1 formally passes the flag list but is economically absurd; P2 hard fail; P3 no answer).

## Reconciliation with the operator's Phase-E notes

- *"Opus produced a PDF, not a PowerPoint"* — **not reproducible.** `/api/deck` returns a valid `.pptx` with the correct MIME type; the UI names the download `ai-rig-setup-<model>.pptx`; there is no PDF code path anywhere in the repo. Most likely a folder-swap-night mix-up; recommend the operator re-checks. (Fable's deck likewise verified as a real 8-slide `.pptx`.)
- *"No product pictures / can't click a product for details"* — **confirmed for all three arms** (Nexus included; its catalog tab shows only name+price, not even the specs). Blind reviewers scored the decks higher than the operator's "old and cheap" impression — code-level structure is good (esp. Opus's 9-slide deck with copy-paste setup commands and honest caveats; Fable close behind); visual template design is plain in all three (little/no imagery, default-ish templates). Both can be true: content quality high, visual wow-factor low. The bar "present to a client without embarrassment": Opus/Fable yes-with-caveats, Nexus no (skeletal 5 generic slides + $31k budget builds).

## Cost, tokens, time (API-equivalent USD; run-1 figures only)

| Arm | Wall-clock | Tokens | API-equiv $ | $ vs cheapest |
|---|---|---|---|---|
| Fable 5 direct | 34.1 min | 7,108,026 | **$16.48** | 1.2× |
| Opus 4.8 direct | 51.3 min | 14,521,076 | **$13.71** | 1.0× |
| Nexus (SR OFF, Full Auto, Smart) | **~2.5–3.3 h active** (21 dispatches summing 3.25 h; 23 h span incl. overnight stall + operator fix) | 73.0 M GLM + 13.6 M frontier | **$241.23** ($211.79 GLM + $29.44 frontier) | **17.6×** |

Nexus per-stage: Spec $57.20 · Implement $80.60 · Code review $18.52 · Fix findings $44.13 · Acceptance $40.78. **The spec stage alone cost 3.5× the entire Fable-5 run.** Judge rounds: spec 2 versions, implement SHIP r1, review REVISE→REVISE→SHIP, fix REVISE→SHIP, acceptance REVISE→SHIP.

Token-vs-dollar note repeated: Fable used half Opus's tokens but cost more (≈2× per-token rate). Always compare dollars.

## Planning analysis — asking vs assuming (a core benchmark question)

- **Claude arms asked 0 questions** and filled gaps by assumption. Both documented their assumptions well. Costs of not asking: both chose a market/currency wrong for the client (Fable USD-explicitly-documented; Opus EUR but never confirmed), and neither could know about unstated preferences. Benefit: zero operator time, and their *own* domain knowledge was current (both researched July-2026 prices with sources; both shipped current-generation KBs).
- **Nexus asked 3 good questions** (stack, engine sophistication, compat strictness) and obtained a materially richer engine spec than either Claude arm had. **It then delivered the weakest engine anyway.** The interview also *missed* the questions that mattered most for this brief: which AI models to support (its KB ended up two years stale), currency/market, and what "budget tier" must mean economically.
- Conclusion for this run: **the interview advantage was real but squandered downstream** — richer requirements did not survive contact with a spec-freeze + compliance-optimizing pipeline. Asking is necessary but not sufficient; the value is capped by what the pipeline does with the answers.

## Why the Nexus arm failed (tool anatomy, with receipts)

This is the most valuable output of the run. The pipeline's *machinery* worked as designed — and that is exactly the problem:

1. **The spec froze a bad design** ("sort GPUs by vram_gb DESC", "premium pads to exactly 4 GPUs" — SPEC.md step 2), and the acceptance suite pinned it (`test_r11b_premium_gpu_count`). The frontier judge *hardened* rather than challenged it: R11b exists "so it is falsifiable" — falsifiability of a nonsensical rule.
2. **The pipeline SAW the absurdity and had no path to act.** Code-review finding F3 ("cost-disproportionate greedy") was explicitly classified: *"a spec limitation, not a code finding… the fix belongs in a spec amendment decided by the operator"* (workflow DECISIONS.md). No Decision card ever reached the operator. The finding died in a file.
3. **Acceptance shipped PASS knowing the data was unverified**: "the 53-unverified-entries item is a data-audit follow-up, not a spec violation" — against a brief whose central ask was *real products, real specs, researched from the internet, so the client can properly test recommendations*.
4. **No web research in implementation.** The GLM implementer baked in training-data products/prices (2024-era models, launch MSRPs, two invented coolers). Both Claude arms did live price/spec research and cited sources. The brief explicitly allowed/required research during development.
5. **What the pipeline DID catch and fix was real:** F1 (unbounded GPU count → MAX_GPUS cap) was a genuine crash-grade defect; catalog socket errors (F4) were confirmed against 3 sources and fixed; model-name lookup UX (F5) fixed. The judge loop drove 4 REVISE→SHIP cycles that all improved *compliance-grade* quality. Nothing in the loop asks "would a customer laugh at this?"

## Ranked verdict

1. **Opus 4.8 direct — winner (44/50 blind, $13.71, 51 min).** Deepest and most honest engine (offload modeling, KV-precision search, calibrated speeds, connector-level validation), current knowledge, cheapest. Margins over Fable are thin (1 point blind; engine depth clearly ahead; Fable's data-epoch consistency slightly ahead of Opus's). Sensitive to: P3 (no image models — Fable handles Flux; if the client weights image-gen customers heavily, Fable wins), and to the unreproducible PDF note.
2. **Fable 5 direct — close second (43/50 blind, $16.48, 34 min).** Broadest KB (27 models incl. image/speech), fastest wall-clock, price data most consistent with mid-2026 reality, honest infeasibility handling, best P3. Wrong currency for the client is its biggest conformance miss; slightly shallower search (no offload modeling, semi-hardcoded platform tiers).
3. **Nexus (run 1, Smart, SR OFF) — distant third (28/50 blind, $241.23, ~2.5–3.3 h active).** Narrowest scope (10 stale models, no images, no cart), fabricated data, economically absurd recommendations in the brief's own example flow — at 15–18× the cost. Its genuine strengths (README that works as written, one-command test harness, disciplined spec/acceptance trail, real per-stage review) are process strengths the client never sees.

**Against the program's §7 success criterion** ("system quality ≥ direct at cost below one Fable-direct pass"): run 1 missed on both axes simultaneously — quality far below direct at ~15× the cost ceiling. That is the honest headline of this benchmark.

---

# What went well / what went badly / what to improve

## What went well

- **Both Claude arms produced genuinely production-credible demo engines in under an hour, unsupervised** — with live web research, sourced pricing, real .pptx generation, meaningful tests, and honest caveats. The blind reviewers hand-reproduced both arms' math and it *checked out*.
- **The benchmark design worked.** The loose brief + answer-sheet + personas separated the arms sharply (near-ties on "does it run", massive gaps on judgment axes). The blind Phase-1 → de-anonymized Phase-2 protocol produced a credible ranking despite self-preference risk (Fable reviewers ranked Opus #1).
- **Nexus process artifacts are real assets:** the Deep Plan interview asked material questions; the branch-artifact deliverable + worktree collection worked; DECISIONS.md gives an auditable trail of every stage's reasoning — none of the other arms can explain *why* they did anything after the fact.
- **The Nexus judge loop caught real defects** (F1 GPU-count crash-class bug, catalog socket errors, name-lookup UX) and its acceptance stage proved offline operation at syscall level. The machinery is sound.
- **Run 1 completed autonomously overnight** despite an SSE stall, and the mid-run recovery preserved the run (stall-based turn guards from the 07-11 fix pass earned their keep).

## What went badly

- **Nexus product judgment (the headline):** budget = $31k H100 builds, premium = 4×H100 padding, fabricated products, two-year-stale KB, no cart, skeletal deck — shipped as PASS by a 5-stage pipeline with a frontier judge, because every stage optimized spec compliance and the one finding that named the real problem (F3) had no route to a human.
- **Nexus economics:** $241 API-equivalent (73 M GLM tokens) for the weakest deliverable. The spec stage alone out-cost an entire direct run 3.5×. Sinks: 4 judge REVISE cycles, three spec rounds, retry/rework loops.
- **Benchmark ops:** crossed `--model` flags (folder-swap incident) cost an evening of attribution work; the operator's PDF note can't be reproduced; the recorded Nexus wall-clock (23 h / "1385 min") is useless because the operator fixed the tool mid-run and tasks stalled overnight — active time had to be reconstructed from dispatch records (3.25 h).
- **Answer-sheet gaps:** P2's €1,450 threshold is ambiguous against USD-priced shops; "complete list" flags don't catch economically absurd builds (Nexus P1 formally passes). The flags need a value-sanity clause.
- **Operator burden:** persistent benign-but-scary "critical hermes error" toasts during the run (already queued as a fix), and a deleted-project zombie run kept executing (also queued).

## Recommendations (ordered by expected impact)

**For Nexus (the product):**
1. **Add a product-sanity axis to the judge** — a mandatory "customer test": drive the running app with 2–3 realistic personas and judge *outcomes* ("is a $31k 'budget' build sane? would you present this deck?"), not artifact-vs-spec compliance. This single change would have caught the worst defect at round 1. (Extends the judge-loop overhaul's stage-contract work — same harness, new axis.)
2. **Give spec-blocking findings a road to the operator.** F3 was correctly diagnosed as a spec defect and then buried. A review finding classified as "spec limitation" on a customer-visible behavior must raise a Decision card (or downgrade the stage verdict), not be filed away. The armed-escalation machinery from the judge overhaul is the natural carrier.
3. **Require web research for data-bearing briefs.** When the brief says "researched from the internet", the spec/implement stages must run (and cite) live research; acceptance should spot-check N catalog facts against sources and treat fabrications as blockers, not "data-audit follow-ups". (GLM stages have no live-web habit; make it a stage contract.)
4. **Interview coverage checklist for commerce briefs:** market/currency, catalog freshness ("current as of?"), and the economic semantics of tiers are exactly the questions the Deep Plan interview should not skip on a webshop brief. Its 3 questions were good engineering questions and zero product questions.
5. **Spec-freeze hygiene:** freeze *contracts* (interfaces, invariants), not *algorithms*. "Sort by VRAM DESC" and "exactly 4 GPUs" should never be acceptance-pinned; "budget tier is the cheapest build meeting demand" should have been. The judge should challenge spec sanity in round 1 (it has the brief), not add falsifiability pins to bad rules.
6. **Token-sink audit before run 2:** 73 M GLM tokens for this deliverable is out of band. Instrument where the implement stage's 25 M and spec's 17 M went (repeated full-context replays? retry loops?). The compression/context-cap knobs from the 07-12 efficiency pass evidently didn't bound this.
7. Already queued, confirmed by this run: SSE reset not-an-ERROR; deletion must stop orphaned Hermes runs.

**For the benchmark harness (runs 2–3 + Phase 8):**
8. **Launch checklist step:** before starting each arm, `echo` the model ID and `pwd` into the session and screenshot it — kills folder-swap-class incidents for good.
9. **Freeze the system under test.** No tool fixes during a scored run; if a blocker forces one, the run restarts (or is labeled tainted). Attempt 3's overlap with the judge-loop overhaul makes its result strictly "run 1 at moving HEAD".
10. **Capture artifacts immediately per arm** (deck file, screenshots, cost prints) into the arm folder before moving on — the PDF-vs-PPTX ambiguity would have been a 10-second check.
11. **Fix collect_nexus.py wall-clock:** sum dispatch durations (started_at→ended_at) instead of created→completed span; report both.
12. **Tighten the answer-sheet:** state persona-P2's cap in "session currency" with a conversion note; add a value-sanity flag ("recommended total >3× the cheapest catalog-satisfying build = fail").

## Go/no-go for run 2 (Balanced) and run 3 (SR ON)

**Go, but not yet.** Running run 2 on the same commit would measure config (Balanced/SR) against a defect class that config cannot fix — stale data and judge blindness to product sanity are tool gaps, not spend-profile gaps. Recommendation: implement at minimum recommendations 1–3 (product-sanity judge axis, spec-finding escalation, research requirement), then run 2/3 against the SAME frozen Claude baselines. Note the learning-loop caveat: runs 2–3 benefit from run-1 lessons; improvements are config + learning + tool fixes, not config alone — label accordingly.

---

**Learn:** The craft lesson of this benchmark is that *verification machinery amplifies whatever objective you give it.* Nexus ran five stages, nine judge rounds, 99 green tests, and syscall-level offline proofs — all faithfully guarding a spec that said "budget tier = the biggest GPU we stock." The two direct arms had no machinery at all, but their objective was the *customer's sentence* ("does this recommendation make sense?"), and both independently spent their effort exactly where the machinery-rich arm spent none: live research, economic sanity, honest caveats. Process without a product-shaped objective converges on defensible nonsense; before adding another gate, ask what the gate is *for*.
