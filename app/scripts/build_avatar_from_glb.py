"""Build the JARVIS avatar bust from a real 3D head model (generic male).

Source model: "Head (Lee Perry-Smith)" — photogrammetry scan by Lee
Perry-Smith / Infinite-Realities (ir-ltd.net), distributed with three.js
examples. License: CC Attribution 3.0 Unported. Self-hosted at
static/avatar/male_head.glb. ATTRIBUTION LIVES HERE AND IN docs/JARVIS-VOICE.md.

Per operator direction 2026-07-08: a generic good-looking male avatar —
NO likeness adjustments. Head + neck come from the scan (real anatomy,
real normals). v9: the procedural chest/torso is GONE — instead the bust
is lowered so the scan's open neck/shoulder cut sits below the visible
frame edge and the head rises from the bottom of the canvas.

Pipeline: parse GLB (positions/normals/indices) → normalize orientation +
scale into avatar world units → area-weighted surface sampling (~46k pts)
→ bake lighting (key lambert + fill + rim, subtle skin tone bands) →
emit static/avatar/head_points.json
  { pos:[xyz...], bri:[...], mouth:[y0,y1,xHalf], eyes:[y0,y1,xHalf],
    occ:[{v:[xyz...], i:[indices...]}, ...] }
The single occ entry is the opaque full-head occluder mesh that
static/jarvis3d.js renders under the particles.

Run:  ~/nexus-agent-os/.venv/bin/python scripts/build_avatar_from_glb.py
"""
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
GLB = ROOT / "static" / "avatar" / "male_head.glb"
OUT = ROOT / "static" / "avatar" / "head_points.json"
PREVIEW = Path("/tmp/claude-1000/-home-sinep-Nexus-Agentic-Coding-Setup/de8d5241-8032-42ce-9546-2f5dd08ad5b7/scratchpad/avatar-preview")

N_HEAD = 46000
KEY = np.array([-0.45, 0.55, 0.8]); KEY = KEY / np.linalg.norm(KEY)

# world placement (matches jarvis3d.js camera/framing).
# The GLB spans crown→shoulder stump; the cranium is ~57% of that span, so
# the full model is scaled to 42 units to get a ~24-unit head.
MODEL_H = 42.0
# The bust anchors to the BOTTOM of the frame: the camera (fov 46°, z=88,
# y drifting −2.5…10.5) puts the lowest visible bottom edge at y≈−39.9, so
# a crown at 1.5 keeps the scan's open cut (1.5−42 = −40.5) always off-frame.
CROWN_Y = 1.5


def parse_glb(path):
    raw = path.read_bytes()
    clen, _ = struct.unpack("<II", raw[12:20])
    gltf = json.loads(raw[20:20 + clen])
    bin_off = 20 + clen + 8
    binc = raw[bin_off:]
    buf_views = gltf["bufferViews"]
    accs = gltf["accessors"]

    def acc_array(i, dtype, ncomp):
        a = accs[i]
        bv = buf_views[a["bufferView"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        n = a["count"] * ncomp
        return np.frombuffer(binc, dtype=dtype, count=n, offset=off).reshape(a["count"], ncomp)

    prim = gltf["meshes"][0]["primitives"][0]
    pos = acc_array(prim["attributes"]["POSITION"], np.float32, 3).astype(np.float64)
    nrm = acc_array(prim["attributes"]["NORMAL"], np.float32, 3).astype(np.float64)
    idx = acc_array(prim["indices"], np.uint16, 1).reshape(-1, 3).astype(np.int64)
    return pos, nrm, idx


def shade(n, rim_k=0.32):
    lam = np.clip(n @ KEY, 0, None)
    fill = np.clip(n[:, 2], 0, None) * 0.24    # frontal fill: the face must read
    rim = np.power(1 - np.abs(n[:, 2]), 2.0) * rim_k
    return 0.12 + 0.55 * np.power(lam, 1.2) + fill + rim


def main():
    pos, nrm, tri = parse_glb(GLB)
    # normalize: center x/z, verify facing (+z should be the nose side)
    pos[:, 0] -= pos[:, 0].mean()
    pos[:, 2] -= pos[:, 2].mean()
    # the LeePerrySmith GLB natively faces +z — NO flip. (Two flip attempts
    # both showed the occiput in the browser: a max-|z| heuristic misfires
    # because the occiput protrudes more than the nose. Leave as authored.)
    y0, y1 = pos[:, 1].min(), pos[:, 1].max()
    s = MODEL_H / (y1 - y0)
    pos *= s
    pos[:, 1] += CROWN_Y - pos[:, 1].max()

    # ── area-weighted surface sampling ──
    v0, v1, v2 = pos[tri[:, 0]], pos[tri[:, 1]], pos[tri[:, 2]]
    n0, n1, n2 = nrm[tri[:, 0]], nrm[tri[:, 1]], nrm[tri[:, 2]]
    area = np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1) / 2
    prob = area / area.sum()
    rng = np.random.default_rng(7)
    t = rng.choice(len(tri), N_HEAD, p=prob)
    r1, r2 = rng.random(N_HEAD), rng.random(N_HEAD)
    su = np.sqrt(r1)
    b0, b1, b2 = (1 - su), su * (1 - r2), su * r2
    P = v0[t] * b0[:, None] + v1[t] * b1[:, None] + v2[t] * b2[:, None]
    N = n0[t] * b0[:, None] + n1[t] * b1[:, None] + n2[t] * b2[:, None]
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-6)
    B = shade(N)

    # fade the scan's open bottom cut (normally below the frame edge; if the
    # camera drift ever grazes it, a dim edge beats a bright rim-lit seam)
    stump_y0 = pos[:, 1].min()
    fade = np.clip((P[:, 1] - stump_y0) / 2.0, 0, 1)
    B = B * (0.45 + 0.55 * fade)
    B = np.clip(B, 0.03, 1.35)

    # ── animation bands (fractions of the ~24-unit head, verified on previews) ──
    eyes_y = CROWN_Y - 0.475 * 24
    mouth_y = CROWN_Y - 0.775 * 24
    meta = {
        "mouth": [round(mouth_y - 1.9, 2), round(mouth_y + 1.9, 2), 5.5],
        "eyes": [round(eyes_y - 1.6, 2), round(eyes_y + 1.6, 2), 8.0],
    }

    # ── occluder: the full head mesh (hides the far-side particles) ──
    occ = [{
        "v": [round(float(x), 2) for x in pos.reshape(-1)],
        "i": [int(x) for x in tri.reshape(-1)],
    }]

    out = {
        "pos": [round(float(x), 2) for x in P.reshape(-1)],
        "bri": [round(float(x), 3) for x in B],
        "occ": occ,
        **meta,
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB) pts={len(B)} bands={meta}")

    # previews
    PREVIEW.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    for name, ang in [("front", 0), ("q40", 40), ("side", 90)]:
        a = math.radians(ang)
        c2, s2 = math.cos(a), math.sin(a)
        x2 = P[:, 0] * c2 + P[:, 2] * s2
        Wp = Hp = 900
        canvas = np.zeros((Hp, Wp), np.float32)
        px = ((x2 + 30) / 60 * Wp).astype(int)
        py = ((CROWN_Y + 6 - P[:, 1]) / 60 * Hp).astype(int)
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
