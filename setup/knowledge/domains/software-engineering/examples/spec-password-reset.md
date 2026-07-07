> TEMPLATE EXEMPLAR — illustrative names/numbers; adapt via BUSINESS-CONTEXT.md

# SPEC: Password reset via email

Owner: {{FILL: requester}} · Estimate: 2 dev-days · Status: approved
Escalation: touches auth + tokens → final diff goes through `creview` before merge (PLAYBOOK: frontier review).

## Context & goal

Users who forget their password currently email support; support manually sets a temporary password. Slow, insecure, and it doesn't scale past a handful a week.

Goal: a logged-out user can reset their own password via an emailed single-use link, so that support stops handling credentials entirely.

Actors: logged-out user (legitimate), attacker probing which emails have accounts, corporate mail scanners that prefetch links in inbound email.
Money-path impact: unblocks login → everything downstream of login; no billing code touched.
Stack assumed here: Node/TypeScript API + Postgres + transactional mailer + server-rendered auth pages ({{FILL: your actual stack per BUSINESS-CONTEXT.md}}).

Flow at a glance:
1. Request: user submits email → API answers 202 immediately → background job finds account, mints token, sends link.
2. Complete: user clicks link → GET renders form (token untouched) → POST validates token + new password → password updated, token burned, all sessions revoked, confirmation email sent → redirect to login.

## Requirements

Request phase
- R1. `POST /auth/password-reset/request` accepts JSON `{"email": string}`. Response is `202 {"ok": true}` for BOTH existing and non-existing emails — identical body, identical status.
- R2. Account lookup, token creation, and email dispatch run AFTER the response is sent (background job), so response timing does not reveal whether the account exists.
- R3. For an existing, active account: a reset email is enqueued within 5 seconds containing the link `{APP_URL}/reset-password?token=<raw-token>`. Deleted or suspended accounts get no email (response still 202).
- R4. Rate limits, enforced BEFORE account lookup:
  - a. max 3 requests per email address per hour;
  - b. max 10 requests per IP per hour;
  - c. excess → `429` with `Retry-After` header (seconds), identical body whether or not the email has an account.
- R5. Issuing a new token invalidates all previously issued unused tokens for that user — only the newest link works.

Token
- R6. Token: 32 bytes from a CSPRNG, URL-safe base64 (43 chars).
  - a. Only its SHA-256 hash is stored.
  - b. The raw token appears in the email link only — never in the database, application logs, or analytics events.
- R7. Token expires 30 minutes after creation (`expires_at` stored; checked server-side at completion).
- R8. Token is single-use: successful completion sets `used_at`; any reuse fails per R12.

Complete phase
- R9. `GET /reset-password?token=…` renders the new-password form WITHOUT consuming or validating the token. All validation happens on POST only.
- R10. `POST /auth/password-reset/complete` accepts `{"token": string, "password": string}`, protected by the app's standard CSRF mechanism (auth pages are session-cookie based).
- R11. On success, in one transaction where the store allows:
  - a. response `200`;
  - b. password stored with argon2id ({{FILL: or bcrypt cost ≥12 — match the existing login path}});
  - c. token marked used (`used_at = now()`);
  - d. ALL of the user's sessions and refresh tokens revoked;
  - e. confirmation email sent ("Your password was changed. Wasn't you? …" — copy per `STYLE-VOICE.md`).
- R12. Invalid, expired, or already-used token → `400 {"error": "invalid_or_expired"}` — one generic body for all three cases, no distinction in status, body, or message.
- R13. Password policy, enforced server-side: 10–128 characters, no other composition rules, whitespace preserved (not trimmed). Violation → `422` with a field-level message per `STYLE-VOICE.md`. ({{FILL: your policy from BUSINESS-CONTEXT.md, e.g. add a breach-list check}})
- R14. Completing the reset does NOT create a session. Redirect to `/login` with a success flash; the user logs in with the new password.

