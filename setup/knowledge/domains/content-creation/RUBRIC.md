# Content Quality Rubric

> Frontier-judge scoping (2026-07-13): for the text-only frontier judge, a gate whose evidence cannot appear on the page and is not contradicted by the task's artifacts is UNVERIFIABLE-HERE (a note), not FAIL — the cjudge verdict contract governs: only binding in-scope gate FAILs and critical/high findings block a SHIP.

Scoreable gate for every piece before it publishes. Companion to `PLAYBOOK.md` (craft) and
`~/knowledge/STYLE-VOICE.md` (voice markers). Every item below is checkable without taste.

**How to use:**
1. Run the must-pass gates. Any FAIL → do not publish. Fix, re-run.
2. Score the dimensions 0–4. Publish at total ≥22/32 with no dimension ≤1.
3. Any dimension still ≤2 after one revision → escalate per PLAYBOOK "Escalate to frontier review."

## Must-pass gates

Binary. Do not publish if any fails.

| # | Gate | Check |
|---|---|---|
| G1 | Hook exists | Line 1 contains at least one of: a number, a named pain, a question, a contrarian claim. |
| G2 | One idea | The takeaway is written in ≤20 words, and every section/tweet/slide serves it. |
| G3 | Claims sourced | Every stat or factual claim is (a) our data, (b) a link the author opened, or (c) explicitly framed as opinion. Zero orphan claims. |
| G4 | Kill list clean | Case-insensitive search for every kill-list item below returns zero matches. |
| G5 | Single CTA | Exactly one primary CTA, matched to reader temperature (cold→follow/save, warm→email, hot→product/call). |
| G6 | Platform-native | Hook was rewritten for this platform; format follows PLAYBOOK playbook 4; the text does not appear verbatim on another platform. |
| G7 | No stale mechanics | Zero platform/algorithm claims stated as current fact without having been verified this quarter. |
| G8 | Permission | Every named client, person, or company: written permission on file or a public source linked. |
| G9 | Length band | Within the platform band from PLAYBOOK playbook 4 / 2 / 3, ±20%. |
| G10 | Mechanical pass | Spell/grammar check run with zero errors; every link clicked and working; renders correctly on mobile. |

## Scored dimensions (0–4 each)

0 = absent · 2 = competent but generic · 4 = top-decile. Anchors below define 2 vs 4; interpolate for 1 and 3.

| Dimension | A "2" looks like | A "4" looks like |
|---|---|---|
| Hook strength | Relevant but generic: "How to improve your onboarding emails." | Specific tension in one line: "87% of our trial signups never came back. One email sequence fixed a third of that." |
| Specificity | Some examples, but round numbers and unnamed tools ("a client," "recently," "a lot faster"). | Named tools, exact numbers, dates, before/after artifacts the reader could screenshot. |
| Structure | Main idea present but the piece detours; sections vary in purpose. | Every section advances one thesis; the argument can be retold from the subheads alone. |
| Skimmability | Subheads exist but walls of text remain; key lines buried mid-paragraph. | Subhead every ≤300 words; no paragraph >4 lines on mobile; bold/bullets carry the argument; a 15-second skim delivers the takeaway. |
| Actionability | Reader knows *what* to do but not *how* to start. | Reader could do it today: steps, thresholds, and a template or worked example included. |
| Voice fit | Grammatical and clear, but interchangeable with any competitor's blog. | First-hand experience, stated opinions, and ≥2 voice markers from STYLE-VOICE.md present. |
| Proof density | Claims mostly asserted; one example carries the whole piece. | Every major claim is shown, not told: a number, an example, or an artifact per claim. |
| CTA fit | CTA present but generic ("check out our product") or temperature-mismatched. | One low-friction CTA that is the natural next step of exactly this piece, at the right temperature. |

**Total: /32. Publish ≥22 with no dimension ≤1.**

**Score log (paste into the asset file header and the tracker):**

```
scored: 2026-07-09 by B          # or by GLM + name of human who confirmed
gates:  G1–G10 all PASS          # or list failures
dims:   hook 3 · spec 4 · struct 3 · skim 4 · action 3 · voice 2 · proof 3 · cta 3 = 25/32
verdict: PUBLISH                  # PUBLISH / REVISE / ESCALATE(cjudge)
```

Rules for scorers:
- Score the piece as a stranger would read it, not as the author intended it.
- When torn between two scores, give the lower one — inflation makes the rubric useless.
- Never revise and score in the same sitting; swap pieces with the other person when possible.

## Kill list

Automatic fail (gate G4). Search case-insensitively; includes close variants.

**Phrases:**
- "in today's fast-paced world" / "in today's digital age" / "in the ever-evolving landscape"
- "delve" / "dive into" or "deep dive" as an opener
- "unlock" / "unleash" / "harness the power of"
- "game-changer" / "game-changing" / "revolutionize" / "revolutionary"
- "take your X to the next level" / "elevate your"
- "seamless" / "seamlessly" / "robust" as filler adjectives
- "it's important to note" / "it's worth noting" / "it should be mentioned"
- "at the end of the day" / "when all is said and done"
- "whether you're a X or a Y" audience-hedging opener
- "look no further" / "your one-stop shop"
- "in conclusion" / a final section titled "Conclusion"
- "the world of X" / "navigating the world of"
- "let's face it" / "we've all been there" / "it's no secret that"
- "leverage" where "use" works
- "I hope this helps" / "hope you're doing well" as an email open
- "gone are the days" / "in a world where"
- "cutting-edge" / "state-of-the-art" for anything we sell
- "let that sink in" / "read that again" as a standalone line

**Patterns:**
- Opening with a rhetorical question to no one: "Have you ever wondered…?"
- "This isn't just X — it's Y" contrast-slop, or chained "Not X. Not Y. Just Z."
- Listicle where every item is advice the reader has already heard, with no example or number attached.
- An invented persona scenario: "Imagine Sarah, a busy marketing manager…"
- Hedge stacks: "might potentially help to consider."
- A closing paragraph that restates every section ("To summarize, we covered…").
- Tricolon filler: "faster, smarter, better" triples with interchangeable words.
- More than 5 hashtags on any platform.
- Emoji clusters (3+ in a row) or a rocket emoji on a business claim.
- Every paragraph the same length (uniform 2-2-2-2 rhythm reads machine-made).
- Title Case On Every Subhead (sentence case per STYLE-VOICE.md).
- "Agree? ♻️ Repost" or "Follow for more" as the entire CTA, with no idea-specific ask.
- A stat with no unit, base, or timeframe ("engagement went up 300%") — of what, from what, over what period?
- Any sentence that would survive unchanged in a competitor's post — if it's true of everyone, it's proof of nothing.
