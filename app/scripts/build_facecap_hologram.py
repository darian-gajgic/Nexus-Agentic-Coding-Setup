"""Build the JARVIS hologram head GLB from the three.js "facecap" model.

Source model: "facecap" — realistic bald male head with the full 52 ARKit
blendshapes (morph targets, names in extras.targetNames), eye meshes under
rotatable pivot nodes (grp_eyeLeft/grp_eyeRight) and a static teeth mesh.
Model by Face Cap (bannaflak.com/face-cap), distributed with the three.js
examples (r160 tag). No explicit standalone model license upstream — the
credit line is preserved here and in static/jarvis3d.js. A clean-license
drop-in replacement is a Ready Player Me GLB exported with
?morphTargets=ARKit,Oculus%20Visemes (mapping table + node names change only).
ATTRIBUTION LIVES HERE AND IN docs/JARVIS-VOICE.md.

Why this script exists: the upstream GLB lists KHR_texture_basisu in
extensionsRequired (KTX2-compressed base color texture). GLTFLoader THROWS at
parse time unless a KTX2Loader is installed — and the hologram renderer never
uses the texture. So we strip, offline:
  - images / textures / samplers
  - every texture reference on materials (baseColor/normal/occlusion/…)
  - KHR_texture_basisu + KHR_texture_transform from extensionsUsed/Required
  - the 4 baked animation clips (we animate morphs/pivots ourselves)
The BIN chunk is left byte-identical: unreferenced bufferViews/accessors are
valid glTF, and not re-indexing the meshopt-compressed views keeps this
surgery trivially safe. EXT_meshopt_compression stays (the vendored
MeshoptDecoder handles it at runtime); KHR_mesh_quantization is natively
supported by GLTFLoader.

Run:  ~/nexus-agent-os/.venv/bin/python scripts/build_facecap_hologram.py
"""
import json
import struct
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "avatar" / "facecap_hologram.glb"
# Source is re-downloadable — cached outside the repo, not committed.
SRC_CACHE = Path.home() / ".hermes" / "cache" / "facecap_r160.glb"
SRC_URL = ("https://raw.githubusercontent.com/mrdoob/three.js/r160/"
           "examples/models/gltf/facecap.glb")

MAGIC = 0x46546C67  # 'glTF'
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
DROP_EXTENSIONS = {"KHR_texture_basisu", "KHR_texture_transform"}
TEXTURE_REF_KEYS = ("baseColorTexture", "metallicRoughnessTexture",
                    "normalTexture", "occlusionTexture", "emissiveTexture")


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
    magic, version, _length = struct.unpack_from("<III", data, 0)
    if magic != MAGIC or version != 2:
        sys.exit(f"not a GLB v2 (magic={magic:#x} version={version})")
    chunks, off = {}, 12
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        chunks[ctype] = data[off + 8: off + 8 + clen]
        off += 8 + clen
    return json.loads(chunks[JSON_CHUNK]), chunks.get(BIN_CHUNK, b"")


def write_glb(gltf: dict, bin_chunk: bytes, path: Path):
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)                      # 4-byte pad with spaces
    bn = bin_chunk + b"\x00" * (-len(bin_chunk) % 4)  # 4-byte pad with zeros
    total = 12 + 8 + len(js) + 8 + len(bn)
    with path.open("wb") as f:
        f.write(struct.pack("<III", MAGIC, 2, total))
        f.write(struct.pack("<II", len(js), JSON_CHUNK))
        f.write(js)
        f.write(struct.pack("<II", len(bn), BIN_CHUNK))
        f.write(bn)


def strip(gltf: dict) -> dict:
    for key in ("images", "textures", "samplers", "animations"):
        n = len(gltf.pop(key, []) or [])
        print(f"strip: {key} ×{n}")
    for mat in gltf.get("materials", []):
        for holder in (mat, mat.get("pbrMetallicRoughness", {})):
            for k in TEXTURE_REF_KEYS:
                holder.pop(k, None)
    for key in ("extensionsUsed", "extensionsRequired"):
        if key in gltf:
            gltf[key] = [e for e in gltf[key] if e not in DROP_EXTENSIONS]
    return gltf


def sanity(gltf: dict):
    req = set(gltf.get("extensionsRequired", []))
    assert req <= {"KHR_mesh_quantization", "EXT_meshopt_compression"}, req
    assert "images" not in gltf and "textures" not in gltf
    assert "animations" not in gltf
    # names live on NODES (gltfpack drops mesh names): named node → child
    # node carrying the mesh index. The 52 morph targets sit on one mesh.
    nodes = {n.get("name") for n in gltf.get("nodes", [])}
    assert {"head", "eyeLeft", "eyeRight", "teeth",
            "grp_eyeLeft", "grp_eyeRight"} <= nodes, nodes
    head = next(m for m in gltf["meshes"]
                if m["primitives"][0].get("targets"))
    targets = head["primitives"][0]["targets"]
    tnames = head.get("extras", {}).get("targetNames", [])
    assert len(targets) == 52 and len(tnames) == 52, (len(targets), len(tnames))
    for probe in ("jawOpen", "mouthFunnel", "mouthPucker", "eyeBlink_L",
                  "eyeLookUp_R", "browInnerUp", "tongueOut"):
        assert probe in tnames, probe
    print(f"sanity: 52 morph targets OK, eye pivots OK, required ext = {sorted(req)}")


def main():
    gltf, bin_chunk = parse_glb(fetch_source())
    gltf = strip(gltf)
    sanity(gltf)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    write_glb(gltf, bin_chunk, OUT)
    print(f"wrote {OUT} ({OUT.stat().st_size} B)")


if __name__ == "__main__":
    main()
