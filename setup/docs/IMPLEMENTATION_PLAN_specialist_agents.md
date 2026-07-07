# Implementation Plan — Persistent Specialist Agents with Scoped Memory

*Prepared 2026-07-05. Grounded in a file:line verification pass over the live Hermes/mem0/nexus/guardian code plus current-API web checks. Build order is dependency-first; every phase is independently testable and shippable.*

---

## What we're building (one paragraph)

Turn Hermes' amnesiac, purely-dynamic subagents into a **hybrid**: a small catalog of **predefined specialists** (web-researcher, coder, tester, brand-copywriter…) that Hermes **reuses** when a task matches, while keeping today's **dynamic ephemeral spawn** as the fallback for novel work. Each specialist is a **git-versioned, human-editable definition** (its standing rules/instructions) bound to reusable **Skills**, plus a **private memory scope** (`agent_id`) that accumulates *curated episodic lessons* on top of a **shared base** everyone reads. New specialists are **proposed on recurrence and promoted by human approval**, never auto-persisted. Everything is **visible and editable in nexus** (definitions via git-committed files, memory via the existing qdrant reader). Instructions ≠ memory: standing rules live in the versioned definition (deterministic, always applied); memory holds soft, learned lessons.

**Design decision — specialists reuse the Skills subsystem (no parallel registry DB).** A specialist is a `SKILL.md` under `~/.hermes/skills/specialists/<name>/` tagged `metadata.hermes.agent_role`, which reuses *all* existing skill plumbing (create/edit/web-API/index/progressive-disclosure/nexus-display) and keeps your mental model: **agents live in `specialists/`, procedures are ordinary skills** they can bind. The only net-new pieces are the memory scoping, the get-or-create matcher, the delegation threading, and the nexus tabs.

---

## Key decisions & gotchas (the traps the verification caught)

| # | Decision / trap | Resolution in this plan |
|---|---|---|
| 1 | **mem0 two-scope read: single OR-filter is contested.** One check says `{user_id, OR:[agent_id=role, agent_id=shared]}` works (Qdrant must+should); another says `should` goes non-filtering when `must` is present. | **Default to two calls** (private `{user_id, agent_id:role}` + base `{user_id}`), merge role-first, dedup by id. Unambiguous, gives independent recall budgets. Keep the single-OR as a *verify-then-optimize* (Phase 1 verification empirically tests it). |
| 2 | **mem0 OSS vs Platform scoping are opposite.** This design only works because you run **OSS** (`mem0.json mode=oss`): OSS ANDs present keys and stores agent_id in the payload. Platform would return empty for combined filters. | Plan is OSS-only. If mem0 ever switches to platform mode, the memory layer must be redesigned — flagged in the risk register and guardian-pinned (`mode=oss`). |
| 3 | **No memory decay in OSS** (`main.py:424` raises on `decay=True`). "Curated + decaying" isn't free. | Build a small scheduled **pruning job** (qdrant delete by age/low-use) in Phase 5. Curation-at-write uses `infer=True` (LLM additive extraction + hash-dedup), *not* `infer=False` (verbatim append). |
| 4 | **`~/.hermes/skills` is not a git repo** and the skill-edit path never commits. | Phase 0 does a one-time `git init` + `.gitignore`; commit-on-save reuses Hermes' existing `/api/git/review/stage`+`/commit` endpoints. |
| 5 | **Guardian will revert UI edits.** It pins two SKILL.md files (`manifest.json:97+`) and restores golden every 15 min. | The save flow **refreshes golden+sha256** after commit (or de-enforces edited specialists). Phase 4 + Phase 6. |
| 6 | **Auth token mismatch.** nexus sends `Bearer API_SERVER_KEY`; Hermes write/git endpoints gate on `HERMES_DASHBOARD_SESSION_TOKEN`. | Phase 0 verifies the two are equal in `~/.hermes/.env` (or makes nexus also send `X-Hermes-Session-Token`). Save/commit 401s until aligned. |
| 7 | **Pre-existing nexus bug:** `showModal()` is called (`app.js:1141/1210/1268`) but never defined — Tools/Skills/Projects detail modals already throw. | Phase 0 defines `showModal` (also hosts the new skill editor). Must pass `verify.sh` (no dup function names, no `console.log`, `avatar.js` absent). |
| 8 | **Two different "agents" in nexus.** The existing `agents` tab is the (simulated) process fleet — a *different concept*. | Add a **separate "Registry" tab**; don't overload the existing one. |
| 9 | **Migration of existing memory.** All 20 existing memories are `agent_id='hermes'`. | Treat **`hermes` = the shared base** (seamless, no backfill). Specialist writes use `agent_id=<specialist-name>`; two-scope read = `{agent_id:role}` ∪ `{agent_id:hermes}`. |
| 10 | **Provider-yes / write-tool-no.** Enabling mem0 for a child re-arms per-turn auto-ingestion (`run_agent.py:3373`) = the append-all log the design forbids. | Split the `skip_memory` gate (retrieval on, MEMORY.md off) **and** gate `sync_all` behind a `memory_read_only` flag. `DELEGATE_BLOCKED_TOOLS` keeps the mem0 *write tools* off structurally. |

