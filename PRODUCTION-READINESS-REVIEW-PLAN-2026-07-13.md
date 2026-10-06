# PRODUCTION READINESS — FINAL REVIEW CAMPAIGN (2026-07-13)

**How to use this document:** Claude sessions execute §§1–13. The human operator executes ONLY §14 (runbook)
and §16 (quick reference). Replaces `PRODUCTION-READINESS-REVIEW-PLAN-2026-07-11.md` (deleted, never executed;
its skeleton was absorbed here and all stale anchors fixed).

## §0 Mission

The FINAL comprehensive check that **every functionality of Nexus Agent OS actually works** — full stack, at
runtime, with **zero trust in prior test reports** (the 07-12 bugfix/improvement wave and the 07-13 judge
overhaul changed a lot) — PLUS an **architecture review**: is the architecture as a whole correct, is there a
better way to reach the tool's goals, what should be improved. Output: complete findings list + fix plan +
improvement plan → fixes/rebuilds executed → re-verified.

**Posture (owner, 2026-07-13):** the code was designed and implemented by a junior software
architect/developer. Nothing in the current implementation is assumed correct — **including its design**.
Every subsystem is judged against web-researched state-of-the-art and best practices
(`Production-Readiness-Review-1/TOOL-DOCUMENTATION-2026-07-13.md` holds the per-functionality research and
verdicts as hypotheses; this campaign confirms them at runtime). Where something is not well implemented, do
NOT patch around it — plan a **proper re-implementation** that reaches the intended goal the right way.

**Campaign shape:** Session A (big review, Fable 5, ultracode) → Sessions B1..Bn (fix + rebuild batches) →
Session C (re-verify judge, Fable 5). Everything lands in `Production-Readiness-Review-1/`:
- `FINAL-REVIEW-2026-07-13.md` — findings ledger + goal/subsystem/domain scorecards + architecture verdict
- `FIX-RUNBOOK-2026-07-13.md` — self-contained fix/rebuild batches (P0/P1/P2)
- `IMPROVEMENTS-2026-07-13.md` — max 7 adopted "work smarter" additions + rejects with earn-back triggers
- `evidence/` — gate outputs, screenshots, question log, journey artifacts, probes
- `PROGRESS.md` — live checklist, updated after every phase (crash-safe resume)

**Verdict standard:** each of the 10 product goals (§5) gets an evidence-based **GO / GO-WITH-FIXES / NO-GO**.
The security row is hard-set **PENDING** (separate `SECURITY-SWEEP-PLAN-2026-07-12.md` session, Opus 4.8);
readiness is not final until both campaigns have run.

## §1 Scope fence (hard)

- **NO security testing of any kind.** Incidental security-shaped observation = ONE line in the ledger
  (`→ route to security sweep`), never investigated here.
- **Guardrail hygiene (Fable 5):** this is owner-authorized functional QA of our own product on our own
  machine. Never construct attack-shaped probes, bypass attempts, or payloads; never attempt access the UI/API
  doesn't offer; cross-user checks use only documented product flows and the product's own scratch test
  accounts. Injection/authz/secrets depth belongs to the separate Opus security sweep. If a check would
  require attack-shaped action → mark `PENDING-SECURITY`, move on. If a guardrail refusal occurs anyway: log
  one line in PROGRESS.md, skip that item, and NEVER rephrase-and-retry the trigger content.
- **Rebuild-over-patch is IN scope** (owner decision): where a subsystem is badly designed/implemented,
  propose (Session A) and execute (Sessions B) a proper re-implementation — developed in a git worktree,
  landed only gate-green, one subsystem at a time, so the tool stays usable throughout. Gratuitous
  *infrastructure* swaps still need a stated payoff at 2-user single-node scale (SQLite→Postgres remains a NO
  without one); correctness/best-practice re-implementations need no payoff bar.
- No public hosting / packaging / licensing work (separate track). Tailnet-only posture is accepted.
- No kernel/driver/system-level changes (hard gate per SESSION-START brief).
- No model re-benchmarking beyond noting `benchmarks/added-value/` status (rubric-relevant for G6).

## §2 Read first (Session A, ~20 min, no skipping)

1. `Production-Readiness-Review-1/TOOL-DOCUMENTATION-2026-07-13.md` — **FIRST.** Per-functionality intended
   goals, current implementation, web-researched proper way, PROPER/PARTIAL/NOT-PROPER verdicts. This is the
   purpose ground truth; its verdicts are hypotheses this campaign confirms or refutes at runtime.
2. `CLAUDE.md` (repo root) — ONE-REPO rule, `app/` is the LIVE tree, `~/nexus-agent-os` symlink is
   load-bearing, run from `main`, worktrees for experiments.
3. `app/CLAUDE.md` — architecture map + the canonical gate commands (single source for gate invocation).
4. `app/docs/SPEC-JUDGE-LOOP.md` — **the judge-overhaul mechanism source of truth** (in-repo, gated by
   verify.sh check "judge-loop spec committed"): full verdict cascade, state inventory, §10 settings table,
   §11 INVARIANTS (any finding that proposes breaking one is automatically wrong unless it argues against
   the invariant itself), §12 verification map, §13 recorded deviations + improvement backlog. Judge the
   overhaul against THIS + the TOOL-DOCUMENTATION D3 verdicts (whose LANDED addendum pins commit/gate
   state). Why-evidence: `IMPLEMENTATION-REPORT-JUDGE-LOOP-2026-07-13.md`. The original operator-approved
   plan (`~/.claude/plans/check-if-the-functionallity-rippling-stallman.md`) is background; where it and
   the SPEC disagree, the SPEC §13 deviations section explains why — treat unexplained disagreements as
   findings.
5. Memory files (auto-loaded MEMORY.md index; open in full): `improvement-batch-2026-07-12`,
   `bugfix-campaign-2026-07-12`, `win-lesson-feedback-loop`, `judge-stub-leak-incident`,
   `e2e-scheduler-job-leak`, `turn-cap-cut-recovery`, `restart-prep-manual-start`,
   `fable5-security-work-presentation`.
6. Prior findings ledgers as MAPS, not proofs: `CODE-REVIEW-FINDINGS-2026-07-12.md` (37 defects, no fix-status
   column) and `BUGFIX-CAMPAIGN-2026-07-12.md` (29 findings marked fixed with SHAs).
7. `benchmarks/bench-02-webshop/ANSWER-SHEET.md` (the interaction-protocol pattern §8 reuses) and a skim of
   `~/knowledge/domains/*/RUBRIC.md` (journey scoring anchors).

## §3 Zero-trust rule — check EVERYTHING; no prior result counts

- **Every prior PASS is stale** — including the "FULLY COMPLETE" 07-12 bugfix campaign and every green gate
  run. Re-verify the full surface as if this were the first audit; regressions in old features are exactly
  what this campaign exists to catch.
