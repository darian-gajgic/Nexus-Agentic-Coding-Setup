"""NEXUS Agent OS — Deep Plan mode (Phase 5).

The conversational planning phase for complex/ambiguous goals:
  triage (heuristics + cheap draft-plan divergence) → soft-gated recommendation
  → scaffolded interview that fills a per-family SPEC → draft the DAG from the
  spec → structural + external-model premortem verification → the spec travels
  downstream.

This module is deterministic and framework-free: pure heuristics, divergence
math, the per-family spec templates and their render/merge helpers. The model
calls (interview turns, divergence sampling, premortem critique) live in
server.py so this stays trivially unit-testable and importable off the event
loop.

Design is locked by DEEP-PLAN-MODE-PLAN-2026-07-10.md §3 (do not add LLM
self-rating to triage; ask gated + capped; scaffold the interview; premortem is
an EXTERNAL verifier).
"""
from __future__ import annotations

import hashlib
import re

# ─────────────────────────── Families ───────────────────────────
# Same four families as evals.DELIVERABLE_TYPES, but with friendly planning
# labels. The stored family KEY is the enum value used downstream (Step 6 map).
FAMILIES = ("software", "analysis-audit", "content", "research")

# family key → evals.DELIVERABLE_TYPES enum (premortem fix, Step 6): the stored
# family IS the enum value; labels stay friendly.
FAMILY_DELIVERABLE_TYPE = {
    "software": "code_change",
    "analysis-audit": "analysis",
    "content": "content",
    "research": "research",
}

FAMILY_LABELS = {
    "software": "Software / coding",
    "analysis-audit": "Analysis / audit",
    "content": "Content / marketing",
    "research": "Research",
}

# Keyword signals for the family guess (triage; user-switchable in the UI).
_FAMILY_KEYWORDS = {
    "software": ("app", "code", "feature", "bug", "api", "endpoint", "backend",
                 "frontend", "database", "migration", "refactor", "deploy",
                 "website", "site", "script", "function", "server", "auth",
                 "login", "webhook", "sdk", "library", "cli", "build", "test"),
    "analysis-audit": ("audit", "analyze", "analysis", "review", "assess",
                       "evaluate", "investigate", "diagnose", "root cause",
                       "compare", "benchmark", "inspect", "verify", "risk"),
    "content": ("write", "article", "blog", "post", "email", "campaign", "ad",
                "copy", "landing", "brand", "marketing", "newsletter", "video",
                "script", "listing", "product description", "social", "deck"),
    "research": ("research", "find out", "sources", "survey", "literature",
                 "state of the art", "options", "market", "competitor",
                 "landscape", "compile", "gather", "investigate the"),
}


def detect_family(goal: str) -> str:
    """Best-effort family guess from the goal text (user-switchable)."""
    g = (goal or "").lower()
    scores = {f: 0 for f in FAMILIES}
    for fam, kws in _FAMILY_KEYWORDS.items():
        for kw in kws:
            if kw in g:
                scores[fam] += 1
    # software wins ties for engineering-shaped goals; else the max, else content
    best = max(FAMILIES, key=lambda f: (scores[f], f == "software"))
    return best if scores[best] > 0 else "content"


# ─────────────────────────── Triage heuristics (free, deterministic) ───────────────────────────
# LOCKED decision §3.1: triage NEVER uses LLM self-rating. Signals are
# deterministic heuristics + divergence across cheap sampled draft plans.

