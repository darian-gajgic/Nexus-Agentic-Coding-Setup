# Implementation Report — Appendix C (beat-the-top-tier program, Phase 7)

**Date:** 2026-07-11
**Phase:** 7 of the Quality Program (`EXECUTION-RUNBOOK-2026-07-10.md`)
**Executes:** `SUPER-RESULT-PLAN-2026-07-09.md` Appendix C, with the binding
build order + corrections from `QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md` §5
(C-6/C-7/C-8) and `QUALITY-AUTOPILOT-PLAN-2026-07-10.md` Part 4 (P1/P5).
**Model:** Opus 4.8 (implementation session, headless program runner).

Build order followed (per C-6): **C3 → C1a/C1c/C1b/C1d → C2**, plus C5 =
escalation-threshold settings only. C4 (benchmark harness) is deferred to Phase 8;
C6 (flywheel) already landed as Q2 in Phase 3.

---

## What shipped

### C3 — Full-cost ledger + JSON-envelope unwrap (contract C-8)
The frontier critic/judge/escalation runs bill the Claude CLI subscription
invisibly (B7). C3 makes that spend visible and puts it next to the GLM spend so
"beats Opus, cheaper than Fable" is a checkable claim.

- **Contract change C-8 (binding).** `cverify` and `cjudge` now pass
  `--output-format json`, so the model's reply arrives wrapped in a JSON envelope
  `{result, usage, total_cost_usd, modelUsage}`. The sentinel parsers
  (`parse_critic_json`, `parse_judge_metrics`) consume the INNER text, so
  `run_critic_cmd`/`run_judge_cmd` now unwrap `.result` via the new
  `evals._unwrap_frontier_output()` **before** parsing. A stubbed or legacy
  plain-text output has no envelope and passes straight through unchanged →
  the sentinel search still works and the ledger falls back to a transcript-size
  estimate. Verified end-to-end in the gate (envelope → parse; stub → passthrough).
- **Per-model price table** seeded in settings (`cost.model_prices`) from
  `MODEL-PRICING-2026-07-10.md`: GLM-5.2 $1.40/$4.40 (cache-hit $0.26); Opus 4.8
  $5/$25 (cache write $6.25, hit $0.50); Fable 5 $10/$50 (cache write $12.50, hit
  $1) — per 1M tokens. GLM 5.1/4.5-air/turbo priced at the GLM-5.2 public rate
  (documented default; no separate sheet). Fable 5 is priced for the reference/
  comparison arm only — never assigned. `cost.output_fraction` (default 0.5) blends
  the GLM `tokens_used` counter (input+output mixed) into a single rate.
- **Ledger persistence.** New `frontier_ledger` table (one row per run) + per-task
  accumulators `tasks.frontier_tokens` / `frontier_cost_usd`. Each critic/judge/
  escalation run records the envelope's OWN tokens + dollars (authoritative for
  frontier runs); a stub/legacy run records a transcript-size token estimate priced
  from the table (`source='estimate'`). Eval-runner judge spend is tagged by
  `run_id` for the Phase-8 campaign.
- **Reporting.** `db.task_cost_ledger()` / `workflow_cost_ledger()` sum the GLM
  estimate (from `tokens_used` × the table) + the frontier envelope dollars into a
  total, **labelled "API-equivalent USD" — a comparison figure, not a bill**.
  Endpoints `GET /api/tasks/{id}/ledger` and `GET /api/workflows/{id}/ledger`; the
  Deliverables list carries `frontier_cost_usd` + a combined `cost_usd`.

### C1a — `escalation_model` registry purpose (P5)
`spec_model` already landed with Deep Plan (Phase 5), so it was seeded once — not
duplicated. Added `escalation_model` to `db.MODEL_PURPOSES`, `sreg.PURPOSES`,
`sreg.CLI_PURPOSES`, the assignment API/UI (data-driven; `PURPOSE_ROUTES` in
app.js gained `escalation_model: 'cli'`), and both the fresh-install seed and a
marker-guarded migration for existing installs (`migrated.escalation_model`).
Default = the frontier-judge tier (Opus 4.8), verified seeded in the live DB.
`evals.escalation_model_for()` resolves it (mirrors `judge_model_for`). Every
frontier call goes through the P1 `_FRONTIER_GATE` semaphore (already in place).
**Fable 5 is never assigned to any purpose.**

