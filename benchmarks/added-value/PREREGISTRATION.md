# PRE-REGISTRATION — "Does Nexus add value?" benchmark
**Status: LOCKED once committed. Thresholds below were written BEFORE the first artifact was generated (2026-07-11). Any change after the first run is a new benchmark, not an amendment.**

## Primary question
Does the Nexus pipeline produce measurably better and/or cheaper deliverables than (a) a normal user typing the same brief into plain Claude Code, and (b) the same cheap model (GLM-5.2) called raw — and if yes, **what** improves (which rubric dimensions/gates) and **by how much** (score delta, cost per rubric point)?

## Arms (same 27 briefs, verbatim, one generation each)
- **Arm A — Nexus** (`arm_a_mode` in config.json):
  - `task` (default, the product promise): real kanban task per brief with `super_result: true`, `autopilot: full_auto`, closed loop — dispatch framing → GLM-5.2 → grounded critic → auto-retry rounds until SHIP / round cap. Deliverable = final `workspaces/<task-id>/deliverable.md`.
  - `evals` (fallback, framing-only): the existing eval runner (`POST /api/evals/run`) — dispatch framing + single pass, no retry loop. Measures less of Nexus; the report labels which mode ran.
- **Arm B — plain Claude Code, "normal user"**: headless `claude -p "<brief>"` in an empty working directory with a **minimal clean config** (credentials only — no user CLAUDE.md, no business brain, no memory; env scrubbed the same way `cjudge` scrubs). Model pinned in config (`claude-opus-4-8`) for determinism. One shot, no follow-ups. *Definition note: "normal user" = subscription defaults without this machine's customizations.*
- **Arm C — raw GLM-5.2**: one `chat/completions` call to the Z.AI endpoint from `~/.hermes/config.yaml`, brief + "produce the deliverable" instruction, no framing, no tools, no retry.

A vs B answers the headline question. A vs C isolates the harness's contribution on the same model family. B vs C is reported for context only.

## Judging (blind)
1. Artifacts are copied into per-brief packets as `deliverable_1/2/3.md` in shuffled order (seeded RNG). The arm↔number mapping lives in `runs/<id>/private/`, outside the packet tree; judges are pointed at packet files only. Lines that explicitly self-identify the model ("As Claude…", "I am an AI…") are stripped and logged; all other content untouched.
2. **Absolute scoring, two judge families** (each scores every artifact independently):
   - Claude judge (subscription CLI, same env-scrub as `cjudge`), reads deliverable + domain RUBRIC.md + STYLE-VOICE.md.
   - GLM-5.2 judge (Z.AI API), same prompt with files inlined.
   Both emit sentinel-fenced JSON: every rubric gate PASS/FAIL, every dimension 0–4, kill-list hits, and a **grounding check** (2 load-bearing claims each: consistent / contradicted / unverifiable) — the miniature of the quality-loop P2 fix, because we know artifact-only judging passes well-formed-but-wrong work.
3. **Pairwise A-vs-B and A-vs-C** (Claude judge, both presentation orders): a win counts only if the same artifact wins in both orders; otherwise tie.
4. **Human taste check**: the operator blind-reviews 5 random packets (`05_report.py --sample` prints them with mapping withheld) and records picks before reading RESULTS.md.

## Metrics
Per artifact: dimension mean (0–4), gates passed/total, verdict, grounding flags, generation seconds, tokens, cost (list-price equivalents from config; subscription-authed calls additionally report $0-marginal + the CLI-reported `total_cost_usd` for transparency; Arm A also reports GLM tokens from the eval/task record — frontier judge/critic spend inside Arm A is subscription and reported separately as "frontier assist", not silently omitted).
Aggregates: per-arm mean dimension score (per judge family and pooled), pairwise win rates, cost per artifact, **cost per rubric point**, per-dimension deltas A−B and A−C, gate-failure profiles, judge-family agreement (% same-direction on A−B per brief), pairwise order-consistency.

## Decision thresholds (locked)
- **"Nexus adds value vs plain Claude Code" = YES** if, on pooled judge scores over non-excluded briefs: A's pairwise win rate vs B ≥ **55%** (ties count 0.5), **or** |mean dimension delta| ≤ **0.3** with A's list-price cost ≤ **40%** of B's ("iso-quality, much cheaper").
- **"The harness adds value over the raw model" = YES** if A beats C pairwise on ≥ **70%** of briefs.
- **FALSIFIED** if B beats A pairwise on > **60%** of briefs — then the pipeline subtracts value for business deliverables at current quality, and that gets fixed before anything is sold.
- Secondary (reported, not decisive): grounding — A should have strictly fewer `contradicted` + `unsupported_load_bearing` flags than B and C (the verification pitch); dimension-level story = the top-3 dimensions by A−B delta.

## Exclusions & retries
Each generation gets 2 retries on transport/quota errors (GLM 1305 load-shed → 90 s backoff). A brief where any arm still failed is **excluded from win rates** and listed in RESULTS.md with its error. Judge calls get 1 retry on JSON-parse failure. If > 5 briefs are excluded, the run is void — rerun off-peak rather than reading a biased subset.

## Known limitations (accepted, disclosed)
- n=1 generation per brief per arm (variance unmeasured; a future run may add repeats).
- Business-deliverable corpus only — says nothing about coding tasks (phase 2 would use test-suite ground truth).
- Judge families overlap with generator families (Claude judges Claude; GLM judges GLM). Mitigations: two families + pairwise order-swap + human sample. Residual self-preference bias is possible and disclosed.
- Arm B lacks the business brain by design — part of any A win is context, not orchestration. That is the product-experience comparison, and the report says so.
- Judges can technically read files outside their packet (Claude CLI has tools); mapping lives outside the packet tree and prompts restrict reading — residual risk accepted.
- Grounding checks are internal-consistency checks (no web access) — they catch contradictions and unsupported claims, not all falsehoods.
