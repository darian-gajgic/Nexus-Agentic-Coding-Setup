---
name: claim-verification
description: "Use before finalizing any answer that asserts load-bearing facts, numbers, names, dates, or causal claims — research findings, client-facing statements, extracted data. Runs the Chain-of-Verification loop: draft, generate independent verification questions, answer each in isolation without anchoring on the draft, then revise to delete or hedge unsupported claims. Don't use for opinion, creative text, or writing with no factual load."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [verification, fact-checking, anti-hallucination, cove, quality-gate]
    related_skills: [deep-research, research-paper-writing, goal-drift-discipline]
---

> **Business Brain:** verification standards for business research live in `~/knowledge/domains/research-learning/PLAYBOOK.md` (source hierarchy, triangulate important claims across >=3 independent sources, date-stamp everything) — apply them together with this skill's method.

# Claim Verification (Chain-of-Verification)

## Overview

A quality gate that catches hallucinated and half-remembered facts before they ship. Based on Chain-of-Verification (CoVe, arXiv 2309.11495): the decisive move is to answer each verification question **in isolation**, without looking at the draft, so the model can't rubber-stamp its own claim. A vague "let me double-check" does not do this; this skill does.

**Core principle:** a check that reads the draft first will agree with the draft. Verify blind.

## When to Use

**Use before finalizing:**
- Research findings, comparisons, or any memo carrying numbers/dates/names
- Client-facing statements where a wrong fact costs credibility or money
- Data you extracted or summarized from sources

**Don't use for:**
- Opinion, creative writing, brainstorming, or text with no factual load
- A trivial claim with one obvious authoritative source already in hand

## The Loop

### 1. Draft
Produce the candidate answer as you normally would.
**Done when:** the full answer text exists to verify against.

### 2. Plan checks
List every **load-bearing** claim — a fact the conclusion depends on. For each, write one specific verification question ("What was X's 2025 revenue?"), not a yes/no ("Is this right?").
**Done when:** each load-bearing claim maps to exactly one answerable question; claims with no factual load are skipped.

### 3. Answer in isolation
Answer each verification question **independently** — ideally a fresh `web_search`/`web_extract` — **without re-reading the draft**. This is the whole point: no anchoring on what you already wrote.
**Done when:** every question has an answer derived from a source, not from the draft.

### 4. Reconcile and revise
Compare each isolated answer to the draft, then: keep corroborated claims; **delete** unsupported ones; **hedge** low-confidence ones ("reportedly", "as of <date>"); mark conflicts **contested** and show both sides.
**Done when:** every load-bearing claim is corroborated, hedged, deleted, or flagged — none left as a bare unverified assertion.

## Common Pitfalls

1. **Answering checks from the draft.** If step 3 reads the draft, it confirms whatever's there — a no-op. Answer blind.
2. **Only verifying the easy claims.** The claim you're least sure of is the one to check first.
3. **Verifying existence, not correctness.** "A source exists" ≠ "the claim is right." Check what the source actually says.
4. **Treating a hedge as a fix.** Hedging a genuine unknown is honest; hedging a *checkable* claim you skipped is not.

## Verification Checklist

- [ ] Every load-bearing claim has a verification question
- [ ] Each question answered independently, without anchoring on the draft
- [ ] Isolated answers reconciled against the draft
- [ ] Unsupported claims deleted; low-confidence ones hedged; conflicts flagged contested
- [ ] No load-bearing claim remains as a bare unverified assertion
