# Bench-02 Final Comparison — protocol for the analysis session

Run this AFTER all three arms are finished AND the operator completed Phase E (functional checklists in RESULTS.md). One fresh Fable 5 session executes it end to end.

## How to launch (operator)

1. Prepare the anonymized copies (last argument = the prompt file actually used):
   ```
   bash /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-02-webshop/grading/prepare_judge.sh ~/benchmarks/bench-02/fable5 ~/benchmarks/bench-02/opus48 ~/benchmarks/bench-02/nexus /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-02-webshop/PROMPT-B.md
   ```
2. Start a fresh session and paste the prompt:
   ```
   cd /home/sinep/Nexus-Agentic-Coding-Setup && claude --model claude-fable-5
   ```
   Paste:
   > Execute the final-comparison protocol in benchmarks/bench-02-webshop/FINAL-COMPARISON.md exactly as written. Do Phase 1 fully before opening any Phase-2 file.

---

## Instructions for the analysis session (Claude, follow exactly)

You are producing the final comparison for a three-arm benchmark: the same client brief was given to three systems, each built a local AI-hardware webshop demo. Your job: determine **whether each arm got everything right**, whether the work **uses state-of-the-art technology and follows best practices**, and which arm delivered the best value — grounded in evidence, not vibes.

**Integrity rules (binding):**
- Two phases. In Phase 1 you may ONLY read `benchmarks/bench-02-webshop/grading/out/blind/` (X/, Y/, Z/, BRIEF.md) and `ANSWER-SHEET.md`. Do NOT open RESULTS.md, mapping.txt, or the arm-named folders until Phase 1 scores are written down. This limits (it cannot eliminate) self-preference — one of the three arms is your own model; ignore any provenance clues and judge artifacts only.
- Every claim you make must carry evidence: a file:line, a command + output, or a URL you actually fetched. Mark anything you could not verify as [UNVERIFIED] instead of asserting it.
- Web research is REQUIRED, not optional (details below). Today's date matters: judge "state of the art" against what is current NOW, not against your training data alone.
- Do not modify any solution files. Your outputs: a report file + edits to RESULTS.md only.

### Phase 1 — blind technical review (per solution X, Y, Z)

**1a. Requirement conformance — "did they get everything right".** Build the requirement list from BRIEF.md (browsable shop; intelligent model→parts helper with researched specs; recommendations only from the shop's own catalog; complete working setups; 40+ real products with real specs; downloadable per-recommendation PowerPoint setup guide; runs fully offline locally; README with exact install/start commands; decisions documented). For each solution render a table: requirement → MET / PARTIAL / MISSED, with file:line or observed evidence. A PDF where PowerPoint was demanded is PARTIAL at best. Also run each app briefly (their READMEs tell you how; use timeouts, stop the servers after) to confirm the flow works — the operator's Phase-E checklist in RESULTS.md is the authority for deep behavior, but you must at least see each app answer HTTP.

**1b. Recommendation-engine depth.** Read the actual logic. Score what happens for a model it wasn't demoed with: is there a genuine knowledge base (VRAM by quantization, PSU headroom math, socket/RAM compatibility) mapped to the catalog, or a hardcoded happy path? Trace ONE concrete case per solution end to end (e.g. "Llama 3 70B"): write down the VRAM figure it derives, the GPU(s) it picks, the PSU it sizes — and check that math yourself. A recommender that hardcodes three canned bundles scores low even if the demo looks right.

**1c. Data accuracy (web-verified).** Sample ≥6 catalog products per solution across categories: do they exist as named? Are VRAM/wattage/socket/capacity right? Are prices within plausible market range? Fabricated or wrong-spec products are critical findings.

**1d. State-of-the-art & best practices (web-verified).** Two layers:
- *Domain SOTA:* are the recommended GPUs/CPUs/platforms current generations as of today (search for what is actually current), or does the catalog read like stale training data? Are the AI models in the knowledge base (Llama/Qwen/DeepSeek/Flux etc.) current, with sensible quantization assumptions?
- *Engineering practice:* held to DEMO scope (the brief excludes production auth/payments/security) — judge structure and craft, not enterprise ceremony: separation of data/logic/UI, tests present and meaningful, error handling, no dead code, dependency hygiene (pinned? minimal? no abandoned packages — check anything unfamiliar on the web), README accuracy, and a defensible stack choice for a local demo. Flag both under- and over-engineering.

**1e. Deliverable polish.** The client-facing quality axis: shop UX (product detail views? images or graceful placeholders? usable navigation?) and the setup-guide quality (open the PPTX/PDF: structure, completeness, would a client accept it?). The bar: "would the middleman present this to his client without embarrassment?"

Per solution, write scores 1–10 for: conformance, engine depth, data accuracy, SOTA & practices, polish — each with a 2–3 sentence justification citing evidence. Record all of Phase 1 in your report BEFORE Phase 2.

### Phase 2 — de-anonymize and synthesize

Now read `grading/out/mapping.txt`, `RESULTS.md` (operator functional checklists, Q&A logs, cost captures, notes), and `RUNBOOK.md` if needed.

- Reconcile your Phase-1 findings with the operator's Phase-E results; where you disagree, say so and explain (the operator drove the real UI; you read code — both can be right about different things).
- **Planning analysis:** the Claude arms asked 0 questions; Nexus's Deep Plan asked 3 and thereby obtained a materially richer spec (see the Arm-3 Q&A log). Assess how much of each arm's quality difference traces to asking vs assuming — that is a core benchmark question.
- **Cost-value analysis in dollars** (never tokens): API-equivalent $ per arm against the quality you scored. Include Nexus's discovery cost footnotes only as context, not in the run-1 figure.
- **Final output:**
  1. A ranked verdict with rationale (which arm won, on what margins, sensitive to which assumptions).
  2. The filled Verdict section of RESULTS.md (Quality / Cost / Questions-planning quality / First impression / go-no-go for runs 2–3).
  3. The full report written to `benchmarks/bench-02-webshop/COMPARISON-REPORT.md` (Phase-1 tables + scores first, then Phase-2 synthesis; state the self-preference caveat and n=1 prominently).
  4. One `**Learn:**` section at the end (house rule): the single most instructive craft lesson from comparing the three.
  5. Log outcomes to `~/knowledge/feedback/WINS.md` / `LESSONS.md` per house rules if any clear win/lesson emerged.

**Caveats to carry into everything you write:** n=1 per arm — directional only, no product decisions (master plan C-10); you share a model with one arm (self-preference); the operator's presence makes this a field test, not a controlled experiment; the Nexus arm ran at a later commit than the Claude arms (judge-fix mid-benchmark, documented in RESULTS Note 3).
