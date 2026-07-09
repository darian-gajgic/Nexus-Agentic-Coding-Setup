"""NEXUS Agent OS — Looping (v3.2): designer + closed-loop runtime engine.

A LOOP wires a task's/project's QUALITY VERDICTS back into WORK:

  open loop   — every checkpoint (failed verification, judge says REVISE)
                stops and waits for the human to press Retry. Nothing runs
                on its own; you stay in full control of every iteration.
  closed loop — the engine automatically feeds the findings back to the
                task that must fix them and re-runs the check, a bounded
                number of rounds, then escalates to the human. This is the
                evaluator-optimizer pattern: iterate against a real gate
                (verifier PASS/FAIL, frontier-judge SHIP/REVISE) instead of
                shipping the first attempt.

The DESIGNER is deterministic (no LLM, instant, auditable): it inspects the
task/project (pipeline shape, high-stakes flag, domain rubric, specialist)
plus the operator's quality-vs-speed preference and emits a loop_config JSON
with plain-language reasoning. The ENGINE is a server-side sweep (thread,
like the watchdog) that fires the configured triggers via the local HTTP API
(retry + judge endpoints do the heavy lifting: deliverable versioning,
approval expiry, feedback attachment).

Bounded by design: per-trigger round caps, per-sweep action cap, budget
checks stay in force, and every action lands in the activity feed.
"""
import os
import json
import re
import sys
import time
import threading

import httpx

import database as db

API = "https://127.0.0.1:8777"
SWEEP_S = 20
MAX_ACTIONS_PER_SWEEP = 3  # storm brake: a runaway loop can't drain the budget

KNOWLEDGE_DIR = os.path.expanduser("~/knowledge")


# ─────────────────────────── DESIGNER ───────────────────────────

def _judgeable(domain: str | None) -> bool:
    return bool(domain) and os.path.isfile(
        os.path.join(KNOWLEDGE_DIR, "domains", domain, "RUBRIC.md"))


def design_loop(kind: str, meta: dict, preference: str = "quality",
                mode: str = "closed") -> dict:
    """Deterministic, task-specific loop design following the house pipeline +
    SOTA practice (evaluator-optimizer with bounded rounds). Returns a full
    loop_config dict incl. plain-language reasoning."""
    preference = preference if preference in ("quality", "speed") else "quality"
    mode = mode if mode in ("closed", "open") else "closed"
    q = preference == "quality"
    title = (meta.get("title") or meta.get("name") or "").strip()
    domain = (meta.get("domain") or "").strip() or None
    high_stakes = bool(meta.get("high_stakes"))
    specialists = meta.get("specialists") or ([meta.get("specialist")] if meta.get("specialist") else [])
    specialists = [s for s in specialists if s]
    has_verifier = "acceptance-verifier" in specialists
    has_fixer = "code-implementer" in specialists
    judge_ok = _judgeable(domain)

    triggers, reasoning = [], []
    reasoning.append(
        f"Designed for {'project' if kind == 'workflow' else 'task'} "
        f"“{title[:80]}” with the ‘{'maximum quality' if q else 'speed / token efficiency'}’ "
        "preference you picked.")

    if kind == "workflow" and has_verifier:
        rounds = 2 if q else 1
        triggers.append({
            "id": "verify_fail", "enabled": True,
            "label": "Failed inspection → automatic fix round",
            "action": "retry_fix_then_reverify",
            "max_rounds": rounds, "used": 0,
            "explain": (
                "The project ends with an independent inspection (the "
                "acceptance-verifier runs the spec's checks against the real "
                "result). When that inspection says FAIL, this trigger sends "
                "the inspector's findings back to the fix task, lets it repair "
                "the work, and then re-runs the inspection — up to "
                f"{rounds} time(s) — before asking you."),
        })
        reasoning.append(
            "This project has a built-in final inspection, which is the "
            "strongest possible checkpoint: it runs real commands and returns "
            "a hard PASS or FAIL. Looping on a hard checkpoint is best "
            "practice (an automatic fix round is how a good team works: build "
            "→ check → fix → re-check)."
            + (" Two rounds because you chose quality — most real defects are "
               "fixed in round one, round two catches fixes that broke "
               "something else." if q else
               " One round only, because you chose speed — one automatic "
               "repair catches the common case without extra token spend."))
        if not has_fixer:
            reasoning.append(
                "Note: no dedicated fix task exists, so the findings go back "
                "to the task that produced the result.")

    if judge_ok and (high_stakes or kind == "task"):
        rounds = 2 if q else 1
        triggers.append({
            "id": "judge_revise", "enabled": True,
            "label": "Judge says REVISE → automatic rework",
            "action": "retry_with_judge_findings",
            "max_rounds": rounds, "used": 0,
            "explain": (
                "A second, stronger AI (the frontier judge) grades the "
                "deliverable against your domain rubric. If it says REVISE or "
                "REWRITE, this trigger sends its findings back and re-runs "
                f"the work — up to {rounds} time(s) — then re-judges the new "
                "version. It stops and waits for you once the rounds are used "
                "or the judge says SHIP."),
        })
        reasoning.append(
            "The deliverable can be graded against your "
            f"“{domain}” rubric by a different, stronger model — judging with "
            "a second model family catches blind spots the working model "
            "cannot see about itself.")

    auto_judge = bool(q and judge_ok and high_stakes and mode == "closed")
    if auto_judge:
        reasoning.append(
            "Because you chose quality and this is high-stakes, the judge is "
            "run AUTOMATICALLY when a deliverable is ready — you review work "
            "that already survived the judge, instead of judging it yourself "
            "first.")
    elif judge_ok and high_stakes:
        reasoning.append(
            "Speed mode: the judge is NOT run automatically (it costs time "
            "and tokens) — the loop only reacts if you run the judge "
            "yourself and it says REVISE.")

    if not triggers:
        reasoning.append(
            "No hard checkpoint exists for this item (no final inspection "
            "task, and no domain rubric for the judge), so there is nothing "
            "safe to loop on automatically. The loop stays formally enabled "
            "but has no triggers — add a domain with a rubric, or make it a "
            "project with an acceptance-verification stage, to give the loop "
            "a real checkpoint.")

    if mode == "open":
        reasoning.append(
            "OPEN loop: all checkpoints stop and wait for you. The system "
            "never re-runs work on its own — you press Retry when you agree "
            "with the findings. Choose this when you want eyes on every "
            "iteration (e.g. anything customer-facing you want to steer).")
    else:
        reasoning.append(
            "CLOSED loop: failures are fed back and re-worked automatically "
            "within the round limits above, then the system escalates to "
            "you. Budgets still apply — every round counts against the "
            "task's token budget and the daily cap, so a runaway loop is "
            "structurally impossible.")

    return {
        "enabled": True,
        "mode": mode,
        "preference": preference,
        "auto_judge": auto_judge,
        "triggers": triggers,
        "reasoning": reasoning,
        "designed_for": title[:120],
        "designed_at": time.time(),
    }


