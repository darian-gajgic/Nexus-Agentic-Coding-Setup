---
title: Spec — webhook delivery with retries for Mahnwerk
specialist: tech-lead-orchestrator
notes: exercises spec gates — falsifiable requirements, exact verification commands, edge cases
---
Write the full SPEC (no code) for the feature below, following the house spec format:
context & goal / numbered requirements R1..Rn (each independently testable and falsifiable) /
files & interfaces with exact paths / out of scope / verification (exact commands + expected
results) / ordered plan with per-item acceptance criteria and edge cases.

CONTEXT (fixed):
- Product: Mahnwerk, a FastAPI + PostgreSQL SaaS (Python 3.12, SQLAlchemy 2, Alembic
  migrations, pytest, deployed as a single Docker service behind Caddy).
- Feature: outbound webhooks — customers register up to 5 endpoint URLs; Mahnwerk POSTs
  JSON events (reminder.sent, invoice.paid, reminder.bounced) with an HMAC-SHA256 signature
  header; delivery must retry on failure with exponential backoff (schedule: 1m, 5m, 30m, 2h,
  12h, then dead-letter), preserve per-endpoint ordering, and expose delivery history to the
  customer (last 100 attempts per endpoint).
- Constraints: no new infrastructure (no Redis/queue service — PostgreSQL-backed queue is
  fine); secrets stored encrypted at rest; a customer disabling an endpoint stops deliveries
  within 60 s; event payloads must be immutable snapshots (a later invoice edit must not
  change an already-emitted event).
- Unfalsifiable wording ("fast", "robust", "handles gracefully") is a DEFECT in this house.

Deliverable: the spec document.
