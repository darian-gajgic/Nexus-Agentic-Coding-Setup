#!/usr/bin/env python3
"""Stage 1 — enumerate the eval corpus into runs/<id>/briefs.jsonl.

Read-only. Reuses the same frontmatter convention as app/evals.py so the
brief text Arm A sees (via the corpus) is byte-identical to what Arms B/C get.

Usage: python3 01_collect.py [--run run1] [--domain marketing ...] [--case id ...]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_lib import CFG, parse_case_md, briefs_path, run_dir, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="run1")
    ap.add_argument("--domain", action="append", default=None,
                    help="limit to domain(s); default = every domain with a RUBRIC.md")
    ap.add_argument("--case", action="append", default=None,
                    help="limit to case id(s)")
    args = ap.parse_args()

    root = Path(CFG["corpus_root"])
    if not root.is_dir():
        sys.exit(f"corpus root missing: {root}")

    rows = []
    for ddir in sorted(root.iterdir()):
        if not ddir.is_dir():
            continue
        domain = ddir.name
        if args.domain and domain not in args.domain:
            continue
        rubric = ddir / "RUBRIC.md"
        edir = ddir / "evals"
        if not rubric.is_file() or not edir.is_dir():
            continue
        for fp in sorted(edir.glob("*.md")):
            fm, body = parse_case_md(fp.read_text())
            if not body.strip():
                continue
            cid = fp.stem
            if args.case and cid not in args.case:
                continue
            rows.append({
                "case_id": cid,
                "domain": domain,
                "title": (fm.get("title") or cid.replace("-", " ")).strip(),
                "brief": body.strip(),
                "rubric_path": str(rubric),
                "source_path": str(fp),
            })

    if not rows:
        sys.exit("no briefs matched — check --domain/--case filters")

    out = briefs_path(args.run)
    run_dir(args.run)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    by_dom: dict = {}
    for r in rows:
        by_dom[r["domain"]] = by_dom.get(r["domain"], 0) + 1
    log(f"wrote {len(rows)} briefs to {out}")
    for d, n in sorted(by_dom.items()):
        log(f"  {d}: {n}")


if __name__ == "__main__":
    main()
