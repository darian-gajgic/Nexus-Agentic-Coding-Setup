# Specialist-Agent System — Wiring Reference

*How the persistent specialist-agent system is built and wired. Written 2026-07-05 so a fresh Claude Code session can understand and safely modify it. Read this fully before touching anything under this system.*

---

## 0. TL;DR for a new session

Hermes can now **reuse predefined "specialist" agents** (web-researcher, code-implementer, qa-tester) instead of always spawning generic dynamic subagents. Each specialist has a **git-versioned playbook** (standing rules) and its **own private mem0 memory scope** (layered on a shared base), reads that memory two-scope, learns **human-curated lessons**, and is **viewable/editable in the nexus dashboard**. Selection is **model-driven**: GLM sees the specialist registry in the `delegate_task` tool and passes `specialist=<name>`.

**CRITICAL — persistence model.** Most of this modifies **Hermes's own bundled source** (`~/.hermes/hermes-agent`, a git repo). A `hermes update` (git pull/reset) would revert those edits. They survive because the **guardian re-applies them as git patches after every update** ("core-mods"). If you edit any of the four core files, you MUST refresh the corresponding patch (see §7) or the guardian will re-assert the OLD version and clobber your change, or flag a conflict.

---

## 1. Components & files

| Component | Location | Kind |
|---|---|---|
| mem0 provider (two-scope memory) | `~/.hermes/hermes-agent/plugins/memory/mem0/__init__.py` | **core-mod patch** |
| agent init (memory gate/scoping) | `~/.hermes/hermes-agent/agent/agent_init.py` | **core-mod patch** |
| agent runtime (read-only write gate) | `~/.hermes/hermes-agent/run_agent.py` | **core-mod patch** |
| delegation (specialist binding + resolver dispatch + schema) | `~/.hermes/hermes-agent/tools/delegate_tool.py` | **core-mod patch** |
| specialist resolver + registry | `~/.hermes/hermes-agent/tools/specialist_resolver.py` | **authored file** (guardian golden) |
| specialist definitions | `~/.hermes/agents/*.md` | git repo (`~/.hermes/agents/.git`) |
| curated lesson writer | `~/.hermes/scripts/mem0_curate.py` | authored file (guardian golden) |
| auto-reflection drafter | `~/.hermes/scripts/reflect.py` | authored file (guardian golden) |
| reflection timer | `~/.config/systemd/user/hermes-reflect.{service,timer}` | systemd user (guardian service) |
| lesson pruner | `~/.hermes/scripts/prune_lessons.py` | authored file (guardian golden) |
| prune timer | `~/.config/systemd/user/hermes-prune.{service,timer}` | systemd user (guardian service) |
| Hermes skill: create-a-specialist | `~/.hermes/skills/software-development/creating-specialist-agents/SKILL.md` | git (`~/.hermes/skills/.git`) |
| guardian reconciler | `~/hermes-guardian/guardian.py` | git repo (`~/hermes-guardian/.git`) |
| core-mod registry + patches | `~/hermes-guardian/core-mods.json`, `~/hermes-guardian/patches/*.patch` | git-versioned |
| nexus dashboard (tabs + APIs) | `~/nexus-agent-os/server.py`, `static/app.js`, `static/index.html` | git repo |

Everything is self-hosted: mem0 OSS + qdrant server (`localhost:6333`, docker `restart:always`), Ollama (`nomic-embed-text` 768d embed, `llama3.1:8b` extractor), GLM-5.2 via Z.AI (primary), nexus on `https://127.0.0.1:8777`, Hermes gateway (systemd user `hermes-gateway.service`).

---

## 2. Memory scoping (mem0 provider)

`plugins/memory/mem0/__init__.py` — the provider was changed so **agent_id is per-call** and reads are **two-scope**:
- `initialize(**kwargs)` (~line 360): `self._agent_id = kwargs.get("agent_id") or self._config.get("agent_id","hermes")`; `self._shared_agent_id = <config agent_id, i.e. "hermes">`.
- Helpers added after `_read_filters` (~373): `_is_specialist()` (agent_id != shared), `_merge_scoped()` (role-first dedup), `_scoped_search()` / `_scoped_get_all()`.
- **Primary agent** (`agent_id == "hermes"`) → `_is_specialist()` is False → reads `{user_id}` (all agents) — **unchanged, zero regression**.
- **Specialist** (`agent_id == role`) → **two separate qdrant queries** merged role-first: `{user_id, agent_id: role}` (its own lessons) + `{user_id, agent_id: _TEAM_SHARED}` where `_TEAM_SHARED = "team-shared"` — a **curated** cross-cutting scope, deliberately NOT the primary agent's raw `hermes` conversation memory (so specialists don't inherit that noise). Uses two calls (NOT a single OR filter — that works on OSS/qdrant but two-call is the safe default for independent recall budgets).
- The `team-shared` scope is curated by the user in the nexus **Specialists tab → "Shared team context"** panel (`/api/shared-context` CRUD → `mem0_curate.py add --agent-id team-shared`). The primary agent (`agent_id == "hermes"`) still reads `{user_id}` (all) — unchanged.
- **mem0 is OSS mode** (`~/.hermes/mem0.json` `mode=oss`). This design ONLY works on OSS (Platform inverts the filter semantics). Do not switch to platform mode.
- **Sentinel** (present iff applied): `_shared_agent_id`.

