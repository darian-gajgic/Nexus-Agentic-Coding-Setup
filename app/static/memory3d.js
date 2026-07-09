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
  cam: { theta: 0.9, phi: 1.15, dist: 115, tx: 0, ty: 0 },
  drag: null, lastInteract: 0, container: null,
  glows: null, labels: [], flyT: -1, searchQ: '', matchSet: null,
};

// shared soft radial glow texture (fake bloom, cheap and pretty)
let _glowTex = null;
function glowTexture() {
  if (_glowTex) return _glowTex;
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.25, 'rgba(255,255,255,.55)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  _glowTex = new THREE.CanvasTexture(c);
  return _glowTex;
}

function textSprite(text, sub, hex) {
  // Region callout in the reference style: small UPPERCASE mono label in the
  // region's own color, underline with a leader tick, dim sub-caption.
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
  // underline + diagonal leader tick pointing at the region
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
  const mat = new THREE.SpriteMaterial({
    map: tex, transparent: true, opacity: 0.95,
    depthWrite: false, depthTest: false });
  const s = new THREE.Sprite(mat);
  s.scale.set(c.width / 15, c.height / 15, 1);
  s.center.set(0.06, 0.28); // anchor near the leader tick
  s.renderOrder = 10;
  return s;
}

// Color = IDENTITY. Each color group is one memory owner (a specialist, or
// one semantic slice of hermes's own mind — the server splits any identity
// holding >50% of the map). Cyan family first and extended across the top
// groups until it covers >=20% of all nodes; then maximally distinct hues.
const CYAN_FAMILY = [0x22d3ee, 0x67e8f9, 0x0ea5b7];
const DISTINCT_HUES = [0xa3e635, 0xf43f5e, 0xf59e0b, 0x8b5cf6, 0xec4899,
                       0x60a5fa, 0x2dd4bf, 0xfb7185, 0xfacc15, 0x34d399,
                       0xc084fc, 0xf97316];

function buildHueMap(data) {
  // groups arrive ranked by size desc; node.group is the rank index
  const groups = data.groups || [];
  const total = groups.reduce((s, g) => s + g.size, 0) || 1;
  M.hueByGroup = [];
  let cyanShare = 0, ci = 0, di = 0;
  groups.forEach((g, rank) => {
    if (cyanShare < 0.20 && ci < CYAN_FAMILY.length) {
      M.hueByGroup[rank] = CYAN_FAMILY[ci++];
      cyanShare += g.size / total;
    } else {
      M.hueByGroup[rank] = DISTINCT_HUES[di++ % DISTINCT_HUES.length];
    }
  });
  // region callouts inherit the hue of the group most of their nodes wear
  M.hueByCluster = {};
  const tally = {};
  (data.nodes || []).forEach((n) => {
    if (n.cluster == null) return;
    (tally[n.cluster] = tally[n.cluster] || {})[n.group] =
      (tally[n.cluster]?.[n.group] || 0) + 1;
  });
  Object.entries(tally).forEach(([cid, byGroup]) => {
    const top = Object.entries(byGroup).sort((a, b) => b[1] - a[1])[0];
    M.hueByCluster[cid] = M.hueByGroup[+top[0]] ?? CYAN_FAMILY[0];
  });
}

function nodeColor(n) {
  return (M.hueByGroup && M.hueByGroup[n.group]) ?? CYAN_FAMILY[0];
}

