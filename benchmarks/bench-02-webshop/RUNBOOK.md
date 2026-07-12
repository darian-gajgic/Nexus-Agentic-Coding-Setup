# Bench-02 Runbook — real-world webshop benchmark (operator steps)

One client brief, three arms, YOU in the loop as the client: Claude Code + Fable 5, Claude Code + Opus 4.8, Nexus. Each system may ask you questions — you answer them live from `ANSWER-SHEET.md`. Which questions get asked (and what gets silently assumed) is part of what we measure.

**Run 1 (this runbook) = Nexus BASELINE: Super Result OFF, involvement 🚀 Full Auto, spending 🧠 Smart.** Runs 2 and 3 (later: ⚖ Balanced, then Super Result ON) repeat only Phases D–F — see Phase H.

**Budget reality:** this is a big task — expect most of a 5-hour usage window PER Claude arm. Run each Claude arm in its own fresh window (different days is fine). If an arm hits the usage cap mid-build, stop there and record "did not finish in one window" in RESULTS.md — that is a result, not a failure of the benchmark.

Every path below is absolute. Log as you go — don't reconstruct afterwards.

---

## Phase 0 — prep (5 min)

1. Run:
   ```
   mkdir -p ~/benchmarks/bench-02/fable5 ~/benchmarks/bench-02/opus48 ~/benchmarks/bench-02/nexus
   ```
