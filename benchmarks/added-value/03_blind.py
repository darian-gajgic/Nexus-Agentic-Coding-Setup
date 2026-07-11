#!/usr/bin/env python3
"""Stage 3 — build blinded judge packets.

- packets/<case>/deliverable_{1,2,3}.md  (seeded shuffle; no arm info)
- packets/<case>/case.json               (domain, rubric path, title — no arms)
- private/mapping.json                   (case → number → arm; judges never read it)
- private/pairwise-jobs.json             (jobs reference packet FILES only)
- private/scrub-log.json                 (removed self-identification lines)

Cases missing any requested arm (or with an error meta) are excluded and listed.
Usage: python3 03_blind.py --run run1
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_lib as bl

SELF_ID = re.compile(
    r"^\s*>?\s*(as (an? )?(ai|assistant|large language model|claude|glm)\b"
    r"|i(’m|'m| am) (an? )?(ai|assistant|large language model|claude|glm)\b"
    r"|this (deliverable|document) was (written|generated) by\b).*$",
    re.IGNORECASE)


def scrub(text: str):
    kept, removed = [], []
    for line in text.splitlines():
        if SELF_ID.match(line):
            removed.append(line[:160])
        else:
            kept.append(line)
    return "\n".join(kept), removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="run1")
    args = ap.parse_args()
    briefs = bl.load_briefs(args.run)
    rd = bl.run_dir(args.run)
    packets = rd / "packets"
    private = rd / "private"
    packets.mkdir(exist_ok=True)
    private.mkdir(exist_ok=True)

    rng = random.Random(bl.CFG["shuffle_seed"])
    mapping, jobs, scrub_log, excluded = {}, [], {}, []

    for b in briefs:
        cid = b["case_id"]
        texts = {}
        bad = None
        for arm in bl.ARMS:
            m = bl.done_marker(args.run, arm, cid)
            d = bl.arm_dir(args.run, arm, cid) / "deliverable.md"
            if not m.exists() or not d.exists():
                bad = f"arm {arm} missing"
                break
            meta = json.loads(m.read_text())
            if meta.get("error"):
                bad = f"arm {arm} error: {meta['error'][:100]}"
                break
            texts[arm] = d.read_text()
        if bad:
            excluded.append({"case_id": cid, "reason": bad})
            continue

        order = list(bl.ARMS)
        rng.shuffle(order)
        pdir = packets / cid
        pdir.mkdir(exist_ok=True)
        mapping[cid] = {}
        for i, arm in enumerate(order, start=1):
            clean, removed = scrub(texts[arm])
            (pdir / f"deliverable_{i}.md").write_text(clean)
            mapping[cid][str(i)] = arm
            if removed:
                scrub_log.setdefault(cid, {})[arm] = removed
        (pdir / "case.json").write_text(json.dumps({
            "case_id": cid, "domain": b["domain"], "title": b["title"],
            "rubric_path": b["rubric_path"]}, indent=2))

        inv = {v: k for k, v in mapping[cid].items()}
        for a, bb in bl.CFG["pairwise"]:
            for order_name, (x, y) in (("fwd", (a, bb)), ("rev", (bb, a))):
                jobs.append({
                    "job_id": f"{cid}::{a}v{bb}::{order_name}",
                    "case_id": cid,
                    "one": f"deliverable_{inv[x]}.md",
                    "two": f"deliverable_{inv[y]}.md",
                })

    (private / "mapping.json").write_text(json.dumps(mapping, indent=2))
    (private / "pairwise-jobs.json").write_text(json.dumps(jobs, indent=2))
    (private / "scrub-log.json").write_text(json.dumps(scrub_log, indent=2))
    (private / "excluded.json").write_text(json.dumps(excluded, indent=2))

    bl.log(f"packets: {len(mapping)} cases; pairwise jobs: {len(jobs)}; "
           f"excluded: {len(excluded)}")
    for e in excluded:
        bl.log(f"  EXCLUDED {e['case_id']}: {e['reason']}")
    if len(excluded) > bl.CFG["thresholds"]["max_excluded_briefs"]:
        bl.log("WARNING: exclusions exceed the pre-registered maximum — "
               "the run is void per PREREGISTRATION.md. Fix errors and rerun "
               "02 with --redo-errors before judging.")


if __name__ == "__main__":
    main()
