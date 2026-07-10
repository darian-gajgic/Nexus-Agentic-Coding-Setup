"""NEXUS Agent OS — App Runner (v3.4): test a task's program output live.

A task that produced a program shouldn't end at a file listing — the operator
presses ▶ Test app and gets the running application in a new browser tab.

Detection (workspace root, then first subdirectory with markers):
  node    — package.json           -> npm install (if needed) + npm run dev|start
  python  — app.py/main.py + reqs  -> venv + pip install + python entry (PORT env)
  static  — index.html             -> python -m http.server (own port = own origin)

Port truth (v3.4): vite scripts get `-- --port <p> --strictPort --host 127.0.0.1`
appended (vite ignores the PORT env); any other server that ignores PORT is
adopted from the URL it prints in its own log (_adopt_logged_port rewrites the
registry port/url once that port answers).

Every app runs as its own process group on a dedicated 127.0.0.1 port from
_PORT_RANGE, logs to <workspace>/_preview.log (the _ prefix keeps it out of
deliverable listings), is auto-stopped after _TTL_S, and the registry persists
to disk so a Nexus restart reaps orphans instead of leaking them.
"""
import json
import os
import re
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

import database as db

BASE_DIR = Path(__file__).parent
WORKSPACES = BASE_DIR / "workspaces"
REGISTRY = WORKSPACES / ".preview-apps.json"
_PORT_RANGE = range(8790, 8821)
_TTL_S = 30 * 60          # auto-stop a forgotten preview after 30 min
_MAX_APPS = 3             # concurrent previews (each dev server is heavy)
_LOG_MAX_BYTES = 5 * 1024 * 1024  # cap _preview.log (chatty dev servers write unbounded)
_SKIP_DIRS = {"node_modules", ".next", ".git", "__pycache__", "attachments",
              "dist", "build", ".venv", "venv"}

_lock = threading.Lock()


# ── registry (persisted so restarts reap instead of leak) ──

def _load() -> dict:
    try:
        return json.loads(REGISTRY.read_text())
    except Exception:
        return {}


def _save(reg: dict):
    try:
        WORKSPACES.mkdir(exist_ok=True)
        REGISTRY.write_text(json.dumps(reg, indent=2))
    except Exception:
        pass


def _pid_is_ours(pid: int) -> bool:
    """PID identity via the env marker — a recycled pid never matches."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            return b"NEXUS_PREVIEW=1" in f.read()
    except Exception:
        return False


def _kill(pid: int):
    """Kill the preview's whole process group (npm spawns children)."""
    try:
        os.killpg(pid, signal.SIGTERM)
    except Exception:
        pass
    time.sleep(1.0)
    try:
        os.killpg(pid, signal.SIGKILL)
    except Exception:
        pass


# ── detection ──

def detect_app(workspace: str) -> dict | None:
    """What runnable thing lives in this workspace? Returns
    {type, dir, label} or None. Root first, then first marker subdir."""
    ws = Path(workspace)
    if not ws.is_dir():
        return None
    candidates = [ws]
    try:
        candidates += sorted(d for d in ws.iterdir()
                             if d.is_dir() and d.name not in _SKIP_DIRS)
    except Exception:
        pass
    for d in candidates:
        if (d / "package.json").is_file():
            try:
                pkg = json.loads((d / "package.json").read_text())
            except Exception:
                pkg = {}
            scripts = pkg.get("scripts") or {}
            script = "dev" if "dev" in scripts else ("start" if "start" in scripts else None)
            if script:
                return {"type": "node", "dir": str(d), "script": script,
                        # the script runs vite itself → port goes on the CLI
                        # (vite ignores the PORT env; vitest must not match)
                        "vite": "vite" in (scripts.get(script) or "").split(),
                        "label": f"Node app ({d.name or 'root'} · npm run {script})",
                        "installed": (d / "node_modules").is_dir()}
    for d in candidates:
        for entry in ("app.py", "main.py", "server.py"):
            if (d / entry).is_file():
                return {"type": "python", "dir": str(d), "entry": entry,
                        "label": f"Python app ({d.name or 'root'} · {entry})",
                        "installed": not (d / "requirements.txt").is_file()
                        or (d / ".venv-preview").is_dir()}
    for d in candidates:
        if (d / "index.html").is_file():
            return {"type": "static", "dir": str(d), "installed": True,
                    "label": f"Static site ({d.name or 'root'} · index.html)"}
    return None


