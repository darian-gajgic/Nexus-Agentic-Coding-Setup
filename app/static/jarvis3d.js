/* JARVIS 3D v3 — sculpted particle bust (true 3D form).

   v2 sampled the reference PHOTO into a flat relief — it read as a 2D poster
   of dots (operator feedback 2026-07-08). v3 builds a real 3D bust:

   - GEOMETRY: parametric skull — cranium + jaw ellipsoids, neck cylinder,
     shoulder capsule — sampled as ~28k surface points with real NORMALS.
     The silhouette is a smooth sculpted form from every angle.
   - SHADING: per-point lambert from a virtual key light + rim light on
     grazing normals (the thing that makes a point cloud read as VOLUME),
     plus depth dimming. This is computed once at build; the tint crossfade
     preserves it.
   - IDENTITY: the reference photo is projected onto the FRONT of the skull
     (anchored at the eye/mouth lines): luminance + edges modulate point
     brightness, so brows/eyes/nose/lips/beard appear as his features.
   - MOTION PARALLAX: slow camera orbit + pointer parallax + a deeper idle
     head turn — motion parallax is the second half of "looks 3D".
   - Same lip-sync (mouth-band points driven by setLevel), states, galaxy
     backdrop from /api/memory3d, and node streams out of the back of the
     skull. Same public API:
     window.Jarvis3D = { mount, dispose, setMode, setLevel, setAnimations }

   Lazy CDN import as in nexus3d/memory3d — the string "three" never appears
   in index.html (verify.sh gate). */

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
  head: null, headGeo: null, galaxy: null, streams: [], pulses: [],
  mouthIdx: [], eyeIdx: [], basePos: null, baseB: null, baseW: null,
  level: 0, mode: 'idle', t: 0, animOn: true, disposed: false,
  resizeObs: null, pointer: { x: 0, y: 0 }, pointerHandler: null,
};

