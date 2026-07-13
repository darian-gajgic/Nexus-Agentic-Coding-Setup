# Consulting & BizDev Quality Rubric

> Frontier-judge scoping (2026-07-13): for the text-only frontier judge, a gate whose evidence cannot appear on the page and is not contradicted by the task's artifacts is UNVERIFIABLE-HERE (a note), not FAIL — the cjudge verdict contract governs: only binding in-scope gate FAILs and critical/high findings block a SHIP.

Quality gate for outreach, proposals, and client-facing documents. Apply BEFORE sending.
Order: (1) must-pass gates — one fail = do not send; (2) scored dimensions 0–4.

Ship thresholds:
- Cold outreach: all gates pass AND average ≥ 3.0 AND no dimension ≤ 1.
- Proposals / client docs: all gates pass AND average ≥ 3.3 AND no dimension ≤ 2.
- Anything on the PLAYBOOK.md escalation list → `cjudge` review regardless of score.

## Must-pass gates

All artifacts:
- G1. Recipient and company names spelled exactly as THEY spell them (verify on their site or LinkedIn).
- G2. Every claim about us carries evidence in the text (number, named work, artifact) or has been deleted. No "many clients," no invented figures.
- G3. Exactly one clearly stated next step.
- G4. Zero kill-list phrases (list below).
- G5. No sentence over 35 words; no paragraph over 6 lines; voice per `~/knowledge/STYLE-VOICE.md`.
- G6. No mail-merge artifacts ("Hi {first_name}", stray brackets, mismatched company names).

Cold outreach only:
- O1. Contains ≥ 1 verifiable, prospect-specific fact. Test: could this email be sent unchanged to another company? If yes → FAIL.
- O2. Word counts: touch 1 ≤ 120, bump ≤ 75, breakup ≤ 100.
- O3. Subject ≤ 5 words, no clickbait, no fake "RE:"/"FWD:".
- O4. Exactly one question in the email.
- O5. Max 1 link, zero attachments, plain text.
- O6. Prospect + sequence stage logged in the tracker before sending.

Proposals only:
- P1. Price appears WITH scope boundaries: included list plus ≥ 3 explicit exclusions.
- P2. Success criteria present; each one measurable and dated.
- P3. Payment terms state deposit %, payment triggers, and the late-client-input rule (dates shift 1:1).
- P4. A kill/exit clause exists: client can stop at a defined point at a defined cost.
- P5. Expiry date on the proposal, max 21 days out.
- P6. Named next step with a date — not "let us know."
- P7. Price was verbally bracketed on a prior call (check call notes). If not → do not send; back to the discovery playbook.
- P8. Situation section contains ≥ 2 phrases or numbers taken from the client's own words (check against call notes).

## Scored dimensions (0–4 each)

1. Research depth / listening evidence
   - 2: References something true but surface-level (industry, city, "saw your website").
   - 4: Names a specific finding with a number the prospect never publicized (their LCP, their funnel gap, their exact words from the call).
2. Outcome framing
   - 2: Describes activities ("we'll audit, optimize, implement").
   - 4: Every activity is tied to a business number that moves, with the mechanism stated in one clause.
3. Economy
   - 2: Correct but padded — roughly a third could be cut without losing meaning.
   - 4: Nothing cuttable; a busy reader gets the point in one pass.
4. Ask clarity
   - 2: CTA present but vague or costly ("thoughts?", "book 30 minutes with us").
   - 4: One micro-step answerable in under 10 seconds, with a default offered ("want the list? I'll just send it — no call needed").
5. Scope precision
   - 2: Deliverables listed but edges fuzzy: no exclusions, no dates, no definition of done.
   - 4: Every deliverable has a definition of done; exclusions listed; dates tied to client inputs.
6. Risk reversal
   - 2: Generic reassurance ("satisfaction guaranteed", "we're confident").
   - 4: A concrete mechanism that moves risk onto us: kill-switch with a price, paid pilot, or a guarantee scoped to things we ship.
7. Credibility per claim
   - 2: Claims plausible for a junior team but unevidenced ("we've done this before").
   - 4: Every claim carries its proof — a number, an artifact, a named piece of work, or the homework itself — or was cut.
8. Momentum
   - 2: Correct but shelvable: no date, no reason to answer this week.
   - 4: Contains one TRUE reason to act now (real expiry, real capacity slot, a finding that decays).

## Kill list

Presence of any item = automatic G4 fail. Reject the draft, do not "fix around" it.

Openers and filler:
- "I hope this email finds you well" / "Hope you're doing well"
- "To whom it may concern"
- Opening with our name or company instead of them ("My name is… and we are…")
- "I know you're busy, but…" / "Sorry to bother you" / "I'll keep this short"

Vague-vendor tells:
- "wide range of services", "full-service", "one-stop shop"
- "solutions" as the noun for what we sell
- "cutting-edge", "best-in-class", "world-class", "leading provider"
- "passionate team", "synergy", "leverage" (as a verb), "value-add", "revert back"

Zombie follow-ups:
- "just checking in", "just following up", "touching base", "circling back"
- "bumping this to the top of your inbox", "as per my last email"
- "any thoughts?" as the entire ask

Fake urgency or intimacy:
- "quick question" as a subject line
- fake "RE:" / "FWD:" on a first touch
- "pick your brain", "hop on a quick call" with no stated reason the call helps THEM

Unearned claims:
- "proven track record" / "many clients" / "dozens of businesses" without a named proof
- "guaranteed results" without a mechanism
- Any adjective doing a number's job: "significant", "huge", "massive improvement"

Self-sabotage:
- "we're just starting out, so…" as a price apology
- More than one exclamation mark per artifact
- Emoji in first-touch outreach or in proposals
- Attachment on a first touch
- Three or more CTAs in one message