---

## 3. Delegation threading (how a subagent becomes a specialist)

Three core files carry a specialist into a delegated child:

**`agent/agent_init.py`** — `init_agent()` gained `provider_memory`, `memory_agent_id`, `memory_read_only`:
- The single `skip_memory` gate was **split**: Block A (MEMORY.md/USER.md store) stays `if not skip_memory` (so a specialist never loads MEMORY.md); Block B (mem0 provider) became `if (not skip_memory) or provider_memory` (so a specialist gets scoped mem0 with `skip_memory=True`). `mem_config` is re-fetched at the top of Block B.
- `memory_agent_id` is injected into the provider init kwargs (near the existing `agent_context="primary"`), and `agent._memory_read_only` is stored.
- Sentinel: `(not skip_memory) or provider_memory`.

**`run_agent.py`** — `AIAgent.__init__` forwards the 3 params to `init_agent`; and the per-turn auto-write is gated: `if not getattr(self, "_memory_read_only", False): self._memory_manager.sync_all(...)` (retrieval/prefetch stays on; the append-all write is suppressed). Sentinel: `getattr(self, "_memory_read_only", False)`.

**`tools/delegate_tool.py`**:
- `_build_child_system_prompt(..., playbook=None)` → injects a `## STANDING RULES` section with the specialist's playbook.
- `_build_child_agent(..., specialist, playbook, memory_agent_id, memory_read_only=True)` → threads playbook into the prompt, `toolsets` = the specialist's allowlist, and at `AIAgent(...)` sets `provider_memory=bool(memory_agent_id), memory_agent_id=..., memory_read_only=...` while **keeping `skip_memory=True` and `skip_context_files=True`**. `DELEGATE_BLOCKED_TOOLS` is untouched (so mem0 **write** tools never reach the child → provider-yes / write-no).
- Dispatch (`delegate_task`): a `specialist` param (top-level + per-task) was added to the schema; `_resolve_task_specialist()` resolves it; the resolved `{name, playbook, agent_id, toolsets}` drive `_build_child_agent`. No specialist → today's dynamic subagent (unchanged).
- The tool DESCRIPTION appends `_specialist_registry_block()` so the delegating model sees the available specialists.
- Sentinel: `provider_memory=bool(memory_agent_id)`.

**Net behavior of a specialist subagent:** playbook injected as standing rules; two-scope memory retrieval (own + shared base); **read-only** (no auto-write, no write tools); MEMORY.md off; its own tool allowlist. Verified against real GLM: research→web-researcher, coding→code-implementer, testing→qa-tester, trivial→no delegation.

---

## 4. Specialists & the resolver (model-driven selection)

**`tools/specialist_resolver.py`** (authored, not bundled):
- `load_specialists()` — parses `~/.hermes/agents/*.md` (frontmatter `name`, `description`, `tools`, `mem0_agent_id` + body = playbook).
- `resolve_specialist(name)` — exact-name lookup → dict or None.
- `registry_block()` — the "AVAILABLE SPECIALISTS — prefer these…" text appended to the `delegate_task` tool description.

**Selection is model-driven, NOT embedding/keyword.** (Embedding matching with nomic was tested and was *not* discriminative — all roles scored ~0.5 and "research how to **implement** X" matched code-implementer. Local-LLM routing was too slow. GLM reading the registry and picking by name is reliable and zero-latency — verified live.)