const MODE_TINT = {
  idle:      [0.30, 0.85, 1.00],   // cyan
  listening: [0.37, 0.92, 0.83],   // teal
  thinking:  [0.98, 0.75, 0.30],   // amber
  talking:   [0.45, 0.95, 1.00],   // bright cyan
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

/* ── photo analysis: subject mask + luminance + edges + depth map.
   The bust geometry is derived from the OPERATOR'S OWN photo: the
   background-removed silhouette (hair, jaw, neck, shoulders) is "inflated"
   into a volume via a chamfer distance transform (distance to the silhouette
   edge → depth), so the front view IS his shape — not a generic ellipsoid. ── */
async function loadPhotoModel() {
  const img = await new Promise((res) => {
    const i = new Image();
    i.onload = () => res(i);
    i.onerror = () => res(null);
    i.src = '/static/avatar/reference.jpg';
  });
  if (!img) return null;
  const S = 170;
  const cv = document.createElement('canvas');
  cv.width = cv.height = S;
  const g = cv.getContext('2d');
  g.drawImage(img, 0, 0, S, S);
  const px = g.getImageData(0, 0, S, S).data;
  const lum = new Float32Array(S * S);
  for (let i = 0; i < S * S; i++) {
    lum[i] = (px[i * 4] * 0.299 + px[i * 4 + 1] * 0.587 + px[i * 4 + 2] * 0.114) / 255;
  }
  // subject mask: color-distance from the top-corner (wall) average
  let br = 0, bgc = 0, bb = 0, bn = 0;
  for (let y = 0; y < 12; y++) {
    for (const x0 of [0, S - 12]) {
      for (let x = x0; x < x0 + 12; x++) {
        const i = (y * S + x) * 4;
        br += px[i] / 255; bgc += px[i + 1] / 255; bb += px[i + 2] / 255; bn++;
      }
    }
  }
  br /= bn; bgc /= bn; bb /= bn;
  const raw = new Uint8Array(S * S);
  for (let i = 0; i < S * S; i++) {
    const d = Math.hypot(px[i * 4] / 255 - br, px[i * 4 + 1] / 255 - bgc, px[i * 4 + 2] / 255 - bb);
    raw[i] = d > 0.16 ? 1 : 0;
  }
  const mask = new Uint8Array(S * S);
  for (let y = 1; y < S - 1; y++) {
    for (let x = 1; x < S - 1; x++) {
      const i = y * S + x;
      if (!raw[i]) continue;
      let nb = 0;
      for (const o of [-S - 1, -S, -S + 1, -1, 1, S - 1, S, S + 1]) nb += raw[i + o];
      mask[i] = nb >= 3 ? 1 : 0;
    }
  }
  // chamfer distance transform: distance (px) to the silhouette edge
  const INF = 1e6;
  const dist = new Float32Array(S * S);
  for (let i = 0; i < S * S; i++) dist[i] = mask[i] ? INF : 0;
  for (let y = 1; y < S; y++) {
    for (let x = 1; x < S - 1; x++) {
      const i = y * S + x;
      if (!dist[i]) continue;
      dist[i] = Math.min(dist[i], dist[i - S] + 1, dist[i - 1] + 1,
                         dist[i - S - 1] + 1.4, dist[i - S + 1] + 1.4);
    }
  }
  for (let y = S - 2; y >= 0; y--) {
    for (let x = S - 2; x >= 1; x--) {
      const i = y * S + x;
      if (!dist[i]) continue;
      dist[i] = Math.min(dist[i], dist[i + S] + 1, dist[i + 1] + 1,
                         dist[i + S - 1] + 1.4, dist[i + S + 1] + 1.4);
    }
  }
  // contrast stretch over the central face window (avoids the bright wall)
  const tones = [];
  for (let y = Math.floor(S * 0.28); y < S * 0.72; y++) {
    for (let x = Math.floor(S * 0.30); x < S * 0.70; x++) tones.push(lum[y * S + x]);
  }
  tones.sort((a, b) => a - b);
  const lo = tones[Math.floor(tones.length * 0.05)] ?? 0;
  const hi = tones[Math.floor(tones.length * 0.97)] ?? 1;
  const stretch = (l) => Math.min(1, Math.max(0, (l - lo) / Math.max(0.01, hi - lo)));
  return { S, mask, dist, lumRaw: lum, stretch };
}

/* ── bust from the 3D SCAN (built offline from the operator's 360° head-turn
   video by scripts/build_avatar_pointcloud.py — Depth-Anything per frame +
   turntable fusion, lighting baked). This is the primary path; the photo
   inflation below is the fallback when no scan file exists. ── */
function buildFromScan(cloud) {
  const pos = [], col = [], bri = [], wmi = [], mouthIdx = [], eyeIdx = [];
  const P = cloud.pos, B = cloud.bri;
  const [my0, my1, mxh] = cloud.mouth || [0, 1, 6];
  const [ey0, ey1, exh] = cloud.eyes || [0, 1, 8];
  for (let i = 0; i < B.length; i++) {
    const x = P[i * 3], y = P[i * 3 + 1], z = P[i * 3 + 2];
    const b = B[i];
    const n = pos.length / 3;
    // jitter breaks the voxel-lattice moiré
    pos.push(x + (Math.random() - .5) * .55,
             y + (Math.random() - .5) * .55,
             z + (Math.random() - .5) * .55);
    const w = b > 0.88 ? Math.min(1, (b - 0.88) / 0.25) * 0.45 : 0;
    bri.push(b); wmi.push(w);
    col.push(b * (MODE_TINT.idle[0] * (1 - w) + w),
             b * (MODE_TINT.idle[1] * (1 - w) + w),
             b * (MODE_TINT.idle[2] * (1 - w) + w));
    if (z > 2 && y > my0 && y < my1 && Math.abs(x) < mxh) mouthIdx.push(n);
    if (z > 2 && y > ey0 && y < ey1 && Math.abs(x) > 1.5 && Math.abs(x) < exh) eyeIdx.push(n);
  }
  return { pos, col, bri, wmi, mouthIdx, eyeIdx, mouthY: [my0, my1] };
}

/* ── bust from the photo: inflated silhouette, HIS actual shape ── */
function buildBust(pm) {
  const pos = [], col = [], bri = [], wmi = [], mouthIdx = [], eyeIdx = [];
  if (!pm) return { pos, col, bri, wmi, mouthIdx, eyeIdx, mouthY: [0, 1] };
  const { S, mask, dist, lumRaw, stretch } = pm;
  const KEY = new THREE.Vector3(-0.45, 0.55, 0.8).normalize();
  const N = new THREE.Vector3();

  const WS = 57;                                  // world size of the photo
  const X = (u) => (u - 0.5) * WS;
  const Y = (v) => (0.52 - v) * WS;               // photo v → world y
  // depth budget per row: full head → thinner neck → shoulders
  const sm = (a, b, x) => {
    const s = Math.min(1, Math.max(0, (x - a) / (b - a)));
    return s * s * (3 - 2 * s);
  };
  const depthScale = (v) => 15 - 8 * sm(0.64, 0.72, v) + 3.5 * sm(0.74, 0.84, v);
  const DCAP = 14;                                // px distance where depth plateaus

  // depth map: inflate the silhouette — deeper toward the middle, plus a
  // touch of luminance relief so the face is not a smooth balloon
  const D = new Float32Array(S * S);
  for (let y = 0; y < S; y++) {
    for (let x = 0; x < S; x++) {
      const i = y * S + x;
      if (!mask[i]) continue;
      const v = y / S;
      D[i] = Math.sqrt(Math.min(1, dist[i] / DCAP)) * depthScale(v)
        + stretch(lumRaw[i]) * 1.6;
    }
  }

  // photo-space feature bands (exact, measured): eyes v≈0.36, mouth v≈0.556
  const EYE_V = [0.335, 0.395], EYE_U = 0.20;     // |u-0.5| in 0.05..0.20
  const MOUTH_V = [0.525, 0.590], MOUTH_U = 0.10;
  const mouthYs = [];

  function addPoint(u, v, front) {
    const xg = Math.round(u * S), yg = Math.round(v * S);
    const i = yg * S + xg;
    const l = stretch(lumRaw[i]);
    const e = Math.min(1, (Math.abs(lumRaw[i + 1] - lumRaw[i - 1])
      + Math.abs(lumRaw[i + S] - lumRaw[i - S])) * 4.0);
    // normals from the depth-map gradient (world-scaled) — HIS silhouette
    // and brow/nose relief drive the lighting
    const pxw = WS / S;
    const dzdx = (D[i + 1] - D[i - 1]) / (2 * pxw);
    const dzdy = (D[i + S] - D[i - S]) / (2 * pxw);   // photo y grows downward
    if (front) N.set(-dzdx, dzdy, 1).normalize();
    else N.set(-dzdx * 0.4, dzdy * 0.4, -1).normalize();
    const frontness = N.z;
    const lambert = Math.max(0, N.dot(KEY));
    const fill = Math.max(0, frontness) * 0.20;
    let rim = Math.pow(1 - Math.abs(frontness), 1.6) * 0.55;
    // identity carving on the front: posterized tones, holes for dark
    // features inside the face oval, edge sparkle
    let faceMul = 1, faceAdd = 0;
    if (front) {
      const inFace = Math.abs(u - 0.5) < 0.20 && v > 0.26 && v < 0.66;
      if (inFace && l < 0.30 && e < 0.25 && Math.random() < 0.75) return;
      faceMul = l < 0.22 ? 0.14 : l < 0.42 ? 0.5 : l < 0.68 ? 0.95 : 1.30;
      faceAdd = e * 0.65;
      if (inFace) rim *= 0.4;
    } else {
      faceMul = 0.4;                              // back shell: dim volume hint
    }
    let b = (0.10 + 0.55 * Math.pow(lambert, 1.25) + fill + rim) * faceMul + faceAdd;
    b = Math.min(1.35, b);
    const wx = X(u), wy = Y(v);
    const wz = front ? D[i] : -D[i] * 0.85;
    const n = pos.length / 3;
    pos.push(wx + (Math.random() - .5) * .4,
             wy + (Math.random() - .5) * .4,
             wz + (Math.random() - .5) * .5);
    const w = b > 0.88 ? Math.min(1, (b - 0.88) / 0.25) * 0.45 : 0;
    bri.push(b); wmi.push(w);
    col.push(b * (MODE_TINT.idle[0] * (1 - w) + w),
             b * (MODE_TINT.idle[1] * (1 - w) + w),
             b * (MODE_TINT.idle[2] * (1 - w) + w));
    if (front && v > MOUTH_V[0] && v < MOUTH_V[1] && Math.abs(u - 0.5) < MOUTH_U) {
      mouthIdx.push(n);
      mouthYs.push(wy);
    }
    if (front && v > EYE_V[0] && v < EYE_V[1]
        && Math.abs(u - 0.5) > 0.05 && Math.abs(u - 0.5) < EYE_U) eyeIdx.push(n);
  }

  // sampling: ~2 front points per subject pixel (extra density in the face
  // oval so features resolve), ~0.6 back points for the volume
  for (let yg = 1; yg < S - 1; yg++) {
    for (let xg = 1; xg < S - 1; xg++) {
      if (!mask[yg * S + xg]) continue;
      const u0 = xg / S, v0 = yg / S;
      const inFace = Math.abs(u0 - 0.5) < 0.22 && v0 > 0.24 && v0 < 0.68;
      const nFront = inFace ? 3 : 1.4;
      for (let k = 0; k < nFront; k++) {
        if (k + 1 > nFront && Math.random() > nFront % 1) break;
        addPoint(u0 + (Math.random() - .5) / S, v0 + (Math.random() - .5) / S, true);
      }
      if (Math.random() < 0.55) {
        addPoint(u0 + (Math.random() - .5) / S, v0 + (Math.random() - .5) / S, false);
      }
    }
  }
  const mouthY = mouthYs.length
    ? [Math.min(...mouthYs), Math.max(...mouthYs)] : [0, 1];
  return { pos, col, bri, wmi, mouthIdx, eyeIdx, mouthY };
}

/* ── Galaxy backdrop from the user's REAL memory map ── */
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
  const centers = {};
  const ccount = {};
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
  const mat = new THREE.PointsMaterial({
    size: 3.6, map: glowTexture(), vertexColors: true, transparent: true,
    opacity: 1.0, depthWrite: false, blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
  });
  J.galaxy = new THREE.Points(geo, mat);
  J.scene.add(J.galaxy);
  return Object.entries(centers).map(([k, s]) => new THREE.Vector3(
    s[0] / ccount[k], s[1] / ccount[k], s[2] / ccount[k]));
}

