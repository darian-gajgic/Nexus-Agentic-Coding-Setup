> TEMPLATE EXEMPLAR — illustrative names/numbers; adapt via BUSINESS-CONTEXT.md

# MVP Scope Cut — "ClientLoop" (same illustrative product as positioning-onepager.md)

Produced by `PLAYBOOK.md` → Task playbook 3 (steps referenced inline).
Input: the founders' raw 20-feature wish list, collected verbatim, no pre-filtering (step 2).
Output: a 4-week MVP one stranger can use end-to-end and pay for — plus a kill log with earn-it-back triggers.

## The one job story (playbook 3, step 1)

> **When** I send a deliverable to a client, **I want** one place where they can view it, comment, and formally approve it, **so I** have an unambiguous record and fewer unpaid revision rounds.

Every item below is judged against this sentence and nothing else.
Tags (step 3): **CORE** = job story fails without it · **ADJACENT** = helps the job · **PERIPHERAL** = different job.

---

## Verdict 1 of 4 — KEEP: the spine (6 items)

| # | Feature | Tag | Why it survives |
|---|---|---|---|
| 1 | Client project page via magic link (no client account) | CORE | The "one place" in the job story; also differentiator #1 on the positioning page |
| 2 | Deliverable upload | CORE | No deliverable, no job |
| 3 | Comment thread per deliverable | CORE | "Comment" is in the job story; without it feedback returns to email and the record fragments |
| 4 | One-click Approve with timestamp + approver + version | CORE | The entire point — the record that ends disputes |
| 5 | Email notifications (new deliverable / comment / approval) | CORE | Clients live in email; without notifications nobody returns and the loop dies |
| 6 | Stripe subscription checkout | CORE (business) | Charge from day one (principle 3); "payment works" is part of the definition of done (step 8) |

## Verdict 2 of 4 — NARROW: kept, deliberately cramped (2 items)

**7. File versioning** — ADJACENT, narrowed to CORE-sized.
- Wish-list version: full version history with visual diffs.
- MVP version: "Replace file" creates v2, v3…; a plain list of versions; NO diffing.
- Rationale: the record needs "client approved v3", not pixel comparisons. ~4 days of work becomes ~0.5 day.

**8. File preview** — ADJACENT, narrowed.
- Wish-list version: inline preview for every format including video and Figma embeds.
- MVP version: inline images + PDF; every other format is a download link.
- Rationale: covers ~90% of web-studio deliverables (illustrative — verify against real pilot uploads); each additional format is days of work and a permanent tax (principle 8).

## Verdict 3 of 4 — FAKE: concierge behind the curtain (2 items) (step 5)

**9. Project templates per service type**
- How we fake it: WE set up each pilot studio's first project by hand on a 15-minute call — which doubles as onboarding and a customer interview (principles 6 and 9).
- Formalize when: >20 active studios, OR setup calls exceed 3 hours/week.

**10. Studio analytics dashboard**
- How we fake it: a monthly plain-text email compiled by hand from the database — approvals count, average time-to-approve, open items.
- Formalize when: 3+ studios reply asking for more frequent or deeper numbers.

## Verdict 4 of 4 — CUT: kill log with earn-it-back triggers (10 items) (steps 4 and 7)

**11. Client accounts + passwords + SSO** — ADJACENT
- Kill rationale: magic links do the job with LESS friction; accounts are the #1 failure of rival tools (see positioning alternatives table).
- Earn it back when: a security/compliance objection blocks ≥3 otherwise-closed deals.

**12. White-label / custom domains** — ADJACENT
- Kill rationale: vanity at n=0 customers; days of DNS/SSL edge cases; zero effect on the job story.
- Earn it back when: 3 paying customers ask unprompted AND accept a higher tier for it.

**13. Invoicing & client payments** — PERIPHERAL
- Kill rationale: different job ("get paid"), brutal competition, compliance surface; the positioning one-pager explicitly concedes it.
- Earn it back when: cited as a primary switching reason in 2 churn interviews.

**14. Time tracking** — PERIPHERAL
- Kill rationale: different job; crowded market; 0/9 pilot studios mentioned it unprompted (illustrative).
- Earn it back when: 5 distinct paying studios request it with a concrete workflow attached.

**15. Contracts / e-signature** — PERIPHERAL
- Kill rationale: legal weight — if the trail is ever challenged, this feature decides a lawsuit. Automatic escalation territory, not a casual add.
- Earn it back when: approvals-as-contract demand is proven in interviews — and only WITH `cjudge` frontier review + a real legal check (PLAYBOOK escalation item 6).

**16. Slack integration** — ADJACENT
- Kill rationale: the ICP's CLIENTS are not in the studio's Slack; email already closes the loop (item 5).
- Earn it back when: 3 paying studios name the exact Slack workflow it would replace.

**17. Native mobile app** — ADJACENT
- Kill rationale: responsive web already covers "client opens the link on a phone"; app stores add weeks plus review friction.
- Earn it back when: >30% of client sessions are mobile AND mobile approval completion lags desktop by >15 percentage points.

**18. AI deliverable summaries** — PERIPHERAL
- Kill rationale: demo candy; summarizing a homepage mockup helps nobody complete the job story.
- Earn it back when: a validated job appears in interviews — never because "AI would be cool" (junior mistake pattern).

