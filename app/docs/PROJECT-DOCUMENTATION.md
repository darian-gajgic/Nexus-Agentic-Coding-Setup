# Nexus Agent OS + Hermes — Project Documentation

*Complete reference, 2026-07-07. The in-app **User Manual** tab carries the
plain-language version; this document is the engineering deep-dive.*

## 1. What the project is

A self-hosted AI-agent operating system for a two-person business. The
operator describes work in natural language; the system plans it, executes it
with specialized AI agents, quality-gates the results, and delivers files,
documents, and code. Everything runs on the operator's machine; the only
external calls are to the LLM provider (Z.AI GLM) and, optionally, Anthropic
Claude as a quality judge.

Two cooperating systems (deliberately separate processes):

| System | Role | Tech | Port |
|---|---|---|---|
| **Nexus Agent OS** | Control plane: UI, kanban, dispatch queue, budgets, loops, judge, gates | FastAPI + SQLite + vanilla JS (no build step) | 8777 (HTTPS) |
| **Hermes Agent** | Execution engine: sessions, tools, specialists, skills, memory | Python agent runtime + gateway (pinned v0.18.0 @ 048270fa) | 8642 |

Supporting services: **qdrant** (vector store, Docker) + **ollama**
(embeddings + local LLM for mem0 memory extraction), **hermes-guardian**
(integrity: verifies/repairs every customization by SHA-256 manifest +
git patches), optional **Langfuse** (LLM observability).

## 2. Architecture

```
┌─────────────────────────────  YOUR MACHINE  ─────────────────────────────┐
│                                                                          │
│  Browser ── HTTPS ──▶ NEXUS server.py (FastAPI, 8777)                    │
│                         │   ├── nexus.db (SQLite WAL: tasks, agents,     │
│                         │   │   workflows, dispatches, settings, …)      │
│                         │   ├── workspaces/<task-id>/ (deliverables)     │
│                         │   └── background threads: watchdog, scheduler, │
│                         │       loop engine, app-runner reaper           │
│                         │                                                │
│      agent lanes: worker.py subprocesses (one per agent row)             │
│                         │  claims task (SQLite CAS) → dispatch           │
│                         ▼                                                │
│  hermes_dispatch.py ── HTTP+SSE ──▶ HERMES gateway (8642)                │
│      create session → stream turn → harvest results                     │
│                         │                                                │
│                         ├──▶ Z.AI GLM-5.2/5.1/4.5-air (LLM calls)        │
│                         ├──▶ tools: terminal, files, browser (playwright │
│                         │    MCP), serena (LSP), context7 (docs)         │
│                         ├──▶ mem0 ──▶ ollama (embed) + qdrant (vectors)  │
│                         └──▶ specialists (~/.hermes/agents/*.md)         │
│                                                                          │
│  hermes-guardian (systemd timer): manifest-verify + patch-repair         │
└──────────────────────────────────────────────────────────────────────────┘
```

**Why the split matters:** Nexus restarts never kill running AI work. A
Hermes session survives its client; the respawned lane *harvests* the
orphaned-but-finished run from session history (verified repeatedly in
production use — zero token waste).

## 3. The execution pipeline

### 3.1 Task lifecycle (dispatch_state, orthogonal to kanban columns)
`none → queued → dispatching → streaming → finalizing → completed |
failed | blocked_budget | blocked_quota`

- **Queue-only dispatch**: `POST /api/tasks/{id}/dispatch` claims + marks
  `queued`; the worker lane is the SOLE executor. Claiming is an atomic
  SQLite compare-and-swap — double-claims are impossible.
- Each task runs as ONE fresh Hermes session (`nexus:<task-id>`) with an
  ephemeral system framing carrying: workspace path, attachments (MUST-READ),
  dependency deliverables as inputs, repo-mode contract (see 3.3), doc-tools
  interpreter, and the structured-facts skill pointer.
- Real token usage comes from the SSE `run.completed` event; budgets count
  input+output per turn (agentic sessions resend context per tool call).

### 3.2 Quality machinery
- **Wizard v3** (`POST /api/tasks/wizard`): two-phase planning. May ask ONE
  round of ≤6 questions (each option with pros/cons + ★ recommended pick +
  default). Coding goals get the enforced house pipeline: spec → implement →
  review → fix → verify; `_repair_workflow()` deterministically inserts
  missing gates, whitelists specialists, and keeps the DAG acyclic.
