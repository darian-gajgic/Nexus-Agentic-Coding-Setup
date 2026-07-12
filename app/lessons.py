"""NEXUS Agent OS — Operator-edit distillation (Quality Autopilot Q2 / N8).

Every human correction becomes a permanent lesson. A deterministic sweep (no
LLM) collects per-domain evidence — rejection feedback, the operator's own
review comments, the diff between a rejected and the accepted version (the
strongest signal), and the judges'/critic's learning notes — and when enough
new evidence accrues, ONE judgment-tier call proposes durable deltas to the
domain's STYLE-VOICE / PLAYBOOK / RUBRIC. The deltas are filed as a single
admin-scoped approval (action_type='lesson_deltas'); on approve they are applied
to ~/knowledge and git-committed (like onboarding apply); on reject the feedback
itself becomes fresh evidence.

Autonomy ceiling (binding): collection, analysis and proposal are autonomous;
the WRITE to the knowledge files is gated by the one-click approval. No
unsupervised self-modification of the system's own prompts.
"""
import os
import re
import json
import time
import uuid
import subprocess
import tempfile

import auth
import database as db

KNOWLEDGE_DIR = os.path.expanduser("~/knowledge")
LESSONS_JSON_BEGIN = "NEXUS_LESSONS_JSON_BEGIN"
LESSONS_JSON_END = "NEXUS_LESSONS_JSON_END"
_LESSON_FILES = ("PLAYBOOK.md", "RUBRIC.md", "STYLE-VOICE.md")


def _knowledge_root() -> str:
    return os.path.expanduser(db.get_setting("onboarding.root", "") or KNOWLEDGE_DIR)


# ─────────────────────────── Evidence capture ───────────────────────────

def record_evidence(task: dict, kind: str, content: str):
    """Store one piece of operator-edit evidence for a task's domain. Called from
    the approve/reject paths (feedback, accept_diff). No-op without a domain."""
    domain = (task.get("domain") or "").strip()
    if not domain or domain == "general" or not (content or "").strip():
        return
    try:
        db.execute(
            "INSERT INTO edit_evidence (id, task_id, domain, user_id, kind, content, "
            "distilled, created_at) VALUES (?,?,?,?,?,?,0,?)",
            (f"ev-{uuid.uuid4().hex[:12]}", task.get("id"), domain, task.get("user_id"),
             kind, (content or "")[:8000], time.time()))
    except Exception as e:
        db.log_activity("warn", "lessons", f"evidence capture failed: {str(e)[:80]}")


def _record_domain_feedback(domain: str, user_id: str | None, content: str):
    """Q2: a rejected lesson_deltas card's feedback becomes evidence for the next
    distillation (task-less, so filed straight against the domain)."""
    if not domain or not (content or "").strip():
        return
    try:
        db.execute(
            "INSERT INTO edit_evidence (id, task_id, domain, user_id, kind, content, "
            "distilled, created_at) VALUES (?,?,?,?,?,?,0,?)",
            (f"ev-{uuid.uuid4().hex[:12]}", None, domain, user_id, "feedback",
             ("lesson-review: " + content)[:8000], time.time()))
    except Exception as e:
        db.log_activity("warn", "lessons", f"domain feedback capture failed: {str(e)[:80]}")


def compact_diff(old_text: str, new_text: str, label: str = "") -> str:
    """A compact unified diff between a rejected and an accepted version — the
    strongest correction signal (what the human actually changed)."""
    import difflib
    old = (old_text or "").splitlines()
    new = (new_text or "").splitlines()
    diff = list(difflib.unified_diff(old, new, fromfile=f"rejected {label}".strip(),
                                     tofile=f"accepted {label}".strip(), lineterm="", n=2))
    return "\n".join(diff)[:8000]


# ─────────────────────────── Evidence gathering (for the call) ───────────────────────────

def _new_evidence(domain: str) -> list[dict]:
    return db.query_all(
        "SELECT * FROM edit_evidence WHERE domain=? AND distilled=0 ORDER BY created_at",
        (domain,))


def count_new_evidence(domain: str) -> int:
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM edit_evidence WHERE domain=? AND distilled=0", (domain,))
    return int((row or {}).get("n") or 0)


