#!/usr/bin/env bash
# PostToolUse(Write|Edit) auto-formatter for the GLM agent.
# Best-effort: formats the edited file if a formatter is available. Never blocks (exit 0).
set -uo pipefail
input=$(cat 2>/dev/null || true)
f=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null || echo "")
[ -n "$f" ] && [ -f "$f" ] || exit 0

case "$f" in
  *.js|*.jsx|*.ts|*.tsx|*.mjs|*.cjs|*.json|*.jsonc|*.css|*.scss|*.less|*.html|*.vue|*.svelte|*.md|*.markdown|*.yaml|*.yml)
    if command -v prettier >/dev/null 2>&1; then prettier --write "$f" >/dev/null 2>&1 || true
    else npx --no-install prettier --write "$f" >/dev/null 2>&1 || true; fi ;;
  *.py)
    if command -v ruff >/dev/null 2>&1; then
      ruff format "$f" >/dev/null 2>&1 || true
      ruff check --fix "$f" >/dev/null 2>&1 || true
    elif command -v black >/dev/null 2>&1; then black -q "$f" >/dev/null 2>&1 || true; fi ;;
  *.go)  command -v gofmt   >/dev/null 2>&1 && gofmt -w "$f"   >/dev/null 2>&1 || true ;;
  *.rs)  command -v rustfmt >/dev/null 2>&1 && rustfmt "$f"    >/dev/null 2>&1 || true ;;
  *.sh|*.bash) command -v shfmt >/dev/null 2>&1 && shfmt -w "$f" >/dev/null 2>&1 || true ;;
esac
exit 0
