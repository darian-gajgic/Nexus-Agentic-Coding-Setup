#!/usr/bin/env bash
# Stop / Notification hook: desktop ping when the GLM agent finishes or needs input.
# Best-effort; needs a graphical session. Never blocks.
set -uo pipefail
# Suppressed during orchestrated fan-out runs (glm-ultra sets this) to avoid per-worker spam.
[ -n "${GLM_NO_NOTIFY:-}" ] && exit 0
input=$(cat 2>/dev/null || true)
msg=$(printf '%s' "$input" | jq -r '.message // "turn finished"' 2>/dev/null || echo "turn finished")
if command -v notify-send >/dev/null 2>&1; then
  notify-send -a "GLM Claude Code" "🤖 GLM agent" "$msg" >/dev/null 2>&1 || true
fi
exit 0