- **Loops v3.2** (`loop_engine.py`): deterministic designer + 20s runtime
  sweep. Closed mode: verify-FAIL → retry fix with findings → re-verify;
  judge REVISE → auto-retry. Bounded: per-trigger round caps, ≤3 actions per
  sweep. Projects inherit loops to member tasks with per-task counters.
- **Frontier judge**: high-stakes deliverables graded by Claude against the
  domain rubric (verdict/findings/score) via the cjudge bridge.
- **Verify gates (dev)**: `scripts/verify.sh` (static, pre-commit enforced,
  self-counting) + Playwright runtime suites (agentic, v3 UI, interactions,
  JARVIS e2e, real-dispatch e2e).

### 3.3 Repo-native coding (Nexus-Agentic-Coding-Setup)
Tasks with `repo_path` run INSIDE an existing repository:
- Idempotent git worktree per pipeline, branch `nexus/<slug>`
  (`<repo>/.worktrees/`, self-ignoring). Pipeline stages share the branch;
  parallel pipelines are isolated. The operator's checkout is never touched.
- Framing switches to repo-mode: follow repo conventions (AGENTS.md excerpt
  injected — no Hermes core-mod needed), run the repo's own gates, commit on
  the branch, never push/merge.
- After the turn: snapshot-commit of uncommitted work (junk-excluded), then
  `changes.diff` (three-dot vs base, junk-excluded) captured into the
  workspace for review/UI/judge. Humans merge.
- Dev specialists carry `mcp-serena` (LSP symbol navigation) + `mcp-context7`
  (live library docs) + Big-Code rules (blast-radius first; done = repo gates
  green AND every touched symbol's usages re-searched; schema changes always
  escalate).

### 3.4 Self-healing & resilience
- **Watchdog** (10s): restarts dead/stuck lanes, enforces cost caps; dead
  agents marked `crashed`, `retired` is terminal.
- **Orphan harvest**: lane death ≠ run death; finished orphans are collected
  from session history, active ones are waited on (resume_quiet_s=600).
- **Stranded claims**: self-resurrected by the owning worker (deps-gated) or
  reassigned on operator dispatch; >1h backstop release in the watchdog.
- **Quota storms** (Z.AI 429/1305 load-shedding): exponential backoff,
  auto-retry, once-per-storm logging.

## 4. Memory system
- **mem0 two-scope** (user + agent) with per-specialist `mem0_agent_id` —
  specialists LEARN: reflection turns operator feedback into lessons queued
  for review, approved lessons bind to the specialist.
- Storage: qdrant collection `mem0` — named vectors: dense 768-dim
  (nomic-embed-text) + `bm25` sparse; payload carries text, attribution,
  channel, timestamps.
- **Memory galaxy** (`/api/memory3d`): scrolls all vectors, PCA (numpy SVD)
  → 3 principal axes, top-3 cosine links ≥0.45, k-means (full 768-D) with
  tf-idf-style distinctive-term labels. Frontend (`static/memory3d.js`):
  region-colored star field, additive glow, label callouts with leader
  lines, screen-space hover picking, search dimming, cinematic fly-in,
  signal pulses along links. Doubles as the dashboard centerpiece with
  scroll-to-expand.

## 5. JARVIS voice stack
Browser mic → `/api/jarvis/stt` (faster-whisper, CUDA) → `/chat/stream`
(SSE proxy to Hermes) → sentence-split → `/api/jarvis/talk` per sentence
(Piper TTS + Wav2Lip lip-sync, muxed MP4) → muted `<video>` (face) +
persistent `<audio>` (voice), 2-deep prefetch pipeline. Holographic stage
(`static/jarvis3d.js`) reacts to real mic/speech amplitude via WebAudio
analysers. Hardened 2026-07-07: JSON errors on all endpoints, 120s render
timeout (lock can't wedge), temp/fd leak fixes, idle-unload 300s (> chat
ceiling), teardown on view switch, barge-in, silence-VAD conversation mode.

## 6. Frontend conventions
No build step; vanilla JS. All server data through `esc()`. Views render via
`render()` switch + per-view `bind*()`. 3D modules (`nexus3d/memory3d/
jarvis3d`) lazy-import the engine from CDN — its name never appears in
index.html (gate-enforced). Cache-bust `?v=N` on every static edit.
In-place DOM patching on tick; no blind innerHTML rebuilds (input focus).
Context-aware help: `TOURS` registry + spotlight engine (`startTour`),
`?` button in the topbar; full manual in the **User Manual** view.

## 7. Operations
- **Services** (systemd user units): `nexus`, `hermes-gateway`,
  `hermes-guardian.timer`, `hermes-reflect.timer`, `hermes-prune.timer`.
