"""NEXUS Agent OS — result review engine (the PR-review experience for
every output type, not just code).

Sources of truth per task type:
- Repo-native tasks: the captured branch diff (changes.diff) — real git.
- Workspace tasks: version snapshots. Every retry/loop round snapshots the
  workspace to _history/v<N>/ first, so "current vs previous round" is always
  comparable — text files line-diff, PDFs diff by extracted text, images and
  other binaries compare metadata side-by-side.
"""
from __future__ import annotations

import difflib
import os
import re
import shutil
from pathlib import Path

TEXT_EXTS = {".md", ".txt", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".html",
             ".css", ".csv", ".yml", ".yaml", ".toml", ".sh", ".sql", ".xml",
             ".svg", ".env.example", ".mjs", ".cjs", ".diff", ".patch"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
SKIP_DIRS = {"_history", "attachments", "node_modules", ".venv", ".venv-preview",
             "__pycache__", ".git", ".next", "dist", "build", "coverage"}
SKIP_FILES = {"_dispatch.json", "_preview.log", ".preview-apps.json"}
MAX_DIFF_BYTES = 400_000
MAX_HUNK_LINES = 4000


# ── workspace snapshots (called on retry — each round = one version) ──

def snapshot_workspace(ws: str) -> str | None:
    """Copy the workspace's current output files to _history/v<N>/."""
    root = Path(ws)
    if not root.is_dir():
        return None
    hist = root / "_history"
    hist.mkdir(exist_ok=True)
    n = 1 + len([d for d in hist.iterdir() if d.is_dir() and re.match(r"^v\d+$", d.name)])
    dst = hist / f"v{n}"
    copied = 0
    for item in root.iterdir():
        if item.name in SKIP_DIRS or item.name in SKIP_FILES or item.name.startswith("deliverable.v"):
            continue
        try:
            if item.is_dir():
                shutil.copytree(item, dst / item.name,
                                ignore=shutil.ignore_patterns(*SKIP_DIRS))
            else:
                dst.mkdir(exist_ok=True)
                shutil.copy2(item, dst / item.name)
            copied += 1
        except Exception:
            continue
    return str(dst) if copied else None


def list_versions(ws: str) -> list[str]:
    hist = Path(ws) / "_history"
    if not hist.is_dir():
        return []
    return sorted([d.name for d in hist.iterdir()
                   if d.is_dir() and re.match(r"^v\d+$", d.name)],
                  key=lambda s: int(s[1:]))


# ── unified diff parsing (git diff text AND difflib output) ──

def parse_unified(text: str) -> list[dict]:
    """Unified diff → [{path, status, additions, deletions, hunks}]."""
    files: list[dict] = []
    cur: dict | None = None
    hunk: dict | None = None
    for raw in (text or "").splitlines():
        if raw.startswith("diff --git "):
            m = re.match(r'diff --git a/(.*?) b/(.*)$', raw)
            cur = {"path": (m.group(2) if m else raw[11:]).strip(),
                   "status": "modified", "additions": 0, "deletions": 0,
                   "hunks": [], "binary": False}
            files.append(cur)
            hunk = None
        elif raw.startswith("--- ") or raw.startswith("+++ "):
            if cur is not None and raw.startswith("--- /dev/null"):
                cur["status"] = "added"
            if cur is not None and raw.startswith("+++ /dev/null"):
                cur["status"] = "deleted"
        elif raw.startswith("new file"):
            if cur is not None:
                cur["status"] = "added"
        elif raw.startswith("deleted file"):
            if cur is not None:
                cur["status"] = "deleted"
        elif raw.startswith("Binary files") or raw.startswith("GIT binary patch"):
            if cur is not None:
                cur["binary"] = True
        elif raw.startswith("@@"):
            if cur is None:  # difflib output without a diff --git header
                cur = {"path": "", "status": "modified", "additions": 0,
                       "deletions": 0, "hunks": [], "binary": False}
                files.append(cur)
            hunk = {"header": raw[:120], "lines": []}
            cur["hunks"].append(hunk)
        elif hunk is not None and cur is not None:
            if sum(len(h["lines"]) for h in cur["hunks"]) > MAX_HUNK_LINES:
                continue
            if raw.startswith("+"):
                cur["additions"] += 1
                hunk["lines"].append({"t": "+", "s": raw[1:][:500]})
            elif raw.startswith("-"):
                cur["deletions"] += 1
                hunk["lines"].append({"t": "-", "s": raw[1:][:500]})
            elif raw.startswith(" ") or raw == "":
                hunk["lines"].append({"t": " ", "s": raw[1:][:500]})
    return files


def _difflib_files(old_text: str, new_text: str, path: str) -> dict:
    diff = "\n".join(difflib.unified_diff(
        (old_text or "").splitlines(), (new_text or "").splitlines(),
        lineterm="", n=3))
    parsed = parse_unified(diff)
    f = parsed[0] if parsed else {"path": path, "status": "modified",
                                  "additions": 0, "deletions": 0, "hunks": [],
                                  "binary": False}
    f["path"] = path
    return f


def _pdf_text(p: Path) -> str:
    try:
        from pypdf import PdfReader
        r = PdfReader(str(p))
        return "\n".join((page.extract_text() or "") for page in r.pages)
    except Exception as e:
        return f"(pdf text extraction failed: {e})"


def _is_texty(p: Path) -> bool:
    if p.suffix.lower() in TEXT_EXTS:
        return True
    try:
        with open(p, "rb") as f:
            chunk = f.read(2048)
        chunk.decode("utf-8")
        return b"\x00" not in chunk
    except Exception:
        return False


def _walk_files(root: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn in SKIP_FILES or fn.startswith("deliverable.v"):
                continue
            p = Path(dirpath) / fn
            out[str(p.relative_to(root))] = p
    return out


def compare_dirs(old_root: str | None, new_root: str, url_base: str) -> list[dict]:
    """Per-file comparison between two directory states (old may be None =
    everything is new)."""
    new_files = _walk_files(Path(new_root))
    old_files = _walk_files(Path(old_root)) if old_root else {}
    out: list[dict] = []
    for rel in sorted(set(new_files) | set(old_files)):
        np, op = new_files.get(rel), old_files.get(rel)
        ext = Path(rel).suffix.lower()
        entry: dict = {"path": rel, "additions": 0, "deletions": 0,
                       "hunks": [], "binary": False}
        if np and not op:
            entry["status"] = "added"
        elif op and not np:
            entry["status"] = "deleted"
        else:
            try:
                if op.stat().st_size == np.stat().st_size and \
                        op.read_bytes() == np.read_bytes():
                    continue  # unchanged — not part of the review
            except Exception:
                pass
            entry["status"] = "modified"

        if ext == ".pdf":
            entry["kind"] = "pdf"
            old_t = _pdf_text(op) if op else ""
            new_t = _pdf_text(np) if np else ""
            f = _difflib_files(old_t, new_t, rel)
            entry.update(hunks=f["hunks"], additions=f["additions"],
                         deletions=f["deletions"])
            entry["note"] = "compared by extracted text"
        elif ext in IMAGE_EXTS:
            entry["kind"] = "image"
            entry["binary"] = True
            if op:
                entry["old_size"] = op.stat().st_size
            if np:
                entry["new_url"] = f"{url_base}/{rel}"
                entry["new_size"] = np.stat().st_size
        elif np and np.stat().st_size <= MAX_DIFF_BYTES and \
                (_is_texty(np) or (op and _is_texty(op))):
            entry["kind"] = "text"
            old_t = op.read_text(errors="replace") if op else ""
            new_t = np.read_text(errors="replace") if np else ""
            f = _difflib_files(old_t, new_t, rel)
            entry.update(hunks=f["hunks"], additions=f["additions"],
                         deletions=f["deletions"])
        else:
            entry["kind"] = "binary"
            entry["binary"] = True
            if op:
                entry["old_size"] = op.stat().st_size
            if np:
                entry["new_size"] = np.stat().st_size
        out.append(entry)
    return out


def build_task_review(task: dict) -> dict:
    """The task's change review: git diff for repo tasks, version comparison
    for workspace tasks."""
    ws = task.get("workspace_path") or ""
    tid = task.get("id")
    if task.get("repo_path"):
        diff_file = Path(ws) / "changes.diff"
        if diff_file.is_file():
            files = parse_unified(diff_file.read_text(errors="replace"))
            return {"mode": "git", "source": "branch diff vs base",
                    "files": files,
                    "additions": sum(f["additions"] for f in files),
                    "deletions": sum(f["deletions"] for f in files)}
        return {"mode": "git", "files": [], "additions": 0, "deletions": 0,
                "note": "no changes.diff captured (task not finished yet?)"}
    versions = list_versions(ws)
    prev = str(Path(ws) / "_history" / versions[-1]) if versions else None
    files = compare_dirs(prev, ws, f"/api/tasks/{tid}/files")
    return {"mode": "workspace",
            "source": f"current output vs {versions[-1] if versions else 'nothing (first version — everything is new)'}",
            "versions": versions,
            "files": files,
            "additions": sum(f["additions"] for f in files),
            "deletions": sum(f["deletions"] for f in files)}
