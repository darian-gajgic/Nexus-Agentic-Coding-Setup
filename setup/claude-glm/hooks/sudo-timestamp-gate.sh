#!/usr/bin/env bash
# PreToolUse gate for Bash commands that START with `sudo`.
# Requires a valid GLOBAL sudo timestamp (opened by the user with `sudo -v` in a
# real terminal). NEVER types a password — there is no TTY here, so it can't.
# - command doesn't use sudo            -> allow (exit 0)
# - command is `sudo -n ...` / `sudo -k`-> allow (our own check / window-close)
# - command starts with `sudo` AND timestamp valid (`sudo -n true`) -> allow
# - command starts with `sudo` AND no valid timestamp -> BLOCK (exit 2) + message
input="$(cat)"

# Fast path: nothing mentions sudo at all -> allow immediately.
case "$input" in *sudo*) ;; *) exit 0 ;; esac

# Extract the actual command string from the PreToolUse JSON on stdin.
cmd="$(printf '%s' "$input" | python3 -c 'import sys, json
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))
except Exception:
    print("")' 2>/dev/null)"

# Only gate commands that START with sudo. Always allow the non-prompting check
# (`sudo -n`) and the window-close (`sudo -k`).
trimmed="${cmd#"${cmd%%[![:space:]]*}"}"
case "$trimmed" in
  "sudo -n"*|"sudo -k"*) exit 0 ;;   # our own status check / kill -> allow
  "sudo "*|"sudo")       ;;          # a real privileged sudo -> gate it below
  *)                     exit 0 ;;   # sudo not the leading command -> allow
esac

# Is a global sudo timestamp currently valid? (-n never prompts for a password)
if sudo -n true 2>/dev/null; then
  exit 0   # window is open -> allow the sudo command through
fi

# Window closed -> block this tool call and tell the human what to do.
cat >&2 <<'MSG'
🔒 sudo is locked — no valid global timestamp, so this command was blocked.

   YOU (in your own terminal):   sudo -v      # authenticate once, opens the window
   then ask me to retry.
   When the privileged task is done, close it: sudo -k

I will not attempt a password — there is no TTY for me to type into.
MSG
exit 2
