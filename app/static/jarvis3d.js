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

   Same public API + galaxy + node streams as before:
   window.Jarvis3D = { mount, dispose, setMode, setLevel, setAnimations }
   Lazy CDN three.js import — the string "three" never appears in index.html
   (verify.sh gate). Lip-sync: mouth-band points (exact by construction)
   displaced by setLevel; eye-band points blink. */

let THREE = null;
let threePromise = null;

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
  head: null, headGroup: null, headGeo: null, occluders: [], galaxy: null, streams: [],
  pulses: [], glints: [], mouthIdx: [], eyeIdx: [], basePos: null,
  baseB: null, baseW: null, mouthY: [0, 1], level: 0, mode: 'idle', t: 0,
  animOn: true, disposed: false, resizeObs: null,
  pointer: { x: 0, y: 0 }, pointerHandler: null,
};

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

/* ═══════════════ galaxy + streams (unchanged aesthetics) ═══════════════ */
const CYAN_FAMILY = [0x22d3ee, 0x67e8f9, 0x0ea5b7];
const DISTINCT_HUES = [0xa3e635, 0xf43f5e, 0xf59e0b, 0x8b5cf6, 0xec4899,
                       0x60a5fa, 0x2dd4bf, 0xfb7185, 0xfacc15, 0x34d399];

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

function mountGalaxy(data) {
  const nodes = data.nodes || [];
  const pos = new Float32Array(nodes.length * 3);
  const col = new Float32Array(nodes.length * 3);
  const centers = {}, ccount = {};
  const color = new THREE.Color();
  nodes.forEach((n, i) => {
    const gx = (n.x || 0) * 1.7, gy = (n.y || 0) * 1.25 + 8, gz = -150 + (n.z || 0) * 1.3;
    pos[i * 3] = gx; pos[i * 3 + 1] = gy; pos[i * 3 + 2] = gz;
    const grp = n.group || 0;
    const hex = grp < 2 ? CYAN_FAMILY[grp % CYAN_FAMILY.length]
                        : DISTINCT_HUES[grp % DISTINCT_HUES.length];
    color.setHex(hex);
    col[i * 3] = color.r; col[i * 3 + 1] = color.g; col[i * 3 + 2] = color.b;
    const key = n.cluster != null ? n.cluster : grp;
    (centers[key] = centers[key] || [0, 0, 0])[0] += gx;
    centers[key][1] += gy; centers[key][2] += gz;
    ccount[key] = (ccount[key] || 0) + 1;
  });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  J.galaxy = new THREE.Points(geo, new THREE.PointsMaterial({
    size: 3.6, map: glowTexture(), vertexColors: true, transparent: true,
    opacity: 1.0, depthWrite: false, blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
  }));
  J.scene.add(J.galaxy);
  return Object.entries(centers).map(([k, s]) => new THREE.Vector3(
    s[0] / ccount[k], s[1] / ccount[k], s[2] / ccount[k]));
}

