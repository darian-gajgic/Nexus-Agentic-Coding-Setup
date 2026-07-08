# SPEC — Settings v2: full UI configurability, encrypted credentials, per-user models

Status: implementing (2026-07-08). Owner: Claude session w/ operator brief.
Origin: operator request — "everything configurable in the Settings tab; credentials
encrypted + never shown; per-user API keys defaulting to current ones; Opus 4.8
(frontier judge) missing; per-user models from different companies with purpose
assignment that is actually applied; current defaults stay default."

## 0. Current state (mapped 2026-07-08)

Two disjoint "model worlds":

1. **Worker world** — every task/JARVIS/wizard/eval generation runs a GLM model in a
   Hermes session (`POST /api/sessions {"model": ...}`, provider fixed `zai` in
   `~/.hermes/config.yaml`). Model lists are hardcoded twice:
   `KNOWN_MODELS` (app.js:1909) and `_TASK_MODELS` (server.py:3048) = 3 GLM models.
   Key = `GLM_API_KEY` in `~/.hermes/.env` (single, global, plaintext 0600).
2. **Frontier-judge world** — `judge.cmd` setting (default `cjudge {file} {domain}`)
   → `~/.local/bin/cjudge` → clean-env `claude -p` → the Claude CLI's saved default
   (Opus 4.8, subscription auth). No model string in the app at all; invisible to
   every dropdown. This is the "missing Opus 4.8".

Settings: key/value `settings` table; `/api/settings` gated to prefixes
`("dispatch.", "judge.", "model.")`, PATCH admin-only. Many live keys have no UI
(`judge.cmd`, `pr.cmd`, `onboarding.root`, `evals.corpus_root`, `watchdog.*`,
`auth.force`) and several config values are env-only (`HERMES_API_BASE`,
`NEXUS_COST_PER_1M_TOKENS`, Langfuse, `MEM0_QDRANT_URL`). No at-rest encryption
exists anywhere (auth.py = scrypt password hashes + sha256 session tokens only).

## 1. Goals (operator requirements → design)

| # | Requirement | Design answer |
|---|---|---|
| R1 | Every needed setting configurable via Settings tab | Declarative settings registry + generic UI renderer (§2) |
| R2 | External services + credentials configurable; encrypted, never displayed | `secrets_store.py` (Fernet, key file 0600) + `credentials` table + masked write-only UI (§3) |
| R3 | Per-user API keys, fallback to current global keys | Per-user credential rows; resolution chain user-cred → global env key (no key duplication) (§3,§6) |
| R4 | Opus 4.8 / frontier judge missing | Judge becomes a first-class purpose with a model registry entry `anthropic/claude-opus-4-8` seeded as global default (§4,§5) |
| R5 | Per-user models from any company, with purpose properties, actually applied | `user_models` + `model_assignments` tables; purposes: complicated / easy / mechanical / frontier_judge; routing reads assignments end-to-end (§4,§6) |
| R6 | Current defaults stay default | Seeded global rows = today's behavior exactly; no seeded credentials (env keys keep working) (§5) |

## 2. Settings registry (R1)

New module `settings_registry.py`: a declarative list of every exposed setting —
`key, section, label, help, type (bool|int|float|str|enum|command|path), default,
admin_only, restart_required`. Defaults = the values in use today (database.py
seeds + code fallbacks).

- `GET /api/settings/schema` → `{sections: [...], values: {...}, is_admin}` so the
  UI renders every setting generically. Values merged from settings table with
  registry defaults; env-backed settings (below) show `setting → env → default`
  provenance.
- `_SETTINGS_PREFIXES` grows to cover the registry namespaces:
  `dispatch. judge. model. pr. onboarding. evals. auth. watchdog. hermes. cost.
  langfuse. qdrant.`
- Env-only values become settings with env fallback (`get_setting(k) or env or
  default`) read lazily at use sites: `hermes.api_base`, `cost.per_1m_tokens`,
  `langfuse.base_url`, `qdrant.url`. Langfuse keys move to the credential store.
- Watchdog keys render in the same UI (existing `/api/watchdog/config` endpoint
  kept for gate compat).
