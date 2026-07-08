/* JARVIS 3D v6 — sculpted anatomical particle bust.

   Direction from the operator (2026-07-08): stop chasing scan likeness —
   model a SOLID, believable 3D human first, and adapt only the shape data
   we trust from his frames: head aspect 0.82, his hair-silhouette curve,
   beard region. Everything else is canonical human anatomy, sculpted
   procedurally: cranium ellipsoid + displacement brushes (brow ridge, eye
   sockets, cheekbones, muzzle, chin, temples, occiput), a real nose wedge,
   ears, tapering jaw, neck cylinder and trapezius shoulders.

   What makes it read SOLID:
   - an OPAQUE dark occluder mesh of the same surfaces renders underneath
     the particles, so the far side of the head is hidden (the see-through
     scatter was the main "not solid" tell);
   - particles are dense, small and hug the surface;
   - per-point lighting (key lambert + fill + rim) is baked from real
     surface normals; hair/beard/brows darken the right regions.

   Scene layers, front to back (v10): bust (z≈0, anchored at the frame
   bottom) → the REAL memory galaxy (the memory-tab map at 10× node spacing,
   slowly spinning, z≈-1600) → the static memory matrix backdrop (z≈-3800).
   100 links run from the back of the skull to the 100 most-linked memory
   nodes; electric signals ride them (rapid inter-node traffic while
   thinking, a flood into the head when the answer starts). toggleGalaxy()
   flies the camera through the bust into the galaxy for orbit / hover /
   click-to-edit (onMemorySelect), like the Memory tab's 3D map.

   window.Jarvis3D = { mount, dispose, setMode, setLevel, setAnimations, toggleGalaxy }
   Lazy CDN three.js import — the string "three" never appears in index.html
   (verify.sh gate). Lip-sync: mouth-band points (exact by construction)
   displaced by setLevel; eye-band points blink. */

let THREE = null;
let threePromise = null;
let _tmpV = null;   // scratch Vector3 (allocated once THREE is loaded)

function loadThree() {
  if (!threePromise) {
    threePromise = import('https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js')
      .then((m) => { THREE = m; return m; })
      .catch((e) => { console.warn('Jarvis3D: engine unavailable', e); threePromise = null; return null; });
  }
  return threePromise;
}

const J = {
  renderer: null, scene: null, camera: null, raf: null, container: null,
  head: null, headGroup: null, headGeo: null, occluders: [],
  glints: [], mouthIdx: [], eyeIdx: [], basePos: null,
  baseB: null, baseW: null, mouthY: [0, 1], level: 0, mode: 'idle', t: 0,
  animOn: true, disposed: false, resizeObs: null,
  pointer: { x: 0, y: 0 }, pointerHandler: null,
  // memory galaxy + static matrix + camera modes
  mem: emptyMem(), matrix: null, galaxyMode: false, fly: null,
  gCam: { theta: Math.PI / 2, phi: 1.35, dist: 700 }, lookCur: null,
  onMemorySelect: null, drag: null, downAt: null,
  downHandler: null, upHandler: null, wheelHandler: null,
};

function emptyMem() {
  return { group: null, data: null, nodeColor: null, cores: null, glows: null,
           linkLines: null, labels: [], pulses: [], thinkPulses: [], thinkPairs: [],
           top: [], avatarLinks: null, avatarPulses: [], burst: 0, hover: -1,
           marker: null, panel: null, hint: null };
}

const MODE_TINT = {
  idle:      [0.30, 0.85, 1.00],
  listening: [0.37, 0.92, 0.83],
  thinking:  [0.98, 0.75, 0.30],
  talking:   [0.45, 0.95, 1.00],
};

let _glowTex = null;
function glowTexture() {
  if (_glowTex) return _glowTex;
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.3, 'rgba(255,255,255,.5)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  _glowTex = new THREE.CanvasTexture(c);
  return _glowTex;
}

/* ═══════════════ sculpted bust geometry ═══════════════ */

const D2R = Math.PI / 180;
const sm = (a, b, x) => {
  const s = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return s * s * (3 - 2 * s);
};
// operator's measured hair/head silhouette (front view, angle from "up"
// -90°..+90° in 12° steps, radius / head height) — the one personal shape
// input we trust; everything else is canonical anatomy.
const HAIR_RADII = [0.43, 0.406, 0.643, 0.602, 0.559, 0.544, 0.527, 0.523,
                    0.523, 0.527, 0.54, 0.576, 0.51, 0.452, 0.422, 0.411];
const HAIR_MIN = 0.406, HAIR_MAX = 0.643;

// displacement brushes: gaussian bumps in (θ from top, φ azimuth; φ=0 front)
const BRUSHES = [
  { t: 52, p: 0,    st: 5,  sp: 26, amp: +0.030 },  // brow ridge
  { t: 58, p: 13,   st: 6.5, sp: 8, amp: -0.075 },  // eye socket R
  { t: 58, p: -13,  st: 6.5, sp: 8, amp: -0.075 },  // eye socket L
  { t: 67, p: 27,   st: 8,  sp: 10, amp: +0.035 },  // cheekbone R
  { t: 67, p: -27,  st: 8,  sp: 10, amp: +0.035 },  // cheekbone L
  { t: 76, p: 0,    st: 9,  sp: 15, amp: +0.035 },  // muzzle
  { t: 88, p: 0,    st: 7,  sp: 9,  amp: +0.050 },  // chin boss
  { t: 55, p: 180,  st: 25, sp: 40, amp: +0.050 },  // occiput fullness
  { t: 95, p: 180,  st: 12, sp: 50, amp: -0.100 },  // skull base in
  { t: 50, p: 68,   st: 12, sp: 14, amp: -0.030 },  // temple R
  { t: 50, p: -68,  st: 12, sp: 14, amp: -0.030 },  // temple L
  { t: 62, p: 92,   st: 7,  sp: 5,  amp: +0.060 },  // ear R
  { t: 62, p: -92,  st: 7,  sp: 5,  amp: +0.060 },  // ear L
  { t: 36, p: 0,    st: 10, sp: 24, amp: -0.015 },  // forehead plane
  { t: 95, p: 115,  st: 10, sp: 30, amp: -0.120 },  // under-jaw hollow R
  { t: 95, p: -115, st: 10, sp: 30, amp: -0.120 },  // under-jaw hollow L
];

const RX = 12.2, RY = 15.0, RZ = 12.9;   // head half axes (aspect ≈ 0.82)
const HEAD_CY = 13;                       // head center y (world)

function dphi(a, b) {
  let d = Math.abs(a - b) % (2 * Math.PI);
  return d > Math.PI ? 2 * Math.PI - d : d;
}

function hairAmp(phi) {
  // map the measured frontal silhouette onto the azimuth; mirror for the back
  const a = Math.abs(phi) <= Math.PI / 2 ? phi : (Math.PI - Math.abs(phi)) * Math.sign(phi);
  const idx = ((a / D2R) + 90) / 12;
  const i0 = Math.max(0, Math.min(HAIR_RADII.length - 1, Math.floor(idx)));
  const i1 = Math.min(HAIR_RADII.length - 1, i0 + 1);
  const f = Math.min(1, Math.max(0, idx - i0));
  const v = HAIR_RADII[i0] * (1 - f) + HAIR_RADII[i1] * f;
  return (v - HAIR_MIN) / (HAIR_MAX - HAIR_MIN);   // 0..1
}

