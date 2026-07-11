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

# Super Result (SUPER-RESULT-PLAN-2026-07-09.md §6 Step 4): grounded critic.
CRITIC_SANDBOXES = Path(__file__).parent / "workspaces" / "_critic"
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
CRITIC_JSON_BEGIN = "NEXUS_CRITIC_JSON_BEGIN"
CRITIC_JSON_END = "NEXUS_CRITIC_JSON_END"
JUDGE_JSON_BEGIN = "NEXUS_JUDGE_JSON_BEGIN"  # N2: cjudge's structured tail
JUDGE_JSON_END = "NEXUS_JUDGE_JSON_END"
PLAN_JSON_BEGIN = "NEXUS_PLAN_JSON_BEGIN"    # Deep Plan premortem critique tail
PLAN_JSON_END = "NEXUS_PLAN_JSON_END"
DELIVERABLE_TYPES = ("analysis", "code_change", "content", "research")


# ─────────────────────────── Frontier backpressure (premortem P1) ───────────────────────────
# Every judge/critic run spawns the Claude CLI against ONE subscription with hard
# usage ceilings. A GLOBAL gate caps concurrent frontier subprocesses (setting
# frontier.max_concurrent, default 2 — mirrors hermes_dispatch's per-model GLM
# slot gate), and CLI rate-limit/quota failures are classified APART from content
# failures so the caller backs off + requeues instead of storing verdict='error'
# and escalating a transient ceiling to the human.

FRONTIER_QUOTA_SIGNATURES = (
    "rate limit", "rate_limit", "429", "quota", "usage limit", "usage_limit",
    "overloaded", "too many requests", "resource_exhausted",
    "credit balance", "insufficient_quota",
)


def is_frontier_quota_error(text: str) -> bool:
    """A Claude-CLI failure caused by the subscription's rate/usage ceiling
    (transient) rather than bad content. Consulted ONLY when a run produced no
    usable output, so a critique that merely discusses rate-limiting code can't
    false-positive into a quota deferral."""
    t = (text or "").lower()
    return any(sig in t for sig in FRONTIER_QUOTA_SIGNATURES)


def frontier_backoff_active() -> bool:
    try:
        return float(db.get_setting("frontier.quota_backoff_until", "0") or 0) > time.time()
    except Exception:
        return False


def note_frontier_quota_hit() -> int:
    """Exponential global backoff (60s doubling, cap 30 min), acknowledged once
    per window — mirrors hermes_dispatch.note_quota_hit for the frontier side."""
    now = time.time()
    until = float(db.get_setting("frontier.quota_backoff_until", "0") or 0)
    if until > now:
        return int(until - now)  # storm already acknowledged by another run
    n = int(db.get_setting("frontier.quota_consecutive", "0") or 0) + 1
    backoff = min(60 * (2 ** (n - 1)), 1800)
    db.set_setting("frontier.quota_consecutive", n)
    db.set_setting("frontier.quota_backoff_until", now + backoff)
    db.log_activity("warn", "frontier",
                    f"Frontier (Claude CLI) quota/rate-limit hit #{n} — backing off {backoff}s")
    return backoff


def note_frontier_quota_ok():
    """A clean frontier run resets the escalation counter; the active window is
    left to expire on its own (the GLM-side semantics)."""
    try:
        if int(db.get_setting("frontier.quota_consecutive", "0") or 0):
            db.set_setting("frontier.quota_consecutive", "0")
    except Exception:
        pass


class _FrontierGate:
    """Bounds concurrent frontier subprocesses. Re-reads the limit on each
    acquisition (and each 1s wake) so a settings change applies without a
    restart — the gate object is never rebuilt (rebuilding would leak the
    in-flight count)."""

    def __init__(self):
        self._cond = threading.Condition()
        self._active = 0

    def _limit(self) -> int:
        import settings_registry as sreg
        try:
            return max(1, int(sreg.conf("frontier.max_concurrent", "2") or 2))
        except Exception:
            return 2

    def __enter__(self):
        with self._cond:
            while self._active >= self._limit():
                self._cond.wait(timeout=1.0)
            self._active += 1
        return self

    def __exit__(self, *exc):
        with self._cond:
            self._active = max(0, self._active - 1)
            self._cond.notify()
        return False


_FRONTIER_GATE = _FrontierGate()


# ─────────────────────────── Frontier cost capture (Appendix C3, contract C-8) ───────────────────────────
# `claude -p --output-format json` (added to cverify/cjudge) wraps the reply in
# a JSON envelope {result, usage, total_cost_usd, modelUsage}. The sentinel
# parsers (parse_critic_json / parse_judge_metrics) consume the INNER text, so
# run_critic_cmd/run_judge_cmd must unwrap `.result` BEFORE they parse — else a
# JSON envelope breaks the sentinel search. A stubbed or legacy plain-text
# output has no envelope and passes straight through unchanged.

def _unwrap_frontier_output(stdout: str, sink: dict | None = None) -> str:
    """Return the model's reply text. When `stdout` is a claude-JSON envelope,
    that is `.result`, and — if `sink` is given — it is filled with the run's
    captured spend: {'tokens': int, 'cost_usd': float|None, 'source': 'envelope',
    'model': str|None}. Plain text (stub/legacy) returns unchanged and leaves the
    sink untouched, so the caller falls back to the transcript-size estimate.
    Never raises."""
    s = (stdout or "").strip()
    # cheap guard: only attempt a parse when it plausibly IS the envelope
    if not (s.startswith("{") and '"result"' in s):
        return stdout
    try:
        env = json.loads(s)
    except Exception:
        return stdout
    if not isinstance(env, dict) or not isinstance(env.get("result"), str):
        return stdout
    if sink is not None:
        usage = env.get("usage") if isinstance(env.get("usage"), dict) else {}
        tok = 0
        for k in ("input_tokens", "output_tokens",
                  "cache_creation_input_tokens", "cache_read_input_tokens"):
            try:
                tok += int(usage.get(k) or 0)
            except (TypeError, ValueError):
                pass
        cost = env.get("total_cost_usd")
        try:
            cost = float(cost) if cost is not None else None
        except (TypeError, ValueError):
            cost = None
        model = None
        mu = env.get("modelUsage")
        if isinstance(mu, dict) and mu:
            model = next(iter(mu.keys()), None)
        sink.update({"tokens": tok, "cost_usd": cost, "source": "envelope",
                     "model": model, "usage": usage})
    return env["result"]