_VAGUE_MARKERS = (
    r"\bthe system\b", r"\bthe app\b", r"\bthe whole thing\b", r"\bthat thing\b",
    r"\beverything\b", r"\bsomehow\b", r"\bstuff\b", r"\bthe platform\b",
    r"\bmake it (?:better|good|work|nice)\b",
)
_ARTIFACT_NOUNS = (
    "report", "site", "website", "campaign", "app", "dashboard", "api",
    "document", "doc", "plan", "deck", "email", "newsletter", "video",
    "model", "analysis", "audit", "spec", "landing page", "presentation",
    "database", "pipeline", "integration", "script",
)
_DEP_PHRASES = (
    r"\bthen\b", r"\bafter (?:that|which)\b", r"\bbased on\b", r"\bonce\b",
    r"\bso that\b", r"\bwhich (?:then|feeds)\b", r"\band then\b",
    r"\busing the (?:results?|output)\b", r"\bfeed(?:s|ing)? into\b",
)
_BLAST_TERMS = (
    "deploy", "production", "prod", "send", "email out", "purchase", "payment",
    "migrate", "migration", "delete", "drop table", "customers", "public",
    "launch", "go live", "charge", "refund", "invoice", "real money",
)
# per-domain keyword buckets for the cross-domain signal
_DOMAIN_BUCKETS = {
    "code": ("code", "app", "api", "backend", "frontend", "database", "deploy"),
    "marketing": ("ad", "campaign", "brand", "copy", "landing", "seo", "social"),
    "data": ("dataset", "analytics", "metrics", "sql", "chart", "dashboard"),
    "research": ("research", "sources", "market", "competitor", "survey"),
    "design": ("design", "logo", "mockup", "ui", "ux", "figma", "wireframe"),
    "ops": ("deploy", "infra", "server", "docker", "ci", "pipeline"),
}


def triage_heuristics(goal: str) -> dict:
    """Deterministic complexity/ambiguity signals from the goal text alone.
    Returns {complexity: 0-10, ambiguity: 0-1, blast_radius: bool,
    reasons: [str], family: str}. No model call."""
    g = (goal or "").strip()
    gl = g.lower()
    score = 0.0
    reasons: list[str] = []

    n = len(g)
    if n > 280:
        score += 2; reasons.append("long, detailed goal (many moving parts)")
    elif n > 120:
        score += 1; reasons.append("multi-sentence goal")

    vague = sum(1 for p in _VAGUE_MARKERS if re.search(p, gl))
    if vague:
        score += 1
        reasons.append("vague references to unnamed targets (\"the system\", \"everything\")")

    artifacts = {a for a in _ARTIFACT_NOUNS if re.search(rf"\b{re.escape(a)}s?\b", gl)}
    if len(artifacts) >= 2:
        score += 2
        reasons.append(f"multiple deliverables ({', '.join(sorted(artifacts)[:4])})")

    domains_hit = [d for d, kws in _DOMAIN_BUCKETS.items() if any(k in gl for k in kws)]
    if len(domains_hit) >= 2:
        score += 2
        reasons.append(f"spans ≥2 domains ({', '.join(domains_hit[:3])})")

    if any(re.search(p, gl) for p in _DEP_PHRASES):
        score += 1
        reasons.append("sequential / dependent steps (\"then\", \"based on\")")

    blast = any(t in gl for t in _BLAST_TERMS)
    if blast:
        score += 2
        reasons.append("real-world blast radius (deploy / send / money)")

    complexity = max(0.0, min(10.0, score))
    # Ambiguity from text alone (refined by divergence sampling when available):
    # vague + underspecified reads as ambiguous; a long precise brief less so.
    ambiguity = 0.15
    if vague:
        ambiguity = 0.45
    if n < 60 and complexity >= 4:
        ambiguity = max(ambiguity, 0.5)  # big ask, tiny brief → underspecified
    return {
        "complexity": round(complexity, 1),
        "ambiguity": round(ambiguity, 2),
        "blast_radius": blast,
        "reasons": reasons,
        "family": detect_family(goal),
    }


def in_uncertain_band(complexity: float) -> bool:
    """The 3–7 middle band where cheap divergence sampling earns its cost
    (heuristics are decisive outside it)."""
    return 3.0 <= float(complexity) <= 7.0


# ─────────────────────────── Divergence (cheap sampling, deterministic math) ───────────────────────────
_STOP = {"the", "a", "an", "and", "or", "of", "to", "for", "with", "in", "on",
         "build", "create", "make", "add", "task", "plan", "spec", "implement"}