## New tools — decision

| Tool | Verdict | Why |
|---|---|---|
| **promptfoo** | **Install (thin)** | Local, YAML golden sets a non-technical partner can read, OpenAI-compatible provider (GLM/Ollama), CLI exit-code = the on-save eval gate, `promptfoo view` UI. |
| Claude Code `.claude/agents` schema + `AGENTS.md` | **Adopt convention** (not a package) | 2026 de-facto standard; mirror its frontmatter (`name`+`description` required, `tools`/`model`/`skills` optional) in the specialist `SKILL.md`. |
| LangMem | Skip | LangGraph-coupled, pre-1.0; would fork the memory layer. Mirror its 3-type concept in the git-playbook instead. |
| DeepEval | Skip (later maybe) | Heavier/pytest-native; promptfoo covers the small per-agent gate. |
| semantic-router / vLLM-SR | Skip | The matcher is ~50 lines over the Ollama+qdrant you already run. |
| CrewAI / MS Agent Framework / OpenAI Agent Builder | Skip | Heavyweight studios that duplicate Hermes+nexus; OpenAI deprecated its Builder. |

Everything else reuses the live stack: mem0+qdrant, Ollama (`nomic-embed-text` 768d, `llama3.1:8b`), Hermes Skills + web API, nexus, Langfuse, the guardian.

---

## Phase 0 — Preconditions (no behavior change, ~½ day)

| Step | Change | Verify |
|---|---|---|
| 0.1 Git-init skills | `git init ~/.hermes/skills` + `.gitignore` (`.usage.json*`, `.curator_state`, `.hub`, snapshots); initial commit. | `git -C ~/.hermes/skills log` shows the initial commit. |
| 0.2 Auth align | Confirm `API_SERVER_KEY == HERMES_DASHBOARD_SESSION_TOKEN` in `~/.hermes/.env`; else make nexus `_hermes_headers()` also send `X-Hermes-Session-Token` (`web_server.py:318` accepts it). | `curl -H "Authorization: Bearer $KEY" $HERMES/api/learning/node?id=client-delivery-gate` → 200; without header → 401. |
| 0.3 Fix `showModal` | Add `function showModal(html){ const c=$('#modalContent'); if(c)c.innerHTML=html; $('#modal').style.display='flex'; }` near `closeModal` (`app.js:2470`). | `bash scripts/verify.sh` passes; Tools/Skills detail modals stop throwing. |
| 0.4 Conventions | Adopt: shared base = `agent_id='hermes'`; specialist `agent_id` = specialist name; specialists live in `~/.hermes/skills/specialists/<name>/SKILL.md` with `metadata.hermes.{agent_role:true, mem0_agent_id, requires_toolsets, tools}`. | Doc only; referenced by later phases. |

## Phase 1 — Per-agent memory scoping in mem0 (the foundation, ~1 day, highest value)

The moment this lands, memory splits by agent and the nexus Memory tab shows it — *before* any specialist exists.

