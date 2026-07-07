# Green tests that hid real bugs — spec-vs-implementation review

A companion to the three anti-patterns in SKILL.md ("wrote the test from what the code does",
"unit mismatch at a cross-layer boundary", "literal contract drift"). Worked examples from a
2026-07-06 independent code review of a Next.js + SQLite webshop. All three bugs shipped with
23/23 tests green. The review was done fresh-context by a `code-reviewer` subagent that read the
actual files, not the implementer's self-assessment.

## Setup that made these invisible

The project had a SPEC with 29 numbered requirements (R1–R29), each with a falsifiable
verification command. The implementer wrote tests named after each R# (good discipline). But
three of those tests passed for the wrong reason, and only an independent reader comparing the
spec text to the code text caught the gaps. The lesson: a green test named `r26_…` is evidence
the code does *something*, not that it does *the spec*.

## Bug 1 — confirmation page dropped the purchased-items list (R26)

- **Spec R26:** "The order confirmation page renders the `orderId`, the list of purchased items,
  and the total."
- **Code (`app/checkout/confirmation/page.tsx`):** rendered orderId + total (read from URL
  query params). The items were never passed through; `checkout/page.tsx` discarded the
  `items` array the API returned and only put `orderId` + `total` in the URL.
- **Test (`e2e.checkout.test.ts` R26):** asserted `order-confirmation` present, `order-id`
  non-empty, `order-total` matches `/\$/`. Did NOT assert the items list.
- **Why the test passed:** it was written by reading what the page rendered, then asserting on
  that. The missing third element never appeared in the assertions because it never appeared in
  the DOM.
- **The fix-at-the-skill-level:** author each test's assertions directly from the spec's
  requirement sentence, enumerating EVERY noun the spec lists. "orderId, items, AND total" →
  three assertions, not two. If the page can't satisfy one, the test fails and you find the gap
  before shipping.

## Bug 2 — price filter unit mismatch (R14 UI)

- **Spec R6:** `GET /api/products?category=gpu&min_price=20000&max_price=80000` — params are in
  CENTS.
- **Code:** `CatalogueClient.tsx` rendered inputs labeled `Min Price ($)` / `Max Price ($)` with
  placeholders `0` / `9999` (implying DOLLARS), then sent the raw typed string as
  `min_price` / `max_price`. `lib/db.ts` compared those values against `price_cents` (CENTS).
- **What a human saw:** type `200` (meaning $200) → API filters `price_cents >= 200` → all 18
  products (200¢ = $2.00). Type the placeholder `9999` → `price_cents <= 9999` → zero products
  (cheapest seed item was 14999¢).
- **Why the test passed:** `products.api.test.ts` R6 called the API directly with cent values
  (`min_price=20000`) and asserted the results were in range. The API was correct. The UI→API
  glue was never exercised by any test.
- **The fix-at-the-skill-level:** for any value that crosses a layer boundary where units can
  differ (UI label vs wire format is the classic case), trace ONE input end-to-end: read the
  label, type the value, follow the param name into the handler, follow the handler into the
  query, confirm the comparator's unit matches. Then write one e2e test that types into the real
  field and asserts on the real filtered result. Placeholder-vs-real-data sanity check: if the
  placeholder value, fed through the transformation, yields zero or all results against the seed
  data, the unit is wrong.

## Bug 3 — cart route + testid drift (R21)

- **Spec R21:** cart page at route `/cart` with `data-testid="cart-page"`. Spec §3 file layout:
  `app/cart/page.tsx`.
- **Code:** no `app/cart/` dir. Cart page lived at `app/checkout/cart/page.tsx` (route
  `/checkout/cart`), tagged line items with `data-testid="cart-item"` but never set
  `cart-page`. `Header.tsx` linked to `/checkout/cart`.
- **Test (`e2e.checkout.test.ts` R21/R22):** navigated to `/checkout/cart`, asserted on
  `cart-item` / `cart-total` / `remove-item`.
- **Why the test passed:** the test targeted the route and testids the code actually used. The
  spec's literal route and testid (`/cart`, `cart-page`) appeared nowhere in the app.
- **Consequence:** a verifier running the spec's R21 verification command ("navigate to `/cart`,
  assert line items") hits a 404 at `/cart`.
- **The fix-at-the-skill-level:** spec-named literals (routes, testids, URL paths, query-param
  names, CSS selectors, field names) are exact-match contracts. Before merge, grep the spec for
  `data-testid=`, quoted URL paths, and `data-` attributes, and confirm each literal exists
  verbatim in the running app. If the implementation legitimately needs a different name, amend
  the spec FIRST — then update the test to match the amended spec. Never move the contract and
  silently move the test to follow; that makes the test suite a rubber stamp for whatever the
  code does.

## The meta-pattern

All three are the same disease: **the test suite was calibrated to the implementation, not to
the spec.** Calibrated to the implementation, a suite can only prove "the code does what the
code does" — tautological green. Calibrated to the spec, a test that fails points at a real gap.

Practical calibration moves, cheap enough to do on every spec-driven build:

1. **Mine the spec for literals.** `grep -nE 'data-testid=|/[a-z][a-z-]*/|"[a-z_]+"' SPEC.md`
   gives you the exact-match contract list (routes, testids, param names). Cross-check each
   against the app.
2. **Enumerate spec nouns into assertions.** If a requirement says "renders A, B, and C", that
   is three assertions, not "renders A" plus a visibility check.
3. **Trace one value per cross-layer boundary end-to-end**, through every unit transformation,
   to the final comparison. Label units explicitly in the trace (UI: dollars → param: number →
   SQL: compared to cents).
4. **Run an independent spec-vs-code review** (fresh context, `code-reviewer` specialist) that
   reads the SPEC and the files and produces an R1..Rn met/partial/missing table. This is the
   check that caught all three — neither author nor self-review could, because both shared the
   implementation's framing.

## How this maps to the existing anti-patterns

This is a sibling of the two earlier "green tests hide bugs" entries in the skill:

- "You edited the test AND ran it as your evidence" — same author wrote both sides, so the bug
  was mirrored.
- "Launch flag disables the restriction the bug lives in" — the test environment suppressed the
  real-world constraint.

The new three are the spec-contract equivalents: the test was written from the code, a
layer-bypassing test masked a UI bug, and a moved literal was followed by a moved test. The
unifying fix is independent calibration — to the spec, to the real environment, and via a fresh
reviewer who hasn't internalized the implementation.
