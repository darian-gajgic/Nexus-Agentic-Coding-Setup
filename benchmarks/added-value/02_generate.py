#!/usr/bin/env python3
"""Stage 2 — generate deliverables for the three arms. Resumable: a case+arm
with an error-free meta.json is skipped; --redo-errors retries failed ones.

Arm A (Nexus)  : mode "task" = real task w/ super_result closed loop (the product);
                 mode "evals" = existing eval-runner framing path (one pass).
Arm B (Claude) : headless `claude -p` in a clean config dir (no CLAUDE.md/memory).
Arm C (GLM raw): one Z.AI chat/completions call, no framing, no tools.

Usage:
  python3 02_generate.py --run run1 [--arm A --arm B --arm C] [--limit N]
                         [--pause 5] [--redo-errors] [--preflight]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_lib as bl

DELIVERABLE_SUFFIX = (
    "\n\n---\nProduce the complete deliverable now, in markdown, as your "
    "reply. Do not ask questions; if a needed fact is missing, state the "
    "assumption in one line and continue."
)
ARM_B_EXTRA = " Reply with the deliverable text directly; do not create files."


def _pending(briefs, run_id, arm, redo):
    out = []
    for b in briefs:
        m = bl.done_marker(run_id, arm, b["case_id"])
        if m.exists():
            try:
                meta = json.loads(m.read_text())
            except Exception:
                meta = {"error": "unreadable meta"}
            if not meta.get("error") or not redo:
                continue
        out.append(b)
    return out


# ── Arm A: task mode ─────────────────────────────────────────────────────

def _get_task(tid):
    ok, t = bl.nexus("GET", f"/api/tasks/{tid}")
    if ok and isinstance(t, dict) and (t.get("id") == tid or t.get("task")):
        return t.get("task") or t
    ok, all_t = bl.nexus("GET", "/api/tasks")
    if ok:
        rows = all_t.get("tasks") if isinstance(all_t, dict) else all_t
        for r in rows or []:
            if isinstance(r, dict) and r.get("id") == tid:
                return r
    return None


def _task_tokens(task, ws: Path):
    for k in ("tokens_used", "total_tokens", "tokens"):
        v = (task or {}).get(k)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    audit = ws / "_dispatch.json"
    if audit.exists():
        try:
            u = json.loads(audit.read_text()).get("usage") or {}
            return int(u.get("total_tokens")
                       or (u.get("input_tokens", 0) + u.get("output_tokens", 0)))
        except Exception:
            pass
    return None


def arm_a_task(brief, run_id, timeout_s):
    ok, res = bl.nexus("POST", "/api/tasks", {
        "title": f"[BENCH] {brief['title']}"[:180],
        "description": brief["brief"],
        "status": "todo",
        "priority": "medium",
        "domain": brief["domain"],
        "model": bl.CFG["arm_a_model"],
        "super_result": True,
        "autopilot": "full_auto",
        "spend_profile": "optimal",
        "tags": ["bench", run_id],
    })
    if not ok:
        return None, {"error": f"task create failed: {res}"}
    task = res.get("task") or res
    tid = task.get("id") or (res.get("data") or {}).get("id")
    if not tid:
        return None, {"error": f"no task id in response: {str(res)[:200]}"}
    ok, dres = bl.nexus("POST", f"/api/tasks/{tid}/dispatch", {})
    if not ok:
        return None, {"error": f"dispatch failed: {dres}", "task_id": tid}

    ws = Path(bl.CFG["app_dir"]) / "workspaces" / tid
    deliv = ws / "deliverable.md"
    t0 = time.time()
    settle_since = None
    last_mtime = 0.0
    terminal = ("completed", "failed", "blocked_budget", "blocked_quota")
    state = "unknown"
    while time.time() - t0 < timeout_s:
        time.sleep(20)
        t = _get_task(tid) or {}
        state = t.get("dispatch_state") or state
        mtime = deliv.stat().st_mtime if deliv.exists() else 0.0
        if (t.get("critic_verdict") or "").upper() == "SHIP":
            break
        if state in terminal:
            # loop engine may still be reworking — wait until the deliverable
            # stops changing for 120s (or nothing exists to wait for)
            if mtime != last_mtime:
                last_mtime, settle_since = mtime, time.time()
            elif settle_since is None:
                settle_since = time.time()
            elif time.time() - settle_since > 120:
                break
    t = _get_task(tid) or {}
    if not deliv.exists():
        return None, {"error": f"no deliverable (state={state})", "task_id": tid,
                      "dispatch_state": state}
    meta = {"task_id": tid, "dispatch_state": t.get("dispatch_state"),
            "critic_verdict": t.get("critic_verdict"),
            "critic_round": t.get("critic_round"),
            "seconds": round(time.time() - t0, 1),
            "glm_tokens": _task_tokens(t, ws),
            "mode": "task", "model": bl.CFG["arm_a_model"],
            "note": "frontier judge/critic ran on subscription (cost not in glm_tokens)"}
    if meta["glm_tokens"] is None:
        meta["cost_usd_list"] = None
    else:
        meta["cost_usd_list"] = bl.list_price_usd(
            bl.CFG["arm_a_model"], int(meta["glm_tokens"] * 0.8),
            int(meta["glm_tokens"] * 0.2))
        meta["cost_note"] = "in/out split unknown → estimated 80/20 at list price"
    return deliv.read_text(), meta


# ── Arm A: evals mode (one run per domain, resumable per case) ───────────

def arm_a_evals(briefs, run_id, timeout_s, pause):
    by_dom = {}
    for b in briefs:
        by_dom.setdefault(b["domain"], []).append(b)
    for domain, cases in by_dom.items():
        ids = [c["case_id"] for c in cases]
        bl.log(f"Arm A/evals: domain {domain} ({len(ids)} case(s))")
        ok, res = bl.nexus("POST", "/api/evals/run",
                           {"domain": domain, "cases": ids,
                            "notes": f"bench {run_id}"})
        if not ok:
            for c in cases:
                bl.write_result(run_id, "A", c["case_id"], None,
                                {"error": f"eval start failed: {res}", "mode": "evals"})
            continue
        rid = res.get("run_id")
        t0 = time.time()
        status = "running"
        while time.time() - t0 < timeout_s:
            time.sleep(15)
            ok, detail = bl.nexus("GET", f"/api/evals/runs/{rid}")
            if not ok:
                continue
            status = (detail.get("run") or {}).get("status") or status
            if status in ("completed", "failed", "cancelled"):
                break
        ok, detail = bl.nexus("GET", f"/api/evals/runs/{rid}")
        results = {r.get("case_id"): r for r in (detail.get("results") or [])} \
            if ok else {}
        for c in cases:
            cid = c["case_id"]
            row = results.get(cid) or {}
            p = Path(bl.CFG["app_dir"]) / "workspaces" / "evals" / str(rid) / cid / "deliverable.md"
            if not p.exists():
                bl.write_result(run_id, "A", cid, None,
                                {"error": row.get("error") or f"no deliverable (run {status})",
                                 "mode": "evals", "eval_run_id": rid})
                continue
            tokens = row.get("tokens_used")
            meta = {"mode": "evals", "eval_run_id": rid,
                    "glm_tokens": tokens,
                    "seconds": row.get("gen_seconds"),
                    "nexus_internal_judge": {"verdict": row.get("verdict"),
                                             "score": row.get("score"),
                                             "score_max": row.get("score_max")},
                    "model": bl.CFG["arm_a_model"],
                    "cost_usd_list": bl.list_price_usd(
                        bl.CFG["arm_a_model"], int((tokens or 0) * 0.8),
                        int((tokens or 0) * 0.2)) if tokens else None,
                    "cost_note": "in/out split unknown → estimated 80/20 at list price"}
            bl.write_result(run_id, "A", cid, p.read_text(), meta)
            bl.log(f"  A/{cid}: ok ({tokens or '?'} tok)")
        time.sleep(pause)


# ── Arm B ────────────────────────────────────────────────────────────────

def arm_b(brief, run_id, home):
    prompt = brief["brief"] + DELIVERABLE_SUFFIX + ARM_B_EXTRA
    work = bl.arm_dir(run_id, "B", brief["case_id"]) / "work"
    t0 = time.time()
    ok, res = bl.run_claude(prompt, work, bl.CFG["arm_b_timeout_s"],
                            model=bl.CFG["arm_b_model"], config_dir=home)
    if not ok:
        return None, {"error": res}
    text = (res.get("result") or "").strip()
    if len(text) < 200:
        # the CLI wrote files instead of replying — take the largest .md
        cands = sorted(work.rglob("*.md"), key=lambda p: p.stat().st_size,
                       reverse=True)
        if cands:
            text = cands[0].read_text()
    if len(text) < 200:
        return None, {"error": f"empty/short reply ({len(text)} chars)"}
    u = res.get("usage") or {}
    tin = int(u.get("input_tokens") or 0)
    tout = int(u.get("output_tokens") or 0)
    meta = {"model": bl.CFG["arm_b_model"], "seconds": round(time.time() - t0, 1),
            "tokens_in": tin, "tokens_out": tout,
            "cli_cost_usd": res.get("total_cost_usd"),
            "cost_usd_list": bl.list_price_usd(bl.CFG["arm_b_model"], tin, tout)
            or res.get("total_cost_usd"),
            "auth": "subscription (marginal $0; list-equivalent reported)"}
    return text, meta


# ── Arm C ────────────────────────────────────────────────────────────────

def arm_c(brief, key):
    t0 = time.time()
    ok, res = bl.zai_chat(
        [{"role": "user", "content": brief["brief"] + DELIVERABLE_SUFFIX}],
        bl.CFG["arm_c_model"], bl.CFG["arm_c_max_tokens"],
        bl.CFG["arm_c_timeout_s"], key)
    if not ok:
        return None, {"error": res}
    u = res.get("usage") or {}
    tin = int(u.get("prompt_tokens") or 0)
    tout = int(u.get("completion_tokens") or 0)
    meta = {"model": bl.CFG["arm_c_model"], "seconds": round(time.time() - t0, 1),
            "tokens_in": tin, "tokens_out": tout,
            "cost_usd_list": bl.list_price_usd(bl.CFG["arm_c_model"], tin, tout)}
    return (res.get("content") or "").strip(), meta


# ── driver ───────────────────────────────────────────────────────────────

def with_retries(fn, label):
    last = None
    for attempt in range(1 + bl.CFG["retries"]):
        text, meta = fn()
        if not meta.get("error"):
            return text, meta
        last = meta
        if bl.is_quota_shed(meta["error"]):
            bl.log(f"  {label}: quota/load-shed — backing off "
                   f"{bl.CFG['quota_backoff_s']}s ({meta['error'][:80]})")
            time.sleep(bl.CFG["quota_backoff_s"])
        else:
            bl.log(f"  {label}: error attempt {attempt + 1}: {meta['error'][:120]}")
            time.sleep(5)
    return None, last


def preflight(arms, home):
    bl.log("preflight…")
    okall = True
    if "A" in arms:
        ok, res = bl.nexus("GET", "/api/health")
        if not ok:
            ok, res = bl.nexus("GET", "/api/stats")
        bl.log(f"  nexus reachable: {ok}")
        okall &= ok
        if bl.CFG["arm_a_mode"] == "task":
            ok, res = bl.nexus("GET", "/api/agents")
            rows = (res.get("agents") if isinstance(res, dict) else res) or []
            live = [a for a in rows if isinstance(a, dict)
                    and a.get("status") not in ("retired",)]
            bl.log(f"  agent lanes (non-retired): {len(live)} "
                   f"{'OK' if live else '— NONE: task mode cannot execute!'}")
            okall &= bool(live)
    if "B" in arms:
        ok, res = bl.run_claude("Reply with exactly: OK", Path("/tmp"), 120,
                                model=bl.CFG["arm_b_model"], config_dir=home)
        good = ok and "OK" in str((res or {}).get("result", ""))
        bl.log(f"  clean-home claude works: {good}"
               + ("" if good else f" ({str(res)[:160]})"))
        okall &= good
    if "C" in arms:
        key = bl.read_glm_key()
        ok, res = bl.zai_chat([{"role": "user", "content": "Reply: OK"}],
                              bl.CFG["arm_c_model"], 16, 60, key)
        bl.log(f"  Z.AI endpoint works: {ok}" + ("" if ok else f" ({res})"))
        okall &= ok
    bl.log("preflight " + ("PASSED" if okall else "FAILED — fix before running"))
    return okall


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="run1")
    ap.add_argument("--arm", action="append", choices=list(bl.ARMS))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pause", type=int, default=5)
    ap.add_argument("--redo-errors", action="store_true")
    ap.add_argument("--preflight", action="store_true",
                    help="run connectivity checks only, generate nothing")
    args = ap.parse_args()
    arms = args.arm or list(bl.ARMS)
    briefs = bl.load_briefs(args.run)
    home = bl.ensure_clean_claude_home() if ("B" in arms or args.preflight) else None

    if args.preflight:
        sys.exit(0 if preflight(arms, home) else 1)

    if args.limit:
        briefs = briefs[:args.limit]

    if "A" in arms:
        pend = _pending(briefs, args.run, "A", args.redo_errors)
        bl.log(f"Arm A ({bl.CFG['arm_a_mode']}): {len(pend)} pending")
        if bl.CFG["arm_a_mode"] == "evals":
            if pend:
                arm_a_evals(pend, args.run, bl.CFG["arm_a_evals_timeout_s"],
                            args.pause)
        else:
            for b in pend:
                bl.log(f"A/{b['case_id']} …")
                text, meta = with_retries(
                    lambda b=b: arm_a_task(b, args.run,
                                           bl.CFG["arm_a_task_timeout_s"]),
                    f"A/{b['case_id']}")
                bl.write_result(args.run, "A", b["case_id"], text, meta or {})
                time.sleep(args.pause)

    if "B" in arms:
        pend = _pending(briefs, args.run, "B", args.redo_errors)
        bl.log(f"Arm B: {len(pend)} pending")
        for b in pend:
            bl.log(f"B/{b['case_id']} …")
            text, meta = with_retries(
                lambda b=b: arm_b(b, args.run, home), f"B/{b['case_id']}")
            if meta and "session limit" in str(meta.get("error", "")).lower():
                bl.write_result(args.run, "B", b["case_id"], None, meta)
                bl.log("Claude session limit hit — stop; rerun after reset "
                       "(resumable).")
                break
            bl.write_result(args.run, "B", b["case_id"], text, meta or {})
            time.sleep(args.pause)

    if "C" in arms:
        key = bl.read_glm_key()
        pend = _pending(briefs, args.run, "C", args.redo_errors)
        bl.log(f"Arm C: {len(pend)} pending")
        for b in pend:
            bl.log(f"C/{b['case_id']} …")
            text, meta = with_retries(lambda b=b: arm_c(b, key),
                                      f"C/{b['case_id']}")
            bl.write_result(args.run, "C", b["case_id"], text, meta or {})
            time.sleep(args.pause)

    bl.log("stage 2 done — next: 03_blind.py")


if __name__ == "__main__":
    main()
