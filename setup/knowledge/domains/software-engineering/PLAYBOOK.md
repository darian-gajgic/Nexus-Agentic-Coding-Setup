# Software Engineering Playbook

Senior operating procedure for all dev work: our SaaS products, client/consulting builds, e-commerce code.
Product specifics (stack, users, money paths, SLAs) live in `~/knowledge/BUSINESS-CONTEXT.md` — read the relevant section before scoping anything. User-facing copy follows `~/knowledge/STYLE-VOICE.md`.
This complements the existing pipeline (spec → implement → adversarial verify, tests as ground truth): playbooks 1–2 feed that pipeline; 3–8 cover everything around it.
Quality gate for every deliverable: `RUBRIC.md` in this folder. Worked artifacts: `examples/`.

## Operating principles

1. **Scope is a budget, not a suggestion — build exactly what the spec says, then stop.**
   Why: on a 2-person team, gold-plating one task silently cancels another task.
2. **When reality contradicts the spec mid-build, stop and amend the spec — never improvise silently.**
   Why: the adversarial verifier checks against the spec; silent divergence makes verification worthless.
3. **Choose boring technology — you get about 3 innovation tokens per product; spend them on the product.**
   Why: every exciting dependency is an unpaid on-call rotation for a team that has no on-call.
4. **Reversible decisions in minutes; one-way doors (data model, public API, billing) slowly.**
   Why: speed comes from knowing where care is actually required, not from being careful everywhere.
5. **Every bug is two bugs: the defect, and the gap that let it ship. Fix both.**
   Why: patching only the defect guarantees a rematch with the same bug class next month.
6. **Optimize code for the reader; it is read ~10x more often than written.**
   Why: at our size the reader is future-you with zero memory of today — cleverness is a tax on them.
7. **Never deploy what you can't roll back with one command in under 5 minutes.**
   Why: rollback speed, not deploy carefulness, is what caps incident blast radius.
8. **A bug you can't explain isn't fixed.**
   Why: "it went away" means it moved somewhere with worse logging.
9. **A test you've never seen fail proves nothing — see red before green.**
   Why: born-passing tests routinely assert nothing (wrong mock, wrong path, tautology).
10. **Duplication is cheaper than the wrong abstraction — extract on the third occurrence, not the second.**
    Why: a wrong abstraction accretes flags and conditionals until nobody dares delete it.

## Task playbooks

### 1. Scoping and writing a SPEC

Applies to any change over ~2 hours of work, or ANY change touching money, auth, or stored data. Below that: ticket + tests, skip the spec.

1. Write the goal as one sentence: "<actor> can <capability> so that <business outcome>." Can't? Stop and ask the requester — you have a solution without a problem.
2. Read the affected product's section in `BUSINESS-CONTEXT.md`. List: actors, triggers, which money path this touches.
3. Enumerate the happy path plus the 3 ugliest edge cases (empty/missing, duplicate/concurrent, malicious). Can't name 3 → you don't understand the feature yet; keep digging.
4. Write numbered requirements R1..Rn. Each must be falsifiable — a test could fail it. "R4: reset link expires 30 min after issue," never "links expire quickly."
5. Specify error behavior for every input a user or external system controls. Unspecified error behavior = implementer invents it = verifier can't check it.
6. List files/interfaces to touch. More than 10 files or more than 1 service boundary → split into two specs.
7. Write "Out of scope": the things a reasonable reader would assume are included but are not. This is the anti-scope-creep contract.
8. Write "Verification": exact commands with expected output. If you can't write the command, the requirement isn't testable — rewrite the requirement.
9. Estimate. Over 3 dev-days → split the spec. Multiply your gut number by 2 — gut estimates cover the happy path only.

Unknowns rule: if any requirement depends on something unverified (new API, undocumented behavior), run a throwaway spike first, timeboxed to 4h. Spike code never ships.
Format exemplar: `examples/spec-password-reset.md`.

### 2. Implementing to a definition of done

