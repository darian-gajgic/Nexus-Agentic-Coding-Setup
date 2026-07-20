"""NEXUS Agent OS — Agent Manager.

Spawns real OS subprocesses, tracks heartbeats, collects live metrics,
and manages the agent lifecycle.
"""
import os
import sys
import time
import json
import uuid
import signal
import subprocess
import threading
import psutil
from pathlib import Path

import database as db

# The agent worker script that runs as a real subprocess
WORKER_SCRIPT = Path(__file__).parent / "worker.py"

LOG_DIR = Path(__file__).parent / "logs"


def _worker_log(agent_id: str):
    """Append-mode log file for a lane's stdout+stderr. A PIPE that nothing
    reads deadlocks the worker once 64KB of tracebacks/warnings accumulate —
    it then looks 'stuck' and gets restart-looped by the watchdog."""
    LOG_DIR.mkdir(exist_ok=True)
    return open(LOG_DIR / f"worker-{agent_id}.log", "ab")


def spawn_agent(name: str, role: str = "worker", program_id: str | None = None,
                auto_claim: bool = True) -> dict:
    """Spawn a real agent lane: DB row + its worker subprocess (real dispatch loop)."""
    agent_id = f"agent-{uuid.uuid4().hex[:8]}"
    now = time.time()
    config = json.dumps({"auto_claim": bool(auto_claim)})

    proc = subprocess.Popen(
        [sys.executable, str(WORKER_SCRIPT), agent_id, name],
        stdout=_worker_log(agent_id),
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        env={**os.environ, "NEXUS_AGENT_ID": agent_id, "NEXUS_AGENT_NAME": name},
    )

    db.execute("""
        INSERT INTO agents (id, name, role, status, program_id, pid, created_at, started_at,
            last_heartbeat, tasks_completed, tasks_failed, tokens_in, tokens_out, current_task, model, config)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (agent_id, name, role, "running", program_id, proc.pid, now, now, now, 0, 0, 0, 0, "", "glm-5.2", config))

    db.log_activity("info", agent_id, f"Agent lane '{name}' spawned (pid={proc.pid})")
    return get_agent(agent_id)


def stop_agent(agent_id: str) -> bool:
    """Stop an agent subprocess."""
    agent = db.query_one("SELECT * FROM agents WHERE id = ?", (agent_id,))
    if not agent:
        return False

    pid = agent["pid"]
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            pass

    db.execute("UPDATE agents SET status = 'stopped', pid = NULL WHERE id = ?", (agent_id,))
    db.log_activity("info", agent_id, f"Agent '{agent['name']}' stopped")
    return True


def retire_agent(agent_id: str) -> dict | None:
    """End a lane through its real lifecycle (R3.1): kill the worker, release its
    unfinished tasks back to the board, set the TERMINAL 'retired' status that
    the watchdog and metrics loop must never touch again. No zombies."""
    agent = db.query_one("SELECT * FROM agents WHERE id = ?", (agent_id,))
    if not agent:
        return None
    pid = agent.get("pid")
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    now = time.time()
    # Release unfinished claims so another lane can pick the work up. Completed
    # dispatch states keep their result; everything else goes back to 'todo'.
    released = db.query_all(
        "SELECT id, title, dispatch_state FROM tasks WHERE claimed_by=? AND status='in_progress'",
        (agent_id,))
    for t in released:
        db.execute(
            "UPDATE tasks SET status='todo', claimed_by=NULL, claimed_at=NULL, "
            "dispatch_state='none', updated_at=? WHERE id=?", (now, t["id"]))
    db.execute("UPDATE agents SET status='retired', pid=NULL, current_task='' WHERE id=?",
               (agent_id,))
    db.log_activity("info", agent_id,
                    f"Agent lane '{agent['name']}' RETIRED"
                    + (f" — released {len(released)} task(s)" if released else ""))
    return get_agent(agent_id)


def restart_agent(agent_id: str) -> dict | None:
    """Restart an agent with the same config (preserves the agent ID)."""
    agent = db.query_one("SELECT * FROM agents WHERE id = ?", (agent_id,))
    if not agent:
        return None
    # Kill old pid if still around (best-effort)
    old_pid = agent.get("pid")
    if old_pid:
        try:
            os.kill(old_pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    time.sleep(0.2)
    # Spawn a fresh worker but reuse the same agent ID + config
    proc = subprocess.Popen(
        [sys.executable, str(WORKER_SCRIPT), agent_id, agent["name"]],
        stdout=_worker_log(agent_id), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        env={**os.environ, "NEXUS_AGENT_ID": agent_id, "NEXUS_AGENT_NAME": agent["name"]},
    )
    now = time.time()
    db.execute(
        "UPDATE agents SET pid=?, status='running', started_at=?, last_heartbeat=?, "
        "current_task='Restarted...' WHERE id=?",
        (proc.pid, now, now, agent_id),
    )
    db.log_activity("info", agent_id, f"Agent '{agent['name']}' restarted (pid={proc.pid})")
    return get_agent(agent_id)


def get_agent(agent_id: str) -> dict | None:
    return db.query_one("SELECT * FROM agents WHERE id = ?", (agent_id,))


def list_agents() -> list[dict]:
    return db.query_all("SELECT * FROM agents ORDER BY created_at")


def list_agents_enriched() -> list[dict]:
    """Agents with program name, latest metrics, and uptime attached."""
    agents = db.query_all("SELECT * FROM agents ORDER BY started_at DESC")
    now = time.time()
    for a in agents:
        prog = db.query_one("SELECT name FROM programs WHERE id = ?", (a.get("program_id"),))
        a["program_name"] = prog["name"] if prog else None
        # latest metric sample
        m = db.query_one(
            "SELECT cpu, memory_mb FROM metrics WHERE agent_id = ? ORDER BY ts DESC LIMIT 1",
            (a["id"],),
        )
        a["cpu"] = round(m["cpu"], 1) if m else 0.0
        a["mem_mb"] = round(m["memory_mb"], 1) if m else 0.0
        # uptime in seconds
        if a.get("started_at"):
            a["uptime_s"] = round(now - a["started_at"], 0)
        else:
            a["uptime_s"] = 0
        # heartbeat age
        if a.get("last_heartbeat"):
            a["heartbeat_age_s"] = round(now - a["last_heartbeat"], 0)
        else:
            a["heartbeat_age_s"] = 0
    return agents


def _update_agent_status():
    """Check if agent processes are still alive; update status.
    A dead agent is marked 'crashed' (NOT silently 'idle') so the self-healing
    watchdog can detect and restart it. Seeded demo agents (pid=NULL) are left as-is.
    """
    agents = db.query_all("SELECT * FROM agents WHERE status IN ('running','busy')")
    for a in agents:
        pid = a["pid"]
        alive = False
        if pid:
            try:
                proc = psutil.Process(pid)
                alive = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                alive = False

        if not alive:
            # Mark crashed so the watchdog heals it (do NOT silently go 'idle')
            db.execute("UPDATE agents SET status = 'crashed' WHERE id = ? AND pid IS NOT NULL", (a["id"],))


def collect_metrics():
    """Collect system + per-agent metrics and store them."""
    _update_agent_status()
    now = time.time()
    agents = db.query_all("SELECT * FROM agents")

    cpu_total = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()

    for a in agents:
        pid = a["pid"]
        cpu, mem_mb = 0.0, 0.0
        if pid:
            try:
                proc = psutil.Process(pid)
                cpu = proc.cpu_percent(interval=0.1)
                mem_mb = proc.memory_info().rss / (1024 * 1024)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        db.execute(
            "INSERT INTO metrics (agent_id, ts, cpu, memory_mb, tasks_per_min) VALUES (?,?,?,?,?)",
            (a["id"], now, round(cpu, 1), round(mem_mb, 1), a["tasks_completed"] / max(1, (now - (a["started_at"] or now)) / 60)),
        )

    # Prune old metrics (> 1 hour) and old activity (> 14 days) — heartbeat
    # and tool events insert activity rows continuously; without pruning the
    # table (and every 'ORDER BY ts DESC' over it) grows without bound.
    db.execute("DELETE FROM metrics WHERE ts < ?", (now - 3600,))
    db.execute("DELETE FROM activity WHERE ts < ?", (now - 14 * 86400,))


# Latest GPU sample, written only by the metrics thread; get_system_stats()
# (called from async routes) must never spawn nvidia-smi itself.
_gpu_stats = {"gpu_percent": None, "gpu_mem_percent": None,
              "gpu_mem_used_mb": None, "gpu_mem_total_mb": None}
_GPU_PCI_DIR = None


def _find_nvidia_pci_dir():
    """Sysfs dir of the NVIDIA display device (vendor 0x10de, class 0x03*)."""
    for dev in Path("/sys/bus/pci/devices").glob("*"):
        try:
            if (dev / "vendor").read_text().strip() == "0x10de" and \
               (dev / "class").read_text().strip().startswith("0x03"):
                return dev
        except OSError:
            continue
    return None


def _sample_gpu(force: bool = False):
    """Refresh _gpu_stats via nvidia-smi. Hybrid-graphics machine: if the dGPU
    is runtime-suspended, report idle from the cached total WITHOUT invoking
    nvidia-smi — the query itself would wake the card and keep it powered.
    force=True bypasses that skip (one startup wake to learn the VRAM total)."""
    global _gpu_stats
    if not force and _GPU_PCI_DIR is not None:
        try:
            if (_GPU_PCI_DIR / "power" / "runtime_status").read_text().strip() == "suspended":
                total = _gpu_stats["gpu_mem_total_mb"]
                _gpu_stats = {"gpu_percent": 0.0, "gpu_mem_percent": 0.0,
                              "gpu_mem_used_mb": 0.0, "gpu_mem_total_mb": total}
                return
        except OSError:
            pass
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        util, used, total = (float(x) for x in out.stdout.strip().splitlines()[0].split(","))
        _gpu_stats = {
            "gpu_percent": util,
            "gpu_mem_percent": round(used / total * 100, 1) if total else 0.0,
            "gpu_mem_used_mb": used,
            "gpu_mem_total_mb": total,
        }
    except Exception:
        _gpu_stats = {"gpu_percent": None, "gpu_mem_percent": None,
                      "gpu_mem_used_mb": None, "gpu_mem_total_mb": None}


def metrics_loop(stop_event: threading.Event):
    """Background thread: collect metrics every few seconds."""
    global _GPU_PCI_DIR
    # Prime psutil's per-process CPU counter once so the first non-blocking
    # cpu_percent(interval=None) read (here and in get_system_stats) returns a
    # real delta instead of 0.0.
    psutil.cpu_percent(interval=None)
    _GPU_PCI_DIR = _find_nvidia_pci_dir()
    try:
        _sample_gpu(force=True)
    except Exception:
        pass
    while not stop_event.is_set():
        try:
            collect_metrics()
        except Exception as e:
            print(f"[metrics] error: {e}", file=sys.stderr)
        try:
            _sample_gpu()
        except Exception as e:
            print(f"[metrics] gpu error: {e}", file=sys.stderr)
        stop_event.wait(3)


def get_system_stats() -> dict:
    """Get current system-wide stats."""
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    try:
        load1, load5, load15 = os.getloadavg()
    except (AttributeError, OSError):
        load1 = load5 = load15 = 0.0

    net = psutil.net_io_counters()
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
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
        **_gpu_stats,
    }


def get_agent_metrics(agent_id: str, limit: int = 60) -> list[dict]:
    return db.query_all(
        "SELECT * FROM metrics WHERE agent_id = ? ORDER BY ts DESC LIMIT ?",
        (agent_id, limit),
    )
