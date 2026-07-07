---
name: frontier-judge
description: Get a second opinion from the frontier Claude model (the user's Anthropic subscription) on a deliverable before it ships. Use for HIGH-STAKES work — anything matching the "Escalate to frontier review" list in the domain playbook at ~/knowledge/domains/<domain>/PLAYBOOK.md — or whenever the user asks for a frontier review, judge, or second opinion. Judges against the domain RUBRIC.md and returns SHIP/REVISE/REWRITE with concrete fixes.
version: 1.0.0
author: sinep
metadata:
  hermes:
    tags: [quality, review, judge, frontier, cross-model]
---

# Frontier Judge

Cross-family quality gate: GLM produces, frontier Claude judges. A model reviewing its own
family's output shares its blind spots — this catches what self-review structurally cannot.

## When to use

- The deliverable matches its playbook's "Escalate to frontier review when…" list
  (~/knowledge/domains/<domain>/PLAYBOOK.md).
- The user explicitly asks for a frontier review / judge / second opinion.
- You are genuinely uncertain whether high-stakes work is good enough.

NOT for routine low-stakes drafts — it spends the user's Claude subscription. Self-score
against the RUBRIC.md yourself first; the judge is the second gate, not the first.

## How

1. Save the deliverable to a file (markdown preferred) — in the project directory if one
   exists, else /tmp/deliverable-<topic>.md.
2. Run in the terminal:
   `cjudge <absolute-file-path> <domain>`
   Domains: software-engineering, saas-business, marketing, content-creation, brand,
   ecommerce, consulting-bizdev, research-learning, music-dj.
3. Wait — it can take 1–3 minutes (frontier model, deep review).
4. Act on the verdict:
   - SHIP → deliver, mention the judge passed it.
   - REVISE → fix every blocking item, then **do the regression re-walk in step 5 BEFORE
     delivering**. "Fixed every item" is necessary, not sufficient — see step 5. After the
     re-walk, deliver if clean; re-judge if step 5 says to.
   - REWRITE → start over following the judge's reasoning; tell the user why.
5. Always relay the judge's "Learning note:" line to the user — they are juniors deliberately
   learning from these reviews.

## 5. The regression re-walk (do this after every REVISE before delivering)

A fix that satisfies the judge's named finding is NOT guaranteed to survive the customer.
Judges name the *symptom scenario*; the natural fix often breaks a *different lifecycle* that
the judge never walked. Two real examples from one session (full catalog in
`references/fix-introduces-bugs.md`):
- Judge: "the double-submit key is wrong." Fix: add a `@@unique(cartId, status)`. That
  satisfied the finding — but silently made repeat purchases impossible (the second order
  can't flip to 'paid' without violating the constraint).
- Judge: "idempotency key should be cart-derived." Fix: `'checkout_' + cart.id`. Satisfied
  the finding — but bricked cancel→edit→retry for ~24h (Stripe rejects same-key+different-params).

**Mandatory after a REVISE fix, before delivery: re-walk the FULL lifecycle, not just the
scenario the judge named.** For each stateful/persistent structure the fix touched, enumerate
and trace the 2nd occurrence of every operation, plus the error/retry/cancel/edit branches:

- Data-model / DB-constraint change → trace the **2nd** create, the **2nd** state transition,
  and the post-success path. Does anything (a unique index, a NOT NULL, a cascade) prevent a
  legitimate second operation?
- Idempotency / caching key change → trace **retry with changed params** (same key, different
  body). Does the key collide when the user legitimately repeats with an edit?
- Payment / money-path change → trace decline, cancel, webhook-before-redirect, and
  webhook-redelivery separately. One status field per row; verify ROLLBACK leaves a coherent
  single state.
- Any new code that "should compile" → actually compile/validate it (e.g. `prisma validate`,
  `tsc`, the language's parser). Don't assert validity from plausibility.
- Test fixture that "covers the finding" → does it actually exercise the condition, or does it
  pass by doing nothing (vacuous)? E.g. a `stripe trigger` without `--add metadata` can't map
  to the order under test, so "assertion passed" proves nothing.

**When to re-judge (vs. deliver after the re-walk):** re-run cjudge when the fix touched
one-way-door structures (data model, public API, money path, idempotency) OR when the fix was
substantial (>~40 lines / >3 sections changed). The cost of a second pass is small; the cost
of shipping a fix-induced regression on a money path is large. For a trivial fix (a typo, a
single clarified sentence), the re-walk alone is enough — don't burn the subscription.

**State the re-walk result in the delivery:** either "re-walked lifecycles X/Y/Z clean,
delivered" or "re-judged; pass 2 found N blockers, all fixed." If a 2nd+ pass is blocked by
the cjudge session limit (it runs against Anthropic with rate limits), say so plainly —
"all known blockers addressed; confirmation pass blocked by rate limit, re-run before
implementation" — rather than claiming a verified SHIP you couldn't obtain.

## Troubleshooting

- `cjudge: command not found` → check ~/.local/bin is on PATH and the script exists; point the
  user to ~/knowledge/WORKFLOW.md.
- Unknown domain → run `ls ~/knowledge/domains` and pick the closest.
- `cjudge` returns a session/rate-limit error (e.g. "session limit · resets <time>") → the
  judge could not run. Apply the step-5 re-walk yourself with extra rigor (no model backstop),
  note the limit in the delivery, and re-run after the reset.
