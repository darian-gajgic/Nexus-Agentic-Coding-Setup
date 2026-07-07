# Paperclip Self-Host Setup — Gotchas & Working Recipe

Session-specific troubleshooting for self-hosting Paperclip via the official Docker quickstart.
Captured 2026-07-03 after ~5 iterations to get a clean `up`. The Paperclip quickstart is NOT
turn-key — it has several latent setup traps. If you set up Paperclip again, follow this recipe in
order and you'll skip the iterations.

## The repo
- GitHub: paperclipai/paperclip
- Quickstart compose: `docker/docker-compose.quickstart.yml` (embedded PGlite, no external Postgres).
- UI + API on :3100. Data persisted to a bind-mounted volume.

## The traps (hit in this order)

1. **Missing BETTER_AUTH_SECRET.** The compose file requires it (`${BETTER_AUTH_SECRET:?...}`) but
   ships no default. `docker compose config` fails with "required variable BETTER_AUTH_SECRET must
   be set." FIX: generate one (`python3 -c "import secrets; print(secrets.token_hex(32))"`) and put
   it in a `.env` file.

2. **`.env` placement.** Docker Compose loads `.env` from the directory CONTAINING the compose file
   (here `docker/`), NOT the cwd you run `docker compose` from. Putting `.env` only in the project
   root means compose doesn't see it. FIX: place `.env` in BOTH the project root AND the `docker/`
   dir, or use `-f docker/docker-compose.quickstart.yml` from a cwd where compose finds .env.

3. **Bind-mount path resolution.** The volume `${PAPERCLIP_DATA_DIR:-../data/docker-paperclip}` is
   resolved RELATIVE TO THE COMPOSE FILE (docker/), so `../data/docker-paperclip` →
   `<repo>/data/docker-paperclip`, NOT `<parent>/data/...`. Creating the data dir at the wrong
   absolute path = mount fails silently or mounts an empty/owned-by-root dir.

4. **EACCES on mkdir `/paperclip/instances/default/logs`.** The Node app (logger.ts) calls
   `resolveDefaultLogsDir()` which builds a path under PAPERCLIP_HOME and `mkdirSync`s it. If the
   bind-mounted dir's ownership doesn't match what the container process can write, the app crashes
   on boot. Even though the compose runs as root, the host dir ownership must allow the container's
   effective user to write. FIX: chown the data dir to uid 1000 (the `node` user inside the image):
   `sudo chown -R 1000:1000 <repo>/data/docker-paperclip`.

5. **`PAPERCLIP_LOG_DIR` in `.env` doesn't reach the container.** The compose `environment:` block
   does NOT pass through arbitrary vars from `.env` (it only lists specific ones). So setting
   `PAPERCLIP_LOG_DIR=/paperclip/logs` in `.env` has no effect. FIX: create
   `docker/docker-compose.override.yml` that adds it to the environment block AND forces `user: root`.

## Working recipe (proven)

```bash
cd /home/sinep/agent-orchestration/paperclip   # or your clone location
SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
printf 'BETTER_AUTH_SECRET=%s\nPORT=3100\nSERVE_UI=true\n' "$SECRET" > .env
cp .env docker/.env   # compose reads .env from the compose-file dir

# Pre-create + chown the data dir (resolved relative to docker/)
mkdir -p data/docker-paperclip/logs
sudo chown -R 1000:1000 data/docker-paperclip

# Override: force log dir + run as root, because .env vars don't reach the container env block
cat > docker/docker-compose.override.yml <<'EOF'
services:
  paperclip:
    environment:
      PAPERCLIP_LOG_DIR: "/paperclip/logs"
    user: "root"
EOF

# Up
PAPERCLIP_PORT=3100 docker compose -f docker/docker-compose.quickstart.yml -f docker/docker-compose.override.yml up -d

# Verify
curl -sf http://localhost:3100/api/health   # expect {"status":"ok",...}
```

## After it's running

- Pass API keys to let it orchestrate agents: add `ANTHROPIC_API_KEY` / the Z.AI key to `.env` and
  `docker/.env`, restart. For GLM/Z.AI you'll likely need an OpenAI-compatible adapter (the image
  pre-installs claude/codex/opencode/gemini CLIs; GLM may need the hermes_local adapter or an
  opencode adapter pointed at Z.AI).
- Built-in `hermes_local` / `hermes_gateway` adapters exist (per the repo's AGENTS.md, fork
  `HenkDz/paperclip` branch `feat/externalize-hermes-adapter`) — Paperclip can orchestrate Hermes
  directly. Worth exploring if you want Paperclip to drive Hermes agents.
- Control via the `paperclip` launcher: `paperclip up|down|logs|status`.
