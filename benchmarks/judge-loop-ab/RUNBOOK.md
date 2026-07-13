# Judge-Loop A/B Replay — proof-of-payback runbook

Purpose: measure what the 2026-07-13 judge-loop overhaul actually buys on ONE
real task, old loop vs new loop, before bench-02 runs 2–3 spend real quota on
it. **Success gate: ≥40% frontier-$ reduction at a non-inferior blind pairwise
verdict, with ≤1.2× GLM tokens.**

Cost estimate: 2 full spec-task runs ≈ 10–25M GLM tokens + $2–8 Opus
(subscription quota). Run it inside one 5h window.

## Seed task

Clone the FIFA spec brief (`task-bb5af00e`, workspace
`app/workspaces/task-bb5af00e/`) — its brief, domain (software-engineering),
attachments and a pending REVISE history exist, so it is a known judge-hard
case. Create TWO fresh tasks via the Kanban ✨ wizard with the same brief text
(copy `title` + `description` from the task detail), same domain, **Balanced +
Assisted**, high_stakes ON, into two fresh scratch repos (or no repo — then
both workspace-mode). Do NOT reuse the original task (its loop state is spent).

## Arm OLD (loop-mechanics emulation of the pre-overhaul loop)

The old cjudge prompt is preserved in git — extract it once:

    git -C ~/Nexus-Agentic-Coding-Setup show 2b7200a~2:setup/bin/cjudge > /tmp/cjudge-old
    chmod +x /tmp/cjudge-old

Settings (Settings tab or API) BEFORE dispatching arm OLD's task — record each
prior value; every key below is restored in the "restore" step:

| key | OLD arm value |
|---|---|
| judge.cmd | `bash /tmp/cjudge-old {file} {domain}` |
| judge.pregate | 0 |
| judge.delta_rejudge | 0 |
| judge.max_runs | 99 |
| judge.screen | off |
| dispatch.rework_continue_session | 0 |
| dispatch.retry_slice_frac | 1.0 |
| dispatch.rework_ceiling_mult | 99 |
| frontier.task_cost_cap_usd | 0 |
| super.escalation | 0 |

Dispatch arm OLD's task (drag to To Do). Let the loop run to a terminal state
(SHIP, parked approval, or your reject-limit — do NOT reject more than once).

## Arm NEW

Restore ALL keys above to defaults (Settings → each key → clear to default;
defaults: cjudge {file} {domain} / 1 / 1 / 4 / interior / 1 / 0.5 / 2.0 / 3.0 / 1).
Dispatch arm NEW's task. Same operator behavior (answer nothing extra; if a
decision card appears, choose "accept as-is" only at a true dead end).

## Collect (per arm)

    .venv/bin/python - <<'EOF'
    import sqlite3, json, sys
    tid = sys.argv[1] if len(sys.argv) > 1 else "task-XXXX"
    db = sqlite3.connect("file:app/nexus.db?mode=ro", uri=True); db.row_factory = sqlite3.Row
    t = dict(db.execute("SELECT tokens_used, budget_tokens, judge_round, judge_verdict, frontier_tokens, frontier_cost_usd FROM tasks WHERE id=?", (tid,)).fetchone())
    runs = [dict(r) for r in db.execute("SELECT kind, tokens, cost_usd FROM frontier_ledger WHERE task_id=?", (tid,))]
    disp = db.execute("SELECT COUNT(*) n, COALESCE(SUM(tokens_in+tokens_out),0) tok FROM dispatches WHERE task_id=?", (tid,)).fetchone()
    print(json.dumps({"task": t, "frontier_runs": runs, "dispatches": dict(disp)}, indent=1))
    EOF

Record per arm: GLM tokens, dispatch count, judge invocations + frontier $,
judge rounds, wall-clock, terminal verdict.

## Blind pairwise judgment

Give a FRESH Claude session both final deliverables as `A.md`/`B.md`
(randomize which arm is which; note the mapping privately):

> Two teams produced this spec deliverable from the same brief (attached).
> Judge them pairwise against the software-engineering rubric at
> ~/knowledge/domains/software-engineering/RUBRIC.md: which one ships, or tie?
> Verdict format: WINNER: A|B|TIE + 3 decisive differences with quotes.

## Verdict

- frontier $ NEW ≤ 0.6 × OLD → cost gate PASSED
- pairwise TIE or NEW wins → quality gate PASSED
- GLM tokens NEW ≤ 1.2 × OLD → efficiency gate PASSED
- Any gate failed → triage before bench-02 runs 2–3; most reversible knobs
  first: `judge.screen=off`, `dispatch.rework_continue_session=0`.

Log the outcome to `RESULTS.md` here + a WIN/LESSON entry.