- Existing seeded-but-dead keys `theme`/`poll_interval` stay ignored.

## 3. Encrypted credential store (R2, R3)

New module `secrets_store.py` — first at-rest crypto in the codebase:

- Master key: `app/secret.key`, 32 random bytes urlsafe-b64 (Fernet key), created
  on first use, `chmod 0600`, **gitignored** (runtime data, like cert.key).
- Cipher: `cryptography.fernet.Fernet` (new dep in requirements.txt).
- Table `credentials(id PK, user_id NULL=global, provider, label, enc_value,
  hint, created_at, updated_at, created_by)`. `hint` = last 4 chars only.
- API (self-scoped — members manage their OWN rows; admin additionally manages
  global rows):
  - `GET /api/credentials` → metadata + hint only. **No endpoint ever returns a
    stored secret.**
  - `POST /api/credentials {provider, value, label, global?}` → create/rotate.
  - `DELETE /api/credentials/{id}`.
- UI: password-type write-only inputs; saved keys display as `provider ••••abcd`
  with Rotate/Remove. "Leave unset to use the system default key."
- **No migration of existing keys into the DB**: the current `~/.hermes/.env` /
  Claude-CLI auth remain the global defaults by absence (R3/R6). The store only
  holds keys users explicitly add.
- Posture change: docs currently say "API keys only in env, not DB"
  (PROJECT-DOCUMENTATION.md) — updated to "user-added keys encrypted in DB;
  system defaults stay in env". Added to the pending security-review scope.

## 4. Per-user model registry (R4, R5)

Tables:

```
user_models(id PK, user_id NULL=global, provider, model_id, label,
            route 'hermes'|'cli', credential_id NULL, enabled 1,
            config JSON '{}', created_at, updated_at)
model_assignments(user_id, purpose, model_row_id, PK(user_id,purpose))
  -- user_id 'global' = admin-managed default row
```

Purposes (exactly the roles the code actually routes on):

| purpose | today | applied at |
|---|---|---|
| `complicated` | glm-5.2 (default + dev-stage floor) | task default, wizard tier text, dev floor, JARVIS/wizard sessions |
| `easy` | glm-5.1 | wizard light-task choice |
| `mechanical` | glm-4.5-air | wizard formatting/extraction choice |
| `frontier_judge` | Opus 4.8 via cjudge (invisible) | task judge + eval scoring |

Routes:
- `hermes` — model runs as a Hermes session (provider must be Hermes-routable;
  setting `hermes.providers`, default `zai`). Worker purposes require this route.
- `cli` — model runs through a command template (judge path). `frontier_judge`
  requires this route. This is how cross-company (Anthropic) models are usable
  today; more providers become worker-routable when Hermes gains them (validation
  message says exactly that instead of silently accepting).

API (self-scoped like credentials): `GET /api/models` (global + own, with
assignments), `POST /api/models`, `PATCH/DELETE /api/models/{id}`,
`PUT /api/models/assignments {purpose: model_row_id, global?}`.
Members see/edit their own; admin manages global rows. Foreign rows ≡ 404
(matches `_owned_task` doctrine).

## 5. Seeded defaults (R4, R6) — behavior-identical to today

Global rows (migration, idempotent):
- `zai/glm-5.2` route=hermes → assigned `complicated`
- `zai/glm-5.1` route=hermes → assigned `easy`
- `zai/glm-4.5-air` route=hermes → assigned `mechanical`
- `anthropic/claude-opus-4-8` label "Claude Opus 4.8 (frontier judge)" route=cli
  → assigned `frontier_judge`
No credential rows seeded. `judge.cmd` default unchanged.

## 6. Routing application (R5 — "settings actually used")

- `server.py _TASK_MODELS` → `db.task_models_for(user_id)` (enabled, hermes-route,
  global+own). Wizard model-guidance text built from the registry (label+purpose).
- Dev-stage floor (server.py ~3247) → owner's `complicated` model instead of
  hardcoded glm-5.2.
- `hermes_dispatch`: `resolve_task_model(task)` = task.model (validated against
  owner registry) else owner `complicated` assignment; passed explicitly to
  `create_session`. JARVIS + wizard sessions also pass the caller's `complicated`
  model (same value as today for unconfigured users).
