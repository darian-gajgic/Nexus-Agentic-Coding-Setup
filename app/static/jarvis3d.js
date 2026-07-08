/* JARVIS 3D v2 — rendered particle AI avatar (inspiration: cyan point-cloud
   head with node streams flowing out of the back of the skull into the real
   memory galaxy behind it).

   - The head is a point cloud sampled from the avatar reference image:
     pixel luminance → point density/brightness, curved over an ellipsoid
     shell, so the face relief is REAL structure, not a texture. Renders like
     the memory galaxy (additive glow sprites), runs smooth (positions are
     static; only the mouth/jaw subset animates per frame).
   - Lip-sync is native-timing: app.js feeds setLevel() from an AnalyserNode
     on the ACTUAL playing TTS audio; mouth points open with amplitude.
   - The galaxy behind is the user's real mem0 galaxy (/api/memory3d data,
     same palette as memory3d.js); node streams (curves + traveling pulses)
     connect the back of the head to its clusters. Falls back to a procedural
     starfield when the galaxy is empty.
   - States: idle / listening / thinking / talking (color + motion).
   - setAnimations(false) freezes the RAF loop on a rendered frame (the
     animations on/off button); dispose() tears everything down.

   Pattern mirrors nexus3d.js/memory3d.js: lazy CDN import; the string
   "three" never appears in index.html (verify.sh gate).
   window.Jarvis3D = { mount, dispose, setMode, setLevel, setAnimations } */

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
  head: null, headGeo: null, backShell: null, galaxy: null, streams: [],
  pulses: [], mouthIdx: [], eyeIdx: [], basePos: null, baseCol: null,
  level: 0, mode: 'idle', t: 0, animOn: true, disposed: false,
  resizeObs: null,
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

