# Testing Stripe webhooks without live keys or Stripe CLI

**When to use:** any project with a Stripe Checkout + webhook flow where you need to verify the
money-path logic (signature verification, idempotency, stock decrement, oversold rollback) but
cannot make live API calls — no real test keys, no Stripe CLI, no `stripe listen` forwarder.

This is the T16 pattern from a spec like: *"Stripe mocked at the HTTP boundary only so the money
logic is fully exercised without a network call."*

## The core insight — two boundaries, different strategies

A Stripe integration has two testable boundaries:

1. **Session creation** (`stripe.checkout.sessions.create`) — makes an HTTP call to Stripe.
   This is pure delegation; your money logic is in *what you pass it* (line items from DB prices,
   the idempotency key derivation, the order upsert). Mock this at the **module boundary** with
   `vi.mock("@/lib/stripe", ...)` and a fake `create()` that returns a deterministic URL.

2. **Webhook signature verification** (`stripe.webhooks.constructEvent`) — does HMAC verification
   against the raw body. This is the #1 thing that breaks on go-live. Do NOT mock it away —
   **exercise the real crypto path** by creating locally-signed events.

## The technique: locally-signed events via the real SDK

The Stripe Node SDK has `stripe.webhooks.generateTestHeaderString({ payload, secret })` which
produces a valid `stripe-signature` header for a given payload+secret. Combined with a real
`stripe.webhooks.constructEvent(rawBody, sig, secret)` call, the full HMAC verification path
runs — no network involved:

```typescript
// In the test file — create a REAL Stripe client (no network, only local signing)
const stripeForSigning = new Stripe("sk_test_signing_only", {
  apiVersion: "2024-12-18.acacia",
});

// Mock only the module's getStripe(), but delegate webhooks to the real SDK
vi.mock("@/lib/stripe", () => {
  const realStripe = new Stripe("sk_test_signing_only", { ... });
  return {
    getStripe: () => ({
      checkout: {
        sessions: { create: async (params, opts) => {
          // Track idempotency keys, return deterministic URLs for convergence tests
          return { id: `cs_test_${Date.now()}`, url: `https://checkout.stripe.com/...` };
        }},
      },
      webhooks: realStripe.webhooks,  // ← REAL constructEvent, exercises HMAC
    }),
  };
});

function makeSignedWebhookRequest(orderId: number, paymentStatus: string) {
  const rawBody = JSON.stringify({
    id: `evt_test_${Date.now()}`,
    object: "event",
    type: "checkout.session.completed",
    data: { object: {
      id: `cs_test_${orderId}`,
      client_reference_id: String(orderId),
      payment_status: paymentStatus,
    }},
  });
  const signature = stripeForSigning.webhooks.generateTestHeaderString({
    payload: rawBody,
    secret: WEBHOOK_SECRET,
  });
  return new Request("http://localhost/api/stripe/webhook", {
    method: "POST",
    headers: { "stripe-signature": signature },
    body: rawBody,
  });
}
```

This lets you test:
- **Signature rejection** — send a bad signature → assert 400 `signature_invalid`.
- **Happy path** — signed `payment_status: "paid"` event → assert order flips to `paid`, stock decremented.
- **Idempotency retry** — fire the same event twice → assert stock decremented only once (the
  `if (order.status === 'paid') return 200` dedupe path).
- **Oversold race** — seed `stock: 1`, create an order for qty 2, fire paid webhook → assert
  `status: 'oversold'` (the `WHERE stock >= qty` guard fails, transaction rolls back).
- **Unpaid guard** — fire with `payment_status: "unpaid"` → assert event is ignored (async methods
  like bank debits complete without 'paid').

## Mock convergence for double-submit / idempotency tests

For checkout session-creation idempotency tests, the mock must simulate Stripe's behavior: same
idempotency key → same session URL. Use a Map keyed on the idempotency key:

```typescript
const sessionCache = new Map<string, string>();
// In the fake create():
if (!sessionCache.has(opts.idempotencyKey)) {
  sessionCache.set(opts.idempotencyKey, `https://checkout.stripe.com/c/pay/cs_test_${++counter}`);
}
return { id: ..., url: sessionCache.get(opts.idempotencyKey) };
```

Then two concurrent identical POSTs → same URL, one Order row. And cancel→edit→retry → different
cartHash → different idempotency key → different URL. This is the double-submit guard convergence
test.

## What this does NOT verify (flag as manual smoke)

- The hosted-page redirect round trip (`checkout.stripe.com` card form) — needs real keys.
- Card declines (`4000...0002`) — they're synchronous on Stripe's hosted page, not webhook-driven.
- The `stripe listen` → live webhook delivery path — needs the Stripe CLI.

Document these as manual smoke steps requiring the user's own Stripe keys + CLI. The local tests
prove the money LOGIC; the live smoke proves the money PLUMBING.

## Common gotcha: raw body for App Router

Next.js App Router webhook routes need `export const runtime = 'nodejs'` and
`const rawBody = await request.text()` — NOT `request.json()`. `constructEvent` needs the raw
string for the HMAC to match. If you parse to JSON first, the signature check will fail because
the serialization isn't byte-identical to what Stripe signed.
