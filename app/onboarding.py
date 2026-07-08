"""NEXUS Agent OS — in-app Business-Brain onboarding (docs/SPEC-ONBOARDING.md).

Source of truth = pristine templates (~/knowledge/templates/*.template.md)
+ per-user answers (onboarding_answers). Rendering writes the caller's
target: u_owner -> the canonical ~/knowledge files (what evals, the judge
and specialists read); every other user -> ~/knowledge/users/<uid>/ overlay,
which hermes_dispatch resolves per task owner.

The hand-holding lives here too: every section carries an impact explanation
(what agents do with these lines, what stays generic while they're blank) so
the wizard can genuinely walk a new user through the system.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import database as db
import auth

FILES = [("context", "BUSINESS-CONTEXT.md"), ("style", "STYLE-VOICE.md")]
# multi-line aware: one STYLE-VOICE slot spans two physical lines
SLOT_RE = re.compile(r"\{\{FILL(?::\s*(.*?))?\}\}", re.DOTALL)
NA_TEXT = "n/a — marked not applicable during onboarding"


def knowledge_root() -> str:
    """Production: ~/knowledge. settings onboarding.root redirects for gates
    (same pattern as evals.corpus_root — default off, restored by the gate)."""
    return db.get_setting("onboarding.root", "") or os.path.expanduser("~/knowledge")


def template_path(fkey: str) -> str:
    name = dict(FILES)[fkey]
    return os.path.join(knowledge_root(), "templates",
                        name.replace(".md", ".template.md"))


def target_dir(user_id: str) -> str:
    """u_owner owns the canonical files (the home dir IS the operator's —
    same ownership model as projects); everyone else gets a personal overlay."""
    root = knowledge_root()
    if user_id == auth.DEFAULT_USER_ID:
        return root
    return os.path.join(root, "users", user_id)


def target_path(user_id: str, fkey: str) -> str:
    return os.path.join(target_dir(user_id), dict(FILES)[fkey])


# ── the hand-holding layer: what each part of the Business Brain DOES ──

FILE_INTRO = {
    "context": (
        "BUSINESS-CONTEXT.md is the FIRST file every agent reads before any business "
        "deliverable — marketing, content, brand, e-commerce, consulting, SaaS strategy, "
        "music. While a line is blank, agents must work from clearly-marked generic "
        "assumptions; once filled, every output is grounded on YOUR reality. Filling this "
        "in is the highest-leverage quarter hour in the whole system."),
    "style": (
        "STYLE-VOICE.md governs how everything you publish SOUNDS. Agents apply it to "
        "every outward-facing text (site, listings, emails, posts, proposals) and the "
        "frontier judge scores deliverables against this voice. The defaults are already "
        "strong — your answers localize and brand them."),
}

SECTION_EXPLAIN = {
    ("context", "The team"): (
        "Who you are and how much time you really have. The task wizard sizes plans to "
        "your capacity, work is split along the roles you name, and languages/markets "
        "decide the default output language — with 'German + English, DACH first' a shop "
        "product page comes back in German without you asking."),
    ("context", "Venture 1 — Our SaaS"): (
        "Everything an agent writes about your SaaS — landing copy, feature posts, "
        "onboarding emails — is grounded on these lines. The ICP decides WHO the copy "
        "speaks to; the differentiation line becomes the recurring argument. Blank means "
        "agents must invent a placeholder product (marked as assumption, but generic)."),
    ("context", "Venture 2 — Client work / consulting"): (
        "Proposals, outreach and pricing pages quote the services, productized offer and "
        "ideal client you define here. A real offer name, scope and price makes agent "
        "proposals sendable instead of template-ish."),
    ("context", "Venture 3 — E-commerce"): (
        "Product descriptions, ads and shop campaigns pull platform, products, margins "
        "and best sellers from these lines. Real margin ranges keep discount and ad-budget "
        "suggestions honest instead of hopeful."),
    ("context", "Venture 4 — Music / DJ"): (
        "Release plans, artist bios, gig outreach and social posts use this. Genre/scene "
        "makes the language scene-native; your goals steer what agents optimize for — "
        "releases, gigs or audience growth."),
    ("context", "Audience & channels (across ventures)"): (
        "Marketing plans allocate effort to the channels you rank here, and growth math "
        "anchors on your REAL numbers (list size, follower counts, traffic) instead of "
        "invented ones."),
    ("context", "Constraints & tools"): (
        "Hard guardrails. Budget ceilings cap what any plan may propose; constraints like "
        "'no paid ads yet' veto whole tactic families; the stack list keeps every "
        "recommendation inside tools you already pay for."),
    ("context", "This quarter's goals (update every quarter)"): (
        "The planning wizard and the frontier judge bias toward these goals — a "
        "deliverable that serves no quarterly goal gets questioned. Goals with a number "
        "and a date make agent output measurable. Revisit every quarter."),
    ("style", "Voice defaults (until onboarding refines them)"): (
        "The language line sets the default output language per audience — the single "
        "most common thing people otherwise fix in review. The trait table above it "
        "already applies to every text; your answer localizes it."),
    ("style", "Formatting conventions"): (
        "The emoji policy is enforced per channel in every deliverable — emails, product "
        "pages and social posts each follow what you set here."),
    ("style", "Per-brand overrides"): (
        "Per-brand voice BEATS the defaults. Name your brands and how each deviates — "
        "e.g. the shop warmer and in German, the artist lowercase and minimal. Agents "
        "apply the matching override whenever they write for that brand."),
}

GENERIC_EXPLAIN = ("These lines are read verbatim by agents before business work — "
                   "concrete beats complete; a short true answer is worth more than a "
                   "polished vague one.")

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.M)
_LABEL_STRIP = re.compile(r"[*_#>`\[\]|]|^\s*-\s*|\d+\.\s*")


def _read_template(fkey: str) -> str:
    with open(template_path(fkey), encoding="utf-8") as f:
        return f.read()


def _real_slots(text: str) -> list:
    """Slot matches EXCLUDING documentation mentions — the templates' intro
    text shows the literal `{{FILL: ...}}` syntax in backticks; that is not a
    question. Parse, render and status all share this predicate so positional
    slot ids always line up."""
    return [m for m in SLOT_RE.finditer(text)
            if not (m.start() > 0 and text[m.start() - 1] == "`")]


def parse_template(fkey: str) -> list[dict]:
    """All {{FILL}} slots of one template, in file order, with section + label
    + hint. slot_id is positional (`context:07`) — stable because the template
    is the frozen source of truth."""
    text = _read_template(fkey)
    headings = [(m.start(), m.group(2).strip()) for m in _HEADING_RE.finditer(text)
                if "{{FILL" not in m.group(2)]  # brand-name headings ARE slots, not sections
    slots = []
    for i, m in enumerate(_real_slots(text)):
        section = ""
        for hpos, htitle in headings:
            if hpos < m.start():
                section = htitle
            else:
                break
        line_start = text.rfind("\n", 0, m.start()) + 1
        label = _LABEL_STRIP.sub("", text[line_start:m.start()]).strip().rstrip(":").strip()
        hint = re.sub(r"\s+", " ", (m.group(1) or "")).strip()
        slots.append({
            "slot_id": f"{fkey}:{i:02d}",
            "section": section,
            "label": label or (hint[:70] if hint else "Fill in"),
            "hint": hint,
        })
    return slots


def schema() -> list[dict]:
    """Wizard schema: both files in order, grouped by section, each section
    carrying its impact explanation."""
    out = []
    for fkey, fname in FILES:
        cur = None
        for s in parse_template(fkey):
            if cur is None or cur["title"] != s["section"]:
                cur = {"file": fkey, "file_name": fname,
                       "file_intro": FILE_INTRO[fkey],
                       "title": s["section"],
                       "explain": SECTION_EXPLAIN.get((fkey, s["section"]), GENERIC_EXPLAIN),
                       "questions": []}
                out.append(cur)
            cur["questions"].append({k: s[k] for k in ("slot_id", "label", "hint")})
    return out


def all_slot_ids() -> set[str]:
    return {q["slot_id"] for sec in schema() for q in sec["questions"]}


def render(fkey: str, answers: dict) -> tuple[str, int, int]:
    """Template + answers -> file text. Returns (text, replaced, remaining).
    Unanswered slots stay {{FILL}} so the file keeps inviting completion."""
    text = _read_template(fkey)
    out, last = [], 0
    replaced = remaining = 0
    for i, m in enumerate(_real_slots(text)):
        out.append(text[last:m.start()])
        a = answers.get(f"{fkey}:{i:02d}")
        if a and a.get("na"):
            out.append(NA_TEXT)
            replaced += 1
        elif a and (a.get("answer") or "").strip():
            out.append(a["answer"].strip())
            replaced += 1
        else:
            out.append(m.group(0))
            remaining += 1
        last = m.end()
    out.append(text[last:])
    return "".join(out), replaced, remaining


def _git(root: str, *args) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True,
                           text=True, timeout=30)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()[-400:]
    except Exception as e:
        return 1, str(e)[:200]


def apply_for(user_id: str, username: str) -> dict:
    """Render + write the caller's Business Brain, git-safe: a dirty knowledge
    repo is snapshot-committed FIRST so hand edits are never lost, then the
    rendered files are committed."""
    root = knowledge_root()
    tdir = target_dir(user_id)
    os.makedirs(tdir, exist_ok=True)
    rows = db.query_all("SELECT * FROM onboarding_answers WHERE user_id=?", (user_id,))
    answers = {r["slot_id"]: {"answer": r["answer"], "na": bool(r["na"])} for r in rows}

    code, out = _git(root, "status", "--porcelain")
    git_ok = code == 0
    if git_ok and out.strip():
        _git(root, "add", "-A")
        _git(root, "-c", "user.name=nexus", "-c", "user.email=nexus@local",
             "commit", "-m", "pre-onboarding snapshot (auto — nothing is lost)")

    written, replaced_total, remaining_total = [], 0, 0
    for fkey, fname in FILES:
        text, replaced, remaining = render(fkey, answers)
        fp = os.path.join(tdir, fname)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(text)
        written.append(fp)
        replaced_total += replaced
        remaining_total += remaining

    committed = False
    if git_ok:
        _git(root, "add", *written)
        code, _ = _git(root, "-c", "user.name=nexus", "-c", "user.email=nexus@local",
                       "commit", "-m",
                       f"onboarding({username}): personalize business context + voice "
                       f"({replaced_total} slots filled)")
        committed = code == 0
    now = time.time()
    db.execute("INSERT OR REPLACE INTO onboarding_state (user_id, applied_at, target_dir) "
               "VALUES (?,?,?)", (user_id, now, tdir))
    db.log_activity("info", "system",
                    f"Onboarding applied for {username}: {replaced_total} slots filled, "
                    f"{remaining_total} still open -> {tdir}")
    return {"written": written, "replaced": replaced_total,
            "remaining": remaining_total, "target_dir": tdir,
            "git_committed": committed, "applied_at": now}


def status_for(user_id: str) -> dict:
    """Per-user unfilled count, keeping the historical response shape
    (files[], total, done, cta). File truth wins when the user's target files
    exist (hand edits count); otherwise template slots minus saved answers."""
    out = {"files": [], "total": 0}
    answered = {r["slot_id"] for r in db.query_all(
        "SELECT slot_id FROM onboarding_answers WHERE user_id=? "
        "AND (na=1 OR TRIM(COALESCE(answer,'')) != '')", (user_id,))}
    for fkey, fname in FILES:
        fp = target_path(user_id, fkey)
        try:
            if os.path.isfile(fp):
                n = len(_real_slots(open(fp, encoding="utf-8").read()))
            else:
                n = sum(1 for s in parse_template(fkey)
                        if s["slot_id"] not in answered)
        except Exception:
            n = 0
        out["files"].append({"file": fname, "unfilled": n})
        out["total"] += n
    out["done"] = out["total"] == 0
    out["cta"] = None if out["done"] else \
        "Fill it in right here — the guided onboarding walks you through every answer."
    return out
