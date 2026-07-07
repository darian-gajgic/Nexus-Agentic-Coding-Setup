# Aider on a custom OpenAI-compatible endpoint (GLM/Z.AI, Ollama, vLLM, LiteLLM, etc.)

Aider speaks the OpenAI Chat Completions API, so any OpenAI-compatible endpoint works. The trick
is giving Aider the right base URL + key WITHOUT polluting the shell or printing secrets.

## The pattern: a key-sourcing launcher script

Put a tiny wrapper in ~/.local/bin that (1) sources the key file with `set -a`, (2) exports
OPENAI_API_BASE + OPENAI_API_KEY, (3) execs aider. Keeps the key out of shell history and rc files.

### Working example — GLM-5.2 via Z.AI (aider-glm)
```bash
#!/usr/bin/env bash
set -euo pipefail
[ -f "$HOME/.glm-agent/key.env" ] && { set -a; . "$HOME/.glm-agent/key.env"; set +a; }
export OPENAI_API_BASE="${GLM_BASE_URL:-https://api.z.ai/api/coding/paas/v4}"
export OPENAI_API_KEY="${ZAI_API_KEY:-${OPENAI_API_KEY:-}}"
exec aider "$@"
```

### Working example — local/free Ollama (aider-local)
```bash
#!/usr/bin/env bash
set -euo pipefail
MODEL="${AIDER_MODEL:-ollama/qwen3:14b}"
exec aider --model "$MODEL" --editor-model "$MODEL" "$@"
```
Ollama needs no key; Aider's `ollama/` model prefix hits http://localhost:11434.

## Global config (~/.aider.conf.yml) — drives the architect/editor split
```yaml
model: openai/glm-5.2          # planner (architect)
editor-model: openai/glm-5.2   # executor (edits)
architect: true
auto-commits: true
auto-accept-architect: true
map-tokens: 2048               # repo-map context budget
```
Override per-run: `aider-glm --architect --editor-model ollama/qwen2.5:14b`.

## Why architect mode (the quality verdict, not just token-saving)
Aider's own benchmark: pairing a planner model with an editor model measurably improves correctness
on multi-file refactors vs a single model end-to-end. Biggest gain is for weaker models and for
changes touching 2+ files / architectural decisions. Result quality goes up — it's not only cheaper.

## Key gotcha
`OPENAI_API_BASE` must be the base up to the version segment (e.g. `…/paas/v4`), NOT including
`/chat/completions` — Aider appends the path. If the model errors with 404, the base is wrong.