function curl(theta, phi) {
  return Math.sin(phi * 7.3 + 1.7) * Math.sin(theta * 9.1 + 0.6) * 0.5
       + Math.sin(phi * 12.7) * Math.sin(theta * 5.3 + 2.1) * 0.5;
}

// head radius along direction (θ,φ) + region info
function headRadius(theta, phi) {
  const dx = Math.sin(theta) * Math.sin(phi);
  const dy = Math.cos(theta);
  const dz = Math.sin(theta) * Math.cos(phi);
  let r = 1 / Math.sqrt((dx * dx) / (RX * RX) + (dy * dy) / (RY * RY) + (dz * dz) / (RZ * RZ));
  let mul = 1;
  for (const b of BRUSHES) {
    const dt = (theta - b.t * D2R) / (b.st * D2R);
    const dp = dphi(phi, b.p * D2R) / (b.sp * D2R);
    mul += b.amp * Math.exp(-(dt * dt + dp * dp) / 2);
  }
  // jaw taper: the lower face narrows toward the chin, sides pull in
  const jt = sm(70 * D2R, 110 * D2R, theta) * sm(20 * D2R, 90 * D2R, dphi(phi, 0));
  mul *= 1 - 0.26 * jt;
  // hair: above the hairline the operator's silhouette + curls take over
  const hairline = (34 + 21 * sm(0, Math.PI, dphi(phi, 0))) * D2R;
  const hf = sm(hairline + 6 * D2R, hairline - 8 * D2R, theta);
  if (hf > 0) {
    mul *= 1 + hf * (0.06 + 0.13 * hairAmp(phi) + 0.035 * curl(theta, phi));
  }
  return { r: r * mul, hair: hf };
}

function headPoint(theta, phi) {
  const { r, hair } = headRadius(theta, phi);
  return {
    x: r * Math.sin(theta) * Math.sin(phi),
    y: HEAD_CY + r * Math.cos(theta),
    z: r * Math.sin(theta) * Math.cos(phi),
    hair,
  };
}

// nose: a wedge grown out of the face (separate surface, s∈[0,1] down the
// ridge, w∈[-1,1] across); protrudes past the sculpted surface
function nosePoint(s, w) {
  const theta = (57 + s * 14) * D2R;
  const halfw = (0.55 + s * 0.95) * (1 + 0.25 * sm(0.75, 1, s));  // nostril flare
  const phi = (w * halfw * 2.4) * D2R;
  const base = headRadius(theta, phi).r;
  const lift = Math.sin(Math.min(1, s * 1.15) * Math.PI * 0.62) * 1.4 * (1 - Math.abs(w) * 0.72);
  const r = base + Math.max(0, lift);
  return {
    x: r * Math.sin(theta) * Math.sin(phi),
    y: HEAD_CY + r * Math.cos(theta),
    z: r * Math.sin(theta) * Math.cos(phi),
  };
}

// neck: elliptical cylinder from INSIDE the skull base down into the torso
function neckPoint(u, v) {          // u∈[0,1] around, v∈[0,1] down
  const a = u * Math.PI * 2;
  const y = 8 - v * 15;             // starts inside the skull, ends in the torso
  const rx = 5.2 + v * 1.8, rz = 5.5 + v * 1.4;
  return { x: Math.sin(a) * rx, y, z: Math.cos(a) * rz + 0.6 - v * 0.4 };
}

// shoulders/upper torso: superelliptic slab with a trapezius slope
function shoulderPoint(u, v) {      // u around [0,1), v down [0,1]
  const a = u * Math.PI * 2;
  const y = -6 - v * 21;
  const slope = sm(0, 0.5, v);
  const halfw = 7.5 + 16 * slope;   // trapezius widening (~2 head-widths)
  const depth = 6.5 + 3 * slope;
  const c = Math.cos(a), s = Math.sin(a);
  const k = 3;                       // superellipse exponent → soft-rect
  const denom = Math.pow(Math.pow(Math.abs(s / halfw), k) + Math.pow(Math.abs(c / depth), k), 1 / k);
  const r = 1 / Math.max(1e-4, denom);
  return { x: s * r, y, z: c * r * 0.92 };
}

/* numeric normal of any param surface fn(p1,p2)->{x,y,z} */
function normalOf(fn, a, b, ea, eb) {
  const p = fn(a, b), pa = fn(a + ea, b), pb = fn(a, b + eb);
  const ux = pa.x - p.x, uy = pa.y - p.y, uz = pa.z - p.z;
  const vx = pb.x - p.x, vy = pb.y - p.y, vz = pb.z - p.z;
  let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
  const l = Math.hypot(nx, ny, nz) || 1;
  return [nx / l, ny / l, nz / l];
}

const KEYL = [-0.45, 0.55, 0.8];
(function () { const l = Math.hypot(...KEYL); KEYL[0] /= l; KEYL[1] /= l; KEYL[2] /= l; })();

function shade(n, opts = {}) {
  const lam = Math.max(0, n[0] * KEYL[0] + n[1] * KEYL[1] + n[2] * KEYL[2]);
  const fill = Math.max(0, n[2]) * 0.10;
  const rim = Math.pow(1 - Math.abs(n[2]), 2.0) * (opts.rim ?? 0.32);
  return 0.10 + 0.58 * Math.pow(lam, 1.2) + fill + rim;
}

/* primary: prebuilt bust from a real male head scan (Lee Perry-Smith /
   Infinite-Realities, CC-BY 3.0 — built by scripts/build_avatar_from_glb.py
   into static/avatar/head_points.json, incl. occluder meshes). */
function buildFromPrebuilt(cloud) {
  const pos = [], col = [], bri = [], wmi = [], mouthIdx = [], eyeIdx = [];
  const P = cloud.pos, B = cloud.bri;
  const [my0, my1, mxh] = cloud.mouth || [0, 1, 6];
  const [ey0, ey1, exh] = cloud.eyes || [0, 1, 8];
  for (let i = 0; i < B.length; i++) {
    const x = P[i * 3], y = P[i * 3 + 1], z = P[i * 3 + 2];
    const b = B[i];
    const n = pos.length / 3;
    pos.push(x + (Math.random() - .5) * .3,
             y + (Math.random() - .5) * .3,
             z + (Math.random() - .5) * .3);
    const w = b > 0.9 ? Math.min(1, (b - 0.9) / 0.25) * 0.4 : 0;
    bri.push(b); wmi.push(w);
    col.push(b * (MODE_TINT.idle[0] * (1 - w) + w),
             b * (MODE_TINT.idle[1] * (1 - w) + w),
             b * (MODE_TINT.idle[2] * (1 - w) + w));
    if (z > 2 && y > my0 && y < my1 && Math.abs(x) < mxh) mouthIdx.push(n);
    if (z > 2 && y > ey0 && y < ey1 && Math.abs(x) > 1.5 && Math.abs(x) < exh) eyeIdx.push(n);
  }
  return { pos, col, bri, wmi, mouthIdx, eyeIdx, mouthY: [my0, my1] };
}

function buildPrebuiltOccluders(cloud) {
  const mat = new THREE.MeshBasicMaterial({
    color: 0x060913, polygonOffset: true, polygonOffsetFactor: 2, polygonOffsetUnits: 2,
  });
  return (cloud.occ || []).map((o) => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(Float32Array.from(o.v), 3));
    geo.setIndex(o.i);
    const mesh = new THREE.Mesh(geo, mat);
    mesh.scale.setScalar(0.985);
    mesh.renderOrder = 0;
    return mesh;
  });
}

