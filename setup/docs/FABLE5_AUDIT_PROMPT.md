## Context

I'm working on auditing and hardening a Hermes Agent installation for a 2-person freelancing team (softwaredevelopement over a broad spectrum + SaaS + consulting + research + marketing + business developement + content creation + brand developement work + ecommerce + DJ + music production). The user is a software developer new to AI agent setup who has been building this by trial-and-error, his girlfirend is just about to finish her study for e-commerce. They want a senior architect's review to catch blind spots and make improvement recommendations before they start real client work. They need a competent AI setup to help them with there freelancing work and everyday tasks as much as possible with the best possible results since they are just 2 persons. A good setup here is the foundation for them to succeed or fail with there plan. A cheaper model (GLM-5.2 / Opus 4.8) will implement your recommendations afterward, so your job is analysis, make improvement recomendations and a plan, not implementation.

A complete snapshot of the setup is in `SYSTEM_OVERVIEW.md` in this directory — read it first. It covers hardware, models, config, the 45 enabled skills, three-layer memory architecture, MCP servers, Claude Code integration, cron, and known gaps.

## The task

Audit this Hermes Agent setup and produce an `AUDIT_REPORT.md` (in this directory) with a prioritized action plan so the user can start client work with confidence.

The user specifically wants your judgment on:
- Is the architecture coherent for their goal? 
- Is the agent sub agent and skill architecture setup and wiring correct and state of the art using hermes as main orchestration agent and make him create and save agents used more frequently like web research in the Agents OS to save updates on instructions and a memory for each agent so each agent improves over time?
- Configuration correctness: verify if this is actually configured correctly. A silently misconfigured file is a failure waiting to happen during client work — surface any you find.
- Blind spots the user (learning by doing) and the current agent (too close to the setup) can't see — failure modes that haven't surfaced, scalability limits, workflow bottlenecks for a 2-person team.
- Improvement opportunities: not just "is this correct now" but "how could this be better." Identify specific improvements that would meaningfully increase output quality or automate work for their goal.
- The 2-person team question: one shared profile, separate Hermes profiles, or something else? What does the second team member's marketing/design/brand workflow need that's missing?
- What must be fixed or implemented BEFORE real client work vs. what can wait.
- I made some modification on hemes, we have to make sure they do not get overwritten by a new update from hermes.
- The laptop sometimes gets shut down and restarted. The system has to handle that, so it's not losing anything and restarting everything on a reboot of the laptop. 

## How to work

- Use parallel subagents to read different parts of the setup concurrently (skills directory, config files, Claude Code integration, hooks, AGENTS.md). This is a strength of yours — use it.
- Before reporting a claim about the setup in your report, verify it against what you actually read in the files. If SYSTEM_OVERVIEW.md conflicts with the real files, trust the files and note the discrepancy. If something is not yet verified, say so explicitly.
- Give recommendations, not exhaustive surveys. If you're weighing options, pick one and justify it.
- Be direct and opinionated. The user explicitly does NOT want sycophancy or generic advice. If something is wrong, say so and explain why. If you disagree with a choice that was made, say that too.
- Because this technology is changing fast, use web research instead of relying on your trainingdata to get the latest information in order to make sure your recommendations work with the latest versions of each tool in the installed setup.

## Boundaries

This is review only. Do NOT modify any config, files, or settings under `~/.hermes/` or `~/.claude/`. Do NOT install or uninstall anything. You may read any file there and run read-only diagnostics (ollama list, hermes config get, nvidia-smi, etc.). The only write you are permitted is the `AUDIT_REPORT.md` output file in THIS directory (/home/sinep/hermes-setup-audit/). Do not run anything destructive.

## Output

Write `AUDIT_REPORT.md` in this directory. Lead with the outcome — your overall assessment in the first sentence. Then: the prioritized action plan (MUST fix before client work / SHOULD fix soon / CONSIDER later), each item with what to change, why, and rough effort. Include your judgment on the vision problem and the 2-person team question. End with an honest verdict: where is this setup genuinely strong, where weakest, and what would you do differently from scratch.

When you finish, your first sentence should be the TLDR — what you found and the single most important recommendation. Supporting detail comes after.

