#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# NEXUS — Tailscale exposure (Block 1). TAILNET ONLY, NEVER PUBLIC.
#
# Design (docs/SPEC-MULTIUSER.md §7):
#   - Nexus keeps binding 127.0.0.1:8777 (loopback — security posture
#     unchanged; this box executes shell commands, it must never face the
#     internet).
#   - `tailscale serve` publishes it INSIDE the tailnet only, at
#     https://<machine>.<tailnet>.ts.net with a REAL Tailscale certificate
#     (browser-trusted → mic/WebSocket work on phones with no cert warnings).
#   - NEVER use `tailscale funnel` — that is the public-internet variant.
#
# Usage:
#   sudo -v                              # open a sudo window first
#   bash scripts/setup_tailscale.sh      # idempotent; re-run any time
#
# Devices: install the Tailscale app on the phone/laptop, sign into the SAME
# tailnet (or accept a shared invite), then open the printed URL.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

# 1. Install (official apt repo) — skipped if already present
if ! command -v tailscale >/dev/null 2>&1; then
  echo "── Installing tailscale (needs sudo) ──"
  CODENAME=$(. /etc/os-release && echo "${VERSION_CODENAME:-noble}")
  # fall back to the latest LTS repo if tailscale doesn't publish for this release yet
  if ! curl -fsIL "https://pkgs.tailscale.com/stable/ubuntu/${CODENAME}.noarmor.gpg" >/dev/null 2>&1; then
    echo "(no tailscale repo for '${CODENAME}' yet — using 'noble')"
    CODENAME=noble
  fi
  curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${CODENAME}.noarmor.gpg" \
    | sudo -n tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
  curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${CODENAME}.tailscale-keyring.list" \
    | sudo -n tee /etc/apt/sources.list.d/tailscale.list >/dev/null
  sudo -n apt-get update -qq
  # Vet first (system-change rule): show what would change, then install
  sudo -n apt-get install -s tailscale | grep -E "^(Inst|Remv)" || true
  sudo -n apt-get install -y tailscale
else
  echo "tailscale already installed: $(tailscale version | head -1)"
fi

# 2. Bring the node up (opens a browser login the FIRST time)
if ! tailscale status >/dev/null 2>&1; then
  echo "── tailscale up (a login URL will be printed — open it) ──"
  sudo -n tailscale up --ssh=false
fi

# 3. Tailnet-only HTTPS reverse proxy to the loopback-bound Nexus
#    (serve = tailnet-only; funnel would be public — never use it here)
echo "── Configuring tailscale serve → https://127.0.0.1:8777 ──"
sudo -n tailscale serve --bg --https=443 https+insecure://127.0.0.1:8777

echo
echo "── Status ──"
tailscale serve status || true
HOST=$(tailscale status --json 2>/dev/null | python3 -c \
  "import sys, json; print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))" 2>/dev/null || echo "<machine>.<tailnet>.ts.net")
echo
echo "Nexus is now reachable INSIDE your tailnet at:  https://${HOST}"
echo "  • Other devices (phone, second laptop): install Tailscale, join the same"
echo "    tailnet, open that URL. Login screen appears once 2+ users exist."
echo "  • Public internet exposure: NONE (verify: tailscale funnel status)"
