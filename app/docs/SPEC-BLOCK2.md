# Block 2 — Review v2 · Galaxy memory editing · PR creation

Roadmap block 2 (agreed 2026-07-08). Three features, one theme: **the operator's
review is a first-class control surface — inspect precisely, correct precisely,
and ship precisely.**

## R1 — Review v2: side-by-side diffs, syntax highlighting, per-line comments

The review modal becomes a real code-review surface that beats GitHub for the
retry loop: comments made on lines flow straight into the next attempt's
framing.

- R1.1 **Line anchors.** `review.parse_unified()` tracks real file positions:
  every hunk line carries `o` (old line no) and/or `n` (new line no) parsed
  from the `@@` headers. Context lines carry both; `-` only `o`; `+` only `n`.
  Both diff sources (git `changes.diff`, difflib workspace comparison) emit
  identical shapes.
- R1.2 **Server-side syntax highlighting (Pygments — already in the venv; no
  build step, no CDN).** `review.highlight_file(f)` lexes by filename and
  highlights each hunk **per side** (old side = context+deletions, new side =
  context+additions, so multi-line constructs survive within a hunk), attaching
  `h` = Pygments HTML to each line. Pygments escapes all content — `h` is the
  ONLY server-HTML the frontend may inject raw; everything else stays `esc()`d.
  Fallback on any lexer/count mismatch: no `h`, UI renders plain `s`.
- R1.3 **Side-by-side view.** The review pane gets a unified ⇄ split toggle
  (persisted in `localStorage.nexusReviewMode`). Split pairs deletion runs with
  addition runs row-wise (classic split algorithm), line-number gutters on both
  sides. Images keep the existing old/new metadata panel.
- R1.4 **Per-line comments.** New table `review_comments(id, task_id, user_id,
  file_path, side old|new, line_no, line_text, body, status open|consumed,
  consumed_at, created_at)`. Endpoints (all `_owned_task`-gated, fail-closed):
  - `GET  /api/tasks/{id}/review/comments`
  - `POST /api/tasks/{id}/review/comments` {file_path, side, line_no,
    line_text?, body} (body ≤2000 chars, ≤200 open per task)
  - `PATCH/DELETE /api/tasks/{id}/review/comments/{cid}` (edit open ones /
    remove any)
  UI: a `+` affordance on every diff line (both views) opens an inline composer;
  threads render under their anchored line; the files list and modal footer show
  open-comment counts.
- R1.5 **Comments feed the retry.** `_retry_task()` (the single feedback
  chokepoint — operator retry, approval-reject, and loop-engine rounds all
  flow through it) appends all OPEN comments to the outgoing feedback as a
  `Reviewer LINE COMMENTS (address EVERY one)` block —
  `- <file>:<line> [side] "<line excerpt>" → <comment>` — then marks them
  `consumed` (kept for audit, shown dimmed in the UI). `retry_feedback`
  truncation raised 4000 → 8000 chars to make room; `build_framing` injection
  is unchanged (comments ride the existing RETRY block).
- R1.6 The review modal footer shows `💬 N open comments` and a
  **↻ Retry with this feedback** button (confirm-gated) when comments exist.

## R2 — Galaxy memory editing (edit / merge / delete, confirm-gated)

Memory nodes stop being read-only exhibits. Clicking a node (galaxy) or a row
(Memory hub list) opens a memory modal with Edit / Merge / Delete.

- R2.1 **Node selection.** `memory3d.js` gains raycast click-select:
  `Memory3D.mount(el, data, {onSelect})` invokes the callback with the node.
  Hover panel unchanged. Same modal reachable from the Memory hub list rows.
- R2.2 **Ownership policy (fail-closed, mirrors Block 1):** points tagged
  `payload.user == me` → editable by me. Untagged points (shared/team by
  design) → only `role='owner'` users. Foreign-tagged → 404 (existence not
  disclosed). Applies identically to edit, merge, and delete.
- R2.3 **Endpoints:**
  - `PATCH  /api/memory/{point_id}` {text} — edit text
  - `DELETE /api/memory/{point_id}` — delete point
  - `POST   /api/memory/merge` {ids: [2..8], text} — create merged point, then
    delete the sources (only after the add succeeded)
  All confirm-gated in the UI (edit = explicit save, delete = confirm dialog,
  merge = editable merged-text preview + confirm). Every mutation clears
  `_MEM3D_CACHE` and broadcasts `memory_updated` to the acting user's sockets.
