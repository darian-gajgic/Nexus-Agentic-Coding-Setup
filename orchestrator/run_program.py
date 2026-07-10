#!/usr/bin/env python3
"""Autonomous runner for the Quality Program (EXECUTION-RUNBOOK-2026-07-10.md v2).

Executes each runbook phase as a separate headless `claude -p` session (one at a
time — runbook rule 1), verifies completion deterministically between phases
(gates, git tree, service health, report file), loops judge REVISE rounds until
SHIP, waits out CLI quota windows, and STOPS at defined human checkpoints.

Usage:
  python3 orchestrator/run_program.py            # run / resume from state.json
  python3 orchestrator/run_program.py --ack      # acknowledge the pending checkpoint, then continue
  python3 orchestrator/run_program.py --status   # show progress, cost, pending checkpoint
  python3 orchestrator/run_program.py --dry-run  # show the step plan without running anything
  python3 orchestrator/run_program.py --from phase3   # force re-run from a step

Exit codes:
  0   all steps up to the next checkpoint completed (or program done)
  3   CHECKPOINT — human review required; rerun with --ack to continue
  4   ESCALATION — see orchestrator/ESCALATION.md; fix, then rerun
  130 interrupted (state saved; rerun to resume)

Model/timeout overrides via env: QP_IMPL_MODEL, QP_JUDGE_MODEL, QP_IMPL_TIMEOUT_S,
QP_JUDGE_TIMEOUT_S, QP_MAX_QUOTA_WAIT_S.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- configuration

ORCH = Path(__file__).resolve().parent
REPO = ORCH.parent
PROMPTS = ORCH / "prompts"
LOGS = ORCH / "logs"
STATE_FILE = ORCH / "state.json"
ESCALATION_FILE = ORCH / "ESCALATION.md"

import os

IMPL_MODEL = os.environ.get("QP_IMPL_MODEL", "claude-opus-4-8")
JUDGE_MODEL = os.environ.get("QP_JUDGE_MODEL", "claude-fable-5")
IMPL_TIMEOUT_S = int(os.environ.get("QP_IMPL_TIMEOUT_S", str(5 * 3600)))
JUDGE_TIMEOUT_S = int(os.environ.get("QP_JUDGE_TIMEOUT_S", str(3 * 3600)))
GATE_TIMEOUT_S = 1800
COMMIT_TIMEOUT_S = 1200          # pre-commit hook runs verify.sh
MAX_JUDGE_ROUNDS = 3             # judge attempts per phase before escalating
MAX_CONTINUATIONS = 2            # interrupted-session continuations per phase
MAX_TRANSIENT_RETRIES = 1        # non-quota child errors
QUOTA_SLEEP_S = 900              # 15 min between quota probes
MAX_QUOTA_WAIT_S = int(os.environ.get("QP_MAX_QUOTA_WAIT_S", str(6 * 3600)))
SERVICE_URL = "https://127.0.0.1:8777/"
VENV_PY = "app/.venv/bin/python"

IMPL_ALLOWED = ["Bash", "Read", "Edit", "Write", "Grep", "Glob", "WebFetch",
                "WebSearch", "Task", "Agent", "TodoWrite", "NotebookEdit"]
JUDGE_ALLOWED = ["Bash", "Read", "Grep", "Glob"]
DISALLOWED = ["Bash(git push:*)", "Bash(gh:*)", "Bash(sudo:*)"]

SIX_DOCS = [
    "QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md",
    "EXECUTION-RUNBOOK-2026-07-10.md",
    "SUPER-RESULT-PLAN-Check.md",
    "SUPER-RESULT-PLAN-2026-07-09.md",
    "QUALITY-AUTOPILOT-PLAN-2026-07-10.md",
    "DEEP-PLAN-MODE-PLAN-2026-07-10.md",
]
PROBE_FILE = "app/static/avatar/_probe_scan.glb"   # master plan C-1: delete, never stage
DOCS_COMMIT_MSG = "docs: quality program verified — master plan + runbook v2 + critic check folded in"

VERIFY_SH = ["bash", "app/scripts/verify.sh"]


def e2e(name):
    return [VENV_PY, f"app/scripts/{name}"]


# gates the runner re-runs itself after each implementation phase / fix round
GATES = {
    "phase1": [VERIFY_SH, e2e("verify_super_result_e2e.py"),
               e2e("verify_block2_e2e.py"), e2e("verify_block3_e2e.py")],
    "phase3": [VERIFY_SH, e2e("verify_autopilot_e2e.py"),
               e2e("verify_super_result_e2e.py"),
               e2e("verify_block2_e2e.py"), e2e("verify_block3_e2e.py")],
    "phase5": [VERIFY_SH, e2e("verify_deep_plan_e2e.py"),
               e2e("verify_super_result_e2e.py")],
    "phase7": [VERIFY_SH, e2e("verify_super_result_e2e.py"),
               e2e("verify_autopilot_e2e.py"), e2e("verify_deep_plan_e2e.py")],
    "phase8": [VERIFY_SH],
}

# report file each implementation phase must leave at the repo root
# (path, required substring or None)
REPORTS = {
    "phase1": ("IMPLEMENTATION-REPORT-SUPER-RESULT.md", "Fixes 2026-07-10"),
    "phase3": ("IMPLEMENTATION-REPORT-QUALITY-AUTOPILOT.md", None),
    "phase5": ("IMPLEMENTATION-REPORT-DEEP-PLAN.md", None),
    "phase7": ("IMPLEMENTATION-REPORT-APPENDIX-C.md", None),
    "phase8": (None, None),
}

STEPS = [
    {"name": "phase0", "kind": "phase0"},
    {"name": "phase1", "kind": "impl", "db_backup": True},
    {"name": "phase2", "kind": "judge", "impl": "phase1"},
    {"name": "checkpoint-after-phase2", "kind": "checkpoint", "msg":
        "Foundation verified (Phase 2 SHIP). Before Phase 3 — the biggest phase —\n"
        "take 5 minutes yourself: open " + SERVICE_URL + " and click around, skim the\n"
        "'Fixes 2026-07-10' section of IMPLEMENTATION-REPORT-SUPER-RESULT.md and\n"
        "`git log --oneline -15`. Then continue with:  python3 orchestrator/run_program.py --ack"},
    {"name": "phase3", "kind": "impl", "db_backup": True},
    {"name": "phase4", "kind": "judge", "impl": "phase3"},
    {"name": "checkpoint-after-phase4", "kind": "checkpoint", "msg":
        "Quality Autopilot verified (Phase 4 SHIP). Do the 2-minute real-usage walk\n"
        "(runbook rule 9): open " + SERVICE_URL + " — Decisions view, the two preset\n"
        "card rows in the wizard, create a throwaway task. Then --ack to continue."},
    {"name": "phase5", "kind": "impl", "db_backup": True},
    {"name": "phase6", "kind": "judge", "impl": "phase5"},
    {"name": "checkpoint-after-phase6", "kind": "checkpoint", "msg":
        "Deep Plan verified (Phase 6 SHIP). Real-usage walk: type a complex goal into\n"
        "the wizard, check the Deep Plan banner appears and accepting it opens the\n"
        "chat+spec modal. Then --ack to continue into Phase 7."},
    {"name": "phase7", "kind": "impl", "db_backup": True},
    {"name": "phase7-judge", "kind": "judge", "impl": "phase7"},
    {"name": "checkpoint-before-phase8", "kind": "checkpoint", "msg":
        "Phases 1-7 are SHIP. Phase 8 is the ONE PAID measurement campaign — it spends\n"
        "real GLM + judge tokens on purpose (runbook: run it when you won't need the\n"
        "machine's full attention for a day). Confirm deliberately with --ack."},
    {"name": "phase8", "kind": "impl", "db_backup": False},
    {"name": "checkpoint-program-complete", "kind": "checkpoint", "msg":
        "Phase 8 finished. Review the win-rate/CI/cost matrix and the WINS/LESSONS\n"
        "entries yourself, set your autopilot defaults from the data (Settings), and\n"
        "--ack to mark the program complete."},
]

IMPL_SUFFIX = """

