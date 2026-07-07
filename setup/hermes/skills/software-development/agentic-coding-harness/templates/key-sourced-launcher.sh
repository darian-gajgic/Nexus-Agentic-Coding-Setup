#!/usr/bin/env bash
# TEMPLATE — generic key-sourcing launcher for a CLI tool that reads an OpenAI-compatible env.
# Copy to ~/.local/bin/<tool>-<flavor>, set KEYFILE + ENV_NAME + the exec line.
# Keeps secrets out of shell history/rc files. Verified working 2026-07-03 (aider-glm).

set -euo pipefail

KEYFILE="${KEYFILE:-$HOME/.glm-agent/key.env}"
# Source the key file (export-all) if present; silent if not.
[ -f "$KEYFILE" ] && { set -a; . "$KEYFILE"; set +a; }

# Set the OpenAI-compatible base + key. Fall back to env/sensible defaults.
export OPENAI_API_BASE="${GLM_BASE_URL:-https://api.z.ai/api/coding/paas/v4}"
export OPENAI_API_KEY="${ZAI_API_KEY:-${OPENAI_API_KEY:-}}"

# Replace the exec line with your target tool:
exec aider "$@"
