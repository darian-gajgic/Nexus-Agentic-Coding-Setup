---
name: technology-landscape-research
description: "Research a technology/tool landscape for a professional developer who needs the whole competitive field — comparable, honestly assessed, with a cost-vs-free breakdown. Cast WIDE before going deep. Use whenever the user asks to 'research X tools', 'what's the best Y', 'compare options for Z', or surveys a space they may adopt."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, landscape-survey, tool-selection, comparison, cost-analysis]
    related_skills: [agentic-coding-harness]
---

# Technology Landscape Research

Use when the user asks to research, survey, compare, or evaluate a technology/tool space —
"what are the options for X", "research the best Y tools", "compare Z approaches". The user is a
professional developer/consultant serving clients; they want the whole field, not a narrow recap.

## The core rule: WIDE before DEEP

A narrow first pass (one vendor, one tool family, one provider) reads as lazy and gets rejected.
It happened once: a survey that covered Anthropic + one model and missed Paperclip, Hermes's own
delegation, BMAD, etc. was called "too narrow and too bad." The user themselves named tools they
expected covered.

So: cast a wide net FIRST — every archetype/category, the full competitive field, open-source AND
commercial, mainstream AND niche — then go deep on the most relevant. Broad sourcing beats
narrow+deep for a landscape task.

## How to structure the sweep

1. **Map the categories/archetypes first.** Don't list tools; list the *classes* of solution,
   then populate each. (e.g. for coding agents: benchmark-leaders / in-editor / open-source-model-
   agnostic / orchestration-frameworks / context-tooling. Not just "here are 5 CLIs".)
2. **Name SPECIFIC tools by name, not categories.** If the user named tools themselves ("Paperclip,
   Hermes Agents, BMAD"), those MUST appear. Don't make them ask twice.
3. **Cover the whole field each pass**: commercial/paid AND free/open-source; mainstream AND
   emerging; the obvious pick AND the niche specialist.
4. **Prefer primary sources**: vendor engineering blogs, official docs, benchmark leaderboards,
   peer-reviewed studies (METR, New Relic), established engineering blogs. Selective-but-wide
   beats a pile of secondary recap blogs. Be picky on sources, not on coverage.
5. **Cast in parallel.** Fire 4-6 web_search calls in one batch across the categories, then
   synthesize. Don't serialize one query at a time.

## Mandatory output elements (the user expects all of these)

- **Cost vs FREE breakdown, always.** The user runs a mix of paid (e.g. GLM/Claude) and free
  (Ollama, OSS) and explicitly wants to know what costs money before adopting. Flag every item's
  cost; offer free/local alternatives for paid things.
- **Per-item status verdict.** End with a clear table or list: for each item, one of
  installed / missing / doesn't-make-sense-for-me — so the user can make decisions, not re-research.
- **Honest assessment.** If something doesn't fit the user's setup, say so and why. Don't pad the
  list with irrelevant options.
- **Synthesis, not a link dump.** Group, compare, and recommend. The common patterns across tools
  matter more than enumerating every feature.

## Pitfalls (learned)

- **Too narrow.** The failure mode this skill exists to prevent. If your first draft covers <3
  categories or omits tools the user named, stop and widen before presenting.
- **Vendor recaps as sources.** A vendor's own comparison page is marketing. Cross-check with an
  independent benchmark, a practitioner thread (r/LocalLLaMA, HN), or a peer study.
- **No cost callout.** Presenting a tool without saying it's paid (or free) forces the user to
  research it themselves — defeats the purpose of the survey.
- **No decision framing.** A survey that ends with "here are 12 tools" and no verdict per item
  leaves the user to do the triage. Always close the loop with status + recommendation.
- **Ignoring the user's constraints.** If the user said "no OpenAI" or "free only", filter
  accordingly — don't surface forbidden options as live recommendations (mention them as
  excluded-with-reason at most).

## A reusable shape for the final answer

```
1. The empirical/category framing (why this space matters, 2-3 sentences)
2. Tool map by archetype (the field, grouped)
3. Cost vs FREE breakdown (explicit per item)
4. What's already in place vs missing vs N/A for THIS user
5. Recommendation (highest-value next step, zero-cost-first if possible)
```

This shape turned a rejected "too narrow" pass into an accepted one in the same session.
