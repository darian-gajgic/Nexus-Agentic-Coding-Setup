# OPERATOR GUIDE — Final Readiness Campaign (2026-07-13)

This is YOUR complete step-by-step guide. It is self-contained: every step is one literal action —
a command to paste, a button to click, or a thing to wait for with its expected result. You do not need to
read anything else to execute it. Background documents (only if you want detail):
`PRODUCTION-READINESS-REVIEW-PLAN-2026-07-13.md` (the campaign the Claude sessions execute) and
`Production-Readyness-Review-1/TOOL-DOCUMENTATION-2026-07-13.md` (what every feature is for + research verdicts).

Rules that keep you safe throughout:
- Never run two campaign sessions at the same time.
- Never `git checkout` another branch in this repo while the service runs (it swaps the RUNNING code).
- Restart the service only with `systemctl --user restart nexus` — never by running start.sh directly.
- If a fix session proposes something you don't understand, reply: "Write it up as a finding instead."

---

## PHASE 0 — NOW: confirm the judge-overhaul is fully landed

**Step 1.** Open a terminal and run:
```
cd ~/Nexus-Agentic-Coding-Setup
```

**Step 2.** Run:
```
git status --short
```
EXPECTED: no lines starting with `M`. Lines starting with `??` (untracked files) are fine.
- If you see `M app/...` or `M setup/...` lines: the overhaul implementation session is NOT finished.
  Go to that session's window and let it finish (if it is idle, send it: `Finish the remaining work from the
  judge-overhaul plan, run the gates, commit and push.`). Then repeat Step 2 until clean. Do not continue
  before this is clean.

**Step 3.** Run:
```
git log --oneline -8
```
EXPECTED: commits about the judge overhaul near the top (e.g. `2b7200a feat(mode-ladder): ...` and
`571d59b feat(judge-loop): ...`), plus possibly newer ones (e2e gates). If they are missing → same as Step 2:
the overhaul has not landed; wait.

**Step 4.** Open `https://127.0.0.1:8777` in your browser (if the page does not load, that is fine — the
stack may be off; you start it in Step 8). If it loads: check the Tasks board — EXPECTED: no benchmark run or
other big task currently streaming. If one is running, wait for it to finish (this campaign restarts the
service several times and would corrupt the run).

## PHASE 1 — Preflight (~15 min)

**Step 5.** Commit the campaign documents:
```
git add PRODUCTION-READINESS-REVIEW-PLAN-2026-07-13.md Production-Readyness-Review-1/ SECURITY-SWEEP-PLAN-2026-07-12.md CODE-REVIEW-FINDINGS-2026-07-12.md && git commit -m "docs: final readiness review campaign 2026-07-13 (plan + tool documentation + operator guide)"
```
EXPECTED: the pre-commit check runs for about a minute, prints `ALL CHECKS PASSED: N/N`, and the commit is
created.
- If the pre-commit check FAILS: do NOT bypass it. That means the overhaul left something broken — send the
  failure output to a quick Claude session with: `verify.sh fails after the judge-overhaul landing — fix
  exactly this.` Then redo Step 5.

**Step 6.** Run:
```
git push
```
EXPECTED: `main -> main` pushed without errors.

**Step 7.** Skip this step if the dashboard already loaded in Step 4.

**Step 8.** Start the stack:
```
nexus-up
```
EXPECTED: it starts ollama, the qdrant/langfuse containers, the timers and the nexus service, then opens
`https://127.0.0.1:8777` in the browser. If the browser shows a certificate warning: click Advanced →
Proceed (the self-signed certificate is expected).

**Step 9.** Run:
```
python3 setup/guardian/guardian.py
```
EXPECTED: output ends with `overall=OK` and shows 8/8 core-mods applied.
- If NOT 8/8: run `python3 setup/guardian/guardian.py --apply` once, then re-run Step 9. Still failing →
  fix this first (a quick Claude session with the output); the campaign result is worthless without the mods.

**Step 10.** In the browser, log in once as your owner account. (Seeing `401` on `/api/health` for anonymous
requests is normal — not an error.)

**Step 11.** Make a CONSISTENT database backup (a plain copy would be a torn backup — this was one of today's
research findings):
```
rm -f app/nexus.db.bak-final-review && app/.venv/bin/python -c "import sqlite3; sqlite3.connect('app/nexus.db').execute(\"VACUUM INTO 'app/nexus.db.bak-final-review'\")"
```
EXPECTED: no output. Then run `ls -la app/nexus.db.bak-final-review` — EXPECTED: the file exists and is
roughly the size of `app/nexus.db`.

**Step 12.** Run:
```
df -h /home | tail -1
```
EXPECTED: more than 15G in the "Avail" column. If less, free space first.

**Step 13.** Physical preparation:
- Plug in / test the microphone you will use (you will speak to JARVIS in Attended Block 1).
- Open `https://127.0.0.1:8777` once on your PHONE (via Tailscale) and confirm it loads — you will need the
  phone in Attended Block 2.