function buildSculpt() {
  const pos = [], col = [], bri = [], wmi = [], mouthIdx = [], eyeIdx = [];
  const push = (p, n, b) => {
    const i = pos.length / 3;
    pos.push(p.x + (Math.random() - .5) * .3,
             p.y + (Math.random() - .5) * .3,
             p.z + (Math.random() - .5) * .3);
    b = Math.min(1.35, Math.max(0.03, b));
    const w = b > 0.9 ? Math.min(1, (b - 0.9) / 0.25) * 0.4 : 0;
    bri.push(b); wmi.push(w);
    col.push(b * (MODE_TINT.idle[0] * (1 - w) + w),
             b * (MODE_TINT.idle[1] * (1 - w) + w),
             b * (MODE_TINT.idle[2] * (1 - w) + w));
    return i;
  };

  // ── head skin/hair points ──
  const NH = 52000;
  for (let k = 0; k < NH; k++) {
    const theta = Math.acos(1 - 2 * Math.random());
    if (theta > 118 * D2R) continue;
    const phi = Math.random() * 2 * Math.PI - Math.PI;
    const p = headPoint(theta, phi);
    const n = normalOf((a, b2) => headPoint(a, b2), theta, phi, 0.01, 0.01);
    let b = shade(n);
    const td = theta / D2R, pd = dphi(phi, 0) / D2R;
    if (p.hair > 0) {                       // hair: darker, curly speckle
      b *= 0.42 + 0.22 * (curl(theta, phi) * 0.5 + 0.5);
      b *= 1 - 0.25 * p.hair;
    } else {
      // brows
      const browL = Math.exp(-(((td - 50) / 2.6) ** 2 + ((dphi(phi, 13 * D2R) / D2R) / 6.5) ** 2) / 2);
      const browR = Math.exp(-(((td - 50) / 2.6) ** 2 + ((dphi(phi, -13 * D2R) / D2R) / 6.5) ** 2) / 2);
      b *= 1 - 0.62 * Math.min(1, browL + browR);
      // beard: lower face + jaw darken with speckle (his beard)
      const beard = sm(70, 78, td) * (1 - sm(96, 106, td)) * (1 - sm(46, 60, pd));
      if (beard > 0) b *= 1 - beard * (0.45 + 0.18 * Math.abs(curl(theta, phi)));
      // lips: slightly darker band
      const lips = Math.exp(-(((td - 77) / 2.2) ** 2 + (pd / 9) ** 2) / 2);
      b *= 1 - 0.30 * lips;
      // sockets shadow deepen
      const sock = Math.exp(-(((td - 58) / 5) ** 2 + ((Math.min(dphi(phi, 13 * D2R), dphi(phi, -13 * D2R)) / D2R) / 7) ** 2) / 2);
      b *= 1 - 0.35 * sock;
    }
    const i = push(p, n, b);
    if (td > 74 && td < 80 && pd < 9 && p.z > 0) { mouthIdx.push(i); }
    if (td > 55 && td < 61 && pd > 6 && pd < 20 && p.z > 0) eyeIdx.push(i);
  }

  // ── nose wedge (dim — an over-bright nose reads as a beak) ──
  for (let k = 0; k < 2400; k++) {
    const s = Math.random(), w = Math.random() * 2 - 1;
    const p = nosePoint(s, w);
    const n = normalOf((a, b2) => nosePoint(a, b2), Math.min(s, 0.98), Math.min(w, 0.98), 0.02, 0.02);
    push(p, n, shade(n) * 0.5);
  }

  // ── neck ──
  for (let k = 0; k < 5200; k++) {
    const u = Math.random(), v = Math.random();
    const p = neckPoint(u, v);
    const n = normalOf(neckPoint, u, v, 0.01, 0.02);
    push(p, n, shade(n) * 0.92);
  }

  // ── shoulders ──
  for (let k = 0; k < 15000; k++) {
    const u = Math.random(), v = Math.random();
    const p = shoulderPoint(u, v);
    const n = normalOf(shoulderPoint, u, v, 0.005, 0.01);
    // dark shirt with cloth-noise
    push(p, n, shade(n, { rim: 0.42 }) * (0.42 + 0.1 * Math.abs(curl(v * 6, u * 12))));
  }

  const ys = mouthIdx.map(i => pos[i * 3 + 1]);
  const mouthY = ys.length ? [Math.min(...ys), Math.max(...ys)] : [0, 1];
  return { pos, col, bri, wmi, mouthIdx, eyeIdx, mouthY };
}

/* occluder meshes: same surfaces, slightly inset, opaque near-black — they
   hide the far side of the bust, which is what makes it read as SOLID */
