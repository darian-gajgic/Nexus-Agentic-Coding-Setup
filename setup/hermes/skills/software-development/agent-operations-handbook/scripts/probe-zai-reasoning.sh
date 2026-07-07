#!/usr/bin/env bash
# probe-zai-reasoning.sh — empirically measure reasoning depth across effort levels.
#
# Calls the Z.AI GLM-5.2 endpoint with each reasoning_effort value and prints
# the reasoning_tokens count from the usage stats, so you can see (a) whether
# the parameter has any effect and (b) what the server default actually is.
#
# Usage:
#   scripts/probe-zai-reasoning.sh          # uses GLM_API_KEY / ZAI_API_KEY from env or ~/.hermes/.env
#   scripts/probe-zai-reasoning.sh "custom prompt"
#
# Source of the endpoint: config.yaml → model.base_url (coding plan endpoint).
# If you get 429 code 1113 on the standard endpoint, you're on the wrong base
# URL — use the coding/paas/v4 path that's actually in your config.
#
# NOTE: this script runs ONE trial per level — good for a quick yes/no signal.
# For comparisons you will publish or defend, run it 3x per level (or wrap the
# probe() calls in a loop) and take the median. Single-run numbers on easy
# prompts are noise (see skill Section 8). Use a genuinely hard prompt.
#
# Part of the agent-operations-handbook skill. See references/provider-parameters.md
# for the full explanation of why this probe is necessary.

set -euo pipefail

# --- resolve API key ---
API_KEY="${GLM_API_KEY:-${ZAI_API_KEY:-}}"
if [[ -z "$API_KEY" && -f "$HOME/.hermes/.env" ]]; then
  API_KEY="$(grep -E '^(GLM_API_KEY|ZAI_API_KEY)=' "$HOME/.hermes/.env" | head -1 | cut -d= -f2- | tr -d '"'"'"'')"
fi
if [[ -z "$API_KEY" ]]; then
  echo "ERROR: set GLM_API_KEY or ZAI_API_KEY (or have it in ~/.hermes/.env)" >&2
  exit 1
fi

BASE_URL="${ZAI_BASE_URL:-https://api.z.ai/api/coding/paas/v4/chat/completions}"
PROMPT="${1:-A bat and a ball cost \$1.10 in total. The bat costs \$1.00 more than the ball. How much does the ball cost? Show your work briefly.}"

echo "Endpoint: $BASE_URL"
echo "Prompt:   $PROMPT"
echo "────────────────────────────────────────────────────────────────────────"
printf "%-28s %s\n" "effort sent" "reasoning_tokens"
echo "────────────────────────────────────────────────────────────────────────"

probe() {
  local label="$1"; shift
  # $@ = extra jq args to build the body; if empty, send no reasoning_effort.
  local body
  if [[ $# -gt 0 ]]; then
    body=$(jq -n --arg p "$PROMPT" --arg e "$1" \
      '{model:"glm-5.2", messages:[{role:"user",content:$p}], thinking:{type:"enabled"}, reasoning_effort:$e}')
  else
    body=$(jq -n --arg p "$PROMPT" \
      '{model:"glm-5.2", messages:[{role:"user",content:$p}], thinking:{type:"enabled"}}')
  fi
  local resp
  resp=$(curl -s -m 120 -X POST "$BASE_URL" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d "$body") || { echo "$label  (request failed)"; return; }
  local tokens
  tokens=$(echo "$resp" | jq -r '.usage.completion_tokens_details.reasoning_tokens // "n/a"')
  if [[ "$tokens" == "n/a" ]]; then
    # Maybe an error — surface it
    local err
    err=$(echo "$resp" | jq -r '.error.message // empty' 2>/dev/null || true)
    printf "%-28s %s%s\n" "$label" "$tokens" "${err:+  (error: ${err:0:80})"
  else
    printf "%-28s %s\n" "$label" "$tokens"
  fi
}

probe "(omitted — server default)"
probe "low"        "low"
probe "medium"     "medium"
probe "high"       "high"
probe "xhigh"      "xhigh"
probe "max"        "max"

echo "────────────────────────────────────────────────────────────────────────"
echo "Interpretation (single-trial — confirm with 3x runs before quoting):"
echo "  - 'max' should produce the MOST reasoning_tokens; 'high' noticeably less."
echo "  - The server default (omitted) for GLM-5.2 is near-max (per Z.AI docs and"
echo "    multi-run measurement ~4930 vs max ~6000 vs high ~2243)."
echo "  - This script probes the Z.AI API directly and bypasses Hermes. It tells"
echo "    you what the API does with each value, NOT what Hermes sends. To check"
echo "    what Hermes actually sends, see skill Section 7 — verify the LIVE"
echo "    registered profile via get_provider_profile('zai').__module__ ."
