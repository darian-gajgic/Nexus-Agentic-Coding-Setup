"""Build the JARVIS avatar bust from a real 3D head model (generic male).

Source model: "Head (Lee Perry-Smith)" — photogrammetry scan by Lee
Perry-Smith / Infinite-Realities (ir-ltd.net), distributed with three.js
examples. License: CC Attribution 3.0 Unported. Self-hosted at
static/avatar/male_head.glb. ATTRIBUTION LIVES HERE AND IN docs/JARVIS-VOICE.md.

Per operator direction 2026-07-08: a generic good-looking male avatar —
NO likeness adjustments. The head comes from the scan (real anatomy, real
normals); neck + trapezius shoulders are the proven procedural surfaces.

Pipeline: parse GLB (positions/normals/indices) → normalize orientation +
scale into avatar world units → area-weighted surface sampling (~46k pts)
→ bake lighting (key lambert + fill + rim, subtle skin tone bands) → add
procedural neck/shoulders points → emit static/avatar/head_points.json
  { pos:[xyz...], bri:[...], mouth:[y0,y1,xHalf], eyes:[y0,y1,xHalf],
    occ:[{v:[xyz...], i:[indices...]}, ...] }
The occ entries are opaque occluder meshes (full head mesh + coarse
neck/shoulder grids) that static/jarvis3d.js renders under the particles.

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
PREVIEW = Path("/tmp/claude-1000/-home-sinep/a9a0ff46-fb67-446b-801f-f05e2d640848/scratchpad/headframes/preview")

N_HEAD = 46000
KEY = np.array([-0.45, 0.55, 0.8]); KEY = KEY / np.linalg.norm(KEY)

# world placement (matches jarvis3d.js camera/framing).
# The GLB spans crown→shoulder stump; the cranium is ~57% of that span, so
# the full model is scaled to 42 units to get a ~24-unit head.
MODEL_H = 42.0
CROWN_Y = 28.0
# torso top is measured from the scan stump at build time (sho_top)


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

    # ── measure the stump's bottom cross-section so the torso continues it
    #    EXACTLY (the v8.0 torso started lower and wider → a visible shelf) ──
    stump_y0 = pos[:, 1].min()
    sel = pos[:, 1] < stump_y0 + 2.0
    stump_hw = float(np.quantile(np.abs(pos[sel, 0]), 0.98))
    stump_dp = float(np.quantile(np.abs(pos[sel, 2]), 0.98))
    stump_cz = float(np.median(pos[sel, 2]))
    sho_top = stump_y0 + 1.2          # torso tucks UP inside the stump

    # fade the scan's open bottom edge into the torso (the boundary rim
    # otherwise catches rim light as a bright seam line)
    fade = np.clip((P[:, 1] - stump_y0) / 2.0, 0, 1)
    B = B * (0.45 + 0.55 * fade)

    pts = [P]
    bri = [B]

    # ── procedural torso: starts at the measured stump section, flares out ──
    k = 14000
    u = rng.random(k) * 2 * np.pi
    v = rng.random(k)
    slope = np.clip(v / 0.55, 0, 1); slope = slope * slope * (3 - 2 * slope)
    halfw = stump_hw * 0.98 + (23.5 - stump_hw) * slope
    depth = stump_dp * 0.98 + 2.5 * slope
    c, sn = np.cos(u), np.sin(u)
    kk = 3
    denom = np.power(np.power(np.abs(sn / halfw), kk) + np.power(np.abs(c / depth), kk), 1 / kk)
    r = 1 / np.maximum(denom, 1e-4)
    ps = np.stack([sn * r, sho_top - v * 20, c * r + stump_cz], axis=1)
    nsh = np.stack([sn, np.zeros(k), c], axis=1)
    cloth = 0.42 + 0.1 * np.abs(np.sin(v * 6) * np.sin(u * 12))
    # soft top: torso brightens in over its first stretch (joint melts away)
    joint = 0.5 + 0.5 * np.clip(v / 0.12, 0, 1)
    pts.append(ps); bri.append(shade(nsh, 0.42) * cloth * joint)

    P = np.concatenate(pts)
    B = np.clip(np.concatenate(bri), 0.03, 1.35)

    # ── animation bands (fractions of the ~24-unit head, verified on previews) ──
    eyes_y = CROWN_Y - 0.475 * 24
    mouth_y = CROWN_Y - 0.775 * 24
    meta = {
        "mouth": [round(mouth_y - 1.9, 2), round(mouth_y + 1.9, 2), 5.5],
        "eyes": [round(eyes_y - 1.6, 2), round(eyes_y + 1.6, 2), 8.0],
    }

    # ── occluders: full head mesh + coarse neck/shoulder grids ──
    occ = [{
        "v": [round(float(x), 2) for x in pos.reshape(-1)],
        "i": [int(x) for x in tri.reshape(-1)],
    }]
    def grid_occ(fn, nu, nv):
        verts, idxs = [], []
        for i in range(nu + 1):
            for j in range(nv + 1):
                x, y, z = fn(i / nu, j / nv)
                verts += [round(x, 2), round(y, 2), round(z, 2)]
        for i in range(nu):
            for j in range(nv):
                a = i * (nv + 1) + j; b = a + 1; cq = a + nv + 1; d = cq + 1
                idxs += [a, b, cq, b, d, cq]
        return {"v": verts, "i": idxs}
    def sho(a, b):
        sl = min(1, max(0, b / 0.55)); sl = sl * sl * (3 - 2 * sl)
        hw = stump_hw * 0.98 + (23.5 - stump_hw) * sl
        dp = stump_dp * 0.98 + 2.5 * sl
        ang = a * 2 * math.pi
        c2, s2 = math.cos(ang), math.sin(ang)
        dn = (abs(s2 / hw) ** 3 + abs(c2 / dp) ** 3) ** (1 / 3)
        r2 = 1 / max(1e-4, dn)
        return (s2 * r2, sho_top - b * 20, c2 * r2 + stump_cz)
    occ.append(grid_occ(sho, 40, 18))

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