def _title_tokens(title: str) -> set:
    toks = re.findall(r"[a-z0-9]+", (title or "").lower())
    return {t for t in toks if t not in _STOP and len(t) > 2}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def summarize_draft(plan: dict) -> dict:
    """Reduce a wizard draft plan to the deterministic shape signals divergence
    compares: task count, the union of title tokens, and DAG shape."""
    if not isinstance(plan, dict):
        return {"task_count": 0, "tokens": set(), "shape": "empty"}
    if plan.get("type") == "workflow" and isinstance(plan.get("workflow"), dict):
        tasks = plan["workflow"].get("tasks") or []
        titles = [str(t.get("title") or "") for t in tasks if isinstance(t, dict)]
        deps = [len((t.get("depends_on") or t.get("depends_on_idx") or []))
                for t in tasks if isinstance(t, dict)]
        n = len(titles)
        if n <= 1:
            shape = "single"
        elif sum(deps) == 0:
            shape = "parallel"
        elif all(d <= 1 for d in deps):
            shape = "chain"
        else:
            shape = "dag"
    else:
        titles = [str((plan.get("task") or {}).get("title") or plan.get("title") or "")]
        n = 1
        shape = "single"
    tokens: set = set()
    for t in titles:
        tokens |= _title_tokens(t)
    return {"task_count": n, "tokens": tokens, "shape": shape}


def divergence(summaries: list) -> dict:
    """Deterministic disagreement across N cheap draft-plan summaries →
    {score: 0-1, reasons: [str]}. High score = ambiguous+complex (ClarifyGPT
    signal). Needs ≥2 summaries; fewer = no signal."""
    sums = [s for s in (summaries or []) if isinstance(s, dict) and s.get("shape") != "empty"]
    if len(sums) < 2:
        return {"score": 0.0, "reasons": []}
    reasons: list[str] = []
    counts = [s["task_count"] for s in sums]
    spread = max(counts) - min(counts)
    count_sig = min(1.0, spread / 4.0)
    if spread >= 2:
        reasons.append(f"draft plans disagreed on size ({min(counts)}–{max(counts)} tasks)")

    pairs = [(i, j) for i in range(len(sums)) for j in range(i + 1, len(sums))]
    dists = [1.0 - _jaccard(sums[i]["tokens"], sums[j]["tokens"]) for i, j in pairs]
    token_sig = sum(dists) / len(dists) if dists else 0.0
    if token_sig >= 0.6:
        reasons.append("draft plans proposed substantially different tasks")

    shapes = {s["shape"] for s in sums}
    shape_sig = 0.0 if len(shapes) <= 1 else min(1.0, (len(shapes) - 1) / 2.0)
    if len(shapes) > 1:
        reasons.append(f"draft plans disagreed on structure ({', '.join(sorted(shapes))})")

    score = round(min(1.0, 0.45 * token_sig + 0.35 * count_sig + 0.20 * shape_sig), 2)
    return {"score": score, "reasons": reasons}


# ─────────────────────────── Recommendation (soft gate) ───────────────────────────
def recommend(heur: dict, div: dict | None = None,
              setting: str = "auto", spend_profile: str | None = None) -> dict:
    """Combine heuristics + (optional) divergence into the triage payload the
    wizard returns. `setting` = plan.recommend (auto|always|never); when the item
    carries a spend profile it OVERRIDES the raw setting (Eco→never, Optimal→auto,
    Smart→always) per the Step-1 coherence note. Returns the full triage dict."""
    heur = heur or {}
    complexity = float(heur.get("complexity") or 0)
    ambiguity = float(heur.get("ambiguity") or 0)
    reasons = list(heur.get("reasons") or [])
    div = div or {}
    if div.get("score"):
        # divergence sharpens ambiguity (never lowers the text-based read)
        ambiguity = max(ambiguity, float(div["score"]))
        for r in (div.get("reasons") or []):
            if r not in reasons:
                reasons.append(r)

    mode = (spend_profile and {"eco": "never", "optimal": "auto",
                               "smart": "always"}.get(spend_profile)) or setting or "auto"
    if mode == "always":
        recommend_deep = True
    elif mode == "never":
        recommend_deep = False
    else:  # auto — gate on detected complexity/ambiguity
        recommend_deep = complexity >= 5.0 or ambiguity >= 0.5

    # Appendix C5 synergy: the same triage drives the Super Result suggestion —
    # high complexity OR real-world blast radius warrants the grounded critic.
    recommend_sr = bool(complexity >= 6.0 or heur.get("blast_radius"))

    return {
        "complexity": round(complexity, 1),
        "ambiguity": round(ambiguity, 2),
        "recommend_deep_plan": bool(recommend_deep),
        "recommend_super_result": recommend_sr,
        "reasons": reasons[:6],
        "family": heur.get("family") or "content",
    }


