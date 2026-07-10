/* JARVIS 3D v7 — holographic head (2026-07-10).

   A cyan point-lattice hologram bust (head + neck/shoulder torso) in the style of the operator's reference
   clip: the three.js "facecap" head (model by Face Cap —
   bannaflak.com/face-cap; texture + baked clips stripped offline by
   scripts/build_facecap_hologram.py) with all 52 ARKit blendshapes,
   rendered three ways off ONE shared geometry:
     occluder  — near-black Mesh (+teeth): hides the far side → reads solid
     wireframe — faint additive cyan lattice (the hologram "grid")
     points    — morph-aware ShaderMaterial dots: fresnel rim, per-dot
                 twinkle, scanline shimmer, rare glitch flicker
   All three share ONE morphTargetInfluences array (r160 texture-based
   morphs work for Points + ShaderMaterial; the renderer binds the morph
   texture per object automatically). Eyes are separate meshes under
   rotatable pivot groups — gaze rotates the pivots, the glints ride along.
   Post: EffectComposer → UnrealBloomPass (half-res) → OutputPass.

   Per-frame animation writes into the shared influences array:
     blink   — measured human dynamics (Trutoiu et al., ACM TAP 2011)
     visemes — text-aligned Oculus viseme timeline (vendor/lipsync-en.mjs,
               MIT) stretched over the REAL per-sentence audio window and
               gated by the live RMS envelope (speak()/stopSpeech() API)
     gaze    — saccade/fixation state machine, camera-dominant
     idle    — breathing + subtle sway; the head always FACES THE USER
   Fallback: an ellipsoid lattice bust if the GLB can't load.

   Scene layers, front to back: head (z≈0, face at +z) → the REAL memory
   galaxy (z≈-7800, 50× node spacing) → static matrix backdrop (z≈-11500).
   100 links run from the back of the skull to the most-linked memory
   nodes; toggleGalaxy() flies the camera through the head into the galaxy
   for orbit / hover / click-to-edit (onMemorySelect), like the Memory tab.

   window.Jarvis3D = { mount, dispose, setMode, setLevel, setAnimations,
                       toggleGalaxy, speak, stopSpeech }
   Lazy CDN three.js import — the string "three" never appears in
   index.html (verify.sh gate). Vendored addons: static/vendor/threejsm/. */

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
  head: null, headGroup: null, holo: null, composer: null, bloom: null,
  glints: [], level: 0, mode: 'idle', t: 0,
  animOn: true, disposed: false, resizeObs: null,
  pointer: { x: 0, y: 0 }, pointerHandler: null,
  // research-grounded animation state (docs/JARVIS-VOICE.md §0)
  env: 0, levelHF: 0, blinkAt: 2, blinkT: -1,
  utterQ: [], utterCtx: null, gaze: null,
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