| Target (file:line) | Change |
|---|---|
| `plugins/memory/mem0/__init__.py:360` | `self._agent_id = kwargs.get('agent_id') or self._config.get('agent_id','hermes')` — honor a per-call override (mirrors how `user_id`/`platform` are already read at 359/361). Define `SHARED_AGENT_ID='hermes'`. |
| `plugins/memory/mem0/__init__.py:367-373` (`_read_filters` + a new two-call retrieval helper) | Implement **two-scope read**: call A `filters={'user_id':u,'agent_id':role}` → call B `filters={'user_id':u}` (the shared base incl. legacy `hermes` rows) → merge **role-first**, dedup by id, cap to top-k. When `agent_id==SHARED_AGENT_ID`, skip call A. |
| `plugins/memory/mem0/__init__.py:570-576` (`mem0_add`) | Switch curated writes from `infer=False` → `infer=True` (LLM additive extraction + md5 dedup), so role memory is not an append-all log. Add optional `scope` (role|shared) → chooses the `agent_id` written. |
| *(delegation hand-off, wired in Phase 2)* | Provider `initialize(**kwargs)` receives `agent_id=<specialist>` from the child-spawn path. |

**Verify (venv python against live qdrant):** add facts under `agent_id∈{web-researcher, hermes}`; assert `search(filters={'user_id':U,'agent_id':'web-researcher'})` returns only the role fact, `filters={'user_id':U}` returns both; assert the two-call merge yields role-first + base; assert `search(filters={'agent_id':{'in':[...]}})` **raises** (proves why we nest correctly); **empirically test the single-OR filter** to decide if we can collapse to one call later. Then open the nexus **Memory** tab → scopes now show `hermes-user / web-researcher` distinct from `hermes-user / hermes`.

## Phase 2 — Specialists (definitions bound to Skills) + delegation threading (~2-3 days)

**2a. Author the first specialists** as `SKILL.md` in `~/.hermes/skills/specialists/<name>/`:
- frontmatter `name`, `description` (the *when-to-use* text used for matching), `metadata.hermes.{agent_role:true, mem0_agent_id:<name>, requires_toolsets:[web,terminal], related_skills:[...]}`, optional top-level `allowed-tools:`;
- body = the tight system prompt + **standing rules** ("always ≥3 independent sources", "prefer primary sources"). *(Validator allows arbitrary frontmatter — `skill_manager_tool.py:508`.)*

**2b. Split the memory gate + add the child params:**

| Target | Change |
|---|---|
| `agent/agent_init.py:1260` (Block B) | Guard `if (not skip_memory) or provider_memory:` (Block A / MEMORY.md stays `if not skip_memory` → never loads for children). |
| `agent/agent_init.py:225-227` sig + `:1272-1316` | Add `provider_memory=False, memory_agent_id=None, memory_read_only=False`; inject `_init_kwargs['agent_id']=memory_agent_id` beside the existing `agent_context='primary'` at 1276; store `agent._memory_read_only`. |
| `run_agent.py:487` sig + `:560-562` fwd + `:3373` | Thread the 3 params; wrap `self._memory_manager.sync_all(...)` in `if not getattr(self,'_memory_read_only',False):` — **stops the append-all auto-write**. |
| `tools/delegate_tool.py:661-736` + call `:1145-1152` | `_build_child_system_prompt(..., playbook=None)`: when set, append a `## STANDING RULES` section with the specialist's definition body + `build_preloaded_skills_prompt(bound_skills)` output. (Bypasses `skip_context_files` for *this* injection only.) |
| `tools/delegate_tool.py:2499` | Replace hardcoded `toolsets=None` with the specialist's **tool allowlist** — the existing intersect+strip logic (`1119-1135`) narrows it safely. |
| `tools/delegate_tool.py:1044-1065` + construct `:1303-1334` | Add `specialist/playbook/memory_agent_id/tool_allowlist`; **keep** `skip_context_files=True` + `skip_memory=True`, **add** `provider_memory=True, memory_agent_id=<name>, memory_read_only=True`. Leave `DELEGATE_BLOCKED_TOOLS` untouched (structurally keeps mem0 write-tools off the child). |