def estimate_frontier_tokens(text: str) -> int:
    """Fallback token estimate when there is no envelope (stub/legacy output):
    ~4 chars per token, the standard rough heuristic. Deliberately conservative
    and clearly labelled 'estimate' in the ledger."""
    return max(0, len(text or "") // 4)


def record_frontier_spend(sink: dict, out_text: str, kind: str,
                          fallback_model: str | None,
                          task_id: str | None = None,
                          workflow_id: str | None = None,
                          user_id: str | None = None) -> None:
    """Persist one frontier run's spend to the C3 ledger. Uses the envelope's
    OWN tokens + dollars when captured (source='envelope'); otherwise estimates
    tokens from the transcript and prices them from the settings table
    (source='estimate'). `out_text` is the already-unwrapped reply. Best-effort."""
    if sink:
        tokens = int(sink.get("tokens") or 0)
        cost = sink.get("cost_usd")
        model = sink.get("model") or fallback_model
        source = "envelope"
        if cost is None:  # envelope without total_cost_usd → price the tokens
            cost = _price_tokens_blended(tokens, model)
    else:
        tokens = estimate_frontier_tokens(out_text)
        model = fallback_model
        cost = _price_tokens_blended(tokens, model)
        source = "estimate"
    db.record_frontier_run(task_id, kind, tokens, cost, source, model=model,
                           workflow_id=workflow_id, user_id=user_id)


def _price_tokens_blended(tokens: int, model: str | None) -> float:
    try:
        return db.glm_cost_estimate(tokens, model)  # blended-rate pricing helper
    except Exception:
        return 0.0


def knowledge_root() -> str:
    return os.path.expanduser(db.get_setting("onboarding.root", "") or KNOWLEDGE_DIR)


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
    dtype = (fm.get("deliverable_type") or "").strip()
    return {
        "id": cid,
        "title": (fm.get("title") or cid.replace("-", " ")).strip()[:200],
        "specialist": (fm.get("specialist") or "").strip() or None,
        "model": (fm.get("model") or "").strip() or None,
        "notes": (fm.get("notes") or "").strip()[:300],
        # optional (N1): lets an eval case opt into the type rubric
        "deliverable_type": dtype if dtype in DELIVERABLE_TYPES else None,
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
    # Type rubrics influence judging (N1) — editing INVESTIGATION.md must not
    # shift scores under an "unchanged" fingerprint.
    rdir = os.path.join(knowledge_root(), "rubrics")
    if os.path.isdir(rdir):
        for fn in sorted(os.listdir(rdir)):
            if fn.endswith(".md"):
                files[f"type_rubric:{fn}"] = os.path.join(rdir, fn)
    # N2 era boundary: the refute-by-default cjudge is harsher — hashing the
    # judge script keeps "scores comparable within a fingerprint" true across
    # judge upgrades.
    files["judge_script"] = os.path.expanduser("~/.local/bin/cjudge")
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

def judge_model_for(user_id: str | None) -> tuple[str | None, str | None]:
    """Settings v2: the owner's 'frontier_judge' purpose → (model_id, api_key).
    No assignment → (None, None) = the historical behavior (cjudge runs the
    Claude CLI's saved default, subscription auth). The key is the owner's
    credential for the judge model's provider — None keeps the CLI default."""
    import secrets_store
    row = db.resolve_assignment(user_id, "frontier_judge")
    if not row or row["route"] != "cli":
        return None, None
    key = secrets_store.resolve_key(user_id, row["provider"], row.get("credential_id"))
    return row["model_id"], key


def spec_model_for(user_id: str | None) -> tuple[str | None, str | None]:
    """Deep Plan premortem model: the owner's 'spec_model' purpose → (model_id,
    api_key). No assignment / non-cli route → (None, None) = the CLI's saved
    default (subscription auth). Mirrors judge_model_for."""
    import secrets_store
    row = db.resolve_assignment(user_id, "spec_model")
    if not row or row["route"] != "cli":
        return None, None
    key = secrets_store.resolve_key(user_id, row["provider"], row.get("credential_id"))
    return row["model_id"], key


def escalation_model_for(user_id: str | None) -> tuple[str | None, str | None]:
    """Appendix C1c escalated-rework model: the owner's 'escalation_model'
    purpose → (model_id, api_key). No assignment / non-cli route → (None, None)
    = the CLI's saved default (subscription auth). Mirrors judge_model_for."""
    import secrets_store
    row = db.resolve_assignment(user_id, "escalation_model")
    if not row or row["route"] != "cli":
        return None, None
    key = secrets_store.resolve_key(user_id, row["provider"], row.get("credential_id"))
    return row["model_id"], key


def run_judge_cmd(file_path: str, domain: str, model: str | None = None,
                  api_key: str | None = None, type_rubric: str | None = None,
                  spec_path: str | None = None, usage_sink: dict | None = None) -> str:
    """Run the frontier judge command on a file (shared with the task judge).
    Template lives in settings judge.cmd so gates can stub it (R4.3).

    Settings v2: `model` (the resolved frontier_judge assignment) replaces an
    optional {model} token and is always exported as JUDGE_MODEL; `api_key`
    (per-user credential) is exported as JUDGE_ANTHROPIC_API_KEY for the
    subprocess only — cjudge decides what to do with both, so a stubbed or
    legacy judge.cmd keeps working unchanged.

    Runs with cwd=~/knowledge AND copies the deliverable there first: headless
    `claude -p` (inside cjudge) can only read files under its working directory
    without permission prompts, and the judge must read BOTH the rubric tree
    and the deliverable."""
    import shlex
    import shutil
    import subprocess as sp
    tmpdir = Path(KNOWLEDGE_DIR) / ".nexus-judge-tmp"
    judged_path = file_path
    spec_tmp = None
    try:
        tmpdir.mkdir(exist_ok=True)
        tmp_file = tmpdir / f"judge-{uuid.uuid4().hex[:8]}.md"
        shutil.copy2(file_path, tmp_file)
        judged_path = str(tmp_file)
    except Exception:
        pass  # fall back to the original path
    # shell=False + per-token replacement (NOT .format — deliverable titles and
    # model ids may contain braces): template values are validated, and this
    # removes the shell layer entirely (defense in depth for judge.cmd).
    tokens = [t.replace("{file}", judged_path).replace("{domain}", domain)
               .replace("{model}", model or "")
               .replace("{type_rubric}", type_rubric or "")
              for t in shlex.split(db.get_setting("judge.cmd", "cjudge {file} {domain}"))]
    tokens = [t for t in tokens if t != ""]  # a {model} token with no model vanishes
    # Under the systemd unit PATH may lack ~/.local/bin (where cjudge lives).
    if tokens and not shutil.which(tokens[0]):
        candidate = os.path.expanduser(f"~/.local/bin/{tokens[0]}")
        if os.path.isfile(candidate):
            tokens[0] = candidate
    env = dict(os.environ)
    env["PATH"] = _augment_path_for_claude(env.get("PATH", ""))  # phase7 finding 1
    if model:
        env["JUDGE_MODEL"] = model
    if api_key:
        env["JUDGE_ANTHROPIC_API_KEY"] = api_key
    if type_rubric:
        # N1: type-aware judging — cjudge grades against BOTH rubrics when set.
        # Optional parameter: absent = exactly today's behavior (eval runner
        # passes it only when the case opts in via frontmatter).
        env["JUDGE_TYPE_RUBRIC"] = type_rubric
    if spec_path and os.path.isfile(spec_path):
        # Deep Plan (Step 8): the ORIGINAL SPEC contract — cjudge also checks the
        # deliverable against it when set (optional token; absent = today's behavior).
        try:
            spec_tmp = tmpdir / f"SPEC-{uuid.uuid4().hex[:8]}.md"
            shutil.copy2(spec_path, spec_tmp)
            env["JUDGE_SPEC"] = str(spec_tmp)
        except Exception:
            pass
    try:
        with _FRONTIER_GATE:  # global frontier concurrency cap (premortem P1)
            r = sp.run(tokens, capture_output=True, text=True, timeout=900,
                       cwd=KNOWLEDGE_DIR, env=env)
        # C-8: unwrap the claude-JSON envelope's `.result` BEFORE the sentinel
        # parser runs, capturing tokens + $ into usage_sink when present.
        out = _unwrap_frontier_output(r.stdout or "", usage_sink)
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
        try:
            if spec_tmp:
                os.unlink(spec_tmp)
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
    out = {"verdict": verdict, "score": score, "score_max": score_max,
           "gates_passed": gates_passed, "gates_failed": gates_failed}

    # N2 (strictly additive): the upgraded cjudge ends with a sentinel-fenced
    # JSON tail {verdict, findings:[{file_path,line_no,line_text,problem,fix}],
    # revision_brief}. Old-format output simply has no block — nothing changes.
    b = (text or "").rfind(JUDGE_JSON_BEGIN)
    if b != -1:
        e = text.find(JUDGE_JSON_END, b)
        if e != -1:
            try:
                data = json.loads(text[b + len(JUDGE_JSON_BEGIN):e])
            except Exception:
                data = None
            if isinstance(data, dict):
                jv = str(data.get("verdict") or "").strip().upper()
                if not out["verdict"] and jv in ("SHIP", "REVISE", "REWRITE"):
                    out["verdict"] = jv
                findings = []
                for f in (data.get("findings") or [])[:25]:
                    if not isinstance(f, dict):
                        continue
                    sev = str(f.get("severity") or "medium").strip().lower()
                    fp = str(f.get("file_path") or "").strip().lstrip("/")
                    if not fp or ".." in fp:
                        fp = "deliverable.md"
                    try:
                        ln = int(f["line_no"]) if f.get("line_no") is not None else None
                    except (TypeError, ValueError):
                        ln = None
                    findings.append({
                        "severity": sev if sev in SEVERITY_ORDER else "medium",
                        "file_path": fp[:500], "side": "new", "line_no": ln,
                        "line_text": _clip(f.get("line_text"), 200),
                        "claim": _clip(f.get("claim"), 300),
                        "evidence": _clip(f.get("evidence"), 400),
                        "problem": _clip(f.get("problem"), 300),
                        "suggested_fix": _clip(f.get("fix") or f.get("suggested_fix"), 300),
                    })
                if findings:
                    findings.sort(key=lambda x: SEVERITY_ORDER[x["severity"]])
                    out["findings"] = findings
                rb = _clip(data.get("revision_brief"), 2500)
                if rb:
                    out["revision_brief"] = rb
    return out


# ─────────────────────────── Grounded critic (Super Result) ───────────────────────────
# SUPER-RESULT-PLAN-2026-07-09.md §6 Step 4. The critic re-verifies a
# deliverable with FULL tool access inside a DISPOSABLE sandbox copy of the
# evidence (workspace + local repo clone). Sandbox lifecycle is owned HERE
# (locked decision §4.2): sp.run(timeout=…) kills the child and the finally:
# block removes the sandbox — cverify only consumes a prepared sandbox.

_SECRET_ENV_RE = re.compile(r"(?i)(api_key|apikey|token|secret|passw|credential)")


def detect_deliverable_type(task: dict) -> str:
    """analysis | code_change | content | research. Explicit column wins;
    then structural signals; then a title/description keyword match."""
    explicit = (task.get("deliverable_type") or "").strip()
    if explicit in DELIVERABLE_TYPES:
        return explicit
    spec = (task.get("specialist") or "").strip()
    domain = (task.get("domain") or "").strip()
    if task.get("repo_path") or domain == "software-engineering" or spec in (
            "code-implementer", "tech-lead-orchestrator", "code-reviewer",
            "acceptance-verifier"):
        return "code_change"
    if spec in ("web-researcher", "market-researcher") or domain == "research-learning":
        return "research"
    if re.search(r"\b(audit|analy[sz]|investigat|reconcil|diagnos|assess|verif)",
                 f"{task.get('title') or ''} {task.get('description') or ''}", re.I):
        return "analysis"
    return "content"


def type_rubric_path(dtype: str | None) -> str | None:
    """Deliverable-type rubric file, or None. Extensible: add entries as more
    type rubrics exist (code_change/content have none yet)."""
    names = {"analysis": "INVESTIGATION.md", "research": "INVESTIGATION.md"}
    name = names.get(dtype or "")
    if not name:
        return None
    fp = os.path.join(knowledge_root(), "rubrics", name)
    return fp if os.path.isfile(fp) else None


def _augment_path_for_claude(path: str) -> str:
    """Ensure the common user CLI bin dirs are on PATH so the frontier scripts
    (cverify/cjudge/cexec) — which `exec env … claude` bare — resolve the `claude`
    binary. The nexus.service PATH omits ~/.npm-global/bin (where the CLI installs
    on this machine), so a service-spawned critic/judge/escalation would otherwise
    exit 127 (Appendix C, judge phase7 finding 1). Idempotent; dirs are appended
    (never prepended) so an operator's own PATH ordering is preserved."""
    parts = [p for p in (path or "").split(os.pathsep) if p]
    home = os.path.expanduser("~")
    for d in (os.path.join(home, ".npm-global", "bin"),
              os.path.join(home, ".local", "bin"),
              os.path.join(home, "bin"),
              os.path.join(home, ".claude", "local")):
        if d not in parts:
            parts.append(d)
    return os.pathsep.join(parts)


def _scrubbed_env() -> dict:
    """Subprocess env with every secret-looking var dropped (§4.3c). The one
    exception, JUDGE_ANTHROPIC_API_KEY, is re-added by run_critic_cmd when the
    owner has a per-user judge credential. PATH is augmented so a bare `claude`
    resolves even off the stripped service PATH (phase7 finding 1)."""
    env = {k: v for k, v in os.environ.items() if not _SECRET_ENV_RE.search(k)}
    env["PATH"] = _augment_path_for_claude(env.get("PATH", ""))
    return env


def sweep_critic_sandboxes(max_age_h: float = 24.0) -> int:
    """P9 (ops hardening): age-out disposable critic sandboxes older than
    `max_age_h`. Called (a) lazily before each new sandbox build, (b) at server
    startup, and (c) periodically by the scheduler — so crash leftovers are
    reclaimed even when no new critic run happens (the old code swept ONLY on the
    next build, so a machine that stopped running critics leaked forever).
    Returns the number of sandboxes removed. Never raises."""
    import shutil
    removed = 0
    try:
        if not CRITIC_SANDBOXES.exists():
            return 0
        cutoff = time.time() - max_age_h * 3600
        for d in CRITIC_SANDBOXES.iterdir():
            try:
                if d.is_dir() and d.stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
                    removed += 1
            except Exception:
                pass
    except Exception:
        pass
    return removed


def build_critic_sandbox(task: dict, round_no: int = 1):
    """Disposable evidence copy → (sandbox_root: Path, deliverable_rel: str).
    Isolation (§4.3a): workspace copytree (heavy build dirs excluded; _history/,
    deliverable.v*.md and attachments/ INCLUDED — they are evidence); repo tasks
    get `git clone --local` + `git remote remove origin` (NOT a worktree —
    worktrees share the object store and remotes with the live repo)."""
    import shutil
    import subprocess as sp
    CRITIC_SANDBOXES.mkdir(parents=True, exist_ok=True)
    # backstop (§4.2 / P9): sweep crash leftovers older than 24 h (shared helper,
    # also run at startup + on the scheduler so it isn't lazy-only).
    sweep_critic_sandboxes(24.0)
    ws = task.get("workspace_path") or ""
    if not os.path.isdir(ws):
        raise ValueError(f"task {task.get('id')} has no workspace directory to sandbox")
    sandbox = CRITIC_SANDBOXES / f"{task['id']}-r{round_no}-{uuid.uuid4().hex[:6]}"
    shutil.copytree(
        ws, sandbox / "workspace",
        ignore=shutil.ignore_patterns("_critic*", "_escalation", "node_modules",
                                      ".venv*", ".next", "dist", "build", "__pycache__"),
        ignore_dangling_symlinks=True)

    repo_root = repo_branch = repo_base = repo_note = None
    rp = (task.get("repo_path") or "").strip()
    if rp:
        try:
            r = sp.run(["git", "clone", "--local", rp, str(sandbox / "repo")],
                       capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or r.stdout or "clone failed")[-300:])
            rr = str(sandbox / "repo")
            b = sp.run(["git", "-C", rr, "symbolic-ref", "--short", "HEAD"],
                       capture_output=True, text=True)
            repo_base = (b.stdout or "").strip() or None
            import hermes_dispatch as _hd  # lazy: avoid import cycle at module load
            branch = f"nexus/{_hd._repo_slug(task)}"
            # `git clone --local` brings the task branch in ONLY as a
            # remote-tracking ref (refs/remotes/origin/<branch>): the branch is
            # born in a LINKED WORKTREE (worktree.ensure_task_worktree), so the
            # source repo's HEAD — hence the clone's checkout — stays on the base
            # branch. Materialize a LOCAL branch from origin/<branch> and check
            # it out BEFORE removing the remote (which drops the only refs to
            # that work), or the critic silently reviews the BASE branch. A plain
            # `rev-parse --verify nexus/<slug>` misses it (it never consults
            # refs/remotes/origin/*), so verify the remote-tracking ref instead.
            chk = sp.run(["git", "-C", rr, "rev-parse", "--verify", "--quiet",
                          f"refs/remotes/origin/{branch}"],
                         capture_output=True, text=True)
            if chk.returncode == 0:
                co = sp.run(["git", "-C", rr, "checkout", "-B", branch,
                             f"origin/{branch}"], capture_output=True, text=True)
                if co.returncode == 0:
                    repo_branch = branch
                else:
                    repo_note = (co.stderr or co.stdout
                                 or "task-branch checkout failed")[-300:]
            # push has nowhere to go now (belt: cverify also denies git push)
            sp.run(["git", "-C", rr, "remote", "remove", "origin"],
                   capture_output=True, text=True)
            repo_root = "repo/"
        except Exception as e:
            repo_note = str(e)[:300]
            shutil.rmtree(sandbox / "repo", ignore_errors=True)

    ctx_dir = sandbox / "_critic_context"
    ctx_dir.mkdir(exist_ok=True)
    rubrics = {}
    domain = (task.get("domain") or "").strip()
    if domain:
        dr = os.path.join(corpus_root(), domain, "RUBRIC.md")
        if os.path.isfile(dr):
            shutil.copy2(dr, ctx_dir / "RUBRIC.md")
            rubrics["domain"] = "_critic_context/RUBRIC.md"
    dtype = detect_deliverable_type(task)
    tr = type_rubric_path(dtype)
    if tr:
        shutil.copy2(tr, ctx_dir / os.path.basename(tr))
        rubrics["type"] = f"_critic_context/{os.path.basename(tr)}"
    business = None
    bc = os.path.join(knowledge_root(), "BUSINESS-CONTEXT.md")
    if os.path.isfile(bc):
        shutil.copy2(bc, ctx_dir / "BUSINESS-CONTEXT.md")
        business = "_critic_context/BUSINESS-CONTEXT.md"

    # Deep Plan (Step 8): the ORIGINAL contract travels to the critic — a task in
    # a Deep-Plan project gets its workflow's spec.json copied in so the critic
    # verifies against the spec, not just the task brief.
    spec_ctx = None
    wfid = task.get("workflow_id")
    if wfid:
        sp_json = (Path(__file__).parent / "workspaces" / f"workflow-{wfid}"
                   / "attachments" / "spec.json")
        if sp_json.is_file():
            shutil.copy2(sp_json, ctx_dir / "spec.json")
            spec_ctx = "_critic_context/spec.json"

    # Sibling reports: each DONE predecessor's deliverable — this is how the
    # N investigator reports reach the reconciler's critic for cross-checking.
    siblings = []
    try:
        import hermes_dispatch as _hd
        for d in _hd.task_dependencies(task):
            if d.get("status") != "done":
                continue
            fp = os.path.join(d.get("workspace_path") or "", "deliverable.md")
            if os.path.isfile(fp):
                (ctx_dir / "siblings").mkdir(exist_ok=True)
                shutil.copy2(fp, ctx_dir / "siblings" / f"{d['id']}.md")
                siblings.append({"task_id": d["id"],
                                 "title": (d.get("title") or "")[:200],
                                 "path": f"_critic_context/siblings/{d['id']}.md"})
    except Exception:
        pass

    prev = None
    versions = [int(m.group(1)) for f in os.listdir(sandbox / "workspace")
                if (m := re.match(r"deliverable\.v(\d+)\.md$", f))]
    if versions:
        prev = f"workspace/deliverable.v{max(versions)}.md"

    open_comments = [{"file_path": c["file_path"], "line_no": c.get("line_no"),
                      "body": (c.get("body") or "")[:300]}
                     for c in db.query_all(
                         "SELECT file_path, line_no, body FROM review_comments "
                         "WHERE task_id=? AND status='open' ORDER BY created_at",
                         (task["id"],))][:50]

    import settings_registry as sreg
    ctx = {
        "task_id": task["id"], "title": (task.get("title") or "")[:200],
        "round": round_no,
        "brief": (task.get("description") or "")[:4000],
        "retry_feedback_last": task.get("retry_feedback") or "",
        "deliverable": "workspace/deliverable.md",
        "deliverable_type": dtype,
        "workspace_root": "workspace/",
        "repo_root": repo_root, "repo_branch": repo_branch, "repo_base": repo_base,
        "previous_version": prev,
        "sibling_reports": siblings,
        "rubrics": rubrics,
        "business_context": business,
        "spec": spec_ctx,  # Deep Plan: the original SPEC contract (Step 8)
        "max_findings": int(sreg.conf("super.max_findings", "25") or 25),
        "open_comments": open_comments,
    }
    if repo_note:
        ctx["repo_note"] = repo_note
    (ctx_dir / "context.json").write_text(json.dumps(ctx, indent=2))
    return sandbox, "workspace/deliverable.md"


def run_critic_cmd(task: dict, domain: str | None, model: str | None = None,
                   api_key: str | None = None, round_no: int = 1,
                   usage_sink: dict | None = None) -> str:
    """Build the sandbox, run the critic command (settings super.critic_cmd —
    gates stub it, same contract as judge.cmd), tear the sandbox down.
    Mirrors run_judge_cmd; the timeout is owned HERE (§4.2)."""
    import shlex
    import shutil
    import subprocess as sp
    import settings_registry as sreg
    sandbox, deliv_rel = build_critic_sandbox(task, round_no)
    try:
        tokens = [t.replace("{file}", str(sandbox / deliv_rel))
                   .replace("{domain}", domain or "-")
                   .replace("{sandbox}", str(sandbox))
                   .replace("{model}", model or "")
                  for t in shlex.split(
                      sreg.conf("super.critic_cmd", "cverify {file} {domain} {sandbox}"))]
        tokens = [t for t in tokens if t != ""]
        # Under the systemd unit PATH may lack ~/.local/bin (where cverify lives).
        if tokens and not shutil.which(tokens[0]):
            candidate = os.path.expanduser(f"~/.local/bin/{tokens[0]}")
            if os.path.isfile(candidate):
                tokens[0] = candidate
        env = _scrubbed_env()
        if model:
            env["JUDGE_MODEL"] = model
        if api_key:
            env["JUDGE_ANTHROPIC_API_KEY"] = api_key
        env["SUPER_MAX_FINDINGS"] = sreg.conf("super.max_findings", "25")
        timeout_s = int(sreg.conf("super.timeout_s", "1500") or 1500)
        try:
            with _FRONTIER_GATE:  # global frontier concurrency cap (premortem P1)
                r = sp.run(tokens, capture_output=True, text=True, timeout=timeout_s,
                           cwd=str(sandbox), env=env)
            # C-8: unwrap the claude-JSON envelope before parse_critic_json.
            out = _unwrap_frontier_output(r.stdout or "", usage_sink)
            if r.returncode != 0:
                out += f"\n[critic exited {r.returncode}] {(r.stderr or '')[-1000:]}"
        except sp.TimeoutExpired:
            out = f"[critic timed out after {timeout_s}s]"
        except Exception as e:
            out = f"[critic failed to run: {e}]"
        return out
    finally:
        if sreg.conf("super.keep_sandbox", "0") != "1":
            shutil.rmtree(sandbox, ignore_errors=True)


# ─────────────────────────── Escalated rework (Appendix C1c) ───────────────────────────
# When the grounded critic returns REWRITE (or the round cap leaves criticals
# open) and super.escalation is ON, the rework ITSELF runs on the judgment-tier
# escalation_model: cverify minus the sandbox — the frontier model rewrites the
# deliverable in the REAL workspace, handed the full dossier. The floor this buys
# APPROACHES judgment-tier-direct but is an empirical claim, not a guarantee
# (C-7): a dossier carrying a wrong finding can anchor the rework below a clean
# direct pass. Phase 8 measures it. Setting-gated, near-zero marginal CLI cost.

def build_escalation_dossier(task: dict) -> str:
    """The full dossier the escalation writer needs: the brief, the grounded
    critic's verified findings + contradictions + missing items + revision brief,
    the open review comments (accumulated across rounds = the critique history),
    and clipped sibling reports. Markdown, self-contained."""
    try:
        parsed = json.loads(task.get("critic_json") or "{}") or {}
    except Exception:
        parsed = {}
    out = [f"# Escalated rework dossier — {(task.get('title') or '')[:200]}", ""]
    out.append("## Task brief")
    out.append((task.get("description") or "(no brief)")[:4000])
    out.append("")
    rb = (parsed.get("revision_brief") or "").strip()
    out.append(f"## Grounded critic verdict: {task.get('critic_verdict') or '?'} "
               f"(round {int(task.get('critic_round') or 0)})")
    if parsed.get("summary"):
        out.append(f"Summary: {parsed['summary']}")
    if rb:
        out.append("")
        out.append("### Revision brief (the exact instruction to satisfy)")
        out.append(rb)
    findings = parsed.get("findings") or []
    if findings:
        out.append("")
        out.append("### Verified findings (resolve EVERY critical/high)")
        for i, f in enumerate(findings, 1):
            loc = f.get("file_path") or "deliverable.md"
            if f.get("line_no"):
                loc += f":{f['line_no']}"
            out.append(f"{i}. [{(f.get('severity') or 'medium').upper()}] {loc}")
            if f.get("claim"):
                out.append(f"   - claim: {f['claim']}")
            if f.get("evidence"):
                out.append(f"   - evidence found: {f['evidence']}")
            if f.get("problem"):
                out.append(f"   - problem: {f['problem']}")
            if f.get("suggested_fix"):
                out.append(f"   - suggested fix: {f['suggested_fix']}")
    contras = parsed.get("contradictions") or []
    if contras:
        out.append("")
        out.append("### Contradictions to resolve")
        for c in contras:
            out.append(f"- with {c.get('with') or 'internal'}: {c.get('a')} ⇄ {c.get('b')}"
                       + (f" — hint: {c['resolution_hint']}" if c.get("resolution_hint") else ""))
    missing = parsed.get("missing") or []
    if missing:
        out.append("")
        out.append("### Missing (add these)")
        for m in missing:
            out.append(f"- {m.get('what')} — {m.get('why_it_matters')}")
    # Open review comments = the accumulated critique history (line-anchored).
    try:
        comments = db.query_all(
            "SELECT file_path, line_no, body, source FROM review_comments "
            "WHERE task_id=? AND status='open' ORDER BY created_at", (task["id"],))
    except Exception:
        comments = []
    if comments:
        out.append("")
        out.append("### Open line comments (address each)")
        for c in comments[:50]:
            loc = f"{c['file_path']}:{c['line_no']}" if c.get("line_no") else c["file_path"]
            out.append(f"- [{(c.get('source') or 'user').upper()}] {loc} → {(c.get('body') or '')[:300]}")
    # Sibling reports (predecessor deliverables) clipped inline — the escalation
    # writer's cwd is THIS task's workspace, so siblings can't be read from disk.
    try:
        import hermes_dispatch as _hd
        sibs = [d for d in _hd.task_dependencies(task) if d.get("status") == "done"]
    except Exception:
        sibs = []
    for d in sibs[:4]:
        fp = os.path.join(d.get("workspace_path") or "", "deliverable.md")
        if os.path.isfile(fp):
            try:
                body = open(fp, errors="replace").read()[:3000]
            except Exception:
                continue
            out.append("")
            out.append(f"### Sibling report — {(d.get('title') or d['id'])[:120]}")
            out.append(body)
    return "\n".join(out)


def run_escalation_cmd(task: dict, dossier_text: str, deliverable_rel: str = "deliverable.md",
                       model: str | None = None, api_key: str | None = None,
                       usage_sink: dict | None = None) -> str:
    """Run the escalated rework: write the dossier into the workspace, run cexec
    (settings super.escalation_cmd — gates stub it, same contract as critic_cmd)
    so the escalation_model rewrites the deliverable in place, then remove the
    dossier. Returns the model's log summary (already unwrapped). Blocks on the
    same _FRONTIER_GATE as the critic/judge (premortem P1)."""
    import shlex
    import shutil
    import subprocess as sp
    import settings_registry as sreg
    ws = task.get("workspace_path") or ""
    if not os.path.isdir(ws):
        return f"[escalation skipped: task {task.get('id')} has no workspace]"
    dossier_dir = Path(ws) / "_escalation"
    try:
        dossier_dir.mkdir(exist_ok=True)
        dossier_fp = dossier_dir / "dossier.md"
        dossier_fp.write_text(dossier_text or "(empty dossier)")
        tokens = [t.replace("{workspace}", ws)
                   .replace("{deliverable}", deliverable_rel)
                   .replace("{dossier}", str(dossier_fp))
                   .replace("{model}", model or "")
                  for t in shlex.split(
                      sreg.conf("super.escalation_cmd",
                                "cexec {workspace} {deliverable} {dossier}"))]
        tokens = [t for t in tokens if t != ""]
        if tokens and not shutil.which(tokens[0]):
            cand = os.path.expanduser(f"~/.local/bin/{tokens[0]}")
            if os.path.isfile(cand):
                tokens[0] = cand
        env = _scrubbed_env()
        if model:
            env["JUDGE_MODEL"] = model
        if api_key:
            env["JUDGE_ANTHROPIC_API_KEY"] = api_key
        timeout_s = int(sreg.conf("super.escalation_timeout_s", "2100") or 2100)
        try:
            with _FRONTIER_GATE:  # global frontier concurrency cap (premortem P1)
                r = sp.run(tokens, capture_output=True, text=True, timeout=timeout_s,
                           cwd=ws, env=env)
            out = _unwrap_frontier_output(r.stdout or "", usage_sink)  # C-8
            if r.returncode != 0:
                out += f"\n[escalation exited {r.returncode}] {(r.stderr or '')[-1000:]}"
        except sp.TimeoutExpired:
            out = f"[escalation timed out after {timeout_s}s]"
        except Exception as e:
            out = f"[escalation failed to run: {e}]"
        return out
    finally:
        shutil.rmtree(dossier_dir, ignore_errors=True)  # never leave it for the next critic copytree


# ─────────────────────────── Deep Plan premortem critique (Phase 5, Step 7) ───────────────────────────
# LOCKED §3.5/§3.6: plan verification is structural first, then ONE premortem by
# a DIFFERENT model (the spec_model purpose, an EXTERNAL judgment-tier verifier) —
# never the planner grading itself. The frontier call goes through the SAME
# _FRONTIER_GATE semaphore as the judge/critic (premortem P1).

def run_plan_critique(spec_text: str, plan_text: str, model: str | None = None,
                      api_key: str | None = None, timeout_s: int = 600) -> str:
    """Premortem: an external model assumes the plan FAILED and lists causes,
    missing tasks/deps, untestable criteria, and unowned risks as sentinel-fenced
    JSON. Mirrors run_judge_cmd's machinery (frontier gate, quota classification,
    cwd under knowledge). plan.stub short-circuits with a canned finding so the
    verify gate needs no frontier tokens (mirrors evals.stub)."""
    import shlex
    import shutil
    import subprocess as sp
    if db.get_setting("plan.stub", "0") == "1":
        return (f"[PLAN STUB — premortem stubbed for the gate]\n{PLAN_JSON_BEGIN}\n"
                '{"findings":[{"target":"task_0","kind":"missing",'
                '"problem":"[stub] a load-bearing dependency is unstated",'
                '"fix":"[stub] add the dependency edge"}]}\n' + PLAN_JSON_END + "\n")
    tmpdir = Path(KNOWLEDGE_DIR) / ".nexus-plan-tmp"
    spec_fp = plan_fp = None
    try:
        tmpdir.mkdir(exist_ok=True)
        tag = uuid.uuid4().hex[:8]
        spec_fp = tmpdir / f"spec-{tag}.md"
        plan_fp = tmpdir / f"plan-{tag}.md"
        spec_fp.write_text(spec_text or "(no spec)")
        plan_fp.write_text(plan_text or "(no plan)")
        prompt = (
            "You are the plan premortem reviewer — a second, stronger model checking a plan "
            "produced by a weaker one BEFORE it runs. Assume this plan has already FAILED.\n"
            f"Read the SPEC at {spec_fp.name} and the PLAN at {plan_fp.name} (both in your CWD).\n"
            "List the most likely causes of failure: missing tasks or dependencies; acceptance "
            "criteria that are not testable AS WRITTEN; scope the plan silently drops; risks with "
            "no owner. Be concrete and specific to THIS plan — no generic advice.\n"
            "Do NOT rewrite the plan. Do NOT modify any files. At most 8 findings.\n"
            "END the reply with exactly one JSON object between these sentinel lines, nothing "
            f"after the closing sentinel:\n{PLAN_JSON_BEGIN}\n"
            '{"findings": [{"target": "task_<idx> | spec_<slot> | plan", '
            '"kind": "missing|untestable|risk|dependency|scope", '
            '"problem": "what fails (<=300)", "fix": "concrete change (<=300)"}]}\n'
            f"{PLAN_JSON_END}")
        # settings override (stub/customization) mirrors judge.cmd; default = the
        # headless claude CLI directly on the spec_model.
        tmpl = (db.get_setting("plan.critique_cmd", "") or "").strip()
        if tmpl:
            tokens = [t.replace("{spec}", str(spec_fp)).replace("{plan}", str(plan_fp))
                       .replace("{model}", model or "") for t in shlex.split(tmpl)]
            tokens = [t for t in tokens if t != ""]
        else:
            tokens = ["claude"] + (["--model", model] if model else []) + ["-p", prompt]
        if tokens and not shutil.which(tokens[0]):
            cand = os.path.expanduser(f"~/.local/bin/{tokens[0]}")
            if os.path.isfile(cand):
                tokens[0] = cand
        # env scrub identical in spirit to cjudge: drop CLI-config vars, honour
        # a per-user key, else fall through to the subscription auth.
        env = {k: v for k, v in os.environ.items()
               if k not in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                            "ANTHROPIC_API_KEY", "CLAUDE_CONFIG_DIR",
                            "CLAUDE_CODE_SUBAGENT_MODEL")}
        env["PATH"] = _augment_path_for_claude(env.get("PATH", ""))  # phase7 finding 1
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        try:
            with _FRONTIER_GATE:  # global frontier concurrency cap (premortem P1)
                r = sp.run(tokens, capture_output=True, text=True, timeout=timeout_s,
                           cwd=str(tmpdir), env=env)
            out = (r.stdout or "")
            if r.returncode != 0:
                out += f"\n[premortem exited {r.returncode}] {(r.stderr or '')[-800:]}"
        except sp.TimeoutExpired:
            out = f"[premortem timed out after {timeout_s}s]"
        except Exception as e:
            out = f"[premortem failed to run: {e}]"
        return out
    finally:
        for fp in (spec_fp, plan_fp):
            try:
                if fp:
                    fp.unlink()
            except Exception:
                pass


