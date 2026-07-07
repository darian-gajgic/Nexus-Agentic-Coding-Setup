"""NEXUS Agent OS — Eval corpus runner (Block 3 R3, docs/SPEC-BLOCK3.md).

Remediation #6: fixed per-domain eval briefs, executed through the REAL
dispatch framing (playbook injection, specialist delegation, rubric
self-score) and scored by the frontier judge against the domain RUBRIC —
so a prompt/playbook change is MEASURED against the same work, not
vibes-checked.

Corpus:   ~/knowledge/domains/<domain>/evals/*.md
          (frontmatter: title / specialist / model / notes; body = the brief.
          Human-editable, git-versioned with the knowledge base.)
Results:  eval_runs + eval_results tables; deliverables under
          workspaces/evals/<run>/<case>/.
Validity: each run records a fingerprint of the config it measured
          (PLAYBOOK, RUBRIC, STYLE-VOICE, BUSINESS-CONTEXT, specialist
          definitions) — two runs with different fingerprints measure the
          change between them. Generation is nondeterministic: compare
          trends across cases, not single points.

Test hooks (gates only, default off — restored by the gate):
  settings evals.corpus_root  → redirect corpus discovery to a scratch dir
  settings evals.stub         → canned generation, no Hermes call
The judge stays stubbable via the existing judge.cmd setting (R4.3 pattern).
"""
import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

import database as db

KNOWLEDGE_DIR = os.path.expanduser("~/knowledge")
WORKSPACES = Path(__file__).parent / "workspaces" / "evals"
MAX_CASES_PER_RUN = 8
GEN_MAX_SECONDS = 1500  # single-deliverable briefs; well under the 45-min task cap


def corpus_root() -> str:
    return db.get_setting("evals.corpus_root", "") or os.path.join(KNOWLEDGE_DIR, "domains")


# ─────────────────────────── Corpus discovery ───────────────────────────

def _parse_case_md(text: str) -> tuple[dict, str]:
    """Minimal frontmatter parser (same convention as ~/.hermes/agents/*.md):
    --- key: value lines --- body."""
    fm: dict = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip("\"'")
            body = text[end + 4:].strip()
    return fm, body


def _case_from_file(fp: str) -> dict | None:
    try:
        fm, body = _parse_case_md(open(fp).read())
    except Exception:
        return None
    if not body.strip():
        return None
    cid = os.path.basename(fp)[:-3]
    return {
        "id": cid,
        "title": (fm.get("title") or cid.replace("-", " ")).strip()[:200],
        "specialist": (fm.get("specialist") or "").strip() or None,
        "model": (fm.get("model") or "").strip() or None,
        "notes": (fm.get("notes") or "").strip()[:300],
        "brief": body.strip(),
    }


def list_corpus() -> list[dict]:
    """Every domain with a RUBRIC.md, its eval cases (briefs omitted — the
    list feeds the UI; load_case() returns the full brief)."""
    root = corpus_root()
    out = []
    if not os.path.isdir(root):
        return out
    for domain in sorted(os.listdir(root)):
        ddir = os.path.join(root, domain)
        if not os.path.isdir(ddir):
            continue
        has_rubric = os.path.isfile(os.path.join(ddir, "RUBRIC.md"))
        cases = []
        edir = os.path.join(ddir, "evals")
        if os.path.isdir(edir):
            for fp in sorted(os.listdir(edir)):
                if fp.endswith(".md"):
                    c = _case_from_file(os.path.join(edir, fp))
                    if c:
                        cases.append({k: c[k] for k in
                                      ("id", "title", "specialist", "model", "notes")})
        if has_rubric or cases:
            out.append({"domain": domain, "has_rubric": has_rubric, "cases": cases})
    return out


def load_case(domain: str, case_id: str) -> dict | None:
    if not re.match(r"^[a-z0-9._-]+$", case_id or ""):
        return None
    fp = os.path.join(corpus_root(), domain, "evals", f"{case_id}.md")
    return _case_from_file(fp) if os.path.isfile(fp) else None


