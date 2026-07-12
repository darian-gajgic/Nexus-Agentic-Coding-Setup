"""NEXUS Agent OS — JARVIS Business-Brain integration.

Makes JARVIS domain-aware: it detects which of the nine business domains a
request touches and injects the matching craft knowledge (~/knowledge) into the
per-turn framing, so spoken/written deliverables follow our own playbooks,
rubrics and voice instead of generic-assistant defaults.

Design constraints:
  - VOICE assistant → injections must stay COMPACT. Full playbooks are 200 lines
    each; we inject only the rubric's must-pass gate TITLES + the playbook's task
    headers as a scaffold, and hand Hermes the file PATHS so it can read the full
    craft when a request actually warrants a deliverable.
  - Always-on global brain (business context facts + the AI-slop kill list) is
    tiny and shapes tone every turn. The heavier domain pack rides along only
    when the turn looks like a real make/write/plan request.
  - Pure stdlib. Files are cached by mtime so edits in ~/knowledge apply live
    without a restart. Everything degrades to "" if the knowledge base is absent.
"""
import os
import re
import time

import auth

try:
    import database as db
except Exception:  # pragma: no cover — standalone import
    db = None

try:
    import feedback_log
except Exception:  # pragma: no cover — standalone import
    feedback_log = None

# domain dir → (display label, keyword set for detection). Order = tie-break
# priority (earlier wins when scores tie). Keywords are matched as whole words
# on the lowercased message; multi-word phrases match as substrings.
DOMAINS: list[tuple[str, str, tuple[str, ...]]] = [
    ("software-engineering", "Software engineering", (
        "code", "coding", "bug", "deploy", "api", "endpoint", "function", "refactor",
        "unit test", "repo", "backend", "frontend", "database", "script", "program",
        "software", "compile", "stack trace", "git", "typescript", "python", "react",
        "server", "framework", "algorithm", "regression", "ci", "pull request")),
    ("saas-business", "SaaS", (
        "saas", "mrr", "arr", "churn", "pricing tier", "subscription", "activation",
        "retention", "product-led", "free trial", "plg", "onboarding flow", "paywall",
        "freemium", "cohort", "ltv", "cac", "north star", "feature adoption")),
    ("consulting-bizdev", "Consulting / bizdev", (
        "client", "proposal", "consulting", "retainer", "scope", "sow", "pipeline",
        "lead gen", "discovery call", "productized", "invoice", "contract", "outreach",
        "cold email", "positioning statement", "case study", "engagement", "close the deal")),
    ("research-learning", "Research / learning", (
        "research", "study", "learn", "paper", "literature", "summarize", "synthesize",
        "compare", "evidence", "cite", "sources", "deep dive", "understand", "explain",
        "state of the art", "benchmark", "survey", "whitepaper", "analysis of")),
    ("marketing", "Marketing", (
        "marketing", "campaign", "ad ", "ads", "seo", "landing page", "email sequence",
        "funnel", "conversion rate", "ctr", "utm", "ad copy", "headline", "cta",
        "target audience", "positioning", "lead magnet", "growth", "acquisition")),
    ("content-creation", "Content creation", (
        "content", "blog", "blog post", "article", "video", "video script", "newsletter",
        "thumbnail", "caption", "thread", "youtube", "tiktok", "instagram", "reel",
        "carousel", "hook", "script for", "post about", "content calendar")),
    ("brand", "Brand", (
        "brand", "logo", "identity", "palette", "typography", "brand voice", "tagline",
        "style guide", "naming", "visual identity", "moodboard", "brand guidelines",
        "rebrand", "positioning", "brand story")),
    ("ecommerce", "E-commerce", (
        "shop", "store", "product listing", "sku", "shopify", "amazon", "fulfillment",
        "dropship", "margin", "cart", "checkout", "inventory", "product page",
        "print on demand", "etsy", "bundle", "upsell", "abandoned cart", "shipping")),
    ("music-dj", "Music / DJ", (
        "track", "mix", "master", " dj", "dj set", "bpm", "melodic techno", "release",
        "label", "beatport", "spotify", "soundcloud", "gig", "remix", "stems",
        "arrangement", "sound design", "ableton", "sample", "drop", "playlist")),
]

