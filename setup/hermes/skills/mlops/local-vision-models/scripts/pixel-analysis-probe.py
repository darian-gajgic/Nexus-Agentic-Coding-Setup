#!/usr/bin/env python3
"""
Blind pixel-analysis probe for UI screenshots.

Use when no VLM backend is available and you need to reconstruct a UI
from the image alone — OR to verify a VLM's visual claims against ground
truth. Extracts: dominant palette, region colors, accent-colored graph
polyline, icon/row positions, panel boundaries.

Usage:
    python3 pixel-analysis-probe.py <image.png> [graph_y_lo graph_y_hi graph_x_lo graph_x_hi]

Prints a JSON report. Graph bbox defaults to the middle 70% of the image
if not given; refine on a second pass once you see the accent bbox.

No GPU, no model, no network. Just numpy + PIL.
"""
import sys, json
import numpy as np
from PIL import Image

img = sys.argv[1] if len(sys.argv) > 1 else None
if not img:
    print(__doc__); sys.exit(1)

im = Image.open(img).convert('RGB')
a = np.array(im).astype(int)
H, W, _ = a.shape
r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]

report = {"size": [W, H]}


def region_avg(x0, y0, x1, y1):
    box = a[y0:y1, x0:x1, :]
    return [int(v) for v in box.mean(axis=(0, 1))], float(box.std())


# 1. Dominant palette via coarse quantization
q = (a // 32) * 32
flat = [tuple(v) for v in q.reshape(-1, 3)]
from collections import Counter
top = Counter(flat).most_common(8)
report["dominant_palette"] = [{"rgb": list(c), "hex": "#%02x%02x%02x" % c, "pct": round(100 * n / len(flat), 1)}
                               for c, n in top]

# 2. Accent (reddish) mask + bounding box
reddish = (r > 90) & (r > g + 35) & (r > b + 35) & (g < 130) & (b < 130)
report["accent_pixel_count"] = int(reddish.sum())
ys, xs = np.where(reddish)
if len(xs):
    report["accent_bbox"] = {"x": [int(xs.min()), int(xs.max())],
                             "y": [int(ys.min()), int(ys.max())]}
    med = a[ys[len(ys) // 2], xs[len(xs) // 2]]
    report["accent_median_color"] = "#%02x%02x%02x" % tuple(int(v) for v in med)

# 3. Graph polyline (refine bbox from accent step or CLI args)
if len(sys.argv) == 6:
    gy0, gy1, gx0, gx1 = (int(v) for v in sys.argv[2:6])
else:
    gy0 = int(H * 0.18); gy1 = int(H * 0.30)
    gx0 = int(W * 0.12); gx1 = int(W * 0.75)
band = reddish[gy0:gy1, gx0:gx1]
poly = []
for x in range(band.shape[1]):
    col = band[:, x]
    ys_at = np.where(col)[0]
    if len(ys_at):
        poly.append((gx0 + x, gy0 + int(ys_at.min())))
if poly:
    pxs = [p[0] for p in poly]; pys = [p[1] for p in poly]
    span_x = max(pxs) - min(pxs) or 1
    span_y = max(pys) - min(pys) or 1
    norm = [((p[0] - min(pxs)) / span_x, (p[1] - min(pys)) / span_y) for p in poly]
    # subsample to ~50 points for SVG
    step = max(1, len(norm) // 50)
    report["graph_polyline_normalized"] = [(round(x, 4), round(y, 4)) for x, y in norm[::step]]
    report["graph_y_range"] = [int(min(pys)), int(max(pys))]

# 4. Sidebar / strip icon positions (variance peaks on leftmost 90px)
strip_var = []
for y in range(0, H, 2):
    block = a[y:y + 48, 10:80, :].astype(float)
    strip_var.append((y + 24, float(block.std())))
peaks = sorted(strip_var, key=lambda t: -t[1])[:15]
peaks_y = sorted([p[0] for p in peaks])
dedup = []
for y in peaks_y:
    if not dedup or y - dedup[-1] > 40:
        dedup.append(y)
report["sidebar_icon_centers_y"] = dedup

# 5. Panel boundaries: classify pixels, find big rectangular clusters
card_blue = (b > r + 2) & (b > g) & (r > 35) & (r < 60) & (b < 75)
row_counts = card_blue.sum(axis=1)
bands, cur = [], None
for i, v in enumerate(row_counts > 500):
    if v and cur is None:
        cur = i
    elif not v and cur is not None:
        bands.append([cur, i]); cur = None
if cur is not None:
    bands.append([cur, len(row_counts)])
report["panel_row_bands"] = [bd for bd in bands if bd[1] - bd[0] > 20]

print(json.dumps(report, indent=2, ensure_ascii=False))
