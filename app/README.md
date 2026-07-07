# NEXUS — Agent OS

A self-contained Agent Operating System that is the **real control plane for the Hermes agent
system**: kanban cards are executed by real Hermes AI sessions (18 specialists), with live
telemetry, deliverable files, budgets, and self-healing. Plus real-time monitoring, agent
fleet management, and the JARVIS voice assistant.

## Features
- **Real execution (v2)** — a kanban card is claimed atomically by an agent lane and executed
  as a REAL Hermes API session; deliverables land as files in `workspaces/<task-id>/`;
  token counts are real. The old worker simulation is gone. Spec: `SPEC-REAL-AGENTS.md`.
- **Dashboard** — live overview: total agents, tasks, programs, CPU/mem gauges, activity feed
- **Kanban Board** — the ONE task board (Hermes's own kanban.db is retired) — drag-and-drop
  across Backlog → Todo → In Progress → Review → Done, atomic claiming, dispatch states
- **Agent Fleet** — spawn/retire/stop lanes, real status, heartbeats, resume-based self-heal
- **Programs** — list and manage registered programs/applications
- **Monitor** — real-time system + per-agent metrics (CPU, memory, uptime, task throughput)
- **Zero external deps** — pure Python backend + vanilla JS frontend. No Docker, no Postgres, no Redis.

## Run
```bash
cd ~/nexus-agent-os
bash start.sh
```
Then open https://localhost:8777 (self-signed cert — accept the warning).
Requires the `hermes-gateway` systemd user service for real task execution
(`systemctl --user status hermes-gateway`).

## Stack
- Backend: FastAPI + SQLite (stdlib `sqlite3`)
- Frontend: Vanilla JS + Chart.js CDN (no build step)
- Real processes: agent lanes run as actual OS subprocesses (`worker.py`)
- Real intelligence: tasks execute via the Hermes Agent API (`http://127.0.0.1:8642`),
  one persistent `api_*` session per task

## Verify
```bash
bash scripts/verify.sh                                  # static gate (70 checks)
.venv/bin/python scripts/verify_agentic_e2e.py          # agentic API mechanics (30)
.venv/bin/python scripts/verify_real_dispatch_e2e.py    # REAL dispatch end-to-end
.venv/bin/python scripts/verify_v3_ui.py                # UI (24)
```
