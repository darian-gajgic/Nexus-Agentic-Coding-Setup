"""Build the JARVIS avatar point cloud from the operator's head-turn video.

v2 — NO multi-view fusion. The v1 turntable fusion smeared into a blob:
without pose registration, 23 hand-guessed yaws + head bob + per-frame depth
scale drift cannot align. Instead this uses three frames where each is strong:

  FRONT frame  -> Depth-Anything-V2 relief = the actual face geometry
                  (nose, brow, eye sockets), lit from its real normals
  PROFILE frame-> the true per-row head depth (nose->back-of-skull span,
                  hair puff) that shapes the BACK closure
  BACK frame   -> hair texture for the back shell

The back half is generated per row as a half-ellipse: width from the front
mask, depth from the profile mask — his real proportions, zero alignment risk.

Outputs static/avatar/head_points.json {pos, bri, mouth, eyes} consumed by
static/jarvis3d.js (which falls back to photo inflation if the file is gone).

Run:  ~/ml-env/bin/python scripts/build_avatar_pointcloud.py <frames-dir>
Frame choices + face rows below were verified by eye on the extracted frames
(f001 front / f006 right-facing profile / f012 back; eyes~375px, mouth~490px
on the 478x850 video). Re-check them if a new video is recorded.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter

FRAMES_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
OUT = Path(__file__).resolve().parent.parent / "static" / "avatar" / "head_points.json"
PREVIEW = FRAMES_DIR / "preview"

FRONT_F, PROFILE_F, BACK_F = "f001.jpg", "f006.jpg", "f012.jpg"
NOSE_HIGH_X = True          # in the profile frame the nose points image-RIGHT
EYE_ROW_PX, MOUTH_ROW_PX = 375, 490     # measured on f001 (478x850)
FRONT_SHARE = 0.45          # nose-side share of the head depth (ear axis)
TARGET_FRONT = 40000        # point budget
TARGET_BACK = 22000
KEY = np.array([-0.45, 0.55, 0.8]); KEY = KEY / np.linalg.norm(KEY)


def depth_and_mask(pipe, img):
    W, H = img.size
    d = pipe(img)["predicted_depth"].squeeze().float().cpu().numpy()
    d = np.array(Image.fromarray(d).resize((W, H)))
    d = (d - d.min()) / max(1e-6, d.max() - d.min())
    thr = 0.5
    for _ in range(8):
        lo, hi = d[d < thr].mean(), d[d >= thr].mean()
        thr = (lo + hi) / 2
    m = Image.fromarray(((d >= thr) * 255).astype(np.uint8))
    m = m.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(3))
    mask = np.array(m) > 127
    return d, mask


def tone(l):
    return np.where(l < 0.22, 0.35, np.where(l < 0.45, 0.65,
           np.where(l < 0.7, 1.0, 1.25)))


def main():
    from transformers import pipeline
    pipe = pipeline("depth-estimation",
                    model="depth-anything/Depth-Anything-V2-Small-hf",
                    device=0 if torch.cuda.is_available() else -1)

    fr = Image.open(FRAMES_DIR / FRONT_F).convert("RGB")
    W, H = fr.size
    d_f, m_f = depth_and_mask(pipe, fr)
    lum_f = np.asarray(fr.convert("L"), np.float32) / 255.0

    pr = Image.open(FRAMES_DIR / PROFILE_F).convert("RGB")
    _, m_p = depth_and_mask(pipe, pr)
    bk = Image.open(FRAMES_DIR / BACK_F).convert("RGB")
    _, m_b = depth_and_mask(pipe, bk)
    lum_b = np.asarray(bk.convert("L"), np.float32) / 255.0

    # luminance contrast stretch inside each mask
    def stretch(lum, mask):
        sl = lum[mask]
        lo, hi = np.quantile(sl, 0.05), np.quantile(sl, 0.97)
        return np.clip((lum - lo) / max(1e-4, hi - lo), 0, 1)
    lum_f = stretch(lum_f, m_f)
    lum_b = stretch(lum_b, m_b)

    ys, xs = np.where(m_f)
    top_f, bot_f = ys.min(), ys.max()
    height_f = bot_f - top_f
    cx_f = np.median(xs[ys < top_f + int(0.45 * height_f)])   # head-region center

    # profile: per-row [front extent, back extent] in units of ITS mask height
    ys_p, xs_p = np.where(m_p)
    top_p, bot_p = ys_p.min(), ys_p.max()
    height_p = bot_p - top_p
    prof_front = np.zeros(101)   # sampled at 101 relative rows
    prof_back = np.zeros(101)
    for i in range(101):
        row = top_p + int(i / 100 * height_p)
        xs_r = np.where(m_p[min(row, m_p.shape[0] - 1)])[0]
        if len(xs_r) < 4:
            continue
        wpx = (xs_r.max() - xs_r.min()) / height_p
        prof_front[i] = wpx * FRONT_SHARE
        prof_back[i] = wpx * (1 - FRONT_SHARE)
    # smooth the profiles
    k = np.ones(7) / 7
    prof_front = np.convolve(prof_front, k, "same")
    prof_back = np.convolve(prof_back, k, "same")

    # depth relief normalization inside the front subject
    df = d_f.copy()
    p05, p98 = np.quantile(df[m_f], 0.05), np.quantile(df[m_f], 0.98)
    rel = np.clip((df - p05) / max(1e-4, p98 - p05), 0, 1)
    gy, gx = np.gradient(d_f)

    pts, bri = [], []

    # ── FRONT: real relief ──
    idx = np.argwhere(m_f)
    keep = idx[np.random.default_rng(7).random(len(idx)) < TARGET_FRONT / len(idx)]
    for y, x in keep:
        u = (x - cx_f) / height_f
        v = (top_f - y) / height_f          # 0 at hair top, negative downward
        ri = int(np.clip(-v * 100, 0, 100))
        z = rel[y, x] * max(0.02, prof_front[ri])
        # real facial normal from the depth gradient
        n = np.array([-gx[y, x] * 600, gy[y, x] * 600, 1.0])
        n /= np.linalg.norm(n)
        lam = max(0, float(n @ KEY))
        rim = (1 - abs(n[2])) ** 1.8 * 0.3
        b = np.clip((0.16 + 0.6 * lam ** 1.2 + rim) * tone(lum_f[y, x]), 0.04, 1.35)
        pts.append((u, v, z))
        bri.append(float(b))

    # ── BACK: half-ellipse closure per row (width = front mask, depth = profile),
    #    textured by the back-of-head frame ──
    ys_b, xs_b = np.where(m_b)
    top_b, height_b = ys_b.min(), ys_b.max() - ys_b.min()
    rows = np.argwhere(m_f[:, :])
    row_extent = {}
    for y in range(top_f, bot_f + 1):
        xs_r = np.where(m_f[y])[0]
        if len(xs_r) >= 4:
            row_extent[y] = (xs_r.min(), xs_r.max())
    n_back = 0
    rng = np.random.default_rng(11)
    # close only HEAD + NECK rows — a shoulder closure reads as a slab from
    # the side, and the chat panel covers the lower bust anyway
    head_rows_max = top_f + int(0.58 * height_f)
    rows_list = [(y, ext) for y, ext in row_extent.items() if y <= head_rows_max]
    while n_back < TARGET_BACK and rows_list:
        y, (x0, x1) = rows_list[rng.integers(len(rows_list))]
        v = (top_f - y) / height_f
        ri = int(np.clip(-v * 100, 0, 100))
        a = (x1 - x0) / 2 / height_f
        c = max(0.02, prof_back[ri])
        phi = math.pi / 2 + rng.random() * math.pi     # back half
        u = a * math.cos(phi) + ((x0 + x1) / 2 - cx_f) / height_f
        z = c * math.sin(phi) * -1 if False else c * math.sin(phi + math.pi)  # negative z
        z = -abs(c * math.sin(phi))
        # texture: map angle across the BACK frame's row
        rowb = top_b + int(np.clip(-v, 0, 1) * height_b)
        xs_rb = np.where(m_b[min(rowb, m_b.shape[0] - 1)])[0]
        if len(xs_rb) > 4:
            tb = (phi - math.pi / 2) / math.pi
            xb = int(xs_rb.min() + tb * (xs_rb.max() - xs_rb.min()))
            l = lum_b[rowb, np.clip(xb, 0, m_b.shape[1] - 1)]
        else:
            l = 0.3
        nrm = np.array([math.cos(phi), 0, math.sin(phi + math.pi)])
        rim = (1 - abs(nrm[2])) ** 1.8 * 0.35
        lam = max(0, float(nrm @ KEY))
        b = np.clip((0.10 + 0.45 * lam + rim) * tone(np.array(l)) * 0.75, 0.03, 0.9)
        pts.append((u, v, z))
        bri.append(float(b))
        n_back += 1

    P = np.array(pts, np.float32)
    B = np.array(bri, np.float32)

    # normalize to avatar world units: bust height 52, head top at +26
    v0, v1 = np.quantile(P[:, 1], 0.005), np.quantile(P[:, 1], 0.995)
    scale = 52.0 / max(1e-6, (v1 - v0))
    P[:, 0] *= scale
    P[:, 1] = (P[:, 1] - v1) * scale + 26.0
    P[:, 2] *= scale

    # animation bands from the measured face rows of the FRONT frame
    def row_to_worldY(row_px):
        return ((top_f - row_px) / height_f - v1) * scale + 26.0
    eyes_y = row_to_worldY(EYE_ROW_PX)
    mouth_y = row_to_worldY(MOUTH_ROW_PX)
    meta = {
        "mouth": [round(mouth_y - 2.0, 2), round(mouth_y + 2.0, 2), 6.0],
        "eyes": [round(eyes_y - 1.7, 2), round(eyes_y + 1.7, 2), 8.5],
    }

    out = {
        "pos": [round(float(v), 2) for v in P.reshape(-1)],
        "bri": [round(float(v), 3) for v in B],
        **meta,
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB) pts={len(B)} bands={meta}")

    # previews
    PREVIEW.mkdir(exist_ok=True)
    for name, ang in [("front", 0), ("q40", 40), ("side", 90)]:
        a = math.radians(ang)
        c2, s2 = math.cos(a), math.sin(a)
        x2 = P[:, 0] * c2 + P[:, 2] * s2
        Wp = Hp = 900
        canvas = np.zeros((Hp, Wp), np.float32)
        px = ((x2 + 30) / 60 * Wp).astype(int)
        py = ((26 - P[:, 1] + 4) / 60 * Hp).astype(int)
        ok = (px > 1) & (px < Wp - 2) & (py > 1) & (py < Hp - 2)
        for i in np.where(ok)[0]:
            canvas[py[i] - 1:py[i] + 2, px[i] - 1:px[i] + 2] += B[i] * 0.5
            canvas[py[i], px[i]] += B[i] * 0.9
        canvas = np.clip(canvas, 0, 1)
        rgb = np.stack([canvas * 0.30, canvas * 0.85, canvas * 1.0], axis=2)
        Image.fromarray((rgb * 255).astype(np.uint8)).save(PREVIEW / f"{name}.png")
    print(f"previews in {PREVIEW}")


if __name__ == "__main__":
    main()