/* ── Node streams: back of head → galaxy clusters, with traveling pulses ── */
function mountStreams(clusterCenters) {
  const targets = clusterCenters.length ? clusterCenters : [new THREE.Vector3(0, 10, -170)];
  const N = Math.min(16, Math.max(8, targets.length * 2));
  for (let i = 0; i < N; i++) {
    const tgt = targets[i % targets.length];
    const a = (i / N) * Math.PI * 2;
    const start = new THREE.Vector3(Math.cos(a) * 9, 9 + Math.sin(a * 2) * 8, -11 - Math.random() * 5);
    const mid1 = new THREE.Vector3(start.x * 3.2, start.y * 1.6 + 6, -46 - Math.random() * 22);
    const mid2 = new THREE.Vector3(tgt.x * 0.55 + (Math.random() - .5) * 24,
                                   tgt.y * 0.7 + (Math.random() - .5) * 18, -110);
    const curve = new THREE.CatmullRomCurve3([start, mid1, mid2, tgt]);
    const pts = curve.getPoints(48);
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    const mat = new THREE.LineBasicMaterial({
      color: 0x22d3ee, transparent: true, opacity: 0.28,
      blending: THREE.AdditiveBlending, depthWrite: false,
    });
    const line = new THREE.Line(geo, mat);
    J.scene.add(line);
    J.streams.push({ curve, line });
    for (let p = 0; p < 2; p++) {
      const sm = new THREE.SpriteMaterial({
        map: glowTexture(), color: 0x67e8f9, transparent: true,
        opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false,
      });
      const sp = new THREE.Sprite(sm);
      sp.scale.set(2.6, 2.6, 1);
      J.scene.add(sp);
      J.pulses.push({ sprite: sp, curve, t: Math.random(), speed: 0.04 + Math.random() * 0.05 });
    }
  }
}

