"""Build the JARVIS avatar point cloud from a 360° head-turn video.

Poor-man's 3D scan (turntable reconstruction):
  1. frames extracted from the video (subject rotates ~uniformly, camera fixed)
  2. Depth-Anything-V2-Small per frame -> relative depth (disparity: high=close)
  3. subject mask from the depth bimodality (person близко, wall far) + erosion
  4. each view lifts its pixels to camera space (x,y from image, z = shell
     radius + depth relief), rotates by the frame's yaw into world space
     (turntable assumption), keeps only camera-facing surfaces (low |grad d|)
  5. voxel-average fusion of all views; per-point lighting is BAKED (lambert
     from the source-view normal + rim) and modulated by video luminance
  6. writes static/avatar/head_points.json {pos, bri, mouth, eyes}
     which static/jarvis3d.js loads (falls back to photo inflation if absent)

Run in ml-env:  ~/ml-env/bin/python scripts/build_avatar_pointcloud.py \
                    /path/to/video-frames-dir
Frame yaw anchors below were eyeballed from the contact sheet — adjust there
if a new video is recorded (see docs/JARVIS-VOICE.md §0).
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

# yaw anchors (frame number -> degrees); frames between anchors interpolate.
# f001 = facing camera; rotation continuous through back (f012) to front (f023).
ANCHORS = {1: 0, 6: 90, 12: 180, 17: 270, 23: 353}
FRAMES = list(range(1, 24))

SHELL_R = 0.30      # head-surface distance from the rotation axis (of bbox H)
RELIEF = 0.20       # depth relief span (of bbox H)
GRAD_MAX = 0.012    # drop grazing surfaces (relative-depth units per px)
VOXEL = 0.016       # fusion grid (of bbox H)
KEY = np.array([-0.45, 0.55, 0.8]); KEY = KEY / np.linalg.norm(KEY)


def yaw_for(frame: int) -> float:
    ks = sorted(ANCHORS)
    for a, b in zip(ks, ks[1:]):
        if a <= frame <= b:
            t = (frame - a) / (b - a)
            return math.radians(ANCHORS[a] + t * (ANCHORS[b] - ANCHORS[a]))
    return math.radians(ANCHORS[ks[-1]])


def main():
    from transformers import pipeline
    pipe = pipeline("depth-estimation",
                    model="depth-anything/Depth-Anything-V2-Small-hf",
                    device=0 if torch.cuda.is_available() else -1)

    all_pts, all_bri, all_nrm = [], [], []
    front_meta = None

    for f in FRAMES:
        p = FRAMES_DIR / f"f{f:03d}.jpg"
        if not p.is_file():
            continue
        img = Image.open(p).convert("RGB")
        W, H = img.size
        d = pipe(img)["predicted_depth"].squeeze().float().cpu().numpy()
        d = np.array(Image.fromarray(d).resize((W, H)))
        d = (d - d.min()) / max(1e-6, d.max() - d.min())   # 0..1, 1 = closest

        # subject mask: depth bimodality (2-means threshold), cleaned + eroded
        thr = 0.5
        for _ in range(8):
            lo, hi = d[d < thr].mean(), d[d >= thr].mean()
            thr = (lo + hi) / 2
        mask = d >= thr
        m = Image.fromarray((mask * 255).astype(np.uint8))
        m = m.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(3))
        m = m.filter(ImageFilter.MinFilter(3))             # net erosion ~2px
        mask = np.array(m) > 127
        if mask.sum() < 4000:
            print(f"f{f:03d}: mask too small, skipped")
            continue

        ys, xs = np.where(mask)
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        bh = max(1, y1 - y0)                               # bbox height = unit
        cx = (x0 + x1) / 2

        lum = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
        sl = lum[mask]
        lo_l, hi_l = np.quantile(sl, 0.05), np.quantile(sl, 0.97)
        lum = np.clip((lum - lo_l) / max(1e-4, hi_l - lo_l), 0, 1)

        gy, gx = np.gradient(d)
        grad = np.hypot(gx, gy)
        keep = mask & (grad < GRAD_MAX)
        # keep only the CENTRAL strip of each row: pixels near the silhouette
        # are grazing surfaces this view cannot measure — contributing them
        # smears the fused head sideways (seen as a too-wide front view)
        for row in range(H):
            xs_r = np.where(mask[row])[0]
            if len(xs_r) < 8:
                keep[row] = False
                continue
            r0, r1 = xs_r.min(), xs_r.max()
            margin = max(3, int((r1 - r0) * 0.14))
            keep[row, :r0 + margin] = False
            keep[row, r1 - margin:] = False

        dm = np.median(d[mask])
        theta = yaw_for(f)
        c, s = math.cos(theta), math.sin(theta)

        yy, xx = np.where(keep)
        u = (xx - cx) / bh
        v = (((y0 + y1) / 2) - yy) / bh
        rel = np.clip((d[yy, xx] - dm) / max(1e-4, np.quantile(d[mask], 0.9) - dm), -1.5, 1.5)
        zc = SHELL_R + rel * RELIEF
        # turntable: world = R_y(-theta) @ [u, v, zc]
        wx = u * c + zc * s
        wz = -u * s + zc * c
        pts = np.stack([wx, v, wz], axis=1)

        # source-view normal from the depth gradient, rotated into world
        nx = -gx[yy, xx] * (bh * RELIEF)
        ny = gy[yy, xx] * (bh * RELIEF)
        nz = np.ones_like(nx)
        nl = np.sqrt(nx * nx + ny * ny + nz * nz)
        nx, ny, nz = nx / nl, ny / nl, nz / nl
        wnx = nx * c + nz * s
        wnz = -nx * s + nz * c
        nrm = np.stack([wnx, ny, wnz], axis=1)

        all_pts.append(pts)
        all_bri.append(lum[yy, xx])
        all_nrm.append(nrm)
        if f == FRAMES[0]:
            front_meta = {"y_top": v.max(), "y_bot": v.min()}
        print(f"f{f:03d}: yaw {math.degrees(theta):5.1f}°  pts {len(yy)}")

    P = np.concatenate(all_pts)
    B = np.concatenate(all_bri)
    N = np.concatenate(all_nrm)

    # voxel-average fusion
    key = np.round(P / VOXEL).astype(np.int64)
    _, idx, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    cnt = np.bincount(inv).astype(np.float32)
    def avg(a):
        if a.ndim == 1:
            return np.bincount(inv, weights=a) / cnt
        return np.stack([np.bincount(inv, weights=a[:, i]) / cnt for i in range(a.shape[1])], axis=1)
    P, B, N = avg(P), avg(B), avg(N)
    nl = np.linalg.norm(N, axis=1, keepdims=True)
    N = N / np.maximum(nl, 1e-6)
    print(f"fused: {len(P)} points")

    # bake lighting: key lambert + frontal rim + video luminance (posterized-ish)
    lam = np.clip(N @ KEY, 0, None)
    rim = np.power(1 - np.abs(N[:, 2]), 1.8) * 0.35
    tone = np.where(B < 0.22, 0.35, np.where(B < 0.45, 0.65, np.where(B < 0.7, 1.0, 1.25)))
    bri = np.clip((0.16 + 0.6 * lam ** 1.2 + rim) * tone, 0.04, 1.35)

    # normalize: center the axis, scale bust height to ~52 world units
    P[:, 0] -= np.median(P[:, 0])
    P[:, 2] -= np.median(P[:, 2])
    y0, y1 = np.quantile(P[:, 1], 0.005), np.quantile(P[:, 1], 0.995)
    scale = 52.0 / max(1e-6, y1 - y0)
    P *= scale
    P[:, 1] -= (np.quantile(P[:, 1], 0.995) - 26.0)        # head top ≈ +26

    # animation bands from face proportions of the FRONT view: head top ->
    # eyes ~30%, mouth ~62% of HEAD height (head ≈ upper 45% of the bust)
    top = np.quantile(P[:, 1], 0.995)
    head_h = 52.0 * 0.45
    eyes_y = top - 0.30 * head_h
    mouth_y = top - 0.62 * head_h
    meta = {
        "mouth": [round(mouth_y - 2.2, 2), round(mouth_y + 2.2, 2), 6.0],
        "eyes": [round(eyes_y - 1.8, 2), round(eyes_y + 1.8, 2), 8.5],
    }

    out = {
        "pos": [round(float(v), 2) for v in P.reshape(-1)],
        "bri": [round(float(v), 3) for v in bri],
        **meta,
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB), bands {meta}")

    # preview renders (front / 40° / side) for visual verification
    PREVIEW.mkdir(exist_ok=True)
    for name, ang in [("front", 0), ("q40", 40), ("side", 90)]:
        a = math.radians(ang)
        c2, s2 = math.cos(a), math.sin(a)
        x2 = P[:, 0] * c2 + P[:, 2] * s2
        z2 = -P[:, 0] * s2 + P[:, 2] * c2
        order = np.argsort(z2)
        Wp = Hp = 900
        canvas = np.zeros((Hp, Wp), np.float32)
        px = ((x2 + 30) / 60 * Wp).astype(int)
        py = ((26 - P[:, 1] + 4) / 60 * Hp).astype(int)
        ok = (px > 1) & (px < Wp - 2) & (py > 1) & (py < Hp - 2)
        for i in order:
            if not ok[i]:
                continue
            canvas[py[i] - 1:py[i] + 2, px[i] - 1:px[i] + 2] += bri[i] * 0.5
            canvas[py[i], px[i]] += bri[i] * 0.9
        canvas = np.clip(canvas, 0, 1)
        rgb = np.stack([canvas * 0.30, canvas * 0.85, canvas * 1.0], axis=2)
        Image.fromarray((rgb * 255).astype(np.uint8)).save(PREVIEW / f"{name}.png")
    print(f"previews in {PREVIEW}")


if __name__ == "__main__":
    main()
