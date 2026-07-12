#!/usr/bin/env python3
"""Validate a .pptx and summarize it — stdlib only (a pptx is a zip).

Usage:  python3 pptx_check.py <file.pptx>

Prints VALID/INVALID, SLIDES=N, and the first text runs of each slide so the
operator can record slide count + eyeball content without PowerPoint.
"""
import re
import sys
import zipfile


def main():
    if len(sys.argv) != 2:
        print("usage: python3 pptx_check.py <file.pptx>", file=sys.stderr)
        sys.exit(2)
    path = sys.argv[1]
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        print(f"INVALID not a readable zip/pptx: {exc}")
        sys.exit(1)
    names = z.namelist()
    if "ppt/presentation.xml" not in names:
        print("INVALID zip has no ppt/presentation.xml (not a PowerPoint file)")
        sys.exit(1)
    slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                    key=lambda n: int(re.search(r"\d+", n).group()))
    print(f"VALID  SLIDES={len(slides)}")
    for n in slides:
        xml = z.read(n).decode("utf-8", "replace")
        texts = [t.strip() for t in re.findall(r"<a:t>([^<]*)</a:t>", xml) if t.strip()]
        preview = " | ".join(texts[:4])
        print(f"  {n.split('/')[-1]}: {preview[:140] if preview else '(no text)'}")
    media = [n for n in names if n.startswith("ppt/media/")]
    print(f"MEDIA files (images etc.): {len(media)}")
    sys.exit(0 if slides else 1)


if __name__ == "__main__":
    main()