// RGB multipliers on the cyan hologram base (>1 amplifies into bloom)
const MODE_TINT = {
  idle:      [1.00, 0.98, 1.05],
  listening: [0.85, 1.12, 0.92],   // toward --accent-2 teal
  thinking:  [1.30, 1.15, 1.30],   // lit-up electric cyan
  talking:   [1.15, 1.05, 1.15],   // cyan-white
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

/* ═══════════ hologram head (facecap GLB, ARKit-52 morphs) ═══════════ */

const D2R = Math.PI / 180;
const HOLO_WIRE = 0x1595b0, HOLO_OCC = 0x05060f, HOLO_EYE = 0x0b0e1f,
      HOLO_GLINT = 0x9df5ff, HOLO_BG = 0x05050c;
// the fit anchors on the EYES (the perceptual center of a face), not the
// bbox: facecap's cranium is deep and tall, so bbox-anchoring drops the
// face out of frame. The head sits ON a procedural torso (neck+shoulders)
// that rises from the frame bottom and dissolves at the lower edge
// (frame shows y ≈ −33..41 at z=0)
const HEAD_H = 53;          // world height of the fitted head bbox
const EYE_Y = -2, EYE_Z = 3;  // world anchor for the eye midpoint
const FADE_Y = [-40, -33];  // the bust dissolves at the frame bottom edge
const POINT_SUBDIV = true;  // midpoint-subdivide the dot lattice (2.7k → ~10.4k)

let addonsPromise = null;
function loadAddons() {
  if (!addonsPromise) {
    addonsPromise = (async () => {
      const V = '?v=1';
      const [gl, mo, ec, rp, ub, op, lip] = await Promise.all([
        import('/static/vendor/threejsm/loaders/GLTFLoader.js' + V),
        import('/static/vendor/threejsm/libs/meshopt_decoder.module.js' + V),
        import('/static/vendor/threejsm/postprocessing/EffectComposer.js' + V),
        import('/static/vendor/threejsm/postprocessing/RenderPass.js' + V),
        import('/static/vendor/threejsm/postprocessing/UnrealBloomPass.js' + V),
        import('/static/vendor/threejsm/postprocessing/OutputPass.js' + V),
        import('/static/vendor/lipsync/lipsync-en.mjs' + V),
      ]);
      return {
        GLTFLoader: gl.GLTFLoader, MeshoptDecoder: mo.MeshoptDecoder,
        EffectComposer: ec.EffectComposer, RenderPass: rp.RenderPass,
        UnrealBloomPass: ub.UnrealBloomPass, OutputPass: op.OutputPass,
        LipsyncEn: lip.LipsyncEn,
      };
    })().catch((e) => { addonsPromise = null; throw e; });
  }
  return addonsPromise;
}

// bake a mesh's world transform (+ the scene fit) into plain Float32
// geometry: quantized/meshopt attributes → clean floats. Morph POSITION
// deltas transform by the linear part; morph NORMAL deltas are dropped —
// halves the morph texture, and dot fresnel doesn't need morphed normals.
function bakeGeometry(mesh, fit) {
  const src = mesh.geometry;
  const M = new THREE.Matrix4().multiplyMatrices(fit, mesh.matrixWorld);
  const L = new THREE.Matrix3().setFromMatrix4(M);
  const NM = new THREE.Matrix3().getNormalMatrix(M);
  const n = src.attributes.position.count;
  const v = new THREE.Vector3();
  const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    v.fromBufferAttribute(src.attributes.position, i).applyMatrix4(M);
    pos[i * 3] = v.x; pos[i * 3 + 1] = v.y; pos[i * 3 + 2] = v.z;
    if (src.attributes.normal) {
      v.fromBufferAttribute(src.attributes.normal, i).applyMatrix3(NM).normalize();
      nor[i * 3] = v.x; nor[i * 3 + 1] = v.y; nor[i * 3 + 2] = v.z;
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
  if (src.index) geo.setIndex(Array.from(src.index.array));
  const morphs = src.morphAttributes.position || [];
  if (morphs.length) {
    geo.morphAttributes.position = morphs.map((m) => {
      const d = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) {
        v.fromBufferAttribute(m, i).applyMatrix3(L);
        d[i * 3] = v.x; d[i * 3 + 1] = v.y; d[i * 3 + 2] = v.z;
      }
      return new THREE.BufferAttribute(d, 3);
    });
    geo.morphTargetsRelative = true;
  }
  return geo;
}

// one midpoint subdivision for the dot lattice only: one new vertex per
// unique edge; morph deltas midpoint-average (exact for linear morphs)
function subdivideForPoints(geo) {
  const idx = geo.getIndex().array;
  const n0 = geo.attributes.position.count;
  const edges = new Map();
  for (let i = 0; i < idx.length; i += 3) {
    const tri = [idx[i], idx[i + 1], idx[i + 2]];
    for (let e = 0; e < 3; e++) {
      const a = tri[e], b = tri[(e + 1) % 3];
      const k = a < b ? a * n0 + b : b * n0 + a;
      if (!edges.has(k)) edges.set(k, [a, b]);
    }
  }
  const pairs = [...edges.values()];
  const n = n0 + pairs.length;
  // density compensation: dots in dense topology regions (lips, eyes, nose)
  // stack additively and blow out white — dim by local mean edge length
  const pp = geo.attributes.position.array;
  const acc = new Float32Array(n0), cnt = new Float32Array(n0);
  const lens = new Float32Array(pairs.length);
  pairs.forEach(([a, b], e) => {
    const l = Math.hypot(pp[a * 3] - pp[b * 3], pp[a * 3 + 1] - pp[b * 3 + 1],
                         pp[a * 3 + 2] - pp[b * 3 + 2]);
    lens[e] = l; acc[a] += l; cnt[a]++; acc[b] += l; cnt[b]++;
  });
  const med = Float32Array.from(lens).sort()[lens.length >> 1] || 1;
  const dens = (l) => Math.min(1.2, Math.max(0.3, Math.pow(l / med, 0.8)));
  const aD = new Float32Array(n);
  for (let i = 0; i < n0; i++) aD[i] = dens(acc[i] / (cnt[i] || 1));
  pairs.forEach((_, e) => { aD[n0 + e] = dens(lens[e]); });
  const avg3 = (src) => {
    const out = new Float32Array(n * 3);
    out.set(src.array.subarray(0, n0 * 3));
    pairs.forEach(([a, b], e) => {
      const o = (n0 + e) * 3;
      for (let c = 0; c < 3; c++) {
        out[o + c] = (src.array[a * 3 + c] + src.array[b * 3 + c]) / 2;
      }
    });
    return out;
  };
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', new THREE.BufferAttribute(avg3(geo.attributes.position), 3));
  const nn = avg3(geo.attributes.normal);
  for (let i = 0; i < n; i++) {
    const o = i * 3, l = Math.hypot(nn[o], nn[o + 1], nn[o + 2]) || 1;
    nn[o] /= l; nn[o + 1] /= l; nn[o + 2] /= l;
  }
  out.setAttribute('normal', new THREE.BufferAttribute(nn, 3));
  out.setAttribute('aD', new THREE.BufferAttribute(aD, 1));
  out.morphAttributes.position = (geo.morphAttributes.position || []).map(
    (m) => new THREE.BufferAttribute(avg3(m), 3));
  out.morphTargetsRelative = true;
  return out;
}

// Points draw per index entry when an index exists (shared verts would
// stack additively) — share the attributes, drop the index
function deindexForPoints(geo) {
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', geo.attributes.position);
  out.setAttribute('normal', geo.attributes.normal);
  const mp = geo.morphAttributes.position;
  if (mp && mp.length) {   // an EMPTY morph array still trips USE_MORPHTARGETS
    out.morphAttributes.position = mp;
    out.morphTargetsRelative = true;
  }
  return out;
}

// front-most vertex of a pivot-local eye = the cornea (face is +z)
function corneaOf(geo) {
  const p = geo.attributes.position;
  let best = 0, bz = -1e9;
  for (let i = 0; i < p.count; i++) {
    const z = p.getZ(i);
    if (z > bz) { bz = z; best = i; }
  }
  return new THREE.Vector3(p.getX(best), p.getY(best), p.getZ(best));
}

function hologramPointsMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, depthTest: true,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uTime: { value: 0 }, uSize: { value: 1.05 }, uScale: { value: 1000 },
      uOpacity: { value: 0.8 }, uGlitch: { value: 1 },
      // base hologram cyan (the pre-v7 avatar color); MODE_TINT multiplies
      uBase: { value: new THREE.Vector3(0.30, 0.85, 1.0) },
      uTint: { value: new THREE.Vector3(...MODE_TINT.idle) },
      uFade: { value: new THREE.Vector2(FADE_Y[0], FADE_Y[1]) },
    },
    vertexShader: `
      #include <morphtarget_pars_vertex>
      attribute float aSeed; attribute float aSize; attribute float aB;
      uniform float uTime, uSize, uScale, uGlitch;
      uniform vec3 uBase, uTint;
      uniform vec2 uFade;
      varying vec3 vColor;
      void main() {
        vec3 transformed = vec3(position);
        #include <morphtarget_vertex>
        // organic micro-drift: each dot breathes on its own seed
        vec3 p = transformed + 0.05 * vec3(sin(uTime * 1.1 + aSeed * 17.0),
                                           sin(uTime * 1.4 + aSeed * 29.0),
                                           sin(uTime * 0.9 + aSeed * 41.0));
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        vec3 vN = normalize(normalMatrix * normal);
        float rim = pow(1.0 - abs(dot(vN, normalize(-mv.xyz))), 2.0);
        float tw = 1.0 + 0.22 * sin(uTime * (3.1 + aSeed * 6.3) + aSeed * 40.0);
        float scan = 1.0 + 0.12 * sin(p.y * 1.4 - uTime * 2.2);
        // the head dissolves toward the neck cut — floating hologram
        float fade = smoothstep(uFade.x, uFade.y, p.y);
        vColor = aB * (0.28 + 0.62 * rim) * tw * scan * fade * uGlitch * uBase * uTint;
        gl_PointSize = uSize * aSize * (uScale / -mv.z);   // manual attenuation
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `
      uniform float uOpacity;
      varying vec3 vColor;
      void main() {
        float r = length(gl_PointCoord - 0.5) * 2.0;
        if (r > 1.0) discard;
        float core = smoothstep(0.45, 0.0, r);              // bright node core
        float halo = pow(max(0.0, 1.0 - r), 2.4) * 0.35;    // soft glow skirt
        gl_FragColor = vec4(vColor * (core + halo), (core + halo) * uOpacity);
      }`,
  });
}

// per-dot attributes for the hologram point shader (dim = brightness scale)
function dressPoints(ptsGeo, dim) {
  const N = ptsGeo.attributes.position.count;
  const dA = ptsGeo.attributes.aD;   // density compensation (subdivided path)
  const aSeed = new Float32Array(N), aSize = new Float32Array(N), aB = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    aSeed[i] = Math.random();
    aSize[i] = 0.55 + Math.random() * 0.4;
    aB[i] = (0.5 + Math.random() * 0.3) * (dA ? dA.array[i] : 1) * (dim || 1);
  }
  if (dA) ptsGeo.deleteAttribute('aD');
  ptsGeo.setAttribute('aSeed', new THREE.BufferAttribute(aSeed, 1));
  ptsGeo.setAttribute('aSize', new THREE.BufferAttribute(aSize, 1));
  ptsGeo.setAttribute('aB', new THREE.BufferAttribute(aB, 1));
}

// the three renderables off one geometry, sharing ONE influences array —
// a single controller write per frame drives occluder + wireframe + dots
function assembleHologram(baseGeo, ptsGeo, dict) {
  dressPoints(ptsGeo, 1);
  const occ = new THREE.Mesh(baseGeo, new THREE.MeshBasicMaterial({
    color: HOLO_OCC, polygonOffset: true, polygonOffsetFactor: 2, polygonOffsetUnits: 2,
  }));
  occ.scale.setScalar(0.985);
  occ.renderOrder = 0;
  const wire = new THREE.Mesh(baseGeo, new THREE.MeshBasicMaterial({
    color: HOLO_WIRE, wireframe: true, transparent: true, opacity: 0.13,
    blending: THREE.AdditiveBlending, depthWrite: false,
  }));
  wire.renderOrder = 1;
  const pts = new THREE.Points(ptsGeo, hologramPointsMaterial());
  pts.renderOrder = 2;
  const influences = new Float32Array((baseGeo.morphAttributes.position || []).length);
  for (const o of [occ, wire, pts]) o.morphTargetInfluences = influences;
  return { occ, wire, pts, influences, dict: dict || {} };
}

async function buildHologramHead(A) {
  const loader = new A.GLTFLoader();
  loader.setMeshoptDecoder(A.MeshoptDecoder);
  const gltf = await loader.loadAsync('/static/avatar/facecap_hologram.glb');
  const root = gltf.scene;
  root.updateMatrixWorld(true);
  // gltfpack layout: named holder nodes wrap unnamed mesh children
  const meshOf = (name) => {
    let m = null;
    root.getObjectByName(name).traverse((o) => { if (o.isMesh && !m) m = o; });
    return m;
  };
  const headMesh = meshOf('head'), teethMesh = meshOf('teeth');
  const pivots = { L: root.getObjectByName('grp_eyeLeft'),
                   R: root.getObjectByName('grp_eyeRight') };
  const dict = { ...(headMesh.morphTargetDictionary || {}) };
  if (dict.jawOpen === undefined || dict.eyeBlink_L === undefined) {
    throw new Error('facecap morph target names missing');
  }

  // fit: uniform scale to HEAD_H, then place the eye midpoint at the world
  // anchor (EYE_Y/EYE_Z), face toward +z (the camera)
  headMesh.geometry.computeBoundingBox();
  const bb = headMesh.geometry.boundingBox.clone().applyMatrix4(headMesh.matrixWorld);
  const ctr = bb.getCenter(new THREE.Vector3());
  const eyeMid = new THREE.Vector3().setFromMatrixPosition(pivots.L.matrixWorld)
    .add(new THREE.Vector3().setFromMatrixPosition(pivots.R.matrixWorld))
    .multiplyScalar(0.5);
  const s = HEAD_H / Math.max(1e-6, bb.max.y - bb.min.y);
  const flip = eyeMid.z < ctr.z;      // the eyes sit at the front of the skull
  const R = flip ? new THREE.Matrix4().makeRotationY(Math.PI) : new THREE.Matrix4();
  const em = eyeMid.clone().applyMatrix4(R).multiplyScalar(s);
  const fit = new THREE.Matrix4()
    .makeTranslation(-em.x, EYE_Y - em.y, EYE_Z - em.z)
    .multiply(new THREE.Matrix4().makeScale(s, s, s))
    .multiply(R);

  const baseGeo = bakeGeometry(headMesh, fit);
  const teethGeo = bakeGeometry(teethMesh, fit);
  const eyes = {};
  for (const k of ['L', 'R']) {
    const pv = pivots[k];
    const mesh = meshOf(k === 'L' ? 'eyeLeft' : 'eyeRight');
    const pvPos = new THREE.Vector3().setFromMatrixPosition(pv.matrixWorld).applyMatrix4(fit);
    const toLocal = new THREE.Matrix4()
      .makeTranslation(-pvPos.x, -pvPos.y, -pvPos.z).multiply(fit);
    eyes[k] = { geo: bakeGeometry(mesh, toLocal), pos: pvPos };
  }
  const halfW = (bb.max.x - bb.min.x) / 2 * s;   // head half-width, world
  return { baseGeo, teethGeo, eyes, dict, halfW };
}

/* ── VisemeController: text-aligned lip sync ──
   app.js registers a LIVE utterance record per spoken sentence via
   speak({text,start,end,done}, audioCtx): start/end are AudioContext-clock
   seconds (or performance-clock when audioCtx is null, e.g. the HTTP WAV
   fallback) and .end keeps growing as PCM chunks are scheduled. Each frame
   the Oculus-viseme timeline (vendor lipsync-en, relative units) is
   stretched over the REAL audio window — it self-corrects as chunks land —
   and evaluated with attack/release envelopes, then mapped to ARKit
   blendshapes and gated by the live RMS envelope so true pauses close the
   mouth even if the text timing drifts. */
const VISEME_ARKIT = {
  sil: {},
  aa: { jawOpen: 0.50 },
  E:  { jawOpen: 0.22, mouthStretch_L: 0.30, mouthStretch_R: 0.30,
        mouthSmile_L: 0.12, mouthSmile_R: 0.12 },
  I:  { jawOpen: 0.12, mouthSmile_L: 0.30, mouthSmile_R: 0.30,
        mouthStretch_L: 0.20, mouthStretch_R: 0.20 },
  O:  { jawOpen: 0.40, mouthFunnel: 0.50 },
  U:  { jawOpen: 0.12, mouthPucker: 0.60, mouthFunnel: 0.20 },
  PP: { mouthClose: 0.70, mouthPress_L: 0.40, mouthPress_R: 0.40, jawOpen: 0.08 },
  FF: { mouthRollLower: 0.45, mouthShrugUpper: 0.15, jawOpen: 0.08 },
  TH: { tongueOut: 0.35, jawOpen: 0.14 },
  DD: { jawOpen: 0.15, mouthShrugUpper: 0.10 },
  kk: { jawOpen: 0.14, mouthShrugLower: 0.08 },
  CH: { mouthFunnel: 0.35, mouthPucker: 0.25, mouthShrugUpper: 0.20, jawOpen: 0.10 },
  SS: { jawOpen: 0.06, mouthStretch_L: 0.25, mouthStretch_R: 0.25,
        mouthSmile_L: 0.15, mouthSmile_R: 0.15, mouthPress_L: 0.15, mouthPress_R: 0.15 },
  nn: { jawOpen: 0.12, mouthPress_L: 0.10, mouthPress_R: 0.10 },
  RR: { jawOpen: 0.12, mouthPucker: 0.25, mouthFunnel: 0.15 },
};
const VIS_ATTACK = 0.05, VIS_RELEASE = 0.12;   // seconds (co-articulation)
const ss01 = (x) => {
  const c = Math.min(1, Math.max(0, x));
  return c * c * (3 - 2 * c);
};

function utterClock(rec) {
  return rec.ctx ? rec.ctx.currentTime : performance.now() / 1000;
}

// returns true when a timed utterance drove the mouth this frame
function updateVisemes(put) {
  const q = J.utterQ;
  if (!q.length || !J.holo || !J.holo.lip) return false;
  while (q.length) {          // drop finished sentences
    const r = q[0];
    if (r.done && (r.start < 0 || utterClock(r) > r.end + 0.3)) q.shift();
    else break;
  }
  const rec = q.find((r) => r.start >= 0 && utterClock(r) >= r.start - VIS_ATTACK
    && (!r.done || utterClock(r) <= r.end + VIS_RELEASE + 0.1));
  if (!rec) return false;
  if (!rec.vt) {
    try {
      const lp = J.holo.lip;
      const vt = lp.wordsToVisemes(lp.preProcessText(rec.text));
      const n = (vt.visemes || []).length;
      rec.vt = n ? { v: vt.visemes, ts: vt.times, ds: vt.durations,
                     total: Math.max(1e-3, vt.times[n - 1] + vt.durations[n - 1]) }
                 : { v: [] };
    } catch { rec.vt = { v: [] }; }
  }
  const vt = rec.vt;
  if (!vt.v.length || !(rec.end > rec.start)) return false;
  const now = utterClock(rec);
  const scale = (rec.end - rec.start) / vt.total;
  // live-audio gate: analyser-driven when on the WS graph, full otherwise
  const gate = rec.ctx ? 0.25 + 0.75 * Math.min(1, J.env) : 1;
  let any = false;
  for (let k = 0; k < vt.v.length; k++) {
    const a = rec.start + vt.ts[k] * scale;
    const b = a + vt.ds[k] * scale;
    if (now < a - VIS_ATTACK) break;         // times sorted — rest is future
    if (now > b + VIS_RELEASE) continue;
    let w;
    if (now < a) w = ss01((now - (a - VIS_ATTACK)) / VIS_ATTACK);
    else if (now <= b) w = 1;
    else w = 1 - ss01((now - b) / VIS_RELEASE);
    const m = VISEME_ARKIT[vt.v[k]];
    if (!m || w <= 0) continue;
    any = true;
    for (const name in m) put(name, m[name] * w * gate);
  }
  return any;
}

/* ── GazeController: saccade/fixation state machine ──
   Camera-dominant (~75% of fixations lock onto the camera and then TRACK
   it — the camera rides the pointer, so the eyes subtly follow the user),
   with occasional offset fixations; 60–90 ms saccades with slight
   overshoot, microsaccadic jitter during fixations, and mode postures
   (thinking → up-aside, listening → locked on camera). Drives the eye
   pivot groups (the glints ride along) + eyeLook* morphs as lid follow. */
function updateGaze(t, put) {
  if (!J.holo || !J.holo.eyePivots) return;
  if (!J.gaze) {
    J.gaze = { yaw: 0, pitch: 0, fromY: 0, fromP: 0, tY: 0, tP: 0,
               lock: 'cam', until: 0, sacT: -1, sacDur: 0.07 };
  }
  const g = J.gaze;
  const thinking = J.mode === 'thinking', listening = J.mode === 'listening';
  if (t >= g.until) {           // pick the next fixation
    let ty, tp, dur;
    if (thinking) {             // gaze drifts up-aside while working
      g.lock = 'off';
      ty = (Math.random() < 0.5 ? -1 : 1) * (5 + Math.random() * 4) * D2R;
      tp = -(6 + Math.random() * 5) * D2R;   // negative rotation.x = up
      dur = 0.7 + Math.random() * 1.2;
    } else if (listening || Math.random() < 0.75) {
      g.lock = 'cam';           // target refreshed every frame below
      ty = g.tY; tp = g.tP;
      dur = listening ? 1.5 + Math.random() * 1.5 : 0.8 + Math.random() * 1.7;
    } else {
      g.lock = 'off';           // brief natural glance away
      ty = (Math.random() * 2 - 1) * 8 * D2R;
      tp = (Math.random() * 2 - 1) * 5 * D2R;
      dur = 0.4 + Math.random() * 0.8;
    }
    g.fromY = g.yaw; g.fromP = g.pitch;
    g.tY = ty; g.tP = tp;
    g.sacT = t; g.sacDur = 0.06 + Math.random() * 0.03;
    g.until = t + dur;
    // blink probability doubles around saccade onset
    if (J.blinkT < 0 && Math.random() < 0.15) J.blinkAt = Math.min(J.blinkAt, t + 0.04);
  }
  if (g.lock === 'cam' && J.camera && !J.galaxyMode) {
    // track the (pointer-driven) camera; compensate the head sway so the
    // fixation holds like a real one. Eye midpoint sits at ≈ (0, EYE_Y, EYE_Z).
    const dz = Math.max(10, J.camera.position.z - EYE_Z);
    g.tY = Math.atan2(J.camera.position.x, dz) - J.headGroup.rotation.y;
    g.tP = -Math.atan2(J.camera.position.y - EYE_Y, dz) - J.headGroup.rotation.x;
  }
  let e = 1;
  if (g.sacT >= 0) {
    const k = Math.min(1, (t - g.sacT) / g.sacDur);
    e = ss01(k) * (1 + 0.05 * Math.sin(k * Math.PI));   // ~5% overshoot
    if (k >= 1) g.sacT = -1;
  }
  g.yaw = g.fromY + (g.tY - g.fromY) * e;
  g.pitch = g.fromP + (g.tP - g.fromP) * e;
  // microsaccadic jitter during fixation (sub-degree)
  const my = Math.sin(t * 13.7) * 0.15 * D2R;
  const mp = Math.sin(t * 17.3 + 1.0) * 0.12 * D2R;
  const yaw = Math.max(-0.22, Math.min(0.22, g.yaw + my));
  const pitch = Math.max(-0.20, Math.min(0.20, g.pitch + mp));
  J.holo.eyePivots.L.rotation.set(pitch, yaw, 0);
  J.holo.eyePivots.R.rotation.set(pitch, yaw, 0);
  // eyeLook* morphs at partial weight — the lids/socket follow the gaze
  const h = yaw / (12 * D2R), v = -pitch / (12 * D2R);
  if (v > 0) { put('eyeLookUp_L', 0.6 * Math.min(1, v)); put('eyeLookUp_R', 0.6 * Math.min(1, v)); }
  else { put('eyeLookDown_L', 0.6 * Math.min(1, -v)); put('eyeLookDown_R', 0.6 * Math.min(1, -v)); }
  if (h > 0) { put('eyeLookIn_L', 0.6 * Math.min(1, h)); put('eyeLookOut_R', 0.6 * Math.min(1, h)); }
  else { put('eyeLookOut_L', 0.6 * Math.min(1, -h)); put('eyeLookIn_R', 0.6 * Math.min(1, -h)); }
}

/* ── procedural torso: neck + shoulders under the head (hologram bust) ──
   Parametric grids in the old sculpt's proportions, sized off the fitted
   head half-width; each surface renders as occluder + wireframe lattice +
   dots like the head (static — no morphs). The dots share the head's fade
   so the bust dissolves at the frame bottom. */
function torsoSurfaceGeo(fn, nu, nv) {
  const pos = [];
  for (let i = 0; i <= nu; i++) {
    for (let j = 0; j <= nv; j++) pos.push(...fn(i / nu, j / nv));
  }
  const idx = [];
  for (let i = 0; i < nu; i++) {
    for (let j = 0; j < nv; j++) {
      const a = i * (nv + 1) + j, b = a + 1, c = a + nv + 1, d = c + 1;
      idx.push(a, b, c, b, d, c);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(Float32Array.from(pos), 3));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  return geo;
}

function buildTorso(halfW, occMat, wireMat) {
  const zc = -0.15 * halfW;           // torso axis sits behind the face
  const neck = (u, v) => {            // top rim tucks INSIDE the jaw
    const a = u * 2 * Math.PI;        // silhouette, widening downward
    const rx = (0.33 + 0.23 * v) * halfW, rz = (0.32 + 0.19 * v) * halfW;
    return [Math.sin(a) * rx, EYE_Y - 9 - v * 17, Math.cos(a) * rz + zc];
  };
  const shoulder = (u, v) => {        // superellipse slab, trapezius slope
    const a = u * 2 * Math.PI;
    const sl = ss01(v * 2);
    const hw = (0.62 + 1.13 * sl) * halfW;
    const dp = (0.50 + 0.22 * sl) * halfW;
    const sA = Math.sin(a), cA = Math.cos(a);
    const r = 1 / Math.max(1e-4,
      Math.pow(Math.pow(Math.abs(sA / hw), 3) + Math.pow(Math.abs(cA / dp), 3), 1 / 3));
    return [sA * r, EYE_Y - 22 - v * 19, cA * r * 0.92 + zc];
  };
  const parts = [], ptsMat = hologramPointsMaterial();
  for (const { fn, nu, nv, wnu, wnv } of [
    { fn: neck, nu: 30, nv: 20, wnu: 22, wnv: 12 },
    { fn: shoulder, nu: 72, nv: 30, wnu: 48, wnv: 16 },
  ]) {
    // dots on a DENSE grid (the sparse torso read as a hole next to the
    // 10k-dot head); the wireframe lattice stays coarser for the grid look
    const dotGeo = torsoSurfaceGeo(fn, nu, nv);
    const wireGeo = torsoSurfaceGeo(fn, wnu, wnv);
    const occ = new THREE.Mesh(wireGeo, occMat);
    occ.renderOrder = 0;
    const wire = new THREE.Mesh(wireGeo, wireMat);
    wire.renderOrder = 1;
    const pg = deindexForPoints(dotGeo);
    dressPoints(pg, 1.15);
    const pts = new THREE.Points(pg, ptsMat);
    pts.renderOrder = 2;
    pts.userData.dotGeo = dotGeo;   // disposed with the part
    parts.push(occ, wire, pts);
  }
  return { parts, ptsMat };
}

// degraded-but-visible stand-in if the GLB can't load: ellipsoid lattice
// (no morphs — the mouth/eye controllers no-op on the empty dict)
function buildFallbackHead() {
  const geo = new THREE.SphereGeometry(1, 40, 30);
  geo.scale(12.5, 16.5, 13.5);
  geo.translate(0, -12, 0);
  geo.computeVertexNormals();
  const h = assembleHologram(geo, deindexForPoints(geo), {});
  h.torso = buildTorso(12.5, h.occ.material, h.wire.material);
  console.warn('Jarvis3D: procedural fallback head active (GLB unavailable)');
  return h;
}

/* ═══════ memory galaxy (the memory-tab 3D map, embedded) + matrix ═══════ */
const CYAN_FAMILY = [0x22d3ee, 0x67e8f9, 0x0ea5b7];
const DISTINCT_HUES = [0xa3e635, 0xf43f5e, 0xf59e0b, 0x8b5cf6, 0xec4899,
                       0x60a5fa, 0x2dd4bf, 0xfb7185, 0xfacc15, 0x34d399,
                       0xc084fc, 0xf97316];

// world layout, front to back: bust (z≈0) → memory galaxy → static matrix.
// The galaxy cloud spans ±6000 (tab ±120 × GALAXY_SCALE) around its center;
// its front edge stays far behind the bust and it fills the sky above.
const GALAXY_CENTER = { x: 0, y: 1540, z: -7800 };
const GALAXY_SCALE = 50;     // 5× the previous 10× node spacing (operator ask)
const GALAXY_SPIN = 0.0011;  // rad/frame — the tab's idle auto-orbit rate
const MATRIX_CENTER = { x: 0, y: 30, z: -16500 };
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
  s.scale.set(c.width / 0.6, c.height / 0.6, 1);   // sized for the 50× spread
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
    pos[i * 3] = (n.x || 0) * 24;
    pos[i * 3 + 1] = (n.y || 0) * 16;
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
    size: 70, map: glowTexture(), vertexColors: true, transparent: true,
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
    map: glowTexture(), size: 9, vertexColors: true, transparent: true,
    opacity: 0.95, depthWrite: false, sizeAttenuation: true }));
  mem.group.add(mem.cores);
  const glowGeo = new THREE.BufferGeometry();
  glowGeo.setAttribute('position', coreGeo.getAttribute('position'));
  glowGeo.setAttribute('color', coreGeo.getAttribute('color'));
  mem.glows = new THREE.Points(glowGeo, new THREE.PointsMaterial({
    map: glowTexture(), size: 56, vertexColors: true, transparent: true,
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
    s.position.set(cl.x * S, cl.y * S + 260, cl.z * S);
    mem.group.add(s);
    mem.labels.push(s);
  });

  // ambient electrical pulses along the links (the tab's signature motion)
  if (links.length) {
    const pulseGeo = new THREE.SphereGeometry(16, 8, 8);
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
    const thinkGeo = new THREE.SphereGeometry(30, 8, 8);
    for (let i = 0; i < 40; i++) {
      const p = new THREE.Mesh(thinkGeo, new THREE.MeshBasicMaterial({
        color: 0x9df5ff, transparent: true, opacity: 0,   // thinking = cyan
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

  // 100 links: back of the skull → the top nodes (endpoints track per frame).
  // Each link is THREE strands (center + two offset satellites): WebGL caps
  // LineBasicMaterial at 1px, so the 3× thickness ask is a 3-strand beam.
  if (mem.top.length) {
    const nT = mem.top.length;
    const apos = new Float32Array(nT * 18);
    const acol = new Float32Array(nT * 18);
    mem.top.forEach((ni, k) => {
      const c = new THREE.Color(mem.nodeColor(nodes[ni])).multiplyScalar(0.85);
      for (let s = 0; s < 3; s++) {
        const dimS = s === 1 ? 1 : 0.55;         // soft beam edges
        const o = k * 18 + s * 6;
        // BOTH ends carry the memory node's identity hue (head end dimmer)
        acol[o] = c.r * 0.6 * dimS; acol[o + 1] = c.g * 0.6 * dimS; acol[o + 2] = c.b * 0.6 * dimS;
        acol[o + 3] = c.r * dimS; acol[o + 4] = c.g * dimS; acol[o + 5] = c.b * dimS;
      }
    });
    const aGeo = new THREE.BufferGeometry();
    aGeo.setAttribute('position', new THREE.BufferAttribute(apos, 3));
    aGeo.setAttribute('color', new THREE.BufferAttribute(acol, 3));
    mem.avatarLinks = new THREE.LineSegments(aGeo, new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.16,
      blending: THREE.AdditiveBlending, depthWrite: false }));
    mem.avatarLinks.frustumCulled = false; // endpoints rewritten every frame
    J.scene.add(mem.avatarLinks);

    // pooled signals riding those links into the head (idle trickle → flood)
    for (let i = 0; i < 80; i++) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({
        map: glowTexture(), color: 0x9df5ff, transparent: true, opacity: 0,
        blending: THREE.AdditiveBlending, depthWrite: false }));
      sp.scale.set(12, 12, 1);
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
  c.dist = Math.max(500, Math.min(18000, c.dist));
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
  const nearHead = new THREE.Vector3(0, -10, -60);
  const midField = new THREE.Vector3(0, -300, -3500);
  J.fly = {
    t: 0, dur: entering ? 3.0 : 2.0,
    fromPos: J.camera.position.clone(),
    fromLook: (J.lookCur || new THREE.Vector3(0, 4, 0)).clone(),
    via1: entering ? nearHead : midField,   // head-side control stays by the bust
    via2: entering ? midField : nearHead,
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
      // cubic bezier threaded through the bust — the camera pierces the
      // particle head, dives under the link fan, then climbs to the galaxy
      J.fly.t += dt / J.fly.dur;
      const k = Math.min(1, J.fly.t);
      const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      const q = 1 - e;
      const A = J.fly.fromPos, B1 = J.fly.via1, B2 = J.fly.via2, C = J.fly.toPos;
      const w0 = q * q * q, w1 = 3 * q * q * e, w2 = 3 * q * e * e, w3 = e * e * e;
      J.camera.position.set(
        w0 * A.x + w1 * B1.x + w2 * B2.x + w3 * C.x,
        w0 * A.y + w1 * B1.y + w2 * B2.y + w3 * C.y,
        w0 * A.z + w1 * B1.z + w2 * B2.z + w3 * C.z);
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

  if (J.headGroup && J.holo) {
    // ── IdleController: breathing + subtle sway; the head FACES THE USER
    // (no turntable — operator decision 2026-07-09) ──
    const listening = J.mode === 'listening';
    J.headGroup.rotation.y = Math.sin(t * 0.44) * 0.05;
    J.headGroup.rotation.x = Math.sin(t * 0.28) * 0.02
      + (J.mode === 'talking' ? Math.sin(t * 3.1) * 0.01 * Math.min(1, J.env) : 0);
    J.headGroup.rotation.z += ((listening ? 0.05 : 0) - J.headGroup.rotation.z) * 0.04;
    J.headGroup.scale.y = 1 + Math.sin(t * 1.38) * 0.006;

    // every controller writes into the ONE shared influences array
    const inf = J.holo.influences, dict = J.holo.dict;
    inf.fill(0);
    const put = (name, v) => {
      const ix = dict[name];
      if (ix !== undefined) inf[ix] = Math.max(inf[ix], Math.min(1, v));
    };

    // mouth — text-aligned visemes when a timed utterance is active; pure
    // amplitude fallback otherwise (mic mouthing, unknown text). The RMS
    // envelope keeps its fast-attack/slow-release shape either way.
    const target = Math.min(1.6, J.level) * (J.mode === 'talking' ? 1 : 0.12)
      * (1 - 0.35 * J.levelHF);
    J.env += (target - J.env) * (target > J.env ? 0.55 : 0.10);
    if (!updateVisemes(put)) {
      put('jawOpen', 0.5 * J.env);
      put('mouthStretch_L', 0.2 * J.levelHF * J.env);
      put('mouthStretch_R', 0.2 * J.levelHF * J.env);
    }
    // sibilance narrows the aperture on s/sh/f regardless of the driver
    const jx = dict.jawOpen;
    if (jx !== undefined) inf[jx] *= 1 - 0.45 * J.levelHF;

    // blink — measured human dynamics (Trutoiu et al., Disney Research /
    // ACM TAP 2011): ~80ms accelerating close, brief closure, ~220ms
    // asymptotic reopen, randomized 2–6s apart, 12% double blinks
    if (J.blinkT < 0 && t >= J.blinkAt) J.blinkT = t;
    let lid = 0;
    if (J.blinkT >= 0) {
      const x = t - J.blinkT;
      if (x < 0.08) lid = Math.pow(x / 0.08, 1.7);
      else if (x < 0.12) lid = 1;
      else if (x < 0.34) lid = Math.pow(1 - (x - 0.12) / 0.22, 2.6);
      else {
        J.blinkT = -1;
        J.blinkAt = t + (Math.random() < 0.12 ? 0.25 : 2 + Math.random() * 4);
      }
    }
    put('eyeBlink_L', lid);
    put('eyeBlink_R', lid);

    // gaze — saccade/fixation machine (pivots + eyeLook lid-follow)
    updateGaze(t, put);

    // mode postures
    if (J.mode === 'thinking') put('browInnerUp', 0.35);
    if (listening) { put('eyeWide_L', 0.12); put('eyeWide_R', 0.12); }
    if (J.mode === 'talking') put('browInnerUp', 0.12 * Math.min(1, J.env));

    // uniforms: time, glitch flicker, mode tint ease, size pulse
    const u = J.head.material.uniforms;
    u.uTime.value = t;
    const fr = (x => x - Math.floor(x))(Math.sin(Math.floor(t * 3) * 91.7) * 437.585);
    u.uGlitch.value = fr > 0.992 ? 0.85 : 1;
    const tc = u.uTint.value;
    tc.x += (tint[0] - tc.x) * 0.05;
    tc.y += (tint[1] - tc.y) * 0.05;
    tc.z += (tint[2] - tc.z) * 0.05;
    u.uSize.value = 1.05 + Math.min(0.35, J.level * 0.25)
      + (J.mode === 'thinking' ? Math.sin(t * 5) * 0.07 : 0);
    // the wireframe lattice follows the tint (dim cyan × tint)
    J.holo.wire.material.color.setRGB(0.082 * tc.x, 0.513 * tc.y, 0.578 * tc.z);
    // the torso dots ride the same uniforms (separate material — no morphs)
    if (J.holo.torso) {
      const tm = J.holo.torso.ptsMat.uniforms;
      tm.uTime.value = t;
      tm.uGlitch.value = u.uGlitch.value;
      tm.uSize.value = u.uSize.value;
      tm.uTint.value.copy(tc);
    }

    // the glints slip under the closing lid
    const gvis = (1 - lid) * (1 - lid);
    for (const g of J.glints) g.material.opacity = 0.6 * gvis;
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
      const anchor = _tmpV.set(0, -7, -8);   // inside the skull, at the back
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
        // side strands spread perpendicular to the link (in xz), narrow at
        // the head, wide at the node — a converging beam, not 3 loose wires
        let px = -(w[2] - anchor.z), pz = (w[0] - anchor.x);
        const pl = Math.hypot(px, pz) || 1;
        px /= pl; pz /= pl;
        for (let s = 0; s < 3; s++) {
          const off = s - 1;                     // −1, 0, +1
          const o = k * 18 + s * 6;
          ap[o]     = anchor.x + off * 0.9 * px;   // ×1.5 beam thickness
          ap[o + 1] = anchor.y + off * 0.9;
          ap[o + 2] = anchor.z + off * 0.9 * pz;
          ap[o + 3] = w[0] + off * 82 * px;
          ap[o + 4] = w[1] + off * 82;
          ap[o + 5] = w[2] + off * 82 * pz;
        }
      });
      mem.avatarLinks.geometry.attributes.position.needsUpdate = true;
      mem.avatarLinks.material.opacity +=
        ((thinking ? 0.30 : 0.16) - mem.avatarLinks.material.opacity) * 0.06;

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

  if (J.composer) J.composer.render();
  else J.renderer.render(J.scene, J.camera);
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
  // dist 5800 vs the ±6000 cloud ≈ the tab's default framing at 50× scale
  J.gCam = { theta: Math.PI / 2, phi: 1.35, dist: 5800 };
  _tmpV = new THREE.Vector3();
  const w = container.clientWidth || 800, h = container.clientHeight || 600;
  J.scene = new THREE.Scene();
  // solid background: UnrealBloomPass artifacts over transparent canvases —
  // and it matches the stage's CSS vignette base tone anyway
  J.scene.background = new THREE.Color(HOLO_BG);
  // fog light enough that the galaxy (~7800) and matrix (~11500) stay visible
  J.scene.fog = new THREE.FogExp2(0x05050c, 0.00006);
  J.camera = new THREE.PerspectiveCamera(46, w / h, 0.1, 16000);
  J.camera.position.set(0, 4, 88);
  J.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  J.renderer.setSize(w, h);
  J.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
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

  // ── hologram head: facecap GLB (model: Face Cap, bannaflak.com) — dark
  // occluder + additive wireframe lattice + morph-aware glowing dots; an
  // ellipsoid lattice keeps the stage alive if the GLB fails ──
  let A = null;
  try { A = await loadAddons(); } catch (e) { console.warn('Jarvis3D: addons unavailable', e); }
  if (J.disposed) return;
  if (A) {
    try {
      const built = await buildHologramHead(A);
      if (J.disposed) return;
      const ptsGeo = POINT_SUBDIV ? subdivideForPoints(built.baseGeo)
                                  : deindexForPoints(built.baseGeo);
      const holo = assembleHologram(built.baseGeo, ptsGeo, built.dict);
      holo.teeth = new THREE.Mesh(built.teethGeo, holo.occ.material);
      holo.teeth.renderOrder = 0;
      holo.eyePivots = {};
      for (const k of ['L', 'R']) {
        const e = built.eyes[k];
        const pv = new THREE.Group();
        pv.position.copy(e.pos);
        const em = new THREE.Mesh(e.geo, new THREE.MeshBasicMaterial({ color: HOLO_EYE }));
        em.renderOrder = 0;
        pv.add(em);
        // glint at the cornea (front-most vertex, pivot-local) — it rides
        // the pivot, so the eyes visibly move even as a dot lattice
        const sp = new THREE.Sprite(new THREE.SpriteMaterial({
          map: glowTexture(), color: HOLO_GLINT, transparent: true,
          opacity: 0.6, blending: THREE.AdditiveBlending, depthWrite: false,
        }));
        sp.scale.set(1.5, 1.5, 1);
        sp.position.copy(corneaOf(e.geo)).multiplyScalar(1.03);
        sp.renderOrder = 3;
        pv.add(sp);
        J.glints.push(sp);
        holo.eyePivots[k] = pv;
      }
      holo.lip = new A.LipsyncEn();
      // the head sits ON a torso rising from the frame bottom (like the
      // pre-v7 bust); occluder + wireframe share the head materials
      holo.torso = buildTorso(built.halfW, holo.occ.material, holo.wire.material);
      J.holo = holo;
    } catch (e) {
      console.warn('Jarvis3D: hologram head failed — using fallback lattice', e);
    }
  }
  if (J.disposed) return;
  if (!J.holo) J.holo = buildFallbackHead();
  J.env = 0; J.levelHF = 0;
  J.blinkAt = J.t + 1.5 + Math.random() * 3;
  J.blinkT = -1;
  J.head = J.holo.pts;   // carries the shared uniforms (uTint/uTime/uSize)
  // manual size attenuation (ShaderMaterial loses sizeAttenuation): points
  // are sized in device pixels from the drawing-buffer height and the fov
  J.setPtScale = () => {
    if (!J.head || !J.renderer) return;
    const sc = J.renderer.domElement.height / (2 * Math.tan(23 * D2R));
    J.head.material.uniforms.uScale.value = sc;
    if (J.holo && J.holo.torso) J.holo.torso.ptsMat.uniforms.uScale.value = sc;
  };
  J.setPtScale();

  J.headGroup = new THREE.Group();
  J.headGroup.add(J.holo.occ, J.holo.wire, J.holo.pts);
  if (J.holo.teeth) J.headGroup.add(J.holo.teeth);
  if (J.holo.eyePivots) J.headGroup.add(J.holo.eyePivots.L, J.holo.eyePivots.R);
  if (J.holo.torso) J.headGroup.add(...J.holo.torso.parts);
  J.scene.add(J.headGroup);

  // post: bloom halo — RenderPass → UnrealBloomPass (half-res) → OutputPass.
  // MSAA render target: composer passes bypass the canvas antialias flag.
  if (A) {
    try {
      const rt = new THREE.WebGLRenderTarget(w, h, {
        type: THREE.HalfFloatType, samples: 4,
      });
      J.composer = new A.EffectComposer(J.renderer, rt);
      J.composer.addPass(new A.RenderPass(J.scene, J.camera));
      // threshold high: the additive dot pile easily sums past 1.0 — bloom
      // only the hottest cores or the whole head blows out to white
      J.bloom = new A.UnrealBloomPass(new THREE.Vector2(w / 2, h / 2), 0.45, 0.30, 0.85);
      J.composer.addPass(J.bloom);
      J.composer.addPass(new A.OutputPass());
      J.composer.setPixelRatio(J.renderer.getPixelRatio());
      J.composer.setSize(w, h);
    } catch (e) {
      console.warn('Jarvis3D: composer unavailable — direct render', e);
      J.composer = null; J.bloom = null;
    }
  }

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
    if (J.composer) J.composer.setSize(W, H);
    if (J.setPtScale) J.setPtScale();
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
  if (J.composer) { try { J.composer.dispose(); } catch { } J.composer = null; J.bloom = null; }
  if (J.holo) {
    // base geometry dispose also frees the r160 morph texture (WeakMap +
    // dispose listener); the eye/teeth/point geometries are their own
    try {
      const seen = new Set();
      for (const o of [J.holo.occ, J.holo.wire, J.holo.pts, J.holo.teeth]) {
        if (!o || seen.has(o.geometry)) continue;
        seen.add(o.geometry);
        o.geometry.dispose(); o.material.dispose();
      }
      for (const k of ['L', 'R']) {
        const pv = J.holo.eyePivots && J.holo.eyePivots[k];
        if (pv) pv.traverse((o) => {
          try { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); } catch { }
        });
      }
      if (J.holo.torso) {
        for (const o of J.holo.torso.parts) { try { o.geometry.dispose(); } catch { } }
        try { J.holo.torso.ptsMat.dispose(); } catch { }
      }
    } catch { }
    J.holo = null;
  }
  J.head = null;
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
  for (const g of J.glints) { try { g.material.dispose(); } catch { } }
  J.glints = []; J.headGroup = null;
  J.renderer = null; J.scene = null;
  J.utterQ = []; J.utterCtx = null; J.gaze = null;
}

function setMode(mode) {
  // leaving THINKING = the answer is forming → memory floods into the head
  if (J.mode === 'thinking' && mode !== 'thinking') J.mem.burst = 2.4;
  J.mode = mode;
}
// v = amplitude; hf (optional 0..1) = sibilance share of the spectrum —
// high-frequency sounds narrow the mouth instead of dropping the jaw
function setLevel(v, hf) {
  J.level = Math.max(0, v || 0);
  J.levelHF = Math.max(0, Math.min(1, hf || 0));
}
function setAnimations(on) {
  J.animOn = !!on;
  if (on && !J.raf && !J.disposed && J.renderer) tick();
  else if (!on && J.raf) { cancelAnimationFrame(J.raf); J.raf = null; }
}

// register a LIVE utterance record {text, start, end, done} for viseme lip
// sync — the caller keeps mutating start/end as audio chunks are scheduled.
// audioCtx = the WebAudio context whose clock start/end live on (null →
// performance.now()/1000, used by the HTTP WAV fallback).
function speak(rec, audioCtx) {
  if (!rec || !rec.text) return;
  rec.ctx = audioCtx || null;
  if (!J.utterQ.includes(rec)) J.utterQ.push(rec);
}
// barge-in / stop: drop every queued utterance (the mouth eases shut via
// the RMS envelope, which collapses when the audio stops)
function stopSpeech() {
  J.utterQ = [];
}

window.Jarvis3D = { mount, dispose, setMode, setLevel, setAnimations,
                    toggleGalaxy, speak, stopSpeech };