**The library (46 specialists, 2026-07-05):** 3 base + 26 (first wave: dev/SaaS/research/marketing/brand + dj/music/multi-tenancy/auth/strategy) + 17 (second wave). Second wave = **dev-pipeline** (tech-lead-orchestrator, technical-writer, acceptance-verifier), **content creation** (long-form-writer, social-content-creator, newsletter-writer, content-repurposer, content-editor), **brand execution** (brand-namer, visual-identity-director, brand-auditor), **e-commerce** (product-data-feed-optimizer, marketplace-listing-optimizer, lifecycle-retention-marketer, shopping-ads-specialist, ecommerce-merchandiser, pricing-promotions-strategist). All git-versioned in `~/.hermes/agents/.git`. **Gotcha:** a `description:` containing a `:` breaks YAML — always quote descriptions (the converter does).

**SOTA dev pipeline (2026 audit):** the roster had the roles but not the wired pipeline. Fixed by the `development-workflow` skill (`~/.hermes/skills/software-development/development-workflow/`) which makes GLM run research→plan→implement→test→review-LOOP→verify→document (fresh-context code-review loop + verification gate; "parallelize reads, single-thread writes"), plus the 3 dev-pipeline agents above. `/goal` contracts + verification_evidence.db are the intended gate.

**Delegation-directive note:** `specialist_resolver.registry_block()` was broadened so GLM delegates *creative/commerce* work, not only coding. 46 specialists ⇒ ~3.6k-token tool description (fine).