def goal_hash(goal: str, uid: str | None = None) -> str:
    return hashlib.sha1(f"{uid or '-'}|{(goal or '').strip()}".encode()).hexdigest()[:16]


# ─────────────────────────── Spec templates (scaffold the interview) ───────────────────────────
# LOCKED §3.4: the interview is scaffolded by a per-family spec template; the
# conversation fills slots, free-form chat is allowed but answers always map back
# into the spec. Each slot: (key, label, kind 'text'|'list', required, hint).
SPEC_TEMPLATES: dict = {
    "software": [
        ("goal", "Goal", "text", True, "what the software must do, in one or two sentences"),
        ("stack_platform", "Stack / platform", "text", True, "language, framework, runtime, target"),
        ("acceptance_criteria", "Acceptance criteria", "list", True,
         "each independently testable (\"the API returns 401 for an expired token\")"),
        ("users", "Users", "text", False, "who uses it and how"),
        ("constraints", "Constraints", "text", False, "performance, security, compatibility, deadlines"),
        ("data_integrations", "Data / integrations", "text", False, "stores, external services, APIs"),
        ("out_of_scope", "Out of scope", "text", False, "what this explicitly does NOT do"),
        ("risks", "Risks", "text", False, "what could go wrong; blast radius"),
        ("notes", "Notes / decisions", "text", False,
         "operator decisions made during plan revision"),
    ],
    "analysis-audit": [
        ("scope", "Scope", "text", True, "the subsystems / artifacts to examine, enumerated"),
        ("questions_to_answer", "Questions to answer", "list", True,
         "the specific questions the analysis must resolve"),
        ("evidence_standard", "Evidence standard", "text", True,
         "what counts as proof (re-run commands, primary sources, A-gates)"),
        ("deliverable_format", "Deliverable format", "text", False, "report shape, length, audience"),
        ("out_of_scope", "Out of scope", "text", False, "what is explicitly NOT examined"),
        ("notes", "Notes / decisions", "text", False,
         "operator decisions made during plan revision"),
    ],
    "content": [
        ("audience", "Audience", "text", True, "who reads it and what they already know"),
        ("channel_format", "Channel / format", "text", True, "where it runs and in what form"),
        ("core_message", "Core message", "text", True, "the one thing it must land"),
        ("voice", "Voice", "text", False, "tone; STYLE-VOICE reference"),
        ("success_metric", "Success metric", "text", False, "what a win looks like"),
        ("length", "Length", "text", False, "word/section budget"),
        ("mandatories_taboos", "Mandatories / taboos", "text", False, "must-include and never-say"),
        ("notes", "Notes / decisions", "text", False,
         "operator decisions made during plan revision"),
    ],
    "research": [
        ("research_questions", "Research questions", "list", True,
         "the questions the research must answer"),
        ("source_standard", "Source standard", "text", True,
         "what sources qualify; how claims are verified"),
        ("output_format", "Output format", "text", True, "report shape, length, citations"),
        ("depth_breadth", "Depth / breadth", "text", False, "how wide vs how deep"),
        ("decision_it_informs", "Decision it informs", "text", False,
         "the decision this research feeds"),
        ("notes", "Notes / decisions", "text", False,
         "operator decisions made during plan revision"),
    ],
}


def spec_slots(family: str) -> list:
    return SPEC_TEMPLATES.get(family, SPEC_TEMPLATES["content"])


def required_slots(family: str) -> list:
    return [s[0] for s in spec_slots(family) if s[3]]


def new_spec(family: str, goal: str = "") -> dict:
    """An empty spec skeleton for the family, goal pre-filled where the slot
    exists (software has a 'goal' slot)."""
    spec = {s[0]: ([] if s[2] == "list" else "") for s in spec_slots(family)}
    if "goal" in spec and goal:
        spec["goal"] = goal.strip()[:2000]
    return spec


def _is_filled(value, kind: str) -> bool:
    if kind == "list":
        return bool(isinstance(value, list) and any(str(x).strip() for x in value))
    return bool(str(value or "").strip())


