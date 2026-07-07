---
name: client-delivery-gate
description: Critic-gate any client deliverable before sending; block low scores.
version: 1.0.0
author: Hermes Agent
metadata:
  hermes:
    category: productivity
    tags: [quality, review, client-work]
---

> **Business Brain:** this critic gate complements (never replaces) the canonical quality bar — the matching `~/knowledge/domains/<domain>/RUBRIC.md` must-pass gates, plus the frontier judge for high-stakes client deliverables (`cjudge <file> <domain>`, see the frontier-judge skill). Run both: critic mean >= 3.0 AND rubric gates green.

# Client Delivery Gate Skill

Run this BEFORE handing any artifact to a paying client — code, copy, research,
design spec, or proposal. It is a last-line quality gate, not a substitute for
doing the work well. It does NOT run on internal scratch work.

## When to Use

Any output that will reach a client or be sent externally on the team's behalf.

## Do Not Use For

Internal notes, throwaway experiments, or intermediate steps not shown to a client.

## Procedure

1. **Gather inputs.** Put the near-final artifact next to the ORIGINAL brief /
   requirements. The critic cannot judge coverage without the brief.
2. **Mechanical kill-list sweep (deterministic, zero tokens, run FIRST).** For
   any Business Brain deliverable with a matching RUBRIC.md, run:
   `python3 ~/.hermes/skills/client-delivery-gate/scripts/rubric_kill_sweep.py <file> <domain>`
   It reads the domain RUBRIC.md banned-word fence and checks the deliverable
   for: banned-word hits, `{{`/`[TODO`/lorem/XXX placeholders (gate 10),
   we-heavy copy (we/our/us > you/your), exclamation storms, and a reading-level
   proxy. Any FAIL = fix before spending critic tokens. Eyeballing the rubric
   regularly misses what this catches in <1s. (No RUBRIC.md for the domain, or
   not a Business Brain deliverable? Skip to step 3.)
3. **Run the critic pass.** Send both to a critic — use `delegate_task` with a
   fresh subagent, or an auxiliary model — with this rubric. Score each dimension
   0–5 (0 = unusable, 3 = acceptable, 5 = excellent). Use a 0–5 scale, never 0–10
   (0–10 adds noise and aligns worse with human judgement):
   - **Requirement coverage** — did it do everything the brief asked?
   - **Correctness** — factually right? For research/claims, ALSO run the
     `claim-verification` skill and fold its result in.
   - **Clarity & professionalism** — client-ready tone, zero placeholders/TODOs,
     no internal notes leaking through.
   - **Risk** — anything that could embarrass the sender or the client?
4. **Decide.** Compute the mean. **Block delivery if mean < 3.0 OR any single
   dimension is 0 or 1.** Return the critic's specific fixes, revise, then
   re-run this gate. Only deliver when it clears.
5. **For code deliverables**, ALSO require the runtime verification (tests/build)
   to pass — `agent.verify_on_stop` already enforces this for code turns; do not
   bypass it.
6. **For web/UI deliverables**, ALSO run the domain audit tools and read the
   individual audit results, not just composite scores: `npx lighthouse <url>
   --only-categories=accessibility,performance`. A composite score ≥90 can still
   hide a failed audit (e.g. `color-contrast` = 0). See the "Score ≥90 ≠ zero
   failed audits" pitfall.

## Pitfalls

- The critic MUST see the original brief, or it cannot judge requirement coverage.
- Do not gate on the critic alone for factual output — pair it with
  `claim-verification`.
- Use a genuinely capable critic. GLM-5.2 at max effort judging its own output is
  acceptable; a *different* model (e.g. a stronger escalation model) is stronger
  for high-stakes deliverables — a model reviewing itself shares its own blind spots.
- Keep this gate cheap and fast enough that it actually gets used every time; a
  gate that's skipped protects nothing.
- **Numeric spec thresholds are BINARY — "close" is a FAIL.** When the brief/spec
  states a number (contrast ≥4.5:1, Lighthouse ≥90, meta ≤155 chars, page weight
  ≤300KB), a value below it fails no matter how small the gap. 4.47:1 is not
  "borderline" against a ≥4.5:1 requirement — it is a blocking FAIL. Do not round
  a near-miss up or grade it leniently because it "looks fine to the eye." If the
  number is in the spec, the number is the gate. (Origin: a webshop acceptance
  gate where the evaluator computed 4.47:1 for CTA buttons and called it a nit;
  an independent Lighthouse run correctly escalated it to blocking.)
- **"Score ≥90" and "zero failed audits" are DIFFERENT bars.** Lighthouse (and
  similar weighted tools) can report an Accessibility score of 95 while a single
  `color-contrast` audit scores 0 (FAIL). If the brief says "score ≥90" that bar
  passes; if it ALSO says "no audit flagged as fail," that bar fails. When the
  brief states both, check BOTH — and when writing a brief, be explicit about
  which bar you mean.
- **For web/UI deliverables: run the actual audit tool, do not eyeball or
  hand-compute.** Manual WCAG contrast computation against the page background
  routinely misses accent colors used on *elevated* surfaces (cards, panels) —
  indigo `#6366f1` passes on near-black `#0a0a0f` but fails on an elevated card
  `#13131a`. Run `npx lighthouse <url> --only-categories=accessibility` (it
  installs on first `npx` run) and read the individual audit scores, not just the
  composite. The ~30 seconds of tool runtime catches what minutes of manual
  computation miss.
- **Self-scoring meta-blocks trip their own gates.** A reviewer-note section at
  the end of the deliverable that *quotes* `{{FILL}}` templates or *uses* "we"
  will itself trigger the placeholder gate (10) and inflate the we/you ratio.
  Either drop the meta-note before delivery, or phrase it without the literal
  `{{` and without first-person plurals. The kill-sweep script strips a trailing
  `## Why/Note/Scoring` section before counting we/you, so keep meta-notes under
  such a heading if you keep them at all.

## Verification

The gate is working when: (a) a deliberately flawed draft (missing a stated
requirement) is BLOCKED with a specific fix, and (b) a clean draft passes with a
mean ≥ 3.0 and a one-line rationale per dimension.
