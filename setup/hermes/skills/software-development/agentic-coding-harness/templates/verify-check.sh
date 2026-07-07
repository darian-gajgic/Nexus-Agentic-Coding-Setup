#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# verify-check.sh — PostToolUse(Write|Edit) verify gate for Claude Code (any flavor).
# Install at ~/.claude-glm/hooks/verify-check.sh (or ~/.claude/hooks/) and register in
# settings.json under hooks.PostToolUse (matcher "Write|Edit"). Reproduce with modifications.
#
# After any code edit: look for a project-level <project>/.claude/check.sh; if it exists and
# is executable, run it from the PROJECT ROOT on the edited file. On non-zero exit, BLOCK and
# feed the output back so the agent self-corrects instead of declaring done on broken code.
# If no check.sh exists, silently allow (project hasn't opted in). Timeout-capped (170s).
# ═══════════════════════════════════════════════════════════
set -uo pipefail
input=$(cat 2>/dev/null || true)
f=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null || echo "")
[ -n "$f" ] || exit 0   # can't tell what was edited -> allow

# Walk up from the edited file looking for <dir>/.claude/check.sh
dir="$(cd "$(dirname "$f")" 2>/dev/null && pwd)"
[ -n "$dir" ] || exit 0
check=""
while :; do
  if [ -x "$dir/.claude/check.sh" ]; then check="$dir/.claude/check.sh"; break; fi
  parent="$(dirname "$dir")"
  [ "$parent" = "$dir" ] && break
  dir="$parent"
done
[ -n "$check" ] || exit 0   # no project gate -> allow

projroot="$(dirname "$(dirname "$check")")"
out=$(cd "$projroot" && timeout 170 env CLAUDE_EDITED_FILE="$f" bash "$check" "$f" 2>&1)
rc=$?
# Build the JSON payload with jq --arg so error output (newlines, quotes) is escaped safely.
# Do NOT use printf | jq — raw newlines in error output make invalid JSON and the block is silently
# swallowed. Must cd to projroot before running check.sh or its relative globs fail.
if [ "$rc" -eq 0 ]; then
  exit 0
elif [ "$rc" -eq 124 ]; then
  jq -nc --arg m "Verify gate ($check) timed out after 170s; skipped. Point check.sh at a faster, focused check." \
    '{systemMessage:$m}' 2>/dev/null || true
  exit 0
else
  msg="Verify gate failed ($check) after editing $f:"$'\n'"$(printf '%s' "$out" | tail -c 4000)"$'\n'"Fix the failing check before continuing."
  jq -nc --arg d block --arg r "$msg" '{decision:$d, reason:$r}' 2>/dev/null || true
  exit 0   # exit 0 so Claude Code reads the decision from the JSON payload
fi