- R2.4 **Mechanism: through the mem0 backend, never raw payload writes.**
  `~/.hermes/scripts/mem0_curate.py` (guardian-tracked golden) gains:
  - `update --id <mem-id> --text "…"` → `p._backend.update(id, text)` — mem0
    re-embeds via ollama `nomic-embed-text` (768-d) and PRESERVES the existing
    payload (user/client/agent tags survive; verified in mem0 2.0.10 source).
  - `add` learns optional `--metadata '<json>'` (merged-point stamps:
    `user`, `channel:"nexus"`, `attributed_to:"user"`, `source:"merge"`) and
    `--agent-id` becomes optional (merged user memories carry no agent scope).
  Guardian golden + manifest sha256 updated in ~/hermes-guardian AND mirrored
  in ~/hermes-team-setup (commit, operator pushes).
- R2.5 Merge default text = the source texts joined by newlines; the operator
  edits it in the preview before confirming. Sources are shown with their
  stored dates. Merging points with mixed ownership follows R2.2 per point
  (one foreign point in the set → 404 for the whole merge).

## R3 — PR creation for repo tasks + code-map in repo framing

- R3.1 **`POST /api/tasks/{id}/pr`** (`_owned_task` + `_visible_repo_path`):
  for a repo task whose `nexus/<slug>` branch exists with commits ahead of
  base. Pushes the branch (`git push -u origin nexus/<slug>`) and runs
  `gh pr create --head nexus/<slug> --base <base> --title <task title>
  --body <generated>`; if a PR already exists for the branch, returns the
  existing URL (`gh pr view`). 409 with a "Publish first" hint when the repo
  has no origin remote. Result URL stored in new column `tasks.pr_url` and
  returned; broadcast `task_updated`.
- R3.2 **PR body** = task brief (truncated) + review stats (files/+/−, from
  `build_task_review`) + open/consumed review-comment count + "Created by
  Nexus Agent OS" footer.
- R3.3 **UI:** task detail modal shows **⬆ Create PR** (confirm-gated) for
  repo tasks that have produced work, replaced by a **↗ View PR** link once
  `pr_url` is set.
- R3.4 **Test hook (gates only, default off):** settings `pr.cmd` — overrides
  the `gh` invocation exactly like `judge.cmd` stubs the judge. The e2e gate
  pushes to a local bare origin and stubs only `gh`. Restored by the gate;
  never set in production.
- R3.5 **Code-map in repo framing.** `_repo_context()` additionally builds a
  compact `code_map` from `git ls-files` in the worktree: top-level layout
  with per-directory file counts, key files, and a language histogram, capped
  at ~4000 chars / 150 entries. `build_framing` injects it as a
  `CODE MAP (repository layout)` block right after the conventions file, so
  agents stop re-discovering the tree with shell calls every round.

## Verification

- Static: `bash scripts/verify.sh` (new Block-2 checks: line-number emission +
  highlight function in review.py, comments endpoints + retry wiring in
  server.py, memory edit/merge/delete endpoints + ownership helper, pr
  endpoint + pr.cmd hook, code_map in hermes_dispatch, mem0_curate update
  subcommand present in the Hermes tree, app.js/memory3d/style function +
  class checks, `?v=` bumps).
- Runtime: `.venv/bin/python scripts/verify_block2_e2e.py` — review JSON
  line-numbers + highlight on a fixture diff; comment CRUD + cross-user 404;
  retry consumes comments into `retry_feedback` verbatim block; memory
  edit/merge/delete round-trip against real qdrant+ollama on probe points
  (payload preserved, vector re-embedded, sources deleted after merge) +
  member-vs-untagged 403/owner allowed + foreign 404; PR flow against a
  scratch repo with a local bare origin + stubbed `gh` (branch pushed, URL
  stored, foreign task 404); code-map content in framing. Self-cleaning,
  `_gate_auth`-based, multi-user-preserving.
- Runtime UI: `.venv/bin/python scripts/verify_block2_ui.py` — Playwright:
  unified render with gutters + highlight spans, split toggle, add a line
  comment from the UI, footer count, memory modal (edit/delete/merge buttons,
  confirm gating), Create-PR button visibility.
- Existing suites must stay green: verify.sh 167+, multiuser 83, agentic 30,
  playwright 11, v3 UI 24, interactions 24, real-dispatch 54, block3 33+15.
