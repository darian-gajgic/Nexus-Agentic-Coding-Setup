# SaaS Business Playbook

Operating procedure for SaaS strategy work done by this team's AI agents and reviewed by the humans.
Scope: our own SaaS products. Client work → `domains/consulting-bizdev/`. Shop products → `domains/ecommerce/`.

Before running any playbook below:
1. Load `~/knowledge/BUSINESS-CONTEXT.md` — which product, stage, MRR, runway, constraints.
2. Load `~/knowledge/STYLE-VOICE.md` for anything customer-facing.
3. Score the finished work against `RUBRIC.md` before delivering. No exceptions.

---

## Operating principles

1. **Sell before you build.**
   Why: code is the most expensive way to learn nobody wants it; a pre-order or signed LOI is the cheapest.
2. **Niche until it hurts.**
   Why: a 2-person team wins by being the obvious #1 for 500 specific people, never #47 for 5 million.
3. **Charge from day one.**
   Why: free users give you feedback about a free product — a product you are not building.
4. **Retention beats acquisition.**
   Why: signups poured into a leaky bucket buy nothing; fixing churn compounds every month afterward.
5. **Distribution is a product decision.**
   Why: only build for markets 2 people can reach (search, communities, marketplaces, existing audience) — never markets that need a sales team.
6. **Talk to customers weekly; never ask what to build.**
   Why: they are experts in their problem and amateurs in your solution — mine problems, design solutions yourself.
7. **Price against the alternative, not your costs.**
   Why: costs set the floor, the customer's next-best option sets the ceiling — most indie SaaS sits 5x too close to the floor.
8. **Every feature is a permanent tax.**
   Why: support, docs, bugs, migrations forever — on a 2-person team, cutting is a growth strategy.
9. **Do things that don't scale until ~$10k MRR.**
   Why: manual onboarding calls ARE the activation flow at this stage, and double as customer interviews.
10. **Know your default-alive number.**
    Why: months-of-runway and self-sustaining-MRR, recomputed monthly, change the right answer to almost every decision below.

---

## Task playbooks

### 1. Positioning (category, ICP, differentiation)

Use when: new product, homepage rewrite, "what do we say we are", entering a new segment.
Output: a one-pager in the shape of `examples/positioning-onepager.md`.

1. List 10 alternatives the target customer uses TODAY.
   - Must include at least one non-software option: "spreadsheet", "email", "do nothing", "intern does it".
2. Pull evidence: 5 interviews with recent buyers or trials (script in playbook 7). Extract:
   - what they used before,
   - the trigger event that made them look,
   - the words they used for the problem (verbatim — these become copy).
3. List capabilities ONLY we have vs. those alternatives.
   - Empty list → STOP. Positioning cannot fix a parity product; escalate as a product problem.
4. Map each unique capability → the value it creates → who cares about that value most.
   - The "who cares most" cluster is the ICP candidate.
5. Write the ICP as: role + company size/type + observable situation + trigger event.
   - Test: could you build a list of 100 of them this week? No → it's a demographic, not an ICP. Redo.
6. Choose the category frame:
   - Existing category ("a CRM") — only if we win a head-to-head feature/price comparison. Rare for us.
   - Subcategory ("a CRM for wedding photographers") — DEFAULT for a 2-person team.
   - New category ("we invented revenue archaeology") — FORBIDDEN below ~$1M ARR; market education costs more than we have.
7. Draft the one-pager from the exemplar template. All launch/homepage copy derives from it afterward — no freelancing.
8. Cold-read test: 3 ICP members (or closest proxies) read it for 30 seconds.
   - Pass = each can say what it is, who it's for, and why not the obvious alternative — in their own words.
   - Any jargon they stumble on gets replaced with their words.
9. Freeze it. Positioning changes ship only through frontier review (see escalation section).

**Decision rule:** torn between two ICPs → pick the one with (a) a trigger event detectable from outside, and (b) an existing watering hole we can reach.

### 2. Pricing (value metric, tier design, testing changes)

