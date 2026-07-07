# MCP Servers + Memory Layer — Hermes Setup Recipes

> Reusable install recipes discovered 2026-07-03. For the agentic-coding-harness skill.
> These are the non-obvious bits; the obvious bits are in the hermes-agent skill.

## Adding an MCP server to Hermes (bypassing the interactive prompt)

`hermes mcp add` is discovery-first: it connects, lists tools, then asks
"Enable all N tools? [Y/n/select]". In a non-interactive context (scripts, agent
tool calls) the prompt hangs and the add is cancelled. Fix: pipe Y in.

```bash
# stdio server (e.g. Context7, Playwright)
echo "Y" | hermes mcp add <name> --command npx --args -y <package>@latest

# remote/HTTP server
echo "Y" | hermes mcp add <name> --url https://<endpoint>/mcp --auth oauth
```

Verify: `hermes mcp list` (shows status) and `hermes mcp test <name>` (connects +
counts tools). Changes take effect on a NEW session, not mid-conversation (prompt
caching is sacred).

## The MCP starter pack (install only what you have a real workflow for)

Each connected MCP injects ~2-5K tokens of schema on every model call. Do NOT
install a big list on day one — you pay for unused schemas. The consensus
starter pack is THREE, each replacing something:

- **Context7** (`@upstash/context7-mcp`) — pulls current, version-specific
  library docs into the prompt. Replaces "guessing APIs from training data." The
  single highest-value MCP for a coding agent. Pair with a SOUL.md rule that
  auto-triggers it before writing library/framework code.
- **Playwright** (`@playwright/mcp@latest`, Microsoft) — browser automation via
  the accessibility tree (not pixels). Replaces fragile screenshot/pixel agents.
  Works on Wayland (see runtime-verification skill).
- **GitHub MCP** — usually SKIPPED: the `gh` CLI already covers it at 7-32x lower
  token cost. Only add if you have no CLI alternative.

## Memory layer — use the NATIVE plugin, not the MCP route

Hermes ships built-in memory-provider plugins at
`~/.hermes/hermes-agent/plugins/memory/` (supermemory, mem0, byterover, hindsight,
honcho, openviking, retaindb, holographic). This is the correct integration path
— it wires into Hermes' memory system directly (auto-capture, auto-recall,
profile-scoped), unlike a raw MCP server which is just a side-channel tool.

### Supermemory setup (the full sequence)

```bash
# 1. Install the pinned dep into the Hermes venv (it's uv-managed — use uv, not pip)
VIRTUAL_ENV=~/.hermes/hermes-agent/venv uv pip install "supermemory==3.50.0"

# 2. API key → ~/.hermes/.env (chmod 600; .env is secrets-only)
echo "SUPERMEMORY_API_KEY=sm_..." >> ~/.hermes/.env
chmod 600 ~/.hermes/.env

# 3. Flip the provider
hermes config set memory.provider supermemory
```

Verify: `hermes memory status` should show `Provider: supermemory` + `✓ Connected`
+ `auto_recall on` + `auto_capture on`. Memory is container-scoped (`container:
hermes`), so multiple agents can have separate memory layers without crosstalk —
Hermes uses supermemory, Claude Code uses its own (MEMORY.md + knowledge-graph MCP),
they stay independent by design.

### Why not the MCP route for memory
`hermes mcp add supermemory --url https://mcp.supermemory.ai/mcp --auth oauth`
fails headless (OAuth needs a browser) and even with an API key it's a weaker
integration than the native plugin (no auto-capture/recall wiring). Use the plugin.

### Cost note
Supermemory has a genuine free tier (~$5/mo usage, no card, token-level dedup so
re-ingesting the same context is free — important for looping agents). Flag cost
to the user before wiring any paid memory backend, per the cost-transparency rule.
