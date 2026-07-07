/* NEXUS 3D — agent constellation rendered with Three.js (loaded lazily from CDN).
   Exposed as window.Nexus3D = { mount, update, dispose }.
   Three.js must never be referenced from index.html (verify.sh gate) — it is
   dynamically imported here, and the whole module degrades gracefully offline. */

let THREE = null;
let threePromise = null;

const STATUS_COLORS = {
  running: 0x4ade80,
  busy: 0xfbbf24,
  idle: 0x64748b,
  stopped: 0xf87171,
  crashed: 0xf97316,
  cost_capped: 0xef4444,
  stuck: 0xeab308,
};

const ctx = {
  renderer: null, scene: null, camera: null, raf: null,
  core: null, coreWire: null, halo: null, group: null,
  nodes: [], links: null, stars: null, canvas: null,
  resizeObs: null, t: 0, agentKey: '',
};

function loadThree() {
  if (!threePromise) {
    threePromise = import('https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js')
      .then((m) => { THREE = m; return m; })
      .catch((e) => { console.warn('Nexus3D: three.js unavailable', e); threePromise = null; return null; });
  }
  return threePromise;
}

function agentSignature(agents) {
  return (agents || []).map(a => `${a.id}:${a.status}`).join('|');
}

function buildNodes(agents) {
  // Remove previous nodes + links
  for (const n of ctx.nodes) { ctx.group.remove(n.mesh); n.mesh.geometry.dispose(); n.mesh.material.dispose(); }
  ctx.nodes = [];
  if (ctx.links) { ctx.group.remove(ctx.links); ctx.links.geometry.dispose(); ctx.links.material.dispose(); ctx.links = null; }

  const n = (agents || []).length;
  if (!n) return;

  const linkPts = [];
  const linkCols = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const a = agents[i];
    const color = STATUS_COLORS[a.status] ?? 0x8888a0;
    // Fibonacci sphere distribution, flattened into a wide band
    const y = (1 - (i / Math.max(1, n - 1)) * 2) * 0.55;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const th = golden * i;
    const R = 3.1;
    const pos = [Math.cos(th) * r * R, y * R * 0.85, Math.sin(th) * r * R];

    const geo = new THREE.SphereGeometry(a.status === 'running' || a.status === 'busy' ? 0.17 : 0.12, 16, 16);
    const mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95 });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(pos[0], pos[1], pos[2]);
    ctx.group.add(mesh);
    ctx.nodes.push({ mesh, base: pos, phase: i * 1.7, status: a.status });

    linkPts.push(0, 0, 0, pos[0], pos[1], pos[2]);
    const c = new THREE.Color(color);
    linkCols.push(0.49, 0.36, 1.0, c.r, c.g, c.b);
  }

  const lg = new THREE.BufferGeometry();
  lg.setAttribute('position', new THREE.Float32BufferAttribute(linkPts, 3));
  lg.setAttribute('color', new THREE.Float32BufferAttribute(linkCols, 3));
  const lm = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.28 });
  ctx.links = new THREE.LineSegments(lg, lm);
  ctx.group.add(ctx.links);
}

