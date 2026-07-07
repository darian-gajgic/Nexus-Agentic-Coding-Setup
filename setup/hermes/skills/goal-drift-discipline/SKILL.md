---
name: goal-drift-discipline
description: Prevents promoting a diagnostic test / probe to the goal during long iteration loops on a benchmark. Apply when working 3+ iterations on the same sub-task, optimizing a user-defined score, or doing any "prove you can X" task. Triggered by the agent on its own turns — does not require user prompting.
version: 1.0.0
metadata:
  hermes:
    category: meta-cognition
    tags: [goal-alignment, anti-pattern, iteration-discipline, benchmarking]
---

# Goal-Drift Discipline

## The core distinction

A diagnostic test ("prove X by doing Y") makes **Y the PROBE** and **X the GOAL**.
Y is complete once X is demonstrated to a usable degree. Continuing to optimize
Y past that point is optimizing a proxy metric, not advancing the goal.

## Trigger conditions (load this skill when ANY is true)
- You are on iteration 3+ of the same sub-task or benchmark.
- The user defined a score you are trying to improve (e.g. "make it 8/10", "match Claude's output").
- The task framing is "prove you can X" / "demonstrate capability by doing Y" / "test whether you can".
- You are about to start another round of tuning/polish on an already-working artifact.

## Procedure

### At task start
1. Write ONE line: `User's underlying goal: ___`
2. Tag the current action's role: `builds-toward-goal | verifies-capability | polishes-a-proxy`
3. If you cannot write the goal in one line, ASK the user before proceeding.
   Do not guess the goal and proceed on the guess.

### At every 3rd iteration on the same sub-problem
4. Stop and answer out loud: *"Is the next step the highest-leverage move toward the stated goal, or am I optimizing a proxy metric?"*
5. If proxy, surface this to the user explicitly:
   > "I'm at iteration N on [sub-task]. The stated goal is [goal]. Continuing to polish [sub-task] has diminishing returns toward it. Options: (a) keep going, (b) move to [higher-leverage step], (c) declare this done. Which?"
6. Do NOT silently continue past this checkpoint. The discipline is the surfacing, not the answer.

### Capability-demonstration tasks
7. "Prove you can X" is DONE the moment X is demonstrated to a usable degree. Further polish is scope creep.
8. Propose continued polish explicitly (*"want me to keep improving this, or is that sufficient?"*) — do NOT default to another round.

## Red flags (you are drifting if…)
- You're improving a user-defined metric but haven't re-stated the goal in 3+ turns.
- The artifact already works and you're making it "better" without being asked.
- You can recall the last benchmark number but not the last goal-level instruction.
- The numbers are going up and it feels productive, but nothing has shipped toward the goal.

## Recovery (if you realize mid-drift)
1. STOP the current iteration.
2. State plainly: *"I drifted — I've been optimizing [proxy] instead of [goal]."*
3. Restate the goal in one line.
4. Propose the highest-leverage next step toward the goal.
5. Do NOT justify the drift with "but the numbers improved." Improvement on a proxy is not goal progress.

## Pitfalls
- **"Just one more iteration"**: each round feels productive → local optimization trap. The 3rd-iteration checkpoint exists specifically to break this.
- **Measurable proxy progress feels like goal progress** — they are different. A diff metric dropping from 55→24 is real, but if the goal was "ship vision for PC control," it may not move the goal at all.
- **The user won't always interrupt you.** This session they did, at iteration ~6. Future sessions, assume they won't. The check has to be self-imposed.
- **"Prove capability" has no natural stopping point** unless you impose one. Set it at "usable demonstration," not "pixel-perfect."

## Verification (before sending any turn on iteration 3+)
Answer in one sentence: *What is the goal, and how does this turn advance it?*
If you can't answer in one sentence, you are drifting — apply Recovery.

## Origin
Learned 2026-07-04 in a vision-redraw session: user said "redraw this screenshot to prove you can see images." The agent spent 6+ iterations chasing redraw fidelity (3/10 → 8/10) via PIL pixel-compositing on one GNOME Resources screenshot, while the actual goal — a working vision backend for PC control & frontend testing — was already fixed in config and only needed a session restart. User had to interrupt: "what's the goal — draw one image, or build the see-and-control feature?" The answer was the latter. The redraw work was technically improving but had stopped serving the goal around iteration 2.
