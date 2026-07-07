# Eval 02 — Marketplace listing (title + bullets)

Domain: `ecommerce` · Judge: `cjudge <output> ecommerce`

## Task (give verbatim)

> Write a marketplace listing title (max ~180 chars) and 5 benefit bullets for
> {{FILL: one of your real products — until onboarding, use: "a 1.2 m × 25 m roll of premium
> stretch wrap film, 23 µm, for moving and pallet securing, sold on Amazon.de to private movers
> and small businesses"}}. Follow ~/knowledge/domains/ecommerce/PLAYBOOK.md: search-term
> logic in the title, one benefit per bullet with the spec that proves it. Then list the 8
> backend search keywords you'd use.

## Run

- Hermes: `hermes chat -q "<task>"` (should route to marketplace-listing-optimizer)

## What good looks like

- Title front-loads what people search, not brand fluff; includes size/spec.
- Each bullet = benefit first, proving spec second; no keyword stuffing; no "high quality".
- Backend keywords: no duplicates of title words, includes synonyms/misspellings variants.

## Baseline runs

<!-- paste: date · output file · cjudge verdict + scores -->