def gather_evidence_text(domain: str) -> tuple[str, list[str]]:
    """Assemble the evidence document for the distillation call + the ids of the
    edit_evidence rows consumed (marked distilled after a successful run).
    Also folds in user review comments and the judges'/critic's learning notes
    for tasks of this domain — free, high-quality input (B6)."""
    parts, ids = [], []
    rows = _new_evidence(domain)
    for r in rows:
        ids.append(r["id"])
        parts.append(f"### {r['kind']} (task {r.get('task_id') or '-'})\n{r.get('content') or ''}")
    # User review comments on this domain's tasks (deterministic join)
    comments = db.query_all(
        "SELECT rc.body, rc.file_path, rc.line_no FROM review_comments rc "
        "JOIN tasks t ON t.id = rc.task_id "
        "WHERE t.domain=? AND rc.source='user' ORDER BY rc.created_at DESC LIMIT 40",
        (domain,))
    if comments:
        parts.append("### operator review comments\n" + "\n".join(
            f"- {c.get('file_path') or ''}:{c.get('line_no') or ''} — {c.get('body') or ''}"
            for c in comments))
    # Judge/critic learning notes for this domain (B6)
    notes = []
    for t in db.query_all(
            "SELECT learn_section, critic_json FROM tasks WHERE domain=? "
            "AND (learn_section IS NOT NULL OR critic_json IS NOT NULL) "
            "ORDER BY updated_at DESC LIMIT 30", (domain,)):
        if t.get("learn_section"):
            notes.append(str(t["learn_section"])[:600])
        try:
            ln = (json.loads(t.get("critic_json") or "{}") or {}).get("learning_note")
            if ln:
                notes.append(str(ln)[:400])
        except Exception:
            pass
    if notes:
        parts.append("### judge / critic learning notes\n" + "\n".join(f"- {n}" for n in notes[:30]))
    return ("\n\n".join(parts))[:60000], ids


# ─────────────────────────── The distillation call ───────────────────────────

def parse_lesson_deltas(out: str) -> list[dict] | None:
    """Parse the sentinel-fenced JSON deltas from a cdistill run. None on failure."""
    if not out or LESSONS_JSON_BEGIN not in out:
        return None
    try:
        seg = out.split(LESSONS_JSON_BEGIN, 1)[1].split(LESSONS_JSON_END, 1)[0].strip()
        data = json.loads(seg)
    except Exception:
        return None
    deltas = data.get("deltas") if isinstance(data, dict) else None
    if not isinstance(deltas, list):
        return None
    clean = []
    for d in deltas[:5]:
        if not isinstance(d, dict):
            continue
        f = str(d.get("file") or "").strip()
        if f not in _LESSON_FILES:
            continue
        clean.append({
            "file": f,
            "target": "user_overlay" if str(d.get("target")) == "user_overlay" else "canonical",
            "kind": str(d.get("kind") or "add")[:12],
            "before": str(d.get("before") or "")[:500],
            "after": str(d.get("after") or "")[:800],
            "rationale": str(d.get("rationale") or "")[:400],
        })
    return clean