# ── lifecycle ──

def _free_port() -> int | None:
    reg = _load()
    used = {a.get("port") for a in reg.values()}
    for p in _PORT_RANGE:
        if p in used:
            continue
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return None


def _listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_URL_PORT_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(\d{2,5})")


def _adopt_logged_port(key: str, a: dict) -> bool:
    """A dev server that ignored the PORT env announces its real URL in its
    log (vite: 'Local: http://localhost:3001/' — ANSI codes sit INSIDE the
    URL, strip first). If that port answers, rewrite the registry entry in
    place so the UI opens the right place."""
    ports = _URL_PORT_RE.findall(_ANSI_RE.sub("", log_tail(a.get("workspace") or "", 40)))
    p = int(ports[-1]) if ports else 0          # last announcement wins
    if not p or p == a.get("port") or not _listening(p):
        return False
    a["port"], a["url"] = p, f"http://127.0.0.1:{p}"
    with _lock:
        reg = _load()
        cur = reg.get(key)
        if cur and cur.get("pid") == a.get("pid"):   # not replaced meanwhile
            cur["port"], cur["url"] = p, f"http://127.0.0.1:{p}"
            _save(reg)
    db.log_activity("info", "preview",
                    f"Preview {key} answers on :{p} (found in its log) — URL updated")
    return True


def start_app(task_id: str, workspace: str) -> dict:
    with _lock:
        reg = _load()
        cur = reg.get(task_id)
        if cur and _pid_is_ours(cur.get("pid", -1)):
            cur["expires_at"] = time.time() + _TTL_S  # touching extends the TTL
            _save(reg)
            return {"ok": True, **cur}
        running = [t for t, a in reg.items() if _pid_is_ours(a.get("pid", -1))]
        if len(running) >= _MAX_APPS:
            return {"ok": False, "error":
                    f"{_MAX_APPS} preview apps already running — stop one first "
                    f"(running: {', '.join(running)})"}
        app = detect_app(workspace)
        if not app:
            return {"ok": False, "error": "nothing runnable found (no package.json "
                    "with dev/start script, no app.py/main.py, no index.html)"}
        port = _free_port()
        if not port:
            return {"ok": False, "error": "no free preview port"}
        log_path = Path(workspace) / "_preview.log"
        env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1",
               "HOSTNAME": "127.0.0.1", "BROWSER": "none", "CI": "1",
               "NEXUS_PREVIEW": "1"}
        if app["type"] == "node":
            # vite ignores the PORT env: pin it on the CLI, else a config port
            # (server.port) auto-increments when busy and strands the preview
            args = f" -- --port {port} --strictPort --host 127.0.0.1" if app.get("vite") else ""
            # npm install first when needed (logged; the UI polls the log).
            inner = (f"npm install --no-audit --no-fund && " if not app["installed"] else "") \
                + f"exec npm run {app['script']}{args}"
        elif app["type"] == "python":
            venv = Path(app["dir"]) / ".venv-preview"
            pre = ""
            if (Path(app["dir"]) / "requirements.txt").is_file():
                pre = (f"[ -d .venv-preview ] || python3 -m venv .venv-preview; "
                       f". .venv-preview/bin/activate && "
                       f"pip install -q -r requirements.txt && ")
            else:
                pre = ""
            py = f"{venv}/bin/python" if pre else "python3"
            inner = pre + f"exec {py} {app['entry']}"
        else:  # static
            inner = f"exec python3 -m http.server {port} --bind 127.0.0.1"
        cmd = ["bash", "-c", inner]
        with open(log_path, "wb") as lf:
            lf.write(f"=== nexus preview {task_id} :{port} {app['label']} ===\n".encode())
        proc = subprocess.Popen(
            cmd, cwd=app["dir"], env=env,
            stdout=open(log_path, "ab"), stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True)
        entry = {"task_id": task_id, "pid": proc.pid, "port": port,
                 "type": app["type"], "label": app["label"],
                 "url": f"http://127.0.0.1:{port}",
                 "workspace": workspace, "started_at": time.time(),
                 "expires_at": time.time() + _TTL_S,
                 "installing": not app.get("installed", True)}
        reg[task_id] = entry
        _save(reg)
        db.log_activity("info", "preview",
                        f"▶ Preview starting for {task_id}: {app['label']} on :{port}")
        return {"ok": True, **entry}


