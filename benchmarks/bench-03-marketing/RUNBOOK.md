# Bench-03 Runbook — marketing campaign benchmark (operator steps)

Follow-up to bench-02, testing the areas bench-02 doesn't: marketing strategy, e-commerce thinking, deep research, and non-code deliverables (docs + visual assets). Same interactive protocol: you are the client, you answer questions live from `ANSWER-SHEET.md`, every Q&A gets logged. The business facts (budget, market, language, goals) are obtainable ONLY by asking — a system that markets an unknown shop without asking is measured doing exactly that.

**Nexus config for run 1: Super Result OFF, 🚀 Full Auto, 🧠 Smart** (same baseline as bench-02 run 1; the Balanced/SR ladder can be repeated here later the same way).

**Symmetry rule:** do NOT attach the benchmark2 project to the Nexus task and do NOT run the Claude arms inside their bench-02 shop folders — all arms start from an empty context and must ask for what they need. (Grounding on the real shop project is a separate capability worth its own later run.)

**Scheduling:** run this only after the bench-02 Nexus workflow is fully finished (no shared dispatch slots, clean ledgers). This task is smaller than bench-02 — a Claude arm should fit comfortably in a window, but check usage before starting each arm.

## Phase 0 — prep (5 min)

1. Run:
   ```
   mkdir -p ~/benchmarks/bench-03/fable5 ~/benchmarks/bench-03/opus48 ~/benchmarks/bench-03/nexus
   ```
2. Choose the prompt variant — `PROMPT-B.md` recommended (adds the launch-kit/overview-folder anchor and the image fallback so outputs stay gradeable; `PROMPT-A.md` = your original verbatim). SAME variant for all three arms; record it in RESULTS.md → Config.
3. Read `/home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-03-marketing/ANSWER-SHEET.md` completely.
4. Print the prompt for pasting:
   ```
   cat /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-03-marketing/PROMPT-B.md
   ```

## Phase A — Arm 1: Claude Code + Fable 5 (interactive)

5. Run:
   ```
   cd ~/benchmarks/bench-03/fable5 && claude --model claude-fable-5
   ```
6. `/status` → if usage > 40%, postpone to a fresh window; else Esc and continue.
7. Paste the prompt; note "started at" in RESULTS.md → Arm 1.
8. Answer questions per ANSWER-SHEET, log every Q&A; approve permission prompts (not logged).
9. On the final summary: note "finished at", then `/cost` (copy), `/status` (note usage %), `/exit`.
10. Cost capture:
    ```
    python3 /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-01-first-impression/grading/claude_session_cost.py "$(ls -t ~/.claude/projects/-home-sinep-benchmarks-bench-03-fable5/*.jsonl | head -1)"
    ```

## Phase B — window gate

11. Start Arm 2 only if the current window has comfortable headroom (< ~40% used) — otherwise wait for the reset.

## Phase C — Arm 2: Claude Code + Opus 4.8

12. Run:
    ```
    cd ~/benchmarks/bench-03/opus48 && claude --model claude-opus-4-8
    ```
13. Repeat steps 6–10 for Arm 2 (cost path: `-home-sinep-benchmarks-bench-03-opus48`).

## Phase D — Arm 3: Nexus (SR OFF, Full Auto, 🧠 Smart)

14. Dashboard → Tasks → **✨ Describe a task**. Paste the SAME prompt. "📂 About an existing project?" = **No** (symmetry rule). **✨ Super Result UNTICKED.**
15. Accept ✦ Deep Plan if offered/recommended, else ✨ Plan it. Answer the interview per ANSWER-SHEET, log Q&A, note "started at".
16. Review card: involvement **🚀 Full Auto**, spending **🧠 Smart** (note the tool's own suggestion first), SR off, approve/create. Verify tasks reach To Do/In Progress.
17. WAIT for completion. High-stakes checkpoint protocol from bench-02 applies: if a review/decision blocks, **wait for the judge verdict to land first**, review the deliverable, approve, log the intervention. Note "finished at".
18. Collect:
    ```
    ~/nexus-agent-os/.venv/bin/python /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-02-webshop/grading/collect_nexus.py list
    ```
    then with the matching id:
    ```
    ~/nexus-agent-os/.venv/bin/python /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-02-webshop/grading/collect_nexus.py <wf-…/task-… id> ~/benchmarks/bench-03/nexus
    ```
    Copy the whole output (statuses, wall-clock, ledger) into RESULTS.md → Arm 3.

## Phase E — deliverable review (documentary, ~15 min per arm)

Per arm, open the kit and fill the 10-row checklist in RESULTS.md:

19. Read the overview/index doc first, then every deliverable, in its stated order.
20. Open every visual asset (does it render? is it usable?) and every image-generation prompt (is it exact enough to reproduce?).
21. Spot-check **at least 3 cited sources/statistics per arm** in your browser: do they exist, and do they say what the kit claims? A fabricated source or statistic fails row 8 outright.
22. Grep each kit for placeholder debris (row 7):
    ```
    grep -rniE '\{\{|TODO|lorem|XXX' <arm_dir> | grep -v '.git' | head
    ```

## Phase F — blind judge (needs web access for source verification)

23. Run:
    ```
    bash /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-03-marketing/grading/prepare_judge.sh ~/benchmarks/bench-03/fable5 ~/benchmarks/bench-03/opus48 ~/benchmarks/bench-03/nexus /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-03-marketing/PROMPT-B.md
    ```
24. Run (approve web-search permissions — the judge must verify sources):
    ```
    cd /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-03-marketing/grading/out/blind && claude --model claude-fable-5 "$(cat JUDGE-PROMPT.txt)"
    ```
    Copy gate results + scores + ranking into RESULTS.md, `/exit`.
25. Reveal the mapping only now:
    ```
    cat /home/sinep/Nexus-Agentic-Coding-Setup/benchmarks/bench-03-marketing/grading/out/mapping.txt
    ```

## Phase G — wrap-up

26. `claude --version && git -C ~/nexus-agent-os log -1 --oneline` → RESULTS.md Config, plus the date.
27. Fill the Scoreboard.
28. Analysis session in the repo: `Analyze the bench-03 results in benchmarks/bench-03-marketing/RESULTS.md` (it also cross-reads bench-02 for the combined picture and logs WINS/LESSONS).
