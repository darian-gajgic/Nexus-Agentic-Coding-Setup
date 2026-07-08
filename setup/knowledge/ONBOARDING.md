# ONBOARDING — personalize the Business Brain (run once, ~20 min)

**Primary path — the Nexus wizard (recommended):** open the Nexus dashboard →
click **🚀 Start the guided onboarding** on the dashboard banner (or Settings →
Business Brain). It walks you through every blank section by section, explains
what each answer changes in the system, saves as you go (stop and resume
anytime), and is **per-user**: the owner's answers become these canonical
files; every other Nexus user gets their own personal context under
`users/<id>/` that their tasks use automatically. The pristine questionnaires
live in `templates/` — the wizard reads those, so it can be re-run to revise
answers even after these files are filled.

**Alternative — terminal interview** (if you prefer talking it through):

```bash
cd ~/knowledge && claude
```

then say: **"Read ONBOARDING.md and run the onboarding interview."**

---

## Instructions for the interviewing Claude

You are personalizing this knowledge base for its owners (two juniors running a multi-domain
micro-business). Goal: replace every `{{FILL: ...}}` slot with real information, gathered through
a focused interview. Do NOT lecture; interview.

1. **Read first:** `BUSINESS-CONTEXT.md`, `STYLE-VOICE.md`, and skim one PLAYBOOK.md to
   understand the structure. Collect all `{{FILL}}` slots (grep for `{{FILL` across the repo).

2. **Interview in 4 short rounds** (use AskUserQuestion where options make sense, free text
   otherwise; German or English — match the user):
   - Round 1 — the team: names/roles/strengths, hours available, languages/markets.
   - Round 2 — the ventures: for each active venture (SaaS, client work, shop, music): what it
     is, audience, stage, links, current numbers they know. Skip ventures they say are dormant.
   - Round 3 — audience & assets: channels, list sizes, handles, what has worked so far.
   - Round 4 — voice & constraints: how they want to sound (show them the STYLE-VOICE defaults,
     ask what to change), budget ceilings, hard constraints, this quarter's 3 goals.

3. **Rewrite the files:** update `BUSINESS-CONTEXT.md` and `STYLE-VOICE.md` completely (no
   remaining {{FILL}} slots — write "n/a — <reason>" where truly not applicable). Where domain
   exemplars have {{FILL}} slots that now have obvious values (brand names, product names),
   update those too — but do NOT rewrite whole exemplars.

4. **Close the loop:** `git add -A && git commit -m "onboarding: personalize business context
   + voice"`. Then give the users a 5-bullet summary of what changed and ONE suggested next
   deliverable per active venture (something an agent could produce this week using the packs).

Keep the whole thing under ~25 minutes of their time. Batch questions; don't ask one at a time.
