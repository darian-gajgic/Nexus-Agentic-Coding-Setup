# Backend Architecture for Real-Time Dashboards

FastAPI + SQLite + psutil + real subprocess workers. Zero external infrastructure.

## Project structure

```
my-dashboard/
├── main.py              # entry point, uvicorn launch
├── server.py            # FastAPI app, all REST routes, WebSocket
├── database.py          # SQLite layer, schema, migrations, seed data
├── agent_manager.py     # process spawning, metrics collection, system stats
├── worker.py            # subprocess script each agent runs
├── requirements.txt     # fastapi, uvicorn[standard], psutil
├── nexus.db             # auto-created SQLite DB (WAL mode)
└── static/
    ├── index.html       # SPA shell: sidebar, topbar, modal container
    ├── app.js           # full frontend: router, views, API client, WS, charts
    └── style.css        # dark theme, CSS variables, component styles
```

## Minimal requirements.txt

```
fastapi
uvicorn[standard]
psutil
```

## Thread-safe SQLite pattern

SQLite connections are NOT thread-safe. FastAPI runs handlers across threads.
Use thread-local connections:

```python
import threading, sqlite3

_local = threading.local()

def get_conn():
    if not hasattr(_local, "conn"):
        conn = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn
```

The `check_same_thread=False` + thread-local combo means:
- Each thread gets its own connection (safe)
- Connections are reused within a thread (efficient)
- WAL mode allows concurrent reads from the web frontend while workers write

## Schema with safe migration

```python
def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            -- ... columns ...
        );
        -- other tables...
    """)

    # Safe migration: add columns to existing tables without dropping data
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(agents)").fetchall()}
    migrations = [
        ("tokens_in", "INTEGER DEFAULT 0"),
        ("current_task", "TEXT DEFAULT ''"),
    ]
    for col, typedef in migrations:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE agents ADD COLUMN {col} {typedef}")

    conn.commit()
    _seed_if_empty(conn)  # only seed on truly first run
```

## Seed-on-first-run pattern

```python
def _seed_if_empty(conn):
    count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    if count > 0:
        return  # already has data, don't re-seed
    # ... insert demo agents, tasks, programs, activity ...
```

This ensures the dashboard looks alive on first open but doesn't
overwrite user data on subsequent runs.

## Enriched endpoint pattern

Don't make the frontend do joins. Attach computed fields server-side:

```python
@app.get("/api/agents")
async def get_agents():
    return am.list_agents_enriched()

# In agent_manager.py:
def list_agents_enriched():
    agents = db.query_all("SELECT * FROM agents ORDER BY started_at DESC")
    now = time.time()
    for a in agents:
        prog = db.query_one("SELECT name FROM programs WHERE id = ?", (a.get("program_id"),))
        a["program_name"] = prog["name"] if prog else None
        m = db.query_one(
            "SELECT cpu, memory_mb FROM metrics WHERE agent_id = ? ORDER BY ts DESC LIMIT 1",
            (a["id"],))
        a["cpu"] = round(m["cpu"], 1) if m else 0.0
        a["uptime_s"] = round(now - a["started_at"], 0) if a.get("started_at") else 0
        a["heartbeat_age_s"] = round(now - a["last_heartbeat"], 0) if a.get("last_heartbeat") else 0
    return agents
```

## Aggregate stats endpoint

```python
@app.get("/api/stats")
async def get_stats():
    agents = db.query_all("SELECT * FROM agents")
    # ... compute status counts, token totals, task totals ...
    return {
        "system": am.get_system_stats(),  # psutil data
        "agents": {"total": len(agents), "by_status": agent_status},
        "tokens": {"total_in": total_in, "total_out": total_out},
        # ...
    }
```

## Background metrics collection

```python
def metrics_loop(stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            collect_metrics()
        except Exception as e:
            print(f"[metrics] error: {e}", file=sys.stderr)
        stop_event.wait(3)  # 3-second interval, interruptible

# Start on app startup:
@app.on_event("startup")
def startup():
    db.init_db()
    stop_event = threading.Event()
    t = threading.Thread(target=am.metrics_loop, args=(stop_event,), daemon=True)
    t.start()
    app.state.metrics_stop = stop_event
```

## System stats via psutil

```python
import psutil

def get_system_stats():
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    try:
        load1, load5, load15 = os.getloadavg()
    except (AttributeError, OSError):
        load1 = load5 = load15 = 0.0
    net = psutil.net_io_counters()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "cpu_count": psutil.cpu_count(),
        "load_avg": [round(load1, 2), round(load5, 2), round(load15, 2)],
        "mem_total_gb": round(mem.total / (1024**3), 1),
        "mem_used_gb": round(mem.used / (1024**3), 1),
        "mem_percent": mem.percent,
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "disk_used_gb": round(disk.used / (1024**3), 1),
        "disk_percent": disk.percent,
        "net_sent_mb": round(net.bytes_sent / (1024**2), 1),
        "net_recv_mb": round(net.bytes_recv / (1024**2), 1),
        "uptime": time.time() - psutil.boot_time(),
    }
```

## Worker subprocess script

Each agent/worker runs as a real OS process that writes heartbeats and
metrics to the shared SQLite DB:

```python
# worker.py
import sqlite3, time, random
DB_PATH = Path(__file__).parent / "nexus.db"

def main():
    agent_id = sys.argv[1]
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")

    tick = 0
    while True:
        tick += 1
        now = time.time()
        conn.execute("UPDATE agents SET last_heartbeat = ? WHERE id = ?", (now, agent_id))
        # simulate token consumption
        conn.execute("UPDATE agents SET tokens_in = tokens_in + ?, tokens_out = tokens_out + ? WHERE id = ?",
                     (random.randint(200, 1500), random.randint(100, 800), agent_id))
        # periodically log activity
        if tick % 5 == 0:
            conn.execute("INSERT INTO activity (ts, level, source, message) VALUES (?,?,?,?)",
                         (now, "info", agent_id, f"Completed task #{random.randint(100,999)}"))
            conn.execute("UPDATE agents SET tasks_completed = tasks_completed + 1 WHERE id = ?", (agent_id,))
        conn.commit()
        time.sleep(2)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: sys.exit(0)
```

## Serving static files + SPA route

```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC / "index.html").read_text()
```

## Restart procedure (for code changes)

When updating backend code, the server process must be killed and restarted:

```bash
# Find and kill
pkill -f "python3 main.py"
sleep 2

# Restart
cd ~/my-dashboard
source .venv/bin/activate
python3 main.py
```

For background servers managed by Hermes terminal, use `pkill -f "main.py"`.
The process might respawn from a background shell wrapper — verify with
`pgrep -af "main.py"` and `kill -9` the wrapper PID if needed.