function buildOccluders() {
  const mat = new THREE.MeshBasicMaterial({
    color: 0x060913, polygonOffset: true, polygonOffsetFactor: 2, polygonOffsetUnits: 2,
  });
  const grids = [
    { fn: (a, b) => headPoint(a * 118 * D2R + 0.001, b * 2 * Math.PI - Math.PI), nu: 72, nv: 96 },
    { fn: (a, b) => neckPoint(b, a), nu: 12, nv: 28 },
    { fn: (a, b) => shoulderPoint(b, a), nu: 18, nv: 40 },
  ];
  const meshes = [];
  for (const g of grids) {
    const positions = [];
    const indices = [];
    for (let i = 0; i <= g.nu; i++) {
      for (let jx = 0; jx <= g.nv; jx++) {
        const p = g.fn(i / g.nu, jx / g.nv);
        positions.push(p.x, p.y, p.z);
      }
    }
    for (let i = 0; i < g.nu; i++) {
      for (let jx = 0; jx < g.nv; jx++) {
        const a = i * (g.nv + 1) + jx, b = a + 1, c = a + g.nv + 1, d = c + 1;
        indices.push(a, b, c, b, d, c);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(Float32Array.from(positions), 3));
    geo.setIndex(indices);
    const mesh = new THREE.Mesh(geo, mat);
    mesh.scale.setScalar(0.985);
    mesh.renderOrder = 0;
    meshes.push(mesh);
  }
  return meshes;
}

/* ═══════ memory galaxy (the memory-tab 3D map, embedded) + matrix ═══════ */
const CYAN_FAMILY = [0x22d3ee, 0x67e8f9, 0x0ea5b7];
const DISTINCT_HUES = [0xa3e635, 0xf43f5e, 0xf59e0b, 0x8b5cf6, 0xec4899,
                       0x60a5fa, 0x2dd4bf, 0xfb7185, 0xfacc15, 0x34d399,
                       0xc084fc, 0xf97316];

// world layout, front to back: bust (z≈0) → memory galaxy → static matrix.
// The galaxy cloud spans ±1200 (tab ±120 × GALAXY_SCALE), so its center must
// sit deep enough that the front edge stays FAR behind the bust.
const GALAXY_CENTER = { x: 0, y: 30, z: -2600 };
const GALAXY_SCALE = 10;     // 10× the memory-tab node spacing (operator ask)
const GALAXY_SPIN = 0.0011;  // rad/frame — the tab's idle auto-orbit rate
const MATRIX_CENTER = { x: 0, y: 30, z: -5200 };
const TOP_N = 100;           // avatar ↔ the 100 most-linked memory nodes

async function buildGalaxyData() {
  try {
    const r = await fetch('/api/memory3d');
    if (r.ok) {
      const d = await r.json();
      if ((d.nodes || []).length >= 8) return d;
    }
  } catch { }
  const nodes = [];
  for (let c = 0; c < 6; c++) {
    const cx = (Math.random() - .5) * 150, cy = (Math.random() - .5) * 90,
          cz = (Math.random() - .5) * 60;
    for (let i = 0; i < 40; i++) {
      nodes.push({ x: cx + (Math.random() - .5) * 26, y: cy + (Math.random() - .5) * 26,
                   z: cz + (Math.random() - .5) * 26, group: c });
    }
  }
  return { nodes, groups: [] };
}

// identity hues, exactly as the memory tab assigns them (memory3d.js)
function buildHueMapJ(data) {
  const groups = data.groups || [];
  const total = groups.reduce((s, g) => s + g.size, 0) || 1;
  const hueByGroup = [];
  let cyanShare = 0, ci = 0, di = 0;
  groups.forEach((g, rank) => {
    if (cyanShare < 0.20 && ci < CYAN_FAMILY.length) {
      hueByGroup[rank] = CYAN_FAMILY[ci++];
      cyanShare += g.size / total;
    } else hueByGroup[rank] = DISTINCT_HUES[di++ % DISTINCT_HUES.length];
  });
  const tally = {};
  (data.nodes || []).forEach((n) => {
    if (n.cluster == null) return;
    (tally[n.cluster] = tally[n.cluster] || {})[n.group] =
      (tally[n.cluster]?.[n.group] || 0) + 1;
  });
  const hueByCluster = {};
  Object.entries(tally).forEach(([cid, byGroup]) => {
    const top = Object.entries(byGroup).sort((a, b) => b[1] - a[1])[0];
    hueByCluster[cid] = hueByGroup[+top[0]] ?? CYAN_FAMILY[0];
  });
  return { hueByGroup, hueByCluster };
}

// region callout in the memory-tab style, scaled for the ×10 galaxy.
// depthTest ON (unlike the tab): the bust occluder must be able to hide it.
function memLabel(text, sub, hex) {
  const c = document.createElement('canvas');
  const g = c.getContext('2d');
  const label = String(text).toUpperCase();
  g.font = '700 26px "JetBrains Mono", monospace';
  const w = Math.max(140, Math.ceil(g.measureText(label).width) + 46);
  c.width = w;
  c.height = 92;
  const col = '#' + (hex || 0xa3e635).toString(16).padStart(6, '0');
  g.font = '700 26px "JetBrains Mono", monospace';
  g.textAlign = 'left';
  g.shadowColor = col;
  g.shadowBlur = 12;
  g.fillStyle = col;
  g.fillText(label, 34, 34);
  g.shadowBlur = 0;
  g.strokeStyle = col;
  g.globalAlpha = 0.85;
  g.lineWidth = 2.5;
  g.beginPath();
  g.moveTo(6, 66); g.lineTo(26, 44); g.lineTo(w - 8, 44);
  g.stroke();
  g.globalAlpha = 1;
  g.font = '500 19px "JetBrains Mono", monospace';
  g.fillStyle = 'rgba(168,168,200,.9)';
  g.fillText(sub, 34, 88);
  const tex = new THREE.CanvasTexture(c);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex, transparent: true, opacity: 0.9, depthWrite: false }));
  s.scale.set(c.width / 1.6, c.height / 1.6, 1);
  s.center.set(0.06, 0.28);
  return s;
}

// the far backdrop: the same memory scatter, pushed deep — a static matrix
function buildMatrix(data) {
  const nodes = data.nodes || [];
  if (!nodes.length) return;
  const pos = new Float32Array(nodes.length * 3);
  const col = new Float32Array(nodes.length * 3);
  const color = new THREE.Color();
  nodes.forEach((n, i) => {
    pos[i * 3] = (n.x || 0) * 14;
    pos[i * 3 + 1] = (n.y || 0) * 10;
    pos[i * 3 + 2] = (n.z || 0) * 8;
    const grp = n.group || 0;
    color.setHex(grp < 2 ? CYAN_FAMILY[grp % CYAN_FAMILY.length]
                         : DISTINCT_HUES[grp % DISTINCT_HUES.length]);
    col[i * 3] = color.r; col[i * 3 + 1] = color.g; col[i * 3 + 2] = color.b;
  });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  J.matrix = new THREE.Group();
  J.matrix.position.set(MATRIX_CENTER.x, MATRIX_CENTER.y, MATRIX_CENTER.z);
  J.matrix.add(new THREE.Points(geo, new THREE.PointsMaterial({
    size: 44, map: glowTexture(), vertexColors: true, transparent: true,
    opacity: 0.8, depthWrite: false, blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
  })));
  J.scene.add(J.matrix);
}