- Per-user Z.AI-side keys: **session-keys bridge**, mirroring the existing
  `model-efforts.json` precedent — Nexus resolves the owner's provider credential
  at dispatch and writes `~/.hermes/session-keys.json` (0600)
  `{"sessions": {sid: {"provider": p, "api_key": k}}}`; the Hermes zai provider
  (guardian-managed patch) checks it per request, falls back to env
  `GLM_API_KEY`. Entries removed at finalize + pruned at boot. Plaintext-0600
  posture = same as `~/.hermes/.env` itself; documented for security review.
- Judge: `_judge_model_for(owner)` → `frontier_judge` assignment. `run_judge_cmd`
  gains model + env plumbing: `{model}` token replaced if present in `judge.cmd`
  (token-replace, not .format), and env `JUDGE_MODEL` always set; if the owner has
  an `anthropic` credential, env `JUDGE_ANTHROPIC_API_KEY` is set for the
  subprocess (in-memory only). `~/.local/bin/cjudge` updated: honors
  `JUDGE_MODEL` (`claude -p --model`), and when `JUDGE_ANTHROPIC_API_KEY` is set
  exports it as `ANTHROPIC_API_KEY` instead of unsetting (default clean-env
  subscription behavior unchanged when unset). judge_stub.sh untouched.
- Frontend: `KNOWN_MODELS` deleted; all model UI (settings table, topbar strip,
  2 task selects, wizard hints) renders from `GET /api/models`.
- tools_hub PRICE_TABLE already has claude-opus tier — no change.

## 7. Settings tab v2 layout

1. ⚙ Dispatch & budgets (extended: enabled, max_turn_seconds, resume_quiet_s)
2. 🧠 Models & routing — registry manager + purpose assignment + per-model
   concurrency/effort (hermes-route rows)
3. 🔑 Providers & credentials — masked per-user keys (+ global for admin)
4. 🧭 Business Brain (unchanged)
5. 👥 Users & access (unchanged, admin)
6. 🛠 Advanced — judge.cmd, pr.cmd, onboarding.root, evals.corpus_root,
   auth.force, hermes.api_base, cost.per_1m_tokens, langfuse.base_url, qdrant.url
   (admin; restart-required flags shown)
7. 🛡 Watchdog (moved into tab; modal + endpoint kept)

Members see 2/3/4 (self-scoped) + password panel; admin sections gated by the
schema endpoint's `is_admin` (capability probing preserved).

## 8. Hermes-side changes (ship-flow step 4)

1. zai provider patch: read session-keys bridge (mtime-cached, like
   model-efforts). Guardian golden + manifest sha update; vendor into `setup/`.
2. `~/.local/bin/cjudge` update (JUDGE_MODEL / JUDGE_ANTHROPIC_API_KEY) + vendor
   wherever it's packaged in `setup/`.

## 9. Gates

- verify.sh: new section — endpoint greps (`/api/settings/schema`,
  `/api/credentials`, `/api/models`), table greps (`credentials`, `user_models`,
  `model_assignments`), `secret.key` gitignore check, `KNOWN_MODELS` absence,
  registry module presence; keep `m-task-model`, onboarding entry string, no
  literal `three` in index.html; bump ?v= floors (app.js ≥54, style.css ≥15).
- `scripts/verify_settings_e2e.py` (self-cleaning, `_gate_auth`, multi-user-
  preserving): schema endpoint; member 403 on admin writes; credential set →
  masked read-back → never plaintext in any GET; model CRUD + assignment +
  per-user invisibility; judge model resolution via stubbed judge.cmd echoing
  JUDGE_MODEL; defaults seeded (opus row + 4 assignments); bridge file write on
  dispatch stub; restore all touched settings.
- `scripts/verify_settings_ui.py` (Playwright): sections render, masked input,
  add-model flow, member view.
- Docs updated: PROJECT-DOCUMENTATION (key posture, settings list), CLAUDE.md
  gate counts, security-review scope additions (secrets store, bridge file,
  judge env passing, new admin surfaces).