**19. Public API / Zapier** — ADJACENT
- Kill rationale: an integration surface is the most permanent of all taxes (principle 8) — versioning, docs, support — at n=0.
- Earn it back when: 3 integration requests each naming the exact trigger→action they would wire.

**20. Internal kanban / task board** — PERIPHERAL
- Kill rationale: internal project management is a different job; Trello/ClickUp own it; the positioning page concedes it on purpose.
- Earn it back: never as a board. If "where does my project stand" recurs in tickets, the answer is a status field on the project page — not a PM tool.

**Scorecard: 6 kept, 2 narrowed, 2 faked, 10 cut.** More killed than kept — rubric D3 passes.

---

## The 4-week build order (playbook 3, step 6)

**Week 1 — see the work.**
- Studio signup/auth, create project, upload deliverable, magic-link client page (read-only).
- Demoable milestone: a real client can SEE a real deliverable via one link.

**Week 2 — close the loop.**
- Comment threads, replace-file versioning (item 7), email notifications (item 5).
- Demoable milestone: full feedback round-trip without anyone touching email attachments.

**Week 3 — the record.**
- Approve action with timestamp/approver/version, approval-record export (simple PDF), inline image+PDF preview (item 8).
- Demoable milestone: the job story completes end-to-end.

**Week 4 — take money and harden.**
- Stripe checkout (item 6), plan gate (e.g., 3 active projects on Starter — illustrative), empty-state polish on the ONE core path, error tracking, 10 friendly-user runs (launch playbook, pre-launch step 1).
- Demoable milestone: a stranger signs up, completes the job, and pays — definition of done (step 8).

**Overflow rule (pre-committed):** if Week 3 slips, the PDF export moves post-launch — a screenshot of the approval record is the interim export. The Approve action itself never moves; it IS the product.

---

## Why this works

Annotations for juniors — tie each move back to `PLAYBOOK.md` / `RUBRIC.md`:

1. **One job story, written first.**
   Every dispute below it became cheap: "does the job story fail without this?" is answerable in seconds; "is this feature nice?" is answerable never (playbook 3, steps 1–3).
2. **The tags do the arguing.**
   CORE/ADJACENT/PERIPHERAL turns scope fights into classification questions a junior or a GLM-5.2 agent can settle without taste. Item 20 shows the discipline: "different job" kills a feature even though every competitor has it.
3. **NARROW is a separate verdict from KEEP.**
   The classic failure is keeping "versioning" and accidentally building a month of diff views. Writing the cramped version down ("replace file = v2") caps scope explicitly and records the effort saved.
4. **Concierge before code** (items 9–10).
   Manual setup calls and hand-compiled emails deliver the value at <20 users AND double as interviews (principles 6, 9). The "formalize when" threshold stops concierge from silently becoming the permanent unbuilt product.
5. **Every cut has an observable trigger** (gate G6).
   "3 paying customers ask unprompted" is countable in the request log (playbook 7, step 8); "maybe later" is not. Triggers name PAYING customers — free users asking for white-label count for nothing.
6. **Cut rationales cite evidence and positioning, not preference.**
   Items 13, 14, and 20 die partly because the positioning one-pager already conceded those jobs. Scope and positioning must agree, or the product drifts back toward "all-in-one" (kill-list item 3).
7. **Item 15 shows the escalation reflex.**
   A cut can carry conditions beyond demand: anything with legal weight routes its earn-it-back path through `cjudge` review. Juniors should notice that "enough customers asked" is not always sufficient.
8. **The overflow rule is pre-committed.**
   Deciding what slips BEFORE the slip removes the week-3 panic negotiation (step 6: cut scope, never the timeline, never core-path quality).
9. **Payment is inside the MVP, not after it.**
   Junior instinct says "add billing once validated" — but paying IS the validation (principle 3). Week 4 exists so launch day can take money.
10. **Illustrative numbers are labeled** ("0/9 pilots", "~90% of uploads") — gates G4/G8. The shape of the evidence is the lesson; the values must be re-measured for a real product.

## Adapt this

Pull real inputs from `~/knowledge/BUSINESS-CONTEXT.md`. Keep the verdict structure (KEEP / NARROW / FAKE / CUT) — it is the deliverable format for any scope-cut request.

- {{FILL: the one job story — if stakeholders propose two, force the pick before any tagging (playbook 3 step 1)}}
- {{FILL: the full wish list, 15–25 items — collect verbatim from founders/notes first; do not pre-filter, the kill log is half the value}}
- {{FILL: tag verdicts — re-tag from YOUR job story; the same feature (e.g., invoicing) can be CORE in a different product}}
- {{FILL: narrow verdicts — for each kept-but-big feature, one sentence describing the cramped v1 plus the effort saved}}
- {{FILL: concierge candidates — anything servable by hand below ~20 users, each with a formalize-when threshold}}
- {{FILL: earn-it-back triggers — countable events from YOUR request log / churn interviews / funnel, always scoped to paying customers}}
- {{FILL: build order — max 4 weeks to "stranger completes the job and pays"; name each week's demoable milestone}}
- {{FILL: overflow rule — which item slips first, decided now, in writing}}
- {{FILL: escalation flags — mark any keep/cut touching legal exposure, existing payers' money, or >2-week bets for `cjudge` review (PLAYBOOK escalation section)}}