function buildMemoryGalaxy(data) {
  const nodes = data.nodes || [], links = data.links || [];
  if (!nodes.length) return;
  const { hueByGroup, hueByCluster } = buildHueMapJ(data);
  const mem = J.mem;
  const S = GALAXY_SCALE;
  mem.data = data;
  mem.nodeColor = (n) => (hueByGroup && hueByGroup[n.group]) ?? CYAN_FAMILY[0];
  mem.group = new THREE.Group();
  mem.group.position.set(GALAXY_CENTER.x, GALAXY_CENTER.y, GALAXY_CENTER.z);
  J.scene.add(mem.group);

  // node cores + additive glow layer (two Points clouds — node size stays at
  // tab scale so the ×10 spread reads as real distance between memories)
  const cp = [], cc = [];
  nodes.forEach((n) => {
    const c = new THREE.Color(mem.nodeColor(n));
    cp.push(n.x * S, n.y * S, n.z * S);
    cc.push(c.r, c.g, c.b);
  });
  const coreGeo = new THREE.BufferGeometry();
  coreGeo.setAttribute('position', new THREE.BufferAttribute(Float32Array.from(cp), 3));
  coreGeo.setAttribute('color', new THREE.BufferAttribute(Float32Array.from(cc), 3));
  mem.cores = new THREE.Points(coreGeo, new THREE.PointsMaterial({
    map: glowTexture(), size: 4, vertexColors: true, transparent: true,
    opacity: 0.95, depthWrite: false, sizeAttenuation: true }));
  mem.group.add(mem.cores);
  const glowGeo = new THREE.BufferGeometry();
  glowGeo.setAttribute('position', coreGeo.getAttribute('position'));
  glowGeo.setAttribute('color', coreGeo.getAttribute('color'));
  mem.glows = new THREE.Points(glowGeo, new THREE.PointsMaterial({
    map: glowTexture(), size: 34, vertexColors: true, transparent: true,
    opacity: 0.75, blending: THREE.AdditiveBlending, depthWrite: false,
    sizeAttenuation: true }));
  mem.group.add(mem.glows);

  // hair-thin similarity web, endpoint-tinted, brightness = real similarity
  if (links.length) {
    const lp = [], lc = [];
    links.forEach((ln) => {
      const a = nodes[ln.a], b = nodes[ln.b];
      const t = 0.35 + 0.65 * Math.min(1, Math.max(0, (ln.s - 0.45) / 0.5));
      const ca = new THREE.Color(mem.nodeColor(a)).multiplyScalar(t);
      const cb = new THREE.Color(mem.nodeColor(b)).multiplyScalar(t);
      lp.push(a.x * S, a.y * S, a.z * S, b.x * S, b.y * S, b.z * S);
      lc.push(ca.r, ca.g, ca.b, cb.r, cb.g, cb.b);
    });
    const linkGeo = new THREE.BufferGeometry();
    linkGeo.setAttribute('position', new THREE.BufferAttribute(Float32Array.from(lp), 3));
    linkGeo.setAttribute('color', new THREE.BufferAttribute(Float32Array.from(lc), 3));
    mem.linkLines = new THREE.LineSegments(linkGeo, new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.30,
      blending: THREE.AdditiveBlending, depthWrite: false }));
    mem.group.add(mem.linkLines);
  }

  // semantic region callouts
  (data.clusters || []).forEach((cl) => {
    const s = memLabel(cl.label, `${cl.size} memories`,
                       (hueByCluster && hueByCluster[cl.id]) ?? CYAN_FAMILY[0]);
    s.position.set(cl.x * S, cl.y * S + 70, cl.z * S);
    mem.group.add(s);
    mem.labels.push(s);
  });

  // ambient electrical pulses along the links (the tab's signature motion)
  if (links.length) {
    const pulseGeo = new THREE.SphereGeometry(4, 8, 8);
    const n = Math.min(46, Math.max(10, Math.floor(links.length / 4)));
    for (let i = 0; i < n; i++) {
      const p = new THREE.Mesh(pulseGeo, new THREE.MeshBasicMaterial({
        color: 0x9df5ff, transparent: true, opacity: 0.9,
        blending: THREE.AdditiveBlending, depthWrite: false }));
      const link = links[Math.floor(Math.random() * links.length)];
      p.userData = { link, t: Math.random(), speed: 0.15 + link.s * 0.5 };
      mem.group.add(p);
      mem.pulses.push(p);
    }
  }

  // the avatar's memory taps: the TOP_N most-linked ("most used") nodes
  mem.top = nodes.map((_, i) => i)
    .sort((a, b) => (nodes[b].degree || 0) - (nodes[a].degree || 0))
    .slice(0, TOP_N);
  const topSet = new Set(mem.top);

  // think-traffic paths: real links with BOTH ends avatar-connected, topped
  // up with links touching one end, else direct node↔node paths
  mem.thinkPairs = links.filter((l) => topSet.has(l.a) && topSet.has(l.b));
  if (mem.thinkPairs.length < 40) {
    mem.thinkPairs = mem.thinkPairs.concat(
      links.filter((l) => topSet.has(l.a) !== topSet.has(l.b)));
  }
  if (!mem.thinkPairs.length && mem.top.length > 1) {
    for (let i = 0; i < 60; i++) {
      const a = mem.top[Math.floor(Math.random() * mem.top.length)];
      const b = mem.top[Math.floor(Math.random() * mem.top.length)];
      if (a !== b) mem.thinkPairs.push({ a, b, s: 0.6 });
    }
  }
  if (mem.thinkPairs.length) {
    const thinkGeo = new THREE.SphereGeometry(8, 8, 8);
    for (let i = 0; i < 40; i++) {
      const p = new THREE.Mesh(thinkGeo, new THREE.MeshBasicMaterial({
        color: 0xffd28a, transparent: true, opacity: 0,   // thinking amber
        blending: THREE.AdditiveBlending, depthWrite: false }));
      const link = mem.thinkPairs[Math.floor(Math.random() * mem.thinkPairs.length)];
      p.userData = { link, t: Math.random(), speed: 1.2 + Math.random() * 1.4 };
      p.visible = false;
      mem.group.add(p);
      mem.thinkPulses.push(p);
    }
  }

  // hover marker (galaxy mode): one bright sprite snapped to the picked star
  mem.marker = new THREE.Sprite(new THREE.SpriteMaterial({
    map: glowTexture(), color: 0xffffff, transparent: true, opacity: 0.95,
    blending: THREE.AdditiveBlending, depthWrite: false }));
  mem.marker.scale.set(44, 44, 1);
  mem.marker.visible = false;
  mem.group.add(mem.marker);

  // 100 links: back of the skull → the top nodes (endpoints track per frame)
  if (mem.top.length) {
    const nT = mem.top.length;
    const apos = new Float32Array(nT * 6);
    const acol = new Float32Array(nT * 6);
    mem.top.forEach((ni, k) => {
      const c = new THREE.Color(mem.nodeColor(nodes[ni])).multiplyScalar(0.85);
      acol[k * 6] = 0.14; acol[k * 6 + 1] = 0.50; acol[k * 6 + 2] = 0.62; // dim cyan at the head
      acol[k * 6 + 3] = c.r; acol[k * 6 + 4] = c.g; acol[k * 6 + 5] = c.b;
    });
    const aGeo = new THREE.BufferGeometry();
    aGeo.setAttribute('position', new THREE.BufferAttribute(apos, 3));
    aGeo.setAttribute('color', new THREE.BufferAttribute(acol, 3));
    mem.avatarLinks = new THREE.LineSegments(aGeo, new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.10,
      blending: THREE.AdditiveBlending, depthWrite: false }));
    mem.avatarLinks.frustumCulled = false; // endpoints rewritten every frame
    J.scene.add(mem.avatarLinks);

    // pooled signals riding those links into the head (idle trickle → flood)
    for (let i = 0; i < 80; i++) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({
        map: glowTexture(), color: 0x9df5ff, transparent: true, opacity: 0,
        blending: THREE.AdditiveBlending, depthWrite: false }));
      sp.scale.set(10, 10, 1);
      sp.visible = false;
      sp.userData = { k: mem.top[i % nT], t: Math.random(), speed: 0.1 };
      J.scene.add(sp);
      mem.avatarPulses.push(sp);
    }
  }
}

/* ═══════════ galaxy mode: camera, hover picking, edit panel ═══════════ */
function galaxyCamPos(out) {
  const c = J.gCam;
  c.phi = Math.max(0.15, Math.min(Math.PI - 0.15, c.phi));
  c.dist = Math.max(150, Math.min(4500, c.dist));
  return out.set(
    GALAXY_CENTER.x + c.dist * Math.sin(c.phi) * Math.cos(c.theta),
    GALAXY_CENTER.y + c.dist * Math.cos(c.phi),
    GALAXY_CENTER.z + c.dist * Math.sin(c.phi) * Math.sin(c.theta));
}

