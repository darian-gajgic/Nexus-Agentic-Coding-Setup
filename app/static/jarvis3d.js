/* JARVIS 3D v7 — holographic head (2026-07-10).

   A violet point-lattice hologram in the style of the operator's reference
   clip: the three.js "facecap" head (model by Face Cap —
   bannaflak.com/face-cap; texture + baked clips stripped offline by
   scripts/build_facecap_hologram.py) with all 52 ARKit blendshapes,
   rendered three ways off ONE shared geometry:
     occluder  — near-black Mesh (+teeth): hides the far side → reads solid
     wireframe — faint additive violet lattice (the hologram "grid")
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
  utterQ: [], utterCtx: null,
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

// RGB multipliers on the violet hologram base (>1 amplifies into bloom)
const MODE_TINT = {
  idle:      [1.00, 0.95, 1.15],
  listening: [0.75, 1.15, 1.05],   // toward --accent-2 teal
  thinking:  [1.25, 1.10, 1.45],   // lit-up electric violet
  talking:   [1.10, 1.00, 1.30],
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
const HOLO_WIRE = 0x5b3fd6, HOLO_OCC = 0x05060f, HOLO_EYE = 0x0b0e1f,
      HOLO_GLINT = 0xb9a5ff, HOLO_BG = 0x05050c;
// the fit anchors on the EYES (the perceptual center of a face), not the
// bbox: facecap's cranium is deep and tall, so bbox-anchoring drops the
// face out of frame. Fitted: crown ≈ +13, mouth ≈ −12, neck cut ≈ −21
// (the dots fade out above the cut — floating-head hologram, like the
// reference clip; frame shows y ≈ −33..41 at z=0)
const HEAD_H = 44;          // world height of the fitted head bbox
const EYE_Y = 0, EYE_Z = 3;   // world anchor for the eye midpoint
const FADE_Y = [-23, -14];  // dot brightness fades to 0 toward the neck cut
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
  out.morphAttributes.position = geo.morphAttributes.position || [];
  out.morphTargetsRelative = true;
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
      // base hologram violet (#8a6bff); MODE_TINT multiplies on top
      uBase: { value: new THREE.Vector3(0.54, 0.42, 1.0) },
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

// the three renderables off one geometry, sharing ONE influences array —
// a single controller write per frame drives occluder + wireframe + dots
function assembleHologram(baseGeo, ptsGeo, dict) {
  const N = ptsGeo.attributes.position.count;
  const aSeed = new Float32Array(N), aSize = new Float32Array(N), aB = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    aSeed[i] = Math.random();
    aSize[i] = 0.55 + Math.random() * 0.4;
    aB[i] = 0.5 + Math.random() * 0.3;
  }
  ptsGeo.setAttribute('aSeed', new THREE.BufferAttribute(aSeed, 1));
  ptsGeo.setAttribute('aSize', new THREE.BufferAttribute(aSize, 1));
  ptsGeo.setAttribute('aB', new THREE.BufferAttribute(aB, 1));
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
  return { baseGeo, teethGeo, eyes, dict };
}

// degraded-but-visible stand-in if the GLB can't load: ellipsoid lattice
// (no morphs — the mouth/eye controllers no-op on the empty dict)
function buildFallbackHead() {
  const geo = new THREE.SphereGeometry(1, 40, 30);
  geo.scale(12.5, 16.5, 13.5);
  geo.translate(0, -12, 0);
  geo.computeVertexNormals();
  const h = assembleHologram(geo, deindexForPoints(geo), {});
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
        acol[o] = 0.14 * dimS; acol[o + 1] = 0.50 * dimS; acol[o + 2] = 0.62 * dimS;
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

    // mouth — amplitude envelope on jawOpen (fast attack / slow release,
    // sibilance narrows); the viseme timeline replaces this in P3
    const target = Math.min(1.6, J.level) * (J.mode === 'talking' ? 1 : 0.12)
      * (1 - 0.35 * J.levelHF);
    J.env += (target - J.env) * (target > J.env ? 0.55 : 0.10);
    put('jawOpen', 0.5 * J.env * (1 - 0.5 * J.levelHF));
    put('mouthStretch_L', 0.2 * J.levelHF * J.env);
    put('mouthStretch_R', 0.2 * J.levelHF * J.env);

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

    // mode postures (P4 adds the full saccade/fixation gaze machine)
    if (J.mode === 'thinking') put('browInnerUp', 0.35);
    if (listening) { put('eyeWide_L', 0.12); put('eyeWide_R', 0.12); }

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
    // the wireframe lattice follows the tint (#5b3fd6 × tint)
    J.holo.wire.material.color.setRGB(0.357 * tc.x, 0.247 * tc.y, 0.839 * tc.z);

    // the glints slip under the closing lid
    const gvis = (1 - lid) * (1 - lid);
    for (const g of J.glints) g.material.opacity = 0.45 * gvis;
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
          ap[o]     = anchor.x + off * 0.6 * px;
          ap[o + 1] = anchor.y + off * 0.6;
          ap[o + 2] = anchor.z + off * 0.6 * pz;
          ap[o + 3] = w[0] + off * 55 * px;
          ap[o + 4] = w[1] + off * 55;
          ap[o + 5] = w[2] + off * 55 * pz;
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
          opacity: 0.45, blending: THREE.AdditiveBlending, depthWrite: false,
        }));
        sp.scale.set(1.0, 1.0, 1);
        sp.position.copy(corneaOf(e.geo)).multiplyScalar(1.03);
        sp.renderOrder = 3;
        pv.add(sp);
        J.glints.push(sp);
        holo.eyePivots[k] = pv;
      }
      holo.lip = new A.LipsyncEn();
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
    J.head.material.uniforms.uScale.value =
      J.renderer.domElement.height / (2 * Math.tan(23 * D2R));
  };
  J.setPtScale();

  J.headGroup = new THREE.Group();
  J.headGroup.add(J.holo.occ, J.holo.wire, J.holo.pts);
  if (J.holo.teeth) J.headGroup.add(J.holo.teeth);
  if (J.holo.eyePivots) J.headGroup.add(J.holo.eyePivots.L, J.holo.eyePivots.R);
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
  J.utterQ = []; J.utterCtx = null;
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

window.Jarvis3D = { mount, dispose, setMode, setLevel, setAnimations, toggleGalaxy };