2. Decide the prompt variant and use the SAME one for all three arms: `PROMPT-B.md` (recommended — same content as A, plus run-command/README, catalog-size and offline anchors so every arm's output stays testable) or `PROMPT-A.md` (your original, maximum looseness). Write the choice into RESULTS.md → Config.
3. Read `/home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-02-webshop/ANSWER-SHEET.md` completely — you must answer from it consistently in all three sessions.
4. Print the chosen prompt for copy-pasting (keep this terminal open):
   ```
   cat /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-02-webshop/PROMPT-B.md
   ```

## Phase A — Arm 1: Claude Code + Fable 5 (interactive, expect 1–3 h)

5. Run:
   ```
   cd ~/benchmarks/bench-02/fable5 && claude --model claude-fable-5
   ```
6. Type `/status`, press Enter. If session usage is above 20%, STOP — exit and restart Phase A after the window resets. Otherwise press Esc and continue.
7. Paste the ENTIRE chosen prompt (from step 4) as your first message and press Enter. Write the clock time into RESULTS.md → Arm 1 → "started at".
8. While it works, you are the client:
   - It asks a question → answer per ANSWER-SHEET (rules at the top of that file), and log the Q and your A into RESULTS.md → Arm 1 → Q&A log.
   - It asks for a permission → approve it (choose "don't ask again" options where offered). Permissions are not questions — don't log them.
9. Wait for the final summary. Write the clock time into RESULTS.md → Arm 1 → "finished at".
10. Type `/cost`, Enter → copy the output into RESULTS.md → Arm 1 → raw captures.
11. Type `/status`, Enter → note the usage % into RESULTS.md, press Esc.
12. Type `/exit`, Enter.
13. Run and copy the whole output into RESULTS.md → Arm 1 (exact tokens + API-equivalent $):
    ```
    python3 /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression/grading/claude_session_cost.py "$(ls -t ~/.claude/projects/-home-sinep-benchmarks-bench-02-fable5/*.jsonl | head -1)"
    ```

## Phase B — window gate

14. Do NOT start Arm 2 in the same usage window. Wait for the window reset (the `/status` output in step 11 shows it), or run Arm 2 tomorrow.

## Phase C — Arm 2: Claude Code + Opus 4.8 (interactive)

15. Run:
    ```
    cd ~/benchmarks/bench-02/opus48 && claude --model claude-opus-4-8
    ```
16. Repeat steps 6–13 exactly, with "Arm 2" in RESULTS.md and this cost command at the end:
    ```
    python3 /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression/grading/claude_session_cost.py "$(ls -t ~/.claude/projects/-home-sinep-benchmarks-bench-02-opus48/*.jsonl | head -1)"
    ```

## Phase D — Arm 3: Nexus run 1 (baseline: SR OFF, Full Auto, 🧠 Smart)

17. If Nexus is not running: run `nexus-up`, wait for the dashboard (`https://127.0.0.1:8777`), log in.
18. Open the Tasks/Kanban view and click **✨ Describe a task**.
19. Paste the SAME prompt into the big text box. Leave "📂 About an existing project?" on "— No: something new —". Leave **✨ Super Result UNTICKED**.
20. If the tool suggests **✦ Start Deep Plan** (or you see the ✦ Deep Plan button and the tool recommends planning), accept/click it — a real user follows the tool's recommendation. Otherwise click **✨ Plan it**.
21. Answer every clarifying/interview question per ANSWER-SHEET (answer, don't skip) and log each Q&A into RESULTS.md → Arm 3 → Q&A log. Write the clock time as "started at" when you submit the first answer round.
22. On the review/proposal card before anything is created: set involvement to **🚀 Full Auto** and spending to **🧠 Smart** (override any suggested profile — note the suggestion in RESULTS first), confirm Super Result is OFF, then approve/create the proposed task or workflow (accept a workflow if proposed — that's the tool's plan).
23. Verify the created task(s) start moving (To Do → In Progress). If a task sits in Backlog, move it to To Do.
24. WAIT until everything reaches Done/Review and stops moving. If a Decision card blocks progress in the inbox, approve the ★-recommended option and log it as an intervention. Write "finished at" (clock time) into RESULTS.md.
25. Identify and collect the run:
    ```
    ~/nexus-agent-os/.venv/bin/python /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-02-webshop/grading/collect_nexus.py list
    ```
    Find the webshop entry in the printed list (the wizard names it itself), then:
    ```
    ~/nexus-agent-os/.venv/bin/python /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-02-webshop/grading/collect_nexus.py <that wf-… or task-… id> ~/benchmarks/bench-02/nexus
    ```
    Copy the WHOLE output (statuses, wall-clock, cost ledger) into RESULTS.md → Arm 3.

## Phase E — functional test of all three shops (the objective layer, ~20 min per arm)

Do this identically per arm, in order fable5 → opus48 → nexus. For the nexus arm, the app may live in a task subfolder of `~/benchmarks/bench-02/nexus` — use the folder containing the README.

26. Open the arm's README and follow its install + start commands EXACTLY as written (create the venv/npm install it asks for). If a command fails, note the failure and the fix you needed in the checklist — a README whose commands don't work is a finding, not something to silently repair.
27. Open the shop in the browser (the README/startup output tells you the URL). Fill the arm's Functional checklist in RESULTS.md as you go:
    - Does the catalog browse? Roughly how many products, which categories?
    - Do the products look real (names you recognize, plausible specs/prices)?
28. Run the three personas from ANSWER-SHEET (P1, P2, P3) through the intelligent helper, verbatim, one at a time. For each: complete parts list? Any sanity flag from the sheet violated? PowerPoint offered and downloadable?
29. For one downloaded PowerPoint per arm, run and copy the output into the checklist:
    ```
    python3 /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-02-webshop/grading/pptx_check.py <path to the downloaded .pptx>
    ```
30. Stop the server (Ctrl+C) before testing the next arm.

## Phase F — blind judge (static review + web spot-checks; small token cost)

31. Run:
    ```
    bash /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-02-webshop/grading/prepare_judge.sh ~/benchmarks/bench-02/fable5 ~/benchmarks/bench-02/opus48 ~/benchmarks/bench-02/nexus /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-02-webshop/PROMPT-B.md
    ```
    (last argument = the prompt file you actually used in step 2)
32. Run:
    ```
    cd /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-02-webshop/grading/out/blind && claude --model claude-fable-5 "$(cat JUDGE-PROMPT.txt)"
    ```
    Approve read/web permissions as asked. Copy the scores + ranking into RESULTS.md → Judge verdict, then `/exit`.
33. Only NOW reveal the mapping and write it under the verdict:
    ```
    cat /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-02-webshop/grading/out/mapping.txt
    ```

## Phase G — wrap-up

34. Run and copy both lines into RESULTS.md → Config (plus today's date):
    ```
    claude --version && git -C ~/nexus-agent-os log -1 --oneline
    ```
35. Fill the Scoreboard in RESULTS.md.
36. Start a Claude session in `/home/sinep/Nexus-Agentic-Coding-Setup` and say: `Analyze the bench-02 run-1 results in benchmarks/bench-02-webshop/RESULTS.md` — that session writes the comparison and logs WINS/LESSONS.

## Phase H — later runs (2 = ⚖ Balanced, 3 = Super Result ON)

The Claude arms are FROZEN after run 1 — never re-run them; all later runs compare against the same two baselines.

37. Run 2: repeat Phases D–F only, with spending **⚖ Balanced** in step 22 (everything else identical), collecting into `~/benchmarks/bench-02/nexus-run2` (pass that as the collector's dest) and a fresh "Arm 3 run 2" section in RESULTS.md.
38. Run 3: repeat Phases D–F only, with **✨ Super Result TICKED** in step 19 (keep 🧠 Smart in step 22 unless we decide otherwise then), collecting into `~/benchmarks/bench-02/nexus-run3`.
39. Caveat to record with runs 2–3: Nexus learns between runs (exemplars/lessons from run 1 can inform run 2) — improvements are "config + accumulated learning", not config alone.