# Turn LOOKS like a real deliverable/craft request (vs. a command or chit-chat).
# A false positive just adds a bit of rubric context — benign.
_DELIVERABLE_RE = re.compile(
    r"\b(write|draft|create|make|produce|design|build|generate|compose|plan|"
    r"outline|copy|script|proposal|campaign|strategy|rewrite|improve|polish|"
    r"critique|brainstorm|headline|caption|tagline|pitch|storyboard|help me "
    r"(write|make|build|create|design|plan))\b", re.I)

_cache: dict[str, tuple[float, str]] = {}


def knowledge_root() -> str:
    root = ""
    if db is not None:
        try:
            root = db.get_setting("onboarding.root", "") or ""
        except Exception:
            root = ""
    return root or os.path.expanduser("~/knowledge")


def _context_style_paths(uid: str | None) -> tuple[str, str]:
    """SPEC-ONBOARDING R2.3 (parity with hermes_dispatch._knowledge_paths): a
    non-owner user with a completed personal onboarding gets their overlay
    BUSINESS-CONTEXT/STYLE-VOICE; everyone else (and the owner) the canonical
    files. PLAYBOOK/RUBRIC stay shared (craft, not identity)."""
    root = knowledge_root()
    u = (uid or "").strip()
    if u and u != auth.DEFAULT_USER_ID:
        d = os.path.join(root, "users", u)
        ctx = os.path.join(d, "BUSINESS-CONTEXT.md")
        style = os.path.join(d, "STYLE-VOICE.md")
        if os.path.isfile(ctx) and os.path.isfile(style):
            return ctx, style
    return (os.path.join(root, "BUSINESS-CONTEXT.md"),
            os.path.join(root, "STYLE-VOICE.md"))


def _read(path: str) -> str:
    """mtime-cached file read (edits in ~/knowledge apply without a restart)."""
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return ""
    hit = _cache.get(path)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        with open(path, encoding="utf-8") as f:
            txt = f.read()
    except OSError:
        txt = ""
    _cache[path] = (mt, txt)
    return txt


def detect_domain(text: str) -> str | None:
    """Best-matching domain dir name, or None. Whole-word scoring; ties break by
    DOMAINS order."""
    low = f" {text.lower()} "
    best, best_score = None, 0
    for dom, _label, kws in DOMAINS:
        score = 0
        for kw in kws:
            if " " in kw or kw.startswith(" ") or kw.endswith(" "):
                if kw in low:
                    score += 1
            elif re.search(r"\b" + re.escape(kw) + r"\b", low):
                score += 1
        if score > best_score:
            best, best_score = dom, score
    return best if best_score >= 1 else None


def domain_label(dom: str | None) -> str:
    if not dom:
        return ""
    for d, label, _ in DOMAINS:
        if d == dom:
            return label
    return dom


def _business_facts(path: str) -> str:
    """BUSINESS-CONTEXT trimmed to KNOWN facts — drop instruction blockquotes and
    still-{{FILL}} placeholder lines so we inject signal, not a blank template."""
    raw = _read(path)
    if not raw:
        return ""
    out, section = [], None
    for line in raw.splitlines():
        indented_cont = bool(re.match(r"\s+\S", line)) and not line.lstrip().startswith(("-", "*", "#", ">", "|"))
        s = line.strip()
        if s.startswith(">") or not s or s.startswith(("|", "---")):
            continue
        if s.startswith("#"):
            section = re.sub(r"\{\{.*?\}\}", "", s.lstrip("# ").split("—")[0]).strip()
            continue
        if "{{FILL" in s:
            continue
        fact = re.sub(r"[*_`]", "", re.sub(r"\s+", " ", s.lstrip("-* ").strip()))
        if not fact:
            continue
        # merge a wrapped continuation onto the previous fact instead of emitting
        # it as a headerless fragment
        if indented_cont and out:
            out[-1] = (out[-1] + " " + fact).strip()
        else:
            out.append(f"{section}: {fact}" if section else fact)
    return " · ".join(out[:10])