### C1c — Escalated rework (setting-gated `super.escalation`)
On a REWRITE verdict — or the round cap with criticals still open — the rework
itself runs on the `escalation_model` (judgment-tier). New `cexec` script
(vendored `setup/bin/` + installed `~/.local/bin/`, byte-identical): cverify minus
the sandbox — the frontier model rewrites the deliverable in the REAL workspace,
handed the full dossier (`evals.build_escalation_dossier`: brief + verified
findings + contradictions + missing + revision brief + open comments/critique
history + clipped sibling reports). Deny rules still forbid push/remote/gh/sudo.

- `evals.run_escalation_cmd()` writes the dossier into the workspace, runs cexec
  through the `_FRONTIER_GATE`, unwraps the envelope (C-8), books the spend to the
  C3 ledger (`kind='escalation'`), and cleans up the dossier.
- Server: `_escalation_thread` + `POST /api/tasks/{id}/escalate` (CAS-guarded to
  `critic_verdict='escalating'` — no double-spawn; 409 on a lost race). It
  snapshots the failing version as `deliverable.v<N>.md` (evidence for the next
  critic) and — **only when the rework actually rewrote the deliverable** (content
  hash changed AND no failure marker; see the phase7 judge round below) — consumes
  the open comments, advances the version clock, and clears the verdict so the
  sweep re-critiques the rewritten deliverable. Frontier quota is classified like
  the critic (backoff + requeue, never `error`/human-escalate).
- Loop hook (`loop_engine._try_escalate_super`): fires on REWRITE (closed mode)
  and on the round cap when criticals remain, bounded by `super.escalation_max`
  (default 1) — after the budget is spent it falls through to the human
  checkpoint. Off by default.
- **C-7 honored:** the floor this buys *approaches* judgment-tier-direct but is an
  empirical claim (a bad dossier can anchor the rework below a clean direct pass) —
  documented in cexec + the setting help; Phase 8 measures it.