# ─────────────────────────── RUNTIME ENGINE ───────────────────────────

def _cfg(row) -> dict | None:
    try:
        c = json.loads(row.get("loop_config") or "null")
        return c if isinstance(c, dict) else None
    except Exception:
        return None


def _save_cfg(kind: str, oid: str, cfg: dict):
    table = "tasks" if kind == "task" else "workflows"
    db.execute(f"UPDATE {table} SET loop_config=? WHERE id=?", (json.dumps(cfg), oid))


def _trigger(cfg: dict, tid: str) -> dict | None:
    for t in cfg.get("triggers") or []:
        if t.get("id") == tid and t.get("enabled") and \
                int(t.get("used") or 0) < int(t.get("max_rounds") or 0):
            return t
    return None


# An explicit labelled verdict wins; otherwise the first STANDALONE uppercase
# token. Word boundaries + case sensitivity keep prose like "all tests passed"
# or "failures: 0" from inverting the verdict (they did, as bare substrings).
_VERDICT_LABELLED = re.compile(r"VERDICT\s*[:\-]?\s*\**\s*(PASS|FAIL)\b", re.I)
_VERDICT_TOKEN = re.compile(r"\b(PASS|FAIL)\b")


def _verdict_from_summary(summary: str | None) -> str | None:
    """The acceptance-verifier's contract is an explicit PASS or FAIL."""
    head = (summary or "")[:600]
    m = _VERDICT_LABELLED.search(head)
    if m:
        return m.group(1).upper()
    m = _VERDICT_TOKEN.search(head)
    return m.group(1) if m else None


def _api(method: str, path: str, body: dict | None = None,
         user_id: str | None = None) -> bool:
    """Local API call, authenticated as the OWNING USER of the work being
    looped (in-process service token — see auth.INTERNAL_TOKEN). The engine
    runs in the server process, so the token is shared module state."""
    try:
        import auth as _auth
        headers = {_auth.INTERNAL_HEADER: _auth.INTERNAL_TOKEN}
        if user_id:
            headers[_auth.INTERNAL_USER_HEADER] = user_id
        r = httpx.request(method, API + path, json=body, headers=headers,
                          verify=False, timeout=20)
        return r.status_code < 300
    except Exception as e:
        db.log_activity("warn", "loop", f"engine API call {path} failed: {str(e)[:80]}")
        return False