/* ── Frame loop ── */
function tick() {
  if (J.disposed) return;
  J.raf = J.animOn ? requestAnimationFrame(tick) : null;
  const dt = 1 / 60;
  J.t += dt;
  const t = J.t;
  const tint = MODE_TINT[J.mode] || MODE_TINT.idle;

  // motion parallax: slow camera orbit + pointer-follow (eased)
  if (J.camera) {
    const px = J.pointer.x, py = J.pointer.y;
    const ox = Math.sin(t * 0.13) * 6 + px * 7;
    const oy = 4 + Math.sin(t * 0.081) * 2.5 - py * 4;
    J.camera.position.x += (ox - J.camera.position.x) * 0.03;
    J.camera.position.y += (oy - J.camera.position.y) * 0.03;
    J.camera.lookAt(0, 1, 0);
  }

  if (J.head) {
    const breathe = 1 + Math.sin(t * 1.1) * 0.006;
    J.head.scale.set(1, breathe, 1);
    // deeper idle turn: the form reveal is what reads as 3D
    J.head.rotation.y = Math.sin(t * 0.16) * 0.17 + (J.mode === 'listening' ? 0.05 : 0);
    J.head.rotation.x = Math.sin(t * 0.11) * 0.035;

    // mouth: native-timing lip-sync — band measured from the photo at build
    const posAttr = J.headGeo.attributes.position;
    const open = Math.min(1.6, J.level) * (J.mode === 'talking' ? 1 : 0.15);
    const mc = (J.mouthY[0] + J.mouthY[1]) / 2;
    const mh = Math.max(0.8, (J.mouthY[1] - J.mouthY[0]) / 2);
    for (let k = 0; k < J.mouthIdx.length; k++) {
      const n = J.mouthIdx[k];
      const by = J.basePos[n * 3 + 1];
      const center = Math.max(0, 1 - Math.abs((by - mc) / mh));
      posAttr.array[n * 3 + 1] = by - open * 2.8 * center - open * 0.4 * Math.random();
      posAttr.array[n * 3 + 2] = J.basePos[n * 3 + 2] - open * 0.8 * center;
    }
    if (J.mouthIdx.length) posAttr.needsUpdate = true;

    // eye blink + mode tint crossfade (full-buffer writes every 4th frame)
    const blink = (t % 4.7) > 4.55 ? 0.25 : 1;
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
    J.head.material.size = 0.85 + Math.min(0.45, J.level * 0.32)
      + (J.mode === 'thinking' ? Math.sin(t * 5) * 0.06 : 0);
  }

  if (J.galaxy) J.galaxy.rotation.y = Math.sin(t * 0.05) * 0.12;

  const speedMul = J.mode === 'thinking' ? 3.2 : J.mode === 'talking' ? 1.7 : 1;
  for (const p of J.pulses) {
    p.t += p.speed * speedMul * dt * 2.2;
    if (p.t > 1) p.t = 0;
    const v = p.curve.getPoint(p.t);
    p.sprite.position.copy(v);
    p.sprite.material.opacity = 0.25 + 0.65 * Math.sin(p.t * Math.PI);
  }
  for (const s of J.streams) {
    s.line.material.opacity = 0.10 + (J.mode === 'thinking' ? 0.14 : 0.05) * (0.6 + 0.4 * Math.sin(t * 2));
  }

  J.renderer.render(J.scene, J.camera);
}

