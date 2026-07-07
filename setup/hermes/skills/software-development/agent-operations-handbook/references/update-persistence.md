# Update Persistence — What Survives `hermes update`

Verified 2026-07-05 against the official docs
(https://hermes-agent.nousresearch.com/docs/getting-started/updating) and the
Hermes source (`hermes_cli/subcommands/update.py`, `providers/__init__.py`,
`tools/skills_sync.py`). Re-verify the update-behavior claims against live
docs before acting on them — this note is a memory aid, not the source of
truth (see skill Section 1).

## The key architectural fact

The git repo lives at `~/.hermes/hermes-agent/`. `hermes update` runs
`git pull` INSIDE that repo only. Everything custom lives OUTSIDE the repo,
under `~/.hermes/`. `git pull` physically cannot touch anything outside its
root, so most customizations are safe by construction.

## What `hermes update` does (in order)

1. **Pairing-data snapshot** — lightweight, unconditional
   (~/.hermes/pairing/, Feishu comment rules, runtime state files).
2. **git pull** on `main` (or `--branch <name>`) inside the repo.
3. **Post-pull syntax validation** — compiles 8 critical files; on failure,
   `git reset --hard <pre-pull-sha>` auto-rolls back so the shell stays
   bootable.
4. **Dependency install** — `uv pip install -e ".[all]"`.
5. **Config migration** — detects NEW config options and prompts to add them.
   Additive only — never overwrites existing values. Backs up config.yaml
   before any rewrite.
6. **Gateway auto-restart**.

## Local source-tree changes on update

Interactive update: Hermes stashes uncommitted changes, pulls, then ASKS
whether to restore them. Non-interactive (desktop/gateway `/update`):
governed by `updates.non_interactive_local_changes` in config.yaml
(default `stash` = keep + auto-restore; alt `discard` = drop the stash).

This setup carries one local-only commit (`048270f` "fix: refresh NVIDIA
featured models", not in origin/main as of 2026-07-05). On update it will
stash/restore; if upstream touched the same lines, resolve the conflict or
`git reset --hard origin/main` if the data is now upstream.

## Risk map for this setup

SAFE — outside git repo, git pull cannot touch:

- **ZAI reasoning_effort override** —
  `~/.hermes/plugins/model-providers/zai/__init__.py`. Verified outside repo.
  This is the update-safe design pattern (a bundled edit would be overwritten).
  Discovery: user plugins load AFTER bundled, last-writer-wins
  (`providers/__init__.py:_discover_providers`).
- **Other user plugins** — wayland_portal, brave_context, local_reader under
  `~/.hermes/plugins/`. Same mechanism.
- **config.yaml** — outside repo. Update MIGRATES (adds new options) but never
  overwrites existing values. Backed up pre-rewrite.
- **.env** (API keys), **SOUL.md**, **MEMORY.md**, **USER.md** — outside repo,
  never touched.
- **MCP server config** (context7, playwright, serena) — defined in
  config.yaml, safe.
- **Cron jobs + scripts** (`error-watchdog.sh`) — `~/.hermes/cron/`,
  `~/.hermes/scripts/`, outside repo.
- **Local skills** (project-ledger, goal-drift-discipline, client-delivery-gate,
  project-orchestration, agent-operations-handbook, etc.) — NOT in the repo,
  `skills_sync` never touches them.
- **Runtime data** — sessions, state.db, auth.json, mem0, kanban.db — all
  outside repo.

PROTECTED BY HASH-CHECK — builtin skills:

- **Builtin skills** (source: builtin) — `skills_sync.py` uses a manifest with
  MD5 origin hashes at `~/.hermes/skills/.bundled_manifest`. If your copy
  matches the origin hash (unmodified), it gets UPDATED from bundled on update
  (you get improvements). If your copy DIFFERS (you customized it), it is
  SKIPPED. So unmodified builtins auto-update; modified builtins are preserved.

## Hardening options (verify against live docs before applying)

1. **Pre-update backup** — `hermes update --backup` creates a full zip of
   `~/.hermes/` (config, auth, sessions, skills, plugins). Or make it
   permanent: `hermes config set updates.pre_update_backup true`. Trade-off:
   adds minutes to each update on large homes.
2. **Clean the stale local commit** — causes a stash/restore cycle every
   update. Check if upstream now includes it
   (`git -C ~/.hermes/hermes-agent log origin/main --oneline | grep -i nvidia`),
   then `git reset --hard origin/main` if safe.
3. **Off-repo backup of `~/.hermes/plugins/`** — the ZAI override would be
   hard to recreate from memory. Back up the dir externally or add it to a
   private dotfiles repo for disaster recovery.

## Post-update verification checklist

```bash
# 1. ZAI override still the live registered profile:
python3 -c "
import sys; sys.path.insert(0, '/home/sinep/.hermes/hermes-agent')
from providers import get_provider_profile as g
print(g('zai').__module__)
"   # expect: _hermes_user_provider_zai

# 2. Reasoning still firing at max:
grep 'zai-override' ~/.hermes/logs/errors.log | tail -3

# 3. Plugins intact:
ls ~/.hermes/plugins/model-providers/zai/__init__.py

# 4. Config preserved:
hermes config | grep -E 'model|reasoning'

# 5. General health:
hermes doctor && hermes --version
```

## Related

- Skill Section 7 — the bundled-vs-user-plugin override trap and the
  `__module__` check (why reading bundled source can mislead you).
- `references/provider-parameters.md` — the ZAI reasoning_effort case study
  that motivated this analysis.
