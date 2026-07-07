---
name: content-repurposing
description: "Use when turning one long-form piece — blog post, video, talk, transcript, essay — into several platform-native posts (X thread, LinkedIn post, Instagram carousel, newsletter blurb), each rewritten to stand alone in its platform's idiom rather than the same text truncated. Routes to the canonical method in ~/knowledge/domains/content-creation (playbook + rubric + worked example). Don't use for YouTube-transcript-only repurposing (use youtube-content) or pure tone cleanup (use humanizer)."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [content, creator, repurposing, social, multi-platform]
    related_skills: [youtube-content, humanizer, frontier-judge]
---

# Content Repurposing

> **The canonical method lives in the Business Brain — this skill is the router, the playbook
> is the method.** Read `~/knowledge/domains/content-creation/PLAYBOOK.md`: the platform-native
> table (what changes between LinkedIn / X / Instagram / TikTok) and the repurposing pipeline
> (1 pillar → 5+ assets, with the conversion table). Quality gate:
> `~/knowledge/domains/content-creation/RUBRIC.md`. Fully worked example:
> `~/knowledge/domains/content-creation/examples/repurposing-set.md`.

## Workflow (condensed)

1. Read the playbook sections above plus `~/knowledge/STYLE-VOICE.md` (voice + kill list).
2. Atomize the source ONCE: extract the core insights, each usable stand-alone.
3. Reformat per platform following the playbook's platform table — **re-write in the
   platform's idiom, never truncate-and-paste**. Copy-paste across platforms reads as
   copy-paste.
4. Self-score against the RUBRIC's must-pass gates before delivering; end with the standard
   "**Learn:**" bullets.
5. High-stakes sets (launches, client work) → frontier pass: `cjudge <file> content-creation`
   (see the frontier-judge skill).

## Routing

- YouTube-transcript-only repurposing → `youtube-content`
- Pure tone/voice cleanup of existing text → `humanizer`
