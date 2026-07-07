"""NEXUS Agent OS — Git Worktree Isolation helper.

Each agent can optionally work in its own git worktree + branch so parallel agents
never stomp each other's files (the amux isolation pattern).
"""
import os
import shutil
import subprocess
from pathlib import Path


def _run_git(cwd: str, *args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)


def is_repo(path: str) -> bool:
    if not path or not os.path.isdir(path):
        return False
    code, _ = _run_git(path, "rev-parse", "--is-inside-work-tree")
    return code == 0


def create_worktree(repo_path: str, agent_id: str) -> dict | None:
    """Create an isolated worktree+branch for an agent. Returns info or None."""
    repo = Path(repo_path).resolve()
    if not is_repo(str(repo)):
        return None
    short = agent_id.replace("agent-", "")[:8]
    branch = f"session/{short}"
    wt_root = repo / ".worktrees"
    wt_root.mkdir(exist_ok=True)
    wt_path = wt_root / short
    code, out = _run_git(str(repo), "worktree", "add", "-b", branch, str(wt_path))
    if code != 0:
        # branch may already exist; try without -b
        code, out = _run_git(str(repo), "worktree", "add", str(wt_path), branch)
        if code != 0:
            return None
    return {"worktree_path": str(wt_path), "worktree_branch": branch}


def worktree_has_changes(wt_path: str) -> bool:
    if not wt_path or not os.path.isdir(wt_path):
        return False
    code, out = _run_git(wt_path, "status", "--porcelain")
    return code == 0 and bool(out.strip())


def remove_worktree(repo_path: str, wt_path: str) -> bool:
    """Remove a worktree if clean. Returns True if removed, False if left for review."""
    if not wt_path:
        return True
    if worktree_has_changes(wt_path):
        return False  # leave for human review
    code, _ = _run_git(repo_path or wt_path, "worktree", "remove", "--force", wt_path)
    if code != 0 and os.path.isdir(wt_path):
        shutil.rmtree(wt_path, ignore_errors=True)
    return True


# ── Repo-native tasks (v3.5): worktree-per-pipeline + diff deliverables ──

def base_branch(repo_path: str) -> str:
    """The branch the operator's main checkout is on — the diff baseline."""
    code, out = _run_git(repo_path, "symbolic-ref", "--short", "HEAD")
    return out.strip() if code == 0 and out.strip() else "main"


def ensure_task_worktree(repo_path: str, slug: str) -> dict | None:
    """Idempotent worktree + branch `nexus/<slug>` for a task/pipeline.
    Tasks of one project share a slug (= one branch), so the pipeline's
    stages (implement -> review -> fix -> verify) see each other's work,
    while different pipelines on the same repo stay isolated. The operator's
    main checkout is never touched."""
    repo = Path(repo_path).resolve()
    if not is_repo(str(repo)):
        return None
    branch = f"nexus/{slug}"
    wt_path = repo / ".worktrees" / f"nexus-{slug}"
    if wt_path.is_dir() and is_repo(str(wt_path)):
        return {"worktree_path": str(wt_path), "worktree_branch": branch,
                "base_branch": base_branch(str(repo))}
    base = base_branch(str(repo))
    (repo / ".worktrees").mkdir(exist_ok=True)
    # Self-ignoring dir: keeps the client's main checkout clean without
    # touching their .gitignore.
    gi = repo / ".worktrees" / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n")
    code, out = _run_git(str(repo), "worktree", "add", "-b", branch,
                         str(wt_path), base)
    if code != 0:  # branch exists from an earlier run — reattach
        code, out = _run_git(str(repo), "worktree", "add", str(wt_path), branch)
        if code != 0:
            return None
    return {"worktree_path": str(wt_path), "worktree_branch": branch,
            "base_branch": base}


# Build/runtime junk that must never pollute a task branch or its review diff
# (the E2E probe's snapshot once committed test-run __pycache__).
_JUNK_PATHSPECS = tuple(
    f":(exclude){p}" for p in (
        "__pycache__", "*.pyc", "node_modules", ".venv", "venv", "dist",
        "build", ".pytest_cache", "*.egg-info", ".next", "coverage"))


def snapshot_commit(wt_path: str, message: str) -> bool:
    """Safety net: commit anything the agent left uncommitted, so the diff
    capture never loses work. No-op on a clean tree; never adds junk."""
    if not worktree_has_changes(wt_path):
        return False
    _run_git(wt_path, "add", "-A", "--", ".", *_JUNK_PATHSPECS)
    # anything staged?
    code, staged = _run_git(wt_path, "diff", "--cached", "--name-only")
    if code != 0 or not staged.strip():
        return False
    code, _ = _run_git(wt_path, "-c", "user.name=nexus", "-c",
                       "user.email=nexus@local", "commit", "-m", message)
    return code == 0


def capture_diff(wt_path: str, base: str) -> str:
    """The pipeline's real deliverable: everything the branch changed vs the
    baseline (three-dot = since the merge-base, immune to base moving on).
    Junk paths are excluded so reviews see only real changes."""
    code, out = _run_git(wt_path, "diff", f"{base}...HEAD", "--",
                         ".", *_JUNK_PATHSPECS)
    if code != 0:
        return ""
    code2, stat = _run_git(wt_path, "diff", "--stat", f"{base}...HEAD", "--",
                           ".", *_JUNK_PATHSPECS)
    return (stat + "\n\n" + out) if code2 == 0 and stat else out