def run_distillation(domain: str, user_id: str | None = None, min_evidence: int | None = None) -> dict:
    """Gather evidence, run ONE judgment-tier distillation call (setting
    lessons.cmd — gates stub it), and file an admin-scoped lesson_deltas approval.
    Returns {ok, reason?, approval_id?, deltas?}."""
    import evals as _ev
    if not re.match(r"^[a-z0-9-]+$", domain or ""):
        return {"ok": False, "reason": "bad domain"}
    n = count_new_evidence(domain)
    need = min_evidence if min_evidence is not None else int(db.get_setting("lessons.min_evidence", "5") or 5)
    if n < need:
        return {"ok": False, "reason": f"only {n} new evidence items (< {need})"}
    if _ev.frontier_backoff_active():
        return {"ok": False, "reason": "frontier quota backoff active — deferred"}
    evidence, ev_ids = gather_evidence_text(domain)
    if not evidence.strip():
        return {"ok": False, "reason": "no evidence text assembled"}
    owner = user_id or auth.DEFAULT_USER_ID  # [15]
    jmodel, jkey = _ev.judge_model_for(owner)
    tmpl = db.get_setting("lessons.cmd", "cdistill {domain} {evidence}") or "cdistill {domain} {evidence}"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, dir="/tmp") as tf:
        tf.write(evidence)
        evid_path = tf.name
    try:
        # [13]/[R3]: shell=False + brace-safe per-token replacement — the SAME
        # resolver as judge.cmd/critic_cmd/escalation_cmd/plan.critique_cmd
        # (evals.resolve_cmd_tokens). The old tmpl.format(...) raised KeyError
        # on any literal brace in a customized lessons.cmd (awk/jq), and
        # shell=True made this the only frontier hook interpreted by a shell.
        tokens = _ev.resolve_cmd_tokens(tmpl, {"domain": domain, "evidence": evid_path,
                                               "model": jmodel})
        # [5]: the scrubbed env every other frontier subprocess gets — secrets
        # (GLM_API_KEY, …) stripped + the claude CLI PATH fix (phase7 finding 1);
        # raw os.environ re-introduced both gaps on this call site.
        env = _ev._scrubbed_env()
        if jmodel:
            env["JUDGE_MODEL"] = jmodel
        if jkey:
            env["JUDGE_ANTHROPIC_API_KEY"] = jkey
        timeout = int(db.get_setting("super.timeout_s", "1500") or 1500)
        with _ev._FRONTIER_GATE:  # global frontier concurrency cap (premortem P1)
            r = subprocess.run(tokens, capture_output=True, text=True,
                               timeout=timeout, env=env)
        out = (r.stdout or "") + (("\n" + r.stderr) if r.returncode else "")
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "distillation timed out"}
    except Exception as e:
        return {"ok": False, "reason": f"distillation error: {str(e)[:120]}"}
    finally:
        try:
            os.unlink(evid_path)
        except Exception:
            pass
    deltas = parse_lesson_deltas(out)
    if deltas is None:
        if _ev.is_frontier_quota_error(out):
            _ev.note_frontier_quota_hit()  # transient — leave evidence undistilled, retry later
            return {"ok": False, "reason": "frontier quota/rate-limit — deferred"}
        return {"ok": False, "reason": "no parseable deltas"}
    _ev.note_frontier_quota_ok()
    # Mark the consumed evidence distilled even when zero deltas — we asked, the
    # model found nothing durable; re-asking the same evidence wastes a call.
    for eid in ev_ids:
        db.execute("UPDATE edit_evidence SET distilled=1 WHERE id=?", (eid,))
    if not deltas:
        db.log_activity("info", "lessons",
                        f"Distillation for '{domain}': no durable lessons from {n} items")
        return {"ok": True, "reason": "no durable deltas", "deltas": []}
    payload = {"domain": domain, "deltas": deltas, "evidence_count": n,
               "recommendation": "Review each proposed lesson; approve to fold it into "
               "the knowledge base (git-committed).",
               "reasons": [f"{len(deltas)} durable delta(s) distilled from {n} operator "
                           "corrections", "each delta cites the evidence that justifies it"],
               "cost_hint": "no model cost to apply (deltas already generated)"}
    aid = f"appr-{uuid.uuid4().hex[:10]}"
    db.execute(
        "INSERT INTO approvals (id, agent_id, action_type, description, payload, status, "
        "risk_level, requested_at, user_id, scope) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (aid, "lessons-distiller", "lesson_deltas",
         f"{len(deltas)} distilled lesson(s) for '{domain}' — review & apply to the knowledge base",
         json.dumps(payload), "pending", "medium", time.time(), owner, "admin"))
    db.log_activity("info", "lessons",
                    f"Distillation for '{domain}': {len(deltas)} delta(s) proposed → approval {aid}")
    return {"ok": True, "approval_id": aid, "deltas": deltas}


# ─────────────────────────── Apply (approve path) ───────────────────────────

def _git(root: str, *args) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=30)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()[-400:]
    except Exception as e:
        return 1, str(e)[:200]


def _delta_path(root: str, domain: str, file: str, target: str, user_id: str | None) -> str:
    """Resolve a delta to a concrete knowledge file. PLAYBOOK/RUBRIC live under
    the domain; STYLE-VOICE is business-wide. L2: user_overlay STYLE-VOICE goes
    to the user's overlay dir (users/<uid>/), everything else canonical."""
    if file == "STYLE-VOICE.md":
        if target == "user_overlay" and user_id and user_id != auth.DEFAULT_USER_ID:
            d = os.path.join(root, "users", user_id)
            os.makedirs(d, exist_ok=True)
            return os.path.join(d, "STYLE-VOICE.md")
        return os.path.join(root, "STYLE-VOICE.md")
    return os.path.join(root, "domains", domain, file)


