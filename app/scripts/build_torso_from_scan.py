"""Build the JARVIS hologram torso from the Lee Perry-Smith scan bust.

Source model: "Head (Lee Perry-Smith)" — photogrammetry scan by Lee
Perry-Smith / Infinite-Realities (ir-ltd.net), distributed with the
three.js examples (examples/models/gltf/LeePerrySmith/LeePerrySmith.glb).
License: CC Attribution 3.0 Unported. ATTRIBUTION LIVES HERE AND IN
docs/JARVIS-VOICE.md. This is the SAME scan the pre-v7 avatar bust was
baked from — its real neck/shoulder anatomy is the torso the operator
liked; the facecap blendshape head sits on top of it at runtime.

What this script does:
  - slice the scan BELOW the mid-neck plane (SLICE_Y, raw coords): keep
    only triangles whose three vertices are all under it → neck +
    shoulders, no head (the facecap head replaces it, its neck stub
    tucking INSIDE the scan's wider neck — the classic seam-hiding
    overlap)
  - normalize: neck-ring centroid → origin (x,z), ring plane → y 0, and
    scale so ONE UNIT = the scan head's half-width (skull + ears). At
    runtime the torso is scaled by the facecap head's world half-width —
    i.e. the body is proportioned exactly as if its original head were
    the hologram head.
  - emit a minimal extension-free GLB (float32 pos/normal + uint32 index)
    → static/avatar/torso_scan.glb

Run:  ~/nexus-agent-os/.venv/bin/python scripts/build_torso_from_scan.py
"""
import json
import struct
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "avatar" / "torso_scan.glb"
SRC_CACHE = Path.home() / ".hermes" / "cache" / "LeePerrySmith_r160.glb"
SRC_URL = ("https://raw.githubusercontent.com/mrdoob/three.js/r160/"
           "examples/models/gltf/LeePerrySmith/LeePerrySmith.glb")

SLICE_Y = -1.2        # raw coords: mid-neck, above the trapezius slope
HEAD_REGION_Y = 0.0   # verts above this = skull+ears (head width sample)

MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942


def fetch_source() -> bytes:
    if SRC_CACHE.exists():
        print(f"source: cached {SRC_CACHE} ({SRC_CACHE.stat().st_size} B)")
        return SRC_CACHE.read_bytes()
    print(f"source: downloading {SRC_URL}")
    with urllib.request.urlopen(SRC_URL, timeout=60) as r:
        data = r.read()
    SRC_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SRC_CACHE.write_bytes(data)
    print(f"source: saved {SRC_CACHE} ({len(data)} B)")
    return data


def parse_glb(data: bytes):
    magic, version, _ = struct.unpack_from("<III", data, 0)
    if magic != MAGIC or version != 2:
        sys.exit("not a GLB v2")
    chunks, off = {}, 12
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        chunks[ctype] = data[off + 8: off + 8 + clen]
        off += 8 + clen
    return json.loads(chunks[JSON_CHUNK]), chunks.get(BIN_CHUNK, b"")


def read_accessor(gltf, binc, idx):
    acc = gltf["accessors"][idx]
    bv = gltf["bufferViews"][acc["bufferView"]]
    off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    n = acc["count"]
    comp = acc["componentType"]
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}[acc["type"]]
    fmt = {5126: "f", 5123: "H", 5125: "I"}[comp]
    vals = struct.unpack_from(f"<{n * ncomp}{fmt}", binc, off)
    return [vals[i * ncomp:(i + 1) * ncomp] for i in range(n)]


def main():
    gltf, binc = parse_glb(fetch_source())
    mesh = gltf["meshes"][0]["primitives"][0]
    pos = read_accessor(gltf, binc, mesh["attributes"]["POSITION"])
    nrm = read_accessor(gltf, binc, mesh["attributes"]["NORMAL"])
    idx = [t[0] for t in read_accessor(gltf, binc, mesh["indices"])]
    print(f"scan: {len(pos)} verts, {len(idx) // 3} tris")

    # measurements on the ORIGINAL scan
    head_halfw = max(abs(p[0]) for p in pos if p[1] > HEAD_REGION_Y)
    ring = [p for p in pos if SLICE_Y - 0.12 <= p[1] <= SLICE_Y + 0.02]
    cx = sum(p[0] for p in ring) / len(ring)
    cz = sum(p[2] for p in ring) / len(ring)
    ring_r = sum(((p[0] - cx) ** 2 + (p[2] - cz) ** 2) ** 0.5 for p in ring) / len(ring)
    print(f"head halfW={head_halfw:.3f}  neck ring: r={ring_r:.3f} "
          f"({ring_r / head_halfw:.2f}×halfW) center=({cx:.3f},{cz:.3f})")

    # slice: triangles fully below the plane
    keep_tris = [(idx[i], idx[i + 1], idx[i + 2]) for i in range(0, len(idx), 3)
                 if all(pos[idx[i + k]][1] <= SLICE_Y for k in range(3))]
    used = sorted({v for t in keep_tris for v in t})
    remap = {v: k for k, v in enumerate(used)}
    s = 1.0 / head_halfw
    npos, nnrm = [], []
    for v in used:
        p = pos[v]
        npos.append(((p[0] - cx) * s, (p[1] - SLICE_Y) * s, (p[2] - cz) * s))
        nnrm.append(nrm[v])
    nidx = [remap[v] for t in keep_tris for v in t]
    ys = [p[1] for p in npos]
    xs = [abs(p[0]) for p in npos]
    print(f"sliced: {len(npos)} verts, {len(nidx) // 3} tris; normalized "
          f"y {min(ys):.2f}..{max(ys):.2f}, shoulders halfW {max(xs):.2f}×head")

    # minimal GLB
    def flat(a):
        return [c for v in a for c in v]
    pbin = struct.pack(f"<{len(npos) * 3}f", *flat(npos))
    nbin = struct.pack(f"<{len(nnrm) * 3}f", *flat(nnrm))
    ibin = struct.pack(f"<{len(nidx)}I", *nidx)
    binout = pbin + nbin + ibin + b"\x00" * (-len(pbin + nbin + ibin) % 4)
    mins = [min(p[i] for p in npos) for i in range(3)]
    maxs = [max(p[i] for p in npos) for i in range(3)]
    out = {
        "asset": {"version": "2.0", "generator": "build_torso_from_scan.py",
                  "copyright": "Head scan: Lee Perry-Smith / Infinite-Realities, CC-BY 3.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "torso", "mesh": 0}],
        "meshes": [{"name": "torso", "primitives": [{
            "attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2}]}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(npos),
             "type": "VEC3", "min": mins, "max": maxs},
            {"bufferView": 1, "componentType": 5126, "count": len(nnrm), "type": "VEC3"},
            {"bufferView": 2, "componentType": 5125, "count": len(nidx), "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(pbin)},
            {"buffer": 0, "byteOffset": len(pbin), "byteLength": len(nbin)},
            {"buffer": 0, "byteOffset": len(pbin) + len(nbin), "byteLength": len(ibin)},
        ],
        "buffers": [{"byteLength": len(binout)}],
    }
    js = json.dumps(out, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(binout)
    with OUT.open("wb") as f:
        f.write(struct.pack("<III", MAGIC, 2, total))
        f.write(struct.pack("<II", len(js), JSON_CHUNK))
        f.write(js)
        f.write(struct.pack("<II", len(binout), BIN_CHUNK))
        f.write(binout)
    print(f"wrote {OUT} ({OUT.stat().st_size} B)")


if __name__ == "__main__":
    main()
