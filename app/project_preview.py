"""NEXUS Agent OS — Project preview states (v3.6): ▶ Test the WHOLE project.

A project (workflow) shouldn't only be testable one task-deliverable at a
time — the operator wants to run the complete assembled result, and to
time-travel: start the state as it was BEFORE the newest changes next to the
current one, so old and new can be compared live (did the last stage break
something?).

Two project shapes, two history sources — both materialize into an isolated,
disposable directory under workspaces/workflow-<id>/_project_preview/<key>/state
so the live worktree / task workspaces are NEVER run in place or mutated:

  repo project (member tasks carry repo_path) — the shared task branch
    nexus/<wf-slug> IS the history. States = the branch's commits;
    materialize = `git archive <sha>` (tracked files only, read-only on the
    repo, commits are immutable so materialized dirs are cached).
  workspace project — states = the DONE member tasks in completion order;
    state vK = overlay of the first K task workspaces (later stages overwrite
    same-named files); each stage's deliverable.md is collected into
    _deliverables/ instead of colliding at the root.

app_runner runs the materialized dir under the registry key
wf:<workflow-id>:<state-key>, so an old and the new state run side by side on
their own ports — same 30-min TTL, same 3-app cap, same reaper.
"""
import re
import shutil
import subprocess
from pathlib import Path

import worktree as wt

BASE_DIR = Path(__file__).parent
WORKSPACES = BASE_DIR / "workspaces"

# per-task junk that must not leak into an assembled project state
SKIP_DIRS = {"_history", "_project_preview", "attachments", "node_modules",
             ".venv", ".venv-preview", "__pycache__", ".git", ".next",
             "dist", "build", "coverage", ".pytest_cache"}
SKIP_FILES = {"_dispatch.json", "_preview.log", ".preview-apps.json",
              "changes.diff"}
MAX_GIT_STATES = 30


def app_key(wf_id: str, state_key: str) -> str:
    """Registry key for app_runner — distinct per (project, state)."""
    return f"wf:{wf_id}:{state_key}"


def preview_root(wf_id: str) -> Path:
    return WORKSPACES / f"workflow-{wf_id}" / "_project_preview"


def state_dir(wf_id: str, state_key: str) -> Path:
    return preview_root(wf_id) / state_key / "state"


def _live(tasks: list[dict]) -> list[dict]:
    return [t for t in tasks if t.get("status") != "archived"]


def _done_ordered(tasks: list[dict]) -> list[dict]:
    """DONE member tasks with output, oldest completion first."""
    done = [t for t in _live(tasks)
            if t.get("status") == "done" and t.get("workspace_path")]
    return sorted(done, key=lambda t: t.get("completed_at")
                  or t.get("updated_at") or t.get("created_at") or 0)


def _repo_context(tasks: list[dict], wf_id: str) -> dict | None:
    """Repo project? Resolve the shared branch nexus/<wf-slug> (same slug rule
    as hermes_dispatch._repo_slug for workflow tasks)."""
    for t in _live(tasks):
        rp = (t.get("repo_path") or "").strip()
        if not rp:
            continue
        repo = str(Path(rp).expanduser().resolve())
        if not wt.is_repo(repo):
            return None
        branch = f"nexus/{wf_id.replace('wf-', '')}"
        code, _ = wt._run_git(repo, "rev-parse", "--verify", "--quiet", branch)
        if code != 0:
            return None
        return {"repo": repo, "branch": branch, "base": wt.base_branch(repo)}
    return None


def list_states(wf: dict, tasks: list[dict]) -> dict:
    """The project's runnable history, newest first.
    Returns {mode, states:[{key,label,ts}], latest, note?}."""
    rc = _repo_context(tasks, wf["id"])
    if rc:
        # Only the commits THIS project added on top of the baseline — the
        # nexus stages — newest first, so a big repo's unrelated history never
        # buries them. The fork point is appended as the "before" anchor so the
        # operator can still run the project as it was pre-changes.
        base, branch = rc["base"], rc["branch"]
        fork = ""
        if base and base != branch:
            fcode, fout = wt._run_git(rc["repo"], "merge-base", base, branch)
            fork = fout.strip() if fcode == 0 else ""
        # `<fork>..branch` = exactly the project's own commits; with no fork
        # (base==branch edge / detached) fall back to the branch's recent log
        rng = f"{fork}..{branch}" if fork else branch
        code, out = wt._run_git(rc["repo"], "log", "--format=%h|%ct|%s",
                                "-n", str(MAX_GIT_STATES), rng, "--")
        states = []
        if code == 0:
            for ln in out.splitlines():
                sha, ts, subj = (ln.split("|", 2) + ["", ""])[:3]
                if re.fullmatch(r"[0-9a-f]{6,40}", sha or ""):
                    states.append({"key": sha, "label": (subj or "(no message)")[:110],
                                   "ts": float(ts or 0)})
        # baseline anchor (the fork-point state, before this project's changes)
        if fork:
            bcode, bout = wt._run_git(rc["repo"], "log", "--format=%h|%ct|%s",
                                      "-n", "1", fork, "--")
            if bcode == 0 and bout.strip():
                sha, ts, subj = (bout.strip().split("|", 2) + ["", ""])[:3]
                if re.fullmatch(r"[0-9a-f]{6,40}", sha or "") and \
                        not any(s["key"] == sha for s in states):
                    states.append({"key": sha, "ts": float(ts or 0),
                                   "label": f"baseline ({base}) — before this project's changes"})
        return {"mode": "git", "branch": branch, "repo": rc["repo"],
                "states": states,
                "latest": states[0]["key"] if states else None,
                "note": None if states else
                "no commits on the task branch yet — run a stage first"}
    done = _done_ordered(tasks)
    states = [{"key": f"v{i}", "label": f"after '{t.get('title', '')[:80]}'",
               "ts": t.get("completed_at") or t.get("updated_at") or 0,
               "task_id": t["id"]}
              for i, t in enumerate(done, 1)]
    states.reverse()  # newest first, like git
    return {"mode": "workspace", "states": states,
            "latest": states[0]["key"] if states else None,
            "note": None if states else
            "no completed stages with output yet — finish a task first"}