def apply_deltas(domain: str, deltas: list[dict], user_id: str | None, username: str = "operator") -> dict:
    """Apply approved deltas to the knowledge files, git-safe (snapshot dirty tree
    first, then commit). 'add' appends the after-text; 'reword'/'tighten' replace
    the before-text when found, else append with a marker. Returns a summary."""
    root = _knowledge_root()
    code, out = _git(root, "status", "--porcelain")
    git_ok = code == 0
    if git_ok and out.strip():
        _git(root, "add", "-A")
        _git(root, "-c", "user.name=nexus", "-c", "user.email=nexus@local",
             "commit", "-m", "pre-lessons snapshot (auto — nothing is lost)")
    applied, written = [], set()
    for d in deltas:
        if not isinstance(d, dict) or str(d.get("file")) not in _LESSON_FILES:
            continue
        target = "user_overlay" if str(d.get("target")) == "user_overlay" else "canonical"
        path = _delta_path(root, domain, d["file"], target, user_id)
        before = (d.get("before") or "").strip()
        after = (d.get("after") or "").strip()
        if not after:
            continue
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            cur = ""
            if os.path.isfile(path):
                cur = open(path, encoding="utf-8").read()
            if before and before in cur:
                cur = cur.replace(before, after, 1)
            else:
                sep = "" if cur.endswith("\n") or not cur else "\n"
                cur = cur + sep + "\n" + after + "\n"
            with open(path, "w", encoding="utf-8") as f:
                f.write(cur)
            written.add(path)
            applied.append({"file": d["file"], "target": target, "path": path})
        except Exception as e:
            db.log_activity("warn", "lessons", f"delta apply failed for {path}: {str(e)[:80]}")
    committed = False
    if git_ok and written:
        _git(root, "add", *written)
        code, _ = _git(root, "-c", "user.name=nexus", "-c", "user.email=nexus@local",
                       "commit", "-m",
                       f"lessons({domain}): {len(applied)} distilled delta(s) applied")
        committed = code == 0
    db.log_activity("info", "lessons",
                    f"Applied {len(applied)} lesson delta(s) for '{domain}' "
                    f"(git_committed={committed})", user_id=user_id)
    return {"applied": applied, "git_committed": committed}


# ─────────────────────────── Scheduler sweep ───────────────────────────

def sweep_distillation():
    """Cron-gated autonomous distillation (lessons.auto_distill + lessons.cron).
    For each domain with >= lessons.min_evidence undistilled items, run ONE
    distillation if the cron window is due and none is pending. Deterministic
    schedule guard via a per-domain last-run marker so it fires once per window."""
    if db.get_setting("lessons.auto_distill", "1") != "1":
        return
    cron = db.get_setting("lessons.cron", "0 4 * * 1") or "0 4 * * 1"  # weekly Mon 04:00
    try:
        import scheduler as _sch
        # due when the previous scheduled fire time has passed since the last run
        last = float(db.get_setting("lessons.last_run", "0") or 0)
        # [20]: last==0 means NEVER ran — every scheduled fire time has passed,
        # so it is due now. Feeding 0 into next_run treated it as "now" (falsy
        # `after`), making due_at always the NEXT future occurrence and this
        # early return unconditional — the setter at the bottom (the only
        # writer of lessons.last_run) was unreachable and auto-distillation
        # never fired. Bounded: min_evidence + the pending-approval skip below.
        if last:
            due_at = _sch.next_run(cron, last)
            if due_at > time.time():
                return
    except Exception:
        return
    domains = db.query_all(
        "SELECT domain, COUNT(*) AS n FROM edit_evidence WHERE distilled=0 GROUP BY domain")
    need = int(db.get_setting("lessons.min_evidence", "5") or 5)
    ran = 0
    for row in domains:
        d = row.get("domain")
        if not d or int(row.get("n") or 0) < need:
            continue
        # skip if a lesson_deltas approval for this domain is already pending
        pend = db.query_one(
            "SELECT id FROM approvals WHERE status='pending' AND action_type='lesson_deltas' "
            "AND payload LIKE ?", (f'%"domain": "{d}"%',))
        if pend:
            continue
        res = run_distillation(d)
        if res.get("ok"):
            ran += 1
    db.set_setting("lessons.last_run", time.time())
    if ran:
        db.log_activity("info", "lessons", f"Weekly distillation swept {ran} domain(s)")