1. Pick the value metric — the unit customers pay per. It must pass ALL three:
   - (a) grows as the customer gets more value,
   - (b) understood in 5 seconds,
   - (c) predictable in advance by the buyer (unpredictable bills cause churn).
   - Seats, projects, orders, contacts usually pass; API calls and GB of storage usually fail (c).
2. Compute the value anchor: what does the problem cost the ICP per month?
   - hours × their rate, or revenue lost, or the tool/person it replaces.
   - Price the middle tier at roughly 10% of that number.
3. Design 3 tiers, no more:
   - Low: solo/starter, deliberately cramped on the value metric. Exists to make Middle look sane.
   - Middle: where 60%+ of revenue should land; the ICP's obvious choice.
   - High: 3–5x Middle; adds what bigger teams need (roles, SSO, priority support). Anchor first, revenue second.
4. Gate tiers on the value metric + at most 2 features.
   - A 15-row feature matrix is for enterprises with pricing teams, not us.
5. Offer annual at 10–20% off, default-highlighted. Cash now beats MRR optics for a self-funded team.
6. **Raise-price triggers** — check quarterly, any ONE fires a 20% raise for new customers:
   - zero price complaints in 90 days;
   - >40% of demos/trials convert without a price objection;
   - support cost per account exceeds the Low tier price.
7. **Testing a change:**
   - Never A/B test price at our volume — noise swamps signal.
   - Change for NEW signups only; run one full sales-cycle cohort (min 4 weeks).
   - Compare conversion × ARPU against the prior cohort, not against the first week.
8. **Existing customers:** grandfather them, or give 60–90 days written notice plus a 1-year price-lock offer.
   - Springing a raise on payers is how a small SaaS commits suicide in public.

**Hard rules:**
- Never compete on price — someone with lower costs always wins that race.
- Never discount to close. Extend the trial or add onboarding help instead; discounts train buyers to haggle and leak into public.

### 3. MVP scoping and cutting

Output: a scope-cut doc in the shape of `examples/mvp-scope-cut.md`.

1. Write the ONE job story: "When [situation], I want to [motivation], so I can [outcome]."
   - One sentence. Needing two job stories = scoping two products. Pick one.
2. Dump every candidate feature into a list — aim for completeness, 15–25 items, no pre-filtering.
3. Tag each item:
   - **CORE** — the job story fails without it.
   - **ADJACENT** — helps the job.
   - **PERIPHERAL** — serves a different job.
4. Kill all PERIPHERAL. Kill ADJACENT unless build cost < 2 days AND it removes a known objection.
5. For every survivor ask: can a human fake it (concierge), or a script + email replace the UI?
   - If it will touch <20 users, fake it.
6. Timebox: 4 weeks to a version one stranger can use end-to-end and pay for.
   - Overflow → cut scope. Never extend the timeline. Never cut quality of the core path.
7. For every cut feature write an **earn-it-back criterion** — an observable event that reopens the discussion.
   - Good: "3 paying customers ask unprompted", "cited in 2 churn interviews".
   - No criterion = the cut was arbitrary. Rubric gate G6 fails.
8. Definition of done: one real user completes the core job with zero help from us, and payment works.
   - "Demos well" is not done. "Would be done after a small fix" is not done.

**Decision rule:** arguing KEEP vs CUT for >10 minutes → CUT. A wrong cut costs one build later; a wrong keep costs maintenance forever (principle 8).

### 4. Activation & onboarding design

1. Define ONE activation event = the first moment the user receives the core value.
   - Must be countable in the database: "sent first invoice", "first client approved a deliverable".
   - "Completed profile" or "finished tour" is never it.
2. Measure time-to-value (TTV) from signup to that event.
   - Target for self-serve: same session, under 10 minutes.
3. List every step from landing page → activation event. Count clicks, form fields, decisions, waits.
4. Cut or defer everything not strictly required to reach the event.
   - Profile, team invites, preferences, billing details — all post-activation.
5. Never land users on an empty screen.
   - Pre-load a sample project / template / demo data they can poke, replaced by their own on first real action.
6. Instrument the funnel step-by-step. Weekly: find the single biggest drop-off, fix only that, re-measure.
   - One fix per week beats a redesign per quarter.
