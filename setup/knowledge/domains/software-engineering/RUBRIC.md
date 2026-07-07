# Software Engineering Rubric

Scoreable quality gate for every engineering deliverable (code, PR, spec). Companion to `PLAYBOOK.md`; worked artifacts in `examples/`.

How to apply, in order:
1. Run the gates. Any failure → do not deliver; fix and re-run. No judgment calls.
2. Score the dimensions 0–4. Deliver at average ≥3.0 with no dimension below 2. Otherwise revise the weakest dimension first.
3. Scan the kill list against the diff/PR/spec. Any hit → fix before delivering.
4. If the work matches PLAYBOOK "Escalate to frontier review" → run `creview`/`cjudge` before delivery regardless of score.

## Must-pass gates (binary — do not deliver if any fails)

- G1. Full test suite passes as one command, exit code 0. No tests skipped/disabled in this diff without a linked ticket id.
- G2. Linter and typechecker pass with zero NEW warnings or errors.
- G3. Every numbered spec requirement (R#) is named by at least one test. Check mechanically: grep test names for each R# — zero orphan requirements.
- G4. The spec's Verification commands pass, run exactly as written.
- G5. Secret scan clean on the diff (`gitleaks detect` or at minimum grep for `sk_live|AKIA|-----BEGIN|api[_-]?key.*=`) — including test fixtures and config.
- G6. Every new or changed endpoint has a server-side authz check AND a test where a wrong-user/wrong-tenant request receives 404/403.
- G7. Zero swallowed errors in the diff: every catch/except handles, translates, or rethrows. Empty catch blocks: zero.
- G8. Every migration has a down-migration, or is marked `-- IRREVERSIBLE` with a backup step in the deploy notes.
- G9. Diff hygiene: no debug prints, no commented-out code, no TODO/FIXME without ticket id, no unrelated file churn.
- G10. If the change deploys: rollback command is written in the PR description.

## Scored dimensions (0–4 each)

Scale anchors: 0 = absent/broken, 2 = passable professional work, 4 = exemplary. 1 and 3 sit between their neighbors.

**D1. Correctness vs spec**
- 2: Happy path of every requirement works; at least one edge case per requirement handled.
- 4: All specced edges plus boundaries (empty, 0, 1, max, duplicate, concurrent) handled and tested; every deviation from spec was surfaced and the spec amended — nothing improvised.

**D2. Test quality**
- 2: A test per requirement, deterministic, asserting outcomes (not merely "doesn't throw").
- 4: Tests read as documentation of the spec; failure paths and boundaries covered; each new test was seen failing (fails again if the change is reverted); mocks only at process boundaries, none of our own modules.

**D3. Error handling and failure modes**
- 2: Expected failures (validation, not-found, external timeout) return correct status and message; nothing swallowed.
- 4: Partial-failure behavior is deliberate (transaction or idempotency where two writes could split); errors carry a correlation id; user-facing messages match `STYLE-VOICE.md` and leak no internals or stack traces.

**D4. Readability and structure**
- 2: A stranger can follow it with effort; names are accurate; functions ≤40 lines except where justified in a comment.
- 4: Reads top-down without jumping between files to understand intent; no dead code; each module has one reason to change; a new teammate could extend it without asking questions.

**D5. Security and input handling**
- 2: Parameterized queries; schema validation on every new input; no secrets in code; authn+authz present.
- 4: Output encoding verified at every sink; rate limits on abusable endpoints; tokens hashed at rest; cross-tenant tests present; upload/webhook hardening per PLAYBOOK 8 wherever those surfaces appear.

**D6. Scope discipline**
- 2: Diff is substantially the specced change; any drive-by is small and called out in the PR description.
- 4: Diff maps 1:1 to the spec; discovered-but-deferred work is listed as follow-ups with ticket ids; zero mixed refactor+behavior commits.

**D7. Operability**
- 2: Boundary logging exists; a failure of the new code is diagnosable from logs alone.
- 4: Correlation id flows end-to-end; risky path behind a flag or kill switch; the log query or alert for the new failure mode is written in the PR; deploy and rollback rehearsed.

## Kill list (amateur markers — fix on sight, no judgment needed)

In code:
- Empty catch/except; or a catch that only logs and continues on a write path
- SQL, shell, or HTML assembled by string concatenation/interpolation with runtime values
- Hardcoded environment-specific values (URLs, ids, keys) in source
- `any` / `@ts-ignore` / blind casts used to silence the type checker instead of fixing the type
- Magic numbers in business logic without a named constant (`86400`, `0.2`, `3`)
- Floats for money (use integer minor units or a decimal type)
- N+1 queries in a loop; sequential awaits on independent I/O
- `console.log` / `print` / `dbg!` left in the diff
- A copy-pasted block of ≥10 lines appearing 3+ times
- Naive/local-time datetime handling on the server (no timezone; locale-dependent formatting)

In PRs:
- Title that doesn't state the change ("fix", "updates", "wip", "misc")
- More than 400 changed lines with no split justification
- Behavior change and refactor mixed in one commit
- Behavior diff with no accompanying test diff
- UI change without a before/after screenshot
- Review comment resolved without a commit reference or a stated reason
- Force-push over a reviewed branch without a note describing what changed

In specs:
- Unfalsifiable requirement language with no number or observable behavior: "fast", "robust", "user-friendly", "properly", "handles gracefully"
- Unnumbered requirements (tests and reviews can't reference them)
- No "Out of scope" section
- Verification section missing, or written as prose instead of runnable commands with expected output
- Implementation prescribed ("use Redis") with no behavioral requirement it serves
- No error behavior specified for user-controlled input