def merge_spec(spec: dict, updates: dict, family: str) -> dict:
    """Merge model/user slot updates into the spec, clamped to the family's
    known slots and types. List slots accept a list OR a newline/semicolon
    string; text slots are trimmed."""
    out = dict(spec or {})
    kinds = {s[0]: s[2] for s in spec_slots(family)}
    for k, v in (updates or {}).items():
        if k not in kinds:
            continue
        if kinds[k] == "list":
            if isinstance(v, str):
                v = [p.strip() for p in re.split(r"[\n;]+", v) if p.strip()]
            elif isinstance(v, list):
                v = [str(x).strip()[:400] for x in v if str(x).strip()][:20]
            else:
                continue
            out[k] = v
        else:
            out[k] = str(v or "").strip()[:2000]
    return out


def required_filled(spec: dict, family: str) -> bool:
    kinds = {s[0]: s[2] for s in spec_slots(family)}
    return all(_is_filled((spec or {}).get(k), kinds[k]) for k in required_slots(family))


def empty_required(spec: dict, family: str) -> list:
    kinds = {s[0]: s[2] for s in spec_slots(family)}
    return [k for k in required_slots(family)
            if not _is_filled((spec or {}).get(k), kinds[k])]


def spec_public(spec: dict, family: str) -> list:
    """Slot rows for the live spec pane: label, value, filled, required, kind."""
    out = []
    for key, label, kind, req, hint in spec_slots(family):
        v = (spec or {}).get(key, [] if kind == "list" else "")
        out.append({"key": key, "label": label, "kind": kind, "required": bool(req),
                    "hint": hint, "value": v, "filled": _is_filled(v, kind)})
    return out


def render_spec_md(spec: dict, family: str, goal: str = "") -> str:
    """The on-disk SPEC.md that travels downstream (Step 8)."""
    lines = [f"# SPEC — {FAMILY_LABELS.get(family, family)}", ""]
    if goal:
        lines += [f"**Goal:** {goal.strip()}", ""]
    for key, label, kind, req, _hint in spec_slots(family):
        v = (spec or {}).get(key, [] if kind == "list" else "")
        star = " *(required)*" if req else ""
        lines.append(f"## {label}{star}")
        if kind == "list":
            items = [str(x).strip() for x in (v or []) if str(x).strip()]
            lines += ([f"- {it}" for it in items] if items else ["_(not specified)_"])
        else:
            lines.append(str(v).strip() or "_(not specified)_")
        lines.append("")
    return "\n".join(lines)


# ─────────────────────────── Interview framing + turn parsing ───────────────────────────
def interview_framing(family: str, max_q: int, max_turns: int, goal: str,
                      context: str = "") -> str:
    """Scaffolded system framing for the planning session (LOCKED §3.3/§3.4).
    The model interviews the operator to fill the template; it asks ONLY for
    empty/ambiguous required slots, ≤max_q questions/turn with 3–5 ★-marked
    options, and says READY once required slots are filled. `context` grounds
    the interview in existing work (repo conventions/tree/languages) so the
    questions target the CHANGE, not a greenfield rebuild."""
    slots = spec_slots(family)
    slot_lines = "\n".join(
        f"- {key} ({'list' if kind == 'list' else 'text'}"
        f"{', REQUIRED' if req else ', optional'}): {hint}"
        for key, _label, kind, req, hint in slots)
    ctx_block = ""
    if (context or "").strip():
        ctx_block = (
            "EXISTING PROJECT STATE — the goal is a CHANGE to this existing work. Ground "
            "every question and every suggested option in it: never re-ask what the context "
            "already answers (stack, framework, structure), ask how the change integrates "
            "with what exists, and fill slots from it where possible.\n"
            + context.strip()[:5000] + "\n\n")
    return (
        "You are the Deep Plan interviewer for the Nexus agent control plane. The operator "
        f"has a {FAMILY_LABELS.get(family, family)} goal and you are filling a structured SPEC "
        "by interviewing them — you NEVER do the work, you only elicit requirements and map "
        "answers into spec slots.\n\n"
        "⛔ TOOLS ARE OFF-LIMITS IN THIS SESSION. Even though tools may be available to you, "
        "you must never call any: no terminal commands, no reading or writing files, no code "
        "execution, no web access. Planning is pure conversation — if the goal asks for an "
        "audit, a build, or research, that work happens LATER in the tasks this plan creates, "
        "never here. Reply immediately with the JSON object and nothing else.\n\n"
        f"OPERATOR GOAL: {goal.strip()[:1500]}\n\n"
        + ctx_block +
        "SPEC SLOTS (fill these — required slots gate readiness):\n" + slot_lines + "\n\n"
        "EVERY reply is ONLY a JSON object, no prose outside it, no code fences:\n"
        '{"message": "<one short line to the operator>",\n'
        ' "spec_updates": {"<slot>": <text or list of strings>, ...},\n'
        f' "questions": [{{"id":"q1","question":str,"why":str,'
        '"slot":"<which slot this fills>",'
        '"options":[{"label":str,"recommended":bool}, 3-5 of these]}}],\n'
        ' "ready": false}\n\n'
        "RULES:\n"
        f"- Ask at most {max_q} questions per turn, ONLY for empty or ambiguous REQUIRED "
        "slots (optional slots: infer a sensible default into spec_updates, don't ask).\n"
        "- Each question offers 3–5 concrete options; mark EXACTLY ONE recommended:true "
        "(the best-practice default). The operator may also answer freely.\n"
        "- Fold everything the operator tells you (this turn and before) into spec_updates, "
        "mapping each answer to its slot. acceptance_criteria / questions_to_answer / "
        "research_questions are LISTS of independently-testable strings.\n"
        f"- After at most {max_turns} turns, OR as soon as every REQUIRED slot is filled, set "
        '"ready": true, ask NO more questions, and let "message" say the plan is ready to draft.\n'
        "- Never invent facts the operator must decide (names, prices, dates) — ask or leave "
        "the slot for them.")