**Step 14.** Timing decision: the heaviest GLM phase starts about 4 hours after launch. Launch in the morning
or another off-peak window if you can (GLM quota burns ~3× at peak; upstream "1305" errors are load-shedding).

## PHASE 2 — Launch Session A (the big review)

**Step 15.** Run:
```
claude --model claude-fable-5 --permission-mode acceptEdits
```
- If that errors about the model: run `claude --permission-mode acceptEdits`, then type `/model` and select
  Fable 5.

**Step 16.** Paste this prompt EXACTLY and send:
```
Execute PRODUCTION-READINESS-REVIEW-PLAN-2026-07-13.md — Session A, ultracode.
You are the reviewer, not the fixer: findings are PROPOSED (only the labeled batch-0 one-liners get
committed, at the end, after my Block-2 approval). Zero trust in prior test reports — re-verify everything
yourself at runtime, and judge design against Production-Readyness-Review-1/TOOL-DOCUMENTATION-2026-07-13.md
(its verdicts are hypotheses to confirm or refute). Work the phases in order; after every phase update
Production-Readyness-Review-1/PROGRESS.md and flush findings to FINAL-REVIEW-2026-07-13.md. Ping me ONLY at
the two ATTENDED BLOCKS and for cost-risky approvals; play the client yourself via the plan's ANSWER-SHEET
and log every question. Functional QA only — no security probing, per the plan's §1 guardrail hygiene.
Start with Phase 0 and report the stub-sweep result before anything else.
```

**Step 17.** Wait ~10 minutes and check the session once. EXPECTED: it has confirmed the plan, created
`Production-Readyness-Review-1/PROGRESS.md` and the FINAL-REVIEW skeleton, and reported a CLEAN stub-sweep.
Now you can leave the machine. Total Session A runtime: ~10–13 hours; it needs you only twice (~45 min total).

## PHASE 3 — DURING Session A: the only 4 things it will ask of you

**Ping type 1 — "ATTENDED BLOCK 1 ready" (~4h in, ~20 min).** Do these 9 steps at the DESKTOP:
1. Open `https://127.0.0.1:8777` (accept the certificate if asked).
2. Log in as the owner.
3. Click through ALL nav tabs top to bottom. Type anything ugly, confusing or broken into the session — it
   records your words verbatim.
4. Open the J.A.R.V.I.S tab. Click the mic button. Say: "What is on the board right now?" —
   EXPECTED: your words appear as transcript, a spoken reply plays, the avatar mouth moves while talking.
5. Repeat step 4 once more (it must work 2 of 2 times).
6. While it is speaking, start talking over it — EXPECTED: the voice stops and it listens to you.
7. Click into a text field (e.g. the Notes panel), press your dictation key, speak one sentence, press the
   key again — EXPECTED: a small overlay appeared while recording, and your sentence is typed into the field.
8. Meetings tab → start meeting recording, say two sentences, stop it — EXPECTED: a transcript appears in the
   Meetings tab.
9. The session now shows its journey plan + spend estimate. Reply `GO` (or state changes). Also answer any
   short [UNSURE] questions it queued — brief answers, only what is asked.

**Ping type 2 — occasional short questions.** Answer in one short sentence, only what is asked. If you don't
care, reply: "You decide — note the assumption."

**Ping type 3 — "ATTENDED BLOCK 2 ready" (~9–11h in, ~25 min).** Do these 7 steps:
1. On your PHONE, open the dashboard and log in as the owner.
2. On the phone: open the Tasks board, open one task's detail and scroll it, decide one approval card, open
   J.A.R.V.I.S. Tell the session everything that is broken or awkward on the phone.
3. On the desktop: the session shows 3 finished deliverables. Read each and answer: "Would I send this to a
   client?" (yes / yes-with-edits / no — plus one line why).
4. Decide the approval/decision cards that piled up during the journeys (approve or reject each).
5. Read the draft scorecard for the 10 product goals. Say where you disagree.
6. It shows a small diff of trivial one-line fixes ("batch-0"). Reply `COMMIT` to allow or `SKIP`.
7. It lists everything it created (all named `campaign-...`). Confirm deletion, or name what to keep.

**Ping type 4 — the final message.** It states the verdict, the top-5 findings and where all documents are.
Session A is done.

**If the session dies / the PC sleeps / it says context is full:**
```
cd ~/Nexus-Agentic-Coding-Setup && claude --continue
```
Then paste EXACTLY:
```
Resume the production-readiness campaign. Read Production-Readyness-Review-1/PROGRESS.md and
PRODUCTION-READINESS-REVIEW-PLAN-2026-07-13.md, run git status and the stub-hygiene sweep, then re-do the
FIRST unticked PROGRESS item from scratch and continue the plan. Do not trust any in-context memory of prior
progress over the files on disk.
```
If `--continue` finds nothing to resume: run `claude`, type `/model`, pick Fable 5, paste the same text.
EXPECTED either way: it re-reads PROGRESS.md and continues where the files say it stopped. This is safe to
repeat any number of times.

## PHASE 4 — AFTER Session A: read and approve (~30 min)

**Step 18.** Read `Production-Readyness-Review-1/FINAL-REVIEW-2026-07-13.md` — at minimum section 1
(executive verdict) and the P0/P1 findings.