--- HEADLESS PROTOCOL (appended by the program runner) ---
You are running headless inside an automated program runner; nobody can answer
questions mid-run. Rules:
- Every design decision is already locked in the plan documents — follow them.
  QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md section 5 overrides on conflict. If the
  docs are genuinely wrong about the code, record the deviation in your report and
  continue; do not stop to ask.
- Work from the repo root. Never `git push`, never `gh`, never `sudo`.
- Commit granularly as instructed and leave the working tree FULLY COMMITTED when
  you finish (untracked artifacts you created either belong in a commit or must be
  removed).
- If you approach your context limit: commit what is done, write HANDOFF-<phase>.md
  at the repo root (exact step reached, files touched, what remains), and stop —
  the runner spawns a continuation session that reads it.
- End your final message with exactly one line: `PHASE COMPLETE` if you finished
  everything, or `PHASE PARTIAL` if you stopped early or handed off.
"""

JUDGE_SUFFIX = """

--- HEADLESS PROTOCOL (appended by the program runner) ---
You are running headless inside an automated program runner; nobody can answer
questions. Work from the repo root. You are a judge: do NOT modify any file, do NOT
fix anything you find. End your reply with EXACTLY one of these two forms as the
final lines, nothing after them:

VERDICT: SHIP

or

VERDICT: REVISE
BLOCKING:
1. <file:line — what remains and why it blocks>
2. ...
"""

CONTINUATION_PROMPT = """A previous headless session executing {phase} of the quality program was
interrupted (timeout, crash, or context handoff). Recover and continue:

