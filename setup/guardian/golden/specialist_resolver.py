"""Predefined specialist registry for delegate_task (model-driven selection).

Specialists are defined in ~/.hermes/agents/*.md (Claude Code-style markdown +
YAML frontmatter). The delegating agent sees a compact registry in the
delegate_task tool description and selects one by name via the `specialist`
parameter — the LLM does the matching (it understands the goal + the "when to
use" descriptions), which is more reliable than a local embedding/keyword router
and adds zero latency (the parent is already reasoning about the delegation).

This module resolves a named specialist to its playbook + mem0 scope + tool
allowlist, and renders the registry block for the tool description. No match /
no name -> the caller falls back to a dynamic ephemeral subagent (today's
behavior). Everything is fail-soft: any error yields no specialist.

Authored by us (not bundled Hermes); guardian-protected.
"""
import os
from pathlib import Path

AGENTS_DIR = Path(os.path.expanduser("~/.hermes/agents"))


def _parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    try:
        import yaml
        fm = yaml.safe_load(text[3:end]) or {}
    except Exception:
        fm = {}
    return fm, text[end + 4:].lstrip("\n")


def load_specialists():
    """Return [{name, description, playbook, agent_id, toolsets}], sorted by name."""
    out = []
    if not AGENTS_DIR.is_dir():
        return out
    for f in sorted(AGENTS_DIR.glob("*.md")):
        try:
            fm, body = _parse_frontmatter(f.read_text())
            desc = (fm.get("description") or "").strip()
            if not desc:
                continue
            name = fm.get("name") or f.stem
            out.append({
                "name": name,
                "description": desc,
                "playbook": body.strip(),
                "agent_id": fm.get("mem0_agent_id") or name,
                "toolsets": fm.get("tools") or fm.get("toolsets"),
            })
        except Exception:
            continue
    return out


def resolve_specialist(name):
    """Resolve a specialist by exact name -> its dict, or None (dynamic fallback)."""
    if not name:
        return None
    try:
        for s in load_specialists():
            if s["name"] == name:
                return s
    except Exception:
        return None
    return None


def registry_block():
    """A compact 'available specialists' block for the delegate_task tool description.

    Empty string when no specialists are defined (so the tool description is
    unchanged on a stock setup).
    """
    try:
        specs = load_specialists()
    except Exception:
        specs = []
    if not specs:
        return ""
    lines = [
        "",
        "AVAILABLE SPECIALISTS — prefer delegating to one of these over doing the work "
        "yourself or spawning a generic subagent. This applies to ALL substantial work, "
        "not only coding: writing, content, marketing, branding, research, and "
        "e-commerce tasks each have a specialist here, and they carry that role's "
        "accumulated memory and standing rules — so a blog post, an ad, a brand name, a "
        "product listing, or a market analysis should go to its specialist, not be "
        "answered directly. Before you handle any substantial request yourself, check "
        "this list: if a specialist's role fits, you MUST delegate with "
        "`specialist=<name>` (top-level, or per-task in `tasks`) rather than doing it "
        "inline. Only handle it yourself when the task is trivial or no specialist fits.",
    ]
    for s in specs:
        lines.append(f"- {s['name']}: {s['description']}")
    return "\n".join(lines)
