/* JARVIS 3D — holographic stage around the neural avatar.
   The identity face stays the real Wav2Lip lip-sync video (it IS the user's
   likeness, driven by real TTS audio); this module builds the living room
   around it: a holo-projector base, particle energy field and state-driven
   ring system that reacts to the REAL microphone level while listening and
   the REAL speech amplitude while talking.
   window.Jarvis3D = { mount, setMode, setLevel, dispose }.
   Same lazy-CDN pattern as nexus3d/memory3d — the string "three" never
   appears in index.html. */

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
  renderer: null, scene: null, camera: null, raf: null, canvas: null,
  container: null, resizeObs: null, t: 0,
  mode: 'idle', level: 0, smooth: 0,
  dust: null, rings: [], base: null, baseGlow: null, orbiters: null,
  waves: [], beams: null,
};

const MODE_COLORS = {
  idle: 0x22d3ee,
  listening: 0x5eead4,
  thinking: 0x7c5cff,
  talking: 0x9df5ff,
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

function buildScene() {
  // ambient dust field (the "room")
  const n = 700;
  const pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const r = 30 + Math.random() * 160;
    const th = Math.random() * Math.PI * 2;
    pos[i * 3] = Math.cos(th) * r;
    pos[i * 3 + 1] = (Math.random() - 0.5) * 160;
    pos[i * 3 + 2] = Math.sin(th) * r;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  J.dust = new THREE.Points(geo, new THREE.PointsMaterial({
    map: glowTexture(), color: 0x3d3d6b, size: 1.6, transparent: true,
    opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false }));
  J.scene.add(J.dust);

  // holo-projector base: stacked rotating rings under the avatar
  for (let i = 0; i < 3; i++) {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(26 + i * 7, 0.28 - i * 0.05, 8, 96),
      new THREE.MeshBasicMaterial({
        color: 0x22d3ee, transparent: true, opacity: 0.5 - i * 0.13,
        blending: THREE.AdditiveBlending, depthWrite: false }));
    ring.rotation.x = Math.PI / 2;
    ring.position.y = -34 - i * 2.4;
    J.scene.add(ring);
    J.rings.push(ring);
  }
  const baseGeo = new THREE.CircleGeometry(24, 64);
  J.baseGlow = new THREE.Mesh(baseGeo, new THREE.MeshBasicMaterial({
    map: glowTexture(), color: 0x22d3ee, transparent: true, opacity: 0.30,
    blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
  J.baseGlow.rotation.x = -Math.PI / 2;
  J.baseGlow.position.y = -33;
  J.scene.add(J.baseGlow);

  // thinking orbiters: particles that swirl faster while processing
  const on = 90;
  const opos = new Float32Array(on * 3);
  const oseed = [];
  for (let i = 0; i < on; i++) {
    oseed.push({ r: 34 + Math.random() * 14, th: Math.random() * Math.PI * 2,
                 y: (Math.random() - 0.5) * 46, sp: 0.4 + Math.random() * 0.8 });
    opos[i * 3] = 0; opos[i * 3 + 1] = 0; opos[i * 3 + 2] = 0;
  }
  const ogeo = new THREE.BufferGeometry();
  ogeo.setAttribute('position', new THREE.BufferAttribute(opos, 3));
  J.orbiters = new THREE.Points(ogeo, new THREE.PointsMaterial({
    map: glowTexture(), color: 0x7c5cff, size: 2.6, transparent: true,
    opacity: 0.0, blending: THREE.AdditiveBlending, depthWrite: false }));
  J.orbiters.userData.seed = oseed;
  J.scene.add(J.orbiters);

  // expanding wave rings (spawned while listening/talking)
  for (let i = 0; i < 6; i++) {
    const w = new THREE.Mesh(
      new THREE.TorusGeometry(1, 0.22, 6, 80),
      new THREE.MeshBasicMaterial({
        color: 0x5eead4, transparent: true, opacity: 0,
        blending: THREE.AdditiveBlending, depthWrite: false }));
    w.rotation.x = Math.PI / 2;
    w.position.y = -33;
    w.userData = { active: false, r: 1 };
    J.scene.add(w);
    J.waves.push(w);
  }

  // light shafts rising from the base
  const shaft = new THREE.Mesh(
    new THREE.CylinderGeometry(24, 27, 70, 48, 1, true),
    new THREE.MeshBasicMaterial({
      color: 0x22d3ee, transparent: true, opacity: 0.045,
      blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
  shaft.position.y = 0;
  J.scene.add(shaft);
  J.beams = shaft;
}

let _waveTimer = 0;
function spawnWave(strength) {
  const w = J.waves.find((x) => !x.userData.active);
  if (!w) return;
  w.userData = { active: true, r: 24, str: strength };
  w.material.color.setHex(MODE_COLORS[J.mode] || 0x22d3ee);
}

function animate() {
  J.raf = requestAnimationFrame(animate);
  J.t += 0.016;
  const target = MODE_COLORS[J.mode] || MODE_COLORS.idle;

  // smoothed live level (mic while listening, speech amplitude while talking)
  J.smooth += (J.level - J.smooth) * 0.25;
  const energy = J.mode === 'idle' ? 0.12 : 0.25 + J.smooth * 1.6;

  // base rings: rotate, tint toward the mode color, pulse with energy
  J.rings.forEach((r, i) => {
    r.rotation.z += (0.002 + i * 0.0013) * (J.mode === 'thinking' ? 3 : 1);
    r.material.color.lerp(new THREE.Color(target), 0.06);
    r.scale.setScalar(1 + Math.sin(J.t * 1.8 + i) * 0.012 + J.smooth * 0.10);
  });
  if (J.baseGlow) {
    J.baseGlow.material.color.lerp(new THREE.Color(target), 0.06);
    J.baseGlow.material.opacity = 0.22 + energy * 0.25;
  }
  if (J.beams) {
    J.beams.material.color.lerp(new THREE.Color(target), 0.06);
    J.beams.material.opacity = 0.03 + energy * 0.05;
    J.beams.rotation.y += 0.0016;
  }

  // dust drifts; speeds up subtly with energy
  if (J.dust) J.dust.rotation.y += 0.0004 + energy * 0.0012;

  // thinking orbiters fade in and swirl
  if (J.orbiters) {
    const want = J.mode === 'thinking' ? 0.9 : 0.0;
    J.orbiters.material.opacity += (want - J.orbiters.material.opacity) * 0.06;
    if (J.orbiters.material.opacity > 0.02) {
      const p = J.orbiters.geometry.attributes.position.array;
      J.orbiters.userData.seed.forEach((s, i) => {
        s.th += 0.016 * s.sp * (J.mode === 'thinking' ? 2.2 : 0.5);
        p[i * 3] = Math.cos(s.th) * s.r;
        p[i * 3 + 1] = s.y + Math.sin(J.t * 0.9 + i) * 3;
        p[i * 3 + 2] = Math.sin(s.th) * s.r;
      });
      J.orbiters.geometry.attributes.position.needsUpdate = true;
    }
  }

  // waves: spawn on voice energy, expand and fade
  _waveTimer -= 0.016;
  if ((J.mode === 'listening' || J.mode === 'talking') && J.smooth > 0.12 && _waveTimer <= 0) {
    spawnWave(J.smooth);
    _waveTimer = 0.22;
  }
  J.waves.forEach((w) => {
    if (!w.userData.active) { w.material.opacity = 0; return; }
    w.userData.r += 1.6 + (w.userData.str || 0) * 2.4;
    const r = w.userData.r;
    w.scale.setScalar(r);
    w.material.opacity = Math.max(0, 0.5 * (1 - (r - 24) / 90));
    if (r > 114) w.userData.active = false;
  });

  // gentle camera float
  J.camera.position.x = Math.sin(J.t * 0.12) * 6;
  J.camera.position.y = 6 + Math.sin(J.t * 0.2) * 2.5;
  J.camera.lookAt(0, 0, 0);
  J.renderer.render(J.scene, J.camera);
}

async function mount(container) {
  dispose();
  const three = await loadThree();
  if (!three || !container || !container.isConnected) return;
  J.container = container;
  J.scene = new THREE.Scene();
  J.camera = new THREE.PerspectiveCamera(50, 1, 0.1, 1200);
  J.camera.position.set(0, 6, 118);
  J.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  J.renderer.setClearColor(0x000000, 0);
  J.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  J.canvas = J.renderer.domElement;
  J.canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none';
  container.appendChild(J.canvas);
  buildScene();
  const size = () => {
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;
    J.renderer.setSize(w, h, false);
    J.camera.aspect = w / h;
    J.camera.updateProjectionMatrix();
  };
  size();
  J.resizeObs = new ResizeObserver(size);
  J.resizeObs.observe(container);
  animate();
}

function setMode(mode) { J.mode = mode || 'idle'; }
function setLevel(v) { J.level = Math.max(0, Math.min(1, v || 0)); }

function dispose() {
  if (J.raf) cancelAnimationFrame(J.raf);
  if (J.resizeObs) J.resizeObs.disconnect();
  if (J.renderer) {
    J.renderer.dispose();
    if (J.canvas && J.canvas.parentNode) J.canvas.parentNode.removeChild(J.canvas);
  }
  Object.assign(J, {
    renderer: null, scene: null, camera: null, raf: null, canvas: null,
    container: null, resizeObs: null, mode: 'idle', level: 0, smooth: 0,
    dust: null, rings: [], base: null, baseGlow: null, orbiters: null,
    waves: [], beams: null,
  });
}

window.Jarvis3D = { mount, setMode, setLevel, dispose };