7. Until volume forbids: personally email or call EVERY signup within 24h.
   - This is support, marketing, and user research in one motion (principle 9).
8. One automated nudge: no activation within 48h → plain-text email from a founder with ONE link to the next step.

**Thresholds:**
- Signup→activation 30–50% is healthy for self-serve SaaS (verify current benchmarks).
- Below 20% → feature freeze. Nothing new gets built until onboarding is fixed — every marketing hour is being burned at the door.

### 5. Metrics that matter for a 2-person SaaS

Track weekly, in a spreadsheet, by hand, until ~100 customers. Hand-updating forces looking; dashboards rot.

1. **MRR split into** new + expansion − contraction − churned.
   - The split tells the story; the total hides it.
2. **MRR growth rate:** 10–20%/month is strong early-stage (verify current benchmarks).
   - Flat for 3 consecutive months = stop and diagnose (funnel? churn? market?) — do not "push harder".
3. **Activation rate** (playbook 4): 30–50% healthy self-serve (verify current benchmarks).
4. **Week-4 retention curve by signup cohort:** the curve must FLATTEN.
   - Flattens at any decent level = someone truly needs this.
   - Slides toward zero = no product-market fit, and no marketing spend fixes it.
5. **Gross revenue churn:** <2%/mo good; 3–5%/mo tolerable pre-PMF with SMB customers; >7%/mo = fire, drop everything (verify current benchmarks).
   - SMB logo churn runs 3–5%/mo naturally (small businesses die); don't panic against enterprise benchmarks (<1%).
6. **Quick ratio** = (new MRR + expansion) ÷ (churned + contraction).
   - >4 excellent · 2–4 okay · <1 shrinking in disguise.
7. **CAC in founder-hours.** At our scale spend is time, so money-CAC lies.
   - Track hours-per-acquired-customer per channel; kill channels above 2x the median.
8. **NRR** once >50 customers: >100% = expansion outruns churn (the compounding engine).
   - Under 90% → build expansion paths (usage growth, tier upgrades) before buying more acquisition.

**Vanity list — never report as progress:** total registered users, page views, social followers, GitHub stars, waitlist size, "pipeline".

### 6. Launch playbook

A launch is a repeatable marketing event, not a birth. Run the same play for v1, big features, milestones — quarterly if possible.

**Pre-launch (2–4 weeks out):**
1. Push 10 friendly users through the full flow; fix everything that blocked or confused ≥2 of them.
2. Positioning one-pager finalized (playbook 1). All launch copy derives from it.
3. Pricing live and tested with a real card. Analytics + error tracking wired. Support inbox staffed.
4. Assets ready: 5 clean screenshots, a ≤60-second demo video, 3 title/copy variants per channel, FAQ of the 10 objections already heard.
5. Channel list built: the 3–5 communities where the ICP actually is (subreddits, niche Slack/Discords, forums, newsletters), plus Product Hunt / Show HN only if the audience genuinely overlaps.
   - Read each community's self-promotion rules NOW, not launch morning.

**Launch week:**
6. One channel per day, not all at once — you can only converse in one place at a time, and the comments ARE the launch.
7. Reply to every comment/question within 1 hour during waking hours. Founders replying is the growth hack.
8. Capture every objection verbatim into the feedback log (playbook 7). Objections are positioning bugs.
9. Ship a visible fix or improvement daily during launch week, and say so in the thread.

**Post-launch:**
10. Day 7 and day 30: funnel review — visits → signups → ACTIVATED → paid, by channel.
    - Judge channels on activated users, never on traffic.
11. Write a 10-line retro: which channel worked, which objection repeated, what you'd cut next time. File it beside this playbook.
12. Schedule the next launch before the glow fades.

**Decision rule:** launch when the core job works end-to-end and payment works. Embarrassing UI is not a blocker; a broken signup is. Not slightly embarrassed = launched late.

### 7. Customer feedback loops

**Interviews:**
1. Standing quota: 2 per week, every week, forever.
   - Sources: new signups, recent activations, and every cancellation.
