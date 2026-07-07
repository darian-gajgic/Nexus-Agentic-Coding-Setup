#!/usr/bin/env bash
# PreToolUse(Bash) guardrail for the GLM agent.
# Blocks catastrophic / secret-exfiltrating commands. Exit 2 = block (stderr fed back to model).
set -uo pipefail
input=$(cat 2>/dev/null || true)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""' 2>/dev/null || echo "")
[ -z "$cmd" ] && exit 0

deny() { echo "BLOCKED by GLM danger-guard: $1  (rephrase or ask the user to run it manually)" >&2; exit 2; }

# recursive+force delete (any flag order: -rf, -fr, -r -f, --recursive --force)
printf '%s' "$cmd" | grep -Eq 'rm[[:space:]]+(-[^[:space:]]*[rR][^[:space:]]*[fF]|-[^[:space:]]*[fF][^[:space:]]*[rR]|-[rR][[:space:]]+-[fF]|-[fF][[:space:]]+-[rR]|--recursive[[:space:]]+--force|--force[[:space:]]+--recursive)' \
  && deny "recursive force rm"
# recursive rm targeting a broad/root/home/glob path
printf '%s' "$cmd" | grep -Eq 'rm[[:space:]]+(-[^[:space:]]*[rR]|--recursive)' \
  && printf '%s' "$cmd" | grep -Eq '([[:space:]]/([[:space:]]|$)|[[:space:]]/\*|[[:space:]]~|[[:space:]]\$HOME|[[:space:]]\*[[:space:]]*$)' \
  && deny "recursive rm on a broad path"
# disk / partition destroyers
printf '%s' "$cmd" | grep -Eq '(^|[[:space:];|&])(dd|mkfs(\.[a-z0-9]+)?|fdisk|parted|gdisk|sgdisk|cfdisk|wipefs|shred|mkswap)([[:space:]]|$)' \
  && deny "disk/partition destroyer"
# git history nukes
printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+push[[:space:]]+.*(--force([[:space:]]|=|$)|[[:space:]]-f([[:space:]]|$))' \
  && deny "git force-push"
# reading / copying secrets & keys (broad reader set incl. sed/awk/python/perl/node)
printf '%s' "$cmd" | grep -Eq '(\.env([[:space:]"'\'']|$)|\.glm-agent|key\.env|/\.ssh/|/\.gnupg/|id_rsa|id_ed25519|\.credentials)' \
  && printf '%s' "$cmd" | grep -Eq '(^|[[:space:];|&])(cat|less|more|head|tail|cp|scp|rsync|curl|wget|nc|ncat|base64|xxd|strings|grep|awk|sed|perl|python|python3|node|ruby|php|od|hexdump|cut|tr|nl|tac|rev|tee|dd)([[:space:]]|$)' \
  && deny "access to secrets/keys"
# piping remote content into an interpreter = remote code execution
printf '%s' "$cmd" | grep -Eq '(curl|wget|fetch)([[:space:]]|$)' \
  && printf '%s' "$cmd" | grep -Eq '\|[[:space:]]*(sudo[[:space:]]+)?(sh|bash|zsh|dash|python|python3|perl|node|ruby|php)([[:space:]]|$)' \
  && deny "piping remote content into an interpreter (RCE)"
# reverse shells (nc/ncat also denied at the permission layer; this is defense-in-depth)
printf '%s' "$cmd" | grep -Eq '((nc|ncat|netcat)[[:space:]].*-e|(ba)?sh[[:space:]]+-i|/dev/(tcp|udp)/)' && deny "reverse-shell pattern"
# tampering with the GLM guard / config dir: block write verbs into it, or a redirect whose
# TARGET token is inside it. Reads of ~/.claude-glm (cat/grep/wc/find/ls/stat on settings.json,
# hooks, statusline) are ALLOWED — that's config, not secrets. The redirect target is token-
# bounded (no whitespace/separators) so a harmless `2>/dev/null` followed *later* by `.claude-glm`
# no longer false-fires — the old [^|]* spanned the whole command line and matched anything.
printf '%s' "$cmd" | grep -Eq '(\.claude-glm|\.glm-agent)' \
  && printf '%s' "$cmd" | grep -Eq '(^|[[:space:];|&])(rm|mv|cp|tee|truncate|chmod|chown|install|ln|sed)([[:space:]]|$)|>[[:space:]]*[^[:space:];|&<>]*(\.claude-glm|\.glm-agent)' \
  && deny "attempt to modify the GLM guard/config/secret dir"
# fork bomb
printf '%s' "$cmd" | grep -Eq ':\(\)[[:space:]]*\{.*:\|:.*\}[[:space:]]*;[[:space:]]*:' && deny "fork bomb"

exit 0
