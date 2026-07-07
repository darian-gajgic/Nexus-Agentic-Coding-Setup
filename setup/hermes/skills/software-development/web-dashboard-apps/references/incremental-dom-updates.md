# Incremental DOM Updates for Real-Time Dashboard Views

The core technique for building real-time vanilla JS dashboards with Chart.js
without flicker, memory leaks, or broken animations.

## Root Cause of the Flicker Bug

The default SPA pattern for vanilla JS is to rebuild `innerHTML` on every render:

```javascript
// BROKEN PATTERN
function render() {
  const c = document.getElementById('content');
  if (currentView === 'agents') {
    c.innerHTML = viewAgents();    // wipes all DOM
    bindAgentCharts();             // creates NEW Chart instances
  }
}
setInterval(tick, 3000);  // tick() → render() every 3s
```

Each tick destroys every Chart.js canvas and creates a new one. Effects:
- **Visual flicker** — charts disappear and reappear every 3 seconds
- **Memory leak** — old Chart instances may not be garbage collected
- **Broken animations** — Chart.js entry animations restart every tick
- **Lost state** — scroll position, hover state, selection all wiped
- **Wasted CPU** — DOM creation + chart initialization is expensive

## The Fix: Build-Once-Patch-In-Place

### 1. Track whether the view has been built

```javascript
let agentsBuilt = false;

function switchView(view) {
  currentView = view;
  agentsBuilt = false;  // reset on any view switch
  render();
}
```

### 2. Build the full DOM only once

```javascript
function renderAgentsView() {
  if (!agentsBuilt) {
    // FULL BUILD: create HTML structure, then create charts
    document.getElementById('content').innerHTML = `
      <div class="agent-summary-bar">...</div>
      <div class="agent-grid" id="agentGrid">
        ${state.agents.map(a => agentCardHTML(a)).join('')}
      </div>
    `;
    agentsBuilt = true;
    // Create Chart.js instances AFTER DOM exists
    buildAgentCharts(state.agents);
  } else {
    // INCREMENTAL: patch text values, update chart data
    updateAgentCardsInPlace(state.agents);
  }
}
```

### 3. Give every dynamic element a stable ID

```javascript
function agentCardHTML(a) {
  return `
    <div class="agent-card" id="card-${a.id}">
      <span class="agent-status-badge" id="badge-${a.id}">${a.status}</span>
      <div class="agent-stat-val" id="completed-${a.id}">${a.tasks_completed}</div>
      <div class="agent-stat-val" id="cpu-${a.id}">${a.cpu.toFixed(1)}%</div>
      <canvas id="chart-${a.id}"></canvas>
      <span id="tok-total-${a.id}">${fmtTokens(a.tokens_in + a.tokens_out)}</span>
    </div>
  `;
}
```

### 4. Patch values in-place on each tick

```javascript
function updateAgentCardsInPlace(agents) {
  for (const a of agents) {
    // Check if this card exists (agent might be new)
    const card = document.getElementById(`card-${a.id}`);
    if (!card) {
      // New agent appeared — force full rebuild
      agentsBuilt = false;
      renderAgentsView();
      return;
    }

    // Patch text content
    const badge = document.getElementById(`badge-${a.id}`);
    if (badge) { badge.className = `agent-status-badge status-${a.status}`; badge.textContent = a.status; }

    const completed = document.getElementById(`completed-${a.id}`);
    if (completed) completed.textContent = a.tasks_completed;

    const cpu = document.getElementById(`cpu-${a.id}`);
    if (cpu) cpu.textContent = `${(a.cpu || 0).toFixed(1)}%`;

    // Update token bars (width transition via CSS)
    const barIn = document.getElementById(`tok-bar-in-${a.id}`);
    if (barIn) barIn.style.width = `${(a.tokens_in / (a.tokens_in + a.tokens_out)) * 100}%`;

    // Update chart in-place
    updateAgentChart(a);
  }
}
```

### 5. Persist chart instances, update data without destroying

Store Chart.js instances in a long-lived object, NOT in the DOM rebuild:

```javascript
let agentCharts = {};  // persists across ticks

async function buildAgentCharts(agents) {
  // Clean up old charts if any
  for (const k in agentCharts) {
    try { agentCharts[k].destroy(); } catch {}
    delete agentCharts[k];
  }

  for (const a of agents) {
    const canvas = document.getElementById(`chart-${a.id}`);
    if (!canvas) continue;
    const metrics = await api('GET', `/api/agents/${a.id}/metrics?limit=30`);

    agentCharts[a.id] = new Chart(canvas, {
      type: 'line',
      data: {
        labels: metrics.map((_, i) => i),
        datasets: [{
          data: metrics.map(m => m.cpu),
          borderColor: '#7c5cff',
          backgroundColor: 'rgba(124,92,255,.1)',
          borderWidth: 1.5, fill: true, tension: 0.4, pointRadius: 0,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 400, easing: 'easeOutQuart' },
        plugins: { legend: { display: false } },
        scales: { x: { display: false }, y: { display: false, beginAtZero: true } },
      },
    });
  }
}

async function updateAgentChart(a) {
  const chart = agentCharts[a.id];
  if (!chart) return;
  const metrics = await api('GET', `/api/agents/${a.id}/metrics?limit=30`);
  chart.data.datasets[0].data = metrics.reverse().map(m => m.cpu);
  chart.update('active');  // smooth animation, NOT destroy+recreate
}
```

### 6. Handle structural changes (new/deleted agents)

When an agent is spawned or deleted, the set of cards changes. Force rebuild:

```javascript
async function deleteAgent(id) {
  await api('DELETE', `/api/agents/${id}`);
  state.agents = await api('GET', '/api/agents');
  agentsBuilt = false;  // force full rebuild
  render();
}
```

Also detect during incremental update if an agent appeared that has no card:

```javascript
function updateAgentCardsInPlace(agents) {
  for (const a of agents) {
    const card = document.getElementById(`card-${a.id}`);
    if (!card) {
      agentsBuilt = false;  // new agent — need rebuild
      renderAgentsView();
      return;
    }
    // ... patch values
  }
}
```

## Chart.js update modes

- `chart.update('active')` — smooth animation, recommended for live data
- `chart.update('none')` — no animation, useful when you want instant snap
- `chart.update()` — default animation

For monitor-style continuous graphs, `'none'` is better (appends without
re-animating). For per-agent sparklines that get fully refreshed, `'active'`
gives a nicer effect.

## WebSocket vs Polling

- **WebSocket** (`/ws`) — use for instant notification of structural changes
  (agent created/deleted, task moved). On message, set `viewBuilt = false` and
  re-render.
- **Polling** (`setInterval(tick, 3000)`) — use for metric refreshes. This
  triggers the incremental update path, NOT a full rebuild.

```javascript
ws.onmessage = async (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === 'agent_created' || msg.type === 'agent_deleted') {
    state.agents = await api('GET', '/api/agents');
    agentsBuilt = false;  // structural change → full rebuild
  }
  render();
};
```

## Summary checklist

- [ ] View has a `viewBuilt` flag, reset on view switch and structural changes
- [ ] Every dynamic element has a stable ID: `id="field-${entity.id}"`
- [ ] Charts stored in a persistent object (`agentCharts = {}`), not recreated
- [ ] Tick path calls `updateInPlace()`, NOT `innerHTML =`
- [ ] Chart updates use `chart.update('active')`, not destroy+recreate
- [ ] Structural changes set `viewBuilt = false` to trigger full rebuild
- [ ] CSS transitions on bar widths use `transition: width .5s ease`