2. Script rule: past behavior only — "Walk me through the last time [problem] happened."
   - BAN future/hypothetical questions; "would you use/pay for X" produces polite lies.
3. 30 minutes, recorded with consent, 5-whys on the problem behind any feature request.
4. Churn interviews within 48h of cancel.
   - Do NOT offer a save-discount during the interview — it poisons the answer. Save offers go in a separate, later email.

**Support mining:**
5. Tag every ticket: `bug` / `confusion` / `feature-request` / `pricing` / `praise`.
6. Weekly 30-minute tag review.
   - Same `confusion` 3+ times = product fix (UI copy, flow) — not a docs article. Docs are where confusion fixes go to be ignored.
7. Quote of the week: lift one verbatim customer sentence into the marketing-copy candidates file (voice per `~/knowledge/STYLE-VOICE.md`).

**Roadmap discipline:**
8. Feature requests land in a request log: requester, plan/tier, verbatim quote, underlying job.
   - NEVER straight onto the roadmap.
9. Prioritize by (paying customers affected × frequency of the job) ÷ build cost.
   - A loud user counts once. Check the log for how many DISTINCT payers asked.
10. Answer every request with a decision:
    - "shipping", or
    - "logged — here's the trigger that would change it", or
    - "no, because [reason]".
    - Silence loses trust; auto-yes loses the product.

---

## Junior mistakes

1. **Building for 3 weeks without talking to a user.**
   Correction: max 5 working days between customer conversations while building anything new.
2. **Copying a big competitor's pricing/positioning page.**
   Correction: they solve a different ICP with 200 employees; run playbooks 1–2 from OUR alternatives and OUR value anchor.
3. **"One more feature before launch."**
   Correction: apply playbook 3 step 8 — if a stranger can do the job and pay, launch; the feature goes to the earn-it-back log.
4. **Reporting traffic/signups as success.**
   Correction: report activated users and MRR movement; traffic is an input, not an outcome.
5. **Asking "would you pay for this?"**
   Correction: banned question. Ask what they did last time, or ask for actual money (pre-order/LOI).
6. **Positioning as "like X but cheaper."**
   Correction: forbidden frame — reposition on a niche or capability, or escalate as a product problem.
7. **Discounting to close a hesitant buyer.**
   Correction: extend the trial or offer onboarding help; the price stands.
8. **Rebuilding the roadmap around one loud customer.**
   Correction: log the request, count distinct paying requesters, apply playbook 7 step 9.
9. **Onboarding that ends on an empty screen.**
   Correction: sample data/template first-run; activation event reachable within 10 minutes (playbook 4).
10. **Comparing our metrics to VC-scale benchmark blog posts.**
    Correction: use playbook 5 ranges, flag "(verify current benchmarks)", and mind SMB vs enterprise churn baselines.
11. **Grand redesigns to fix a funnel.**
    Correction: one biggest-drop-off fix per week, re-measure, repeat.
12. **Surprise price increases on existing customers.**
    Correction: grandfather, or 60–90 day notice + price-lock offer, always (playbook 2 step 8).

---

## Escalate to frontier review when…

High-stakes here = hard to reverse, touches money already committed, or speaks publicly for the brand.
Process: run the draft through `cjudge` for a frontier-model second review BEFORE delivery. Attach the RUBRIC score and the specific question you want challenged.

Escalate when ANY of these is true:

1. Pricing changes affecting existing paying customers — raises, plan removals, value-metric changes.
2. Positioning/category changes — anything that rewrites the homepage promise or renames the product.
3. Kill/sunset decisions for a product or feature customers currently pay for.
4. Committing >2 weeks of dev time to a single bet — new product, major rebuild, platform migration.
5. Public flagship launch copy — v1 launch, Product Hunt page, anything press-facing.
6. Legal/contractual surface — refund policy, terms changes, data-handling promises, compliance claims.
7. Numbers leaving the building — investor updates, partner decks; every figure re-checked against source data first.

If in doubt whether it qualifies: it costs one `cjudge` run to find out. Cheap insurance.
