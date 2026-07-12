"""NEXUS Agent OS — Business-Brain feedback ledgers (WINS.md / LESSONS.md).

Single owner of the two feedback files: path resolution (honors the
onboarding.root redirect like every other knowledge reader), template
bootstrap, locked atomic writes, entry parsing, and the framing excerpt that
closes the loop — recent domain-matching entries ride into every dispatch so
logged wins/lessons actually shape future work (win-lesson-logging SKILL.md
is the canonical spec of the entry format; keep it byte-compatible).

All functions are plain sync — async callers run them in a threadpool
(the write endpoint is a sync `def` route for exactly that reason).
"""
import hashlib
import os
import re
import shutil
import tempfile
import threading
import datetime as _dt
from pathlib import Path

import auth
import database as db
from onboarding import knowledge_root

MARKER = "<!-- newest first -->"
FILES = {"win": "WINS.md", "lesson": "LESSONS.md"}
# In-process lock is enough: the server is single-process and worker lanes
# never write these files. A Hermes agent editing the file concurrently can
# still race the read-modify-write window — accepted (rare, human-triggered);
# upgrade path if it ever matters: filelock (in the venv, not requirements.txt).
_LOCK = threading.Lock()
_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "setup" / "knowledge" / "feedback"
_FALLBACK = {
    "win": "# WINS — real-world results worth learning from\n\n---\n\n" + MARKER + "\n",
    "lesson": "# LESSONS — what went wrong + the correction\n\n---\n\n" + MARKER + "\n",
}
_TASK_ID_RE = re.compile(r"\btask-[0-9a-fA-F]{6,12}\b")
_HEADING_RE = re.compile(r"^###\s+(\d{4}-\d{2}-\d{2})\s*(?:—|–|--|-)\s*(.+?)\s*$")
_BULLET_RE = re.compile(r"^-\s+([^:]+):\s?(.*)$")

_entries_cache: dict[str, tuple[float, list]] = {}


def feedback_path(kind: str, user_id: str | None = None) -> str:
    """Item 7 (per-user learning): the owner's ledgers stay canonical
    (~/knowledge/feedback/ — they double as the shared 'General' bucket, zero
    migration); every other user gets an overlay ledger under
    users/<uid>/feedback/ — same layout as onboarding.target_dir."""
    if user_id and user_id != auth.DEFAULT_USER_ID:
        return os.path.join(knowledge_root(), "users", user_id, "feedback", FILES[kind])
    return os.path.join(knowledge_root(), "feedback", FILES[kind])


def ensure_file(kind: str, user_id: str | None = None) -> str:
    """The ledger must exist before an insert; seed it from the repo template
    (or a minimal embedded skeleton) instead of 500ing on a fresh root."""
    target = feedback_path(kind, user_id)
    if not os.path.isfile(target):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tpl = _TEMPLATE_DIR / FILES[kind]
        if tpl.is_file():
            shutil.copyfile(tpl, target)
        else:
            with open(target, "w") as f:
                f.write(_FALLBACK[kind])
    return target


def _one_line(s, cap: int = 1000) -> str:
    """Textarea input must not break the one-bullet-per-field template."""
    s = re.sub(r"\s*\n+\s*", "; ", str(s or "").strip())
    return re.sub(r"[ \t]+", " ", s)[:cap]


def compose_entry(kind: str, task: dict, f: dict) -> str:
    today = _dt.date.today().isoformat()
    headline = f.get("headline") or task.get("title") or "untitled"
    domain = task.get("domain") or "—"
    artifact = os.path.join(task.get("workspace_path") or "?", "deliverable.md")
    if kind == "win":
        promoted = f.get("promoted_to")
        promote_line = (f"yes (promoted {today} → {promoted})" if promoted
                        else "no (review first)")
        return (f"### {today} — {headline}\n"
                f"- Domain: {domain}\n"
                f"- Artifact: {artifact} (Nexus task {task['id']})\n"
                f"- Result: {f['numbers']}\n"
                f"- Why we think it worked: {f['note']}\n"
                f"- Promote to examples/? {promote_line}\n")
    applied = f.get("applied_where") or f"Nexus task {task['id']} ({artifact})"
    return (f"### {today} — {headline}\n"
            f"- Domain: {domain}\n"
            f"- What we expected vs what happened: {f['note']}\n"
            f"- Root cause (be honest): {f.get('root_cause') or 'see note'}\n"
            f"- Correction: {f['correction']}\n"
            f"- Applied where: {applied}\n")


