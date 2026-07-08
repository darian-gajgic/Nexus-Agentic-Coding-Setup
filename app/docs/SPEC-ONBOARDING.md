# In-Nexus Business-Brain onboarding — guided, per-user

Operator request 2026-07-08: replace the "open a terminal → `cd ~/knowledge &&
claude` → say 'run the onboarding'" flow with a **guided onboarding inside
Nexus** that takes a new user by the hand — explains what the Business Brain
is, what every input is for, and **how each answer changes the system's
behavior** — and maps the result to **whoever runs it**, individually.

## R1 — Source of truth: templates + per-user answers

- R1.1 The pristine questionnaire lives in
  `~/knowledge/templates/{BUSINESS-CONTEXT,STYLE-VOICE}.template.md`
  (snapshotted from the unfilled originals, committed to the knowledge repo).
  The wizard schema derives from the TEMPLATES, so onboarding keeps working
  after the live files are filled, and can be re-run to revise answers.
- R1.2 `{{FILL: hint}}` slots are parsed with a multi-line-aware regex
  (`re.DOTALL` — one STYLE-VOICE slot spans two physical lines). Each slot:
  `slot_id` (`context:NN` / `style:NN`), its section (nearest `##`/`###`
  heading), a label (the physical line up to the slot, cleaned of markdown),
  and the hint.
- R1.3 Answers are stored per user in `onboarding_answers(user_id, slot_id,
  answer, na, updated_at)` (PK user_id+slot_id) — partial saves are the norm
  (the wizard auto-saves every step; users can stop and resume any time).
  `onboarding_state(user_id, applied_at, target_dir)` records the last apply.
- R1.4 Every section carries a hand-authored **impact explanation** (module
  `onboarding.py`): what agents do with these lines, what breaks or stays
  generic while they're blank, one concrete example of a deliverable that
  changes. This is the "take the user by the hand" layer.

## R2 — Per-user mapping (whoever executes it)

- R2.1 **u_owner** applies to the CANONICAL files `~/knowledge/*.md` — the
  home directory is the operator's, and evals/judge/specialists read these.
- R2.2 **Every other user** applies to an overlay
  `~/knowledge/users/<user_id>/{BUSINESS-CONTEXT,STYLE-VOICE}.md`, rendered
  from the same templates with THEIR answers.
- R2.3 Dispatch framing resolves per task owner:
  `hermes_dispatch._knowledge_paths(task)` returns the overlay paths when both
  overlay files exist for `task.user_id`, else the canonical paths. The
  domain-framing block names the resolved paths explicitly and states they
  override any defaults named in specialist definitions. PLAYBOOK/RUBRIC stay
  shared — they are craft knowledge, not identity.
- R2.4 Answers and status are private: `GET /api/onboarding` returns only the
  calling user's answers; there is no cross-user read or write path.
- R2.5 Apply is git-safe: if the knowledge repo is dirty, a snapshot commit
  (`pre-onboarding snapshot`) is made first; the rendered files are then
  written and committed (`onboarding(<user>): personalize business context +
  voice — N slots`). Nothing hand-edited is ever lost — it is in git history.

## R3 — Endpoints

- `GET  /api/onboarding` — schema (sections with explanations + questions,
  both files, in file order) + the caller's saved answers + counts
  (total/answered/na) + `applied_at` + resolved `target_dir` + `is_owner`.
- `POST /api/onboarding/answers` `{answers: {slot_id: {text, na}}}` — upsert;
  empty text + na=false deletes the row (un-answer). 400 on unknown slot_id.
- `POST /api/onboarding/apply` — renders both files from template + answers
  (answered → text; na → `n/a — marked not applicable during onboarding`;
  unanswered → the `{{FILL: hint}}` slot stays), writes to the caller's
  target, git-commits, records `onboarding_state`. Returns
  `{written, replaced, remaining, target_dir, summary}`.
- `GET /api/onboarding-status` (existing shape kept — real-dispatch gate
  asserts `total`/`done`): now per-user. For a user whose target files exist:
  count `{{FILL:` in THEIR files (file truth — hand edits count). Otherwise:
  template slot count minus their saved answers. `cta` drops the terminal
  text; the banner now opens the wizard.
- Test hook (gates only, default off): settings `onboarding.root` redirects
  the knowledge root exactly like `evals.corpus_root`; restored by the gate.

## R4 — The wizard UI

- R4.1 Entry points: the dashboard CTA banner (now a **🚀 Start the guided
  onboarding** button + "answers save as you go"), and Settings → Business
  Brain (always available, also for revising answers later).
- R4.2 Flow: **Welcome step** (what the Business Brain is, which agents read
  it and when, what happens while it is blank, where THIS user's answers land
  — canonical vs personal overlay) → **one step per section** (only sections
  that contain slots): impact explanation, then each question as label + hint
  placeholder + textarea + "not applicable" toggle → **Review step** (every
  section with answered/na/open counts, jump-back links, unanswered listed) →
  **Apply** (confirm-gated; shows exactly which files will be written) →
  **Success step**: what was written where, what improves immediately, and a
  suggested first task to feel the difference.
- R4.3 Progress header on every step: `Section i/n · answered/total filled`.
  Next auto-saves the step's inputs (resumable); Back never loses input.
- R4.4 The banner disappears when the user's status says done; Settings keeps
  the re-edit entry point.

## R5 — Docs

- `~/knowledge/ONBOARDING.md` rewritten: the Nexus wizard is the primary
  path; the Claude-CLI interview stays as the alternative for terminal users.
- Nexus `CLAUDE.md` documents the new gates.

## Verification

- Static: verify.sh section 14 (module functions, endpoints, tables, framing
  helper, wizard functions, templates exist, ?v bump).
- Runtime: `scripts/verify_onboarding_e2e.py` — schema parse (33 slots, every
  section explained), partial save + resume, un-answer, apply for owner
  (canonical files rendered, slots replaced, git commit present, dirty-tree
  snapshot first), apply for a probe member (overlay under `users/<uid>/`),
  answer isolation both directions, `_knowledge_paths` resolves overlay for
  the member's task and canonical for the owner's, status endpoint per-user,
  `onboarding.root` restored, self-cleaning.
- Runtime UI: `scripts/verify_onboarding_ui.py` — banner button, welcome step,
  answer + auto-save on Next (DB row proof), n/a toggle, review counts, no
  console errors.
- Existing suites stay green (real-dispatch's onboarding-status check keeps
  its shape).
