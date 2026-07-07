#!/usr/bin/env python3
"""Deterministic pixel QA: exact color read + perceptual diff. No VLM guessing.

Self-contained (needs only Pillow + numpy, both already present). No scikit-image.

Usage:
  pixel_qa.py color  <img.png> <x> <y>          -> prints exact #RRGGBB at pixel
  pixel_qa.py deltae <hexA> <hexB>              -> CIEDE2000 (<2 == perceptually identical)
  pixel_qa.py diff   <a.png> <b.png> [out.png]  -> changed-pixel count + % (+ red-overlay png)

Why: no VLM (local OR frontier) reads exact hex reliably (ColorBench: GPT-4o 40.6%).
Always read colors/geometry deterministically here, never from a vision model.
"""
import sys
import math
from PIL import Image


def _hex(rgb):
    return "#%02X%02X%02X" % (rgb[0], rgb[1], rgb[2])


def color(p, x, y):
    print(_hex(Image.open(p).convert("RGB").getpixel((int(x), int(y)))))


def _hex_to_lab(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c):
        return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92

    r, g, b = lin(r), lin(g), lin(b)
    X = (0.4124 * r + 0.3576 * g + 0.1805 * b) * 100
    Y = (0.2126 * r + 0.7152 * g + 0.0722 * b) * 100
    Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) * 100
    Xn, Yn, Zn = 95.047, 100.0, 108.883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(X / Xn), f(Y / Yn), f(Z / Zn)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _ciede2000(lab1, lab2):
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25 ** 7))) if Cbar > 0 else 0.0
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp) / 2)
    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbp = (h1p + h2p + 360) / 2
    else:
        hbp = (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hbp - 30))
         + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6))
         - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dtheta = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    Sl = 1 + (0.015 * (Lbp - 50) ** 2) / math.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                     + Rt * (dCp / Sc) * (dHp / Sh))


def deltae(a, b):
    print(round(_ciede2000(_hex_to_lab(a), _hex_to_lab(b)), 3))


def diff(a, b, out=None):
    import numpy as np
    ia = Image.open(a).convert("RGB")
    ib = Image.open(b).convert("RGB")
    if ia.size != ib.size:
        print("SIZE MISMATCH %s vs %s" % (ia.size, ib.size))
        sys.exit(2)
    da, db = np.array(ia), np.array(ib)
    mask = (da != db).any(axis=2)
    n, tot = int(mask.sum()), int(mask.size)
    print("changed=%d pixels (%.3f%%)" % (n, 100 * n / tot))
    if out:
        vis = da.copy()
        vis[mask] = [255, 0, 0]
        Image.fromarray(vis).save(out)


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"color": lambda: color(*sys.argv[2:5]),
     "deltae": lambda: deltae(*sys.argv[2:4]),
     "diff": lambda: diff(*sys.argv[2:5])}[cmd]()