def parse_plan_critique(text: str, max_findings: int = 8) -> list:
    """Extract the premortem's sentinel-fenced findings → advisory annotations.
    Never raises — a malformed reply yields []."""
    t = text or ""
    raw = None
    b = t.rfind(PLAN_JSON_BEGIN)
    if b != -1:
        e = t.find(PLAN_JSON_END, b)
        if e != -1:
            raw = t[b + len(PLAN_JSON_BEGIN):e].strip()
    if raw is None:
        end = t.rfind("}")
        if end != -1:
            depth = 0
            for i in range(end, -1, -1):
                if t[i] == "}":
                    depth += 1
                elif t[i] == "{":
                    depth -= 1
                    if depth == 0:
                        raw = t[i:end + 1]
                        break
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    findings = []
    for f in (data.get("findings") or [])[:max_findings] if isinstance(data, dict) else []:
        if not isinstance(f, dict):
            continue
        target = str(f.get("target") or "plan").strip()[:40]
        task_idx = None
        slot = None
        m = re.match(r"task[_\s]*(\d+)", target, re.I)
        if m:
            task_idx = int(m.group(1))
        elif target.lower().startswith("spec_"):
            slot = target[5:]
        findings.append({
            "target": target, "task_idx": task_idx, "slot": slot,
            "kind": str(f.get("kind") or "risk").strip().lower()[:20],
            "problem": _clip(f.get("problem"), 300),
            "fix": _clip(f.get("fix") or f.get("concrete_fix"), 300),
        })
    return findings