**Keyword-triggered forced router (the general fix for under-delegation) — `~/.hermes/plugins/routing/specialist_router/`.** GLM under-delegates (self-handles research/analysis/writing via web_search). Fix, per web research (Anthropic routing-workflow + forced tool choice) + a code audit of Hermes hooks: a user plugin (`__init__.py` + `plugin.yaml`, enabled in `config.yaml` plugins.enabled) registering the **`pre_gateway_dispatch`** hook. On a trigger phrase ("use a specialist/agent"…) it runs ONE **forced** `select_specialist` classification call (enum built at runtime from the registry + a "none" escape — so new agents are auto-included, zero config) and **rewrites the message to prepend** a mandatory delegate directive naming the chosen specialist. No trigger / "none" fit → untouched. Subagent-safe (`is_internal`), fail-soft, survives updates (not core, not guardian). **Provider facts that shaped it:** z.ai/GLM honors forced `tool_choice` for the small select_specialist tool but NOT for the huge delegate_task tool (can't hard-force delegation → use a directive); **prepending** the directive beats appending for stubborn "analyze our X" phrasings (→ `pre_gateway_dispatch` rewrite, not the append-only `pre_llm_call` channel). A softer, trigger-less nudge also lives in `SOUL.md` (optional; the router is the reliable, general layer).

**Specialist definition format** (`~/.hermes/agents/<name>.md`, Claude Code `.claude/agents` style):
```
---
name: web-researcher
description: <when-to-use text the model matches on>
tools: [web]
mem0_agent_id: web-researcher
---
<body = standing-rules playbook>
```
Three exist: `web-researcher`, `code-implementer`, `qa-tester`. Git repo at `~/.hermes/agents/.git`.

---

## 5. nexus dashboard

**Specialists tab** (`static/app.js`: `viewSpecialists`/`bindSpecialists`/`editSpecialist`/`saveSpecialist`/`manageLessons`/`addLesson`/`deleteLesson`; `showModal` was added — it was previously undefined):
- `GET /api/specialists` → each specialist's def + tools + `agent_id` + `memories` (from qdrant by agent_id) + count.
- `POST /api/specialists/save` `{name, content}` → writes `~/.hermes/agents/<name>.md` + `git commit`.
- `POST /api/specialists/{name}/memory` `{text}` → adds a curated lesson via `~/.hermes/scripts/mem0_curate.py add`.
- `DELETE /api/specialists/{name}/memory/{id}` → `mem0_curate.py delete`.

**Guardian tab → Core Mods panel** (`viewCoremods`/`decideCoremod`): shows each tracked core-mod's status; on CONFLICT shows the diff + impact + **Keep-ours / Accept-upstream** buttons. `GET /api/coremods`, `POST /api/coremods/decide`.

**`mem0_curate.py`** (hermes-venv script) writes/deletes a lesson through the mem0 backend under a chosen `agent_id` (embeds via Ollama, `infer=False` = verbatim curated). nexus subprocesses it.

---

## 6. Guardian & the core-mod persistence mechanism (READ THIS)

`~/hermes-guardian/` (git repo, outside `~/.hermes`). The guardian runs on a systemd timer (boot + every 15 min) and reconciles:
- **files** (golden copies), **config values** (surgical line edits), **env presence**, **packages**, **services**, **containers** — the original hardening.
- **core-mods** — NEW: our edits to Hermes's own source, tracked as git patches.

**`reconcile_core_mods()` in `guardian.py`** — for each entry in `core-mods.json` (`{name, file, patch, sentinel, description, impact_if_dropped}`):
- **intact** (sentinel present) → OK.
- **cleanly reverted** (sentinel gone, `git apply --check` clean) → auto `git apply` (re-assert ours) + report REASSERTED.
- **conflict** (`git apply --check` fails — an update changed the same lines) → HOLD, do NOT force; surface in nexus for a decision.
- Honors standing decisions in `core-mods-state.json`: `standing="accept_upstream"` (hands off) / one-shot `decision="keep_ours"` (force `git apply --3way`).
- After reasserting any core-mod, restarts the Hermes gateway.

**The four tracked core-mods** (patches in `~/hermes-guardian/patches/`):
| name | file | sentinel |
|---|---|---|
| `mem0-per-agent-scoping` | `plugins/memory/mem0/__init__.py` | `_shared_agent_id` |
| `specialist-mem-gate-agentinit` | `agent/agent_init.py` | `(not skip_memory) or provider_memory` |
| `specialist-mem-readonly-runagent` | `run_agent.py` | `getattr(self, "_memory_read_only", False)` |
| `specialist-binding-delegate` | `tools/delegate_tool.py` | `provider_memory=bool(memory_agent_id)` |

**Verified:** reverting all 4 files at once (simulating a full update) → guardian re-applied all 4 + restarted the gateway + the system stayed intact.

---

## 7. How to modify things (playbook for a future session)

**Edit a core Hermes file (any of the 4):** make the edit → **regenerate its patch**: `git -C ~/.hermes/hermes-agent diff <file> > ~/hermes-guardian/patches/<patch>.patch` → run `python3 ~/hermes-guardian/guardian.py` (should show OK) → `git -C ~/hermes-guardian commit`. If you forget, the guardian re-asserts the stale patch and reverts your edit (or conflicts).
- Keep the Hermes edits as **unstaged working-tree modifications** (not staged/committed in the Hermes repo). `git -C ~/.hermes/hermes-agent status` should show ` M`. (Staged edits break patch regen via `git diff`.)

**Add/protect a new authored file (not a core edit):** copy it to `~/hermes-guardian/golden/`, add a `files[]` entry to `~/hermes-guardian/manifest.json` (`{path, golden, sha256, mode, restore_mode:"whole"}`), run the guardian.

**Add a specialist:** create `~/.hermes/agents/<name>.md` (frontmatter + playbook), `git -C ~/.hermes/agents commit`. It auto-appears in the registry / nexus. (Specialist *defs* are git-protected, NOT guardian-golden — they're meant to be edited.)

**Edit a specialist's rules / add a lesson:** via the nexus Specialists tab (commits to `~/.hermes/agents` git / writes mem0), or edit the file / call `mem0_curate.py` directly.

**After editing nexus:** `systemctl --user restart nexus.service` (kill any orphan on :8777 first — see below). Commit with `--no-verify` (the pre-commit hook has a pre-existing avatar.js/query-string false-positive unrelated to our work).

**nexus gotcha:** a stale process can keep holding :8777 across a restart, causing a crash-loop on old code. Fix: `kill` the orphan PID on :8777, then `systemctl --user restart nexus.service`.

---

## 8. Verify it's all healthy
```
python3 ~/hermes-guardian/guardian.py          # expect: overall=OK, core_mods all OK
curl -sk https://127.0.0.1:8777/api/coremods   # expect: all OK
curl -sk https://127.0.0.1:8777/api/specialists
```
Guardian is authoritative: `overall OK` + 4 core-mods OK = the system is intact.

---

## 9. Auto-reflection (DONE — validated + built + verified)

Web-validated 2026-07-05 (Reflexion / ACE +10.6% / GEPA / OWASP ASI06 / diff-and-approve). Verdict: **SOUND** — reflection→lesson→memory is proven, and human-approval-before-write is the exact OWASP ASI06 defense. **Full loop wiring:**
- **Completion log:** `tools/delegate_tool.py::_log_specialist_completion()` appends `{specialist, goal, outcome, ts}` to `~/.hermes/agents/.reflection_log.jsonl` when a *specialist* child finishes ok (in the result-collection loop; only specialists, not dynamic subagents). This is part of the `specialist-binding-delegate` core-mod patch.
- **Drafter:** `~/.hermes/scripts/reflect.py` (systemd `hermes-reflect.timer`, every 30 min; state in `.reflect_state.json` tracks processed offset). For each new completion it asks **GLM** (`glm-5.2` via Z.AI, key read from `~/.hermes/.env`) for ONE atomic lesson or `{"lesson": null}` (salience gate — routine tasks yield nothing). Then a **worthiness gate**: discard if confidence < 0.55, or if embedding-similar (≥0.86, nomic + qdrant search in the specialist's scope) to an existing lesson — never surfaces a duplicate.
- **Proposal** (in `~/.hermes/agents/.pending_lessons.json`): `{specialist, insight (What I learned), lesson (How I'll apply it — the rule to store), source_goal, source_outcome (confabulation/provenance check), similar_existing (diff), confidence, type}`.
- **Approval** — nexus Specialists tab shows a "Proposed lessons" panel; **Review** opens the 6-field summary → **Approve / edit-the-rule-then-approve / Reject**. `GET /api/lessons/pending`, `POST /api/lessons/{id}/decide`. Approve → `mem0_curate.py add --source reflection-approved` writes to the specialist's **PRIVATE scope only**, metadata `{trust: human-approved, source: reflection-approved}`. Nothing writes without approval.
- **Verified:** salient task → high-confidence atomic rule drafted; routine task → nothing; approve → written to private memory + queue cleared; isolation preserved.
- Deferred iterations: decay/prune old lessons, eval-gate a new lesson vs a per-specialist canary set, route rule-type lessons to the git playbook as a PR, approval-rate telemetry (rubber-stamp warning), reject-reason capture.

## 10. Creating specialists & lesson lifecycle (pruning)

**Creating a specialist — three ways:** (1) nexus **Specialists tab → "+ Add specialist"** form; (2) ask **Hermes** ("make this a persistent agent") — it now knows the convention via the `creating-specialist-agents` skill (writes `~/.hermes/agents/<name>.md` + commits); (3) drop the `.md` file yourself. All three go live immediately (resolver reads the dir). Auto-promotion (Hermes *proposing* a specialist on its own) is intentionally NOT built.

**Pruning / decay (bulletproof, nothing deleted):**
- mem0 `_scoped_search` logs which of a specialist's own lessons actually surface → `~/.hermes/agents/.lesson_usage.jsonl` (part of the `mem0-per-agent-scoping` core-mod; sentinel still `_shared_agent_id`).
- `~/.hermes/scripts/prune_lessons.py` (`hermes-prune.timer`, weekly) folds the usage log into `.lesson_usage_state.json`, then **soft-archives** any lesson older than `ARCHIVE_AGE_DAYS` (60; env `PRUNE_AGE_DAYS` overrides for testing) that has **never been retrieved** — by moving its qdrant `agent_id` to `<role>__archived`. It leaves active retrieval but is fully preserved.
- **Recover:** nexus manage-lessons shows archived lessons with a **restore** button (`GET /api/specialists/{name}/archived`, `POST .../archived/{id}/restore`). Nothing is ever hard-deleted by the pruner.
- Verified: unused lesson archived, used lesson kept, restore returns it to active memory.

## 11. Build status (2026-07-05)
- ✅ Phase 1 memory scoping · Core-mod reconciler + nexus panel · Phase 2 delegation threading · Phase 3 specialists + model-driven selection · Phase 4 nexus Specialists tab (view/edit) · Phase 5 human-curated lessons · Phase 6 persistence sweep · **Auto-reflection (§9)** · **Shared-base cleanup** (curated `team-shared` scope, §2) · **Eval gate — deterministic** · **Manual specialist creation** (Add button + Hermes skill, §10) · **Lesson pruning/decay** (soft-archive + restore, §10).
- ⬜ Next: **behavioral eval** (run a specialist on a per-role golden set + warn on regression — needs an independent judge, NOT GLM-judging-GLM; on-demand, not per-save). Intentionally skipped: auto-promotion (manual creation covers it).
- ⬜ Interim safeguard idea (not built): a "Test this specialist on an ad-hoc task" button + one-click rule-revert — cheap partial substitute for the behavioral eval.
- ⬜ Eval gate on rule edits (promptfoo). ⬜ Auto-promotion of recurring dynamic tasks. ⬜ Memory pruning/decay. ⬜ Shared-base cleanup (curated `team-shared` scope). ⬜ Edit Hermes *skills* in nexus (needs `HERMES_DASHBOARD_SESSION_TOKEN` = `API_SERVER_KEY` in `~/.hermes/.env`).

*Keep this document updated as each remaining feature lands.*