function lerp3(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

function buildScene(data) {
  const { nodes, links } = data;
  buildHueMap(data);
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

  // no floor grid — the reference look is pure deep space

  // ── nodes at their real PCA positions — small bright star-points, the
  // galaxy look comes from the glow layer, not from big geometry ──
  const sphereGeo = new THREE.IcosahedronGeometry(1, 1);
  nodes.forEach((n, i) => {
    const size = 0.6 + Math.min(1.1, n.degree * 0.2);
    const mat = new THREE.MeshBasicMaterial({
      color: nodeColor(n), transparent: true, opacity: 0.95,
    });
    const mesh = new THREE.Mesh(sphereGeo, mat);
    mesh.position.set(n.x, n.y, n.z);
    mesh.scale.setScalar(size);
    mesh.userData = { idx: i, baseSize: size, phase: Math.random() * Math.PI * 2 };
    M.group.add(mesh);
    M.nodeMeshes.push(mesh);
  });

  // ── per-node glow sprites (one Points cloud, additive = bloom feel) ──
  const gp = [], gc = [], gs = [];
  nodes.forEach((n, i) => {
    gp.push(n.x, n.y, n.z);
    const c = new THREE.Color(nodeColor(n));
    gc.push(c.r, c.g, c.b);
    gs.push(3.4 + Math.min(5, n.degree * 1.1));
  });
  const glowGeo = new THREE.BufferGeometry();
  glowGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(gp), 3));
  glowGeo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(gc), 3));
  M.glows = new THREE.Points(glowGeo, new THREE.PointsMaterial({
    map: glowTexture(), size: 8.5, vertexColors: true, transparent: true,
    opacity: 0.75, blending: THREE.AdditiveBlending, depthWrite: false,
    sizeAttenuation: true }));
  M.group.add(M.glows);

  // ── semantic region callouts in their region's color ──
  (data.clusters || []).forEach((cl) => {
    const hue = (M.hueByCluster && M.hueByCluster[cl.id]) ?? CYAN_FAMILY[0];
    const s = textSprite(cl.label, `${cl.size} memories`, hue);
    s.position.set(cl.x, cl.y + 7, cl.z);
    M.group.add(s);
    M.labels.push(s);
  });

  // ── links: hair-thin web, each strand tinted by its endpoints' region
  // colors, brightness by real similarity strength ──
  const lp = [], lc = [];
  links.forEach((ln) => {
    const a = nodes[ln.a], b = nodes[ln.b];
    const t = 0.35 + 0.65 * Math.min(1, Math.max(0, (ln.s - 0.45) / 0.5));
    const ca = new THREE.Color(nodeColor(a)).multiplyScalar(t);
    const cb = new THREE.Color(nodeColor(b)).multiplyScalar(t);
    lp.push(a.x, a.y, a.z, b.x, b.y, b.z);
    lc.push(ca.r, ca.g, ca.b, cb.r, cb.g, cb.b);
  });
  const linkGeo = new THREE.BufferGeometry();
  linkGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(lp), 3));
  linkGeo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(lc), 3));
  M.linkLines = new THREE.LineSegments(linkGeo, new THREE.LineBasicMaterial({
    vertexColors: true, transparent: true, opacity: 0.30,
    blending: THREE.AdditiveBlending, depthWrite: false }));
  M.group.add(M.linkLines);

  // ── electrical pulses that travel along links ──
  // no links (no similarity above threshold yet): zero pulses — indexing
  // links[NaN] here threw and blanked the whole galaxy
  const pulseGeo = new THREE.SphereGeometry(0.55, 8, 8);
  const nPulses = links.length ? Math.min(46, Math.max(10, Math.floor(links.length / 4))) : 0;
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

  M.scene.fog = new THREE.FogExp2(0x02080a, 0.0012);
}

function applyCamera() {
  const c = M.cam;
  c.phi = Math.max(0.15, Math.min(Math.PI - 0.15, c.phi));
  c.dist = Math.max(24, Math.min(760, c.dist));
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
  M.nodeMeshes.forEach((m, i) => {
    const dim = M.matchSet && !M.matchSet.has(i);
    m.scale.setScalar(m.userData.baseSize * (M.matchSet && !dim ? 2.2 : 1));
  });
  if (idx < 0) {
    M.panel.style.opacity = '0';
    M.container.style.cursor = 'grab';
    return;
  }
  const mesh = M.nodeMeshes[idx];
  mesh.scale.setScalar(mesh.userData.baseSize * 3.2);
  const n = M.data.nodes[idx];
  const conns = M.data.links
    .filter((l) => l.a === idx || l.b === idx)
    .sort((x, y) => y.s - x.s).slice(0, 4)
    .map((l) => [M.data.nodes[l.a === idx ? l.b : l.a].text, l.s]);
  M.panel.innerHTML = panelHTML(n, conns);
  M.panel.style.opacity = '1';
  M.container.style.cursor = 'pointer';
}

function setSearch(q) {
  M.searchQ = (q || '').trim().toLowerCase();
  if (!M.searchQ) { M.matchSet = null; }
  else {
    M.matchSet = new Set();
    M.data.nodes.forEach((n, i) => {
      if ((n.text || '').toLowerCase().includes(M.searchQ)) M.matchSet.add(i);
    });
  }
  M.nodeMeshes.forEach((m, i) => {
    const dim = M.matchSet && !M.matchSet.has(i);
    m.material.opacity = dim ? 0.08 : 0.95;
    m.scale.setScalar(m.userData.baseSize * (M.matchSet && !dim ? 2.2 : 1));
  });
  if (M.glows) M.glows.material.opacity = M.matchSet ? 0.15 : 0.75;
  if (M.linkLines) M.linkLines.material.opacity = M.matchSet ? 0.08 : 0.30;
  return M.matchSet ? M.matchSet.size : (M.data ? M.data.nodes.length : 0);
}

