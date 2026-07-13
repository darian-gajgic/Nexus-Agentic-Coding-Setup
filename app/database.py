"""NEXUS Agent OS — Database layer (SQLite via stdlib)."""
import sqlite3
import json
import time
import uuid
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
        # P9 (ops hardening): set the busy timeout EXPLICITLY as a PRAGMA (10s) so a
        # writer waits out a concurrent lock instead of raising "database is locked"
        # immediately — the periodic sweeps (critic-sandbox age-out, scheduler,
        # loop engine) all write on their own threads.
        conn.execute("PRAGMA busy_timeout=10000")
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
        heartbeat_at REAL,
        model TEXT
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
        ("pr_url", "TEXT"),
        # Super Result (SUPER-RESULT-PLAN-2026-07-09.md §6 Step 1): grounded
        # critic state — separate from judge_* by design (§4.1: overloading
        # judge_ts/judge_verdict would double-fire the existing loop triggers
        # and leak raw critic JSON into executor prompts via _retry_task).
        ("super_result", "INTEGER DEFAULT 0"),
        ("deliverable_type", "TEXT"),            # analysis|code_change|content|research|NULL
        ("critic_verdict", "TEXT"),              # running|SHIP|REVISE|REWRITE|error
        ("critic_output", "TEXT"),               # raw cverify stdout tail (≤30000)
        ("critic_json", "TEXT"),                 # validated parsed findings JSON (≤60000)
        ("critic_ts", "REAL"),
        ("critic_round", "INTEGER DEFAULT 0"),
        ("critic_keys", "TEXT"),                 # {"round":N,"keys":[...],"prev":[...]} convergence state
        # Judge-loop overhaul (2026-07-13): per-version-family judge state.
        # judge_round counts STORED verdicts (quota-interrupted runs don't
        # count); the hard cap judge.max_runs reads it — the round caps only
        # bound retries, and 3-7 full frontier passes per task were observed.
        # judge_keys mirrors critic_keys for the plain loop's convergence
        # guard. Both reset ONLY on an operator reject (new version family).
        ("judge_round", "INTEGER DEFAULT 0"),
        ("judge_keys", "TEXT"),
        # Budget honesty (2026-07-13): the budget as first derived at creation.
        # Retry slices and the rework ceiling (dispatch.rework_ceiling_mult)
        # compute from THIS, not from the silently-grown budget_tokens.
        ("budget_original", "INTEGER"),
        # Quality Autopilot Q7a: two orthogonal preset axes. NULL = legacy (P10b:
        # no derivation, existing explicit preference honored as-is).
        ("autopilot", "TEXT"),                   # full_auto|assisted|manual|NULL
        ("spend_profile", "TEXT"),               # eco|optimal|smart|NULL
        # Appendix C3 (full-cost ledger): frontier subprocess spend for this task —
        # critic/judge/spec/escalation runs bill the Claude subscription, invisible
        # to the GLM token counter (tokens_used). These accumulate their captured
        # tokens + API-EQUIVALENT dollars (from the claude-JSON envelope, else a
        # transcript-size estimate priced from cost.model_prices) so the ledger
        # can show a task's total $ across BOTH currencies. Not a bill — a compare.
        ("frontier_tokens", "INTEGER DEFAULT 0"),
        ("frontier_cost_usd", "REAL DEFAULT 0"),
        # Operator stop (item 5, 2026-07-12): timestamp of a stop request. The
        # executor polls it between SSE events and aborts; run_task_dispatch
        # re-checks it before spending. Cleared on explicit re-dispatch.
        ("cancel_requested", "REAL"),
        # Item 15: WHY auto-routing picked this task's model (plain language,
        # shown in the task detail). Cleared when a human sets the model.
        ("model_reason", "TEXT"),
    ]
    for col, typedef in task_migrations:
        if col not in existing_task_cols:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {typedef}")

    # In-app onboarding (docs/SPEC-ONBOARDING.md): per-user Business-Brain
    # answers (partial saves are the norm — the wizard is resumable) and the
    # last-applied marker. Answers NEVER cross users.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS onboarding_answers (
        user_id TEXT NOT NULL,
        slot_id TEXT NOT NULL,
        answer TEXT,
        na INTEGER DEFAULT 0,
        updated_at REAL,
        PRIMARY KEY (user_id, slot_id)
    )""")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS onboarding_state (
        user_id TEXT PRIMARY KEY,
        applied_at REAL,
        target_dir TEXT
    )""")

    # Review v2 (docs/SPEC-BLOCK2.md R1.4): per-line comments on a task's
    # change review. status: open (feeds the NEXT retry) | consumed (attached
    # to a retry — kept for audit). Fail-closed per user like approvals.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS review_comments (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        file_path TEXT NOT NULL,
        side TEXT NOT NULL DEFAULT 'new',
        line_no INTEGER,
        line_text TEXT DEFAULT '',
        body TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        consumed_at REAL,
        created_at REAL
    )""")
    # Super Result: who filed the comment — 'user' (the human, historical
    # default), 'critic' (grounded critic auto-comments, superseded per round),
    # or 'judge' (normal-mode judge findings, N3). Retry drains all sources.
    rc_cols = {r[1] for r in conn.execute("PRAGMA table_info(review_comments)").fetchall()}
    if "source" not in rc_cols:
        conn.execute("ALTER TABLE review_comments ADD COLUMN source TEXT NOT NULL DEFAULT 'user'")
    # Appendix C1b: an optional critic-proposed unified-diff patch for a
    # mechanical critical/high fix — stored in full (out of the 500-char body
    # cap) and re-attached by _retry_task as a fenced diff the executor applies
    # verbatim (CriticGPT: critic-proposed diff + executor application).
    if "patch" not in rc_cols:
        conn.execute("ALTER TABLE review_comments ADD COLUMN patch TEXT")

    # Q2 (operator-edit distillation): per-domain evidence that feeds the lessons
    # distillation job — rejection feedback, user review comments, and the diff
    # between a human-rejected version and the accepted one (the strongest signal).
    # kind: 'feedback' | 'comment' | 'accept_diff'. content capped at 8000 chars.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS edit_evidence (
        id TEXT PRIMARY KEY,
        task_id TEXT,
        domain TEXT,
        user_id TEXT,
        kind TEXT NOT NULL DEFAULT 'feedback',
        content TEXT DEFAULT '',
        distilled INTEGER DEFAULT 0,
        created_at REAL
    )""")

    # P7: approvals gain a scope. 'user' (default, historical) rows belong to one
    # user and fail-closed to them; 'admin' rows (lesson deltas, cross-user share
    # cards) have no task and are visible to every admin in the Decisions inbox.
    _appr_cols0 = {r[1] for r in conn.execute("PRAGMA table_info(approvals)").fetchall()}
    if "scope" not in _appr_cols0:
        conn.execute("ALTER TABLE approvals ADD COLUMN scope TEXT NOT NULL DEFAULT 'user'")

    # L1 (outcome-driven routing tuning, premortem P4 schema): one row per task at
    # its terminal state — the routing decision + what actually happened. A
    # deterministic stats job (NO LLM) reads these to propose threshold tweaks.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS routing_outcomes (
        id TEXT PRIMARY KEY,
        task_id TEXT UNIQUE,
        user_id TEXT,
        triage_json TEXT DEFAULT '{}',
        spend_profile TEXT,
        autopilot TEXT,
        rounds_used INTEGER DEFAULT 0,
        fanout_used INTEGER DEFAULT 0,
        final_verdicts TEXT DEFAULT '{}',
        escalated INTEGER DEFAULT 0,
        overridden INTEGER DEFAULT 0,
        created_at REAL
    )""")
    # L4 (fingerprint-tagged learned parameters): tuned thresholds (triage,
    # escalation, profile bands) are MODEL-SPECIFIC → stored with the config
    # fingerprint and auto-invalidated on tier rotation (revert to heuristic
    # defaults until re-tuned). Distilled CRAFT lessons live in ~/knowledge and
    # survive rotations — two stores, never mixed.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS learned_params (
        key TEXT PRIMARY KEY,
        value TEXT,
        fingerprint TEXT,
        updated_at REAL
    )""")

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
    # Block 3: mid-run replanning checkpoint state (JSON; NULL = nothing pending)
    if "replan" not in existing_wf_cols:
        conn.execute("ALTER TABLE workflows ADD COLUMN replan TEXT")
    # Super Result: project-level flag cascades to member tasks (like high_stakes)
    if "super_result" not in existing_wf_cols:
        conn.execute("ALTER TABLE workflows ADD COLUMN super_result INTEGER DEFAULT 0")
    # Quality Autopilot Q7a: preset axes cascade to member tasks (like high_stakes)
    if "autopilot" not in existing_wf_cols:
        conn.execute("ALTER TABLE workflows ADD COLUMN autopilot TEXT")
    if "spend_profile" not in existing_wf_cols:
        conn.execute("ALTER TABLE workflows ADD COLUMN spend_profile TEXT")

    # Known issues: operator feedback with interaction context (v3.4)
    conn.execute("""CREATE TABLE IF NOT EXISTS known_issues (
        id TEXT PRIMARY KEY,
        ts REAL,
        view TEXT,
        feedback TEXT,
        context TEXT,
        status TEXT DEFAULT 'new'
    )""")

    # Item 14 (2026-07-12): quick notes — the 📝 bottom-left panel + Notes tab.
    # project/workflow names are DENORMALIZED on purpose: a note must stay
    # readable after its project or workflow is deleted.
    conn.execute("""CREATE TABLE IF NOT EXISTS notes (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        created_at REAL,
        updated_at REAL,
        text TEXT NOT NULL,
        project_path TEXT,
        project_name TEXT,
        workflow_id TEXT,
        workflow_name TEXT
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id, created_at)")

    # Item 8 (2026-07-12): meeting intelligence — transcript → project link +
    # cached LLM summary/requirements. A DB row (not file frontmatter) because
    # the dictation recorder APPENDS to the transcript live; editing the file
    # under it would race the writer and break the title scan.
    conn.execute("""CREATE TABLE IF NOT EXISTS meeting_meta (
        name TEXT PRIMARY KEY,
        project_path TEXT,
        workflow_id TEXT,
        summary TEXT,
        summary_ts REAL,
        requirements TEXT,
        requirements_ts REAL,
        user_id TEXT,
        created_at REAL,
        updated_at REAL
    )""")

    # B4: a scheduled job may carry a task TEMPLATE (JSON) so recurring high-value
    # jobs get Super Result / deliverable type / autopilot preset automatically.
    _sj_cols = {r[1] for r in conn.execute("PRAGMA table_info(scheduled_jobs)").fetchall()}
    if "task_template" not in _sj_cols:
        conn.execute("ALTER TABLE scheduled_jobs ADD COLUMN task_template TEXT")

    # Migrate dispatches columns (table shipped in S1 without the executor heartbeat)
    existing_disp_cols = {r[1] for r in conn.execute("PRAGMA table_info(dispatches)").fetchall()}
    if "heartbeat_at" not in existing_disp_cols:
        conn.execute("ALTER TABLE dispatches ADD COLUMN heartbeat_at REAL")
    if "model" not in existing_disp_cols:
        # The EFFECTIVE run model of this dispatch (fallback included) — the
        # per-model slot accounting groups by it; tasks.model is only the
        # pre-fallback intent and under-counts the fallback pool.
        conn.execute("ALTER TABLE dispatches ADD COLUMN model TEXT")
    if "run_id" not in existing_disp_cols:
        # Item 5 (stop): the upstream Hermes run id, captured from the first
        # SSE run.started event — lets the stop endpoint attempt a real
        # /v1/runs/{id}/stop abort (effective once the session-run-stop
        # core-mod ships) and audits which run served this dispatch.
        conn.execute("ALTER TABLE dispatches ADD COLUMN run_id TEXT")

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

    # Approvals are per-user (gap fix: deliverable approvals surfaced the
    # owner's work in every user's Agentic view). Backfill: a task-linked
    # approval belongs to its task's owner, anything else to u_owner.
    # Queries are fail-closed (WHERE user_id=?), so the backfill must leave
    # no NULLs behind.
    appr_cols = {r[1] for r in conn.execute("PRAGMA table_info(approvals)").fetchall()}
    if "user_id" not in appr_cols:
        conn.execute("ALTER TABLE approvals ADD COLUMN user_id TEXT")
    conn.execute(
        "UPDATE approvals SET user_id = COALESCE("
        "(SELECT t.user_id FROM tasks t WHERE t.id = json_extract(approvals.payload, '$.task_id')),"
        " 'u_owner') WHERE user_id IS NULL")

    # ===== Eval corpus tables (Block 3, additive — docs/SPEC-BLOCK3.md R3) =====
    # A run executes fixed per-domain briefs through the real dispatch framing
    # and scores each deliverable with the frontier judge against the rubric.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS eval_runs (
        id TEXT PRIMARY KEY,
        domain TEXT NOT NULL,
        notes TEXT DEFAULT '',
        status TEXT DEFAULT 'running',
        cases_total INTEGER DEFAULT 0,
        cases_done INTEGER DEFAULT 0,
        score_total INTEGER DEFAULT 0,
        score_max INTEGER DEFAULT 0,
        ship_count INTEGER DEFAULT 0,
        fingerprint TEXT DEFAULT '{}',
        error TEXT,
        started_at REAL,
        ended_at REAL,
        user_id TEXT NOT NULL
    )""")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS eval_results (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        case_id TEXT NOT NULL,
        case_title TEXT DEFAULT '',
        specialist TEXT,
        model TEXT,
        status TEXT DEFAULT 'pending',
        verdict TEXT,
        score INTEGER,
        score_max INTEGER,
        gates_passed INTEGER,
        gates_failed INTEGER,
        judge_output TEXT,
        deliverable_path TEXT,
        tokens_used INTEGER DEFAULT 0,
        gen_seconds REAL,
        error TEXT,
        started_at REAL,
        ended_at REAL
    )""")

    # Item 9 (2026-07-12): per-user GitHub identity — publish/push/PR run as
    # the project owner's account when they set a PAT (credentials provider
    # 'github'); these two columns carry the matching git author identity.
    _u_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "github_username" not in _u_cols:
        conn.execute("ALTER TABLE users ADD COLUMN github_username TEXT")
    if "git_email" not in _u_cols:
        conn.execute("ALTER TABLE users ADD COLUMN git_email TEXT")

    # Item 6c (2026-07-12): eval → improvement loop state on the run row.
    # improve_status: none|drafting|proposed|applied|rejected|error.
    _er_cols = {r[1] for r in conn.execute("PRAGMA table_info(eval_runs)").fetchall()}
    if "improve_status" not in _er_cols:
        conn.execute("ALTER TABLE eval_runs ADD COLUMN improve_status TEXT")
    if "improve_approval_id" not in _er_cols:
        conn.execute("ALTER TABLE eval_runs ADD COLUMN improve_approval_id TEXT")

    # ===== Settings v2 (docs/SPEC-SETTINGS-V2.md): encrypted credentials +
    # per-user model registry. user_id NULL = global (admin-managed) row.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS credentials (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        provider TEXT NOT NULL,
        label TEXT DEFAULT '',
        enc_value TEXT NOT NULL,
        hint TEXT DEFAULT '',
        created_at REAL,
        updated_at REAL,
        created_by TEXT
    )""")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS user_models (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        provider TEXT NOT NULL,
        model_id TEXT NOT NULL,
        label TEXT DEFAULT '',
        route TEXT NOT NULL DEFAULT 'hermes',
        credential_id TEXT,
        enabled INTEGER DEFAULT 1,
        config TEXT DEFAULT '{}',
        created_at REAL,
        updated_at REAL
    )""")
    # Item 15 (2026-07-12): per-model capability description ("Strengths /
    # Weaknesses / Best for / Avoid for") — powers the deterministic
    # description-informed routing in routing.select_model_for_task.
    _um_cols = {r[1] for r in conn.execute("PRAGMA table_info(user_models)").fetchall()}
    if "description" not in _um_cols:
        conn.execute("ALTER TABLE user_models ADD COLUMN description TEXT DEFAULT ''")

    # Purpose → model routing. user_id 'global' = the default assignment every
    # user inherits until they set their own override.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS model_assignments (
        user_id TEXT NOT NULL,
        purpose TEXT NOT NULL,
        model_row_id TEXT NOT NULL,
        updated_at REAL,
        PRIMARY KEY (user_id, purpose)
    )""")
    # Seed the registry ONCE (empty table = pre-Settings-v2 install): the same
    # three GLM tiers the code hardcoded, plus the frontier judge that was
    # previously invisible (cjudge → Claude CLI default = Opus 4.8). Behavior
    # with these rows is identical to before the registry existed. Deliberate
    # deletions stay deleted — this block never re-seeds a non-empty table.
    if not conn.execute("SELECT 1 FROM user_models LIMIT 1").fetchone():
        now = time.time()
        seed_models = [
            ("mdl-glm52", "zai", "glm-5.2", "GLM 5.2 (hard thinking)", "hermes"),
            ("mdl-glm51", "zai", "glm-5.1", "GLM 5.1 (light/simple)", "hermes"),
            ("mdl-glm45air", "zai", "glm-4.5-air", "GLM 4.5 Air (mechanical)", "hermes"),
            ("mdl-glm5turbo", "zai", "glm-5-turbo", "GLM 5 Turbo (peak-hours fallback)", "hermes"),
            ("mdl-opus48", "anthropic", "claude-opus-4-8", "Claude Opus 4.8 (frontier judge)", "cli"),
        ]
        for mid, prov, model_id, label, route in seed_models:
            conn.execute(
                "INSERT OR IGNORE INTO user_models (id, user_id, provider, model_id, label, "
                "route, enabled, created_at, updated_at) VALUES (?,NULL,?,?,?,?,1,?,?)",
                (mid, prov, model_id, label, route, now, now))
        for purpose, mid in (("complicated", "mdl-glm52"), ("easy", "mdl-glm51"),
                             ("mechanical", "mdl-glm45air"), ("frontier_judge", "mdl-opus48"),
                             # Deep Plan (Phase 5): spec_model runs the premortem plan
                             # critique — an EXTERNAL judgment-tier verifier, seeded to
                             # the same frontier judge as frontier_judge (rotate later).
                             ("spec_model", "mdl-opus48"),
                             # Appendix C1c: escalation_model writes the escalated
                             # rework — same judgment-tier default (Opus 4.8), rotated
                             # up one tier each generation with the others.
                             ("escalation_model", "mdl-opus48")):
            conn.execute(
                "INSERT OR IGNORE INTO model_assignments (user_id, purpose, model_row_id, "
                "updated_at) VALUES ('global',?,?,?)", (purpose, mid, now))

    # Appendix C3 (full-cost ledger): one row per frontier subprocess run
    # (critic / judge / spec-premortem / escalated rework). tokens + cost_usd
    # come from the `claude -p --output-format json` envelope when present
    # (source='envelope') else a transcript-size estimate priced from the
    # settings table (source='estimate'). The task accumulators frontier_tokens/
    # frontier_cost_usd are bumped in the same write. Keeps SR's real spend from
    # being invisible (B7) so "beats Opus, cheaper than Fable" is checkable.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS frontier_ledger (
        id TEXT PRIMARY KEY,
        task_id TEXT,
        workflow_id TEXT,
        eval_run_id TEXT,
        user_id TEXT,
        kind TEXT,
        model TEXT,
        tokens INTEGER DEFAULT 0,
        cost_usd REAL DEFAULT 0,
        source TEXT,
        created_at REAL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frontier_ledger_task "
                 "ON frontier_ledger(task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frontier_ledger_wf "
                 "ON frontier_ledger(workflow_id)")
    # [19]: eval-run judge spend gets its OWN column — it used to be stuffed
    # into the workflow_id slot, so any ledger→workflows join silently mixed
    # in eval rows. One-time backfill moves the old judge_eval rows over.
    fl_cols = {r[1] for r in conn.execute("PRAGMA table_info(frontier_ledger)").fetchall()}
    if "eval_run_id" not in fl_cols:
        conn.execute("ALTER TABLE frontier_ledger ADD COLUMN eval_run_id TEXT")
        conn.execute("UPDATE frontier_ledger SET eval_run_id=workflow_id, workflow_id=NULL "
                     "WHERE kind='judge_eval' AND workflow_id IS NOT NULL")

    # Deep Plan mode (Phase 5): conversational planning sessions. Resumable —
    # no boot-reset; stale 'active' rows are swept >7 days by the plan engine
    # at startup and on the scheduler.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS plan_sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        goal TEXT,
        family TEXT,
        spec_json TEXT,
        transcript TEXT,
        hermes_session_id TEXT,
        status TEXT DEFAULT 'active',
        triage_json TEXT,
        created_at REAL,
        updated_at REAL
    )""")
    # 2026-07-12: sessions grounded on an existing repo — the interview, draft
    # and revise turns all read this so the plan is a CHANGE, not a greenfield.
    existing_ps_cols = {r[1] for r in conn.execute("PRAGMA table_info(plan_sessions)").fetchall()}
    if "repo_path" not in existing_ps_cols:
        conn.execute("ALTER TABLE plan_sessions ADD COLUMN repo_path TEXT")

    # One-time addition (2026-07-08): glm-5-turbo, the peak-hours overload
    # fallback (settings dispatch.fallback_model) — pre-existing installs
    # seeded before it existed get the row here. Marker-guarded so a deliberate
    # later deletion stays deleted (same contract as the seed block above).
    if not conn.execute("SELECT 1 FROM settings WHERE key='migrated.glm5turbo'").fetchone():
        now = time.time()
        conn.execute(
            "INSERT OR IGNORE INTO user_models (id, user_id, provider, model_id, label, "
            "route, enabled, created_at, updated_at) VALUES ('mdl-glm5turbo',NULL,'zai',"
            "'glm-5-turbo','GLM 5 Turbo (peak-hours fallback)','hermes',1,?,?)", (now, now))
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('migrated.glm5turbo','1')")

    # One-time addition (2026-07-10, Deep Plan Phase 5): the spec_model purpose —
    # the external judgment-tier verifier for plan premortem critique. Existing
    # installs (non-empty user_models, so the seed block above was skipped) get
    # the global row here, defaulting to whatever frontier_judge currently
    # resolves to (fallback mdl-opus48). Marker-guarded so a deliberate later
    # deletion stays deleted (same contract as the blocks above).
    if not conn.execute("SELECT 1 FROM settings WHERE key='migrated.spec_model'").fetchone():
        now = time.time()
        fj = conn.execute(
            "SELECT model_row_id FROM model_assignments WHERE user_id='global' "
            "AND purpose='frontier_judge'").fetchone()
        seed_mid = (fj[0] if fj else None) or "mdl-opus48"
        conn.execute(
            "INSERT OR IGNORE INTO model_assignments (user_id, purpose, model_row_id, "
            "updated_at) VALUES ('global','spec_model',?,?)", (seed_mid, now))
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('migrated.spec_model','1')")

    # One-time addition (2026-07-10, Appendix C1c Phase 7): the escalation_model
    # purpose — the judgment-tier model that writes the ESCALATED REWORK. Existing
    # installs get the global row here, defaulting to whatever frontier_judge
    # currently resolves to (fallback mdl-opus48). Marker-guarded (same contract).
    if not conn.execute("SELECT 1 FROM settings WHERE key='migrated.escalation_model'").fetchone():
        now = time.time()
        fj = conn.execute(
            "SELECT model_row_id FROM model_assignments WHERE user_id='global' "
            "AND purpose='frontier_judge'").fetchone()
        seed_mid = (fj[0] if fj else None) or "mdl-opus48"
        conn.execute(
            "INSERT OR IGNORE INTO model_assignments (user_id, purpose, model_row_id, "
            "updated_at) VALUES ('global','escalation_model',?,?)", (seed_mid, now))
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('migrated.escalation_model','1')")

    # Seed real-dispatch settings (visible/editable). Real dispatch is the
    # default since v2 shipped — a fresh install behaves like the main machine.
    dispatch_defaults = [
        ("dispatch.enabled", "1"),
        ("dispatch.default_task_budget", "5000000"),
        ("dispatch.daily_cap", "10000000"),
        ("dispatch.max_concurrent_per_model", "8"),
        ("dispatch.max_concurrent_total", "8"),
        ("judge.cmd", "cjudge {file} {domain}"),
        ("super.critic_cmd", "cverify {file} {domain} {sandbox}"),
        ("super.escalation_cmd", "cexec {workspace} {deliverable} {dossier}"),  # C1c
    ]
    for k, v in dispatch_defaults:
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # Appendix C3 (full-cost ledger): the per-model price table (USD per 1M
    # tokens), seeded from MODEL-PRICING-2026-07-10.md (re-verified 2026-07-10).
    # INSERT OR IGNORE so an operator edit sticks. Frontier runs report the
    # envelope's OWN dollars; this table prices the GLM executor (blended token
    # counter) and displays what a model WOULD cost. Fable 5 is priced for the
    # reference/comparison arm only — it is never assigned to a purpose.
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('cost.model_prices', ?)",
                 (json.dumps(MODEL_PRICES_SEED),))
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('cost.output_fraction', '0.5')")

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
        "CREATE INDEX IF NOT EXISTS idx_memory_agent_scope ON memory(agent_id, scope, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_workflows_user ON workflows(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_exp ON auth_sessions(expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_eval_runs_user ON eval_runs(user_id, started_at)",
        "CREATE INDEX IF NOT EXISTS idx_eval_results_run ON eval_results(run_id)",
        "CREATE INDEX IF NOT EXISTS idx_credentials_scope ON credentials(user_id, provider)",
        "CREATE INDEX IF NOT EXISTS idx_user_models_scope ON user_models(user_id, enabled)",
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


# --- Full-cost ledger (Appendix C3) ------------------------------------------
# Per-model prices in USD per 1M tokens, from MODEL-PRICING-2026-07-10.md
# (re-verified 2026-07-10). GLM 5.1/4.5-air/turbo have no separately published
# sheet — priced at the GLM-5.2 public rate as a documented default (edit the
# cost.model_prices setting to refine). Cache write/read follow the doc's
# multipliers. Fable 5 is the reference/comparison arm only (never assigned).
MODEL_PRICES_SEED = {
    "glm-5.2":       {"input": 1.40, "output": 4.40, "cache_write": 0.0,   "cache_read": 0.26},
    "glm-5.1":       {"input": 1.40, "output": 4.40, "cache_write": 0.0,   "cache_read": 0.26},
    "glm-4.5-air":   {"input": 1.40, "output": 4.40, "cache_write": 0.0,   "cache_read": 0.26},
    "glm-5-turbo":   {"input": 1.40, "output": 4.40, "cache_write": 0.0,   "cache_read": 0.26},
    "claude-opus-4-8": {"input": 5.0, "output": 25.0, "cache_write": 6.25, "cache_read": 0.50},
    "claude-fable-5":  {"input": 10.0, "output": 50.0, "cache_write": 12.50, "cache_read": 1.0},
}


def model_prices() -> dict:
    """The per-model price table (settings cost.model_prices), merged over the
    seed so a partial operator edit still covers the built-ins. USD per 1M
    tokens. Never raises — a corrupt setting falls back to the seed."""
    table = dict(MODEL_PRICES_SEED)
    try:
        raw = get_setting("cost.model_prices", None)
        if raw:
            user = json.loads(raw)
            if isinstance(user, dict):
                for k, v in user.items():
                    if isinstance(v, dict):
                        table[k] = {**table.get(k, {}), **v}
    except Exception:
        pass
    return table


def price_for(model_id: str | None) -> dict | None:
    """The price row for a model id (exact, else a prefix match on the family,
    e.g. 'glm-5.2-0710' → 'glm-5.2'). None when unknown."""
    if not model_id:
        return None
    table = model_prices()
    if model_id in table:
        return table[model_id]
    for k, v in table.items():
        if model_id.startswith(k):
            return v
    return None


def blended_rate(model_id: str | None) -> float:
    """A single USD-per-1M-tokens rate for a BLENDED token counter (input+output
    mixed, e.g. tasks.tokens_used). Weighted by cost.output_fraction (default
    0.5) since the counter doesn't split the two. Returns 0 for unknown models
    (unknown = uncounted, never a fabricated cost)."""
    p = price_for(model_id)
    if not p:
        return 0.0
    try:
        frac = float(get_setting("cost.output_fraction", "0.5") or 0.5)
    except (TypeError, ValueError):
        frac = 0.5
    frac = max(0.0, min(1.0, frac))
    return float(p.get("input", 0.0)) * (1 - frac) + float(p.get("output", 0.0)) * frac


def glm_cost_estimate(tokens: int, model_id: str | None) -> float:
    """API-equivalent USD for a GLM run's blended token count. An ESTIMATE (the
    counter is input+output mixed) — the ledger labels it as such."""
    try:
        t = int(tokens or 0)
    except (TypeError, ValueError):
        t = 0
    return round((t / 1_000_000.0) * blended_rate(model_id), 6)


def record_frontier_run(task_id: str | None, kind: str, tokens: int,
                        cost_usd: float | None, source: str,
                        model: str | None = None, workflow_id: str | None = None,
                        user_id: str | None = None,
                        eval_run_id: str | None = None) -> None:
    """C3: log one frontier subprocess run and bump the task's accumulators.
    cost_usd None (an estimate with no price row) counts as 0 dollars but still
    records the tokens. Never raises — a ledger write must never fail a critic/
    judge run."""
    try:
        tok = int(tokens or 0)
    except (TypeError, ValueError):
        tok = 0
    try:
        cost = float(cost_usd) if cost_usd is not None else 0.0
    except (TypeError, ValueError):
        cost = 0.0
    try:
        execute(
            "INSERT INTO frontier_ledger (id, task_id, workflow_id, eval_run_id, user_id, "
            "kind, model, tokens, cost_usd, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f"fl-{uuid.uuid4().hex[:12]}", task_id, workflow_id, eval_run_id, user_id,
             kind, model, tok, cost, source, time.time()))
        if task_id:
            execute("UPDATE tasks SET frontier_tokens=COALESCE(frontier_tokens,0)+?, "
                    "frontier_cost_usd=COALESCE(frontier_cost_usd,0)+? WHERE id=?",
                    (tok, cost, task_id))
    except Exception:
        pass


def task_cost_ledger(task_id: str) -> dict:
    """API-equivalent cost for one task across BOTH currencies: the GLM executor
    (tokens_used priced from the table — an estimate) + the frontier subprocess
    spend (critic/judge/spec/escalation, from the envelope's own dollars). This
    is a COMPARISON figure, not a bill."""
    t = query_one("SELECT model, user_id, tokens_used, frontier_tokens, frontier_cost_usd "
                  "FROM tasks WHERE id=?", (task_id,)) or {}
    glm_tokens = int(t.get("tokens_used") or 0)
    glm_model = effective_task_model(t.get("model"), t.get("user_id"))
    glm_usd = glm_cost_estimate(glm_tokens, glm_model)
    frontier_tokens = int(t.get("frontier_tokens") or 0)
    frontier_usd = round(float(t.get("frontier_cost_usd") or 0.0), 6)
    runs = query_all(
        "SELECT kind, model, tokens, cost_usd, source FROM frontier_ledger "
        "WHERE task_id=? ORDER BY created_at", (task_id,))
    return {
        "glm_tokens": glm_tokens, "glm_usd": round(glm_usd, 4),
        "glm_model": glm_model,   # the RESOLVED model the estimate priced at
        "frontier_tokens": frontier_tokens, "frontier_usd": round(frontier_usd, 4),
        "total_usd": round(glm_usd + frontier_usd, 4),
        "runs": runs,
        "currency": "API-equivalent USD",
        "note": "comparison figure, not a bill — frontier runs bill the Claude "
                "subscription and GLM runs the Z.AI plan; GLM $ is a blended-rate estimate.",
    }


def workflow_cost_ledger(workflow_id: str) -> dict:
    """Same as task_cost_ledger, summed across a workflow's member tasks."""
    rows = query_all(
        "SELECT model, user_id, tokens_used, frontier_tokens, frontier_cost_usd "
        "FROM tasks WHERE workflow_id=?", (workflow_id,))
    glm_tokens = frontier_tokens = 0
    glm_usd = frontier_usd = 0.0
    for r in rows:
        gt = int(r.get("tokens_used") or 0)
        glm_tokens += gt
        glm_usd += glm_cost_estimate(gt, effective_task_model(r.get("model"), r.get("user_id")))
        frontier_tokens += int(r.get("frontier_tokens") or 0)
        frontier_usd += float(r.get("frontier_cost_usd") or 0.0)
    return {
        "tasks": len(rows),
        "glm_tokens": glm_tokens, "glm_usd": round(glm_usd, 4),
        "frontier_tokens": frontier_tokens, "frontier_usd": round(frontier_usd, 4),
        "total_usd": round(glm_usd + frontier_usd, 4),
        "currency": "API-equivalent USD",
        "note": "comparison figure, not a bill.",
    }


# --- Model registry helpers (Settings v2 — shared by server, dispatch, evals) ---

MODEL_PURPOSES = ("complicated", "easy", "mechanical", "frontier_judge",
                  "spec_model", "escalation_model")

# Appendix C2 (rotation readiness): the ONE place that maps a registry purpose to
# its pre-registry fallback model id. These literals are used ONLY when the
# registry has no assignment for a purpose (a wiped/misconfigured registry still
# boots). A GENERATION ROTATION edits the REGISTRY (model_assignments) — zero code
# changes; this map is the safety net, not the routing table. Every hardcoded
# model-name fallback in the codebase now resolves through here (audited out of
# server.py / hermes_dispatch.py / tools_hub.py) so a rotation never means hunting
# string literals. Fable 5 is never here — it is the reference tier, never assigned.
FALLBACK_MODELS = {
    "complicated": "glm-5.2",
    "easy": "glm-5.1",
    "mechanical": "glm-4.5-air",
    "fallback": "glm-5-turbo",          # dispatch overload fallback (setting-backed)
    "frontier_judge": "claude-opus-4-8",
    "spec_model": "claude-opus-4-8",
    "escalation_model": "claude-opus-4-8",
}


def fallback_model(purpose: str) -> str | None:
    """The pre-registry fallback model id for a purpose (C2). None for unknown
    purposes. Callers use it as `resolve_assignment(...) or fallback_model(p)`."""
    return FALLBACK_MODELS.get(purpose)


def worker_fallback_models() -> list[str]:
    """The three GLM executor tiers, in order — the pre-registry fallback list for
    task_models_for / the wizard model dropdown (C2: derived, not re-typed)."""
    return [FALLBACK_MODELS["complicated"], FALLBACK_MODELS["easy"],
            FALLBACK_MODELS["mechanical"]]


def visible_models(user_id: str | None, enabled_only: bool = False) -> list:
    """Global rows + the user's own rows. Foreign users' models never appear."""
    sql = "SELECT * FROM user_models WHERE (user_id IS NULL OR user_id = ?)"
    if enabled_only:
        sql += " AND enabled = 1"
    return query_all(sql + " ORDER BY user_id IS NULL DESC, provider, model_id", (user_id,))


def task_models_for(user_id: str | None) -> list[str]:
    """Model-id strings a task/eval of this user may run on (hermes-routed).
    Falls back to the historical trio if the registry is somehow empty."""
    ids = []
    for m in visible_models(user_id, enabled_only=True):
        if m["route"] == "hermes" and m["model_id"] not in ids:
            ids.append(m["model_id"])
    return ids or worker_fallback_models()  # C2: centralized pre-registry fallback


def resolve_assignment(user_id: str | None, purpose: str) -> dict | None:
    """The model row a purpose routes to: the user's own assignment beats the
    global default. Disabled/vanished targets fall through to global, then None
    (callers keep their pre-registry fallback for that)."""
    for scope in ([user_id, "global"] if user_id and user_id != "global" else ["global"]):
        row = query_one(
            "SELECT m.* FROM model_assignments a JOIN user_models m ON m.id = a.model_row_id "
            "WHERE a.user_id = ? AND a.purpose = ? AND m.enabled = 1",
            (scope, purpose))
        if row and (row["user_id"] is None or row["user_id"] == user_id):
            return row
    return None


def default_task_model(user_id: str | None) -> str | None:
    """The 'complicated' purpose model id, or None (= let Hermes' own default
    apply — identical to pre-registry behavior)."""
    row = resolve_assignment(user_id, "complicated")
    return row["model_id"] if row and row["route"] == "hermes" else None


def effective_task_model(model_id: str | None, user_id: str | None) -> str | None:
    """The model a task's tokens ACTUALLY ran on — the pricing-side mirror of
    hermes_dispatch.resolve_task_model. `tasks.model` NULL is the DELIBERATE
    default (dispatch resolves it to the owner's 'complicated' purpose), so
    pricing MUST resolve it the same way; taking NULL at face value prices the
    dominant case at $0 and makes the C3 cross-currency total meaningless. The
    registry fallback is the last resort so a wiped registry still prices."""
    return model_id or default_task_model(user_id) or fallback_model("complicated")


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