async function mount(canvas, agents) {
  const three = await loadThree();
  if (!three || !canvas || !canvas.isConnected) return false;
  dispose();
  ctx.canvas = canvas;

  try {
    ctx.renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  } catch (e) {
    console.warn('Nexus3D: WebGL unavailable', e);
    return false;
  }
  ctx.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  ctx.scene = new THREE.Scene();
  ctx.camera = new THREE.PerspectiveCamera(48, 2, 0.1, 100);
  ctx.camera.position.set(0, 0.6, 7.4);
  ctx.camera.lookAt(0, 0, 0);

  ctx.group = new THREE.Group();
  ctx.scene.add(ctx.group);

  // Core: wireframe icosahedron + faint inner glow shell
  ctx.coreWire = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.35, 1),
    new THREE.MeshBasicMaterial({ color: 0x7c5cff, wireframe: true, transparent: true, opacity: 0.7 })
  );
  ctx.core = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.05, 2),
    new THREE.MeshBasicMaterial({ color: 0x5eead4, transparent: true, opacity: 0.06 })
  );
  ctx.halo = new THREE.Mesh(
    new THREE.SphereGeometry(1.7, 24, 24),
    new THREE.MeshBasicMaterial({ color: 0x7c5cff, transparent: true, opacity: 0.035, side: THREE.BackSide })
  );
  ctx.group.add(ctx.coreWire, ctx.core, ctx.halo);

  // Starfield
  const starPts = [];
  for (let i = 0; i < 500; i++) {
    const r = 9 + Math.random() * 14;
    const t = Math.random() * Math.PI * 2;
    const p = Math.acos(2 * Math.random() - 1);
    starPts.push(r * Math.sin(p) * Math.cos(t), r * Math.cos(p) * 0.6, r * Math.sin(p) * Math.sin(t));
  }
  const sg = new THREE.BufferGeometry();
  sg.setAttribute('position', new THREE.Float32BufferAttribute(starPts, 3));
  ctx.stars = new THREE.Points(sg, new THREE.PointsMaterial({ color: 0x8888c0, size: 0.035, transparent: true, opacity: 0.7 }));
  ctx.scene.add(ctx.stars);

  buildNodes(agents);
  ctx.agentKey = agentSignature(agents);

  const resize = () => {
    if (!ctx.renderer || !ctx.canvas) return;
    const w = ctx.canvas.clientWidth, h = ctx.canvas.clientHeight;
    if (!w || !h) return;
    ctx.renderer.setSize(w, h, false);
    ctx.camera.aspect = w / h;
    ctx.camera.updateProjectionMatrix();
  };
  ctx.resizeObs = new ResizeObserver(resize);
  ctx.resizeObs.observe(canvas);
  resize();

  const animate = () => {
    if (!ctx.renderer) return;
    ctx.raf = requestAnimationFrame(animate);
    ctx.t += 0.005;
    ctx.group.rotation.y = ctx.t * 0.55;
    ctx.coreWire.rotation.x = ctx.t * 0.8;
    ctx.coreWire.rotation.z = ctx.t * 0.35;
    const pulse = 1 + Math.sin(ctx.t * 2.4) * 0.045;
    ctx.coreWire.scale.setScalar(pulse);
    ctx.halo.scale.setScalar(1 + Math.sin(ctx.t * 1.6) * 0.08);
    for (const n of ctx.nodes) {
      n.mesh.position.y = n.base[1] + Math.sin(ctx.t * 2 + n.phase) * 0.12;
      if (n.status === 'running' || n.status === 'busy') {
        n.mesh.material.opacity = 0.75 + Math.sin(ctx.t * 3 + n.phase) * 0.25;
      }
    }
    ctx.stars.rotation.y = -ctx.t * 0.05;
    ctx.renderer.render(ctx.scene, ctx.camera);
  };
  animate();
  return true;
}

function update(agents) {
  if (!ctx.renderer || !THREE) return;
  const key = agentSignature(agents);
  if (key === ctx.agentKey) return;
  ctx.agentKey = key;
  buildNodes(agents);
}

function dispose() {
  if (ctx.raf) cancelAnimationFrame(ctx.raf);
  ctx.raf = null;
  if (ctx.resizeObs) { ctx.resizeObs.disconnect(); ctx.resizeObs = null; }
  if (ctx.scene) {
    ctx.scene.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) { (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => m.dispose()); }
    });
  }
  if (ctx.renderer) { ctx.renderer.dispose(); ctx.renderer = null; }
  ctx.scene = null; ctx.camera = null; ctx.group = null;
  ctx.nodes = []; ctx.links = null; ctx.stars = null;
  ctx.core = null; ctx.coreWire = null; ctx.halo = null;
  ctx.canvas = null; ctx.agentKey = '';
}

window.Nexus3D = { mount, update, dispose };
