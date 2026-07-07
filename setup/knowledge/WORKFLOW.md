# WORKFLOW — which tool, which model, for which task

The one rule behind everything: **frontier intelligence at the steering points (spec, plan,
judgment), cheap volume everywhere else, humans on taste and final call.**

| Model | Role | Costs |
|---|---|---|
| **Claude (Opus 4.8 / Fable)** — `claude` | Architect & judge: specs, plans, hard reasoning, final reviews, anything high-stakes | Subscription — use for the 5% that steers the 95% |
| **GLM-5.2** — `glm`, Hermes | Volume worker: implementation, drafts, research legwork, everyday assistant | Cheap — let it do the bulk |
| **Local Ollama** (qwen3-vl, llama3.1, nomic-embed) | Vision, memory embeddings | Free |

## Task routing table

| Task | Do this |
|---|---|
| Quick question, daily errand, "look this up" | `hermes` (or `hermes chat -q "..."` one-shot) |
| Business deliverable (marketing, content, brand, listing, proposal, set plan…) | `hermes` → it delegates to the domain specialist → specialist follows PLAYBOOK + self-scores RUBRIC |
| **High-stakes** business deliverable (per playbook's "escalate" list) | Same, then `cjudge <file> <domain>` for a frontier verdict before it ships |
| Non-trivial coding feature | 1) `cspec "goal"` in the repo → frontier Claude interviews you + writes SPEC.md → 2) `glm` → `/spec` (implements against SPEC.md, tests as ground truth) → 3) `creview` → frontier Claude reviews the diff vs SPEC.md |
| Small code fix / mechanical change | `glm` directly (skip the ceremony) |
| Whole-project build | `cspec` first, then `glm` + `/ultra` or `glm-ultra` |
| Deep multi-source research | `claude` → `/deep-research` (fan-out + verified citations). Market/competitor research inside Hermes → `market-researcher` specialist |
| Hard strategy / important decision / anything you'd lose sleep over | `claude` directly — don't economize on the decisions that steer everything |
| Learning: "explain why this works" | Ask any agent to walk you through its output vs the RUBRIC, or read the domain examples/ |

## The three bridge commands (installed in ~/.local/bin)

| Command | What it does | When |
|---|---|---|
| `cspec "build X"` | Frontier Claude interviews you, then writes a tight `SPEC.md` in the current repo | Before any non-trivial glm coding session |
| `creview` | Frontier Claude reviews the current git diff against `SPEC.md`, returns verdict + findings | After glm says "done", before you trust it |
| `cjudge <file> <domain>` | Frontier Claude judges a deliverable against `~/knowledge/domains/<domain>/RUBRIC.md` | High-stakes business deliverables; also your learning benchmark |

All three run on the Anthropic side (your subscription) with a clean environment, so they work
even from inside a `glm` session or a Hermes terminal.

## Operational notes (verified 2026-07-06)

- **`hermes chat -q` is for quick direct answers only.** Specialist delegations always run in
  the background (the delegate tool is async-only), and a one-shot session exits before the
  specialist returns — the reply is killed and never arrives. For anything that routes to a
  specialist, use interactive `hermes` or the Nexus dashboard. One-shot exits can also lose
  that session's memory writes and print a harmless langfuse teardown warning — same root cause.
- **Z.ai quota reality (verify current numbers):** GLM-5.2 consumes coding-plan quota at ~3×
  during peak hours and ~2× off-peak (promo through ~Sep 2026: 1× off-peak), with prompt limits
  per 5-hour window. A burst of HTTP 429s usually means the window is exhausted — wait for it to
  roll over, or schedule heavy fan-outs (glm-ultra, big Hermes jobs) off-peak.
- **Hermes install carries intentional local modifications** (~300 lines: the specialist
  learning pipeline — per-role mem0 scopes layered on a team-shared scope, lesson-usage
  tracking for pruning, langfuse enrichment, delegate-tool wiring). They are auto-snapshotted
  to `~/.dotfiles/hermes/hermes-agent-local-mods.patch` by sync.sh. If `hermes update` ever
  conflicts on them, that patch is the restore point.

## Why this split works (the part most people miss)

- A weak model executing a **great spec** beats a weak model executing its own mediocre spec.
  The spec is ~5% of the tokens but determines ~80% of the outcome — spend frontier there.
- A model judging its own family's output shares its blind spots. Cross-family review
  (GLM builds → Claude judges) catches what self-review can't.
- Tests, rubrics, and checklists are ground truth; model self-assessment is not.
- Humans stay the taste function: you two make the final call on anything customer-facing,
  and every review you do against a rubric trains YOU, not just the system.