**Step 19.** Read `Production-Readyness-Review-1/FIX-RUNBOOK-2026-07-13.md`. If you disagree with a batch,
delete or reorder it directly in the file.

**Step 20.** Run:
```
git add Production-Readyness-Review-1 && git commit -m "review: Session A findings + fix runbook + improvements" && git push
```
EXPECTED: pre-commit passes, push clean.

## PHASE 5 — Fix sessions (one batch at a time, in the runbook's order)

Repeat Steps 21–24 for every batch in FIX-RUNBOOK, top to bottom. Finish ALL P0 batches before using the tool
for real work again; P1 batches can run during the week; P2 whenever.

**Step 21.** Run:
```
claude --permission-mode acceptEdits
```
Then type `/model` and select the model named in the batch header (Opus 4.8 unless the header says Fable 5;
every REBUILD batch = Fable 5).

**Step 22.** Paste this prompt with the batch ID filled in (e.g. `B1` or `R1`):
```
Execute batch <BATCH-ID> of Production-Readyness-Review-1/FIX-RUNBOOK-2026-07-13.md.
Read the batch entry and the finding entries it cites in FINAL-REVIEW-2026-07-13.md first. FIX batch: fix
exactly that scope — nothing else; a deeper problem you uncover becomes a new finding write-up, not a bigger
fix. REBUILD batch: present the design note and wait for my GO, then build it properly in a git worktree
(main stays live), gates green in the worktree, land as one merge commit. Before finishing: run the batch's
verify commands, then bash scripts/verify.sh from app/ (green), then systemctl --user restart nexus and
re-drive the changed surface on https://127.0.0.1:8777. Tick the batch in FIX-RUNBOOK and PROGRESS.md. If you
ran any e2e gate, re-check the stub-hygiene settings keys before you finish.
```
For a REBUILD (R-) batch: it will first show you a short design note — read it and reply `GO` (or object).

**Step 23.** When the session reports done, run:
```
git log --oneline -3
```
EXPECTED: one new commit for this batch at the top.

**Step 24.** After the LAST batch of the day, run:
```
git push
```

## PHASE 6 — Session C: the independent re-check

**Step 25.** Preferably off-peak. Run:
```
claude --model claude-fable-5 --permission-mode acceptEdits
```

**Step 26.** Paste EXACTLY:
```
Execute PRODUCTION-READINESS-REVIEW-PLAN-2026-07-13.md — Session C, the re-verify judge, ultracode.
Refute by default: the fix sessions' reports and commit messages are claims, not evidence. Re-run the full
gate sweep personally (plan §6 P1 order, outputs to evidence/), re-run the stub-hygiene sweep, and re-drive
every fixed or rebuilt surface on the live HTTPS UI yourself. Verify every REBUILD against its design note
and must-not-regress list. Mark every FIX-RUNBOOK item VERIFIED-FIXED / STILL-BROKEN / DEFERRED-OK with one
evidence line each, update the scorecards in FINAL-REVIEW-2026-07-13.md (marked post-fix), and end with
exactly one line: VERDICT: SHIP or VERDICT: REVISE plus the blocking list. You never edit code. The security
row stays PENDING (separate sweep).
```
EXPECTED after ~2–3 hours: a final line `VERDICT: SHIP`, or `VERDICT: REVISE` with a blocking list.
- On `REVISE`: the blocking list becomes new batches — ask the session to append them to FIX-RUNBOOK, then
  repeat PHASE 5 for those batches, then repeat PHASE 6. Loop until `SHIP`.

## PHASE 7 — Close-out

**Step 27.** Run:
```
git add -A Production-Readyness-Review-1 && git commit -m "review: campaign complete — Session C verdict" && git push
```

**Step 28.** In any Claude session in this repo, say:
```
Update project memory: readiness campaign complete, verdict SHIP, security sweep still pending.
```
(Replace SHIP if the verdict was different.)

**Step 29.** The security check is still open by design. In a NEW small session on **Opus 4.8** (type
`/model` and pick Opus 4.8 — deliberately not Fable 5), say:
```
Execute SECURITY-SWEEP-PLAN-2026-07-12.md
```
Readiness is only final after this session also finishes.

**Step 30.** Optional, after one week of stable daily use:
```
rm app/nexus.db.bak-final-review
```

---

## If something goes wrong — quick table

| Situation | What you do |
|---|---|
| Session died / PC slept / context full | PHASE 3 resume block (`claude --continue` + resume text) |
| Session reports a guardrail refusal | Nothing — it logs, skips that item, continues (by design) |
| Lots of "1305" / quota errors during journeys | Nothing — it waits and retries off-peak; not a failure |
| Session asks a design question you can't judge | Reply: "Write both options into the findings, pick the safer one for now." |
| A fix batch broke something | The batch is ONE commit — tell the session: `git revert` that commit, then re-run the batch fresh |
| Verdict stays REVISE after 2 loops | Read the blocking list yourself; decide per item: fix again, or accept and tell Session C to mark it DEFERRED-OK with your reason |
