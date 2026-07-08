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

/* ── photo → feature map (luminance + edges, subject-masked) ── */
async function loadFaceMap() {
  const img = await new Promise((res) => {
    const i = new Image();
    i.onload = () => res(i);
    i.onerror = () => res(null);
    i.src = '/static/avatar/reference.jpg';
  });
  const S = 180;
  const cv = document.createElement('canvas');
  cv.width = cv.height = S;
  const g = cv.getContext('2d');
  if (!img) return null;
  g.drawImage(img, 0, 0, S, S);
  const px = g.getImageData(0, 0, S, S).data;
  const lum = new Float32Array(S * S);
  for (let i = 0; i < S * S; i++) {
    lum[i] = (px[i * 4] * 0.299 + px[i * 4 + 1] * 0.587 + px[i * 4 + 2] * 0.114) / 255;
  }
  // contrast stretch over the central face window (avoids the bright wall)
  const tones = [];
  for (let y = Math.floor(S * 0.28); y < S * 0.72; y++) {
    for (let x = Math.floor(S * 0.30); x < S * 0.70; x++) tones.push(lum[y * S + x]);
  }
  tones.sort((a, b) => a - b);
  const lo = tones[Math.floor(tones.length * 0.05)] ?? 0;
  const hi = tones[Math.floor(tones.length * 0.97)] ?? 1;
  return {
    S,
    lum: (u, v) => {
      const x = Math.min(S - 2, Math.max(1, Math.round(u * S)));
      const y = Math.min(S - 2, Math.max(1, Math.round(v * S)));
      return Math.min(1, Math.max(0, (lum[y * S + x] - lo) / Math.max(0.01, hi - lo)));
    },
    edge: (u, v) => {
      const x = Math.min(S - 2, Math.max(1, Math.round(u * S)));
      const y = Math.min(S - 2, Math.max(1, Math.round(v * S)));
      const i = y * S + x;
      return Math.min(1, (Math.abs(lum[i + 1] - lum[i - 1]) + Math.abs(lum[i + S] - lum[i - S])) * 4.0);
    },
  };
}

