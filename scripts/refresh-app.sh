#!/usr/bin/env bash
# ⚠ RETIRED (2026-07-09 unification): app/ IS the live working tree now —
# ~/nexus-agent-os is a symlink into this repo, so the old rsync snapshot
# would rsync the directory onto itself and --delete-excluded would WIPE
# runtime data (nexus.db, .venv, workspaces). Commit app/ changes directly.
#
# What still needs refreshing from the live machine is the HERMES side:
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$(readlink -f "$HOME/nexus-agent-os")" = "$(readlink -f "$HERE/app")" ]; then
  echo "app/ is the live tree (symlink verified) — nothing to snapshot."
else
  echo "ERROR: ~/nexus-agent-os is NOT the expected symlink into this repo." >&2
  echo "The old snapshot flow is retired; refusing to rsync." >&2
  exit 1
fi
cp "$HOME/.hermes/agents/"{code-implementer,tech-lead-orchestrator,code-reviewer,acceptance-verifier,debugger}.md \
   "$HERE/files/hermes-agents/"
cp "$HOME/.config/systemd/user/nexus.service" "$HERE/system/nexus.service"
echo "hermes-side files refreshed — review with: git -C $HERE status"
