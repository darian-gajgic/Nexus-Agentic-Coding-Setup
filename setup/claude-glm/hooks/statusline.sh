#!/usr/bin/env bash
# Statusline for the GLM agent: model · dir · git branch · context% (defensive parsing).
set -uo pipefail
input=$(cat 2>/dev/null || true)

get() { printf '%s' "$input" | jq -r "$1 // empty" 2>/dev/null || echo ""; }

model=$(get '.model.display_name'); [ -z "$model" ] && model=$(get '.model.id'); [ -z "$model" ] && model="GLM"
dir=$(get '.workspace.current_dir'); [ -z "$dir" ] && dir=$(get '.cwd'); [ -z "$dir" ] && dir="$PWD"
ctx=$(get '.context.used_pct'); [ -z "$ctx" ] && ctx=$(get '.cost.context_used_pct')

base=$(basename "$dir" 2>/dev/null || echo "$dir")
branch=""
if git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  branch=$(git -C "$dir" branch --show-current 2>/dev/null || echo "")
fi

out="⚡ ${model}  📁 ${base}"
[ -n "$branch" ] && out="${out}  ⎇ ${branch}"
[ -n "$ctx" ] && out="${out}  🧠 ${ctx}%"
# Optional upgrade: replace this script with `npx ccusage statusline` for live cost.
printf '%s' "$out"
