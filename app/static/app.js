/* NEXUS Agent OS — Frontend Application v3
   Vanilla JS, no build step. Design system v3 (glass + aurora + 3D core).
   JARVIS view code is unchanged from v2 (see JARVIS section). */
const API = '';
let currentView = 'dashboard';
let ws = null;
let charts = {};
let agentCharts = {};          // per-agent chart instances, persisted across ticks
let state = { agents: [], tasks: [], programs: [], stats: {}, activity: [], verifyRuns: [], approvals: [], schedulerJobs: [], watchdog: {}, agentCosts: {}, messages: [] };
let agentsBuilt = false;       // agents view DOM built this visit
let dashBuilt = false;         // dashboard DOM built this visit
let monBuilt = false;          // monitor DOM built this visit
let pendingRender = false;     // render was suppressed while UI was busy
let lastTasksJSON = '';
let lastAgenticJSON = '';
let lastWorkflowsJSON = '';

// Encode a workspace-relative path for a URL, keeping the / separators
// (encodeURIComponent would turn them into %2F, which the {name:path}
// route param does not re-split).
function encPath(p) {
  return String(p).split('/').map(encodeURIComponent).join('/');
}
const kanbanFilters = { q: '', assignee: '', priority: '', tag: '', workflow: '' };
const kanbanDrag = { active: false, id: null };

// ===== HELPERS =====
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (t) => String(t == null ? '' : t)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const fmtTime = (ts) => {
  if (!ts) return '--';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('en-US', { hour12: false });
};
const fmtAgo = (ts) => {
  if (!ts) return '--';
  let s = Date.now() / 1000 - ts;
  const future = s < 0;
  s = Math.abs(s);
  const txt = s < 60 ? `${Math.floor(s)}s` : s < 3600 ? `${Math.floor(s / 60)}m` : s < 86400 ? `${Math.floor(s / 3600)}h` : `${Math.floor(s / 86400)}d`;
  return future ? `in ${txt}` : `${txt} ago`;
};
const fmtDuration = (s) => {
  if (s < 60) return `${s.toFixed(1)}s`;
  if (s < 3600) return `${(s / 60).toFixed(1)}m`;
  return `${(s / 3600).toFixed(1)}h`;
};
const fmtUptime = (s) => {
  if (!s || s < 1) return '--';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
};
const fmtTokens = (n) => {
  if (!n) return '0';
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return `${n}`;
};

// Small inline SVG icon set for stat tiles / headers
const NICO = {
  agents: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="15" height="15"><circle cx="12" cy="12" r="2.5"/><circle cx="5" cy="6" r="1.7"/><circle cx="19" cy="6" r="1.7"/><circle cx="12" cy="20" r="1.7"/><line x1="6.2" y1="7.2" x2="10.2" y2="10.4"/><line x1="17.8" y1="7.2" x2="13.8" y2="10.4"/><line x1="12" y1="14.5" x2="12" y2="18.3"/></svg>',
  tasks: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="15" height="15"><rect x="4" y="4" width="16" height="16" rx="3"/><polyline points="8.5 12.5 11 15 15.5 9.5"/></svg>',
  tokens: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="15" height="15"><path d="M13 2.5L5 13.5h6L11 21.5l8-11h-6z"/></svg>',
  done: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="15" height="15"><circle cx="12" cy="12" r="8.5"/><polyline points="8.5 12.5 11 15 15.5 9.5"/></svg>',
};

// ===== TOASTS =====
let _toastN = 0, _lastErrToast = 0;
function toast(msg, type = 'info', ms = 3400) {
  try { uxRecord(type === 'err' ? 'error-output' : 'output', msg); } catch { }
  const c = $('#toasts');
  if (!c || _toastN > 4) return;
  _toastN++;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => { el.remove(); _toastN--; }, 280); }, ms);
}

// ===== API =====
async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  // Feedback journal: record mutating calls (never the GET polling noise,
  // never the known-issues endpoints themselves).
  if (method !== 'GET' && !path.startsWith('/api/known-issues')) {
    try {
      uxRecord('action', `${method} ${path}` + (body ? ' ' + JSON.stringify(body).slice(0, 160) : ''));
    } catch { }
  }
  let res;
  try {
    res = await fetch(API + path, opts);
  } catch (e) {
    if (Date.now() - _lastErrToast > 5000) { _lastErrToast = Date.now(); toast('Server unreachable', 'err'); }
    throw e;
  }
  if (!res.ok) {
    // surface the server's actual error message — it was discarded here,
    // so every endpoint's helpful detail died as "API /x: 400"
    let detail = '';
    try {
      const j = await res.json();
      detail = j.error || j.detail || '';
      if (typeof detail !== 'string') detail = JSON.stringify(detail).slice(0, 200);
    } catch { }
    if (res.status === 401 && authState.user) {
      // Session expired mid-use (or login was just turned on) — reboot into
      // the login screen instead of drowning the user in red toasts.
      location.reload();
      throw new Error('session expired');
    }
    if (method !== 'GET' && Date.now() - _lastErrToast > 2000) {
      _lastErrToast = Date.now();
      toast(detail ? `${detail}` : `${method} ${path} failed (${res.status})`, 'err', 5000);
    }
    throw new Error(detail || `API ${path}: ${res.status}`);
  }
  return res.json();
}

// ===== AUTH (Block 1 multi-user) =====
// Single-user machines never see any of this: /api/auth/state says
// auth_required=false and boot goes straight to init() as before.
let authState = { required: false, user: null };

// F103: client-side gate for admin-only panels. Reliable from the first
// render — bootAuth awaits /api/auth/state before init(); a machine with
// login OFF is the single operator, i.e. the admin.
function isAdminUser() {
  return !authState.required || !!(authState.user && authState.user.role === 'admin');
}

async function bootAuth() {
  try {
    const st = await api('GET', '/api/auth/state');
    authState = { required: !!st.auth_required, user: st.user || null };
  } catch {
    // Server unreachable — show the normal app shell; api() toasts errors.
    authState = { required: false, user: null };
  }
  if (authState.required && !authState.user) { renderLoginScreen(); return; }
  loadFocus();
  renderUserChip();
  ensureModels(); // Settings v2: model registry feeds every task-model dropdown
  init();
}

function renderLoginScreen() {
  document.title = 'NEXUS — Sign in';
  const app = $('#app');
  if (app) app.style.display = 'none';
  const overlay = document.createElement('div');
  overlay.id = 'loginScreen';
  overlay.innerHTML = `
    <div class="login-card">
      <div class="logo" style="justify-content:center;margin-bottom:6px">
        <div class="logo-mark"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><polygon points="12 2.5 21 7.5 21 16.5 12 21.5 3 16.5 3 7.5"/><polygon points="12 7 16.5 9.5 16.5 14.5 12 17 7.5 14.5 7.5 9.5"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/></svg></div>
        <div class="logo-txt"><span class="logo-text">NEXUS</span><span class="logo-sub">AGENT OS</span></div>
      </div>
      <div class="muted" style="text-align:center;margin-bottom:16px;font-size:12.5px">Sign in to your personal workspace</div>
      <form id="loginForm">
        <div class="form-group"><label class="form-label">Username</label>
          <input class="form-input" id="loginUser" autocomplete="username" autocapitalize="none" autofocus></div>
        <div class="form-group" style="margin-top:10px"><label class="form-label">Password</label>
          <input class="form-input" id="loginPass" type="password" autocomplete="current-password"></div>
        <div id="loginErr" class="login-err" style="display:none"></div>
        <button class="btn-primary" type="submit" style="width:100%;margin-top:14px;justify-content:center">Sign in</button>
      </form>
    </div>`;
  document.body.appendChild(overlay);
  $('#loginForm').addEventListener('submit', doLogin);
}

async function doLogin(e) {
  e.preventDefault();
  const errEl = $('#loginErr');
  errEl.style.display = 'none';
  try {
    const r = await fetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: $('#loginUser').value.trim(), password: $('#loginPass').value }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      errEl.textContent = j.error || 'Sign-in failed';
      errEl.style.display = 'block';
      return;
    }
    location.reload();
  } catch {
    errEl.textContent = 'Server unreachable';
    errEl.style.display = 'block';
  }
}

async function doLogout() {
  try { jarvisHardStop(); } catch { }   // stop any live JARVIS turn/audio before the reload
  try { await api('POST', '/api/auth/logout'); } catch { }
  location.reload();
}

function renderUserChip() {
  // Only shown once login is actually in force — the single-operator
  // machine keeps its exact pre-multiuser topbar.
  if (!authState.required || !authState.user) return;
  const right = $('.topbar-right');
  if (!right || $('#userChip')) return;
  const chip = document.createElement('div');
  chip.id = 'userChip';
  chip.className = 'user-chip';
  chip.innerHTML = `<span class="user-avatar">${esc((authState.user.display_name || '?').slice(0, 1).toUpperCase())}</span>` +
    `<span class="user-name">${esc(authState.user.display_name)}</span>` +
    `<button class="user-logout" onclick="doLogout()" title="Sign out">⎋</button>`;
  right.insertBefore(chip, right.firstChild);
}

// ===== INIT =====
async function init() {
  if (window.Chart) {
    Chart.defaults.color = '#9a9ab2';
    Chart.defaults.borderColor = 'rgba(148,148,190,.12)';
    Chart.defaults.font.family = "'JetBrains Mono', monospace";
    Chart.defaults.font.size = 10;
  }
  bindNav();
  bindGlobal();
  connectWS();
  await loadAll();
  switchView('dashboard');
  startClock();
  renderFocusBar();
  setInterval(tick, 3000);
  // Session strip + known-issues badge are visible immediately, not after
  // the first slow quota tick.
  try {
    state.quota = await api('GET', '/api/quota');
    updateQuotaBanner();
    updateModelStrip();
  } catch { }
  loadKnownIssues();
}

function bindNav() {
  $$('.nav-item').forEach(el => {
    el.addEventListener('click', () => switchView(el.dataset.view));
  });
}

function bindGlobal() {
  $('#spawnBtn').addEventListener('click', () => showSpawnModal());
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closeModal(); closeDrawer(); closeMobileNav(); }
  });
  $('#drawerOverlay').addEventListener('click', () => closeDrawer());
  // Mobile off-canvas nav (≤900px: the sidebar hides behind the ☰ button)
  const menuBtn = $('#menuBtn');
  if (menuBtn) menuBtn.addEventListener('click', () => {
    $('.sidebar').classList.toggle('open');
    document.body.classList.toggle('nav-open', $('.sidebar').classList.contains('open'));
  });
  const scrim = $('#sidebarScrim');
  if (scrim) scrim.addEventListener('click', closeMobileNav);
  // Navigating closes the drawer-style nav on phones
  $$('.nav-item').forEach(el => el.addEventListener('click', closeMobileNav));
}

function closeMobileNav() {
  const sb = $('.sidebar');
  if (sb) sb.classList.remove('open');
  document.body.classList.remove('nav-open');
}

function startClock() {
  setInterval(() => {
    $('#liveClock').textContent = new Date().toLocaleTimeString('en-US', { hour12: false });
  }, 1000);
}

// ===== WEBSOCKET =====
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => setWSStatus(true);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    handleWSMessage(msg);
  };
  ws.onclose = () => { setWSStatus(false); setTimeout(connectWS, 3000); };
}

function setWSStatus(on) {
  const d = $('#wsDot'), l = $('#wsLabel'), p = $('#connPill');
  if (!d) return;
  d.className = `status-dot ${on ? 'online' : 'offline'}`;
  if (l) l.textContent = on ? 'LIVE' : 'OFFLINE';
  if (p) p.classList.toggle('offline', !on);
}

async function handleWSMessage(msg) {
  if (msg.type === 'agent_created' || msg.type === 'agent_updated' || msg.type === 'agent_deleted') {
    state.agents = await api('GET', '/api/agents');
    agentsBuilt = false; // force rebuild on structural change
  }
  if (msg.type === 'task_created' || msg.type === 'task_updated' || msg.type === 'task_deleted') {
    // Super Result: surface critic verdict transitions as a toast (B9 — the
    // open review modal is never force-refreshed under the user's cursor).
    if (msg.type === 'task_updated' && msg.data && msg.data.critic_verdict) {
      const old = (state.tasks || []).find(t => t.id === msg.data.id);
      const nv = msg.data.critic_verdict;
      if (old && old.critic_verdict !== nv && nv !== 'running') {
        let k = 0;
        try { k = (((JSON.parse(msg.data.critic_json || '{}')) || {}).findings || []).length; } catch { /* raw */ }
        toast(nv === 'SHIP'
          ? `✨ Super Result: critic verified "${(msg.data.title || '').slice(0, 40)}" — SHIP`
          : `✨ Super Result round ${msg.data.critic_round || '?'}: ${k} finding(s) posted${uiLocked() ? ' — reopen the review to see them' : ''}`,
          nv === 'SHIP' ? 'ok' : 'info');
      }
    }
    state.tasks = await api('GET', '/api/tasks');
  }
  if (msg.type === 'program_created') {
    state.programs = await api('GET', '/api/programs');
  }
  if (msg.type === 'approval_created' || msg.type === 'approval_updated') {
    const appr = await api('GET', '/api/approvals?status=pending');
    state.approvals = appr.approvals || [];
    updateApprovalBadge();
    if (msg.type === 'approval_created') toast('New approval request pending', 'info');
  }
  if (isAdminUser() && (msg.type === 'job_created' || msg.type === 'job_updated' || msg.type === 'job_deleted')) {
    const jobs = await api('GET', '/api/scheduler');   // admin-gated — members skip (F103)
    state.schedulerJobs = jobs.jobs || [];
  }
  if (msg.type === 'lesson_decided' || msg.type === 'specialist_memory_added' || msg.type === 'specialist_saved') {
    // Learning-pipeline data changed (another tab, or the reflect timer):
    // drop the cache so the Specialists view refetches instead of showing
    // decided items as still pending.
    specialistsState.fetched = false;
    if (currentView === 'specialists' && !uiLocked()) loadSpecialists();
  }
  softRender();
}

// Re-render the active view unless the user is mid-interaction.
function softRender() {
  if (currentView === 'jarvis') {
    // JARVIS manages its own live updates (SSE stream, status/event pollers).
    // A blind render() here rebuilds #content, which DETACHES the 3D canvas;
    // mount() then early-returns because the renderer still exists, leaving the
    // avatar + memory galaxy blank until a full teardown/re-enter. tick() already
    // skips jarvis for the same reason — mirror it here for the WS path. Only
    // nudge the command deck (the one genuinely-live panel) if it's open.
    if (jarvisState.deckOpen) jarvisLoadDeck();
    return;
  }
  if (uiLocked()) { pendingRender = true; return; }
  render();
}

function uiLocked() {
  const m = $('#modal');
  if (m && m.style.display !== 'none') return true;
  if (drawerState.open) return true;
  if (kanbanDrag.active) return true;
  const vm = $('#verifyModal'), jm = $('#jobModal');
  if (vm && vm.style.display === 'flex') return true;
  if (jm && jm.style.display === 'flex') return true;
  const ae = document.activeElement;
  if (ae && ['INPUT', 'TEXTAREA', 'SELECT'].includes(ae.tagName)) return true;
  return false;
}

// ===== DATA =====
async function loadAll() {
  const [agents, tasks, programs, stats, activity] = await Promise.all([
    api('GET', '/api/agents'),
    api('GET', '/api/tasks'),
    api('GET', '/api/programs'),
    api('GET', '/api/stats'),
    api('GET', '/api/activity'),
  ]);
  state.agents = agents;
  state.tasks = tasks;
  state.programs = programs;
  state.stats = stats;
  state.activity = activity;
  await loadAgenticData();
}

// Fetch all agentic subsystem data (called on init and when entering the Agentic view)
async function loadAgenticData() {
  try {
    // Verify runs, scheduler and watchdog are admin-gated (Batch 6) — for
    // members don't even ask, or every load fires three 403s (F103). This also
    // keeps the member-visible fetches (approvals/health/quota) from being
    // dragged down by a rejected Promise.all.
    const admin = isAdminUser();
    const [runs, appr, jobs, wd, health, quota] = await Promise.all([
      admin ? api('GET', '/api/verify/runs?limit=10') : { runs: [] },
      api('GET', '/api/approvals?status=pending'),
      admin ? api('GET', '/api/scheduler') : { jobs: [] },
      admin ? api('GET', '/api/watchdog/status') : {},
      api('GET', '/api/health/full'),
      api('GET', '/api/quota'),
    ]);
    state.verifyRuns = runs.runs || [];
    state.approvals = appr.approvals || [];
    state.schedulerJobs = jobs.jobs || [];
    state.watchdog = wd || {};
    state.healthFull = health || {};
    state.quota = quota || {};
    updateApprovalBadge();
    updateQuotaBanner();
  } catch (e) { /* subsystems may be starting */ }
}

// R7: global amber banner while the fleet is paused by a quota storm
function updateQuotaBanner() {
  const q = state.quota || {};
  let el = $('#quotaBanner');
  if (!q.backoff_active && (!q.pct_of_daily_cap || q.pct_of_daily_cap < 100)) {
    if (el) el.remove();
    return;
  }
  const msg = q.backoff_active
    ? `⏸ GLM quota storm — dispatch paused ${q.backoff_remaining_s}s (429 ×${q.consecutive_429}). Tasks wait as "blocked_quota"; nothing is lost.`
    : `⏸ Daily token cap reached (${fmtTokens(q.today_tokens)} / ${fmtTokens(q.daily_cap)}). Dispatch resumes tomorrow or raise the cap in Agentic → Quota.`;
  if (!el) {
    el = document.createElement('div');
    el.id = 'quotaBanner';
    el.style.cssText = 'position:fixed;top:0;left:50%;transform:translateX(-50%);z-index:900;' +
      'background:rgba(251,146,60,.12);border:1px solid rgba(251,146,60,.5);color:#fdba74;' +
      'backdrop-filter:blur(8px);padding:6px 18px;border-radius:0 0 10px 10px;font-size:12.5px;font-weight:600';
    document.body.appendChild(el);
  }
  el.textContent = msg;
}

function updateApprovalBadge() {
  const n = (state.approvals || []).length;
  const b = $('#apprBadge');
  if (!b) return;
  if (n > 0) { b.textContent = n; b.style.display = 'inline-block'; }
  else { b.style.display = 'none'; }
}

async function tick() {
  if (currentView === 'jarvis') return; // JARVIS manages its own updates
  try {
    state.stats = await api('GET', '/api/stats');
    state.activity = await api('GET', '/api/activity');
    if (currentView === 'agents' || currentView === 'dashboard') {
      state.agents = await api('GET', '/api/agents');
    }
    if (pendingRender && !uiLocked()) { pendingRender = false; render(); updateSidebarMini(); return; }
    if (currentView === 'dashboard') {
      updateDashboardInPlace();
    } else if (currentView === 'agents') {
      renderAgentsView(); // in-place patcher once built
    } else if (currentView === 'kanban') {
      const tasks = await api('GET', '/api/tasks');
      const j = JSON.stringify(tasks);
      if (j !== lastTasksJSON) {
        state.tasks = tasks; lastTasksJSON = j;
        if (!uiLocked()) render();
      }
    } else if (currentView === 'agentic') {
      await loadAgenticData();
      const j = JSON.stringify([state.verifyRuns, state.approvals, state.schedulerJobs, state.watchdog]);
      if (j !== lastAgenticJSON) {
        lastAgenticJSON = j;
        if (!uiLocked()) render();
      }
    } else if (currentView === 'workflows') {
      // Lane workers are separate processes — their task-status writes never
      // arrive via WS, so Projects must poll like the kanban does.
      const wfs = await api('GET', '/api/workflows');
      const j = JSON.stringify(wfs);
      if (j !== lastWorkflowsJSON) {
        lastWorkflowsJSON = j;
        wfState.list = wfs.workflows || [];
        wfState.fetched = true;
        if (!uiLocked()) render();
      }
    }
    // monitor updates itself via its own interval; static views don't tick
    updateSidebarMini();
    // quota banner is global — poll it every ~15s regardless of view
    quotaTickCounter = (quotaTickCounter + 1) % 5;
    if (quotaTickCounter === 0) {
      state.quota = await api('GET', '/api/quota');
      updateQuotaBanner();
      updateModelStrip();
    }
  } catch (e) { /* ignore transient */ }
}
let quotaTickCounter = 0;

// ===== VIEW ROUTER =====
const VIEW_META = {
  dashboard: ['Dashboard', 'Mission control — live overview of your agent OS'],
  kanban: ['Tasks', 'The task board: plan, assign and track every unit of work'],
  workflows: ['Workflows', 'Rounds of work: multi-task runs that visit your projects — dependencies run in order, outputs feed forward'],
  deliverables: ['Deliverables', 'Every agent output in one place — read, download, chain'],
  meetings: ['Meetings', 'Dictation MeetingMode transcripts — watch them live, read, manage'],
  agents: ['Agent Fleet', 'Click any agent for memory, messages & cost'],
  agentic: ['Agentic Capabilities', 'Approvals · verification · scheduling · self-healing · cost control'],
  specialists: ['Specialist Agents', 'Reusable experts — and how each one learns'],
  memory: ['Memory Hub', 'Everything your agents remember, in one place'],
  skills: ['Skills', 'Reusable skill library'],
  monitor: ['System Monitor', 'Live host telemetry'],
  tools: ['Tools Hub', 'Connected tools & integration health'],
  programs: ['Programs', 'Registered workloads'],
  projects: ['Projects', 'Your durable projects — client and personal, with backup & delivery workflow'],
  guardian: ['Guardian', 'Change protection & automatic drift repair'],
  usage: ['Usage & Cost', 'Token consumption & estimated spend'],
  observability: ['LLM Observability', 'Traces, tokens & cost via Langfuse'],
  issues: ['Known Issues', 'Your filed feedback with the interaction context — the improvement backlog'],
  settings: ['Settings', 'Budgets, concurrency limits and per-model effort defaults'],
  manual: ['User Manual', 'Everything explained — from first click to full architecture'],
  jarvis: ['J.A.R.V.I.S', 'Neural voice interface'],
};

function switchView(view) {
  if (currentView === 'dashboard' && view !== 'dashboard' && window.Memory3D) {
    window.Memory3D.dispose(); // the galaxy is the dashboard centerpiece now
  }
  if (currentView === 'memory' && view !== 'memory' && window.Memory3D) {
    window.Memory3D.dispose();
  }
  if (currentView === 'jarvis' && view !== 'jarvis') {
    jarvisViewDetach();   // visual-only: the live turn + TTS keep running (Option C)
  }
  currentView = view;
  agentsBuilt = false;
  dashBuilt = false;
  monBuilt = false;
  // Entering Specialists refetches: the reflect timer drafts new pending
  // lessons between visits, and a once-only fetch would never show them.
  if (view === 'specialists') specialistsState.fetched = false;
  // Same for Projects: task statuses move while the view is closed.
  if (view === 'workflows') { wfState.fetched = false; lastWorkflowsJSON = ''; }
  closeDrawer();
  $$('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  const meta = VIEW_META[view] || [view, ''];
  $('#pageTitle').textContent = meta[0];
  const sub = $('#pageSub');
  if (sub) sub.textContent = meta[1];
  render();
}

function render() {
  const c = $('#content');
  if (currentView === 'dashboard') { renderDashboard(); }
  else if (currentView === 'tools') { c.innerHTML = wrapView(viewTools()); bindTools(); }
  else if (currentView === 'skills') { c.innerHTML = wrapView(viewSkills()); bindSkills(); }
  else if (currentView === 'projects') { c.innerHTML = wrapView(viewProjects()); bindProjects(); }
  else if (currentView === 'usage') { c.innerHTML = wrapView(viewUsage()); bindUsage(); }
  else if (currentView === 'settings') { c.innerHTML = wrapView(viewSettings()); bindSettings(); }
  else if (currentView === 'issues') { c.innerHTML = wrapView(viewKnownIssues()); }
  else if (currentView === 'manual') { c.innerHTML = wrapView(viewManual()); }
  else if (currentView === 'observability') { c.innerHTML = wrapView(viewObservability()); bindObservability(); }
  else if (currentView === 'memory') { c.innerHTML = wrapView(viewMemory()); bindMemory(); }
  else if (currentView === 'specialists') { c.innerHTML = wrapView(viewSpecialists()); bindSpecialists(); }
  else if (currentView === 'guardian') { c.innerHTML = wrapView(viewGuardian()); bindGuardian(); }
  else if (currentView === 'kanban') { c.innerHTML = wrapView(viewKanban()); bindKanban(); }
  else if (currentView === 'agents') { renderAgentsView(); }
  else if (currentView === 'programs') { c.innerHTML = wrapView(viewPrograms()); }
  else if (currentView === 'monitor') { c.innerHTML = wrapView(viewMonitor()); bindMonitorCharts(); }
  else if (currentView === 'agentic') { c.innerHTML = wrapView(viewAgentic()); bindAgentic(); }
  else if (currentView === 'workflows') { c.innerHTML = wrapView(viewWorkflows()); bindWorkflows(); }
  else if (currentView === 'deliverables') { c.innerHTML = wrapView(viewDeliverables()); bindDeliverables(); }
  else if (currentView === 'meetings') { c.innerHTML = wrapView(viewMeetings()); bindMeetings(); }
  else if (currentView === 'jarvis') { renderJarvisView(); }
  updateSidebarMini();
}

function wrapView(html) { return `<div class="view">${html}</div>`; }

// ═══════════════════════════════ DASHBOARD ═══════════════════════════════
function renderDashboard() {
  const c = $('#content');
  if (!dashBuilt) {
    c.innerHTML = wrapView(viewDashboard());
    dashBuilt = true;
    mountDashGalaxy(0);
    bindHeroExpand();
    animateStatValues();
    loadOnboardingCta();
  } else {
    updateDashboardInPlace();
  }
}

// The dashboard centerpiece IS the live memory galaxy (same engine as the
// Memory hub's 3D map — the hub keeps the full tooling: search, regions list)
async function mountDashGalaxy(tries) {
  const el = document.getElementById('dashGalaxy');
  if (!el || currentView !== 'dashboard') return;
  if (!window.Memory3D) {
    if (tries < 24) setTimeout(() => mountDashGalaxy(tries + 1), 250);
    else { const fb = document.getElementById('heroFallback'); if (fb) fb.style.display = 'flex'; }
    return;
  }
  try {
    const data = await api('GET', '/api/memory3d');
    if (!document.getElementById('dashGalaxy') || currentView !== 'dashboard') return;
    if (data.nodes && data.nodes.length) {
      window.Memory3D.mount(el, data, { onSelect: openMemoryNodeModal });
      const hc = document.getElementById('heroMemCount');
      if (hc) hc.textContent = `${data.count} memories`;
    } else {
      const fb = document.getElementById('heroFallback');
      if (fb) fb.style.display = 'flex';
    }
  } catch {
    const fb = document.getElementById('heroFallback');
    if (fb) fb.style.display = 'flex';
  }
}

function bindHeroExpand() {
  const hero = document.getElementById('dashHero');
  const btn = document.getElementById('heroExpand');
  const c = $('#content');
  if (!hero || !btn) return;
  const set = (on) => {
    hero.classList.toggle('expanded', on);
    if (on) c.scrollTop = 0;
  };
  btn.onclick = () => set(!hero.classList.contains('expanded'));
  document.addEventListener('keydown', function esc(e) {
    if (e.key === 'Escape') set(false);
    if (currentView !== 'dashboard') document.removeEventListener('keydown', esc);
  });
  // Scrolling up at the top of the page grows the galaxy to the full mid
  // section (the widgets slide down out of the way); the ⛶ restores.
  c.addEventListener('wheel', (e) => {
    if (currentView !== 'dashboard') return;
    if (e.target.closest('#dashGalaxy')) return; // over the galaxy = zoom
    if (e.deltaY < 0 && c.scrollTop <= 2) set(true);
  }, { passive: true });
}

// X4 → SPEC-ONBOARDING: call-to-action opens the IN-APP guided onboarding
async function loadOnboardingCta() {
  const box = $('#onboardingCta');
  if (!box) return;
  try {
    const s = await api('GET', '/api/onboarding-status');
    if (s.done || !box.isConnected) { box.innerHTML = ''; return; }
    box.innerHTML = `
      <div style="margin:14px 0;padding:12px 16px;border:1px solid rgba(251,146,60,.4);
                  background:rgba(251,146,60,.08);border-radius:12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <span style="font-size:20px">🧭</span>
        <div style="flex:1;min-width:240px">
          <div style="font-weight:700;font-size:13.5px">Your Business Brain isn't personalized yet — ${s.total} blanks to fill</div>
          <div style="font-size:12px;color:var(--text-dim)">Agents work from placeholder context until then. ${esc(s.cta || '')} Answers save as you go — pause anytime.</div>
        </div>
        <button class="btn-primary" onclick="openOnboardingWizard()">🚀 Start the guided onboarding</button>
      </div>`;
  } catch { /* optional widget */ }
}

// ═══════ Business-Brain onboarding wizard (SPEC-ONBOARDING R4) ═══════
// step 0 = welcome · 1..S = sections · S+1 = review · after apply = success
let _onb = null;

async function openOnboardingWizard() {
  showModal(`<h2>🧭 Business Brain onboarding</h2>
    <div class="loading" style="padding:40px;text-align:center">Loading your questionnaire…</div>`);
  try {
    const d = await api('GET', '/api/onboarding');
    _onb = { d, step: 0 };
    renderOnbWizard();
  } catch (e) {
    showModal(`<h2>🧭 Onboarding</h2><div class="empty">${esc(e.message)}</div>
      <div class="modal-actions"><button class="btn-primary" onclick="closeModal()">Close</button></div>`);
  }
}

function onbAnsweredCount() {
  return Object.values(_onb.d.answers).filter(a => a.na || (a.text || '').trim()).length;
}

function onbHeaderHTML() {
  const { d, step } = _onb;
  const S = d.sections.length;
  const answered = onbAnsweredCount();
  const where = step === 0 ? 'Welcome' : step > S ? 'Review & apply'
    : `Section ${step}/${S}`;
  return `
    <h2 style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">🧭 Business Brain onboarding
      <span class="chip">${esc(where)}</span>
      <span class="chip c-accent">${answered}/${d.total} answered</span></h2>
    <div class="onb-progress" style="margin:4px 0 14px"><i style="width:${Math.round(100 * answered / d.total)}%"></i></div>`;
}

function onbWelcomeHTML() {
  const { d } = _onb;
  const landing = d.is_owner
    ? `Because you are the <b>owner</b>, your answers become the <b>canonical business identity</b> —
       written to <code>${esc(d.target_dir)}</code> (git-versioned; nothing is ever lost), read by every
       agent, the frontier judge and the eval runner.`
    : `Your answers become <b>your personal business context</b> — written to
       <code>${esc(d.target_dir)}</code>. Tasks <b>you</b> create use <i>your</i> answers; the owner's
       canonical files stay untouched. Each user onboards for themselves.`;
  return `
    <div class="view-intro" style="font-size:13px;line-height:1.6">
      👋 Nexus agents can draft marketing, shop copy, proposals, release plans and more — but they are only
      as sharp as what they know about <b>your</b> business. That knowledge is the <b>Business Brain</b>:
      two files every agent reads before business work.
    </div>
    <div class="onb-q"><b>1 · BUSINESS-CONTEXT.md</b> — who you are, what you sell, to whom.
      <div class="onb-hint">Agents ground every claim, plan and price on these lines. While a line is blank they must
      work from clearly-marked generic assumptions.</div></div>
    <div class="onb-q"><b>2 · STYLE-VOICE.md</b> — how everything you publish sounds.
      <div class="onb-hint">Every outward-facing text is written against this voice, and the frontier judge scores
      deliverables on it.</div></div>
    <div class="onb-explain">📍 <b>Where your answers land:</b> ${landing}</div>
    <div class="onb-explain" style="border-color:rgba(124,92,255,.3);background:rgba(124,92,255,.07)">
      ⏱ <b>How it works:</b> one short section at a time (~15 min total). Every section explains what the answers
      change in the system. Answers <b>save every time you hit Next</b> — close this window whenever you like and
      resume later from the same spot. Short and true beats polished and vague; mark anything that doesn't apply
      as “not applicable” and skip what you don't know yet.</div>`;
}

function onbSectionHTML(sec, prevSec) {
  const { d } = _onb;
  const fileIntro = (!prevSec || prevSec.file !== sec.file)
    ? `<div class="onb-explain" style="border-color:rgba(124,92,255,.3);background:rgba(124,92,255,.07)">📘 <b>${esc(sec.file_name)}</b> — ${esc(sec.file_intro)}</div>` : '';
  const qs = sec.questions.map(q => {
    const a = d.answers[q.slot_id] || { text: '', na: false };
    return `
      <div class="onb-q ${a.na ? 'na' : ''}" id="onbq-${esc(q.slot_id.replace(':', '-'))}">
        <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">
          <b style="font-size:12.5px;flex:1">${esc(q.label)}</b>
          <label style="font-size:11px;color:var(--text-dim);display:flex;gap:5px;align-items:center;cursor:pointer">
            <input type="checkbox" class="onb-na" data-sid="${esc(q.slot_id)}" ${a.na ? 'checked' : ''}
              onchange="this.closest('.onb-q').classList.toggle('na', this.checked)"> not applicable</label>
        </div>
        ${q.hint ? `<div class="onb-hint">e.g. ${esc(q.hint)}</div>` : ''}
        <textarea class="onb-input" data-sid="${esc(q.slot_id)}" rows="2"
          placeholder="${esc(q.hint || 'Your answer…')}">${esc(a.text || '')}</textarea>
      </div>`;
  }).join('');
  return `
    ${fileIntro}
    <h3 class="section-title" style="margin-top:2px">${esc(sec.title)} <span class="chip" style="margin-left:6px">${esc(sec.file_name)}</span></h3>
    <div class="onb-explain">💡 <b>What these answers change:</b> ${esc(sec.explain)}</div>
    ${qs}`;
}

function onbReviewHTML() {
  const { d } = _onb;
  const rows = d.sections.map((sec, i) => {
    let ans = 0, na = 0, open = 0;
    const missing = [];
    sec.questions.forEach(q => {
      const a = d.answers[q.slot_id];
      if (a && a.na) na++;
      else if (a && (a.text || '').trim()) ans++;
      else { open++; missing.push(q.label); }
    });
    return `
      <div class="agentic-row" style="cursor:pointer" onclick="onbGoto(${i + 1})">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <strong style="flex:1">${esc(sec.title)}</strong>
          ${ans ? `<span class="chip c-green">${ans} answered</span>` : ''}
          ${na ? `<span class="chip">${na} n/a</span>` : ''}
          ${open ? `<span class="chip c-orange">${open} open</span>` : '<span class="chip c-green">✓ complete</span>'}
        </div>
        ${open ? `<div class="onb-hint" style="margin-top:3px">open: ${esc(missing.slice(0, 3).join(' · '))}${missing.length > 3 ? ' …' : ''}</div>` : ''}
      </div>`;
  }).join('');
  const answered = onbAnsweredCount();
  return `
    <div class="view-intro">Review before writing. Click a section to jump back and change answers — nothing is
    written until you hit Apply.</div>
    <div style="display:flex;flex-direction:column;gap:6px;max-height:44vh;overflow-y:auto;margin-bottom:12px">${rows}</div>
    <div class="onb-explain">📍 Apply writes <b>${answered}/${d.total}</b> answers into
      <code>${esc(d.target_dir)}</code> ${_onb.d.is_owner ? '(the canonical Business Brain, git-committed)' : '(your personal context, git-committed)'} —
      open slots simply stay open; you can return anytime. From the moment you apply,
      ${_onb.d.is_owner ? 'every agent' : 'every task you own'} works with this context.</div>`;
}

function onbSuccessHTML(res) {
  return `
    <div class="empty" style="padding:18px"><span class="e-ico">🎉</span>
      <b>Your Business Brain is live.</b></div>
    <div class="onb-q"><b>${res.replaced}</b> answers written · <b>${res.remaining}</b> slots still open
      <div class="onb-hint">${(res.written || []).map(esc).join('<br>')}${res.git_committed ? '<br>✓ git-committed (nothing is ever lost)' : ''}</div></div>
    <div class="onb-explain">🚀 <b>What improves right now:</b> business deliverables
      ${_onb.d.is_owner ? '' : 'on your tasks '}are grounded on your real ventures, audience and constraints;
      outward-facing text follows your voice and brand overrides; the judge scores against <i>your</i> quarter goals.</div>
    <div class="onb-explain" style="border-color:rgba(124,92,255,.3);background:rgba(124,92,255,.07)">
      💡 <b>Feel the difference:</b> create a task in a business domain (Kanban → “✨ Describe a task”, e.g.
      “write a product page for our best seller”) and compare it with what you got before. Revise answers anytime
      via Settings → Business Brain.</div>`;
}

function renderOnbWizard() {
  const { d, step } = _onb;
  const S = d.sections.length;
  let body, buttons;
  if (_onb.success) {
    body = onbSuccessHTML(_onb.success);
    buttons = `<button class="btn-primary" onclick="closeModal();loadOnboardingCta()">Done</button>`;
  } else if (step === 0) {
    body = onbWelcomeHTML();
    buttons = `<button class="btn-ghost" onclick="closeModal()">Later</button>
      <button class="btn-primary" onclick="onbNext()">Let's go →</button>`;
  } else if (step > S) {
    body = onbReviewHTML();
    buttons = `<button class="btn-ghost" onclick="onbBack()">← Back</button>
      <button class="btn-ghost" onclick="closeModal()">Save & close</button>
      <button class="btn-primary" onclick="onbApply()">✅ Apply to the Business Brain</button>`;
  } else {
    body = onbSectionHTML(d.sections[step - 1], d.sections[step - 2]);
    buttons = `<button class="btn-ghost" onclick="onbBack()">← Back</button>
      <button class="btn-ghost" onclick="onbSaveClose()">Save & close</button>
      <button class="btn-primary" onclick="onbNext()">${step === S ? 'Review →' : 'Next →'}</button>`;
  }
  showModal(`${onbHeaderHTML()}
    <div style="max-height:58vh;overflow-y:auto;padding-right:4px">${body}</div>
    <div class="modal-actions">${buttons}</div>`);
  const first = document.querySelector('.onb-input');
  if (first && step > 0 && step <= S) first.focus();
}

async function onbCollectSave() {
  const inputs = [...document.querySelectorAll('.onb-input')];
  if (!inputs.length) return true;
  const answers = {};
  inputs.forEach(t => {
    const sid = t.dataset.sid;
    const na = document.querySelector(`.onb-na[data-sid="${CSS.escape(sid)}"]`)?.checked || false;
    answers[sid] = { text: t.value.trim(), na };
    if (!answers[sid].text && !na) _onb.d.answers[sid] ? delete _onb.d.answers[sid] : null;
    else _onb.d.answers[sid] = { text: answers[sid].text, na };
  });
  try {
    await api('POST', '/api/onboarding/answers', { answers });
    return true;
  } catch (e) { toast('Could not save: ' + e.message, 'err'); return false; }
}

async function onbNext() { if (await onbCollectSave()) { _onb.step++; renderOnbWizard(); } }
async function onbBack() { if (await onbCollectSave()) { _onb.step = Math.max(0, _onb.step - 1); renderOnbWizard(); } }
async function onbGoto(i) { _onb.step = i; renderOnbWizard(); }
async function onbSaveClose() {
  if (await onbCollectSave()) { toast('Progress saved — resume anytime from the dashboard banner or Settings → Business Brain', 'ok'); closeModal(); }
}

async function onbApply() {
  const target = _onb.d.is_owner ? 'the CANONICAL Business Brain (all agents)' : 'YOUR personal business context';
  if (!confirm(`Write ${onbAnsweredCount()} answers to ${target}?\n\nOpen slots stay open, the previous state is git-committed first — nothing is lost.`)) return;
  try {
    const res = await api('POST', '/api/onboarding/apply');
    _onb.success = res;
    renderOnbWizard();
    loadOnboardingCta();
  } catch (e) { toast('Apply failed: ' + e.message, 'err'); }
}

function mountNexus3D(tries) {
  const cv = document.getElementById('nexus3d');
  if (!cv || currentView !== 'dashboard') return;
  if (window.Nexus3D) {
    window.Nexus3D.mount(cv, state.agents).then(ok => {
      if (!ok) {
        const fb = document.getElementById('heroFallback');
        if (fb) fb.style.display = 'flex';
      }
    });
  } else if (tries < 24) {
    setTimeout(() => mountNexus3D(tries + 1), 250);
  } else {
    const fb = document.getElementById('heroFallback');
    if (fb) fb.style.display = 'flex';
  }
}

function animateStatValues() {
  $$('.stat-value[data-count]').forEach(el => {
    const target = parseFloat(el.dataset.count) || 0;
    const suffix = el.dataset.suffix || '';
    const t0 = performance.now(), dur = 650;
    const step = (t) => {
      const p = Math.min(1, (t - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = (target >= 100 ? Math.round(target * eased) : (target * eased).toFixed(target % 1 ? 1 : 0)) + suffix;
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

function dashKPIs() {
  const s = state.stats, ag = s.agents || {}, tk = s.tasks || {}, tp = s.throughput || {}, tokens = s.tokens || {};
  return { ag, tk, tp, tokens };
}

function nowRunningHTML() {
  const live = (state.agents || []).filter(a => a.status === 'running' || a.status === 'busy');
  if (!live.length) return '<div class="now-empty">No agent is executing right now</div>';
  return live.map(a => `
    <div class="now-row" onclick="openAgentDrawer('${esc(a.id)}')">
      <div class="nr-head"><span class="status-dot ${a.status === 'busy' ? 'busy' : 'online'}"></span>${esc(a.name)}
        <span class="chip ${a.status === 'busy' ? 'c-yellow' : 'c-green'}" style="margin-left:auto">${esc(a.status)}</span></div>
      <div class="nr-task">${esc(a.current_task || 'Standing by')}</div>
      <div class="nr-meta">♥ ${fmtAgo(a.last_heartbeat)} · ↓${fmtTokens(a.tokens_in || 0)} ↑${fmtTokens(a.tokens_out || 0)}</div>
    </div>`).join('');
}

function rosterHTML() {
  return (state.agents || []).map(a => {
    const prog = (state.programs || []).find(p => p.id === a.program_id);
    const curTask = a.current_task || 'Idle';
    return `
      <div class="roster-row" onclick="openAgentDrawer('${esc(a.id)}')">
        <div class="roster-status"><span class="status-dot ${a.status === 'running' ? 'online' : a.status === 'busy' ? 'busy' : ''}" style="background:${statusColor(a.status)}"></span></div>
        <div class="roster-name">${esc(a.name)}</div>
        <div class="roster-role">${esc(a.role)}</div>
        <div class="roster-task" title="${esc(curTask)}">${esc(curTask)}</div>
        <div class="roster-prog">${prog ? esc(prog.name) : '--'}</div>
        <div class="roster-tokens"><span class="tok-in">↓${fmtTokens(a.tokens_in || 0)}</span><span class="tok-out">↑${fmtTokens(a.tokens_out || 0)}</span></div>
        <div class="roster-badge"><span class="agent-status-badge status-${esc(a.status)}">${esc(a.status)}</span></div>
      </div>`;
  }).join('') || '<div class="empty">No agents</div>';
}

function activityHTML() {
  return (state.activity || []).slice(0, 12).map(a => `
    <div class="activity-item">
      <span class="activity-time">${fmtAgo(a.ts)}</span>
      <span class="activity-level ${esc(a.level)}"></span>
      <span class="activity-msg"><span class="activity-source">${esc(a.source)}</span> ${esc(a.message)}</span>
    </div>`).join('') || '<div class="empty">No activity</div>';
}

function distListHTML(byStatus, colors) {
  return Object.entries(byStatus || {}).map(([k, v]) => `
    <div style="display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:7px;">
      <span style="width:8px;height:8px;border-radius:50%;background:${colors[k] || '#888'};box-shadow:0 0 6px ${colors[k] || '#888'}"></span>
      <span style="text-transform:capitalize">${esc(k).replace('_', ' ')}</span>
      <span style="margin-left:auto;font-weight:700;font-family:var(--font-mono)">${v}</span>
    </div>`).join('');
}

const AGENT_STATUS_COLORS = { running: 'var(--green)', busy: 'var(--yellow)', idle: 'var(--text-dim)', stopped: 'var(--red)', crashed: 'var(--orange)' };
const TASK_STATUS_COLORS = { backlog: 'var(--text-dim)', todo: 'var(--blue)', in_progress: 'var(--yellow)', review: 'var(--orange)', done: 'var(--green)' };

function viewDashboard() {
  const s = state.stats;
  const sys = s.system || {};
  const { ag, tk, tp, tokens } = dashKPIs();
  const cpuPct = sys.cpu_percent ? sys.cpu_percent.toFixed(0) : 0;
  const memPct = sys.mem_percent ? sys.mem_percent.toFixed(0) : 0;
  const diskPct = sys.disk_percent ? sys.disk_percent.toFixed(0) : 0;
  const liveCount = (state.agents || []).filter(a => a.status === 'running' || a.status === 'busy').length;

  return `
    <div class="hero-3d" id="dashHero">
      <div id="dashGalaxy" style="position:absolute;inset:0"></div>
      <div class="hero-fallback" id="heroFallback" style="display:none"><div class="hero-orb"></div></div>
      <div class="hero-overlay" style="pointer-events:none">
        <div class="hero-kicker">Neural Memory · Live</div>
        <div class="hero-title"><span id="heroMemCount">—</span><small id="heroLive">${liveCount} agents active · ${(state.agents || []).length} total</small></div>
      </div>
      <button class="hero-expand" id="heroExpand" title="Expand the memory galaxy — Esc or click again to restore">⛶</button>
      <div class="now-strip">
        <div class="now-title"><span class="status-dot online"></span> Executing right now</div>
        <div id="nowStrip">${nowRunningHTML()}</div>
      </div>
    </div>

    <div id="onboardingCta"></div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-head"><span class="stat-label">Active Agents</span><span class="stat-ico">${NICO.agents}</span></div>
        <div class="stat-value" data-count="${ag.total || 0}" id="kpiAgents">0</div>
        <div class="stat-sub" id="kpiAgentsSub">${(ag.by_status || {}).running || 0} running · ${(ag.by_status || {}).idle || 0} idle</div>
      </div>
      <div class="stat-card green">
        <div class="stat-head"><span class="stat-label">Total Tasks</span><span class="stat-ico">${NICO.tasks}</span></div>
        <div class="stat-value" data-count="${tk.total || 0}" id="kpiTasks">0</div>
        <div class="stat-sub" id="kpiTasksSub">${(tk.by_status || {}).done || 0} done · ${(tk.by_status || {}).in_progress || 0} in progress</div>
      </div>
      <div class="stat-card blue">
        <div class="stat-head"><span class="stat-label">Token Usage</span><span class="stat-ico">${NICO.tokens}</span></div>
        <div class="stat-value" id="kpiTokens">${fmtTokens((tokens.total_in || 0) + (tokens.total_out || 0))}</div>
        <div class="stat-sub" id="kpiTokensSub">↓${fmtTokens(tokens.total_in || 0)} in · ↑${fmtTokens(tokens.total_out || 0)} out</div>
      </div>
      <div class="stat-card orange">
        <div class="stat-head"><span class="stat-label">Tasks Completed</span><span class="stat-ico">${NICO.done}</span></div>
        <div class="stat-value" data-count="${tp.tasks_completed || 0}" id="kpiDone">0</div>
        <div class="stat-sub" id="kpiDoneSub">${tp.tasks_failed || 0} failed</div>
      </div>
    </div>

    <div class="dash-row">
      <div class="panel">
        <div class="panel-header"><span class="panel-title">System Resources</span></div>
        <div class="panel-body">
          <div class="gauge-container" id="gaugeWrap">
            ${gauge('CPU', cpuPct, '#7c5cff', 'gCpu')}
            ${gauge('MEM', memPct, '#5eead4', 'gMem')}
            ${gauge('DISK', diskPct, '#fb923c', 'gDisk')}
          </div>
          <div style="font-size:11px;color:var(--text-faint);text-align:center;margin-top:10px;font-family:var(--font-mono)" id="sysLine">
            ${sys.cpu_count || 0} cores · ${sys.mem_total_gb || 0}GB RAM · Load ${(sys.load_avg || [0, 0, 0]).join(' / ')}
          </div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header"><span class="panel-title">Fleet & Task Mix</span></div>
        <div class="panel-body" style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
          <div><div style="font-size:10px;color:var(--text-faint);letter-spacing:1.5px;margin-bottom:9px">AGENTS</div><div id="agStatusList">${distListHTML(ag.by_status, AGENT_STATUS_COLORS) || '<div class="empty">No agents</div>'}</div></div>
          <div><div style="font-size:10px;color:var(--text-faint);letter-spacing:1.5px;margin-bottom:9px">TASKS</div><div id="taskDist">${distListHTML(tk.by_status, TASK_STATUS_COLORS) || '<div class="empty">No tasks</div>'}</div></div>
        </div>
      </div>
    </div>

    <div class="panel" style="margin-bottom:20px;">
      <div class="panel-header">
        <span class="panel-title">Agent Roster</span>
        <span style="font-size:10px;color:var(--text-faint);font-family:var(--font-mono)" id="rosterCount">LIVE · ${state.agents.length} AGENTS</span>
      </div>
      <div class="panel-body" style="padding:0;">
        <div class="roster-table">
          <div class="roster-header-row">
            <div class="roster-status"></div><div class="roster-name">Agent</div><div class="roster-role">Role</div>
            <div class="roster-task">Current Task</div><div class="roster-prog">Program</div>
            <div class="roster-tokens">Tokens</div><div class="roster-badge">Status</div>
          </div>
          <div id="rosterBody">${rosterHTML()}</div>
        </div>
      </div>
    </div>

    <div class="panel" style="margin-bottom:20px;">
      <div class="panel-header"><span class="panel-title">Recent Activity</span></div>
      <div class="panel-body"><div class="activity-list" id="actList">${activityHTML()}</div></div>
    </div>
  `;
}

function updateDashboardInPlace() {
  if (!dashBuilt || currentView !== 'dashboard') return;
  const s = state.stats;
  const sys = s.system || {};
  const { ag, tk, tp, tokens } = dashKPIs();
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set('kpiAgents', ag.total || 0);
  set('kpiAgentsSub', `${(ag.by_status || {}).running || 0} running · ${(ag.by_status || {}).idle || 0} idle`);
  set('kpiTasks', tk.total || 0);
  set('kpiTasksSub', `${(tk.by_status || {}).done || 0} done · ${(tk.by_status || {}).in_progress || 0} in progress`);
  set('kpiTokens', fmtTokens((tokens.total_in || 0) + (tokens.total_out || 0)));
  set('kpiTokensSub', `↓${fmtTokens(tokens.total_in || 0)} in · ↑${fmtTokens(tokens.total_out || 0)} out`);
  set('kpiDone', tp.tasks_completed || 0);
  set('kpiDoneSub', `${tp.tasks_failed || 0} failed`);
  set('sysLine', `${sys.cpu_count || 0} cores · ${sys.mem_total_gb || 0}GB RAM · Load ${(sys.load_avg || [0, 0, 0]).join(' / ')}`);
  set('rosterCount', `LIVE · ${state.agents.length} AGENTS`);
  const liveCount = (state.agents || []).filter(a => a.status === 'running' || a.status === 'busy').length;
  set('heroLive', `${liveCount} active now`);
  updateGauge('gCpu', sys.cpu_percent || 0);
  updateGauge('gMem', sys.mem_percent || 0);
  updateGauge('gDisk', sys.disk_percent || 0);
  const now = document.getElementById('nowStrip'); if (now) now.innerHTML = nowRunningHTML();
  const rb = document.getElementById('rosterBody'); if (rb) rb.innerHTML = rosterHTML();
  const al = document.getElementById('actList'); if (al) al.innerHTML = activityHTML();
  const asl = document.getElementById('agStatusList'); if (asl) asl.innerHTML = distListHTML(ag.by_status, AGENT_STATUS_COLORS) || '<div class="empty">No agents</div>';
  const td = document.getElementById('taskDist'); if (td) td.innerHTML = distListHTML(tk.by_status, TASK_STATUS_COLORS) || '<div class="empty">No tasks</div>';
}

function gauge(label, pct, color, id) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - pct / 100);
  return `
    <div class="gauge">
      <svg width="130" height="130">
        <circle class="gauge-bg" cx="65" cy="65" r="${r}" fill="none" stroke-width="8"/>
        <circle class="gauge-fg" id="${id}Fg" cx="65" cy="65" r="${r}" fill="none" stroke="${color}" stroke-width="8"
          stroke-dasharray="${c}" stroke-dashoffset="${offset}"/>
      </svg>
      <div class="gauge-val" id="${id}Val">${pct}%</div>
      <div class="gauge-label">${label}</div>
    </div>
  `;
}

function updateGauge(id, pct) {
  const r = 52, c = 2 * Math.PI * r;
  const fg = document.getElementById(`${id}Fg`);
  const val = document.getElementById(`${id}Val`);
  if (fg) fg.style.strokeDashoffset = c * (1 - pct / 100);
  if (val) val.textContent = `${Math.round(pct)}%`;
}

// ═══════════════════════════════ KANBAN ═══════════════════════════════
const KANBAN_COLS = [
  { id: 'backlog', name: 'Backlog', color: 'var(--text-dim)' },
  { id: 'todo', name: 'To Do', color: 'var(--blue)' },
  { id: 'in_progress', name: 'In Progress', color: 'var(--yellow)' },
  { id: 'review', name: 'Review', color: 'var(--orange)' },
  { id: 'done', name: 'Done', color: 'var(--green)' },
];

function kanbanTagUniverse() {
  const set = new Set();
  (state.tasks || []).forEach(t => {
    try { JSON.parse(t.tags || '[]').forEach(x => set.add(x)); } catch { /* skip */ }
  });
  return [...set].sort();
}

function taskMatchesFilters(t) {
  if (!taskInFocus(t)) return false; // global focus context scopes first
  const f = kanbanFilters;
  if (f.q) {
    const q = f.q.toLowerCase();
    if (!(t.title || '').toLowerCase().includes(q) && !(t.description || '').toLowerCase().includes(q)) return false;
  }
  if (f.assignee && t.assignee_id !== f.assignee) return false;
  if (f.workflow === '__none__') { if (t.workflow_id) return false; }
  else if (f.workflow && t.workflow_id !== f.workflow) return false;
  if (f.priority !== '' && String(t.priority) !== f.priority) return false;
  if (f.tag) {
    try { if (!JSON.parse(t.tags || '[]').includes(f.tag)) return false; } catch { return false; }
  }
  return true;
}

// Options for the project filter — also used by loadWorkflows() to fill the
// select in place when the async fetch lands after the first kanban paint.
function kanbanWorkflowOptions() {
  const cur = kanbanFilters.workflow;
  return `<option value="">All projects</option>
        <option value="__none__" ${cur === '__none__' ? 'selected' : ''}>— No project —</option>
        ${(wfState.list || []).map(w => `<option value="${esc(w.id)}" ${cur === w.id ? 'selected' : ''}>⚑ ${esc(w.name)}</option>`).join('')}`;
}

function viewKanban() {
  if (!wfState.fetched) loadWorkflows(); // project names for the filter (fills it when loaded)
  const agentOpts = (state.agents || []).map(a => `<option value="${esc(a.id)}" ${kanbanFilters.assignee === a.id ? 'selected' : ''}>${esc(a.name)}</option>`).join('');
  const tagOpts = kanbanTagUniverse().map(t => `<option value="${esc(t)}" ${kanbanFilters.tag === t ? 'selected' : ''}>${esc(t)}</option>`).join('');
  const filtered = (state.tasks || []).filter(taskMatchesFilters);
  const hasFilter = kanbanFilters.q || kanbanFilters.assignee || kanbanFilters.priority !== '' && kanbanFilters.priority !== '' || kanbanFilters.tag || kanbanFilters.workflow;

  return `
    <div class="kanban-toolbar">
      <input class="k-search" id="kSearch" type="search" placeholder="Search tasks…" value="${esc(kanbanFilters.q)}">
      <select class="k-filter" id="kWorkflow" title="Show only one project's tasks">
        ${kanbanWorkflowOptions()}</select>
      <select class="k-filter" id="kAssignee"><option value="">All assignees</option>${agentOpts}</select>
      <select class="k-filter" id="kPriority">
        <option value="">All priorities</option>
        <option value="0" ${kanbanFilters.priority === '0' ? 'selected' : ''}>Critical</option>
        <option value="1" ${kanbanFilters.priority === '1' ? 'selected' : ''}>High</option>
        <option value="2" ${kanbanFilters.priority === '2' ? 'selected' : ''}>Normal</option>
        <option value="3" ${kanbanFilters.priority === '3' ? 'selected' : ''}>Low</option>
      </select>
      <select class="k-filter" id="kTag"><option value="">All tags</option>${tagOpts}</select>
      ${hasFilter ? `<button class="btn-ghost" id="kClear">Clear</button>` : ''}
      <span class="muted" style="margin-left:auto;font-family:var(--font-mono);font-size:11px">${filtered.length}/${(state.tasks || []).length} tasks</span>
      <button class="btn-ghost" title="Describe it in plain words — the AI fills in every parameter" onclick="describeTaskUI()">✨ Describe a task</button>
      <button class="btn-primary" onclick="showTaskModal()">+ New Task</button>
    </div>
    <div class="kanban-board">
      ${KANBAN_COLS.map(col => {
        const tasks = filtered.filter(t => t.status === col.id);
        return `
          <div class="kanban-col" data-col="${col.id}">
            <div class="col-header">
              <span class="col-dot" style="background:${col.color};color:${col.color}"></span>
              <span class="col-title">${col.name}</span>
              <span class="col-count">${tasks.length}</span>
              <button class="btn-icon col-add" title="Add task here" onclick="showTaskModal('${col.id}')">+</button>
            </div>
            <div class="col-body" data-col="${col.id}">
              ${tasks.map(t => taskCard(t)).join('') || `<div class="col-empty">Drop tasks here</div>`}
            </div>
          </div>
        `;
      }).join('')}
    </div>
  `;
}

function dispatchChip(t) {
  const ds = t.dispatch_state;
  if (!ds || ds === 'none') return '';
  const m = { queued: 'c-blue', dispatching: 'c-blue', streaming: 'c-cyan', finalizing: 'c-cyan',
              completed: 'c-green', failed: 'c-red', blocked_quota: 'c-orange', blocked_budget: 'c-orange' };
  const label = { blocked_quota: 'quota ⏸', blocked_budget: 'budget ⏸' }[ds] || ds;
  return `<span class="chip ${m[ds] || ''}" title="dispatch: ${esc(ds)}"><i></i>${esc(label)}</span>`;
}

// Super Result chip: round + state of the grounded-critic loop (✨SR).
function superChip(t) {
  if (!t.super_result) return '';
  const cfg = parseLoopCfg(t.loop_config);
  const trig = cfg && (cfg.triggers || []).find(x => x.id === 'super_result');
  const max = (trig && trig.max_rounds) || 3;
  const r = t.critic_round || 0;
  const v = t.critic_verdict;
  let label = '✨SR', cls = 'c-accent';
  if (v === 'running') { label = `✨SR r${r + 1}/${max} · critiquing`; cls = 'c-blue'; }
  else if (v === 'SHIP') { label = '✨SR · converged'; cls = 'c-green'; }
  else if (v === 'error') { label = `✨SR r${r}/${max} · escalated`; cls = 'c-red'; }
  else if (v === 'REVISE' || v === 'REWRITE') {
    let k = 0;
    try { k = (((JSON.parse(t.critic_json || '{}')) || {}).findings || []).length; } catch { /* raw */ }
    const esc2 = trig && trig.state && trig.state.kind === 'escalated';
    label = `✨SR r${r}/${max} · ${esc2 ? 'escalated' : `${k} finding${k === 1 ? '' : 's'}`}`;
    cls = esc2 ? 'c-red' : 'c-orange';
  }
  return `<span class="chip ${cls}" title="Super Result — grounded critic loop (round ${r}/${max}${v ? ', ' + v : ''})">${esc(label)}</span>`;
}

function taskCard(t) {
  const tags = (() => { try { return JSON.parse(t.tags || '[]'); } catch { return []; } })();
  const assignee = (state.agents || []).find(a => a.id === t.assignee_id);
  const claimer = (state.agents || []).find(a => a.id === t.claimed_by);
  const vs = t.verify_status || 'unknown';
  const vsChip = { passing: 'c-green', failing: 'c-red', blocked: 'c-orange' }[vs];
  const judgeChip = { SHIP: 'c-green', REVISE: 'c-orange', REWRITE: 'c-red' }[t.judge_verdict];
  return `
    <div class="task-card" draggable="true" data-id="${esc(t.id)}" data-status="${esc(t.status)}" data-priority="${t.priority}">
      <div class="task-title">${t.high_stakes ? '<span title="high-stakes — pauses for approval">⚖ </span>' : ''}${esc(t.title)}</div>
      ${t.description ? `<div class="task-desc">${esc(t.description)}</div>` : ''}
      <div class="task-foot">
        ${tags.map(tg => `<span class="task-tag">${esc(tg)}</span>`).join('')}
        ${t.domain && t.domain !== 'general' ? `<span class="task-tag" title="Business Brain domain">${esc(t.domain)}</span>` : ''}
        ${assignee ? `<span class="chip c-cyan">${esc(assignee.name)}</span>` : ''}
        ${claimer ? `<span class="chip c-yellow" title="claimed by ${esc(claimer.name)}">⚑ ${esc(claimer.name)}</span>` : ''}
        ${t.model ? `<span class="chip c-blue" title="AI model for this task">${esc(t.model)}</span>` : ''}
        ${dispatchChip(t)}
        ${superChip(t)}
        ${judgeChip ? `<span class="chip ${judgeChip}" title="frontier judge verdict">${esc(t.judge_verdict)}</span>` : ''}
        ${vsChip ? `<span class="chip ${vsChip}"><i></i>${esc(vs)}</span>` : ''}
        <span class="task-age">${fmtAgo(t.updated_at || t.created_at)}</span>
      </div>
    </div>
  `;
}

// Card handlers live in shared kanbanDrag state (not a bindKanban closure) so
// cards rebuilt by refreshKanbanBoard keep feeding the columns' drop handlers.
function bindKanbanCards() {
  $$('.task-card').forEach(card => {
    card.addEventListener('dragstart', () => {
      kanbanDrag.id = card.dataset.id;
      kanbanDrag.active = true;
      card.classList.add('dragging');
    });
    card.addEventListener('dragend', () => { kanbanDrag.active = false; card.classList.remove('dragging'); });
    card.addEventListener('click', () => { if (!kanbanDrag.active) openTaskDetail(card.dataset.id); });
  });
}

function bindKanban() {
  bindKanbanCards();

  $$('.col-body').forEach(col => {
    col.addEventListener('dragover', (e) => {
      e.preventDefault();
      col.closest('.kanban-col').classList.add('drag-over');
    });
    col.addEventListener('dragleave', () => {
      col.closest('.kanban-col').classList.remove('drag-over');
    });
    col.addEventListener('drop', async (e) => {
      e.preventDefault();
      col.closest('.kanban-col').classList.remove('drag-over');
      kanbanDrag.active = false;
      const dragId = kanbanDrag.id; // capture: renders below rebuild the cards
      kanbanDrag.id = null;
      if (!dragId) return;
      const newStatus = col.dataset.col;
      const t = (state.tasks || []).find(x => x.id === dragId);
      if (t && t.status !== newStatus) {
        t.status = newStatus; // optimistic
        render();
        await api('PATCH', `/api/tasks/${dragId}`, { status: newStatus });
        state.tasks = await api('GET', '/api/tasks');
        render();
      }
    });
  });

  const search = $('#kSearch');
  if (search) search.oninput = (e) => { kanbanFilters.q = e.target.value; refreshKanbanBoard(); };
  const sa = $('#kAssignee'); if (sa) sa.onchange = (e) => { kanbanFilters.assignee = e.target.value; render(); };
  const sw = $('#kWorkflow'); if (sw) sw.onchange = (e) => { kanbanFilters.workflow = e.target.value; render(); };
  const sp = $('#kPriority'); if (sp) sp.onchange = (e) => { kanbanFilters.priority = e.target.value; render(); };
  const st = $('#kTag'); if (st) st.onchange = (e) => { kanbanFilters.tag = e.target.value; render(); };
  const kc = $('#kClear'); if (kc) kc.onclick = () => { kanbanFilters.q = ''; kanbanFilters.assignee = ''; kanbanFilters.priority = ''; kanbanFilters.tag = ''; kanbanFilters.workflow = ''; render(); };
}

// Re-render only the board columns (keeps the search input focused while typing)
function refreshKanbanBoard() {
  const board = $('.kanban-board');
  if (!board) return;
  const filtered = (state.tasks || []).filter(taskMatchesFilters);
  KANBAN_COLS.forEach(col => {
    const body = board.querySelector(`.col-body[data-col="${col.id}"]`);
    const head = board.querySelector(`.kanban-col[data-col="${col.id}"] .col-count`);
    const tasks = filtered.filter(t => t.status === col.id);
    if (body) body.innerHTML = tasks.map(t => taskCard(t)).join('') || `<div class="col-empty">Drop tasks here</div>`;
    if (head) head.textContent = tasks.length;
  });
  // rebind cards only — same handlers as the full render, so drag still
  // feeds kanbanDrag.id to the columns' (still-bound) drop handlers
  bindKanbanCards();
}

function openTaskDetail(id) {
  const t = (state.tasks || []).find(x => x.id === id);
  if (!t) return;
  const agentOpts = (state.agents || []).map(a => `<option value="${esc(a.id)}" ${t.assignee_id === a.id ? 'selected' : ''}>${esc(a.name)}</option>`).join('');
  const tags = (() => { try { return JSON.parse(t.tags || '[]'); } catch { return []; } })();
  const claimer = (state.agents || []).find(a => a.id === t.claimed_by);
  const vs = t.verify_status || 'unknown';
  showModal(`
    <h2 style="display:flex;align-items:center;gap:10px">Task<span class="chip c-accent">${esc(t.id)}</span></h2>
    <div class="form-group"><label class="form-label">Title</label><input class="form-input" id="td-title" value="${esc(t.title)}"></div>
    <div class="form-group"><label class="form-label">Description</label><textarea class="form-textarea" id="td-desc">${esc(t.description || '')}</textarea></div>
    <div class="form-row">
      <div class="form-group"><label class="form-label">Status</label>
        <select class="form-select" id="td-status">
          ${KANBAN_COLS.map(c => `<option value="${c.id}" ${t.status === c.id ? 'selected' : ''}>${c.name}</option>`).join('')}
        </select></div>
      <div class="form-group"><label class="form-label">Priority</label>
        <select class="form-select" id="td-priority">
          <option value="0" ${t.priority === 0 ? 'selected' : ''}>Critical</option>
          <option value="1" ${t.priority === 1 ? 'selected' : ''}>High</option>
          <option value="2" ${t.priority === 2 ? 'selected' : ''}>Normal</option>
          <option value="3" ${t.priority === 3 ? 'selected' : ''}>Low</option>
        </select></div>
    </div>
    <div class="form-group"><label class="form-label">Assignee</label>
      <select class="form-select" id="td-assignee"><option value="">— Unassigned —</option>${agentOpts}</select></div>
    <div class="form-row">
      <div class="form-group"><label class="form-label">Domain (Business Brain)</label>
        <select class="form-select" id="td-domain">
          ${NEXUS_DOMAINS.map(d => `<option value="${d}" ${(t.domain || 'general') === d ? 'selected' : ''}>${d}</option>`).join('')}
        </select></div>
      <div class="form-group"><label class="form-label">Specialist (optional)</label>
        <select class="form-select" id="td-specialist"><option value="">— Agent decides —</option>
          ${t.specialist ? `<option value="${esc(t.specialist)}" selected>${esc(t.specialist)}</option>` : ''}
        </select></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label class="form-label">Token budget</label>
        <input class="form-input" id="td-budget" type="number" min="1000" step="1000" value="${t.budget_tokens || ''}" placeholder="default (1M)"></div>
      <div class="form-group"><label class="form-label" style="display:flex;align-items:center;gap:8px;margin-top:26px">
        <input type="checkbox" id="td-highstakes" ${t.high_stakes ? 'checked' : ''}> ⚖ High-stakes (pause for approval before shipping)</label></div>
    </div>
    <div class="form-group"><label class="form-label" style="display:flex;align-items:center;gap:8px">
      <input type="checkbox" id="td-super" ${t.super_result ? 'checked' : ''}> ✨ Super Result (grounded critic re-verifies each version — ~5–10× tokens)</label></div>
    <div class="form-group">
      <label class="form-label">AI model</label>
      <select class="form-select" id="td-model">${taskModelOptions(t.model)}</select>
    </div>
    ${(() => {
      const curDeps = (() => { try { return JSON.parse(t.depends_on || '[]'); } catch { return []; } })();
      const pool = (state.tasks || []).filter(x => x.id !== t.id &&
        (t.workflow_id ? x.workflow_id === t.workflow_id : true)).slice(0, 40);
      if (!pool.length && !curDeps.length) return '';
      return `<div class="form-group">
        <label class="form-label">⛓ Depends on (waits until these are DONE — their deliverables become this task's input)</label>
        <select class="form-select" id="td-depends" multiple size="${Math.min(5, Math.max(2, pool.length))}">
          ${pool.map(x => `<option value="${esc(x.id)}" ${curDeps.includes(x.id) ? 'selected' : ''}>${esc(x.title)} (${esc(x.status)})</option>`).join('')}
        </select>
        <div class="form-hint">Hold Ctrl to select several. ${t.workflow_id ? 'Showing tasks from the same project.' : ''}</div>
      </div>`;
    })()}
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px">
      ${tags.map(tg => `<span class="task-tag">${esc(tg)}</span>`).join('')}
      ${claimer ? `<span class="chip c-yellow">⚑ claimed by ${esc(claimer.name)}</span>` : ''}
      ${dispatchChip(t)}
      ${t.tokens_used ? `<span class="chip c-blue" title="real tokens consumed">${fmtTokens(t.tokens_used)} tok</span>` : ''}
      ${t.session_id ? `<span class="chip" title="Hermes session" style="font-family:var(--font-mono)">${esc(t.session_id)}</span>` : ''}
      ${vs !== 'unknown' ? `<span class="chip ${{ passing: 'c-green', failing: 'c-red' }[vs] || 'c-orange'}"><i></i>verify: ${esc(vs)}</span>` : ''}
    </div>
    ${t.dispatch_error ? `<div class="form-group"><div class="chip c-red" style="white-space:normal">✕ ${esc(t.dispatch_error)}</div></div>` : ''}
    ${t.rubric_score ? `<div class="form-group"><label class="form-label">Specialist self-score (rubric)</label>
      <div class="chip c-accent" style="white-space:normal">${esc(t.rubric_score)}</div></div>` : ''}
    ${t.learn_section ? `<div class="form-group"><label class="form-label">Learn (for you two)</label>
      <div style="background:rgba(124,92,255,.08);border:1px solid rgba(124,92,255,.25);border-radius:8px;padding:10px 12px;font-size:12.5px;white-space:pre-wrap">${esc(t.learn_section)}</div></div>` : ''}
    ${t.repo_path ? `<div class="form-group"><label class="form-label">🧬 Repo-native task</label>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px">
        <span class="chip c-cyan" style="font-family:var(--font-mono)">${esc(t.repo_path)}</span>
        <span class="muted">branch nexus/${esc((t.workflow_id || t.id).replace('wf-', '').replace('task-', ''))} · diff is the deliverable</span>
      </div></div>` : ''}
    <div class="form-group"><label class="form-label">📎 Attachments (input files the agent reads before working)</label>
      <div id="td-attach"><span class="muted" style="font-size:11.5px">loading…</span></div></div>
    <div class="form-group"><label class="form-label">🔁 Looping (automatic improve-and-recheck rounds)</label>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span id="td-loop-badge">${loopBadgeHTML(parseLoopCfg(t.loop_config))}</span>
        <button class="btn-sm" onclick="loopViewerModal('task','${esc(t.id)}','${esc(t.title).slice(0, 60)}')">🔁 View / edit loop</button>
      </div></div>
    <div id="td-judge">${judgeSectionHTML(t)}</div>
    <div id="td-critic">${criticSectionHTML(t)}</div>
    <div id="td-extras"></div>
    <div style="font-size:11px;color:var(--text-faint);font-family:var(--font-mono)">created ${fmtAgo(t.created_at)} · updated ${fmtAgo(t.updated_at)}${t.completed_at ? ` · completed ${fmtAgo(t.completed_at)}` : ''}</div>
    <div class="modal-actions" style="justify-content:space-between">
      <button class="btn-sm danger" onclick="deleteTaskUI('${esc(t.id)}')">Delete task</button>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        ${['none', 'failed', 'blocked_quota', 'blocked_budget', undefined, null, ''].includes(t.dispatch_state) && ['backlog', 'todo', 'in_progress'].includes(t.status)
          ? `<button class="btn-ghost" title="Execute NOW via a real Hermes session" onclick="dispatchTaskUI('${esc(t.id)}')">▶ Dispatch</button>` : ''}
        ${['failed'].includes(t.dispatch_state) || (t.judge_verdict && t.judge_verdict !== 'SHIP' && t.judge_verdict !== 'running')
          ? `<button class="btn-ghost" title="Fresh attempt with feedback attached" onclick="retryTaskUI('${esc(t.id)}')">↻ Retry</button>` : ''}
        ${t.repo_path && t.result_summary ? (t.pr_url
          ? `<a class="btn-ghost" href="${esc(t.pr_url)}" target="_blank" style="text-decoration:none" title="Open the GitHub pull request">↗ View PR</a>`
          : `<button class="btn-ghost" title="Push the task branch to origin and open a GitHub pull request (gh)" onclick="createPrUI('${esc(t.id)}')">⬆ Create PR</button>`) : ''}
        ${t.result_summary ? `<button class="btn-ghost" title="New task that reads THIS deliverable as its input" onclick="followUpTaskUI('${esc(t.id)}')">➡ Follow-up task</button>
        <button class="btn-ghost" onclick="logFeedbackUI('${esc(t.id)}','win')">🏆 Log WIN</button>
        <button class="btn-ghost" onclick="logFeedbackUI('${esc(t.id)}','lesson')">📓 Log LESSON</button>` : ''}
        <button class="btn-ghost" onclick="closeModal()">Cancel</button>
        <button class="btn-primary" onclick="saveTaskDetail('${esc(t.id)}')">Save</button>
      </div>
    </div>
  `);
  loadTaskExtras(t);
  loadAttachmentsInto('task', t.id, 'td-attach', t.workflow_id);
  loadLoopBadge(t);
}

// A task without its own loop INHERITS its project's loop — surface that
// instead of showing a misleading "no loop".
async function loadLoopBadge(t) {
  if (parseLoopCfg(t.loop_config) || !t.workflow_id) return;
  try {
    const w = await api('GET', `/api/workflows/${t.workflow_id}`);
    const cfg = parseLoopCfg(w.loop_config);
    const el = $('#td-loop-badge');
    if (el && cfg && cfg.enabled) {
      el.innerHTML = `${loopBadgeHTML(cfg)} <span class="chip" title="This task is covered by its project's loop. Give the task its own loop to override.">↑ inherited from project</span>
        <button class="btn-sm" onclick="loopViewerModal('workflow','${esc(t.workflow_id)}','${esc(w.name || 'project')}')">open project loop</button>`;
    }
  } catch { /* optional */ }
}

// ── Attachments (operator input files on tasks & projects) ──
const ATTACH_ACCEPT = '.png,.jpg,.jpeg,.gif,.webp,.svg,.pdf,.docx,.xlsx,.pptx,.doc,.xls,.ppt,.txt,.md,.csv,.json';

function attachApiBase(kind, id) { return kind === 'task' ? `/api/tasks/${id}` : `/api/workflows/${id}`; }
function attachDlHref(kind, id, n) {
  return kind === 'task'
    ? `/api/tasks/${id}/files/attachments/${encodeURIComponent(n)}`
    : `/api/workflows/${id}/attachments/${encodeURIComponent(n)}/download`;
}
function attachRowHTML(kind, id, f, elId) {
  return `<div style="display:flex;align-items:center;gap:8px;font-size:12px;margin-top:2px">
    📎 <a href="${attachDlHref(kind, id, f.name)}" target="_blank" style="color:var(--accent)">${esc(f.name)}</a>
    <span class="muted" style="font-size:10.5px">${(f.size / 1024).toFixed(0)} KB</span>
    <button class="btn-sm danger" title="remove" onclick="deleteAttachment('${kind}','${esc(id)}','${esc(f.name)}','${elId}')">✕</button>
  </div>`;
}
function attachUploadHTML(elId) {
  return `
    <div class="attach-dz" id="${elId}-dz">
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input type="file" id="${elId}-file" accept="${ATTACH_ACCEPT}" multiple style="font-size:11.5px;max-width:260px">
        <button class="btn-sm" onclick="attachUploadPicked('${elId}')">⬆ Upload</button>
      </div>
      <div class="muted" style="font-size:10.5px;margin-top:4px">…or drag &amp; drop files anywhere in this box · pdf, office, images, text · max 25 MB each</div>
    </div>`;
}
// elId → { getTarget, reload }: the target is resolved at drop/upload time so the
// project block can route by its "Attach to" <select> (whole project vs one task).
const attachTargets = {};
function attachWire(elId, getTarget, reload) {
  attachTargets[elId] = { getTarget, reload };
  const z = document.getElementById(`${elId}-dz`);
  if (!z) return;
  ['dragenter', 'dragover'].forEach(ev => z.addEventListener(ev, e => {
    e.preventDefault(); e.stopPropagation(); z.classList.add('dz-hover');
  }));
  z.addEventListener('dragleave', e => { e.preventDefault(); z.classList.remove('dz-hover'); });
  z.addEventListener('drop', e => {
    e.preventDefault(); e.stopPropagation(); z.classList.remove('dz-hover');
    const files = [...((e.dataTransfer || {}).files || [])];
    if (files.length) attachUploadFiles(elId, files);
  });
}
// A file dropped outside a dropzone must not navigate the SPA away.
window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('drop', e => e.preventDefault());

async function attachUploadPicked(elId) {
  const inp = document.getElementById(`${elId}-file`);
  if (!inp || !inp.files || !inp.files.length) { toast('Pick a file first', 'err'); return; }
  await attachUploadFiles(elId, [...inp.files]);
}
async function attachUploadFiles(elId, files) {
  const t = attachTargets[elId];
  if (!t) return;
  const { kind, id } = t.getTarget();
  let done = 0;
  for (const f of files) {
    try { await attachPostFile(kind, id, f); done++; }
    catch (e) { toast(`${f.name}: ${e.message}`, 'err'); }
  }
  if (done) toast(`Attached ${done} file${done > 1 ? 's' : ''} ${kind === 'task' ? 'to the task' : 'project-wide'}`, 'ok');
  t.reload();
}

async function loadAttachmentsInto(kind, id, elId, wfId) {
  const el = $(`#${elId}`);
  if (!el) return;
  let files = [];
  try { files = (await api('GET', `${attachApiBase(kind, id)}/attachments`)).attachments || []; } catch { }
  let inherited = '';
  if (kind === 'task' && wfId) {
    try {
      const pf = (await api('GET', `/api/workflows/${wfId}/attachments`)).attachments || [];
      if (pf.length) inherited = `<div class="muted" style="font-size:11px;margin-top:4px">↑ also reads ${pf.length} project-wide file${pf.length > 1 ? 's' : ''}: ${pf.map(x => esc(x.name)).join(', ')} <span style="opacity:.7">(manage in the project window)</span></div>`;
    } catch { }
  }
  el.innerHTML = `<div class="attach-list">
    ${files.map(f => attachRowHTML(kind, id, f, elId)).join('') || '<div class="muted" style="font-size:11.5px">No attachments — the agent works from the description alone.</div>'}
    ${inherited}
  </div>${attachUploadHTML(elId)}`;
  attachWire(elId, () => ({ kind, id }), () => loadAttachmentsInto(kind, id, elId, wfId));
}

// Project ("workflow") attachments with TARGETING: upload lands project-wide or
// on ONE member task, and per-task files are grouped so placement stays visible.
async function loadProjectAttachments(wfId, elId = 'wf-attach') {
  const el = $(`#${elId}`);
  if (!el) return;
  let w;
  try { w = await api('GET', `/api/workflows/${wfId}`); }
  catch { el.innerHTML = '<div class="muted" style="font-size:11.5px">load failed</div>'; return; }
  const tasks = (w.tasks || []).filter(t => t.status !== 'archived');
  const results = await Promise.all([
    api('GET', `/api/workflows/${wfId}/attachments`).then(d => d.attachments || []).catch(() => []),
    ...tasks.map(t => api('GET', `/api/tasks/${t.id}/attachments`).then(d => d.attachments || []).catch(() => [])),
  ]);
  const wfFiles = results[0];
  const prevTarget = (document.getElementById(`${elId}-target`) || {}).value;
  const groups = [`<div class="attach-group"><div class="attach-group-label">📌 Project-wide — every task reads these</div>
    ${wfFiles.map(f => attachRowHTML('workflow', wfId, f, elId)).join('') || '<div class="muted" style="font-size:11.5px">none</div>'}</div>`];
  tasks.forEach((t, i) => {
    const fs = results[i + 1];
    if (fs.length) groups.push(`<div class="attach-group"><div class="attach-group-label">↳ only task ${i + 1} — ${esc(t.title.slice(0, 60))}</div>
      ${fs.map(f => attachRowHTML('task', t.id, f, elId)).join('')}</div>`);
  });
  el.innerHTML = `<div class="attach-list">${groups.join('')}</div>
    <div style="display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap">
      <label class="form-label" style="margin:0">Attach to</label>
      <select class="form-select" id="${elId}-target" style="max-width:340px;font-size:12px;padding:5px 8px">
        <option value="wf:${esc(wfId)}">📎 Whole project — every task reads it</option>
        ${tasks.map((t, i) => `<option value="task:${esc(t.id)}">only ${i + 1}. ${esc(t.title.slice(0, 55))}</option>`).join('')}
      </select>
    </div>
    ${attachUploadHTML(elId)}`;
  const sel = document.getElementById(`${elId}-target`);
  if (sel && prevTarget && [...sel.options].some(o => o.value === prevTarget)) sel.value = prevTarget;
  attachWire(elId, () => {
    const v = ((document.getElementById(`${elId}-target`) || {}).value) || `wf:${wfId}`;
    const kind = v.startsWith('task:') ? 'task' : 'workflow';
    return { kind, id: v.slice(v.indexOf(':') + 1) };
  }, () => loadProjectAttachments(wfId, elId));
}

async function deleteAttachment(kind, id, name, elId) {
  try {
    await api('DELETE', `${attachApiBase(kind, id)}/attachments/${encodeURIComponent(name)}`);
    const t = attachTargets[elId];
    if (t) t.reload(); else loadAttachmentsInto(kind, id, elId);
  } catch (e) { toast('Delete failed: ' + e.message, 'err'); }
}

async function attachPostFile(kind, id, f) {
  const fd = new FormData();
  fd.append('file', f);
  const r = await fetch(`${attachApiBase(kind, id)}/attachments`, { method: 'POST', body: fd });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.status);
  return j;
}

// ── Attach at CREATION time: the object doesn't exist yet, so files are staged
//    in memory while the form is open and uploaded right after Create. The
//    HTML helper resets the stage, so a cancelled form never leaks files into
//    the next one. ──
const attachStaged = {}; // elId → File[]
function attachStageHTML(elId) {
  attachStaged[elId] = [];
  return `
    <div id="${elId}-pending"></div>
    <div class="attach-dz" id="${elId}-dz">
      <input type="file" id="${elId}-file" accept="${ATTACH_ACCEPT}" multiple style="font-size:11.5px;max-width:260px"
        onchange="attachStageAdd('${elId}', [...this.files]); this.value='';">
      <div class="muted" style="font-size:10.5px;margin-top:4px">…or drag &amp; drop files here · pdf, office, images, text · max 25 MB each · uploaded when you press Create</div>
    </div>`;
}
function attachStageWire(elId) {
  const z = document.getElementById(`${elId}-dz`);
  if (!z) return;
  ['dragenter', 'dragover'].forEach(ev => z.addEventListener(ev, e => {
    e.preventDefault(); e.stopPropagation(); z.classList.add('dz-hover');
  }));
  z.addEventListener('dragleave', e => { e.preventDefault(); z.classList.remove('dz-hover'); });
  z.addEventListener('drop', e => {
    e.preventDefault(); e.stopPropagation(); z.classList.remove('dz-hover');
    attachStageAdd(elId, [...((e.dataTransfer || {}).files || [])]);
  });
}
function attachStageAdd(elId, files) {
  const cur = attachStaged[elId] || (attachStaged[elId] = []);
  for (const f of files) {
    if (!cur.some(x => x.name === f.name && x.size === f.size)) cur.push(f);
  }
  attachStageRender(elId);
}
function attachStageRemove(elId, i) {
  (attachStaged[elId] || []).splice(i, 1);
  attachStageRender(elId);
}
function attachStageRender(elId) {
  const el = document.getElementById(`${elId}-pending`);
  if (!el) return;
  el.innerHTML = (attachStaged[elId] || []).map((f, i) => `
    <div style="display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:2px">
      📎 ${esc(f.name)} <span class="muted" style="font-size:10.5px">${(f.size / 1024).toFixed(0)} KB · pending</span>
      <button class="btn-sm danger" title="remove" onclick="attachStageRemove('${elId}',${i})">✕</button>
    </div>`).join('');
}
async function attachStageUploadAll(elId, kind, id) {
  const files = attachStaged[elId] || [];
  delete attachStaged[elId];
  let done = 0;
  for (const f of files) {
    try { await attachPostFile(kind, id, f); done++; }
    catch (e) { toast(`${f.name}: ${e.message}`, 'err'); }
  }
  return done;
}

// ═══════════════════ GLOBAL FOCUS CONTEXT (Projects › Workflows › Tasks) ═══════════════════
// Select a project and every downstream view scopes to it; select a workflow
// and Tasks narrows further. Creation inherits the deepest selection.
// Persisted across reloads; always visible in the bar under the topbar.
let focusCtx = { project: null, workflow: null };

// Focus is PER USER (Block 1): each user's project/workflow focus lives under
// their own key. Loaded in bootAuth() once the user is known; the legacy
// un-namespaced key migrates to the current user once, then is removed.
function focusKey() {
  return 'nexusFocus:' + ((authState.user && authState.user.id) || 'u_owner');
}

function loadFocus() {
  try {
    let raw = localStorage.getItem(focusKey());
    if (raw == null) {
      // The legacy un-namespaced key predates multi-user, so it can only be
      // the OWNER's focus — migrating it to whoever logs in next on this
      // browser would hand another user the owner's project context.
      const legacy = localStorage.getItem('nexusFocus');
      if (legacy != null && focusKey() === 'nexusFocus:u_owner') {
        localStorage.setItem(focusKey(), legacy);
        localStorage.removeItem('nexusFocus');
        raw = legacy;
      }
    }
    focusCtx = JSON.parse(raw || '{}') || {};
  } catch { focusCtx = {}; }
  focusCtx.project = focusCtx.project || null;
  focusCtx.workflow = focusCtx.workflow || null;
}

// Called wherever the (user-scoped) projects list arrives: focus pointing at
// a project this user cannot see — stale localStorage, ownership change — is
// cleared instead of silently scoping their boards to an invisible project.
function pruneStaleFocus(projects) {
  if (!focusCtx.project || !Array.isArray(projects)) return;
  if (!projects.some(p => p && p.path === focusCtx.project.path)) {
    focusCtx.project = null;
    focusCtx.workflow = null;
    saveFocus();
  }
}

function saveFocus() {
  try { localStorage.setItem(focusKey(), JSON.stringify(focusCtx)); } catch { }
  renderFocusBar();
}

function setFocusProject(path, name, client) {
  if (focusCtx.project && focusCtx.project.path !== path) focusCtx.workflow = null;
  focusCtx.project = path ? { path, name, client: client || null } : null;
  if (!path) focusCtx.workflow = null;
  saveFocus();
  toast(path ? `🎯 Working in project: ${name} — Workflows & Tasks are now scoped to it` : 'Project focus cleared — showing everything', 'ok');
  render();
}

function setFocusWorkflow(id, name) {
  focusCtx.workflow = id ? { id, name } : null;
  saveFocus();
  toast(id ? `🎯 Focused workflow: ${name} — Tasks shows only its tasks` : 'Workflow focus cleared', 'ok');
  render();
}

function renderFocusBar() {
  const bar = document.getElementById('focusBar');
  if (!bar) return;
  const p = focusCtx.project, w = focusCtx.workflow;
  if (!p && !w) { bar.style.display = 'none'; bar.innerHTML = ''; return; }
  bar.style.display = 'flex';
  bar.innerHTML = `<span style="font-family:var(--font-mono);font-size:10.5px;letter-spacing:.1em">🎯 WORKING IN</span>` +
    (p ? `<span class="focus-chip">📂 <b>${esc(p.name)}</b>${p.client ? ` <span class="muted">(${esc(p.client)})</span>` : ''}<span class="fx" title="clear project focus" onclick="setFocusProject(null)">✕</span></span>` : '') +
    (p && w ? '<span class="focus-sep">›</span>' : '') +
    (w ? `<span class="focus-chip">⚙ <b>${esc(w.name)}</b><span class="fx" title="clear workflow focus" onclick="setFocusWorkflow(null)">✕</span></span>` : '') +
    `<span class="muted" style="margin-left:auto;font-size:11px">new workflows & tasks are assigned here automatically</span>`;
}

// workflow ids whose tasks live in the focused project (derived — a workflow
// has no project field; its tasks' repo_path is the truth)
function focusProjectWorkflowIds() {
  const p = focusCtx.project;
  if (!p) return null;
  const ids = new Set();
  (state.tasks || []).forEach(t => {
    if (t.workflow_id && t.repo_path && (t.repo_path === p.path || t.repo_path.startsWith(p.path + '/'))) {
      ids.add(t.workflow_id);
    }
  });
  return ids;
}

function taskInFocus(t) {
  if (focusCtx.workflow) return t.workflow_id === focusCtx.workflow.id;
  const p = focusCtx.project;
  if (!p) return true;
  if (t.repo_path && (t.repo_path === p.path || t.repo_path.startsWith(p.path + '/'))) return true;
  const ids = focusProjectWorkflowIds();
  return !!(t.workflow_id && ids && ids.has(t.workflow_id));
}

// ═══════════════════ USER MANUAL (view: manual) ═══════════════════
function viewManual() {
  return `<div class="manual-wrap">
  <div class="view-intro" style="margin-bottom:14px">This manual explains the whole system in plain language — no IT background needed — and ends with the full technical architecture for those who want it. On any other tab, the <b>?</b> button in the top bar starts a guided walkthrough of exactly that tab.</div>
  <div class="manual-toc">
    <a href="#m-what">What is this?</a><a href="#m-first">First steps</a><a href="#m-tasks">Creating work</a><a href="#m-projects">Projects</a><a href="#m-results">Getting results</a><a href="#m-quality">Quality machinery</a><a href="#m-coding">Coding on your repos</a><a href="#m-jarvis">JARVIS</a><a href="#m-memory">Memory</a><a href="#m-users">Users &amp; remote access</a><a href="#m-money">Costs &amp; limits</a><a href="#m-trouble">Troubleshooting</a><a href="#m-tech">🔧 Technical architecture</a>
  </div>

  <div class="manual-sec" id="m-users">
    <h2>👥 Users &amp; remote access</h2>
    <div class="m-sub">One machine, personal workspaces — and access from your phone</div>
    <p>Nexus supports multiple people on this one installation. With a single user there is <b>no login</b> — everything works exactly as before. The moment a second account exists (Settings → <b>Users &amp; access</b>), a login screen appears for everyone, and each person gets their <b>own</b> task board, projects, deliverables, focus, JARVIS conversation and memories. Nobody sees anybody else's work — this is enforced by the server on every request, not just hidden in the UI.</p>
    <div class="m-steps">
      <div class="m-step"><div>Go to <b>Settings → Users &amp; access</b> and first set <b>your own password</b>.</div></div>
      <div class="m-step"><div>Click <b>+ Add user</b> — username, display name, a password of at least 8 characters. From now on everyone signs in.</div></div>
      <div class="m-step"><div>Shared between users: the agent fleet, budgets/settings and the specialists' craft knowledge. Personal: everything you create.</div></div>
    </div>
    <p>Remote access runs over <b>Tailscale</b> (a private device-to-device network) — the phone and the second laptop join your tailnet and open <code>https://&lt;machine&gt;.&lt;tailnet&gt;.ts.net</code>. Nexus is <b>never</b> on the public internet. Setup: <code>bash scripts/setup_tailscale.sh</code> (details in docs/TAILSCALE.md). Locked out? On the machine itself: <code>.venv/bin/python scripts/auth_reset.py</code> returns it to single-user.</p>
    <div class="m-tip">💡 The interface adapts to phones: the menu hides behind the ☰ button, and boards scroll sideways with a swipe.</div>
  </div>

  <div class="manual-sec" id="m-what">
    <h2>🧭 What is this?</h2>
    <div class="m-sub">Nexus Agent OS — mission control for your personal AI workforce</div>
    <p>Nexus is the control room for a team of AI agents that do real work for you: research, writing, images, documents, and complete software projects. You describe what you want; the system plans it, splits it into steps, executes each step with the right specialist, checks the quality, and hands you the results. It runs entirely on <b>your own computer</b> — your data never leaves the machine except for the AI model calls themselves.</p>
    <div class="m-visual">  YOU ──describe──▶ ✨ WIZARD ──plans──▶ 📋 KANBAN ──executes──▶ 🤖 AGENTS
                                                        │                      │
   📦 DELIVERABLES ◀──results──  ✅ QUALITY GATES  ◀──checks──┘</div>
    <div class="m-tip">💡 The golden rule: <b>you describe, the system organizes.</b> You never have to know which model, specialist or pipeline is right — the wizard chooses, and you just approve.</div>
  </div>

  <div class="manual-sec" id="m-first">
    <h2>🚀 First steps</h2>
    <div class="m-sub">Your first task in three minutes</div>
    <div class="m-steps">
      <div class="m-step"><div>Open <b>Kanban</b> in the left menu and click <b>✨ Describe a task</b>.</div></div>
      <div class="m-step"><div>Type your wish in normal sentences — for example <i>"Research the best 3 CRM tools for a small agency and write a comparison"</i>. Don't think in computer terms; write as if briefing a colleague.</div></div>
      <div class="m-step"><div>The AI may ask a few questions. Every question already has a <b>★ recommended</b> answer with pros and cons — if unsure, just accept the recommendations.</div></div>
      <div class="m-step"><div>Approve the proposed plan. The task appears on the board and an agent picks it up — you can watch it working live on the Dashboard.</div></div>
      <div class="m-step"><div>When the card reaches <b>Review</b>, open it and read the result under <b>Files</b>. Happy? Approve it. Not happy? Click <b>Reject</b>, say what's wrong in one sentence, and the agent reworks it with your feedback.</div></div>
    </div>
  </div>

  <div class="manual-sec" id="m-tasks">
    <h2>📋 Creating work</h2>
    <div class="m-sub">Tasks, the wizard, attachments and models</div>
    <h4>The task board (Kanban)</h4>
    <p>Work moves left to right: <b>Backlog</b> (ideas, nobody touches them) → <b>Todo</b> (ready — agents may grab these) → <b>In Progress</b> → <b>Review</b> (your turn!) → <b>Done</b>. Drag cards to move them yourself.</p>
    <h4>Attachments — give agents your material</h4>
    <p>Open any task and add files: PDFs, Word, Excel, PowerPoint, pictures. The agent is <b>required</b> to read them before working. Results can also come back in those formats — just ask for "a Word document" or "an Excel sheet" in the description.</p>
    <h4>Choosing a model (optional)</h4>
    <p>Each task can run on a different AI model from your registry (Settings → Models & routing) — a hard-thinking default, a lighter/faster tier, and a cheap mechanical tier. If you don't choose, your 'complicated tasks' model applies.</p>
    <div class="m-tip">💡 A good task description says: what you want, for whom, and what "done" looks like. One sentence of each is enough — the wizard fills in the rest and always shows you its assumptions.</div>
  </div>

  <div class="manual-sec" id="m-projects">
    <h2>🧩 Workflows</h2>
    <div class="m-sub">Rounds of work where one step feeds the next — they visit your durable projects</div>
    <p>A project chains tasks with <b>dependencies</b>. Each stage starts automatically once its predecessors finish, and receives their outputs as input. This is how big jobs stay organized:</p>
    <div class="m-visual">  SPEC &amp; PLAN ──▶ IMPLEMENT ──▶ CODE REVIEW ──▶ FIX FINDINGS ──▶ FINAL VERIFICATION
   (architect)    (builder)     (critic)        (builder)        (independent tester)</div>
    <p>That five-stage shape is the built-in quality pipeline for software: it is enforced automatically for coding goals — the reviewer is never the person who wrote the code, and the final verifier always runs last.</p>
    <p>Create projects with <b>✨ Describe a goal</b> on the Projects tab. You can untick optional stages before approving; quality gates are locked on purpose.</p>
  </div>

  <div class="manual-sec" id="m-results">
    <h2>📦 Getting results</h2>
    <div class="m-sub">Deliverables, previewing apps, chaining follow-ups</div>
    <p>Everything agents produce is collected under <b>Deliverables</b>: reports, images, documents, whole applications. Markdown reports preview inline; everything is downloadable.</p>
    <h4>▶ Test app — run what they built</h4>
    <p>When a task produced a program or website, the <b>▶ Test app</b> button starts it safely on your machine and opens it in a new tab. It shuts down by itself after 30 minutes. If it shows "starting" forever, open the log in the same dialog — it tells the truth.</p>
    <p>Projects have the same button one level up: <b>▶ Test project</b> (on the project card and inside its panel) runs the <b>complete assembled project</b> — every stage's changes together, not one task's output. You can also pick an <b>earlier state</b> from its history and run it next to the latest one on a second port, to compare old vs new and see whether the newest changes broke something. Every run uses a disposable copy, so your real project files are never touched.</p>
    <h4>🔍 Review changes — the pull-request view for everything</h4>
    <p>Every task's detail (and every workflow via "Review results") offers a per-file comparison against the previous version: code shows real line-by-line diffs (green added, red removed), <b>PDFs are compared by their extracted text</b>, images side-by-side, and each rework round becomes a new version automatically. Judge the update like a programmer judges a pull request — then approve or reject with feedback.</p>
    <h4>Follow-ups</h4>
    <p>Under any deliverable, <b>Chain a follow-up</b> creates a new task that receives this result as input — "now translate it", "now make a landing page from it".</p>
  </div>

  <div class="manual-sec" id="m-quality">
    <h2>✅ Quality machinery</h2>
    <div class="m-sub">Loops, the judge, and why results improve by themselves</div>
    <h4>Improvement loops (🔁)</h4>
    <p>Tasks and projects can loop: when a check fails or a judge demands changes, the system automatically sends the work back with the findings attached and re-checks afterwards — up to a bounded number of rounds. <b>Closed</b> mode does this without asking you; <b>open</b> mode waits for your click at each checkpoint. The loop designer explains its plan in plain sentences, and projects pass their loop down to their tasks unless you override it.</p>
    <h4>The frontier judge</h4>
    <p>High-stakes deliverables can be graded by a stronger AI (Claude) against your own quality rubric — verdict, findings, and a score. On quality-mode loops this happens automatically.</p>
    <h4>Rejection with feedback</h4>
    <p>Your "Reject" + one sentence is the strongest quality tool: the agent gets your words verbatim and must address them. Specialists also <b>learn</b> from this — feedback becomes lessons they apply to future work.</p>
  </div>

  <div class="manual-sec" id="m-coding">
    <h2>🧬 Coding on your own repositories</h2>
    <div class="m-sub">Repo-native tasks: the diff is the deliverable</div>
    <div class="m-tip">💡 <b>The model:</b> the repository is the client project — it lives for years under <code>~/Client-Projects/&lt;client&gt;/&lt;project&gt;</code>. Kanban pipelines are work ROUNDS visiting it: build v1, then "implement the demo feedback", then "fix the checkout bug"… each round is a new wizard pipeline targeting the same repo. <b>Repo-first rule:</b> start client work with "➕ New client project" (Projects tab or the wizard's repo dropdown) — never in a loose workspace. Personal long-lived work (uni projects, own experiments) gets the same treatment via 🏠 personal projects (~/Projects, no client, personal memory). Small iterative jobs (diagnose → try → feedback, like fixing a car) don't need a project at all: one task + Reject-with-feedback rounds. If an app already grew inside a task, use <b>📦 Promote to repository</b> on that task to lift it out; the client scope (memory isolation) is derived from the folder automatically.</div>
    <div class="m-steps">
      <div class="m-step"><div>Once per repository: run the <b>"🧬 Onboard a code repository"</b> template. It studies your repo (read-only) and writes an AGENTS.md — the house rules every agent will follow there.</div></div>
      <div class="m-step"><div>On any coding task or project, pick your repo under <b>"Existing code repository"</b>.</div></div>
      <div class="m-step"><div>Agents then work <b>inside</b> an isolated copy (a git worktree on branch <code>nexus/…</code>) — your checkout is never touched. They follow the repo's conventions and run its own tests.</div></div>
      <div class="m-step"><div>Review the <b>changes.diff</b> in Deliverables. Merge the branch yourself when satisfied — nothing merges automatically, ever.</div></div>
    </div>
    <h4>Backup & delivery workflow (Projects tab → click a repo)</h4>
    <div class="m-steps">
      <div class="m-step"><div><b>Publish to GitHub</b> — once per repo: creates a PRIVATE GitHub repository and pushes everything. From then on this repo is backed up offsite and has a handover vehicle.</div></div>
      <div class="m-step"><div><b>Push</b> — after every merge: one click sends your latest state (and tags) to GitHub. The push IS the backup.</div></div>
      <div class="m-step"><div><b>Tag release</b> — when you deliver: marks the exact shipped code state (e.g. v1.0) forever. "What did we ship for invoice #12?" always has a precise answer.</div></div>
      <div class="m-step"><div><b>Handover</b> — at contract end: transfer the GitHub repository to the client's organization (repo Settings → Transfer ownership). Ownership should mirror the contract.</div></div>
    </div>
  </div>

  <div class="manual-sec" id="m-jarvis">
    <h2>🎙 JARVIS</h2>
    <div class="m-sub">Talk to your AI face to face</div>
    <p>Click the face to talk; the reply comes back as your AI speaking with lip-synced video on a live holographic stage. Toggle <b>CONV</b> for hands-free conversation (it detects when you stop speaking). Click the face mid-sentence to interrupt. Typing works too — same brain, same voice.</p>
    <div class="m-tip">💡 The stage isn't decoration: rings pulse from your real microphone level, violet particles orbit while it thinks, and the room throbs with the actual speech amplitude.</div>
  </div>

  <div class="manual-sec" id="m-memory">
    <h2>🧠 Memory</h2>
    <div class="m-sub">The galaxy is real data, not art</div>
    <p>Everything your AI remembers is a point in a 768-dimensional "meaning space". The galaxy (Dashboard, and Memory → 3D Map) projects those true positions into 3D: <b>distance = similarity of meaning</b>. Regions get their colors and names from the memories themselves. Search any topic and the matching stars flare while everything else fades. Hover a star to read the memory and its strongest associations.</p>
    <h4>Client memory isolation</h4>
    <p>Projects and tasks can carry a <b>client</b> tag. Everything agents learn while working for that client is stored in the client's own private scope: sessions for other clients — and your personal chats — can never retrieve it. Each client appears as its own color group in the galaxy. Generalized craft lessons (with client names stripped, human-reviewed) still improve your specialists globally, so quality compounds across clients without data crossing between them. Ending a contract? One command deletes everything in that client's scope.</p>
  </div>

  <div class="manual-sec" id="m-money">
    <h2>💰 Costs &amp; limits</h2>
    <div class="m-sub">Why nothing can run away</div>
    <p>Every task has a token budget; there's a daily cap over everything; each agent lane can carry its own spending cap; and parallel sessions are limited per model. A task that hits its fence pauses as <b>blocked: budget</b> — retrying grants exactly one more slice, never an open tap. See real consumption under <b>Usage</b>; change the fences under <b>Settings</b>.</p>
  </div>

  <div class="manual-sec" id="m-trouble">
    <h2>🛟 Troubleshooting</h2>
    <div class="m-sub">When something looks wrong</div>
    <ul>
      <li><b>Task sits in "queued"</b> — check the session strip (top bar): all slots busy means it waits its turn. Minutes with an empty strip? File it with 🐞.</li>
      <li><b>blocked: quota</b> — the AI provider is load-shedding at peak times. The system retries by itself with growing pauses; you don't need to do anything.</li>
      <li><b>A result is missing</b> — check the task's Files section; every run also keeps a transcript (openable from the task) showing exactly what the agent did.</li>
      <li><b>Something feels buggy or annoying</b> — the 🐞 button (bottom right, every page) files it together with your recent steps into <b>Known Issues</b>. That list is the repair queue.</li>
      <li><b>Guardian shows drift</b> — a protected file changed unexpectedly. Open Guardian and repair or approve the change.</li>
    </ul>
  </div>

  <div class="manual-sec" id="m-tech">
    <h2>🔧 Technical architecture</h2>
    <div class="m-sub">The IT chapter — how it actually works</div>
    <h4>Components</h4>
    <div class="m-visual">  ┌────────────────────────  YOUR MACHINE  ───────────────────────────┐
  │                                                                    │
  │  NEXUS (this app) ── FastAPI + SQLite + vanilla JS, port 8777      │
  │  · control plane: kanban, dispatch queue, budgets, loops, judge    │
  │  · worker lanes: one subprocess per agent, atomic task claiming    │
  │  · quality gates: verify.sh (static) + Playwright suites (runtime) │
  │            │  HTTP + SSE (localhost only)                          │
  │            ▼                                                       │
  │  HERMES (engine) ── agent runtime + gateway, port 8642             │
  │  · sessions, tools (terminal/files/browser/LSP), 18 specialists    │
  │  · skills library, delegation, per-repo AGENTS.md loading          │
  │            │                                                       │
  │            ├──▶ Z.AI GLM-5.2/5.1 (the only external calls)         │
  │            ├──▶ qdrant (vector DB, Docker) + ollama ── mem0 memory  │
  │            └──▶ guardian ── verifies/repairs all customizations    │
  └────────────────────────────────────────────────────────────────────┘</div>
    <h4>Why two systems?</h4>
    <p>Nexus (control plane) and Hermes (execution engine) are separate processes on purpose — the industry-standard split. Nexus can restart a dozen times a day during development without killing a single running AI session: an interrupted task's session keeps running inside Hermes, and the respawned lane <b>harvests</b> the finished result from session history, free.</p>
    <h4>The dispatch lifecycle</h4>
    <div class="m-visual">  queued → dispatching → streaming → finalizing → completed
                                        │
             blocked_budget / blocked_quota / failed  (each self-recovering)</div>
    <p>Dispatch is queue-only: the API claims atomically (SQLite compare-and-swap — two agents can never grab one task), and the worker lane is the sole executor. Every run writes <code>workspaces/&lt;task-id&gt;/</code> with the deliverable, an audit JSON, and real token counts from the stream.</p>
    <h4>Self-healing</h4>
    <p>A watchdog restarts dead/stuck lanes (~10s detection); orphaned runs are harvested rather than re-executed; stranded claims resurrect on the next worker tick; retired agents are terminal (never respawned). The loop engine sweeps every 20s and acts at most 3 times per sweep — bounded autonomy everywhere.</p>
    <h4>Repo-native coding</h4>
    <p>Tasks with a <code>repo_path</code> get an idempotent git worktree on branch <code>nexus/&lt;pipeline&gt;</code> (pipelines share one branch so stages build on each other; the main checkout is untouched). The framing injects the repo's AGENTS.md; dev specialists navigate by LSP symbols (serena) and ground library usage in live docs (context7). After each run: snapshot-commit of uncommitted work, then a junk-free <code>changes.diff</code> vs the base branch is captured for review. Humans merge; the system never does.</p>
    <h4>Memory pipeline</h4>
    <p>mem0 extracts memories from conversations → embeds them (768-dim, nomic-embed-text via ollama) → stores vectors in qdrant. The galaxy endpoint scrolls all vectors, PCA-projects to the 3 principal axes (numpy SVD), links top-3 cosine neighbors ≥0.45, k-means clusters in full 768-D, and names each cluster by its most distinctive terms (tf-idf style) — every visual property maps to a real quantity.</p>
    <h4>Security posture</h4>
    <p>HTTPS-only UI (self-signed, localhost); all server data HTML-escaped; command allowlists removed in favor of approval gates; secrets only in <code>~/.hermes/.env</code> (never in the repo — the setup repo ships a template and a credential scanner); guardian manifests pin every customization by SHA-256. The full reproducible install lives in the <b>Nexus-Agentic-Coding-Setup</b> repository: patches, full source, one-command installer, and this documentation.</p>
    <p style="margin-top:10px">Deep-dive documents (in the repo): <code>docs/PROJECT-DOCUMENTATION.md</code> (this chapter, expanded), <code>SPEC-REAL-AGENTS.md</code> (dispatch contract), <code>docs/JARVIS-VOICE.md</code> (voice pipeline), <code>CLAUDE.md</code> (engineering handbook).</p>
  </div>
</div>`;
}

// ═══════════════════ GUIDED HELP TOURS (the ? button — context-aware) ═══════════════════
// Each view gets a spotlight walkthrough in plain language. Steps whose
// element is missing (empty states) are skipped automatically.
const TOURS = {
  dashboard: [
    { sel: '#dashHero', title: 'The memory galaxy', body: 'This is your AI\'s actual mind, drawn live: every glowing star is one thing it remembers, placed by meaning — memories about similar topics sit close together and form colored regions. Drag inside it to look around, scroll on it to fly closer. The colored labels name each region using words taken from the memories themselves.' },
    { sel: '#heroExpand', title: 'Make it fullscreen', body: 'Click this (or scroll up when the page is at the top) and the widgets slide away so the galaxy fills the screen. Press Esc to bring everything back.' },
    { sel: '#nowStrip', title: 'What is running right now', body: 'Live ticker of tasks your agents are executing at this moment. If it\'s empty, nothing is running — that\'s normal when the kanban queue is empty.' },
    { sel: '.stat-grid', title: 'The vital signs', body: 'Agents, tasks, token usage (how much AI "fuel" was consumed) and system load at a glance. These update by themselves every few seconds.' },
    { sel: '#modelStrip', title: 'Session traffic light', body: 'How many AI conversations are running per model right now, against their limits (e.g. "5.2 2/8" = two of eight allowed). Red means saturated — new tasks briefly wait for a free slot.' },
  ],
  kanban: [
    { sel: '.kanban-board, #content', title: 'Your task board', body: 'Work flows left to right: Backlog (ideas) → Todo (ready) → In Progress (an agent is working) → Review (check the result) → Done. Drag cards between columns, or let agents pull work themselves.' },
    { sel: '[onclick*="describeTaskUI"], .btn-primary', title: 'The magic entrance ✨', body: 'Don\'t build tasks by hand — click "✨ Describe a task", type what you want in normal sentences, and the AI plans it: it may ask a few clarifying questions (each with a recommended answer), then proposes the task or a whole pipeline for you to approve.' },
    { sel: '#kWorkflow', title: 'Filters', body: 'Narrow the board by workflow or assignee. Tip: the 🎯 focus buttons (Projects and Workflows tabs) scope this whole board globally — the bar at the top shows what you are working in.' },
    { sel: '.kanban-card', title: 'A task card', body: 'Click any card to open its full record: description, budget, the agent working on it, attachments, its improvement loop, and every file it produced. The ⚑ flag shows which agent claimed it.' },
  ],
  workflows: [
    { sel: '#content', title: 'Workflows = rounds of work', body: 'A workflow chains tasks with dependencies: research feeds writing, code feeds review, review feeds fixes. Each stage starts automatically when its inputs are ready. Pipelines VISIT your durable projects (Projects tab): build v1, fix a bug, iterate a campaign — the project accumulates the results, pipelines come and go.' },
    { sel: '.btn-primary', title: 'Describe a goal', body: 'Click "✨ Describe a goal" and say what you want in plain words — e.g. "an online shop for GPUs". The AI asks smart questions, then proposes a full pipeline (plan → build → review → fix → verify) which you can trim before approving. Coding projects always get quality gates.' },
    { sel: '.agentic-row, .wf-card', title: 'A project', body: 'Click one to see its stages, their status, the improvement loop (🔁), and attached files. Green stages are done; the diagram shows what feeds what.' },
  ],
  deliverables: [
    { sel: '#content', title: 'Everything your agents produced', body: 'Every task\'s output lands here: reports, documents, images, whole applications. Click a file to preview it, or download it.' },
    { sel: '[onclick*="testAppUI"], .btn-sm', title: '▶ Test app', body: 'When a task built a program or website, this button launches it safely on your machine and opens it in a new browser tab. It stops by itself after 30 minutes.' },
  ],
  agents: [
    { sel: '#content', title: 'Your workforce', body: 'Each card is an agent lane — a worker that picks up one task at a time and executes it as a real AI session. They heal themselves: if one crashes, the watchdog restarts it within seconds.' },
    { sel: '.agent-card', title: 'Agent details', body: 'Click a card for its memory, message history, cost, and configuration — including auto-claim (whether it grabs unassigned tasks by itself) and a token spending cap.' },
  ],
  memory: [
    { sel: '[data-memtab="map3d"]', title: 'The 3D map', body: 'The same galaxy as the dashboard, with full tooling: search lights up matching memories, everything else fades to ghost-glow. Hover any star to read the memory, when it was stored, and its strongest associations.' },
    { sel: '#mem3dSearch', title: 'Search the mind', body: 'Type any topic — matching memories flare up and the rest dim. This is a live search through everything your AI remembers.' },
    { sel: '[data-memtab="semantic"]', title: 'The list views', body: 'The other tabs show the same memories as browsable lists: semantic memory (facts), per-agent memory, lessons your specialists learned from feedback, and shared context between agents.' },
  ],
  jarvis: [
    { sel: '#jReactorWrap', title: 'Talk to your AI — literally', body: 'Click the face to start talking; click again to stop (in conversation mode it detects silence by itself). Your speech is transcribed, answered by the AI, and spoken back with lip-synced video — the face IS the answer.' },
    { sel: '#jConvToggle', title: 'Hands-free conversation', body: 'Switch CONV on and JARVIS listens again automatically after each reply — a flowing conversation without clicking. It stops listening after 1.8s of silence.' },
    { sel: '#jInput', title: 'Typing works too', body: 'Prefer silence? Type here — the reply still streams in live, and JARVIS speaks it if the voice pipeline is on. Click the face mid-sentence to interrupt him.' },
    { sel: '.jarvis-stage', title: 'The stage is alive', body: 'The hologram room reacts to reality: rings pulse from your real microphone level while listening, violet particles orbit while thinking, and the room throbs with the actual voice amplitude while speaking.' },
  ],
  settings: [
    { sel: '#st-taskbudget', title: 'Budgets', body: 'How many tokens (AI "fuel") one task may use by default, and the daily total across everything. A stuck or runaway task can never spend past these fences. Retrying a task automatically grants it one more slice.' },
    { sel: '#st-total', title: 'Parallel sessions', body: 'How many AI conversations may run at once — in total and per model. The provider allows ~10 per model; staying at 8 leaves room for JARVIS and the wizard.' },
    { sel: '.data-table', title: 'Per-model control', body: 'Give each model its own limit and default thinking effort. More effort = smarter but slower and more expensive. "(automatic)" is the recommended setting: big models get maximum effort, light models stay economical.' },
  ],
  issues: [
    { sel: '#content', title: 'Your feedback backlog', body: 'Everything you filed with the 🐞 button, with the steps that led there attached. Work items from "new" → "in progress" → "resolved". This is the improvement queue for the system itself.' },
  ],
  usage: [
    { sel: '#content', title: 'Where the tokens go', body: 'Real consumption per provider and model, a 14-day trend, and estimated cost. The Hermes numbers come from its own billing counters — they are exact, not estimates.' },
  ],
  guardian: [
    { sel: '#content', title: 'The bodyguard', body: 'Guardian watches every protected file of your AI stack. If an update or accident changes one, it flags (or repairs) the drift. Green means everything matches the approved versions.' },
  ],
  agentic: [
    { sel: '#content', title: 'The safety systems', body: 'Approval gates (agents must ask before dangerous actions), the self-healing watchdog, verification runs, the cron scheduler and cost guardrails — the machinery that makes autonomy safe. Mostly it runs itself; check the badge for pending approvals.' },
  ],
  specialists: [
    { sel: '#content', title: 'Your expert team', body: 'Each specialist is a reusable expert (coder, reviewer, researcher…) with its own instructions and memory. They LEARN: feedback on their work becomes lessons they apply next time. Click one to see its playbook and what it has learned.' },
  ],
  skills: [
    { sel: '#content', title: 'The skill library', body: 'Skills are how-to manuals agents load when a task matches. Click any skill to edit it, or let the ✨ wizard draft a new one following best practices — you always review before it goes live.' },
  ],
  projects: [
    { sel: '.stats-strip', title: 'Your code projects', body: 'Every git repository and project folder on this machine. "Uncommitted" counts repos with unsaved changes - worth a look before ending the day.' },
    { sel: '.data-table', title: 'The Remote column', body: '"☁ backed up" = this repo also lives on GitHub (offsite backup). "⚠ local only" = it exists ONLY on this disk - click the row and publish it. For client work, local-only is a risk you do not want.' },
    { sel: '.proj-row', title: 'The delivery workflow', body: 'Click any repo: Publish (once - creates a private GitHub repo), Push (after every merged change - that push IS your backup), Tag release (when you deliver - marks the exact shipped state forever). Handover later = transfer the GitHub repo to the client organization.' },
  ],
  manual: [
    { sel: '#content', title: 'The manual', body: 'Everything explained for humans — from "what is this" to the full technical architecture. Use the chapter chips to jump around. The ? button on every other tab gives you a guided walkthrough of exactly that tab.' },
  ],
};

// ── Popup tours: when a modal/drawer is open, the ? explains THAT window ──
Object.assign(TOURS, {
  'task-detail-modal': [
    { sel: '#td-status, .modal-content', title: 'Status & priority', body: 'Status is the kanban column this task sits in — moving it here is the same as dragging the card. Priority orders it against other waiting tasks (1 is most urgent).' },
    { sel: '#td-model', title: 'Which AI model works on it', body: 'The default is your registry\'s "complicated tasks" model — right for real work. Lighter registry models are faster and cheaper, fine for simple mechanical jobs. Each model has its own traffic lane, so light tasks never queue behind heavy ones.' },
    { sel: '#td-budget', title: 'The spending fence', body: 'The maximum tokens (AI fuel) this task may consume. Empty = the default from Settings. If it runs out, the task pauses as "blocked: budget" — retrying grants exactly one more slice, so nothing ever runs away.' },
    { sel: '#td-depends', title: 'Dependencies', body: 'Tasks selected here must finish first; their results are handed to this task as input automatically. This is how pipelines pass work along.' },
    { sel: '[id^="attachRow"], .attach-list, #td-attachments', title: 'Attachments', body: 'Give the agent your material: PDFs, Office files, images. It is REQUIRED to read them before working. Results can come back in these formats too — just ask in the description.' },
    { sel: '[onclick*="loopViewerModal"], [onclick*="viewLoop"]', title: 'The improvement loop 🔁', body: 'Shows how this task self-corrects: which check triggers a rework, how many rounds are allowed, and whether it runs automatically (closed) or waits for you (open). You can regenerate or disable it here.' },
    { sel: '[onclick*="retryTask"], [onclick*="dispatchTask"]', title: 'Dispatch / Retry', body: 'Dispatch sends the task to an agent now. Retry re-runs a finished/failed task — add a sentence of feedback first and the agent must address it. Retry also grants a fresh budget slice.' },
    { sel: '.modal-content', title: 'Files & transcript', body: 'Every file the task produced is listed at the bottom with previews and downloads. The transcript link shows the agent\'s full working session — every command, every step, complete transparency.' },
  ],
  'task-create-modal': [
    { sel: '#m-task-title, .modal-content input', title: 'Title & description', body: 'Say what you want, for whom, and what "done" looks like — one sentence each is plenty. Tip: the ✨ wizard on the board does this planning for you and asks the right questions.' },
    { sel: '#m-task-specialist', title: 'Specialist', body: 'Pick an expert (coder, researcher, reviewer…) or leave it on "Agent decides". Specialists carry their own instructions and remember lessons from your past feedback.' },
    { sel: '#m-task-repo', title: '🧬 Existing code repository', body: 'For coding on YOUR projects: pick a repo and the agent works inside an isolated copy (a git branch), follows the repo\'s house rules, runs its tests, and delivers a reviewable diff. Your checkout is never touched.' },
    { sel: '#m-task-loop', title: 'Looping', body: 'Enable and the task self-corrects: failed checks send it back with the findings attached, automatically (closed mode) or with your approval (open mode). Choose quality (more rounds, judge involved) or speed.' },
  ],
  'wizard-modal': [
    { sel: '.modal-content h2, .modal-content', title: 'The proposed plan', body: 'The AI turned your description into stages. Each row is one task; arrows show what feeds what. Locked rows are quality gates (review, verification) — they exist so mistakes get caught before they reach you.' },
    { sel: '.modal-content input[type="checkbox"]', title: 'Trim it', body: 'Untick optional stages you don\'t want — dependents automatically reconnect around removed ones. Assumptions the AI made are listed; if one is wrong, cancel and rephrase your description.' },
    { sel: '#wf-repo', title: '🧬 Your code repository', body: 'For coding projects: pick a repo here and every coding stage works INSIDE it on an isolated branch — following the repo\'s house rules and tests — instead of building from scratch. You review the diff and merge it yourself.' },
    { sel: '#wf-client', title: '🏢 Client scope', body: 'Working for a client? Type their name and everything agents learn in this project goes into that client\'s private memory — invisible to other clients and to your personal chats. Generalized craft lessons still improve your specialists globally.' },
    { sel: '#wf-highstakes', title: '⚖ High stakes', body: 'Check this and every task of the project becomes eligible for the frontier judge — a stronger AI grading each deliverable against your quality rubric. Combined with a quality loop, judging happens automatically per version.' },
    { sel: '#wf-super', title: '✨ Super Result', body: 'A grounded frontier critic re-verifies each final deliverable with real tool access in a disposable sandbox — it re-reads sources, re-runs commands, files line comments, and loops the work until it verifies. Independent verification costs ~5–10× tokens; use it for work worth being right.' },
    { sel: '#wf-loop', title: '🔁 The improvement loop', body: 'On = failed checks and judge verdicts automatically send work back with the findings attached, then re-check. Quality mode allows more rounds and arms the auto-judge; speed mode keeps rounds minimal.' },
    { sel: '.modal-actions .btn-primary', title: 'Approve', body: 'Creates all tasks with their dependencies. Stages start on their own as their inputs become ready — watch progress on the board or the project page.' },
  ],
  'agent-drawer': [
    { sel: '#drawerBody .kv-row, #drawerBody', title: 'The agent\'s vitals', body: 'PID is its live process; heartbeat shows it\'s healthy (the watchdog restarts it within seconds if not); tasks done/failed is its track record.' },
    { sel: '#cfg-autoclaim', title: 'Auto-claim', body: 'On = this agent grabs unassigned Todo tasks by itself. Off = it only works on tasks you assign to it explicitly.' },
    { sel: '#cfg-maxtokens', title: 'Spending cap', body: 'A hard token ceiling for this lane. When reached, the watchdog pauses it as cost_capped — a per-worker fence on top of task budgets.' },
    { sel: '.dtab', title: 'Memory · Messages · Cost', body: 'The tabs show what this agent remembers, its message history with other agents, and exactly what it has consumed.' },
  ],
});

function tourContext() {
  // a visible popup wins over the underlying view
  const modal = document.getElementById('modal');
  if (modal && modal.style.display !== 'none' && modal.style.display !== '') {
    const mc = modal.innerHTML || '';
    if (document.getElementById('td-budget')) return 'task-detail-modal';
    if (document.getElementById('m-task-title') || document.getElementById('m-task-loop')) return 'task-create-modal';
    if (mc.includes('stage') || mc.includes('Assumptions') || mc.includes('pipeline')) return 'wizard-modal';
  }
  const drawer = document.getElementById('drawer');
  if (drawer && drawer.classList.contains('open')) return 'agent-drawer';
  return currentView;
}

let _tour = null;
function startTour(view) {
  endTour();
  const ctx = view === currentView ? tourContext() : view;
  const steps = (TOURS[ctx] || []).filter(s => document.querySelector(s.sel));
  if (!steps.length) { switchView('manual'); return; }
  _tour = { steps, i: 0 };
  const dim = document.createElement('div');
  dim.className = 'tour-dim'; dim.id = 'tourDim';
  dim.onclick = endTour;
  const spot = document.createElement('div');
  spot.className = 'tour-spot'; spot.id = 'tourSpot';
  const card = document.createElement('div');
  card.className = 'tour-card'; card.id = 'tourCard';
  document.body.append(dim, spot, card);
  showTourStep();
}

function showTourStep() {
  if (!_tour) return;
  const { steps, i } = _tour;
  const st = steps[i];
  const el = document.querySelector(st.sel);
  if (!el) { nextTourStep(1); return; }
  el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  const r = el.getBoundingClientRect();
  const spot = $('#tourSpot'), card = $('#tourCard');
  spot.style.cssText += `;left:${r.left - 6}px;top:${r.top - 6}px;width:${r.width + 12}px;height:${r.height + 12}px`;
  // card below the target if room, else above
  const below = r.bottom + 190 < innerHeight;
  card.innerHTML = `
    <h3>${esc(st.title)}</h3><p>${esc(st.body)}</p>
    <div class="tour-nav">
      <span class="tour-step-n">${i + 1} / ${steps.length}</span>
      ${i > 0 ? '<button class="btn-ghost" onclick="nextTourStep(-1)">← Back</button>' : ''}
      <button class="btn-primary" onclick="nextTourStep(1)">${i === steps.length - 1 ? 'Done ✓' : 'Next →'}</button>
    </div>`;
  // measure the REAL card, then pick the side with room and clamp fully
  // into the viewport — fixed guesses ran off-screen on tall/edge targets
  const cw = card.offsetWidth || 360, ch = card.offsetHeight || 180;
  const pad = 12, gap = 14;
  let top;
  if (r.bottom + gap + ch <= innerHeight - pad) top = r.bottom + gap;          // below
  else if (r.top - gap - ch >= pad) top = r.top - gap - ch;                    // above
  else top = Math.max(pad, Math.min(innerHeight - ch - pad,                    // beside
                                    r.top + r.height / 2 - ch / 2));
  let left = r.left;
  if (top > r.top - gap - ch && top < r.bottom + gap) {                        // beside: dodge the target
    left = (r.right + gap + cw <= innerWidth - pad) ? r.right + gap : r.left - gap - cw;
  }
  card.style.left = Math.max(pad, Math.min(innerWidth - cw - pad, left)) + 'px';
  card.style.top = Math.max(pad, Math.min(innerHeight - ch - pad, top)) + 'px';
}

function nextTourStep(dir) {
  if (!_tour) return;
  _tour.i += dir;
  if (_tour.i < 0) _tour.i = 0;
  if (_tour.i >= _tour.steps.length) { endTour(); return; }
  showTourStep();
}

function endTour() {
  _tour = null;
  ['tourDim', 'tourSpot', 'tourCard'].forEach(id => { const e = document.getElementById(id); if (e) e.remove(); });
}

// ═══════════════════ SETTINGS TAB (Settings v2 — registry · models · credentials) ═══════════════════
const settingsState = { fetched: false, dispatch: {}, model: {}, schema: null, credentials: [], defaults: null };
// Model registry (Settings v2): global + own rows, purpose routing, task-model list.
const modelState = {
  fetched: false, models: [], assignments: {}, sources: {},
  taskModels: ['glm-5.2', 'glm-5.1', 'glm-4.5-air'], purposes: {}, isAdmin: false,
};

async function ensureModels(force) {
  if (modelState.fetched && !force) return;
  try {
    const r = await api('GET', '/api/models');
    modelState.models = r.models || [];
    modelState.assignments = r.assignments || {};
    modelState.sources = r.assignment_sources || {};
    modelState.taskModels = (r.task_models && r.task_models.length) ? r.task_models : modelState.taskModels;
    modelState.purposes = r.purposes || {};
    modelState.isAdmin = !!r.is_admin;
    modelState.fetched = true;
  } catch { }
}

function modelById(id) { return modelState.models.find(m => m.id === id) || null; }
function hermesModels() { return modelState.models.filter(m => m.route === 'hermes' && m.enabled); }
function defaultTaskModelId() {
  const m = modelById(modelState.assignments.complicated);
  return m ? m.model_id : 'glm-5.2';
}
// Options for every per-task model <select> — built from the caller's registry.
function taskModelOptions(cur) {
  const def = defaultTaskModelId();
  const opts = [`<option value="" ${!cur ? 'selected' : ''}>${esc(def)} — default (your 'complicated tasks' model)</option>`];
  for (const mid of modelState.taskModels) {
    if (mid === def) continue;
    const row = modelState.models.find(m => m.model_id === mid && m.route === 'hermes');
    const label = row && row.label ? ` — ${row.label}` : '';
    opts.push(`<option value="${esc(mid)}" ${cur === mid ? 'selected' : ''}>${esc(mid)}${esc(label)}</option>`);
  }
  return opts.join('');
}

async function loadSettingsData() {
  try {
    const [d, m, sch, mods, creds] = await Promise.all([
      api('GET', '/api/settings?prefix=dispatch.'),
      api('GET', '/api/settings?prefix=model.'),
      api('GET', '/api/settings/schema'),
      api('GET', '/api/models'),
      api('GET', '/api/credentials'),
    ]);
    settingsState.dispatch = d.settings || {};
    settingsState.model = m.settings || {};
    settingsState.schema = sch;
    settingsState.credentials = creds.credentials || [];
    // Machine default keys — admin-only endpoint; members simply skip the panel.
    settingsState.defaults = null;
    if (sch && sch.is_admin) {
      try { settingsState.defaults = (await api('GET', '/api/credentials/defaults')).defaults || []; }
      catch { }
    }
    modelState.models = mods.models || [];
    modelState.assignments = mods.assignments || {};
    modelState.sources = mods.assignment_sources || {};
    modelState.taskModels = (mods.task_models && mods.task_models.length) ? mods.task_models : modelState.taskModels;
    modelState.purposes = mods.purposes || {};
    modelState.isAdmin = !!mods.is_admin;
    modelState.fetched = true;
    settingsState.fetched = true;
    if (currentView === 'settings') render();
  } catch (e) { toast('Settings load failed: ' + e.message, 'err'); }
}

// One registry item → one labeled input (generic renderer; docs/SPEC-SETTINGS-V2.md R1).
function settingItemHTML(it) {
  const id = 'sr-' + it.key.replace(/\./g, '-');
  const eff = it.effective !== undefined && it.effective !== '' ? it.effective : (it.default || '');
  let input;
  if (it.type === 'bool') {
    const opts = [['', `(default: ${eff === '1' ? 'on' : 'off'})`], ['1', 'on'], ['0', 'off']]
      .map(([v, t]) => `<option value="${v}" ${it.value === v ? 'selected' : ''}>${t}</option>`).join('');
    input = `<select class="form-select sr-item" id="${id}" data-key="${esc(it.key)}">${opts}</select>`;
  } else if (it.type === 'int' || it.type === 'float') {
    input = `<input class="form-input sr-item" id="${id}" data-key="${esc(it.key)}" type="number"
      ${it.min !== undefined ? `min="${it.min}"` : ''} ${it.max !== undefined ? `max="${it.max}"` : ''}
      ${it.type === 'float' ? 'step="any"' : ''} value="${esc(it.value || '')}" placeholder="${esc(eff)}">`;
  } else {
    input = `<input class="form-input sr-item" id="${id}" data-key="${esc(it.key)}"
      value="${esc(it.value || '')}" placeholder="${esc(eff)}" spellcheck="false">`;
  }
  const badges = (it.restart ? ' <span class="muted" title="Applies after a service restart">↻ restart</span>' : '')
    + (it.env ? ` <span class="muted" title="Falls back to the ${esc(it.env)} environment variable when unset">env</span>` : '');
  return `<div class="form-group" style="min-width:220px">
    <label class="form-label">${esc(it.label)}${badges}</label>${input}
    ${it.help ? `<div class="form-hint">${esc(it.help)}</div>` : ''}
  </div>`;
}

function settingsRegistryHTML() {
  const sch = settingsState.schema;
  if (!sch || !sch.is_admin) return '';
  return sch.sections.map(sec => `
    <div class="agentic-card" style="margin-top:14px"><div class="card-head"><h3>⚙ ${esc(sec.title)}</h3></div>
    <div class="card-body">
      <div class="form-hint" style="margin-bottom:8px">${esc(sec.desc)}. Empty field = default.</div>
      <div class="form-row" style="flex-wrap:wrap">${sec.items.map(settingItemHTML).join('')}</div>
    </div></div>`).join('');
}

const PURPOSE_ROUTES = { complicated: 'hermes', easy: 'hermes', mechanical: 'hermes', frontier_judge: 'cli' };

function modelsCardHTML() {
  const effOpts = (cur) => ['', 'minimal', 'low', 'medium', 'high', 'max'].map(v =>
    `<option value="${v}" ${cur === v ? 'selected' : ''}>${v || '(automatic)'}</option>`).join('');
  const d = settingsState.dispatch, mset = settingsState.model;
  const rows = modelState.models.map(mo => {
    const isHermes = mo.route === 'hermes';
    const mid = mo.model_id;
    const cred = settingsState.credentials.find(c => c.id === mo.credential_id);
    return `<tr ${mo.enabled ? '' : 'style="opacity:.45"'}>
      <td><code>${esc(mid)}</code>${mo.label ? `<div class="muted" style="font-size:11px">${esc(mo.label)}</div>` : ''}</td>
      <td>${esc(mo.provider)}${mo.user_id ? '' : ' <span class="muted" title="Global default model (admin-managed)">🌐</span>'}</td>
      <td>${mo.route === 'cli' ? 'CLI (judge)' : 'Hermes session'}</td>
      <td class="muted" style="font-size:11px">${cred ? `🔑 ••••${esc(cred.hint)}` : 'default key'}</td>
      <td>${isHermes ? `<input class="form-input" id="st-cap-${esc(mid)}" type="number" min="1" max="10" style="width:70px"
        value="${esc(d['dispatch.max_concurrent.' + mid] || '')}" placeholder="${esc(d['dispatch.max_concurrent_per_model'] || '8')}">` : '<span class="muted">—</span>'}</td>
      <td>${isHermes ? `<select class="form-select" id="st-eff-${esc(mid)}" style="width:130px">${effOpts(mset['model.effort.' + mid] || '')}</select>` : '<span class="muted">—</span>'}</td>
      <td style="white-space:nowrap">
        <button class="btn-ghost btn-sm" onclick="showModelModal('${esc(mo.id)}')">Edit</button>
        <button class="btn-ghost btn-sm" onclick="deleteModelRow('${esc(mo.id)}','${esc(mid)}')">✕</button>
      </td></tr>`;
  }).join('');
  const assignRows = Object.entries(modelState.purposes).map(([p, desc]) => {
    const wantRoute = PURPOSE_ROUTES[p] || 'hermes';
    const eligible = modelState.models.filter(m => m.enabled && m.route === wantRoute);
    const cur = modelState.assignments[p] || '';
    const opts = eligible.map(m =>
      `<option value="${esc(m.id)}" ${cur === m.id ? 'selected' : ''}>${esc(m.model_id)}${m.user_id ? '' : ' 🌐'}</option>`).join('');
    const src = modelState.sources[p] === 'user'
      ? `<button class="btn-ghost btn-sm" title="Back to the global default" onclick="clearAssignment('${esc(p)}')">↩ default</button>`
      : '<span class="muted" style="font-size:11px">global default</span>';
    return `<tr><td style="max-width:340px"><b>${esc(p.replace('_', ' '))}</b>
        <div class="muted" style="font-size:11px">${esc(desc)}</div></td>
      <td><select class="form-select st-assign" data-purpose="${esc(p)}" style="min-width:200px">
        <option value="">(none)</option>${opts}</select></td>
      <td>${src}</td></tr>`;
  }).join('');
  return `
    <div class="agentic-card" style="margin-top:14px"><div class="card-head"><h3>🧠 Models & routing</h3>
      <button class="btn-ghost btn-sm" onclick="showModelModal()">+ Add model</button></div><div class="card-body">
      <div class="form-hint" style="margin-bottom:8px">Your model registry: 🌐 rows are the machine defaults every user inherits; rows you add apply to <b>you only</b>. Hermes-session models run your tasks; CLI models power the frontier judge. Effort = how hard a GLM model thinks per call. Assign below <b>which model serves which purpose</b> — the wizard, dispatch, dev-pipeline floor and judge all follow these assignments.</div>
      <div style="overflow-x:auto"><table class="data-table">
        <thead><tr><th>Model</th><th>Provider</th><th>Runs via</th><th>API key</th><th>Max parallel</th><th>Default effort</th><th></th></tr></thead>
        <tbody id="modelRegistryRows">${rows || '<tr><td colspan="7" class="muted">No models yet — add one.</td></tr>'}</tbody></table></div>
      <h4 style="margin:14px 0 6px">Purpose routing${modelState.isAdmin ? ' <label style="font-weight:400;font-size:11.5px;margin-left:8px"><input type="checkbox" id="assignGlobal"> edit the global defaults (all users)</label>' : ''}</h4>
      <div style="overflow-x:auto"><table class="data-table">
        <thead><tr><th>Purpose</th><th>Model</th><th>Source</th></tr></thead>
        <tbody>${assignRows}</tbody></table></div>
      <div style="margin-top:10px"><button class="btn-ghost" onclick="saveAssignments()">Apply purpose routing</button></div>
    </div></div>`;
}

// Admin-only: the machine default keys (~/.hermes/.env) every user inherits.
function machineDefaultsHTML() {
  const defs = settingsState.defaults;
  if (!defs) return '';
  const rows = defs.map(d => {
    const status = d.managed
      ? `<span class="muted" style="font-size:11.5px">${esc(d.managed)}</span>`
      : (d.set ? `••••••••${esc(d.hint)}` : '<span style="color:var(--red,#f87171)">not set</span>');
    const editor = d.managed ? '<span class="muted">—</span>' : `
      <div style="display:flex;gap:6px">
        <input class="form-input" id="def-${esc(d.provider)}" type="password" autocomplete="off"
          placeholder="new key…" style="min-width:180px">
        <button class="btn-ghost btn-sm" onclick="saveDefaultKey('${esc(d.provider)}')">Rotate</button>
      </div>`;
    return `<tr><td><code>${esc(d.provider)}</code><div class="muted" style="font-size:11px">${esc(d.label)}</div></td>
      <td class="muted" style="font-size:11.5px">${d.env ? esc(d.env) : 'CLI auth'}</td>
      <td>${status}</td><td>${editor}</td></tr>`;
  }).join('');
  return `
    <h4 style="margin:16px 0 6px">Machine default keys <span class="muted" style="font-weight:400;font-size:11.5px">(admin — what everyone inherits when they set no personal key)</span></h4>
    <div class="form-hint" style="margin-bottom:6px">Stored in <code>~/.hermes/.env</code> (0600) — shown masked, never displayed after saving. Keys the Hermes gateway reads (zai, brave) apply to <b>new</b> Hermes work after <code>systemctl --user restart hermes-gateway</code>.</div>
    <div style="overflow-x:auto"><table class="data-table">
      <thead><tr><th>Provider</th><th>Env var</th><th>Current</th><th>Rotate</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
}

async function saveDefaultKey(provider) {
  const el = $(`#def-${CSS.escape(provider)}`);
  const value = (el || {}).value || '';
  if (!value) { toast('Paste the new key first', 'err'); return; }
  if (!confirm(`Rotate the MACHINE default ${provider} key? Every user without a personal key switches to it.`)) return;
  try {
    const r = await api('PUT', `/api/credentials/defaults/${provider}`, { value });
    el.value = '';
    toast(`Default ${provider} key rotated — ${r.note}`, 'ok', 7000);
    settingsState.fetched = false;
    loadSettingsData();
  } catch (e) { toast('Rotate failed: ' + e.message, 'err'); }
}

function credentialsCardHTML() {
  const rows = settingsState.credentials.map(c => `
    <tr><td><code>${esc(c.provider)}</code>${c.global ? ' <span class="muted" title="Machine-wide default override (admin-managed)">🌐</span>' : ''}</td>
      <td>••••••••${esc(c.hint)}</td>
      <td class="muted">${esc(c.label || '')}</td>
      <td><button class="btn-ghost btn-sm" onclick="deleteCredential('${esc(c.id)}','${esc(c.provider)}')">Remove</button></td></tr>`).join('');
  return `
    <div class="agentic-card" style="margin-top:14px"><div class="card-head"><h3>🔑 Providers & credentials</h3></div><div class="card-body">
      <div class="form-hint" style="margin-bottom:8px">Personal API keys — they apply to <b>your</b> tasks/judge runs only and are stored <b>encrypted</b>; saved keys are never shown again (last 4 characters only). No key here = the machine's default key keeps working. Provider slugs: <code>zai</code> (GLM tasks), <code>anthropic</code> (frontier judge)${modelState.isAdmin ? ', <code>langfuse_public</code>/<code>langfuse_secret</code> (observability, global)' : ''}.</div>
      ${rows ? `<div style="overflow-x:auto"><table class="data-table">
        <thead><tr><th>Provider</th><th>Key</th><th>Label</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`
      : '<div class="muted" style="font-size:12px;margin-bottom:6px">No keys saved — the machine defaults apply.</div>'}
      <div class="form-row" style="margin-top:10px;flex-wrap:wrap;align-items:flex-end">
        <div class="form-group"><label class="form-label">Provider</label>
          <input class="form-input" id="credProvider" placeholder="e.g. zai" autocapitalize="none" style="width:140px"></div>
        <div class="form-group"><label class="form-label">API key (write-only)</label>
          <input class="form-input" id="credValue" type="password" autocomplete="off" placeholder="paste key…"></div>
        <div class="form-group"><label class="form-label">Label (optional)</label>
          <input class="form-input" id="credLabel" placeholder="e.g. my Z.AI account" style="width:170px"></div>
        ${modelState.isAdmin ? '<label style="font-size:11.5px;align-self:center;white-space:nowrap"><input type="checkbox" id="credGlobal"> global (all users’ default)</label>' : ''}
        <button class="btn-primary" onclick="saveCredential()" style="align-self:center">Save key</button>
      </div>
      ${machineDefaultsHTML()}
    </div></div>`;
}

function viewSettings() {
  if (!settingsState.fetched) { loadSettingsData(); return skeletonView(); }
  return `
    ${modelsCardHTML()}
    ${credentialsCardHTML()}
    ${settingsRegistryHTML()}
    <div class="agentic-card" style="margin-top:14px"><div class="card-head"><h3>👥 Users & access</h3></div><div class="card-body" id="usersPanel">
      <div class="muted" style="font-size:12px">Loading users…</div>
    </div></div>
    <div class="agentic-card" style="margin-top:14px"><div class="card-head"><h3>🧭 Business Brain</h3></div><div class="card-body">
      <div class="form-hint" style="margin-bottom:8px">The business context + voice every agent reads before business deliverables.
        <strong>Each user fills their own</strong> — the owner's answers are the canonical identity, every other user gets a personal
        context that their tasks use. Answers save as you go; revise them here anytime.</div>
      <button class="btn-ghost" onclick="openOnboardingWizard()">🧭 Open the guided onboarding</button>
    </div></div>
    <div class="agentic-card" style="margin-top:14px"><div class="card-head"><h3>🛡 Related</h3></div><div class="card-body" style="display:flex;gap:10px;flex-wrap:wrap">
      <button class="btn-ghost" onclick="showWatchdogModal()">Watchdog configuration</button>
      <button class="btn-ghost" onclick="switchView('issues')">Known issues</button>
    </div></div>
    <div style="margin-top:14px;display:flex;gap:10px">
      ${settingsState.schema && settingsState.schema.is_admin ? '<button class="btn-primary" onclick="saveSettingsTab()">Save all settings</button>' : ''}
      <span class="muted" style="align-self:center;font-size:11.5px">Most settings apply immediately — workers read them live, per-model efforts reach Hermes without a restart; ↻-marked values need a service restart.</span>
    </div>`;
}

function bindSettings() { loadUsersPanel(); }

// ── Users & access (Block 1 multi-user) ──
async function loadUsersPanel() {
  const panel = $('#usersPanel');
  if (!panel) return;
  let users = null;
  try { users = await api('GET', '/api/users'); } catch { }
  const me = authState.user || {};
  if (!users) {
    // Member account (403) — offer only the self-service password change.
    panel.innerHTML = `
      <div class="form-hint" style="margin-bottom:8px">Signed in as <b>${esc(me.display_name || '?')}</b>. Ask the admin to manage accounts.</div>
      <button class="btn-ghost" onclick="showPasswordModal()">Change my password</button>`;
    return;
  }
  const rows = users.map(u => `
    <tr>
      <td><b>${esc(u.display_name)}</b> <span class="muted">@${esc(u.username)}</span>${u.id === me.id ? ' <span class="muted">(you)</span>' : ''}</td>
      <td>${esc(u.role)}</td>
      <td>${u.active ? (u.has_password ? '🔐 password set' : '⚠ no password') : '⛔ deactivated'}</td>
      <td style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="btn-ghost btn-sm" onclick="resetUserPassword('${esc(u.id)}','${esc(u.display_name)}')">Reset password</button>
        ${u.id !== me.id ? `<button class="btn-ghost btn-sm" onclick="toggleUserActive('${esc(u.id)}',${u.active ? 'false' : 'true'})">${u.active ? 'Deactivate' : 'Reactivate'}</button>` : ''}
      </td>
    </tr>`).join('');
  panel.innerHTML = `
    <div class="form-hint" style="margin-bottom:8px">
      With a single user, no login is asked — the machine works exactly as before.
      <b>Adding a second user turns the login screen on for everyone</b> (set your own
      password first). Each user gets their own tasks, projects, focus, memories and JARVIS.
    </div>
    <div style="overflow-x:auto"><table class="data-table">
      <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <div style="display:flex;gap:10px;margin-top:12px;flex-wrap:wrap">
      <button class="btn-ghost" onclick="showPasswordModal()">Change my password</button>
      <button class="btn-primary" onclick="showAddUserModal()">+ Add user</button>
    </div>`;
}

function showPasswordModal() {
  const me = authState.user || {};
  showModal(`
    <div class="modal-head"><h3>Change my password</h3></div>
    <div class="modal-body">
      ${me.has_password ? `<div class="form-group"><label class="form-label">Current password</label>
        <input class="form-input" id="pwCurrent" type="password" autocomplete="current-password"></div>` : ''}
      <div class="form-group" style="margin-top:10px"><label class="form-label">New password (min 8 characters)</label>
        <input class="form-input" id="pwNew" type="password" autocomplete="new-password"></div>
      <div style="display:flex;gap:10px;margin-top:14px">
        <button class="btn-primary" onclick="submitPasswordChange()">Save password</button>
        <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      </div>
    </div>`);
}

async function submitPasswordChange() {
  try {
    await api('POST', '/api/auth/password', {
      current: ($('#pwCurrent') || {}).value || '',
      password: $('#pwNew').value,
    });
    toast('Password saved', 'ok');
    closeModal();
    if (authState.user) authState.user.has_password = true;
    loadUsersPanel();
  } catch { }
}

function showAddUserModal() {
  showModal(`
    <div class="modal-head"><h3>Add user</h3></div>
    <div class="modal-body">
      <div class="form-hint" style="margin-bottom:10px">⚠ The moment this user exists, <b>everyone signs in with a password</b> — including you. Make sure your own password is set first.</div>
      <div class="form-row">
        <div class="form-group"><label class="form-label">Username</label>
          <input class="form-input" id="nuName" autocapitalize="none" placeholder="e.g. anna"></div>
        <div class="form-group"><label class="form-label">Display name</label>
          <input class="form-input" id="nuDisplay" placeholder="e.g. Anna"></div>
      </div>
      <div class="form-row" style="margin-top:10px">
        <div class="form-group"><label class="form-label">Password (min 8 characters)</label>
          <input class="form-input" id="nuPass" type="password" autocomplete="new-password"></div>
        <div class="form-group"><label class="form-label">Role</label>
          <select class="form-select" id="nuRole"><option value="member">member</option><option value="admin">admin</option></select></div>
      </div>
      <div style="display:flex;gap:10px;margin-top:14px">
        <button class="btn-primary" onclick="submitAddUser()">Create user</button>
        <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      </div>
    </div>`);
}

async function submitAddUser() {
  try {
    await api('POST', '/api/users', {
      username: $('#nuName').value.trim(),
      display_name: $('#nuDisplay').value.trim(),
      password: $('#nuPass').value,
      role: $('#nuRole').value,
    });
    toast('User created — login is now required for everyone', 'ok', 6000);
    closeModal();
    loadUsersPanel();
  } catch { }
}

async function resetUserPassword(uid, name) {
  const pw = prompt(`New password for ${name} (min 8 characters):`);
  if (!pw) return;
  try {
    await api('PATCH', `/api/users/${uid}`, { password: pw });
    toast(`Password reset for ${name} (their sessions were signed out)`, 'ok');
    loadUsersPanel();
  } catch { }
}

async function toggleUserActive(uid, active) {
  try {
    await api('PATCH', `/api/users/${uid}`, { active });
    loadUsersPanel();
  } catch { }
}

async function saveSettingsTab() {
  const body = {};
  // Generic registry inputs (Settings v2) — empty value = clear to default.
  document.querySelectorAll('.sr-item').forEach(el => { body[el.dataset.key] = el.value; });
  // Per-model concurrency + effort rows (hermes-route registry models).
  for (const mo of hermesModels()) {
    const mid = mo.model_id;
    const cap = ($(`#st-cap-${CSS.escape(mid)}`) || {}).value;
    body[`dispatch.max_concurrent.${mid}`] = cap ? String(Math.min(10, parseInt(cap) || 8)) : '';
    body[`model.effort.${mid}`] = ($(`#st-eff-${CSS.escape(mid)}`) || {}).value || '';
  }
  try {
    await api('PATCH', '/api/settings', body);
    settingsState.fetched = false;
    toast('Settings saved', 'ok');
    loadSettingsData();
  } catch (e) { toast('Save failed: ' + e.message, 'err'); }
}

// ── Settings v2: model registry CRUD + purpose routing + credentials ──

function showModelModal(modelRowId) {
  const m = modelRowId ? modelById(modelRowId) : null;
  const creds = settingsState.credentials;
  const credOpts = ['<option value="">(machine default key)</option>']
    .concat(creds.map(c =>
      `<option value="${esc(c.id)}" ${m && m.credential_id === c.id ? 'selected' : ''}>${esc(c.provider)} ••••${esc(c.hint)}${c.global ? ' 🌐' : ''}</option>`))
    .join('');
  showModal(`
    <div class="modal-head"><h3>${m ? 'Edit model' : 'Add model'}</h3></div>
    <div class="modal-body">
      <div class="form-hint" style="margin-bottom:10px">Hermes-session models run tasks (currently the Z.AI/GLM provider — more providers become task-routable when Hermes gains them); CLI models power the frontier judge via <code>judge.cmd</code> (e.g. Anthropic's Opus). ${modelState.isAdmin ? 'Global models are inherited by every user.' : 'Models you add apply to you only.'}</div>
      <div class="form-row">
        <div class="form-group"><label class="form-label">Provider slug</label>
          <input class="form-input" id="mm-provider" autocapitalize="none" placeholder="zai / anthropic / openai…" value="${esc(m ? m.provider : '')}"></div>
        <div class="form-group"><label class="form-label">Model id</label>
          <input class="form-input" id="mm-model" autocapitalize="none" placeholder="e.g. claude-opus-4-8" value="${esc(m ? m.model_id : '')}"></div>
      </div>
      <div class="form-row" style="margin-top:10px">
        <div class="form-group"><label class="form-label">Label (optional)</label>
          <input class="form-input" id="mm-label" placeholder="what it's good at" value="${esc(m ? (m.label || '') : '')}"></div>
        <div class="form-group"><label class="form-label">Runs via</label>
          <select class="form-select" id="mm-route">
            <option value="hermes" ${!m || m.route === 'hermes' ? 'selected' : ''}>Hermes session (tasks)</option>
            <option value="cli" ${m && m.route === 'cli' ? 'selected' : ''}>CLI (frontier judge)</option>
          </select></div>
      </div>
      <div class="form-row" style="margin-top:10px">
        <div class="form-group"><label class="form-label">API key</label>
          <select class="form-select" id="mm-cred">${credOpts}</select>
          <div class="form-hint">Keys are added under Providers & credentials.</div></div>
        <div class="form-group"><label class="form-label">Enabled</label>
          <select class="form-select" id="mm-enabled"><option value="1" ${!m || m.enabled ? 'selected' : ''}>yes</option><option value="0" ${m && !m.enabled ? 'selected' : ''}>no</option></select></div>
      </div>
      ${!m && modelState.isAdmin ? '<label style="font-size:11.5px;display:block;margin-top:10px"><input type="checkbox" id="mm-global"> global (inherited by every user)</label>' : ''}
      <div style="display:flex;gap:10px;margin-top:14px">
        <button class="btn-primary" onclick="submitModelModal(${m ? `'${esc(m.id)}'` : 'null'})">${m ? 'Save changes' : 'Add model'}</button>
        <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      </div>
    </div>`);
}

async function submitModelModal(modelRowId) {
  const body = {
    provider: $('#mm-provider').value.trim().toLowerCase(),
    model_id: $('#mm-model').value.trim(),
    label: $('#mm-label').value.trim(),
    route: $('#mm-route').value,
    credential_id: $('#mm-cred').value || null,
    enabled: $('#mm-enabled').value === '1',
  };
  if ($('#mm-global') && $('#mm-global').checked) body.global = true;
  try {
    if (modelRowId) await api('PATCH', `/api/models/${modelRowId}`, body);
    else await api('POST', '/api/models', body);
    toast(modelRowId ? 'Model updated' : 'Model added', 'ok');
    closeModal();
    settingsState.fetched = false;
    loadSettingsData();
  } catch (e) { toast('Model save failed: ' + e.message, 'err'); }
}

async function deleteModelRow(modelRowId, modelId) {
  if (!confirm(`Remove model ${modelId} from the registry? Purpose assignments pointing at it are cleared.`)) return;
  try {
    await api('DELETE', `/api/models/${modelRowId}`);
    toast('Model removed', 'ok');
    settingsState.fetched = false;
    loadSettingsData();
  } catch (e) { toast('Delete failed: ' + e.message, 'err'); }
}

async function saveAssignments() {
  const body = {};
  document.querySelectorAll('.st-assign').forEach(el => { body[el.dataset.purpose] = el.value || null; });
  if ($('#assignGlobal') && $('#assignGlobal').checked) body.global = true;
  try {
    await api('PUT', '/api/models/assignments', body);
    toast('Purpose routing applied — dispatch/wizard/judge follow it immediately', 'ok');
    settingsState.fetched = false;
    loadSettingsData();
  } catch (e) { toast('Routing save failed: ' + e.message, 'err'); }
}

async function clearAssignment(purpose) {
  try {
    await api('PUT', '/api/models/assignments', { [purpose]: null });
    settingsState.fetched = false;
    loadSettingsData();
  } catch (e) { toast('Failed: ' + e.message, 'err'); }
}

async function saveCredential() {
  const provider = $('#credProvider').value.trim().toLowerCase();
  const value = $('#credValue').value;
  if (!provider || !value) { toast('Provider and key are required', 'err'); return; }
  const body = { provider, value, label: $('#credLabel').value.trim() };
  if ($('#credGlobal') && $('#credGlobal').checked) body.global = true;
  try {
    await api('POST', '/api/credentials', body);
    $('#credValue').value = '';
    toast('Key saved (encrypted) — it will never be displayed again', 'ok', 5000);
    settingsState.fetched = false;
    loadSettingsData();
  } catch (e) { toast('Key save failed: ' + e.message, 'err'); }
}

async function deleteCredential(credId, provider) {
  if (!confirm(`Remove the ${provider} key? Sessions fall back to the machine default key.`)) return;
  try {
    await api('DELETE', `/api/credentials/${credId}`);
    toast('Key removed', 'ok');
    settingsState.fetched = false;
    loadSettingsData();
  } catch (e) { toast('Delete failed: ' + e.message, 'err'); }
}

// ── Always-visible per-model session strip (topbar) ──
function updateModelStrip() {
  const el = $('#modelStrip');
  if (!el || !state.quota) return;
  const inflight = state.quota.in_flight || {};
  const d = settingsState.dispatch || {};
  const globalCap = parseInt(d['dispatch.max_concurrent_per_model']) || state.quota.per_model_cap || 8;
  const stripModels = modelState.taskModels;
  const parts = stripModels.map(mo => {
    const n = inflight[mo] || 0;
    const cap = parseInt(d['dispatch.max_concurrent.' + mo]) || globalCap;
    const hot = n >= cap;
    return `<span style="${n ? 'color:var(--accent-2)' : ''}${hot ? ';color:var(--red,#f87171)' : ''}" title="${esc(mo)}: ${n} running of max ${cap}">${esc(mo.replace('glm-', ''))} ${n}/${cap}</span>`;
  });
  const extra = Object.keys(inflight).filter(k => !stripModels.includes(k));
  for (const k of extra) parts.push(`<span style="color:var(--accent-2)">${esc(k)} ${inflight[k]}</span>`);
  el.innerHTML = `<span class="muted">sessions</span> ` + parts.join(' <span class="muted">·</span> ');
}

// ═══════════════════ FEEDBACK → KNOWN ISSUES ═══════════════════
// Lightweight interaction journal: the feedback button attaches your recent
// actions + the last outputs so a filed issue is reproducible.
const uxLog = [];
function uxRecord(kind, text) {
  uxLog.push({ t: Date.now(), kind, text: String(text).slice(0, 300) });
  if (uxLog.length > 25) uxLog.shift();
}

function feedbackModal() {
  const recent = uxLog.slice(-8);
  showModal(`
    <h2>🐞 File feedback / a known issue</h2>
    <div class="view-intro" style="margin-bottom:8px">Describe what went wrong or what annoyed you. Your recent steps below get attached so the issue is reproducible — untick anything you don't want included.</div>
    <textarea class="form-textarea" id="fb-text" style="height:90px" placeholder="What happened? What did you expect instead?"></textarea>
    <div class="form-group" style="margin-top:8px"><label class="form-label">Attached context (your last steps in this view: ${esc(currentView)})</label>
      ${recent.map((e, i) => `
        <label style="display:flex;gap:8px;font-size:11.5px;align-items:baseline;margin-top:3px">
          <input type="checkbox" id="fb-ctx-${i}" checked>
          <span class="chip" style="flex-shrink:0">${e.kind}</span>
          <span style="font-family:var(--font-mono);color:var(--text-dim);word-break:break-all">${esc(e.text)}</span>
        </label>`).join('') || '<div class="muted" style="font-size:11.5px">No recent interactions recorded yet.</div>'}
    </div>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" id="fb-save">Save to Known Issues</button>
    </div>`);
  $('#fb-save').onclick = async () => {
    const text = ($('#fb-text') || {}).value || '';
    if (!text.trim()) { toast('Describe the issue first', 'err'); return; }
    const ctx = recent.filter((_, i) => ($(`#fb-ctx-${i}`) || {}).checked)
      .map(e => ({ ts: e.t, kind: e.kind, text: e.text }));
    try {
      await api('POST', '/api/known-issues', { feedback: text.trim(), view: currentView, context: ctx });
      closeModal();
      toast('Filed — see the Known Issues tab', 'ok');
    } catch (e) { toast('Save failed: ' + e.message, 'err'); }
  };
}

const kiState = { fetched: false, issues: [] };
async function loadKnownIssues() {
  try {
    kiState.issues = (await api('GET', '/api/known-issues')).issues || [];
    kiState.fetched = true;
    const open = kiState.issues.filter(i => i.status !== 'resolved').length;
    const b = $('#kiBadge');
    if (b) { b.textContent = open; b.style.display = open ? 'inline-block' : 'none'; }
    if (currentView === 'issues') render();
  } catch { }
}

function viewKnownIssues() {
  if (!kiState.fetched) { loadKnownIssues(); return skeletonView(); }
  const rows = kiState.issues.map(i => {
    let ctx = [];
    try { ctx = JSON.parse(i.context || '[]'); } catch { }
    return `
    <div class="agentic-row">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span class="chip ${{ new: 'c-red', in_progress: 'c-orange', resolved: 'c-green' }[i.status] || ''}">${esc(i.status)}</span>
        <strong style="flex:1">${esc(i.feedback).slice(0, 160)}</strong>
        <span class="muted" style="font-size:11px;font-family:var(--font-mono)">${fmtAgo(i.ts)} · ${esc(i.view || '?')}</span>
        <select class="form-select" style="width:130px;padding:2px 6px" onchange="kiSetStatus('${esc(i.id)}', this.value)">
          ${['new', 'in_progress', 'resolved'].map(s => `<option value="${s}" ${i.status === s ? 'selected' : ''}>${s}</option>`).join('')}
        </select>
        <button class="btn-sm danger" onclick="kiDelete('${esc(i.id)}')">✕</button>
      </div>
      ${i.feedback.length > 160 ? `<div style="font-size:12px;color:var(--text-dim);white-space:pre-wrap">${esc(i.feedback)}</div>` : ''}
      ${ctx.length ? `<details style="font-size:11.5px;color:var(--text-dim)"><summary style="cursor:pointer">interaction context (${ctx.length} steps)</summary>
        ${ctx.map(e => `<div style="font-family:var(--font-mono);margin-top:2px"><span class="chip">${esc(e.kind || '?')}</span> ${esc(e.text || '')}</div>`).join('')}</details>` : ''}
    </div>`;
  }).join('');
  return `
    <div class="view-intro" style="margin-bottom:12px">Everything you filed via the 🐞 button, with the steps that led there — work this list down to improve the system. ${kiState.issues.length} issue(s).</div>
    <div style="display:flex;flex-direction:column;gap:6px">${rows || '<div class="empty"><span class="e-ico">🐞</span>No known issues filed — the 🐞 button (bottom right) records one with your recent steps attached.</div>'}</div>`;
}

async function kiSetStatus(id, status) {
  try { await api('PATCH', `/api/known-issues/${id}`, { status }); loadKnownIssues(); }
  catch (e) { toast('Update failed: ' + e.message, 'err'); }
}

async function kiDelete(id) {
  try { await api('DELETE', `/api/known-issues/${id}`); loadKnownIssues(); }
  catch (e) { toast('Delete failed: ' + e.message, 'err'); }
}

// ═══════ RESULT REVIEW v2 (side-by-side, syntax highlight, line comments — SPEC-BLOCK2 R1) ═══════
let _review = null;

async function reviewTaskUI(taskId, title) {
  showModal(`<h2>🔍 Review changes — ${esc(title || taskId)}</h2>
    <div class="loading" style="padding:40px;text-align:center">Comparing versions…</div>`);
  try {
    const [r, cr] = await Promise.all([
      api('GET', `/api/tasks/${taskId}/review`),
      api('GET', `/api/tasks/${taskId}/review/comments`).catch(() => ({ comments: [] })),
    ]);
    _review = { r, taskId, title: title || taskId, sel: 0, composing: null,
                comments: cr.comments || [],
                mode: localStorage.getItem('nexusReviewMode') || 'unified' };
    renderReviewModal();
  } catch (e) {
    showModal(`<h2>🔍 Review</h2><div class="empty">${esc(e.message)}</div>
      <div class="modal-actions"><button class="btn-primary" onclick="closeModal()">Close</button></div>`);
  }
}

// `l.h` is server-generated Pygments HTML whose text content Pygments itself
// escaped — the ONE sanctioned raw-HTML injection; everything else stays esc().
const dlHTML = l => l.h !== undefined ? l.h : esc(l.s);
// A comment anchors to the line's REAL file position: deletions to the old
// side, additions and context to the new side.
const rcAnchor = l => l.t === '-' ? { side: 'old', line: l.o } : { side: 'new', line: l.n };
const rcOpenCount = () => (_review.comments || []).filter(c => c.status === 'open').length;
const rcFileCount = path => (_review.comments || []).filter(c => c.status === 'open' && c.file_path === path).length;

function renderReviewModal() {
  const { r, mode, title } = _review;
  const files = r.files || [];
  const statChip = f => `<span class="review-stat"><span class="rf-add">+${f.additions}</span> <span class="rf-del">−${f.deletions}</span></span>`;
  const icon = f => f.status === 'added' ? '🟢' : f.status === 'deleted' ? '🔴' : '🟡';
  const nOpen = rcOpenCount();
  showModal(`
    <h2 style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">🔍 ${esc(title)}
      <span class="chip">${esc(r.mode === 'git' ? 'git diff' : 'version comparison')}</span>
      <span class="review-toggle" id="rvToggle">
        <button class="${mode === 'unified' ? 'active' : ''}" onclick="setReviewMode('unified')">Unified</button>
        <button class="${mode === 'split' ? 'active' : ''}" onclick="setReviewMode('split')">Side-by-side</button>
      </span>
      <span class="review-stat" style="margin-left:auto"><span class="rf-add">+${r.additions || 0}</span> <span class="rf-del">−${r.deletions || 0}</span> · ${files.length} file(s)</span></h2>
    <div class="view-intro" style="margin-bottom:10px">${esc(r.source || '')}${r.note ? ' — ' + esc(r.note) : ''}. 🟢 added · 🟡 changed · 🔴 removed — click a file to inspect it, hover a line and hit ＋ to comment.</div>
    <div id="rvCritic"></div>
    ${files.length ? `
    <div class="review-layout">
      <div class="review-files">
        ${files.map((f, i) => `
          <div class="review-file ${i === _review.sel ? 'active' : ''}" onclick="_review.sel=${i};_review.composing=null;renderReviewFilePane()" id="rf-${i}">
            <span>${icon(f)}</span><span class="rf-path" title="${esc(f.path)}">${esc(f.path)}</span>${rcFileCount(f.path) ? `<span class="chip c-accent" style="padding:1px 7px">💬${rcFileCount(f.path)}</span>` : ''}${statChip(f)}
          </div>`).join('')}
      </div>
      <div class="review-pane" id="reviewPane"></div>
    </div>` : '<div class="empty"><span class="e-ico">✓</span>No changes to review — output is identical to the previous version.</div>'}
    <div class="modal-actions" style="justify-content:space-between;align-items:center">
      <span class="muted" style="font-size:12px" id="rvFooterInfo">${nOpen
        ? `💬 <b>${nOpen}</b> open comment(s) — they attach to the next retry as line-by-line feedback`
        : 'Line comments you add here become the feedback of the next retry.'}</span>
      <div style="display:flex;gap:10px">
        ${nOpen ? `<button class="btn-ghost" style="border-color:var(--accent-2)" onclick="reviewRetryUI()">↻ Retry with this feedback</button>` : ''}
        <button class="btn-primary" onclick="closeModal()">Close</button>
      </div>
    </div>`);
  if (files.length) renderReviewFilePane();
  rvLoadCritic();
}

// Super Result: collapsible critic panel in the review modal — summary,
// contradictions, missing list, and the revision brief the next retry rides.
async function rvLoadCritic() {
  const box = $('#rvCritic');
  if (!box || !_review || !_review.taskId) return;
  let c;
  try { c = await api('GET', `/api/tasks/${_review.taskId}/critic`); } catch { return; }
  if (!box.isConnected || !c || !c.verdict || c.verdict === 'running') return;
  const p = c.parsed || {};
  const cls = { SHIP: 'c-green', REVISE: 'c-orange', REWRITE: 'c-red' }[c.verdict] || 'c-red';
  const li = (arr, f) => (arr || []).map(x => `<li style="margin:2px 0">${f(x)}</li>`).join('');
  box.innerHTML = `
    <details style="margin-bottom:10px;border:1px solid rgba(124,92,255,.3);border-radius:8px;padding:6px 10px">
      <summary style="cursor:pointer;font-size:12.5px">🤖 Critic — round ${c.round || 0}
        <span class="chip ${cls}" style="margin-left:6px">${esc(c.verdict)}</span>
        ${c.open_critic_comments ? `<span class="chip c-accent">💬 ${c.open_critic_comments} auto-comment(s) below</span>` : ''}</summary>
      <div style="font-size:12px;margin-top:6px;display:flex;flex-direction:column;gap:6px">
        ${p.summary ? `<div>${esc(p.summary)}</div>` : ''}
        ${(p.contradictions || []).length ? `<div><strong>Contradictions</strong><ul style="margin:2px 0 0 16px">${li(p.contradictions, x => `<em>${esc(x.with || '')}</em>: ${esc(x.a || '')} ⟂ ${esc(x.b || '')}${x.resolution_hint ? ' — ' + esc(x.resolution_hint) : ''}`)}</ul></div>` : ''}
        ${(p.missing || []).length ? `<div><strong>Missing</strong><ul style="margin:2px 0 0 16px">${li(p.missing, x => `${esc(x.what || '')}${x.why_it_matters ? ' — ' + esc(x.why_it_matters) : ''}`)}</ul></div>` : ''}
        ${p.revision_brief ? `<div><strong>Revision brief (rides the next retry)</strong><div style="white-space:pre-wrap;color:var(--text-dim);margin-top:2px">${esc(p.revision_brief)}</div></div>` : ''}
        ${p.learning_note ? `<div style="color:var(--text-dim)">📖 ${esc(p.learning_note)}</div>` : ''}
      </div>
    </details>`;
}

function setReviewMode(m) {
  _review.mode = m;
  localStorage.setItem('nexusReviewMode', m);
  renderReviewModal();
}

function rcThreadHTML(f, l) {
  const a = rcAnchor(l);
  const list = (_review.comments || []).filter(c =>
    c.file_path === f.path && c.side === a.side && c.line_no === a.line);
  if (!list.length) return '';
  const srcChip = c => c.source === 'critic'
    ? '<span class="chip c-accent" style="padding:1px 7px;font-size:10px">🤖 AI critic</span> '
    : c.source === 'judge'
      ? '<span class="chip c-blue" style="padding:1px 7px;font-size:10px">⚖ judge</span> ' : '';
  return `<div class="rc-thread">` + list.map(c => `
    <div class="rc-comment ${esc(c.status)}"${c.source === 'critic' || c.source === 'judge'
      ? ' style="border-left:2px solid var(--accent)"' : ''}>
      <div>${srcChip(c)}${esc(c.body)}</div>
      <div class="rc-meta">${c.status === 'open'
      ? `<span>open — attaches to the next retry</span>
         <button class="btn-icon" title="Edit" onclick="rcEdit('${esc(c.id)}')">✏️</button>
         <button class="btn-icon" title="Delete" onclick="rcDelete('${esc(c.id)}')">✕</button>`
      : `<span>✓ sent with a retry${c.consumed_at ? ' ' + fmtAgo(c.consumed_at) : ''}</span>`}</div>
    </div>`).join('') + `</div>`;
}

function rcComposerHTML() {
  return `<div class="rc-composer">
    <textarea id="rcInput" rows="2" placeholder="What should change on this line?"></textarea>
    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button class="btn-ghost" onclick="rcCancel()">Cancel</button>
      <button class="btn-primary" onclick="rcSave()">💬 Comment</button>
    </div>
  </div>`;
}

function uniLineHTML(f, hi, l, li) {
  const composerHere = _review.composing && _review.composing.hi === hi && _review.composing.li === li;
  return `<div class="diff-line ${l.t === '+' ? 'add' : l.t === '-' ? 'del' : ''}">
      <span class="dl-num">${l.o ?? ''}</span><span class="dl-num">${l.n ?? ''}</span>
      <button class="dl-cbtn" title="Comment on this line" onclick="rcCompose(${hi},${li})">＋</button>
      <span class="diff-sign">${l.t === ' ' ? '' : esc(l.t)}</span><pre>${dlHTML(l)}</pre>
    </div>` + rcThreadHTML(f, l) + (composerHere ? rcComposerHTML() : '');
}

function splitCellHTML(f, ent, side) {
  if (!ent) return `<div class="split-cell empty"><span class="dl-num"></span><pre></pre></div>`;
  const { l, hi, li } = ent;
  const cls = l.t === '+' ? 'add' : l.t === '-' ? 'del' : '';
  const num = side === 'old' ? (l.o ?? '') : (l.n ?? '');
  // the ＋ affordance lives where the anchor is: old cell for deletions,
  // new cell for additions AND context
  const canComment = (side === 'old' && l.t === '-') || (side === 'new' && l.t !== '-');
  return `<div class="split-cell ${cls}">
      <span class="dl-num">${num}</span>
      ${canComment ? `<button class="dl-cbtn" title="Comment on this line" onclick="rcCompose(${hi},${li})">＋</button>` : ''}
      <pre>${dlHTML(l)}</pre>
    </div>`;
}

function splitHunkHTML(f, h, hi) {
  const lines = (h.lines || []).map((l, li) => ({ l, hi, li }));
  const rows = [];
  let i = 0;
  while (i < lines.length) {
    if (lines[i].l.t === ' ') { rows.push([lines[i], lines[i]]); i++; continue; }
    const dels = [], adds = [];
    while (i < lines.length && lines[i].l.t === '-') dels.push(lines[i++]);
    while (i < lines.length && lines[i].l.t === '+') adds.push(lines[i++]);
    if (!dels.length && !adds.length) { i++; continue; }
    for (let k = 0; k < Math.max(dels.length, adds.length); k++) {
      rows.push([dels[k] || null, adds[k] || null]);
    }
  }
  return `<div class="diff-hunk"><div class="diff-hunk-head">${esc(h.header)}</div>` +
    rows.map(([L, R]) => {
      let out = `<div class="split-row">${splitCellHTML(f, L, 'old')}${splitCellHTML(f, R, 'new')}</div>`;
      if (L) out += rcThreadHTML(f, L.l);
      if (R && R !== L) out += rcThreadHTML(f, R.l);
      const c = _review.composing;
      if (c && c.hi === hi && ((L && L.li === c.li) || (R && R.li === c.li))) out += rcComposerHTML();
      return out;
    }).join('') + `</div>`;
}

function renderReviewFilePane() {
  const { r, sel, mode } = _review;
  const f = (r.files || [])[sel];
  const pane = document.getElementById('reviewPane');
  if (!f || !pane) return;
  document.querySelectorAll('.review-file').forEach((el, i) =>
    el.classList.toggle('active', i === sel));
  let html = `<div style="margin-bottom:8px;font-size:12px;color:var(--text-dim)">
    <b>${esc(f.path)}</b> · ${esc(f.status)}${f.kind === 'pdf' ? ' · 📄 PDF (compared by extracted text)' : ''}</div>`;
  if (f.kind === 'image') {
    html += `<div style="display:flex;gap:14px;flex-wrap:wrap">
      ${f.old_size != null ? `<div><div class="muted" style="font-size:11px">previous (${(f.old_size / 1024).toFixed(0)} KB)</div></div>` : ''}
      ${f.new_url ? `<div><div class="muted" style="font-size:11px">current (${((f.new_size || 0) / 1024).toFixed(0)} KB)</div><img src="${esc(f.new_url)}" style="max-width:420px;max-height:320px;border-radius:10px;border:1px solid var(--border)"></div>` : ''}
    </div>`;
  } else if (f.binary && !(f.hunks || []).length) {
    html += `<div class="empty" style="padding:20px">Binary file — ${f.status}${f.old_size != null ? `, ${(f.old_size / 1024).toFixed(0)} KB` : ''}${f.new_size != null ? ` → ${(f.new_size / 1024).toFixed(0)} KB` : ''}</div>`;
  } else if (!(f.hunks || []).length) {
    html += `<div class="empty" style="padding:20px">${f.status === 'added' ? 'New file (preview it under the task\'s Files section).' : 'No line-level comparison available.'}</div>`;
  } else if (mode === 'split') {
    html += (f.hunks || []).map((h, hi) => splitHunkHTML(f, h, hi)).join('');
  } else {
    html += (f.hunks || []).map((h, hi) => `
      <div class="diff-hunk">
        <div class="diff-hunk-head">${esc(h.header)}</div>
        ${(h.lines || []).map((l, li) => uniLineHTML(f, hi, l, li)).join('')}
      </div>`).join('');
  }
  const keepScroll = pane.scrollTop;
  pane.innerHTML = html;
  pane.scrollTop = _review.composing ? keepScroll : 0;
  const inp = document.getElementById('rcInput');
  if (inp) inp.focus();
}

function rcCompose(hi, li) {
  _review.composing = { hi, li };
  renderReviewFilePane();
}

function rcCancel() {
  _review.composing = null;
  renderReviewFilePane();
}

async function rcSave() {
  const { r, sel, taskId, composing } = _review;
  if (!composing) return;
  const f = r.files[sel];
  const l = f.hunks[composing.hi].lines[composing.li];
  const a = rcAnchor(l);
  const body = (document.getElementById('rcInput')?.value || '').trim();
  if (!body) { toast('Write the comment first', 'err'); return; }
  try {
    await api('POST', `/api/tasks/${taskId}/review/comments`,
      { file_path: f.path, side: a.side, line_no: a.line, line_text: l.s, body });
    _review.composing = null;
    await rcReload();
  } catch (e) { toast('Comment failed: ' + e.message, 'err'); }
}

async function rcReload() {
  try {
    const cr = await api('GET', `/api/tasks/${_review.taskId}/review/comments`);
    _review.comments = cr.comments || [];
  } catch { /* keep the stale list */ }
  renderReviewModal();
}

async function rcEdit(id) {
  const c = (_review.comments || []).find(x => x.id === id);
  if (!c) return;
  const nb = prompt('Edit comment:', c.body);
  if (nb == null || !nb.trim()) return;
  try {
    await api('PATCH', `/api/tasks/${_review.taskId}/review/comments/${id}`, { body: nb.trim() });
    await rcReload();
  } catch (e) { toast('Edit failed: ' + e.message, 'err'); }
}

async function rcDelete(id) {
  if (!confirm('Delete this comment?')) return;
  try {
    await api('DELETE', `/api/tasks/${_review.taskId}/review/comments/${id}`);
    await rcReload();
  } catch (e) { toast('Delete failed: ' + e.message, 'err'); }
}

async function reviewRetryUI() {
  const n = rcOpenCount();
  if (!confirm(`Re-run this task with your ${n} line comment(s) attached as feedback? The current deliverable is versioned, not destroyed.`)) return;
  try {
    await api('POST', `/api/tasks/${_review.taskId}/retry`, { feedback: null });
    toast('Task queued for retry — your line comments are attached', 'ok');
    closeModal();
    state.tasks = await api('GET', '/api/tasks');
    await loadAgenticData(); // the superseded approval row disappears
    render();
  } catch (e) { toast('Retry failed: ' + e.message, 'err'); }
}

async function reviewWorkflowUI(wfId, name) {
  showModal(`<h2>🔍 Review results — ${esc(name)}</h2>
    <div class="loading" style="padding:40px;text-align:center">Collecting member task changes…</div>`);
  try {
    const r = await api('GET', `/api/workflows/${wfId}/review`);
    const rows = (r.tasks || []).map(t => `
      <div class="agentic-row" style="cursor:pointer" onclick="reviewTaskUI('${esc(t.task_id)}','${esc((t.title || '').slice(0, 60))}')">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <strong style="flex:1">${esc(t.title)}</strong>
          <span class="chip ${t.status === 'done' ? 'c-green' : ''}">${esc(t.status)}</span>
          ${t.error ? `<span class="chip c-red">${esc(t.error)}</span>`
        : `<span class="chip">${esc(t.mode === 'git' ? 'git' : 'versions')}</span>
           <span class="review-stat">${t.files} file(s) · <span class="rf-add">+${t.additions}</span> <span class="rf-del">−${t.deletions}</span></span>`}
        </div>
      </div>`).join('');
    showModal(`<h2>🔍 Review results — ${esc(name)}</h2>
      <div class="view-intro" style="margin-bottom:10px">Each stage's changes since its previous version — click one for the file-by-file comparison.</div>
      <div style="display:flex;flex-direction:column;gap:6px;max-height:55vh;overflow-y:auto">
        ${rows || '<div class="empty">No task output yet.</div>'}</div>
      <div class="modal-actions"><button class="btn-primary" onclick="closeModal()">Close</button></div>`);
  } catch (e) { toast('Review failed: ' + e.message, 'err'); }
}

// ═══════════════════ APP PREVIEW (▶ test a task's program output live) ═══════════════════
let appPreviewPoll = null;

async function testAppUI(taskId, title) {
  let r;
  try { r = await api('POST', `/api/tasks/${taskId}/app/start`); }
  catch (e) { toast('Could not start the app: ' + e.message, 'err'); return; }
  appPreviewModal(taskId, title, r);
}

function appPreviewModal(taskId, title, info) {
  if (appPreviewPoll) { clearInterval(appPreviewPoll); appPreviewPoll = null; }
  showModal(`
    <h2>▶ Test app — ${esc(title || taskId)}</h2>
    <div class="view-intro" style="margin-bottom:8px">${esc(info.label || '')} · <span style="font-family:var(--font-mono)">${esc(info.url || '')}</span></div>
    <div id="ap-state" class="chip c-orange">${info.installing ? '📦 installing dependencies… (first run can take minutes)' : '⏳ starting…'}</div>
    <div class="form-group" style="margin-top:10px"><label class="form-label">Live log</label>
      <pre id="ap-log" style="max-height:280px;overflow-y:auto;font-size:11px;background:rgba(0,0,0,.35);border-radius:8px;padding:8px 10px;white-space:pre-wrap">…</pre></div>
    <div class="form-hint">The app runs on its own local port and stops automatically after 30 minutes (or press Stop). It opens in a new tab as soon as it answers.</div>
    <div class="modal-actions" style="justify-content:space-between">
      <button class="btn-sm danger" onclick="stopAppUI('${esc(taskId)}')">⏹ Stop app</button>
      <div style="display:flex;gap:10px">
        <a class="btn-ghost" id="ap-open" href="${esc(info.url || '#')}" target="_blank" style="text-decoration:none;display:none">↗ Open app</a>
        <button class="btn-primary" onclick="closeAppPreview()">Close window (app keeps running)</button>
      </div>
    </div>`);
  let opened = false;
  const tick = async () => {
    if (!$('#ap-state')) { clearInterval(appPreviewPoll); appPreviewPoll = null; return; }
    try {
      const [st, lg] = await Promise.all([
        api('GET', `/api/tasks/${taskId}/app`),
        api('GET', `/api/tasks/${taskId}/app/log`),
      ]);
      const logEl = $('#ap-log');
      if (logEl) { logEl.textContent = lg.log || '…'; logEl.scrollTop = logEl.scrollHeight; }
      const run = st.running;
      const stEl = $('#ap-state');
      const beTxt = r => r.backend_port ? (' · API backend :' + r.backend_port + (r.backend_ready ? ' ✅' : ' ⏳')) : '';
      if (run && run.ready) {
        stEl.className = 'chip c-green';
        stEl.textContent = '✅ running — ' + run.url + beTxt(run);
        const a = $('#ap-open');
        if (a) { a.style.display = 'inline-block'; a.href = run.url; }
        if (!opened) { opened = true; window.open(run.url, '_blank'); }
      } else if (run) {
        stEl.className = 'chip c-orange';
        stEl.textContent = (run.state === 'installing'
          ? '📦 installing dependencies… (first run can take minutes)'
          : '⏳ starting — waiting for the app to answer on ' + run.url) + beTxt(run);
      } else if (st.exited) {
        stEl.className = 'chip c-red';
        stEl.textContent = '✕ the app exited before becoming ready — see the log above';
        clearInterval(appPreviewPoll); appPreviewPoll = null;
      } else {
        stEl.className = 'chip';
        stEl.textContent = 'stopped';
        clearInterval(appPreviewPoll); appPreviewPoll = null;
      }
    } catch { /* transient */ }
  };
  tick();
  appPreviewPoll = setInterval(tick, 2500);
}

function closeAppPreview() {
  if (appPreviewPoll) { clearInterval(appPreviewPoll); appPreviewPoll = null; }
  closeModal();
}

async function stopAppUI(taskId) {
  if (appPreviewPoll) { clearInterval(appPreviewPoll); appPreviewPoll = null; }
  try { await api('POST', `/api/tasks/${taskId}/app/stop`); toast('App stopped', 'ok'); }
  catch (e) { toast('Stop failed: ' + e.message, 'err'); }
  closeModal();
}

// ═══════════════════ PROJECT APP PREVIEW (▶ run the WHOLE project — current or a past state) ═══════════════════
// Unlike the per-task ▶ Test app, this assembles the COMPLETE project (every
// stage's changes) into a disposable copy and runs that. Any earlier state can
// be started NEXT TO the latest one — each gets its own port — so old and new
// compare side by side (did the newest stage break something?).
let projAppPoll = null;
let projAppFocus = null;      // version whose log the pane shows
let projAppStarted = new Set(); // versions started from this modal → auto-open on ready
let projAppLastHtml = '';

async function projectAppUI(wfId, name) {
  let info;
  try { info = await api('GET', `/api/workflows/${wfId}/app`); }
  catch (e) { toast('Could not load project states: ' + e.message, 'err'); return; }
  projectAppModal(wfId, name, info);
}

function projectAppModal(wfId, name, info) {
  if (projAppPoll) { clearInterval(projAppPoll); projAppPoll = null; }
  projAppFocus = null; projAppStarted = new Set(); projAppLastHtml = '';
  const states = info.states || [];
  const when = ts => ts ? new Date(ts * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
  const opt = (s, i) => `<option value="${esc(s.key)}">${i === 0 ? '★ latest — ' : ''}${esc(info.mode === 'git' ? '#' + s.key + ' ' : s.key + ' ')}· ${esc(s.label || '')} · ${esc(when(s.ts))}</option>`;
  showModal(`
    <h2>▶ Test project — ${esc(name)}</h2>
    <div class="view-intro" style="margin-bottom:8px">Runs the <b>complete assembled project</b> (every stage's changes together), not one task's output. ${info.mode === 'git' ? 'Its history is the task branch — every commit is a testable state.' : 'Its history is the completed stages — each checkpoint is a testable state.'}</div>
    ${states.length ? `
    <div class="form-group"><label class="form-label">Project state to run</label>
      <div style="display:flex;gap:8px;align-items:center">
        <select class="form-select" id="pa-ver" style="flex:1">${states.map(opt).join('')}</select>
        <button class="btn-primary" onclick="projAppStart('${esc(wfId)}')">▶ Start</button>
      </div>
      <div class="form-hint">Start an older state <b>while the latest runs</b> — each state gets its own port, so old and new open side by side to spot what changed or broke. File-by-file diffs live in 🔍 Review results.</div>
    </div>` : `<div class="empty" style="margin-bottom:8px">${esc(info.note || 'No project history yet — finish a stage first.')}</div>`}
    <div class="form-group"><label class="form-label">Running states</label>
      <div id="pa-running"><span class="muted" style="font-size:11.5px">none — start one above</span></div></div>
    <div class="form-group"><label class="form-label">Live log <span class="muted" id="pa-logsrc"></span></label>
      <pre id="pa-log" style="max-height:200px;overflow-y:auto;font-size:11px;background:rgba(0,0,0,.35);border-radius:8px;padding:8px 10px;white-space:pre-wrap">…</pre></div>
    <div class="form-hint">Every state runs from a disposable copy on its own local port and stops by itself after 30 minutes. Your live project files and the agents' branch are never touched — testing an old state cannot damage anything.</div>
    <div class="modal-actions" style="justify-content:space-between">
      <button class="btn-sm danger" onclick="projAppStop('${esc(wfId)}','')">⏹ Stop all</button>
      <button class="btn-primary" onclick="closeProjApp()">Close (apps keep running)</button>
    </div>`);
  const tick = async () => {
    if (!$('#pa-running')) { clearInterval(projAppPoll); projAppPoll = null; return; }
    try {
      const st = await api('GET', `/api/workflows/${wfId}/app`);
      const run = st.running || [];
      const rows = run.map(a => `
        <div class="agentic-row slim" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <span style="font-family:var(--font-mono);font-size:11px">${esc(a.version)}</span>
          <span class="chip ${a.ready ? 'c-green' : 'c-orange'}">${a.ready ? '✅ running' : (a.state === 'installing' ? '📦 installing…' : '⏳ starting…')}</span>
          ${a.backend_port ? `<span class="chip ${a.backend_ready ? 'c-green' : 'c-orange'}" title="API backend on 127.0.0.1:${a.backend_port}">${a.backend_ready ? '⚙ api ✅' : '⚙ api ⏳'}</span>` : ''}
          <span style="flex:1;font-size:11px;color:var(--text-faint)">${esc(a.label || '')}</span>
          ${a.ready ? `<a class="btn-sm" href="${esc(a.url)}" target="_blank" style="text-decoration:none;border-color:var(--accent-2)">↗ Open</a>` : ''}
          <button class="btn-sm" onclick="projAppFocus='${esc(a.version)}'">📜 Log</button>
          <button class="btn-sm danger" onclick="projAppStop('${esc(wfId)}','${esc(a.version)}')">⏹</button>
        </div>`).join('') || '<span class="muted" style="font-size:11.5px">none — start one above</span>';
      if (rows !== projAppLastHtml && $('#pa-running')) { $('#pa-running').innerHTML = rows; projAppLastHtml = rows; }
      run.forEach(a => {
        if (a.ready && projAppStarted.has(a.version)) { projAppStarted.delete(a.version); window.open(a.url, '_blank'); }
      });
      const focus = run.find(a => a.version === projAppFocus) || run[0];
      if (focus) {
        const lg = await api('GET', `/api/workflows/${wfId}/app/log?version=${encodeURIComponent(focus.version)}`);
        const el = $('#pa-log');
        if (el && lg.log !== el.textContent) { el.textContent = lg.log || '…'; el.scrollTop = el.scrollHeight; }
        if ($('#pa-logsrc')) $('#pa-logsrc').textContent = '— ' + focus.version;
      }
    } catch { /* transient */ }
  };
  tick();
  projAppPoll = setInterval(tick, 2500);
}

async function projAppStart(wfId) {
  const ver = $('#pa-ver') ? $('#pa-ver').value : '';
  toast('Preparing that project state — assembling a disposable copy…', 'ok');
  try {
    const r = await api('POST', `/api/workflows/${wfId}/app/start`, { version: ver });
    projAppFocus = r.version || ver;
    projAppStarted.add(projAppFocus);
    projAppLastHtml = '';
    toast(`State ${r.version || ver} starting — it opens in a new tab when it answers`, 'ok');
  } catch (e) { toast('Could not start: ' + e.message, 'err'); }
}

async function projAppStop(wfId, version) {
  try {
    await api('POST', `/api/workflows/${wfId}/app/stop`, { version: version || '' });
    projAppLastHtml = '';
    toast(version ? `Stopped ${version}` : 'All project preview states stopped', 'ok');
  } catch (e) { toast('Stop failed: ' + e.message, 'err'); }
}

function closeProjApp() {
  if (projAppPoll) { clearInterval(projAppPoll); projAppPoll = null; }
  closeModal();
}

// ═══════════════════ LOOPING (v3.2 — automatic improve-and-recheck rounds) ═══════════════════
// Plain-language core: a loop watches this work's quality CHECKPOINTS (the
// final inspection of a project, or the frontier judge's grade). CLOSED loop:
// failures are automatically sent back to be fixed and re-checked, a limited
// number of rounds, THEN you are asked. OPEN loop: every checkpoint stops and
// waits for you — nothing re-runs without your click.

const LOOP_INTRO_SHORT =
  'If a quality check fails (inspection or judge), the system can automatically send the work ' +
  'back to be fixed and re-checked a few rounds before involving you — like a good team that ' +
  'checks its own work. You choose whether that happens automatically (closed) or only on your click (open).';

function loopPrefCardsHTML(prefix, current) {
  const card = (val, icon, title, body, checked) => `
    <label style="flex:1;display:block;padding:10px 12px;border:1px solid ${checked ? 'var(--accent)' : 'rgba(255,255,255,.1)'};border-radius:10px;cursor:pointer">
      <input type="radio" name="${prefix}-loop-pref" value="${val}" ${checked ? 'checked' : ''}> <strong>${icon} ${title}</strong>
      <div style="font-size:11.5px;color:var(--text-dim);margin-top:4px">${body}</div>
    </label>`;
  return `<div style="display:flex;gap:8px">
    ${card('quality', '🏆', 'Maximum quality',
    'More checking rounds, and the frontier judge runs automatically on important work. Slower and uses more tokens — the result gets several chances to be improved before you see it.',
    (current || 'quality') === 'quality')}
    ${card('speed', '⚡', 'Speed / token efficiency',
    'At most one automatic fix round, no automatic judging. Faster and cheaper — small flaws may reach you that quality mode would have caught.',
    current === 'speed')}
  </div>`;
}

function selectedLoopPref(prefix) {
  const el = document.querySelector(`input[name="${prefix}-loop-pref"]:checked`);
  return el ? el.value : 'quality';
}

// Q7a — Autopilot presets: two orthogonal axes as plain-language radio cards.
// Presets SET the raw knobs; the "Advanced" expander below exposes them and any
// manual change flips the label to "customized (based on <preset>)". The
// derived quality/speed preference shows read-only under Advanced (rule 1).
const AUTOPILOT_DEFAULTS = { involvement: 'assisted', spend: 'optimal' };
function autopilotCardsHTML(prefix, inv, spend) {
  inv = inv || AUTOPILOT_DEFAULTS.involvement;
  spend = spend || AUTOPILOT_DEFAULTS.spend;
  const card = (name, val, icon, title, body, checked) => `
    <label class="ap-card" style="flex:1;display:block;padding:9px 11px;border:1px solid ${checked ? 'var(--accent)' : 'rgba(255,255,255,.1)'};border-radius:10px;cursor:pointer">
      <input type="radio" name="${prefix}-${name}" value="${val}" ${checked ? 'checked' : ''}> <strong>${icon} ${title}</strong>
      <div style="font-size:11px;color:var(--text-dim);margin-top:3px">${body}</div>
    </label>`;
  return `
    <div class="ap-axis" data-help="autopilot-involvement">
      <div style="font-size:11.5px;font-weight:600;margin-bottom:4px">How much should I ask you? <span class="qmark" data-help="autopilot-involvement" title="Click for a plain-language explainer">?</span></div>
      <div style="display:flex;gap:7px">
        ${card('inv', 'full_auto', '🚀', 'Full Auto', 'I run the loops and only ask you at the big moments (plan, final, escalations, anything irreversible).', inv === 'full_auto')}
        ${card('inv', 'assisted', '🤝', 'Assisted', 'I close the fix-rounds but pause the inspector checkpoints so you can look before each re-run.', inv === 'assisted')}
        ${card('inv', 'manual', '🎛', 'Manual', 'I only flag problems and recommend — you press the button on every step.', inv === 'manual')}
      </div>
    </div>
    <div class="ap-axis" data-help="autopilot-spend" style="margin-top:8px">
      <div style="font-size:11.5px;font-weight:600;margin-bottom:4px">How much should this cost? <span class="qmark" data-help="autopilot-spend" title="Click for a plain-language explainer">?</span></div>
      <div style="display:flex;gap:7px">
        ${card('spend', 'eco', '🌱', 'Eco', 'Cheapest that still works — fewest rounds, no fan-out, lean pipeline. ~½ the fuel.', spend === 'eco')}
        ${card('spend', 'optimal', '⚖', 'Balanced', 'Best result per fuel — checking scaled to the stakes. The sensible default.', spend === 'optimal')}
        ${card('spend', 'smart', '🧠', 'Smart', 'Spare no fuel — maximum checking, fan-out, the works. ~2× the fuel.', spend === 'smart')}
      </div>
    </div>
    <details style="margin-top:8px">
      <summary style="cursor:pointer;font-size:11.5px;color:var(--text-dim)">Advanced — raw knobs (for professionals)</summary>
      <div style="margin-top:6px">
        <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px">Quality/speed is DERIVED from the spending profile (Eco → speed, else quality) and shown here read-only — changing a raw knob marks the loop "customized (based on your preset)".</div>
        ${loopPrefCardsHTML(prefix)}
      </div>
    </details>`;
}

function selectedAutopilot(prefix) {
  const inv = document.querySelector(`input[name="${prefix}-inv"]:checked`);
  const sp = document.querySelector(`input[name="${prefix}-spend"]:checked`);
  return { autopilot: inv ? inv.value : AUTOPILOT_DEFAULTS.involvement,
           spend_profile: sp ? sp.value : AUTOPILOT_DEFAULTS.spend };
}

async function designLoop(kind, opts) {
  const r = await api('POST', '/api/loop/design', Object.assign({ kind }, opts));
  return r.loop_config;
}

function parseLoopCfg(raw) {
  if (!raw) return null;
  if (typeof raw === 'object') return raw;
  try { return JSON.parse(raw); } catch { return null; }
}

function loopBadgeHTML(cfg) {
  if (!cfg) return '<span class="chip">🔁 no loop</span>';
  if (!cfg.enabled) return '<span class="chip">🔁 looping off</span>';
  return `<span class="chip ${cfg.mode === 'closed' ? 'c-cyan' : 'c-orange'}">🔁 ${cfg.mode === 'closed' ? 'closed loop' : 'open loop'}</span>
    <span class="chip">${cfg.preference === 'speed' ? '⚡ speed' : '🏆 quality'}</span>`;
}

let loopEdit = null; // {kind, id, title, cfg}

async function loopViewerModal(kind, id, title) {
  let raw = null;
  try {
    if (kind === 'task') {
      state.tasks = await api('GET', '/api/tasks');
      raw = ((state.tasks || []).find(t => t.id === id) || {}).loop_config;
    } else {
      raw = (await api('GET', `/api/workflows/${id}`)).loop_config;
    }
  } catch (e) { toast('Load failed: ' + e.message, 'err'); return; }
  let cfg = parseLoopCfg(raw);
  if (!cfg) {
    cfg = await designLoop(kind, { id, preference: 'quality', mode: 'closed' });
    cfg.enabled = false; // designed as a proposal — enabling stays the user's call
  }
  loopEdit = { kind, id, title, cfg };
  renderLoopModal();
}

function renderLoopModal() {
  const { kind, id, title, cfg } = loopEdit;
  const closed = cfg.mode === 'closed';
  const flowBox = (icon, label, sub) => `
    <div style="flex:1;min-width:110px;text-align:center;padding:10px 8px;border:1px solid rgba(255,255,255,.12);border-radius:10px;background:rgba(255,255,255,.03)">
      <div style="font-size:20px">${icon}</div><strong style="font-size:12px">${label}</strong>
      <div style="font-size:10.5px;color:var(--text-faint)">${sub}</div></div>`;
  const arrow = t => `<div style="align-self:center;font-size:14px;color:var(--text-faint);padding:0 2px" title="${t}">➜</div>`;
  const maxR = Math.max(1, ...((cfg.triggers || []).map(t => t.max_rounds || 1)));
  const flow = closed ? `
    <div style="display:flex;gap:4px;align-items:stretch;flex-wrap:wrap">
      ${flowBox('🛠️', 'Agent works', 'produces the result')}
      ${arrow('the result goes to the checkpoint')}
      ${flowBox('🔍', 'Checkpoint', 'inspection / judge grades it')}
      ${arrow('if it fails, findings go back automatically')}
      ${flowBox('🔁', 'Auto-fix round', `failures loop back, max ${maxR}×`)}
      ${arrow('when it passes — or rounds are used up')}
      ${flowBox('👤', 'You', 'review & approve')}
    </div>
    <div class="form-hint" style="margin-top:4px">Failures travel backwards automatically — that is what "closed" means: the circle closes without you. You only see work that passed, or that failed ${maxR}× so a human needs to look.</div>`
    : `
    <div style="display:flex;gap:4px;align-items:stretch;flex-wrap:wrap">
      ${flowBox('🛠️', 'Agent works', 'produces the result')}
      ${arrow('the result goes to the checkpoint')}
      ${flowBox('🔍', 'Checkpoint', 'inspection / judge grades it')}
      ${arrow('PASS or FAIL — either way it stops here')}
      ${flowBox('👤', 'You decide', 'press Retry to loop, or accept')}
    </div>
    <div class="form-hint" style="margin-top:4px">The circle stays "open": nothing re-runs by itself. Every finding waits for your decision — full control, more clicks.</div>`;
  const trigRows = (cfg.triggers || []).map((t, i) => `
    <div class="agentic-row">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <input type="checkbox" id="lp-trig-${i}" ${t.enabled ? 'checked' : ''}>
        <strong>${esc(t.label)}</strong>
        <span class="chip" title="${t.used_tasks ? 'rounds are counted per member task' : 'rounds used'}">round ${t.used || Math.max(0, ...Object.values(t.used_tasks || {}).map(Number)) || 0}/${t.max_rounds}${t.used_tasks ? ' per task' : ''}</span>
        <span style="font-size:11px;color:var(--text-faint)">max rounds:</span>
        <input class="form-input" id="lp-rounds-${i}" type="number" min="1" max="3" value="${t.max_rounds}" style="width:56px;padding:2px 6px">
      </div>
      <div style="font-size:11.5px;color:var(--text-dim)">${esc(t.explain)}</div>
    </div>`).join('') ||
    '<div class="empty" style="padding:12px">This item has no automatic checkpoint to loop on (no final inspection stage and no domain rubric for the judge). Put it in a project with an acceptance-verification stage, or give it a domain that has a rubric, then Regenerate.</div>';
  showModal(`
    <h2 style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">🔁 Loop — ${esc(title || id)} ${loopBadgeHTML(cfg)}</h2>
    <div class="view-intro" style="margin-bottom:10px">${LOOP_INTRO_SHORT}</div>
    <div class="form-group"><label class="form-label">How work flows ${closed ? '(closed loop — automatic)' : '(open loop — you drive)'}</label>${flow}</div>
    <div class="form-row">
      <div class="form-group"><label class="form-label">Loop type</label>
        <select class="form-select" id="lp-mode">
          <option value="closed" ${closed ? 'selected' : ''}>Closed — fix rounds run automatically, then I'm asked</option>
          <option value="open" ${!closed ? 'selected' : ''}>Open — every checkpoint waits for my click</option>
        </select></div>
      <div class="form-group"><label class="form-label">Optimize for</label>
        <select class="form-select" id="lp-pref">
          <option value="quality" ${cfg.preference !== 'speed' ? 'selected' : ''}>🏆 Maximum quality (slower, more tokens)</option>
          <option value="speed" ${cfg.preference === 'speed' ? 'selected' : ''}>⚡ Speed / token efficiency (lower quality)</option>
        </select></div>
    </div>
    <div class="form-group"><label class="form-label">Checkpoints this loop watches</label>
      <div style="display:flex;flex-direction:column;gap:6px">${trigRows}</div></div>
    <div class="form-group"><label class="form-label">Why the loop was designed this way</label>
      <div style="background:rgba(124,92,255,.08);border:1px solid rgba(124,92,255,.25);border-radius:8px;padding:10px 12px;font-size:12.5px">
        ${(cfg.reasoning || []).map(r => `<div style="margin-bottom:5px">· ${esc(r)}</div>`).join('') || '—'}
      </div></div>
    <div class="form-hint">Changing the type or optimization and pressing <strong>Regenerate</strong> designs a fresh loop for those settings (round counters reset). <strong>Save</strong> keeps your manual edits as-is.</div>
    <div class="modal-actions" style="justify-content:space-between">
      <button class="btn-sm ${cfg.enabled ? 'danger' : ''}" id="lp-toggle">${cfg.enabled ? '⏻ Disable looping entirely' : '⏻ Enable looping'}</button>
      <div style="display:flex;gap:10px">
        <button class="btn-ghost" id="lp-regen">🔄 Regenerate loop</button>
        <button class="btn-ghost" onclick="closeModal()">Cancel</button>
        <button class="btn-primary" id="lp-save">Save</button>
      </div>
    </div>`);
  const collect = () => {
    cfg.mode = ($('#lp-mode') || {}).value || cfg.mode;
    cfg.preference = ($('#lp-pref') || {}).value || cfg.preference;
    (cfg.triggers || []).forEach((t, i) => {
      const en = $(`#lp-trig-${i}`), mr = $(`#lp-rounds-${i}`);
      if (en) t.enabled = en.checked;
      if (mr) t.max_rounds = Math.max(1, Math.min(3, parseInt(mr.value) || t.max_rounds));
    });
    return cfg;
  };
  const saveCfg = async c => {
    const base = kind === 'task' ? `/api/tasks/${id}` : `/api/workflows/${id}`;
    await api('PATCH', base, { loop_config: c });
  };
  $('#lp-regen').onclick = async () => {
    const c = collect();
    try {
      const fresh = await designLoop(kind, { id, preference: c.preference, mode: c.mode });
      fresh.enabled = c.enabled;
      loopEdit.cfg = fresh;
      renderLoopModal();
      toast('Loop regenerated for the selected settings', 'ok');
    } catch (e) { toast('Regenerate failed: ' + e.message, 'err'); }
  };
  $('#lp-toggle').onclick = async () => {
    const c = collect();
    c.enabled = !c.enabled;
    try { await saveCfg(c); loopEdit.cfg = c; renderLoopModal(); toast(c.enabled ? 'Looping enabled' : 'Looping disabled', 'ok'); }
    catch (e) { toast('Save failed: ' + e.message, 'err'); }
  };
  $('#lp-save').onclick = async () => {
    const c = collect();
    try { await saveCfg(c); closeModal(); toast('Loop saved', 'ok'); }
    catch (e) { toast('Save failed: ' + e.message, 'err'); }
  };
}

const NEXUS_DOMAINS = ['general', 'marketing', 'content-creation', 'brand', 'ecommerce',
  'consulting-bizdev', 'saas-business', 'software-engineering', 'research-learning', 'music-dj'];
let specialistNamesCache = null;

async function loadTaskExtras(t) {
  // specialists into the picker (cached across modal opens)
  try {
    if (!specialistNamesCache) {
      const r = await api('GET', '/api/specialists/names');
      specialistNamesCache = (r.specialists || []).map(s => s.name);
    }
    const sel = $('#td-specialist');
    if (sel) {
      const cur = t.specialist || '';
      sel.innerHTML = `<option value="">— Agent decides —</option>` +
        specialistNamesCache.map(n => `<option value="${esc(n)}" ${n === cur ? 'selected' : ''}>${esc(n)}</option>`).join('');
    }
  } catch { /* specialist list is optional */ }
  // workspace files + transcript (only when the task has been dispatched)
  const box = $('#td-extras');
  if (!box || !t.session_id) return;
  let html = '';
  try {
    const [fr, ap] = await Promise.all([
      api('GET', `/api/tasks/${t.id}/files`),
      api('GET', `/api/tasks/${t.id}/app`).catch(() => ({})),
    ]);
    if (ap && ap.detected) {
      const run = ap.running;
      html += `<div class="form-group"><label class="form-label">▶ Runnable program detected</label>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <span class="chip c-cyan">${esc(ap.detected.label)}</span>
          ${run && run.ready ? `<span class="chip c-green">running</span><a class="btn-sm" href="${esc(run.url)}" target="_blank" style="text-decoration:none">↗ Open</a>
            <button class="btn-sm danger" onclick="stopAppUI('${esc(t.id)}')">⏹ Stop</button>`
      : `<button class="btn-sm" style="border-color:var(--accent-2)" onclick="testAppUI('${esc(t.id)}','${esc(t.title).slice(0, 50)}')">▶ Test app</button>`}
          <button class="btn-sm" title="Lift this app out of the task workspace into a real client repository (git + backup + delivery workflow)" onclick="promoteTaskUI('${esc(t.id)}','${esc(t.title).slice(0, 50)}')">📦 Promote to repository</button>
        </div></div>`;
    }
    if ((fr.files || []).length) {
      html += `<div class="form-group"><label class="form-label" style="display:flex;align-items:center;gap:10px">Deliverable files (workspace)
        <button class="btn-sm" style="border-color:var(--accent)" title="PR-style comparison: what changed since the previous version — per file, for code AND documents" onclick="reviewTaskUI('${esc(t.id)}','${esc(t.title).slice(0, 50)}')">🔍 Review changes</button></label>
        <div style="display:flex;flex-direction:column;gap:4px">` +
        fr.files.map(f => `<a href="/api/tasks/${esc(t.id)}/files/${encPath(f.name)}" target="_blank"
          style="font-family:var(--font-mono);font-size:12px;color:var(--accent-2)">📄 ${esc(f.name)} <span class="muted">(${(f.size / 1024).toFixed(1)} KB)</span></a>`).join('') +
        `</div></div>`;
    }
  } catch { /* workspace may not exist yet */ }
  try {
    const tr = await api('GET', `/api/tasks/${t.id}/transcript`);
    if ((tr.messages || []).length) {
      html += `<div class="form-group"><label class="form-label">Session transcript (the real log)</label>
        <details><summary style="cursor:pointer;font-size:12px;color:var(--text-dim)">${tr.messages.length} messages — click to expand</summary>
        <div style="max-height:300px;overflow-y:auto;margin-top:8px;display:flex;flex-direction:column;gap:6px">` +
        tr.messages.map(m => `<div style="font-size:12px;border-left:2px solid ${m.role === 'assistant' ? 'var(--accent)' : 'var(--cyan)'};padding:4px 8px">
          <span class="chip ${m.role === 'assistant' ? 'c-accent' : 'c-cyan'}">${esc(m.role || '?')}</span>
          <div style="white-space:pre-wrap;margin-top:4px">${esc((m.content || '').slice(0, 2000))}${(m.content || '').length > 2000 ? '…' : ''}</div>
        </div>`).join('') + `</div></details></div>`;
    }
  } catch { /* transcript proxy may be down */ }
  if (box.isConnected) box.innerHTML = html;
}

function judgeSectionHTML(t) {
  if (!t.result_summary && !t.judge_verdict) return '';
  const v = t.judge_verdict;
  if (v === 'running') {
    setTimeout(() => pollJudge(t.id), 4000);
    return `<div class="form-group"><label class="form-label">Frontier judge</label>
      <div class="chip c-blue">⏳ judging… (takes a few minutes)</div></div>`;
  }
  if (v && v !== 'error') {
    const cls = { SHIP: 'c-green', REVISE: 'c-orange', REWRITE: 'c-red' }[v] || '';
    const learn = (t.judge_output || '').match(/Learning note:?\s*(.+)/i);
    return `<div class="form-group"><label class="form-label">Frontier judge verdict</label>
      <div style="display:flex;flex-direction:column;gap:6px">
        <div><span class="chip ${cls}" style="font-size:13px;font-weight:700">${esc(v)}</span></div>
        ${learn ? `<div style="font-size:12.5px;color:var(--text-dim)">📖 ${esc(learn[1])}</div>` : ''}
        <details><summary style="cursor:pointer;font-size:12px;color:var(--text-dim)">full judge report</summary>
          <pre style="max-height:260px;overflow-y:auto;white-space:pre-wrap;font-size:11.5px;margin-top:6px">${esc(t.judge_output || '')}</pre></details>
      </div></div>`;
  }
  return `<div class="form-group"><label class="form-label">Frontier judge</label>
    <div style="display:flex;gap:8px;align-items:center">
      <button class="btn-ghost" onclick="runJudgeUI('${esc(t.id)}')">⚖ Run frontier judge</button>
      ${v === 'error' ? `<span class="chip c-red">last run failed — see activity</span>` : ''}
      <span class="muted" style="font-size:11.5px">frontier second opinion vs the ${esc(t.domain || 'domain')} rubric</span>
    </div></div>`;
}

async function runJudgeUI(id) {
  try {
    await api('POST', `/api/tasks/${id}/judge`);
    toast('Frontier judge started — verdict lands in a few minutes', 'ok');
    const t = (state.tasks || []).find(x => x.id === id);
    if (t) { t.judge_verdict = 'running'; }
    const jb = $('#td-judge');
    if (jb && t) jb.innerHTML = judgeSectionHTML(t);
  } catch (e) { toast('Judge failed to start: ' + e.message, 'err'); }
}

async function pollJudge(id) {
  const jb = $('#td-judge');
  if (!jb || !jb.isConnected) return; // modal closed — stop polling
  try {
    const r = await api('GET', `/api/tasks/${id}/judge`);
    if (r.running) { setTimeout(() => pollJudge(id), 5000); return; }
    state.tasks = await api('GET', '/api/tasks');
    const t = (state.tasks || []).find(x => x.id === id);
    if (t && jb.isConnected) {
      jb.innerHTML = judgeSectionHTML(t);
      toast(`Judge verdict: ${r.verdict}`, r.verdict === 'SHIP' ? 'ok' : 'err');
    }
  } catch { setTimeout(() => pollJudge(id), 8000); }
}

// ── Super Result: grounded critic section (follows the judge pattern) ──
function criticSectionHTML(t) {
  if (!t.result_summary && !t.critic_verdict && !t.super_result) return '';
  const v = t.critic_verdict;
  if (v === 'running') {
    setTimeout(() => pollCritic(t.id), 4000);
    return `<div class="form-group"><label class="form-label">🤖 Grounded critic (Super Result)</label>
      <div class="chip c-blue">⏳ critiquing in a sandbox… (takes minutes — it re-runs the evidence)</div></div>`;
  }
  if (v && v !== 'error') {
    const cls = { SHIP: 'c-green', REVISE: 'c-orange', REWRITE: 'c-red' }[v] || '';
    let p = {};
    try { p = JSON.parse(t.critic_json || '{}') || {}; } catch { /* raw */ }
    const k = (p.findings || []).length;
    return `<div class="form-group"><label class="form-label">🤖 Grounded critic (Super Result) — round ${t.critic_round || 0}</label>
      <div style="display:flex;flex-direction:column;gap:6px">
        <div><span class="chip ${cls}" style="font-size:13px;font-weight:700">${esc(v)}</span>
          ${k ? `<span class="chip c-accent">${k} finding${k === 1 ? '' : 's'} → review comments</span>` : ''}</div>
        ${p.summary ? `<div style="font-size:12.5px;color:var(--text-dim)">${esc(p.summary)}</div>` : ''}
        ${p.learning_note ? `<div style="font-size:12px;color:var(--text-dim)">📖 ${esc(p.learning_note)}</div>` : ''}
        ${k ? `<details><summary style="cursor:pointer;font-size:12px;color:var(--text-dim)">findings</summary>
          <div style="max-height:220px;overflow-y:auto;display:flex;flex-direction:column;gap:6px;margin-top:6px">
          ${p.findings.map(f => `<div style="font-size:11.5px;border-left:2px solid var(--accent);padding-left:8px">
            <strong>[${esc((f.severity || '').toUpperCase())}]</strong> ${esc(f.file_path || '')}${f.line_no ? ':' + f.line_no : ''} — ${esc(f.problem || '')}
            ${f.evidence ? `<div style="color:var(--text-faint)">evidence: ${esc(f.evidence)}</div>` : ''}
            ${f.suggested_fix ? `<div style="color:var(--text-dim)">fix: ${esc(f.suggested_fix)}</div>` : ''}</div>`).join('')}
          </div></details>` : ''}
        <div><button class="btn-ghost" onclick="runCriticUI('${esc(t.id)}')">🤖 Run critic again</button></div>
      </div></div>`;
  }
  return `<div class="form-group"><label class="form-label">🤖 Grounded critic (Super Result)</label>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <button class="btn-ghost" onclick="runCriticUI('${esc(t.id)}')">🤖 Run critic</button>
      ${v === 'error' ? `<span class="chip c-red">last run failed — see activity</span>` : ''}
      <span class="muted" style="font-size:11.5px">frontier model re-verifies every claim with tools in a disposable sandbox</span>
    </div></div>`;
}

async function runCriticUI(id) {
  try {
    await api('POST', `/api/tasks/${id}/critic`);
    toast('Grounded critic started — it re-verifies the evidence in a sandbox (minutes)', 'ok');
    const t = (state.tasks || []).find(x => x.id === id);
    if (t) { t.critic_verdict = 'running'; }
    const cb = $('#td-critic');
    if (cb && t) cb.innerHTML = criticSectionHTML(t);
  } catch (e) { toast('Critic failed to start: ' + e.message, 'err'); }
}

async function pollCritic(id) {
  const cb = $('#td-critic');
  if (!cb || !cb.isConnected) return; // modal closed — stop polling
  try {
    const r = await api('GET', `/api/tasks/${id}/critic`);
    if (r.running) { setTimeout(() => pollCritic(id), 5000); return; }
    state.tasks = await api('GET', '/api/tasks');
    const t = (state.tasks || []).find(x => x.id === id);
    if (t && cb.isConnected) {
      cb.innerHTML = criticSectionHTML(t);
      toast(`Critic verdict: ${r.verdict}${r.open_critic_comments ? ` — ${r.open_critic_comments} comment(s) filed` : ''}`,
        r.verdict === 'SHIP' ? 'ok' : 'err');
    }
  } catch { setTimeout(() => pollCritic(id), 8000); }
}

async function dispatchTaskUI(id) {
  const t = (state.tasks || []).find(x => x.id === id);
  const lanes = (state.agents || []).filter(a => a.pid && !['retired', 'stopped'].includes(a.status));
  if (!lanes.length) { toast('No running agent lane — spawn one in the Agents tab first', 'err'); return; }
  const lane = lanes.find(a => a.id === (t && t.assignee_id)) || lanes[0];
  try {
    await api('POST', `/api/tasks/${id}/dispatch`, { agent_id: lane.id });
    toast(`Dispatched to ${lane.name} — a real Hermes session is on it`, 'ok');
    closeModal();
    state.tasks = await api('GET', '/api/tasks');
    render();
  } catch (e) { toast('Dispatch failed: ' + e.message, 'err'); }
}

// Chain agents: open the create form prefilled so the NEXT task reads this
// task's deliverable as its input (agents have file tools — the path is enough).
function followUpTaskUI(id) {
  const t = (state.tasks || []).find(x => x.id === id);
  if (!t) return;
  closeModal();
  // chain properly: same project (if any) + a real dependency, so the framing
  // injects the predecessor deliverable automatically at dispatch time
  taskCreateContext = { workflow_id: t.workflow_id || null, depends_on: [t.id] };
  showTaskModal('todo');
  setTimeout(() => {
    const ttl = $('#m-task-title'); const desc = $('#m-task-desc');
    if (ttl) ttl.value = `Follow-up: ${t.title}`;
    if (desc) desc.value = `[describe what to do with the previous result — its deliverable is provided as INPUT automatically]`;
    if ($('#m-task-domain') && t.domain) $('#m-task-domain').value = t.domain;
    toast('Chained: this task waits for the previous one and reads its deliverable as input', 'ok');
  }, 150);
}

async function retryTaskUI(id) {
  const note = prompt('Feedback for the retry — what must be different? (optional: leave EMPTY to automatically attach the frontier judge’s findings; open review line-comments ride along either way)');
  if (note === null) return; // cancelled — nothing happens
  try {
    await api('POST', `/api/tasks/${id}/retry`, { feedback: note.trim() || null });
    toast('Task is back in Todo — a lane picks it up in seconds and redoes it with the feedback attached. Old version kept as deliverable.vN.md.', 'ok');
    closeModal();
    state.tasks = await api('GET', '/api/tasks');
    await loadAgenticData(); // the superseded approval row disappears
    render();
  } catch (e) { toast('Retry failed: ' + e.message, 'err'); }
}

async function createPrUI(id) {
  if (!confirm('Push this task\'s branch to origin and open a GitHub pull request? (SPEC-BLOCK2 R3 — the branch leaves your machine.)')) return;
  toast('Creating PR — pushing the branch…');
  try {
    const r = await api('POST', `/api/tasks/${id}/pr`);
    toast(r.existing ? 'A PR already existed for this branch — reusing it' : 'PR created', 'ok');
    if (r.url) window.open(r.url, '_blank');
    state.tasks = await api('GET', '/api/tasks');
    openTaskDetail(id);
  } catch (e) { toast('PR failed: ' + e.message, 'err'); }
}

async function logFeedbackUI(id, kind) {
  const note = prompt(kind === 'win'
    ? 'What worked? (1-3 short bullets)'
    : 'What did you expect vs what actually happened?');
  if (note === null || !note.trim()) return;
  const numbers = prompt(kind === 'win'
    ? 'The REAL numbers (required): CTR, sales, opens, attendance…'
    : 'Root cause (be honest — optional):');
  if (kind === 'win' && (numbers === null || !numbers.trim())) {
    toast('A WIN needs the real numbers — that’s the whole point', 'err'); return;
  }
  try {
    const r = await api('POST', `/api/tasks/${id}/feedback`, { kind, note: note.trim(), numbers: (numbers || '').trim() });
    toast(`Logged as ${kind.toUpperCase()} → ${r.file.split('/').pop()}`, 'ok');
  } catch (e) { toast('Logging failed: ' + e.message, 'err'); }
}

async function saveTaskDetail(id) {
  const body = {
    title: $('#td-title').value.trim(),
    description: $('#td-desc').value,
    status: $('#td-status').value,
    priority: parseInt($('#td-priority').value),
    assignee_id: $('#td-assignee').value || null,
    domain: $('#td-domain') ? $('#td-domain').value : null,
    specialist: $('#td-specialist') ? ($('#td-specialist').value || '') : null,
    high_stakes: $('#td-highstakes') ? $('#td-highstakes').checked : null,
    super_result: $('#td-super') ? $('#td-super').checked : null,
    budget_tokens: $('#td-budget') && $('#td-budget').value ? parseInt($('#td-budget').value) : null,
    model: $('#td-model') ? ($('#td-model').value || '') : null,
    depends_on: $('#td-depends')
      ? [...$('#td-depends').selectedOptions].map(o => o.value) : null,
  };
  if (!body.title) { toast('Title is required', 'err'); return; }
  closeModal();
  await api('PATCH', `/api/tasks/${id}`, body);
  state.tasks = await api('GET', '/api/tasks');
  toast('Task updated', 'ok');
  render();
}

async function deleteTaskUI(id) {
  if (!confirm('Delete this task permanently?')) return;
  closeModal();
  await api('DELETE', `/api/tasks/${id}`);
  state.tasks = await api('GET', '/api/tasks');
  toast('Task deleted', 'ok');
  render();
}

// ═══════════════════════════════ AGENTS (incremental) ═══════════════════════════════
function renderAgentsView() {
  const c = $('#content');
  const agents = state.agents || [];

  const running = agents.filter(a => a.status === 'running').length;
  const busy = agents.filter(a => a.status === 'busy').length;
  const idle = agents.filter(a => a.status === 'idle').length;
  const totalTIn = agents.reduce((s, a) => s + (a.tokens_in || 0), 0);
  const totalTOut = agents.reduce((s, a) => s + (a.tokens_out || 0), 0);

  if (!agentsBuilt) {
    c.innerHTML = wrapView(`
      <div style="margin-bottom:12px;padding:10px 14px;border:1px solid var(--border);border-radius:10px;background:rgba(124,92,255,.05);font-size:12px;color:var(--text-dim);line-height:1.5">
        <strong style="color:var(--text)">What you're looking at:</strong> each card is an <strong>agent lane</strong> — a real worker process that picks up kanban cards and executes them as real Hermes AI sessions.
        <strong>running</strong> = alive, waiting for work · <strong>busy</strong> = executing a task right now (watch its live preview) · <strong>retired</strong> = ended for good.
        Tokens shown are real consumption. Lanes heal themselves: if one crashes, the watchdog revives it and it resumes its task. More lanes = more tasks in parallel.
      </div>
      <div class="agent-summary-bar">
        <div class="summary-item"><span class="summary-val" style="color:var(--green)" id="sumRunning">${running}</span><span class="summary-label">Running</span></div>
        <div class="summary-item"><span class="summary-val" style="color:var(--yellow)" id="sumBusy">${busy}</span><span class="summary-label">Busy</span></div>
        <div class="summary-item"><span class="summary-val" style="color:var(--text-dim)" id="sumIdle">${idle}</span><span class="summary-label">Idle</span></div>
        <div class="summary-divider"></div>
        <div class="summary-item"><span class="summary-val" style="color:#b3a1ff" id="sumTok">${fmtTokens(totalTIn + totalTOut)}</span><span class="summary-label">Total Tokens</span></div>
        <div class="summary-item"><span class="summary-val" style="font-size:14px" id="sumIO"><span class="tok-in">↓${fmtTokens(totalTIn)}</span> <span class="tok-out">↑${fmtTokens(totalTOut)}</span></span><span class="summary-label">In / Out</span></div>
        <div class="summary-divider"></div>
        <div class="summary-item" style="justify-content:center"><span class="muted" style="font-size:11px">Click a card for memory · messages · cost</span></div>
      </div>
      <div class="agent-grid" id="agentGrid">
        ${agents.map(a => agentCardHTML(a)).join('') || '<div class="empty"><span class="e-ico">◇</span>No agents. Spawn one to get started.</div>'}
      </div>
    `);
    agentsBuilt = true;
    buildAgentCharts(agents);
  } else {
    updateAgentCardsInPlace(agents);
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('sumRunning', running); set('sumBusy', busy); set('sumIdle', idle);
    set('sumTok', fmtTokens(totalTIn + totalTOut));
    const io = document.getElementById('sumIO');
    if (io) io.innerHTML = `<span class="tok-in">↓${fmtTokens(totalTIn)}</span> <span class="tok-out">↑${fmtTokens(totalTOut)}</span>`;
  }
}

function agentCardHTML(a) {
  const prog = (state.programs || []).find(p => p.id === a.program_id);
  const uptime = a.started_at ? fmtUptime(a.uptime_s || (Date.now() / 1000 - a.started_at)) : '--';
  const tIn = a.tokens_in || 0;
  const tOut = a.tokens_out || 0;
  const tTotal = tIn + tOut;
  const curTask = a.current_task || '— Idle —';

  return `
    <div class="agent-card st-${esc(a.status)}" id="card-${esc(a.id)}" onclick="openAgentDrawer('${esc(a.id)}')">
      <div class="agent-header">
        <div class="agent-name">
          <span class="status-dot ${a.status === 'running' ? 'online' : a.status === 'busy' ? 'busy' : ''}" style="background:${statusColor(a.status)}"></span>
          ${esc(a.name)}
        </div>
        <span class="agent-status-badge status-${esc(a.status)}">${esc(a.status)}</span>
      </div>
      <div class="agent-role">${esc(a.role)} · model: per task${prog ? ' · ' + esc(prog.name) : ''}</div>

      <div class="agent-current-task" id="task-${esc(a.id)}">
        <span class="task-icon">▸</span>
        <span class="task-text">${esc(curTask)}</span>
      </div>

      <div class="agent-stats">
        <div class="agent-stat"><div class="agent-stat-label">Completed</div><div class="agent-stat-val" style="color:var(--green)" id="completed-${esc(a.id)}">${a.tasks_completed}</div></div>
        <div class="agent-stat"><div class="agent-stat-label">Failed</div><div class="agent-stat-val" style="color:var(--red)" id="failed-${esc(a.id)}">${a.tasks_failed}</div></div>
        <div class="agent-stat"><div class="agent-stat-label">CPU</div><div class="agent-stat-val" style="color:#b3a1ff" id="cpu-${esc(a.id)}">${(a.cpu || 0).toFixed(1)}%</div></div>
        <div class="agent-stat"><div class="agent-stat-label">Memory</div><div class="agent-stat-val" style="color:var(--accent-2)" id="mem-${esc(a.id)}">${(a.mem_mb || 0).toFixed(0)}MB</div></div>
      </div>

      <div class="agent-token-section">
        <div class="token-header">
          <span class="token-label">Token Usage</span>
          <span class="token-total" id="tok-total-${esc(a.id)}">${fmtTokens(tTotal)}</span>
        </div>
        <div class="token-bar-container">
          <div class="token-bar in" id="tok-bar-in-${esc(a.id)}" style="width:${Math.round((tIn / Math.max(1, tTotal)) * 100)}%"></div>
          <div class="token-bar out" id="tok-bar-out-${esc(a.id)}" style="width:${Math.round((tOut / Math.max(1, tTotal)) * 100)}%"></div>
        </div>
        <div class="token-breakdown">
          <span class="tok-in">↓ In: ${fmtTokens(tIn)}</span>
          <span class="tok-out">↑ Out: ${fmtTokens(tOut)}</span>
        </div>
      </div>

      <div class="agent-chart-wrap"><canvas id="chart-${esc(a.id)}"></canvas></div>

      <div class="agent-meta-grid" id="meta-${esc(a.id)}">
        <div><span class="meta-label">Uptime</span><span class="meta-val">${uptime}</span></div>
        <div><span class="meta-label">Heartbeat</span><span class="meta-val">${fmtAgo(a.last_heartbeat)}</span></div>
        <div><span class="meta-label">PID</span><span class="meta-val">${a.pid || 'N/A'}</span></div>
        <div><span class="meta-label">Started</span><span class="meta-val">${fmtAgo(a.started_at)}</span></div>
      </div>

      <div class="agent-actions" onclick="event.stopPropagation()">
        <button class="btn-sm" onclick="openAgentDrawer('${esc(a.id)}')">☰ Details</button>
        <button class="btn-sm" onclick="restartAgent('${esc(a.id)}')">↻ Restart</button>
        <button class="btn-sm danger" onclick="deleteAgent('${esc(a.id)}')">✕ Stop</button>
      </div>
    </div>
  `;
}

function updateAgentCardsInPlace(agents) {
  for (const a of agents) {
    const card = document.getElementById(`card-${a.id}`);
    if (!card) { agentsBuilt = false; renderAgentsView(); return; }

    card.className = `agent-card st-${a.status}`;
    const badge = card.querySelector('.agent-status-badge');
    if (badge) { badge.className = `agent-status-badge status-${a.status}`; badge.textContent = a.status; }
    const dot = card.querySelector('.agent-name .status-dot');
    if (dot) {
      dot.style.background = statusColor(a.status);
      dot.className = `status-dot ${a.status === 'running' ? 'online' : a.status === 'busy' ? 'busy' : ''}`;
    }
    const taskEl = document.getElementById(`task-${a.id}`);
    if (taskEl) taskEl.querySelector('.task-text').textContent = a.current_task || '— Idle —';

    const completed = document.getElementById(`completed-${a.id}`);
    if (completed) completed.textContent = a.tasks_completed;
    const failed = document.getElementById(`failed-${a.id}`);
    if (failed) failed.textContent = a.tasks_failed;
    const cpu = document.getElementById(`cpu-${a.id}`);
    if (cpu) cpu.textContent = `${(a.cpu || 0).toFixed(1)}%`;
    const mem = document.getElementById(`mem-${a.id}`);
    if (mem) mem.textContent = `${(a.mem_mb || 0).toFixed(0)}MB`;

    const tIn = a.tokens_in || 0, tOut = a.tokens_out || 0, tTotal = tIn + tOut;
    const tokTotal = document.getElementById(`tok-total-${a.id}`);
    if (tokTotal) tokTotal.textContent = fmtTokens(tTotal);
    const tokBreakdown = card.querySelector('.token-breakdown');
    if (tokBreakdown) {
      tokBreakdown.querySelector('.tok-in').textContent = `↓ In: ${fmtTokens(tIn)}`;
      tokBreakdown.querySelector('.tok-out').textContent = `↑ Out: ${fmtTokens(tOut)}`;
    }
    const barIn = document.getElementById(`tok-bar-in-${a.id}`);
    const barOut = document.getElementById(`tok-bar-out-${a.id}`);
    if (barIn && barOut) {
      barIn.style.width = `${Math.round((tIn / Math.max(1, tTotal)) * 100)}%`;
      barOut.style.width = `${Math.round((tOut / Math.max(1, tTotal)) * 100)}%`;
    }
    const meta = document.getElementById(`meta-${a.id}`);
    if (meta) {
      const children = meta.children;
      if (children[0]) children[0].querySelector('.meta-val').textContent = a.uptime_s ? fmtUptime(a.uptime_s) : '--';
      if (children[1]) children[1].querySelector('.meta-val').textContent = fmtAgo(a.last_heartbeat);
      if (children[2]) children[2].querySelector('.meta-val').textContent = a.pid || 'N/A';
      if (children[3]) children[3].querySelector('.meta-val').textContent = fmtAgo(a.started_at);
    }
    updateAgentChart(a);
  }
}

function statusColor(s) {
  return { running: 'var(--green)', busy: 'var(--yellow)', idle: 'var(--text-dim)', stopped: 'var(--red)', crashed: 'var(--orange)', retired: 'var(--text-dim)', cost_capped: 'var(--orange)' }[s] || 'var(--text-dim)';
}

async function buildAgentCharts(agents) {
  for (const k in agentCharts) {
    try { agentCharts[k].destroy(); } catch { /* gone */ }
    delete agentCharts[k];
  }
  for (const a of agents) {
    const canvas = document.getElementById(`chart-${a.id}`);
    if (!canvas) continue;
    try {
      const metrics = await api('GET', `/api/agents/${a.id}/metrics?limit=30`);
      const data = metrics.reverse();
      agentCharts[a.id] = new Chart(canvas, {
        type: 'line',
        data: {
          labels: data.map((_, i) => i),
          datasets: [{
            data: data.map(m => m.cpu),
            borderColor: '#7c5cff',
            backgroundColor: 'rgba(124,92,255,.12)',
            borderWidth: 1.5, fill: true, tension: .4, pointRadius: 0,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          animation: { duration: 400, easing: 'easeOutQuart' },
          plugins: { legend: { display: false } },
          scales: { x: { display: false }, y: { display: false, beginAtZero: true } },
        },
      });
    } catch { /* skip */ }
  }
}

async function updateAgentChart(a) {
  const chart = agentCharts[a.id];
  if (!chart) return;
  try {
    const metrics = await api('GET', `/api/agents/${a.id}/metrics?limit=30`);
    const data = metrics.reverse();
    chart.data.labels = data.map((_, i) => i);
    chart.data.datasets[0].data = data.map(m => m.cpu);
    chart.update('active');
  } catch { /* skip */ }
}

// ── Agent drawer (memory / messages / cost) ──
const drawerState = { open: false, agentId: null, tab: 'overview', cache: {} };

function closeDrawer() {
  drawerState.open = false;
  const d = $('#drawer'), o = $('#drawerOverlay');
  if (d) { d.classList.remove('open'); d.setAttribute('aria-hidden', 'true'); }
  if (o) o.style.display = 'none';
  if (pendingRender && !uiLocked()) { pendingRender = false; render(); }
}

function openAgentDrawer(id, tab = 'overview') {
  const a = (state.agents || []).find(x => x.id === id);
  if (!a) return;
  drawerState.open = true;
  drawerState.agentId = id;
  drawerState.tab = tab;
  drawerState.cache = {};
  const d = $('#drawer'), o = $('#drawerOverlay');
  o.style.display = 'block';
  d.classList.add('open');
  d.setAttribute('aria-hidden', 'false');
  renderDrawerShell(a);
  renderDrawerTab();
}

function renderDrawerShell(a) {
  $('#drawer').innerHTML = `
    <div class="drawer-head">
      <span class="status-dot ${a.status === 'running' ? 'online' : a.status === 'busy' ? 'busy' : ''}" style="background:${statusColor(a.status)}"></span>
      <h2>${esc(a.name)} <span class="agent-status-badge status-${esc(a.status)}">${esc(a.status)}</span></h2>
      <button class="btn-icon" onclick="closeDrawer()" title="Close">✕</button>
    </div>
    <div class="drawer-tabs">
      ${['overview', 'memory', 'messages', 'cost'].map(t =>
        `<button class="dtab ${drawerState.tab === t ? 'active' : ''}" onclick="switchDrawerTab('${t}')">${t[0].toUpperCase() + t.slice(1)}</button>`).join('')}
    </div>
    <div class="drawer-body" id="drawerBody"><div class="loading">Loading…</div></div>
  `;
}

async function setAgentConfig(id, patch) {
  try {
    const updated = await api('PATCH', `/api/agents/${id}/config`, patch);
    const i = (state.agents || []).findIndex(x => x.id === id);
    if (i >= 0) state.agents[i] = updated;
    toast('Agent config saved — applies on the next tick', 'ok');
  } catch (e) { toast('Config save failed: ' + e.message, 'err'); }
}

function switchDrawerTab(tab) {
  drawerState.tab = tab;
  $$('.dtab').forEach((el, i) => el.classList.toggle('active', ['overview', 'memory', 'messages', 'cost'][i] === tab));
  renderDrawerTab();
}

async function renderDrawerTab() {
  const id = drawerState.agentId;
  const a = (state.agents || []).find(x => x.id === id);
  const body = $('#drawerBody');
  if (!a || !body) return;
  try {
    if (drawerState.tab === 'overview') body.innerHTML = drawerOverviewHTML(a);
    else if (drawerState.tab === 'memory') {
      if (!isAdminUser()) {   // admin-gated endpoints — a member gets a note, not a 403 (F103)
        body.innerHTML = '<div class="empty"><span class="e-ico">🔒</span>Agent memory is admin-only.</div>';
        return;
      }
      body.innerHTML = '<div class="loading">Loading memory…</div>';
      const [mem, ctxBlob] = await Promise.all([
        api('GET', `/api/agents/${id}/memory?limit=100`),
        api('GET', `/api/agents/${id}/memory/context`).catch(() => null),
      ]);
      drawerState.cache.memory = mem.memory || [];
      drawerState.cache.context = ctxBlob;
      body.innerHTML = drawerMemoryHTML(a);
    } else if (drawerState.tab === 'messages') {
      if (!isAdminUser()) {
        body.innerHTML = '<div class="empty"><span class="e-ico">🔒</span>Agent messages are admin-only.</div>';
        return;
      }
      body.innerHTML = '<div class="loading">Loading messages…</div>';
      const msgs = await api('GET', `/api/agents/${id}/messages?limit=50`);
      drawerState.cache.messages = msgs.messages || [];
      body.innerHTML = drawerMessagesHTML(a);
    } else if (drawerState.tab === 'cost') {
      body.innerHTML = '<div class="loading">Loading cost…</div>';
      drawerState.cache.cost = await api('GET', `/api/agents/${id}/cost`);
      body.innerHTML = drawerCostHTML(a);
    }
  } catch (e) {
    body.innerHTML = `<div class="empty">Failed to load: ${esc(e.message)}</div>`;
  }
}

function drawerOverviewHTML(a) {
  const prog = (state.programs || []).find(p => p.id === a.program_id);
  return `
    <div class="drawer-sec">
      <h4>Live</h4>
      <div class="agent-current-task"><span class="task-icon">▸</span><span class="task-text">${esc(a.current_task || '— Idle —')}</span></div>
    </div>
    <div class="drawer-sec">
      <h4>Identity</h4>
      <div class="kv-row"><span class="kv-key">ID</span><span class="kv-val">${esc(a.id)}</span></div>
      <div class="kv-row"><span class="kv-key">Role</span><span class="kv-val">${esc(a.role)}</span></div>
      <div class="kv-row"><span class="kv-key">Model</span><span class="kv-val">${esc(a.model || '—')}</span></div>
      <div class="kv-row"><span class="kv-key">Program</span><span class="kv-val">${prog ? esc(prog.name) : '—'}</span></div>
      <div class="kv-row"><span class="kv-key">PID</span><span class="kv-val">${a.pid || '—'}</span></div>
      <div class="kv-row"><span class="kv-key">Started</span><span class="kv-val">${fmtAgo(a.started_at)}</span></div>
      <div class="kv-row"><span class="kv-key">Heartbeat</span><span class="kv-val">${fmtAgo(a.last_heartbeat)}</span></div>
      <div class="kv-row"><span class="kv-key">Worktree</span><span class="kv-val">${esc(a.worktree_path || 'none')}</span></div>
      <div class="kv-row"><span class="kv-key">Tasks</span><span class="kv-val">${a.tasks_completed} done · ${a.tasks_failed} failed</span></div>
    </div>
    <div class="drawer-sec">
      <h4>Configuration</h4>
      ${(() => {
        let cfg = {};
        try { cfg = JSON.parse(a.config || '{}') || {}; } catch { }
        const ac = cfg.auto_claim !== false; // default true, matching the worker
        return `
        <label style="display:flex;align-items:center;gap:8px;font-size:12.5px;margin-bottom:8px">
          <input type="checkbox" id="cfg-autoclaim" ${ac ? 'checked' : ''}
            onchange="setAgentConfig('${esc(a.id)}', { auto_claim: this.checked })">
          Auto-claim: pick up unassigned Todo tasks by itself
        </label>
        <div style="display:flex;gap:8px;align-items:center;font-size:12.5px">
          <span>Token cap (0 = none):</span>
          <input class="form-input" id="cfg-maxtokens" type="number" min="0" step="100000" value="${cfg.max_tokens || 0}" style="width:130px">
          <button class="btn-sm" onclick="setAgentConfig('${esc(a.id)}', { max_tokens: parseInt($('#cfg-maxtokens').value) || 0 })">Set</button>
        </div>
        <div class="form-hint" style="margin-top:4px">Applies live — the lane re-reads its config every tick. The token cap makes the watchdog pause this lane at the limit (cost_capped).</div>`;
      })()}
    </div>
    <div class="drawer-sec">
      <h4>Rename</h4>
      <div style="display:flex;gap:8px">
        <input class="form-input" id="renameInput" value="${esc(a.name)}" style="flex:1">
        <button class="btn-ghost" onclick="renameAgentUI('${esc(a.id)}')">Rename</button>
      </div>
    </div>
    <div class="drawer-sec">
      <h4>Actions</h4>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn-ghost" onclick="restartAgent('${esc(a.id)}')">↻ Restart</button>
        <button class="btn-ghost" onclick="createWorktreeUI('${esc(a.id)}')">⎇ Create worktree</button>
        ${a.status !== 'retired' ? `<button class="btn-ghost" title="End this lane for good — the watchdog will never respawn it" onclick="retireAgentUI('${esc(a.id)}')">⏻ Retire</button>` : ''}
        <button class="btn-sm danger" onclick="deleteAgent('${esc(a.id)}');closeDrawer()">✕ Stop agent</button>
      </div>
    </div>
  `;
}

const MEM_SCOPES = ['stm', 'lts', 'experience', 'longterm'];
function drawerMemoryHTML(a) {
  const mems = drawerState.cache.memory || [];
  const ctxBlob = drawerState.cache.context;
  const byScope = {};
  mems.forEach(m => { (byScope[m.scope] = byScope[m.scope] || []).push(m); });
  const scopeColor = { stm: 'c-blue', lts: 'c-accent', experience: 'c-cyan', longterm: 'c-green' };
  const sections = MEM_SCOPES.filter(s => (byScope[s] || []).length).map(scope => `
    <div class="drawer-sec">
      <h4>${scope} <span class="muted">(${byScope[scope].length})</span></h4>
      ${byScope[scope].map(m => `
        <div class="mem-item">
          <div style="flex:1">${esc(m.content)}
            <div class="mi-meta">${fmtAgo(m.created_at)}${m.kind ? ' · ' + esc(m.kind) : ''}${m.source ? ' · ' + esc(m.source) : ''}</div>
          </div>
          <button class="btn-icon" title="Forget" onclick="deleteAgentMemoryUI('${esc(a.id)}','${esc(m.id)}')">✕</button>
        </div>`).join('')}
    </div>`).join('');
  return `
    ${ctxBlob ? `<div class="drawer-sec"><h4>Condensed context (what it recalls on tasks)</h4>
      <div class="mem-item" style="flex-direction:column;gap:6px;align-items:stretch">
        <div><span class="chip c-accent">LTS summary</span><div style="margin-top:6px;font-size:12.5px">${esc(ctxBlob.lts_summary)}</div></div>
        <div style="margin-top:4px"><span class="chip c-cyan">Recent experience</span><pre style="margin-top:6px;font-size:11.5px;white-space:pre-wrap;font-family:var(--font-ui)">${esc(ctxBlob.recent_experience)}</pre></div>
      </div></div>` : ''}
    ${sections || '<div class="empty"><span class="e-ico">◍</span>No memories yet — this agent has not learned anything.</div>'}
    <div class="drawer-sec">
      <h4>Teach this agent</h4>
      <div style="display:flex;gap:8px">
        <select class="form-select" id="memScopeSel" style="width:130px">${MEM_SCOPES.map(s => `<option value="${s}">${s}</option>`).join('')}</select>
        <input class="form-input" id="memAddInput" placeholder="New memory…" style="flex:1">
        <button class="btn-primary" onclick="addAgentMemoryUI('${esc(a.id)}')">Add</button>
      </div>
    </div>
  `;
}

function drawerMessagesHTML(a) {
  const msgs = drawerState.cache.messages || [];
  const others = (state.agents || []).filter(x => x.id !== a.id);
  const rows = msgs.map(m => {
    const inbound = m.to_agent === a.id;
    return `<div class="msg-row" style="border-left:3px solid ${inbound ? 'var(--accent-2)' : 'var(--accent)'}">
      <div class="m-head"><span>${inbound ? '⬇ from' : '⬆ to'} <b>${esc(inbound ? m.from_agent : m.to_agent)}</b></span><span>${fmtAgo(m.ts)}</span></div>
      <div>${esc(m.content)}</div>
    </div>`;
  }).join('') || '<div class="empty"><span class="e-ico">✉</span>No messages yet.</div>';
  return `
    <div class="drawer-sec"><h4>Inter-agent messages</h4>${rows}</div>
    <div class="drawer-sec">
      <h4>Send a message to ${esc(a.name)}</h4>
      <div style="display:flex;gap:8px">
        <select class="form-select" id="msgFromSel" style="width:150px">
          <option value="operator">operator (you)</option>
          ${others.map(x => `<option value="${esc(x.id)}">${esc(x.name)}</option>`).join('')}
        </select>
        <input class="form-input" id="msgInput" placeholder="Message…" style="flex:1">
        <button class="btn-primary" onclick="sendAgentMessageUI('${esc(a.id)}')">Send</button>
      </div>
    </div>
  `;
}

function drawerCostHTML(a) {
  const c = drawerState.cache.cost || {};
  const pct = c.pct_of_cap;
  return `
    <div class="drawer-sec">
      <h4>Token spend</h4>
      <div class="stat-grid" style="grid-template-columns:1fr 1fr;margin-bottom:0">
        <div class="stat-card"><div class="stat-label">Total tokens</div><div class="stat-value" style="font-size:24px">${fmtTokens(c.total || 0)}</div>
          <div class="stat-sub">↓${fmtTokens(c.tokens_in || 0)} in · ↑${fmtTokens(c.tokens_out || 0)} out</div></div>
        <div class="stat-card green"><div class="stat-label">Projected cost</div><div class="stat-value" style="font-size:24px">$${(c.projected_usd || 0).toFixed(4)}</div>
          <div class="stat-sub">at configured $/1M rate</div></div>
      </div>
    </div>
    <div class="drawer-sec">
      <h4>Cap</h4>
      ${c.max_tokens ? `
        <div style="display:flex;justify-content:space-between;font-size:12px"><span>${fmtTokens(c.total || 0)} / ${fmtTokens(c.max_tokens)}</span><b style="font-family:var(--font-mono);color:${pct > 85 ? 'var(--red)' : 'var(--text)'}">${pct}%</b></div>
        <div class="cost-cap-bar"><div class="cost-cap-fill" style="width:${Math.min(100, pct || 0)}%;${pct > 85 ? 'background:linear-gradient(90deg,var(--orange),var(--red))' : ''}"></div></div>
        <div class="muted">The watchdog force-stops this agent at 100% (status <code>cost_capped</code>).</div>`
      : '<div class="muted">No token cap configured for this agent (set <code>max_tokens</code> in its config to enable the guardrail).</div>'}
    </div>
  `;
}

async function retireAgentUI(id) {
  if (!confirm('Retire this agent lane? Its worker stops, unfinished tasks go back to the board, and the watchdog will NEVER respawn it. (This is the proper way to end a lane.)')) return;
  try {
    await api('POST', `/api/agents/${id}/retire`);
    toast('Agent retired — released tasks are back on the board', 'ok');
    closeDrawer();
    softRender();
  } catch (e) { toast('Retire failed: ' + e.message, 'err'); }
}

async function renameAgentUI(id) {
  const name = ($('#renameInput') || {}).value?.trim();
  if (!name) return;
  try {
    await api('PATCH', `/api/agents/${id}/rename`, { name });
    state.agents = await api('GET', '/api/agents');
    agentsBuilt = false;
    toast('Agent renamed', 'ok');
    const a = state.agents.find(x => x.id === id);
    if (a) { renderDrawerShell(a); renderDrawerTab(); }
  } catch { /* toast shown by api() */ }
}

async function addAgentMemoryUI(id) {
  const inp = $('#memAddInput'), scope = ($('#memScopeSel') || {}).value || 'experience';
  const content = inp ? inp.value.trim() : '';
  if (!content) return;
  await api('POST', `/api/agents/${id}/memory`, { scope, kind: 'manual', content, source: 'operator' });
  toast('Memory added', 'ok');
  renderDrawerTab();
}

async function deleteAgentMemoryUI(id, mid) {
  await api('DELETE', `/api/agents/${id}/memory/${mid}`);
  renderDrawerTab();
}

async function sendAgentMessageUI(id) {
  const inp = $('#msgInput'), from = ($('#msgFromSel') || {}).value || 'operator';
  const content = inp ? inp.value.trim() : '';
  if (!content) return;
  await api('POST', `/api/agents/${id}/message`, { from_agent: from, content });
  toast('Message sent', 'ok');
  renderDrawerTab();
}

async function createWorktreeUI(id) {
  // A worktree gives this lane an isolated COPY of a git repo so parallel
  // agents editing code never overwrite each other. Only useful for coding
  // tasks against a repo — business deliverables use task workspaces instead.
  let hint = '~/nexus-agent-os';
  try {
    const pr = await api('GET', '/api/projects');
    const gitRepos = (pr.projects || []).filter(p => p.is_repo).map(p => p.path).filter(Boolean);
    if (gitRepos.length) hint = gitRepos.slice(0, 3).join('\n');
  } catch { /* suggestions optional */ }
  const repo = prompt(
    'Git worktree = an isolated copy of a code repository for this lane (coding tasks only; '
    + 'business deliverables don\'t need this).\n\nFull path of the git repo to isolate, e.g.:\n' + hint,
    '');
  if (repo === null || !repo.trim()) return;
  try {
    const r = await api('POST', `/api/agents/${id}/worktree`, { repo_path: repo.trim() });
    toast(`Worktree created: ${(r.worktree || {}).worktree_path || 'ok'}`, 'ok');
    state.agents = await api('GET', '/api/agents');
    renderDrawerTab();
  } catch (e) { toast('Worktree failed: ' + e.message, 'err'); }
}

// ═══════════════════════════════ PROGRAMS ═══════════════════════════════
function viewPrograms() {
  return `
    <div style="margin-bottom:16px">
      <button class="btn-primary" onclick="showProgramModal()">+ Register Program</button>
    </div>
    <div class="prog-grid">
      ${(state.programs || []).map(p => progCard(p)).join('') || '<div class="empty"><span class="e-ico">▤</span>No programs registered</div>'}
    </div>
  `;
}

function progCard(p) {
  const tags = (() => { try { return JSON.parse(p.tags || '[]'); } catch { return []; } })();
  return `
    <div class="prog-card">
      <div class="prog-header">
        <div class="prog-name">${esc(p.name)}</div>
        <span class="prog-lang">${esc(p.language)}</span>
      </div>
      <div class="prog-desc">${esc(p.description || 'No description')}</div>
      <div class="prog-stats">
        <div><div class="prog-stat-val">${p.run_count || 0}</div><div class="prog-stat-label">Runs</div></div>
        <div><div class="prog-stat-val">${p.avg_duration ? fmtDuration(p.avg_duration) : '--'}</div><div class="prog-stat-label">Avg Time</div></div>
        <div><div class="prog-stat-val">${p.agent_count || 0}</div><div class="prog-stat-label">Agents</div></div>
        <div><div class="prog-stat-val">${p.task_count || 0}</div><div class="prog-stat-label">Tasks</div></div>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span class="agent-status-badge status-${p.status === 'running' ? 'running' : p.status === 'active' ? 'busy' : 'idle'}">${esc(p.status)}</span>
        <div class="prog-tags">${tags.map(t => `<span class="task-tag">${esc(t)}</span>`).join('')}</div>
      </div>
      <div style="font-size:11px;color:var(--text-faint);margin-top:9px;font-family:var(--font-mono)">Entry: ${esc(p.entry_point || 'N/A')}</div>
    </div>
  `;
}

// ═══════════════════════════════ MONITOR ═══════════════════════════════
function viewMonitor() {
  const sys = state.stats.system || {};
  return `
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-head"><span class="stat-label">CPU Usage</span></div>
        <div class="stat-value" id="monCpuVal">${(sys.cpu_percent || 0).toFixed(1)}<span style="font-size:15px;color:var(--text-dim)">%</span></div>
        <div class="stat-sub" id="monCpuSub">${sys.cpu_count || 0} cores · Load ${((sys.load_avg || [0])[0] || 0).toFixed(2)}</div>
      </div>
      <div class="stat-card green">
        <div class="stat-head"><span class="stat-label">Memory</span></div>
        <div class="stat-value" id="monMemVal">${(sys.mem_used_gb || 0).toFixed(1)}<span style="font-size:15px;color:var(--text-dim)">GB</span></div>
        <div class="stat-sub" id="monMemSub">${sys.mem_total_gb || 0}GB total · ${(sys.mem_percent || 0).toFixed(0)}% used</div>
      </div>
      <div class="stat-card blue">
        <div class="stat-head"><span class="stat-label">Network I/O</span></div>
        <div class="stat-value" id="monNetVal">${(sys.net_sent_mb || 0).toFixed(0)}<span style="font-size:14px;color:var(--text-dim)">MB↑</span></div>
        <div class="stat-sub" id="monNetSub">${(sys.net_recv_mb || 0).toFixed(0)}MB received</div>
      </div>
      <div class="stat-card orange">
        <div class="stat-head"><span class="stat-label">Disk Usage</span></div>
        <div class="stat-value" id="monDiskVal">${(sys.disk_used_gb || 0).toFixed(0)}<span style="font-size:15px;color:var(--text-dim)">GB</span></div>
        <div class="stat-sub" id="monDiskSub">${sys.disk_total_gb || 0}GB total · ${(sys.disk_percent || 0).toFixed(0)}% used</div>
      </div>
    </div>
    <div class="monitor-grid">
      <div class="panel">
        <div class="panel-header"><span class="panel-title">CPU Usage (Live)</span></div>
        <div class="panel-body"><div class="chart-container"><canvas id="monCpu"></canvas></div></div>
      </div>
      <div class="panel">
        <div class="panel-header"><span class="panel-title">Memory Usage (Live)</span></div>
        <div class="panel-body"><div class="chart-container"><canvas id="monMem"></canvas></div></div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header"><span class="panel-title">Per-Agent CPU (Live)</span></div>
      <div class="panel-body"><div class="chart-container big-chart"><canvas id="monAgents"></canvas></div></div>
    </div>
  `;
}

let monitorHistory = { cpu: [], mem: [], labels: [] };

async function bindMonitorCharts() {
  if (monBuilt) return;
  monBuilt = true;
  monitorHistory = { cpu: [], mem: [], labels: [] };

  // destroy last visit's instances — Chart.js keeps RAF/ResizeObserver alive otherwise
  for (const k of ['cpu', 'mem', 'agents']) {
    if (charts[k]) { try { charts[k].destroy(); } catch { /* gone */ } delete charts[k]; }
  }

  const cpuCanvas = $('#monCpu');
  const memCanvas = $('#monMem');
  const agentsCanvas = $('#monAgents');
  if (!cpuCanvas) return;

  const baseOpts = {
    responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
    plugins: { legend: { display: false } },
    scales: {
      x: { display: false },
      y: { beginAtZero: true, ticks: { color: '#5e5e78', font: { size: 10 } }, grid: { color: 'rgba(148,148,190,.08)' } },
    },
  };

  charts.cpu = new Chart(cpuCanvas, {
    type: 'line',
    data: { labels: [], datasets: [{ data: [], borderColor: '#7c5cff', backgroundColor: 'rgba(124,92,255,.14)', fill: true, tension: .3, pointRadius: 0, borderWidth: 2 }] },
    options: { ...baseOpts, scales: { ...baseOpts.scales, y: { ...baseOpts.scales.y, max: 100 } } },
  });

  charts.mem = new Chart(memCanvas, {
    type: 'line',
    data: { labels: [], datasets: [{ data: [], borderColor: '#5eead4', backgroundColor: 'rgba(94,234,212,.13)', fill: true, tension: .3, pointRadius: 0, borderWidth: 2 }] },
    options: baseOpts,
  });

  const agents = state.agents || [];
  const datasets = agents.map((a, i) => ({
    label: a.name,
    data: [],
    borderColor: ['#7c5cff', '#5eead4', '#fbbf24', '#f87171', '#60a5fa', '#fb923c', '#4ade80'][i % 7],
    tension: .3, pointRadius: 0, borderWidth: 1.5, fill: false,
  }));
  charts.agents = new Chart(agentsCanvas, {
    type: 'line',
    data: { labels: [], datasets },
    options: {
      ...baseOpts,
      plugins: { legend: { display: true, position: 'bottom', labels: { color: '#9a9ab2', font: { size: 11 }, boxWidth: 12 } } },
      scales: { x: { display: false }, y: { beginAtZero: true, ticks: { color: '#5e5e78', font: { size: 10 } }, grid: { color: 'rgba(148,148,190,.08)' } } },
    },
  });

  if (charts.monitorInterval) clearInterval(charts.monitorInterval);
  charts.monitorInterval = setInterval(updateMonitorCharts, 2000);
}

async function updateMonitorCharts() {
  if (currentView !== 'monitor') {
    clearInterval(charts.monitorInterval);
    return;
  }
  try {
    const sys = state.stats.system || {};
    // patch stat tiles in place
    const set = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };
    set('monCpuVal', `${(sys.cpu_percent || 0).toFixed(1)}<span style="font-size:15px;color:var(--text-dim)">%</span>`);
    set('monCpuSub', `${sys.cpu_count || 0} cores · Load ${((sys.load_avg || [0])[0] || 0).toFixed(2)}`);
    set('monMemVal', `${(sys.mem_used_gb || 0).toFixed(1)}<span style="font-size:15px;color:var(--text-dim)">GB</span>`);
    set('monMemSub', `${sys.mem_total_gb || 0}GB total · ${(sys.mem_percent || 0).toFixed(0)}% used`);
    set('monNetVal', `${(sys.net_sent_mb || 0).toFixed(0)}<span style="font-size:14px;color:var(--text-dim)">MB↑</span>`);
    set('monNetSub', `${(sys.net_recv_mb || 0).toFixed(0)}MB received`);
    set('monDiskVal', `${(sys.disk_used_gb || 0).toFixed(0)}<span style="font-size:15px;color:var(--text-dim)">GB</span>`);
    set('monDiskSub', `${sys.disk_total_gb || 0}GB total · ${(sys.disk_percent || 0).toFixed(0)}% used`);

    const t = new Date().toLocaleTimeString('en-US', { hour12: false });
    monitorHistory.cpu.push(sys.cpu_percent || 0);
    monitorHistory.mem.push(sys.mem_used_gb || 0);
    monitorHistory.labels.push(t);
    if (monitorHistory.cpu.length > 30) {
      monitorHistory.cpu.shift(); monitorHistory.mem.shift(); monitorHistory.labels.shift();
    }
    if (charts.cpu) {
      charts.cpu.data.labels = monitorHistory.labels;
      charts.cpu.data.datasets[0].data = monitorHistory.cpu;
      charts.cpu.update('none');
    }
    if (charts.mem) {
      charts.mem.data.labels = monitorHistory.labels;
      charts.mem.data.datasets[0].data = monitorHistory.mem;
      charts.mem.update('none');
    }
    const agents = state.agents || [];
    const metricFetches = agents.slice(0, charts.agents.data.datasets.length)
      .map(a => api('GET', `/api/agents/${a.id}/metrics?limit=1`).catch(() => []));
    const results = await Promise.all(metricFetches);
    results.forEach((metrics, i) => {
      const cpu = metrics[0]?.cpu || 0;
      if (!charts.agents.data.datasets[i].data) charts.agents.data.datasets[i].data = [];
      charts.agents.data.datasets[i].data.push(cpu);
      if (charts.agents.data.datasets[i].data.length > 30) charts.agents.data.datasets[i].data.shift();
    });
    if (charts.agents.data.labels.length < monitorHistory.labels.length) {
      charts.agents.data.labels = monitorHistory.labels;
    }
    charts.agents.update('none');
  } catch { /* skip */ }
}

// ===== SIDEBAR MINI =====
function updateSidebarMini() {
  const sys = state.stats.system || {};
  const el1 = $('#miniCpu'); if (el1) el1.style.width = (sys.cpu_percent || 0) + '%';
  const el2 = $('#miniMem'); if (el2) el2.style.width = (sys.mem_percent || 0) + '%';
  const v1 = $('#miniCpuVal'); if (v1) v1.textContent = `${Math.round(sys.cpu_percent || 0)}%`;
  const v2 = $('#miniMemVal'); if (v2) v2.textContent = `${Math.round(sys.mem_percent || 0)}%`;
}

// ===== ACTIONS =====
async function restartAgent(id) {
  await api('POST', `/api/agents/${id}/restart`);
  state.agents = await api('GET', '/api/agents');
  agentsBuilt = false;
  toast('Agent restarting', 'ok');
  softRender();
}
async function deleteAgent(id) {
  const a = (state.agents || []).find(x => x.id === id);
  if (!confirm(`Stop and remove agent "${a ? a.name : id}"?`)) return;
  await api('DELETE', `/api/agents/${id}`);
  state.agents = await api('GET', '/api/agents');
  agentsBuilt = false;
  toast('Agent stopped', 'ok');
  softRender();
}

// ===== MODALS =====
function showSpawnModal() {
  const progOptions = (state.programs || []).map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
  $('#modalContent').innerHTML = `
    <h2>Spawn New Agent</h2>
    <div class="form-group">
      <label class="form-label">Agent Name</label>
      <input class="form-input" id="m-agent-name" placeholder="e.g. Agent-Hydra" value="Agent-${Math.random().toString(36).slice(2, 6).toUpperCase()}">
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Role</label>
        <select class="form-select" id="m-agent-role">
          <option value="worker">Worker</option>
          <option value="orchestrator">Orchestrator</option>
          <option value="analyzer">Analyzer</option>
          <option value="trainer">Trainer</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Program (optional)</label>
        <select class="form-select" id="m-agent-prog">
          <option value="">— None —</option>
          ${progOptions}
        </select>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label" style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" id="m-agent-autoclaim" checked> Auto-claim: pick up unassigned Todo tasks by itself</label>
    </div>
    <div class="form-hint" style="margin-bottom:10px">A lane is a worker that executes ONE task at a time. The AI model (from your registry in Settings → Models & routing) is chosen per TASK, not per lane — every lane runs whatever the task specifies.</div>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" onclick="submitSpawn()">Spawn</button>
    </div>
  `;
  $('#modal').style.display = 'flex';
}

async function submitSpawn() {
  const name = $('#m-agent-name').value.trim();
  const role = $('#m-agent-role').value;
  const prog = $('#m-agent-prog').value || null;
  if (!name) return;
  closeModal();
  const autoClaim = $('#m-agent-autoclaim') ? $('#m-agent-autoclaim').checked : true;
  await api('POST', '/api/agents', { name, role, program_id: prog, auto_claim: autoClaim });
  state.agents = await api('GET', '/api/agents');
  agentsBuilt = false;
  toast(`Agent ${name} spawned`, 'ok');
  render();
}

function showTaskModal(status) {
  const agentOptions = (state.agents || []).map(a => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join('');
  const progOptions = (state.programs || []).map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
  $('#modalContent').innerHTML = `
    <h2>Create Task</h2>
    <div class="form-group">
      <label class="form-label">Template (prefills everything)</label>
      <select class="form-select" id="m-task-template"><option value="">— Start blank —</option></select>
    </div>
    <div class="form-group">
      <label class="form-label">Title</label>
      <input class="form-input" id="m-task-title" placeholder="Task title">
    </div>
    <div class="form-group">
      <label class="form-label">Description</label>
      <textarea class="form-textarea" id="m-task-desc" placeholder="Task details..."></textarea>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Status</label>
        <select class="form-select" id="m-task-status">
          ${KANBAN_COLS.map(c => `<option value="${c.id}" ${status === c.id ? 'selected' : ''}>${c.name}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Priority</label>
        <select class="form-select" id="m-task-priority">
          <option value="0">Critical</option>
          <option value="1">High</option>
          <option value="2" selected>Normal</option>
          <option value="3">Low</option>
        </select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Assignee</label>
        <select class="form-select" id="m-task-assignee">
          <option value="">— Unassigned —</option>
          ${agentOptions}
        </select>
        <div class="form-hint">Which agent lane may run this. <strong>Unassigned</strong> = any free lane picks it up automatically (normal case). Pick a lane only to force who does it.</div>
      </div>
      <div class="form-group">
        <label class="form-label">Program</label>
        <select class="form-select" id="m-task-prog">
          <option value="">— None —</option>
          ${progOptions}
        </select>
        <div class="form-hint">Optional grouping label for reporting — has NO effect on execution. Leave empty unless you sort work by project.</div>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">AI model</label>
      <select class="form-select" id="m-task-model">${taskModelOptions('')}</select>
      <div class="form-hint">The list comes from your model registry (Settings → Models & routing). Concurrency is per model — putting light tasks on a lighter model keeps default-model slots free for the hard ones.</div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Domain (Business Brain)</label>
        <select class="form-select" id="m-task-domain">
          ${NEXUS_DOMAINS.map(d => `<option value="${d}">${d}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Specialist (optional)</label>
        <select class="form-select" id="m-task-specialist"><option value="">— Agent decides —</option></select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Token budget</label>
        <input class="form-input" id="m-task-budget" type="number" min="1000" step="1000" placeholder="default (1M)">
      </div>
      <div class="form-group">
        <label class="form-label" style="display:flex;align-items:center;gap:8px;margin-top:26px">
          <input type="checkbox" id="m-task-highstakes"> ⚖ High-stakes (pause for approval)</label>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label" style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" id="m-task-super"> ✨ Super Result</label>
      <div class="form-hint">A grounded frontier critic re-verifies every version of the deliverable
        with full tool access in a disposable sandbox, files line comments, and loops the work until
        it verifies. ~5–10× tokens — for work worth being right.</div>
    </div>
    <div class="form-group">
      <label class="form-label">🎚 Autopilot — how hands-on, and how much to spend</label>
      ${autopilotCardsHTML('m-task')}
    </div>
    <div class="form-group">
      <label class="form-label">Tags (comma-separated)</label>
      <input class="form-input" id="m-task-tags" placeholder="bug, urgent">
    </div>
    <div class="form-group">
      <label class="form-label">🧬 Existing code repository (repo-native task)</label>
      <select class="form-select" id="m-task-repo"><option value="">— None: fresh workspace (default) —</option></select>
      <div class="form-hint">Pick a repo and the task works INSIDE it: isolated git worktree + branch, follows the repo's AGENTS.md/CLAUDE.md conventions, runs its own test gates, and delivers a reviewable DIFF. Your main checkout is never touched.</div>
    </div>
    <div class="form-group">
      <label class="form-label">🔁 Looping — automatic improve-and-recheck rounds</label>
      <div class="form-hint" style="margin-bottom:6px">${LOOP_INTRO_SHORT}</div>
      <label style="display:flex;align-items:center;gap:8px"><input type="checkbox" id="m-task-loop"
        onchange="const o=$('#m-task-loop-opts'); if(o) o.style.display=this.checked?'block':'none'"> Enable looping for this task</label>
      <div id="m-task-loop-opts" style="display:none;margin-top:8px">${loopPrefCardsHTML('m-task')}
        <div class="form-hint" style="margin-top:4px">The loop itself is designed automatically for this exact task when you press Create — you can view, understand and change it afterwards via the task's 🔁 Loop settings.</div>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">📎 Attachments (input files the agent reads before working)</label>
      ${attachStageHTML('tc-attach')}
    </div>
    <div class="modal-actions" style="justify-content:space-between">
      <button class="btn-ghost" title="Save these form values as a reusable template" onclick="saveAsTemplateUI()">⭐ Save as template</button>
      <div style="display:flex;gap:10px">
        <button class="btn-ghost" onclick="closeModal()">Cancel</button>
        <button class="btn-primary" onclick="submitTask()">Create</button>
      </div>
    </div>
  `;
  $('#modal').style.display = 'flex';
  attachStageWire('tc-attach');
  // fill the specialist + template pickers async (cached)
  (async () => {
    try {
      if (!specialistNamesCache) {
        const r = await api('GET', '/api/specialists/names');
        specialistNamesCache = (r.specialists || []).map(s => s.name);
      }
      const sel = $('#m-task-specialist');
      if (sel) sel.innerHTML = `<option value="">— Agent decides —</option>` +
        specialistNamesCache.map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join('');
    } catch { /* optional */ }
    try {
      const repos = (await api('GET', '/api/projects')).projects || [];
      pruneStaleFocus(repos);
      const rsel = $('#m-task-repo');
      if (rsel && repos.length) {
        rsel.innerHTML = `<option value="">— None: fresh workspace (default) —</option>` +
          repos.map(r => `<option value="${esc(r.path)}">${r.client ? '🏢 ' + esc(r.client) + ' / ' : (r.personal ? '🏠 ' : '')}${esc(r.name)}</option>`).join('');
        // preselect AFTER the options exist — a timer here raced the fetch
        if (focusCtx.project) rsel.value = focusCtx.project.path;
      }
    } catch { /* optional */ }
    try {
      if (!templateCache) templateCache = (await api('GET', '/api/templates')).templates || [];
      const tsel = $('#m-task-template');
      if (tsel && templateCache.length) {
        tsel.innerHTML = `<option value="">— Start blank —</option>` +
          templateCache.map(t => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join('');
        tsel.onchange = () => {
          const tpl = templateCache.find(x => x.id === tsel.value);
          if (!tpl) return;
          $('#m-task-title').value = tpl.title || '';
          $('#m-task-desc').value = tpl.description || '';
          if ($('#m-task-domain')) $('#m-task-domain').value = tpl.domain || 'general';
          if ($('#m-task-highstakes')) $('#m-task-highstakes').checked = !!tpl.high_stakes;
          if ($('#m-task-tags')) $('#m-task-tags').value = (tpl.tags || []).join(', ');
          if ($('#m-task-model')) $('#m-task-model').value = tpl.model || '';
          const ssel = $('#m-task-specialist');
          if (ssel && tpl.specialist) {
            if (![...ssel.options].some(o => o.value === tpl.specialist)) {
              ssel.insertAdjacentHTML('beforeend', `<option value="${esc(tpl.specialist)}">${esc(tpl.specialist)}</option>`);
            }
            ssel.value = tpl.specialist;
          }
          toast('Template applied — replace the [brackets] with your specifics', 'ok');
        };
      }
    } catch { /* optional */ }
  })();
}
let templateCache = null;

async function saveAsTemplateUI() {
  const name = prompt('Template name (how it will appear in the picker):');
  if (name === null || !name.trim()) return;
  try {
    await api('POST', '/api/templates', {
      name: name.trim(),
      title: $('#m-task-title').value,
      description: $('#m-task-desc').value,
      domain: $('#m-task-domain') ? $('#m-task-domain').value : 'general',
      specialist: $('#m-task-specialist') ? ($('#m-task-specialist').value || null) : null,
      high_stakes: $('#m-task-highstakes') ? $('#m-task-highstakes').checked : false,
      model: $('#m-task-model') ? ($('#m-task-model').value || null) : null,
      tags: ($('#m-task-tags').value || '').split(',').map(t => t.trim()).filter(Boolean),
    });
    templateCache = null; // refresh on next open
    toast(`Template "⭐ ${name.trim()}" saved — it's in the picker from now on`, 'ok');
  } catch (e) { toast('Save failed: ' + e.message, 'err'); }
}

async function submitTask() {
  const title = $('#m-task-title').value.trim();
  if (!title) return;
  const tags = ($('#m-task-tags').value || '').split(',').map(t => t.trim()).filter(Boolean);
  const ap = selectedAutopilot('m-task');
  let loopCfg = null;
  if ($('#m-task-loop') && $('#m-task-loop').checked) {
    try {
      loopCfg = await designLoop('task', {
        preference: selectedLoopPref('m-task'),
        mode: 'closed',
        meta: {
          title,
          domain: $('#m-task-domain') ? $('#m-task-domain').value : null,
          specialist: $('#m-task-specialist') ? ($('#m-task-specialist').value || null) : null,
          high_stakes: $('#m-task-highstakes') ? $('#m-task-highstakes').checked : false,
          super_result: $('#m-task-super') ? $('#m-task-super').checked : false,
          autopilot: ap.autopilot, spend_profile: ap.spend_profile,
        },
      });
    } catch (e) { toast('Loop design failed (task created without loop): ' + e.message, 'err'); }
  }
  closeModal();
  const created = await api('POST', '/api/tasks', {
    loop_config: loopCfg,
    repo_path: $('#m-task-repo') ? ($('#m-task-repo').value || null) : null,
    title,
    description: $('#m-task-desc').value,
    status: $('#m-task-status').value,
    priority: parseInt($('#m-task-priority').value),
    assignee_id: $('#m-task-assignee').value || null,
    program_id: $('#m-task-prog').value || null,
    tags,
    domain: $('#m-task-domain') ? $('#m-task-domain').value : null,
    specialist: $('#m-task-specialist') ? ($('#m-task-specialist').value || null) : null,
    high_stakes: $('#m-task-highstakes') ? $('#m-task-highstakes').checked : false,
    super_result: $('#m-task-super') ? $('#m-task-super').checked : false,
    autopilot: ap.autopilot, spend_profile: ap.spend_profile,
    budget_tokens: $('#m-task-budget') && $('#m-task-budget').value ? parseInt($('#m-task-budget').value) : null,
    model: $('#m-task-model') ? ($('#m-task-model').value || null) : null,
    // exactly once (a duplicate key silently overwrote the focused project
    // with null): explicit create-context wins, else the focused project
    workflow_id: (taskCreateContext && taskCreateContext.workflow_id)
      || (focusCtx.workflow ? focusCtx.workflow.id : null),
    depends_on: taskCreateContext && (taskCreateContext.depends_on || []).length
      ? taskCreateContext.depends_on : null,
  });
  taskCreateContext = null;
  const nAtt = await attachStageUploadAll('tc-attach', 'task', created.id);
  wfState.fetched = false;
  state.tasks = await api('GET', '/api/tasks');
  toast(`Task created${nAtt ? ` with ${nAtt} attachment${nAtt > 1 ? 's' : ''}` : ''}`, 'ok');
  render();
}

function showProgramModal() {
  $('#modalContent').innerHTML = `
    <h2>Register Program</h2>
    <div class="form-group">
      <label class="form-label">Name</label>
      <input class="form-input" id="m-prog-name" placeholder="e.g. Sentiment Analyzer">
    </div>
    <div class="form-group">
      <label class="form-label">Description</label>
      <textarea class="form-textarea" id="m-prog-desc" placeholder="What does this program do?"></textarea>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Language</label>
        <select class="form-select" id="m-prog-lang">
          <option value="python">Python</option>
          <option value="node">Node.js</option>
          <option value="go">Go</option>
          <option value="rust">Rust</option>
          <option value="shell">Shell</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Entry Point</label>
        <input class="form-input" id="m-prog-entry" placeholder="main.py">
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Tags (comma-separated)</label>
      <input class="form-input" id="m-prog-tags" placeholder="ml, data, async">
    </div>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" onclick="submitProgram()">Register</button>
    </div>
  `;
  $('#modal').style.display = 'flex';
}

async function submitProgram() {
  const name = $('#m-prog-name').value.trim();
  if (!name) return;
  closeModal();
  const tags = $('#m-prog-tags').value.split(',').map(t => t.trim()).filter(Boolean);
  await api('POST', '/api/programs', {
    name,
    description: $('#m-prog-desc').value,
    language: $('#m-prog-lang').value,
    entry_point: $('#m-prog-entry').value,
    tags,
  });
  state.programs = await api('GET', '/api/programs');
  toast('Program registered', 'ok');
  render();
}

// ═══════════════════════════════ TOOLS HUB ═══════════════════════════════
const toolsState = { tools: null, loading: false, fetched: false };
async function loadTools() {
  if (toolsState.loading) return;
  toolsState.loading = true; toolsState.tools = null; render();
  try { const d = await api('GET', '/api/tools'); toolsState.tools = d.tools; }
  catch { toolsState.tools = []; }
  toolsState.loading = false; toolsState.fetched = true; render();
}
function viewTools() {
  if (!toolsState.fetched) { loadTools(); return skeletonView(); }
  if (toolsState.loading) return skeletonView();
  const tools = toolsState.tools || [];
  if (!tools.length) return `<div class="empty"><span class="e-ico">⚙</span>No tools detected.</div>`;
  const cats = {};
  tools.forEach(t => { (cats[t.category] = cats[t.category] || []).push(t); });
  const online = tools.filter(t => t.status === 'online').length;
  const cfg = tools.filter(t => t.status === 'configured').length;
  const off = tools.filter(t => t.status === 'offline').length;
  const part = tools.filter(t => t.status === 'partial').length;
  const sColor = s => ({ online: 'var(--green)', configured: 'var(--blue)', offline: 'var(--red)', partial: 'var(--yellow)' }[s] || 'var(--text-dim)');
  const sIcon = s => ({ online: '●', configured: '◐', offline: '○', partial: '◑' }[s] || '○');
  let html = `
    <div class="stats-strip">
      <div class="stat-card green"><div class="stat-num green">${online}</div><div class="stat-label">Online</div></div>
      <div class="stat-card blue"><div class="stat-num" style="color:var(--blue)">${cfg}</div><div class="stat-label">Configured</div></div>
      <div class="stat-card orange"><div class="stat-num" style="color:var(--yellow)">${part}</div><div class="stat-label">Partial</div></div>
      <div class="stat-card red"><div class="stat-num red">${off}</div><div class="stat-label">Offline</div></div>
      <div class="stat-card"><div class="stat-num">${tools.length}</div><div class="stat-label">Total Tools</div></div>
    </div>
    <button class="btn-primary" id="refreshTools" style="margin-bottom:6px">↻ Refresh Health Checks</button>`;
  for (const [cat, catTools] of Object.entries(cats)) {
    html += `<h3 class="section-title">${esc(cat)}</h3><div class="tool-grid">`;
    for (const t of catTools) {
      const icon = t.icon || '◇';
      const extra = [];
      if (t.model) extra.push(`<span class="tool-meta">model: ${esc(t.model)}</span>`);
      if (t.transcripts != null) extra.push(`<span class="tool-meta">${t.transcripts} sessions</span>`);
      if (t.skills_count != null) extra.push(`<span class="tool-meta">${t.skills_count} skills</span>`);
      if (t.models) extra.push(`<span class="tool-meta">${t.models.length} models</span>`);
      html += `
        <div class="tool-card" data-tool="${esc(t.id)}" style="--tool-color:${sColor(t.status)}">
          <div class="tool-header">
            <span class="tool-icon" style="color:${esc(t.accent || 'var(--accent)')}">${icon}</span>
            <div class="tool-name">${esc(t.name)}${t.primary ? ' <span class="badge-primary">PRIMARY</span>' : ''}</div>
            <span class="tool-status" style="color:${sColor(t.status)}">${sIcon(t.status)} ${esc(t.status)}</span>
          </div>
          <div class="tool-detail">${esc(t.detail || '')}</div>
          <div class="tool-extras">${extra.join('')}</div>
        </div>`;
    }
    html += `</div>`;
  }
  return html;
}
function bindTools() {
  const btn = $('#refreshTools');
  if (btn) btn.onclick = () => { toolsState.fetched = false; loadTools(); };
  $$('.tool-card').forEach(c => {
    c.onclick = () => {
      const id = c.dataset.tool;
      const t = (toolsState.tools || []).find(x => x.id === id);
      if (t) showModal(toolDetailHTML(t));
    };
  });
}
function toolDetailHTML(t) {
  const rows = Object.entries(t).filter(([k]) => !['icon'].includes(k));
  const cfg = rows.map(([k, v]) => {
    let val = v;
    if (Array.isArray(v)) val = v.length > 5 ? `${v.length} items` : v.join(', ');
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) val = JSON.stringify(v, null, 2).slice(0, 200);
    return `<div class="kv-row"><span class="kv-key">${esc(k)}</span><span class="kv-val">${val == null ? '—' : esc(String(val).slice(0, 300))}</span></div>`;
  }).join('');
  return `<div class="modal-head"><h2>${t.icon || '◇'} ${esc(t.name)}</h2></div>
    <div class="modal-body">${cfg}</div>`;
}

function skeletonView() {
  return `
    <div class="skel-grid" style="margin-bottom:16px">
      <div class="skel" style="height:86px"></div><div class="skel" style="height:86px"></div>
      <div class="skel" style="height:86px"></div><div class="skel" style="height:86px"></div>
    </div>
    <div class="skel" style="height:200px;margin-bottom:14px"></div>
    <div class="skel" style="height:200px"></div>`;
}

// ═══════════════════════════════ SKILLS ═══════════════════════════════
const skillsState = { data: null, loading: false, fetched: false, search: '', custom: [] };
async function loadSkills() {
  if (skillsState.loading) return;
  skillsState.loading = true; skillsState.data = null; render();
  try { skillsState.data = await api('GET', '/api/skills'); }
  catch { skillsState.data = { categories: [] }; }
  try { skillsState.custom = (await api('GET', '/api/hermes-skills')).skills || []; }
  catch { skillsState.custom = []; }
  skillsState.loading = false; skillsState.fetched = true; render();
}
function skillsResultsHTML() {
  const d = skillsState.data || { categories: [] };
  const search = skillsState.search.toLowerCase();
  let html = '', shown = 0;
  for (const cat of (d.categories || [])) {
    const filtered = cat.skills.filter(s =>
      !search || s.name.toLowerCase().includes(search) || (s.description || '').toLowerCase().includes(search));
    if (!filtered.length) continue;
    shown += filtered.length;
    html += `<h3 class="section-title">${esc(cat.name)} <span class="muted">(${filtered.length})</span></h3><div class="skill-grid">`;
    const maxUse = Math.max(...cat.skills.map(s => s.use_count), 1);
    for (const s of filtered) {
      const bar = Math.round((s.use_count / maxUse) * 100);
      const stale = s.state === 'archived' ? ' opacity:0.5;' : '';
      html += `
        <div class="skill-card" data-path="${esc(s.path)}" style="${stale}">
          <div class="skill-name">${esc(s.name)}${s.state === 'archived' ? ' <span class="muted">(archived)</span>' : ''}</div>
          <div class="skill-desc">${esc((s.description || '').slice(0, 120))}</div>
          <div class="skill-bar"><div class="skill-bar-fill" style="width:${bar}%"></div></div>
          <div class="skill-meta">used ${s.use_count}× · viewed ${s.view_count}×</div>
        </div>`;
    }
    html += `</div>`;
  }
  if (!shown) html += `<div class="empty"><span class="e-ico">✦</span>No skills match "${esc(skillsState.search)}".</div>`;
  return html;
}
function viewSkills() {
  if (!skillsState.fetched) { loadSkills(); return skeletonView(); }
  if (skillsState.loading) return skeletonView();
  const d = skillsState.data || { categories: [], total_skills: 0, total_uses: 0 };
  return `
    <div class="stats-strip">
      <div class="stat-card"><div class="stat-num" style="color:#b3a1ff">${d.total_skills || 0}</div><div class="stat-label">Skills</div></div>
      <div class="stat-card blue"><div class="stat-num" style="color:var(--accent-2)">${d.total_categories || 0}</div><div class="stat-label">Categories</div></div>
      <div class="stat-card green"><div class="stat-num green">${d.total_uses || 0}</div><div class="stat-label">Total Uses</div></div>
    </div>
    <div class="agentic-card" style="margin-bottom:14px">
      <div class="card-head"><h3>🛠 Your skills (editable)</h3>
        <button class="btn-primary sm" onclick="newSkillUI()">＋ New skill (AI wizard)</button></div>
      <div class="card-body">
        <div class="form-hint" style="margin-bottom:8px">These live in ~/.hermes/skills and teach every agent a repeatable how-to. Create or edit in plain words — the AI drafts, YOU review before it goes live.</div>
        ${(skillsState.custom || []).map(s => `
          <div class="agentic-row slim">
            <strong style="min-width:200px;font-size:12.5px">${esc(s.name)}</strong>
            <span style="flex:1;font-size:11.5px;color:var(--text-dim)">${esc(s.description || '')}</span>
            <button class="btn-sm" onclick="editHermesSkill('${esc(s.name)}')">✏ Edit</button>
          </div>`).join('') || '<div class="empty">No skills found in ~/.hermes/skills</div>'}
      </div>
    </div>
    <div class="search-bar"><input id="skillSearch" type="search" placeholder="Search skills by name or description…" value="${esc(skillsState.search)}"></div>
    <div id="skillResults">${skillsResultsHTML()}</div>`;
}
function bindSkills() {
  const inp = $('#skillSearch');
  if (inp) {
    inp.oninput = e => {
      skillsState.search = e.target.value;
      const res = $('#skillResults');
      if (res) { res.innerHTML = skillsResultsHTML(); bindSkillCards(); }
    };
  }
  bindSkillCards();
}
function bindSkillCards() {
  $$('.skill-card').forEach(c => {
    c.onclick = () => {
      const path = c.dataset.path;
      // Workspace-relative skill id: …/skills/<maybe-category>/<name>/SKILL.md
      const m = path.match(/\/skills\/(.+)\/SKILL\.md$/);
      if (m) { editHermesSkill(m[1]); return; }
      showModal(`<div class="modal-head"><h2>📄 ${esc(path.split('/').pop())}</h2></div>
        <div class="modal-body"><div class="kv-row"><span class="kv-key">Path</span><span class="kv-val">${esc(path)}</span></div>
        <p class="muted" style="margin-top:10px">This file lives outside ~/.hermes/skills and is not editable here.</p></div>`);
    };
  });
}

// ═══════════════════════════════ PROJECTS ═══════════════════════════════
const projectsState = { data: null, loading: false, fetched: false, sortBy: 'modified' };
async function loadProjects() {
  if (projectsState.loading) return;
  projectsState.loading = true; projectsState.data = null; render();
  try { projectsState.data = await api('GET', '/api/projects'); }
  catch { projectsState.data = { projects: [] }; }
  pruneStaleFocus((projectsState.data || {}).projects);
  projectsState.loading = false; projectsState.fetched = true; render();
}
function viewProjects() {
  if (!projectsState.fetched) { loadProjects(); return skeletonView(); }
  if (projectsState.loading) return skeletonView();
  const projs = (projectsState.data && projectsState.data.projects) || [];
  if (!projs.length) return `<div class="empty"><span class="e-ico">▣</span>No projects found.</div>`;
  const langColor = l => ({ Python: '#3776ab', JavaScript: '#f7df1e', TypeScript: '#3178c6', Rust: '#dea584', 'C': '#a8b9cc', 'C++': '#00599c', Shell: '#89e051', Markdown: '#888', HTML: '#e34c26', CSS: '#563d7c' }[l] || '#888');
  const fmtSize = b => b > 1e9 ? (b / 1e9).toFixed(1) + ' GB' : b > 1e6 ? (b / 1e6).toFixed(0) + ' MB' : (b / 1e3).toFixed(0) + ' KB';
  const fmtDays = ts => { const d = (Date.now() / 1000 - ts) / 86400; return d < 1 ? Math.round(d * 24) + 'h ago' : d < 30 ? Math.round(d) + 'd ago' : Math.round(d / 30) + 'mo ago'; };
  let html = `
    <div style="display:flex;justify-content:flex-end;margin-bottom:10px">
      <button class="btn-primary" onclick="newClientProjectUI()">➕ New project</button>
    </div>
    <div class="stats-strip">
      <div class="stat-card"><div class="stat-num" style="color:#b3a1ff">${projs.length}</div><div class="stat-label">Repositories</div></div>
      <div class="stat-card green"><div class="stat-num green">${projs.filter(p => p.is_repo).length}</div><div class="stat-label">Git Repos</div></div>
      <div class="stat-card orange"><div class="stat-num" style="color:var(--yellow)">${projs.filter(p => p.git_dirty).length}</div><div class="stat-label">Uncommitted</div></div>
      <div class="stat-card"><div class="stat-num">${fmtSize(projs.reduce((a, p) => a + p.size_bytes, 0))}</div><div class="stat-label">Total Size</div></div>
    </div>
    <div class="panel"><table class="data-table">
      <thead><tr><th>Project</th><th>Languages</th><th>Branch</th><th>Status</th><th>Focus</th><th>Remote</th><th>Size</th><th>Modified</th></tr></thead>
      <tbody>`;
  for (const p of projs) {
    const langs = Object.entries(p.languages).slice(0, 3).map(([l]) =>
      `<span class="lang-tag" style="border-left:3px solid ${langColor(l)}">${esc(l)}</span>`).join(' ');
    const status = p.git_dirty ? '<span style="color:var(--yellow)">● dirty</span>' :
      p.is_repo ? '<span style="color:var(--green)">● clean</span>' :
        '<span class="muted">○ no git</span>';
    html += `<tr class="proj-row" data-path="${esc(p.path)}">
      <td><div class="proj-name">${esc(p.name)} ${p.client ? `<span class="chip c-cyan" title="client project — memory isolated">🏢 ${esc(p.client)}</span>` : (p.personal ? '<span class="chip" title="personal project">🏠 personal</span>' : '')}</div><div class="proj-desc muted">${esc(p.description || '')}</div></td>
      <td>${langs}</td>
      <td><code class="git-branch">${esc(p.git_branch || '—')}</code></td>
      <td>${status}</td>
      <td>${p.is_repo ? `<button class="focus-btn" title="Work in this project: Workflows & Tasks scope to it; new work is assigned to it" onclick="event.stopPropagation(); setFocusProject('${esc(p.path)}','${esc(p.name)}','${esc(p.client || '')}')">🎯 ${focusCtx.project && focusCtx.project.path === p.path ? 'selected' : 'select'}</button>` : ''}</td>
      <td>${p.is_repo ? (p.git_remote ? '<span title="' + esc(p.git_remote) + '" style="color:var(--accent-2)">☁ backed up</span>' : '<span style="color:var(--yellow)">⚠ local only</span>') : '<span class="muted">—</span>'}</td>
      <td>${fmtSize(p.size_bytes)}</td>
      <td class="muted">${fmtDays(p.last_modified)}</td>
    </tr>`;
  }
  html += `</tbody></table></div>`;
  return html;
}
function bindProjects() {
  $$('.proj-row').forEach(r => {
    r.onclick = () => {
      const p = ((projectsState.data || {}).projects || []).find(x => x.path === r.dataset.path);
      if (!p) return;
      const langs = Object.entries(p.languages).map(([l, n]) => `<div class="kv-row"><span class="kv-key">${esc(l)}</span><span class="kv-val">${n} files</span></div>`).join('');
      showModal(`<div class="modal-head"><h2>📂 ${esc(p.name)}</h2></div>
        <div class="modal-body">
          <div class="kv-row"><span class="kv-key">Path</span><span class="kv-val">${esc(p.path)}</span></div>
          ${p.description ? `<div class="kv-row"><span class="kv-key">Description</span><span class="kv-val">${esc(p.description)}</span></div>` : ''}
          <div class="kv-row"><span class="kv-key">Git</span><span class="kv-val">${p.is_repo ? `branch <code>${esc(p.git_branch)}</code>${p.git_dirty ? ' (uncommitted changes)' : ''}<br><span class="muted">${esc(p.git_remote || '')}</span>` : 'not a git repo'}</span></div>
          <div class="kv-row"><span class="kv-key">Size</span><span class="kv-val">${(p.size_bytes / 1e6).toFixed(1)} MB</span></div>
          <div class="kv-row"><span class="kv-key">venv</span><span class="kv-val">${p.has_venv ? 'yes' : 'no'}</span></div>
          <h4 style="margin-top:12px">Languages</h4>${langs}
          ${p.is_repo ? `<h4 style="margin-top:14px">Work history</h4>
          <div id="repoHistory" class="muted" style="font-size:12px">loading…</div>` : ''}
          ${p.is_repo ? `
          <h4 style="margin-top:14px">Git workflow</h4>
          <div class="form-hint" style="margin-bottom:8px">${p.git_remote
            ? 'Backed up to a remote. Push after merges; tag what you deliver.'
            : '⚠ This repository exists ONLY on this machine — a disk failure loses it. Publish creates a PRIVATE GitHub repo and pushes everything (your offsite backup and the future handover vehicle).'}</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            ${!p.git_remote ? `<button class="btn-primary" onclick="publishRepoUI('${esc(p.path)}','${esc(p.name)}')">☁ Publish to GitHub (private)</button>` : `
            <button class="btn-primary" onclick="pushRepoUI('${esc(p.path)}')">⬆ Push to remote</button>
            <button class="btn-ghost" onclick="tagRepoUI('${esc(p.path)}','${esc(p.name)}')">🏷 Tag release</button>`}
          </div>` : ''}
        </div>`);
      if (p.is_repo) loadRepoHistory(p.path);
    };
  });
}

async function wfRepoChanged(repoSel) {
  if (repoSel.value === '__new__') {
    repoSel.value = '';
    const client = prompt('Client name:', ($('#wf-client') || {}).value || '');
    if (!client) return;
    const name = prompt('Project name:', '');
    if (!name) return;
    try {
      const r = await api('POST', '/api/projects/create-client',
        { client: slugify(client), name: slugify(name), publish: true });
      const opt = document.createElement('option');
      opt.value = r.path;
      opt.textContent = `🏢 ${r.client} / ${name.trim().toLowerCase()}`;
      opt.dataset.client = r.client;
      repoSel.insertBefore(opt, repoSel.lastElementChild);
      repoSel.value = r.path;
      if ($('#wf-client')) $('#wf-client').value = r.client;
      toast('Repository created' + (r.note ? ' — ' + r.note : ''), 'ok', 5000);
    } catch (e) { toast('Create failed: ' + e.message, 'err', 6000); }
    return;
  }
  // picking a client repo auto-fills the client scope — one source of truth
  const sel = repoSel.selectedOptions[0];
  if (sel && sel.dataset.client && $('#wf-client') && !$('#wf-client').value.trim()) {
    $('#wf-client').value = sel.dataset.client;
  }
}

// "Acme GmbH / Web Shop!" → "acme-gmbh" / "web-shop" — typing naturally just works
function slugify(s) {
  return String(s || '').trim().toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-').replace(/^[-.]+|[-.]+$/g, '').slice(0, 60);
}

function newClientProjectUI() {
  showModal(`
    <h2>➕ New project</h2>
    <div class="view-intro" style="margin-bottom:10px">Creates <code>~/Client-Projects/&lt;client&gt;/&lt;project&gt;</code> as a proper git repository (README, .gitignore, first commit) — the repo-first rule: client code is versioned and backable from minute one. Every work round then targets this repo via the wizard.</div>
    <label style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      <input type="checkbox" id="ncp-personal" onchange="const c=$('#ncp-client'); if(c){c.disabled=this.checked; c.value=this.checked?'':c.value;}">
      🏠 Personal project (no client — uni work, own experiments; stored under ~/Projects, memory stays personal)</label>
    <div class="form-row">
      <div class="form-group"><label class="form-label">Client</label>
        <input class="form-input" id="ncp-client" placeholder="acme"></div>
      <div class="form-group"><label class="form-label">Project</label>
        <input class="form-input" id="ncp-name" placeholder="webshop"></div>
    </div>
    <label style="display:flex;align-items:center;gap:8px;margin-top:6px">
      <input type="checkbox" id="ncp-publish" checked> ☁ Also publish privately to GitHub now (recommended — offsite backup from day one)</label>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" id="ncp-create">Create repository</button>
    </div>`);
  $('#ncp-create').onclick = async () => {
    const personal = !!($('#ncp-personal') && $('#ncp-personal').checked);
    const client = personal ? '' : slugify($('#ncp-client').value);
    const name = slugify($('#ncp-name').value);
    if (!name || (!personal && !client)) { toast(personal ? 'Project name required' : 'Client and project name required', 'err'); return; }
    $('#ncp-create').disabled = true; $('#ncp-create').textContent = 'Creating…';
    try {
      const r = await api('POST', '/api/projects/create-client',
        { client, name, publish: $('#ncp-publish').checked });
      toast(`Repository created: ${r.path}` + (r.note ? ' — ' + r.note : ''), 'ok', 6000);
      closeModal(); projectsState.fetched = false; render();
    } catch (e) {
      toast('Create failed: ' + e.message, 'err', 6000);
      $('#ncp-create').disabled = false; $('#ncp-create').textContent = 'Create repository';
    }
  };
}

async function promoteTaskUI(taskId, title) {
  showModal(`
    <h2>📦 Promote to repository</h2>
    <div class="view-intro" style="margin-bottom:10px">Lifts the app built in this task's workspace into a real client repository under <code>~/Client-Projects</code> (git history, backup, delivery workflow). All future work rounds then target the repository — this workspace stays as the historical record.</div>
    <div class="form-row">
      <div class="form-group"><label class="form-label">Client</label>
        <input class="form-input" id="pr-client" placeholder="acme (or 'internal')"></div>
      <div class="form-group"><label class="form-label">Project name</label>
        <input class="form-input" id="pr-name" placeholder="webshop"></div>
    </div>
    <div class="form-group"><label class="form-label">Code folder inside the workspace (empty = everything except reports)</label>
      <input class="form-input" id="pr-subdir" placeholder="e.g. webshop"></div>
    <label style="display:flex;align-items:center;gap:8px;margin-top:6px">
      <input type="checkbox" id="pr-publish" checked> ☁ Publish privately to GitHub</label>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" id="pr-go">Promote</button>
    </div>`);
  $('#pr-go').onclick = async () => {
    const client = slugify($('#pr-client').value);
    const name = slugify($('#pr-name').value);
    if (!client || !name) { toast('Client and project name required', 'err'); return; }
    $('#pr-go').disabled = true; $('#pr-go').textContent = 'Promoting…';
    try {
      const r = await api('POST', `/api/tasks/${taskId}/promote`,
        { client, name, subdir: $('#pr-subdir').value.trim(), publish: $('#pr-publish').checked });
      toast(`📦 Promoted to ${r.path} (${r.items} items)` + (r.note ? ' — ' + r.note : ''), 'ok', 7000);
      closeModal(); projectsState.fetched = false;
    } catch (e) {
      toast('Promote failed: ' + e.message, 'err', 6000);
      $('#pr-go').disabled = false; $('#pr-go').textContent = 'Promote';
    }
  };
}

async function loadRepoHistory(path) {
  const el = () => document.getElementById('repoHistory');
  try {
    const h = await api('GET', `/api/projects/history?path=${encodeURIComponent(path)}`);
    if (!el()) return;
    if (!h.total_tasks) {
      el().innerHTML = 'No pipelines have visited this project yet — target it via ✨ Describe a goal.';
      return;
    }
    const chip = s => `<span class="chip ${s === 'done' ? 'c-green' : s === 'in_progress' ? 'c-cyan' : ''}">${esc(s)}</span>`;
    el().innerHTML =
      (h.pipelines || []).map(w => `
        <div style="padding:6px 0;border-bottom:1px dashed rgba(148,148,190,.12)">
          <strong>⚑ ${esc(w.name)}</strong> <span class="muted">${new Date((w.created_at || 0) * 1000).toLocaleDateString()}</span><br>
          ${(w.tasks || []).map(t => `<span style="font-size:11.5px">· ${esc(t.title.slice(0, 48))} ${chip(t.status)}</span>`).join('<br>')}
        </div>`).join('') +
      (h.loose_tasks || []).map(t => `
        <div style="padding:4px 0">· ${esc(t.title.slice(0, 55))} ${chip(t.status)}</div>`).join('');
  } catch (e) {
    if (el()) el().textContent = 'history unavailable: ' + e.message;
  }
}

async function publishRepoUI(path, name) {
  const repoName = prompt('GitHub repository name (private):', name);
  if (!repoName) return;
  toast('Publishing to GitHub…', 'info');
  try {
    await api('POST', '/api/projects/publish', { path, name: repoName });
    toast('☁ Published privately to GitHub — this repo is now backed up offsite', 'ok', 5000);
    closeModal(); projectsState.fetched = false; render();
  } catch (e) { toast('Publish failed: ' + e.message, 'err', 6000); }
}

async function pushRepoUI(path) {
  toast('Pushing…', 'info');
  try {
    const r = await api('POST', '/api/projects/push', { path });
    toast('⬆ ' + (r.output || 'pushed'), 'ok', 4000);
  } catch (e) { toast('Push failed: ' + e.message, 'err', 6000); }
}

async function tagRepoUI(path, name) {
  const tag = prompt(`Release tag for ${name} (marks the exact delivered state):`, 'v1.0');
  if (!tag) return;
  const msg = prompt('Short release note (what was delivered):', `Release ${tag}`) || `Release ${tag}`;
  try {
    const r = await api('POST', '/api/projects/tag', { path, tag, message: msg });
    toast('🏷 ' + tag + ' — ' + (r.pushed ? 'tagged and pushed' : r.output), 'ok', 5000);
  } catch (e) { toast('Tag failed: ' + e.message, 'err', 6000); }
}

// ═══════════════════════════════ GUARDIAN ═══════════════════════════════
const guardianState = { data: null, loading: false, fetched: false };
async function loadGuardian() {
  if (guardianState.loading) return;
  guardianState.loading = true; render();
  try {
    const [g, cm] = await Promise.all([
      api('GET', '/api/guardian'),
      api('GET', '/api/coremods').catch(() => ({ mods: [] })),
    ]);
    guardianState.data = g; guardianState.coremods = cm;
  }
  catch (e) { guardianState.data = { error: String(e) }; }
  guardianState.loading = false; guardianState.fetched = true; render(); bindGuardian();
}
function _gcolor(o) { return o === 'OK' ? 'var(--green)' : (o === 'RESTORED' ? 'var(--yellow)' : 'var(--red)'); }
function viewGuardian() {
  const d = guardianState.data;
  if (!guardianState.fetched && !guardianState.loading) loadGuardian();
  if (guardianState.loading || !d) return skeletonView();
  if (d.error) return `<div class="panel"><div class="empty">${esc(d.error)}</div></div>`;
  if (!d.available) return `<div class="panel"><div class="empty"><span class="e-ico">▩</span>No guardian report yet — it runs on boot + every 15 min (systemd timer <code>hermes-guardian.timer</code>).</div></div>`;
  const r = d.latest || {}, s = r.summary || {};
  const probRows = (r.problems || []).map(p => `<tr><td>${esc(p.item)}</td><td style="color:var(--yellow)">${esc(p.status)}</td><td>${esc((p.detail || '').slice(0, 90))}</td></tr>`).join('')
    || `<tr><td colspan="3" style="color:var(--text-dim)">None — every change intact ✓</td></tr>`;
  const restRows = (r.restored || []).map(x => `<li>${esc(x)}</li>`).join('') || '<li style="color:var(--text-dim)">Nothing needed restoring.</li>';
  const hist = (d.history || []).map(h => `<tr><td>${esc((h.timestamp || '').replace('T', ' '))}</td><td style="color:${_gcolor(h.overall)}">${esc(h.overall)}</td><td>${h.was_post_update ? 'after update' : 'routine'}</td><td>${(h.restored || []).length}</td><td>${h.problems}</td></tr>`).join('')
    || `<tr><td colspan="5" style="color:var(--text-dim)">No noteworthy runs yet.</td></tr>`;
  return `
    <div class="view-intro">Verifies every hardening change survives Hermes updates &amp; reboots and auto-restores anything missing (files, packages, services, containers). Runs on boot + every 15 min.</div>
    <div class="stats-strip">
      <div class="stat-card ${r.overall === 'OK' ? 'green' : 'red'}"><div class="stat-num" style="color:${_gcolor(r.overall)}">${esc(r.overall || '?')}</div><div class="stat-label">Status</div></div>
      <div class="stat-card green"><div class="stat-num">${s.OK || 0}</div><div class="stat-label">Checks OK</div></div>
      <div class="stat-card orange"><div class="stat-num">${(r.restored || []).length}</div><div class="stat-label">Auto-Restored</div></div>
      <div class="stat-card"><div class="stat-num" style="color:${(r.problems || []).length ? 'var(--red)' : 'var(--green)'}">${(r.problems || []).length}</div><div class="stat-label">Problems</div></div>
    </div>
    <div style="color:var(--text-faint);margin:4px 0 14px;font-size:11px;font-family:var(--font-mono)">Last run ${esc((r.timestamp || '').replace('T', ' '))} · commit ${esc((r.hermes_commit || '').slice(0, 10))}${r.was_post_update ? ' · <b style="color:var(--yellow)">post-update run</b>' : ''}${r.gateway_restarted ? ' · gateway restarted' : ''}</div>
    ${viewCoremods()}
    <div class="panel" style="margin-top:14px"><div class="panel-header"><span class="panel-title">Problems / Drift</span></div>
      <table class="data-table"><thead><tr><th>Item</th><th>Status</th><th>Detail</th></tr></thead><tbody>${probRows}</tbody></table></div>
    <div class="panel" style="margin-top:14px"><div class="panel-header"><span class="panel-title">Restored this run</span></div><div style="padding:12px 18px"><ul style="margin:0;padding-left:18px">${restRows}</ul></div></div>
    <div class="panel" style="margin-top:14px"><div class="panel-header"><span class="panel-title">Run History</span><button class="btn-ghost" id="guardianRefresh">↻ Refresh</button></div>
      <table class="data-table"><thead><tr><th>Time</th><th>Result</th><th>Trigger</th><th>Restored</th><th>Problems</th></tr></thead><tbody>${hist}</tbody></table></div>`;
}
function _cmColor(s) {
  return { OK: 'var(--green)', REASSERTED: 'var(--yellow)', CONFLICT: 'var(--red)', FAIL: 'var(--red)', ACCEPTED_UPSTREAM: 'var(--text-dim)' }[s] || 'var(--text-dim)';
}
function viewCoremods() {
  const cm = (guardianState.coremods && guardianState.coremods.mods) || [];
  if (!cm.length) return '';
  const cards = cm.map(m => {
    const conflict = m.status === 'CONFLICT';
    const accepted = m.status === 'ACCEPTED_UPSTREAM' || m.standing === 'accept_upstream';
    let actions = '';
    if (conflict) {
      actions = `<div style="margin-top:9px;border-top:1px solid var(--border);padding-top:9px">
        <div style="color:var(--red);font-size:12px;margin-bottom:8px">⚠ A Hermes update changed these same lines. Impact if you drop ours: <b>${esc(m.impact_if_dropped)}</b></div>
        <button class="btn-primary cm-decide" data-name="${esc(m.name)}" data-decision="keep_ours">Keep ours (re-apply)</button>
        <button class="btn-ghost cm-decide" data-name="${esc(m.name)}" data-decision="accept_upstream" style="margin-left:8px">Accept upstream (drop ours)</button>
        ${m.patch ? `<details style="margin-top:9px"><summary style="cursor:pointer;color:var(--text-dim);font-size:12px">Show our change (diff)</summary><pre style="overflow-x:auto;background:rgba(7,7,13,.6);padding:10px;border-radius:8px;font-size:11px;margin-top:6px">${esc(m.patch)}</pre></details>` : ''}
      </div>`;
    } else if (accepted) {
      actions = `<div style="margin-top:8px;font-size:12px;color:var(--text-dim)">You chose the Hermes version for this change. <button class="btn-ghost cm-decide" data-name="${esc(m.name)}" data-decision="reenable" style="margin-left:6px;padding:3px 10px;font-size:11px">Re-enable ours</button></div>`;
    }
    return `<div class="agentic-row" style="margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div><b>${esc(m.name)}</b> <span style="color:var(--text-faint);font-size:11px;font-family:var(--font-mono)">· ${esc(m.file)}</span></div>
        <span style="color:${_cmColor(m.status)};font-weight:700;font-size:11px;font-family:var(--font-mono)">${esc(m.status)}</span>
      </div>
      <div style="color:var(--text-dim);font-size:12px;margin-top:4px">${esc(m.description)}</div>${actions}
    </div>`;
  }).join('');
  const nConflict = cm.filter(m => m.status === 'CONFLICT').length;
  const hdr = nConflict ? `<span style="color:var(--red)">${nConflict} need your decision</span>` : `<span style="color:var(--green)">all intact</span>`;
  return `<div class="panel" style="margin-top:14px"><div class="panel-header"><span class="panel-title">Core Hermes Modifications</span><span style="font-size:12px">${hdr}</span></div>
    <div style="padding:10px 16px 4px;color:var(--text-dim);font-size:12px">Our changes to Hermes' own source, re-applied automatically after each update — unless an update conflicts, then you decide here.</div>
    <div style="padding:8px 16px 14px">${cards}</div></div>`;
}
async function decideCoremod(name, decision, el) {
  if (decision === 'accept_upstream' && !confirm('Drop our change and keep the Hermes version? This can disable functionality we built.')) return;
  if (el) { el.disabled = true; el.textContent = 'Working…'; }
  try { await api('POST', '/api/coremods/decide', { name, decision }); }
  catch (e) { toast('Failed: ' + e, 'err'); }
  guardianState.fetched = false; loadGuardian();
}
function bindGuardian() {
  const b = document.getElementById('guardianRefresh');
  if (b) b.onclick = () => { guardianState.fetched = false; loadGuardian(); };
  document.querySelectorAll('.cm-decide').forEach(el => {
    el.onclick = () => decideCoremod(el.getAttribute('data-name'), el.getAttribute('data-decision'), el);
  });
}

// ═══════════════════════════════ MEMORY HUB ═══════════════════════════════
const memoryState = { data: null, loading: false, fetched: false, tab: 'semantic', search: '', agentSel: null, agentMem: null, scopeFilter: '' };
async function loadMemory() {
  if (memoryState.loading) return;
  memoryState.loading = true; render();
  try { memoryState.data = await api('GET', '/api/memory'); }
  catch (e) { memoryState.data = { error: String(e) }; }
  memoryState.loading = false; memoryState.fetched = true; render(); bindMemory();
}

function memBadge(label, val, color) {
  return val ? `<span class="chip" style="color:${color};border-color:${color}44;background:${color}14">${label}: ${esc(val)}</span>` : '';
}

function memSemanticHTML() {
  const d = memoryState.data || {};
  if (d.error) return `<div class="empty">${esc(d.error)}</div>`;
  const q = memoryState.search.toLowerCase();
  const mems = (d.memories || []).filter(m => !q || (m.memory || '').toLowerCase().includes(q));
  const scopeRows = Object.entries(d.agents || {}).map(([k, v]) => `<span class="chip c-accent">${esc(k)}: ${v}</span>`).join(' ') || '<span class="muted">none</span>';
  const cards = mems.map(m => `
    <div class="mem-card">
      <div>${esc(m.memory)}</div>
      <div class="mc-badges">
        ${memBadge('agent', m.agent_id, '#b3a1ff')}${memBadge('user', m.user_id, '#60a5fa')}${memBadge('channel', m.channel, '#4ade80')}${memBadge('from', m.attributed_to, '#fb923c')}
      </div>
      <div class="mc-meta" style="display:flex;align-items:center;gap:8px">
        <span style="flex:1">${esc((m.updated_at || m.created_at || '').replace('T', ' ').slice(0, 19))} · vector ${m.vector_dims || '?'}-dim · id ${esc((m.id || '').slice(0, 8))}</span>
        <button class="btn-icon" title="Edit / merge / delete" onclick="memCardEdit('${esc(String(m.id))}')">✏️</button>
      </div>
    </div>`).join('') || `<div class="empty"><span class="e-ico">◍</span>No semantic memories${q ? ` matching "${esc(memoryState.search)}"` : ' yet — they accumulate as you work with Hermes'}.</div>`;
  return `
    <div class="stats-strip">
      <div class="stat-card"><div class="stat-num" style="color:#b3a1ff">${d.count || 0}</div><div class="stat-label">Memories</div></div>
      <div class="stat-card blue"><div class="stat-num" style="color:var(--blue)">${Object.keys(d.agents || {}).length}</div><div class="stat-label">Scopes</div></div>
      <div class="stat-card green"><div class="stat-num green">${d.vector_dims || '?'}</div><div class="stat-label">Vector dims (${esc(d.vector_distance || 'cosine')})</div></div>
    </div>
    <div class="scope-row">${scopeRows}<button class="btn-ghost" id="memRefresh" style="margin-left:auto">↻ Refresh</button></div>
    <div class="search-bar"><input id="memSearch" type="search" placeholder="Search memories…" value="${esc(memoryState.search)}"></div>
    <div class="mem-grid" id="memCards">${cards}</div>`;
}

function memAgentHTML() {
  if (!isAdminUser()) return '<div class="empty"><span class="e-ico">🔒</span>Per-agent memory is admin-only.</div>';
  const agents = state.agents || [];
  if (!agents.length) return '<div class="empty"><span class="e-ico">◉</span>No agents to inspect.</div>';
  const sel = memoryState.agentSel || agents[0].id;
  memoryState.agentSel = sel;
  const mem = memoryState.agentMem;
  const scopeChips = ['', ...MEM_SCOPES].map(s =>
    `<button class="subtab ${memoryState.scopeFilter === s ? 'active' : ''}" data-scope="${s}" style="padding:5px 13px;font-size:11px">${s || 'all scopes'}</button>`).join('');
  let list = '<div class="loading">Loading…</div>';
  if (mem) {
    const rows = mem.filter(m => !memoryState.scopeFilter || m.scope === memoryState.scopeFilter);
    list = rows.map(m => `
      <div class="mem-card">
        <div>${esc(m.content)}</div>
        <div class="mc-badges">
          <span class="chip ${{ stm: 'c-blue', lts: 'c-accent', experience: 'c-cyan', longterm: 'c-green' }[m.scope] || 'c-accent'}">${esc(m.scope)}</span>
          ${m.kind ? `<span class="chip">${esc(m.kind)}</span>` : ''}
          ${m.source ? `<span class="chip">${esc(m.source)}</span>` : ''}
        </div>
        <div class="mc-meta">${fmtAgo(m.created_at)} · ${esc(m.id)}</div>
      </div>`).join('') || '<div class="empty"><span class="e-ico">◍</span>This agent has no memories in this scope yet.</div>';
  }
  return `
    <div class="scope-row">
      <select class="k-filter" id="memAgentSel">${agents.map(a => `<option value="${esc(a.id)}" ${sel === a.id ? 'selected' : ''}>${esc(a.name)}</option>`).join('')}</select>
      ${scopeChips}
      <button class="btn-ghost" style="margin-left:auto" onclick="openAgentDrawer('${esc(sel)}','memory')">Open in agent drawer →</button>
    </div>
    <div class="view-intro">Working memory of the selected runtime agent: <b>stm</b> (short-term scratch), <b>lts</b> (long-term summary), <b>experience</b> (task lessons), <b>longterm</b> (durable facts).</div>
    <div class="mem-grid">${list}</div>`;
}

function memLessonsHTML() {
  const d = specialistsState.data;
  if (!d || !d.specialists) {
    if (!specialistsState.loading) loadSpecialists();
    return '<div class="loading">Loading specialist lessons…</div>';
  }
  const specs = (d.specialists || []).filter(s => (s.memories || []).length);
  if (!specs.length) return '<div class="empty"><span class="e-ico">🎓</span>No specialist has learned a lesson yet. Lessons appear after tasks run — review them in the Specialists tab.</div>';
  return specs.map(s => `
    <h3 class="section-title">${esc(s.name)} <span class="muted">(${(s.memories || []).length} lessons)</span></h3>
    <div class="mem-grid" style="margin-bottom:10px">
      ${(s.memories || []).map(m => `
        <div class="mem-card">
          <div>${esc(m.memory)}</div>
          <div class="mc-meta">${esc((m.created_at || '').replace('T', ' ').slice(0, 16))}${m.source ? ' · ' + esc(m.source) : ''}</div>
        </div>`).join('')}
    </div>`).join('');
}

function memSharedHTML() {
  const shared = specialistsState.shared;
  if (shared == null) {
    if (!specialistsState.loading) loadSpecialists();
    return '<div class="loading">Loading shared context…</div>';
  }
  const rows = (shared || []).map(m => `
    <div class="mem-card" style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start">
      <div>${esc(m.memory)}</div>
      <button class="btn-icon shared-del" data-id="${esc(m.id)}" title="Remove">✕</button>
    </div>`).join('') || '<div class="empty"><span class="e-ico">🌐</span>No shared context yet — add facts every specialist should know.</div>';
  return `
    <div class="view-intro">Cross-cutting facts that <b>all</b> specialists read on every task — separate from any one specialist's private lessons.</div>
    <div class="mem-grid">${rows}</div>
    <div style="margin-top:14px;display:flex;gap:8px">
      <input class="form-input" id="sharedText" placeholder="Add a shared fact…" style="flex:1">
      <button class="btn-primary" id="sharedAdd">Add</button>
    </div>`;
}

function viewMemory() {
  const d = memoryState.data;
  if (memoryState.tab === 'semantic' && !memoryState.fetched && !memoryState.loading) loadMemory();
  if (memoryState.tab === 'semantic' && (memoryState.loading || !d)) return skeletonView();
  const semCount = ((memoryState.data || {}).count) || 0;
  const lessonCount = ((specialistsState.data || {}).specialists || []).reduce((n, s) => n + (s.memory_count || 0), 0);
  const sharedCount = (specialistsState.shared || []).length;
  const tabs = [
    ['map3d', '🧠 3D Map', null],
    ['semantic', `Semantic (mem0)`, semCount],
    ['agent', 'Agent memory', null],
    ['lessons', 'Specialist lessons', lessonCount || null],
    ['shared', 'Shared context', sharedCount || null],
  ];
  let body = '';
  if (memoryState.tab === 'map3d') body = mem3dHTML();
  else if (memoryState.tab === 'semantic') body = memSemanticHTML();
  else if (memoryState.tab === 'agent') body = memAgentHTML();
  else if (memoryState.tab === 'lessons') body = memLessonsHTML();
  else if (memoryState.tab === 'shared') body = memSharedHTML();
  return `
    <div class="subtabs">
      ${tabs.map(([id, label, n]) => `<button class="subtab ${memoryState.tab === id ? 'active' : ''}" data-memtab="${id}">${label}${n != null ? `<span class="n">${n}</span>` : ''}</button>`).join('')}
    </div>
    <div id="memTabBody">${body}</div>`;
}

async function loadAgentMemoryTab() {
  memoryState.agentMem = null;
  const id = memoryState.agentSel;
  if (!id || !isAdminUser()) return;  // admin-gated — the tab shows a 🔒 note instead (F103)
  try {
    const r = await api('GET', `/api/agents/${id}/memory?limit=100`);
    memoryState.agentMem = r.memory || [];
  } catch { memoryState.agentMem = []; }
  if (currentView === 'memory' && memoryState.tab === 'agent') { render(); }
}

function mem3dHTML() {
  return `
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:10px;flex-wrap:wrap">
      <div class="view-intro" style="flex:1;min-width:320px;margin:0">Your agent's mind, spatially: every point is a real memory at its true position in mem0's 768-dimensional vector space. The floating labels are <strong>semantic regions</strong> — named by their own most distinctive words, computed, not written by anyone. <strong>Drag</strong> orbit · <strong>scroll</strong> zoom · <strong>hover</strong> for the record · <strong>click</strong> a star to edit, merge or delete it.</div>
      <input class="form-input" id="mem3dSearch" placeholder="🔍 light up memories about…" style="width:250px">
      <span id="mem3dStats" style="font-family:var(--font-mono);font-size:10.5px;color:var(--text-dim);white-space:nowrap"></span>
    </div>
    <div id="mem3dStage" style="position:relative;height:calc(100vh - 258px);min-height:600px;border-radius:14px;border:1px solid rgba(124,92,255,.18);background:#07070d;overflow:hidden">
      <div class="loading" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center">Projecting 768-dim memory space…</div>
    </div>`;
}

async function mountMem3d() {
  const stage = document.getElementById('mem3dStage');
  if (!stage) return;
  try {
    const data = await api('GET', '/api/memory3d');
    if (!document.getElementById('mem3dStage')) return; // user navigated away
    if (!data.nodes || !data.nodes.length) {
      stage.innerHTML = '<div class="empty" style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center"><span class="e-ico">🧠</span>No semantic memories yet — they appear as agents work and learn.</div>';
      return;
    }
    stage.innerHTML = '';
    if (window.Memory3D) window.Memory3D.mount(stage, data, { onSelect: openMemoryNodeModal });
    const stats = document.getElementById('mem3dStats');
    if (stats) stats.textContent =
      `${data.count} memories · ${data.links.length} associations · ${(data.clusters || []).length} regions · 768-D live`;
    const inp = document.getElementById('mem3dSearch');
    if (inp) inp.oninput = () => {
      const n = window.Memory3D.search(inp.value);
      if (stats) stats.textContent = inp.value.trim()
        ? `${n} of ${data.count} memories match · ${data.links.length} associations`
        : `${data.count} memories · ${data.links.length} associations · ${(data.clusters || []).length} regions · 768-D live`;
    };
  } catch (e) {
    stage.innerHTML = `<div class="empty" style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center"><span class="e-ico">⚠️</span>${esc(e.message)}</div>`;
  }
}

function bindMemory() {
  if (memoryState.tab === 'map3d') mountMem3d();
  else if (window.Memory3D) window.Memory3D.dispose();
  $$('[data-memtab]').forEach(el => {
    el.onclick = () => {
      memoryState.tab = el.dataset.memtab;
      if (memoryState.tab === 'agent' && memoryState.agentMem == null) loadAgentMemoryTab();
      render();
    };
  });
  const b = document.getElementById('memRefresh');
  if (b) b.onclick = () => { memoryState.fetched = false; loadMemory(); };
  const s = document.getElementById('memSearch');
  if (s) s.oninput = (e) => {
    memoryState.search = e.target.value;
    const grid = document.getElementById('memCards');
    if (grid) {
      const html = memSemanticHTML();
      const tmp = document.createElement('div'); tmp.innerHTML = html;
      const newGrid = tmp.querySelector('#memCards');
      if (newGrid) grid.innerHTML = newGrid.innerHTML;
    }
  };
  const sel = document.getElementById('memAgentSel');
  if (sel) sel.onchange = (e) => { memoryState.agentSel = e.target.value; memoryState.agentMem = null; loadAgentMemoryTab(); render(); };
  $$('[data-scope]').forEach(el => {
    el.onclick = () => { memoryState.scopeFilter = el.dataset.scope; render(); };
  });
  const sa = document.getElementById('sharedAdd');
  if (sa) sa.onclick = () => addSharedContext();
  document.querySelectorAll('.shared-del').forEach(el => {
    el.onclick = () => deleteSharedContext(el.getAttribute('data-id'));
  });
}

// ═══════ Galaxy memory editing (SPEC-BLOCK2 R2): edit / merge / delete, confirm-gated ═══════
let _memMerge = null;

function memCardEdit(id) {
  const m = ((memoryState.data || {}).memories || []).find(x => String(x.id) === String(id));
  if (m) openMemoryNodeModal(m);
}

function openMemoryNodeModal(node) {
  // accepts BOTH shapes: a galaxy node ({id,text,agent,user,...}) and a
  // semantic-list row ({id,memory,agent_id,metadata:{user},...})
  const m = {
    id: String(node.id),
    text: node.text ?? node.memory ?? '',
    agent: node.agent ?? node.agent_id,
    user: node.user ?? ((node.metadata || {}).user),
    channel: node.channel,
    created_at: node.created_at,
  };
  showModal(`
    <h2>🧠 Memory</h2>
    <div class="view-intro">Saving re-embeds the text — the star moves to where its new meaning lives. ${m.user ? '' : '<b>This is a SHARED memory</b> — every user reads it; only admins can change it.'}</div>
    <div class="form-group"><label class="form-label">Text</label>
      <textarea class="form-input" id="memEditText" rows="6" style="font-size:13px;line-height:1.5">${esc(m.text)}</textarea></div>
    <div class="mc-badges" style="margin-bottom:8px">
      ${memBadge('agent', m.agent, '#b3a1ff')}${memBadge('user tag', m.user || 'shared', '#60a5fa')}${memBadge('channel', m.channel, '#4ade80')}
    </div>
    <div class="mc-meta">id ${esc(m.id)} · stored ${esc(String(m.created_at || '?').replace('T', ' ').slice(0, 19))}</div>
    <div class="modal-actions" style="justify-content:space-between">
      <button class="btn-sm danger" onclick="memDeleteUI('${esc(m.id)}')">🗑 Delete</button>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn-ghost" onclick="memMergeUI('${esc(m.id)}')">⧉ Merge with…</button>
        <button class="btn-ghost" onclick="closeModal()">Cancel</button>
        <button class="btn-primary" onclick="memSaveUI('${esc(m.id)}')">💾 Save changes</button>
      </div>
    </div>`);
}

async function memSaveUI(id) {
  const text = (document.getElementById('memEditText')?.value || '').trim();
  if (!text) { toast('The text cannot be empty — use Delete to remove a memory', 'err'); return; }
  if (!confirm('Rewrite this memory? It is re-embedded and recalled in its new form from now on.')) return;
  try {
    await api('PATCH', `/api/memory/${encodeURIComponent(id)}`, { text });
    toast('Memory updated', 'ok');
    closeModal();
    memAfterChange();
  } catch (e) { toast('Update failed: ' + e.message, 'err'); }
}

async function memDeleteUI(id) {
  if (!confirm('Delete this memory permanently? Agents stop recalling it immediately.')) return;
  try {
    await api('DELETE', `/api/memory/${encodeURIComponent(id)}`);
    toast('Memory deleted', 'ok');
    closeModal();
    memAfterChange();
  } catch (e) { toast('Delete failed: ' + e.message, 'err'); }
}

async function memMergeUI(id) {
  let d;
  try { d = await api('GET', '/api/memory'); }
  catch (e) { toast('Could not load memories: ' + e.message, 'err'); return; }
  const all = d.memories || [];
  const src = all.find(m => String(m.id) === String(id));
  if (!src) { toast('Source memory not found', 'err'); return; }
  _memMerge = { id: String(id), src, all: all.filter(m => String(m.id) !== String(id)), sel: new Set(), q: '' };
  renderMemMerge();
}

function memMergeListHTML() {
  const { all, sel, q } = _memMerge;
  return all
    .filter(m => !q || (m.memory || '').toLowerCase().includes(q))
    .slice(0, 80)
    .map(m => `
      <label class="mem-merge-row">
        <input type="checkbox" ${sel.has(String(m.id)) ? 'checked' : ''} onchange="memMergeToggle('${esc(String(m.id))}')">
        <span>${esc((m.memory || '').slice(0, 180))}</span>
      </label>`).join('') || '<div class="empty">Nothing matches.</div>';
}

function renderMemMerge() {
  const { src, sel } = _memMerge;
  showModal(`
    <h2>⧉ Merge memories</h2>
    <div class="view-intro">Fold duplicates or fragments into ONE memory. You edit the merged text before anything is written — the sources are deleted only AFTER the merged memory is stored.</div>
    <div class="mem-card" style="margin-bottom:8px"><b style="font-size:11px;color:var(--text-dim)">MERGING INTO THIS:</b><div>${esc((src.memory || '').slice(0, 240))}</div></div>
    <div class="search-bar"><input type="search" id="memMergeSearch" placeholder="Filter memories…" value="${esc(_memMerge.q)}"></div>
    <div class="mem-merge-list" id="memMergeList">${memMergeListHTML()}</div>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" id="memMergeGo" onclick="memMergePreview()" ${sel.size ? '' : 'disabled'}>Preview merged text (${sel.size + 1})</button>
    </div>`);
  const s = document.getElementById('memMergeSearch');
  if (s) s.oninput = () => {
    _memMerge.q = s.value.toLowerCase();
    const list = document.getElementById('memMergeList');
    if (list) list.innerHTML = memMergeListHTML();
  };
}

function memMergeToggle(id) {
  const s = _memMerge.sel;
  s.has(id) ? s.delete(id) : s.add(id);
  const b = document.getElementById('memMergeGo');
  if (b) { b.disabled = !s.size; b.textContent = `Preview merged text (${s.size + 1})`; }
}

function memMergePreview() {
  const { src, all, sel } = _memMerge;
  if (!sel.size) return;
  if (sel.size + 1 > 8) { toast('Merge at most 8 memories at once', 'err'); return; }
  const chosen = all.filter(m => sel.has(String(m.id)));
  const text = [src, ...chosen].map(m => (m.memory || '').trim()).filter(Boolean).join('\n');
  showModal(`
    <h2>⧉ Merge ${chosen.length + 1} memories into one</h2>
    <div class="view-intro">This text becomes ONE new memory (re-embedded); the ${chosen.length + 1} sources are then deleted. Edit it into a single clean statement — the system never invents content for you.</div>
    <textarea class="form-input" id="memMergeText" rows="9" style="font-size:13px;line-height:1.5">${esc(text)}</textarea>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="renderMemMerge()">← Back to selection</button>
      <button class="btn-primary" onclick="memMergeConfirm()">✓ Merge & delete ${chosen.length + 1} sources</button>
    </div>`);
}

async function memMergeConfirm() {
  const ids = [_memMerge.id, ..._memMerge.sel];
  const text = (document.getElementById('memMergeText')?.value || '').trim();
  if (!text) { toast('The merged text cannot be empty', 'err'); return; }
  if (!confirm(`Merge ${ids.length} memories into one and DELETE the sources? This cannot be undone.`)) return;
  try {
    const r = await api('POST', '/api/memory/merge', { ids, text });
    toast((r.failed || []).length
      ? `Merged, but ${r.failed.length} source(s) could not be deleted — check the memory list`
      : `Merged ${ids.length} memories into one`, (r.failed || []).length ? 'err' : 'ok');
    closeModal();
    memAfterChange();
  } catch (e) { toast('Merge failed: ' + e.message, 'err'); }
}

function memAfterChange() {
  memoryState.fetched = false;
  if (currentView === 'memory') {
    loadMemory(); // re-renders the active subtab; map3d remounts via bindMemory
  } else if (currentView === 'dashboard') {
    mountDashGalaxy(0); // the server cleared its galaxy cache — refetch
  }
}

// ═══════════════════════════════ OBSERVABILITY ═══════════════════════════════
const obsState = { data: null, loading: false, fetched: false, chart: null };
async function loadObservability() {
  if (obsState.loading) return;
  obsState.loading = true; render();
  try { obsState.data = await api('GET', '/api/observability?days=30'); }
  catch (e) { obsState.data = { error: String(e) }; }
  obsState.loading = false; obsState.fetched = true; render(); bindObservability();
}
function viewObservability() {
  const d = obsState.data;
  if (!obsState.fetched && !obsState.loading) { loadObservability(); }
  if (obsState.loading || !d) return skeletonView();
  const url = (d && d.langfuse_url) || 'http://localhost:3000';
  const openBtn = `<a class="btn-primary" href="${esc(url)}" target="_blank" rel="noopener">Open Langfuse ↗</a>`;
  if (d.configured === false) {
    return `<div class="panel"><div class="empty"><span class="e-ico">⊙</span>Langfuse credentials not found. Set HERMES_LANGFUSE_PUBLIC_KEY / _SECRET_KEY / _BASE_URL in ~/.hermes/.env.</div></div>`;
  }
  if (d.error) {
    return `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <div class="muted">Langfuse unreachable — is the stack running? (docker compose up -d in ~/langfuse)</div>${openBtn}</div>
      <div class="panel"><div class="empty">${esc(d.error)}</div></div>`;
  }
  const t = d.totals || {};
  const cost = (v) => '$' + (Number(v || 0)).toFixed(4);
  const num = (v) => (Number(v || 0)).toLocaleString();
  const rows = (d.models || []).map(m => `<tr>
      <td><code>${esc(m.model)}</code></td><td>${num(m.total)}</td><td>${num(m.input)}</td><td>${num(m.output)}</td><td>${cost(m.cost)}</td>
    </tr>`).join('') || `<tr><td colspan="5" style="color:var(--text-dim)">No LLM usage recorded yet — run a Hermes turn.</td></tr>`;
  return `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div class="muted">Live LLM traces, tokens &amp; cost — captured from Hermes via self-hosted Langfuse (last 30 days)</div>
      ${openBtn}
    </div>
    <div class="stats-strip">
      <div class="stat-card"><div class="stat-num" style="color:#b3a1ff">${cost(t.cost)}</div><div class="stat-label">Est. Cost (30d)</div></div>
      <div class="stat-card green"><div class="stat-num green">${num(t.tokens)}</div><div class="stat-label">Total Tokens</div></div>
      <div class="stat-card blue"><div class="stat-num" style="color:var(--blue)">${num(t.traces)}</div><div class="stat-label">Turns Traced</div></div>
      <div class="stat-card orange"><div class="stat-num" style="color:var(--orange)">${num(t.observations)}</div><div class="stat-label">LLM Calls</div></div>
    </div>
    <div class="panel" style="margin-top:4px">
      <div class="panel-header"><span class="panel-title">Daily Cost</span></div>
      <div style="padding:14px;height:210px"><canvas id="obsChart"></canvas></div>
    </div>
    <div class="panel" style="margin-top:14px">
      <div class="panel-header"><span class="panel-title">By Model</span></div>
      <table class="data-table"><thead><tr><th>Model</th><th>Tokens</th><th>Input</th><th>Output</th><th>Cost</th></tr></thead>
      <tbody>${rows}</tbody></table>
    </div>`;
}
function bindObservability() {
  const d = obsState.data;
  if (!d || !d.daily || !d.daily.length || !window.Chart) return;
  const cv = document.getElementById('obsChart');
  if (!cv) return;
  if (obsState.chart) { try { obsState.chart.destroy(); } catch { /* gone */ } }
  obsState.chart = new Chart(cv, {
    type: 'line',
    data: {
      labels: d.daily.map(x => x.date), datasets: [{
        label: 'Cost ($)', data: d.daily.map(x => x.cost),
        borderColor: '#7c5cff', backgroundColor: 'rgba(124,92,255,0.14)', fill: true, tension: 0.3, pointRadius: 2,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: { grid: { display: false } }, y: {} }
    },
  });
}

// ═══════════════════════════════ USAGE ═══════════════════════════════
const usageState = { data: null, loading: false, fetched: false, chart: null };
async function loadUsage() {
  if (usageState.loading) return;
  usageState.loading = true; usageState.data = null; render();
  try { usageState.data = await api('GET', '/api/usage'); }
  catch { usageState.data = null; }
  usageState.loading = false; usageState.fetched = true; render(); bindUsage();
}
function viewUsage() {
  if (!usageState.fetched) { loadUsage(); return skeletonView(); }
  if (usageState.loading) return skeletonView();
  const d = usageState.data;
  if (!d) return `<div class="empty"><span class="e-ico">◈</span>Unable to load usage data.</div>`;
  const t = d.totals;
  const fmtT = n => n > 1e9 ? (n / 1e9).toFixed(2) + 'B' : n > 1e6 ? (n / 1e6).toFixed(1) + 'M' : n > 1e3 ? (n / 1e3).toFixed(0) + 'K' : n;
  let html = `
    <div class="stats-strip">
      <div class="stat-card"><div class="stat-num" style="color:#b3a1ff">$${t.est_cost_usd.toFixed(2)}</div><div class="stat-label">Est. Total Cost</div></div>
      <div class="stat-card blue"><div class="stat-num" style="color:var(--blue)">${t.sessions}</div><div class="stat-label">Sessions</div></div>
      <div class="stat-card green"><div class="stat-num" style="color:var(--accent-2)">${fmtT(t.total_tokens)}</div><div class="stat-label">Total Tokens</div></div>
    </div>`;
  html += `<h3 class="section-title">By Provider</h3><div class="tool-grid">`;
  for (const p of d.providers) {
    const inOut = p.input_tokens + p.output_tokens;
    const totalInOut = d.providers.reduce((a, x) => a + x.input_tokens + x.output_tokens, 0);
    const share = totalInOut ? Math.round(inOut / totalInOut * 100) : 0;
    html += `
      <div class="tool-card" style="--tool-color:var(--accent)">
        <div class="tool-header"><span class="tool-icon">⚙</span><div class="tool-name">${esc(p.name)}</div></div>
        <div class="stat-pair"><span>$${p.est_cost_usd.toFixed(2)}</span><span class="muted">${p.sessions} sessions</span></div>
        <div class="stat-pair"><span class="muted">in: ${fmtT(p.input_tokens)}</span><span class="muted">out: ${fmtT(p.output_tokens)}</span></div>
        ${p.cache_read_tokens ? `<div class="stat-pair"><span class="muted">cache read: ${fmtT(p.cache_read_tokens)}</span><span class="muted">${share}% share</span></div>` : ''}
      </div>`;
  }
  html += `</div>`;
  html += `<h3 class="section-title">14-Day Token Trend</h3><div class="chart-wrap"><canvas id="usageChart"></canvas></div>`;
  const models = Object.entries(d.per_model || {}).sort((a, b) => (b[1].in + b[1].out) - (a[1].in + a[1].out));
  if (models.length) {
    html += `<h3 class="section-title">By Model</h3><div class="panel"><table class="data-table"><thead><tr><th>Model</th><th>Input</th><th>Output</th><th>Calls</th><th>Cost</th></tr></thead><tbody>`;
    for (const [m, v] of models) {
      html += `<tr><td><code>${esc(m)}</code></td><td>${fmtT(v.in)}</td><td>${fmtT(v.out)}</td><td>${v.count}</td><td>$${v.cost.toFixed(2)}</td></tr>`;
    }
    html += `</tbody></table></div>`;
  }
  if (d.top_projects && d.top_projects.length) {
    const maxTok = d.top_projects[0].tokens;
    html += `<h3 class="section-title">Top Projects by Tokens</h3>`;
    for (const tp of d.top_projects) {
      const pct = Math.round(tp.tokens / maxTok * 100);
      html += `<div class="proj-bar"><span class="proj-bar-name">${esc(tp.project)}</span>
        <div class="proj-bar-track"><div class="proj-bar-fill" style="width:${pct}%"></div></div>
        <span class="proj-bar-val">${fmtT(tp.tokens)}</span></div>`;
    }
  }
  html += `<p class="muted" style="margin-top:16px">Costs are estimates from local transcript token counts × price table. Cache reads billed at 10% input rate; cache creation at 125%. Data cached ${d.cache_ttl}s. <button class="btn-link" id="usageRefresh">↻ Refresh now</button></p>`;
  return html;
}
function bindUsage() {
  const cv = $('#usageChart');
  if (cv && usageState.data && (usageState.data.timeseries || []).length) {
    renderUsageChart(cv, usageState.data);
  }
  const ref = $('#usageRefresh');
  if (ref) ref.onclick = () => { usageState.fetched = false; loadUsage(); };
}
function renderUsageChart(canvas, d) {
  const ctx = canvas.getContext('2d');
  const labels = d.timeseries.map(t => t.day.slice(5));
  const modelNames = [...new Set(d.timeseries.flatMap(t => Object.keys(t.models)))];
  const palette = ['rgba(124,92,255,0.85)', 'rgba(94,234,212,0.85)', 'rgba(245,158,11,0.85)', 'rgba(34,197,94,0.85)', 'rgba(239,68,68,0.85)'];
  const datasets = modelNames.map((m, i) => ({
    label: m, data: d.timeseries.map(t => Math.round((t.models[m] || 0) / 1000)),
    backgroundColor: palette[i % palette.length], borderColor: palette[i % palette.length].replace('0.85', '1'),
    borderWidth: 1, stack: 'stack0', borderRadius: 3,
  }));
  if (usageState.chart) usageState.chart.destroy();
  usageState.chart = new Chart(ctx, {
    type: 'bar', data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, title: { display: true, text: 'Tokens (K)', color: '#9a9ab2' } } },
      plugins: { legend: { labels: { color: '#eaeaf4' } } }
    }
  });
}

// ═══════════════════════════════ AGENTIC CAPABILITIES ═══════════════════════════════
function viewAgentic() {
  const runs = state.verifyRuns || [];
  const appr = state.approvals || [];
  const jobs = state.schedulerJobs || [];
  const wd = state.watchdog || {};
  const wdcfg = wd.config || {};
  const wdacts = wd.recent_actions || [];
  const agents = state.agents || [];

  const apprHtml = appr.length ? appr.map(a => {
    let payload = {};
    try { payload = JSON.parse(a.payload || '{}') || {}; } catch { /* generic approval */ }
    const taskId = payload.task_id || null;
    const task = taskId ? (state.tasks || []).find(t => t.id === taskId) : null;
    const judgeChip = task && { SHIP: 'c-green', REVISE: 'c-orange', REWRITE: 'c-red' }[task.judge_verdict];
    const isSR = a.action_type === 'super_result';
    const srChips = isSR ? `
        <span class="chip c-accent">✨ round ${payload.round || '?'}</span>
        <span class="chip c-orange">${payload.findings ?? '?'} finding(s)</span>
        ${payload.verdict ? `<span class="chip ${{ SHIP: 'c-green', REVISE: 'c-orange', REWRITE: 'c-red' }[payload.verdict] || 'c-red'}">${esc(payload.verdict)}</span>` : ''}` : '';
    return `
    <div class="agentic-row">
      <div><strong>${isSR ? '✨ Super Result checkpoint' : esc(a.action_type)}</strong> <span style="color:var(--text-dim)">— ${esc(a.description || '')}</span>
        ${srChips}
        ${judgeChip ? `<span class="chip ${judgeChip}" title="frontier judge verdict">${esc(task.judge_verdict)}</span>` : ''}</div>
      <div style="font-size:11px;color:var(--text-dim);font-family:var(--font-mono)">${esc(a.agent_id || 'system')} · risk: ${esc(a.risk_level)} · ${fmtAgo(a.requested_at)}</div>
      ${taskId ? `<div style="font-size:11.5px;color:var(--text-dim)">${isSR
        ? 'Review/edit the 🤖 critic comments in the task\'s review first — <strong>Reject</strong> reworks with them, <strong>Approve</strong> accepts this version.'
        : 'Check it first: deliverable files, self-score, judge report → <strong>Open deliverable</strong>. Then decide here.'}</div>` : ''}
      <div class="row-actions">
        ${taskId ? `<button class="btn-sm" onclick="openApprovalTask('${esc(taskId)}')">📄 Open deliverable</button>` : ''}
        <button class="btn-primary sm" onclick="decideApproval('${esc(a.id)}','approved')">Approve</button>
        <button class="btn-danger sm" onclick="decideApproval('${esc(a.id)}','rejected')">Reject</button>
      </div>
    </div>`;
  }).join('') : '<div class="empty"><span class="e-ico">⏵</span>No pending approvals — agents will queue risky actions here for your sign-off.</div>';

  const runsHtml = runs.length ? runs.map(r => `
    <div class="agentic-row">
      <div><span class="vs-dot ${r.passed ? 'pass' : 'fail'}"></span><code style="font-size:11px">${esc((r.command || '').slice(0, 50))}</code></div>
      <div style="font-size:11px;color:var(--text-dim);font-family:var(--font-mono)">${esc(r.kind)} · exit ${r.exit_code} · ${r.duration_ms}ms · ${fmtAgo(r.ts)}</div>
    </div>`).join('') : '<div class="empty"><span class="e-ico">✓</span>No verify runs yet</div>';

  const jobsHtml = jobs.length ? jobs.map(j => `
    <div class="agentic-row">
      <div><strong>${esc(j.name)}</strong> <code style="font-size:11px;color:var(--accent-2)">${esc(j.cron_expr)}</code>
        ${j.enabled ? '' : '<span style="color:var(--text-faint);font-size:10px">(disabled)</span>'}
      </div>
      <div style="font-size:11px;color:var(--text-dim);font-family:var(--font-mono)">${esc(j.action)} · runs: ${j.run_count} · ${esc(j.last_status || '—')} · next ${fmtAgo(j.next_run)}</div>
      <div class="row-actions">
        <button class="btn-primary sm" onclick="toggleJob('${esc(j.id)}', ${j.enabled ? false : true})">${j.enabled ? 'Disable' : 'Enable'}</button>
        <button class="btn-danger sm" onclick="deleteJob('${esc(j.id)}')">Delete</button>
      </div>
    </div>`).join('') : '<div class="empty"><span class="e-ico">⚙</span>No scheduled jobs</div>';

  const actsHtml = wdacts.length ? wdacts.slice(0, 8).map(a => `
    <div class="agentic-row slim"><span class="log-${esc(a.level)}">[${esc(a.level)}]</span> <span style="font-size:11px;flex:1">${esc(a.message)}</span> <span style="font-size:10px;color:var(--text-faint);font-family:var(--font-mono)">${fmtAgo(a.ts)}</span></div>`).join('') : '<div class="empty">Watchdog idle — nothing needed healing.</div>';

  const maxTok = Math.max(1, ...agents.map(a => (a.tokens_in || 0) + (a.tokens_out || 0)));
  const costRows = agents.map(a => {
    const tot = (a.tokens_in || 0) + (a.tokens_out || 0);
    const usd = ((tot / 1e6) * 2.0).toFixed(4);
    const pct = Math.round(tot / maxTok * 100);
    return `<div class="agentic-row slim">
      <span style="font-size:11px;min-width:110px">${esc(a.name)}</span>
      <div class="cap-bar"><div class="cap-fill ${pct > 85 ? 'hot' : ''}" style="width:${pct}%"></div></div>
      <span style="font-size:11px;color:var(--text-dim);font-family:var(--font-mono)">${fmtTokens(tot)} tok</span>
      <span style="font-size:11px;color:var(--green);font-family:var(--font-mono)">$${usd}</span>
      <span class="agent-status ${esc(a.status)}">${esc(a.status)}</span>
    </div>`;
  }).join('');

  const admin = isAdminUser();
  // F103: watchdog / verify runs / scheduler are admin-gated server-side —
  // members get one quiet note instead of three cards full of 403s.
  const adminCards = admin ? `
      <div class="agentic-card">
        <div class="card-head"><h3>🛡 Self-Healing Watchdog</h3><button class="btn-sm" onclick="showWatchdogModal()">⚙ Configure</button></div>
        <div class="card-body">
          <div class="wd-config">
            <div class="wc-item"><div class="wc-label">Check interval</div><div class="wc-val">${wdcfg.interval_s || '—'}s</div></div>
            <div class="wc-item"><div class="wc-label">Stale after</div><div class="wc-val">${wdcfg.stale_threshold_s || '—'}s</div></div>
            <div class="wc-item"><div class="wc-label">Restart dead</div><div class="wc-val" style="color:${wdcfg.restart_on_dead ? 'var(--green)' : 'var(--red)'}">${wdcfg.restart_on_dead ? 'ON' : 'OFF'}</div></div>
            <div class="wc-item"><div class="wc-label">Restart stuck</div><div class="wc-val" style="color:${wdcfg.restart_on_stuck ? 'var(--green)' : 'var(--red)'}">${wdcfg.restart_on_stuck ? 'ON' : 'OFF'}</div></div>
          </div>
          <div style="max-height:150px;overflow-y:auto;display:flex;flex-direction:column;gap:6px">${actsHtml}</div>
        </div>
      </div>
      <div class="agentic-card span2">
        <div class="card-head"><h3>✓ Verify Runs (PEV loop)</h3><button class="btn-primary sm" onclick="showVerifyModal()">+ Run</button></div>
        <div class="card-body" style="max-height:230px;overflow-y:auto">${runsHtml}</div>
      </div>
      <div class="agentic-card">
        <div class="card-head"><h3>⚙ Cron Scheduler</h3><button class="btn-primary sm" onclick="showJobModal()">+ Job</button></div>
        <div class="card-body" style="max-height:230px;overflow-y:auto">${jobsHtml}</div>
      </div>` : `
      <div class="agentic-card">
        <div class="card-head"><h3>🔒 Admin tools</h3></div>
        <div class="card-body"><div class="empty"><span class="e-ico">🔒</span>The watchdog, verify runs and the scheduler are managed by the admin.</div></div>
      </div>`;

  return `
    <div class="agentic-grid">
      <div class="agentic-card span2">
        <div class="card-head"><h3>⏵ Approval Gates</h3><span class="badge-pill">${appr.length}</span></div>
        <div class="card-body">${apprHtml}</div>
      </div>
      ${adminCards}
      <div class="agentic-card span3">
        <div class="card-head"><h3>$ Cost Guardrails</h3><button class="btn-sm" onclick="dispatchSettingsUI()">⚙ Budgets & limits</button><span style="font-size:11px;color:var(--text-dim);font-family:var(--font-mono)">@ \$2/1M tok · bar = share of top spender</span></div>
        <div class="card-body" style="max-height:180px;overflow-y:auto">${costRows || '<div class="empty">No agents</div>'}</div>
      </div>
      <div class="agentic-card span2">
        <div class="card-head"><h3>♥ System Health</h3><span class="badge-pill" style="background:${(state.healthFull || {}).ok ? 'var(--green)' : 'var(--red)'}">${(state.healthFull || {}).ok ? 'ALL OK' : 'ISSUES'}</span></div>
        <div class="card-body">${healthRowsHTML()}</div>
      </div>
      <div class="agentic-card">
        <div class="card-head"><h3>◔ GLM Quota</h3></div>
        <div class="card-body">${quotaCardHTML()}</div>
      </div>
    </div>

    ${admin ? `
    <div class="modal-overlay" id="verifyModal" style="display:none" onclick="if(event.target===this)this.style.display='none'">
      <div class="modal" style="max-width:480px;min-width:420px">
        <h3 style="margin-bottom:14px">Run Verification</h3>
        <input id="vfCmd" class="modal-input" placeholder="command (e.g. bash scripts/verify.sh)" style="width:100%;margin-bottom:8px">
        <select id="vfKind" class="modal-input" style="width:100%;margin-bottom:8px"><option value="static">static</option><option value="runtime">runtime</option></select>
        <input id="vfTask" class="modal-input" placeholder="task_id (optional)" style="width:100%;margin-bottom:8px">
        <div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn-primary" onclick="runVerify()">Run</button></div>
      </div>
    </div>
    <div class="modal-overlay" id="jobModal" style="display:none" onclick="if(event.target===this)this.style.display='none'">
      <div class="modal" style="max-width:480px;min-width:420px">
        <h3 style="margin-bottom:14px">Schedule Job</h3>
        <input id="jbName" class="modal-input" placeholder="job name" style="width:100%;margin-bottom:8px">
        <input id="jbCron" class="modal-input" placeholder="cron (min hr dom mon dow), e.g. */5 * * * *" style="width:100%;margin-bottom:8px">
        <input id="jbAction" class="modal-input" placeholder="action" style="width:100%;margin-bottom:8px">
        <div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn-primary" onclick="createJob()">Create</button></div>
      </div>
    </div>` : ''}
  `;
}

function healthRowsHTML() {
  const checks = (state.healthFull || {}).checks || [];
  if (!checks.length) return '<div class="empty">Health data loading…</div>';
  return checks.map(c => `
    <div class="agentic-row slim">
      <span class="status-dot ${c.ok ? 'online' : ''}" style="background:${c.ok ? 'var(--green)' : 'var(--red)'};box-shadow:0 0 6px ${c.ok ? 'var(--green)' : 'var(--red)'}"></span>
      <span style="font-size:12px;min-width:180px">${esc(c.name)}</span>
      <span style="font-size:11px;color:var(--text-dim);font-family:var(--font-mono);flex:1">${esc(c.detail || '')}</span>
      ${c.ok ? '' : `<code style="font-size:10.5px;color:var(--red);user-select:all" title="copy-paste this to fix">${esc(c.fix)}</code>`}
    </div>`).join('');
}

function quotaCardHTML() {
  const q = state.quota || {};
  const pct = Math.min(100, q.pct_of_daily_cap || 0);
  return `
    <div style="display:flex;flex-direction:column;gap:10px">
      <div class="agentic-row slim">
        <span style="font-size:12px;min-width:130px">Today (real tokens)</span>
        <div class="cap-bar"><div class="cap-fill ${pct > 85 ? 'hot' : ''}" style="width:${pct}%"></div></div>
        <span style="font-size:11px;font-family:var(--font-mono);color:var(--text-dim)">${fmtTokens(q.today_tokens || 0)} / ${fmtTokens(q.daily_cap || 0)}</span>
      </div>
      <div class="agentic-row slim"><span style="font-size:12px;min-width:130px">Dispatches today</span>
        <span style="font-size:11px;font-family:var(--font-mono);color:var(--text-dim)">${q.today_dispatches || 0}</span></div>
      <div class="agentic-row slim"><span style="font-size:12px;min-width:130px">In flight now</span>
        <span style="font-size:11px;font-family:var(--font-mono);color:var(--text-dim)">${Object.entries(q.in_flight || {}).map(([m, n]) => `${m}: ${n}/${q.per_model_cap || 8}`).join(' · ') || 'none'} (total cap ${q.total_cap || 8})</span></div>
      <div class="agentic-row slim"><span style="font-size:12px;min-width:130px">429 backoff</span>
        <span class="chip ${q.backoff_active ? 'c-orange' : 'c-green'}">${q.backoff_active ? `paused ${q.backoff_remaining_s}s (×${q.consecutive_429})` : 'clear'}</span></div>
      <div class="agentic-row slim"><span style="font-size:12px;min-width:130px">Blocked tasks</span>
        <span class="chip ${q.blocked_tasks ? 'c-orange' : 'c-green'}">${q.blocked_tasks || 0}</span></div>
      <div style="font-size:10.5px;color:var(--text-faint)">Z.ai "429 error 1305" bursts = the provider load-shedding at peak — tasks wait as blocked_quota and auto-retry. Not your quota.</div>
    </div>`;
}

function bindAgentic() { /* actions are inline onclick; nothing to bind here */ }

// Jump from an approval row to the full deliverable view (files, self-score,
// judge report, transcript) — refresh tasks first so the modal is current.
async function openApprovalTask(taskId) {
  try {
    state.tasks = await api('GET', '/api/tasks');
    openTaskDetail(taskId);
  } catch (e) { toast('Could not load the task: ' + e.message, 'err'); }
}

async function decideApproval(id, decision) {
  const body = { status: decision, decided_by: 'operator' };
  if (decision === 'rejected') {
    const fb = prompt('Rejecting — what should change? (optional: leave EMPTY to automatically attach the frontier judge’s findings; the task retries either way)');
    if (fb === null) return; // cancelled — no decision made
    if (fb.trim()) body.feedback = fb.trim();
  }
  await api('PATCH', `/api/approvals/${id}`, body);
  toast(decision === 'approved'
    ? 'Approved — shipped to Done'
    : 'Rejected — back on the board; a lane will retry it with the feedback attached', 'ok');
  await loadAgenticData();
  state.tasks = await api('GET', '/api/tasks');
  render();
}
async function toggleJob(id, enabled) {
  await api('PATCH', `/api/scheduler/${id}`, { enabled });
  await loadAgenticData();
  render();
}
async function deleteJob(id) {
  await api('DELETE', `/api/scheduler/${id}`);
  toast('Job deleted', 'ok');
  await loadAgenticData();
  render();
}
function showVerifyModal() { $('#verifyModal').style.display = 'flex'; }
function showJobModal() { $('#jobModal').style.display = 'flex'; }
async function runVerify() {
  const cmd = $('#vfCmd').value.trim(); const kind = $('#vfKind').value; const tid = $('#vfTask').value.trim();
  if (!cmd) return;
  const body = { command: cmd, kind };
  if (tid) body.task_id = tid;
  const r = await api('POST', '/api/verify', body);
  $('#verifyModal').style.display = 'none';
  await loadAgenticData();
  render();
  toast(r.passed ? '✓ verify PASSED' : '✗ verify FAILED', r.passed ? 'ok' : 'err');
}
async function createJob() {
  const name = $('#jbName').value.trim(); const cron = $('#jbCron').value.trim(); const action = $('#jbAction').value.trim();
  if (!name || !cron || !action) return;
  await api('POST', '/api/scheduler', { name, cron_expr: cron, action });
  $('#jobModal').style.display = 'none';
  toast('Job scheduled', 'ok');
  await loadAgenticData();
  render();
}

// ── Dispatch budgets & limits (operator-editable, stored in settings) ──
async function dispatchSettingsUI() {
  let s = {};
  try { s = (await api('GET', '/api/settings')).settings || {}; }
  catch { }
  const v = k => s[k];
  showModal(`
    <h2>⚙ Dispatch budgets & limits</h2>
    <div class="view-intro" style="margin-bottom:10px">Budgets count <strong>input + output tokens per turn</strong> — agentic sessions resend their growing context every tool call, so real coding tasks use millions. The per-task default applies when a task has no own budget (set one in the task form); every retry automatically grants one more budget-slice.</div>
    <div class="form-row">
      <div class="form-group"><label class="form-label">Default per-task budget (tokens)</label>
        <input class="form-input" id="ds-taskbudget" type="number" min="100000" step="100000" value="${esc(String(v('dispatch.default_task_budget') || 5000000))}">
        <div class="form-hint">Blocks a single runaway task. Typical real implement task: 5–15M.</div></div>
      <div class="form-group"><label class="form-label">Daily cap (tokens, all tasks)</label>
        <input class="form-input" id="ds-dailycap" type="number" min="1000000" step="1000000" value="${esc(String(v('dispatch.daily_cap') || 9900000000))}">
        <div class="form-hint">Hard stop for the whole day across all lanes.</div></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label class="form-label">Max concurrent per model</label>
        <input class="form-input" id="ds-permodel" type="number" min="1" max="10" value="${esc(String(v('dispatch.max_concurrent_per_model') || 8))}"></div>
      <div class="form-group"><label class="form-label">Max concurrent total</label>
        <input class="form-input" id="ds-total" type="number" min="1" max="10" value="${esc(String(v('dispatch.max_concurrent_total') || 8))}"></div>
    </div>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" onclick="saveDispatchSettings()">Save</button>
    </div>`);
}

async function saveDispatchSettings() {
  const body = {
    'dispatch.default_task_budget': String(parseInt($('#ds-taskbudget').value) || 5000000),
    'dispatch.daily_cap': String(parseInt($('#ds-dailycap').value) || 9900000000),
    'dispatch.max_concurrent_per_model': String(parseInt($('#ds-permodel').value) || 8),
    'dispatch.max_concurrent_total': String(parseInt($('#ds-total').value) || 8),
  };
  closeModal();
  try {
    await api('PATCH', '/api/settings', body);
    toast('Dispatch budgets & limits saved — apply immediately, no restart needed', 'ok');
  } catch (e) { toast('Save failed: ' + e.message, 'err'); }
}

function showWatchdogModal() {
  const cfg = (state.watchdog || {}).config || {};
  showModal(`
    <h2>Watchdog Configuration</h2>
    <div class="form-row">
      <div class="form-group"><label class="form-label">Check interval (s)</label>
        <input class="form-input" id="wd-interval" type="number" min="2" value="${cfg.interval_s || 10}"></div>
      <div class="form-group"><label class="form-label">Stale heartbeat threshold (s)</label>
        <input class="form-input" id="wd-stale" type="number" min="10" value="${cfg.stale_threshold_s || 60}"></div>
    </div>
    <div class="form-group" style="display:flex;gap:22px;margin-top:6px">
      <label class="switch"><input type="checkbox" id="wd-dead" ${cfg.restart_on_dead ? 'checked' : ''}><span class="sw-track"></span>Restart dead agents</label>
      <label class="switch"><input type="checkbox" id="wd-stuck" ${cfg.restart_on_stuck ? 'checked' : ''}><span class="sw-track"></span>Restart stuck agents</label>
    </div>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" onclick="saveWatchdogConfig()">Save</button>
    </div>
  `);
}

async function saveWatchdogConfig() {
  const body = {
    interval_s: parseInt($('#wd-interval').value) || 10,
    stale_threshold_s: parseInt($('#wd-stale').value) || 60,
    restart_on_dead: $('#wd-dead').checked,
    restart_on_stuck: $('#wd-stuck').checked,
  };
  closeModal();
  try {
    await api('PATCH', '/api/watchdog/config', body);
    toast('Watchdog config saved', 'ok');
    await loadAgenticData();
    render();
  } catch { /* error toast shown */ }
}
// ===== JARVIS =====
// v2 (2026-07-08): particle avatar in the BACKGROUND (Jarvis3D point-cloud
// head + node streams into the real memory galaxy), chat floating in front,
// sessions sidebar with resume, drag&drop file exchange with Hermes,
// WS-streamed chunked TTS with native-timing lip-sync (AnalyserNode on the
// real audio drives the mouth), adaptive VAD + barge-in conversation mode,
// webcam/screen share indexed into SigLIP visual memory, vision search popup,
// /imagine image generation, morning briefing, spoken task callbacks.
let jarvisState = {
  connected: false,
  voiceAvailable: false,
  visionAvailable: false,
  mode: 'idle',        // idle | listening | thinking | talking
  messages: [],
  sessions: [],
  currentSession: null,
  recording: false,
  streaming: false,
  mediaRecorder: null,
  audioChunks: [],
  micAnalyser: null,
  micStream: null,
  audioContext: null,
  ttsAudioEl: null,     // HTTP-fallback audio element (WS is the primary path)
  conversationMode: false,
  voiceOn: localStorage.getItem('jvVoiceOn') !== '0',
  fxOn: localStorage.getItem('jvFxOn') !== '0',
  deckOpen: localStorage.getItem('jvDeckOpen') === '1',
  domain: null,
  domainLabel: null,   // kept so the 📚 chip survives a view detach/re-attach
  abortController: null,
  ttsAnimating: false,  // true while the WS audio pipeline is speaking
  statusGen: 0,
  eventsGen: 0,
  eventsSince: 0,
  capture: { webcam: null, screen: null },  // {stream, video, timer}
  _vad: null,
  _barge: null,
  _titled: {},
};

// ── WS TTS pipeline: server streams raw PCM (16-bit mono 22050) per sentence;
//    chunks are scheduled gaplessly on an AudioContext; an AnalyserNode on the
//    SAME graph feeds the avatar's mouth = native-timing lip-sync. ──
// uq = per-sentence LIVE utterance records for the avatar's viseme lip sync:
// {text, start, end, done} on the AudioContext clock (see Jarvis3D.speak)
const jTTS = { ws: null, connecting: null, nextTime: 0, sources: [], pending: 0, analyser: null, data: null, uq: [] };

function jarvisAudioCtx() {
  if (!jarvisState.audioContext) {
    jarvisState.audioContext = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (jarvisState.audioContext.state === 'suspended') {
    jarvisState.audioContext.resume().catch(() => { });
  }
  return jarvisState.audioContext;
}

function jarvisTTSGraph() {
  const ctx = jarvisAudioCtx();
  if (!jTTS.analyser) {
    jTTS.analyser = ctx.createAnalyser();
    jTTS.analyser.fftSize = 256;
    jTTS.analyser.connect(ctx.destination);
    jTTS.data = new Uint8Array(jTTS.analyser.frequencyBinCount);
  }
  return jTTS.analyser;
}

function jarvisTTSWs() {
  if (jTTS.ws && jTTS.ws.readyState === 1) return Promise.resolve(jTTS.ws);
  if (jTTS.connecting) return jTTS.connecting;   // F130: one socket only — await the in-flight connect
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';   // derive scheme like the main /ws socket
  const p = new Promise((resolve) => {
    const ws = new WebSocket(`${proto}://${location.host}/ws/jarvis/tts`);
    ws.binaryType = 'arraybuffer';
    // Only THIS attempt may clear the shared connect marker — a stale socket's
    // late open/error/close must not wipe a NEWER connect's promise, or a second
    // socket could open and break the one-socket invariant (F130).
    const clearConnecting = () => { if (jTTS.connecting === p) jTTS.connecting = null; };
    ws.onmessage = (e) => {
      if (typeof e.data === 'string') {
        let d = {};
        try { d = JSON.parse(e.data); } catch { }
        if (d.done || d.error) {
          // sentences are FIFO on this socket: the first not-done utterance
          // record is the one that just finished synthesizing
          const cur = jTTS.uq.find(u => !u.done);
          if (cur) cur.done = true;
          jTTS.pending = Math.max(0, jTTS.pending - 1);
          jarvisTTSMaybeFinish();
        }
        return;
      }
      // A chunk with no outstanding utterance is a straggler from a stopped /
      // barged-in reply — drop it so it can't re-wake the avatar into "talking"
      // and play audio past the interrupt (F063).
      if (jTTS.pending <= 0) return;
      // binary PCM chunk → schedule right after whatever is already queued
      const ctx = jarvisAudioCtx();
      const i16 = new Int16Array(e.data);
      if (!i16.length) return;
      const f32 = new Float32Array(i16.length);
      for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768;
      const buf = ctx.createBuffer(1, f32.length, 22050);
      buf.getChannelData(0).set(f32);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(jarvisTTSGraph());
      const at = Math.max(jTTS.nextTime, ctx.currentTime + 0.06);
      src.start(at);
      jTTS.nextTime = at + buf.duration;
      // viseme lip sync: bind this chunk to its sentence (FIFO). The first
      // chunk fixes the start; every chunk extends the end — the avatar
      // holds the LIVE record and re-stretches its timeline each frame.
      const cur = jTTS.uq.find(u => !u.done);
      if (cur) {
        if (cur.start < 0) {
          cur.start = at;
          if (window.Jarvis3D && window.Jarvis3D.speak) window.Jarvis3D.speak(cur, ctx);
        }
        cur.end = at + buf.duration;
      }
      jTTS.sources.push(src);
      src.onended = () => {
        jTTS.sources = jTTS.sources.filter(s => s !== src);
        jarvisTTSMaybeFinish();
      };
      if (!jarvisState.ttsAnimating) {
        jarvisState.ttsAnimating = true;
        jarvisState.ttsEngagedEver = true;   // latch for the e2e gate — a short
        // reply can start AND finish speaking between two 1.5s gate polls
        jarvisSetMode('talking');
        jarvisTtsLevelLoop();
        jarvisBargeMonitorStart();
      }
    };
    ws.onopen = () => { jTTS.ws = ws; clearConnecting(); resolve(ws); };
    ws.onerror = () => { clearConnecting(); if (jTTS.ws === ws) jarvisTTSReset(); resolve(null); };
    ws.onclose = () => {
      clearConnecting();
      // socket dropped mid-utterance → force the pipeline back to idle so the
      // avatar can't stay wedged in "talking" forever (F063)
      if (jTTS.ws === ws) { jTTS.ws = null; jarvisTTSReset(); }
    };
  });
  jTTS.connecting = p;
  return p;
}

function jarvisTTSMaybeFinish() {
  if (!jarvisState.ttsAnimating) return;
  const ctx = jarvisState.audioContext;
  if (jTTS.pending === 0 && jTTS.sources.length === 0 &&
      (!ctx || ctx.currentTime >= jTTS.nextTime - 0.05)) {
    jTTS.uq = [];   // all sentences spoken — drop the utterance records
    jarvisState.ttsAnimating = false;
    jarvisBargeMonitorStop();
    if (jarvisState.mode === 'talking') jarvisSetMode('idle');
    if (window.Jarvis3D) window.Jarvis3D.setLevel(0);
    jarvisMaybeAutoListen();
  }
}

// Force the WS TTS pipeline back to a quiet idle state and drop any queued /
// scheduled audio. Used when the socket drops or errors mid-utterance (there is
// no {done} coming, so jarvisTTSMaybeFinish would never fire) so the avatar can
// never get stuck "talking" (F063).
function jarvisTTSReset() {
  for (const s of jTTS.sources) { try { s.stop(); } catch { } }
  jTTS.sources = [];
  jTTS.pending = 0;
  jTTS.nextTime = 0;
  jTTS.uq = [];
  if (window.Jarvis3D && window.Jarvis3D.stopSpeech) window.Jarvis3D.stopSpeech();
  jarvisState.ttsAnimating = false;
  jarvisBargeMonitorStop();
  if (window.Jarvis3D) window.Jarvis3D.setLevel(0);
  if (jarvisState.mode === 'talking') jarvisSetMode('idle');
}

// gate-contract name: speak a reply (sentence-split, streamed over the WS)
async function jarvisSpeak(text) {
  if (!jarvisState.voiceAvailable || !jarvisState.voiceOn) return;
  const sentences = (text.match(/[^.!?]+[.!?]*/g) || [text])
    .map(s => s.trim()).filter(s => s.length > 1);
  if (!sentences.length) return;
  const ws = await jarvisTTSWs();
  if (!ws) { jarvisSpeakFallback(sentences); return; }
  for (const s of sentences) {
    jTTS.pending++;
    jTTS.uq.push({ text: s, start: -1, end: -1, done: false });
    ws.send(JSON.stringify({ text: s }));
  }
}

// HTTP fallback when the WS is unavailable (gate-contract name kept: fetches
// audio for one utterance — WAV via /api/jarvis/tts; Wav2Lip /talk retired)
async function jarvisFetchClip(text) {
  try {
    const resp = await fetch('/api/jarvis/tts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (resp.ok) return await resp.blob();
  } catch { }
  return null;
}

async function jarvisSpeakFallback(sentences) {
  jarvisState.ttsAnimating = true;
  jarvisSetMode('talking');
  for (const s of sentences) {
    if (!jarvisState.ttsAnimating) break;   // stopped
    const blob = await jarvisFetchClip(s);
    if (!blob) continue;
    await new Promise((res) => {
      if (!jarvisState.ttsAudioEl) jarvisState.ttsAudioEl = new Audio();
      const a = jarvisState.ttsAudioEl;
      a.src = URL.createObjectURL(blob);
      a.onended = a.onerror = () => { URL.revokeObjectURL(a.src); res(); };
      // no analyser on this path — hand the avatar a fixed-window utterance
      // on the performance clock (strictly better than the old static mouth)
      a.onloadedmetadata = () => {
        if (isFinite(a.duration) && window.Jarvis3D && window.Jarvis3D.speak) {
          const t0 = performance.now() / 1000;
          window.Jarvis3D.speak(
            { text: s, start: t0, end: t0 + a.duration, done: true }, null);
        }
      };
      a.play().catch(() => res());
    });
  }
  jarvisState.ttsAnimating = false;
  if (jarvisState.mode === 'talking') jarvisSetMode('idle');
  jarvisMaybeAutoListen();
}

function jarvisStopTTS() {
  jTTS.pending = 0;
  if (jTTS.ws && jTTS.ws.readyState === 1) jTTS.ws.send(JSON.stringify({ stop: true }));
  for (const s of jTTS.sources) { try { s.stop(); } catch { } }
  jTTS.sources = [];
  jTTS.nextTime = 0;
  jTTS.uq = [];
  if (window.Jarvis3D && window.Jarvis3D.stopSpeech) window.Jarvis3D.stopSpeech();
  if (jarvisState.ttsAudioEl) { try { jarvisState.ttsAudioEl.pause(); } catch { } }
  jarvisState.ttsAnimating = false;
  jarvisBargeMonitorStop();
  if (window.Jarvis3D) window.Jarvis3D.setLevel(0);
  if (jarvisState.mode === 'talking') jarvisSetMode('idle');
}

function jarvisTtsLevelLoop() {
  if (currentView !== 'jarvis') return;  // detached — renderJarvisView restarts the loop
  if (!jarvisState.ttsAnimating || !jTTS.analyser) {
    if (window.Jarvis3D && !jarvisState.recording) window.Jarvis3D.setLevel(0);
    return;
  }
  jTTS.analyser.getByteTimeDomainData(jTTS.data);
  let sum = 0;
  for (let i = 0; i < jTTS.data.length; i++) { const d = (jTTS.data[i] - 128) / 128; sum += d * d; }
  const rms = Math.sqrt(sum / jTTS.data.length);
  // spectral hint for the mouth: sibilance share (high band vs vowel band) —
  // jarvis3d narrows the aperture on s/sh/f instead of dropping the jaw
  if (!jTTS.freq) jTTS.freq = new Uint8Array(jTTS.analyser.frequencyBinCount);
  jTTS.analyser.getByteFrequencyData(jTTS.freq);
  let lo = 0, hi = 0;
  for (let i = 1; i <= 6; i++) lo += jTTS.freq[i];
  for (let i = 24; i <= 60; i++) hi += jTTS.freq[i];
  lo /= 6 * 255; hi /= 37 * 255;
  if (window.Jarvis3D) window.Jarvis3D.setLevel(rms * 6, hi / (lo + hi + 1e-4));
  requestAnimationFrame(jarvisTtsLevelLoop);
}

// ── view ──
function renderJarvisView() {
  const c = $('#content');
  c.innerHTML = `
    <div class="jv2">
      <aside class="jv2-side">
        <button class="btn-primary" id="jNewChat" style="width:100%">✚ New conversation</button>
        <div class="jv2-panel-title">Recent sessions</div>
        <div class="jv2-sessions" id="jSessions"><div class="muted" style="font-size:11.5px">—</div></div>
        <div class="jv2-panel-title">File exchange <button class="jv2-mini-btn" id="jFilesRefresh" title="refresh">⟳</button></div>
        <div class="jv2-files" id="jFilesList"><div class="muted" style="font-size:11.5px">—</div></div>
        <div class="attach-dz jv2-dz" id="jFilesDz">
          <div style="font-size:11.5px">📎 Drop files for JARVIS<br><span class="muted" style="font-size:10.5px">…or click to browse. He reads, edits and creates files here.</span></div>
          <input type="file" id="jFilesInput" multiple style="display:none">
        </div>
      </aside>
      <div class="jv2-stage" id="jStage">
        <div class="jv2-topbar">
          <span class="jv2-chip" id="jStateChip">IDLE</span>
          <span class="jv2-chip"><span class="j-dot" id="jDotHermes"></span> Hermes</span>
          <span class="jv2-chip"><span class="j-dot" id="jDotVoice"></span> Voice</span>
          <span class="jv2-chip" id="jVisionChip" title="frames in visual memory">👁 —</span>
          <span class="jv2-chip jv2-domain" id="jDomainChip" title="craft domain JARVIS is drawing on (Business Brain)" style="display:none"></span>
          <span style="flex:1"></span>
          <button class="jv2-btn${jarvisState.deckOpen ? ' active' : ''}" id="jDeckBtn" title="Command deck — board, deliverables, approvals, Test app">⚡ Deck</button>
          <button class="jv2-btn" id="jCamBtn" title="Share webcam — JARVIS sees and remembers frames">🎥 Cam</button>
          <button class="jv2-btn" id="jScreenBtn" title="Share screen — JARVIS sees and remembers frames">🖥 Screen</button>
          <button class="jv2-btn" id="jVisMemBtn" title="Search everything JARVIS has seen">👁 Memory</button>
          <button class="jv2-btn" id="jGalaxyBtn" title="Fly into the memory galaxy — orbit, inspect and edit memories">🧠 Memory</button>
          <button class="jv2-btn" id="jImagineBtn" title="Generate an image (local SDXL)">🎨 Imagine</button>
          <button class="jv2-btn" id="jBriefBtn" title="Status briefing">📋 Brief</button>
          <button class="jv2-btn" id="jVoiceBtn" title="Voice replies on/off">${jarvisState.voiceOn ? '🔊' : '🔇'}</button>
          <button class="jv2-btn" id="jFxBtn" title="Avatar animations on/off">${jarvisState.fxOn ? '✨ FX' : '▪ FX'}</button>
          <label class="conv-toggle" title="Hands-free conversation: JARVIS listens after each reply, detects when you stop talking, and you can talk over him to interrupt">
            <input type="checkbox" id="jConvToggle" ${jarvisState.conversationMode ? 'checked' : ''}>
            <span class="conv-slider"></span><span class="conv-label">CONV</span>
          </label>
          <div class="mic-level"><i id="jMicLevel"></i></div>
        </div>
        <div class="jv2-chat">
          <div class="jv2-feed" id="jFeed"></div>
          <div class="jv2-inputrow">
            <button class="jv2-mic" id="jMicBtn" title="Hold a conversation — click to talk">🎙</button>
            <input class="jarvis-chat-input" id="jInput" placeholder="Talk or type — /see  /imagine  /find <what you showed me>…" autocomplete="off">
            <button class="jarvis-send-btn" id="jSendBtn">SEND</button>
            <button class="jarvis-stop-btn" id="jStopBtn" style="display:none">STOP</button>
          </div>
        </div>
        <video id="jCapPreview" class="jv2-cap-preview" style="display:none" muted playsinline></video>
      </div>
      <aside class="jv2-deck" id="jDeck" style="display:${jarvisState.deckOpen ? 'flex' : 'none'}">
        <div class="jv2-panel-title" style="margin-top:0">⚡ Command deck
          <button class="jv2-mini-btn" id="jDeckRefresh" title="refresh">⟳</button></div>
        <div class="jv2-deck-body" id="jDeckBody"><div class="muted" style="font-size:11.5px">—</div></div>
      </aside>
    </div>
  `;
  jarvisBindControls();
  if (jarvisState.deckOpen) jarvisLoadDeck();
  jarvisState.statusGen++;
  jarvisLoadStatus(jarvisState.statusGen);
  jarvisState.eventsGen++;
  if (!jarvisState.eventsSince) jarvisState.eventsSince = Date.now() / 1000;
  jarvisPollEvents(jarvisState.eventsGen);
  jarvisLoadSessions();
  jarvisLoadFiles();
  if (window.Jarvis3D) {
    // the galaxy inside the JARVIS scene is editable, like the Memory tab's map
    window.Jarvis3D.mount($('#jStage'), { onMemorySelect: openMemoryNodeModal });
    window.Jarvis3D.setAnimations(jarvisState.fxOn);
  }
  if (jarvisState.messages.length) jarvisRenderFeed();
  // Option C re-attach: a turn/speech may have kept running while the view was
  // away — restore the busy controls, wake the audio clock, and restart the
  // mouth loop + barge monitor that jarvisViewDetach shed.
  if (jarvisState.streaming) {
    const sb = $('#jSendBtn'), stb = $('#jStopBtn');
    if (sb) sb.disabled = true;
    if (stb) stb.style.display = 'block';
  }
  if (jarvisState.domain) jarvisSetDomain(jarvisState.domain, jarvisState.domainLabel);
  if (jarvisState.audioContext && jarvisState.audioContext.state === 'suspended') {
    jarvisState.audioContext.resume().catch(() => { });
  }
  if (jarvisState.ttsAnimating) {
    jarvisTtsLevelLoop();
    jarvisBargeMonitorStart();
  }
  jarvisSetMode(jarvisState.streaming ? 'thinking' : jarvisState.ttsAnimating ? 'talking' : 'idle');
  jarvisMaybeBrief();
}

// Leaving the JARVIS view (Batch 8 "Option C"): shed only what is DOM- or
// presence-bound — avatar, mic capture, webcam/screen share, barge monitor,
// view-scoped pollers. The in-flight chat stream, the TTS WebSocket and the
// AudioContext deliberately SURVIVE, so JARVIS keeps streaming AND speaking
// while another view is open; renderJarvisView re-attaches on return.
function jarvisViewDetach() {
  try {
    if (jarvisState.mediaRecorder && jarvisState.recording) {
      jarvisState.mediaRecorder.onstop = null;
      jarvisState.mediaRecorder.stop();
      jarvisState.mediaRecorder.stream.getTracks().forEach(t => t.stop());
    }
  } catch { }
  jarvisState.recording = false;
  jarvisState.micAnalyser = null;
  jarvisCaptureStop('webcam');
  jarvisCaptureStop('screen');
  jarvisBargeMonitorStop();
  jarvisState.statusGen++;
  jarvisState.eventsGen++;
  if (window.Jarvis3D) window.Jarvis3D.dispose();
}

// The FULL stop — abort the turn, silence TTS, drop the audio socket. Only an
// explicit user Stop or logout comes through here; a view switch must not.
function jarvisHardStop() {
  try { jarvisStopStreaming(); } catch { }
  if (jTTS.ws) { try { jTTS.ws.close(); } catch { } jTTS.ws = null; }
}

function jarvisBindControls() {
  $('#jSendBtn').addEventListener('click', () => jarvisSendText());
  $('#jInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); jarvisSendText(); }
  });
  $('#jStopBtn').addEventListener('click', () => jarvisHardStop());
  $('#jMicBtn').addEventListener('click', () => {
    if (jarvisState.recording) { jarvisStopRecording(); return; }
    if (jarvisState.ttsAnimating) jarvisStopTTS();   // click barge-in
    jarvisStartRecording();
  });
  const convToggle = $('#jConvToggle');
  convToggle.addEventListener('change', () => {
    jarvisState.conversationMode = convToggle.checked;
    if (convToggle.checked && !jarvisState.recording && !jarvisState.streaming
        && !jarvisState.ttsAnimating) jarvisStartRecording();
  });
  $('#jNewChat').addEventListener('click', async () => {
    try {
      const r = await api('POST', '/api/jarvis/session');
      jarvisState.currentSession = r.session_id;
      jarvisState.messages = [];
      jarvisRenderFeed();
      jarvisLoadSessions();
      toast('Fresh conversation started', 'ok');
    } catch (e) { toast('Failed: ' + e.message, 'err'); }
  });
  $('#jCamBtn').addEventListener('click', () => jarvisCaptureToggle('webcam'));
  $('#jScreenBtn').addEventListener('click', () => jarvisCaptureToggle('screen'));
  $('#jVisMemBtn').addEventListener('click', () => jarvisVisionSearchModal(''));
  $('#jGalaxyBtn').addEventListener('click', () => {
    if (!window.Jarvis3D || !window.Jarvis3D.toggleGalaxy) return;
    const on = window.Jarvis3D.toggleGalaxy();
    $('#jStage').classList.toggle('galaxy-on', on);
    $('#jGalaxyBtn').classList.toggle('active', on);
    $('#jGalaxyBtn').textContent = on ? '↩ JARVIS' : '🧠 Memory';
  });
  $('#jImagineBtn').addEventListener('click', () => {
    const q = prompt('Describe the image JARVIS should create:');
    if (q) jarvisImagine(q);
  });
  $('#jBriefBtn').addEventListener('click', () => jarvisBrief(true));
  $('#jDeckBtn').addEventListener('click', () => jarvisToggleDeck());
  $('#jDeckRefresh').addEventListener('click', () => jarvisLoadDeck());
  $('#jVoiceBtn').addEventListener('click', () => {
    jarvisState.voiceOn = !jarvisState.voiceOn;
    localStorage.setItem('jvVoiceOn', jarvisState.voiceOn ? '1' : '0');
    $('#jVoiceBtn').textContent = jarvisState.voiceOn ? '🔊' : '🔇';
    if (!jarvisState.voiceOn) jarvisStopTTS();
  });
  $('#jFxBtn').addEventListener('click', () => {
    jarvisState.fxOn = !jarvisState.fxOn;
    localStorage.setItem('jvFxOn', jarvisState.fxOn ? '1' : '0');
    $('#jFxBtn').textContent = jarvisState.fxOn ? '✨ FX' : '▪ FX';
    if (window.Jarvis3D) window.Jarvis3D.setAnimations(jarvisState.fxOn);
  });
  // file exchange dropzone
  const dz = $('#jFilesDz'), finput = $('#jFilesInput');
  dz.addEventListener('click', () => finput.click());
  finput.addEventListener('change', () => { jarvisUploadFiles([...finput.files]); finput.value = ''; });
  ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => {
    e.preventDefault(); e.stopPropagation(); dz.classList.add('dz-hover');
  }));
  dz.addEventListener('dragleave', e => { e.preventDefault(); dz.classList.remove('dz-hover'); });
  dz.addEventListener('drop', e => {
    e.preventDefault(); e.stopPropagation(); dz.classList.remove('dz-hover');
    jarvisUploadFiles([...((e.dataTransfer || {}).files || [])]);
  });
  $('#jFilesRefresh').addEventListener('click', () => jarvisLoadFiles());
  // dropping an image anywhere on the chat = "look at this"
  const feed = $('#jFeed');
  ['dragenter', 'dragover'].forEach(ev => feed.addEventListener(ev, e => e.preventDefault()));
  feed.addEventListener('drop', e => {
    e.preventDefault();
    const f = [...((e.dataTransfer || {}).files || [])].find(f => f.type.startsWith('image/'));
    if (f) jarvisLookAtFile(f);
  });
}

// ── status + sessions + files ──
async function jarvisLoadStatus(gen) {
  if (gen !== jarvisState.statusGen) return;
  try {
    const s = await api('GET', '/api/jarvis/status');
    jarvisState.connected = s.connected;
    const d = $('#jDotHermes');
    if (d) { d.classList.toggle('on', s.connected); d.classList.toggle('off', !s.connected); }
    if (!jarvisState.currentSession) jarvisState.currentSession = s.session_id;
  } catch { const d = $('#jDotHermes'); if (d) d.classList.add('off'); }
  try {
    const v = await api('GET', '/api/jarvis/voice/status');
    jarvisState.voiceAvailable = v.available;
    const d = $('#jDotVoice');
    if (d) { d.classList.toggle('on', v.available); d.classList.toggle('off', !v.available); }
  } catch { const d = $('#jDotVoice'); if (d) d.classList.add('off'); }
  try {
    const vi = await api('GET', '/api/jarvis/vision/status');
    jarvisState.visionAvailable = !!vi.available;
    const c = $('#jVisionChip');
    if (c) c.textContent = vi.available ? `👁 ${vi.frames ?? 0}` : '👁 off';
  } catch { }
  setTimeout(() => {
    if (currentView === 'jarvis' && gen === jarvisState.statusGen) jarvisLoadStatus(gen);
  }, 15000);
}

async function jarvisLoadSessions() {
  try {
    const r = await api('GET', '/api/jarvis/my-sessions');
    jarvisState.sessions = r.sessions || [];
    if (r.current) jarvisState.currentSession = r.current;
    const el = $('#jSessions');
    if (!el) return;
    el.innerHTML = jarvisState.sessions.slice(0, 14).map(s => `
      <div class="jv2-session${s.id === jarvisState.currentSession ? ' active' : ''}"
           onclick="jarvisSwitchSession('${esc(s.id)}')">
        <button class="jv2-mini-btn jv2-session-x" title="forget this conversation"
          onclick="event.stopPropagation();jarvisForgetSession('${esc(s.id)}')">✕</button>
        <div class="jv2-session-title">${esc(s.title || 'Conversation')}</div>
        <div class="jv2-session-time">${s.ts ? fmtAgo(s.ts) : ''}</div>
      </div>`).join('') || '<div class="muted" style="font-size:11.5px">No conversations yet</div>';
  } catch { }
}

async function jarvisForgetSession(sid) {
  if (!confirm('Forget this conversation? Its messages are removed from the sidebar.')) return;
  try {
    const r = await api('POST', '/api/jarvis/session/forget', { id: sid });
    if (sid === jarvisState.currentSession) {
      jarvisState.currentSession = r.current;
      jarvisState.messages = [];
      jarvisRenderFeed();
    }
    jarvisLoadSessions();
  } catch (e) { toast('Failed: ' + e.message, 'err'); }
}

async function jarvisSwitchSession(sid) {
  if (sid === jarvisState.currentSession) return;
  try {
    await api('POST', '/api/jarvis/session/switch', { id: sid });
    jarvisState.currentSession = sid;
    jarvisState.messages = [];
    const h = await api('GET', `/api/jarvis/messages/${sid}`);
    const msgs = h.messages || h.data || [];
    for (const m of msgs) {
      const role = (m.role || '').includes('user') ? 'user' : 'jarvis';
      const text = typeof m.content === 'string' ? m.content
        : Array.isArray(m.content) ? m.content.map(b => b.text || '').join('') : '';
      if (text) jarvisState.messages.push({ role, text });
    }
    jarvisRenderFeed();
    jarvisLoadSessions();
  } catch (e) { toast('Switch failed: ' + e.message, 'err'); }
}

async function jarvisLoadFiles() {
  try {
    const r = await api('GET', '/api/jarvis/files');
    const el = $('#jFilesList');
    if (!el) return;
    el.innerHTML = (r.files || []).map(f => `
      <div class="jv2-file">
        <a href="/api/jarvis/files/${encodeURIComponent(f.name)}" target="_blank">📄 ${esc(f.name)}</a>
        <span class="muted" style="font-size:10px">${(f.size / 1024).toFixed(0)}K</span>
        <button class="jv2-mini-btn" title="delete" onclick="jarvisDeleteFile('${esc(f.name)}')">✕</button>
      </div>`).join('') || '<div class="muted" style="font-size:11.5px">Empty — drop a file below</div>';
  } catch { }
}

async function jarvisDeleteFile(name) {
  try { await api('DELETE', `/api/jarvis/files/${encodeURIComponent(name)}`); jarvisLoadFiles(); }
  catch (e) { toast('Delete failed: ' + e.message, 'err'); }
}

async function jarvisUploadFiles(files) {
  let done = 0;
  for (const f of files) {
    const fd = new FormData();
    fd.append('file', f);
    try {
      const r = await fetch('/api/jarvis/files', { method: 'POST', body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || r.status);
      done++;
    } catch (e) { toast(`${f.name}: ${e.message}`, 'err'); }
  }
  if (done) {
    toast(`${done} file${done > 1 ? 's' : ''} shared with JARVIS`, 'ok');
    jarvisLoadFiles();
    jarvisAddMessage('tool', `📎 ${done} file${done > 1 ? 's' : ''} uploaded to the exchange — mention them to JARVIS by name.`);
  }
}

// ── mode + feed ──
function jarvisSetMode(mode) {
  jarvisState.mode = mode;
  if (window.Jarvis3D) window.Jarvis3D.setMode(mode);
  const labels = { idle: 'IDLE', listening: 'LISTENING', thinking: 'THINKING', talking: 'SPEAKING' };
  const chip = $('#jStateChip');
  if (chip) {
    chip.textContent = labels[mode] || mode.toUpperCase();
    chip.className = 'jv2-chip mode-' + mode;
  }
  const mic = $('#jMicBtn');
  if (mic) mic.classList.toggle('rec', mode === 'listening');
}

function jarvisAddMessage(role, text, extra) {
  jarvisState.messages.push(Object.assign({ role, text }, extra || {}));
  jarvisRenderFeed();
}

// ── domain chip (Business Brain) ──
function jarvisSetDomain(domain, label) {
  jarvisState.domain = domain || null;
  jarvisState.domainLabel = label || null;
  const chip = $('#jDomainChip');
  if (!chip) return;
  if (domain) {
    chip.textContent = '📚 ' + (label || domain);
    chip.style.display = '';
  } else {
    chip.style.display = 'none';
  }
}

// ── command deck: board · deliverables (▶ Test app) · approvals, without
//    leaving the conversation. Data mirrors the dedicated tabs; actions reuse
//    their handlers (testAppUI, decideApproval, describeTaskUI). ──
function jarvisToggleDeck() {
  jarvisState.deckOpen = !jarvisState.deckOpen;
  localStorage.setItem('jvDeckOpen', jarvisState.deckOpen ? '1' : '0');
  const deck = $('#jDeck'), btn = $('#jDeckBtn');
  if (deck) deck.style.display = jarvisState.deckOpen ? 'flex' : 'none';
  if (btn) btn.classList.toggle('active', jarvisState.deckOpen);
  if (jarvisState.deckOpen) jarvisLoadDeck();
}

async function jarvisLoadDeck() {
  const body = $('#jDeckBody');
  if (!body) return;
  let tasks = [], delivs = [], approvals = [];
  try {
    const [tr, dr, ar] = await Promise.all([
      api('GET', '/api/tasks').catch(() => ({ tasks: [] })),
      api('GET', '/api/deliverables?limit=8').catch(() => ({ deliverables: [] })),
      api('GET', '/api/approvals?status=pending').catch(() => ({ approvals: [] })),
    ]);
    tasks = tr.tasks || [];
    delivs = dr.deliverables || [];
    approvals = ar.approvals || ar.pending || [];
  } catch { /* deck is best-effort */ }
  if ($('#jDeckBody') !== body) return;  // view changed mid-fetch

  // board glance
  const live = tasks.filter(t => t.status !== 'archived');
  const col = (s) => live.filter(t => t.status === s).length;
  const running = live.filter(t => ['queued', 'dispatching', 'streaming', 'finalizing']
    .includes(t.dispatch_state)).length;
  const board = `
    <div class="jv2-deck-sec">
      <div class="jv2-deck-h">Board</div>
      <div class="jv2-deck-board" onclick="switchView('kanban')" title="Open the kanban">
        ${[['Backlog', col('backlog')], ['To do', col('todo')], ['Doing', col('in_progress')], ['Done', col('done')]]
      .map(([l, n]) => `<div class="jv2-deck-stat"><b>${n}</b><span>${l}</span></div>`).join('')}
      </div>
      ${running ? `<div class="jv2-deck-running">▶ ${running} running now</div>` : ''}
    </div>`;

  // deliverables with ▶ Test app when a runnable was detected
  const vBadge = (v) => v ? `<span class="jv2-deck-badge ${/APPROVE|PASS/i.test(v) ? 'ok' : /REVISE|REWRITE|FAIL/i.test(v) ? 'warn' : ''}">${esc(v)}</span>` : '';
  const delRows = delivs.length ? delivs.slice(0, 8).map(d => {
    const test = d.app ? `<button class="jv2-mini-btn" title="Run the produced app/site live" onclick="testAppUI('${esc(d.task_id)}', ${JSON.stringify(esc(d.title))})">▶ Test</button>` : '';
    const open = (d.files && d.files.length)
      ? `<a class="jv2-mini-btn" href="/api/tasks/${esc(d.task_id)}/files/${encodeURIComponent(d.files[0].name || d.files[0])}" target="_blank" title="open first output file">📄</a>` : '';
    return `<div class="jv2-deck-row">
      <div class="jv2-deck-row-t" title="${esc(d.title)}">${esc(d.title)} ${vBadge(d.judge_verdict)}${d.critic_verdict && d.critic_verdict !== 'running' ? ' ' + vBadge('✨' + d.critic_verdict) : ''}</div>
      <div class="jv2-deck-row-a">${test}${open}</div>
    </div>`;
  }).join('') : '<div class="muted" style="font-size:11px">No output yet.</div>';
  const deliverables = `
    <div class="jv2-deck-sec">
      <div class="jv2-deck-h">Deliverables <button class="jv2-mini-btn" onclick="switchView('deliverables')" title="open Deliverables tab">all</button></div>
      ${delRows}
    </div>`;

  // pending approvals
  const apRows = approvals.length ? approvals.slice(0, 6).map(a => `
    <div class="jv2-deck-row">
      <div class="jv2-deck-row-t" title="${esc(a.description || a.reason || a.action || '')}">${a.action_type === 'super_result' ? '✨ ' : ''}${esc(a.description || a.action || a.reason || a.action_type || 'request')}</div>
      <div class="jv2-deck-row-a">
        <button class="jv2-mini-btn ok" title="approve" onclick="decideApproval('${esc(a.id)}','approved').then(jarvisLoadDeck)">✓</button>
        <button class="jv2-mini-btn warn" title="reject" onclick="decideApproval('${esc(a.id)}','rejected').then(jarvisLoadDeck)">✕</button>
      </div>
    </div>`).join('') : '';
  const approvalsSec = approvals.length ? `
    <div class="jv2-deck-sec">
      <div class="jv2-deck-h">Approvals · ${approvals.length}</div>
      ${apRows}
    </div>` : '';

  body.innerHTML = board + deliverables + approvalsSec + `
    <button class="btn-ghost" style="width:100%;margin-top:4px" onclick="describeTaskUI()"
      title="Describe a goal in plain words — the fleet plans and builds it">✨ Hand a task to the fleet</button>`;
}

function jarvisRenderFeed() {
  const feed = $('#jFeed');
  if (!feed) return;
  feed.innerHTML = jarvisState.messages.map((m, i) => {
    const cls = m.role === 'user' ? 'you' : m.role === 'tool' ? 'tool' : m.role === 'error' ? 'error' : 'jarvis';
    const cls2 = m.live ? ' live' : '';
    const files = (m.files || []).map(f =>
      `<a class="jv2-filechip" href="/api/jarvis/files/${encodeURIComponent(f)}" target="_blank">📄 ${esc(f)}</a>`).join('');
    const imgs = (m.images || []).map(u =>
      `<a href="${esc(u)}" target="_blank"><img class="jv2-msg-img" src="${esc(u)}"></a>`).join('');
    const copy = m.role === 'jarvis' && m.text && !m.live
      ? `<button class="jv2-copy" title="copy" onclick="jarvisCopyMsg(${i})">⧉</button>` : '';
    return `<div class="j-msg ${cls}${cls2}">${esc(m.text)}${imgs}${files ? `<div class="jv2-filerow">${files}</div>` : ''}${copy}</div>`;
  }).join('');
  feed.scrollTop = feed.scrollHeight;
}

function jarvisCopyMsg(i) {
  const m = jarvisState.messages[i];
  if (!m) return;
  navigator.clipboard.writeText(m.text).then(() => toast('Copied', 'ok')).catch(() => { });
}

// ── send + intents ──
function jarvisSendText(forced) {
  const input = $('#jInput');
  const text = (forced != null ? forced : input ? input.value : '').trim();
  if (!text || jarvisState.streaming) return;
  if (input && forced == null) input.value = '';

  // local intents that never need the LLM round-trip
  const mImag = text.match(/^\/imagine\s+(.+)/i) ||
    text.match(/^(?:create|generate|make|draw|paint)\s+(?:me\s+)?(?:an?\s+)?(?:image|picture|photo|drawing|illustration)\s+(?:of|showing|with)\s+(.+)/i);
  if (mImag) { jarvisAddMessage('user', text); jarvisImagine(mImag[1]); return; }
  const mFind = text.match(/^\/(?:find|see)\s+(.+)/i) ||
    text.match(/\bwhen did (?:i|we|you)\b.*\b(?:show|see|saw|shown|watch)\b/i) ||
    text.match(/\b(?:search|find|look up|look for)\b.*\b(?:visual memory|you (?:have )?seen|i showed|screen history|camera history)\b/i);
  if (mFind) {
    jarvisAddMessage('user', text);
    const q = (mFind[1] || text).replace(/^\/(find|see)\s+/i, '');
    jarvisVisionSearchModal(q, true);
    return;
  }

  jarvisAddMessage('user', text);
  jarvisStreamChat(text);
}

// ── chat streaming (progressive speech: sentences are spoken WHILE the reply
//    is still streaming — clause-level latency, not whole-reply latency) ──
async function jarvisStreamChat(text) {
  jarvisState.streaming = true;
  jarvisSetDomain(null);  // cleared; the server's 'domain' event re-sets it if detected
  jarvisSetMode('thinking');
  const sendBtn = $('#jSendBtn'), stopBtn = $('#jStopBtn');
  if (sendBtn) sendBtn.disabled = true;
  if (stopBtn) stopBtn.style.display = 'block';

  const liveMsg = { role: 'jarvis', text: '', live: true, _spoken: 0 };
  jarvisState.messages.push(liveMsg);
  jarvisState.abortController = new AbortController();

  // session titling: first message names the conversation in the sidebar
  const sid = jarvisState.currentSession;
  if (sid && !jarvisState._titled[sid]) {
    jarvisState._titled[sid] = true;
    api('POST', '/api/jarvis/session/title', { id: sid, title: text.slice(0, 60) })
      .then(() => jarvisLoadSessions()).catch(() => { });
  }

  // eyes: if a share is live and the words reference seeing, ride the frame along.
  // Broad on purpose — a miss leaves JARVIS blind and he may improvise (e.g. try
  // to shell into the frames dir), so cover common perception phrasings too.
  let frame = null, frameKind = null;
  const wantsEyes = /\b(see|look|looking|watch|read(ing)?|this|screen|camera|webcam|showing|show you|holding|wearing|colou?r|describe|what am i|what'?s this|what is this|in front|behind me|point(ing)? (at|to)|front of)\b/i.test(text);
  if (wantsEyes) {
    const cap = jarvisState.capture.webcam || jarvisState.capture.screen;
    if (cap) {
      const grab = jarvisCaptureGrab(cap);
      frame = grab && grab.luma >= 8 ? grab.dataUrl : null;  // never show him black
      frameKind = jarvisState.capture.webcam === cap ? 'webcam' : 'screen';
      if (frame) jarvisAddMessage('tool', '👁 Showing JARVIS the current frame…');
      else if (grab) jarvisAddMessage('tool', '👁 The current camera frame is black — not sending it.');
    }
  }

  try {
    const resp = await fetch('/api/jarvis/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(frame ? { input: text, frame_b64: frame, frame_kind: frameKind }
                                 : { input: text }),
      signal: jarvisState.abortController.signal,
    });

    if (!resp.ok) {
      // a non-2xx (expired session → 401, server error → 500) is NOT an
      // overload — surface the real status instead of the generic message
      let detail = '';
      try {
        const raw = await resp.text();
        try { detail = JSON.parse(raw).error || raw; } catch { detail = raw; }
      } catch { /* unreadable body — status alone will have to do */ }
      throw new Error(`HTTP ${resp.status}${detail ? ` — ${String(detail).slice(0, 180)}` : ''}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentEvent = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          await jarvisHandleSSE(currentEvent, line.slice(6).trim(), liveMsg);
        }
      }
    }
    liveMsg.live = false;

    if (!liveMsg.text.trim()) {
      const i = jarvisState.messages.indexOf(liveMsg);
      if (i >= 0) jarvisState.messages.splice(i, 1);
      jarvisAddMessage('error',
        '⚠ No reply arrived — the AI provider is overloaded right now (peak-time load shedding). Wait a few seconds and send it again.');
    } else {
      jarvisSpeakProgress(liveMsg, true);   // flush the unspoken tail
    }
  } catch (e) {
    if (e.name === 'AbortError') {
      liveMsg.text += ' [stopped]';
    } else {
      const i = jarvisState.messages.indexOf(liveMsg);
      if (i >= 0 && !liveMsg.text.trim()) jarvisState.messages.splice(i, 1);
      jarvisAddMessage('error', `Stream error: ${e.message} — try again.`);
    }
    liveMsg.live = false;
  } finally {
    jarvisState.streaming = false;
    jarvisState.abortController = null;
    jarvisRenderFeed();
    if (sendBtn) sendBtn.disabled = false;
    if (stopBtn) stopBtn.style.display = 'none';
    if (jarvisState.mode === 'thinking') jarvisSetMode(jarvisState.ttsAnimating ? 'talking' : 'idle');
  }
}

// speak completed sentences as they stream in; final=true flushes the rest
function jarvisSpeakProgress(liveMsg, final) {
  if (!jarvisState.voiceAvailable || !jarvisState.voiceOn) return;
  const unspoken = liveMsg.text.slice(liveMsg._spoken || 0);
  if (final) {
    if (unspoken.trim().length > 1) jarvisSpeak(unspoken);
    liveMsg._spoken = liveMsg.text.length;
    return;
  }
  const m = unspoken.match(/^[\s\S]*[.!?](?=\s|$)/);
  if (m && m[0].trim().length > 2) {
    jarvisSpeak(m[0]);
    liveMsg._spoken = (liveMsg._spoken || 0) + m[0].length;
  }
}

async function jarvisHandleSSE(event, data, liveMsg) {
  let parsed;
  try { parsed = JSON.parse(data); } catch { return; }

  switch (event) {
    case 'assistant.delta':
    case 'text_delta':
    case 'text':
      if (parsed.delta || parsed.text) {
        liveMsg.text += parsed.delta || parsed.text || '';
        jarvisSpeakProgress(liveMsg, false);
        jarvisRenderFeed();
      }
      break;
    case 'content_block_delta':
      if (parsed.delta?.text) {
        liveMsg.text += parsed.delta.text;
        jarvisSpeakProgress(liveMsg, false);
        jarvisRenderFeed();
      }
      break;
    case 'assistant.message':
    case 'message.complete':
      if (parsed.message?.content) {
        const c = parsed.message.content;
        const txt = typeof c === 'string' ? c : (Array.isArray(c) ? c.map(b => b.text || '').join('') : '');
        if (txt && !liveMsg.text) { liveMsg.text = txt; jarvisRenderFeed(); }
      }
      liveMsg.live = false;
      break;
    case 'tool.progress':
    case 'tool_use':
    case 'tool_call': {
      const toolName = parsed.name || parsed.tool || parsed.tool_name || 'tool';
      if (toolName && toolName !== '_thinking') {
        jarvisAddMessage('tool', `⚙ TOOL · ${toolName}`);
      }
      break;
    }
    case 'files':
      // server diffed the exchange folder after the turn — show what appeared
      if ((parsed.files || []).length) {
        jarvisAddMessage('tool', `📦 JARVIS produced ${parsed.files.length} file${parsed.files.length > 1 ? 's' : ''}:`,
          { files: parsed.files.map(f => f.name) });
        jarvisLoadFiles();
        if (jarvisState.deckOpen) jarvisLoadDeck();
      }
      break;
    case 'fallback':
      // primary model load-shed by the provider — this reply continues on the fallback model
      jarvisAddMessage('tool',
        `⚡ ${parsed.from || 'The usual model'} is overloaded right now — answering on ${parsed.to || 'the fallback model'} instead.`);
      break;
    case 'status':
      // server-side progress note (e.g. local vision analyzing an image)
      if (parsed.text) jarvisAddMessage('tool', parsed.text);
      break;
    case 'domain':
      // the Business Brain detected which craft domain this turn draws on
      jarvisSetDomain(parsed.domain, parsed.label);
      break;
    case 'run.completed':
    case 'message_complete':
    case 'done':
      liveMsg.live = false;
      break;
    case 'run.failed':
    case 'error': {
      const raw = parsed.error ?? parsed.detail ?? parsed.message ?? 'Unknown error';
      const msg = typeof raw === 'string' ? raw : (raw.message || JSON.stringify(raw).slice(0, 200));
      jarvisAddMessage('error',
        /429|1305|overload/i.test(msg)
          ? '⚠ The AI provider is overloaded right now (peak-time load shedding). Wait a few seconds and try again.'
          : msg);
      liveMsg.live = false;
      break;
    }
  }
}

function jarvisStopStreaming() {
  if (jarvisState.abortController) jarvisState.abortController.abort();
  jarvisStopTTS();
}

// ── recording + adaptive VAD (auto-detects when you stop talking) ──
function jarvisMaybeAutoListen() {
  if (jarvisState.conversationMode && !jarvisState.recording && !jarvisState.streaming
      && jarvisState.voiceAvailable && currentView === 'jarvis') {
    jarvisStartRecording();
  }
}

async function jarvisStartRecording() {
  if (!jarvisState.voiceAvailable) {
    jarvisAddMessage('error', 'Voice pipeline not available');
    return;
  }
  if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    jarvisAddMessage('error', 'Microphone needs a secure context. Open https://localhost:8777 or use HTTPS.');
    return;
  }
  // warm the shared STT worker while the user speaks — large-v3 loads in
  // ~4-8s, which the utterance + VAD hangover fully hides (fire-and-forget)
  fetch('/api/jarvis/stt/warm', { method: 'POST' }).catch(() => { });
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    jarvisState.micStream = stream;
    jarvisState.mediaRecorder = new MediaRecorder(stream);
    jarvisState.audioChunks = [];
    const ctx = jarvisAudioCtx();
    if (jarvisState._micSource) { try { jarvisState._micSource.disconnect(); } catch { } }
    const micSource = ctx.createMediaStreamSource(stream);
    jarvisState._micSource = micSource;
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    micSource.connect(analyser);
    jarvisState.micAnalyser = analyser;
    jarvisState._micData = new Uint8Array(analyser.fftSize);
    // adaptive VAD: noise floor calibrates itself from the ambient signal
    jarvisState._vad = {
      startedAt: performance.now(), spokeAt: 0, floor: 0.008, spoke: false,
    };
    jarvisMicLevelLoop();

    jarvisState.mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) jarvisState.audioChunks.push(e.data);
    };
    jarvisState.mediaRecorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop());
      jarvisState.micStream = null;
      jarvisHandleRecording();
    };
    jarvisState.mediaRecorder.start();
    jarvisState.recording = true;
    jarvisSetMode('listening');
  } catch (e) {
    jarvisAddMessage('error', `Mic error: ${e.message}`);
  }
}

async function jarvisStopRecording() {
  if (jarvisState.mediaRecorder && jarvisState.mediaRecorder.state === 'recording') {
    jarvisState.mediaRecorder.stop();
  }
  jarvisState.recording = false;
  if (jarvisState.mode === 'listening') jarvisSetMode('idle');
}

async function jarvisHandleRecording() {
  const blob = new Blob(jarvisState.audioChunks, { type: 'audio/webm' });
  if (blob.size < 2500) {   // nothing meaningful was said — don't bother STT
    if (jarvisState.mode === 'thinking') jarvisSetMode('idle');
    return;
  }
  jarvisSetMode('thinking');
  const formData = new FormData();
  formData.append('file', blob, 'speech.webm');
  try {
    const resp = await fetch('/api/jarvis/stt', { method: 'POST', body: formData });
    const data = await resp.json();
    const text = (data.text || '').trim();
    if (!text) {
      if (!jarvisState.conversationMode) jarvisAddMessage('error', 'No speech detected');
      jarvisSetMode('idle');
      return;
    }
    jarvisAddMessage('user', text);
    jarvisSendTextFromVoice(text);
  } catch (e) {
    jarvisAddMessage('error', `STT error: ${e.message}`);
    jarvisSetMode('idle');
  }
}

// voice goes through the same intent routing as typed text
function jarvisSendTextFromVoice(text) {
  const mImag = text.match(/^(?:create|generate|make|draw|paint)\s+(?:me\s+)?(?:an?\s+)?(?:image|picture|photo|drawing|illustration)\s+(?:of|showing|with)\s+(.+)/i);
  if (mImag) { jarvisImagine(mImag[1]); return; }
  const mFind = text.match(/\bwhen did (?:i|we|you)\b.*\b(?:show|see|saw|shown|watch)\b/i) ||
    text.match(/\b(?:search|find|look up|look for)\b.*\b(?:visual memory|you (?:have )?seen|i showed|screen history|camera history)\b/i);
  if (mFind) { jarvisVisionSearchModal(text, true); return; }
  jarvisStreamChat(text);
}

function jarvisMicLevelLoop() {
  if (!jarvisState.micAnalyser || !jarvisState.recording) {
    const el = $('#jMicLevel');
    if (el) el.style.width = '0%';
    if (window.Jarvis3D && jarvisState.mode !== 'talking') window.Jarvis3D.setLevel(0);
    return;
  }
  jarvisState.micAnalyser.getByteTimeDomainData(jarvisState._micData);
  let sum = 0;
  for (let i = 0; i < jarvisState._micData.length; i++) {
    const d = (jarvisState._micData[i] - 128) / 128;
    sum += d * d;
  }
  const rms = Math.sqrt(sum / jarvisState._micData.length);
  const el = $('#jMicLevel');
  if (el) el.style.width = Math.min(100, rms * 320) + '%';
  if (window.Jarvis3D) window.Jarvis3D.setLevel(rms * 7);

  const v = jarvisState._vad;
  if (v) {
    const now = performance.now();
    const speechThresh = Math.max(0.028, v.floor * 3.0);
    if (rms > speechThresh) {
      v.spoke = true;
      v.spokeAt = now;
    } else if (!v.spoke) {
      v.floor = v.floor * 0.92 + rms * 0.08;   // calibrate on ambient noise
    }
    // end-of-speech: hangover after the last speech burst (auto-send —
    // shorter leash hands-free, longer when the mic was clicked manually)
    const hang = jarvisState.conversationMode ? 1150 : 2100;
    if (v.spoke && now - v.spokeAt > hang) { jarvisStopRecording(); return; }
    // nothing said at all
    const patience = jarvisState.conversationMode ? 15000 : 9000;
    if (!v.spoke && now - v.startedAt > patience) {
      jarvisStopRecording();
      if (jarvisState.conversationMode) {
        jarvisState.conversationMode = false;
        const t = $('#jConvToggle');
        if (t) t.checked = false;
        toast('Conversation mode paused — nothing heard for a while', 'info');
      }
      return;
    }
  }
  requestAnimationFrame(jarvisMicLevelLoop);
}

// ── barge-in: while JARVIS talks in CONV mode, a live mic monitor watches for
//    the user's voice (echoCancellation strips JARVIS's own output) and cuts
//    playback so he immediately listens. ──
async function jarvisBargeMonitorStart() {
  if (currentView !== 'jarvis') return;  // never open the mic while detached (Option C)
  if (!jarvisState.conversationMode || jarvisState._barge || jarvisState.recording) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    const ctx = jarvisAudioCtx();
    const src = ctx.createMediaStreamSource(stream);
    const an = ctx.createAnalyser();
    an.fftSize = 512;
    src.connect(an);
    const data = new Uint8Array(an.fftSize);
    const st = { stream, src, an, data, hot: 0, gen: setInterval(() => {
      if (!jarvisState.ttsAnimating || !jarvisState.conversationMode) { jarvisBargeMonitorStop(); return; }
      an.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) { const d = (data[i] - 128) / 128; sum += d * d; }
      const rms = Math.sqrt(sum / data.length);
      st.hot = rms > 0.05 ? st.hot + 1 : 0;
      if (st.hot >= 5) {          // ~450ms of sustained speech = interrupt
        jarvisBargeMonitorStop();
        jarvisStopTTS();
        jarvisStartRecording();
      }
    }, 90) };
    jarvisState._barge = st;
  } catch { }
}

function jarvisBargeMonitorStop() {
  const b = jarvisState._barge;
  if (!b) return;
  jarvisState._barge = null;
  clearInterval(b.gen);
  try { b.src.disconnect(); } catch { }
  try { b.stream.getTracks().forEach(t => t.stop()); } catch { }
}

// ── webcam / screen share → SigLIP visual memory ──
function jarvisCaptureGrab(cap) {
  try {
    const v = cap.video;
    if (!v || v.readyState < 2) return null;
    const cv = document.createElement('canvas');
    const scale = Math.min(1, 768 / v.videoWidth);
    cv.width = Math.round(v.videoWidth * scale);
    cv.height = Math.round(v.videoHeight * scale);
    const g = cv.getContext('2d');
    g.drawImage(v, 0, 0, cv.width, cv.height);
    // mean luminance on a subsample — black-frame detector (IR/depth sensors,
    // privacy shutters and still-warming cams all deliver ~black)
    const d = g.getImageData(0, 0, cv.width, cv.height).data;
    let sum = 0, n = 0;
    for (let i = 0; i < d.length; i += 160) {
      sum += 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]; n++;
    }
    return { dataUrl: cv.toDataURL('image/jpeg', 0.82), luma: sum / Math.max(1, n) };
  } catch { return null; }
}

function jarvisSavedCam() {
  // last camera that actually delivered light (ideal: falls back if unplugged)
  const id = localStorage.getItem('jvCamId');
  return id ? { deviceId: { ideal: id } } : {};
}

// IR/depth sensors (face-unlock laptops enumerate them right next to the
// real webcam) deliver near-black frames. Probe shortly after start — if
// black, walk the other cameras and keep the first that actually shows light.
async function jarvisCamAutoFix(cap) {
  await new Promise(r => setTimeout(r, 1400));
  if (jarvisState.capture.webcam !== cap) return;
  const first = jarvisCaptureGrab(cap);
  if (first && first.luma >= 8) {
    try { localStorage.setItem('jvCamId', cap.stream.getVideoTracks()[0].getSettings().deviceId || ''); } catch { }
    return;
  }
  let devs = [];
  try { devs = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'videoinput'); } catch { }
  const curId = (cap.stream.getVideoTracks()[0].getSettings() || {}).deviceId;
  for (const d of devs) {
    if (!d.deviceId || d.deviceId === curId) continue;
    let s = null;
    try {
      s = await navigator.mediaDevices.getUserMedia({ video: { width: 960, deviceId: { exact: d.deviceId } } });
    } catch { continue; }
    const v = document.createElement('video');
    v.muted = true; v.playsInline = true; v.srcObject = s;
    await v.play().catch(() => { });
    await new Promise(r => setTimeout(r, 1100));
    const probe = jarvisCaptureGrab({ video: v });
    v.srcObject = null;
    if (jarvisState.capture.webcam !== cap) { try { s.getTracks().forEach(t => t.stop()); } catch { } return; }
    if (probe && probe.luma >= 8) {
      try { cap.stream.getTracks().forEach(t => t.stop()); } catch { }
      cap.stream = s;
      cap.video.srcObject = s;
      await cap.video.play().catch(() => { });
      s.getVideoTracks()[0].onended = () => jarvisCaptureStop('webcam');
      try { localStorage.setItem('jvCamId', d.deviceId); } catch { }
      jarvisAddMessage('tool', `🎥 The first camera delivered black frames (IR sensor?) — switched to "${(d.label || 'camera 2').slice(0, 48)}".`);
      return;
    }
    try { s.getTracks().forEach(t => t.stop()); } catch { }
  }
  toast('The camera only delivers black frames — check the privacy shutter or lighting', 'err');
}

async function jarvisCaptureToggle(kind) {
  if (jarvisState.capture[kind]) { jarvisCaptureStop(kind); return; }
  if (!jarvisState.visionAvailable) { toast('Vision memory is not available', 'err'); return; }
  try {
    const stream = kind === 'webcam'
      ? await navigator.mediaDevices.getUserMedia({ video: { width: 960, ...jarvisSavedCam() } })
      : await navigator.mediaDevices.getDisplayMedia({ video: true });
    const video = $('#jCapPreview');
    video.srcObject = stream;
    video.style.display = 'block';
    await video.play().catch(() => { });
    const cap = { stream, video, timer: null };
    jarvisState.capture[kind] = cap;
    stream.getVideoTracks()[0].onended = () => jarvisCaptureStop(kind);
    const period = kind === 'webcam' ? 4000 : 5000;
    let busy = false;
    cap.timer = setInterval(async () => {
      if (busy || currentView !== 'jarvis') return;
      const grab = jarvisCaptureGrab(cap);
      if (!grab) return;
      if (grab.luma < 8) {              // never index black frames
        cap.blacks = (cap.blacks || 0) + 1;
        if (cap.blacks === 3) toast('Camera frames are black — check the privacy shutter/lighting, or toggle the share to let JARVIS try another camera', 'err');
        return;
      }
      cap.blacks = 0;
      const dataUrl = grab.dataUrl;
      busy = true;
      try {
        const blob = await (await fetch(dataUrl)).blob();
        const fd = new FormData();
        fd.append('file', blob, 'frame.jpg');
        const r = await fetch(`/api/jarvis/vision/frame?kind=${kind}`, { method: 'POST', body: fd });
        const j = await r.json().catch(() => ({}));
        if (j.indexed) {
          const c = $('#jVisionChip');
          const n = c ? parseInt((c.textContent.match(/\d+/) || [])[0], 10) : NaN;
          if (c && !isNaN(n)) c.textContent = `👁 ${n + 1}`;
        }
      } catch { }
      busy = false;
    }, period);
    const btn = $(kind === 'webcam' ? '#jCamBtn' : '#jScreenBtn');
    if (btn) btn.classList.add('active');
    if (kind === 'webcam') jarvisCamAutoFix(cap);   // black-frame rescue
    jarvisAddMessage('tool', kind === 'webcam'
      ? '🎥 Webcam ON — JARVIS sees and remembers what you show him (say "look at this").'
      : '🖥 Screen share ON — JARVIS sees and remembers your screen (ask "what am I looking at?").');
  } catch (e) {
    toast(`${kind} share failed: ${e.message}`, 'err');
  }
}

function jarvisCaptureStop(kind) {
  const cap = jarvisState.capture[kind];
  if (!cap) return;
  jarvisState.capture[kind] = null;
  clearInterval(cap.timer);
  try { cap.stream.getTracks().forEach(t => t.stop()); } catch { }
  const other = jarvisState.capture[kind === 'webcam' ? 'screen' : 'webcam'];
  const video = $('#jCapPreview');
  if (video) {
    if (other) video.srcObject = other.stream;
    else { video.srcObject = null; video.style.display = 'none'; }
  }
  const btn = $(kind === 'webcam' ? '#jCamBtn' : '#jScreenBtn');
  if (btn) btn.classList.remove('active');
}

// "look at this file" — an image dropped straight onto the chat
async function jarvisLookAtFile(file) {
  const b64 = await new Promise((res) => {
    const r = new FileReader();
    r.onload = () => res(r.result);
    r.readAsDataURL(file);
  });
  jarvisAddMessage('user', `👁 [showed JARVIS an image: ${file.name}]`);
  jarvisSetMode('thinking');
  try {
    const r = await api('POST', '/api/jarvis/see', { image_b64: b64, prompt: '' });
    jarvisAddMessage('jarvis', r.description || '(no description)');
    jarvisSpeak(r.description || '');
    // index it too, so "when did I show you…" finds it later
    const blob = await (await fetch(b64)).blob();
    const fd = new FormData();
    fd.append('file', blob, 'upload.jpg');
    fetch('/api/jarvis/vision/frame?kind=upload', { method: 'POST', body: fd }).catch(() => { });
  } catch (e) {
    jarvisAddMessage('error', 'Vision failed: ' + e.message);
  }
  if (jarvisState.mode === 'thinking') jarvisSetMode('idle');
}

// ── vision memory search popup (scroll / select / copy) ──
async function jarvisVisionSearchModal(query, run) {
  showModal(`
    <div class="modal-head"><h2>👁 Visual memory</h2></div>
    <div class="modal-body">
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <input class="form-input" id="jvsQuery" placeholder="e.g. the red box · an error dialog · invoice pdf on screen" value="${esc(query || '')}">
        <button class="btn-primary" onclick="jarvisVisionSearchRun()">Search</button>
      </div>
      <div id="jvsResults" class="jvs-results"><div class="muted">Search everything JARVIS has seen through your camera and screen shares. Results show when he saw it, with the frame and any text he read in it.</div></div>
      <div class="modal-actions" style="justify-content:space-between">
        <button class="btn-sm danger" onclick="jarvisVisionForget()">🗑 Forget ALL visual memory</button>
        <div style="display:flex;gap:8px">
          <button class="btn-ghost" id="jvsCopyAll" style="display:none" onclick="jarvisVisionCopyAll()">⧉ Copy results</button>
          <button class="btn-primary" onclick="closeModal()">Close</button>
        </div>
      </div>
    </div>`);
  const inp = document.getElementById('jvsQuery');
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') jarvisVisionSearchRun(); });
  if (run && query) jarvisVisionSearchRun();
}

let _jvsLast = [];
async function jarvisVisionSearchRun() {
  const q = (document.getElementById('jvsQuery') || {}).value || '';
  const box = document.getElementById('jvsResults');
  if (!q.trim() || !box) return;
  box.innerHTML = '<div class="muted">Searching…</div>';
  try {
    const r = await api('POST', '/api/jarvis/vision/search', { query: q.trim(), limit: 18 });
    const hits = r.hits || [];
    _jvsLast = hits;
    document.getElementById('jvsCopyAll').style.display = hits.length ? 'inline-block' : 'none';
    if (!hits.length) {
      box.innerHTML = '<div class="muted">Nothing matched. JARVIS only remembers what was shared while 🎥/🖥 was on.</div>';
      return;
    }
    box.innerHTML = hits.map(h => `
      <div class="jvs-hit">
        <a href="/api/jarvis/vision/frame/${encodeURIComponent(h.file)}" target="_blank">
          <img src="/api/jarvis/vision/frame/${encodeURIComponent(h.file)}" loading="lazy"></a>
        <div class="jvs-meta">
          <div><b>${esc(h.when || '')}</b> <span class="chip ${h.kind === 'screen' ? 'c-cyan' : 'c-green'}">${esc(h.kind || '')}</span> <span class="muted">match ${(h.score * 100).toFixed(0)}%</span></div>
          ${h.note ? `<div class="jvs-note">you said: "${esc(h.note)}"</div>` : ''}
          ${h.ocr ? `<div class="jvs-ocr">${esc(h.ocr)}</div>` : ''}
          <button class="jv2-mini-btn" onclick="navigator.clipboard.writeText(${JSON.stringify('')}+this.closest('.jvs-hit').innerText).then(()=>toast('Copied','ok'))">⧉ copy</button>
        </div>
      </div>`).join('');
    const top = hits[0];
    jarvisAddMessage('jarvis', `I found ${hits.length} moment${hits.length > 1 ? 's' : ''} matching "${q.trim()}" — the closest is from ${top.when} (${top.kind}).`);
    jarvisSpeak(`I found ${hits.length} matching moment${hits.length > 1 ? 's' : ''}. The closest is from ${top.when}.`);
  } catch (e) {
    box.innerHTML = `<div class="muted">Search failed: ${esc(e.message)}</div>`;
  }
}

function jarvisVisionCopyAll() {
  const txt = _jvsLast.map(h =>
    `[${h.when}] (${h.kind}, ${(h.score * 100).toFixed(0)}%)${h.note ? ` note: ${h.note}` : ''}${h.ocr ? `\n  text seen: ${h.ocr}` : ''}`).join('\n');
  navigator.clipboard.writeText(txt).then(() => toast('Results copied', 'ok')).catch(() => { });
}

async function jarvisVisionForget() {
  if (!confirm('Erase EVERYTHING JARVIS has seen (all indexed frames)? This cannot be undone.')) return;
  try {
    const r = await api('DELETE', '/api/jarvis/vision');
    toast(`Forgot ${r.forgotten} frames`, 'ok');
    closeModal();
  } catch (e) { toast('Failed: ' + e.message, 'err'); }
}

// ── image generation (local SDXL-Turbo) ──
async function jarvisImagine(prompt) {
  jarvisAddMessage('tool', `🎨 Painting: "${prompt.trim()}" (local SDXL — first run loads the model, ~30s)…`);
  jarvisSetMode('thinking');
  try {
    const r = await api('POST', '/api/jarvis/imagine', { prompt: prompt.trim() });
    jarvisAddMessage('jarvis', `Here's "${prompt.trim().slice(0, 80)}" — saved to the file exchange as ${r.name}.`,
      { images: [r.url], files: [r.name] });
    jarvisSpeak('Done — the image is in your file exchange.');
    jarvisLoadFiles();
  } catch (e) {
    jarvisAddMessage('error', 'Image generation failed: ' + e.message);
  }
  if (jarvisState.mode === 'thinking') jarvisSetMode('idle');
}

// ── briefing + spoken task callbacks ──
async function jarvisMaybeBrief() {
  const today = new Date().toDateString();
  if (localStorage.getItem('jvBriefDate') === today) return;
  localStorage.setItem('jvBriefDate', today);
  jarvisBrief(false);
}

async function jarvisBrief(manual) {
  try {
    const r = await api('GET', '/api/jarvis/briefing');
    if (r.text) {
      jarvisAddMessage('jarvis', `📋 ${r.text}`);
      if (manual || jarvisState.voiceOn) jarvisSpeak(r.text);
    }
  } catch { }
}

async function jarvisPollEvents(gen) {
  if (gen !== jarvisState.eventsGen || currentView !== 'jarvis') return;
  try {
    const r = await api('GET', `/api/jarvis/events?since=${jarvisState.eventsSince}`);
    jarvisState.eventsSince = r.now || (Date.now() / 1000);
    for (const ev of (r.events || [])) {
      const line = ev.kind === 'completed'
        ? `✅ Task "${ev.title}" just finished.`
        : ev.kind === 'super_result'
          ? `✨ ${ev.title}`
          : `❌ Task "${ev.title}" failed — want me to look into it?`;
      jarvisAddMessage('tool', line);
      if (!jarvisState.ttsAnimating) jarvisSpeak(line.replace(/^[✅❌✨] /, ''));
    }
  } catch { }
  setTimeout(() => jarvisPollEvents(gen), 12000);
}


function showModal(html) {
  const c = $('#modalContent');
  // every popup carries its own ? — the topbar one is under the overlay
  if (c) c.innerHTML = html +
    '<button class="help-btn modal-help" onclick="startTour(currentView)" title="Explain this window step by step">?</button>';
  $('#modal').style.display = 'flex';
}
function closeModal() {
  const m = $('#modal');
  if (m) m.style.display = 'none';
  const c = $('#modalContent');
  if (c) c.classList.remove('modal-fs'); // next popup opens at normal size
  if (pendingRender && !uiLocked()) { pendingRender = false; render(); }
}

// ── Full-screen toggle for every popup. The observer (not showModal) injects the
//    button because many builders set #modalContent.innerHTML directly; the
//    .modal-fs class lives on #modalContent itself so it survives in-place
//    re-renders (wizard steps, onboarding) until closeModal resets it. ──
const MODAL_FS_MAX = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>';
const MODAL_FS_MIN = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>';
function toggleModalFS() {
  const c = $('#modalContent');
  if (!c) return;
  const on = c.classList.toggle('modal-fs');
  const b = document.getElementById('modalFsBtn');
  if (b) { b.innerHTML = on ? MODAL_FS_MIN : MODAL_FS_MAX; b.title = on ? 'Exit full screen' : 'Full screen'; }
}
function injectModalFsBtn() {
  const c = $('#modalContent');
  if (!c || c.querySelector('#modalFsBtn')) return;
  const on = c.classList.contains('modal-fs');
  const b = document.createElement('button');
  b.id = 'modalFsBtn'; b.type = 'button';
  b.className = 'help-btn modal-fs-btn';
  b.title = on ? 'Exit full screen' : 'Full screen';
  b.setAttribute('aria-label', 'Toggle full screen');
  b.innerHTML = on ? MODAL_FS_MIN : MODAL_FS_MAX;
  b.onclick = toggleModalFS;
  c.appendChild(b);
}
(() => {
  const c = document.getElementById('modalContent');
  if (c) new MutationObserver(injectModalFsBtn).observe(c, { childList: true });
})();

// ═══════════════════════════════ SPECIALISTS ═══════════════════════════════
const specialistsState = { data: null, loading: false, fetched: false, tab: 'team' };
// Evals (Block 3 R3): fixed per-domain briefs scored by the judge vs the rubric
const evalsState = { corpus: null, runs: null, loading: false, fetched: false, pollTimer: null };
async function loadSpecialists() {
  if (specialistsState.loading) return;
  specialistsState.loading = true; render();
  try {
    const [s, p, sh] = await Promise.all([
      api('GET', '/api/specialists'),
      api('GET', '/api/lessons/pending').catch(() => ({ pending: [] })),
      api('GET', '/api/shared-context').catch(() => ({ memories: [] })),
    ]);
    specialistsState.data = s;
    specialistsState.pending = (p && p.pending) || [];
    specialistsState.shared = (sh && sh.memories) || [];
  }
  catch (e) { specialistsState.data = { error: String(e) }; }
  specialistsState.loading = false; specialistsState.fetched = true; render(); bindSpecialists();
}

function specInitials(name) {
  const parts = String(name || '?').split('-').filter(Boolean);
  return (parts[0] ? parts[0][0] : '?') + (parts[1] ? parts[1][0] : '');
}

const SPEC_GRADS = [
  'linear-gradient(135deg,#7c5cff,#22d3ee)', 'linear-gradient(135deg,#f472b6,#7c5cff)',
  'linear-gradient(135deg,#22d3ee,#4ade80)', 'linear-gradient(135deg,#fb923c,#f472b6)',
  'linear-gradient(135deg,#60a5fa,#5eead4)', 'linear-gradient(135deg,#fbbf24,#fb923c)',
];

function learningPipelineHTML(pendingCount) {
  const steps = [
    ['⚡', 'Task runs', 'a specialist executes work'],
    ['◎', 'Outcome captured', 'success or failure recorded'],
    ['✦', 'Insight extracted', 'the model proposes a lesson'],
    ['✋', 'You review', pendingCount ? `${pendingCount} waiting below` : 'approve · edit · reject'],
    ['◍', 'Lesson stored', 'saved to that specialist only'],
    ['↻', 'Recalled next task', 'behavior actually changes'],
  ];
  return `<div class="pipeline">${steps.map(([ico, name, sub], i) => `
    ${i ? '<div class="pipe-arrow">→</div>' : ''}
    <div class="pipe-step ${i === 3 && pendingCount ? 'hot' : ''}">
      <div class="pipe-ico">${ico}</div>
      <div class="pipe-name">${name}</div>
      <div class="pipe-sub">${sub}</div>
    </div>`).join('')}</div>`;
}

function specTabsHTML() {
  const runsRunning = (evalsState.runs || []).some(r => ['running', 'cancelling'].includes(r.status));
  return `<div class="subtabs" style="margin-bottom:12px">
    <button class="subtab ${specialistsState.tab === 'team' ? 'active' : ''}" data-spectab="team">🧑‍🔬 Team</button>
    <button class="subtab ${specialistsState.tab === 'evals' ? 'active' : ''}" data-spectab="evals">📏 Evals${runsRunning ? '<span class="n">▶</span>' : ''}</button>
  </div>`;
}

function viewSpecialists() {
  if (specialistsState.tab === 'evals') return specTabsHTML() + evalsTabHTML();
  const d = specialistsState.data;
  if (!specialistsState.fetched && !specialistsState.loading) loadSpecialists();
  if (specialistsState.loading || !d) return skeletonView();
  if (d.error) return `<div class="panel"><div class="empty">${esc(d.error)}</div></div>`;
  const specs = d.specialists || [];
  const pend = specialistsState.pending || [];
  const shared = specialistsState.shared || [];
  const totalLessons = specs.reduce((n, s) => n + (s.memory_count || 0), 0);

  const cards = specs.map((s, i) => `
    <div class="spec-card">
      <div class="spec-head">
        <div class="spec-avatar" style="background:${SPEC_GRADS[i % SPEC_GRADS.length]}">${esc(specInitials(s.name))}</div>
        <div style="flex:1;min-width:0">
          <div class="spec-name">${esc(s.name)}</div>
          <div class="spec-chips">
            ${(s.tools || []).map(t => `<span class="chip c-cyan">${esc(t)}</span>`).join('') || '<span class="chip">inherits all tools</span>'}
            <span class="chip c-accent">scope: ${esc(s.agent_id)}</span>
          </div>
        </div>
        <button class="btn-ghost spec-edit" data-name="${esc(s.name)}" style="flex-shrink:0">Edit rules</button>
      </div>
      <div class="spec-desc">${esc(s.description)}</div>
      <div class="spec-foot">
        <button class="btn-sm spec-lessons" data-name="${esc(s.name)}"><span class="lesson-count"><b>${s.memory_count}</b> learned ${s.memory_count === 1 ? 'lesson' : 'lessons'}</span> — manage</button>
      </div>
    </div>`).join('') || `<div class="empty"><span class="e-ico">⬡</span>No specialists defined yet. Add one — it becomes a reusable expert.</div>`;

  const pendPanel = pend.length ? `<div class="panel pending-panel" style="margin-bottom:16px">
    <div class="panel-header"><span class="panel-title">🎓 Proposed lessons — ${pend.length} awaiting your review</span></div>
    <div style="padding:6px 18px 12px">${pend.map(p => `<div class="lesson-row">
      <div style="flex:1">
        <div><b>${esc(p.specialist)}</b> <span class="chip ${p.similar_existing ? 'c-yellow' : 'c-green'}" style="margin-left:6px">${p.similar_existing ? 'similar exists' : 'novel'}</span>
          <span style="color:var(--text-faint);font-size:11px;font-family:var(--font-mono);margin-left:6px">confidence ${Math.round((p.confidence || 0) * 100)}%</span></div>
        <div style="font-size:12.5px;margin-top:5px"><b>Learned:</b> ${esc(p.insight)}</div>
        <div style="font-size:12.5px;margin-top:2px;color:var(--text-dim)"><b>Will apply:</b> ${esc(p.lesson)}</div>
      </div>
      <button class="btn-primary lesson-review" data-id="${esc(p.id)}" style="align-self:center;flex-shrink:0">Review</button>
    </div>`).join('')}</div></div>` : '';

  const sharedRows = shared.map(m => `<div class="lesson-row"><div style="font-size:12.5px">${esc(m.memory)}</div><button class="btn-icon shared-del" data-id="${esc(m.id)}" title="Remove">✕</button></div>`).join('')
    || '<div style="color:var(--text-faint);font-size:12.5px;padding:8px 0">No shared context yet — add facts every specialist should know.</div>';
  const sharedPanel = `<div class="panel" style="margin-bottom:16px">
    <div class="panel-header"><span class="panel-title">🌐 Shared team context</span><span style="font-size:10.5px;color:var(--text-faint)">every specialist reads these</span></div>
    <div style="padding:8px 18px 14px">
      ${sharedRows}
      <div style="margin-top:10px;display:flex;gap:8px"><input class="form-input" id="sharedText" placeholder="Add a shared fact…" style="flex:1"><button class="btn-primary" id="sharedAdd">Add</button></div>
    </div></div>`;

  return specTabsHTML() + `
    <div class="stats-strip">
      <div class="stat-card"><div class="stat-num" style="color:#b3a1ff">${specs.length}</div><div class="stat-label">Specialists</div></div>
      <div class="stat-card green"><div class="stat-num green">${totalLessons}</div><div class="stat-label">Lessons learned</div></div>
      <div class="stat-card ${pend.length ? 'orange' : ''}"><div class="stat-num" style="color:${pend.length ? 'var(--yellow)' : 'var(--text)'}">${pend.length}</div><div class="stat-label">Pending review</div></div>
      <div class="stat-card blue"><div class="stat-num" style="color:var(--blue)">${shared.length}</div><div class="stat-label">Shared facts</div></div>
    </div>
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px">
      <div class="view-intro" style="margin-bottom:0">Predefined experts Hermes reuses for recurring work (defined in <code>~/.hermes/agents/</code>, git-versioned). Each learns privately from its own tasks — the pipeline below shows how a lesson becomes behavior.</div>
      <button class="btn-primary" id="specNew" style="white-space:nowrap">+ Add specialist</button>
    </div>
    ${learningPipelineHTML(pend.length)}
    ${pendPanel}${sharedPanel}
    <div class="spec-grid">${cards}</div>`;
}

function newSpecialist() {
  showModal(`
    <h2>New specialist agent</h2>
    <div class="view-intro" style="margin-bottom:12px">Hermes will reuse this whenever a task matches the "when to use" description.</div>
    <div class="form-group"><label class="form-label">Name (lowercase-hyphen, e.g. instagram-post-writer)</label>
      <input class="form-input" id="nsName"></div>
    <div class="form-group"><label class="form-label">When to use it (this is what routes tasks to it)</label>
      <textarea class="form-textarea" id="nsDesc" style="height:52px"></textarea></div>
    <div class="form-group"><label class="form-label">Tools it may use (comma-separated: web, file, terminal)</label>
      <input class="form-input" id="nsTools" placeholder="web"></div>
    <div class="form-group"><label class="form-label">Standing rules (its playbook)</label>
      <textarea class="form-textarea" id="nsRules" style="height:120px"></textarea></div>
    <div class="form-hint" style="margin-bottom:10px">Not sure what to write? Fill only Name + "When to use it", then let the AI draft the whole definition — you review it before anything goes live.</div>
    <div class="modal-actions" style="justify-content:space-between">
      <button class="btn-ghost" id="nsWizard" title="AI drafts the complete definition from Name + purpose — you review, then create">✨ Draft with AI</button>
      <div style="display:flex;gap:10px">
        <button class="btn-ghost" onclick="closeModal()">Cancel</button>
        <button class="btn-primary" id="nsCreate">Create</button>
      </div>
    </div>`);
  const b = document.getElementById('nsCreate');
  if (b) b.onclick = () => createSpecialist();
  const w = document.getElementById('nsWizard');
  if (w) w.onclick = () => draftSpecialistWithAI();
}

async function draftSpecialistWithAI() {
  const name = ((document.getElementById('nsName') || {}).value || '').trim();
  const desc = ((document.getElementById('nsDesc') || {}).value || '').trim();
  const rules = ((document.getElementById('nsRules') || {}).value || '').trim();
  if (!/^[a-z0-9-]+$/.test(name)) { toast('Set a valid Name first (lowercase-hyphen)', 'err'); return; }
  if (!desc) { toast('Fill "When to use it" first — that\'s what the AI builds from', 'err'); return; }
  const w = document.getElementById('nsWizard');
  if (w) { w.disabled = true; w.textContent = '✨ Drafting… (~30–60s)'; }
  try {
    const r = await api('POST', '/api/specialists/wizard', {
      name, instruction: `When to use: ${desc}` + (rules ? `\nAdditional rules the owner wants: ${rules}` : '') });
    // hand the draft to the full editor for review + save
    showModal(`
      <h2>Review AI draft: ${esc(name)}</h2>
      <div class="view-intro" style="margin-bottom:10px">Nothing is live yet. Read it, adjust anything, then Create — the eval gate still checks it.</div>
      <textarea class="form-textarea" id="specContent" style="height:360px;font-family:var(--font-mono);font-size:12px">${esc(r.content)}</textarea>
      <div class="modal-actions">
        <button class="btn-ghost" onclick="closeModal()">Cancel</button>
        <button class="btn-primary" id="specSave">Create specialist</button>
      </div>`);
    const btn = document.getElementById('specSave');
    if (btn) btn.onclick = () => saveSpecialist(name);
  } catch (e) {
    toast('Wizard failed: ' + e.message, 'err');
    if (w) { w.disabled = false; w.textContent = '✨ Draft with AI'; }
  }
}

async function createSpecialist() {
  const name = (document.getElementById('nsName') || {}).value || '';
  const desc = (document.getElementById('nsDesc') || {}).value || '';
  const tools = ((document.getElementById('nsTools') || {}).value || '').split(',').map(t => t.trim()).filter(Boolean);
  const rules = (document.getElementById('nsRules') || {}).value || '';
  if (!/^[a-z0-9-]+$/.test(name.trim())) { toast('Name must be lowercase letters, numbers, and hyphens only.', 'err'); return; }
  const n = name.trim();
  const toolsLine = tools.length ? `tools: [${tools.join(', ')}]\n` : '';
  const content = `---\nname: ${n}\ndescription: ${desc.trim().replace(/\n/g, ' ')}\n${toolsLine}mem0_agent_id: ${n}\n---\n${rules.trim()}\n`;
  const btn = document.getElementById('nsCreate');
  if (btn) { btn.disabled = true; btn.textContent = 'Creating…'; }
  try {
    const r = await api('POST', '/api/specialists/save', { name: n, content });
    if (r && r.error) throw new Error(r.error);
    closeModal(); specialistsState.fetched = false;
    toast(`Specialist ${n} created`, 'ok');
    loadSpecialists();
  } catch (e) {
    toast('Failed: ' + e, 'err');
    if (btn) { btn.disabled = false; btn.textContent = 'Create'; }
  }
}

function bindSpecialists() {
  $$('[data-spectab]').forEach(el => {
    el.onclick = () => {
      specialistsState.tab = el.dataset.spectab;
      if (specialistsState.tab === 'evals' && !evalsState.fetched) loadEvals();
      render();
    };
  });
  if (specialistsState.tab === 'evals') { bindEvals(); return; }
  document.querySelectorAll('.spec-edit').forEach(el => {
    el.onclick = () => editSpecialist(el.getAttribute('data-name'));
  });
  document.querySelectorAll('.spec-lessons').forEach(el => {
    el.onclick = () => manageLessons(el.getAttribute('data-name'));
  });
  document.querySelectorAll('.lesson-review').forEach(el => {
    el.onclick = () => reviewLesson(el.getAttribute('data-id'));
  });
  const sn = document.getElementById('specNew');
  if (sn) sn.onclick = () => newSpecialist();
  const sa = document.getElementById('sharedAdd');
  if (sa) sa.onclick = () => addSharedContext();
  document.querySelectorAll('.shared-del').forEach(el => {
    el.onclick = () => deleteSharedContext(el.getAttribute('data-id'));
  });
}

async function addSharedContext() {
  const inp = document.getElementById('sharedText');
  const text = inp ? inp.value.trim() : '';
  if (!text) return;
  const btn = document.getElementById('sharedAdd');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  try { await api('POST', '/api/shared-context', { text }); specialistsState.fetched = false; toast('Shared fact added', 'ok'); loadSpecialists(); }
  catch (e) { toast('Failed: ' + e, 'err'); if (btn) { btn.disabled = false; btn.textContent = 'Add'; } }
}

async function deleteSharedContext(id) {
  try { await api('DELETE', `/api/shared-context/${id}`); specialistsState.fetched = false; loadSpecialists(); }
  catch (e) { toast('Failed: ' + e, 'err'); }
}

// ═══════════════════ EVALS (Block 3 R3) — measure prompt/playbook changes ═══════════════════
async function loadEvals() {
  if (evalsState.loading) return;
  evalsState.loading = true;
  try {
    const [c, r] = await Promise.all([api('GET', '/api/evals'), api('GET', '/api/evals/runs')]);
    evalsState.corpus = c.domains || [];
    evalsState.runs = r.runs || [];
    evalsState.fetched = true;
    evalsState.error = null;
  } catch (e) { evalsState.corpus = evalsState.corpus || []; evalsState.runs = evalsState.runs || []; evalsState.error = e.message; }
  evalsState.loading = false;
  if (currentView === 'specialists' && specialistsState.tab === 'evals' && !uiLocked()) render();
  evalsAutoPoll();
}

// While a run is executing, refresh every 8s so progress/scores appear live.
function evalsAutoPoll() {
  const active = (evalsState.runs || []).some(r => ['running', 'cancelling'].includes(r.status));
  if (active && !evalsState.pollTimer) {
    evalsState.pollTimer = setInterval(() => loadEvals(), 8000);
  } else if (!active && evalsState.pollTimer) {
    clearInterval(evalsState.pollTimer);
    evalsState.pollTimer = null;
  }
}

function runPct(r) { return r.score_max ? Math.round(100 * r.score_total / r.score_max) : null; }
const evWhen = ts => ts ? new Date(ts * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';

function evalsTabHTML() {
  if (!evalsState.fetched && !evalsState.loading) loadEvals();
  if (!evalsState.corpus) return skeletonView();
  const corpus = (evalsState.corpus || []).filter(d => d.cases.length || d.has_rubric);
  const runs = evalsState.runs || [];
  const activeRun = runs.find(r => ['running', 'cancelling'].includes(r.status));
  const byDomain = {};
  runs.filter(r => r.status === 'completed' && r.score_max)
    .forEach(r => { (byDomain[r.domain] = byDomain[r.domain] || []).push(r); }); // newest first
  const totalCases = corpus.reduce((n, d) => n + d.cases.length, 0);
  const cards = corpus.map(d => {
    const hist = byDomain[d.domain] || [];
    const pct = hist[0] ? runPct(hist[0]) : null;
    const dpct = hist[1] ? runPct(hist[0]) - runPct(hist[1]) : null;
    const trend = hist.slice(0, 5).reverse().map(runPct).join('% → ');
    return `
    <div class="agentic-card">
      <div class="card-head"><h3>📏 ${esc(d.domain)}</h3>
        ${pct != null ? `<span class="chip ${pct >= 75 ? 'c-green' : pct >= 55 ? 'c-orange' : 'c-red'}" title="last completed run, rubric score">${pct}%${dpct != null ? ` (${dpct >= 0 ? '+' : ''}${dpct} vs prev)` : ''}</span>` : '<span class="chip">never run</span>'}
      </div>
      <div class="card-body">
        <div style="font-size:12px;color:var(--text-dim)">${d.cases.length} fixed brief(s)${d.has_rubric ? '' : ' · <span style="color:var(--red,#f87171)">no RUBRIC.md — cannot score</span>'}</div>
        ${hist.length > 1 ? `<div style="font-size:11px;font-family:var(--font-mono);color:var(--text-faint);margin-top:4px" title="score history, oldest → newest">${trend}%</div>` : ''}
        <div style="margin-top:8px">
          <button class="btn-sm" style="border-color:var(--accent)" ${(!d.cases.length || !d.has_rubric || activeRun) ? 'disabled' : ''} onclick="evalsRunModal('${esc(d.domain)}')">▶ Run evals</button>
        </div>
      </div>
    </div>`;
  }).join('');
  const runRows = runs.slice(0, 20).map(r => {
    const pct = runPct(r);
    const st = { running: 'c-cyan', cancelling: 'c-orange', completed: 'c-green', failed: 'c-red', cancelled: '' }[r.status] || '';
    return `
    <div class="agentic-row" style="cursor:pointer" onclick="evalRunDetail('${esc(r.id)}')">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <strong>${esc(r.domain)}</strong>
        <span class="chip ${st}">${r.status === 'running' ? `running ${r.cases_done}/${r.cases_total}` : esc(r.status)}</span>
        ${pct != null ? `<span class="chip">${pct}% (${r.score_total}/${r.score_max})</span>` : ''}
        ${r.status === 'completed' ? `<span class="chip">${r.ship_count}/${r.cases_total} SHIP</span>` : ''}
        <span class="chip" title="config fingerprint — same hash = same playbook/rubric/specialist config">⚙ ${esc((r.fingerprint || {}).combined || '?')}</span>
        <span style="flex:1"></span>
        <span class="muted" style="font-size:11px">${evWhen(r.started_at)}</span>
        ${['running', 'cancelling'].includes(r.status) ? `<button class="btn-sm danger" onclick="event.stopPropagation();evalsCancel('${esc(r.id)}')">⏹ Cancel</button>` : ''}
      </div>
      ${r.notes ? `<div style="font-size:11.5px;color:var(--text-dim)">📝 ${esc(r.notes)}</div>` : ''}
      ${r.error ? `<div style="font-size:11.5px;color:var(--red,#f87171)">${esc(r.error)}</div>` : ''}
    </div>`;
  }).join('');
  const scored = runs.filter(r => r.status === 'completed' && r.score_max);
  return `
    <div class="stats-strip">
      <div class="stat-card"><div class="stat-num" style="color:#b3a1ff">${corpus.length}</div><div class="stat-label">Domains</div></div>
      <div class="stat-card blue"><div class="stat-num" style="color:var(--blue)">${totalCases}</div><div class="stat-label">Fixed briefs</div></div>
      <div class="stat-card green"><div class="stat-num green">${scored.length}</div><div class="stat-label">Scored runs</div></div>
      <div class="stat-card ${activeRun ? 'orange' : ''}"><div class="stat-num" style="color:${activeRun ? 'var(--yellow)' : 'var(--text)'}">${activeRun ? `${activeRun.cases_done}/${activeRun.cases_total}` : '—'}</div><div class="stat-label">Running now</div></div>
    </div>
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px">
      <div class="view-intro" style="margin-bottom:0">The eval corpus is a set of <strong>fixed briefs per domain</strong> (<code>~/knowledge/domains/&lt;domain&gt;/evals/</code>). A run executes each brief through the real task pipeline (playbook + specialist), then the <strong>frontier judge scores it against the domain rubric</strong>. Changed a playbook, rubric or specialist? Run the domain's evals and compare with the previous run — the ⚙ fingerprint tells you which config each score measured. Scores wobble between runs; read trends, not single points.</div>
      <button class="btn-ghost" id="evRefresh" style="white-space:nowrap">↻ Refresh</button>
    </div>
    ${evalsState.error ? `<div class="chip c-red" style="margin-bottom:10px">${esc(evalsState.error)}</div>` : ''}
    <div class="agentic-grid" style="margin-bottom:16px">${cards || '<div class="empty"><span class="e-ico">📏</span>No eval corpus found — add briefs under ~/knowledge/domains/&lt;domain&gt;/evals/.</div>'}</div>
    <div class="panel">
      <div class="panel-header"><span class="panel-title">Run history</span><span style="font-size:10.5px;color:var(--text-faint)">click a run for per-case scores + judge output</span></div>
      <div style="padding:8px 18px 14px;display:flex;flex-direction:column;gap:6px">${runRows || '<div style="color:var(--text-faint);font-size:12.5px;padding:8px 0">No runs yet — pick a domain above and press ▶ Run evals.</div>'}</div>
    </div>`;
}

function bindEvals() {
  const rb = $('#evRefresh');
  if (rb) rb.onclick = () => { evalsState.fetched = false; loadEvals(); };
}

function evalsRunModal(domain) {
  const d = (evalsState.corpus || []).find(x => x.domain === domain);
  if (!d) return;
  showModal(`
    <h2>▶ Run evals: ${esc(domain)}</h2>
    <div class="view-intro" style="margin-bottom:10px">Each brief runs through the REAL task pipeline (playbook + specialist), then the frontier judge scores the result against the ${esc(domain)} rubric. Cases run one after another — expect ~3–8 min per case.</div>
    ${d.cases.map(c => `
      <label style="display:flex;align-items:center;gap:8px;font-size:12.5px;margin-top:4px">
        <input type="checkbox" class="ev-case" data-id="${esc(c.id)}" checked>
        <strong>${esc(c.title)}</strong>
        ${c.specialist ? `<span class="chip c-cyan">${esc(c.specialist)}</span>` : ''}
        ${c.model ? `<span class="chip c-blue">${esc(c.model)}</span>` : ''}
      </label>`).join('')}
    <div class="form-group" style="margin-top:10px">
      <label class="form-label">📝 What changed since the last run? (stored on the run)</label>
      <input class="form-input" id="ev-notes" placeholder="e.g. rewrote PLAYBOOK proof-density rules">
    </div>
    <div class="form-hint">Costs real GLM tokens + one frontier-judge call per case.</div>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" id="ev-start">▶ Start run</button>
    </div>`);
  const b = $('#ev-start');
  if (b) b.onclick = async () => {
    const cases = $$('.ev-case').filter(x => x.checked).map(x => x.dataset.id);
    if (!cases.length) { toast('Pick at least one case', 'err'); return; }
    b.disabled = true; b.textContent = 'Starting…';
    try {
      await api('POST', '/api/evals/run', { domain, cases, notes: ($('#ev-notes') || {}).value || '' });
      closeModal();
      toast('Eval run started — it works case by case in the background', 'ok');
      evalsState.fetched = false;
      loadEvals();
    } catch (e) {
      toast('Start failed: ' + e.message, 'err');
      b.disabled = false; b.textContent = '▶ Start run';
    }
  };
}

async function evalRunDetail(id) {
  let d;
  try { d = await api('GET', `/api/evals/runs/${id}`); }
  catch (e) { toast('Load failed: ' + e.message, 'err'); return; }
  const r = d.run;
  const results = d.results || [];
  const pct = runPct(r);
  const rows = results.map(x => `
    <div class="agentic-row">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <strong>${esc(x.case_title || x.case_id)}</strong>
        <span class="chip ${{ scored: 'c-green', judging: 'c-cyan', generating: 'c-cyan', error: 'c-red' }[x.status] || ''}">${esc(x.status)}</span>
        ${x.verdict ? `<span class="chip ${x.verdict === 'SHIP' ? 'c-green' : 'c-orange'}">${esc(x.verdict)}</span>` : ''}
        ${x.score != null ? `<span class="chip">${x.score}/${x.score_max}</span>` : ''}
        ${x.gates_failed ? `<span class="chip c-red">${x.gates_failed} gate FAIL</span>` : ''}
        ${x.specialist ? `<span class="chip c-cyan">${esc(x.specialist)}</span>` : ''}
        ${x.tokens_used ? `<span class="muted" style="font-size:11px">${Math.round(x.tokens_used / 1000)}k tok</span>` : ''}
        ${x.deliverable_path ? `<a class="btn-sm" style="text-decoration:none" href="/api/evals/runs/${esc(r.id)}/file?case=${encodeURIComponent(x.case_id)}" target="_blank">📄 deliverable</a>` : ''}
      </div>
      ${x.error ? `<div style="font-size:11.5px;color:var(--red,#f87171)">${esc(x.error)}</div>` : ''}
      ${x.judge_output ? `<details style="margin-top:4px"><summary style="cursor:pointer;font-size:11.5px;color:var(--text-dim)">judge output</summary><pre style="white-space:pre-wrap;font-size:11px;max-height:300px;overflow:auto">${esc(x.judge_output)}</pre></details>` : ''}
    </div>`).join('');
  const fp = r.fingerprint || {};
  showModal(`
    <h2>📏 Eval run — ${esc(r.domain)} ${pct != null ? `<span class="chip ${pct >= 75 ? 'c-green' : 'c-orange'}">${pct}%</span>` : ''}</h2>
    <div class="view-intro" style="margin-bottom:6px">${esc(r.notes || 'no notes recorded — next time say what changed, future-you will thank you')}</div>
    <div style="font-size:11px;font-family:var(--font-mono);color:var(--text-faint);margin-bottom:8px">config ⚙ ${esc(fp.combined || '?')} · playbook ${esc(fp.playbook || '—')} · rubric ${esc(fp.rubric || '—')} · ${evWhen(r.started_at)}</div>
    <div style="display:flex;flex-direction:column;gap:6px;max-height:440px;overflow-y:auto">${rows || '<div class="empty">no cases</div>'}</div>
    <div class="modal-actions"><button class="btn-primary" onclick="closeModal()">Close</button></div>`);
}

async function evalsCancel(id) {
  try {
    await api('POST', `/api/evals/runs/${id}/cancel`);
    toast('Cancelling after the current case…', 'ok');
    loadEvals();
  } catch (e) { toast('Cancel failed: ' + e.message, 'err'); }
}

function reviewLesson(id) {
  const p = (specialistsState.pending || []).find(x => x.id === id);
  if (!p) return;
  const provenance = p.similar_existing
    ? `<div style="font-size:12px;color:var(--yellow);margin-top:8px"><b>Similar existing memory:</b> ${esc(p.similar_existing)} (${Math.round((p.similarity || 0) * 100)}% similar) — approve only if this adds something.</div>`
    : `<div style="font-size:12px;color:var(--green);margin-top:8px">Novel — no similar memory exists.</div>`;
  showModal(`
    <h2 style="display:flex;align-items:center;gap:10px">Review lesson <span class="chip c-accent">${esc(p.specialist)}</span>
      <span class="chip">confidence ${Math.round((p.confidence || 0) * 100)}%</span></h2>
    <div style="font-size:13px;margin:8px 0"><b>What I learned:</b> ${esc(p.insight)}</div>
    <div style="font-size:13px;margin:8px 0"><b>How I'll apply it</b> (edit before approving if too broad):
      <textarea class="form-textarea" id="lessonEdit" style="margin-top:6px;height:70px">${esc(p.lesson)}</textarea></div>
    <div style="font-size:12px;color:var(--text-dim);margin:8px 0;background:rgba(7,7,13,.5);padding:10px;border-radius:8px;border:1px solid var(--border)"><b>Triggered by task:</b> ${esc(p.source_goal)}<br><b>Outcome:</b> ${esc(p.source_outcome)}</div>
    ${provenance}
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-sm danger" id="lessonReject" style="padding:8px 14px">Reject</button>
      <button class="btn-primary" id="lessonApprove">Approve</button>
    </div>`);
  const ap = document.getElementById('lessonApprove');
  const rj = document.getElementById('lessonReject');
  if (ap) ap.onclick = () => decideLesson(id, 'approve');
  if (rj) rj.onclick = () => decideLesson(id, 'reject');
}

async function decideLesson(id, action) {
  const body = { action };
  if (action === 'approve') { const ta = document.getElementById('lessonEdit'); if (ta) body.lesson = ta.value; }
  try {
    const r = await api('POST', `/api/lessons/${id}/decide`, body);
    if (r && r.ok === false) throw new Error(r.error || 'failed');
    closeModal(); specialistsState.fetched = false;
    toast(action === 'approve' ? 'Lesson stored' : 'Lesson rejected', 'ok');
    loadSpecialists();
  } catch (e) { toast('Failed: ' + e, 'err'); }
}

async function manageLessons(name) {
  const s = ((specialistsState.data || {}).specialists || []).find(x => x.name === name);
  if (!s) return;
  let archived = [];
  try { const a = await api('GET', `/api/specialists/${name}/archived`); archived = (a && a.archived) || []; } catch { /* ignore */ }
  const rows = (s.memories || []).map(m => `<div class="lesson-row">
      <div style="font-size:12.5px">${esc(m.memory)}<div class="lesson-meta">${esc((m.created_at || '').replace('T', ' ').slice(0, 16))}${m.source ? ' · ' + esc(m.source) : ''}</div></div>
      <button class="btn-icon lesson-del" data-id="${esc(m.id)}" title="Forget">✕</button>
    </div>`).join('') || '<div style="color:var(--text-faint);font-size:12.5px;padding:8px 0">No lessons yet — teach it something below.</div>';
  const archBlock = archived.length ? `<div style="margin-top:14px"><div style="font-size:11px;color:var(--text-dim);margin-bottom:4px">Archived (auto-retired: old &amp; never used — nothing is deleted, restore anytime):</div>${archived.map(m => `<div class="lesson-row" style="opacity:.7"><div style="font-size:12.5px">${esc(m.memory)}</div><button class="btn-ghost lesson-restore" data-id="${esc(m.id)}" style="padding:2px 10px;font-size:11px">restore</button></div>`).join('')}</div>` : '';
  showModal(`
    <h2>Lessons — ${esc(name)}</h2>
    <div class="view-intro" style="margin-bottom:10px">Curated memories this specialist recalls on its tasks. Only this specialist sees them.</div>
    <div style="max-height:300px;overflow-y:auto">${rows}${archBlock}</div>
    <div style="margin-top:14px;display:flex;gap:8px">
      <input class="form-input" id="lessonText" placeholder="Teach it a lesson…" style="flex:1">
      <button class="btn-primary" id="lessonAdd">Add</button>
      <button class="btn-ghost" onclick="closeModal()">Close</button>
    </div>`);
  const addb = document.getElementById('lessonAdd');
  if (addb) addb.onclick = () => addLesson(name);
  document.querySelectorAll('.lesson-del').forEach(el => { el.onclick = () => deleteLesson(name, el.getAttribute('data-id')); });
  document.querySelectorAll('.lesson-restore').forEach(el => { el.onclick = () => restoreLesson(name, el.getAttribute('data-id')); });
}

async function restoreLesson(name, id) {
  try { await api('POST', `/api/specialists/${name}/archived/${id}/restore`); specialistsState.fetched = false; await loadSpecialists(); manageLessons(name); }
  catch (e) { toast('Failed: ' + e, 'err'); }
}

async function addLesson(name) {
  const inp = document.getElementById('lessonText');
  const text = inp ? inp.value.trim() : '';
  if (!text) return;
  const btn = document.getElementById('lessonAdd');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  try {
    const r = await api('POST', `/api/specialists/${name}/memory`, { text });
    if (!r.ok) throw new Error(r.error || 'failed');
    specialistsState.fetched = false; await loadSpecialists(); manageLessons(name);
  } catch (e) {
    toast('Failed: ' + e, 'err');
    if (btn) { btn.disabled = false; btn.textContent = 'Add'; }
  }
}

async function deleteLesson(name, id) {
  try {
    await api('DELETE', `/api/specialists/${name}/memory/${id}`);
    specialistsState.fetched = false; await loadSpecialists(); manageLessons(name);
  } catch (e) { toast('Failed: ' + e, 'err'); }
}

function editSpecialist(name) {
  const s = ((specialistsState.data || {}).specialists || []).find(x => x.name === name);
  if (!s) return;
  showModal(`
    <h2>Edit specialist: ${esc(name)}</h2>
    <div class="view-intro" style="margin-bottom:10px">Frontmatter (name / description / tools) controls when it is used; the body below is its standing rules. Saved to git.</div>
    <div style="display:flex;gap:8px;margin-bottom:10px">
      <input class="form-input" id="specWizardAsk" style="flex:1" placeholder="✨ Describe a change in plain words, e.g. 'always answer in German' or 'add a pricing checklist'">
      <button class="btn-ghost" id="specWizardBtn" title="An AI drafts the revised definition into the editor — you review, then Save">✨ Ask AI to revise</button>
    </div>
    <textarea class="form-textarea" id="specContent" style="height:340px;font-family:var(--font-mono);font-size:12px">${esc(s.content)}</textarea>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" id="specSave">Save</button>
    </div>`);
  const btn = document.getElementById('specSave');
  if (btn) btn.onclick = () => saveSpecialist(name);
  const wb = document.getElementById('specWizardBtn');
  if (wb) wb.onclick = () => runSpecialistWizard(name);
}

async function runSpecialistWizard(name) {
  const ask = document.getElementById('specWizardAsk');
  const ta = document.getElementById('specContent');
  const wb = document.getElementById('specWizardBtn');
  const instruction = ask ? ask.value.trim() : '';
  if (!instruction) { toast('Describe the change first', 'err'); return; }
  if (wb) { wb.disabled = true; wb.textContent = '✨ Drafting… (~30–60s)'; }
  try {
    const r = await api('POST', '/api/specialists/wizard', {
      name, instruction, current_content: ta ? ta.value : '' });
    if (ta && ta.isConnected) {
      ta.value = r.content;
      toast('Draft ready — REVIEW the changes, then Save (nothing is live until you save)', 'ok');
    }
  } catch (e) { toast('Wizard failed: ' + e.message, 'err'); }
  if (wb) { wb.disabled = false; wb.textContent = '✨ Ask AI to revise'; }
}

async function saveSpecialist(name) {
  const ta = document.getElementById('specContent');
  const content = ta ? ta.value : '';
  const btn = document.getElementById('specSave');
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try {
    await api('POST', '/api/specialists/save', { name, content });
    closeModal(); specialistsState.fetched = false;
    toast('Specialist saved', 'ok');
    loadSpecialists();
  } catch (e) {
    toast('Save failed: ' + e, 'err');
    if (btn) { btn.disabled = false; btn.textContent = 'Save'; }
  }
}

// ═══════════════════ WORKFLOWS (Projects: task chains) ═══════════════════
const wfState = { list: null, fetched: false };
let taskCreateContext = null; // {workflow_id, depends_on} consumed by submitTask

async function loadWorkflows() {
  try { wfState.list = (await api('GET', '/api/workflows')).workflows || []; }
  catch { wfState.list = []; }
  wfState.fetched = true;
  if (currentView === 'workflows') render();
  else if (currentView === 'kanban') {
    // first kanban visit kicks this fetch off mid-paint — fill the project
    // filter in place (a full render would eat the user's search keystrokes)
    const sw = $('#kWorkflow');
    if (sw) sw.innerHTML = kanbanWorkflowOptions();
  }
}

// ── Mid-run replanning (R2): checkpoint state parsed off the workflow row ──
function parseReplan(w) {
  try {
    const r = JSON.parse(w.replan || 'null');
    return r && typeof r === 'object' ? r : null;
  } catch { return null; }
}

function replanChipHTML(w) {
  const rp = parseReplan(w);
  if (!rp) return '';
  if (rp.status === 'needed') return ' <span class="chip c-orange" title="a stage failed — open the project to replan">⚠ replan</span>';
  if (rp.status === 'drafting') return ' <span class="chip c-cyan" title="the wizard is drafting a recovery plan">✨ drafting…</span>';
  if (rp.status === 'proposed') return ' <span class="chip c-accent" title="a recovery plan awaits your review">📋 replan ready</span>';
  return '';
}

function viewWorkflows() {
  if (!wfState.fetched) { loadWorkflows(); return skeletonView(); }
  const wfIds = focusProjectWorkflowIds();
  const fp = focusCtx.project;
  const scoped = (wfState.list || []).filter(w =>
    !fp || w.project_path === fp.path || (wfIds && wfIds.has(w.id)));
  const scopeNote = fp ? `<div class="view-intro" style="margin-bottom:8px">Scoped to 📂 <b>${esc(fp.name)}</b> — ${scoped.length} of ${(wfState.list || []).length} workflows. <span class="fx" style="cursor:pointer;color:var(--accent-2)" onclick="setFocusProject(null)">show all</span></div>` : '';
  const rows = scoped.map(w => `
    <div class="agentic-card" style="cursor:pointer" onclick="openWorkflowDetail('${esc(w.id)}')">
      <div class="card-head"><h3>⚑ ${esc(w.name)}</h3>
        <button class="focus-btn" title="Work in this workflow: Tasks scopes to it; new tasks join it" onclick="event.stopPropagation(); setFocusWorkflow('${esc(w.id)}','${esc(w.name).slice(0, 40)}')">🎯 ${focusCtx.workflow && focusCtx.workflow.id === w.id ? 'focused' : 'focus'}</button>
        <button class="focus-btn" title="Run the complete assembled project — current state or any earlier one" onclick="event.stopPropagation(); projectAppUI('${esc(w.id)}','${esc(w.name).slice(0, 40)}')">▶ test</button>
        <span class="chip ${w.all_done ? 'c-green' : w.status === 'active' ? 'c-cyan' : ''}">${w.all_done ? 'complete' : esc(w.status)}</span>${replanChipHTML(w)}</div>
      <div class="card-body">
        ${w.goal ? `<div style="font-size:12.5px;color:var(--text-dim);margin-bottom:8px">${esc(w.goal)}</div>` : ''}
        <div class="agentic-row slim">
          <div class="cap-bar" style="flex:1"><div class="cap-fill" style="width:${w.progress_pct}%"></div></div>
          <span style="font-size:11px;font-family:var(--font-mono);color:var(--text-dim)">${w.tasks_done}/${w.tasks_total} done</span>
        </div>
        <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">
          ${w.domain ? `<span class="task-tag">${esc(w.domain)}</span>` : ''}
          ${Object.entries(w.tasks_by_status || {}).map(([s, n]) => `<span class="chip">${esc(s)}: ${n}</span>`).join('')}
        </div>
      </div>
    </div>`).join('');
  return `
    <div class="view-intro" style="margin-bottom:12px">A <strong>project</strong> connects several tasks into one campaign. Tasks with dependencies wait until their inputs are DONE, then run automatically — each agent reads its predecessors' deliverable files. Example: research → ad copy → channel plan → publish plan.</div>
    <div style="display:flex;gap:10px;margin-bottom:14px">
      <button class="btn-primary" onclick="newWorkflowUI()">➕ Create workflow</button>
      <button class="btn-ghost" title="Describe the whole goal in plain words — the AI plans the task chain" onclick="describeTaskUI()">✨ Describe a goal (AI plans it)</button>
      <button class="btn-ghost" title="Creates a ready-made 4-task marketing campaign chain — edit the [brackets], then watch it run in order" onclick="createExampleCampaign()">Example: marketing campaign</button>
    </div>
    ${scopeNote}
    <div class="agentic-grid">${rows || `<div class="empty"><span class="e-ico">⚑</span>${focusCtx.project ? 'No workflows in this project yet — ✨ Describe a goal creates the first round.' : 'No workflows yet — create one, or start from the example campaign.'}</div>`}</div>`;
}
function bindWorkflows() { /* inline onclick */ }

async function newWorkflowUI() {
  const name = prompt('Workflow name (e.g. "Q3 marketing campaign"):');
  if (!name || !name.trim()) return;
  const goal = prompt('Goal in one sentence (what does DONE look like?):') || '';
  await api('POST', '/api/workflows', {
    name: name.trim(), goal: goal.trim(),
    project_path: focusCtx.project ? focusCtx.project.path : null,
    client: focusCtx.project ? (focusCtx.project.client || null) : null,
  });
  wfState.fetched = false;
  toast(focusCtx.project
    ? `Workflow created in 📂 ${focusCtx.project.name} — open it and add tasks`
    : 'Workflow created — open it and add tasks', 'ok');
  render();
}

async function setWorkflowHighStakes(id, on) {
  try {
    await api('PATCH', `/api/workflows/${id}`, { high_stakes: on });
    state.tasks = await api('GET', '/api/tasks'); // member tasks changed too
    toast(on ? 'High stakes ON — applied to all tasks of this project' : 'High stakes off for this project', 'ok');
  } catch (e) { toast('Update failed: ' + e.message, 'err'); }
}

async function setWorkflowProject(id) {
  const v = $('#wfd-project') ? $('#wfd-project').value : '';
  try {
    await api('PATCH', `/api/workflows/${id}`, { project_path: v || null });
    wfState.fetched = false;
    state.tasks = await api('GET', '/api/tasks');
    toast(v ? '📂 Workflow linked to the project — it now appears under its focus' : 'Project link removed', 'ok');
  } catch (e) { toast('Update failed: ' + e.message, 'err'); }
}

async function setWorkflowClient(id) {
  const v = ($('#wfd-client') ? $('#wfd-client').value : '').trim().toLowerCase();
  try {
    await api('PATCH', `/api/workflows/${id}`, { client: v || null });
    state.tasks = await api('GET', '/api/tasks');
    toast(v ? `Client scope '${v}' applied to all tasks of this project` : 'Client scope removed', 'ok');
  } catch (e) { toast('Update failed: ' + e.message, 'err'); }
}

async function openWorkflowDetail(id) {
  let w;
  try { w = await api('GET', `/api/workflows/${id}`); }
  catch (e) { toast('Load failed: ' + e.message, 'err'); return; }
  state.tasks = await api('GET', '/api/tasks'); // fresh for task modals
  const depNames = t => {
    try {
      return (JSON.parse(t.depends_on || '[]')).map(d =>
        ((w.tasks || []).find(x => x.id === d) || {}).title || d);
    } catch { return []; }
  };
  const live = (w.tasks || []).filter(t => t.status !== 'archived');
  const archived = (w.tasks || []).filter(t => t.status === 'archived');
  const taskRow = (t, i) => `
    <div class="agentic-row" style="cursor:pointer${t.status === 'archived' ? ';opacity:.5' : ''}" onclick="closeModal();openTaskDetail('${esc(t.id)}')">
      <div><span class="muted" style="font-family:var(--font-mono)">${i + 1}.</span> <strong>${esc(t.title)}</strong>
        <span class="chip ${{ done: 'c-green', in_progress: 'c-cyan', review: 'c-orange' }[t.status] || ''}">${t.status === 'archived' ? 'superseded' : esc(t.status)}</span>
        ${dispatchChip(t)}
        ${superChip(t)}
        ${t.high_stakes ? '<span title="pauses for approval">⚖</span>' : ''}
        ${t.model ? `<span class="chip c-blue">${esc(t.model)}</span>` : ''}</div>
      ${depNames(t).length ? `<div style="font-size:11px;color:var(--text-faint)">⛓ waits for: ${depNames(t).map(esc).join(' · ')}</div>` : ''}
    </div>`;
  const taskRows = live.map(taskRow).join('')
    + (archived.length ? `
      <div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--text-faint);margin-top:6px">Superseded by replan (kept for audit)</div>
      ${archived.map(taskRow).join('')}` : '');
  const rp = parseReplan(w);
  const rpPanel = rp && ['needed', 'drafting', 'proposed'].includes(rp.status) ? `
    <div class="agentic-row" style="border-color:var(--orange,#fb923c);margin-bottom:8px">
      <div><strong>⚠ Replanning checkpoint</strong> <span class="chip c-orange">${esc(rp.status)}</span></div>
      <div style="font-size:12px;color:var(--text-dim);margin-top:4px">${esc(rp.reason || '')}</div>
      ${rp.error ? `<div style="font-size:11.5px;color:var(--red,#f87171);margin-top:4px">last draft failed: ${esc(rp.error)}</div>` : ''}
      <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;align-items:center">
        ${rp.status === 'proposed' ? `<button class="btn-primary sm" onclick="replanReviewModal('${esc(w.id)}')">📋 Review recovery plan (${((rp.proposal || {}).tasks || []).length} tasks)</button>` : ''}
        ${rp.status === 'drafting'
      ? '<span class="chip c-cyan">✨ drafting… (~1–3 min — this panel updates by itself)</span>'
      : `<button class="btn-sm" style="border-color:var(--accent)" onclick="replanDraftUI('${esc(w.id)}')">✨ ${rp.status === 'proposed' ? 'Draft again' : 'Draft a recovery plan'}</button>`}
        <button class="btn-ghost sm" onclick="replanDismissUI('${esc(w.id)}')">Dismiss — I'll handle it manually</button>
      </div>
    </div>` : '';
  showModal(`
    <h2 style="display:flex;align-items:center;gap:10px">⚑ ${esc(w.name)}
      <span class="chip ${w.all_done ? 'c-green' : 'c-cyan'}">${w.tasks_done}/${w.tasks_total} done</span></h2>
    ${w.goal ? `<div class="view-intro" style="margin-bottom:10px">${esc(w.goal)}</div>` : ''}
    ${rpPanel}
    <div style="display:flex;flex-direction:column;gap:6px;max-height:380px;overflow-y:auto">${taskRows || '<div class="empty">No tasks yet — add the first one.</div>'}</div>
    <div style="margin:8px 0;display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn-sm" style="border-color:var(--accent)" onclick="reviewWorkflowUI('${esc(w.id)}','${esc(w.name).slice(0, 50)}')">🔍 Review results — what every stage changed</button>
      <button class="btn-sm" style="border-color:var(--accent-2)" title="Run the complete assembled project — the current state or any earlier one, side by side" onclick="projectAppUI('${esc(w.id)}','${esc(w.name).slice(0, 50)}')">▶ Test project — run any version</button>
    </div>
    <div class="form-group" style="margin-top:10px"><label class="form-label">📎 Attachments (input files — attach to the whole project or to one task)</label>
      <div id="wf-attach"><span class="muted" style="font-size:11.5px">loading…</span></div></div>
    <div class="form-group"><label class="form-label">🔁 Project looping (automatic improve-and-recheck rounds)</label>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        ${loopBadgeHTML(parseLoopCfg(w.loop_config))}
        <button class="btn-sm" onclick="loopViewerModal('workflow','${esc(w.id)}','${esc(w.name).slice(0, 60)}')">🔁 View / edit loop</button>
      </div></div>
    <div class="form-group">
      <label style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" ${w.high_stakes ? 'checked' : ''}
          onchange="setWorkflowHighStakes('${esc(w.id)}', this.checked)">
        ⚖ High-stakes project
      </label>
      <div class="form-hint">Applies to ALL tasks of this project: every deliverable becomes eligible for the frontier judge. It runs automatically only when the loop is on quality + closed; otherwise it stays the manual judge button.</div>
    </div>
    <div class="form-group">
      <label class="form-label">📂 Project (this workflow's durable home)</label>
      <div style="display:flex;gap:8px;align-items:center">
        <select class="form-select" id="wfd-project" style="max-width:320px"><option value="">— none —</option></select>
        <button class="btn-sm" onclick="setWorkflowProject('${esc(w.id)}')">Set</button>
      </div>
      <div class="form-hint">Linking makes this workflow appear when the project is focused, and inherits the project's client scope. Legacy workflows from before the project system can be linked here.</div>
    </div>
    <div class="form-group">
      <label class="form-label">🏢 Client scope (memory isolation)</label>
      <div style="display:flex;gap:8px;align-items:center">
        <input class="form-input" id="wfd-client" value="${esc(w.client || '')}" placeholder="none — internal project" style="max-width:260px">
        <button class="btn-sm" onclick="setWorkflowClient('${esc(w.id)}')">Set</button>
      </div>
      <div class="form-hint">Applies to all tasks: their sessions read/write this client's private memory scope. Other clients and personal chats never see it.</div>
    </div>
    <div class="modal-actions" style="justify-content:space-between">
      <button class="btn-sm danger" onclick="deleteWorkflowUI('${esc(w.id)}')">Delete project (tasks stay)</button>
      <div style="display:flex;gap:10px">
        <button class="btn-ghost" onclick="addTaskToWorkflow('${esc(w.id)}')">+ Add task</button>
        <button class="btn-primary" onclick="closeModal()">Close</button>
      </div>
    </div>`);
  loadProjectAttachments(w.id, 'wf-attach');
  api('GET', '/api/projects').then(d => {
    const sel = document.getElementById('wfd-project');
    if (!sel) return;
    const ps = (d.projects || []).filter(x => x.is_repo);
    ps.sort((a, b2) => (b2.client ? 1 : 0) - (a.client ? 1 : 0));
    sel.innerHTML = '<option value="">— none —</option>' + ps.map(x =>
      `<option value="${esc(x.path)}">${x.client ? '🏢 ' + esc(x.client) + ' / ' : (x.personal ? '🏠 ' : '')}${esc(x.name)}</option>`).join('');
    if (w.project_path) sel.value = w.project_path;
  }).catch(() => { });
}

// ── Replanning actions (R2.2/R2.3): draft → review/edit → apply, all human-gated ──
async function replanDraftUI(id) {
  try {
    await api('POST', `/api/workflows/${id}/replan/draft`);
    closeModal();
    toast('Drafting a recovery plan — the wizard replans the remaining work (~1–3 min)', 'ok');
    replanPoll(id);
  } catch (e) { toast('Draft failed: ' + e.message, 'err'); }
}

function replanPoll(id) {
  let n = 0;
  const t = setInterval(async () => {
    if (++n > 40) { clearInterval(t); return; }
    try {
      const w = await api('GET', `/api/workflows/${id}`);
      const rp = parseReplan(w);
      if (rp && rp.status === 'drafting') return;
      clearInterval(t);
      wfState.fetched = false;
      if (rp && rp.status === 'proposed') {
        toast('Recovery plan ready — review it in the project panel', 'ok');
      } else if (rp && rp.error) {
        toast('Replan draft failed: ' + rp.error, 'err');
      }
      if (currentView === 'workflows' && !uiLocked()) render();
    } catch { /* transient — keep polling */ }
  }, 6000);
}

async function replanDismissUI(id) {
  if (!confirm('Dismiss this replanning checkpoint? It will not re-flag for the same failure — a new failure re-arms it.')) return;
  try {
    await api('POST', `/api/workflows/${id}/replan/dismiss`);
    wfState.fetched = false;
    toast('Checkpoint dismissed', 'ok');
    openWorkflowDetail(id);
  } catch (e) { toast('Failed: ' + e.message, 'err'); }
}

// The proposal opens in the SAME plan editor as the wizard (R1) — review,
// edit, then Apply archives the unfinished old tasks and creates the new ones.
async function replanReviewModal(id) {
  let w;
  try { w = await api('GET', `/api/workflows/${id}`); }
  catch (e) { toast('Load failed: ' + e.message, 'err'); return; }
  const rp = parseReplan(w);
  if (!rp || rp.status !== 'proposed' || !rp.proposal) { toast('No proposal to review', 'err'); return; }
  const doneTasks = (w.tasks || []).filter(t => t.status === 'done');
  planEd = {
    mode: 'replan', domain: w.domain || 'general', name: w.name,
    tasks: JSON.parse(JSON.stringify(rp.proposal.tasks || [])),
    keep: (rp.proposal.tasks || []).map(() => true),
    editing: null, edited: false,
    repairs: rp.proposal.repairs || [],
    roster: specialistNamesCache || [],
  };
  planEdLoadRoster().then(() => planEdRender());
  const doneRows = doneTasks.map(t => `
    <div class="agentic-row" style="opacity:.75">
      <div>✅ <strong>${esc(t.title)}</strong> <span class="chip c-green">done — kept</span></div>
    </div>`).join('');
  const assumptions = rp.proposal.assumptions || [];
  showModal(`
    <h2>📋 Recovery plan: ${esc(w.name)}</h2>
    <div class="view-intro" style="margin-bottom:8px">${esc(rp.reason || '')}</div>
    ${doneRows ? `<div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--text-faint);margin-bottom:4px">Kept from the old plan — their deliverables feed the new tasks</div><div style="display:flex;flex-direction:column;gap:6px;margin-bottom:8px">${doneRows}</div>` : ''}
    ${assumptions.length ? `<div style="font-size:12px;color:var(--warn,#eab308);margin-bottom:6px"><strong>Assumed:</strong><br>${assumptions.map(a => '· ' + esc(a)).join('<br>')}</div>` : ''}
    <div id="wfRepairs" style="font-size:11.5px;color:var(--text-faint);margin-bottom:6px"></div>
    <div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--text-faint);margin-bottom:4px">New recovery tasks — these replace every unfinished task</div>
    <div id="wfStages" style="display:flex;flex-direction:column;gap:6px;max-height:380px;overflow-y:auto"></div>
    <div style="margin-top:6px;display:flex;align-items:center;gap:8px">
      <button class="btn-sm" id="wfAddTask">➕ Add a task</button>
      <span class="form-hint" style="margin:0">Applying archives the old unfinished tasks (kept for audit) and creates these in Backlog.</span>
    </div>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" id="wfCreateBtn">Apply replan (${(rp.proposal.tasks || []).length} tasks)</button>
    </div>`);
  planEdRender();
  const addBtn = $('#wfAddTask');
  if (addBtn) addBtn.onclick = () => planEdAddTask();
  const b = $('#wfCreateBtn');
  if (b) b.onclick = async () => {
    if (planEd.editing != null) { toast('Finish the open ✏️ edit first', 'err'); return; }
    const finalTasks = planEdFinalTasks();
    if (!finalTasks.length) { toast('Keep at least one task', 'err'); return; }
    b.disabled = true; b.textContent = 'Applying…';
    try {
      const r = await api('POST', `/api/workflows/${id}/replan/apply`, { tasks: finalTasks });
      if ((r.repairs || []).length) toast('Plan checker adjusted the applied plan: ' + r.repairs.join(' · '), 'info');
      wfState.fetched = false;
      state.tasks = await api('GET', '/api/tasks');
      planEd = null;
      closeModal();
      toast('Replan applied — recovery tasks are in Backlog; move the first one to Todo to resume', 'ok');
      openWorkflowDetail(id);
    } catch (e) {
      toast('Apply failed: ' + e.message, 'err');
      b.disabled = false; b.textContent = 'Apply replan';
    }
  };
}

function addTaskToWorkflow(wfId) {
  // Preselect: new task joins this project and depends on its current LAST task
  const inWf = (state.tasks || []).filter(t => t.workflow_id === wfId);
  const last = inWf.length ? inWf[inWf.length - 1] : null;
  taskCreateContext = { workflow_id: wfId, depends_on: last ? [last.id] : [] };
  closeModal();
  showTaskModal('todo');
  setTimeout(() => toast(last
    ? `Task will join the project and wait for "${last.title}" (change under Depends-on after creating)`
    : 'Task will join the project', 'ok'), 200);
}

async function deleteWorkflowUI(id) {
  if (!confirm('Delete this project? Its tasks stay on the kanban board (only the grouping is removed).')) return;
  await api('DELETE', `/api/workflows/${id}`);
  wfState.fetched = false;
  closeModal();
  toast('Project deleted — tasks kept', 'ok');
  render();
}

async function createExampleCampaign() {
  if (!confirm('Create the example marketing-campaign project (4 chained tasks, prefilled with [brackets] to edit)? Nothing dispatches until the first task is in Todo with real content.')) return;
  const w = await api('POST', '/api/workflows', {
    name: 'Marketing campaign: [product]',
    goal: 'Research the market, produce ads, pick channels, and deliver a publish plan for [product].',
    domain: 'marketing' });
  const mk = (body) => api('POST', '/api/tasks', { status: 'backlog', workflow_id: w.id, ...body });
  const t1 = await mk({ title: 'Research: market + competitors for [product]',
    description: 'Research the market for [product]: target audience, 3-5 competitors (strengths/weaknesses/pricing), positioning gaps, and the 3 strongest angles we can own. Cite sources.',
    domain: 'research-learning', specialist: 'market-researcher' });
  const t2 = await mk({ title: 'Ad copy: 3 ad variants for [product]',
    description: 'Using the research, write 3 ad variants (headline, body, CTA) for [platform]. Mark which to ship and why.',
    domain: 'marketing', specialist: 'copywriter-specialist', high_stakes: true, depends_on: [t1.id] });
  const t3 = await mk({ title: 'Channel plan: where to publish for [product]',
    description: 'Using the research, recommend the 3 best channels/platforms to reach the audience, with budget split, format per channel, and expected outcomes.',
    domain: 'marketing', specialist: 'content-strategist', depends_on: [t1.id] });
  await mk({ title: 'Publish plan: schedule + checklist',
    description: 'Combine the ad variants and the channel plan into a 2-week publish schedule: what goes where when, who approves, and success metrics to track.',
    domain: 'marketing', high_stakes: true, depends_on: [t2.id, t3.id] });
  wfState.fetched = false;
  state.tasks = await api('GET', '/api/tasks');
  toast('Example campaign created (4 chained tasks in Backlog) — edit the [brackets], then move task 1 to Todo', 'ok');
  render();
}

// ═══════════════════ DELIVERABLES (all outputs, organized) ═══════════════════
const delState = { list: null, fetched: false, q: '' };

async function loadDeliverables() {
  try { delState.list = (await api('GET', '/api/deliverables')).deliverables || []; }
  catch { delState.list = []; }
  delState.fetched = true;
  if (currentView === 'deliverables') render();
}

function viewDeliverables() {
  if (!delState.fetched) { loadDeliverables(); return skeletonView(); }
  const q = delState.q.toLowerCase();
  const rows = (delState.list || [])
    .filter(d => !q || (d.title + ' ' + (d.domain || '') + ' ' + (d.workflow || '')).toLowerCase().includes(q))
    .map(d => {
      const judgeChip = { SHIP: 'c-green', REVISE: 'c-orange', REWRITE: 'c-red' }[d.judge_verdict];
      const criticChip = { SHIP: 'c-green', REVISE: 'c-orange', REWRITE: 'c-red', running: 'c-blue', error: 'c-red' }[d.critic_verdict];
      return `
      <div class="agentic-row">
        <div><strong>${esc(d.title)}</strong>
          <span class="chip ${{ done: 'c-green', review: 'c-orange' }[d.status] || ''}">${esc(d.status)}</span>
          ${judgeChip ? `<span class="chip ${judgeChip}">${esc(d.judge_verdict)}</span>` : ''}
          ${criticChip ? `<span class="chip ${criticChip}" title="Super Result grounded critic (round ${d.critic_round || 0})">✨ ${esc(d.critic_verdict)} r${d.critic_round || 0}</span>` : ''}
          ${d.workflow ? `<span class="task-tag" title="project">⚑ ${esc(d.workflow)}</span>` : ''}
          ${d.domain ? `<span class="task-tag">${esc(d.domain)}</span>` : ''}</div>
        <div style="font-size:11px;color:var(--text-dim);font-family:var(--font-mono)">
          ${fmtAgo(d.completed_at)} · ${fmtTokens(d.tokens_used || 0)} tok${d.model ? ' · ' + esc(d.model) : ''}</div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
          ${d.files.map(f => (f.name.endsWith('.md') || f.name.endsWith('.diff'))
            ? `<a href="#" onclick="previewDeliverable('${esc(d.task_id)}','${esc(f.name)}');return false" style="font-family:var(--font-mono);font-size:12px;color:var(--accent-2)">${f.name.endsWith('.diff') ? '🧬' : '📄'} ${esc(f.name)}</a>`
            : `<a href="/api/tasks/${esc(d.task_id)}/files/${encPath(f.name)}" target="_blank" style="font-family:var(--font-mono);font-size:12px;color:var(--accent-2)">📎 ${esc(f.name)}</a>`).join('')}
        </div>
        <div class="row-actions">
          ${d.app ? `<button class="btn-sm" style="border-color:var(--accent-2)" title="${esc(d.app.label)} — launches on its own local port and opens in a new tab" onclick="testAppUI('${esc(d.task_id)}','${esc(d.title).slice(0, 50)}')">▶ Test app</button>` : ''}
          <button class="btn-sm" onclick="openApprovalTask('${esc(d.task_id)}')">Open task</button>
          <button class="btn-sm" title="New task that uses this output as input" onclick="followUpTaskUI('${esc(d.task_id)}')">➡ Follow-up</button>
        </div>
      </div>`;
    }).join('');
  return `
    <div class="view-intro" style="margin-bottom:12px">Every file your agents produced, newest first. Click 📄 to read here, 📎 to download. <strong>➡ Follow-up</strong> hands a result to the next agent.</div>
    <div class="search-bar"><input id="delSearch" type="search" placeholder="Filter by title, domain, project…" value="${esc(delState.q)}"></div>
    <div style="display:flex;flex-direction:column;gap:8px;margin-top:10px">
      ${rows || '<div class="empty"><span class="e-ico">📦</span>No deliverables yet — dispatch a task and its output lands here.</div>'}
    </div>`;
}
function bindDeliverables() {
  const s = $('#delSearch');
  if (s) s.oninput = e => { delState.q = e.target.value; render(); setTimeout(() => { const x = $('#delSearch'); if (x) { x.focus(); x.setSelectionRange(x.value.length, x.value.length); } }, 0); };
}

// Q5 (uncertainty tagging): wrap [UNSURE: reason] spans — post-escape, so the
// input is already safe HTML — in an amber marker so the operator sees every
// claim the system flagged as unverified at a glance.
function highlightUnsure(escaped) {
  return (escaped || '').replace(/\[UNSURE:[^\]]*\]/g,
    '<span class="unsure-tag" title="The system flagged this claim as unverified against a primary source">$&</span>');
}

async function previewDeliverable(taskId, name) {
  try {
    const r = await fetch(`/api/tasks/${taskId}/files/${encPath(name)}`);
    const text = await r.text();
    showModal(`
      <h2>📄 ${esc(name)}</h2>
      <pre style="max-height:60vh;overflow-y:auto;white-space:pre-wrap;font-size:12.5px;font-family:var(--font-ui);line-height:1.55">${highlightUnsure(esc(text))}</pre>
      <div class="modal-actions">
        <a class="btn-ghost" href="/api/tasks/${esc(taskId)}/files/${encPath(name)}" download style="text-decoration:none">⬇ Download</a>
        <button class="btn-primary" onclick="closeModal()">Close</button>
      </div>`);
  } catch (e) { toast('Preview failed: ' + e.message, 'err'); }
}

// ═══════════════════ MEETINGS (dictation MeetingMode transcripts) ═══════════════════
const meetState = { list: null, fetched: false, live: null, dir: '', _poll: null };

async function loadMeetings(renderIfChanged = false) {
  const before = JSON.stringify([meetState.list, meetState.live]);
  try {
    const r = await api('GET', '/api/meetings');
    meetState.list = r.meetings || [];
    meetState.live = r.live || null;
    meetState.dir = r.dir || '';
  } catch { meetState.list = []; meetState.live = null; }
  meetState.fetched = true;
  if (currentView !== 'meetings') return;
  if (!renderIfChanged) { render(); return; }
  // poll path: repaint only on real change and never under an open modal
  if (JSON.stringify([meetState.list, meetState.live]) !== before && !uiLocked()) render();
}

const fmtBytes = (n) => n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';

function viewMeetings() {
  if (!meetState.fetched) { loadMeetings(); return skeletonView(); }
  const live = meetState.live;
  const rows = (meetState.list || []).map(m => `
    <div class="agentic-row">
      <div><strong>${esc(m.title || m.name)}</strong>
        ${m.name === live ? '<span class="chip c-red">● LIVE</span>' : ''}</div>
      <div style="font-size:11px;color:var(--text-dim);font-family:var(--font-mono)">
        ${fmtAgo(m.mtime)} · ${fmtBytes(m.size)} · ${esc(m.name)}</div>
      <div class="row-actions">
        <button class="btn-sm" onclick="previewMeeting('${esc(m.name)}')">📄 Read${m.name === live ? ' live' : ''}</button>
        ${m.name === live ? '' : `<button class="btn-sm" onclick="deleteMeeting('${esc(m.name)}')">🗑 Delete</button>`}
      </div>
    </div>`).join('');
  return `
    <div class="view-intro" style="margin-bottom:12px">Dual-channel meeting transcripts — 🎤 <strong>Me</strong> (your mic) and 🔊 <strong>Client</strong> (whatever is playing, e.g. the call) — from dictation's MeetingMode. Start one here, from the overlay button, or with the dictation hotkey during a meeting. Files live in <code>${esc(meetState.dir)}</code>.</div>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px">
      <button class="${live ? 'btn-ghost' : 'btn-primary'}" id="meetToggleBtn">${live ? '⏹ Stop meeting' : '● Start meeting'}</button>
      ${live ? `<span class="chip c-red">recording → ${esc(live)}</span>` : ''}
      <button class="btn-ghost" onclick="meetState.fetched=false;render()">↻ Refresh</button>
    </div>
    <div style="display:flex;flex-direction:column;gap:8px">
      ${rows || '<div class="empty"><span class="e-ico">🎙</span>No meeting transcripts yet — start a meeting and its live transcript appears here.</div>'}
    </div>`;
}

function bindMeetings() {
  const b = $('#meetToggleBtn');
  if (b) b.onclick = async () => {
    b.disabled = true;
    try {
      const r = await api('POST', '/api/dictation/meeting');
      toast(r.reply === 'meeting' ? 'Meeting started — transcript appears live' : ('Meeting: ' + (r.reply || 'ok')), 'ok');
      // the meeting session takes a moment to open its transcript file
      setTimeout(() => { if (currentView === 'meetings') loadMeetings(); }, 1200);
    } catch (e) { toast('Meeting toggle failed: ' + e.message, 'err'); }
    if (b.isConnected) b.disabled = false;
  };
  // while a meeting is live, keep the list fresh (self-clearing poller)
  if (meetState.live && !meetState._poll) {
    meetState._poll = setInterval(() => {
      if (currentView !== 'meetings' || !meetState.live) {
        clearInterval(meetState._poll); meetState._poll = null; return;
      }
      loadMeetings(true);
    }, 5000);
  }
}

async function previewMeeting(name) {
  try {
    const r = await api('GET', `/api/meetings/${encodeURIComponent(name)}`);
    showModal(`
      <h2>🎙 ${esc(name)} ${r.live ? '<span class="chip c-red">● LIVE</span>' : ''}</h2>
      <pre id="meetPreviewBody" style="max-height:60vh;overflow-y:auto;white-space:pre-wrap;font-size:12.5px;font-family:var(--font-ui);line-height:1.55">${esc(r.content)}</pre>
      <div class="modal-actions"><button class="btn-primary" onclick="closeModal()">Close</button></div>`);
    if (r.live) {
      // follow the growing transcript; self-clears when the modal closes or
      // the meeting ends (the element check makes leaks impossible)
      const t = setInterval(async () => {
        const el = document.getElementById('meetPreviewBody');
        if (!el) { clearInterval(t); return; }
        try {
          const u = await api('GET', `/api/meetings/${encodeURIComponent(name)}`);
          const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
          el.textContent = u.content;
          if (atBottom) el.scrollTop = el.scrollHeight;
          if (!u.live) clearInterval(t);
        } catch { clearInterval(t); }
      }, 4000);
    }
  } catch (e) { toast('Preview failed: ' + e.message, 'err'); }
}

async function deleteMeeting(name) {
  if (!confirm(`Delete ${name}? This cannot be undone.`)) return;
  try {
    await api('DELETE', `/api/meetings/${encodeURIComponent(name)}`);
    toast('Deleted', 'ok');
    meetState.fetched = false;
    if (currentView === 'meetings') render();
  } catch (e) { toast('Delete failed: ' + e.message, 'err'); }
}

// ═══════════════════ TASK WIZARD (describe → clarify → parameterized task/project) ═══════════════════
function describeTaskUI() {
  showModal(`
    <h2>✨ Describe what you want done</h2>
    <div class="view-intro" style="margin-bottom:10px">Plain words, German or English. The AI may ask up to 5 clarifying questions first (every one skippable), then plans: specialist, domain, model, priority, high-stakes flag and the full brief — you review before anything is created. Coding goals become the full pipeline (spec → implement → review → fix → verify) automatically.</div>
    <textarea class="form-textarea" id="twAsk" style="height:120px" placeholder="e.g. We have to develop our application. It has to be a webshop for clothing with a basket and payment…"></textarea>
    <div class="form-group" style="margin-top:8px">
      <label class="form-label">📂 About an existing project? (optional)</label>
      <select class="form-select" id="twRepo"><option value="">— No: something new —</option></select>
      <div class="form-hint">Pick the project and the AI plans an <strong>improvement round on the real thing</strong>: it reads the project's contents, skips questions the project already answers, and writes briefs that reference the existing work. Bug fixes and new features on client projects always go through here.</div>
    </div>
    <div class="form-group" style="margin-top:8px">
      <label style="display:flex;align-items:center;gap:8px"><input type="checkbox" id="twSuper"
        onchange="const o=$('#twSuperOpts'); if(o) o.style.display=this.checked?'block':'none'">
        ✨ Super Result</label>
      <div class="form-hint">A grounded frontier critic independently re-verifies every deliverable
        (full tool access in a disposable sandbox), files line comments, and loops the work until it
        verifies. ~5–10× tokens: independent verification rounds + fan-out.</div>
      <div id="twSuperOpts" style="display:none;margin-top:6px">
        <label style="display:flex;align-items:center;gap:8px;font-size:12.5px"><input type="checkbox" id="twFanout" checked>
          Fan out where parallelizable (independent perspectives cross-check each other, then a reconciler unifies)</label>
      </div>
    </div>
    <div class="form-hint" style="margin-top:6px">💡 This wizard only <strong>plans</strong> — the actual work happens later, inside the task it creates. Describe the goal and desired outcome (e.g. "a summary of what is on a picture"); if the work needs files, 📎 attach them to the created task afterwards.</div>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" id="twGo">✨ Plan it</button>
    </div>`);
  const twSel = $('#twRepo');
  if (twSel) {
    api('GET', '/api/projects').then(d => {
      pruneStaleFocus(d.projects);
      const ps = (d.projects || d || []).filter(x => x.is_repo);
      ps.sort((a, b2) => (b2.client ? 1 : 0) - (a.client ? 1 : 0));
      if (twSel.isConnected) {
        twSel.innerHTML += ps.map(x =>
          `<option value="${esc(x.path)}">${x.client ? '🏢 ' + esc(x.client) + ' / ' : (x.personal ? '🏠 ' : '')}${esc(x.name)}</option>`).join('');
        if (focusCtx.project) twSel.value = focusCtx.project.path; // focus context
      }
    }).catch(() => { });
  }
  const b = $('#twGo');
  if (b) b.onclick = async () => {
    const instruction = ($('#twAsk') || {}).value || '';
    if (!instruction.trim()) { toast('Describe it first', 'err'); return; }
    wizardCtx.repo_path = ($('#twRepo') || {}).value || null;
    wizardCtx.super_result = !!($('#twSuper') && $('#twSuper').checked);
    wizardCtx.fanout = wizardCtx.super_result ? !!($('#twFanout') && $('#twFanout').checked) : null;
    b.disabled = true; b.textContent = '✨ Planning… (up to ~3 min under load)';
    try {
      const r = await api('POST', '/api/tasks/wizard',
        { instruction: instruction.trim(), repo_path: wizardCtx.repo_path,
          super_result: wizardCtx.super_result, fanout: wizardCtx.fanout });
      handleWizardPlan(instruction.trim(), r);
    } catch (e) {
      toast('Wizard failed: ' + e.message, 'err');
      b.disabled = false; b.textContent = '✨ Plan it';
    }
  };
}

const wizardCtx = { repo_path: null, super_result: false, fanout: null };

// Route a wizard response: one question round, or straight to the plan preview.
function handleWizardPlan(instruction, r) {
  if (r.type === 'questions') { wizardQuestionsModal(instruction, r); return; }
  if (r.type === 'workflow') { proposeWorkflowModal(r.workflow, r); }
  else { closeModal(); applyWizardTask(r.task, r); }
}

// One round of clarifying questions — every question skippable with its default.
function wizardQuestionsModal(instruction, r) {
  const qs = r.questions || [];
  const optRow = (o, i) => {
    const label = typeof o === 'string' ? o : (o.label || '');
    const rec = typeof o === 'object' && o.recommended;
    const pros = (typeof o === 'object' && o.pros) || '';
    const cons = (typeof o === 'object' && o.cons) || '';
    return `
      <label style="display:block;font-size:12.5px;margin-top:5px;padding:6px 8px;border:1px solid ${rec ? 'var(--accent)' : 'var(--border, rgba(255,255,255,.08))'};border-radius:8px">
        <input type="radio" name="wq${i}" value="${esc(label)}" ${rec || label === qs[i].default ? 'checked' : ''}>
        <strong>${esc(label)}</strong>${rec ? ' <span class="chip c-cyan">★ recommended</span>' : ''}
        ${pros ? `<div style="font-size:11px;color:var(--ok,#4ade80);margin-left:20px">+ ${esc(pros)}</div>` : ''}
        ${cons ? `<div style="font-size:11px;color:var(--text-faint);margin-left:20px">− ${esc(cons)}</div>` : ''}
      </label>`;
  };
  const rows = qs.map((q, i) => `
    <div class="agentic-row">
      <div><strong>${esc(q.question)}</strong></div>
      ${q.why ? `<div style="font-size:11px;color:var(--text-faint)">${esc(q.why)}</div>` : ''}
      ${(q.options || []).map(o => optRow(o, i)).join('')}
      ${(q.options || []).length ? `<label style="display:block;font-size:12.5px;margin-top:5px"><input type="radio" name="wq${i}" value="__other__"> Other…</label>` : ''}
      <input class="form-input" id="wqOther${i}" style="margin-top:4px" placeholder="${(q.options || []).length ? 'Your own answer (pick Other above)' : esc('Answer — leave empty to use default: ' + q.default)}">
    </div>`).join('');
  showModal(`
    <h2>✨ Quick questions first</h2>
    ${r.preamble ? `<div class="view-intro" style="margin-bottom:8px">${esc(r.preamble)}</div>` : ''}
    <div style="display:flex;flex-direction:column;gap:6px;max-height:420px;overflow-y:auto">${rows}</div>
    <div class="form-hint" style="margin-top:8px">One round only — skipped questions use their default and show up as stated assumptions in the plan.</div>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-ghost" id="wqSkipAll">Skip all — use defaults</button>
      <button class="btn-primary" id="wqGo">✨ Answer & plan</button>
    </div>`);
  const submit = async (answers, btn) => {
    btn.disabled = true; btn.textContent = '✨ Planning… (up to ~3 min under load)';
    try {
      const r2 = await api('POST', '/api/tasks/wizard', { instruction, answers, repo_path: wizardCtx.repo_path,
        super_result: wizardCtx.super_result, fanout: wizardCtx.fanout });
      handleWizardPlan(instruction, r2);
    } catch (e) {
      toast('Wizard failed: ' + e.message, 'err');
      btn.disabled = false; btn.textContent = '✨ Answer & plan';
    }
  };
  const collect = () => qs.map((q, i) => {
    const sel = document.querySelector(`input[name="wq${i}"]:checked`);
    const other = (($(`#wqOther${i}`) || {}).value || '').trim();
    let val = '';
    if (sel && sel.value !== '__other__') val = sel.value;
    else val = other;
    const skipped = !val;
    return { id: q.id, question: q.question, answer: skipped ? q.default : val, skipped };
  });
  const go = $('#wqGo'), skip = $('#wqSkipAll');
  if (go) go.onclick = () => submit(collect(), go);
  if (skip) skip.onclick = () => submit(
    qs.map(q => ({ id: q.id, question: q.question, answer: q.default, skipped: true })), skip);
}

// Single task → prefill the normal create form for review
function applyWizardTask(t, meta) {
  if (meta && (meta.assumptions || []).length) {
    toast(`${meta.assumptions.length} assumption(s) embedded in the description — check them`, 'info');
  }
  taskCreateContext = null;
  showTaskModal('todo');
  setTimeout(() => {
    if ($('#m-task-title')) $('#m-task-title').value = t.title || '';
    if ($('#m-task-desc')) $('#m-task-desc').value = t.description || '';
    if ($('#m-task-domain')) $('#m-task-domain').value = t.domain || 'general';
    if ($('#m-task-highstakes')) $('#m-task-highstakes').checked = !!t.high_stakes;
    if ($('#m-task-super')) $('#m-task-super').checked = !!t.super_result;
    if ($('#m-task-model')) $('#m-task-model').value = t.model || '';
    if ($('#m-task-priority')) $('#m-task-priority').value = String(t.priority ?? 2);
    if ($('#m-task-budget') && t.budget_tokens) $('#m-task-budget').value = t.budget_tokens;
    if ($('#m-task-tags')) $('#m-task-tags').value = (t.tags || []).join(', ');
    if ($('#m-task-repo') && (meta && meta.repo_path)) {
      const rs = $('#m-task-repo');
      if (![...rs.options].some(o => o.value === meta.repo_path)) {
        rs.insertAdjacentHTML('beforeend', `<option value="${esc(meta.repo_path)}">${esc(meta.repo_path.split('/').slice(-2).join('/'))}</option>`);
      }
      rs.value = meta.repo_path;
    }
    const ssel = $('#m-task-specialist');
    if (ssel && t.specialist) {
      if (![...ssel.options].some(o => o.value === t.specialist)) {
        ssel.insertAdjacentHTML('beforeend', `<option value="${esc(t.specialist)}">${esc(t.specialist)}</option>`);
      }
      ssel.value = t.specialist;
    }
    toast('Review the plan — fill any [brackets], then Create', 'ok');
  }, 250);
}

// Stage number per task: 1 + max(stage of dependencies); parallel tasks share a stage.
function wizStages(tasks) {
  const level = [];
  tasks.forEach((t, i) => {
    const deps = (t.depends_on_idx || []).filter(d => d < i);
    level[i] = deps.length ? 1 + Math.max(...deps.map(d => level[d])) : 0;
  });
  return level;
}

// ═══════════ PLAN EDITOR (R1) — shared by wizard proposal + replan review ═══════════
// planEd holds the mutable plan while a proposal modal is open. The editor
// enforces the earlier-index invariant in the UI itself (deps pick from EARLIER
// tasks only); everything else — specialist whitelist, model floors, mandatory
// quality gates — is re-checked server-side by /api/tasks/wizard/revalidate.
let planEd = null;

async function planEdLoadRoster() {
  if (!specialistNamesCache) {
    try {
      const r = await api('GET', '/api/specialists/names');
      specialistNamesCache = (r.specialists || []).map(s => s.name);
    } catch { specialistNamesCache = []; }
  }
  if (planEd) { planEd.roster = specialistNamesCache; }
}

function planEdIsCoding() {
  return planEd.tasks.some((t, i) => planEd.keep[i] && t.specialist === 'code-implementer');
}
function planEdMandatory(i) {
  const t = planEd.tasks[i];
  return planEdIsCoding() &&
    (t.specialist === 'code-reviewer' || t.specialist === 'acceptance-verifier');
}

function planEdRowHTML(t, i) {
  const locked = planEdMandatory(i);
  return `
    <div class="agentic-row">
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
        <input type="checkbox" id="wfKeep${i}" ${planEd.keep[i] ? 'checked' : ''} ${locked ? 'disabled title="quality gate — required"' : ''}>
        <span class="muted" style="font-family:var(--font-mono)">${i + 1}.</span> <strong>${esc(t.title || '(untitled task)')}</strong>
        ${t.specialist ? `<span class="chip c-cyan">${esc(t.specialist)}</span>` : ''}
        ${t.high_stakes ? '<span title="pauses for approval">⚖</span>' : ''}
        ${t.super_result ? '<span class="chip c-accent" title="Super Result — grounded critic loop">✨SR</span>' : ''}
        ${t.deliverable_type ? `<span class="task-tag" title="deliverable type">${esc(t.deliverable_type)}</span>` : ''}
        ${t.model ? `<span class="chip c-blue">${esc(t.model)}</span>` : ''}
        <span class="task-tag">${esc(t.domain || 'general')}</span>
        ${locked ? '<span class="chip" title="quality gate — required">🔒 gate</span>' : ''}
        <span style="flex:1"></span>
        <button class="btn-icon pe-edit" data-i="${i}" title="Edit this task">✏️</button>
        ${t._added ? `<button class="btn-icon pe-del" data-i="${i}" title="Remove this task">🗑</button>` : ''}
      </div>
      ${(t.depends_on_idx || []).length ? `<div style="font-size:11px;color:var(--text-faint)">⛓ waits for: ${t.depends_on_idx.map(x => x + 1).join(', ')}</div>` : ''}
      <div style="font-size:11.5px;color:var(--text-dim);white-space:pre-wrap">${esc((t.description || '').slice(0, 220))}${(t.description || '').length > 220 ? '…' : ''}</div>
    </div>`;
}

function planEdEditorHTML(t, i) {
  const locked = planEdMandatory(i);
  const roster = planEd.roster || specialistNamesCache || [];
  const deps = new Set(t.depends_on_idx || []);
  const depBoxes = planEd.tasks.slice(0, i).map((d, di) => `
    <label style="display:inline-flex;align-items:center;gap:4px;font-size:11.5px;margin:2px 10px 2px 0">
      <input type="checkbox" class="pe-dep" data-d="${di}" ${deps.has(di) ? 'checked' : ''}> ${di + 1}. ${esc((d.title || '').slice(0, 40))}
    </label>`).join('') || '<span class="muted" style="font-size:11.5px">first task — nothing earlier to wait for</span>';
  return `
    <div class="agentic-row" style="border-color:var(--accent)">
      <div style="font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--text-faint)">✏️ Editing task ${i + 1}${locked ? ' — quality gate (specialist locked)' : ''}</div>
      <input class="form-input" id="pe-title" value="${esc(t.title || '')}" placeholder="Task title" style="margin-top:6px">
      <textarea class="form-textarea" id="pe-desc" style="height:110px;margin-top:6px" placeholder="Complete brief — the executing agent starts fresh and sees only this + predecessor deliverables">${esc(t.description || '')}</textarea>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
        <select class="form-select" id="pe-spec" style="max-width:220px" ${locked ? 'disabled' : ''}>
          <option value="">— Agent decides —</option>
          ${roster.map(n => `<option value="${esc(n)}" ${t.specialist === n ? 'selected' : ''}>${esc(n)}</option>`).join('')}
        </select>
        <select class="form-select" id="pe-domain" style="max-width:190px">
          ${NEXUS_DOMAINS.map(d => `<option value="${d}" ${(t.domain || 'general') === d ? 'selected' : ''}>${d}</option>`).join('')}
        </select>
        <select class="form-select" id="pe-model" style="max-width:230px">${taskModelOptions(t.model)}</select>
        <input class="form-input" id="pe-budget" type="number" min="0" step="100000" value="${t.budget_tokens || ''}" placeholder="token budget (default)" style="max-width:190px">
        <label style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px"><input type="checkbox" id="pe-hs" ${t.high_stakes ? 'checked' : ''}> ⚖ high-stakes</label>
        <label style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px" title="grounded critic loop on this task's deliverable (~5–10× tokens)"><input type="checkbox" id="pe-super" ${t.super_result ? 'checked' : ''}> ✨ Super Result</label>
        <select class="form-select" id="pe-dtype" style="max-width:170px" title="deliverable type (drives type-aware quality gates)">
          <option value="">type: auto</option>
          ${['analysis', 'code_change', 'content', 'research'].map(d => `<option value="${d}" ${t.deliverable_type === d ? 'selected' : ''}>${d}</option>`).join('')}
        </select>
      </div>
      <div style="margin-top:8px"><span style="font-size:11.5px;color:var(--text-faint)">⛓ waits for:</span><br>${depBoxes}</div>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:8px">
        <button class="btn-ghost sm" id="pe-cancel">Cancel</button>
        <button class="btn-primary sm" id="pe-save">Apply edit</button>
      </div>
    </div>`;
}

function planEdStagesHTML() {
  const tasks = planEd.tasks;
  const levels = wizStages(tasks);
  const maxLevel = levels.length ? Math.max(...levels) : 0;
  const out = [];
  for (let s = 0; s <= maxLevel; s++) {
    const members = tasks.map((t, i) => ({ t, i })).filter(x => levels[x.i] === s);
    if (!members.length) continue;
    out.push(`
      <div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--text-faint);margin-top:${s ? 8 : 0}px">${s ? '↓ ' : ''}Stage ${s + 1}${members.length > 1 ? ' (parallel)' : ''}</div>
      ${members.map(x => planEd.editing === x.i ? planEdEditorHTML(x.t, x.i) : planEdRowHTML(x.t, x.i)).join('')}`);
  }
  return out.join('');
}

function planEdRender() {
  const c = $('#wfStages');
  if (!c || !planEd) return;
  c.innerHTML = planEdStagesHTML();
  planEdBindStages();
  const b = $('#wfCreateBtn');
  if (b) b.textContent = (planEd.mode === 'replan' ? 'Apply replan' : 'Create project')
    + ` (${planEd.keep.filter(Boolean).length} tasks)`;
  const rb = $('#wfRepairs');
  if (rb) rb.innerHTML = (planEd.repairs || []).length
    ? `🔧 wizard auto-fixed: ${planEd.repairs.map(esc).join(' · ')}` : '';
}

function planEdBindStages() {
  planEd.tasks.forEach((_, i) => {
    const cb = $(`#wfKeep${i}`);
    if (cb) cb.onchange = () => { planEd.keep[i] = cb.checked; planEd.edited = true; planEdRender(); };
  });
  $$('.pe-edit').forEach(el => el.onclick = () => {
    if (planEd.editing != null) { toast('Finish the open edit first', 'err'); return; }
    planEd.editing = +el.dataset.i; planEdRender();
  });
  $$('.pe-del').forEach(el => el.onclick = () => planEdRemove(+el.dataset.i));
  const save = $('#pe-save'), cancel = $('#pe-cancel');
  if (cancel) cancel.onclick = () => {
    const i = planEd.editing;
    planEd.editing = null;
    const t = i != null ? planEd.tasks[i] : null;
    if (t && t._added && !(t.title || '').trim() && !(t.description || '').trim()) planEdRemove(i); // abandoned blank add
    else planEdRender();
  };
  if (save) save.onclick = () => {
    const i = planEd.editing;
    const t = planEd.tasks[i];
    const title = (($('#pe-title') || {}).value || '').trim();
    const desc = (($('#pe-desc') || {}).value || '').trim();
    if (!title) { toast('Give the task a title', 'err'); return; }
    if (!desc) { toast('Write the brief — the executing agent sees nothing else', 'err'); return; }
    t.title = title; t.description = desc;
    if (!planEdMandatory(i)) t.specialist = ($('#pe-spec') || {}).value || null;
    t.domain = ($('#pe-domain') || {}).value || 'general';
    t.model = ($('#pe-model') || {}).value || null;
    t.high_stakes = !!($('#pe-hs') || {}).checked;
    t.super_result = !!($('#pe-super') || {}).checked;
    t.deliverable_type = ($('#pe-dtype') || {}).value || null;
    const bud = parseInt(($('#pe-budget') || {}).value);
    t.budget_tokens = Number.isFinite(bud) && bud > 0 ? bud : null;
    t.depends_on_idx = $$('.pe-dep').filter(x => x.checked).map(x => +x.dataset.d).sort((a, b2) => a - b2);
    planEd.editing = null;
    planEd.edited = true;
    planEdRender();
  };
}

function planEdAddTask() {
  if (!planEd) return;
  if (planEd.editing != null) { toast('Finish the open edit first', 'err'); return; }
  const last = planEd.tasks.length - 1;
  planEd.tasks.push({
    title: '', description: '', domain: planEd.domain || 'general', specialist: null,
    high_stakes: false, super_result: false, deliverable_type: null,
    model: null, priority: 2, budget_tokens: null, tags: [],
    depends_on_idx: last >= 0 ? [last] : [], _added: true,
  });
  planEd.keep.push(true);
  planEd.editing = planEd.tasks.length - 1;
  planEd.edited = true;
  planEdRender();
}

function planEdRemove(i) {
  planEd.tasks.splice(i, 1);
  planEd.keep.splice(i, 1);
  planEd.tasks.forEach((t, j) => {
    if (j >= i) t.depends_on_idx = (t.depends_on_idx || []).filter(d => d !== i).map(d => d > i ? d - 1 : d);
  });
  if (planEd.editing === i) planEd.editing = null;
  else if (planEd.editing != null && planEd.editing > i) planEd.editing -= 1;
  planEd.edited = true;
  planEdRender();
}

// Unticked tasks are spliced out of the DAG: dependents inherit their
// dependencies (transitively), so the chain never breaks.
function planEdFinalTasks() {
  const { tasks, keep } = planEd;
  const eff = (i, seen) => {
    const out = new Set();
    for (const d of (tasks[i].depends_on_idx || [])) {
      if (seen.has(d)) continue;
      seen.add(d);
      if (keep[d]) out.add(d);
      else eff(d, seen).forEach(x => out.add(x));
    }
    return out;
  };
  const remap = {};
  let n = 0;
  tasks.forEach((_, i) => { if (keep[i]) remap[i] = n++; });
  return tasks.map((t, i) => ({ t, i })).filter(x => keep[x.i]).map(x => {
    const { _added, ...clean } = x.t;
    return { ...clean, depends_on_idx: [...eff(x.i, new Set())].map(d => remap[d]).sort((a, b2) => a - b2) };
  });
}

// Multi-step goal → staged DAG preview (assumptions + auto-repairs shown), full
// plan editing (R1), create on confirm
function proposeWorkflowModal(wf, meta) {
  const tasks = wf.tasks || [];
  const isCoding = tasks.some(t => t.specialist === 'code-implementer');
  planEd = {
    mode: 'wizard', domain: wf.domain || 'general', name: wf.name,
    tasks: JSON.parse(JSON.stringify(tasks)),
    keep: tasks.map(() => true),
    editing: null, edited: false,
    repairs: (meta && meta.repairs) || [],
    roster: specialistNamesCache || [],
  };
  planEdLoadRoster().then(() => planEdRender());
  const assumptions = (meta && meta.assumptions) || [];
  showModal(`
    <h2>✨ Proposed project: ${esc(wf.name)}</h2>
    <div class="view-intro" style="margin-bottom:8px">${esc(wf.goal || '')}</div>
    ${assumptions.length ? `<div style="font-size:12px;color:var(--warn,#eab308);margin-bottom:6px"><strong>Assumed:</strong><br>${assumptions.map(a => '· ' + esc(a)).join('<br>')}<br><span style="color:var(--text-faint)">Wrong assumption? Cancel and rephrase — or ✏️ edit the affected task right here.</span></div>` : ''}
    <div id="wfRepairs" style="font-size:11.5px;color:var(--text-faint);margin-bottom:6px"></div>
    <div id="wfStages" style="display:flex;flex-direction:column;gap:6px;max-height:420px;overflow-y:auto"></div>
    <div style="margin-top:6px;display:flex;align-items:center;gap:8px">
      <button class="btn-sm" id="wfAddTask">➕ Add a task</button>
      <span class="form-hint" style="margin:0">✏️ edit any task — the plan checker re-verifies edited plans (quality gates, wiring) before anything is created.</span>
    </div>
    ${isCoding ? `
    <div class="form-group" style="margin-top:8px">
      <label class="form-label">🧬 Existing code repository</label>
      <select class="form-select" id="wf-repo"><option value="">— None: fresh workspace (default) —</option></select>
      <div class="form-hint">Pick a repo and every coding stage works INSIDE it: isolated branch, the repo's own conventions and tests, and a reviewable diff as the deliverable. Your checkout is never touched.</div>
    </div>` : ''}
    <div class="form-group" style="margin-top:8px">
      <label class="form-label">🏢 Client (optional — isolates this project's memory)</label>
      <input class="form-input" id="wf-client" placeholder="e.g. acme — leave empty for internal work" style="max-width:340px">
      <div class="form-hint">With a client set, everything agents learn here is stored in that client's private memory scope: other clients' sessions (and your personal chats) can never see it. Generalized craft lessons still reach your specialists via the reviewed-lessons pipeline.</div>
    </div>
    <div class="form-group" style="margin-top:8px">
      <label style="display:flex;align-items:center;gap:8px"><input type="checkbox" id="wf-highstakes" ${tasks.some(t => t.high_stakes) ? 'checked' : ''}>
        ⚖ High-stakes project</label>
      <div class="form-hint">Marks every task as high-stakes: each deliverable becomes eligible for the frontier judge (a stronger AI grading against your quality rubric). The judge only runs automatically when the loop below is on quality + closed — otherwise it stays a button.</div>
    </div>
    <div class="form-group" style="margin-top:8px">
      <label style="display:flex;align-items:center;gap:8px"><input type="checkbox" id="wf-super" ${(wf.super_result || tasks.some(t => t.super_result)) ? 'checked' : ''}>
        ✨ Super Result</label>
      <div class="form-hint">A grounded frontier critic re-verifies each final deliverable with full tool access in a
        disposable sandbox, auto-fills the per-line review comments, and loops the work until it verifies.
        ~5–10× tokens: independent verification rounds + fan-out. ${tasks.some(t => t.super_result) ? 'This plan already fans out with a reconciler where useful.' : ''}</div>
    </div>
    <div class="form-group" style="margin-top:8px">
      <label class="form-label">🎚 Autopilot — how hands-on, and how much to spend</label>
      ${autopilotCardsHTML('wf', wf.autopilot, wf.spend_profile)}
    </div>
    <div class="form-group" style="margin-top:8px">
      <label class="form-label">🔁 Looping — automatic improve-and-recheck rounds</label>
      <div class="form-hint" style="margin-bottom:6px">${LOOP_INTRO_SHORT}</div>
      <label style="display:flex;align-items:center;gap:8px"><input type="checkbox" id="wf-loop" ${isCoding ? 'checked' : ''}
        onchange="const o=$('#wf-loop-opts'); if(o) o.style.display=this.checked?'block':'none'"> Enable looping for this project${isCoding ? ' <span class="chip c-cyan">recommended — this project has a final inspection stage</span>' : ''}</label>
      <div id="wf-loop-opts" style="display:${isCoding ? 'block' : 'none'};margin-top:8px">${loopPrefCardsHTML('wf')}
        <div class="form-hint" style="margin-top:4px">The loop is designed automatically for this exact project when you press Create — inspect and change it later via the project's 🔁 Loop settings.</div>
      </div>
    </div>
    <div class="form-group" style="margin-top:8px">
      <label class="form-label">📎 Attachments — project-wide input files (every task reads them)</label>
      ${attachStageHTML('wz-attach')}
    </div>
    <div class="form-hint" style="margin-top:8px">Tasks are created in <strong>Backlog</strong> so you can fill any [brackets] first. Move task 1 to Todo to start the chain.</div>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" id="wfCreateBtn">Create project (${tasks.length} tasks)</button>
    </div>`);
  planEdRender();
  attachStageWire('wz-attach');
  const addBtn = $('#wfAddTask');
  if (addBtn) addBtn.onclick = () => planEdAddTask();
  const b = $('#wfCreateBtn');
  // repo picker options (coding projects only)
  const repoSel = $('#wf-repo');
  if (repoSel) {
    api('GET', '/api/projects').then(d => {
      pruneStaleFocus(d.projects);
      const ps = (d.projects || d || []).filter(p => p.is_repo);
      ps.sort((a, b2) => (b2.client ? 1 : 0) - (a.client ? 1 : 0)); // client repos first
      if (!repoSel.isConnected) return;
      repoSel.innerHTML += ps.map(p =>
        `<option value="${esc(p.path)}" data-client="${esc(p.client || '')}">${p.client ? '🏢 ' + esc(p.client) + ' / ' : (p.personal ? '🏠 ' : '')}${esc(p.name)}</option>`).join('') +
        '<option value="__new__">➕ New client repository…</option>';
      repoSel.onchange = () => wfRepoChanged(repoSel);
      const pre = (meta && meta.repo_path) || wizardCtx.repo_path ||
        (focusCtx.project && focusCtx.project.path);
      if (pre && [...repoSel.options].some(o => o.value === pre)) {
        repoSel.value = pre;
        wfRepoChanged(repoSel); // autofills the client field
      }
    }).catch(() => { });
  }
  if (b) b.onclick = async () => {
    if (planEd.editing != null) { toast('Finish the open ✏️ edit first', 'err'); return; }
    let finalTasks = planEdFinalTasks();
    if (!finalTasks.length) { toast('Keep at least one task', 'err'); return; }
    // R1.3: an EDITED plan goes back through the deterministic plan checker
    // (same _repair_workflow that guards wizard output). If it changed
    // anything, show the repaired plan and let the operator confirm again.
    if (planEd.edited) {
      b.disabled = true; b.textContent = 'Checking the edited plan…';
      let r;
      try {
        r = await api('POST', '/api/tasks/wizard/revalidate', { name: wf.name, tasks: finalTasks });
      } catch (e) {
        toast('Plan check failed: ' + e.message, 'err');
        b.disabled = false; planEdRender(); return;
      }
      planEd.tasks = r.tasks || [];
      planEd.keep = planEd.tasks.map(() => true);
      planEd.edited = false;
      planEd.repairs = r.repairs || [];
      b.disabled = false;
      planEdRender();
      if ((r.repairs || []).length) {
        toast('The plan checker adjusted your edits — review, then press Create again', 'info');
        return;
      }
      finalTasks = planEdFinalTasks();
    }
    b.disabled = true; b.textContent = 'Creating…';
    const projHigh = !!($('#wf-highstakes') && $('#wf-highstakes').checked);
    const projSuper = !!($('#wf-super') && $('#wf-super').checked);
    // Ticked at the proposal stage on a plan the wizard made WITHOUT the flag:
    // flag the sink tasks (final results), same deterministic rule the wizard
    // applies server-side (§7a).
    if (projSuper && !finalTasks.some(t => t.super_result)) {
      const incoming = new Set(finalTasks.flatMap(t => t.depends_on_idx || []));
      finalTasks.forEach((t, i) => { if (!incoming.has(i)) t.super_result = true; });
    }
    if (!projSuper) finalTasks.forEach(t => { t.super_result = false; });
    const projClient = $('#wf-client') ? ($('#wf-client').value.trim().toLowerCase() || null) : null;
    const repo = $('#wf-repo') ? ($('#wf-repo').value || null) : null;
    const projAp = selectedAutopilot('wf');  // Q7a: two preset axes for the project
    const DEV_SPECIALISTS = new Set(['code-implementer', 'tech-lead-orchestrator',
      'code-reviewer', 'acceptance-verifier', 'debugger']);
    let wfLoop = null;
    if ($('#wf-loop') && $('#wf-loop').checked) {
      try {
        wfLoop = await designLoop('workflow', {
          preference: selectedLoopPref('wf'),
          mode: 'closed',
          meta: {
            title: wf.name, domain: wf.domain,
            specialists: finalTasks.map(t => t.specialist).filter(Boolean),
            high_stakes: projHigh || finalTasks.some(t => t.high_stakes),
            super_result: projSuper,
            autopilot: projAp.autopilot, spend_profile: projAp.spend_profile,
          },
        });
      } catch (e) { toast('Loop design failed (project created without loop): ' + e.message, 'err'); }
    }
    try {
      const w = await api('POST', '/api/workflows',
        { name: wf.name, goal: wf.goal, domain: wf.domain, loop_config: wfLoop,
          high_stakes: projHigh, client: projClient, super_result: projSuper,
          autopilot: projAp.autopilot, spend_profile: projAp.spend_profile,
          project_path: repo || (focusCtx.project && focusCtx.project.path) || null });
      const ids = [];
      for (const t of finalTasks) {
        const created = await api('POST', '/api/tasks', {
          title: t.title, description: t.description, status: 'backlog',
          priority: t.priority ?? 2, domain: t.domain, specialist: t.specialist,
          high_stakes: projHigh || !!t.high_stakes, model: t.model || null,
          super_result: !!t.super_result,
          deliverable_type: t.deliverable_type || null,
          autopilot: projAp.autopilot, spend_profile: projAp.spend_profile,
          budget_tokens: t.budget_tokens || null, tags: t.tags || [],
          workflow_id: w.id,
          // repo-native: coding stages work inside the chosen repo (they
          // share one branch, so review/fix/verify see each other's work)
          repo_path: repo && DEV_SPECIALISTS.has(t.specialist) ? repo : null,
          client: projClient,
          depends_on: (t.depends_on_idx || []).map(x => ids[x]).filter(Boolean),
        });
        ids.push(created.id);
      }
      const nAtt = await attachStageUploadAll('wz-attach', 'workflow', w.id);
      wfState.fetched = false;
      state.tasks = await api('GET', '/api/tasks');
      planEd = null;
      closeModal();
      toast(`Project "${wf.name}" created${nAtt ? ` with ${nAtt} project-wide file${nAtt > 1 ? 's' : ''}` : ''} — fill the [brackets], then move task 1 to Todo`, 'ok');
      switchView('workflows');
    } catch (e) {
      toast('Create failed: ' + e.message, 'err');
      b.disabled = false; b.textContent = 'Create project';
    }
  };
}

// ═══════════════════ HERMES SKILL WIZARD ═══════════════════
async function newSkillUI() {
  const name = prompt('Skill name (lowercase-hyphen, e.g. newsletter-writing):');
  if (name === null || !/^[a-z0-9_-]+$/.test(name.trim())) {
    if (name !== null) toast('Name must be lowercase letters/numbers/hyphens', 'err');
    return;
  }
  const instruction = prompt('What should this skill teach the agents to do? (plain words — the AI drafts the full skill)');
  if (instruction === null || !instruction.trim()) return;
  toast('✨ Drafting the skill… (~30–60s)', 'ok');
  try {
    const r = await api('POST', '/api/hermes-skills/wizard', { name: name.trim(), instruction: instruction.trim() });
    reviewSkillModal(name.trim(), r.content, true);
  } catch (e) { toast('Skill wizard failed: ' + e.message, 'err'); }
}

async function editHermesSkill(name) {
  try {
    const r = await api('GET', `/api/hermes-skills/${encPath(name)}`);
    reviewSkillModal(name, r.content, false);
  } catch (e) { toast('Load failed: ' + e.message, 'err'); }
}

function reviewSkillModal(name, content, isNew) {
  showModal(`
    <h2>${isNew ? 'Review AI-drafted skill' : 'Edit skill'}: ${esc(name)}</h2>
    <div class="view-intro" style="margin-bottom:10px">${isNew ? 'Nothing is live yet — read it, adjust, then Save.' : 'The description decides WHEN agents load this skill; the body is the how-to.'}</div>
    <div style="display:flex;gap:8px;margin-bottom:10px">
      <input class="form-input" id="skillWizardAsk" style="flex:1" placeholder="✨ Describe a change in plain words — the AI revises the draft">
      <button class="btn-ghost" id="skillWizardBtn">✨ Ask AI to revise</button>
    </div>
    <textarea class="form-textarea" id="skillContent" style="height:340px;font-family:var(--font-mono);font-size:12px">${esc(content)}</textarea>
    <div class="modal-actions">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" id="skillSaveBtn">${isNew ? 'Create skill' : 'Save'}</button>
    </div>`);
  const wb = $('#skillWizardBtn');
  if (wb) wb.onclick = async () => {
    const ask = $('#skillWizardAsk'); const ta = $('#skillContent');
    if (!ask || !ask.value.trim()) { toast('Describe the change first', 'err'); return; }
    wb.disabled = true; wb.textContent = '✨ Drafting… (~30–60s)';
    try {
      const r = await api('POST', '/api/hermes-skills/wizard',
        { name, instruction: ask.value.trim(), current_content: ta ? ta.value : '' });
      if (ta && ta.isConnected) { ta.value = r.content; toast('Draft updated — review, then Save', 'ok'); }
    } catch (e) { toast('Wizard failed: ' + e.message, 'err'); }
    wb.disabled = false; wb.textContent = '✨ Ask AI to revise';
  };
  const sb = $('#skillSaveBtn');
  if (sb) sb.onclick = async () => {
    const ta = $('#skillContent');
    sb.disabled = true; sb.textContent = 'Saving…';
    try {
      await api('POST', '/api/hermes-skills/save', { name, content: ta ? ta.value : '' });
      closeModal(); skillsState.fetched = false;
      toast(`Skill "${name}" saved — agents can use it from their next session`, 'ok');
      render();
    } catch (e) {
      toast('Save failed: ' + e.message, 'err');
      sb.disabled = false; sb.textContent = isNew ? 'Create skill' : 'Save';
    }
  };
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) closeModal();
});

// ===== BOOT =====
// Auth gate first: single-user machines fall straight through to init();
// multi-user setups see the login screen until a valid session exists.
bootAuth();