- **Prior audit docs are maps of bug clusters, not proofs.** Re-hunt each documented class across the WHOLE
  current code: event-loop blocking (STABILITY-AUDIT class — re-run `scripts/check_async_blocking.py` + spot
  new handlers), VRAM contention (MEMORY-AUDIT class), **stub-leak class** (3 incidents — dedicated sweeps,
  Phase 0/8), judge-grades-artifact-not-system class, duplicate-definition drift class.
- **"verify.sh green ≠ healthy":** the gates THEMSELVES are under audit (Phase 1: feature→gate coverage map +
  stub-rot spot checks). A feature added after its area's gate was written is untested no matter how green.
- **Change inventory is attention-weighting, not scope-limiting:** `git log --oneline --stat 75dcbda..HEAD`
  coarse per subsystem, `5df5d26..HEAD` fine (07-12 improvement batch onward), and the judge-overhaul commits
  as the newest cluster. Every touched module gets a named lane/probe; untouched features still get re-tested.
- **Junior-authored assumption:** the current design is a hypothesis, not a baseline. When runtime behavior
  matches the code but the code's approach contradicts the researched proper way (TOOL-DOCUMENTATION), that is
  a finding (severity by impact), not a pass.

## §4 Ground rules

- The service is LIVE. No destructive ops; additive-only DB changes; experiments in git worktrees; restart
  only via `systemctl --user restart nexus`; bound every `journalctl` with `-n` (a 22 GB OOM happened once).
- **Findings culture:** every finding = `F-NNN` + severity (P0 fix-before-daily-use / P1 first-week /
  P2 later / P3 cleanup-table) + goal tag (G1–G10) + file:line or command + reproduction/failure narrative +
  proposed fix (or REBUILD pointer) + verify step + adversarial verdict (CONFIRMED / PLAUSIBLE / REFUTED —
  refuted ones listed with why). No vibes.
- **Crash-safety:** append findings to FINAL-REVIEW and tick PROGRESS.md after EVERY phase (journeys: after
  EVERY journey). An aborted session must lose minutes, not the audit.
- Fixes are PROPOSED, not applied — except trivially safe one-liners collected into ONE labeled `batch-0`
  commit at the very end, authorized by the operator in Attended Block 2 (pre-commit gate must pass).
- **Probe hygiene:** every campaign-created artifact (tasks, workflows, users, repos, agents) is named with
  prefix `campaign-`. NEVER touch real member `ariana`'s data — scratch-member pattern exactly as
  `verify_multiuser_e2e.py` does. DB backup exists from preflight.
- **Anti-runaway:** post-overhaul the SYSTEM must self-cap (judge.max_runs=4, at-cap closure card, frontier
  cost caps). Any journey task that exceeds the cap, loops silently, or blows its cost cap = **P0 finding on
  the overhaul** — stop that task, file it, continue the campaign.
- Cost figures are API-equivalent (Claude sessions bill the subscription, $0 marginal). GLM burns a real
  quota window — run GLM-heavy phases off-peak (error 1305 = upstream load-shedding, not a campaign failure).

## §5 The 10-goal rubric (the campaign's spine)

Every goal: probes below + evidence artifacts in `evidence/` + a scorecard row citing finding IDs.

**G1 — Properly organized UI (overview + productivity workflows).**
Probes: `screenshot_all_tabs.py campaign-start` clean (console-error-free); phone-viewport (390×844) ad-hoc
screenshot probe (stock script is 1600×1000-only); "find it in 3 clicks" drills via Playwright (yesterday's
deliverable / a running task's transcript / current spend / a specific lesson); the Projects-vs-Workflows
naming collision assessed explicitly; attended eyeballs (AB1 desktop, AB2 phone).
Verdict: NO-GO only if a daily-use surface is broken or unusable on either device class.

**G2 — Fully automated parameter setting ("like Manus, but never stuck, no token waste").**
Probes: five one-sentence briefs (code / content / research / analysis / mechanical) created with ZERO manual
settings → dump each derived parameter set (model+reason, budget, effort, SR, pipeline shape, spend
preselect) and judge every derivation against the documented rules; journey question-log metrics (≤1 wizard
question round; question quality; zero stuck/wasted-output events); `_feature_present`-staged derivations
enumerated live-vs-staged (staged must not half-fire).
Verdict: a non-IT user naming a task gets a sensible full configuration with ≤1 question round; any
getting-stuck or token-burn-on-garbage event is NO-GO-grade evidence.

**G3 — Full manual control + see everything + teach/correct.**
Probes: override EVERY wizard-set parameter and prove each override sticks through dispatch (model + effort
visible in `~/.hermes/agent.log` `[zai-override]` lines; budget honored); live visibility drill (transcript,
dispatches, ledger, activity feed during a real run); full teach round-trip: file a lesson via 🐞 →
framing injection observed in the next same-domain dispatch (`build_framing` output) → the mistake does not
repeat on a re-run of the same brief.
Verdict: every parameter reachable, every action observable, one teach round-trip proven end-to-end.

**G4 — Learns, memorizes, recaps its own work; asks when unsure.**
Probes: dispatch → `memory` table experience row exists (write has a reader); trigger a consolidation sweep
and read the rolling summary; wins/lessons injection observed in framing; deliberately ambiguous brief →
wizard asks the RIGHT question instead of assuming; JARVIS briefing recaps yesterday's completions.
Verdict: each memory write path has a proven read path that changes behavior (write-only memory = finding).

**G5 — Frontier quality stack (fixes LLM weaknesses; max quality per $).** Expectations pinned to the
POST-overhaul contract: deterministic pre-gate fires before any frontier judge; round-1 SHIP/SHIP-with-notes
is common (0% round-1 SHIP was the old pathology); REVISE briefs are numbered [F1..Fn] fix-lists; delta
re-judge on round ≥2 (<300k judge input tokens, criteria frozen, no re-litigating passed text); at-cap /
converged → closure decision card, never a silent continue; GLM screen on Balanced interior members (never
SHIP-authorizes sinks; booked `kind='judge_screen'`; screen verdicts never qualify golden exemplars); judge
output grounded in the artifacts (cites real lines; instant-verdict stub tell ABSENT); critic sandboxes
created AND cleaned; deep-plan premortem annotations + one revise round on two journeys; review modal shows
round-over-round diff + findings panel (anchored AND unanchored); overhaul must-not-regress list spot-checked.
Verdict: the stack demonstrably catches ≥1 real defect during journeys — if it never fires or always SHIPs
first pass, assess: correctly calibrated or evidence-blind?

**G6 — Self-adjusting economics (Eco / Balanced / Smart + Super Result).**
Probes: the SAME brief derived at eco/optimal/smart → diff derived budgets/models/efforts/judge-scope against
the overhaul's per-mode matrix (frontier cost caps $1.50/$3/$6; retry slice 0.5×; ceiling 2.0× + budget
decision card at ceiling); one real eco-tier task judge-REVISEd → tier escalation fires and is recorded in
`model_reason`; ledger spot-audit (5 recent tasks priced non-zero with plausible models); NEW cost surfaces
work (task-drawer true-cost line, board $ chip, Usage quality_loop split); Usage answers "can I start a big
job now?".
Verdict: **pre-capped at GO-WITH-FIXES** — "each mode beats using models the normal way" stays unproven until
`benchmarks/added-value/` runs (IMPROVEMENTS must schedule it; check the honest-heuristic labels render).