1. Restate the spec's requirements as a checklist in the PR description. This is your contract with the verifier.
2. Build a walking skeleton first: thinnest end-to-end slice (route → logic → storage → response) with one test. Early integration surfaces unknown-unknowns while they're cheap.
3. Implement requirement by requirement. Name each test after the requirement it proves (`r4_token_expires_after_30_min`). Watch each test fail before making it pass.
4. Commit in vertical slices that each pass the suite. Never leave the branch red overnight.
5. Handle every specced error path. `catch`/`except` must handle, translate, or rethrow — log-and-continue counts as swallowing unless the spec says "degrade."
6. Log at boundaries: one line entering each external call (with correlation/request id), one line on failure with the error. Never log secrets, tokens, or PII.
7. Run the full local gate: format, lint, typecheck, tests — {{FILL: the project's single gate command, e.g. `make check`}}. Green with zero new warnings.
8. Self-review your own diff hunk by hunk as a hostile stranger, before opening the PR. Strip debug prints, dead code, TODOs without ticket ids.

Definition of done (all binary — also enforced by RUBRIC gates):
- [ ] Every R# has at least one passing test that names it
- [ ] Spec's Verification commands pass, run exactly as written
- [ ] Full gate green, zero new warnings
- [ ] No swallowed errors, debug output, or commented-out code in the diff
- [ ] Diff ≤400 changed lines, or a split justification in the PR description
- [ ] User-facing copy checked against `STYLE-VOICE.md`
- [ ] If it deploys: rollback command written down (see playbook 7)

### 3. Code review

Timebox: 60 minutes per session, max ~400 lines per session — defect detection collapses beyond both. Bigger diff → review in named chunks or bounce it back for splitting.

1. Read the spec/ticket first, then the tests. Tests reveal what the author believes the code does. First hunt: which requirement has no test?
2. Trace the main happy path end-to-end once. Then hunt in this priority order:
   a. Authz: every new/changed endpoint — who can call it, is ownership checked server-side? (IDOR is the #1 small-SaaS vuln.)
   b. Boundaries: empty, null, 0, 1, max, duplicate submit, concurrent submit.
   c. Error paths: what happens when the DB/HTTP call fails halfway? Any partial writes?
   d. Injection: every string that reaches SQL, HTML, shell, or CSV.
   e. Data: migrations reversible? Index for each new query pattern?
3. Style and naming last, and only as `nit`.
4. Severity per finding: `blocker` (do not merge), `major` (fix before merge unless explicitly waived), `minor` (fix or ticket it), `nit` (author's choice). Every finding: file:line, one line on why it matters, concrete fix.
5. State what you checked and found clean. An approval with no coverage notes is a rubber stamp — the next person must redo your work.
6. End with an explicit verdict — approve / approve-with-minors / request-changes — plus exactly what would flip it.

Rule: you may not demand anything the spec didn't require without proposing a spec amendment. Reviews enforce the spec and the rubric, not personal taste.
Format exemplar: `examples/code-review-report.md`.

### 4. Methodical debugging

1. Reproduce first. No repro → no fix. Instead, add logging/metrics to catch the next occurrence, ticket it, move on. (1 failure in 10 runs IS a repro — script the loop.)
2. Write down: expected, actual, exact error text, when it last worked. Read the error message twice, then search its verbatim text before theorizing.
3. Regression? Bisect: `git bisect start; git bisect bad HEAD; git bisect good <last-known-good>` then `git bisect run <failing-test-cmd>`. O(log n) beats any amount of staring.
4. Not a regression? Binary-search the stack: cut at a boundary (client / API / service / DB), verify the data at the cut, discard the clean half, repeat.
5. One hypothesis at a time. Change one variable. Predict the result BEFORE running the experiment — a surprising result is information; write it down.
6. 45-minute rule: no NEW information for 45 minutes → write a 5-line summary (symptom, tried, ruled out) and escalate or break. Writing the summary solves it embarrassingly often.
7. Found it? Explain the mechanism: why it broke AND why now. Can't answer "why now" → you found a bug, possibly not the bug.
8. Write the regression test, watch it fail, then fix, watch it pass. In that order.
9. Grep the codebase for the same pattern — bugs come in litters (principle 5).

### 5. Test strategy for a 2-person team

Budget allocation, in order:
1. Integration tests at the API/service boundary — real DB (local/containerized), real wiring, fakes only for external vendors. Highest bugs-caught-per-line for SaaS CRUD code.
2. Unit tests only for logic with real branching: pricing, permissions, parsing, date math. A branchless function is already covered by the integration test above it.
3. E2E browser tests for the 3–5 money paths ONLY: {{FILL: e.g. signup, login, checkout/subscribe, the product's core action}}. E2E is expensive to keep green — cap the count, resist adding more.

Rules:
- Every bugfix ships with a regression test that failed before the fix. Zero exceptions — this is how a suite earns trust.
- Test behavior through the public interface. If renaming a private function breaks a test, that test is testing implementation — rewrite it.
- Mock only at process boundaries: HTTP, email, payments, clock, randomness. Mocking your own modules means testing your mocks.
- Coverage is a smoke detector, not a target: investigate below 60% on money-path modules; never chase 100% (the last 20% buys assertions on getters).
- Flaky test: quarantine same day; fix or delete within a week. A suite people rerun-until-green catches nothing.
- Speed budget: unit slice <30s, full suite <5 min locally. A slow suite stops being run, and an unrun suite is decoration.
- Test data: builders/factories with sensible defaults, override only what the test is about. Shared fixture files rot into load-bearing mysteries.

### 6. Technical decisions: build vs buy, choosing dependencies

Build vs buy:
1. Classify the capability: core (differentiates the product) vs context (everything else). Two-person default: BUY context, BUILD core. Auth infra, payments, email delivery, file storage, search, analytics = context — buy.
2. True cost to build = your estimate x3; maintenance over 2 years ≈ 2x the initial build. Compare against 24 months of vendor fees (verify current numbers), not 1 month.
3. Vendor checklist before buying: data export path exists; pricing at 10x current scale still acceptable; know exactly what breaks in our product when the vendor has a bad day.
4. Record it: 10-line decision record in `docs/decisions/NNN-title.md` — context, options, choice, why, revisit-when trigger. Otherwise you re-litigate it in 6 months from memory.

Before adding ANY dependency — all must pass:
- [ ] Writing it ourselves would exceed ~200 lines, OR it involves crypto/auth/parsing untrusted formats (never hand-roll those regardless of size)
- [ ] A release within the last 12 months and maintainer responses visible on the issue tracker
- [ ] Not a solo-maintainer package sitting on a money path (bus factor 1 is a vendor risk without a vendor)
- [ ] License is MIT / Apache-2.0 / BSD / ISC. GPL/AGPL/SSPL/"fair source" → stop, escalate (see frontier review)
- [ ] You spent 5 minutes reading its open issues — the cheapest due diligence nobody does
- [ ] Transitive tree is sane (`npm ls <pkg>` / `pipdeptree`): a 20-line need does not justify 80 transitive dependencies

### 7. Shipping safely: migrations, deploys, rollback

Migrations — expand-contract, always:
1. Deploy N: ADD the new column/table/index only. Backwards-compatible; old code ignores it.
2. Deploy N: dual-write old + new. Backfill in batches ≤1000 rows per transaction with a pause between batches — one big UPDATE locks the table in prod.
3. Deploy N+1: switch reads to the new location; keep dual-writing.
4. Deploy N+2 (days later, after verifying counts match): stop old writes. DROP only in a still-later deploy.
Never rename or drop a column in the same deploy as the code change that stops using it — the old code still runs during rollout AND during rollback.
Every migration ships a down-migration, or is marked `-- IRREVERSIBLE` and the deploy notes include a verified backup plus before/after row counts.

Deploy checklist (binary):
- [ ] CI gate green; migration rehearsed against a prod-shaped copy
- [ ] Rollback command written down BEFORE deploying (previous tag + down-migration); one command, <5 min
- [ ] Risky user-visible change behind a feature flag; any new external integration has a kill switch
- [ ] Window: Tue–Thu, before mid-afternoon. Never Friday. Never within 1h of stopping work for the day
- [ ] Post-deploy: watch error rate, p95 latency, and the money path for 15 minutes. "Deployed and walked away" is not deployed

Rollback rule: error rate ≥2x baseline, or ANY money-path failure → roll back first, debug from the timeline afterwards. Roll forward only if the fix is already reviewed and smaller than the rollback.

### 8. Security basics for a small SaaS

Authorization:
1. Every endpoint: authenticate, then authorize against the resource's owner/tenant server-side. Deny by default.
2. Never trust client-supplied ids. Fetch by `(id, current_account_id)`, never by `id` alone. Ship the cross-tenant test with every new endpoint: user A requests user B's object → 404 (404, not 403 — don't confirm existence).
3. Admin routes: separate router/middleware, role re-checked server-side per request — never from a client-editable field.

Secrets:
4. Secrets live in env vars or a secret manager, different values per environment. Never in code, git history, logs, error messages, or test fixtures.
5. Secret scanning (gitleaks or equivalent) runs pre-commit/CI on every repo. A leaked secret gets rotated the same hour — rotate first, investigate second.

Input handling:
6. Validate at the boundary with a schema (types, lengths, enums). Parameterized queries only. Encode on output; any raw-HTML sink (`dangerouslySetInnerHTML`, template `|safe`) requires frontier review.
7. File uploads: allowlist content types, cap size, store in object storage outside the webroot, serve with forced `Content-Disposition` — never serve user-supplied HTML/SVG from the app's own domain.
8. Webhooks: verify the signature, reject stale timestamps, process with an idempotency key (senders retry).

Auth mechanics:
9. Passwords: argon2id, or bcrypt at cost ≥12 (verify current numbers). Rate-limit auth endpoints: 5 attempts / 15 min / account plus an IP throttle. Error messages identical for "no such user" and "wrong password."
10. Sessions: httpOnly + Secure + SameSite cookies; rotate session id on privilege change; revoke all sessions on password change or reset.
11. One-time tokens (reset, invite, magic link): ≥32 bytes CSPRNG, store only the hash, single-use, explicit expiry. Full worked pattern: `examples/spec-password-reset.md`.
12. Dependency audit (`npm audit` / `pip-audit`) weekly and automated; critical vulns patched within 48h. Log auth events (login success/fail, resets, role changes) with timestamp and IP — never the credential itself.

## Junior mistakes (the classics)

1. Fixing where the error appears, not where the invariant broke → trace to root cause; symptom patches turn one bug into two.
2. "Works on my machine" as done → done = the spec's verification commands pass in a clean environment/CI.
3. Week-old branch, 1500-line PR → vertical slices behind a flag, merge daily; big PRs get worse reviews, not more review.
4. `catch (e) {}` or log-and-continue → handle, translate, or rethrow; silence is corruption deferred.
5. Mock-everything tests asserting `mock.calledOnce` → assert observable behavior; mock-assertions pass while prod burns.
6. Extracting an abstraction at the second occurrence → wait for the third (principle 10); duplication is cheaper than the wrong abstraction.
7. Optimizing without a measurement → profile first; name the number and target ("p95 400ms → 150ms") or don't touch it.
8. Treating client-side validation as security → the client is a suggestion; enforce everything server-side.
9. "While I was in there" refactors inside a feature PR → separate PR; mixed diffs hide bugs from reviewers.
10. Estimating the happy path → list every integration point, count each as half a day, then multiply by 2.
11. Pasting AI/StackOverflow code unread → you own every pasted line; read it until you could have written it, including its failure modes.
12. Resolving a review comment with "done" and nothing else → reply with the commit hash or the reason you disagree.
13. Skipping the error path because "it basically can't fail" → the network is not "basically"; the spec says what failure does, so implement it.
14. Reaching for the shiny new framework on a revenue product → boring tech (principle 3); shiny things go in side projects first.

## Escalate to frontier review when…

Run `creview <diff>` for code or `cjudge <artifact>` for specs/decisions/docs — a stronger model performs a second review. GLM output in any of these zones ships ONLY after that pass:

- Any diff touching auth, sessions, payments/billing, or PII — no minimum size.
- Any cryptography, token generation/validation, or signature verification.
- Destructive or irreversible migrations; any backfill on data you can't restore within minutes.
- Public API contract changes; webhook handlers.
- Concurrency: queues, retries, idempotency, anything described as "must happen exactly once."
- New dependency or vendor on a money path; any GPL/AGPL-family license question.
- Anything with external blast radius: sends real emails, charges cards, notifies users in bulk.
- Diff still >400 changed lines or >10 files after honest attempts to split.
- Debugging: two falsified hypotheses in a row, or any fix you cannot explain mechanistically.
- You are about to override the spec, RUBRIC.md, or this playbook — the override may be right, but it gets a second brain first.