def fingerprint(domain: str, specialists: list) -> dict:
    """Short hashes of everything that shapes the output quality. Two runs
    with equal fingerprints measured the SAME config."""
    files = {
        "playbook": os.path.join(corpus_root(), domain, "PLAYBOOK.md"),
        "rubric": os.path.join(corpus_root(), domain, "RUBRIC.md"),
        "style": os.path.join(KNOWLEDGE_DIR, "STYLE-VOICE.md"),
        "context": os.path.join(KNOWLEDGE_DIR, "BUSINESS-CONTEXT.md"),
    }
    for s in sorted({s for s in specialists if s}):
        files[f"specialist:{s}"] = os.path.expanduser(f"~/.hermes/agents/{s}.md")
    out = {}
    for key, fp in files.items():
        try:
            out[key] = hashlib.sha256(open(fp, "rb").read()).hexdigest()[:8]
        except Exception:
            out[key] = None
    out["combined"] = hashlib.sha256(
        json.dumps(out, sort_keys=True).encode()).hexdigest()[:8]
    return out


# ─────────────────────────── Judge integration ───────────────────────────

def run_judge_cmd(file_path: str, domain: str) -> str:
    """Run the frontier judge command on a file (shared with the task judge).
    Template lives in settings judge.cmd so gates can stub it (R4.3).

    Runs with cwd=~/knowledge AND copies the deliverable there first: headless
    `claude -p` (inside cjudge) can only read files under its working directory
    without permission prompts, and the judge must read BOTH the rubric tree
    and the deliverable."""
    import shlex
    import shutil
    import subprocess as sp
    tmpdir = Path(KNOWLEDGE_DIR) / ".nexus-judge-tmp"
    judged_path = file_path
    try:
        tmpdir.mkdir(exist_ok=True)
        tmp_file = tmpdir / f"judge-{uuid.uuid4().hex[:8]}.md"
        shutil.copy2(file_path, tmp_file)
        judged_path = str(tmp_file)
    except Exception:
        pass  # fall back to the original path
    # shell=False + per-token formatting: template values are validated, and
    # this removes the shell layer entirely (defense in depth for judge.cmd).
    tokens = [t.format(file=judged_path, domain=domain)
              for t in shlex.split(db.get_setting("judge.cmd", "cjudge {file} {domain}"))]
    # Under the systemd unit PATH may lack ~/.local/bin (where cjudge lives).
    if tokens and not shutil.which(tokens[0]):
        candidate = os.path.expanduser(f"~/.local/bin/{tokens[0]}")
        if os.path.isfile(candidate):
            tokens[0] = candidate
    try:
        r = sp.run(tokens, capture_output=True, text=True, timeout=900,
                   cwd=KNOWLEDGE_DIR)
        out = (r.stdout or "")
        if r.returncode != 0:
            out += f"\n[judge exited {r.returncode}] {(r.stderr or '')[-1000:]}"
    except sp.TimeoutExpired:
        out = "[judge timed out after 900s]"
    except Exception as e:
        out = f"[judge failed to run: {e}]"
    finally:
        try:
            if judged_path != file_path:
                os.unlink(judged_path)
        except Exception:
            pass
    return out


def parse_judge_metrics(text: str) -> dict:
    """Best-effort extraction from free-form judge output. Every domain rubric
    formats its own score line, so parsing is defensive; the raw output is
    stored regardless.
    - verdict: SHIP / REVISE / REWRITE (the cjudge contract)
    - score:   an 'X/Y' total (prefers lines mentioning score/total/→,
               denominators 8..100 — dimension lines like '3/4' don't qualify)
    - gates:   count of PASS/FAIL tokens on gate-looking lines."""
    verdict = None
    m = re.search(r"VERDICT[:\s]*\**\s*(SHIP|REVISE|REWRITE)", text or "", re.I)
    if not m:
        m = re.search(r"^\s*\**(SHIP|REVISE|REWRITE)\**\s*$", text or "", re.M)
    if m:
        verdict = m.group(1).upper()

    score = score_max = None
    candidates = []
    for line in (text or "").splitlines():
        for sm in re.finditer(r"(\d{1,3})\s*/\s*(\d{1,3})", line):
            x, y = int(sm.group(1)), int(sm.group(2))
            if 8 <= y <= 100 and x <= y:
                prio = 1 if re.search(r"score|total|→|=>", line, re.I) else 0
                candidates.append((prio, x, y))
    if candidates:
        candidates.sort(key=lambda c: c[0], reverse=True)
        _, score, score_max = candidates[0]

    # Token count (not per-line): the rubrics' required formats put many gate
    # verdicts on ONE line ("GATES: 1 PASS · 2 PASS · 3 FAIL …"). Uppercase-only
    # word matches keep prose ("passed", "failing") out of the count.
    gates_passed = gates_failed = 0
    for line in (text or "").splitlines():
        if re.search(r"VERDICT", line, re.I):
            continue
        gates_passed += len(re.findall(r"\bPASS\b", line))
        gates_failed += len(re.findall(r"\bFAIL(?:ED)?\b", line))
    return {"verdict": verdict, "score": score, "score_max": score_max,
            "gates_passed": gates_passed, "gates_failed": gates_failed}


