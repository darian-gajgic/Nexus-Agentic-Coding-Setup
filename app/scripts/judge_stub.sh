#!/usr/bin/env bash
# Stub frontier judge for CI-speed gate runs (SPEC R4.3). Mimics cjudge's output
# shape (verdict line + learning note) without spending frontier tokens.
# Usage: judge_stub.sh <file> <domain>
cat <<'EOF'
⚠ STUB JUDGE (CI gate fixture) — NOT a real verdict. If this appears on a live
task, judge.cmd leaked from a crashed gate run: clear it in Settings → Judge
(empty = back to the real cjudge default).

Must-pass gates:
1. Voice matches STYLE-VOICE.md — PASS
2. Headline states a concrete outcome — FAIL: headline is category-generic

Scored dimensions:
- Clarity: 3/4 — clean structure
- Specificity: 2/4 — claims lack numbers

Top 3 highest-leverage improvements:
1. Replace "innovative solution" with the concrete outcome it delivers.
2. Add one verifiable proof point under the headline.
3. Cut the last paragraph — it restates the first.

VERDICT: REVISE (blocks: headline names no outcome; missing proof line)
Learning note: professional copy names the outcome, not the category.
EOF