def parse_turn(text: str) -> dict:
    """Extract the interviewer's JSON reply → {message, spec_updates, questions, ready}.
    Defensive: a non-JSON reply becomes a plain message with no updates."""
    t = text or ""
    s, e = t.find("{"), t.rfind("}")
    data = {}
    if s != -1 and e != -1:
        import json as _json
        try:
            data = _json.loads(t[s:e + 1])
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    questions = []
    for q in (data.get("questions") or [])[:6]:
        if not isinstance(q, dict):
            continue
        opts = [{"label": str(o.get("label") or "").strip()[:200],
                 "recommended": bool(o.get("recommended"))}
                for o in (q.get("options") or []) if isinstance(o, dict)
                and str(o.get("label") or "").strip()][:5]
        if not any(o["recommended"] for o in opts) and opts:
            opts[0]["recommended"] = True
        questions.append({
            "id": str(q.get("id") or f"q{len(questions)+1}")[:20],
            "question": str(q.get("question") or "").strip()[:400],
            "why": str(q.get("why") or "").strip()[:300],
            "slot": str(q.get("slot") or "").strip()[:60],
            "options": opts})
    return {
        "message": str(data.get("message") or (t.strip()[:400] if not data else "")).strip()[:600],
        "spec_updates": data.get("spec_updates") if isinstance(data.get("spec_updates"), dict) else {},
        "questions": questions,
        "ready": bool(data.get("ready")),
    }


# the family's primary list slot — the "acceptance criteria" distributed onto
# tasks as "Done when: …" lines (Step 6) and checked for orphans (Step 7).
_CRITERIA_SLOT = {
    "software": "acceptance_criteria",
    "analysis-audit": "questions_to_answer",
    "research": "research_questions",
    "content": None,
}


def criteria_slot(family: str) -> str | None:
    return _CRITERIA_SLOT.get(family)


def list_criteria(spec: dict, family: str) -> list:
    slot = criteria_slot(family)
    if not slot:
        return []
    v = (spec or {}).get(slot) or []
    return [str(x).strip() for x in v if str(x).strip()]