/* ── Head: sample the reference face into a curved particle relief ── */
async function buildHead() {
  const img = await new Promise((res) => {
    const i = new Image();
    i.onload = () => res(i);
    i.onerror = () => res(null);
    i.src = '/static/avatar/reference.jpg';
  });
  const S = 110;                       // sample grid
  const cv = document.createElement('canvas');
  cv.width = cv.height = S;
  const g = cv.getContext('2d');
  if (img) g.drawImage(img, 0, 0, S, S);
  else {                               // fallback: soft radial "face" blob
    const rg = g.createRadialGradient(S / 2, S / 2, 6, S / 2, S / 2, S / 2);
    rg.addColorStop(0, '#cccccc'); rg.addColorStop(1, '#000000');
    g.fillStyle = rg; g.fillRect(0, 0, S, S);
  }
  const px = g.getImageData(0, 0, S, S).data;

  // luminance map with contrast stretch — a photo's face is tonally flat, so
  // raw luminance carves no features; stretching + edge boost makes eyes,
  // nose, mouth and hair POP as denser/brighter particles (the inspiration
  // look). Edges via simple gradient magnitude.
  const lumAt = new Float32Array(S * S);
  let lmin = 1, lmax = 0;
  for (let i = 0; i < S * S; i++) {
    const l = (px[i * 4] * 0.299 + px[i * 4 + 1] * 0.587 + px[i * 4 + 2] * 0.114) / 255;
    lumAt[i] = l;
    if (l < lmin) lmin = l;
    if (l > lmax) lmax = l;
  }
  const stretch = (l) => Math.min(1, Math.max(0, (l - lmin) / Math.max(0.01, lmax - lmin)));

  const pos = [], col = [], mouthIdx = [], eyeIdx = [];
  const W = 34, H = 44, DEPTH = 16;    // head proportions (world units)
  for (let y = 1; y < S - 1; y++) {
    for (let x = 1; x < S - 1; x++) {
      const i = y * S + x;
      const lum = stretch(lumAt[i]);
      const edge = Math.min(1, (Math.abs(lumAt[i + 1] - lumAt[i - 1])
        + Math.abs(lumAt[i + S] - lumAt[i - S])) * 3.4);
      const u = x / S - 0.5, v = 0.5 - y / S;      // -0.5..0.5
      const rr = (u * u) / 0.23 + (v * v) / 0.245; // ellipse mask (head-shaped)
      if (rr > 1.0) continue;
      // density: features (edges) always sample; flat areas by tone
      const density = Math.min(1, Math.pow(lum, 1.7) * 0.75 + edge * 0.9 + 0.05);
      if (Math.random() > density) continue;
      const wx = u * W, wy = v * H;
      const wz = Math.sqrt(Math.max(0, 1 - rr)) * DEPTH + lum * 4.2 + edge * 1.5;
      const n = pos.length / 3;
      pos.push(wx + (Math.random() - .5) * .45,
               wy + (Math.random() - .5) * .45,
               wz + (Math.random() - .5) * .45);
      const b = 0.28 + lum * 0.62 + edge * 0.5;
      col.push(b * MODE_TINT.idle[0], b * MODE_TINT.idle[1], b * MODE_TINT.idle[2]);
      // regions (in image space): mouth = lower-center, eyes = upper band
      if (v < -0.10 && v > -0.30 && Math.abs(u) < 0.16) mouthIdx.push(n);
      if (v > 0.02 && v < 0.14 && Math.abs(u) > 0.05 && Math.abs(u) < 0.26) eyeIdx.push(n);
    }
  }
  // sparse back-of-skull shell so the head reads as a volume from the side
  const back = [];
  for (let k = 0; k < 2600; k++) {
    const th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
    const sx = Math.sin(ph) * Math.cos(th), sy = Math.cos(ph), sz = Math.sin(ph) * Math.sin(th);
    if (sz > 0.15) continue;                       // front stays the face
    back.push(sx * W * 0.52, sy * H * 0.5, sz * DEPTH * 1.35);
  }
  return { pos, col, mouthIdx, eyeIdx, back };
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
  // procedural fallback: a few star clusters
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
    // galaxy swarms wide AROUND and behind the head (inspiration look)
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
    const start = new THREE.Vector3(Math.cos(a) * 10, 6 + Math.sin(a * 2) * 9, -10 - Math.random() * 6);
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
    // 2 pulses per stream
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

  if (J.head) {
    // breathing + idle sway (whole-group transforms — cheap)
    const breathe = 1 + Math.sin(t * 1.1) * 0.006;
    J.head.scale.set(1, breathe, 1);
    J.head.rotation.y = Math.sin(t * 0.22) * 0.055 + (J.mode === 'listening' ? 0.03 : 0);
    J.head.rotation.x = Math.sin(t * 0.15) * 0.02;
    if (J.backShell) {
      J.backShell.rotation.copy(J.head.rotation);
      J.backShell.scale.copy(J.head.scale);
    }

    // mouth: native-timing lip-sync — displace mouth points by audio level
    const posAttr = J.headGeo.attributes.position;
    const open = Math.min(1.6, J.level) * (J.mode === 'talking' ? 1 : 0.15);
    for (let k = 0; k < J.mouthIdx.length; k++) {
      const n = J.mouthIdx[k];
      const by = J.basePos[n * 3 + 1];
      const depth = (by + 13.2) / 8.8;             // deeper rows open more
      posAttr.array[n * 3 + 1] = by - open * 3.4 * Math.max(0, 1 - Math.abs(depth))
        - open * 0.7 * Math.random();
      posAttr.array[n * 3 + 2] = J.basePos[n * 3 + 2] - open * 1.1;
    }
    if (J.mouthIdx.length) posAttr.needsUpdate = true;

    // eye blink: fade eye points every few seconds; mode tint crossfade
    // (full-buffer writes only every 4th frame — they're the expensive part)
    const blink = (t % 4.7) > 4.55 ? 0.25 : 1;
    const colAttr = J.headGeo.attributes.color;
    if ((Math.round(t * 60) & 3) === 0) {
      const mix = 0.14;
      for (let n = 0; n < colAttr.count; n++) {
        const b = J.baseCol[n * 3] / MODE_TINT.idle[0];   // stored brightness
        colAttr.array[n * 3]     += (b * tint[0] - colAttr.array[n * 3]) * mix;
        colAttr.array[n * 3 + 1] += (b * tint[1] - colAttr.array[n * 3 + 1]) * mix;
        colAttr.array[n * 3 + 2] += (b * tint[2] - colAttr.array[n * 3 + 2]) * mix;
      }
      for (const n of J.eyeIdx) {
        colAttr.array[n * 3] *= blink; colAttr.array[n * 3 + 1] *= blink; colAttr.array[n * 3 + 2] *= blink;
      }
      colAttr.needsUpdate = true;
    }
    // talking glow
    J.head.material.size = 0.9 + Math.min(0.5, J.level * 0.35)
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

  const { pos, col, mouthIdx, eyeIdx, back } = await buildHead();
  if (J.disposed) return;
  J.basePos = Float32Array.from(pos);
  J.baseCol = Float32Array.from(col);
  J.mouthIdx = mouthIdx;
  J.eyeIdx = eyeIdx;
  J.headGeo = new THREE.BufferGeometry();
  J.headGeo.setAttribute('position', new THREE.BufferAttribute(Float32Array.from(pos), 3));
  J.headGeo.setAttribute('color', new THREE.BufferAttribute(Float32Array.from(col), 3));
  J.head = new THREE.Points(J.headGeo, new THREE.PointsMaterial({
    size: 0.9, map: glowTexture(), vertexColors: true, transparent: true,
    opacity: 0.95, depthWrite: false, blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
  }));
  J.head.position.set(0, 2, 0);
  J.scene.add(J.head);

  const bgeo = new THREE.BufferGeometry();
  bgeo.setAttribute('position', new THREE.BufferAttribute(Float32Array.from(back), 3));
  J.backShell = new THREE.Points(bgeo, new THREE.PointsMaterial({
    size: 0.7, map: glowTexture(), color: 0x1899b8, transparent: true,
    opacity: 0.35, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  J.backShell.position.copy(J.head.position);
  J.scene.add(J.backShell);

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
  if (J.renderer) {
    try {
      J.renderer.dispose();
      J.renderer.domElement.remove();
    } catch { }
  }
  for (const k of ['head', 'backShell', 'galaxy']) {
    if (J[k]) { try { J[k].geometry.dispose(); J[k].material.dispose(); } catch { } J[k] = null; }
  }
  J.streams = []; J.pulses = []; J.renderer = null; J.scene = null;
  J.headGeo = null; J.basePos = null; J.baseCol = null;
}

function setMode(mode) { J.mode = mode; }
function setLevel(v) { J.level = Math.max(0, v || 0); }
function setAnimations(on) {
  J.animOn = !!on;
  if (on && !J.raf && !J.disposed && J.renderer) tick();
  else if (!on && J.raf) { cancelAnimationFrame(J.raf); J.raf = null; }
}

window.Jarvis3D = { mount, dispose, setMode, setLevel, setAnimations };