1. Inspect current state: `git log --oneline -15`, `git status`, any HANDOFF-*.md at
   the repo root, and {report} if it exists.
2. Continue {phase} from where it stopped — do NOT redo work that is already
   committed; verify it instead. Delete the HANDOFF file once absorbed.
3. The original phase instructions follow; the same rules apply.

--- ORIGINAL PHASE PROMPT ---
{prompt}
"""

REMEDIATION_PROMPT = """The automated program runner verified {phase} after the implementation session
finished and found these completion problems:

{failures}

Fix ONLY these problems: re-run the failing gates yourself until green, commit any
uncommitted work as coherent commits (never one blob), complete the missing report
section if listed. Do NOT start new feature work. The phase contract is
orchestrator/prompts/{prompt_file} plus the plan documents it names;
QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md section 5 overrides on conflict.
"""

FIX_PROMPT = """The independent judge reviewed {phase} of the quality program and returned REVISE.
Fix the judge's blocking findings: verify each against HEAD first (re-locate by
symbol; if a finding is not reproducible, record 'already-ok' with evidence in the
report instead of patching), add a regression check per fix, update {report}, and
commit granularly.

JUDGE'S BLOCKING LIST:
{blocking}
"""

QUOTA_RE = re.compile(
    r"(usage limit|rate.?limit|quota|overloaded|too many requests|limit reached|"
    r"out of extra usage|resets at)", re.I)

# ---------------------------------------------------------------- small helpers


def now_ts():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / "program.log", "a") as f:
        f.write(line + "\n")


def notify(title, body):
    if shutil.which("notify-send"):
        try:
            subprocess.run(["notify-send", "-u", "critical", title, body],
                           timeout=10, capture_output=True)
        except Exception:
            pass


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"completed": [], "acked": [], "pending_checkpoint": None,
            "judge_rounds": {}, "cost_usd": 0.0, "preflight_done": False}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def escalate(state, step, reason, details=""):
    save_state(state)
    ESCALATION_FILE.write_text(f"""# ESCALATION — quality program runner

**When:** {datetime.now().isoformat(timespec='seconds')}
**Step:** {step}
**Reason:** {reason}

{details}

## What to do
1. Read the latest child logs in `orchestrator/logs/` (newest first).
2. If this is an implementer-vs-judge deadlock: per runbook rule 8, do NOT referee it
   yourself here — resume the planning conversation (`claude --resume`) and paste both
   positions; it has the design context to arbitrate.
3. If it is an operational wedge (service down, dirty git tree, stuck DB): fix only
   the operational issue. DB backups are at app/nexus.db.bak-*.
4. Then rerun `python3 orchestrator/run_program.py` — it resumes at this step.
   (To redo an earlier step: `--from <step>`.)