**Verify:** delegate with a forced specialist; grep the child's built system prompt (debug dump at `delegate_tool.py:1435`) for the STANDING RULES section; assert the child's `enabled_toolsets` excludes `memory` and has no `mem0_add`; assert it can *retrieve* its two-scope memory but 2 turns write **nothing** to qdrant (read-only proof); assert MEMORY.md never loads (`child._memory_store is None`).

## Phase 3 — Get-or-create resolver + semantic matcher (~1-2 days)

| Target | Change |
|---|---|
| New `scripts/build_agents_index.py` + qdrant collection `agents_registry` | On registry change, embed each specialist `description` via `nomic-embed-text` (768d) → upsert (separate from the `mem0` collection). |
| `tools/delegate_tool.py:2488-2517` (dispatch) + new resolver | Before spawn: embed the goal, cosine top-1 vs `agents_registry`; **match** (score ≥ ~0.6 **and** top1−top2 margin ≥ 0.05) → pass specialist/playbook/tool_allowlist/`memory_agent_id`; **no match** → today's dynamic ephemeral spawn (`memory_agent_id=None`). **No auto-persist.** Log the routing decision. |
| `DELEGATE_TASK_SCHEMA` (`:3377+`) | Optional `specialist` param (top-level + per-task) to *force* a named specialist; get-or-create stays automatic otherwise. |

**Verify:** matching goal routes to the specialist (scoped `agent_id`, narrowed toolset, injected rules); off-topic goal falls below threshold → dynamic spawn with `skip_memory=True` (no leakage). Routing scores logged to Langfuse.

## Phase 4 — nexus UI: editable Skills tab + Registry tab (~2-3 days)

| Target | Change |
|---|---|
| nexus `server.py` new `GET /api/skills/{name}/source` | Proxy Hermes `GET /api/learning/node?id={name}` (or `/api/skills/content`) with `_hermes_headers()`. |
| nexus `server.py` new `POST /api/skills/{name}/save` | Body `{content,message}` → Hermes `PUT /api/skills/content` → `POST /api/git/review/stage` → `/commit` (path=`~/.hermes/skills`) → **then trigger guardian golden refresh** (Phase 6). |
| `app.js` viewSkills/bindSkills (`1166-1215`) | Turn the read-only card into an editor: `showModal` with `<textarea>` prefilled from `/source` + commit-message input + Save→`/save`. Unique function names, no `console.log`. |
| `index.html:33` nav + `app.js:181` titles + `:186` render | Add a **Registry** tab (`data-view='registry'`) — separate from the existing `agents` fleet tab. |
| `app.js` new `viewRegistry/bindRegistry` (mirror Memory tab `1325-1365`) | Per specialist card shows its **three things**: (1) definition/instructions (opens the Skills editor), (2) private memory via `GET /api/memory?agent_id=<name>` (add the filter to `server.py:370`), (3) pending **promotion proposals** via the existing nexus approvals subsystem (`/api/approvals`, `decideApproval`). |

**Verify:** edit a specialist's rules in nexus → file changes on disk, a git commit appears, reload persists; run `hermes-guardian.service` → the edit is **not** reverted (golden refreshed); the Registry tab shows the specialist's own memories only.

## Phase 5 — Governance: eval gate, promotion, pruning (~2-3 days)

| Piece | Change |
|---|---|
| **Eval gate** (install promptfoo) | Per-specialist golden set (10-30 cases, `input→assertions`) under the specialist dir. `POST /save` runs `npx promptfoo eval` (provider = GLM via `GLM_API_KEY`, or Ollama; **judge = Claude, never GLM-judges-GLM**); nonzero exit **blocks the commit** and shows red in nexus. `promptfoo view` for the partner. |
| **Promotion flow** (no auto-persist) | Log every dynamic spawn (task text, fallback, ts) to a ledger. When a near-duplicate recurs N times below threshold → emit a `promote_specialist` **approval proposal** (recurrence count + sample tasks + draft def) to the Registry tab. On human approve → write the specialist `SKILL.md`, git-commit, embed into `agents_registry`. |
| **Memory pruning** (OSS has no decay) | Scheduled job (systemd timer): delete role memories by age/low-use and cross-scope duplicates from qdrant; provenance tag (`source`, `ts`) on writes. |

