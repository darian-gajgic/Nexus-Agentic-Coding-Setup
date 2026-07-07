#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# PRE-COMMIT GATE — blocks bad code from entering the repo
# Runs verify.sh (syntax + API + function integrity).
# Browser tests run if server is live.
# ═══════════════════════════════════════════════════════════
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

echo "━━━ PRE-COMMIT GATE ━━━"

# Stash any unstaged changes so we test what's actually staged
STASHED=false
if ! git diff --quiet || ! git diff --cached --quiet; then
  # Only stash if there are unstaged changes (not the staged ones)
  if ! git diff --quiet; then
    git stash push --keep-index -m "pre-commit-auto" >/dev/null 2>&1
    STASHED=true
  fi
fi

cleanup() {
  if $STASHED; then
    git stash pop >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# 1. Run static verification
if ! bash scripts/verify.sh; then
  echo ""
  echo "❌ PRE-COMMIT BLOCKED: verify.sh failed"
  echo "Fix the issues above, then re-commit."
  echo "To bypass (NOT RECOMMENDED): git commit --no-verify"
  exit 1
fi

# 2. Run browser verification if server is running
if curl -sf http://localhost:8777/api/jarvis/status >/dev/null 2>&1; then
  echo ""
  echo "━━━ BROWSER VERIFY (server detected) ━━━"
  if ! node scripts/browser-verify.mjs 2>&1; then
    echo ""
    echo "❌ PRE-COMMIT BLOCKED: browser-verify.mjs failed"
    echo "The page has runtime errors. Fix them before committing."
    exit 1
  fi
fi

echo ""
echo "✅ PRE-COMMIT PASSED — all gates green"
exit 0