def _overlay_copy(src: Path, dst: Path):
    """Merge-copy one workspace item into the assembled state (later stages
    overwrite earlier files of the same name; junk dirs never copied)."""
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(*SKIP_DIRS))
    else:
        shutil.copy2(src, dst)


def materialize(wf: dict, tasks: list[dict], state_key: str | None) -> dict:
    """Build the requested project state into its disposable dir.
    Returns {dir, mode, key} or {error}. The key MUST come from list_states —
    membership is the injection gate (no arbitrary git revs / paths)."""
    info = list_states(wf, tasks)
    if not info["states"]:
        return {"error": info["note"] or "no project history yet"}
    key = (state_key or "").strip() or info["latest"]
    if not any(s["key"] == key for s in info["states"]):
        return {"error": f"unknown project state '{key}' — reload the state list"}
    dest = state_dir(wf["id"], key)

    if info["mode"] == "git":
        # commits are immutable → an existing materialization is a valid cache
        # (and keeps node_modules from a previous run of the same state)
        if dest.is_dir() and any(dest.iterdir()):
            return {"dir": str(dest), "mode": "git", "key": key}
        dest.mkdir(parents=True, exist_ok=True)
        try:
            ar = subprocess.run(["git", "archive", key], cwd=info["repo"],
                                capture_output=True, timeout=120)
            if ar.returncode != 0:
                return {"error": "git archive failed: "
                        + ar.stderr.decode(errors="replace")[:200]}
            tar = subprocess.run(["tar", "-x", "-C", str(dest)],
                                 input=ar.stdout, capture_output=True, timeout=120)
            if tar.returncode != 0:
                return {"error": "unpack failed: "
                        + tar.stderr.decode(errors="replace")[:200]}
        except Exception as e:
            return {"error": str(e)[:200]}
        return {"dir": str(dest), "mode": "git", "key": key}

    # workspace overlay — assemble the first K stages. Fingerprint the
    # contributing tasks (id + updated_at, which bumps on every retry) so a
    # repeat start reuses the built copy — keeping a prior npm install / .next
    # build — and only rebuilds when a stage actually changed. (The endpoint
    # never rebuilds a RUNNING state, so an npm-installing copy is never wiped.)
    k = int(key[1:])
    done = _done_ordered(tasks)
    if k > len(done):
        return {"error": f"state {key} no longer exists (a stage was retried?)"}
    fp = "|".join(f"{t['id']}:{t.get('updated_at') or t.get('completed_at') or 0}"
                  for t in done[:k])
    fp_file = preview_root(wf["id"]) / key / ".pp-fingerprint"
    if dest.is_dir() and any(dest.iterdir()) and \
            fp_file.is_file() and fp_file.read_text() == fp:
        return {"dir": str(dest), "mode": "workspace", "key": key}
    shutil.rmtree(preview_root(wf["id"]) / key, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    try:
        fp_file.write_text(fp)
    except Exception:
        pass
    deliv = dest / "_deliverables"
    for i, t in enumerate(done[:k], 1):
        ws = Path(t["workspace_path"])
        if not ws.is_dir():
            continue
        for item in sorted(ws.iterdir()):
            if item.name in SKIP_DIRS or item.name in SKIP_FILES \
                    or item.name.startswith("deliverable.v"):
                continue
            try:
                if item.name == "deliverable.md":
                    deliv.mkdir(exist_ok=True)
                    slug = re.sub(r"[^A-Za-z0-9]+", "-",
                                  (t.get("title") or t["id"]))[:60].strip("-")
                    shutil.copy2(item, deliv / f"{i:02d}-{slug or t['id']}.md")
                else:
                    _overlay_copy(item, dest / item.name)
            except Exception:
                continue  # a file/dir name collision across stages — later stage stands
    return {"dir": str(dest), "mode": "workspace", "key": key}


def gc(wf_id: str, keep_keys: set[str]):
    """Delete materialized state dirs not in keep_keys (running or just
    requested) so old npm-installed copies don't pile up on disk."""
    root = preview_root(wf_id)
    if not root.is_dir():
        return
    for d in root.iterdir():
        if d.is_dir() and d.name not in keep_keys:
            shutil.rmtree(d, ignore_errors=True)
