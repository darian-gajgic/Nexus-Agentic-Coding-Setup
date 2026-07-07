---
name: creating-specialist-agents
description: Use when the user asks to create, save, or persist a task or role as a reusable specialist agent (e.g. "make this a persistent agent", "save X as an agent", "create a <role> agent"). Explains the ~/.hermes/agents/ convention this setup uses.
version: 1.0.0
author: hermes-specialists
license: MIT
metadata:
  hermes:
    tags: [agents, specialists, delegation, setup]
    related_skills: [plan]
---

# Creating a persistent specialist agent

This machine has a **specialist-agent registry**: predefined agents that Hermes reuses (via the `delegate_task` tool's `specialist` parameter) for recurring work. Each specialist has its own standing rules (a playbook) and its own private memory. When the user asks to turn a task or role into a persistent/reusable agent, create one as follows.

## How to create one

Write a markdown file to `~/.hermes/agents/<name>.md` where `<name>` is lowercase letters, numbers, and hyphens (e.g. `instagram-post-writer`). It must have YAML frontmatter followed by the playbook body. The exact shape (frontmatter between the two `---` lines, then the body):

    ---
    name: instagram-post-writer
    description: <one line describing WHEN to use this specialist — this is the text the delegating model matches a task against, so make it specific>
    tools: [web, file]
    mem0_agent_id: instagram-post-writer
    ---
    You are the Instagram-post specialist. <the standing rules / how this specialist should do its work — concrete, e.g. "Keep every post under 500 characters", "Lead with a hook", "Always include 3-5 relevant hashtags".>

Steps:
1. `write_file` the content to `~/.hermes/agents/<name>.md`.
2. Commit it: `git -C ~/.hermes/agents add <name>.md && git -C ~/.hermes/agents commit -m "add specialist <name>"`.

## Rules

- `name` and `description` are REQUIRED. The `description` is the "when to use" text — the delegating model reads it to decide whether to reuse this specialist, so make it a precise trigger.
- Set `mem0_agent_id` equal to the name (that is the agent's private memory scope).
- `tools` is an optional allowlist of toolsets the specialist may use (`web`, `file`, `terminal`, ...). Omit to inherit the parent's tools.
- The body is the specialist's **playbook**: concrete standing rules it must follow every time.
- It takes effect immediately — the next matching delegation reuses it, and it appears in the nexus Specialists tab for the user to edit.

## When to use

- The user asks to "make this a persistent/reusable agent", "save this as an agent/specialist", or "create a <role> agent".

## Don't use for

- One-off delegations — those are just normal `delegate_task` calls with no `specialist` set. Only create a specialist when the user wants a *reusable* one.

## Verification Checklist

- [ ] File is at `~/.hermes/agents/<name>.md`, name is lowercase-hyphen
- [ ] Frontmatter has `name`, a specific `description`, and `mem0_agent_id: <name>`
- [ ] Body contains concrete standing rules
- [ ] Committed in the `~/.hermes/agents` git repo
