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