**G7 — Broad task-type coverage, per-type best-practice workflows.**
Probes: the 10 journeys ARE the probe; each journey's DAG shape reviewed against domain best practice BEFORE
dispatch; one mid-journey failure exercised through replan detect → draft → apply.
Verdict: per-domain scorecard with ≥8/10 domains GO or GO-WITH-FIXES.

**G8 — Productivity tools properly implemented + automatically used.**
Probes: each tool produces one real artifact inside the journeys — consulting→PDF, ecommerce→SDXL image,
software→review v2+PR+▶ Test-app preview, AB1 meeting recording→summarize→requirements→create-workflow chain,
notes, dictation (AB1); "automated use" = the plan reaches for the right tool WITHOUT being told (the
consulting brief says "client-ready proposal" and a PDF stage appears).
Verdict: every listed tool works AND ≥half were selected autonomously.

**G9 — JARVIS voice assistant.**
Probes: `verify_jarvis_e2e.py` + `verify_jarvis_v2_backend.py` fresh; AB1 live mic round-trip ×2 (transcript
→ spoken Piper reply → avatar talking state) + barge-in; deck→"hand to fleet" creates and dispatches a real
task; briefing spoken. Parked items verified PARKED, not broken: torso `SHOW_TORSO=false` (no console
errors), Kokoro blocked on py3.14 (Piper active), `/talk`+`/lipsync` 410 Gone (tools_hub still listing
wav2lip = cosmetic finding).
Verdict: voice round-trip reliable 2/2 on the real mic.

**G10 — Multi-user deployment + modern impressive GUI.**
Probes: `verify_multiuser_e2e.py` fresh; scratch member `campaign-member` re-runs 2 journeys via documented
product flows only (its board/lessons/deliverables show what sharing intends — isolation depth = security
sweep); adopt flow copies a lesson with provenance; onboarding overlay renders for the member; admin sees
member known-issues; AB2 phone check; GUI "modern/impressive" scored by the owner in both attended blocks
(subjective verdict recorded verbatim).
Verdict: a second real user could onboard and work a full day unaided.

## §6 Session A — phase plan

Constraints: ONE live service (runtime probes serialize), 12 GB VRAM (voice/vision probes serialize with
journeys), GLM quota (≤2 journeys in flight, off-peak preferred). Read-only code lanes and adversarial
verification fan out in parallel (ultracode). **Last step of every phase: flush findings to FINAL-REVIEW +
tick PROGRESS.md.**

**P0 — Setup, baseline, stub hygiene (serial, ~25 min).**
1. §2 read-first. 2. Create `PROGRESS.md` + `FINAL-REVIEW-2026-07-13.md` skeleton (§9) + `evidence/` tree.
3. Record HEAD SHA into PROGRESS; confirm branch `main` and tree CLEAN (guaranteed by preflight; if dirty →
STOP, ping operator). 4. **Stub-hygiene sweep (start):** via `app/.venv/bin/python` sqlite one-liner (no
sqlite3 CLI on this box) check these settings are unset/default: `judge.cmd, super.critic_cmd,
super.escalation_cmd, plan.critique_cmd, plan.stub, evals.stub, evals.improve_cmd, dispatch.stub_stream,
dispatch.force_429, jarvis.force_429, agentmem.stub`; `GET /api/scheduler` → DELETE any leftover
`e2e-*`/`*test-tick*` jobs; check for leftover `campaign-`/`probe-`/`HermesVerify*` artifacts. Output →
`evidence/probes/stub-sweep-start.txt`. 5. Baseline: `systemctl --user status nexus`; journal error census
(`journalctl --user -u nexus -n 2000 --no-pager | grep -iE "error|traceback|warning" | sort | uniq -c |
sort -rn | head -40` — recurring errors ARE findings); disk/db sizes (nexus.db+WAL, workspaces/,
~/.hermes/state.db, qdrant, HF cache); `nvidia-smi` idle; guardian 8/8. 6. Change inventory (§3 anchors).

**P1 — Gate audit + full gate sweep (serial on the service, ~2h; P2 fan-out launches in parallel).**
1. `app/.venv/bin/python scripts/screenshot_all_tabs.py campaign-start` (fastest full-surface smoke) + the
phone-viewport ad-hoc probe (write a 390×844 variant into the scratchpad, never into the repo).
2. `cd app && bash scripts/verify.sh` — record the printed N/N (the count itself is drift evidence).
3. **Gate coverage map BEFORE trusting gates:** change inventory × `app/scripts/verify_*` → feature→gate|NONE
table; every NONE = automatic finding; spot-check 3 gates for stub-rot (a gate that stubs so much it can't
fail).
4. All e2e suites (canonical commands in `app/CLAUDE.md`), this order: agentic_e2e → agentic_playwright →
v3_ui → block2_e2e → block2_ui → block3_e2e → block3_ui → settings_e2e → feedback_e2e → onboarding_e2e →
onboarding_ui → multiuser_e2e → autopilot_e2e → autopilot_ui → deep_plan_e2e → deep_plan_ui →
mode_coherence_e2e → stop_e2e → phase_c_e2e → **verify_judge_loop_e2e (overhaul gate)** → jarvis_v2_backend →
jarvis_e2e → stt_e2e → super_result_e2e (slow) → real_dispatch_e2e (real GLM — check quota weather first) →
restart_prep_e2e LAST (restarts the service). Full stdout of each → `evidence/gate-outputs/<gate>.txt`.
Any red / hang / error = finding. **After ANY gate crash: immediately re-run the stub-hygiene sweep.**

**P2 — Architecture review fan-out (PARALLEL, read-only; ~3h overlapped).**
Nine finder lanes; **every lane verifies its patterns via WEB RESEARCH against current authoritative sources
(citations required)** and cross-checks the TOOL-DOCUMENTATION verdicts for its area; each subsystem it covers
gets a build-quality verdict **SOUND / NEEDS-REFACTOR / REBUILD-PROPERLY** with the cited practice gap and a
sketch of the proper implementation:
- A backend/core: server.py (~11k lines; router split), hermes_dispatch state machine edges (cancel/cut/
  harvest, turn-cap-cut class), worker lanes, loop_engine sweeps, watchdog; async-blocking re-run + new
  handlers spot-check.
- B data model: schema/indexes for hot paths (kanban poll, WS broadcast), `_ensure_columns` migration
  hygiene, WAL/busy_timeout, backup-ability.
