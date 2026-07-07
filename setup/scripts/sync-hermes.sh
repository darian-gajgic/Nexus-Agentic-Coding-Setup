#!/usr/bin/env bash
# Refresh the hermes/, guardian/ and systemd/ snapshots in this repo from the
# LIVE setup on this machine. Allowlist-based and secret-scanned: it copies
# only known-safe customization files, never ~/.hermes/.env, key.env, session
# state, personal memories, kanban/state DBs, reports, or caches — and it
# ABORTS if anything in the export looks like a credential.
#
# Usage:  bash scripts/sync-hermes.sh
# Then:   git diff --stat && git add hermes guardian systemd && git commit && git push
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
H="$HOME/.hermes"
G="$HOME/hermes-guardian"
UPSKILLS="$H/hermes-agent/skills"

# ── hermes core config (keys live in .env, which is NEVER copied) ──
mkdir -p "$REPO_DIR/hermes"
cp "$H/SOUL.md"     "$REPO_DIR/hermes/SOUL.md"
cp "$H/config.yaml" "$REPO_DIR/hermes/config.yaml"
cp "$H/mem0.json"   "$REPO_DIR/hermes/mem0.json"

# ── specialists: 18 active + archive (definitions only — *.md; the personal
#    .pending_lessons.json and any .git metadata never match this glob) ──
rm -rf "$REPO_DIR/hermes/agents"
mkdir -p "$REPO_DIR/hermes/agents/archive"
cp "$H"/agents/*.md "$REPO_DIR/hermes/agents/"
cp "$H"/agents/archive/*.md "$REPO_DIR/hermes/agents/archive/" 2>/dev/null || true

# ── learning-pipeline scripts ──
rm -rf "$REPO_DIR/hermes/scripts"
mkdir -p "$REPO_DIR/hermes/scripts"
cp "$H"/scripts/*.py "$H"/scripts/*.sh "$REPO_DIR/hermes/scripts/"

# ── user-level plugins (specialist_router, zai provider override, …) ──
rm -rf "$REPO_DIR/hermes/plugins"
rsync -a --exclude='__pycache__' "$H/plugins/" "$REPO_DIR/hermes/plugins/"

# ── skills: OURS only = not shipped upstream, or modified vs upstream ──
rm -rf "$REPO_DIR/hermes/skills"
mkdir -p "$REPO_DIR/hermes/skills"
for d in "$H"/skills/*/; do
  name="$(basename "$d")"
  if [ -d "$UPSKILLS/$name" ] && diff -rq "$UPSKILLS/$name" "$d" >/dev/null 2>&1; then
    continue  # identical to upstream — not ours to snapshot
  fi
  rsync -a --exclude='__pycache__' --exclude='index-cache' "$d" "$REPO_DIR/hermes/skills/$name/"
done

# ── guardian: code + patches + golden copies (NO runtime state or reports) ──
rm -rf "$REPO_DIR/guardian"
mkdir -p "$REPO_DIR/guardian"
cp "$G/guardian.py" "$G/core-mods.json" "$G/manifest.json" "$REPO_DIR/guardian/"
rsync -a "$G/patches/" "$REPO_DIR/guardian/patches/"
rsync -a "$G/golden/"  "$REPO_DIR/guardian/golden/"

# ── systemd user units ──
mkdir -p "$REPO_DIR/systemd"
cp "$HOME"/.config/systemd/user/hermes-*.service \
   "$HOME"/.config/systemd/user/hermes-*.timer \
   "$HOME"/.config/systemd/user/nexus.service "$REPO_DIR/systemd/"

# ── keep this repo's own .gitignore files inside synced dirs ──
git -C "$REPO_DIR" checkout -- guardian/.gitignore hermes/agents/.gitignore 2>/dev/null || true

# ── provenance ──
{
  echo "source: ~/.hermes + ~/hermes-guardian + systemd user units (local)"
  echo "agents: $(ls "$REPO_DIR"/hermes/agents/*.md | wc -l) active + $(ls "$REPO_DIR"/hermes/agents/archive/*.md 2>/dev/null | wc -l) archived"
  echo "skills: $(ls -d "$REPO_DIR"/hermes/skills/*/ | wc -l) (custom or modified-vs-upstream only)"
  echo "exported-at: $(date -Is)"
} > "$REPO_DIR/hermes/.snapshot-provenance"

# ── HARD secret scan: abort the sync if anything looks like a REAL credential
#    (documentation placeholders like sk-xxxx…, ghp_XXXX…, <your-key> are ignored) ──
HITS="$(grep -rInE "(sk-[A-Za-z0-9_-]{16,}|gho_[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{16,}|AKIA[A-Z0-9]{12,}|xox[baprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|Bearer +[A-Za-z0-9._-]{20,}|[a-f0-9]{32}\.[A-Za-z0-9]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY|(api[_-]?key|auth[_-]?token|password)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9+/_.-]{16,})" \
    "$REPO_DIR/hermes" "$REPO_DIR/guardian" "$REPO_DIR/systemd" \
  | grep -vEi "x{6,}|\*{4,}|<[a-z_-]*(key|token|secret)|your[_-]|example|placeholder|redacted" || true)"
if [ -n "$HITS" ]; then
  echo "$HITS"
  echo "ABORT: the lines above look like credentials — fix the source, re-run."
  exit 1
fi

echo "OK — no credential patterns found."
echo "Review with: git -C $REPO_DIR diff --stat"
