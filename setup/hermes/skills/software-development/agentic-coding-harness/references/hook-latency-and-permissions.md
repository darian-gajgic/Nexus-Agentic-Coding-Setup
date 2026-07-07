# Post-Edit Hook Latency & Permission-Glob Security

Two configuration lessons that apply to ANY Claude Code / Claude-GLM harness setup.
Both are class-level — they recur every time you wire up hooks and permissions.

## 1. PostToolUse hook latency — bash early-exit beats Node spawns

### The problem

A PostToolUse(Write|Edit) hook fires on EVERY code edit. If the hook is a Node.js
script (`node /path/hook.js`), Claude Code spawns a fresh Node/V8 runtime each time.
Startup cost: ~50-70ms per spawn. Two hooks (common: a syntax-check + a project-test
hook) = ~120-140ms of pure overhead added to every single edit, even when there is
nothing to do (no check.sh in the project, non-code file edited, etc.).

Over a coding session with hundreds of edits, this is seconds-to-minutes of dead time,
and it makes the agent feel sluggish.

### The fix — single unified bash hook with early exit

Replace multiple Node hooks with ONE bash script that:

1. Reads the hook JSON payload from stdin (jq for parsing).
2. Exits in <5ms when there's nothing to do (non-code file, no check.sh).
3. Only spawns a linter/checker when the file type matches AND a project gate exists.

```bash
#!/usr/bin/env bash
# Unified PostToolUse(Write|Edit) gate — replaces syntax-check.js + test-check.js
set -uo pipefail
input=$(cat 2>/dev/null || true)
f=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null || echo "")
[ -n "$f" ] && [ -f "$f" ] || exit 0    # ← EARLY EXIT: <5ms, no spawn

errors=""

# Phase 1: syntax check (one spawn, only for code files)
case "$f" in
  *.js|*.mjs|*.cjs)  err=$(node --check "$f" 2>&1) || errors+="Syntax: $err\n";;
  *.py)              err=$(python3 -c "import ast,sys;ast.parse(open(sys.argv[1]).read())" "$f" 2>&1) || errors+="Syntax: $err\n";;
  *.json)            err=$(jq empty "$f" 2>&1) || errors+="JSON: $err\n";;
  *.sh)              err=$(bash -n "$f" 2>&1) || errors+="Bash: $err\n";;
esac

# Phase 2: project check.sh (opt-in — walk up to find <dir>/.claude/check.sh)
dir="$(cd "$(dirname "$f")" 2>/dev/null && pwd)"
check=""
while :; do
  [ -x "$dir/.claude/check.sh" ] && { check="$dir/.claude/check.sh"; break; }
  parent="$(dirname "$dir")"; [ "$parent" = "$dir" ] && break; dir="$parent"
done
if [ -n "$check" ]; then
  projroot="$(dirname "$(dirname "$check")")"
  cout=$(cd "$projroot" && timeout 60 env CLAUDE_EDITED_FILE="$f" bash "$check" "$f" 2>&1)
  [ $? -ne 0 ] && [ $? -ne 124 ] && errors+="Check failed:\n$(printf '%s' "$cout" | tail -c 3000)\n"
fi

# Emit block decision if errors found
if [ -n "$errors" ]; then
  jq -nc --arg d block --arg r "Edit gate blocked on $f:\n$errors" '{decision:$d,reason:$r}'
fi
exit 0
```

Wire it in `settings.json`:
```json
"PostToolUse": [{
  "matcher": "Write|Edit",
  "hooks": [{"type": "command", "command": "/home/USER/.claude/hooks/post-edit-gate.sh"}]
}]
```

### Benchmark (measured 2026-07-04)

| Setup | Latency per edit (no-op path) |
|-------|-------------------------------|
| Old: 2x Node spawns (syntax-check.js + test-check.js) | ~120-140ms |
| New: single bash hook, early exit | ~5ms |
| New: bash hook + python3 syntax check | ~10ms |

**13x+ faster on the common path** (edits in projects without a check.sh, or non-code files).

### Timeout guidance

- The old test-check.js had a 180s timeout — absurd for a per-edit gate.
- A per-edit gate should be FAST. Use 60s max. If a project's check.sh takes longer,
  it belongs in the pre-commit hook or CI, not the per-edit loop.
- The verify-check.sh (GLM side) was similarly lowered from 170s → 60s.

## 2. Permission-glob security — `./` is root-only, `**/` is required for depth

### The problem

Claude Code / Hermes permission rules use gitignore-style globs. A common mistake:

```json
"allow": ["Read(**)", ...],
"deny":  ["Read(./.env*)"]
```

`Read(./.env*)` anchors to the CWD root only. It matches `./.env` and `./.env.local`
in the project root, but does NOT match nested files like `project/subdir/.env` or
`backend/config/.env.production`. The broader `Read(**)` allow rule OVERRIDES the
narrow deny for any nested `.env` file — a **secret leak vector**.

### The fix — depth-complete deny globs

Use `**/` prefix to match at every depth, and enumerate common secret file patterns:

```json
"deny": [
  "Read(**/.env*)",
  "Read(**/.env)",
  "Read(**/.env.local)",
  "Read(**/.env.production)",
  "Read(**/.env.staging)",
  "Read(**/.env.development)",
  "Read(**/secrets/**)",
  "Read(**/credentials*)",
  "Read(**/key.env)",
  "Read(**/.ssh/**)",
  "Read(**/.gnupg/**)",
  "Read(**/.glm-agent/**)"
]
```

Apply to BOTH `~/.claude/settings.json` AND `~/.claude-glm/settings.json` (and any
other Claude Code install) — each has its own permission file.

### Verification recipe — always test globs with nested paths

Never trust a security glob until you've tested it against nested paths. Run this
Python check after editing deny rules:

```python
import json, re

def glob_to_regex(pat):
    i = 0; result = []
    while i < len(pat):
        if pat[i:i+3] == '**/': result.append('(.*/)?'); i += 3
        elif pat[i] == '*': result.append('[^/]*'); i += 1
        elif pat[i] == '?': result.append('.'); i += 1
        elif pat[i] in '.()[]{}+^$|\\': result.append('\\' + pat[i]); i += 1
        else: result.append(pat[i]); i += 1
    return ''.join(result)

for f in ['~/.claude/settings.json', '~/.claude-glm/settings.json']:
    d = json.load(open(f))
    deny = [r.replace('Read(','').rstrip(')') for r in d['permissions']['deny']]
    test_paths = ['.env', 'project/.env', 'project/subdir/.env',
                  'project/.env.local', 'config/credentials.json']
    for tp in test_paths:
        blocked = any(re.fullmatch(glob_to_regex(r), tp) for r in deny if 'Read' not in r)
        print(f"  {tp:40s} {'BLOCKED' if blocked else 'LEAK!!!'}")
```

If any path shows LEAK, the deny rule is incomplete. Fix before moving on.

### General rule

When writing security globs for permission systems, ALWAYS test with:
- Root path (`.env`)
- One level deep (`project/.env`)
- Two levels deep (`project/subdir/.env`)
- With common suffixes (`.env.local`, `.env.production`)
- In secret directories (`secrets/`, `credentials`)

The `./` prefix is a trap — it looks like "current directory" but in glob terms it
anchors to exactly the root, missing everything below. Use `**/` for defense in depth.