def insert_entry(kind: str, entry: str, user_id: str | None = None) -> str:
    """Newest-first insert after the marker; atomic replace so a crash or a
    concurrent log can't tear the file."""
    with _LOCK:
        target = ensure_file(kind, user_id)
        with open(target) as fh:
            text = fh.read()
        idx = text.find(MARKER)
        if idx == -1:
            text += f"\n{entry}\n"
        else:
            at = idx + len(MARKER)
            text = text[:at] + f"\n\n{entry}" + text[at:]
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, target)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    return target


def promote_deliverable(task: dict, headline: str, numbers: str = "",
                        by: str = "") -> str:
    """Copy the winning deliverable into domains/<domain>/examples/ — the
    directory golden_exemplars + dispatch framing already treat as the
    quality bar, so a promoted win immediately shapes future work."""
    domain = (task.get("domain") or "").strip()
    if not re.match(r"^[a-z0-9-]+$", domain) or domain == "general":
        raise ValueError("task needs a real domain to promote into")
    src = os.path.join(task.get("workspace_path") or "", "deliverable.md")
    if not os.path.isfile(src):
        raise ValueError("no deliverable.md to promote")
    dest_dir = os.path.join(knowledge_root(), "domains", domain, "examples")
    os.makedirs(dest_dir, exist_ok=True)
    today = _dt.date.today().isoformat()
    slug = re.sub(r"[^a-z0-9]+", "-", (headline or "win").lower()).strip("-")[:40] or "win"
    dest = os.path.join(dest_dir, f"{today}-{task['id']}-{slug}.md")
    with open(src) as fh:
        content = fh.read()
    prov = (f"<!-- promoted from Nexus task {task['id']} on {today}"
            + (f" by {_one_line(by, 60)}" if by else "")
            + (f"; result: {_one_line(numbers, 200)}" if numbers else "") + " -->\n\n")
    with open(dest, "w") as fh:
        fh.write(prov + content)
    return dest


def parse_entries(text: str) -> list[dict]:
    """Tolerant parser for hand- and agent-edited ledgers. Only the region
    after the marker is real entries (the `## Template` fenced example stays
    out); unknown bullet labels are preserved; malformed blocks are skipped."""
    idx = text.find(MARKER)
    if idx != -1:
        text = text[idx + len(MARKER):]
    else:
        text = re.sub(r"```.*?```", "", text, flags=re.S)
    entries: list[dict] = []
    cur = None
    cont = False  # a blank line ends a multi-line field value
    for line in text.splitlines():
        hm = _HEADING_RE.match(line)
        if hm:
            cur = {"date": hm.group(1), "headline": hm.group(2), "fields": [], "raw": [line]}
            entries.append(cur)
            cont = False
            continue
        if cur is None:
            continue
        cur["raw"].append(line)
        bm = _BULLET_RE.match(line)
        if bm:
            cur["fields"].append([bm.group(1).strip(), bm.group(2).strip()])
            cont = True
        elif not line.strip():
            cont = False
        elif cont and cur["fields"]:
            cur["fields"][-1][1] = (cur["fields"][-1][1] + " " + line.strip()).strip()
    for e in entries:
        e["raw"] = "\n".join(e["raw"]).strip()
        dom = next((v for k, v in e["fields"] if k.lower() == "domain"), "")
        dom = (dom or "").strip().lower()
        e["domain"] = dom if dom and dom not in ("—", "-", "?") else None
        m = _TASK_ID_RE.search(e["raw"])
        e["task_id"] = m.group(0) if m else None
        # Item 7: stable identity for cross-user adopt/dedupe + provenance.
        e["key"] = hashlib.sha1(e["raw"].encode()).hexdigest()[:12]
        adopted = next((v for k, v in e["fields"] if k.lower().startswith("adopted from")), "")
        e["adopted_from"] = adopted.strip() or None
        origin = next((v for k, v in e["fields"] if k.lower() == "origin"), "")
        e["origin"] = origin.strip() or None
    return entries


def load_entries(kind: str, user_id: str | None = None) -> list[dict]:
    """mtime-cached parse (edits in ~/knowledge apply live, like jarvis_brain).
    Never raises — a missing/broken ledger just means fewer entries."""
    path = feedback_path(kind, user_id)
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return []
    hit = _entries_cache.get(path)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        with open(path) as fh:
            entries = parse_entries(fh.read())
    except Exception:
        entries = []
    _entries_cache[path] = (mt, entries)
    return entries


