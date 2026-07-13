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
import json
import os
import re
import shutil
from pathlib import Path

TEXT_EXTS = {".md", ".txt", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".html",
             ".css", ".csv", ".yml", ".yaml", ".toml", ".sh", ".sql", ".xml",
             ".svg", ".env.example", ".mjs", ".cjs", ".diff", ".patch"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
SKIP_DIRS = {"_history", "_judge", "attachments", "artifacts", "node_modules",
             ".venv", ".venv-preview",
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
    """Unified diff → [{path, status, additions, deletions, hunks}].
    Every hunk line carries its real file position (`o` = old line no,
    `n` = new line no) so the UI can anchor per-line comments and build
    the side-by-side view."""
    files: list[dict] = []
    cur: dict | None = None
    hunk: dict | None = None
    old_no = new_no = 0
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
            m = re.match(r'@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@', raw)
            old_no = int(m.group(1)) if m else 1
            new_no = int(m.group(2)) if m else 1
        elif hunk is not None and cur is not None:
            if sum(len(h["lines"]) for h in cur["hunks"]) > MAX_HUNK_LINES:
                continue
            if raw.startswith("+"):
                cur["additions"] += 1
                hunk["lines"].append({"t": "+", "s": raw[1:][:500], "n": new_no})
                new_no += 1
            elif raw.startswith("-"):
                cur["deletions"] += 1
                hunk["lines"].append({"t": "-", "s": raw[1:][:500], "o": old_no})
                old_no += 1
            elif raw.startswith(" ") or raw == "":
                hunk["lines"].append({"t": " ", "s": raw[1:][:500],
                                      "o": old_no, "n": new_no})
                old_no += 1
                new_no += 1
    return files


# ── syntax highlighting (Pygments — server-side, no build step) ──
# The `h` field is Pygments-generated HTML whose text content is fully
# escaped by Pygments itself; it is the ONLY server HTML the frontend may
# inject raw. Anything without `h` renders through esc() as before.

def _lexer_for(path: str):
    try:
        from pygments.lexers import get_lexer_for_filename
        return get_lexer_for_filename(path, stripnl=False, ensurenl=False)
    except Exception:
        return None


def highlight_file(f: dict) -> None:
    """Attach `h` (highlighted HTML) to each hunk line of a text-y file entry.
    Each hunk is highlighted per side (old = context+deletions, new =
    context+additions) so multi-line constructs survive within the hunk.
    Any mismatch falls back to plain rendering for that side."""
    if f.get("binary") or f.get("kind") in ("image", "binary", "pdf") or not f.get("hunks"):
        return
    lexer = _lexer_for(f.get("path") or "")
    if lexer is None:
        return
    try:
        from pygments import highlight as _pyg_highlight
        from pygments.formatters import HtmlFormatter
    except Exception:
        return
    fmt = HtmlFormatter(nowrap=True)
    for hunk in f["hunks"]:
        lines = hunk.get("lines") or []
        # new side last so context lines keep the new-side highlight
        for types in ((" ", "-"), (" ", "+")):
            idxs = [i for i, ln in enumerate(lines) if ln["t"] in types]
            if not idxs:
                continue
            try:
                out = _pyg_highlight("\n".join(lines[i]["s"] for i in idxs),
                                     lexer, fmt)
            except Exception:
                continue
            out_lines = out.split("\n")
            while out_lines and out_lines[-1] == "":
                out_lines.pop()
            if len(out_lines) != len(idxs):
                continue
            for i, html in zip(idxs, out_lines):
                lines[i]["h"] = html


def highlight_files(files: list[dict]) -> None:
    total = 0
    for f in files:
        total += sum(len(h.get("lines") or []) for h in (f.get("hunks") or []))
        if total > MAX_HUNK_LINES * 3:  # highlighting is decoration, not worth stalling huge reviews
            return
        highlight_file(f)


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


def repo_rounds(ws: str) -> list[dict]:
    """Per-finalize HEAD records ([{round, head_sha, ts}]) written by
    _capture_repo_result — the round-over-round diff's source of truth."""
    p = Path(ws) / "_history" / "rounds.json"
    try:
        rounds = json.loads(p.read_text()) if p.is_file() else []
        return rounds if isinstance(rounds, list) else []
    except Exception:
        return []


def _report_entry(ws: str) -> dict | None:
    """The deliverable.md report as a review file entry for REPO tasks
    (2026-07-13): the judge/critic anchor findings to deliverable.md, but the
    branch diff never contains it — so 0 of a task's judge comments could
    render (verified live: 44/44 invisible on one task). Rendering the report
    as its own diffed entry (previous _history version vs live) gives those
    anchors a surface; first version = all-added but present."""
    cur = Path(ws) / "deliverable.md"
    if not cur.is_file():
        return None
    versions = list_versions(ws)
    old_t = ""
    if versions:
        oldp = Path(ws) / "_history" / versions[-1] / "deliverable.md"
        if oldp.is_file():
            old_t = oldp.read_text(errors="replace")
    new_t = cur.read_text(errors="replace")
    f = _difflib_files(old_t, new_t, "deliverable.md")
    entry = {"path": "deliverable.md", "kind": "text", "binary": False,
             "status": "modified" if old_t else "added",
             "hunks": f["hunks"], "additions": f["additions"],
             "deletions": f["deletions"],
             "note": "the task report (repo tasks: shown alongside the code diff "
                     "— judge findings anchor here)"}
    return entry if entry["hunks"] else None


def build_task_review(task: dict, pair: str | None = None,
                      from_v: str | None = None, to_v: str | None = None) -> dict:
    """The task's change review: git diff for repo tasks, version comparison
    for workspace tasks.

    2026-07-13 pair selection: repo tasks default to the ROUND-OVER-ROUND diff
    (previous finalize HEAD → current) once ≥2 rounds exist — the old
    branch-vs-base view showed a spec-stage rework as the same all-green new
    files every round ("looks like a complete new file"); it stays one click
    away as pair='base'. Workspace tasks accept ?from_v=vN[&to_v=vM|live]."""
    ws = task.get("workspace_path") or ""
    tid = task.get("id")
    if task.get("repo_path"):
        rounds = repo_rounds(ws)
        pairs = []
        if len(rounds) >= 2:
            pairs.append({"id": "round",
                          "label": f"Round {rounds[-2]['round']} → {rounds[-1]['round']} (latest rework)"})
        pairs.append({"id": "base", "label": "All changes vs base (whole branch)"})
        selected = pair if pair in {p["id"] for p in pairs} else pairs[0]["id"]
        files, src = [], ""
        if selected == "round":
            import worktree as wt
            wt_dir = os.path.join(task["repo_path"], ".worktrees",
                                  "nexus-" + (task.get("workflow_id") or tid or "")
                                  .replace("wf-", "").replace("task-", ""))
            root = wt_dir if os.path.isdir(wt_dir) else task["repo_path"]
            diff = wt.capture_diff_between(root, rounds[-2]["head_sha"],
                                           rounds[-1]["head_sha"])
            files = parse_unified(diff)
            src = (f"round {rounds[-2]['round']} → round {rounds[-1]['round']} "
                   "(what the rework changed)")
            if not files:
                selected = "base"  # SHAs pruned/unreachable → fall back
        if selected == "base":
            diff_file = Path(ws) / "changes.diff"
            if diff_file.is_file():
                files = parse_unified(diff_file.read_text(errors="replace"))
                src = "branch diff vs base"
            else:
                return {"mode": "git", "files": [], "additions": 0, "deletions": 0,
                        "pairs": pairs, "selected": "base",
                        "note": "no changes.diff captured (task not finished yet?)"}
        report = _report_entry(ws)
        if report and not any(f.get("path") == "deliverable.md" for f in files):
            files = [report] + files
        highlight_files(files)
        return {"mode": "git", "source": src, "files": files,
                "pairs": pairs, "selected": selected,
                "rounds": len(rounds),
                "additions": sum(f["additions"] for f in files),
                "deletions": sum(f["deletions"] for f in files)}
    versions = list_versions(ws)
    frm = from_v if from_v in versions else (versions[-1] if versions else None)
    to_dir = ws
    to_label = "current output"
    if to_v and to_v != "live" and to_v in versions:
        to_dir = str(Path(ws) / "_history" / to_v)
        to_label = to_v
    prev = str(Path(ws) / "_history" / frm) if frm else None
    files = compare_dirs(prev, to_dir, f"/api/tasks/{tid}/files")
    highlight_files(files)
    return {"mode": "workspace",
            "source": f"{to_label} vs {frm if frm else 'nothing (first version — everything is new)'}",
            "versions": versions, "selected_from": frm,
            "selected_to": (to_v if to_dir != ws else "live"),
            "files": files,
            "additions": sum(f["additions"] for f in files),
            "deletions": sum(f["deletions"] for f in files)}