def instances(prefix: str) -> list[dict]:
    """Live registry entries whose key starts with prefix — how project
    previews (keys wf:<id>:<state>) enumerate their running states."""
    out = []
    for key, a in _load().items():
        if not key.startswith(prefix) or not _pid_is_ours(a.get("pid", -1)):
            continue
        ready = _listening(a["port"]) or _adopt_logged_port(key, a)
        out.append({**a, "key": key, "ready": ready,
                    "state": "ready" if ready else
                    ("installing" if a.get("installing") else "starting")})
    return out


def app_status(task_id: str, workspace: str) -> dict:
    reg = _load()
    cur = reg.get(task_id)
    out = {"detected": detect_app(workspace)}
    if cur and _pid_is_ours(cur.get("pid", -1)):
        ready = _listening(cur["port"]) or _adopt_logged_port(task_id, cur)
        out["running"] = {**cur, "ready": ready,
                          "state": "ready" if ready else
                          ("installing" if cur.get("installing") else "starting")}
    elif cur:  # process died (crash or install failure) — surface the log
        out["exited"] = {**cur}
        with _lock:
            reg.pop(task_id, None)
            _save(reg)
    return out


def stop_app(task_id: str) -> dict:
    with _lock:
        reg = _load()
        cur = reg.pop(task_id, None)
        _save(reg)
    if cur and _pid_is_ours(cur.get("pid", -1)):
        _kill(cur["pid"])
        db.log_activity("info", "preview", f"⏹ Preview stopped for {task_id}")
        return {"ok": True}
    return {"ok": True, "note": "was not running"}


def log_tail(workspace: str, lines: int = 80) -> str:
    p = Path(workspace) / "_preview.log"
    try:
        # seek-read only the tail — a chatty dev server's log grows unbounded
        # and this is polled every few seconds while the preview modal is open
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 16000))
            data = f.read()
        return "\n".join(data.decode(errors="replace").splitlines()[-lines:])
    except Exception:
        return ""


def reaper_thread(stop_event: threading.Event):
    """Boot: kill previews orphaned by a restart. Then: enforce the TTL."""
    with _lock:
        reg = _load()
        for tid, a in list(reg.items()):
            if _pid_is_ours(a.get("pid", -1)):
                _kill(a["pid"])
            reg.pop(tid, None)
        _save(reg)
    while not stop_event.is_set():
        now = time.time()
        with _lock:
            reg = _load()
            for tid, a in list(reg.items()):
                alive = _pid_is_ours(a.get("pid", -1))
                if not alive:
                    reg.pop(tid, None)
                elif now > float(a.get("expires_at") or 0):
                    _kill(a["pid"])
                    reg.pop(tid, None)
                    db.log_activity("info", "preview",
                                    f"Preview for {tid} auto-stopped (30 min TTL)")
                else:
                    try:  # the child's O_APPEND fd continues at the new end
                        lp = Path(a.get("workspace") or "") / "_preview.log"
                        if lp.is_file() and lp.stat().st_size > _LOG_MAX_BYTES:
                            os.truncate(lp, 0)
                    except Exception:
                        pass
            _save(reg)
        stop_event.wait(60)