function escJ(s) {
  return String(s).replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

function memPanelHTML(n) {
  const by = n.by === 'user' ? ['OPERATOR', '#5eead4'] : ['AGENT', '#7c5cff'];
  const when = n.created_at ? String(n.created_at).replace('T', ' ').slice(0, 19) : '—';
  return `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      <span style="width:9px;height:9px;border-radius:50%;background:${by[1]};box-shadow:0 0 8px ${by[1]}"></span>
      <span style="font-family:var(--font-mono);font-size:10.5px;letter-spacing:.14em;color:${by[1]}">${by[0]} MEMORY</span>
      <span style="margin-left:auto;font-family:var(--font-mono);font-size:10px;color:var(--text-dim)">${n.degree || 0} link${n.degree === 1 ? '' : 's'}</span>
    </div>
    <div style="font-size:13px;line-height:1.5;color:var(--text);margin-bottom:10px;max-height:150px;overflow:hidden">${escJ(n.text || '—')}</div>
    <div style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim)">${escJ(n.agent || '—')} · ${escJ(n.channel || '—')} · ${escJ(when)}${n.id ? ' · click to edit' : ''}</div>`;
}

function setMemHover(idx) {
  const mem = J.mem;
  if (idx === mem.hover) return;
  mem.hover = idx;
  if (!mem.marker) return;
  if (idx < 0) {
    mem.marker.visible = false;
    if (mem.panel) mem.panel.style.opacity = '0';
    if (J.container) J.container.style.cursor = J.galaxyMode ? 'grab' : '';
    return;
  }
  const n = mem.data.nodes[idx];
  mem.marker.visible = true;
  mem.marker.position.set(n.x * GALAXY_SCALE, n.y * GALAXY_SCALE, n.z * GALAXY_SCALE);
  mem.marker.material.color = new THREE.Color(mem.nodeColor(n));
  if (mem.panel) { mem.panel.innerHTML = memPanelHTML(n); mem.panel.style.opacity = '1'; }
  if (J.container) J.container.style.cursor = 'pointer';
}

// fly the camera through the bust into the galaxy (and back). Returns the
// new state so the app layer can swap the chat overlay in/out.
function toggleGalaxy() {
  if (!J.camera || !J.mem.group) return false;
  const entering = !J.galaxyMode;
  J.galaxyMode = entering;
  const toPos = new THREE.Vector3();
  const toLook = new THREE.Vector3();
  if (entering) {
    galaxyCamPos(toPos);
    toLook.set(GALAXY_CENTER.x, GALAXY_CENTER.y, GALAXY_CENTER.z);
  } else {
    toPos.set(0, 4, 88);
    toLook.set(0, 4, 0);
  }
  J.fly = {
    t: 0, dur: entering ? 2.6 : 1.8,
    fromPos: J.camera.position.clone(),
    fromLook: (J.lookCur || new THREE.Vector3(0, 4, 0)).clone(),
    via: new THREE.Vector3(0, -25, -250),   // dip through the bust
    toPos, toLook,
  };
  setMemHover(-1);
  J.drag = null; J.downAt = null;
  if (J.mem.hint) J.mem.hint.style.display = entering ? 'block' : 'none';
  if (J.container) J.container.style.cursor = entering ? 'grab' : '';
  return entering;
}

/* ═══════════════ frame loop ═══════════════ */
function tick() {
  if (J.disposed) return;
  J.raf = J.animOn ? requestAnimationFrame(tick) : null;
  const dt = 1 / 60;
  J.t += dt;
  const t = J.t;
  const tint = MODE_TINT[J.mode] || MODE_TINT.idle;

  if (J.camera) {
    if (J.fly) {
      // quadratic bezier dipped through the bust — the camera pierces the
      // particle head on its way into (or out of) the galaxy
      J.fly.t += dt / J.fly.dur;
      const k = Math.min(1, J.fly.t);
      const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      const q = 1 - e;
      const A = J.fly.fromPos, B = J.fly.via, C = J.fly.toPos;
      J.camera.position.set(
        q * q * A.x + 2 * q * e * B.x + e * e * C.x,
        q * q * A.y + 2 * q * e * B.y + e * e * C.y,
        q * q * A.z + 2 * q * e * B.z + e * e * C.z);
      J.lookCur.lerpVectors(J.fly.fromLook, J.fly.toLook, e);
      J.camera.lookAt(J.lookCur);
      if (k >= 1) J.fly = null;
    } else if (J.galaxyMode) {
      galaxyCamPos(J.camera.position);
      J.lookCur.set(GALAXY_CENTER.x, GALAXY_CENTER.y, GALAXY_CENTER.z);
      J.camera.lookAt(J.lookCur);
    } else {
      const ox = Math.sin(t * 0.13) * 6 + J.pointer.x * 7;
      const oy = 4 + Math.sin(t * 0.081) * 2.5 - J.pointer.y * 4;
      J.camera.position.x += (ox - J.camera.position.x) * 0.03;
      J.camera.position.y += (oy - J.camera.position.y) * 0.03;
      J.lookCur.set(0, 4, 0);
      J.camera.lookAt(0, 4, 0);
    }
  }

  if (J.head && J.headGroup) {
    // the whole bust (points + occluders + eye glints) turns as one
    J.headGroup.rotation.y = Math.sin(t * 0.16) * 0.17 + (J.mode === 'listening' ? 0.05 : 0);
    J.headGroup.rotation.x = Math.sin(t * 0.11) * 0.035;
    J.headGroup.scale.y = 1 + Math.sin(t * 1.1) * 0.005;

    // lip-sync: mouth band opens with the real audio level (down + forward
    // so open lips stay in front of the occluder surface)
    const posAttr = J.headGeo.attributes.position;
    const open = Math.min(1.6, J.level) * (J.mode === 'talking' ? 1 : 0.12);
    const mc = (J.mouthY[0] + J.mouthY[1]) / 2;
    const mh = Math.max(0.7, (J.mouthY[1] - J.mouthY[0]) / 2);
    for (let k = 0; k < J.mouthIdx.length; k++) {
      const n = J.mouthIdx[k];
      const by = J.basePos[n * 3 + 1];
      const center = Math.max(0, 1 - Math.abs((by - mc) / mh));
      posAttr.array[n * 3 + 1] = by - open * 2.2 * center - open * 0.3 * Math.random();
      posAttr.array[n * 3 + 2] = J.basePos[n * 3 + 2] + open * 0.7 * center;
    }
    if (J.mouthIdx.length) posAttr.needsUpdate = true;

    const blink = (t % 4.7) > 4.55 ? 0.2 : 1;
    const colAttr = J.headGeo.attributes.color;
    if ((Math.round(t * 60) & 3) === 0) {
      const mix = 0.14;
      for (let n = 0; n < colAttr.count; n++) {
        const b = J.baseB[n], w = J.baseW[n];
        colAttr.array[n * 3]     += (b * (tint[0] * (1 - w) + w) - colAttr.array[n * 3]) * mix;
        colAttr.array[n * 3 + 1] += (b * (tint[1] * (1 - w) + w) - colAttr.array[n * 3 + 1]) * mix;
        colAttr.array[n * 3 + 2] += (b * (tint[2] * (1 - w) + w) - colAttr.array[n * 3 + 2]) * mix;
      }
      for (const n of J.eyeIdx) {
        colAttr.array[n * 3] *= blink; colAttr.array[n * 3 + 1] *= blink; colAttr.array[n * 3 + 2] *= blink;
      }
      colAttr.needsUpdate = true;
    }
    J.head.material.size = 0.62 + Math.min(0.3, J.level * 0.22)
      + (J.mode === 'thinking' ? Math.sin(t * 5) * 0.05 : 0);
  }

  if (J.matrix) J.matrix.rotation.y = Math.sin(t * 0.02) * 0.03;

  const mem = J.mem;
  if (mem.group && mem.data) {
    mem.group.rotation.y += GALAXY_SPIN;   // the tab's slow spin
    const nodes = mem.data.nodes;
    const S = GALAXY_SCALE;
    const thinking = J.mode === 'thinking';

    // ambient electrical signals along the similarity links
    for (const p of mem.pulses) {
      const u = p.userData;
      u.t += u.speed * dt;
      if (u.t >= 1) {
        u.link = mem.data.links[Math.floor(Math.random() * mem.data.links.length)];
        u.t = 0; u.speed = 0.15 + u.link.s * 0.5;
      }
      const a = nodes[u.link.a], b = nodes[u.link.b];
      p.position.set((a.x + (b.x - a.x) * u.t) * S,
                     (a.y + (b.y - a.y) * u.t) * S,
                     (a.z + (b.z - a.z) * u.t) * S);
      p.material.opacity = 0.35 + Math.sin(u.t * Math.PI) * 0.6;
    }

    // THINKING: rapid amber traffic between the avatar-connected nodes
    for (const p of mem.thinkPulses) {
      if (!thinking) { p.visible = false; continue; }
      p.visible = true;
      const u = p.userData;
      u.t += u.speed * dt;
      if (u.t >= 1) {
        u.link = mem.thinkPairs[Math.floor(Math.random() * mem.thinkPairs.length)];
        u.t = 0; u.speed = 1.2 + Math.random() * 1.4;
      }
      const a = nodes[u.link.a], b = nodes[u.link.b];
      p.position.set((a.x + (b.x - a.x) * u.t) * S,
                     (a.y + (b.y - a.y) * u.t) * S,
                     (a.z + (b.z - a.z) * u.t) * S);
      p.material.opacity = 0.5 + Math.sin(u.t * Math.PI) * 0.5;
    }

    if (mem.avatarLinks) {
      // the 100 links follow the galaxy spin and the bust sway
      const ry = mem.group.rotation.y, cry = Math.cos(ry), sry = Math.sin(ry);
      const anchor = _tmpV.set(0, -8, -8);
      if (J.headGroup) anchor.applyEuler(J.headGroup.rotation);
      const ap = mem.avatarLinks.geometry.attributes.position.array;
      const wOf = (ni, out) => {
        const n = nodes[ni];
        const lx = n.x * S, lz = n.z * S;
        out[0] = GALAXY_CENTER.x + lx * cry + lz * sry;
        out[1] = GALAXY_CENTER.y + n.y * S;
        out[2] = GALAXY_CENTER.z - lx * sry + lz * cry;
      };
      const w = [0, 0, 0];
      mem.top.forEach((ni, k) => {
        wOf(ni, w);
        ap[k * 6] = anchor.x; ap[k * 6 + 1] = anchor.y; ap[k * 6 + 2] = anchor.z;
        ap[k * 6 + 3] = w[0]; ap[k * 6 + 4] = w[1]; ap[k * 6 + 5] = w[2];
      });
      mem.avatarLinks.geometry.attributes.position.needsUpdate = true;
      mem.avatarLinks.material.opacity +=
        ((thinking ? 0.22 : 0.10) - mem.avatarLinks.material.opacity) * 0.06;

      // inbound signals: idle trickle → flood while the answer forms
      if (mem.burst > 0) mem.burst -= dt;
      const want = mem.burst > 0 ? 80 : J.mode === 'talking' ? 16 : 6;
      mem.avatarPulses.forEach((sp, i) => {
        const u = sp.userData;
        const on = i < want;
        if (!sp.visible) {
          if (!on) return;
          sp.visible = true;
          u.t = Math.random() * 0.35;
          u.k = mem.top[Math.floor(Math.random() * mem.top.length)];
        }
        u.speed = mem.burst > 0 ? 0.9 + (i % 7) * 0.12 : 0.10 + (i % 5) * 0.02;
        u.t += u.speed * dt;
        if (u.t >= 1) {
          if (!on) { sp.visible = false; return; }
          u.t = 0;
          u.k = mem.top[Math.floor(Math.random() * mem.top.length)];
        }
        wOf(u.k, w);
        sp.position.set(w[0] + (anchor.x - w[0]) * u.t,
                        w[1] + (anchor.y - w[1]) * u.t,
                        w[2] + (anchor.z - w[2]) * u.t);
        sp.material.opacity = (mem.burst > 0 ? 0.95 : 0.5)
          * (0.4 + 0.6 * Math.sin(u.t * Math.PI));
      });
    }

    // galaxy mode: screen-space nearest-star picking (geometric raycasts
    // miss sub-pixel star points — same approach as the memory tab)
    if (J.galaxyMode && !J.fly && J.pointer && J.container) {
      const cw = J.container.clientWidth, ch = J.container.clientHeight;
      const px = (J.pointer.x + 1) / 2 * cw, py = (J.pointer.y + 1) / 2 * ch;
      let best = -1, bestD = 16 * 16;
      mem.group.updateMatrixWorld();
      const mw = mem.group.matrixWorld;
      for (let i = 0; i < nodes.length; i++) {
        _tmpV.set(nodes[i].x * S, nodes[i].y * S, nodes[i].z * S)
          .applyMatrix4(mw).project(J.camera);
        if (_tmpV.z > 1) continue;
        const dx = (_tmpV.x + 1) / 2 * cw - px, dy = (1 - _tmpV.y) / 2 * ch - py;
        const d = dx * dx + dy * dy;
        if (d < bestD) { bestD = d; best = i; }
      }
      setMemHover(best);
    } else if (mem.hover >= 0) {
      setMemHover(-1);
    }
  }

  J.renderer.render(J.scene, J.camera);
}

/* ═══════════════ public API ═══════════════ */
async function mount(container, opts) {
  const three = await loadThree();
  if (!three || !container || J.renderer) return;
  J.disposed = false;
  J.container = container;
  J.onMemorySelect = (opts && opts.onMemorySelect) || null;
  J.lookCur = new THREE.Vector3(0, 4, 0);
  J.galaxyMode = false;
  J.fly = null;
  // dist 1400 vs the ±1200 cloud ≈ the tab's default framing at 10× scale
  J.gCam = { theta: Math.PI / 2, phi: 1.35, dist: 1400 };
  _tmpV = new THREE.Vector3();
  const w = container.clientWidth || 800, h = container.clientHeight || 600;
  J.scene = new THREE.Scene();
  // fog light enough that the galaxy (~1600) and matrix (~3800) stay visible
  J.scene.fog = new THREE.FogExp2(0x05050c, 0.00016);
  J.camera = new THREE.PerspectiveCamera(46, w / h, 0.1, 9000);
  J.camera.position.set(0, 4, 88);
  J.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  J.renderer.setSize(w, h);
  J.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  J.renderer.domElement.className = 'jarvis3d-canvas';
  container.prepend(J.renderer.domElement);

  J.pointerHandler = (e) => {
    const r = container.getBoundingClientRect();
    J.pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    J.pointer.y = ((e.clientY - r.top) / r.height) * 2 - 1;
    if (J.drag && J.galaxyMode && !J.fly) {
      J.gCam.theta += (e.clientX - J.drag.x) * 0.0052;
      J.gCam.phi -= (e.clientY - J.drag.y) * 0.0052;
      J.drag = { x: e.clientX, y: e.clientY };
    }
  };
  container.addEventListener('pointermove', J.pointerHandler);

  // galaxy-mode navigation. Only pointer events whose TARGET is the canvas
  // count — clicks on toolbar buttons/chrome must never orbit or open a star.
  J.downHandler = (e) => {
    if (!J.galaxyMode || J.fly || e.target !== J.renderer.domElement) return;
    J.drag = { x: e.clientX, y: e.clientY };
    J.downAt = { x: e.clientX, y: e.clientY, t: performance.now() };
    try { container.setPointerCapture(e.pointerId); } catch { }
  };
  J.upHandler = (e) => {
    if (J.galaxyMode && !J.fly && J.onMemorySelect && J.downAt && J.mem.hover >= 0 &&
        Math.hypot(e.clientX - J.downAt.x, e.clientY - J.downAt.y) <= 6 &&
        performance.now() - J.downAt.t <= 600) {
      const n = J.mem.data.nodes[J.mem.hover];
      if (n && n.id) { try { J.onMemorySelect(n); } catch { } }
    }
    J.drag = null;
    J.downAt = null;
  };
  J.wheelHandler = (e) => {
    if (!J.galaxyMode) return;
    e.preventDefault();
    J.gCam.dist *= (1 + Math.sign(e.deltaY) * 0.09);
  };
  container.addEventListener('pointerdown', J.downHandler);
  container.addEventListener('pointerup', J.upHandler);
  container.addEventListener('wheel', J.wheelHandler, { passive: false });

  // galaxy-mode chrome: hover panel + help hint (DOM, above the canvas)
  J.mem.panel = document.createElement('div');
  J.mem.panel.style.cssText =
    'position:absolute;top:56px;left:14px;width:330px;max-width:44%;padding:14px 16px;' +
    'background:rgba(13,13,26,.85);border:1px solid rgba(124,92,255,.35);border-radius:14px;' +
    'backdrop-filter:blur(14px);opacity:0;transition:opacity .22s;pointer-events:none;z-index:6';
  container.appendChild(J.mem.panel);
  J.mem.hint = document.createElement('div');
  J.mem.hint.style.cssText =
    'position:absolute;left:16px;bottom:12px;font-family:var(--font-mono);font-size:10.5px;' +
    'color:var(--text-dim);pointer-events:none;z-index:6;display:none';
  J.mem.hint.textContent =
    'memory galaxy · drag orbit · scroll zoom · hover a star · click to edit · 🧠 Memory returns to JARVIS';
  container.appendChild(J.mem.hint);

  // primary: the prebuilt real-scan bust; fallback: the procedural sculpt
  let prebuilt = null;
  try {
    const r = await fetch('/static/avatar/head_points.json');
    if (r.ok) {
      const c = await r.json();
      if (c && c.occ && c.pos && c.pos.length > 9000) prebuilt = c;
    }
  } catch { }
  if (J.disposed) return;
  const built = prebuilt ? buildFromPrebuilt(prebuilt) : buildSculpt();
  const { pos, col, bri, wmi, mouthIdx, eyeIdx, mouthY } = built;
  if (J.disposed) return;
  J.mouthY = mouthY;
  J.basePos = Float32Array.from(pos);
  J.baseB = Float32Array.from(bri);
  J.baseW = Float32Array.from(wmi);
  J.mouthIdx = mouthIdx;
  J.eyeIdx = eyeIdx;
  J.headGeo = new THREE.BufferGeometry();
  J.headGeo.setAttribute('position', new THREE.BufferAttribute(Float32Array.from(pos), 3));
  J.headGeo.setAttribute('color', new THREE.BufferAttribute(Float32Array.from(col), 3));
  J.head = new THREE.Points(J.headGeo, new THREE.PointsMaterial({
    size: 0.55, map: glowTexture(), vertexColors: true, transparent: true,
    opacity: 0.62, depthWrite: false, blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
  }));
  J.head.renderOrder = 1;

  J.headGroup = new THREE.Group();
  J.headGroup.add(J.head);
  J.occluders = prebuilt ? buildPrebuiltOccluders(prebuilt) : buildOccluders();
  for (const m of J.occluders) J.headGroup.add(m);

  // eye glints: two soft sparks in the sockets — the "alive" cue
  const eyeY = prebuilt ? (prebuilt.eyes[0] + prebuilt.eyes[1]) / 2 : null;
  for (const side of [-1, 1]) {
    const gp = prebuilt
      ? { x: side * 3.6, y: eyeY, z: 9.6 }
      : headPoint(58 * D2R, side * 13 * D2R);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({
      map: glowTexture(), color: 0x9df5ff, transparent: true, opacity: 0.85,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    sp.scale.set(1.6, 1.6, 1);
    sp.position.set(gp.x, gp.y, gp.z + 0.6);
    sp.renderOrder = 2;
    J.headGroup.add(sp);
    J.glints.push(sp);
  }
  J.scene.add(J.headGroup);

  const memData = await buildGalaxyData();
  if (J.disposed) return;
  buildMatrix(memData);
  buildMemoryGalaxy(memData);

  J.resizeObs = new ResizeObserver(() => {
    if (!J.renderer || !J.container) return;
    const W = J.container.clientWidth, H = J.container.clientHeight;
    if (!W || !H) return;
    J.camera.aspect = W / H;
    J.camera.updateProjectionMatrix();
    J.renderer.setSize(W, H);
  });
  J.resizeObs.observe(container);

  tick();
}

function dispose() {
  J.disposed = true;
  if (J.raf) cancelAnimationFrame(J.raf);
  J.raf = null;
  if (J.resizeObs) { J.resizeObs.disconnect(); J.resizeObs = null; }
  if (J.container) {
    if (J.pointerHandler) J.container.removeEventListener('pointermove', J.pointerHandler);
    if (J.downHandler) J.container.removeEventListener('pointerdown', J.downHandler);
    if (J.upHandler) J.container.removeEventListener('pointerup', J.upHandler);
    if (J.wheelHandler) J.container.removeEventListener('wheel', J.wheelHandler);
    J.container.style.cursor = '';
    J.pointerHandler = J.downHandler = J.upHandler = J.wheelHandler = null;
  }
  if (J.renderer) {
    try { J.renderer.dispose(); J.renderer.domElement.remove(); } catch { }
  }
  if (J.head) { try { J.head.geometry.dispose(); J.head.material.dispose(); } catch { } J.head = null; }
  for (const root of [J.mem.group, J.matrix]) {
    if (!root) continue;
    root.traverse((o) => {
      try { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); } catch { }
    });
  }
  if (J.mem.avatarLinks) {
    try { J.mem.avatarLinks.geometry.dispose(); J.mem.avatarLinks.material.dispose(); } catch { }
  }
  for (const sp of J.mem.avatarPulses) { try { sp.material.dispose(); } catch { } }
  if (J.mem.panel) J.mem.panel.remove();
  if (J.mem.hint) J.mem.hint.remove();
  J.mem = emptyMem();
  J.matrix = null; J.galaxyMode = false; J.fly = null;
  J.drag = null; J.downAt = null; J.onMemorySelect = null;
  for (const m of J.occluders) { try { m.geometry.dispose(); } catch { } }
  for (const g of J.glints) { try { g.material.dispose(); } catch { } }
  J.occluders = []; J.glints = []; J.headGroup = null;
  J.renderer = null; J.scene = null;
  J.headGeo = null; J.basePos = null; J.baseB = null; J.baseW = null;
}

function setMode(mode) {
  // leaving THINKING = the answer is forming → memory floods into the head
  if (J.mode === 'thinking' && mode !== 'thinking') J.mem.burst = 2.4;
  J.mode = mode;
}
function setLevel(v) { J.level = Math.max(0, v || 0); }
function setAnimations(on) {
  J.animOn = !!on;
  if (on && !J.raf && !J.disposed && J.renderer) tick();
  else if (!on && J.raf) { cancelAnimationFrame(J.raf); J.raf = null; }
}

window.Jarvis3D = { mount, dispose, setMode, setLevel, setAnimations, toggleGalaxy };