/* ── parametric bust sampled as lit surface points ── */
function buildBust(face) {
  const pos = [], col = [], bri = [], wmi = [], mouthIdx = [], eyeIdx = [];
  const KEY = new THREE.Vector3(-0.45, 0.55, 0.8).normalize();   // key light
  const Zax = new THREE.Vector3(0, 0, 1);
  const N = new THREE.Vector3();

  // photo anchors (measured): eyes at v=0.36 ↔ head y=+3.5;
  // mouth at v=0.556 ↔ head y=-4.5; face half-width 0.215 ↔ x=10.5
  const photoV = (y) => 0.36 + (3.5 - y) * 0.0245;
  const photoU = (x) => 0.5 + x * (0.215 / 10.5);

  function addPoint(x, y, z, nx, ny, nz, part) {
    N.set(nx, ny, nz).normalize();
    const frontness = N.z;   // normalized! the raw nz param is ellipsoid-scaled
    // volume shading: ambient + key lambert + frontal fill + rim on grazing
    // normals — fill keeps the FACE readable, rim sells the silhouette
    const lambert = Math.max(0, N.dot(KEY));
    const fill = Math.max(0, frontness) * 0.20;
    let rim = Math.pow(1 - Math.max(0, frontness), 2.6) * 0.42;
    // identity: the photo CARVES the front of the face. Dark features REMOVE
    // points (holes survive additive glow-bleed; dimming alone does not) and
    // squared contrast keeps eye sockets/brows/lips dark vs lit skin.
    let faceMul = 1, faceAdd = 0;
    if (face && part === 'skull' && frontness > 0.30 && y > -9.5 && y < 15) {
      const u = photoU(x), v = photoV(y);
      if (u > 0.03 && u < 0.97 && v > 0.03 && v < 0.97) {
        const l = face.lum(u, v);
        const e = face.edge(u, v);
        // inner-face oval: eyes/nose/mouth/beard — dark tones become HOLES
        const inFace = Math.abs(u - 0.5) < 0.18 && v > 0.28 && v < 0.64;
        if (inFace && l < 0.30 && e < 0.25 && Math.random() < 0.75) return -1;
        // posterized tones — 4 bands read at particle resolution, raw
        // luminance does not
        faceMul = l < 0.22 ? 0.10 : l < 0.42 ? 0.42 : l < 0.68 ? 0.95 : 1.30;
        faceAdd = e * 0.7;             // feature lines sparkle
        rim *= 0.35;                   // silhouette glow must not fight the face
      }
    }
    let b = (0.10 + 0.55 * Math.pow(lambert, 1.25) + fill + rim) * faceMul + faceAdd;
    b = Math.min(1.35, b);
    const n = pos.length / 3;
    pos.push(x + (Math.random() - .5) * .4,
             y + (Math.random() - .5) * .4,
             z + (Math.random() - .5) * .4);
    const w = b > 0.88 ? Math.min(1, (b - 0.88) / 0.25) * 0.45 : 0;
    bri.push(b); wmi.push(w);
    col.push(b * (MODE_TINT.idle[0] * (1 - w) + w),
             b * (MODE_TINT.idle[1] * (1 - w) + w),
             b * (MODE_TINT.idle[2] * (1 - w) + w));
    // animation regions (head space): mouth band + eye band, front-facing
    if (y > -6.3 && y < -2.7 && Math.abs(x) < 5.2 && frontness > 0.45) mouthIdx.push(n);
    if (y > 2.2 && y < 5.4 && Math.abs(x) > 2.4 && Math.abs(x) < 7.2 && frontness > 0.45) eyeIdx.push(n);
    return n;
  }

  const smooth = (a, b, x) => {
    const s = Math.min(1, Math.max(0, (x - a) / (b - a)));
    return s * s * (3 - 2 * s);
  };

  // SKULL: one continuous deformed ellipsoid — the lower-front bulges into a
  // jaw/chin, the lower-back tapers slightly. A single surface = no seam
  // rings (the v3.0 two-ellipsoid head drew a glowing circle mid-face).
  const RX = 13.4, RY = 15.0, RZ = 14.6, CY = 7.5;
  const skullPoint = (sx, sy, sz) => {
    // jaw bulge: lower-front directions push outward, chin most of all
    const jaw = smooth(-0.15, -0.75, sy) * smooth(0.05, 0.75, sz) * 1.25;
    // slight cranial back-taper below the ears
    const taper = 1 - 0.16 * smooth(-0.2, -0.9, sy) * smooth(0.1, 0.9, -sz);
    const m = (1 + 0.24 * jaw) * taper;
    addPoint(sx * RX * m, CY + sy * RY * m, sz * RZ * m,
             sx / RX, sy / RY, sz / RZ, 'skull');
  };
  for (let k = 0; k < 20000; k++) {
    const th = Math.random() * Math.PI * 2;
    const ph = Math.acos(2 * Math.random() - 1);
    skullPoint(Math.sin(ph) * Math.cos(th), Math.cos(ph), Math.sin(ph) * Math.sin(th));
  }
  // extra FACE-resolution pass: double the point density on the front so the
  // projected features actually resolve at particle scale
  for (let k = 0; k < 14000; k++) {
    const th = Math.random() * Math.PI * 2;
    const ph = Math.acos(2 * Math.random() - 1);
    const sx = Math.sin(ph) * Math.cos(th), sy = Math.cos(ph), sz = Math.sin(ph) * Math.sin(th);
    if (sz < 0.25) continue;                       // front hemisphere only
    skullPoint(sx, sy, sz);
  }
  // neck — cylinder
  for (let k = 0; k < 2600; k++) {
    const a = Math.random() * Math.PI * 2;
    const y = -18 + Math.random() * 9.5;
    const r = 5.7;
    addPoint(Math.cos(a) * r, y, Math.sin(a) * r * 0.92 + 0.5,
             Math.cos(a), 0, Math.sin(a), 'neck');
  }
  // shoulders — wide flattened capsule, upper half only
  for (let k = 0; k < 9000; k++) {
    const th = Math.random() * Math.PI * 2;
    const ph = Math.acos(2 * Math.random() - 1);
    const sx = Math.sin(ph) * Math.cos(th), sy = Math.cos(ph), sz = Math.sin(ph) * Math.sin(th);
    if (sy <= 0.05) continue;
    addPoint(sx * 30, -23.5 + sy * 8.5, -1.5 + sz * 11,
             sx / 30, sy / 8.5, sz / 11, 'shoulders');
  }

  return { pos, col, bri, wmi, mouthIdx, eyeIdx };
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

    // mouth: native-timing lip-sync (band center y≈-4.5, half-height≈1.8)
    const posAttr = J.headGeo.attributes.position;
    const open = Math.min(1.6, J.level) * (J.mode === 'talking' ? 1 : 0.15);
    for (let k = 0; k < J.mouthIdx.length; k++) {
      const n = J.mouthIdx[k];
      const by = J.basePos[n * 3 + 1];
      const center = Math.max(0, 1 - Math.abs((by + 4.5) / 1.8));
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

  const face = await loadFaceMap();
  if (J.disposed) return;
  const { pos, col, bri, wmi, mouthIdx, eyeIdx } = buildBust(face);
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
  J.head.position.set(0, 4, 0);
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
