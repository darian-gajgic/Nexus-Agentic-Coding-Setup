# Bench-01 Runbook — first-impression benchmark (operator steps)

One identical prompt, three arms: Claude Code + Fable 5, Claude Code + Opus 4.8, Nexus (Super Result ON, Full Auto + Optimal). Then objective grading + cost comparison. This is the small pilot of the Phase-8 methodology (`QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md` §7) — n=1 per arm, directional only.

Budget guard: the task is sized to finish well under 50% of one 5-hour Pro window per Claude arm. Both Claude arms share the same window — step 10 checks usage before Arm 2.

Every path below is absolute. `KIT` in prose means `/home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression` — but the commands always spell it out.

---

## Phase 0 — prep (1 min)

1. Run:
   ```
   mkdir -p ~/benchmarks/bench-01/fable5 ~/benchmarks/bench-01/opus48 ~/benchmarks/bench-01/nexus
   ```
2. Run and confirm it prints the spec (starts with `# Build \`gridcalc\``):
   ```
   head -3 /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression/PROMPT.md
   ```

## Phase A — Arm 1: Claude Code + Fable 5 (unattended, ~10–30 min)

3. Run (one line; `--dangerously-skip-permissions` is acceptable here because the session works in an empty scratch directory on a stdlib-only task — do not reuse the flag elsewhere):
   ```
   cd ~/benchmarks/bench-01/fable5 && claude --model claude-fable-5 --dangerously-skip-permissions "$(cat /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression/PROMPT.md)"
   ```
4. WAIT — do not type anything while it works. Expected end state: it prints a summary (built `gridcalc.py`, tests pass) and the input box goes idle. If it asks a question instead, reply exactly `Proceed with your best judgment within the spec.` and note "1 intervention" in RESULTS.md → Arm 1 notes.
5. Type `/cost`, press Enter. Copy the printed output into RESULTS.md → "Arm 1 — raw captures".
6. Type `/status`, press Enter. Note the session usage percentage (and the window reset time) into RESULTS.md → "Arm 1 — raw captures". Press Esc if a panel opened.
7. Type `/exit`, press Enter.
8. Run and confirm the three deliverables exist (`README.md gridcalc.py test_gridcalc.py`; a `__pycache__` folder is fine):
   ```
   ls ~/benchmarks/bench-01/fable5
   ```
9. Run and copy the whole output into RESULTS.md → Arm 1 (exact tokens + API-equivalent $ + wall-clock):
   ```
   python3 /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression/grading/claude_session_cost.py "$(ls -t ~/.claude/projects/-home-sinep-benchmarks-bench-01-fable5/*.jsonl | head -1)"
   ```

## Phase B — budget check (30 s)

10. Look at the usage percentage from step 6. If it is BELOW 50%: continue to Phase C now. If it is 50% or higher: STOP and wait until the 5-hour window resets (step 6 showed the reset time), then continue.

## Phase C — Arm 2: Claude Code + Opus 4.8 (unattended, ~10–30 min)

11. Run (one line):
    ```
    cd ~/benchmarks/bench-01/opus48 && claude --model claude-opus-4-8 --dangerously-skip-permissions "$(cat /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression/PROMPT.md)"
    ```
12. WAIT as in step 4 (same intervention rule, note under Arm 2).
13. Type `/cost`, press Enter, copy output into RESULTS.md → "Arm 2 — raw captures".
14. Type `/status`, press Enter, note usage % into RESULTS.md → "Arm 2 — raw captures".
15. Type `/exit`, press Enter.
16. Run and confirm the three deliverables exist:
    ```
    ls ~/benchmarks/bench-01/opus48
    ```
17. Run and copy the whole output into RESULTS.md → Arm 2:
    ```
    python3 /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression/grading/claude_session_cost.py "$(ls -t ~/.claude/projects/-home-sinep-benchmarks-bench-01-opus48/*.jsonl | head -1)"
    ```

## Phase D — Arm 3: Nexus, Super Result ON (mostly unattended)

18. If Nexus is not already running: run `nexus-up` in a terminal and wait until the dashboard opens at `https://127.0.0.1:8777` and you are logged in (accept the self-signed-certificate warning if the browser shows one).
19. In the dashboard, click **+ New Task**.
20. Title — paste exactly:
    ```
    Bench-01 gridcalc mini spreadsheet engine
    ```
21. Description — in a terminal run `cat /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression/PROMPT.md`, select ALL printed text (from `# Build \`gridcalc\`` to the last line), copy it (Ctrl+Shift+C), and paste it into the Description box.
22. Tick the checkbox **✨ Super Result**.
23. Set the involvement preset to **Full Auto** and the spending profile to **Optimal** (defaults show Assisted★/Optimal★ — change involvement to Full Auto, keep Optimal).
24. Set **Status = To Do** (the dropdown defaults to Backlog — a Backlog task will NOT run).
25. Leave everything else at defaults: Model empty/auto, High stakes UNticked, Loop UNticked, Repo path empty.
26. Click **Create**. Write the current clock time into RESULTS.md → "Arm 3 — raw captures" as "created at".
27. WAIT until the task finishes: the card reaches Review/Done and the ✨SR chip shows its final state (SHIP or loop end). Do not answer or approve anything; if a decision card blocks progress in the inbox, approve the ★-recommended option and note "1 intervention". Expect minutes to ~1 h depending on SR rounds.
28. Run and copy the WHOLE output (task info + "copied →" line + cost ledger) into RESULTS.md → Arm 3:
    ```
    ~/nexus-agent-os/.venv/bin/python /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression/grading/collect_nexus.py
    ```
29. Run and confirm `gridcalc.py` is present (other workspace files may also appear — fine):
    ```
    ls ~/benchmarks/bench-01/nexus
    ```

## Phase E — objective grading (2 min, no LLM tokens)

30. Run:
    ```
    bash /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression/grading/grade.sh ~/benchmarks/bench-01/fable5 ~/benchmarks/bench-01/opus48 ~/benchmarks/bench-01/nexus
    ```
31. Copy the printed `=== SUMMARY ===` block into RESULTS.md → Scoreboard section. Per-check detail is in `grading/out/acceptance-*.txt`, own-test logs in `grading/out/selftests-*.txt`.

## Phase F — blind qualitative judging (optional, ~5 min, small token cost)

32. Run (the judge sees only anonymized X/Y/Z + the spec):
    ```
    cd /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression/grading/out/blind && claude --model claude-fable-5 --dangerously-skip-permissions "$(cat JUDGE-PROMPT.txt)"
    ```
33. When it prints the scores and ranking, copy them into RESULTS.md → "Judge verdict", then type `/exit` and press Enter.
34. Only NOW run the following and write the X/Y/Z mapping into RESULTS.md under the judge verdict:
    ```
    cat /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression/grading/out/mapping.txt
    ```

## Phase G — wrap-up

35. Run and copy both printed lines into RESULTS.md → Config table (also fill in today's date):
    ```
    claude --version && git -C ~/nexus-agent-os log -1 --oneline
    ```
36. Fill the Scoreboard table in RESULTS.md (each column says where its number comes from).
37. Start a Claude session in `/home/sinep/Nexus-Agentic-Coding-Setup` and say: `Analyze the bench-01 results in benchmarks/bench-01-first-impression/RESULTS.md` — that session does the comparison write-up and logs WINS/LESSONS.
