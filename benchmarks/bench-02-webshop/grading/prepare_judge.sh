#!/usr/bin/env bash
# Assemble the anonymized judge directory for Bench-02.
# Usage: bash prepare_judge.sh <fable5_dir> <opus48_dir> <nexus_dir> <prompt_file_used>
set -u
if [ $# -ne 4 ]; then
  echo "usage: bash prepare_judge.sh <fable5_dir> <opus48_dir> <nexus_dir> <prompt_file_used>" >&2
  exit 2
fi
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/out"
rm -rf "$OUT"
mkdir -p "$OUT/blind"

ARMS=(fable5 opus48 nexus)
DIRS=("$1" "$2" "$3")
LETTERS=($(shuf -e X Y Z))
: >"$OUT/mapping.txt"
for i in 0 1 2; do
  L=${LETTERS[$i]}
  mkdir -p "$OUT/blind/$L"
  # copy the whole solution minus heavy/provenance dirs
  (cd "${DIRS[$i]}" && tar cf - \
      --exclude='.git' --exclude='node_modules' --exclude='.venv' --exclude='venv' \
      --exclude='__pycache__' --exclude='*.log' .) | (cd "$OUT/blind/$L" && tar xf -)
  echo "$L = ${ARMS[$i]} (${DIRS[$i]})" >>"$OUT/mapping.txt"
done
cp "$4" "$OUT/blind/BRIEF.md"
cp "$HERE/judge-prompt.txt" "$OUT/blind/JUDGE-PROMPT.txt"

echo "Judge dir ready: $OUT/blind"
echo "Mapping (do NOT show the judge): $OUT/mapping.txt"
