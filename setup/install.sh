#!/usr/bin/env bash
# Hermes Team Setup — installer.
# Copies our customizations into a fresh Hermes install and applies the core-mods.
# Idempotent-ish; backs up files it would overwrite. Run AFTER installing the base
# tools (Hermes Agent, Docker/qdrant, ollama) — see README.md.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
GUARDIAN_DIR="$HOME/hermes-guardian"
NEXUS_DIR="$HOME/nexus-agent-os"
SYSTEMD_DIR="$HOME/.config/systemd/user"
STAMP="$(date +%Y%m%d_%H%M%S 2>/dev/null || echo backup)"

# The setup was authored under this home; we rewrite it to yours everywhere.
SRC_HOME="/home/sinep"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }

[ -d "$HERMES_HOME/hermes-agent" ] || {
  warn "Hermes install not found at $HERMES_HOME/hermes-agent."
  warn "Install Hermes Agent first (see README.md), then re-run."
  exit 1
}

# 1. Hermes configs + assets ------------------------------------------------
say "Installing Hermes configs, agents, skills, scripts, plugins into $HERMES_HOME"
mkdir -p "$HERMES_HOME"/{agents,skills,scripts,plugins}
for f in config.yaml SOUL.md mem0.json; do
  [ -f "$HERMES_HOME/$f" ] && cp -a "$HERMES_HOME/$f" "$HERMES_HOME/$f.bak-$STAMP"
  cp -a "$REPO/hermes/$f" "$HERMES_HOME/$f"
done
cp -a "$REPO/hermes/agents/."  "$HERMES_HOME/agents/"
cp -a "$REPO/hermes/skills/."  "$HERMES_HOME/skills/"
cp -a "$REPO/hermes/scripts/." "$HERMES_HOME/scripts/"
cp -a "$REPO/hermes/plugins/." "$HERMES_HOME/plugins/"
chmod +x "$HERMES_HOME/scripts/"*.py 2>/dev/null || true

# 2. Guardian ---------------------------------------------------------------
say "Installing guardian into $GUARDIAN_DIR"
mkdir -p "$GUARDIAN_DIR"
cp -a "$REPO/guardian/." "$GUARDIAN_DIR/"

# 3. Nexus (code only; build its venv separately) ---------------------------
say "Installing Nexus into $NEXUS_DIR"
mkdir -p "$NEXUS_DIR"
cp -a "$REPO/nexus/." "$NEXUS_DIR/"

# 4. Rewrite hard-coded paths ($SRC_HOME -> your $HOME) ----------------------
if [ "$SRC_HOME" != "$HOME" ]; then
  say "Rewriting paths $SRC_HOME -> $HOME"
  grep -rIl "$SRC_HOME" "$HERMES_HOME/config.yaml" "$GUARDIAN_DIR" "$NEXUS_DIR" "$REPO/systemd" 2>/dev/null \
    | while read -r f; do sed -i "s|$SRC_HOME|$HOME|g" "$f"; done || true
fi

# 5. systemd user units -----------------------------------------------------
say "Installing systemd user units into $SYSTEMD_DIR"
mkdir -p "$SYSTEMD_DIR"
for u in "$REPO"/systemd/*; do
  base="$(basename "$u")"
  sed "s|$SRC_HOME|$HOME|g; s|User=sinep|User=$USER|g" "$u" > "$SYSTEMD_DIR/$base"
done

# 5b. Frontier bridge scripts (cspec/creview/cjudge) ------------------------
# The Nexus judge pipeline shells out to `cjudge` (settings key judge.cmd) —
# without these on PATH, judging fails with command-not-found on a fresh box.
# They additionally need the `claude` CLI installed and logged in.
if [ -d "$REPO/bin" ]; then
  say "Installing frontier bridge scripts (cspec/creview/cjudge) into ~/.local/bin"
  mkdir -p "$HOME/.local/bin"
  cp -a "$REPO"/bin/. "$HOME/.local/bin/"
  chmod +x "$HOME/.local/bin/cspec" "$HOME/.local/bin/creview" "$HOME/.local/bin/cjudge" 2>/dev/null || true
  command -v claude >/dev/null 2>&1 || warn "the 'claude' CLI is not installed — cjudge/cspec/creview need it (npm i -g @anthropic-ai/claude-code, then 'claude' to log in)"
fi

# 6. Apply the Hermes core-mods (via the guardian) --------------------------
say "Applying core-mod patches to the Hermes source (guardian reconcile)"
PY="$HERMES_HOME/hermes-agent/venv/bin/python"
if [ -x "$PY" ] && [ -f "$GUARDIAN_DIR/guardian.py" ]; then
  # --restore: guardian is verify-only by default; an install is an explicit "apply our mods now"
  "$PY" "$GUARDIAN_DIR/guardian.py" --restore || warn "guardian run reported issues — check core-mods.json version match"
else
  warn "Could not auto-apply core-mods (missing venv or guardian). Apply guardian/patches/*.patch manually."
fi

cat <<EOF

$(say "Done.")
Next:
  1. cp .env.example ~/.hermes/.env   &&   edit it (GLM_API_KEY is required)
  2. Start qdrant:   docker compose -f infra/qdrant-docker-compose.yml up -d
  3. Nexus venv:     (cd $NEXUS_DIR && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt)
  4. systemctl --user daemon-reload
     systemctl --user enable --now hermes-gateway.service hermes-guardian.timer hermes-reflect.timer hermes-prune.timer nexus.service

Verify:  $PY $GUARDIAN_DIR/guardian.py   (expect overall=OK, 5 core-mods)
EOF