def list_all_entries(kind: str) -> list[dict]:
    """Item 7: every user's entries for the browse-and-adopt UI. Canonical
    ledger entries are tagged general=True (the owner's house ledger, read by
    everyone); overlay entries carry their author's uid. Bounded: one dir
    listing + the same mtime-cached parses as load_entries."""
    out = []
    for e in load_entries(kind):
        out.append({**e, "author_id": auth.DEFAULT_USER_ID, "general": True})
    users_dir = os.path.join(knowledge_root(), "users")
    try:
        uids = sorted(os.listdir(users_dir))
    except OSError:
        uids = []
    for uid in uids:
        if not os.path.isfile(os.path.join(users_dir, uid, "feedback", FILES[kind])):
            continue
        for e in load_entries(kind, uid):
            out.append({**e, "author_id": uid, "general": False})
    return out


def adopt_entry(kind: str, entry: dict, adopter_uid: str,
                author_name: str, author_id: str) -> str:
    """Item 7: copy another user's entry into MY ledger with provenance
    bullets. The physical copy keeps dispatch_block trivial (own file +
    canonical, nothing else) and survives the tolerant parser. Dedupe by the
    Origin key — adopting twice is a no-op error."""
    for mine in load_entries(kind, adopter_uid):
        if mine.get("origin") == entry["key"] or mine["key"] == entry["key"]:
            raise ValueError("already in your ledger")
    today = _dt.date.today().isoformat()
    copy = (entry["raw"].rstrip() + "\n"
            f"- Adopted from: {author_name} ({author_id}) on {today}\n"
            f"- Origin: {entry['key']}\n")
    return insert_entry(kind, copy, adopter_uid)


def _field(entry: dict, prefix: str) -> str:
    p = prefix.lower()
    return next((v for k, v in entry["fields"] if k.lower().startswith(p)), "")


def _merged_entries(kind: str, dom: str, user_id: str | None) -> list[dict]:
    """Own entries first (incl. adopted copies — they live in the own file),
    then the canonical/General ledger, deduped by key/origin. For the owner
    (or no user) this is exactly the pre-item-7 canonical list."""
    own = ([e for e in load_entries(kind, user_id) if e["domain"] == dom]
           if user_id and user_id != auth.DEFAULT_USER_ID else [])
    seen = {e["key"] for e in own} | {e["origin"] for e in own if e.get("origin")}
    general = [e for e in load_entries(kind) if e["domain"] == dom
               and e["key"] not in seen]
    return own + general


def dispatch_block(domain: str, user_id: str | None = None) -> str:
    """The loop-closer: a compact excerpt of recent domain-matching wins and
    lessons for the dispatch/JARVIS framing. Item 7: entries are per user —
    the task owner's own ledger (plus anything they adopted) merges ahead of
    the shared General ledger. Size-capped; kill switch
    feedback.framing_enabled."""
    dom = (domain or "").strip().lower()
    if not dom or dom == "general":
        return ""
    try:
        if db.get_setting("feedback.framing_enabled", "1") != "1":
            return ""
        max_n = max(0, int(db.get_setting("feedback.framing_max_entries", "2") or 2))
        max_chars = max(200, int(db.get_setting("feedback.framing_max_chars", "1200") or 1200))
    except Exception:
        max_n, max_chars = 2, 1200
    if not max_n:
        return ""
    lines = []
    for e in _merged_entries("win", dom, user_id)[:max_n]:
        result = _field(e, "result")
        why = _field(e, "why")
        lines.append(f"- [WIN {e['date']}] {e['headline']} — Result: {result}"
                     + (f" — Why: {why}" if why else ""))
    lessons = [l for l in _merged_entries("lesson", dom, user_id)
               if not _field(l, "correction").lower().startswith("to be decided")]
    for e in lessons[:max_n]:
        lines.append(f"- [LESSON {e['date']}] {e['headline']} — "
                     f"Correction: {_field(e, 'correction')}")
    if not lines:
        return ""
    lines = [ln[:240] for ln in lines]
    own_path_note = (f"{feedback_path('win', user_id)} + {feedback_path('lesson', user_id)}"
                     + (f" (yours) and {feedback_path('win')} + {feedback_path('lesson')} (shared)"
                        if user_id and user_id != auth.DEFAULT_USER_ID else ""))
    header = (f"FEEDBACK LEDGER — real-world results in the '{dom}' domain (newest "
              "first). Imitate what measurably WON; apply every LESSON's correction. "
              f"Full ledgers (read with your file tools for more): {own_path_note}")
    block = "\n".join([header] + lines)
    while len(block) > max_chars and lines:
        lines.pop()
        block = "\n".join([header] + lines)
    return block if lines else ""