- C frontend: app.js ~11.5k-line single-file no-build choice judged as such; dead views; WS/SSE lifecycle
  leaks; tick()/softRender discipline; `?v=` cache-bust. (NO injection/escaping review — security sweep's.)
- D integration seams: Hermes pin @048270fa069f + guardian 8 core-mods (what breaks on a Hermes update; does
  guardian actually re-assert — test in a sandbox/worktree, never live), zai plugin, cjudge/cverify/cexec
  bridges, ollama ×2 + qdrant assumptions.
- E goal-fit G1+G10 (UI/multi-user architecture) · F goal-fit G2+G6 (is parameter derivation a sound
  architecture or a rule pile?) · G goal-fit G3+G4 (do the learning loops actually close?) · H goal-fit
  G5+G7+G8+G9 (is the judge/critic/SR layering right?). Each lane answers per goal: serves it / fights it /
  fundamentally better mechanism (honest migration cost).
- I frontier comparison: mid-2026 agent-harness SOTA (Claude Agent SDK patterns, Manus-class autonomy,
  multi-agent orchestration, memory/learning loops) — every "adopt X" gated by the 2-user payoff rule.
Then: dedup → adversarial verification fan-out (refute-by-default, one verifier per surviving candidate);
only CONFIRMED/PLAUSIBLE enter the ledger; REFUTED appendix with reasons.

**P3 — Prior-findings reconciliation + overhaul verification (serial, ~1h).**
(a) 37-row table: every CODE-REVIEW-FINDINGS-2026-07-12 item → status at HEAD (fixed@sha / still-open /
regressed / superseded) using BUGFIX-CAMPAIGN SHAs + git log; ALL P0/P1 re-tested live, 5 random P2s, rest by
diff inspection; still-open items enter the ledger as `F-0xx (carried: CR-#n)`.
(b) **Overhaul verification** — claims per `app/docs/SPEC-JUDGE-LOOP.md` (§10 settings table is the
authoritative expected-defaults list; §12 maps which gate proves what), each checked at HEAD:
new settings exist with documented defaults (`judge.pregate=1`, `judge.pregate_min_chars=400`,
`judge.max_runs=4`, `judge.delta_rejudge=1`, `judge.screen=interior`,
`dispatch.rework_continue_session=1`, `dispatch.retry_slice_frac=0.5`, `dispatch.rework_ceiling_mult=2.0`,
`frontier.task_cost_cap_usd=3.0`, `super.escalation=1`; **`judge.auto_scope` default stays `high_stakes`**
— a RECORDED deviation from the original plan (SPEC §13: profiles govern scope; the global key only affects
profile-less tasks; Balanced derives 'sinks' via `autopilot.derive`, which is what to verify); cjudge
byte-identical in `setup/bin/` AND `~/.local/bin/` with the recalibrated stance/gate-table/verdict text;
UNVERIFIABLE-HERE preamble present in `~/knowledge` rubrics AND `setup/knowledge` mirrors;
`autopilot.derive` matches the per-mode matrix (incl. dead-key fix `plan.deep_enabled`, assisted
`sr_mode=closed`); judge-thread catch-all + stale-'running' reaper + zombie-dispatch detector present;
per-round state (`_judge/round-N.json`, `rounds.json`) written; review pair selection (landed as `?pair=` +
`from_v`/`to_v` — SPEC §13 deviation, not a bug) + findings panel live; SPEC §11 INVARIANTS spot-checked
(esp. screen-SHIP-authorizes-nothing, rework-harvest epoch marker, operator-only family re-arm);
**A/B replay evidence exists and met its gate (≥40% frontier-$ cut, non-inferior pairwise, ≤1.2× GLM) —
skipped or failed = automatic P1 finding**; the D3 TOOL-DOCUMENTATION improvement asks (judge-vs-operator
calibration metric, screen self-preference, global frontier daily ceiling, real GLM in/out split, critic
execution invariant) assessed as candidate FIX batches; must-not-regress list (workspace `_history` review,
comment compose loop, drain-to-retry, SR critic panel, unified⇄split) spot-checked live.

**P4 — Runtime deep probes beyond gates (serial on the service, ~1.5h active + 2h passive).**
1. Responsiveness: `scripts/_probe_responsiveness.py` / `loop_probe.py` at (a) idle, (b) one real dispatch
streaming, (c) dispatch + JARVIS turn + STT simultaneously — p95 latency; any event-loop stall >100 ms =
finding. 2. VRAM contention matrix (12 GB): STT + vision describe + SDXL imagine + dictation cleanup-LLM in
realistic overlaps — evict-before-load / CPU fallbacks must fire instead of OOM; JARVIS cold vs warm latency.
3. Self-heal: kill a lane worker mid-dispatch → resume-not-restart harvest; SIGKILL the STT worker → respawn;
retire path terminates cleanly. 4. Stop/cancel semantics: stop a streaming task (≤30s cancel, no token burn
continuing — `session-run-stop` core-mod live check). 5. Parked-items check (§5 G9 list + deep-plan
single-task no-critique + `_feature_present` staged list + topbar ⏻ reveal + restart-prep drain/restore round
trip). 6. Start the soak: scripted light load (tick poll + 1 WS client + periodic cheap dispatch), harvest at
P6 (RSS/fd/thread creep + journal delta).

**→ ATTENDED BLOCK 1 (~T+4h, ~20 min human — §7). Session pings the operator and, while waiting, only does
autonomous-safe work (drafting journey briefs, verification).**

**P5 — Ten-domain journey test (mostly serial, ≤2 in flight; ~4–6h; the GLM-heavy phase — off-peak).**
Quota-weather check first (one cheap real dispatch; two 1305s within the hour → shift journeys later, pull
P6/P7 reading work forward). Then J1..J10 per §8: wizard (answer-sheet) → deep plan where marked → dispatch →
judge/critic → deliverable → member visibility. Per journey: ledger snapshot before/after, question log
updated, score row written, deliverable copied to `evidence/journeys/J<N>-<domain>/`. Journeys double as the
overhaul's live-drive acceptance: record judge-ledger rows (expect ≤2), round-1 verdict, pre-gate fired,
delta-round input size. Member re-runs (J2 visibility, J8 full) as `campaign-member`. **Flush after EVERY
journey.**

**P6 — Cross-cutting synthesis probes (serial, ~45 min).**
Teach round-trip (G3), consolidation sweep + briefing (G4), adopt flow (G10), decision-inbox states
accumulated during journeys, question-log metrics (G2), soak harvest.

**P7 — Adversarial verification + scorecards + architecture verdict (~1.5h; verification fan-out parallel).**
Refute-by-default verifiers over every unverified finding. Fill the goal/subsystem/domain scorecards; write
the architecture verdict §5a–d of FINAL-REVIEW (per-goal fit; better-way table
`goal/subsystem | current | proper way (cited) | migration cost | SOUND/REFACTOR/REBUILD`; frontier
comparison; adopted directions). Draft FIX-RUNBOOK batches (FIX + REBUILD kinds, §9) + IMPROVEMENTS (max 7 +
rejects with earn-back triggers; must decide: added-value benchmark scheduling, quality-loop P1/P2 parked
items, BUSINESS-CONTEXT/exemplar seeding, **backup/DR for nexus.db + ~/knowledge + ~/.hermes + secret.key**,
1-page member ops runbook). Prepare batch-0 (trivial one-liners) as a PROPOSED diff — not committed.

**→ ATTENDED BLOCK 2 (~T+9–11h, ~25 min human — §7).**

**P8 — Close-out (serial, ~40 min).**
Batch-0 commit if authorized (pre-commit gate green). Scratch cleanup: delete `campaign-*`
tasks/workflows/users/repos per the AB2-confirmed list. **Stub-hygiene sweep (end)** + scheduler-leak check →
`evidence/probes/stub-sweep-end.txt`. Finalize FINAL-REVIEW §1 executive verdict (verdict first, ALWAYS
caveated "pending the separate security sweep", top-5 findings, doc paths). Final PROGRESS tick; auto-memory
update (campaign executed, verdict line, doc links). Final message to the operator: verdict + top-5 + where
everything lives + the literal next step (read FIX-RUNBOOK → launch B1).

**Totals:** ~10–13h wall (~45 min attended), ~$150–250 API-equivalent Claude (subscription-billed), ~10–25M
GLM tokens. Context exhaustion mid-run is EXPECTED and fine — the resume protocol (§12) is stateless.

## §7 Attended blocks — exact human checklists

**ATTENDED BLOCK 1 (desktop, ~20 min).** The session posts this checklist and waits:
1. Sit at the desktop. Open `https://127.0.0.1:8777` in the browser. If a certificate warning appears, click
   Advanced → Proceed (self-signed is expected).
2. Log in as the owner account.
3. Click through ALL nav tabs top to bottom, comparing against the screenshot list the session posted. Say
   out loud (type to the session) anything ugly, confusing, or broken per tab — it records your words verbatim.
4. Open the J.A.R.V.I.S tab. Click the mic button. Say: "What is on the board right now?" — EXPECTED: your
   words appear as a transcript, a spoken reply plays in the Piper voice, the avatar switches to a talking
   state with mouth movement.
5. Repeat step 4 once (reliability must be 2/2).
6. While it is speaking a reply, start talking — EXPECTED: the voice stops and it listens (barge-in works).
7. Click into any text field (e.g. the Notes panel), press the dictation hotkey (your dedicated dictation
   key), speak one sentence, press the key again — EXPECTED: an overlay pill appeared while recording and
   your sentence is typed into the field.
8. Start meeting mode (Meetings tab → record), say two sentences, stop it — EXPECTED: a transcript file
   appears in the Meetings tab. (This recording is reused for the meetings→summarize→workflow chain.)
9. The session now shows the journey plan + spend envelope (GLM token estimate + frontier budget). Reply
   `GO` or state adjustments. Also answer any batched [UNSURE] questions it queued — short answers, only
   what's asked.
Done-when: all 9 done; the session writes `evidence/attended-block-1.md` and resumes autonomously.

**ATTENDED BLOCK 2 (phone + desktop, ~25 min).**
1. On your phone (connected to the Tailnet), open the dashboard URL and log in as the owner.
2. On the phone: open the Tasks board, open one task's detail, scroll it, decide one approval card, open
   J.A.R.V.I.S — say what is broken or awkward; the session records it verbatim.
3. On the desktop: the session shows 3 journey deliverables (best / median / worst). Read each and answer:
   "Would I send this to a client?" (yes / yes-with-edits / no + one line why).
4. Decide the Decision-inbox cards accumulated during the journeys (approve/reject each).
5. Read the draft goal scorecard G1–G10. Object where you disagree — objections are recorded; the session may
   keep its verdict with reasons; both are recorded.
6. The session shows the batch-0 one-liner diff. Reply `COMMIT` to authorize or `SKIP` to reject.
7. The session lists every `campaign-*` artifact it created. Confirm deletion (or name anything to keep).
Done-when: all 7 done; the session writes `evidence/attended-block-2.md`.

## §8 Journey protocol + campaign answer sheet

Method: ONE realistic end-to-end journey per domain — wizard → (deep plan where marked) → dispatch →
judge/critic → deliverable → member visibility — as the owner; J2 (visibility) and J8 (full) re-run as
scratch member `campaign-member`. Score each journey: friction points, framing/knowledge gaps, latency,
output quality vs `~/knowledge/domains/<domain>/RUBRIC.md`, and "would a non-IT member succeed unaided?".

**ANSWER-SHEET protocol (binding — bench-02 pattern):** Session A plays the client.
1. Answer ONLY what is asked; never volunteer extra requirements.
2. Use the canonical answers below word-for-word where they fit; improvised answers = one short sentence.
3. Off-sheet question → "You decide — whatever a typical client would want." (logged as off-sheet).
4. Log EVERY question + answer + timestamp → `evidence/question-log.md` (this log is primary G2 evidence:
   right questions? too many? none where one was needed?).
5. Answer skippable interview questions rather than skipping (comparability). Deep-plan interviews follow the
   same sheet.

**Canonical answers (master):** tech stack → "your choice, must run locally" · region/currency → "Euros,
German market" · audience/brand/business facts → use `~/knowledge/BUSINESS-CONTEXT.md`; if a fact is missing
there → "You decide, note the assumption" · deadline → "end-to-end working first, polish second" · budget
questions → "sensible default, note alternatives" · scope pushback → "smallest version that fully works".

**Journeys** (mode = involvement/spend; SR = Super Result flag):
- **J1 software-dev** — assisted/optimal, deep plan YES — "Add a small CSV-export command to this repo" on a
  scratch clone at `~/Projects/campaign-swdev` (local bare origin; stubbed `gh` per the block2-gate pattern);
  expects house pipeline, review v2, PR flow, ▶ Test-app preview.
- **J2 SaaS strategy** — assisted/optimal, deep plan YES, member visibility re-run — "Positioning + pricing
  one-pager for our AI-agent consulting offer."
- **J3 consulting** — assisted/optimal — "Discovery-call prep + a client-ready proposal for a mid-size
  ecommerce client" (PDF expected AUTONOMOUSLY — G8).
- **J4 research** — assisted/smart + SR ON — "Verified multi-source brief: local-LLM inference options for a
  12 GB GPU workstation, mid-2026" (web tooling must work; G5/G6 evidence).
- **J5 marketing** — assisted/optimal — "Landing-page copy for the webshop demo" (live task, not eval-stub).
- **J6 bizdev** — assisted/optimal — "Cold-outreach sequence (3 emails) + a 25-prospect research homework
  pattern for the consulting offer."
- **J7 content** — assisted/optimal — "Newsletter article: what an AI agent OS does for a small business"
  (STYLE-VOICE compliance checked against ~/knowledge).
- **J8 brand** — assisted/**eco**, member FULL re-run — "Naming + positioning one-pager for the internal
  agent-OS product" (G6 eco-floor evidence; cheap).
- **J9 ecommerce** — assisted/optimal — "One marketplace listing for a refurbished RTX-4090 workstation,
  incl. one product image" (SDXL image path — G8).
- **J10 music-dj** — assisted/optimal — "Release plan + set plan for a 2-track EP" — the deliverable MUST
  include an honest "what Nexus cannot do here" section (audio production itself) with adjacent wins instead.
Cross-cutting member checks after J-runs: onboarding overlay renders for `campaign-member`; per-user model
routing + credentials; member sees shared lessons, cannot write admin scopes; approvals UX on the phone (AB2).

## §9 Deliverable formats

**FINAL-REVIEW-2026-07-13.md skeleton** (created in P0, appended per phase):
```
# FINAL REVIEW — 2026-07-13 (Session A start <ts>, HEAD <sha>)
## 0. Status (live)                 one line per phase, updated on every flush
## 1. Executive verdict             filled P8: ready-for-daily-use line, top-5 findings, security-PENDING caveat
## 2. Goal scorecard (G1–G10)       GO / GO-WITH-FIXES / NO-GO + evidence line + finding IDs
## 3. Subsystem scorecard           dispatch/lanes · workflows+replan · wizard+deep-plan · judge/critic/SR ·
                                    autopilot+economics · memory/learning · JARVIS · dictation/meetings/STT ·
                                    productivity tools · notes/deliverables · multi-user surface · scheduler ·
                                    settings/credentials · observability · SECURITY = PENDING (fixed row)
## 4. Domain scorecard (J1–J10)     + friction / latency / quality-vs-RUBRIC / unaided? columns
## 5. Architecture verdict          a) per-goal fit  b) better-way table:
                                    goal/subsystem | current | proper way (cited) | migration cost | SOUND/REFACTOR/REBUILD
                                    c) frontier comparison (cited)  d) adopted directions
## 6. Findings ledger               F-001…, grouped P0/P1/P2 (P3 = compressed table); full format per §4;
                                    REFUTED appendix with reasons
## 7. Prior-findings reconciliation 37-row CR-# table: status at HEAD + evidence
## 8. Question-log summary          per journey: #questions, quality notes (G2 evidence)
## 9. Security routing list         one-liners routed to SECURITY-SWEEP-PLAN-2026-07-12.md
```

**FIX-RUNBOOK-2026-07-13.md** — header: rules for fix sessions (one batch = one fresh session = one commit;
model per batch header; batch verify commands + `bash scripts/verify.sh` green + `systemctl --user restart
nexus` + re-drive the fixed surface before committing; tick the batch here and in PROGRESS.md; if a batch ran
any e2e gate, re-check the stub keys after). Batches ordered P0 → P1 → P2 + a Deferred/Accepted section.
Two batch kinds:

*FIX batch template:*
```
### Batch B<N> — <title> — P<sev> — kind: FIX — model: <Opus 4.8 | Fable 5> — est <min> — payoff: <one line>
Findings: F-0xx, F-0yy (read their ledger entries first)
Files: <paths>
Prompt:
```<fenced copy-paste prompt — self-contained: context, exact changes, what NOT to touch>```
Verify: <exact commands + expected output>
Rollback: git revert <batch commit>
```

*REBUILD batch template (verdict was REBUILD-PROPERLY):*
```
### Batch R<N> — rebuild: <subsystem> — P<sev> — kind: REBUILD — model: Fable 5 — est <hours> — payoff: <one line>
Design note: intended goal (from TOOL-DOCUMENTATION) · why the current implementation fails it (finding IDs) ·
             the proper approach with citations (from P2/P7 research) · explicit non-goals
Procedure: operator skims the design note and replies GO → develop in a git worktree (tool stays live on main)
           → subsystem e2e + full verify.sh green in the worktree → land as ONE reviewed merge commit → restart
           → re-drive the subsystem live
Must-not-regress: <list of neighboring behaviors with their verify commands>
Rollback: git revert -m 1 <merge commit>
```
Assignment rule: mechanical/decided fixes → Opus 4.8; judgment-heavy fixes and ALL rebuilds → Fable 5.

**IMPROVEMENTS-2026-07-13.md** — max 7 adopted additions (title, goals served, expected payoff per user-week,
effort, 2-user payoff justification, honest migration cost) + every rejected candidate with an earn-back
trigger.

**evidence/ layout:** `gate-outputs/` (one .txt per gate) · `screenshots/` (desktop + phone sets) ·
`question-log.md` · `journeys/J<N>-<domain>/` · `ledger-snapshots/` · `probes/` (stub sweeps, responsiveness,
VRAM, soak) · `reconciliation/` · `attended-block-{1,2}.md`.

**PROGRESS.md skeleton:**
```
# CAMPAIGN PROGRESS — production-readiness final review
Session A start: <ts> · model Fable 5 · HEAD <sha> · DB backup: app/nexus.db.bak-final-review
Resume rule: re-do the FIRST unticked item from scratch; every tick names its evidence file.
## Phase checklist
- [x] P0.4 stub-hygiene sweep — clean — evidence/probes/stub-sweep-start.txt — 09:12
- [ ] P1.2 verify.sh — …
## Counters
Findings: P0 n · P1 n · P2 n · P3 n · refuted n | Journeys: n/10 | Attended blocks: 0/2
## Session B/C ledger (filled later)
- [ ] B1 … | - [ ] R1 … | - [ ] C verdict: …
```

## §10 Session B — fix & rebuild batches

- Trigger: operator has read FINAL-REVIEW §1 and (optionally edited then) accepted FIX-RUNBOOK.
- FIX batches: one batch per fresh session, exactly the batch scope. A deeper problem discovered mid-fix is
  WRITTEN UP as a new finding, not fixed inline — EXCEPT when its root cause is already a REBUILD batch, which
  then owns it.
- REBUILD batches: design-note GO from the operator first; worktree development; the live service keeps
  running `main`; subsystem gates + full verify.sh green in the worktree BEFORE the merge lands; one merge
  commit; restart; live re-drive. One subsystem per session. Order rebuilds by (goal impact ÷ risk).
- P0 batches complete before the tool returns to daily use; P1 within the first week alongside real use;
  P2 opportunistic.
- Any batch that ran an e2e gate re-checks the stub-hygiene keys before finishing (3 prior leak incidents).

## §11 Session C — re-verify judge

Fresh Fable 5 session. Refute-by-default: fix-session reports and commit messages are CLAIMS, not evidence.
Personally re-runs the full gate sweep (P1 order, outputs to evidence/), re-runs the stub-hygiene sweep, and
re-drives every fixed/rebuilt surface on the live HTTPS UI. Per FIX-RUNBOOK item: **VERIFIED-FIXED** (one
evidence line) / **STILL-BROKEN** (goes to the blocking list) / **DEFERRED-OK** (owner-accepted, reason
quoted). Rebuilt subsystems are additionally verified against their design notes (intended goal reached the
proper way; must-not-regress list green). Updates the FINAL-REVIEW scorecards in place (marked "post-fix,
Session C <date>"), appends a Session-C section, and ends with exactly one line: `VERDICT: SHIP` or
`VERDICT: REVISE` + the blocking list. Session C never edits code. The security row stays PENDING.

## §12 Resume protocol (any session, any interruption)

Operator: `cd ~/Nexus-Agentic-Coding-Setup && claude --continue`, then paste:
```
Resume the production-readiness campaign. Read Production-Readiness-Review-1/PROGRESS.md and
PRODUCTION-READINESS-REVIEW-PLAN-2026-07-13.md, run git status and the stub-hygiene sweep, then re-do the
FIRST unticked PROGRESS item from scratch and continue the plan. Do not trust any in-context memory of prior
progress over the files on disk.
```
If `--continue` has nothing to resume: start fresh (`claude`, `/model` → Fable 5) and paste the same text —
the protocol is stateless by design. The stub sweep on resume is mandatory: a crashed session is exactly when
stubs leak.

## §13 Risks & mitigations

| Risk | Mitigation (baked in) |
|---|---|
| Context exhaustion mid-Session-A (near-certain at 10–13h) | stateless resume (§12) + per-phase/per-journey disk flush |
| Overhaul half-landed or still in flight at launch | preflight hard gate (steps 2–3) + P3 claims verification |
| Campaign grades the OLD judge loop by mistake | G5/G6 expectations pinned to the overhaul contract |
| Stub leak FROM this campaign (3 prior incidents) | 4 mandatory sweeps: P0, after any gate crash, every resume, P8; Session C repeats |
| GLM 1305 load-shedding mid-journeys | quota-weather check at P5 entry; journey marked PARTIAL + retried off-peak; never a campaign failure |
| Judge-loop runaway burning frontier calls | system self-cap is UNDER TEST (violation = P0) + AB1 spend envelope + per-journey ledger snapshots |
| Fable 5 guardrail trip on security-shaped incidentals | §1 hygiene: route-and-continue, never rephrase-and-retry |
| Board/data pollution, touching real member data | `campaign-` prefix, scratch-member pattern, AB2-confirmed cleanup, DB backup, restart-y gates last |
| Double-counting already-fixed findings | P3 reconciliation table, carried IDs `F-0xx (carried: CR-#n)` |
| Attended block hits while operator away | blocks are the only human dependencies; session parks on them but continues autonomous-safe work |
| Verdict inflation / judge grades the report not the system | evidence artifact per scorecard cell; Session C re-runs everything personally; G6 pre-capped |
| Rebuild scope explosion / tool broken mid-rebuild | design-note GO gate, worktree dev, land-only-gate-green, one subsystem/session, Session C design-note check |
| This plan going stale like its predecessor | committed in preflight; no file:line anchors (symbols/settings/scripts only) |

## §14 OPERATOR RUNBOOK — exact steps, one action each

**PREFLIGHT — AFTER the judge-overhaul session has finished, BEFORE anything else (~15 min)**
1. Open a terminal: `cd ~/Nexus-Agentic-Coding-Setup`
2. Run: `git status --short` — EXPECTED: no `M`-flagged files (a clean tree; only `??` untracked docs are
   fine). If ANY `M app/...` lines remain, the overhaul has NOT landed — STOP, let that session finish (or
   tell it to finish + commit + push), then restart this preflight.
3. Run: `git log --oneline -8` — EXPECTED: the judge-overhaul commits at the top. If they are missing, STOP —
   same as step 2.
4. Open `https://127.0.0.1:8777` → Tasks board — EXPECTED: no bench-02 run or other big dispatch currently
   streaming (this campaign restarts the service several times). If one is running, wait for it.
5. Commit the campaign docs:
   `git add PRODUCTION-READINESS-REVIEW-PLAN-2026-07-13.md Production-Readiness-Review-1/ SECURITY-SWEEP-PLAN-2026-07-12.md CODE-REVIEW-FINDINGS-2026-07-12.md && git commit -m "docs: final readiness review campaign 2026-07-13 (plan + tool documentation)"`
   — EXPECTED: pre-commit verify.sh runs and passes, commit created.
6. Run: `git push` — EXPECTED: pushed to origin/main clean.
7. Start the stack: `nexus-up` — EXPECTED: ollama + qdrant/langfuse containers + timers + nexus.service come
   up; it opens the dashboard. (Skip if already running.)
8. Run: `python3 setup/guardian/guardian.py` — EXPECTED: `overall=OK`, 8/8 core-mods applied. Anything else:
   STOP and fix before launch (keystone mod = session-model-api-server).
9. In the browser, log in once as the owner (an anonymous `/api/health` 401 is normal, not a failure).
10. Back up the DB (consistent snapshot — a plain `cp` would be a torn copy because SQLite WAL holds recent
    state; see TOOL-DOCUMENTATION, Data layer):
    `rm -f app/nexus.db.bak-final-review && app/.venv/bin/python -c "import sqlite3; sqlite3.connect('app/nexus.db').execute(\"VACUUM INTO 'app/nexus.db.bak-final-review'\")"`
    — EXPECTED: command exits silently and `ls -la app/nexus.db.bak-final-review` shows a file about the size
    of nexus.db.
11. Run: `df -h /home | tail -1` — EXPECTED: >15 GB free.
12. Physical prep: plug in / test the mic you'll use for Attended Block 1; make sure your phone is on the
    Tailnet for Attended Block 2.
13. Timing: launch in an off-peak window if possible — the GLM-heavy journey phase starts ~4h in (GLM quota
    burns ~3× at peak; Z.ai error 1305 load-shedding is real).

**LAUNCH SESSION A**
14. Run: `claude --model claude-fable-5 --permission-mode acceptEdits`
    (If the model flag errors: run `claude --permission-mode acceptEdits`, then type `/model` and pick
    Fable 5.)
15. Paste the Session-A kickoff prompt from §15 (block 1) and send.
16. EXPECTED within ~10 min: it confirms the plan + read-first docs, creates
    `Production-Readiness-Review-1/PROGRESS.md` + the FINAL-REVIEW skeleton, reports the stub-sweep result,
    and starts Phase 1. You can leave.
17. PINGS TO EXPECT: (a) ~T+4h "ATTENDED BLOCK 1 ready" → do §7 block 1 (9 steps, ~20 min);
    (b) occasional batched [UNSURE] questions → answer short, only what's asked;
    (c) ~T+9–11h "ATTENDED BLOCK 2 ready" → do §7 block 2 (7 steps, ~25 min);
    (d) the final message: verdict + top-5 findings + doc paths.
18. DONE-WHEN (Session A): FINAL-REVIEW has all 9 sections filled, FIX-RUNBOOK + IMPROVEMENTS exist, every
    PROGRESS phase is ticked, stub-sweep-end is clean, and the final chat message states the verdict.

**IF THE SESSION DIES / THE PC SLEEPS / CONTEXT FILLS**
19. Run: `cd ~/Nexus-Agentic-Coding-Setup && claude --continue`
20. Paste the §12 resume text. If `--continue` has nothing to resume: `claude` → `/model` → Fable 5 → paste
    the same resume text. EXPECTED: it re-reads PROGRESS.md, re-runs the stub sweep, redoes the first
    unticked item.

**AFTER SESSION A (you, ~30 min)**
21. Read `Production-Readiness-Review-1/FINAL-REVIEW-2026-07-13.md` §1, then skim the P0/P1 findings.
22. Read `FIX-RUNBOOK-2026-07-13.md`. Edit it directly to strike or reorder batches you disagree with.
23. Run: `git add Production-Readiness-Review-1 && git commit -m "review: Session A findings + fix runbook + improvements" && git push`

**SESSIONS B1..Bn — one batch per session, in runbook order**
24. For the next unticked batch: `claude --permission-mode acceptEdits`, then `/model` → the model named in
    the batch header (Opus 4.8 unless it says Fable 5; ALL R-batches = Fable 5).
25. Paste the Session-B template prompt from §15 (block 2) with the batch ID filled in. For an R-batch, first
    read its design note; reply `GO` when it asks.
26. EXPECTED per batch: one commit (R-batches: one merge commit), batch verify + verify.sh green, service
    restarted, surface re-driven, batch ticked in FIX-RUNBOOK + PROGRESS.md. Spot-check:
    `git log --oneline -3`.
27. Repeat 24–26 until all P0 batches are done (only then resume daily use), then P1 batches through the
    week. After the last batch: `git push`.

**SESSION C — re-verify judge**
28. Off-peak preferred. Run: `claude --model claude-fable-5 --permission-mode acceptEdits`
29. Paste the Session-C kickoff prompt from §15 (block 3).
30. EXPECTED: ~2–3h; it re-runs all gates itself, re-drives fixed surfaces, updates scorecards, ends with
    `VERDICT: SHIP` or `VERDICT: REVISE` + a blocking list. On REVISE: turn the blocking list into new
    B-batches (steps 24–26), then rerun Session C. Loop until SHIP.

**CLOSE-OUT**
31. Run: `git add -A Production-Readiness-Review-1 && git commit -m "review: campaign complete — Session C verdict" && git push`
32. In any Claude session in this repo, say: "Update project memory: readiness campaign complete, verdict
    <SHIP/...>, security sweep still pending."
33. Schedule/run the security sweep (`SECURITY-SWEEP-PLAN-2026-07-12.md`, own small session, **Opus 4.8**) —
    readiness stays PENDING until it lands.
34. Optional, after a week of stable daily use: `rm app/nexus.db.bak-final-review`

## §15 Kickoff prompts (verbatim)

**Block 1 — Session A:**
```
Execute PRODUCTION-READINESS-REVIEW-PLAN-2026-07-13.md — Session A, ultracode.
You are the reviewer, not the fixer: findings are PROPOSED (only the labeled batch-0 one-liners get
committed, at the end, after my Block-2 approval). Zero trust in prior test reports — re-verify everything
yourself at runtime, and judge design against Production-Readiness-Review-1/TOOL-DOCUMENTATION-2026-07-13.md
(its verdicts are hypotheses to confirm or refute). Work the phases in order; after every phase update
Production-Readiness-Review-1/PROGRESS.md and flush findings to FINAL-REVIEW-2026-07-13.md. Ping me ONLY at
the two ATTENDED BLOCKS and for cost-risky approvals; play the client yourself via the plan's ANSWER-SHEET
and log every question. Functional QA only — no security probing, per the plan's §1 guardrail hygiene.
Start with Phase 0 and report the stub-sweep result before anything else.
```

**Block 2 — Session B (fill `<BATCH-ID>`):**
```
Execute batch <BATCH-ID> of Production-Readiness-Review-1/FIX-RUNBOOK-2026-07-13.md.
Read the batch entry and the finding entries it cites in FINAL-REVIEW-2026-07-13.md first. FIX batch: fix
exactly that scope — nothing else; a deeper problem you uncover becomes a new finding write-up, not a bigger
fix. REBUILD batch: present the design note and wait for my GO, then build it properly in a git worktree
(main stays live), gates green in the worktree, land as one merge commit. Before finishing: run the batch's
verify commands, then bash scripts/verify.sh from app/ (green), then systemctl --user restart nexus and
re-drive the changed surface on https://127.0.0.1:8777. Tick the batch in FIX-RUNBOOK and PROGRESS.md. If you
ran any e2e gate, re-check the stub-hygiene settings keys before you finish.
```

**Block 3 — Session C:**
```
Execute PRODUCTION-READINESS-REVIEW-PLAN-2026-07-13.md — Session C, the re-verify judge, ultracode.
Refute by default: the fix sessions' reports and commit messages are claims, not evidence. Re-run the full
gate sweep personally (plan §6 P1 order, outputs to evidence/), re-run the stub-hygiene sweep, and re-drive
every fixed or rebuilt surface on the live HTTPS UI yourself. Verify every REBUILD against its design note
and must-not-regress list. Mark every FIX-RUNBOOK item VERIFIED-FIXED / STILL-BROKEN / DEFERRED-OK with one
evidence line each, update the scorecards in FINAL-REVIEW-2026-07-13.md (marked post-fix), and end with
exactly one line: VERDICT: SHIP or VERDICT: REVISE plus the blocking list. You never edit code. The security
row stays PENDING (separate sweep).
```

## §16 QUICK REFERENCE

| Phase | Who | Model | Input | Output | Done-when |
|---|---|---|---|---|---|
| Preflight 1–13 | operator | — | §14 | clean tree @ overhaul HEAD, docs pushed, stack up, guardian 8/8, DB backup | steps 2,3,8,10 all EXPECTED |
| Session A (P0–P8) | Claude, ultracode | Fable 5 | this plan §§1–13 | FINAL-REVIEW, FIX-RUNBOOK, IMPROVEMENTS, evidence/, PROGRESS | all PROGRESS ticks + clean stub-sweep-end |
| Attended Block 1 | operator | — | §7 (9 steps) | attended-block-1.md, journey GO | voice 2/2, dictation typed, spend approved |
| Attended Block 2 | operator | — | §7 (7 steps) | attended-block-2.md, batch-0 + cleanup decisions | phone OK, deliverables judged |
| Sessions B/R | Claude | Opus 4.8 / Fable 5 (R: always Fable 5) | FIX-RUNBOOK batch | 1 commit per batch, ticks | batch verify + verify.sh green + surface re-driven |
| Session C | Claude (judge) | Fable 5 | §11 + both docs | updated scorecards + VERDICT line | SHIP (or REVISE list → new batches → rerun C) |
| Close-out 31–34 | operator | — | §14 | pushed repo, memory updated, security sweep scheduled | steps 31–33 done |
