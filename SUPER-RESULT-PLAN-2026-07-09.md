# SUPER RESULT — grounded quality loop: full implementation guide

**Status:** IMPLEMENTED 2026-07-10 — Steps 0–10 + N1–N4 + B-items landed as commits `c16e18f…df67c6f`; see `IMPLEMENTATION-REPORT-SUPER-RESULT.md`. Still OPEN: the Phase-1 fix batch (grounded review + premortem findings), Step 11 measurement, N5–N8, B4, and Appendix C — all executed via `EXECUTION-RUNBOOK-2026-07-10.md`. This document remains the feature's design reference; do not re-implement §6.
**Date:** 2026-07-09
**Author:** Claude Fable 5 (frontier side), from a 3-agent exploration of the live code, a 2023–2026 literature review, and operator decisions (recorded below).
**Supersedes:** `QUALITY-LOOP-IMPROVEMENT-PROPOSAL-2026-07-09.md` (Opus 4.8's read-only findings — used for problem evidence; its P1–P5 recommendations were independently re-derived and substantially extended here).
**For the implementing session:** read this file fully before touching code. Every architectural decision is already made — do not revisit them (§4). Work step by step (§6); each step is independently committable and must leave `bash app/scripts/verify.sh` green. Restart the service only via `systemctl --user restart nexus`. All `file:line` anchors were verified on 2026-07-09 at HEAD `7b24b49`+ — treat them as "near here", re-locate before editing.

---

## 1. Why this exists (the evidence)

The operator ran the same stability-audit prompt through (a) Claude Code Opus 4.8 directly and (b) a Nexus workflow. Nexus reports 1 & 2 were well-formatted but **confidently wrong on the root cause** (concluded "not a code problem" because tests passed and logs were noisy — missed the systemic event-loop blocking that never writes an error line), and the internal judge SHIPPED them (~4.0 self-score). Only after the operator manually rejected report 2 and pasted in the external frontier critique did run 3 produce a report that was not only correct but **beat the frontier side on 2 points** (refuted 2 of its findings with source evidence, added 1 finding it missed).

Two conclusions, both load-bearing for this design:

1. **The loop beats any single frontier pass** — independent critique with real evidence → targeted feedback → re-run produced the best artifact either side made alone. The best output was the UNION of two independent investigations with different blind spots.
2. **Today a human must drive it by hand** — carrying the critique in, writing every rejection comment personally. Nothing produces that union automatically.

**Goal:** make that loop a built-in, mostly-automatic, UNIVERSAL Nexus feature ("Super Result") that works for all task types (analysis, code, content, research), auto-fills the side-by-side per-line comments and the revision brief before each re-run, keeps the human informed and able to edit at every step, and is toggleable because it costs ~5–10× a single pass.

## 2. Why this design wins (research grounding, 2023–2026)

The literature is unambiguous about why reports 1 & 2 shipped and what fixes it:

| # | Finding | Consequence in this design |
|---|---------|---------------------------|
| 1 | Ungrounded LLM-as-judge cannot catch confidently-wrong conclusions — it scores surface plausibility (self-preference, verbosity, position biases). Critics **with tool/environment access** fix this: CRITIC (ICLR'24 — gains vanish when the tool is removed), Agent-as-a-Judge (arXiv 2410.10934), CriticGPT (arXiv 2407.00215). | The critic runs INSIDE a sandbox copy of the workspace/repo with full tools: it re-reads sources, re-runs quoted commands, re-derives numbers. |
| 2 | Intrinsic self-correction doesn't work; **external** feedback does (Huang ICLR'24 2310.01798; Kamoi TACL'24; "Pride & Prejudice" ACL'24 — self-refine amplifies self-bias). Cross-model critics beat self-critique (N-CRITICS). | Critic = frontier Claude (different family than the GLM executor), fresh context every round, refute-by-default framing. |
| 3 | Parallel fan-out with distinct lenses + reconciling verifier beats debate-to-consensus (Anthropic multi-agent research system: +90.2% over single Opus 4 at ~15× tokens; MoA 2406.04692; best-of-N + verifier, Snell ICLR'25; "Talk Isn't Always Cheap" 2509.05396 — naive debate degrades via conformity). | Fan-out per goal family + a reconciler that takes the UNION and adversarially verifies each claim. Never argue-to-agreement. |
| 4 | Feedback must be specific, localized, actionable — a "textual gradient", not a score (Self-Refine ablations: generic feedback drops results ~12pts; TextGrad; DSPy GEPA 2507.19457). | Structured findings {location, claim, evidence, problem, fix} auto-posted as per-line review comments + a synthesized revision brief. |
| 5 | Contradiction detection generates the best verification questions (Chain-of-Verification 2309.11495; SelfCheckGPT 2303.08896 — divergence between independent outputs ≈ hallucination signal). | The critic explicitly diffs vs the previous version + sibling reports; contradictions become "investigate this" comments — exactly the automation the operator asked for. |
| 6 | Binary rubric gates + adversarial framing beat Likert scoring (judge-bias literature 2410.02736, 2406.07791). | New substance gates A1–A4 (§6 Step 8); verdict stays SHIP/REVISE/REWRITE. |
| 7 | Loops don't self-detect completion; hard stops + cost gating are mandatory (Anthropic: multi-agent only when task value justifies ~15×). | Round cap, no-new-findings convergence, budget ceilings, human escalation, per-task/workflow toggle default OFF. |

## 3. Operator decisions (asked & answered 2026-07-09)

1. **Critic evidence access = FULL tool access in a disposable ISOLATED COPY** (temp local git clone for repo tasks / workspace copy otherwise). Isolation is the safety boundary, not tool restrictions.
2. **Default round behavior = fully automatic (closed)** — critique → auto-comments → auto-re-run until SHIP / convergence / round cap. Open "checkpoint each round" mode remains available.
3. **Fan-out scope = ALL Super Result workflows** (shape adapted per goal family), with a per-workflow escape hatch.

## 4. Locked architectural decisions (implementer: do NOT revisit)

1. **New `critic_*` task columns, NOT reuse of `judge_*`.** `judge_ts`/`judge_verdict` freshness drives the existing `judge_revise`/`auto_judge` triggers (`loop_engine.py:316-320`) and `_retry_task` auto-injects `judge_output` as feedback when feedback is empty (`server.py:3710`) — overloading them would double-fire loops and leak raw critic JSON into executor prompts. The judge UI reads `judge_output` as prose; critic output is a JSON artifact.
2. **Sandbox lifecycle owned by `evals.py` (Python), not the bash script.** `sp.run(timeout=…)` kills the child and the `finally:` block removes the sandbox — a bash `trap` can't survive a SIGKILL'd wrapper. `cverify` only CONSUMES a prepared sandbox (which also makes it hand-testable). Backstop: 24 h age sweep of `app/workspaces/_critic/` on each sandbox build.
3. **Isolation mechanics — three concrete layers.** (a) Repo tasks: `git clone --local <repo_path> <sandbox>/repo` then `git remote remove origin` — push has nowhere to go (do NOT use `git worktree`: worktrees share the object store and remotes with the live repo). Workspace tasks: `shutil.copytree` excluding `_critic*`, `node_modules`, `.venv*`, `.venv-preview`, `.next`, `dist`, `build`, `__pycache__`; `_history/`, `deliverable.v*.md`, and `attachments/` INCLUDED — they are evidence. (b) `--disallowedTools "Bash(git push:*)" "Bash(git remote:*)" "Bash(gh:*)" "Bash(sudo:*)"` — deny rules beat allow rules; flags `-p`, `--model`, `--permission-mode acceptEdits`, `--allowedTools`, `--disallowedTools` all verified present in this machine's `claude --help`. (c) Scrubbed subprocess env: drop every var matching `(?i)(api_key|apikey|token|secret|passw|credential)` except `JUDGE_ANTHROPIC_API_KEY`. Full tools otherwise (`--permission-mode acceptEdits` + broad `--allowedTools` — NOT `bypassPermissions`, so the deny list stays enforceable). **Honesty note (put in the cverify header):** this is an accident boundary, not an adversary boundary — HOME stays visible for claude auth.
4. **Auto-comments inserted via an internal function (direct DB), not the HTTP endpoint** — the endpoint enforces user-comment semantics; the critic thread already runs server-side. Each fresh critique **supersedes its own stale comments**: `DELETE FROM review_comments WHERE task_id=? AND status='open' AND source='critic'` first. User comments are never touched.
5. **Precedence: `super_result` REPLACES `judge_revise` + `auto_judge`** in `design_loop` when the flag is set (the grounded critic subsumes the document-only judge). Belt-and-braces: `_sweep_task_loops` skips items whose config carries a `super_result` trigger.
6. **Fan-out is planning-time** (shapes the wizard DAG), per goal family: analysis → N lens-investigators + reconciler; code → ONE implementation + 2 parallel adversarial lens-reviewers (NEVER parallel implementations); content/research → 2 independent drafts + adversarial synthesis. Escape hatch: wizard body `fanout:false` (default from `super.fanout_default`).
7. **Critic model = the existing `frontier_judge` purpose** (`evals.judge_model_for` `evals.py:139`, seeded `claude-opus-4-8` route=cli) — a different model family from the GLM executor by construction, fresh context every round. Same `JUDGE_MODEL`/`JUDGE_ANTHROPIC_API_KEY` env contract as cjudge.
8. **`_retry_task` feedback cap raised 8000 → 16000.** 25 findings × ~500-char comment bodies ≈ 12.5k+ chars before formatting — the 8000 slice would silently truncate. `retry_feedback` is TEXT; GLM context absorbs 16k. Findings are severity-ordered at insert so any residual truncation drops the least severe. (This corrects an arithmetic error in the design pass — keep the 500-char body clamp AND the 16000 cap.)

## 5. Architecture overview

```
                    ┌─ Super Result OFF → existing pipeline (unchanged)
 Wizard/goal ───────┤
                    └─ ON → fan-out task graph (per goal family, §6 Step 7)
                                 │ (existing DAG: depends_on join, all-predecessor input injection)
                                 ▼
 per deliverable-bearing task:  EXECUTE (GLM, existing dispatch)
                                 │ fresh deliverable
                                 ▼
                    ┌──────── GROUNDED CRITIC round (new) ─────────┐
                    │ frontier model, fresh context, FULL tools in  │
                    │ disposable sandbox copy of workspace(+repo)   │
                    │ • claim ledger → refute-by-default verify     │
                    │   against primary evidence                    │
                    │ • contradictions vs deliverable.v{N-1} +      │
                    │   sibling investigator reports + internal     │
                    │ • completeness pass vs brief + rubrics        │
                    │ • emits sentinel-fenced STRUCTURED JSON       │
                    └──────┬───────────────────────────────────────┘
                           ▼
              auto-insert review_comments (source='critic', line-anchored, severity-ordered)
              + revision_brief → existing _retry_task drains them verbatim into the re-run
                           │
          closed (default): auto-retry ── next round      open: approval checkpoint,
          until SHIP | no-new-findings | round cap        user edits comments, then Retry
                           ▼
              final human approval gate (existing high-stakes flow)
              with full audit trail of every round's comments
```

**Key reuse (all verified in code):**
- `_retry_task` (`server.py:3697`) already merges open `review_comments` + feedback into `tasks.retry_feedback`, which `build_framing` (`hermes_dispatch.py:828-832`) injects verbatim into the re-run prompt. Retry also snapshots `_history/vN` + renames `deliverable.md → deliverable.vN.md` — version history is free.
- The DAG already supports fan-out/join: `tasks.depends_on` JSON list, fail-closed `deps_satisfied` (`hermes_dispatch.py:467`), all done predecessors' `deliverable.md` injected as INPUT (`build_framing:820-827`) — a reconciler depending on N investigators automatically receives all N reports.
- The loop engine (`loop_engine.py`) already sweeps every 20 s, round-caps per trigger, retries via the internal HTTP API (`_api` :214, INTERNAL_TOKEN), and logs to the activity feed. The loop modal UI renders trigger cards generically from `cfg.triggers` (`app.js:3243`) — a new trigger appears with zero UI work.
- The judge thread pattern (`server.py:3590-3642`) is the template for the critic thread; `run_judge_cmd` (`evals.py:152-212`) is the template for the critic runner.

---

## 6. Implementation steps

### Step 0 — Preconditions
- Commit the in-flight B7-era modifications (`app/server.py`, `app/secrets_store.py`, `app/tools_hub.py` were dirty on 2026-07-09) BEFORE starting; do not interleave.
- B6/F033 (loop verdict parsing) already landed (`d754e67`) — the old proposal's sequencing precondition is satisfied. B8–B10 touch other areas (JARVIS frontend, camera, dictation); only trivial merge-order coordination in `server.py`/`app.js`.

### Step 1 — Migrations + settings seed (`app/database.py`)
1. Extend `task_migrations` (list at `database.py:229-258`):
   ```python
   ("super_result", "INTEGER DEFAULT 0"),
   ("deliverable_type", "TEXT"),            # analysis|code_change|content|research|NULL
   ("critic_verdict", "TEXT"),              # running|SHIP|REVISE|REWRITE|error
   ("critic_output", "TEXT"),               # raw cverify stdout tail (≤30000)
   ("critic_json", "TEXT"),                 # validated parsed findings JSON (≤60000)
   ("critic_ts", "REAL"),
   ("critic_round", "INTEGER DEFAULT 0"),
   ("critic_keys", "TEXT"),                 # {"round":N,"keys":[...],"prev":[...]} convergence state
   ```
2. Workflow migration (after `replan` at `database.py:313`): `workflows.super_result INTEGER DEFAULT 0`.
3. `review_comments.source` (after the CREATE at `database.py:285-298`):
   ```python
   rc_cols = {r[1] for r in conn.execute("PRAGMA table_info(review_comments)").fetchall()}
   if "source" not in rc_cols:
       conn.execute("ALTER TABLE review_comments ADD COLUMN source TEXT NOT NULL DEFAULT 'user'")
   ```
4. Seed in `dispatch_defaults` (`database.py:499-506`): `("super.critic_cmd", "cverify {file} {domain} {sandbox}")` — same stub-hook contract as `judge.cmd`.

**Verify:** `bash app/scripts/verify.sh`; after restart, `sqlite3` read-only `PRAGMA table_info(tasks)` shows the columns.

### Step 2 — Settings section (`app/settings_registry.py`)
Append to `SECTIONS` after the `judge` section (`:62-72`; `PREFIXES` derives automatically):
```python
{
  "id": "super", "title": "Super Result (grounded critic loop)",
  "desc": "A frontier critic with evidence access re-verifies each deliverable in a disposable "
          "sandbox, files line-anchored findings as review comments, and loops the work until "
          "SHIP, convergence, or the round cap. Model = the 'frontier judge' purpose.",
  "items": [
    {"key": "super.critic_cmd", "label": "Critic command template", "type": "command",
     "default": "cverify {file} {domain} {sandbox}",
     "help": "Tokens: {file} {domain} {sandbox} and optional {model}. Gates stub this — restore after testing."},
    {"key": "super.max_rounds",  "label": "Max automatic rounds",  "type": "int", "default": "3", "min": 1, "max": 6},
    {"key": "super.timeout_s",   "label": "Critic timeout (s)",    "type": "int", "default": "1500", "min": 120, "max": 3600},
    {"key": "super.max_findings","label": "Max findings per round","type": "int", "default": "25", "min": 3, "max": 40},
    {"key": "super.fanout_default","label": "Wizard fan-out by default","type": "bool", "default": "1"},
    {"key": "super.fanout_n",    "label": "Fan-out width",         "type": "int", "default": "3", "min": 2, "max": 4},
    {"key": "super.keep_sandbox","label": "Keep critic sandboxes (debug)","type": "bool", "default": "0"},
  ],
},
```
**Verify:** `GET /api/settings/schema` shows the section; `sreg.conf("super.max_rounds") == "3"`.

### Step 3 — The `cverify` script
**Files:** `setup/bin/cverify` (vendored source of truth) + installed `~/.local/bin/cverify` (`install.sh:65-74` copies `setup/bin/.` wholesale — add `cverify` to the chmod line). Base it on `setup/bin/cjudge`; reuse its `MODEL_ARGS`/`KEY_ENV`/`env -u` scrub block (`cjudge:39-57`) verbatim.

**argv contract:** `cverify <file> <domain|-> <sandbox>`
- `<file>` — absolute path of the deliverable copy INSIDE the sandbox (`<sandbox>/workspace/deliverable.md`).
- `<domain>` — domain slug or `-` (no domain rubric; the critic still runs — unlike cjudge, a rubric is not required).
- `<sandbox>` — sandbox root; script `cd`s there; must contain `_critic_context/context.json` (else exit 1 + usage).
- Env in: `JUDGE_MODEL`, `JUDGE_ANTHROPIC_API_KEY`, `SUPER_MAX_FINDINGS` (default 25).
- No timeout inside the script — `evals.py` owns it.

**Invocation (exact):**
```bash
cd "$SANDBOX"
exec env -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL \
  <same -u list as cjudge:49-55> \
  "${KEY_ENV[@]}" \
  claude "${MODEL_ARGS[@]}" \
    --permission-mode acceptEdits \
    --allowedTools "Bash" "Read" "Edit" "Write" "Grep" "Glob" "WebSearch" "WebFetch" \
    --disallowedTools "Bash(git push:*)" "Bash(git remote:*)" "Bash(gh:*)" "Bash(sudo:*)" \
    -p "$PROMPT"
```

**Prompt (single heredoc string, cjudge-style), outline:**
1. Role: *"You are the GROUNDED CRITIC — a second, stronger model that independently re-verifies work produced by a weaker one. You are inside a DISPOSABLE, ISOLATED sandbox copy of the evidence ($SANDBOX). You may read, edit, run tests, install dependencies — nothing here is the real workspace. Never operate on paths outside $SANDBOX. Never push, never use gh."*
2. *"FIRST read `_critic_context/context.json` — it names the task brief, round number, deliverable type, the previous version, sibling reports, rubrics, and existing open review comments (do not duplicate those)."*
3. Method, in order:
   (a) **CLAIM LEDGER** — extract every load-bearing claim in $FILE (facts, numbers, file:line references, "tests pass", causal statements);
   (b) **VERIFY, refute-by-default** — a claim stays UNVERIFIED until confirmed against primary evidence: read the actual files, re-run the exact commands whose output the deliverable quotes, re-derive numbers. The deliverable's own assertions and self-scores are never evidence. A proxy inference ("tests pass" ⇒ "code correct") is NOT verification;
   (c) **CONTRADICTIONS** — against the previous version (path in context), each sibling report, and internally;
   (d) **COMPLETENESS** — what is missing versus the brief and every rubric dimension;
   (e) score the must-pass gates of BOTH rubrics (domain + type) briefly.
4. Output contract: narration allowed, but the reply MUST END with exactly one JSON object between sentinel lines, nothing after the closing sentinel:
   ```
   NEXUS_CRITIC_JSON_BEGIN
   { ... }
   NEXUS_CRITIC_JSON_END
   ```
5. **The canonical schema** (embed with limits — this is the contract for the whole feature):
   ```json
   {
     "verdict": "SHIP|REVISE|REWRITE",
     "confidence": 0.0,
     "summary": "≤600 chars",
     "findings": [{
        "severity": "critical|high|medium|low",
        "file_path": "workspace-relative, e.g. workspace/deliverable.md or repo/src/x.py",
        "side": "new",
        "line_no": 12,
        "line_text": "verbatim quote of that exact line (≤200)",
        "claim": "what the deliverable asserts (≤300)",
        "evidence": "what you actually found and WHERE — file:line or command + real output (≤400)",
        "problem": "why the claim fails (≤300)",
        "suggested_fix": "concrete edit (≤300)"
     }],
     "contradictions": [{"with": "previous_version|sibling:<task-id>|internal",
                         "a": "…", "b": "…", "resolution_hint": "…"}],
     "missing": [{"what": "…", "why_it_matters": "…"}],
     "revision_brief": "≤2500 chars — the exact instruction the reworking agent needs"
   }
   ```
6. Rules: at most `$SUPER_MAX_FINDINGS` findings, most severe first; every finding must cite verifiable evidence; `line_no`/`line_text` must reference a real existing line or be null; **SHIP only when zero critical/high findings AND all rubric gates pass**.

**Verify standalone:** hand-build a throwaway sandbox (copied workspace + minimal `_critic_context/context.json`), run `cverify <file> - <sandbox>`, confirm sentinel JSON returns and `git -C <real repo> status` is untouched.

### Step 4 — Critic engine (`app/evals.py`)
New "Grounded critic" section after the judge section (`:137-252`). Module constants: `CRITIC_SANDBOXES = Path(__file__).parent / "workspaces" / "_critic"`, `SEVERITY_ORDER = {"critical":0,"high":1,"medium":2,"low":3}`, sentinels.

- **`detect_deliverable_type(task) -> str`** — explicit `task["deliverable_type"]` wins; else `repo_path` set, or specialist in `{code-implementer, tech-lead-orchestrator, code-reviewer, acceptance-verifier}`, or domain `software-engineering` → `code_change`; else specialist in `{web-researcher, market-researcher}` or domain `research-learning` → `research`; else title+description match `r"\b(audit|analy[sz]|investigat|reconcil|diagnos|assess|verif)"i` → `analysis`; else `content`.
- **`type_rubric_path(dtype) -> str|None`** — `analysis`/`research` → `<knowledge root>/rubrics/INVESTIGATION.md` (knowledge root = `db.get_setting("onboarding.root","") or ~/knowledge`); others None (extensible dict).
- **`_scrubbed_env() -> dict`** — per §4.3(c).
- **`build_critic_sandbox(task, round_no) -> (sandbox_root, deliverable_rel_path)`**:
  1. mkdir parents; sweep subdirs older than 24 h (crash leftovers).
  2. `sandbox = CRITIC_SANDBOXES / f"{task['id']}-r{round_no}-{uuid4().hex[:6]}"`.
  3. Workspace copytree per §4.3(a).
  4. Repo tasks: `git clone --local` → checkout `nexus/<slug>` (slug via `hermes_dispatch._repo_slug`, lazy import; guard with `git rev-parse --verify`) → `git remote remove origin`; clone failure → proceed without `repo/`, record `"repo_root": null, "repo_note": "<err>"`.
  5. `_critic_context/`: copies of domain `RUBRIC.md` (if any), type rubric, `BUSINESS-CONTEXT.md`; `siblings/<dep-task-id>.md` = each DONE predecessor's `deliverable.md` (via `hermes_dispatch.task_dependencies(task)` — this is how sibling investigator reports reach the reconciler's critic); `context.json` (schema below).
  6. `previous_version` = highest `workspace/deliverable.v{N}.md` in the copy, or null.

  **`context.json` schema (exact):**
  ```json
  {
    "task_id": "task-…", "title": "…", "round": 2,
    "brief": "<task.description, ≤4000>",
    "retry_feedback_last": "<task.retry_feedback or ''>",
    "deliverable": "workspace/deliverable.md",
    "deliverable_type": "analysis",
    "workspace_root": "workspace/",
    "repo_root": "repo/", "repo_branch": "nexus/<slug>", "repo_base": "main",
    "previous_version": "workspace/deliverable.v3.md",
    "sibling_reports": [{"task_id": "…", "title": "…", "path": "_critic_context/siblings/task-….md"}],
    "rubrics": {"domain": "_critic_context/RUBRIC.md", "type": "_critic_context/INVESTIGATION.md"},
    "business_context": "_critic_context/BUSINESS-CONTEXT.md",
    "max_findings": 25,
    "open_comments": [{"file_path": "…", "line_no": 3, "body": "…"}]
  }
  ```
  (`open_comments` = current open review_comments, compact, so the critic doesn't duplicate the human's notes.)
- **`run_critic_cmd(task, domain, model=None, api_key=None, round_no=1) -> str`** — mirrors `run_judge_cmd` (`:152-212`): build sandbox; shlex-split `super.critic_cmd`; per-token replace `{file}` (absolute path of the deliverable inside the sandbox), `{domain}` (`domain or "-"`), `{sandbox}`, `{model}`; `~/.local/bin` PATH fallback (as `:187-190`); env = `_scrubbed_env()` + `JUDGE_MODEL`/`JUDGE_ANTHROPIC_API_KEY` + `SUPER_MAX_FINDINGS`; `sp.run(tokens, cwd=str(sandbox), timeout=int(super.timeout_s), capture_output=True, text=True)`; append `[critic exited N]`/timeout/exception markers like the judge; `finally:` rmtree unless `super.keep_sandbox == "1"`.
- **`parse_critic_json(text) -> dict`** (raises ValueError on unusable output): extract between sentinels (last occurrence); fallback = last balanced `{…}` block; `json.loads`. Validate/coerce: verdict required + enum; confidence float clamped 0..1 (default 0.5); findings list — clamp every string to schema limits, unknown severity → `medium`, sort by `SEVERITY_ORDER`, truncate to `super.max_findings`; `file_path` strip leading `/`, REJECT any containing `..` (drop the anchor, keep the finding on `deliverable.md`); normalize prefixes (strip `workspace/`; strip `repo/` for repo tasks — review paths are repo-relative); `line_no` int or None; contradictions/missing ≤10 each; `revision_brief` ≤2500. Compute stable finding keys `sha1(f"{file_path}|{severity}|{(claim or problem)[:120].lower()}")[:12]` → `parsed["_keys"]`.

**Verify:** stub `super.critic_cmd` with a scratch script printing canned sentinel JSON; drive `run_critic_cmd` from a `.venv/bin/python` REPL against a real done task; confirm sandbox created+destroyed and the parse. Restore the setting.

### Step 5 — Server wiring (`app/server.py`)
**5a. `_critic_thread(task_id)`** — beside `_judge_thread` (`:3592`): load task; `round = (critic_round or 0) + 1`; `(model, key) = evals.judge_model_for(owner)`; `out = evals.run_critic_cmd(...)`; `parsed = evals.parse_critic_json(out)` — on ValueError: store `critic_verdict='error'` + output tail + ts + round, log error activity, return (the sweep escalates on `error`). Convergence bookkeeping: old `critic_keys` → `prev = old.get("keys") or []`; new `critic_keys = json.dumps({"round": round, "keys": parsed["_keys"], "prev": prev})`. Then `_insert_critic_comments(task, parsed)`; persist `critic_verdict/critic_output[-30000:]/critic_json[:60000]/critic_ts/critic_round`; `db.log_activity` + `hermes_dispatch.notify_desktop("Nexus: Super Result", f"{verdict} — {len(findings)} finding(s) on '{title}'")`.

**5b. `_insert_critic_comments(task, parsed)`** (internal, direct DB): supersede-then-insert per §4.4. Anchor validation per finding (severity order): resolve `os.path.join(workspace_path, file_path)` with realpath-prefix check (repo findings keep the repo-relative anchor as-is); if `line_no` given, read the file and require `line_text.strip()` to match that line ±2 lines (accept nearest, rewrite `line_no`; take `line_text` from the REAL file), else null `line_no`, keep the file anchor. Insert: `id=f"rc-{uuid4().hex[:12]}"`, `user_id=task["user_id"]`, `side='new'`, `source='critic'`, `body = f"[{SEV.upper()}] {problem} — claim: {claim}. Evidence: {evidence}. Fix: {suggested_fix}"[:500]`, `status='open'`; stop at `_COMMENT_MAX_OPEN` (200). Also add `source` to the existing user-comment INSERT (`:6035-6041`), hardcoded `'user'`.

**5c. Endpoints** — beside the judge endpoints (`:3611-3644`): `POST /api/tasks/{id}/critic` (`_owned_task` gate; 400 if no `workspace_path/deliverable.md`; 409 if `critic_verdict=='running'`; set `critic_verdict='running'`, `critic_output=NULL`, `critic_ts=now`; spawn daemon thread; return `{ok, status:"running", round}`) and `GET /api/tasks/{id}/critic` (owner-scoped: verdict/output/parsed json/ts/round + `running` bool + open critic-comment count). Blocking work stays in the thread (B7's no-block-in-async rule).

**5d. `_retry_task` — three surgical changes only** (`:3699-3770`): (1) note tags in the comment loop (`:3721-3725`): `tag = "CRITIC" if c.get("source")=="critic" else "REVIEWER"` → `f"- [{tag}] {loc} [{side}]… → {c['body']}"`; (2) approval expiry (`:3765`): `action_type IN ('deliverable','super_result')`; (3) fb cap `fb[:8000]` → `fb[:16000]` (§4.8). Everything else (snapshot, versioning, budget slice, comment consumption) already does exactly what Super Result needs.

**5e. Flag plumbing:**
- `TaskCreate` (`:230`) / `TaskUpdate` (`:267`): `super_result: bool = False` / `Optional[bool]`, `deliverable_type: Optional[str]` validated against `{analysis, code_change, content, research}` or None → 400.
- `create_task` (`:534`) / `update_task` (`:564`): both columns; on `super_result` flip call `_sync_super_result_loop("task", row)`.
- `create_workflow` (`:4746`) / `update_workflow` (`:4794`): accept + cascade mirroring `high_stakes` (`:4823-4833`): set workflow column, `UPDATE tasks SET super_result=? WHERE workflow_id=?`, log, `_sync_super_result_loop("workflow", row)`.
- **`_sync_super_result_loop(kind, row)`**: parse existing `loop_config`; flag ON + no `super_result` trigger → regenerate via `loop_engine.design_loop(kind, meta_with_flag, preference=cfg.get("preference","quality"), mode=cfg.get("mode","closed"))`, preserving `used` counts of surviving triggers by id; flag OFF → strip the trigger.
- `loop_design` endpoint (`:4451`): add `"super_result": bool(...)` to task meta (`:4465`) and workflow meta (`:4475`).
- `decide_approval` (`:2819`): new branch `action_type == "super_result"`: approved → `loop_engine.mark_super_done(task_id)`; rejected → `await run_in_threadpool(_retry_task, task_id, feedback or None)` + `loop_engine.bump_super_round(task_id)`. Broadcast `task_updated` like the deliverable branch.
- `replan_apply` (`:5044-5052`): pass `super_result` + `deliverable_type` into `create_task`.

**Verify:** stub critic (canned JSON, 2 findings, REVISE); via HTTPS: create task + fake `workspaces/<id>/deliverable.md`; `POST /critic`; poll `GET /critic`; assert `review_comments` rows `source='critic'` with validated anchors; `POST /retry` → comments consumed, `retry_feedback` contains `[CRITIC]` notes. Restore setting. Use the app:verify skill flow.

### Step 6 — Loop engine (`app/loop_engine.py`)
**6a. `design_loop` (`:51-171`):** when `meta.get("super_result")`, emit first:
```python
{"id": "super_result", "enabled": True,
 "label": "Super Result — grounded critic → auto-comments → rework",
 "action": "critic_comment_retry",
 "max_rounds": int(db.get_setting("super.max_rounds", "3") or 3), "used": 0,
 "explain": "A sandboxed frontier critic independently verifies every claim against the real "
            "files, files line comments, and re-runs the work automatically. Stops on SHIP, "
            "on convergence (no new findings), or escalates to you at the round cap."}
```
Guard `judge_revise` (`:105`) and `auto_judge` (`:126`) with `and not meta.get("super_result")`; add a reasoning line explaining the replacement.

**6b. `_sweep_super_result(actions_left) -> int`** — called from `loop_sweep()` (`:413-418`) before `_sweep_workflow_loops`. Candidates: own-or-inherited cfg pattern of `_sweep_task_loops` (`:299-309`) but do NOT filter mode (open mode acts here too). Per candidate with an enabled `super_result` trigger:
1. `critiqued_this_version = critic_ts and critic_ts >= (completed_at or updated_at or 0)` (mirror of `:316-317`).
2. Not critiqued and `critic_verdict != 'running'` → `_api("POST", f"/api/tasks/{id}/critic", {}, user_id=…)`; decrement actions; continue.
3. `running` → continue.
4. Fresh verdict:
   - `SHIP` → mark terminal state once (idempotence via a `state`/`state_tasks` map on the trigger, mirroring `used_tasks`); info log "Super Result converged: SHIP after round N".
   - `error` → escalate once.
   - `REVISE`/`REWRITE`: parse `critic_keys`; `converged = round > 1 and set(keys) <= set(prev)` → escalate once ("no new findings — human judgment needed"); `used >= max_rounds` → escalate once ("round cap reached"); else **open mode** → checkpoint approval once per version (skip if a pending `super_result` approval exists): direct `INSERT INTO approvals` (pattern `hermes_dispatch.py:1001-1007`) with `action_type='super_result'`, description `f"Super Result round {round}: {K} findings — review/edit the auto-comments, then Retry or Approve"`, payload `{task_id, round, findings, verdict, reason?}`, `risk_level='high'`, owner user_id; `notify_desktop`. **Closed mode** → `_api("POST", f"/api/tasks/{id}/retry", {"feedback": f"SUPER RESULT round {used+1}/{max}: grounded critic verdict {verdict}.\n" + revision_brief[:2500]}, user_id=…)`; on success bump rounds + `_save_cfg` + warn log; decrement actions. (`_retry_task` drains the critic comments automatically; budgets/quota enforced downstream; `MAX_ACTIONS_PER_SWEEP=3` is the storm brake.)
   - **Escalate** = the open-mode approval insert with a `reason` in the payload + terminal-state mark for idempotence.
5. Belt-and-braces in `_sweep_task_loops` (`:310`): `if _trigger(cfg, "super_result"): continue`.

**6c. Exported helpers for server.py:** `bump_super_round(task_id)` / `mark_super_done(task_id)` — load effective cfg (own else inherited), locate the trigger, bump/mark, `_save_cfg`.

**Verify:** stubbed critic + `dispatch.enabled=1`: enable `super_result` on a done task → within ~40 s critic runs → comments appear → auto-retry with the brief (closed); flip to open → approval row instead; stub SHIP → quiet with one log line; stub identical keys twice → escalation. Watch `journalctl --user -u nexus -n 100`.

### Step 7 — Wizard fan-out (`app/server.py`)
**7a. `task_wizard` (`:4520`):** accept `body["super_result"]` (bool, default False) and `body["fanout"]` (None → `sreg.conf("super.fanout_default")=="1"`); pass both + `int(sreg.conf("super.fanout_n"))` into `_task_wizard_framing`; call `_repair_workflow` with `max_raw=7` when fan-out requested. After repair, deterministic post-step (not the LLM's job): `out["workflow"]["super_result"] = True` and `super_result: true` on every sink task; single-task plans set it on the task.

**7b. `_task_wizard_framing` (`:4104-4226`):** new params `super_result, fanout, fanout_n`. Add to TASK FIELDS: `deliverable_type: one of analysis|code_change|content|research` and `super_result: true only where the plan says so below`. When `super_result and fanout`, append a **SUPER RESULT FAN-OUT** block after the pipeline templates (`:4186`):
- *"This project runs under Super Result. Where the goal is parallelizable, fan the work out so independent perspectives cross-check each other, then reconcile:"*
- **ANALYSIS / AUDIT / INVESTIGATION goals:** `{fanout_n}` investigator tasks, parallel (`depends_on []`), each description carrying an explicit DISTINCT LENS paragraph — lens 1: verify-the-facts against primary evidence; lens 2: gaps, risks, what's missing; lens 3: alternative explanations / steelman the opposite conclusion — plus ONE reconciler depending on ALL investigators: union of findings, adversarially verify each against primary evidence, resolve every contradiction explicitly (name which investigator was wrong and why), final report. Tags: investigators `["investigation","fanout"]`, reconciler `["reconciler"]`; reconciler `super_result: true`, `deliverable_type: "analysis"`.
- **CODING goals:** NEVER parallel implementations. Keep the 5-stage pipeline, but replace the single review with TWO parallel independent code-review tasks with distinct lenses (A: correctness/security/failure-modes — actively try to break it; B: spec-coverage/regression/test-integrity — every requirement, no weakened tests), both depending on the implementation, tags `["review","quality-gate","fanout"]`; the fix task depends on the implementation and BOTH reviews; the verifier stays the final sink with `super_result: true`.
- **CONTENT / RESEARCH goals:** 2 independent draft tasks with distinct angle/lens prompts, parallel, tags `["draft","fanout"]` + ONE synthesis reconciler depending on both: pick the strongest elements, adversarially fact-check every claim it keeps, produce the final; `super_result: true`, tag `["reconciler"]`.
- *"≤7 tasks total. When the goal is NOT parallelizable (trivial one-liner, single mechanical artifact), fall back to the normal templates — Super Result still critiques the single result."*
When `super_result and not fanout`: one line — normal templates, final task carries `super_result`.

**7c. `_clamp_wizard_task` (`:4229`):** pass through `super_result` (bool) and `deliverable_type` (enum-whitelisted, else None).

**7d. `_repair_workflow` (`:4325-4448`):**
- **Multi-reviewer awareness:** generalize `rev_i` → `rev_is = [...]` (all code-reviewer tasks). Empty → existing single-gate insertion unchanged. Else loop the dep-repair (`:4412-4418`) over each reviewer; the fix task's deps ⊇ impl + all reviewers; verifier deps (`:4428`) = `sinks | set(rev_is) | {spec_i}`.
- **Reconciler enforcement:** after the coding block: `fanout_is` = tasks tagged `fanout`/`investigation`/`draft` with ≥2 members and no coding pipeline present; if no task tagged `reconciler` (or depending on all of `fanout_is`) → append `_reconciler_gate_task(wf_name)` (new template beside `_review_gate_task` `:4240`: title `f"Reconcile & verify findings: {goal}"`, description = union/adversarial-verify/resolve-contradictions contract, `specialist: None`, `super_result: True`, `deliverable_type: "analysis"`, `budget_tokens: 3000000`, `tags: ["reconciler","quality-gate"]`, `depends_on_idx = fanout_is`) + repair note. If a reconciler exists but misses an investigator dep → complete its deps.
- All inside the existing try/except — the sequential-chain fallback (`:4444-4447`) remains the safety net.

**Verify:** `POST /api/tasks/wizard/revalidate` with a hand-built fan-out plan (3 tagged investigators, no reconciler) → repaired plan contains the appended reconciler as unique sink; a coding plan with 2 reviewers → fix waits for both, verifier gates on both.

### Step 8 — INVESTIGATION rubric (knowledge layer)
**Files:** `~/knowledge/rubrics/INVESTIGATION.md` (live) + vendored `setup/knowledge/rubrics/INVESTIGATION.md` (verify install.sh copies `setup/knowledge` wholesale; add the dir if needed). Same shape as domain RUBRICs — must-pass gates + scored 0–4 dimensions:
- **A1 Verified-not-inferred:** every load-bearing claim traced to primary evidence with an exact location (file:line, command+output, source URL); inference explicitly labeled as inference. Gate: any unlabeled inference presented as fact = FAIL. *(Reports 1 & 2 fail A1 outright — this gate alone would have caught them.)*
- **A2 Alternatives-ruled-out:** competing explanations enumerated and each excluded with evidence, not plausibility.
- **A3 Coverage:** the investigated surface enumerated; sampling strategy stated; an honest "What I did NOT check" section exists.
- **A4 Re-verify-borrowed-claims:** claims imported from sibling reports, previous versions, or cited sources independently re-checked before reuse. *(Report 3's own "Learn" lesson, institutionalized.)*
- Scored dimensions: evidence density, falsifiability of statements, contradiction handling, actionability of conclusions.

### Step 9 — Frontend (`app/static/app.js` + `index.html`; bump `?v=N` on `app.js`)
1. **Critic comment badging:** `rcThreadHTML` (`app.js:2769`) renders `source==='critic'` comments with a distinct chip (🤖 AI critic, accent border) — still editable/deletable via existing PATCH/DELETE before the re-run consumes them. Comment rows arrive via existing `GET /api/tasks/{id}/review/comments` (rows now carry `source`).
2. **Revision-brief panel:** review modal (`renderReviewModal` `app.js:2726`) gains a collapsible "🤖 Critic — round N (verdict)" panel: summary, contradictions, missing list, and the revision brief that will ride the next retry; data from `GET /api/tasks/{id}/critic`.
3. **Kanban chip:** `superChip(t)` beside `dispatchChip` (`app.js:1173` pattern): `✨SR r2/3 · critiquing | 5 findings | converged | escalated`; fields from the task row (`critic_verdict/critic_round`) + loop config.
4. **Task detail:** critic section following the `judgeSectionHTML` pattern (`app.js:3385`): running spinner, verdict chip, findings count, collapsible parsed findings, "Run critic" button → `POST /api/tasks/{id}/critic`.
5. **Loop modal:** the `super_result` trigger renders automatically in the generic trigger cards (`app.js:3243`, verified). No work beyond the trigger existing.
6. **Toasts/feed:** loop engine already logs `CLOSED LOOP`-style activity lines; add toast on `task_updated` WS when `critic_verdict` transitions ("Super Result round 2: 5 findings posted, re-running").
7. **Toggles:** wizard project modal beside `#wf-highstakes` (`app.js:8757`): "✨ Super Result" checkbox with cost hint ("~5–10× tokens: independent verification rounds + fan-out") revealing sub-options (fan-out on/off); sent in `POST /api/workflows` / wizard body. Task-create beside `#m-task-loop` (`app.js:4408`); task-detail beside `#td-highstakes` (`app.js:1318`, submit `:3522`).
8. **Approval cards** (`viewAgentic` `app.js:5662` + JARVIS deck): `super_result` approvals show round/findings/verdict summary from the payload; Approve/Reject reuse `decideApproval` (reject prompt text = feedback → `_retry_task`).

### Step 10 — Gates + docs
1. `install.sh`: add `cverify` to the chmod line (`:70-74`).
2. `app/scripts/verify.sh`: new "SUPER RESULT" section — `chk` existence lines for: the new columns in `database.py`; `run_critic_cmd`/`parse_critic_json`/`build_critic_sandbox`/`detect_deliverable_type` in `evals.py`; `/api/tasks/{task_id}/critic`, `_critic_thread`, `_insert_critic_comments`, `'deliverable','super_result'` in `server.py`; `super_result` trigger + `_sweep_super_result` in `loop_engine.py`; `super.critic_cmd` in `settings_registry.py`; `[ -f ../setup/bin/cverify ]`; the `source` column migration.
3. New runtime gate `app/scripts/verify_super_result_e2e.py` (~20 checks, self-cleaning, stubbed `super.critic_cmd` restored in finally): critic run → comments (source/anchors) → retry drain (`[CRITIC]` in retry_feedback) → closed auto-round → convergence escalation → round-cap escalation → open-mode approval → approve/reject semantics → workflow cascade → revalidate reconciler repair.
4. `app/CLAUDE.md`: feature block + the new gate in the canonical commands list.

### Step 11 — Measure it (the honesty step)
1. Rerun the original stability-audit brief as a Super Result workflow; compare against `STABILITY-AUDIT-2026-07-08.md` and the three recon briefs.
2. Run 2–3 eval-corpus cases (`~/knowledge/domains/<d>/evals/`) SR-on vs SR-off — NOT via the eval runner (it can't drive the loop): seed each brief as a real workflow/task pair, let the pipeline run, then judge the final deliverables; compare judge scores AND total tokens.
3. Control per the literature: also compare against best-of-N at the same token budget (N independent runs, judge picks best) — SR must beat that too, not just the single pass.
4. Log the outcome to `~/knowledge/feedback/WINS.md` / `LESSONS.md`.

---

## 7. Risks & notes
- **Cost:** expect ~5–10× a single pass with fan-out + 2–3 rounds (literature: multi-agent ≈ 15× chat). Toggle defaults OFF; `high_stakes` recommended alongside but orthogonal.
- **Critic hallucination:** even grounded critics invent problems (CriticGPT data). Mitigations: evidence citation required per finding, anchor validation against real lines, comments stay human-editable, escalation instead of infinite loops.
- **Sandbox residue:** `finally:` rmtree + 24 h sweep; `super.keep_sandbox=1` for debugging only.
- **Isolation honesty:** accident boundary, not adversary boundary (§4.3).
- **CLI drift:** `cverify` depends on `-p`, `--model`, `--permission-mode acceptEdits`, `--allowedTools`, `--disallowedTools` — all verified on this machine. Sentinel-fenced JSON + defensive parsing chosen over fancier output flags on purpose.
- **Convergence semantics:** `keys ⊆ prev` also catches "critic repeats the same findings because the executor failed to fix them" → correct behavior is escalate to human, which this does.

## 8. Appendix A — normal-mode optimizations (cheap, ride along with the main build)

Super Result is the expensive mode. The everyday pipeline (no sandbox, no fan-out) can still get most of the *automation* at near-zero extra token cost by sharing components. Implement N1–N4 during the main steps (they reuse Step 1/4/5 code); N5–N8 are independent, setting-gated follow-ups.

**Tier 1 — zero extra LLM calls (the judge already runs; make the one call count):**
- **N1. Type-aware rubric for the normal judge.** In `run_judge_cmd` (`evals.py:152`), resolve `detect_deliverable_type` + `type_rubric_path` (Step 4 functions) and pass the type rubric to cjudge (new optional token `{type_rubric}` or env `JUDGE_TYPE_RUBRIC`; cjudge grades against BOTH rubrics). An analysis report then faces the A1 "verified-not-inferred" gate instead of code-diff gates G1–G10. **This alone — no sandbox — would have failed reports 1 & 2**: a document-only judge can't verify evidence is *true*, but it CAN see that a load-bearing conclusion rests on a proxy inference ("tests pass ⇒ code healthy") instead of cited primary evidence.
- **N2. cjudge prompt upgrade** (`setup/bin/cjudge` + `~/.local/bin/cjudge`): refute-by-default framing, binary gate table, and END with a small sentinel-fenced JSON block `{verdict, findings:[{file_path, line_no, line_text, problem, fix}], revision_brief}` after the prose. Parse best-effort in `parse_judge_metrics` (`evals.py:215`); on parse failure fall back to today's behavior — strictly additive.
- **N3. Judge auto-comments.** When `_judge_thread` (`server.py:3590`) gets parsed findings, reuse `_insert_critic_comments` with `source='judge'` (needs only the Step 1 `source` column) — the side-by-side view auto-fills in normal mode too, ungrounded but free, human-editable, drained by the existing retry. Tag `[JUDGE]` in `_retry_task` notes.
- **N4. Structured revision brief.** In `_retry_task` (`server.py:3710`), prefer the parsed `revision_brief` over the raw `judge_output[-3000:]` tail when available — the re-run gets a textual gradient instead of prose scrapings.

**Tier 2 — one extra LLM call at specific moments, each behind a setting:**
- **N5. Widen auto-judge gating.** Today `auto_judge` requires quality + high-stakes + closed (`loop_engine.py:126`). New setting `judge.auto_scope = high_stakes (default) | all_quality` so every quality-mode deliverable gets judged (+1 judge call each) — the loop then auto-retries non-high-stakes work too.
- **N6. Auto-draft replans.** `_sweep_replan_detection` (`loop_engine.py:355`) currently only flags `replan.status='needed'`; drafting waits for the operator. Setting `replan.auto_draft=1` → the sweep also fires `POST /api/workflows/{id}/replan/draft`, so the proposal is already sitting there when the human opens it. Apply stays operator-approved — the three-gate design is preserved, only the wait in the middle disappears.
- **N7. Judge-before-blind-retry** (optional, `judge.on_blind_reject`): an approval rejected with empty feedback and no fresh judge verdict currently re-runs on stale/no substance; gate-run the judge first so every retry carries findings.

**Eval-corpus compatibility (REQUIRED when implementing N1/N2 — the eval runner shares the judge path):**
- The eval runner (`_run_thread` `evals.py:319-378`) calls `run_judge_cmd` + `parse_judge_metrics` without a real task. **N1's type rubric must be an optional parameter** (`run_judge_cmd(..., type_rubric=None)`, default = today's behavior); task-judge callers resolve it via `detect_deliverable_type(task)`; the eval runner passes None, or resolves from new OPTIONAL eval-case frontmatter `deliverable_type`.
- **Extend `fingerprint`** (`evals.py:115-134`) to hash `~/knowledge/rubrics/*.md` once type rubrics influence judging — otherwise editing INVESTIGATION.md shifts scores under an "unchanged" config fingerprint, breaking the config-delta tracking the corpus exists for.
- **N2 is an era boundary for eval trends**: the refute-by-default/binary-gate judge is harsher, so historical score comparability breaks at that commit. Note it in the run history (scores comparable within a fingerprint only); `parse_judge_metrics` keeps its existing fallback so old-format judge output still parses.
- The Super Result loop itself intentionally does NOT run inside eval runs (the runner never enters the task/dispatch/loop pipeline) — evals stay a single-pass measure of executor+config quality.

**Tier 3 — the self-improving loop (small separate feature):**
- **N8. Recurring-findings distillation (GEPA-lite).** A scheduled job (scheduler exists) aggregates the last N judged tasks' findings + `learn_section` lines per domain, one LLM call proposes PLAYBOOK/RUBRIC deltas ("executor keeps omitting X — add to checklist"), filed as an approval; on approve, write to `~/knowledge` (git-committed, like onboarding apply). Normal mode then stops repeating the same mistakes — the automated version of the WINS/LESSONS habit.

## 9. Appendix B — system-coherence audit (every other subsystem vs this plan)

Audited 2026-07-09 against the full feature surface. **Coherent by construction (no changes needed):** budgets/quota (retry's budget slice + daily cap + quota backoff all sit downstream of the loop's retry call), watchdog (critic runs in server threads, not agent lanes; timeout owned by `sp.run`), app/project previews (sandboxes live in `app/workspaces/_critic/`, not in any task workspace, so deliverable aggregation, review diffs, and preview overlays never see them), attachments (included in the sandbox copy as evidence), PR flow (critic clones the repo read-equivalent; branch/PR path untouched), multi-user (comments/approvals/endpoints all owner-scoped), existing gates (Block 2's "retry consumes comments" unaffected — `source` defaults `'user'`), guardian/vendoring (cverify follows the cjudge dual-copy convention).

**Gaps found — fold these into the build:**

- **B1 (correctness, fold into Step 5): boot-reset orphaned critic state.** A server restart mid-critique leaves `critic_verdict='running'` forever — the sweep then never re-runs the critic (step 3 of `_sweep_super_result` skips `running`) and never escalates. On startup, mirror the replan orphan reset (`drafting`→`needed` pattern): `UPDATE tasks SET critic_verdict='error', critic_output=COALESCE(critic_output,'')||' [orphaned by restart]' WHERE critic_verdict='running'`. Add a check for this to `verify_super_result_e2e.py`.
- **B2 (integration, fold into Step 9 or its own step): JARVIS awareness.** JARVIS's per-turn system control framing documents the FULL OS surface so it can drive the board via curl — it must learn: the `super_result` flag on task/workflow create+patch, `POST/GET /api/tasks/{id}/critic`, and the new `super_result` approval type (so "JARVIS, run this as a Super Result task" / "what's stuck?" work). Also: the deck's approvals list and the spoken task callbacks should treat `super_result` escalations as first-class ("Super Result on X escalated after 3 rounds — 4 findings await you"), and the daily briefing should count pending SR checkpoints.
- **B3 (fold into Step 9): plan-editor fields.** The proposal-modal plan editor (`planEd*`) must display + preserve `super_result` and `deliverable_type` per task through the edit → `revalidate` round-trip (the backend passthrough exists via `_clamp_wizard_task`; the UI must not drop the fields when rebuilding the plan payload), ideally as editable controls next to stakes/model.
- **B4 (small): scheduler templates.** Cron-scheduled tasks (`scheduled_jobs` → single todo task) should accept `super_result`/`deliverable_type` in the job's task template so recurring high-value jobs (e.g. a weekly audit) get the loop automatically. One field passthrough in scheduler.py + the job-create UI.
- **B5 (small, extend Step 9): critic visibility parity.** The deliverables tab and workflow roll-up show the judge verdict chip — add the critic verdict/round chip in the same spots, not just kanban cards and task detail.
- **B6 (small, extend Step 3 schema): `learning_note` field.** cjudge ends with a `Learning note:` line that feeds `learn_section` and the lessons flow; give the critic schema an optional `"learning_note": "≤300"` and store it the same way — it becomes free, high-quality input for N8's distillation.
- **B7 (note): critic cost is invisible to token accounting.** Critic runs bill the Claude CLI subscription, not the GLM budget counters (same as the judge today) — the Usage tab will under-report Super Result cost. Minimum: `log_activity` already records each run (Step 5a); optionally add a `critic_runs` counter per task in the GET payload so the UI can show "3 critic runs" honestly. Do NOT wire it into `budget_tokens` (different currency).
- **B8 (one-line guards, fold into Step 6): sweep state filters.** `_sweep_super_result` must skip `status='archived'` tasks (replan leftovers) and not re-trigger while a task sits `blocked_quota`/`blocked_budget` or mid-dispatch — mirror the freshness/state filters `_sweep_task_loops` already applies, so the loop never hammers a blocked task.
- **B9 (nicety): live comment refresh.** If the review modal is open while the critic posts comments, `uiLocked()` correctly prevents a re-render; emit a toast ("critic posted 5 comments — reopen review to see them") rather than force-refreshing under the user's cursor.

## 10. Appendix C — beat-the-top-tier program (approved 2026-07-10; post-Step-11, NOT part of the initial implementation)

**Operating principle (locked by operator):** the system permanently runs on models **one tier below the current top**. Bulk executor = best cheap model (today GLM-5.2); judgment roles (critic/judge/spec/escalation) = best affordable frontier (today **Opus 4.8**). The current top model (today **Fable 5**) is NEVER a system component — it is the **reference**: the quality bar to approach and the blind judge in arm-comparison tests. On each model generation, every role rotates up one tier (Opus 4.8 → Fable 5 once affordable; GLM-5.2 → its successor) and the benchmark harness re-runs. **Success criterion per generation: beat the judgment-tier model used directly (win-rate > 50%, target 70%+) while total $ per task stays below one top-tier direct pass.**

Build order: ~~C3 → C4 → C1a → C1c → C1b/C1d → C2 → C5/C6~~ **SUPERSEDED 2026-07-10 by `QUALITY-AUTOPILOT-PLAN-2026-07-10.md` Part 3** (operator decision: ONE deferred measurement campaign at the end — C3 → C1 → C2 build in Phase 7, C4 + Step 11 + Q6 run last as Phase 8). Recorded risk, stated plainly: C1/C5 thresholds and the profile bands ship HEURISTIC and unmeasured until that final campaign validates or reverts them. The "post-Step-11" label in this appendix's header reflects the original ordering and is likewise superseded.

- **C1 — Escalation ladder** (closes the generation gap where the executor's writing ceiling binds, i.e. coding/design):
  - **C1a Frontier spec stage.** Coding/complex pipelines run the spec/architecture task on the judgment-tier model (new registry purpose `spec_model`, default = the frontier_judge assignment); GLM implements from the spec. Specs are short — a few thousand frontier tokens buy the binding constraint (design quality). Replaces the hardcoded dev-stage model floor with purpose resolution. **Premortem note (2026-07-10): `db.MODEL_PURPOSES` is a hard whitelist enforced by the assignment API/UI — extend it (+ the settings UI loop) with `spec_model`/`escalation_model` in the same step that seeds them, or the operator can never point or rotate them. All frontier calls go through the P1 backpressure semaphore (QUALITY-AUTOPILOT Part 4).**
  - **C1b Critic patches.** `cverify` findings gain an optional `patch` field (unified-diff hunks) for critical findings; the executor applies them mechanically instead of reinterpreting prose. (CriticGPT pattern: critic-proposed fix + executor application beats either alone.)
  - **C1c Escalated rework — the guarantee.** On REWRITE verdict, or round-cap with critical findings still open, the rework itself runs on the judgment-tier model: a headless-claude *executor* runner (cverify minus the sandbox — real workspace, write access) handed the full dossier (brief, verified findings, contradiction list, critique history, sibling reports). Worst case the judgment-tier model writes the final version with the full dossier as input — designed so the floor *approaches* judgment-tier-direct, but NOT guaranteed "by construction" (critic check F8): a dossier carrying wrong critic findings or a flawed draft can anchor the rework below a clean direct pass (see the §7 critic-hallucination note). Treat the floor as an empirical claim — the C4 campaign should include an escalated-rework-vs-direct comparison where cheap. New purpose `escalation_model`; setting-gated (`super.escalation`), and near-zero marginal cost on the CLI subscription.
  - **C1d Best-of-2 executor drafts** (optional, medium coding tasks): two cheap independent GLM implementations, critic picks the better before refinement rounds.
- **C2 — Registry-only model references (rotation readiness).** Audit out every hardcoded model name (dev-stage floor `glm-5.2`, fallback `glm-5-turbo`, …) so ALL roles resolve via registry purposes: `executor_bulk / executor_light / fallback / spec_model / escalation_model / frontier_judge`. A generation rotation then = registry edits + benchmark rerun, zero code changes.
- **C3 — Full-cost ledger (prerequisite for the goal).** Frontier runs (critic/judge/spec/escalation) currently bill the Claude subscription invisibly (B7). Capture their token usage (`claude -p --output-format json` usage fields; fallback: transcript-size estimate) into per-task counters, plus a per-model price table in settings → every task/workflow gets a **total $ figure across both currencies**. Without this, "beats Opus, cheaper than Fable" is an unverifiable claim.
- **C4 — Permanent benchmark harness (Step 11 generalized).** Fixed suite (~12 tasks: 3 × coding / research-audit / content / long-project) run through 4 arms: system-SR, GLM-direct, judgment-tier-direct (Opus 4.8), top-tier-direct (Fable 5, reference). **Blind judging by the reference model**: provenance stripped, pairwise with position-swapping (kills position/self-preference bias), rubric-anchored. Outputs: win-rate matrix + $ per arm, stored eval_runs-style with config fingerprint. Reruns on every tier rotation, prompt/rubric change, or quarterly. This is what turns "we think it beats Opus" into a measured, re-checkable fact per generation. **Additions from the 2026-07-10 spend-profile audit:** (a) define "Optimal" empirically the RouterArena way — log `(route, correctness, cost)` per case, compute the oracle cheapest-correct frontier, score with a weighted harmonic mean of accuracy and log-normalized cost (β≈0.1), and tune the Optimal profile's triage thresholds to it; (b) run 2–3 suite rows additionally under Eco and Smart to validate the profile bands BEHAVIORALLY (low-effort modes are documented to reduce tool-call thoroughness, not just tokens — "same answer, cheaper" must be proven, else Eco's floor rises); (c) check for router collapse (spend distribution saturating to the max-spend path when the oracle wouldn't).
- **C5 — Cost-aware routing polish.** Difficulty triage at wizard time (auto-recommend SR only when goal complexity warrants), adaptive fan-out width by stakes, escalation thresholds tuned from C4 data — spend frontier tokens only where the measured gap is.
- **C6 — The flywheel (N8, now with fuel).** Lessons distillation has automatic input since every critic round produces findings + `learning_note`s: schedule the per-domain distillation → PLAYBOOK/RUBRIC deltas (approval-gated). Each cycle raises the cheap executor's baseline for free — compounding toward the top-tier bar between rotations.

## 11. Primary sources
- Huang et al., *LLMs Cannot Self-Correct Reasoning Yet* — arxiv.org/abs/2310.01798 · Kamoi et al. (TACL'24) — arxiv.org/html/2406.01297v3 · Xu et al., *Pride and Prejudice* — arxiv.org/abs/2402.11436
- Gou et al., *CRITIC* — arxiv.org/abs/2305.11738 · Zhuge et al., *Agent-as-a-Judge* — arxiv.org/abs/2410.10934 · McAleese et al., *CriticGPT* — arxiv.org/abs/2407.00215
- Madaan et al., *Self-Refine* — arxiv.org/pdf/2303.17651 · Shinn et al., *Reflexion* — arxiv.org/html/2303.11366
- Du et al., *Multiagent Debate* — arxiv.org/abs/2305.14325 · *Talk Isn't Always Cheap* — arxiv.org/html/2509.05396 · Wang et al., *Mixture-of-Agents* — arxiv.org/abs/2406.04692 · Snell et al., *Scaling Test-Time Compute* (ICLR'25)
- Dhuliawala et al., *Chain-of-Verification* — arxiv.org/abs/2309.11495 · Manakul et al., *SelfCheckGPT* — arxiv.org/abs/2303.08896 · Agrawal et al., *GEPA* — arxiv.org/html/2507.19457v1 · *N-CRITICS* — arxiv.org/pdf/2310.18679
- Anthropic, *Multi-Agent Research System* — anthropic.com/engineering/multi-agent-research-system · *Building Effective Agents* — anthropic.com/engineering/building-effective-agents
- Judge bias: arxiv.org/abs/2410.02736 · arxiv.org/abs/2406.07791 · arxiv.org/pdf/2410.21819
