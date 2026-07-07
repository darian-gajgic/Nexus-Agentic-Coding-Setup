---
name: deep-research
description: "Use when researching an arbitrary question deeply across many web sources — market/competitive intel, due diligence, a factual or policy question, a client brief — and producing a cited answer. Fans out parallel searches, triages source credibility, adversarially verifies load-bearing claims, and synthesizes a memo with inline citations and explicit confidence levels. Don't use for academic ML paper writing (use research-paper-writing) or single tool/vendor surveys (use technology-landscape-research)."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, web, verification, synthesis, citations]
    related_skills: [technology-landscape-research, research-paper-writing, claim-verification, llm-wiki]
---

> **Business Brain:** for business-relevant research, also apply `~/knowledge/domains/research-learning/PLAYBOOK.md` (source hierarchy, triangulation, confidence labels) and self-score against its RUBRIC.md; high-stakes conclusions get a frontier pass via the frontier-judge skill (`cjudge <file> research-learning`).

# Deep Research

## Overview

A disciplined multi-source research loop over the tools you already have (`web_search`, `web_extract` on the brave-context backend). It replaces the "search once, answer" reflex with **decompose → fan out → triage sources → verify claims → synthesize with citations**. The output is a memo a client or future-you can trust: every load-bearing claim is traceable to a source and tagged with a confidence level.

**Core principle:** an answer is only as good as its worst-sourced claim. Find the disconfirming source before you commit a fact.

## When to Use

**Use for:**
- Market/competitive intelligence, due diligence, vendor/tool comparisons spanning many sources
- A factual, policy, or "is X true / what's the state of Y" question where being wrong is costly
- A client-facing brief that must cite and hedge honestly

**Don't use for:**
- Academic ML paper writing → `research-paper-writing`
- A single tool/vendor/technology survey → `technology-landscape-research`
- A quick lookup with one obvious authoritative source (just `web_search` it)

## The Loop

### 1. Decompose
Write the question, then break it into 3-6 sub-questions that together answer it. Save them to a plan file (`.hermes/plans/<date>-research-<slug>.md`) as a checklist.
**Done when:** the sub-questions are mutually exclusive enough that answering all of them answers the top question, and each is searchable on its own.

### 2. Fan out
Run at least one `web_search` per sub-question; `web_extract` the 2-4 hits that look substantive (not SEO stubs). For a broad question with independent branches, delegate sub-questions to parallel subagents (respect the live `delegation.max_concurrent_children`); for a narrow one, do it inline.
**Done when:** every sub-question has **≥2 independent sources** — not two pages tracing to the same origin.

### 3. Triage sources
Tag each source **primary** (original data, filing, spec, first-hand), **secondary** (reporting on a primary), or **tertiary/aggregator**. Note authority and date. Down-weight or discard: content farms, undated pages, AI-generated slop, and pages that merely restate another source (circular sourcing).
**Done when:** each retained claim rests on the most primary source you could find, and you know how old it is.

### 4. Verify load-bearing claims
For every claim the conclusion depends on — a number, date, causal or superlative statement — actively seek **one disconfirming source**. If none exists, confidence rises; if sources conflict, mark the fact **contested** and present both. For high-stakes fact sets, invoke `claim-verification` (Chain-of-Verification).
**Done when:** each load-bearing claim is independently corroborated or explicitly flagged contested/low-confidence.

### 5. Synthesize
Write a themed memo, not a source-by-source dump:
- One inline citation per claim (URL or source name).
- A **confidence level** (high / medium / low) on each major finding.
- A dated stamp on any time-sensitive fact ("as of <date>").
- An explicit **"What's contested / What we don't know"** section — omitting it launders uncertainty into false confidence.
**Done when:** a reader can trace every claim to a source and see where you're unsure.

## Output Shape

```
# <Question> — Research Memo (<date>)
## Answer            (2-4 sentences — the bottom line)
## Findings          (themed; each claim cited + confidence)
## What's contested / unknown
## Sources           (primary sources first)
```

## Common Pitfalls

1. **Single-source claims.** One page is a lead, not a fact. Corroborate or flag.
2. **Circular sourcing.** Five articles citing one press release is one source. Trace to origin.
3. **Stale facts stated as current.** Date every time-sensitive claim; never present old data as now.
4. **Marketing pages as fact.** A vendor's own page is a claim about itself, not neutral evidence.
5. **Skipping the disconfirming search.** Only searching for support is confirmation bias with extra steps.
6. **Dumping instead of synthesizing.** A list of what each source said is not an answer.

## Verification Checklist

- [ ] Question decomposed into 3-6 searchable sub-questions (saved to a plan file)
- [ ] Every sub-question backed by ≥2 independent sources
- [ ] Each source triaged (primary/secondary; authority; date)
- [ ] Every load-bearing claim corroborated or flagged contested/low-confidence
- [ ] Disconfirming evidence actively sought for the key claims
- [ ] Memo has inline citations, per-finding confidence, and a "contested/unknown" section
- [ ] Time-sensitive facts carry an "as of <date>" stamp