# ─────────────────────────── Runner ───────────────────────────

def _generate(case: dict, domain: str, run_id: str, uid: str | None) -> dict:
    """Produce the deliverable for one case through the REAL dispatch framing.
    Returns {path, tokens, seconds, error}."""
    ws = WORKSPACES / run_id / case["id"]
    ws.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if db.get_setting("evals.stub", "0") == "1":
        # Gate hook (R3.6): canned deliverable, no Hermes call, no fake tokens.
        (ws / "deliverable.md").write_text(
            f"[EVAL STUB — generation stubbed for the verify gate]\n\n"
            f"# {case['title']}\n\nBrief:\n{case['brief'][:800]}\n")
        return {"path": str(ws / "deliverable.md"), "tokens": 0,
                "seconds": time.time() - t0, "error": None}
    import hermes_dispatch as hd
    synth = {
        "id": f"eval-{run_id}-{case['id']}",
        "title": f"[EVAL] {case['title']}",
        "description": case["brief"],
        "domain": domain,
        "specialist": case.get("specialist"),
        "model": case.get("model"),
    }
    framing = hd.build_framing(synth, ws)
    sid = hd.create_session(f"nexus:eval:{run_id}:{case['id']}",
                            model=case.get("model"))
    hd.publish_session_scope(sid, user=uid)  # memory stays the runner's scope
    try:
        res = hd.stream_turn(sid, f"{synth['title']}\n\n{case['brief']}",
                             system_message=framing, max_seconds=GEN_MAX_SECONDS)
    finally:
        try:
            hd.delete_session(sid)
        except Exception:
            pass
    content = (res.get("content") or "").strip()
    if res.get("error"):
        return {"path": None, "tokens": 0, "seconds": time.time() - t0,
                "error": str(res["error"])[:300]}
    deliv = ws / "deliverable.md"
    if not deliv.exists():
        if not content:
            return {"path": None, "tokens": 0, "seconds": time.time() - t0,
                    "error": "no deliverable produced"}
        deliv.write_text(content)
    usage = res.get("usage") or {}
    tokens = int(usage.get("total_tokens")
                 or (int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)))
    return {"path": str(deliv), "tokens": tokens,
            "seconds": time.time() - t0, "error": None}


def _run_status(run_id: str) -> str | None:
    row = db.query_one("SELECT status FROM eval_runs WHERE id=?", (run_id,))
    return (row or {}).get("status")


def _finish_run(run_id: str, status: str, error: str | None = None):
    db.execute("UPDATE eval_runs SET status=?, error=?, ended_at=? WHERE id=?",
               (status, error, time.time(), run_id))


