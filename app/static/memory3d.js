/* MEMORY 3D — the mem0 vector space rendered as a navigable neural room.
   Every node sits at its REAL semantic position (PCA of the 768-dim qdrant
   embeddings, computed server-side); lines are real cosine-similarity links,
   colored by strength; pulses travel the links like electrical signals.
   Pattern mirrors nexus3d.js: lazy CDN import, window.Memory3D = {mount,dispose},
   the string "three" never appears in index.html (verify.sh gate). */

let THREE = null;
let threePromise = null;

function loadThree() {
  if (!threePromise) {
    threePromise = import('https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js')
      .then((m) => { THREE = m; return m; })
      .catch((e) => { console.warn('Memory3D: engine unavailable', e); threePromise = null; return null; });
  }
  return threePromise;
}

const M = {
  renderer: null, scene: null, camera: null, raf: null, canvas: null,
  group: null, nodeMeshes: [], linkLines: null, pulses: [], stars: null,
  grid: null, data: null, panel: null, hoverId: -1, raycaster: null,
  pointer: null, resizeObs: null, t: 0,
  cam: { theta: 0.9, phi: 1.15, dist: 150, tx: 0, ty: 0 },
  drag: null, lastInteract: 0, container: null,
};

const COL = {
  user: 0x5eead4,       // operator-attributed memories — teal
  assistant: 0x7c5cff,  // agent-attributed — violet
  weak: [0.30, 0.24, 0.66],   // link gradient: dim indigo…
  strong: [0.13, 0.83, 0.93], // …to bright cyan
};

function nodeColor(n) {
  return n.by === 'user' ? COL.user : COL.assistant;
}

function lerp3(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

function buildScene(data) {
  const { nodes, links } = data;
  M.group = new THREE.Group();
  M.scene.add(M.group);

  // ── the "room": drifting star dust + a faint horizon grid ──
  const starGeo = new THREE.BufferGeometry();
  const starPos = new Float32Array(900 * 3);
  for (let i = 0; i < 900; i++) {
    starPos[i * 3] = (Math.random() - 0.5) * 700;
    starPos[i * 3 + 1] = (Math.random() - 0.5) * 700;
    starPos[i * 3 + 2] = (Math.random() - 0.5) * 700;
  }
  starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
  M.stars = new THREE.Points(starGeo, new THREE.PointsMaterial({
    color: 0x3b3b5e, size: 0.9, transparent: true, opacity: 0.7 }));
  M.scene.add(M.stars);

  M.grid = new THREE.GridHelper(400, 28, 0x232345, 0x15152b);
  M.grid.position.y = -85;
  M.grid.material.transparent = true;
  M.grid.material.opacity = 0.5;
  M.scene.add(M.grid);

  // ── nodes at their real PCA positions ──
  const sphereGeo = new THREE.IcosahedronGeometry(1, 2);
  nodes.forEach((n, i) => {
    const size = 1.1 + Math.min(2.2, n.degree * 0.45);
    const mat = new THREE.MeshStandardMaterial({
      color: nodeColor(n), emissive: nodeColor(n), emissiveIntensity: 0.55,
      roughness: 0.35, metalness: 0.2, transparent: true, opacity: 0.95,
    });
    const mesh = new THREE.Mesh(sphereGeo, mat);
    mesh.position.set(n.x, n.y, n.z);
    mesh.scale.setScalar(size);
    mesh.userData = { idx: i, baseSize: size, phase: Math.random() * Math.PI * 2 };
    M.group.add(mesh);
    M.nodeMeshes.push(mesh);
  });

  // ── links, vertex-colored by real similarity strength ──
  const lp = [], lc = [];
  links.forEach((ln) => {
    const a = nodes[ln.a], b = nodes[ln.b];
    const t = Math.min(1, Math.max(0, (ln.s - 0.45) / 0.5)); // 0.45→0.95 sim
    const c = lerp3(COL.weak, COL.strong, t);
    lp.push(a.x, a.y, a.z, b.x, b.y, b.z);
    lc.push(...c, ...c);
  });
  const linkGeo = new THREE.BufferGeometry();
  linkGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(lp), 3));
  linkGeo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(lc), 3));
  M.linkLines = new THREE.LineSegments(linkGeo, new THREE.LineBasicMaterial({
    vertexColors: true, transparent: true, opacity: 0.42 }));
  M.group.add(M.linkLines);

  // ── electrical pulses that travel along links ──
  const pulseGeo = new THREE.SphereGeometry(0.55, 8, 8);
  const nPulses = Math.min(46, Math.max(10, Math.floor(links.length / 4)));
  for (let i = 0; i < nPulses; i++) {
    const mat = new THREE.MeshBasicMaterial({
      color: 0x9df5ff, transparent: true, opacity: 0.9,
      blending: THREE.AdditiveBlending, depthWrite: false });
    const p = new THREE.Mesh(pulseGeo, mat);
    const link = links[Math.floor(Math.random() * links.length)];
    p.userData = { link, t: Math.random(), speed: 0.15 + link.s * 0.5 };
    M.group.add(p);
    M.pulses.push(p);
  }

  M.scene.add(new THREE.AmbientLight(0x8888aa, 0.7));
  const key = new THREE.PointLight(0x7c5cff, 900, 600);
  key.position.set(80, 120, 80);
  M.scene.add(key);
  const fill = new THREE.PointLight(0x22d3ee, 500, 600);
  fill.position.set(-100, -60, -80);
  M.scene.add(fill);
  M.scene.fog = new THREE.FogExp2(0x07070d, 0.0028);
}

