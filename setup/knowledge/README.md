# Business Brain (~/knowledge)

The shared intelligence layer for our AI setup. Every AI agent (Hermes specialists, glm coding
sessions, frontier Claude) reads from here before producing business deliverables — and we humans
learn the craft from the same files.

## Structure

```
knowledge/
├── README.md            ← you are here
├── MANUAL.md            ← USER MANUAL — plain-language guide for non-technical operators (+ German quick guide)
├── WORKFLOW.md          ← WHICH TOOL/MODEL FOR WHICH TASK — read this first
├── BUSINESS-CONTEXT.md  ← who we are, what we sell, to whom (agents read this first)
├── STYLE-VOICE.md       ← how everything we publish sounds
├── ONBOARDING.md        ← interview that personalizes this whole knowledge base
├── domains/<domain>/
│   ├── PLAYBOOK.md      ← senior operating procedure (HOW a pro does the work)
│   ├── RUBRIC.md        ← quality gate (WHAT good looks like, scoreable)
│   └── examples/        ← annotated exemplar outputs (LEARN from these)
├── feedback/
│   ├── WINS.md          ← real-world winners → promoted to examples/ over time
│   └── LESSONS.md       ← what went wrong + the correction
└── evals/               ← repeatable test tasks to measure config changes
```

Domains: `software-engineering`, `saas-business`, `marketing`, `content-creation`, `brand`,
`ecommerce`, `consulting-bizdev`, `research-learning`, `music-dj`.

## How agents use this (wired automatically)

1. Read `BUSINESS-CONTEXT.md` + `STYLE-VOICE.md` once per session.
2. Read the matching `domains/<domain>/PLAYBOOK.md` before working; follow it.
3. Self-score the draft against `domains/<domain>/RUBRIC.md`; fix every must-pass failure
   before delivering.
4. End deliverables with a short **Learn:** section (≤3 bullets) explaining the key choices —
   that's for us humans.
5. High-stakes work (defined per playbook) additionally gets a frontier second opinion via
   `cjudge` before it ships.

## How WE use this (the learning loop)

This is how two juniors get to professional level fast:

1. **Before reading AI output**, score it against the domain RUBRIC yourself. Write your score down.
2. Compare with the agent's self-score and (for high-stakes work) the `cjudge` verdict.
   The gap between your judgment and the frontier judge's = exactly what you need to learn next.
3. Log the insight in `feedback/LESSONS.md` (30 seconds, or tell any agent to do it).
4. When something wins in the real world (a listing that sells, an email that converts, a set
   that worked), log it in `feedback/WINS.md` — with the numbers. Periodically promote the best
   entries into `domains/<domain>/examples/` to replace the generic templates.

Over time this repo stops being generic professional knowledge and becomes YOUR proven playbook.

## Maintenance rules

- **First thing: run the onboarding** (see `ONBOARDING.md`) so `{{FILL: ...}}` slots get real values.
- This is a git repo. Commit after meaningful edits: `git add -A && git commit -m "..."`.
- Don't bloat it. One strong playbook per domain beats five overlapping ones. If a file stops
  earning its place, delete it — git remembers.
- Facts rot. Anything marked "(verify current numbers)" means: check live before relying on it.
