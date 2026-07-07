#!/usr/bin/env python3
"""Mechanical pre-delivery sweep of a Business Brain domain RUBRIC.md kill-list.

Run BEFORE declaring any marketing/business deliverable done. Catches FAILs that
eyeballing the rubric misses (banned words, literal {{ placeholders, we-heavy
copy, exclamation storms, grade-level). Prints PASS/FAIL per check + exit code
0/1. Cheap, deterministic, no model tokens.

Usage:
    python3 rubric_kill_sweep.py <deliverable.md> [<domain>]
    <domain> defaults to 'marketing'. Must match a ~/knowledge/domains/<domain>/RUBRIC.md.

RUBRIC.md conventions this relies on (all current domains follow them):
  - A fenced ``` block under the kill list whose lines are literal banned terms
    (case-insensitive substring match). We extract everything between the fences
    that follow a heading containing 'kill list' / 'banned'.
  - Gate 10 (placeholders): the deliverable must not contain {{ , [TODO , lorem, XXX.
  - We-heavy copy (kill-list pattern): count we/our/us vs you/your on the BODY.
  - Reading level: avg words/sentence proxy (<=~14 ~= grade 7; B2B allow <=~18).
"""
import os
import re
import sys

KNOWLEDGE = os.path.expanduser("~/knowledge")


def load_banned(domain: str) -> list[str]:
    """Extract literal banned terms from a domain RUBRIC.md kill-list fence."""
    path = os.path.join(KNOWLEDGE, "domains", domain, "RUBRIC.md")
    if not os.path.isfile(path):
        return []
    text = open(path).read()
    # find fenced blocks; take the one whose preceding heading mentions kill/banned
    blocks = re.findall(r"```(?:[^\n]*)\n(.*?)```", text, re.S)
    banned = []
    for blk in blocks:
        # heading context = last ## / ### line before this block
        pos = text.find(blk)
        head = text.rfind("\n#", 0, pos)
        ctx = text[head:pos].lower() if head != -1 else ""
        if "kill" in ctx or "banned" in ctx:
            for line in blk.strip().splitlines():
                t = line.strip()
                if t and not t.startswith("#"):
                    banned.append(t)
    return banned


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: rubric_kill_sweep.py <deliverable.md> [domain]", file=sys.stderr)
        return 2
    path = sys.argv[1]
    domain = sys.argv[2] if len(sys.argv) > 2 else "marketing"
    text = open(path).read()
    low = text.lower()

    fails: list[str] = []

    # 1. banned-word sweep (literal, case-insensitive)
    banned = load_banned(domain)
    hits = [b for b in banned if b.lower() in low]
    print(f"[{'PASS' if not hits else 'FAIL'}] banned words ({len(banned)} in {domain} RUBRIC): "
          + (", ".join(hits) if hits else "none"))

    # 2. placeholders (gate 10)
    ph = re.findall(r"{{|\[TODO|lorem|XXX", text)
    print(f"[{'PASS' if not ph else 'FAIL'}] placeholders: {ph if ph else 'none'}")
    if ph:
        fails.append("placeholders")

    # 3. we-heavy copy — on BODY only (drop any trailing self-scoring/meta note)
    body = re.split(r"\n## (?:Why|Note|Scoring|Gates|Self-score)", text, maxsplit=1)[0]
    we = len(re.findall(r"\b(we|our|us|ours)\b", body, re.I))
    you = len(re.findall(r"\b(you|your|yours)\b", body, re.I))
    we_heavy = we > you
    print(f"[{'PASS' if not we_heavy else 'FAIL'}] we/you ratio (body): we={we} you={you} "
          + ("-> we-heavy, rewrite" if we_heavy else ""))
    if we_heavy:
        fails.append("we-heavy copy")

    # 4. exclamation marks (kill-list: >1 per asset; any in B2B)
    excl = text.count("!")
    print(f"[{'PASS' if excl <= 1 else 'FAIL'}] exclamation marks: {excl}")

    # 5. reading-level proxy (avg words/sentence on body, ignoring headings/lists)
    prose = re.sub(r"^#.*$", "", body, flags=re.M)  # drop headings
    sents = [s.split() for s in re.split(r"[.!?]+", prose) if s.strip()]
    sents = [s for s in sents if len(s) > 2]
    avg = sum(len(s) for s in sents) / max(len(sents), 1)
    grade_ok = avg <= 18  # B2B allowance; tighten to 14 for B2C
    print(f"[{'PASS' if grade_ok else 'WARN'}] avg words/sentence: {avg:.1f} "
          f"(<=18 ok for B2B; <=14 for B2C)")
    longest = max(sents, key=len) if sents else []
    if longest:
        print(f"        longest sentence ({len(longest)}w): {' '.join(longest)[:120]}")

    if hits or ph or we_heavy or excl > 1:
        print("\nRESULT: FAIL — fix the flagged checks before delivery.")
        return 1
    print("\nRESULT: PASS — kill-list clean; still run RUBRIC gates + critic manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
