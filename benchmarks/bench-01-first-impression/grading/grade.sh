#!/usr/bin/env bash
# Bench-01 grader.
# Usage: bash grade.sh <fable5_dir> <opus48_dir> <nexus_dir>
# Writes everything to grading/out/: acceptance-*.txt, selftests-*.txt,
# blind/ (anonymized X/Y/Z copies + SPEC.md + JUDGE-PROMPT.txt), mapping.txt.
set -u
if [ $# -ne 3 ]; then
  echo "usage: bash grade.sh <fable5_dir> <opus48_dir> <nexus_dir>" >&2
  exit 2
fi
HERE="$(cd "$(dirname "$0")" && pwd)"
BENCH="$(dirname "$HERE")"
OUT="$HERE/out"
rm -rf "$OUT"
mkdir -p "$OUT/blind"

ARMS=(fable5 opus48 nexus)
DIRS=("$1" "$2" "$3")

for i in 0 1 2; do
  arm=${ARMS[$i]}; dir=${DIRS[$i]}
  echo "=== $arm ($dir) ==="
  python3 "$HERE/acceptance_test.py" "$dir" >"$OUT/acceptance-$arm.txt" 2>&1
  grep -E '^(SCORE|FAIL|NOTE)' "$OUT/acceptance-$arm.txt" | tail -15
  if [ -f "$dir/test_gridcalc.py" ]; then
    if (cd "$dir" && timeout 180 python3 -m unittest test_gridcalc -v) >"$OUT/selftests-$arm.txt" 2>&1; then
      echo "own tests: PASS ($(grep -c ' \.\.\. ok$' "$OUT/selftests-$arm.txt") ok)"
    else
      echo "own tests: FAIL (see out/selftests-$arm.txt)"
    fi
  else
    echo "own tests: MISSING"
  fi
  [ -f "$dir/gridcalc.py" ] && echo "LOC gridcalc.py: $(wc -l <"$dir/gridcalc.py")"
  echo
done

# Anonymized copies for blind qualitative judging (deliverables only — no
# deliverable.md/extras that could reveal which system produced what).
LETTERS=($(shuf -e X Y Z))
: >"$OUT/mapping.txt"
for i in 0 1 2; do
  L=${LETTERS[$i]}
  mkdir -p "$OUT/blind/$L"
  for f in gridcalc.py test_gridcalc.py README.md; do
    [ -f "${DIRS[$i]}/$f" ] && cp "${DIRS[$i]}/$f" "$OUT/blind/$L/"
  done
  echo "$L = ${ARMS[$i]}" >>"$OUT/mapping.txt"
done
cp "$BENCH/PROMPT.md" "$OUT/blind/SPEC.md"
cp "$HERE/judge-prompt.txt" "$OUT/blind/JUDGE-PROMPT.txt"

echo "=== SUMMARY ==="
for arm in "${ARMS[@]}"; do
  printf '%-8s %s\n' "$arm" "$(grep -h '^SCORE' "$OUT/acceptance-$arm.txt" || echo 'no score')"
done
echo
echo "Blind copies for the judge: $OUT/blind"
echo "De-anonymization mapping (do NOT show the judge): $OUT/mapping.txt"