function applyCamera() {
  const c = M.cam;
  c.phi = Math.max(0.15, Math.min(Math.PI - 0.15, c.phi));
  c.dist = Math.max(30, Math.min(420, c.dist));
  M.camera.position.set(
    c.tx + c.dist * Math.sin(c.phi) * Math.cos(c.theta),
    c.ty + c.dist * Math.cos(c.phi),
    c.dist * Math.sin(c.phi) * Math.sin(c.theta));
  M.camera.lookAt(c.tx, c.ty, 0);
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function panelHTML(n, conns) {
  const by = n.by === 'user' ? ['OPERATOR', '#5eead4'] : ['AGENT', '#7c5cff'];
  return `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
      <span style="width:9px;height:9px;border-radius:50%;background:${by[1]};box-shadow:0 0 8px ${by[1]}"></span>
      <span style="font-family:var(--font-mono);font-size:10.5px;letter-spacing:.14em;color:${by[1]}">${by[0]} MEMORY</span>
      <span style="margin-left:auto;font-family:var(--font-mono);font-size:10px;color:var(--text-dim)">${n.degree} link${n.degree === 1 ? '' : 's'}</span>
    </div>
    <div style="font-size:13px;line-height:1.55;color:var(--text);margin-bottom:12px;max-height:170px;overflow-y:auto">${esc(n.text)}</div>
    <div style="display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:11px;margin-bottom:12px">
      <span style="color:var(--text-dim)">Stored</span><span style="font-family:var(--font-mono)">${esc(fmtDate(n.created_at))}</span>
      <span style="color:var(--text-dim)">Agent</span><span style="font-family:var(--font-mono)">${esc(n.agent || '—')}</span>
      <span style="color:var(--text-dim)">Channel</span><span style="font-family:var(--font-mono)">${esc(n.channel || '—')}</span>
    </div>
    ${conns.length ? `
    <div style="font-family:var(--font-mono);font-size:10px;letter-spacing:.12em;color:var(--text-dim);margin-bottom:6px">STRONGEST ASSOCIATIONS</div>
    ${conns.map(([txt, s]) => `
      <div style="display:flex;align-items:center;gap:8px;margin-top:5px">
        <div style="flex:0 0 46px;height:3px;border-radius:2px;background:linear-gradient(90deg,#4c3da8,#22d3ee);opacity:${0.35 + s * 0.65};width:${Math.round(s * 46)}px"></div>
        <span style="font-family:var(--font-mono);font-size:10px;color:#22d3ee">${(s * 100).toFixed(0)}%</span>
        <span style="font-size:11px;color:var(--text-dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(txt.slice(0, 60))}</span>
      </div>`).join('')}` : ''}`;
}

function setHover(idx) {
  if (idx === M.hoverId) return;
  M.hoverId = idx;
  M.nodeMeshes.forEach((m) => {
    m.material.emissiveIntensity = 0.55;
    m.scale.setScalar(m.userData.baseSize);
  });
  if (idx < 0) {
    M.panel.style.opacity = '0';
    M.container.style.cursor = 'grab';
    return;
  }
  const mesh = M.nodeMeshes[idx];
  mesh.material.emissiveIntensity = 1.6;
  mesh.scale.setScalar(mesh.userData.baseSize * 1.6);
  const n = M.data.nodes[idx];
  const conns = M.data.links
    .filter((l) => l.a === idx || l.b === idx)
    .sort((x, y) => y.s - x.s).slice(0, 4)
    .map((l) => [M.data.nodes[l.a === idx ? l.b : l.a].text, l.s]);
  M.panel.innerHTML = panelHTML(n, conns);
  M.panel.style.opacity = '1';
  M.container.style.cursor = 'pointer';
}

function animate() {
  M.raf = requestAnimationFrame(animate);
  M.t += 0.016;

  // idle auto-orbit resumes 3s after the last interaction
  if (performance.now() - M.lastInteract > 3000) M.cam.theta += 0.0011;
  applyCamera();

  // node breathing
  for (const m of M.nodeMeshes) {
    const p = m.userData;
    if (M.hoverId !== p.idx) {
      m.scale.setScalar(p.baseSize * (1 + Math.sin(M.t * 1.6 + p.phase) * 0.07));
    }
  }
  // electrical signals along the links
  const nodes = M.data.nodes;
  for (const p of M.pulses) {
    const u = p.userData;
    u.t += u.speed * 0.016;
    if (u.t >= 1) {
      u.link = M.data.links[Math.floor(Math.random() * M.data.links.length)];
      u.t = 0; u.speed = 0.15 + u.link.s * 0.5;
    }
    const a = nodes[u.link.a], b = nodes[u.link.b];
    p.position.set(a.x + (b.x - a.x) * u.t, a.y + (b.y - a.y) * u.t, a.z + (b.z - a.z) * u.t);
    p.material.opacity = 0.35 + Math.sin(u.t * Math.PI) * 0.6;
  }
  if (M.stars) M.stars.rotation.y += 0.00016;

  // hover raycast
  if (M.pointer && M.raycaster) {
    M.raycaster.setFromCamera(M.pointer, M.camera);
    const hits = M.raycaster.intersectObjects(M.nodeMeshes, false);
    setHover(hits.length ? hits[0].object.userData.idx : -1);
  }
  M.renderer.render(M.scene, M.camera);
}

async function mount(container, data) {
  dispose();
  const three = await loadThree();
  if (!three || !container || !container.isConnected) return;
  M.container = container;
  M.data = data;

  M.scene = new THREE.Scene();
  M.scene.background = new THREE.Color(0x07070d);
  M.camera = new THREE.PerspectiveCamera(55, 1, 0.1, 2000);
  M.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  M.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  M.canvas = M.renderer.domElement;
  M.canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;border-radius:14px;cursor:grab';
  container.appendChild(M.canvas);

  // hover info panel (glass card, pointer-transparent so orbiting works through it)
  M.panel = document.createElement('div');
  M.panel.style.cssText =
    'position:absolute;top:18px;right:18px;width:330px;max-width:44%;padding:16px 18px;' +
    'background:rgba(13,13,26,.82);border:1px solid rgba(124,92,255,.35);border-radius:14px;' +
    'backdrop-filter:blur(14px);box-shadow:0 8px 40px rgba(0,0,0,.5),0 0 24px rgba(124,92,255,.12);' +
    'opacity:0;transition:opacity .22s;pointer-events:none;z-index:5';
  container.appendChild(M.panel);

  // legend
  const legend = document.createElement('div');
  legend.style.cssText =
    'position:absolute;left:18px;bottom:16px;display:flex;gap:16px;align-items:center;' +
    'font-family:var(--font-mono);font-size:10.5px;color:var(--text-dim);pointer-events:none;z-index:5';
  legend.innerHTML =
    '<span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#5eead4;box-shadow:0 0 6px #5eead4;margin-right:6px"></i>operator memory</span>' +
    '<span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#7c5cff;box-shadow:0 0 6px #7c5cff;margin-right:6px"></i>agent memory</span>' +
    '<span><i style="display:inline-block;width:22px;height:3px;border-radius:2px;background:linear-gradient(90deg,#4c3da8,#22d3ee);margin-right:6px;vertical-align:2px"></i>association strength</span>' +
    '<span style="opacity:.75">drag to orbit · scroll to zoom · hover a node</span>';
  container.appendChild(legend);

  M.raycaster = new THREE.Raycaster();
  M.raycaster.params.Points = { threshold: 2 };

  buildScene(data);

  // ── controls ──
  const rect = () => M.canvas.getBoundingClientRect();
  M.canvas.addEventListener('pointerdown', (e) => {
    M.drag = { x: e.clientX, y: e.clientY };
    M.lastInteract = performance.now();
    M.container.style.cursor = 'grabbing';
    M.canvas.setPointerCapture(e.pointerId);
  });
  M.canvas.addEventListener('pointermove', (e) => {
    const r = rect();
    M.pointer = new THREE.Vector2(
      ((e.clientX - r.left) / r.width) * 2 - 1,
      -((e.clientY - r.top) / r.height) * 2 + 1);
    if (M.drag) {
      M.cam.theta += (e.clientX - M.drag.x) * 0.0052;
      M.cam.phi -= (e.clientY - M.drag.y) * 0.0052;
      M.drag = { x: e.clientX, y: e.clientY };
      M.lastInteract = performance.now();
    }
  });
  const endDrag = () => { M.drag = null; if (M.container) M.container.style.cursor = 'grab'; };
  M.canvas.addEventListener('pointerup', endDrag);
  M.canvas.addEventListener('pointerleave', () => { endDrag(); M.pointer = null; setHover(-1); });
  M.canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    M.cam.dist *= (1 + Math.sign(e.deltaY) * 0.09);
    M.lastInteract = performance.now();
  }, { passive: false });

  const size = () => {
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;
    M.renderer.setSize(w, h, false);
    M.camera.aspect = w / h;
    M.camera.updateProjectionMatrix();
  };
  size();
  M.resizeObs = new ResizeObserver(size);
  M.resizeObs.observe(container);

  applyCamera();
  animate();
}

function dispose() {
  if (M.raf) cancelAnimationFrame(M.raf);
  if (M.resizeObs) M.resizeObs.disconnect();
  if (M.renderer) {
    M.renderer.dispose();
    if (M.canvas && M.canvas.parentNode) M.canvas.parentNode.removeChild(M.canvas);
  }
  if (M.panel && M.panel.parentNode) M.panel.parentNode.removeChild(M.panel);
  if (M.container) {
    M.container.querySelectorAll(':scope > div').forEach((el) => el.remove());
  }
  Object.assign(M, {
    renderer: null, scene: null, camera: null, raf: null, canvas: null,
    group: null, nodeMeshes: [], linkLines: null, pulses: [], stars: null,
    grid: null, data: null, panel: null, hoverId: -1, raycaster: null,
    pointer: null, resizeObs: null, drag: null, container: null,
  });
}

window.Memory3D = { mount, dispose };