""")
    log(f"ESCALATION at {step}: {reason} — see {ESCALATION_FILE}")
    notify("Quality program: ESCALATION", f"{step}: {reason}")
    sys.exit(4)


def run_cmd(argv, timeout, cwd=REPO):
    """Run a plain command; return (rc, combined-tail)."""
    try:
        p = subprocess.run(argv, cwd=str(cwd), timeout=timeout,
                           capture_output=True, text=True)
        tail = ((p.stdout or "") + "\n" + (p.stderr or ""))[-3000:]
        return p.returncode, tail
    except subprocess.TimeoutExpired:
        return -1, f"TIMEOUT after {timeout}s: {' '.join(argv)}"
    except Exception as e:  # noqa: BLE001
        return -2, f"EXEC ERROR: {e}"


# ---------------------------------------------------------------- claude children


def run_claude(state, name, prompt, model, allowed, timeout, cont_prompt=None):
    """Run one headless claude session; handles quota waits and transient retries.

    cont_prompt: recovery prompt to use for re-spawns after a quota interruption
    (the interrupted child's on-disk/committed work survives; the fresh child must
    continue, not redo). Credentials are read fresh at every spawn, so switching
    `claude login` accounts during a quota sleep takes effect on the next probe.

    Returns dict {ok, timed_out, text, log_path}.
    """
    LOGS.mkdir(parents=True, exist_ok=True)
    # Subscription-only guarantee: strip anything that could reroute billing to a
    # metered API or a third-party gateway. Children then authenticate solely via
    # the `claude login` OAuth credentials (the operator's subscription).
    child_env = {k: v for k, v in os.environ.items()
                 if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                              "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK",
                              "CLAUDE_CODE_USE_VERTEX")}
    argv = ["claude", "-p", prompt, "--model", model,
            "--output-format", "json",
            "--permission-mode", "acceptEdits",
            "--allowedTools", *allowed,
            "--disallowedTools", *DISALLOWED]
    quota_waited = 0
    transient = 0
    while True:
        log_path = LOGS / f"{now_ts()}-{name}.json"
        log(f"child start: {name} (model={model}, timeout={timeout}s) → {log_path.name}")
        t0 = time.time()
        timed_out = False
        try:
            p = subprocess.run(argv, cwd=str(REPO), timeout=timeout,
                               env=child_env, capture_output=True, text=True)
            rc, stdout, stderr = p.returncode, p.stdout or "", p.stderr or ""
        except subprocess.TimeoutExpired as e:
            timed_out = True
            rc = -1
            stdout = (e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout) or ""
            stderr = (e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr) or ""

        envelope, text, cost = {}, stdout, 0.0
        try:
            envelope = json.loads(stdout)
            text = envelope.get("result") or ""
            cost = float(envelope.get("total_cost_usd") or 0.0)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

        log_path.write_text(json.dumps({
            "name": name, "model": model, "rc": rc, "timed_out": timed_out,
            "duration_s": round(time.time() - t0), "stdout": stdout,
            "stderr": stderr}, indent=2))
        state["cost_usd"] = round(state.get("cost_usd", 0.0) + cost, 4)
        save_state(state)
        log(f"child end: {name} rc={rc} timed_out={timed_out} "
            f"cost=${cost:.2f} (program total ${state['cost_usd']:.2f})")

        if timed_out:
            return {"ok": False, "timed_out": True, "text": text, "log_path": log_path}

        is_error = bool(envelope.get("is_error")) or rc != 0
        if not is_error:
            return {"ok": True, "timed_out": False, "text": text, "log_path": log_path}

        blob = (stdout + "\n" + stderr)
        if QUOTA_RE.search(blob):
            if quota_waited >= MAX_QUOTA_WAIT_S:
                escalate(state, name, "quota wait budget exhausted",
                         f"Waited {quota_waited // 60} min total. Last output tail:\n"
                         f"```\n{blob[-1500:]}\n```\nRerun later; the runner resumes here.")
            log(f"quota/rate-limit detected — sleeping {QUOTA_SLEEP_S // 60} min "
                f"({(MAX_QUOTA_WAIT_S - quota_waited) // 60} min budget left). "
                f"Tip: `claude logout && claude login` on another account in your own "
                f"terminal — the next probe uses the new credentials automatically.")
            notify("Quality program: quota wait",
                   f"{name}: sleeping {QUOTA_SLEEP_S // 60} min on CLI usage limit "
                   f"(account switch in a terminal takes effect on the next probe)")
            time.sleep(QUOTA_SLEEP_S)
            quota_waited += QUOTA_SLEEP_S
            if cont_prompt and argv[2] != cont_prompt:
                argv[2] = cont_prompt
                log(f"{name}: switching to the continuation prompt — the fresh child "
                    f"will resume from git state instead of redoing the phase")
            continue

        if transient < MAX_TRANSIENT_RETRIES:
            transient += 1
            log(f"child error (non-quota) — transient retry {transient}/{MAX_TRANSIENT_RETRIES}")
            time.sleep(30)
            continue

        escalate(state, name, "child session failed (non-quota error)",
                 f"Exit {rc}. Output tail:\n```\n{blob[-2000:]}\n```")


# ---------------------------------------------------------------- verification


def service_ok():
    subprocess.run(["systemctl", "--user", "restart", "nexus"],
                   capture_output=True, timeout=60)
    for _ in range(30):
        rc, out = run_cmd(["curl", "-ks", "-o", "/dev/null", "-w", "%{http_code}",
                           "--max-time", "5", SERVICE_URL], timeout=10)
        code = out.strip()[-3:]
        if rc == 0 and code.isdigit() and int(code) < 500:
            return True
        time.sleep(2)
    return False


def git_dirty():
    rc, out = run_cmd(["git", "status", "--porcelain"], timeout=60)
    return [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else ["<git status failed>"]


def collect_failures(phase):
    """Deterministic completion check. Returns list of failure descriptions."""
    failures = []
    if not service_ok():
        failures.append(f"service: `systemctl --user restart nexus` did not yield an "
                        f"HTTP response < 500 at {SERVICE_URL}")
    for gate in GATES.get(phase, []):
        target = Path(REPO / gate[-1])
        if gate[0] != "bash" and not target.exists():
            failures.append(f"gate MISSING (was supposed to be built this phase): {gate[-1]}")
            continue
        rc, tail = run_cmd(gate, timeout=GATE_TIMEOUT_S)
        if rc != 0:
            failures.append(f"gate FAILED (exit {rc}): `{' '.join(gate)}`\n"
                            f"output tail:\n{tail}")
    dirty = git_dirty()
    dirty = [d for d in dirty if not d.split()[-1].startswith("orchestrator/")]
    if dirty:
        failures.append("git tree not clean (uncommitted work):\n" + "\n".join(dirty[:30]))
    report, marker = REPORTS.get(phase, (None, None))
    if report:
        rp = REPO / report
        if not rp.exists():
            failures.append(f"report missing: {report}")
        elif marker and marker not in rp.read_text():
            failures.append(f"report {report} lacks required section '{marker}'")
    return failures


# ---------------------------------------------------------------- step runners


def read_prompt(fname):
    p = PROMPTS / fname
    if not p.exists():
        sys.exit(f"prompt file missing: {p}")
    return p.read_text()


def db_backup(tag):
    src = REPO / "app/nexus.db"
    if src.exists():
        dst = REPO / f"app/nexus.db.bak-{tag}"
        shutil.copy2(src, dst)
        log(f"db backup → {dst.name}")
    else:
        log("WARN: app/nexus.db not found — no backup taken")


def run_impl_phase(state, phase):
    if next(s for s in STEPS if s["name"] == phase).get("db_backup"):
        db_backup(phase)
    prompt_file = f"{phase}-impl.md"
    prompt = read_prompt(prompt_file) + IMPL_SUFFIX
    report, _ = REPORTS.get(phase, (None, None))

    cont = CONTINUATION_PROMPT.format(phase=phase, report=report or "the phase report",
                                      prompt=read_prompt(prompt_file)) + IMPL_SUFFIX
    res = run_claude(state, f"{phase}-impl", prompt, IMPL_MODEL,
                     IMPL_ALLOWED, IMPL_TIMEOUT_S, cont_prompt=cont)
    conts = 0
    while (res["timed_out"] or "PHASE PARTIAL" in res["text"]) and conts < MAX_CONTINUATIONS:
        conts += 1
        log(f"{phase}: interrupted/partial — continuation {conts}/{MAX_CONTINUATIONS}")
        res = run_claude(state, f"{phase}-impl-cont{conts}", cont, IMPL_MODEL,
                         IMPL_ALLOWED, IMPL_TIMEOUT_S, cont_prompt=cont)
    if res["timed_out"] or "PHASE PARTIAL" in res["text"]:
        escalate(state, phase, "phase still incomplete after continuation budget",
                 f"See {res['log_path']} and any HANDOFF-*.md at the repo root.")

    failures = collect_failures(phase)
    if failures:
        log(f"{phase}: completion check found {len(failures)} problem(s) — one remediation child")
        rem = REMEDIATION_PROMPT.format(phase=phase, prompt_file=prompt_file,
                                        failures="\n\n".join(failures)) + IMPL_SUFFIX
        run_claude(state, f"{phase}-remediate", rem, IMPL_MODEL, IMPL_ALLOWED, IMPL_TIMEOUT_S)
        failures = collect_failures(phase)
        if failures:
            escalate(state, phase, "completion checks still failing after remediation",
                     "\n\n".join(failures))
    log(f"{phase}: implementation complete, all deterministic checks green")


def parse_verdict(text):
    matches = list(re.finditer(r"VERDICT:\s*(SHIP|REVISE)", text, re.I))
    if not matches:
        return None, ""
    verdict = matches[-1].group(1).upper()
    tail = text[matches[-1].end():]
    m = re.search(r"BLOCKING:\s*(.+)", tail, re.S)
    blocking = (m.group(1).strip() if m else tail.strip()) or text[-4000:]
    return verdict, blocking[:8000]


def run_judge_phase(state, step):
    phase, impl = step["name"], step["impl"]
    prompt = read_prompt(f"{phase}-judge.md") + JUDGE_SUFFIX
    report, _ = REPORTS.get(impl, (None, None))
    rounds = state["judge_rounds"].get(phase, 0)

    while rounds < MAX_JUDGE_ROUNDS:
        rounds += 1
        state["judge_rounds"][phase] = rounds
        save_state(state)
        res = run_claude(state, f"{phase}-judge-r{rounds}", prompt, JUDGE_MODEL,
                         JUDGE_ALLOWED, JUDGE_TIMEOUT_S)
        verdict, blocking = parse_verdict(res["text"])
        if verdict is None:
            log(f"{phase}: judge returned no VERDICT line — one retry")
            res = run_claude(state, f"{phase}-judge-r{rounds}-retry", prompt, JUDGE_MODEL,
                             JUDGE_ALLOWED, JUDGE_TIMEOUT_S)
            verdict, blocking = parse_verdict(res["text"])
            if verdict is None:
                escalate(state, phase, "judge produced no parsable verdict twice",
                         f"See {res['log_path']}")
        if verdict == "SHIP":
            log(f"{phase}: VERDICT SHIP after round {rounds}")
            state["judge_rounds"].pop(phase, None)
            save_state(state)
            return
        log(f"{phase}: VERDICT REVISE (round {rounds}/{MAX_JUDGE_ROUNDS}) — spawning fix session")
        judge_dirty = [d for d in git_dirty()
                       if not d.split()[-1].startswith("orchestrator/")]
        if judge_dirty:
            escalate(state, phase, "judge session modified the working tree",
                     "A judge must not edit. Dirty entries:\n" + "\n".join(judge_dirty[:30]))
        fix = FIX_PROMPT.format(phase=impl, report=report or "the phase report",
                                blocking=blocking) + IMPL_SUFFIX
        run_claude(state, f"{impl}-fix-r{rounds}", fix, IMPL_MODEL, IMPL_ALLOWED, IMPL_TIMEOUT_S)
        failures = collect_failures(impl)
        if failures:
            rem = REMEDIATION_PROMPT.format(phase=impl, prompt_file=f"{impl}-impl.md",
                                            failures="\n\n".join(failures)) + IMPL_SUFFIX
            run_claude(state, f"{impl}-fix-r{rounds}-remediate", rem, IMPL_MODEL,
                       IMPL_ALLOWED, IMPL_TIMEOUT_S)
            failures = collect_failures(impl)
            if failures:
                escalate(state, phase, "fix round left completion checks red",
                         "\n\n".join(failures))
    escalate(state, phase, f"no SHIP after {MAX_JUDGE_ROUNDS} judge rounds",
             "Likely an implementer-vs-judge deadlock — runbook rule 8 applies "
             "(arbitrate via the planning conversation, not here). Last judge log in "
             "orchestrator/logs/.")


# ---------------------------------------------------------------- phase 0


def classify_dirt():
    cats = {"docs": [], "orch": [], "probe": [], "other_md": [], "other": []}
    for ln in git_dirty():
        path = ln[3:].strip().strip('"') if len(ln) > 3 else ln
        if path in SIX_DOCS:
            cats["docs"].append(path)
        elif path.startswith("orchestrator/"):
            cats["orch"].append(path)
        elif path == PROBE_FILE:
            cats["probe"].append(path)
        elif path.endswith(".md") and "/" not in path:
            cats["other_md"].append(path)
        else:
            cats["other"].append(path)
    return cats


def run_phase0(state, args):
    cats = classify_dirt()
    if cats["other"]:
        escalate(state, "phase0", "non-doc feature work is dirty in the tree",
                 "Runbook Phase 0 / critic check F1: anything that is not a program doc "
                 "needs its OWN commit first, by you or a dedicated session — the runner "
                 "will not guess what it belongs to:\n\n"
                 + "\n".join(f"- {p}" for p in cats["other"])
                 + "\n\nCommit or remove these, then rerun.")

    plan_lines = []
    if cats["probe"]:
        plan_lines.append(f"DELETE {PROBE_FILE} (master plan C-1: delete, never stage)")
    for md in cats["other_md"]:
        plan_lines.append(f"commit '{md}' alone as: docs: {Path(md).stem} (pre-program housekeeping)")
    if cats["docs"]:
        plan_lines.append(f"commit the {len(cats['docs'])} program doc(s) as: {DOCS_COMMIT_MSG}")
    plan_lines.append("commit orchestrator/ as: feat(orchestrator): autonomous quality-program runner")
    plan_lines.append("cp app/nexus.db app/nexus.db.bak-pre-quality-program")
    plan_lines = [f"{i}. {ln}" for i, ln in enumerate(plan_lines, 1)]

    if "phase0-plan" not in state["acked"]:
        state["pending_checkpoint"] = "phase0-plan"
        save_state(state)
        print("\n" + "=" * 74)
        print("PHASE 0 PLAN (commit hygiene — review, then rerun with --ack):")
        print("=" * 74)
        print("\n".join(plan_lines))
        print("=" * 74 + "\n")
        notify("Quality program", "Phase 0 plan awaits your --ack")
        sys.exit(3)

    if cats["probe"]:
        (REPO / PROBE_FILE).unlink(missing_ok=True)
        log(f"deleted {PROBE_FILE} (C-1)")
    for md in cats["other_md"]:
        for cmd in (["git", "add", md],
                    ["git", "commit", "-m", f"docs: {Path(md).stem} (pre-program housekeeping)"]):
            rc, tail = run_cmd(cmd, timeout=COMMIT_TIMEOUT_S)
            if rc != 0:
                escalate(state, "phase0", f"git failed on {md}", tail)
    if cats["docs"]:
        rc, tail = run_cmd(["git", "add", *cats["docs"]], timeout=60)
        rc2, tail2 = run_cmd(["git", "commit", "-m", DOCS_COMMIT_MSG], timeout=COMMIT_TIMEOUT_S)
        if rc != 0 or rc2 != 0:
            escalate(state, "phase0", "docs commit failed", tail + "\n" + tail2)
    rc, tail = run_cmd(["git", "add", "orchestrator"], timeout=60)
    rc2, tail2 = run_cmd(["git", "commit", "-m",
                          "feat(orchestrator): autonomous quality-program runner"],
                         timeout=COMMIT_TIMEOUT_S)
    if rc != 0 or rc2 != 0:
        escalate(state, "phase0", "orchestrator commit failed", tail + "\n" + tail2)
    db_backup("pre-quality-program")
    leftover = [d for d in git_dirty() if not d.split()[-1].startswith("orchestrator/")]
    if leftover:
        escalate(state, "phase0", "tree still dirty after Phase 0 commits",
                 "\n".join(leftover[:30]))
    log("phase0: clean tree, docs + orchestrator committed, DB backed up")


# ---------------------------------------------------------------- preflight


def preflight(state):
    if state.get("preflight_done"):
        return
    log("preflight: environment checks")
    problems = []
    if not (REPO / "app" / "scripts" / "verify.sh").exists():
        problems.append("app/scripts/verify.sh missing — wrong repo root?")
    if not (REPO / VENV_PY).exists():
        problems.append(f"{VENV_PY} missing")
    if not shutil.which("claude"):
        problems.append("claude CLI not on PATH")
    rc, _ = run_cmd(["systemctl", "--user", "status", "nexus"], timeout=30)
    if rc not in (0, 3):
        problems.append("systemd user unit 'nexus' not found")
    if problems:
        escalate(state, "preflight", "environment not ready", "\n".join(problems))
    for label, model in (("impl", IMPL_MODEL), ("judge", JUDGE_MODEL)):
        res = run_claude(state, f"preflight-{label}", "Reply with exactly: OK",
                         model, ["Read"], 300)
        if "OK" not in res["text"]:
            escalate(state, "preflight", f"{label} model '{model}' ping failed",
                     f"Override with QP_{label.upper()}_MODEL env var if the id is wrong. "
                     f"See {res['log_path']}")
    state["preflight_done"] = True
    save_state(state)
    log(f"preflight OK (impl={IMPL_MODEL}, judge={JUDGE_MODEL})")


# ---------------------------------------------------------------- main


def print_status(state):
    print(f"completed: {', '.join(state['completed']) or '(none)'}")
    print(f"pending checkpoint: {state['pending_checkpoint'] or '(none)'}")
    print(f"judge rounds in flight: {state['judge_rounds'] or '{}'}")
    print(f"cost so far (API-equivalent): ${state.get('cost_usd', 0):.2f}")
    nxt = next((s["name"] for s in STEPS if s["name"] not in state["completed"]), None)
    print(f"next step: {nxt or 'PROGRAM COMPLETE'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ack", action="store_true",
                    help="acknowledge the pending checkpoint and continue")
    ap.add_argument("--status", action="store_true", help="show progress and exit")
    ap.add_argument("--dry-run", action="store_true", help="show the step plan and exit")
    ap.add_argument("--from", dest="from_step", metavar="STEP",
                    help="force re-run from this step (clears it and later steps)")
    ap.add_argument("--preflight", action="store_true",
                    help="re-run the model/environment preflight before continuing "
                         "(use after switching `claude login` accounts)")
    args = ap.parse_args()

    state = load_state()

    if args.status:
        print_status(state)
        return

    if args.dry_run:
        for s in STEPS:
            mark = "✓" if s["name"] in state["completed"] else " "
            kind = s["kind"]
            model = {"impl": IMPL_MODEL, "judge": JUDGE_MODEL}.get(kind, "—")
            print(f" [{mark}] {s['name']:32s} {kind:10s} {model}")
        print(f"\nprompts dir: {PROMPTS}  |  state: {STATE_FILE}")
        return

    if args.from_step:
        names = [s["name"] for s in STEPS]
        if args.from_step not in names:
            sys.exit(f"unknown step '{args.from_step}'. Steps: {', '.join(names)}")
        idx = names.index(args.from_step)
        drop = set(names[idx:])
        state["completed"] = [n for n in state["completed"] if n not in drop]
        state["acked"] = [n for n in state["acked"] if n not in drop and
                          not (args.from_step == "phase0" and n == "phase0-plan")]
        state["pending_checkpoint"] = None
        for k in list(state["judge_rounds"]):
            if k in drop:
                state["judge_rounds"].pop(k)
        save_state(state)
        log(f"state rewound to re-run from {args.from_step}")

    if args.ack:
        pc = state.get("pending_checkpoint")
        if pc:
            state["acked"].append(pc)
            state["pending_checkpoint"] = None
            save_state(state)
            log(f"checkpoint acknowledged: {pc}")
        else:
            log("--ack given but no checkpoint pending (continuing)")

    if args.preflight:
        state["preflight_done"] = False
        save_state(state)

    preflight(state)

    for step in STEPS:
        name = step["name"]
        if name in state["completed"]:
            continue
        if step["kind"] == "checkpoint":
            if name in state["acked"]:
                state["completed"].append(name)
                save_state(state)
                continue
            state["pending_checkpoint"] = name
            save_state(state)
            print("\n" + "=" * 74)
            print(f"CHECKPOINT: {name}")
            print("=" * 74)
            print(step["msg"])
            print("=" * 74 + "\n")
            notify("Quality program: checkpoint", name)
            sys.exit(3)

        log(f"=== STEP {name} ({step['kind']}) ===")
        if step["kind"] == "phase0":
            run_phase0(state, args)
        elif step["kind"] == "impl":
            run_impl_phase(state, name)
        elif step["kind"] == "judge":
            run_judge_phase(state, step)
        state["completed"].append(name)
        save_state(state)
        notify("Quality program", f"{name} complete "
               f"(${state.get('cost_usd', 0):.2f} API-equiv so far)")

    print("\n" + "=" * 74)
    print("QUALITY PROGRAM COMPLETE — all steps done.")
    print_status(state)
    print("=" * 74)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\ninterrupted — state saved; rerun to resume")
        sys.exit(130)