function animate() {
  M.raf = requestAnimationFrame(animate);
  M.t += 0.016;

  // cinematic fly-in on mount (cancelled by the first interaction)
  if (M.flyT >= 0) {
    M.flyT += 0.016;
    const k = Math.min(1, M.flyT / 2.4);
    const ease = 1 - Math.pow(1 - k, 3);
    M.cam.dist = 640 - (640 - 115) * ease;
    M.cam.phi = 0.62 + (1.15 - 0.62) * ease;
    if (k >= 1) M.flyT = -1;
  }

  // idle auto-orbit resumes 3s after the last interaction
  if (performance.now() - M.lastInteract > 3000) M.cam.theta += 0.0011;
  applyCamera();

  // star twinkle (respects search highlighting)
  for (const m of M.nodeMeshes) {
    const p = m.userData;
    if (M.hoverId === p.idx) continue;
    const boost = M.matchSet && M.matchSet.has(p.idx) ? 2.2 : 1;
    m.scale.setScalar(p.baseSize * boost * (1 + Math.sin(M.t * 1.6 + p.phase) * 0.08));
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

  // hover: screen-space nearest-star picking — geometric raycasts miss
  // sub-pixel star points, so we project positions and pick within 16px
  if (M.pointer && M.data) {
    const w = M.canvas.clientWidth, h = M.canvas.clientHeight;
    const px = (M.pointer.x + 1) / 2 * w, py = (1 - M.pointer.y) / 2 * h;
    let best = -1, bestD = 16 * 16;
    const v = new THREE.Vector3();
    for (let i = 0; i < M.nodeMeshes.length; i++) {
      if (M.matchSet && !M.matchSet.has(i)) continue; // dimmed = not pickable
      v.copy(M.nodeMeshes[i].position).project(M.camera);
      if (v.z > 1) continue; // behind camera
      const dx = (v.x + 1) / 2 * w - px, dy = (1 - v.y) / 2 * h - py;
      const d = dx * dx + dy * dy;
      if (d < bestD) { bestD = d; best = i; }
    }
    setHover(best);
  }
  M.renderer.render(M.scene, M.camera);
}

async function mount(container, data, opts) {
  dispose();
  const three = await loadThree();
  if (!three || !container || !container.isConnected) return;
  M.container = container;
  M.data = data;
  M.onSelect = (opts && opts.onSelect) || null; // SPEC-BLOCK2 R2.1: click a star to edit it

  M.scene = new THREE.Scene();
  M.scene.background = new THREE.Color(0x02080a); // deep teal-black space
  M.camera = new THREE.PerspectiveCamera(55, 1, 0.1, 2000);
  M.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  M.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  M.canvas = M.renderer.domElement;
  M.canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;border-radius:14px;cursor:grab';
  container.appendChild(M.canvas);

  // hover info panel (glass card, pointer-transparent so orbiting works through it)
  M.panel = document.createElement('div');
  M.panel.style.cssText =
    'position:absolute;top:18px;left:18px;width:330px;max-width:44%;padding:16px 18px;' +
    'background:rgba(13,13,26,.82);border:1px solid rgba(124,92,255,.35);border-radius:14px;' +
    'backdrop-filter:blur(14px);box-shadow:0 8px 40px rgba(0,0,0,.5),0 0 24px rgba(124,92,255,.12);' +
    'opacity:0;transition:opacity .22s;pointer-events:none;z-index:5';
  container.appendChild(M.panel);

  // legend: the semantic regions in their own colors
  const legend = document.createElement('div');
  legend.style.cssText =
    'position:absolute;left:18px;bottom:16px;display:flex;gap:14px;align-items:center;flex-wrap:wrap;' +
    'font-family:var(--font-mono);font-size:10.5px;color:var(--text-dim);pointer-events:none;z-index:5;max-width:75%';
  const regionChips = (data.groups || []).slice(0, 9).map((g, rank) => {
    const col = '#' + ((M.hueByGroup && M.hueByGroup[rank]) ?? CYAN_FAMILY[0]).toString(16).padStart(6, '0');
    const word = esc(String(g.label).replace('hermes · ', '').slice(0, 18));
    return `<span><i style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${col};box-shadow:0 0 6px ${col};margin-right:5px"></i>${word}</span>`;
  }).join('');
  legend.innerHTML = regionChips +
    `<span style="opacity:.7">· drag orbit · scroll zoom · hover a star${M.onSelect ? ' · click to edit' : ''}</span>`;
  container.appendChild(legend);

  M.raycaster = new THREE.Raycaster();
  M.raycaster.params.Points = { threshold: 2 };

  buildScene(data);
  M.flyT = 0; // cinematic approach from deep space

  // ── controls ──
  const rect = () => M.canvas.getBoundingClientRect();
  M.canvas.addEventListener('pointerdown', (e) => {
    M.drag = { x: e.clientX, y: e.clientY };
    M.downAt = { x: e.clientX, y: e.clientY, t: performance.now() };
    M.flyT = -1; // interaction cancels the fly-in
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
  M.canvas.addEventListener('pointerup', (e) => {
    // a CLICK (not a drag): ≤6px travel, ≤600ms, over a hovered star
    if (M.onSelect && M.downAt && M.hoverId >= 0 &&
        Math.hypot(e.clientX - M.downAt.x, e.clientY - M.downAt.y) <= 6 &&
        performance.now() - M.downAt.t <= 600) {
      try { M.onSelect(M.data.nodes[M.hoverId]); } catch { /* modal errors stay in the app layer */ }
    }
    M.downAt = null;
    endDrag();
  });
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
    glows: null, labels: [], flyT: -1, searchQ: '', matchSet: null,
    onSelect: null, downAt: null,
  });
}

window.Memory3D = { mount, dispose, search: setSearch };