def stub_plan(spec: dict, family: str, goal: str) -> dict:
    """Deterministic canned DRAFT plan for the verify gate (plan.stub). Produces
    a raw wizard plan (before _repair_workflow) with the acceptance criteria
    distributed onto the build task as 'Done when: …' lines — so the gate can
    exercise the real repair + criteria-distribution path without a model call."""
    crit = list_criteria(spec, family)
    done_when = "".join(f"\nDone when: {c}" for c in crit)
    g = (goal or "goal").strip()[:120]
    if family == "software":
        return {"type": "workflow", "workflow": {
            "name": g, "goal": g, "domain": "software-engineering", "tasks": [
                {"title": f"Spec & plan: {g}", "specialist": "tech-lead-orchestrator",
                 "domain": "software-engineering", "depends_on": [],
                 "description": f"Produce the SPEC & plan for: {g}. {(spec or {}).get('stack_platform','')}"},
                {"title": f"Implement + tests: {g}", "specialist": "code-implementer",
                 "domain": "software-engineering", "depends_on": [0],
                 "description": f"Implement {g} against the SPEC.{done_when}"},
            ]}}
    if family == "analysis-audit":
        return {"type": "task", "task": {
            "title": f"Analyze: {g}", "domain": "general", "specialist": None,
            "deliverable_type": "analysis",
            "description": f"Analysis of: {g}. Scope: {(spec or {}).get('scope','')}.{done_when}"}}
    if family == "research":
        return {"type": "task", "task": {
            "title": f"Research: {g}", "domain": "research-learning", "specialist": "web-researcher",
            "deliverable_type": "research",
            "description": f"Research: {g}. Source standard: {(spec or {}).get('source_standard','')}.{done_when}"}}
    return {"type": "task", "task": {
        "title": f"Create: {g}", "domain": "content-creation", "specialist": None,
        "deliverable_type": "content",
        "description": f"Create: {g}. Audience: {(spec or {}).get('audience','')}. "
                       f"Core message: {(spec or {}).get('core_message','')}.{done_when}"}}


def stub_revise(spec: dict, family: str, goal: str, tasks: list,
                findings: list, notes: str = "") -> dict:
    """Deterministic canned REVISION for the verify gate (plan.stub): each
    finding's problem line is appended to its target task ('Addressed finding
    N: …'), and one canned operator question is returned on a notes-free round
    (none once notes/answers are supplied) — so the gate can assert both the
    revision and the guided-question path without a model call."""
    import copy
    out = copy.deepcopy(tasks or [])
    for n, f in enumerate(findings or []):
        if not out:
            break
        f = f if isinstance(f, dict) else {}
        idx = f.get("task_idx")
        idx = idx if isinstance(idx, int) and 0 <= idx < len(out) else 0
        problem = str(f.get("problem") or f.get("message") or "finding").strip()[:120]
        out[idx]["description"] = ((out[idx].get("description") or "").rstrip()
                                   + f"\nAddressed finding {n + 1}: {problem}").strip()
    questions = []
    if (findings or []) and not (notes or "").strip():
        questions = [{"id": "q1", "question": "[stub] Keep the current scope?",
                      "why": "stub revision decision",
                      "options": [{"label": "Yes", "recommended": True},
                                  {"label": "No", "recommended": False}]}]
    g = (goal or "revised plan").strip()[:120]
    return {"type": "workflow",
            "workflow": {"name": g, "goal": g, "tasks": out},
            "questions": questions}


def stub_turn(spec: dict, family: str, user_message: str, turns_so_far: int,
              max_turns: int) -> dict:
    """Deterministic canned interviewer for the verify gate (plan.stub) — mirrors
    evals.stub's generation short-circuit. Fills the first empty required slot
    from the user's message each turn and asks about the next; once all required
    slots are filled (or the turn cap is hit) it declares READY. No model call."""
    empties = empty_required(spec, family)
    updates = {}
    kinds = {s[0]: s[2] for s in spec_slots(family)}
    if empties:
        slot = empties[0]
        val = (user_message or "").strip() or f"[stub value for {slot}]"
        updates[slot] = [val] if kinds[slot] == "list" else val
        remaining = empties[1:]
    else:
        remaining = []
    ready = not remaining or (turns_so_far + 1) >= max_turns
    if remaining and not ready:
        nxt = remaining[0]
        label = next((s[1] for s in spec_slots(family) if s[0] == nxt), nxt)
        questions = [{"id": "q1", "question": f"[stub] What is the {label}?",
                      "why": "stub", "slot": nxt,
                      "options": [{"label": "Option A", "recommended": True},
                                  {"label": "Option B", "recommended": False}]}]
        message = f"[PLAN STUB] recorded {list(updates)}, asking about {nxt}"
    else:
        questions = []
        message = "[PLAN STUB] all required slots filled — ready to draft"
    return {"message": message, "spec_updates": updates,
            "questions": questions, "ready": bool(ready)}
