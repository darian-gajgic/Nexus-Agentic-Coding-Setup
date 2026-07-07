# SPEC — Block 1: Multi-user + service deployment (2026-07-07)

Household multi-tenancy on ONE shared Nexus instance. Each user logs in and
gets their own personal system: own task board, workflows, project focus,
known issues, deliverables, JARVIS conversation, and mem0 memory scope.
Execution infra (agent lanes, watchdog, scheduler, settings, specialists)
stays shared. Single-user mode without login stays the default.

## 1. Identity model

- `users` table: `id` ('u_'+hex), `username` (unique, lowercase), `display_name`,
  `password_hash` (scrypt, empty = not set), `role` ('admin'|'member'),
  `active` (1|0), `created_at`.
- Migration seeds ONE default user `u_owner` (username `owner`, role admin,
  no password) and backfills every existing row to it — so ALL queries are
  ALWAYS user-scoped; there is no unscoped code path to leak through.
- `auth_sessions` table: `token_hash` (sha256 of the cookie token — DB theft
  doesn't yield sessions), `user_id`, `created_at`, `expires_at`, `last_seen`,
  `ua`. Cookie `nexus_session`: HttpOnly, SameSite=Lax, Secure (on HTTPS),
  30-day sliding expiry.

## 2. When is login required? (single-user default preserved)

`auth_required()` = (count of active users ≥ 2) OR setting `auth.force=1`.
- 0/1 users → NO login. Every request auto-resolves to the sole active user.
  The operator's machine keeps working unchanged.
- Adding user #2 flips login on for everyone. The API refuses to create a
  second user until the acting user has a password set (no lockout window).
- Emergency hatch (local machine access only): `scripts/auth_reset.py`
  clears passwords / deletes extra users directly in sqlite.

## 3. Enforcement (server-side, single chokepoint)

- Pure-ASGI middleware (not BaseHTTPMiddleware — keeps SSE streaming intact)
  resolves the cookie → user, stores it in a contextvar + `scope["state"]`.
  Public paths: `/`, `/static/*`, `/api/auth/login`, `/api/auth/state`.
  Everything else under `/api/*` → 401 JSON when unauthenticated.
- Origin check on state-changing methods (CSRF belt-and-braces on top of
  SameSite=Lax + JSON-only bodies).
- Login rate-limit: 5 failures / 15 min per username+IP; constant-time
  compares; generic error (no username enumeration).
- `/ws` authenticates the cookie at handshake; each socket is tagged with
  its user; user-scoped events broadcast ONLY to the owner's sockets.

## 4. Data scoping

- `user_id` column (additive) on: `tasks`, `workflows`, `known_issues`,
  `activity` (nullable = system-wide row, visible to all).
- Scoped per user: task list/CRUD + every by-id subresource (transcript,
  files, attachments, app preview, judge, feedback, retry, review, promote,
  claim/release, dispatch), workflows + attachments + review, deliverables,
  known-issues, activity feed (own + system rows), dispatches, stats' task
  counts, WS task/workflow events. Cross-user access → 404 (no existence
  disclosure).
- Shared (by design, household trust): agents fleet, monitor, scheduler,
  approvals, watchdog, verify runs, specialists/lessons/skills, shared-context
  (team memory), settings (writes admin-only), guardian, usage, tools,
  programs. User management admin-only.
- New rows are stamped with the creating user; engine-created rows (loop
  retries, wizard-accepted plans) inherit from their source row.
- **Projects (gap fix 2026-07-07):** the Projects view scans the shared
  filesystem, so visibility comes from the `project_owners` table
  (path → user_id). A path WITHOUT a row belongs to `u_owner` (the home
  directory is the operator's); Nexus writes a row for every project it
  creates (`_create_repo`: create-client + task promote). Enforced at
  `GET /api/projects` (list + all repo dropdowns feed from it) and at every
  path-accepting endpoint: projects history/publish/push/tag, task
  create/patch `repo_path`, wizard `repo_path` (foreign = silently dropped,
  like invalid), workflow create/patch `project_path`, agent worktree.
  Foreign paths answer exactly like nonexistent ones. Frontend: the legacy
  un-namespaced focus key migrates only to `u_owner`, and a focus pointing
  at a project the user can no longer see is pruned when the projects list
  arrives.

## 5. Per-user JARVIS

`jarvis_session.json` becomes `{"sessions": {user_id: hermes_session_id}}`
(legacy `session_id` key migrates to `u_owner`). Every JARVIS endpoint
resolves the CURRENT user's session; `/api/jarvis/messages/{sid}` only serves
a session the caller owns; the Hermes-sessions browser is admin-only.
Session titles: `JARVIS — <display_name>`.

## 6. Per-user mem0 memory scope (generalizes M3 client isolation)

Same bridge-file mechanism as client scoping, one level up:
- `~/.hermes/client-scopes.json` gains a `"users"` map: `{session_id: user_id}`.
  Nexus publishes it when dispatching a task (owner) and when creating/using
  a JARVIS session.
- The `mem0-client` provider stamps `metadata.user` on writes from user-tagged
  sessions and post-filters EVERY read path: a row tagged with another user is
  invisible. Untagged rows = shared/global (operator's existing memories and
  team-shared scope keep working). Client filtering is unchanged and composes.
- Guardian golden + manifest sha updated for the plugin edit.
- `/api/memory` and `/api/memory3d` apply the same rule server-side
  (memory3d cache keyed per user).
- **Legacy backfill (gap fix 2026-07-07):** the pre-Block-1 backlog (358
  untagged points — all the operator's) was handed to `u_owner` by
  `scripts/migrate_mem0_user_backfill.py` (one-time, idempotent, undo log in
  `logs/`), mirroring the tasks/workflows backfill — so a new user's memory
  views start EMPTY. Companion: the migration writes a top-level
  `"default_user": "u_owner"` into the scopes file and the provider falls
  back to it for sessions with no `users` entry — the operator's local
  Hermes CLI keeps its memories. Nexus publishes a user scope for EVERY
  session it creates (dispatch, JARVIS, and the task/skill/specialist
  wizards), so the fallback can never apply to another user's requests.
  Memories added outside a session (shared-context, curator lessons) remain
  untagged = deliberately global.

## 7. Service exposure — Tailscale ONLY (never public)

- Server keeps binding 127.0.0.1:8777 (self-signed HTTPS unchanged).
- `tailscale serve` publishes it tailnet-only at
  `https://<machine>.<tailnet>.ts.net` with a real Tailscale cert
  (WS + mic work; no funnel, no port-forward, no public exposure — the
  system executes shell commands).
- `scripts/setup_tailscale.sh` (idempotent) + docs/TAILSCALE.md steps for
  the phone and the second laptop.

## 8. Mobile layout pass

≤900px: off-canvas sidebar + hamburger (nav structure untouched — gate
contracts), compact topbar, full-width modals/drawer, kanban horizontal
swipe, larger touch targets. Verified with Playwright at 390×844.

## 9. Proof (E2E, like the client-isolation probe)

`scripts/verify_multiuser_e2e.py` (leaves the system single-user again):
A) HTTP isolation: two probe users; cross-user list/by-id/files/WS/
   deliverables/activity/JARVIS-history assertions.
B) mem0 isolation proven live vs qdrant: user-tagged session A stores a
   distinctive fact → qdrant point carries `metadata.user=A`; retrieval in
   user B's session filters it out; B's search returns 0 user-A rows.
Static gate: verify.sh grows auth checks. Existing suites must stay green.