def _sweep_workflow_loops(actions_left: int) -> int:
    """verify_fail: verifier finished FAIL → retry fix with findings, re-verify."""
    rows = db.query_all(
        "SELECT * FROM workflows WHERE loop_config IS NOT NULL")
    for wf in rows:
        if actions_left <= 0:
            break
        cfg = _cfg(wf)
        if not cfg or not cfg.get("enabled") or cfg.get("mode") != "closed":
            continue
        trig = _trigger(cfg, "verify_fail")
        if not trig:
            continue
        tasks = db.query_all(
            "SELECT * FROM tasks WHERE workflow_id=? AND status != 'archived' "
            "ORDER BY created_at", (wf["id"],))
        ver = next((t for t in tasks if t.get("specialist") == "acceptance-verifier"), None)
        if not ver or ver.get("dispatch_state") != "completed" \
                or ver.get("status") not in ("review", "done"):
            continue
        if _verdict_from_summary(ver.get("result_summary")) != "FAIL":
            continue
        fixer = next((t for t in reversed(tasks) if t.get("specialist") == "code-implementer"), None) \
            or next((t for t in reversed(tasks) if t["id"] != ver["id"]), None)
        if not fixer or fixer.get("status") == "in_progress":
            continue
        findings = (ver.get("result_summary") or "")[:3000]
        ok1 = _api("POST", f"/api/tasks/{fixer['id']}/retry", {
            "feedback": "The acceptance verification FAILED. Fix every blocking "
                        "finding below, then the inspection re-runs automatically "
                        "(closed loop, round "
                        f"{int(trig['used']) + 1}/{trig['max_rounds']}):\n" + findings},
                   user_id=fixer.get("user_id"))
        ok2 = _api("POST", f"/api/tasks/{ver['id']}/retry", {},
                   user_id=ver.get("user_id"))  # re-verify after fix
        if ok1 and ok2:
            trig["used"] = int(trig.get("used") or 0) + 1
            _save_cfg("workflow", wf["id"], cfg)
            db.log_activity("warn", "loop",
                            f"CLOSED LOOP round {trig['used']}/{trig['max_rounds']}: "
                            f"verification FAILED on '{wf['name']}' — fix task re-queued "
                            "with findings, inspection will re-run")
            actions_left -= 1
    return actions_left


def _trigger_rounds(trig: dict, task_id: str | None) -> int:
    """Rounds already used — per-task when the loop is INHERITED from a
    workflow (each member task gets its own round budget)."""
    if task_id is not None:
        return int((trig.get("used_tasks") or {}).get(task_id) or 0)
    return int(trig.get("used") or 0)


def _bump_rounds(trig: dict, task_id: str | None):
    if task_id is not None:
        ut = trig.setdefault("used_tasks", {})
        ut[task_id] = int(ut.get(task_id) or 0) + 1
    else:
        trig["used"] = int(trig.get("used") or 0) + 1


def _sweep_task_loops(actions_left: int) -> int:
    """judge_revise + auto_judge on loop-enabled tasks. A task with its own
    loop_config uses it; otherwise it INHERITS its project's loop (the
    operator's mental model: 'the project has a loop' covers members), with
    per-task round accounting stored on the workflow trigger."""
    own = db.query_all(
        "SELECT * FROM tasks WHERE loop_config IS NOT NULL "
        "AND status IN ('review','done') AND dispatch_state='completed'")
    inherited = db.query_all(
        "SELECT t.*, w.loop_config AS _wf_cfg, w.id AS _wf_id FROM tasks t "
        "JOIN workflows w ON w.id = t.workflow_id "
        "WHERE t.loop_config IS NULL AND w.loop_config IS NOT NULL "
        "AND t.status IN ('review','done') AND t.dispatch_state='completed'")
    candidates = [(t, _cfg(t), "task", t["id"], None) for t in own] + \
                 [(t, _cfg({"loop_config": t.get("_wf_cfg")}), "workflow",
                   t.get("_wf_id"), t["id"]) for t in inherited]
    for t, cfg, owner_kind, owner_id, per_task in candidates:
        if actions_left <= 0:
            break
        if not cfg or not cfg.get("enabled") or cfg.get("mode") != "closed":
            continue
        verdict = t.get("judge_verdict")
        judged_this_version = bool(t.get("judge_ts")) and \
            (t.get("judge_ts") or 0) >= (t.get("completed_at") or t.get("updated_at") or 0)
        # 1) auto-judge a fresh deliverable (quality mode, high-stakes, rubric)
        if cfg.get("auto_judge") and not judged_this_version and verdict != "running" \
                and bool(t.get("high_stakes")) and _judgeable(t.get("domain")):
            if _api("POST", f"/api/tasks/{t['id']}/judge", {}, user_id=t.get("user_id")):
                db.log_activity("info", "loop",
                                f"Loop auto-ran the frontier judge on '{t['title'][:50]}'"
                                + (" (project loop)" if per_task else ""))
                actions_left -= 1
            continue
        # 2) judge said REVISE/REWRITE on THIS version → automatic rework round
        if verdict in ("REVISE", "REWRITE") and judged_this_version:
            trig = next((x for x in (cfg.get("triggers") or [])
                         if x.get("id") == "judge_revise" and x.get("enabled")), None)
            if not trig or _trigger_rounds(trig, per_task) >= int(trig.get("max_rounds") or 0):
                continue
            if _api("POST", f"/api/tasks/{t['id']}/retry", {},
                    user_id=t.get("user_id")):  # retry auto-attaches judge findings
                _bump_rounds(trig, per_task)
                _save_cfg(owner_kind, owner_id, cfg)
                used = _trigger_rounds(trig, per_task)
                db.log_activity("warn", "loop",
                                f"CLOSED LOOP round {used}/{trig['max_rounds']}: "
                                f"judge said {verdict} on '{t['title'][:50]}' — re-queued "
                                "with the judge's findings"
                                + (" (project loop)" if per_task else ""))
                actions_left -= 1
    return actions_left


