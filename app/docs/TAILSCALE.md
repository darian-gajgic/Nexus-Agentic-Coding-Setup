# Nexus over Tailscale — tailnet-only access (Block 1)

**Hard rule: Nexus is NEVER exposed to the public internet.** It executes
shell commands; the only remote path is the private tailnet.

## How it works

- The server keeps binding `127.0.0.1:8777` (loopback, self-signed HTTPS) —
  nothing about the local security posture changes.
- `tailscale serve` reverse-proxies it **inside the tailnet only** at
  `https://<machine>.<tailnet>.ts.net` with a real, browser-trusted
  Tailscale certificate (so the mic and WebSockets work on phones with no
  warnings).
- `tailscale funnel` is the public variant — **never enable it** for Nexus.

## One-time setup (on this machine)

```bash
sudo -v                          # open a sudo window
bash scripts/setup_tailscale.sh  # idempotent: install → up → serve
```

The first `tailscale up` prints a login URL — sign in with your tailnet
account. `serve --bg` persists across reboots (state in tailscaled).

## Adding the phone / the second laptop

1. Install the Tailscale app (iOS/Android/Windows/macOS/Linux).
2. Sign in to the SAME tailnet account, or send a **share invite** from the
   Tailscale admin console (Users → Invite) so she has her own account.
3. Open `https://<machine>.<tailnet>.ts.net` — with 2+ Nexus users
   configured, the login screen appears; each person signs into their own
   Nexus account (Settings → Users & access to create accounts).

## Checks

```bash
tailscale serve status    # should show :443 → https+insecure://127.0.0.1:8777
tailscale funnel status   # should show NOTHING enabled
ss -tlnp | grep 8777      # nexus itself still bound to 127.0.0.1 only
```

## Turning remote access off

```bash
sudo tailscale serve --https=443 off   # stop serving Nexus into the tailnet
sudo tailscale down                    # or drop off the tailnet entirely
```
