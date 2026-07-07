# Fix-Induced Regressions — Concrete Catalog

Why the step-5 re-walk exists: a fix that resolves the judge's *named symptom* often breaks
a *different lifecycle* the judge never walked. These are the classes that bit in practice,
so future sessions can re-walk them by name instead of rediscovering them.

## 1. DB-constraint fix → breaks the 2nd legitimate operation

Symptom judged: "double-submit can create two orders for one cart."
Naive fix: `@@unique([cartId, status])` to enforce one order per (cart, status).
Regression: a repeat customer buys (order A: cartId=C, status='paid'), browses again with
the same cookie, checks out (order B: cartId=C, status='pending' — allowed), pays — the
webhook's `UPDATE Order SET status='paid'` on B **violates the unique index** because
(C,'paid') already exists. Transaction fails → webhook 500s → Stripe retries forever → money
captured, order stuck pending. Every repeat customer hits this.

General rule: any unique constraint on (entity, status) where status transitions through a
repeated value blocks the 2nd lifecycle. Prefer a **nullable pointer** that is set during the
guarded state and cleared on exit (e.g. `pendingCartId String? @unique`, set on creation,
NULL'd in the success transaction). The nullable pointer only enforces "at most one pending
per cart," not "at most one paid per cart ever."

Re-walk: for every new `@unique` / `@@unique`, trace the 2nd create and the 2nd state
transition through the guarded value.

## 2. Idempotency / cache key fix → bricks retry-with-edit

Symptom judged: "idempotency key derived from the wrong field."
Naive fix: key on a stable identifier alone (e.g. `'checkout_' + cart.id`).
Regression: Stripe (and most dedupe/caching systems) cache the first response under a key
for hours and return `idempotency_error` if the same key is reused with *different
parameters*. User cancels checkout, edits the cart, retries — same `cart.id` → same key →
different `line_items` → Stripe rejects → that cart cannot check out for ~24h.

General rule: an idempotency key must be stable across retries of the **same logical request**
but change when the **meaningful payload** changes. Include a hash of the payload contents:
`key = ${stableId}_${hash(payload)}`. Same payload retried → same key → dedup. Payload edited
→ new hash → new key → fresh request.

Re-walk: for any new dedupe/cache key, trace retry-with-changed-params, not just
retry-with-same-params.

## 3. "Roll back and flag" → incoherent dual state

Symptom judged: "oversold orders must not be marked paid."
Naive fix prose: "if stock update fails, the transaction rolls back and the order is marked
paid but flagged oversold."
Regression: that sentence is self-contradictory — if the transaction rolls back, nothing was
written, so the order can't also be "marked paid." One status column ended up described as
holding two states at once.

General rule: a rollback means "nothing persisted." If you need to record that the failure
happened, that recording must be a **separate** committed transaction with a **single
coherent status** (e.g. ROLLBACK the paid+decrement txn, then in a new txn set
`status='oversold'`). One status field = one state per row, always.

Re-walk: any sentence containing both "rollback" and "mark" in the same clause is wrong.
Pick one outcome per row.

## 4. "Should compile" → it doesn't

Symptom judged: "the schema is invalid."
Naive fix: rewrite the block by eye to "look right."
Regression: PSL/SQL/config grammars have silent requirements — field-per-line, missing
back-relations (`Product` must declare `cartItems CartItem[]` if `CartItem.product` references
it), statement separators that don't exist in that grammar. Eyeballing it passed; the tool
rejected it.

General rule: for any code/config the fix produces, run the language's own validator
(`prisma validate`, `tsc --noEmit`, `python -c 'import ast; ast.parse(open(f).read())'`,
`kubeval`, etc.) before claiming it's fixed. Don't assert validity from plausibility.

Re-walk: every new code/config block in the fix → run the parser/validator. If the tool
isn't available, say "not validated" rather than "fixed."

## 5. Test fixture that "covers the finding" → vacuous

Symptom judged: "the test doesn't exercise the path."
Naive fix: add a test that fires the event.
Regression: `stripe trigger checkout.session.completed` mints a **fixture** session with no
link to your order — the handler can't map it, so "assertion passed" but it proved nothing.
The test passes by doing nothing.

General rule: a test passes vacuously when its inputs can't reach the code path under test,
or when the assertion is true regardless of the code (e.g. "nothing happened" after taking no
action). Before shipping a test added to satisfy a finding, ask: "if I revert the code fix,
does this test fail?" If no, the test is decorative.

Re-walk: for every test added in the fix, mentally revert the code change and confirm the
test fails (the RUBRIC "see red before green" rule, applied to the fix).

---

## Meta-pattern

Every one of these is the same shape: **the fix optimized for the judge's named scenario and
ignored the adjacent ones.** The judge is an adversarial reader of the *current* draft; it
cannot see the *next* draft. The regression re-walk (skill step 5) is the agent's job because
the agent is the only party that sees the fixed draft before it ships. Treat the re-walk as
load-bearing, not optional, whenever the fix touches one-way-door structures.