def _clip(v, n: int) -> str:
    return str(v).strip()[:n] if v is not None else ""


def parse_critic_json(text: str, repo_task: bool = False) -> dict:
    """Extract + validate the critic's sentinel-fenced JSON. Raises ValueError
    on unusable output (caller stores verdict='error' and escalates)."""
    t = text or ""
    raw = None
    b = t.rfind(CRITIC_JSON_BEGIN)  # last occurrence — narration may quote it
    if b != -1:
        e = t.find(CRITIC_JSON_END, b)
        if e != -1:
            raw = t[b + len(CRITIC_JSON_BEGIN):e].strip()
    if raw is None:
        # fallback: last balanced {…} block in the output
        end = t.rfind("}")
        if end != -1:
            depth = 0
            for i in range(end, -1, -1):
                if t[i] == "}":
                    depth += 1
                elif t[i] == "{":
                    depth -= 1
                    if depth == 0:
                        raw = t[i:end + 1]
                        break
    if not raw:
        raise ValueError("no critic JSON found in output")
    try:
        data = json.loads(raw)
    except Exception as e:
        raise ValueError(f"critic JSON did not parse: {e}")
    if not isinstance(data, dict):
        raise ValueError("critic JSON is not an object")
    verdict = str(data.get("verdict") or "").strip().upper()
    if verdict not in ("SHIP", "REVISE", "REWRITE"):
        raise ValueError(f"critic verdict missing/invalid: {verdict!r}")
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence"))))
    except (TypeError, ValueError):
        confidence = 0.5

    import settings_registry as sreg
    findings = []
    for f in (data.get("findings") or []):
        if not isinstance(f, dict):
            continue
        sev = str(f.get("severity") or "").strip().lower()
        if sev not in SEVERITY_ORDER:
            sev = "medium"
        fp = str(f.get("file_path") or "").strip().lstrip("/")
        if ".." in fp:
            fp = ""  # reject traversal: drop the anchor, keep the finding
        if fp.startswith("workspace/"):
            fp = fp[len("workspace/"):]
        elif repo_task and fp.startswith("repo/"):
            fp = fp[len("repo/"):]  # review paths are repo-relative
        if not fp:
            fp = "deliverable.md"
        try:
            line_no = int(f["line_no"]) if f.get("line_no") is not None else None
        except (TypeError, ValueError):
            line_no = None
        findings.append({
            "severity": sev, "file_path": fp[:500], "side": "new",
            "line_no": line_no,
            "line_text": _clip(f.get("line_text"), 200),
            "claim": _clip(f.get("claim"), 300),
            "evidence": _clip(f.get("evidence"), 400),
            "problem": _clip(f.get("problem"), 300),
            "suggested_fix": _clip(f.get("suggested_fix"), 300),
            # C1b: an optional unified-diff hunk for a mechanical critical/high
            # fix — the executor applies it verbatim instead of re-deriving prose.
            "patch": _clip(f.get("patch"), 1600) or None,
        })
    # severity-ordered so a truncation (here or at the comment cap) always
    # drops the LEAST severe findings (§4.8)
    findings.sort(key=lambda x: SEVERITY_ORDER[x["severity"]])
    findings = findings[:int(sreg.conf("super.max_findings", "25") or 25)]

    contradictions = [{"with": _clip(c.get("with"), 100) or "internal",
                       "a": _clip(c.get("a"), 300), "b": _clip(c.get("b"), 300),
                       "resolution_hint": _clip(c.get("resolution_hint"), 300)}
                      for c in (data.get("contradictions") or [])[:10]
                      if isinstance(c, dict)]
    missing = [{"what": _clip(m.get("what"), 300),
                "why_it_matters": _clip(m.get("why_it_matters"), 300)}
               for m in (data.get("missing") or [])[:10] if isinstance(m, dict)]

    parsed = {
        "verdict": verdict,
        "confidence": confidence,
        "summary": _clip(data.get("summary"), 600),
        "findings": findings,
        "contradictions": contradictions,
        "missing": missing,
        "revision_brief": _clip(data.get("revision_brief"), 2500),
        "learning_note": _clip(data.get("learning_note"), 300) or None,  # B6
    }
    # stable per-finding keys drive the no-new-findings convergence check
    parsed["_keys"] = [
        hashlib.sha1(f"{f['file_path']}|{f['severity']}|"
                     f"{(f['claim'] or f['problem'])[:120].lower()}".encode()
                     ).hexdigest()[:12]
        for f in findings]
    return parsed


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
    run_model = case.get("model") or db.default_task_model(uid)  # Settings v2
    sid = hd.create_session(f"nexus:eval:{run_id}:{case['id']}", model=run_model)
    hd.publish_session_scope(sid, user=uid)  # memory stays the runner's scope
    hd.publish_session_key(sid, uid, run_model)  # owner's key, if configured
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
            jmodel, jkey = judge_model_for(uid)
            # N1 eval-corpus compatibility: the type rubric applies ONLY when
            # the case opts in via frontmatter — default stays today's behavior.
            trubric = type_rubric_path(case["deliverable_type"]) \
                if case.get("deliverable_type") else None
            jsink: dict = {}
            out = run_judge_cmd(gen["path"], domain, model=jmodel, api_key=jkey,
                                type_rubric=trubric, usage_sink=jsink)
            # C3 ledger: eval-judge spend is tagged by run_id (workflow_id slot)
            # so the Phase-8 campaign can total frontier $ per arm.
            record_frontier_spend(jsink, out, "judge_eval",
                                  jmodel or db.fallback_model("frontier_judge"),
                                  task_id=None, workflow_id=run_id, user_id=uid)
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
