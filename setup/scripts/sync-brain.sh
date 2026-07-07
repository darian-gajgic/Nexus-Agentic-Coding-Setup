#!/usr/bin/env bash
# Refresh the knowledge/ (Business Brain), bin/ (frontier bridge) and claude-glm/
# snapshots in this repo from the LIVE setup. Companion to sync-hermes.sh — same
# rules: allowlist-based, never secrets, hard secret-scan abort before finishing.
#
# knowledge/  <- ~/knowledge          (playbooks, rubrics, exemplars, MANUAL, evals;
#                                      BUSINESS-CONTEXT holds team data — repo must stay private)
# bin/        <- ~/.local/bin         (cspec, creview, cjudge — frontier bridge scripts)
# claude-glm/ <- ~/.claude-glm        (GLM Claude Code config; its key lives in
#                                      ~/.glm-agent/key.env and is NEVER copied)
#
# Usage:  bash scripts/sync-brain.sh
# Then:   git diff --stat && git add knowledge bin claude-glm && git commit && git push
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
H="$HOME"

# ── Business Brain (full content, minus git metadata) ──
rm -rf "$REPO_DIR/knowledge"
rsync -a --exclude='.git' "$H/knowledge/" "$REPO_DIR/knowledge/"

# ── frontier bridge scripts ──
mkdir -p "$REPO_DIR/bin"
for f in cspec creview cjudge; do
  cp "$H/.local/bin/$f" "$REPO_DIR/bin/$f"
done

# ── GLM-side Claude Code config (allowlist; no .claude.json/sessions/history) ──
rm -rf "$REPO_DIR/claude-glm"
mkdir -p "$REPO_DIR/claude-glm"
for p in settings.json CLAUDE.md; do
  [ -f "$H/.claude-glm/$p" ] && cp "$H/.claude-glm/$p" "$REPO_DIR/claude-glm/" || true
done
for d in agents commands hooks; do
  [ -d "$H/.claude-glm/$d" ] && rsync -a "$H/.claude-glm/$d" "$REPO_DIR/claude-glm/" || true
done

# ── provenance ──
{
  echo "source: ~/knowledge + ~/.local/bin/{cspec,creview,cjudge} + ~/.claude-glm (local)"
  echo "knowledge-files: $(find "$REPO_DIR/knowledge" -name '*.md' | wc -l) markdown"
  echo "exported-at: $(date -Is)"
} > "$REPO_DIR/knowledge/.snapshot-provenance"

# ── HARD secret scan (same pattern as sync-hermes.sh) ──
HITS="$(grep -rInE "(sk-[A-Za-z0-9_-]{16,}|gho_[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{16,}|AKIA[A-Z0-9]{12,}|xox[baprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|Bearer +[A-Za-z0-9._-]{20,}|[a-f0-9]{32}\.[A-Za-z0-9]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY|(api[_-]?key|auth[_-]?token|password)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9+/_.-]{16,})" \
    "$REPO_DIR/knowledge" "$REPO_DIR/bin" "$REPO_DIR/claude-glm" \
  | grep -vEi "x{6,}|\*{4,}|<[a-z_-]*(key|token|secret)|your[_-]|example|placeholder|redacted" || true)"
if [ -n "$HITS" ]; then
  echo "$HITS"
  echo "ABORT: the lines above look like credentials — fix the source, re-run."
  exit 1
fi

echo "OK — no credential patterns found."
echo "Review with: git -C $REPO_DIR diff --stat"