def _kill_list(path: str) -> str:
    """The AI-slop kill list from STYLE-VOICE — the single most useful voice
    guardrail. Returns the backtick-quoted forbidden phrases, condensed."""
    raw = _read(path)
    if not raw:
        return ""
    m = re.search(r"kill list[^\n]*\)\s*\n(.*?)(?:\n#|\Z)", raw, re.I | re.S)
    if not m:
        return ""
    phrases = re.findall(r"`([^`]+)`", m.group(1))
    return ", ".join(p.strip() for p in phrases if p.strip())[:600]


def _gate_titles(rubric_path: str) -> list[str]:
    """Bold titles of the numbered must-pass gates — a compact self-check list."""
    raw = _read(rubric_path)
    if not raw:
        return []
    m = re.search(r"must-pass gates.*?\n(.*?)(?:\n##|\Z)", raw, re.I | re.S)
    body = m.group(1) if m else raw
    titles = []
    for line in body.splitlines():
        gm = re.match(r"\s*\d+\.\s+\*\*(.+?)\.?\*\*", line)
        if gm:
            titles.append(gm.group(1).strip())
    return titles[:12]


def _playbook_tasks(playbook_path: str) -> list[str]:
    """The '### N. Task' headers under the playbook's task section — the menu of
    craft workflows available for deep reading."""
    raw = _read(playbook_path)
    if not raw:
        return []
    out = []
    for line in raw.splitlines():
        hm = re.match(r"###\s+\d+\.\s+(.+)", line.strip())
        if hm:
            out.append(hm.group(1).strip())
    return out[:12]


def domain_pack(dom: str, deep: bool, uid: str | None = None) -> str:
    """Compact craft context for a domain. `deep` (a deliverable-looking turn)
    adds the rubric gate checklist + playbook task menu; otherwise just names the
    resources so JARVIS can offer to go deeper."""
    root = knowledge_root()
    ddir = os.path.join(root, "domains", dom)
    playbook = os.path.join(ddir, "PLAYBOOK.md")
    rubric = os.path.join(ddir, "RUBRIC.md")
    if not os.path.isdir(ddir):
        return ""
    lines = [f"DOMAIN: {domain_label(dom)}. Craft knowledge lives at {ddir}/ "
             f"(PLAYBOOK.md, RUBRIC.md) — read them with your file tools before a "
             f"real deliverable in this domain."]
    if deep:
        tasks = _playbook_tasks(playbook)
        gates = _gate_titles(rubric)
        if tasks:
            lines.append("Playbook workflows: " + "; ".join(tasks) + ".")
        if gates:
            lines.append("Before delivering, self-check against the rubric's "
                         "must-pass gates: " + "; ".join(gates) +
                         ". State any FAIL and fix it. End a deliverable with a "
                         "short **Learn:** line (we are juniors learning the craft).")
        # Feedback loop parity with dispatch: recent domain wins/lessons on
        # deliverable-looking turns only (shallow chat stays lean).
        fb_block = feedback_log.dispatch_block(dom, uid) if feedback_log else ""
        if fb_block:
            lines.append(fb_block)
    return "\n".join(lines)


def brain_framing(text: str, uid: str | None = None) -> tuple[str, str | None]:
    """(framing_block, detected_domain). The block folds into the JARVIS system
    message. uid selects the per-user knowledge overlay (members with a
    completed onboarding get THEIR business context/voice, not the owner's).
    Empty string when the knowledge base is absent."""
    if not os.path.isdir(knowledge_root()):
        return "", None
    parts = []
    ctx_path, style_path = _context_style_paths(uid)
    facts = _business_facts(ctx_path)
    if facts:
        parts.append("BUSINESS CONTEXT (our ventures — treat unknowns as marked "
                     "assumptions, never invent): " + facts)
    kill = _kill_list(style_path)
    if kill:
        parts.append("VOICE: write like one sharp human to another — direct, "
                     "concrete, honest, active voice, one idea per line. NEVER use "
                     "these AI-slop phrases: " + kill + ".")
    dom = detect_domain(text)
    if dom:
        pack = domain_pack(dom, deep=bool(_DELIVERABLE_RE.search(text)), uid=uid)
        if pack:
            parts.append(pack)
    return ("\n\n".join(parts), dom)