def _parse_replan(wf) -> dict | None:
    try:
        rp = json.loads(wf.get("replan") or "null")
        return rp if isinstance(rp, dict) else None
    except Exception:
        return None


def _sweep_replan_detection():
    """R2.1 (SPEC-BLOCK3): DETECTION ONLY — free, no LLM, no action. Flags a
    workflow replan.status='needed' when a stage failed terminally or the final
    inspection failed with no automatic fix round remaining. Drafting and
    applying stay behind the operator (gated deliberately: this is the
    loop-engine touchpoint, and the engine must never rewrite a pipeline)."""
    for wf in db.query_all("SELECT * FROM workflows WHERE status='active'"):
        rp = _parse_replan(wf)
        if rp and rp.get("status") in ("needed", "drafting", "proposed"):
            continue  # a checkpoint is already open
        tasks = db.query_all(
            "SELECT * FROM tasks WHERE workflow_id=? AND status != 'archived' "
            "ORDER BY created_at", (wf["id"],))
        if not tasks:
            continue
        # A dismissed/applied checkpoint covers exactly ONE failure — a
        # DIFFERENT stage failing later must re-arm the checkpoint.
        handled = rp.get("failed_task_id") \
            if rp and rp.get("status") in ("dismissed", "applied") else None
        candidates = []  # (reason, task_id, title)
        for t in tasks:
            if t.get("dispatch_state") == "failed":
                candidates.append((
                    f"stage '{t['title'][:60]}' failed terminally: "
                    f"{(t.get('dispatch_error') or 'no error recorded')[:200]}",
                    t["id"], t["title"]))
        if not candidates:
            ver = next((t for t in reversed(tasks)
                        if t.get("specialist") == "acceptance-verifier"), None)
            if ver and ver.get("dispatch_state") == "completed" \
                    and ver.get("status") in ("review", "done") \
                    and _verdict_from_summary(ver.get("result_summary")) == "FAIL":
                cfg = _cfg(wf)
                trig = _trigger(cfg, "verify_fail") \
                    if cfg and cfg.get("enabled") and cfg.get("mode") == "closed" else None
                if not trig:  # no automatic fix round remains → human checkpoint
                    candidates.append((
                        "final inspection FAILED and no automatic fix round "
                        "remains — replan or fix by hand", ver["id"], ver["title"]))
        fresh = next((c for c in candidates if c[1] != handled), None)
        if not fresh:
            continue
        reason, fid, ftitle = fresh
        payload = {"status": "needed", "reason": reason, "failed_task_id": fid,
                   "failed_task_title": (ftitle or "")[:200], "detected_at": time.time()}
        db.execute("UPDATE workflows SET replan=? WHERE id=?",
                   (json.dumps(payload), wf["id"]))
        db.log_activity("warn", "loop",
                        f"REPLAN checkpoint on '{wf['name']}': {reason[:150]} "
                        "(open the project to draft a recovery plan)",
                        user_id=wf.get("user_id"))
        try:
            import hermes_dispatch as _hd
            _hd.notify_desktop("Nexus: pipeline stalled ⚠", f"{wf['name']}: {reason[:120]}")
        except Exception:
            pass


def loop_sweep():
    if db.get_setting("dispatch.enabled", "0") != "1":
        return
    _sweep_replan_detection()
    left = _sweep_workflow_loops(MAX_ACTIONS_PER_SWEEP)
    _sweep_task_loops(left)


def loop_engine_thread(stop_event: threading.Event):
    """Background thread (started like the watchdog in server startup)."""
    while not stop_event.is_set():
        try:
            loop_sweep()
        except Exception as e:
            print(f"[loop-engine] error: {e}", file=sys.stderr)
        stop_event.wait(SWEEP_S)