def _run_thread(run_id: str, domain: str, uid: str | None):
    results = db.query_all(
        "SELECT * FROM eval_results WHERE run_id=? ORDER BY id", (run_id,))
    try:
        for row in results:
            if _run_status(run_id) == "cancelling":
                db.execute("UPDATE eval_results SET status='skipped' "
                           "WHERE run_id=? AND status='pending'", (run_id,))
                _finish_run(run_id, "cancelled")
                db.log_activity("info", "evals", f"Eval run {run_id} cancelled", user_id=uid)
                return
            case = load_case(domain, row["case_id"])
            if not case:
                db.execute("UPDATE eval_results SET status='error', error=?, ended_at=? "
                           "WHERE id=?", ("case file disappeared", time.time(), row["id"]))
                continue
            db.execute("UPDATE eval_results SET status='generating', started_at=? WHERE id=?",
                       (time.time(), row["id"]))
            gen = _generate(case, domain, run_id, uid)
            if gen["error"]:
                db.execute(
                    "UPDATE eval_results SET status='error', error=?, gen_seconds=?, "
                    "ended_at=? WHERE id=?",
                    (gen["error"], gen["seconds"], time.time(), row["id"]))
                db.execute("UPDATE eval_runs SET cases_done=cases_done+1 WHERE id=?", (run_id,))
                continue
            db.execute(
                "UPDATE eval_results SET status='judging', deliverable_path=?, "
                "tokens_used=?, gen_seconds=? WHERE id=?",
                (gen["path"], gen["tokens"], gen["seconds"], row["id"]))
            out = run_judge_cmd(gen["path"], domain)
            m = parse_judge_metrics(out)
            db.execute(
                "UPDATE eval_results SET status='scored', verdict=?, score=?, score_max=?, "
                "gates_passed=?, gates_failed=?, judge_output=?, ended_at=? WHERE id=?",
                (m["verdict"], m["score"], m["score_max"], m["gates_passed"],
                 m["gates_failed"], out[-30000:], time.time(), row["id"]))
            db.execute(
                "UPDATE eval_runs SET cases_done=cases_done+1, "
                "score_total=score_total+?, score_max=score_max+?, "
                "ship_count=ship_count+? WHERE id=?",
                (m["score"] or 0, m["score_max"] or 0,
                 1 if m["verdict"] == "SHIP" else 0, run_id))
            db.log_activity("info", "evals",
                            f"Eval case {row['case_id']} ({domain}): "
                            f"{m['verdict'] or 'no verdict'}"
                            + (f", {m['score']}/{m['score_max']}" if m["score"] is not None else ""),
                            user_id=uid)
        _finish_run(run_id, "completed")
        run = db.query_one("SELECT * FROM eval_runs WHERE id=?", (run_id,))
        pct = (100 * run["score_total"] // run["score_max"]) if run.get("score_max") else None
        db.log_activity("info", "evals",
                        f"Eval run finished — {domain}: {run['cases_done']}/{run['cases_total']} "
                        "cases" + (f", rubric score {pct}%" if pct is not None else "")
                        + f", {run['ship_count']} SHIP", user_id=uid)
    except Exception as e:
        _finish_run(run_id, "failed", str(e)[:300])
        db.log_activity("error", "evals",
                        f"Eval run {run_id} failed: {str(e)[:160]}", user_id=uid)


def start_run(domain: str, case_ids: list | None, uid: str,
              notes: str = "") -> tuple[str | None, str | None]:
    """Validate + insert the run and its pending results, then hand off to a
    daemon thread. Returns (run_id, error). One run at a time — generation and
    judging share the Hermes/judge capacity with real work."""
    if not re.match(r"^[a-z0-9-]+$", domain or ""):
        return None, "invalid domain"
    if not os.path.isfile(os.path.join(corpus_root(), domain, "RUBRIC.md")):
        return None, f"no RUBRIC.md for domain '{domain}' — nothing to score against"
    active = db.query_one("SELECT id FROM eval_runs WHERE status IN ('running','cancelling')")
    if active:
        return None, f"eval run {active['id']} is still running — one at a time"
    backoff_until = float(db.get_setting("dispatch.quota_backoff_until", "0") or 0)
    if backoff_until > time.time() and db.get_setting("evals.stub", "0") != "1":
        return None, "GLM is load-shedding right now (quota backoff active) — try later"
    all_cases = []
    edir = os.path.join(corpus_root(), domain, "evals")
    if os.path.isdir(edir):
        for fp in sorted(os.listdir(edir)):
            if fp.endswith(".md"):
                c = _case_from_file(os.path.join(edir, fp))
                if c:
                    all_cases.append(c)
    if case_ids:
        wanted = [str(c) for c in case_ids]
        cases = [c for c in all_cases if c["id"] in wanted]
    else:
        cases = all_cases
    cases = cases[:MAX_CASES_PER_RUN]
    if not cases:
        return None, f"no eval cases found for '{domain}' — add briefs under domains/{domain}/evals/"
    run_id = f"ev-{uuid.uuid4().hex[:8]}"
    fp = fingerprint(domain, [c.get("specialist") for c in cases])
    db.execute(
        "INSERT INTO eval_runs (id, domain, notes, status, cases_total, cases_done, "
        "fingerprint, started_at, user_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (run_id, domain, (notes or "").strip()[:500], "running", len(cases), 0,
         json.dumps(fp), time.time(), uid))
    for c in cases:
        db.execute(
            "INSERT INTO eval_results (id, run_id, case_id, case_title, specialist, "
            "model, status) VALUES (?,?,?,?,?,?,?)",
            (f"evr-{uuid.uuid4().hex[:10]}", run_id, c["id"], c["title"],
             c.get("specialist"), c.get("model"), "pending"))
    threading.Thread(target=_run_thread, args=(run_id, domain, uid), daemon=True).start()
    db.log_activity("info", "evals",
                    f"Eval run started — {domain}, {len(cases)} case(s), "
                    f"config {fp.get('combined')}", user_id=uid)
    return run_id, None