**Verify:** a seeded failing assertion blocks a save; replay a task type N× → proposal appears → approve → next identical task **reuses** the new specialist; prune job removes an aged low-use memory.

## Phase 6 — Persistence & guardian (~½ day, do alongside)

Enroll everything so an update/venv-rebuild/reboot can't drop it:
- `manifest.json files[]` + golden copies: each specialist `SKILL.md`, the promotion ledger, `build_agents_index.py`, the pruning job unit; **config asserts** `mem0.json mode=oss`, `memory.provider=mem0`.
- `manifest.json packages[]`: pin `promptfoo` (npm) alongside the existing `mem0ai==2.0.10`, `qdrant-client`, `ollama`, `langfuse`.
- Add `agents_registry` qdrant collection existence to the guardian's container/readiness checks (recreate-if-missing).
- **Critical:** the nexus save flow calls `guardian.py --capture` (or a scoped golden refresh) after each commit so pinned specialist files aren't reverted.
- New systemd `--user` units (indexer refresh, pruning) get `linger`-safe enable, mirroring `hermes-guardian.timer`.

---

## End-to-end walkthrough (proof the workflow actually works)

> You: *"research how to implement a payment system in a web shop."*
1. Hermes' resolver embeds the goal, matches `web-researcher` in `agents_registry` (score ≥ 0.6) → **reuse**.
2. It spawns a child with the web-researcher's **definition body as standing rules** ("≥3 sources, prefer primary, always check the official spec") + bound Skills, a **web-only tool allowlist**, and `memory_agent_id='web-researcher'`, `memory_read_only=True`.
3. The child **retrieves two-scope memory**: its own past lessons ("on PSD2, Wikipedia was stale; EU Commission page current") *and* the shared base (your focus/values) — but writes nothing automatically.
4. It runs the search→reason→re-search loop under its rules, returns a distilled result.
5. A **curated lesson** (if any) is written under `agent_id='web-researcher'` via `infer=True` (deduped) — not an append-all log.
6. In nexus: the **Registry** tab shows web-researcher's definition (editable, git-versioned) and its private memories; the **Skills** tab edits any procedure. You tell it *"always verify with 3 sources"* → that edits the **definition** (one commit, eval-gated), applied on every future run.
7. A novel task (*"structure an Instagram carousel"* with no matching specialist) → **dynamic ephemeral spawn** (today's behavior); if it recurs, nexus proposes promoting it — you approve, and it becomes reusable.

---

## Risk register (top items)
- **mem0 must stay OSS mode** — platform mode inverts the scoping and breaks two-scope reads. Guardian-pinned.
- **Local model ceiling** — extraction (`llama3.1:8b`) and embeddings (`nomic-embed-text`) bound memory precision and match accuracy; a swap forces a re-embed (guardian tracks the 768-dim/model).
- **Matcher mis-route** — stale/overlapping descriptions cause wrong reuse; mitigate with threshold+margin, tight non-overlapping descriptions, human-visible routing logs, and a small specialist cap (~6-10).
- **Guardian revert** — any UI edit to a pinned file without golden refresh is undone within 15 min (handled in Phase 4/6).
- **Unbounded memory** — no OSS decay; the pruning job is mandatory, not optional.
- **Concurrency** — nexus reads qdrant while Hermes writes it (already server-mode); nexus-side memory deletes must not race Hermes' `sync_turn`.

## Effort & sequencing
Phase 1 (memory scoping) is the highest value and is shippable alone — you'd *see* per-agent memory immediately. Recommended order: **0 → 1 → 2 → 4(Skills-edit slice) → 3 → 4(Registry) → 5 → 6**, landing usable capability after each. Rough total: ~1.5–2 focused weeks; the risky/novel bits are the mem0 two-scope read (Phase 1) and the delegation threading (Phase 2) — both have concrete verification gates above.
```
