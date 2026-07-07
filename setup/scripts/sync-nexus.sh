#!/usr/bin/env bash
# Pull the latest nexus-agent-os into the nexus/ SUBTREE of this repo.
# Since the `unified` merge, nexus/ is a real git subtree (squashed import),
# not an rm-rf+copy snapshot: this pulls the committed tree of the live repo
# (~/nexus-agent-os) as one squash commit — still secret-free by construction,
# because only files committed to nexus's git can arrive (nexus.db, certs,
# .env, workspaces/, models/ are gitignored there).
#
# Usage:  bash scripts/sync-nexus.sh        # pull ~/nexus-agent-os HEAD into nexus/
# Then:   git push
# Reverse (push edits made under nexus/ here back to the live repo):
#         git subtree push --prefix=nexus "$NEXUS_SRC" <branch>
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${NEXUS_SRC:-$HOME/nexus-agent-os}"

[ -d "$SRC/.git" ] || { echo "ERROR: $SRC is not a git repo"; exit 1; }
if [ -n "$(git -C "$SRC" status --porcelain --untracked-files=no)" ]; then
  echo "ERROR: $SRC has uncommitted tracked changes — commit them first (the"
  echo "subtree mirrors a committed state so it is reproducible)."
  exit 1
fi
if [ -n "$(git -C "$REPO_DIR" status --porcelain --untracked-files=no)" ]; then
  echo "ERROR: this repo has uncommitted changes — commit/stash them first"
  echo "(subtree pull creates a merge commit)."
  exit 1
fi

HEAD_SHA="$(git -C "$SRC" rev-parse --short HEAD)"
echo "Subtree-pulling nexus @ $HEAD_SHA -> $REPO_DIR/nexus/"
git -C "$REPO_DIR" subtree pull --prefix=nexus "$SRC" master --squash \
  -m "sync: nexus subtree pull @ $HEAD_SHA"
echo "Done. Review with: git -C $REPO_DIR log --oneline -3"