Cross-cutting
- R15. Audit log rows (existing `audit_log` mechanism) for:
  - a. `password_reset.requested` (only when the account exists);
  - b. `password_reset.completed`;
  - c. `password_reset.failed_attempt` (invalid/expired/used token).
  - Fields: event, user_id (nullable), ip, user_agent, created_at. Never the token or the password.
- R16. Both new endpoints sit outside auth middleware (logged-out flow) but inside the app's standard security headers and rate-limit stack.
- R17. Both email templates (reset link, change confirmation) ship text + HTML parts and render with the existing mailer layout.

## Files / interfaces

- `migrations/NNN_create_password_reset_tokens.sql` (down-migration drops the table):

```sql
create table password_reset_tokens (
  id          bigint generated always as identity primary key,
  user_id     bigint not null references users(id) on delete cascade,
  token_hash  text not null unique,          -- sha256 hex; never the raw token
  expires_at  timestamptz not null,
  used_at     timestamptz,
  request_ip  inet,
  created_at  timestamptz not null default now()
);
create index prt_user_id_idx on password_reset_tokens (user_id);
```

- `src/auth/password-reset/routes.ts` — endpoints for R1, R9, R10.
- `src/auth/password-reset/service.ts` — `requestReset(email, ip)`, `completeReset(rawToken, newPassword, ip)`.
- `src/auth/password-reset/tokens.ts` — `generateToken()`, `hashToken(raw)`; pure functions, unit-tested.
- `src/mailers/templates/password-reset.{html,txt}`, `password-changed.{html,txt}`.
- `src/middleware/rate-limit.ts` — add the two buckets from R4.
- `tests/integration/password-reset.test.ts` — tests named `r1_…` through `r17_…`.
- Touched interfaces: session store (`revokeAllForUser(userId)` — already exists), mailer queue, audit log. No public API contract changes.

## Out of scope