function mountStreams(clusterCenters) {
  const targets = clusterCenters.length ? clusterCenters : [new THREE.Vector3(0, 10, -170)];
  const N = Math.min(16, Math.max(8, targets.length * 2));
  for (let i = 0; i < N; i++) {
    const tgt = targets[i % targets.length];
    const a = (i / N) * Math.PI * 2;
    const start = new THREE.Vector3(Math.cos(a) * 8, 14 + Math.sin(a * 2) * 7, -9 - Math.random() * 4);
    const mid1 = new THREE.Vector3(start.x * 3.2, start.y * 1.4 + 6, -46 - Math.random() * 22);
    const mid2 = new THREE.Vector3(tgt.x * 0.55 + (Math.random() - .5) * 24,
                                   tgt.y * 0.7 + (Math.random() - .5) * 18, -110);
    const curve = new THREE.CatmullRomCurve3([start, mid1, mid2, tgt]);
    const geo = new THREE.BufferGeometry().setFromPoints(curve.getPoints(48));
    const line = new THREE.Line(geo, new THREE.LineBasicMaterial({
      color: 0x22d3ee, transparent: true, opacity: 0.28,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    J.scene.add(line);
    J.streams.push({ curve, line });
    for (let p = 0; p < 2; p++) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({
        map: glowTexture(), color: 0x67e8f9, transparent: true,
        opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false,
      }));
      sp.scale.set(2.6, 2.6, 1);
      J.scene.add(sp);
      J.pulses.push({ sprite: sp, curve, t: Math.random(), speed: 0.04 + Math.random() * 0.05 });
    }
  }
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
    const ox = Math.sin(t * 0.13) * 6 + J.pointer.x * 7;
    const oy = 4 + Math.sin(t * 0.081) * 2.5 - J.pointer.y * 4;
    J.camera.position.x += (ox - J.camera.position.x) * 0.03;
    J.camera.position.y += (oy - J.camera.position.y) * 0.03;
    J.camera.lookAt(0, 4, 0);
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

  if (J.galaxy) J.galaxy.rotation.y = Math.sin(t * 0.05) * 0.12;
  const speedMul = J.mode === 'thinking' ? 3.2 : J.mode === 'talking' ? 1.7 : 1;
  for (const p of J.pulses) {
    p.t += p.speed * speedMul * dt * 2.2;
    if (p.t > 1) p.t = 0;
    p.sprite.position.copy(p.curve.getPoint(p.t));
    p.sprite.material.opacity = 0.25 + 0.65 * Math.sin(p.t * Math.PI);
  }
  for (const s of J.streams) {
    s.line.material.opacity = 0.10 + (J.mode === 'thinking' ? 0.14 : 0.05) * (0.6 + 0.4 * Math.sin(t * 2));
  }

  J.renderer.render(J.scene, J.camera);
}

/* ═══════════════ public API ═══════════════ */
async function mount(container) {
  const three = await loadThree();
  if (!three || !container || J.renderer) return;
  J.disposed = false;
  J.container = container;
  const w = container.clientWidth || 800, h = container.clientHeight || 600;
  J.scene = new THREE.Scene();
  J.scene.fog = new THREE.FogExp2(0x05050c, 0.0028);
  J.camera = new THREE.PerspectiveCamera(46, w / h, 0.1, 600);
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
  };
  container.addEventListener('pointermove', J.pointerHandler);

  const { pos, col, bri, wmi, mouthIdx, eyeIdx, mouthY } = buildSculpt();
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
  J.occluders = buildOccluders();
  for (const m of J.occluders) J.headGroup.add(m);

  // eye glints: two soft sparks in the sockets — the "alive" cue
  for (const side of [-1, 1]) {
    const gp = headPoint(58 * D2R, side * 13 * D2R);
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

  const centers = mountGalaxy(await buildGalaxyData());
  if (J.disposed) return;
  mountStreams(centers);

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
  if (J.container && J.pointerHandler) {
    J.container.removeEventListener('pointermove', J.pointerHandler);
    J.pointerHandler = null;
  }
  if (J.renderer) {
    try { J.renderer.dispose(); J.renderer.domElement.remove(); } catch { }
  }
  for (const k of ['head', 'galaxy']) {
    if (J[k]) { try { J[k].geometry.dispose(); J[k].material.dispose(); } catch { } J[k] = null; }
  }
  for (const m of J.occluders) { try { m.geometry.dispose(); } catch { } }
  for (const g of J.glints) { try { g.material.dispose(); } catch { } }
  J.occluders = []; J.glints = []; J.headGroup = null;
  J.streams = []; J.pulses = []; J.renderer = null; J.scene = null;
  J.headGeo = null; J.basePos = null; J.baseB = null; J.baseW = null;
}

function setMode(mode) { J.mode = mode; }
function setLevel(v) { J.level = Math.max(0, v || 0); }
function setAnimations(on) {
  J.animOn = !!on;
  if (on && !J.raf && !J.disposed && J.renderer) tick();
  else if (!on && J.raf) { cancelAnimationFrame(J.raf); J.raf = null; }
}

window.Jarvis3D = { mount, dispose, setMode, setLevel, setAnimations };