/* ── Public API ── */
async function mount(container) {
  const three = await loadThree();
  if (!three || !container || J.renderer) return;
  J.disposed = false;
  J.container = container;
  const w = container.clientWidth || 800, h = container.clientHeight || 600;
  J.scene = new THREE.Scene();
  J.scene.fog = new THREE.FogExp2(0x05050c, 0.0028);
  J.camera = new THREE.PerspectiveCamera(46, w / h, 0.1, 600);
  J.camera.position.set(0, 4, 86);
  J.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  J.renderer.setSize(w, h);
  J.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  J.renderer.domElement.className = 'jarvis3d-canvas';
  container.prepend(J.renderer.domElement);

  // pointer parallax (normalized -1..1 over the stage)
  J.pointerHandler = (e) => {
    const r = container.getBoundingClientRect();
    J.pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    J.pointer.y = ((e.clientY - r.top) / r.height) * 2 - 1;
  };
  container.addEventListener('pointermove', J.pointerHandler);

  // primary: the offline 3D scan of the operator; fallback: photo inflation
  let scan = null;
  try {
    const r = await fetch('/static/avatar/head_points.json');
    if (r.ok) scan = await r.json();
  } catch { }
  if (J.disposed) return;
  let built;
  if (scan && scan.pos && scan.pos.length > 9000) {
    built = buildFromScan(scan);
  } else {
    built = buildBust(await loadPhotoModel());
  }
  if (J.disposed) return;
  const { pos, col, bri, wmi, mouthIdx, eyeIdx, mouthY } = built;
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
    size: 0.85, map: glowTexture(), vertexColors: true, transparent: true,
    opacity: 0.95, depthWrite: false, blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
  }));
  J.head.position.set(0, 1, 0);
  J.scene.add(J.head);

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
    try {
      J.renderer.dispose();
      J.renderer.domElement.remove();
    } catch { }
  }
  for (const k of ['head', 'galaxy']) {
    if (J[k]) { try { J[k].geometry.dispose(); J[k].material.dispose(); } catch { } J[k] = null; }
  }
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