- **Restart discipline**: check nothing is `queued/dispatching/streaming/
  finalizing` before restarting nexus (`systemctl --user restart nexus`);
  harvest recovers interruptions but don't provoke them.
- **Settings v2** (docs/SPEC-SETTINGS-V2.md): the Settings tab exposes the
  FULL settings registry (`settings_registry.py` — dispatch budgets/limits,
  judge/PR command templates, knowledge/eval roots, watchdog, auth.force,
  service endpoints with env fallback), a per-user **model registry** with
  purpose routing (complicated/easy/mechanical/frontier_judge — seeded to the
  historical GLM trio + Claude Opus 4.8 as judge), and per-user **encrypted
  credentials**. Per-model effort still bridges live to Hermes via
  `~/.hermes/model-efforts.json`; per-user API keys bridge per session via
  `~/.hermes/session-keys.json` (0600).
- **Backups**: config-only encrypted USB snapshot + Timeshift (system-only);
  the reproducible install lives in the **Nexus-Agentic-Coding-Setup** repo
  (full source, patches, installer, docs — secrets excluded by design).

## 7b. Multi-user (Block 1, 2026-07-07 — docs/SPEC-MULTIUSER.md)
Household multi-tenancy on one instance. Every row and query is user-scoped
(a seeded `u_owner` owns all pre-multiuser data), so there is no unscoped
code path. With 0/1 users configured there is NO login — the single-operator
machine behaves exactly as before. Adding user #2 (Settings → Users & access)
turns the login screen on for everyone; each user then gets their own task
board, workflows/projects, deliverables, known issues, activity, focus
context, JARVIS conversation, and mem0 memory scope (the M3 client-isolation
provider generalized: sessions are user-tagged via `~/.hermes/
client-scopes.json` `"users"` map; reads post-filter other users' rows).
Cookie sessions (scrypt passwords, hashed tokens, HttpOnly + SameSite=Lax,
sliding 30-day expiry, login rate-limit); WS handshakes authenticate the
cookie and task/workflow events broadcast only to the owner's sockets.
Shared by design: agents fleet, scheduler, watchdog, settings (admin-write),
specialists/lessons/skills, shared-context. Per-user since Settings v2:
model registry + purpose routing and encrypted credentials (approvals became
per-user in the Block-1 gap fix). Emergency:
`scripts/auth_reset.py` (local) returns the box to single-user.
Proof: `scripts/verify_multiuser_e2e.py` (55 checks) — HTTP/WS/JARVIS/mem0
isolation probed E2E against the live server + qdrant, self-cleaning.
Remote access: **Tailscale only, never public** — see docs/TAILSCALE.md
(`tailscale serve` on the tailnet; nexus stays loopback-bound).

## 8. Security posture
- HTTPS-only UI; localhost binding everywhere. MACHINE-default API keys live
  only in `~/.hermes/.env` (guardrail-protected, never in git; template +
  credential scanner in the setup repo). USER-added keys (Settings v2) are
  Fernet-encrypted in nexus.db (`secrets_store.py`; master key `secret.key`
  0600, gitignored) and are never returned by any endpoint — masked hints
  only. At execution they surface only as a per-session entry in
  `~/.hermes/session-keys.json` (0600 — same at-rest posture as .env) or as
  env vars into the judge subprocess. ⚠ flag for the pending security review.
- Multi-user auth + per-user data isolation (see 7b); remote access is
  tailnet-only via `tailscale serve` — never port-forwarded, never funneled.
- No command allowlist auto-approval (removed — guardian-enforced absence);
  approval gates for sensitive actions; tirith pre-exec security hook
  fail-closed.
- Guardian pins every customization (5 core-mod patches, plugins, goldens)
  by SHA-256; drift is flagged/repaired; `hermes update` is survivable.
- XSS: all interpolation escaped (JARVIS feed fixed 2026-07-07).

## 9. Repository map
- `~/nexus-agent-os` — the control plane (this app).
- `~/.hermes` — Hermes engine + customizations (agents/skills/plugins).
- `~/hermes-guardian` — integrity system (patches/goldens/manifest).
- `~/hermes-team-setup` — portable snapshot of the whole environment.
- `~/Nexus-Agentic-Coding-Setup` — **the finished-project package**: full
  Nexus source (`app/`), complete Hermes environment (`setup/`), installer,
  patches, docs. Private GitHub: `dariannixda-eng/Nexus-Agentic-Coding-Setup`.