### C1b — Critic patch field (CriticGPT pattern)
`cverify` findings gained an optional `patch` field (unified-diff hunk) for
mechanical critical/high fixes. `parse_critic_json` captures it; a new
`review_comments.patch` column stores it in full (out of the 500-char body cap);
`_retry_task` re-attaches it to the executor feedback as a fenced ```diff block —
so the executor applies it verbatim instead of re-deriving the fix from prose.

### C1d — Best-of-2 executor drafts — **DEFERRED (see Deviations)**

### C2 — Registry-only model references (rotation readiness)
Every hardcoded routing model-name fallback now resolves through **one** map,
`database.FALLBACK_MODELS` (+ `fallback_model()` / `worker_fallback_models()`).
Audited out of `server.py` (`_TASK_MODELS`, `_model_guidance`, `_clamp_wizard_task`
default, the divergence-sampler easy model, the C3 pricing fallbacks),
`hermes_dispatch.py` (`DEFAULT_MODEL`), and the eval runner. A **generation
rotation = registry edits (model_assignments) + Phase-8 rerun; the fallback map is
the safety net, not the routing table.** (The dispatch overload fallback stays in
the `dispatch.fallback_model` setting — already config-surface.)

- **rule 3 (Eco model floor)** — was P2-staged pending C2, now completed:
  `autopilot.derive` emits `model_floor: "easy"` for Eco (the light-executor tier),
  `None` for Optimal/Smart; `_repair_workflow`/`_clamp_wizard_task` floor non-dev,
  non-high-stakes work stages to it (dev stages + risk keep the hard tier). An
  empirical claim ("same answer, cheaper") — Phase 8 validates or reverts.
- **L4 fingerprint** (`routing.config_fingerprint`) now spans `spec_model` +
  `escalation_model` too, so rotating either judgment tier invalidates tuned
  thresholds (e.g. the escalation thresholds Phase 8 tunes) back to heuristics.

### C5 — Escalation-threshold settings only
`super.escalation_trigger` (`off` | `rewrite` | `rewrite_or_cap`, default
`rewrite_or_cap`) + `super.escalation_max`. A task carrying a spend profile uses
the profile's derived value instead (Eco off / Optimal rewrite / Smart
rewrite_or_cap — the P2-staged escalation derivation, now consumed by
`loop_engine._escalation_mode`). C1c's floor is setting-gated; Phase 8 tunes the
thresholds from measured data. (Added a generic `enum` setting type + validator +
dropdown rendering to support the threshold picker.)

---

## Binding corrections honored
- **C-6** — build order followed (C3 → C1a/C1c/C1b/C1d → C2; C4 deferred; C5 =
  settings only).
- **C-7** — the C1c floor is documented as an empirical claim, not a guarantee.
- **C-8** — the `--output-format json` envelope is unwrapped BEFORE the sentinel
  parsers run; usage + `total_cost_usd` persisted; transcript-size estimate kept as
  fallback; regression check added. Both copies of cverify/cjudge updated
  (byte-identical).
- **P1** — every frontier call (critic/judge/spec/escalation) goes through the
  `_FRONTIER_GATE` semaphore; escalation quota is classified + backed off, never an
  `error`/human escalation.
- **P5** — `MODEL_PURPOSES` + the assignment UI extended in the same step that
  seeds `escalation_model`.

---

## Gates run (all green)
- **Static** `scripts/verify.sh` — **436/436** (was 409; +27 Appendix-C checks
  across C3/C1a/C1b/C1c/C2/rule3/C5/rule12).
- **Super Result e2e** `scripts/verify_super_result_e2e.py` — full live-sweep run,
  **83/83 (0 failed)**. Includes 12 C3 checks (envelope unwrap, price table, ledger
  math + API), 9 C1c checks (dossier, endpoint gating + CAS, live escalated rework
  rewriting the deliverable, v-snapshot, ledger booking, re-critique, comment
  consumption), 2 C1b checks (patch stored + re-attached as a fenced diff),
  **+14 phase7 judge-REVISE regression checks** (finding 1: PATH augmentation +
  claude resolves under a stripped service PATH; finding 2: exit-127 and
  byte-identical reworks do not false-SHIP — comments kept, clock frozen,
  verdict→error), and **+4 judge-round-2 regression checks** (NULL-model task and
  workflow ledgers price > $0 at the resolved `complicated` model, an explicit
  model still wins, `/api/deliverables` costs the same task > $0).
- **Quality Autopilot e2e** `scripts/verify_autopilot_e2e.py` — **56/56**
  (rule-3 model-floor now asserts DERIVED, not staged).
- **Deep Plan e2e** `scripts/verify_deep_plan_e2e.py` — **21/21** (spec_model /
  MODEL_PURPOSES changes are backward-compatible).
- Service restarts clean; https://127.0.0.1:8777 loads; migration is idempotent
  (new columns/table/seed applied to the live DB with no data loss;
  `nexus.db.bak-phase7` taken).

---

## Judge REVISE round (phase7) — blocking findings fixed (2026-07-11)

The independent judge returned REVISE with two blocking findings. Both were
re-verified against HEAD (reproduced), then fixed with a regression check each and
a real live re-drive.

### Finding 1 — service-spawned `claude` exits 127 (escalation never really ran)
**Verified at HEAD (reproduced):** the running `nexus.service` PATH is
`~/.local/bin:/usr/local/sbin:…:/snap/bin` — it does **not** contain
`~/.npm-global/bin`, which is where the `claude` CLI actually lives on this
machine (there is no `~/.local/bin/claude`). The frontier scripts
(`cverify`/`cjudge`/`cexec`) `exec env … claude`, so under the exact service PATH
`command -v claude` fails (exit 1) → a service-spawned escalation/critic/judge
`env`-execs to **exit 127 in ~30 ms**. Confirmed the fault reaches four call
sites, not just escalation: `run_critic_cmd` + `run_escalation_cmd` build env via
`_scrubbed_env`, while **`run_judge_cmd` uses `dict(os.environ)` and
`run_plan_critique` builds its own env** (and can invoke `claude` directly) — so
cjudge/premortem were silently exposed too.

**Fix (`app/evals.py`):** new `_augment_path_for_claude(path)` appends the common
user CLI bin dirs (`~/.npm-global/bin`, `~/.local/bin`, `~/bin`,
`~/.claude/local`) to PATH, idempotent and append-only (operator ordering
preserved). Applied in **all four** frontier envs: `_scrubbed_env` (critic +
escalation), `run_judge_cmd`, and `run_plan_critique`. Chose the
`_scrubbed_env`-PATH option from the judge's two alternatives because it is
central, committable through the tracked `app/` tree (live via the
`~/nexus-agent-os` symlink), and fixes the live service without editing the
untracked `~/.local/bin` script copies.

**Regression (`verify_super_result_e2e.py`):** under a synthesized claude-less
service PATH, assert `_scrubbed_env` re-adds the CLI bin dirs and that `claude`
resolves via `shutil.which(path=…)` (guarded to skip if claude isn't installed);
plus a source assert that judge + premortem envs are augmented too (`>= 2`
`_augment_path_for_claude(env.get("PATH"…)` sites).

**Live re-drive (the judge's criterion):** created a scratch task
("capital of France is Berlin") with a REWRITE critic verdict + one open comment,
set `super.escalation=1` and the real `cexec`, and POSTed `/escalate` through the
running service (whose PATH lacks `~/.npm-global/bin`). Result: **real `claude`
ran** (no exit-127 marker), rewrote the deliverable to "…is Paris.", booked a real
envelope to the C3 ledger (`kind=escalation`, `source=envelope`, **$0.65 /
217k tokens**), verdict cleared → re-critique, comment consumed. The
"one escalated rework on a scratch task" criterion now passes.

### Finding 2 — a failed/no-op rework was booked as success
**Verified at HEAD (reproduced by inspection + the live finding-1 result):**
`_escalation_thread` ran the quota check, then **unconditionally** consumed the
open comments, advanced the version clock (`completed_at`), cleared the verdict,
and logged "wrote the final version" — regardless of whether the rework produced
anything. So the exit-127 above (and any timeout / crash / byte-identical
deliverable) was treated as a successful rewrite: the critic's comments were
thrown away and the loop advanced on an unimproved draft.

**Fix (`app/server.py`):** the thread now hashes the deliverable before the rework
and, after the quota gate, only books success when the deliverable was **actually
rewritten** (`post_hash != pre_hash`) **and** `run_escalation_cmd` reported no
failure marker (`[escalation exited|timed out|failed to run|skipped]`). On failure
it reverts the deliverable to the pre-rework snapshot (undoing any partial/timeout
write), drops the redundant `deliverable.v<N>.md` snapshot (new `_drop_snapshot`
helper — also applied on the quota path so retries don't inflate snapshots), KEEPS
the open comments, sets `critic_verdict='error'`, and re-arms the loop-engine
super-state (`loop_engine._locate_super_cfg` → `_set_super_state(…, None)`) so
`_sweep_super_result` re-evaluates the critique through its `'error'` branch and
opens the human checkpoint instead of skipping it as already-handled.

**Regression (`verify_super_result_e2e.py`):** two `/escalate` drives on a
sweep-invisible plain task with no-op stubs — (a) `exit 127`, (b) exit 0 with a
clean claude-JSON envelope that rewrites nothing (the exact "byte-identical
deliverable" the judge observed live). Each asserts: verdict lands on `'error'`
(never a false SHIP), the open comment is KEPT, the deliverable equals its
pre-rework content, and `completed_at` is unchanged — plus a source assert that
the failure branch re-arms the super-state and keeps the comments.

---

## Judge REVISE round 2 (phase7) — blocking finding fixed (2026-07-11)

A second independent judge pass returned REVISE with one blocking finding. It was
re-verified against HEAD (reproduced exactly), then fixed with regression checks
and a live re-drive of the workflow the judge cited.

### Finding 1 — `tasks.model = NULL` (the default) priced at $0, hiding ~99% of GLM spend
**Verified at HEAD (reproduced).** `task_cost_ledger` / `workflow_cost_ledger`
passed `tasks.model` straight into `blended_rate()`, which returns `0.0` for an
unknown model — and `NULL` is the *deliberate* default, not an unknown. Live
counts on the working DB confirmed the judge's numbers:

| `tasks.model` | tasks with tokens | tokens |
|---|---|---|
| `NULL` (default) | 40 | 50,285,578 |
| `glm-4.5-air` | 2 | 132,109 |
| `glm-5.2` | 1 | 250,000 |

So **50.3M of 50.7M tokens (99.2%) priced at $0**, and the judge's observed case
`GET /api/workflows/wf-ae849fa6/ledger` returned 10,386,674 GLM tokens at
`glm_usd: 0.0` / `total_usd: 0.0`. C3's contract goal — "every task/workflow gets
a total $ figure across both currencies, else *beats Opus, cheaper than Fable* is
unverifiable" — was unmet for the dominant case, and Phase 8's cost arm would have
been biased toward "GLM is free".

**Root cause:** pricing read `tasks.model` at face value while *dispatch* resolves
it (`hermes_dispatch.resolve_task_model` = `task.model or default_task_model(uid)`).
The two sides disagreed about what NULL means.

**Fix (`app/database.py`):** new `effective_task_model(model_id, user_id)` — the
pricing-side mirror of `resolve_task_model`: explicit task model → the owner's
`complicated` assignment → `fallback_model("complicated")` (so a wiped registry
still prices instead of pricing free). Both ledgers now resolve through it (their
queries also select `user_id`), and `task_cost_ledger` additionally returns
`glm_model` — the resolved model the estimate actually priced at, so the figure is
auditable rather than opaque. Took the judge's first alternative (resolve at
pricing time) over stamping the model at dispatch, because it also fixes the **40
historical tasks already on disk**; stamping only helps future rows and would have
left Phase 8's baseline biased.

**Extended beyond the judge's line numbers (same defect, same C3 contract):**
`GET /api/deliverables` (`server.py`) built its `cost_usd` column with the same
raw `t.get("model")` and so showed $0 for the same 99% — it now goes through
`db.effective_task_model` too. `evals.py:_price_tokens_blended` was audited and is
**correct as-is** (it is only ever handed an already-resolved frontier model).

**Regression (`verify_super_result_e2e.py`, +4 checks):** a NULL-model task with
`tokens_used=1M` in a scratch workflow asserts (a) the task ledger prices it at
$2.90 with `glm_model == effective_task_model(None, None)` while the row's `model`
column is still genuinely `NULL`, (b) the *workflow* ledger rolls it up at $2.90
(no $0 rollup), (c) an explicit task model still wins over the resolved default
(no regression to the pre-existing explicit-model check at line 243, which was the
only coverage before), and (d) `/api/deliverables` costs the same task > $0. The
task is also given a `result_summary` so it genuinely surfaces in the deliverables
list — otherwise that check would pass vacuously.

**Live re-drive (the judge's exact case):** after the fix,
`workflow_cost_ledger("wf-ae849fa6")` → 5 tasks, 10,386,674 GLM tokens,
**`glm_usd: 30.1214`, `total_usd: 30.1214`** (was `0.0`); a sampled NULL-model task
prices at $1.16 with `glm_model: "glm-5.2"`. The cross-currency total is now real
for the dominant case.

---

## Deviations & follow-ups (recorded per the headless protocol)
1. **C1d (best-of-2 executor drafts) deferred.** It is marked "optional (medium
   coding tasks)" in the SR plan, and the existing content/research fan-out already
   implements best-of-N drafts + synthesis. C1d's coding-specific best-of-2 is a
   narrow extension; deferring it kept the ledger/escalation core solid. Phase 8's
   measured gap will show whether it earns its place. **Recommend building it only
   if Phase 8 shows a coding-quality gap the escalation ladder doesn't close.**
2. **Pre-existing Phase-5 bug (not fixed — out of Appendix-C scope):**
   `autopilot._feature_present("deep_plan")` checks `deep_plan.enabled`, but the
   real setting is `plan.deep_enabled`. So the `plan_recommend` profile derivation
   is permanently staged even though Deep Plan shipped. Recorded here as a
   follow-up; the autopilot gate still (correctly) asserts it is staged. **Fix: one
   key rename in `_feature_present`.**
3. **Repo-task escalation scope.** C1c's escalated rework operates on the task
   WORKSPACE (deliverable rewrite) — the safe, testable path that satisfies the
   judge live-drive. Escalation that edits a repo worktree in place is deliberately
   out of scope (blast-radius); repo tasks more naturally re-dispatch to GLM. The
   dossier still improves the deliverable.md summary on repo tasks.
4. **Legacy Usage-tab price table.** `tools_hub.PRICE_TABLE` (the old per-agent
   Usage aggregator) predates the C3 ledger and carries stale GLM prices
   ($0.5/$0.5). It is a display classifier, not routing, so it doesn't block
   rotation — but it and the C3 ledger are two price tables. **Follow-up: point the
   Usage aggregator at `db.model_prices()` for one source of truth.**
5. **JARVIS framing (rule 12).** Updated the system-control framing with the cost
   ledger + escalated-rework surface; validated by the verify.sh rule-12 check and
   a clean server boot. The heavy JARVIS Playwright gate was not re-run (the change
   is framing-text only; no JARVIS runtime surface changed).

---

## Files touched
`app/database.py` (price table, ledger table/helpers, `escalation_model` purpose +
seed/migration, `FALLBACK_MODELS`, `review_comments.patch`), `app/evals.py`
(envelope unwrap, usage_sink, escalation runner + dossier, patch capture,
`escalation_model_for`, fallback centralization), `app/server.py` (ledger
endpoints + persistence, escalation thread/endpoint, patch plumbing, Eco model
floor, JARVIS framing, C2 fallbacks), `app/loop_engine.py` (escalation hook +
threshold mode + counters), `app/settings_registry.py` (price/output-fraction,
escalation settings, `enum` type), `app/autopilot.py` (rule-3 model floor),
`app/routing.py` (L4 fingerprint), `app/hermes_dispatch.py` (`DEFAULT_MODEL` via
registry), `app/static/app.js` (`escalation_model` route, `enum` rendering),
`app/static/index.html` (cache-bust v90), `setup/bin/cverify` + `setup/bin/cjudge`
(`--output-format json`, patch field) + `~/.local/bin` copies, **new**
`setup/bin/cexec` (+ `~/.local/bin/cexec`). Gates: `verify.sh`,
`verify_super_result_e2e.py`, `verify_autopilot_e2e.py`.

**Phase7 judge-REVISE round (2026-07-11):** `app/evals.py`
(`_augment_path_for_claude` + PATH augmentation in `_scrubbed_env`,
`run_judge_cmd`, `run_plan_critique` — finding 1), `app/server.py`
(`_escalation_thread` success-verification: pre/post content hash + failure-marker
gate, pre-rework revert, super-state re-arm → human checkpoint; new
`_drop_snapshot` helper — finding 2), `app/scripts/verify_super_result_e2e.py`
(+14 regression checks). No Hermes-side (`setup/bin`) change was needed: the fix
is central in `evals`, which every frontier script inherits its env from.

**Phase7 judge-REVISE round 2 (2026-07-11):** `app/database.py` (new
`effective_task_model` — the pricing-side mirror of
`hermes_dispatch.resolve_task_model`; `task_cost_ledger` /`workflow_cost_ledger`
resolve through it and select `user_id`; task ledger gained `glm_model`),
`app/server.py` (`/api/deliverables` `cost_usd` uses the same resolver),
`app/scripts/verify_super_result_e2e.py` (+4 regression checks). Purely a pricing
change — no dispatch/routing behavior moved, and `evals._price_tokens_blended` was
audited as already-correct (only ever handed a resolved frontier model).
