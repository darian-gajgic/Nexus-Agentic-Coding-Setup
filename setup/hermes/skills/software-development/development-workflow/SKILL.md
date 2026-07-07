---
name: development-workflow
description: Use when implementing any non-trivial software change — a feature, refactor, or bug fix. Orchestrates the research → plan → implement → test → review-loop → verify → document pipeline (with a fresh-context code-review loop and a verification gate) that produces the best-quality code. Skip only for one-line/trivial edits.
version: 1.0.0
author: hermes-specialists
license: MIT
metadata:
  hermes:
    tags: [development, orchestration, code-review, testing, pipeline, quality]
    related_skills: [plan, creating-specialist-agents]
---

# Development workflow — the pipeline that produces great code

The point of this skill: **do not "pick one specialist and ship."** State-of-the-art code quality comes from a *wired pipeline with a feedback loop and a gate*, not from a single strong agent. Run these stages in order for any non-trivial change. The one governing rule across all of it:

> **Parallelize reads. Single-thread writes.** Fan out research, exploration, analysis, and review to parallel agents (cap 3–5). But exactly **one** agent writes code for a given work item at a time — multiple writers on shared code produce incoherent results.

## Wired into the Business Brain + frontier bridge

- All dev specialists carry a standing knowledge protocol: `~/knowledge/domains/software-engineering/PLAYBOOK.md` governs how each stage is done, and its RUBRIC.md must-pass gates apply to the final diff.
- If a `SPEC.md` exists at the repo root (authored via `cspec` — frontier Claude), it is the authoritative requirements contract: don't re-plan what it already decides; PLAN.md then only orders and assigns the work.
- **High-stakes changes** (the playbook's "Escalate to frontier review" list — auth, payments, data migrations, security-touching, customer-visible): after the internal review loop passes, run **`creview`** in the terminal — frontier Claude adversarially reviews the diff vs SPEC.md (takes minutes). Treat its BLOCKING findings exactly like reviewer FAILs: fix → re-test → re-run once. Max 2 rounds, then surface remaining findings to the user.

## The stages

### 0. Detect predecessor work (follow-up tasks) — before scoping

Tasks phrased as "implement the X," "follow-up," or referencing a prior task ID often arrive with a
predecessor session that already produced artifacts. In this setup those artifacts live in
`workspaces/<task-id>/` (a `deliverable.md` + the actual code directory). The deliverable.md can look
EMPTY or misleading — a redaction artifact (e.g. a `sk_test_…` placeholder auto-redacted on read), a
truncated 2-line stub, or a harvest error — while a COMPLETE, working, tested codebase sits in a
sibling subdirectory right next to it.

Before treating the task as greenfield and re-scaffolding:

1. Look for the predecessor's task ID in the prompt or nearby workspaces. `ls workspaces/task-*/`
   and read each `_dispatch.json` (shows `harvested`, `agent_id`, `usage`) to find completed runs.
2. If a code directory exists, inspect its actual contents (`find . -type f`, `package.json`,
   `prisma/schema`, test files) — NOT just the deliverable.md. A populated `node_modules` + a test
   suite + a `.next`/build cache means it was built AND run, not merely scaffolded.
3. Re-scope accordingly:
   - **Found working + tested code** → this is a focused DELTA (elevate / extend / fix), not a
     rebuild. Read the existing code first, identify what is already done vs. what the follow-up
     asks for, and delegate only the gap. Run the existing gate yourself to establish a green
     baseline BEFORE making any change.
   - **Found nothing / only a plan** → greenfield; proceed to Stage 1.

Cost of skipping this: a wasteful from-scratch rebuild of ~30 files that duplicates work the
predecessor already shipped and tested. Origin (2026-07-06, clothing webshop follow-up): the
deliverable.md was a 2-line redaction artifact, but the `webshop/` directory beside it held a
complete Next.js + Prisma + Stripe app with 20 passing R1–R12 tests. Inspecting the workspace first
turned "implement the webshop" into a focused design-elevation pass that kept every test green.

### 1. Explore & plan (before writing any code)
Delegate to **`tech-lead-orchestrator`** (or do this yourself for small tasks). It reads the codebase **read-only**, then writes a short **PLAN.md** containing: an ordered task list, **explicit, testable acceptance criteria**, edge cases, and which specialist handles each step. This plan is the rubric everything else is checked against. Don't skip it — "looks done" without criteria is the #1 cause of shipping the wrong thing. For research-heavy tasks, fan out `web-researcher` (quick factual lookups) and `market-researcher` (market/competitor questions) **in parallel** first.

### 2. Implement (single writer)
Delegate the actual code to **`code-implementer`** — it implements the task end-to-end AND writes+runs its own tests (language/domain expertise comes from the software-engineering playbook its standing rules make it read). **One writer per work item.** If the plan has independent work items, you may run separate `code-implementer` instances on *separate files/areas* — never two on the same code.

### 3. Test (author tests that actually run)
Tests are written by the **same `code-implementer` in the same pass** (its standing rules forbid gaming them — no tautologies, no weakened assertions; `acceptance-verifier` checks for that at the gate). Tests must **execute red → green**, not aspirational, and encode the acceptance criteria from PLAN.md. Capture the actual pass/fail output — you will need it as evidence at the gate.

### 4. Review LOOP (the highest-leverage stage — do not skip)
Delegate to **`code-reviewer`** in a **fresh context**, giving it **only the diff + the PLAN.md acceptance criteria** — not the implementation conversation. Fresh eyes on a short context beat context-rotted self-review. It returns severity-ranked (critical/high/medium/low) **PASS/FAIL** findings.

- If **FAIL**: hand the *full findings* back to the implementer (or to **`debugger`** if a test is failing — hypothesis → reproduce → fix → reproduce-fix) → fix → **re-review**. Loop until the reviewer returns PASS with no critical/high findings.
- Tell the reviewer to flag **correctness and requirement gaps only**, marking style/nice-to-haves as optional, so the loop **converges** instead of gold-plating.
- The generator and the reviewer must **not** be the same agent and must **not** share prior context. This is the write → catch → fix → merge loop; a coding agent alone is a tool, a coding agent + a review loop is a system.

### 5. Verification GATE (don't call it done until it's proven)
Delegate to **`acceptance-verifier`** (fresh context): it grades the finished work against the PLAN.md acceptance criteria, **runs the tests/build**, and returns **PASS only with evidence** (the command + its output). Demand **evidence, not assertions** of success. If the project uses `/goal` completion contracts, the acceptance criteria are the gate — the work is not "done" until tests are green and review passed. On FAIL, go back to stage 2/4.

**Re-run the gate in YOUR context, not just the delegate's.** A subagent's self-reported
"tests pass" is a starting point, not a conclusion — its environment can differ from the
orchestrator's in ways that silently mask a failure. Run the gate command yourself in the
orchestrator's terminal and capture the real stdout. If the suite needs an environment value the
delegate had set internally (a browser-binary path, a DB path, an env var), set it explicitly and
note it. Origin (2026-07-07, webshop retry): the `code-implementer` reported the Playwright e2e
suite green; re-running it in the orchestrator's context errored with "Executable doesn't exist
at ~/.agent-browser/browsers/..." because Playwright looked for chromium at a different path than
where it was installed (`~/.cache/ms-playwright`). The suite was only actually green once
`PLAYWRIGHT_BROWSERS_PATH=/home/sinep/.cache/ms-playwright` was set. The retry would have shipped a
secretly-broken e2e gate on the delegate's word alone.

### 6. Document (close the loop so docs never drift)
Update README/CHANGELOG/API docs and the PLAN/SPEC from the **final merged diff** — the implementer does this itself, or delegate user-facing docs to `long-form-writer`.

## What runs in parallel vs. sequential

- **Parallel (reads):** initial research, exploring options, competitive/security analysis, reviewing N *independent* files, multi-lens review. Cap 3–5 concurrent.
- **Sequential (writes + gates):** plan → implement → test → review-loop → verify → document. These depend on each other; don't parallelize them.

## The ship phase (commit + PR) — two rules

### Rule A: manual-test gate BEFORE the first commit

This user reviews and manually tests before the first git commit is made — not after CI, not after push. Sequence the ship phase accordingly:

1. Implement + verify (compile, grep, logic-check).
2. **Stop.** Report exactly what changed, in which files, and give the user a concrete how-to-test checklist. Do NOT commit yet.
3. User tests, gives explicit approval ("works", "looks good", "ship it").
4. THEN branch + commit + push + PR.

Committing before the user has tested forces them to review a commit they may want changed — and on this setup the user benchmarks against Claude Code, so a wrong-shape commit is a visible failure. When in doubt about whether to commit, don't; ask.

### Rule B: branch hygiene when the working tree is dirty

When implementation was done on a stale or feature branch, or `main` moved while you worked, do NOT commit on top of the dirty branch. Land changes on current main first:

```bash
# 1. Stash ONLY the files you intend to ship (not agent metadata like .hermes/)
git stash push -m "wip-<feature>" -- path/to/file1.py path/to/file2.py

# 2. Update main
git fetch origin
git checkout main && git pull origin main

# 3. Branch from current main
git checkout -b feat/<description>

# 4. Pop onto the fresh branch
git stash pop
```

**CRITICAL — re-verify after the pop.** `git stash pop` can apply without textual conflicts while the surrounding code has shifted enough to break your changes semantically (moved functions, renamed symbols, changed call sites, shifted line numbers). After popping:

- Re-run `py_compile` / type-check / lint on every changed file.
- Grep / re-read to confirm your changes still reference correct symbols and line locations against the new base.
- If main touched the same files heavily, treat it like a rebase conflict: open the file, confirm the logic still holds, fix if not.

Origin (2026-07-05, local-wisprflow lang-cycle PR): implementation sat on a stale `notemode-ui-debounce` branch (4 commits ahead) while `main` had moved 699 lines into the same three files. The stash → clean-main → new-branch → pop sequence applied without textual conflict, but without re-verification the changes would have been semantically broken against the new base (shifted line numbers, moved `transcribe()` body). Re-grep + `py_compile` after the pop caught nothing only because the changes were symbol-based — a line-number-dependent patch would have silently corrupted.

**Also:** exclude agent metadata (`.hermes/`, plan files, `PLAN.md` under `.hermes/`) from commits. They are session artifacts, not application code. `gh pr create` will warn "uncommitted change" when they sit untracked — that warning is expected and fine to ignore.

## Greenfield builds under iteration limits (critical)

When building a large multi-file project **from scratch** (scaffold + 20+ files), the pipeline above applies but there is an additional constraint the orchestrator must manage: **iteration budget.** An agent that writes all 30 files first and then discovers nothing installs or compiles has wasted its entire budget. Rules:

1. **Front-load the install.** Write `package.json` (or equivalent), run `npm install` / dependency install, and verify it succeeds BEFORE writing the rest of the source. A broken install invalidates everything downstream.
2. **Interleave build steps with scaffolding.** After the DB schema is written → run `prisma generate` + `prisma db push` immediately. After config files → run `tsc --noEmit` to catch the obvious errors early. Do NOT save all gates for the end.
3. **Get to a gate-passing skeleton fast, then add features.** Write one page, run typecheck+lint, fix. Write the next. Each checkpoint confirms the layer compiles. Writing 30 unverified files and then running the gate produces an unfixable wall of errors.
4. **Batch independent file writes in parallel** when they don't depend on each other (config files, components, pages). Don't serialize every single `write_file` — group them so tool-call budget goes to install + verify, not file creation.
5. **The gates are the deliverable, not the files.** A project with 30 files that never ran `npm run check` is NOT partially done — it's unverified. Always reserve enough budget for at least one full `typecheck && lint && test` pass with real output.

Origin (2026-07-06, clothing webshop): wrote ~30 source files sequentially (config → prisma → lib → pages → components → API routes → tests) without ever running `npm install`, `prisma generate`, or any gate. Hit the tool-calling iteration limit with a pile of unverified TypeScript. Every file had LSP diagnostics that were "expected" because deps weren't installed — but none were ever confirmed resolved. The fix is to install early and check-point every 5–10 files, not to write the whole project blind.

## Visual/UI layer refactors under test constraints

A distinct class: "redesign the visual layer without breaking existing functionality or tests." The
app already works and has test coverage; your job is to elevate the UI/UX (typography, palette,
layout, component styling) while keeping every test green. The pipeline stages still apply but with
a critical added step at the FRONT.

### Step 0: Mine the test suite for string-level contracts BEFORE writing code

Many test suites — especially in web apps without browser/Playwright testing — assert on **source
code content** rather than runtime DOM. They `fs.readFileSync()` a `.tsx` or `.css` file and check
`toContain("grid-cols-2")`, `toContain("min-h-[44px]")`, `toContain("max-w-6xl")`, `toContain("44px")`.
These are **invisible constraints** on what you can change stylistically. Rewrite a file with
prettier-but-different classes and the test fails even though the app works.

**Before writing any redesigned code:**

1. Read every test file. Grep for `toContain`, `toMatch`, `expect(.*toContain`.
2. Extract the EXACT strings/patterns each test checks for in each file it reads.
3. Build a contract: "page.tsx MUST contain `grid-cols-2`, `md:grid-cols-3`, `lg:grid-cols-4`; must
   NOT contain `w-[` or `min-w-[400`. globals.css MUST contain `44px`. AddToCartButton.tsx MUST
   contain `min-h-[44px]`."
4. When writing redesigned versions, carry those exact strings forward. You can change everything
   AROUND them (parent wrappers, sibling classes, inline styles) but the asserted strings must appear
   verbatim in the final file. `toContain` is substring match — the string just needs to exist
   SOMEWHERE in the file, so you have flexibility in HOW you use it, just not WHETHER it's there.

See `references/test-contract-mining.md` for the full worked example from this webshop redesign, including the per-file contract extraction and the list of what can vs cannot be freely changed.

### Do NOT touch the functional core

Data models, API routes, server actions, lib utilities, and business logic are OFF LIMITS. Only
edit: config (tailwind, postcss), CSS, layout/page/component TSX, and static assets (images, SVGs).
If you find yourself wanting to change a server action or API route "while you're in there," stop —
that's scope creep into the functional core that the tests are guarding.

### SVG asset regeneration

When product/illustration SVGs need upgrading from placeholders: keep the same filenames, same
viewBox/dimensions (e.g., 400×400), same `xmlns`. Use a cohesive palette drawn from the new design
system. Simple geometric silhouettes read better than detailed photorealism attempts in SVG. Group
paths with `<g transform="translate(cx,cy)">` for easy centering.

Origin (2026-07-06, webshop visual redesign): 13 code files + 12 SVGs redesigned. R11 test
checked 6 files for exact class-name substrings. Mining tests first meant every redesigned file
carried its required strings and all 20 tests passed first try — zero iterations to fix test
failures.

### Retries rejected for aesthetics: freeze the contract, redelegate only presentation

A distinct sub-case arrives as a **retry**: a deliverable was functionally complete and green,
then rejected with feedback like "looks cheap / looks like 2005 / needs modern colors, pictures,
animations." The functional layer is proven; only the visual layer is in question. The right move
is NOT a rebuild — it is a surgical, low-risk redelegation:

1. **Establish the green baseline yourself, first.** Before delegating anything, run the existing
   gate in the orchestrator's own context (the full test suite + build) and confirm it is green.
   This proves the functional layer is a safe foundation to redesign on top of. If it isn't green,
   that is a separate problem — fix it before any redesign.
2. **Freeze the contract surface explicitly in the delegation brief.** Enumerate, by name,
   everything the redesign must NOT change behavior of: every `data-testid`, the API response
   shapes, the localStorage cart JSON, `lib/` data/logic files, the test files ("DO NOT weaken,
   skip, or delete ANY test"). State which files are presentation-only (free to edit) vs.
   off-limits (functional core). The brief's job is to make regression impossible by construction.
3. **Verify contract preservation mechanically after the redesign.** Grep all `data-testid`
   attributes before and after — the set must be identical. Re-run the FULL gate (tests + build) in
   your own context. The functional tests passing first-try after a pure-presentation change is the
   proof the contract surface held.

This made a 2026-07-07 webshop retry pass on the first re-run: the v1 had 16/16 unit tests +
build green but looked dated; the retry froze every testid and API shape, redelegated only
components/CSS/SVGs, and all 16 tests passed first try because no behavior changed. The lesson
generalizes — **when a retry is about polish, freeze the contract surface so you only re-grade
one axis.**

**Impact priority when a storefront "looks dated":** distinct per-product imagery carries ~80%
of the "modern" impression — far more than the color palette or the animations. The most common
cause of a "looks like 2005" verdict is every product card showing the same generic gray
placeholder/missing-image box, which makes the whole catalog read as empty regardless of how
polished the chrome around it is. When the complaint is "looks dated," generate branded,
visually-distinct artwork per product FIRST; do not lead with palette or animations. (In the
2026-07-07 retry: 18 per-product SVGs using each brand's real colors + correct GPU-vs-motherboard
silhouettes was the single highest-leverage fix.)

## When to skip this

Trivial one-liners, config tweaks, or a single obvious fix — just make the edit. This pipeline is for features, refactors, and non-trivial bug fixes where quality matters. Adding process to a trivial change is waste; omitting it on a real change is how bugs ship.

## Verification Checklist (for the orchestrator)

- [ ] PLAN.md exists with testable acceptance criteria before code was written
- [ ] Exactly one writer touched any given file
- [ ] Tests were authored and executed red → green
- [ ] code-reviewer ran in a fresh context on the diff + criteria, and the loop reached PASS
- [ ] acceptance-verifier confirmed green with command output as evidence
- [ ] docs/PLAN updated from the final diff
- [ ] **Ship phase**: user gave explicit approval before the first commit (manual-test gate)
- [ ] **Ship phase**: if the tree was dirty or main moved, changes were stashed → landed on fresh main → re-verified (compile + grep) after the pop — NOT committed on the stale branch
