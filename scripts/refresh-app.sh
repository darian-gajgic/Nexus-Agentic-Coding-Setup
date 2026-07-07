#!/usr/bin/env bash
# Refresh this package from the live install on the source machine:
# app tree snapshot + git patch + specialist copies. Run before pushing.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$HOME/nexus-agent-os"

rsync -a --delete --delete-excluded \
  --exclude=.git --exclude=.venv --exclude=__pycache__ --exclude=workspaces \
  --exclude=models --exclude=logs --exclude="nexus.db*" --exclude="nexus_archive*" \
  --exclude="*.bak*" --exclude=cert.pem --exclude=cert.key \
  --exclude=jarvis_session.json --exclude=".preview-apps.json" \
  --exclude=templates.user.json --exclude=.claude --exclude=.worktrees \
  "$SRC/" "$HERE/app/"

# curated requirements are package-owned — restore over the source's stub
git -C "$HERE" checkout -- app/requirements.txt app/requirements-voice.txt 2>/dev/null || true

git -C "$SRC" diff > "$HERE/patches/nexus-repo-native-tasks.patch"
cp "$HOME/.hermes/agents/"{code-implementer,tech-lead-orchestrator,code-reviewer,acceptance-verifier,debugger}.md \
   "$HERE/files/hermes-agents/"
cp "$HOME/.config/systemd/user/nexus.service" "$HERE/system/nexus.service"
echo "refreshed — review with: git -C $HERE status"
