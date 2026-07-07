#!/usr/bin/env bash
# Nexus-Agentic-Coding-Setup installer — installs the full Nexus Agent OS
# (with the repo-native agentic-coding feature) onto a new machine.
#
# PREREQUISITES (this script checks, but does not install them):
#   - Hermes Agent installed with its gateway on http://localhost:8642
#     (GLM_API_KEY configured; serena + context7 MCP servers recommended)
#   - python3 (3.11+) and git
#
# Usage:  bash install.sh [target-dir]     (default: ~/nexus-agent-os)
set -euo pipefail

TARGET="${1:-$HOME/nexus-agent-os}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "== Nexus Agent OS installer =="

# ── preflight ──
command -v python3 >/dev/null || { echo "FATAL: python3 not found"; exit 1; }
command -v git >/dev/null || { echo "FATAL: git not found"; exit 1; }
if ! curl -s --max-time 3 http://localhost:8642/health >/dev/null 2>&1; then
  echo "WARN: Hermes gateway not answering on :8642 — Nexus will start, but"
  echo "      dispatch/JARVIS need it. Install/start Hermes first for full function."
fi
if [ -e "$TARGET/nexus.db" ]; then
  echo "FATAL: $TARGET already has a nexus.db — refusing to overwrite an install."
  echo "       Move it away or pick another target dir."
  exit 1
fi

# ── files ──
echo "-- Copying app tree to $TARGET"
mkdir -p "$TARGET"
rsync -a "$HERE/app/" "$TARGET/"

# ── python env ──
echo "-- Creating venv + installing requirements (this takes a few minutes)"
python3 -m venv "$TARGET/.venv"
"$TARGET/.venv/bin/pip" install --upgrade pip -q
"$TARGET/.venv/bin/pip" install -r "$TARGET/requirements.txt" -q
"$TARGET/.venv/bin/playwright" install chromium >/dev/null 2>&1 || \
  echo "WARN: playwright browser download failed — UI verify gates need it (rerun later)."

# ── HTTPS cert (self-signed; browser mic + HTTPS-only frontend need it) ──
if [ ! -f "$TARGET/cert.pem" ]; then
  echo "-- Generating self-signed certificate"
  openssl req -x509 -newkey rsa:2048 -keyout "$TARGET/cert.key" \
    -out "$TARGET/cert.pem" -days 3650 -nodes -subj "/CN=127.0.0.1" 2>/dev/null
fi

# ── Hermes-side: dev specialists (LSP navigation + Big-Code rules) ──
if [ -d "$HOME/.hermes/agents" ]; then
  echo "-- Installing dev specialists into ~/.hermes/agents (backing up originals)"
  for f in "$HERE"/files/hermes-agents/*.md; do
    base="$(basename "$f")"
    [ -f "$HOME/.hermes/agents/$base" ] && cp "$HOME/.hermes/agents/$base" \
      "$HOME/.hermes/agents/$base.bak-pre-agentic-coding" || true
    cp "$f" "$HOME/.hermes/agents/$base"
  done
else
  echo "WARN: ~/.hermes/agents not found — skipping specialist install."
  echo "      Install Hermes first, then: cp files/hermes-agents/*.md ~/.hermes/agents/"
fi

# ── systemd user unit ──
echo "-- Installing systemd user unit"
mkdir -p "$HOME/.config/systemd/user"
sed "s|/home/sinep/nexus-agent-os|$TARGET|g" "$HERE/system/nexus.service" \
  > "$HOME/.config/systemd/user/nexus.service"
systemctl --user daemon-reload
systemctl --user enable nexus >/dev/null 2>&1 || true

echo
echo "== Done. Start with:  systemctl --user start nexus"
echo "   Dashboard:         https://127.0.0.1:8777  (accept the self-signed cert)"
echo "   First run creates nexus.db and seeds default settings automatically."
echo
echo "NOT included (by design):"
echo "  - JARVIS voice models (optional; see app/requirements-voice.txt +"
echo "    docs/JARVIS-VOICE.md — needs a GPU + Piper/whisper/Wav2Lip assets)"
echo "  - Your task history/workspaces (runtime data stays on each machine)"
echo
echo "Sanity check:  cd $TARGET && bash scripts/verify.sh"
