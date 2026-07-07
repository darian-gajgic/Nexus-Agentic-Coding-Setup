# Memory Architecture & Setup Audit Methodology

Two operational patterns for managing the Hermes agent's own memory and for
preparing a setup for external review. Both developed 2026-07-04.

## 1. Three-Layer Memory Split

When the agent has BOTH the built-in memory block AND a semantic memory
provider (supermemory, mem0, etc.), the two fight each other unless roles are
explicitly assigned. The problem manifests as "tools not being used properly"
and "forgetting mid-session" — the agent doesn't know which layer to write to
or read from.

### The split

| Layer | What lives here | Injection |
|---|---|---|
| **Memory block** (built-in, `~/.hermes/config.yaml` memory settings) | STABLE FACTS + IRON RULES only: hardware, OS, model preferences, behavioral rules, keyboard layout, user role | Always injected, every turn. Keep under ~25% of capacity. |
| **Semantic provider** (supermemory etc.) | EPISODIC context: project state, session outcomes, decisions, "what did we decide about X" | Searched on demand (auto_recall) |
| **Skills** | PROCEDURAL how-to: debugging recipes, setup modification steps, workflows | Loaded via `skill_view` when relevant; only short descriptions injected per turn |

### How to enforce it

Write the split rule INTO the memory block as an iron rule, e.g.:
"Write episodic state to supermemory (NOT this block). Procedures go in skills."

Without the rule being explicit in the always-injected context, the split
won't be followed.

### The memory-block bloat failure mode

A common cause of "forgetting mid-session" and "losing the goal": the memory
block fills up with process notes, debugging logs, and session outcomes (the
things that belong in supermemory or skills). These compete with the actual
goal for attention every turn. When pruning:
- Move procedural notes → a skill (load on demand)
- Move episodic state → supermemory (search on demand)
- Keep only: stable user/environment facts + behavioral rules
- Target: under 25% of capacity so there's room to grow

## 2. Setup-Audit Preparation Pattern

When invoking an expensive external model (e.g. a strong frontier model on a
paid tier) to review an agent setup, write a SYSTEM_OVERVIEW first so the
reviewer's context window is spent on ANALYSIS, not EXPLORATION.

### Why

A reviewer reading config.yaml + all skill files + AGENTS.md (which alone is
~70KB) + hooks + CLAUDE.md burns 50K+ tokens discovering what it could read in
4-5KB of structured overview. The overview also embeds the WHY behind
decisions, which files can't convey.

### What the overview must contain

A single Markdown file (~10-15KB) covering:
1. The user & the goal (who is this for, what are they trying to achieve)
2. Hardware & OS
3. Model & provider stack (primary, secondary, auxiliary, fallback — with
   reasoning and known limits)
4. Key config settings (table form)
5. Skills architecture (counts, what's enabled/disabled and why)
6. Memory architecture (the layers, capacities, usage)
7. MCP servers / plugins (what each does)
8. Integrations (e.g. Claude Code hooks, settings)
9. Cron / scheduled jobs
10. Known gaps & problems (the reviewer should address these explicitly)
11. What's intentionally NOT here
12. Cost posture
13. Desired outcome of the audit (specific questions to answer)

### The prompt that accompanies it

Separate file. Structures the audit into parts (Architecture Review, Blind
Spots, prioritized action plan, honest verdict). Key constraints to bake in:
- Review-only, no modifications
- Anti-sycophancy: "be direct, disagree, don't just confirm"
- Cite specific files/settings when making points
- Split recommendations into MUST-FIX / SHOULD-FIX / CONSIDER-LATER

### How to use

Put both files in a dedicated directory (e.g. `~/hermes-setup-audit/`). Run
the external reviewer from that directory so it sees both files, with
filesystem read access to `~/.hermes` and `~/.claude`.

Example (Claude Code CLI):
```
cd ~/hermes-setup-audit
claude -p "$(cat AUDIT_PROMPT.md)" --model <strong-model> --effort max \
  --allowedTools 'Read,Write,Glob,Grep,Bash' --max-turns 50
```

The `--max-turns 50` matters: architecture review with file exploration needs
more turns than typical coding. Partial output (early audit parts) is still
useful if it doesn't finish.
