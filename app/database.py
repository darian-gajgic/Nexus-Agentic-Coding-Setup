"""NEXUS Agent OS — Database layer (SQLite via stdlib)."""
import sqlite3
import json
import time
import threading
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "nexus.db"
_local = threading.local()


def get_conn() -> sqlite3.Connection:
    """Thread-local connection with WAL mode."""
    if not hasattr(_local, "conn"):
        conn = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        role TEXT DEFAULT 'worker',
        status TEXT DEFAULT 'idle',
        program_id TEXT,
        pid INTEGER,
        created_at REAL,
        started_at REAL,
        last_heartbeat REAL,
        tasks_completed INTEGER DEFAULT 0,
        tasks_failed INTEGER DEFAULT 0,
        tokens_in INTEGER DEFAULT 0,
        tokens_out INTEGER DEFAULT 0,
        current_task TEXT DEFAULT '',
        model TEXT DEFAULT 'glm-5.2',
        config TEXT DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS programs (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        language TEXT DEFAULT 'python',
        entry_point TEXT DEFAULT '',
        status TEXT DEFAULT 'registered',
        created_at REAL,
        last_run REAL,
        run_count INTEGER DEFAULT 0,
        avg_duration REAL DEFAULT 0,
        tags TEXT DEFAULT '[]'
    );

    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        status TEXT DEFAULT 'backlog',
        priority INTEGER DEFAULT 2,
        assignee_id TEXT,
        program_id TEXT,
        created_at REAL,
        updated_at REAL,
        completed_at REAL,
        tags TEXT DEFAULT '[]',
        position INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT,
        ts REAL,
        cpu REAL DEFAULT 0,
        memory_mb REAL DEFAULT 0,
        tasks_per_min REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL,
        level TEXT DEFAULT 'info',
        source TEXT DEFAULT 'system',
        message TEXT
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );

    -- ===== Agentic OS tables (v1, additive) =====

    CREATE TABLE IF NOT EXISTS verify_runs (
        id TEXT PRIMARY KEY,
        task_id TEXT,
        agent_id TEXT,
        kind TEXT DEFAULT 'static',
        command TEXT,
        exit_code INTEGER,
        stdout_tail TEXT DEFAULT '',
        stderr_tail TEXT DEFAULT '',
        passed INTEGER DEFAULT 0,
        duration_ms INTEGER DEFAULT 0,
        ts REAL
    );

    CREATE TABLE IF NOT EXISTS approvals (
        id TEXT PRIMARY KEY,
        agent_id TEXT,
        action_type TEXT,
        description TEXT,
        payload TEXT DEFAULT '{}',
        status TEXT DEFAULT 'pending',
        risk_level TEXT DEFAULT 'medium',
        requested_at REAL,
        decided_at REAL,
        decided_by TEXT
    );

    CREATE TABLE IF NOT EXISTS memory (
        id TEXT PRIMARY KEY,
        agent_id TEXT,
        scope TEXT DEFAULT 'lts',
        kind TEXT DEFAULT 'note',
        content TEXT,
        embedding_b64 TEXT,
        source TEXT DEFAULT 'agent',
        created_at REAL,
        expires_at REAL
    );

    CREATE TABLE IF NOT EXISTS scheduled_jobs (
        id TEXT PRIMARY KEY,
        name TEXT,
        cron_expr TEXT,
        agent_id TEXT,
        action TEXT,
        enabled INTEGER DEFAULT 1,
        last_run REAL,
        next_run REAL,
        run_count INTEGER DEFAULT 0,
        last_status TEXT DEFAULT 'never',
        created_at REAL
    );

    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        from_agent TEXT,
        to_agent TEXT,
        content TEXT,
        ts REAL,
        read INTEGER DEFAULT 0
    );

    -- ===== Real-dispatch tables (v2, additive — SPEC-REAL-AGENTS.md §4) =====

    -- Workflows: multi-task projects/campaigns with dependencies (v2.1).
    CREATE TABLE IF NOT EXISTS workflows (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        goal TEXT DEFAULT '',
        domain TEXT,
        status TEXT DEFAULT 'active',
        created_at REAL,
        updated_at REAL
    );

    CREATE TABLE IF NOT EXISTS dispatches (
        id TEXT PRIMARY KEY,
        task_id TEXT,
        agent_id TEXT,
        session_id TEXT,
        started_at REAL,
        ended_at REAL,
        state TEXT DEFAULT 'queued',
        tokens_in INTEGER DEFAULT 0,
        tokens_out INTEGER DEFAULT 0,
        error TEXT,
        heartbeat_at REAL
    );

    -- ===== Multi-user tables (Block 1, additive — docs/SPEC-MULTIUSER.md) =====

    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        display_name TEXT DEFAULT '',
        password_hash TEXT DEFAULT '',
        role TEXT DEFAULT 'member',
        active INTEGER DEFAULT 1,
        created_at REAL
    );

    CREATE TABLE IF NOT EXISTS auth_sessions (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        created_at REAL,
        expires_at REAL,
        last_seen REAL,
        ua TEXT DEFAULT ''
    );
    """)

    # Migrate: add columns if they don't exist (for existing DBs)
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(agents)").fetchall()}
    migrations = [
        ("tokens_in", "INTEGER DEFAULT 0"),
        ("tokens_out", "INTEGER DEFAULT 0"),
        ("current_task", "TEXT DEFAULT ''"),
        ("model", "TEXT DEFAULT 'glm-5.2'"),
        ("worktree_path", "TEXT"),
        ("worktree_branch", "TEXT"),
        ("restart_count", "INTEGER DEFAULT 0"),
    ]
    for col, typedef in migrations:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE agents ADD COLUMN {col} {typedef}")

    # Migrate task columns
    existing_task_cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    task_migrations = [
        ("claimed_by", "TEXT"),
        ("claimed_at", "REAL"),
        ("verify_status", "TEXT DEFAULT 'unknown'"),
        # Real-dispatch columns (SPEC-REAL-AGENTS.md §4)
        ("session_id", "TEXT"),
        ("dispatch_state", "TEXT DEFAULT 'none'"),
        ("domain", "TEXT"),
        ("specialist", "TEXT"),
        ("high_stakes", "INTEGER DEFAULT 0"),
        ("budget_tokens", "INTEGER"),
        ("tokens_used", "INTEGER DEFAULT 0"),
        ("workspace_path", "TEXT"),
        ("result_summary", "TEXT"),
        ("rubric_score", "TEXT"),
        ("learn_section", "TEXT"),
        ("dispatch_error", "TEXT"),
        ("judge_verdict", "TEXT"),
        ("judge_output", "TEXT"),
        ("judge_ts", "REAL"),
        ("retry_feedback", "TEXT"),
        ("model", "TEXT"),
        ("workflow_id", "TEXT"),
        ("depends_on", "TEXT"),
        ("loop_config", "TEXT"),
        ("repo_path", "TEXT"),
        ("client", "TEXT"),
        ("user_id", "TEXT"),
    ]
    for col, typedef in task_migrations:
        if col not in existing_task_cols:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {typedef}")

    # Migrate workflows columns (looping v3.2)
    existing_wf_cols = {r[1] for r in conn.execute("PRAGMA table_info(workflows)").fetchall()}
    if "loop_config" not in existing_wf_cols:
        conn.execute("ALTER TABLE workflows ADD COLUMN loop_config TEXT")
    if "high_stakes" not in existing_wf_cols:
        conn.execute("ALTER TABLE workflows ADD COLUMN high_stakes INTEGER DEFAULT 0")
    if "client" not in existing_wf_cols:
        conn.execute("ALTER TABLE workflows ADD COLUMN client TEXT")
    if "project_path" not in existing_wf_cols:
        conn.execute("ALTER TABLE workflows ADD COLUMN project_path TEXT")
    if "user_id" not in existing_wf_cols:
        conn.execute("ALTER TABLE workflows ADD COLUMN user_id TEXT")

    # Known issues: operator feedback with interaction context (v3.4)
    conn.execute("""CREATE TABLE IF NOT EXISTS known_issues (
        id TEXT PRIMARY KEY,
        ts REAL,
        view TEXT,
        feedback TEXT,
        context TEXT,
        status TEXT DEFAULT 'new'
    )""")

    # Migrate dispatches columns (table shipped in S1 without the executor heartbeat)
    existing_disp_cols = {r[1] for r in conn.execute("PRAGMA table_info(dispatches)").fetchall()}
    if "heartbeat_at" not in existing_disp_cols:
        conn.execute("ALTER TABLE dispatches ADD COLUMN heartbeat_at REAL")

    # ===== Multi-user migration (Block 1, additive — docs/SPEC-MULTIUSER.md) =====
    # user_id on the per-user tables; NULL on activity = system-wide row.
    for tbl in ("known_issues", "activity"):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()}
        if "user_id" not in cols:
            conn.execute(f"ALTER TABLE {tbl} ADD COLUMN user_id TEXT")
    # Seed the default owner ONCE, then hand every pre-multiuser row to it so
    # ALL queries are uniformly user-scoped (no unscoped legacy path). With
    # only this one user configured, login stays off and nothing changes for
    # the single-operator machine.
    if not conn.execute("SELECT 1 FROM users WHERE id='u_owner'").fetchone():
        conn.execute(
            "INSERT INTO users (id, username, display_name, password_hash, role, "
            "active, created_at) VALUES ('u_owner','owner','Operator','','admin',1,?)",
            (time.time(),))
    for tbl in ("tasks", "workflows", "known_issues"):
        conn.execute(f"UPDATE {tbl} SET user_id='u_owner' WHERE user_id IS NULL")

    # Project ownership (Block 1 gap fix): the Projects view scans the shared
    # filesystem, so visibility needs its own map. Paths NOT in this table
    # belong to u_owner (the machine's home directory IS the operator's) —
    # rows are only written when a project is created through Nexus, so a
    # directory the operator makes by hand stays his without bookkeeping.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS project_owners (
        path TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        created_at REAL
    )""")

    # Seed real-dispatch settings (visible/editable). Real dispatch is the
    # default since v2 shipped — a fresh install behaves like the main machine.
    dispatch_defaults = [
        ("dispatch.enabled", "1"),
        ("dispatch.default_task_budget", "5000000"),
        ("dispatch.daily_cap", "10000000"),
        ("dispatch.max_concurrent_per_model", "8"),
        ("dispatch.max_concurrent_total", "8"),
        ("judge.cmd", "cjudge {file} {domain}"),
    ]
    for k, v in dispatch_defaults:
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('theme', 'dark')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('poll_interval', '2')")

    # Secondary indexes for the hot paths (worker _find_work tick every 2s,
    # slots_in_use per dispatch, activity feed) — the tables ship index-free.
    for ddl in (
        "CREATE INDEX IF NOT EXISTS idx_tasks_claimed ON tasks(claimed_by, status)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
        "CREATE INDEX IF NOT EXISTS idx_dispatches_task ON dispatches(task_id, state)",
        "CREATE INDEX IF NOT EXISTS idx_dispatches_state ON dispatches(state, heartbeat_at)",
        "CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity(ts)",
        "CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_workflows_user ON workflows(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_exp ON auth_sessions(expires_at)",
    ):
        conn.execute(ddl)
    conn.commit()
    # v2: no demo seeding. A fresh install starts EMPTY — every agent, task,
    # token count and activity row in this database is real (SPEC-REAL-AGENTS §4).


