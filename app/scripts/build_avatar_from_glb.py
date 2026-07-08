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

# v13: the bust renders as DISCRETE memory-node dots (GPU shader points with
# core+halo), not a dense fuzz — far fewer, bigger, individually visible
N_HEAD = 7000
KEY = np.array([-0.45, 0.55, 0.8]); KEY = KEY / np.linalg.norm(KEY)
# dim counter-key from the right so the shadow side keeps its form
KEY2 = np.array([0.65, 0.05, 0.60]); KEY2 = KEY2 / np.linalg.norm(KEY2)

# world placement (matches jarvis3d.js camera/framing).
# The GLB spans crown→shoulder stump; the cranium is ~57% of that span.
# v12: 30% down from the v11 1.5× (63 → 44.1 units, ~25-unit head); still
# the SAME 46k particles with face-weighted sampling.
MODEL_H = 44.1
# The bust anchors to the BOTTOM of the frame: the camera (fov 46°, z=88,
# y drifting −2.5…10.5) puts the lowest visible bottom edge at y≈−39.9, so
# a crown at 3.6 keeps the scan's open cut (3.6−44.1 = −40.5) always off-frame.
CROWN_Y = 3.6
HEAD_H = 24.0 * MODEL_H / 42.0   # cranium height in world units (36)
SC = MODEL_H / 42.0              # scale factor vs the v9 placement (1.5)


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
    # sculpted portrait light: sharp key falloff + dim counter-key + gentle
    # fill/sky. (The old flat 0.24 frontal fill washed out every feature —
    # brow, nose, lips read only if their shadows survive.)
    lam = np.clip(n @ KEY, 0, None)
    lam2 = np.clip(n @ KEY2, 0, None)
    fill = np.clip(n[:, 2], 0, None) * 0.15
    rim = np.power(1 - np.abs(n[:, 2]), 2.6) * rim_k
    up = np.clip(n[:, 1], 0, None) * 0.06
    return 0.07 + 0.78 * np.power(lam, 1.4) + 0.20 * np.power(lam2, 1.3) + fill + rim + up


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

    # ── area-weighted surface sampling, biased toward the FACE: front
    # triangles get up to 2.6× density so the same 46k points carry more
    # feature detail where it counts (occiput/neck give it up) ──
    v0, v1, v2 = pos[tri[:, 0]], pos[tri[:, 1]], pos[tri[:, 2]]
    n0, n1, n2 = nrm[tri[:, 0]], nrm[tri[:, 1]], nrm[tri[:, 2]]
    area = np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1) / 2
    cent_z = (v0[:, 2] + v1[:, 2] + v2[:, 2]) / 3
    facew = 1 + 1.6 * np.clip(cent_z / (cent_z.max() + 1e-9), 0, 1)
    prob = area * facew
    prob = prob / prob.sum()
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

    # ── animation bands (fractions of the head height, verified on previews) ──
    eyes_y = CROWN_Y - 0.475 * HEAD_H
    mouth_y = CROWN_Y - 0.775 * HEAD_H
    meta = {
        "mouth": [round(mouth_y - 1.9 * SC, 2), round(mouth_y + 1.9 * SC, 2), round(5.5 * SC, 2)],
        "eyes": [round(eyes_y - 1.6 * SC, 2), round(eyes_y + 1.6 * SC, 2), round(8.0 * SC, 2)],
    }

    # ── eye glints measured from the sampled surface, so the sparks sit ON
    # the eyes (the old hardcoded x±3.6/z9.6 floated in front of the face) ──
    glints = []
    for side in (-1.0, 1.0):
        sel_g = ((np.abs(P[:, 1] - eyes_y) < 1.6 * SC)
                 & (P[:, 0] * side > 2.0 * SC) & (P[:, 0] * side < 7.0 * SC)
                 & (P[:, 2] > 0))
        if sel_g.sum() < 10:
            glints.append([round(side * 3.6 * SC, 2), round(eyes_y, 2), round(9.6 * SC, 2)])
        else:
            gx = float(np.median(P[sel_g, 0]))
            gz = float(np.quantile(P[sel_g, 2], 0.9))
            glints.append([round(gx, 2), round(eyes_y, 2), round(gz, 2)])
    meta["glints"] = glints

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
        px = ((x2 + 42) / 84 * Wp).astype(int)
        py = ((CROWN_Y + 10 - P[:, 1]) / 84 * Hp).astype(int)
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
