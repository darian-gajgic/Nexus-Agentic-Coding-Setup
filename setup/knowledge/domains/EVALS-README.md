# Eval corpus — fixed briefs that measure playbook/prompt changes

Each domain folder may contain `evals/*.md`: **fixed briefs** run by Nexus
(Specialists → 📏 Evals) through the real task pipeline and scored by the
frontier judge against that domain's `RUBRIC.md`.

Why: after editing a PLAYBOOK, RUBRIC, STYLE-VOICE or a specialist definition,
re-run the domain's evals — same briefs, new config — and compare scores with
the previous run. The run's ⚙ fingerprint records which config produced which
score. Trends over 2–3 runs beat single points (generation is nondeterministic).

## Case file format

```markdown
---
title: Short human name of the case
specialist: copywriter-specialist   # optional — must exist in ~/.hermes/agents/
model: glm-5.1                      # optional — omit for the default tier
notes: what this case exercises     # optional, shown in the UI
---
The brief. SELF-CONTAINED and FIXED: embed every fact the work needs
(numbers, quotes, constraints) so runs stay comparable and nothing must be
invented. State explicitly that missing facts become stated assumptions.
End with the expected deliverable shape.
```

Rules for good cases:
- One deliverable, one session — no multi-stage pipelines here.
- Facts embedded, stable over time (no "current prices" unless the case is
  ABOUT live research, like research-learning's).
- Exercise the domain's rubric gates on purpose (objectives, proofs, CTAs…).
- 2–3 strong cases per domain beat 10 shallow ones; keep total runtime sane —
  every case costs a GLM run plus a frontier-judge call.