# --- CRUD helpers ---

def query_all(sql, params=()):
    return [dict(r) for r in get_conn().execute(sql, params).fetchall()]


def query_one(sql, params=()):
    r = get_conn().execute(sql, params).fetchone()
    return dict(r) if r else None


def execute(sql, params=()):
    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur


def log_activity(level, source, message, user_id=None):
    """user_id=None = system-wide row (visible to every user); pass the owning
    task's user_id when the event is about one user's work."""
    execute("INSERT INTO activity (ts, level, source, message, user_id) VALUES (?,?,?,?,?)",
            (time.time(), level, source, message, user_id))


# --- Settings helpers (shared by server, worker, watchdog) ---

def get_setting(key, default=None):
    row = query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def set_setting(key, value):
    execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))


# --- Atomic task claiming (single CAS code path — used by the HTTP endpoint
#     and by worker processes, so two claimers can never both win) ---

def claim_task_cas(task_id: str, agent_id: str) -> bool:
    """Claim a task atomically. True = we own it now; False = CAS lost."""
    now = time.time()
    cur = execute(
        "UPDATE tasks SET status='in_progress', claimed_by=?, claimed_at=?, updated_at=? "
        "WHERE id=? AND status IN ('backlog','todo')",
        (agent_id, now, now, task_id),
    )
    return cur.rowcount > 0