- Password change while logged in (different flow, different threat model — separate spec).
- Admin-initiated resets; SMS or any non-email channel.
- MFA/SSO interaction — the product has neither today. If BUSINESS-CONTEXT.md says otherwise, STOP: this spec must be re-reviewed (SSO users shouldn't hold passwords; MFA must survive a reset).
- Account lockout policy changes.
- Login/auth page redesign — reuse the existing auth layout.
- Email deliverability / bounce monitoring.

## Verification

Local stack running; mail captured by Mailpit ({{FILL: your local mail-capture tool + port}}). `$API` = local API base, `$APP` = local app base, `$DB` = local database URL.

1. `npm test -- password-reset`
   → all pass; test names cover r1..r17 (RUBRIC G3: zero orphan requirements).
2. `curl -s -o /dev/null -w "%{http_code}\n" -X POST $API/auth/password-reset/request -H 'content-type: application/json' -d '{"email":"user1@test.local"}'`
   → `202`. Repeat with `{"email":"nobody@test.local"}` → `202`, byte-identical body.
3. Run step 2 four times for the same email within an hour
   → 4th response `429` with a `Retry-After` header.
4. `curl -s localhost:8025/api/v1/messages | jq '.messages[0]'`
   → reset email present for user1; extract the raw `token` from the link.
5. `psql $DB -c "select token_hash, used_at from password_reset_tokens order by created_at desc limit 1;"`
   → 64-char hex hash, NOT equal to the raw token from step 4; `used_at` is null.
6. `grep -r "<raw token from step 4>" logs/`
   → zero hits (R6b).
7. `curl -s -o /dev/null -w "%{http_code}\n" "$APP/reset-password?token=<raw>"`, then re-run step 5
   → `200`, and `used_at` STILL null (R9 — the GET consumed nothing).
8. POST `/auth/password-reset/complete` with the token and password `"correct horse battery st"`
   → `200`; sessions row count for user1 = 0; confirmation email visible in Mailpit.
9. POST the same token again
   → `400 {"error":"invalid_or_expired"}` (R8/R12). Confirm the SAME response for a made-up token, and for an expired one (set `expires_at` into the past via psql first).
10. POST with password `"short"`
    → `422` with a field message (R13).
11. Request a reset twice in a row for user2; try the FIRST email's link
    → `400 invalid_or_expired`; the second link works (R5 — only the newest token lives).
12. `psql $DB -c "select event from audit_log order by created_at desc limit 3;"`
    → the `password_reset.*` events from R15.

## Why this works

- **Every requirement is falsifiable and numbered.** Tests bind to R-numbers (RUBRIC G3), the adversarial verifier checks each mechanically, and review disputes become "R12 says X" instead of taste. This is PLAYBOOK scoping step 4 in action.
- **R1 + R2 kill account enumeration twice.** Identical responses close the response-body oracle; doing the work after responding closes the timing oracle. Naming "background job" is not implementation meddling here — observable timing IS the behavior, the one case where mechanism belongs in a requirement.
- **R4 rate-limits before the account lookup** so the limiter itself can't become an existence oracle (limited-vs-not must not depend on whether the email is real), and it doubles as cheap DoS cover for an unauthenticated endpoint.
- **R6 hash-at-rest** means a leaked database or backup contains no usable reset links — the same reasoning as password hashing (PLAYBOOK 8.11). One line in the spec neutralizes a whole breach class.
- **R9 (validate on POST, never on GET) is the hard-won one.** Corporate mail scanners and link-preview bots prefetch GET links; a flow that burns tokens on GET fails mysteriously for exactly the users behind corporate email. You cannot discover this edge on your own laptop — it has to be encoded in the spec.
- **R5 + R8 bound the attack window** when a user mashes "resend": at most one live token, dead after one use.
- **R11d revokes all sessions** because a reset implies suspected compromise — leaving existing sessions alive would defeat the flow's purpose.
- **R14 (no auto-login)** keeps the emailed link's privilege minimal and stays correct if MFA arrives later. One sentence now avoids a re-architecture later.
- **R12's single generic error** refuses to be an oracle: distinct "expired"/"invalid"/"used" messages each leak state to an attacker holding candidate tokens.
- **Out of scope names the adjacent flows** a builder would drift into ("while I'm in auth…"), enforcing PLAYBOOK principle 1 — and it contains a tripwire (the MFA/SSO stop condition) instead of a silent assumption.
- **Verification is commands with expected output, not prose** — "done" becomes binary (RUBRIC G4). Steps 5–7 deliberately check the non-obvious invariants (hash at rest, GET doesn't burn, token absent from logs) that a happy-path manual test would never touch.

## Adapt this

- {{FILL: route paths, file layout, framework idioms from your repo}} — change freely; keep the R-numbered behaviors identical.
- {{FILL: password policy from BUSINESS-CONTEXT.md}} — R13's 10–128 is a sane default; add a breach-list check if the threat model warrants it.
- {{FILL: hashing algorithm}} — match the existing login path exactly; never run two schemes without a migration plan.
- {{FILL: session revocation call}} — how "revoke all for user" works in your session store. If it can't be done, that's a prerequisite ticket — not a reason to drop R11d.
- {{FILL: CSRF mechanism}} — R10 assumes cookie-session forms; a pure token-auth SPA replaces CSRF with its standard header scheme.
- {{FILL: mailer + local capture tool}} — swap the Mailpit URL/API in verification steps 4 and 8.
- {{FILL: rate-limit backend and standard buckets}} — R4's numbers (3/hr/email, 10/hr/IP) are sane defaults; tighten for high-value targets.
- {{FILL: audit log destination}} — table, service, or log stream; keep the three events and the never-log-the-token rule regardless.
- {{FILL: test runner + naming convention}} — whatever makes RUBRIC G3's grep-for-R# check work in your repo.
- Token TTL 30 min and 32-byte size reflect current good practice — verify current numbers against OWASP guidance when reusing this spec later.
