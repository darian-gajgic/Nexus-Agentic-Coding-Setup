# SECURITY SWEEP — standalone session plan (defensive review of our own app)

**Authorization context (read first):** this is an OWNER-AUTHORIZED defensive security review of
our own application (Nexus Agent OS — `app/` in this repo) on our own single machine. Both user
accounts involved (owner + member `ariana`) are ours; the service is reachable only over our
private Tailnet. Nothing here targets third-party systems. The goal is verifying that the
ownership/authorization checks in code WE wrote are correct before a second real user relies on
the tool daily.

**Why this is a separate session (user decision 2026-07-12):** deliberately carved OUT of
`PRODUCTION-READINESS-REVIEW-PLAN-2026-07-11.md` so the long, expensive ultracode readiness run
contains zero security content — a safety-guardrail false positive can then never poison that
session's context. THIS session is small and disposable by design: if it stalls for any reason,
abandon it and relaunch fresh — the loss is minutes, because findings are flushed to disk
continuously (see ground rules).

**Recommended launch:** run this one on **Opus 4.8**, not Fable 5 — the work is mechanical
pattern review plus a few boundary probes (it doesn't need Fable-tier reasoning), and Opus does
not carry Fable's additional dual-use safety layer (the false-positive class that has burned us
before). Open the repo in Claude Code, switch model via `/model`, then say
`Execute SECURITY-SWEEP-PLAN-2026-07-12.md`.
Sequencing vs. the readiness review: either order works. The readiness scorecard's security row
stays **PENDING** until this session's results land.

## Ground rules
- Defensive vocabulary and intent throughout: this is a CORRECTNESS audit of ownership checks
  ("does every handler scope to the requesting user?"). No exploit development; no tooling
  beyond `curl` and the repo's own gate scripts.
- **Flush findings to disk after EVERY subsystem:** append to `SECURITY-SWEEP-<date>.md` as you
  go — never hold results only in context. An aborted session must lose minutes, not the audit.
- The service is LIVE and used: no destructive ops, no schema surgery on `nexus.db`. Boundary
  probes use a scratch member account created the way `verify_multiuser_e2e.py` does — NEVER
  touch `ariana`'s real account or data; clean up scratch artifacts afterwards.
- Bound every `journalctl` with `-n` (a 22 GB OOM happened here once).
- Findings culture: every finding = severity + file:line/command + evidence + proposed fix +
  verify step; adversarially verify before reporting. Fixes are PROPOSED (runbook entries), not
  applied mid-audit — except trivially safe one-liners in one clearly labeled batch-0 commit at
  the end (pre-commit gate must pass).

## Read first (5 min)
- `CLAUDE.md` (repo root — ONE-REPO rule, `app/` is the LIVE tree) + `app/CLAUDE.md`
  (architecture map, gate commands)
- Memory: `SESSION-START.md`, `security-review-multiuser-done.md` (the 2026-07-08 review —
  what was found and fixed then; a MAP of where this bug class clusters, NOT proof anything
  still holds)

## The sweep (zero-trust: every prior PASS is stale; the code has changed a lot since 2026-07-08)
1. **Full authz re-sweep over EVERY handler in the current code** (not a delta): the 2026-07-08
   pattern — every POST/PATCH/DELETE must call `_owned_*`/`WHERE user_id=?` OR `is_admin()` OR
   sit on an explicit public allowlist; every GET checked for cross-user data leaks. Endpoints
   added or changed since then (the bug-fix campaign, Super Result, Deep Plan, autopilot,
   dictation/meetings, restart-prep) are prime suspects, but old ones get re-checked too —
   fixes regress.
2. **Re-confirm the previously-fixed C1/C2/H1–H4 behaviors** with live member-vs-admin boundary
   probes (scratch member): each either still holds (one evidence line) or is a regression
   finding.
3. **Re-decide the open items** (fix or accept, with written reasons): M1 (GET /api/verify/runs
   unscoped), M2 (current_task leak), M4 (login-throttle whitespace bypass), LOW
   shared-fleet-metadata read leaks, stored-XSS-as-attachment.
4. **Secrets hygiene:** file permissions (0600 on `~/.hermes/.env`, `secret.key`, `cert.key`,
   `nexus.db`), no secrets in logs/journal (bounded greps), credentials remain write-only
   through the API, nothing sensitive in git.
5. **Authz coverage gate:** implement-or-propose the verify.sh check that walks handlers and
   fails on any mutating endpoint lacking an ownership/admin/allowlist marker — so this class
   can't silently regress again. (If implemented: separate commit, pre-commit gate green.)

## Deliverables
- `SECURITY-SWEEP-<date>.md` (repo root, appended throughout the session): findings + per-item
  verdicts (holds / regressed / fix-now / accepted-with-reason).
- P0/P1 entries formatted for `READINESS-FIX-RUNBOOK-<date>.md` (append there if the readiness
  session already produced it; otherwise leave them in the sweep doc for it to absorb).
- Flip the readiness scorecard's security row from PENDING once both docs exist; auto-memory
  update with a one-line outcome.

## Non-goals (hard scope fence)
- Nothing offensive: no exploit PoCs beyond a `curl` demonstrating a scoping gap on our own
  service, no third-party targets, no load/DoS testing.
- No public-hosting hardening — Tailnet-only is the accepted posture (separate track).
- No kernel/driver/system-level changes of any kind (hard gate per SESSION-START).
