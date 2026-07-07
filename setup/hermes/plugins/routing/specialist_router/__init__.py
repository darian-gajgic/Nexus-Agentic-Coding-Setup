"""Specialist router — keyword-gated forced routing to the best-matching specialist.

PROBLEM (documented failure mode): the orchestrator model under-delegates — for tasks
it feels it can do itself (research, analysis, writing) it answers directly instead of
routing to the matching specialist. Prompt-nudging in the system prompt is unreliable.

MECHANISM (Anthropic "routing workflow" + forced tool choice, adapted to this provider):
when the user's message contains a trigger phrase ("use a specialist" / "use an agent" /
...), the pre_gateway_dispatch hook runs ONE FORCED classification call — tool_choice
forces a `select_specialist` function whose `specialist_id` is an enum built at RUNTIME
from the specialist registry (~/.hermes/agents/*.md) plus a mandatory "none" escape. If a
specialist fits, it REWRITES the incoming message to PREPEND a mandatory delegation
directive naming that specialist; if none fits (or no trigger), it leaves the message
untouched and the turn proceeds exactly as before.

Why this shape: z.ai/GLM reliably honors forced tool_choice for the small select_specialist
tool (so the routing DECISION is a hard guarantee), but does NOT honor forcing the giant
delegate_task tool — so delegation is driven by a strong PREPENDED directive (prepending
beats appending for the stubborn "analyze our X" cases; the pre_gateway_dispatch rewrite is
the clean way to prepend). New agents enter the enum automatically — zero config.

Properties: reliable routing decision (forced tool call), general (enum from the live
registry), non-breaking (pure user plugin; fires only for real user messages — subagents are
`is_internal` and excluded; fail-soft; no core edits, survives updates).
"""
import os
import re
import json
import glob
import logging
import urllib.request

logger = logging.getLogger("specialist_router")

AGENTS_DIR = os.path.expanduser("~/.hermes/agents")
ENV_PATH = os.path.expanduser("~/.hermes/.env")
DEFAULT_URL = "https://api.z.ai/api/coding/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-5.2"

# Trigger: the user explicitly asking to use a specialist / agent.
_TRIGGER = re.compile(
    r"\b(use|call|pick|choose|delegate\s+to)\s+"
    r"(a\s+|an\s+|the\s+|your\s+|one\s+of\s+(?:your\s+|the\s+)?)?"
    r"(specialist|specialists|specialist\s+agent|agent|agents|sub-?agent)\b",
    re.I,
)


def _has_trigger(text):
    return bool(text) and bool(_TRIGGER.search(text))


def _load_registry():
    """Parse ~/.hermes/agents/*.md -> [{name, description}]. Self-contained, no imports."""
    out = []
    try:
        for path in sorted(glob.glob(os.path.join(AGENTS_DIR, "*.md"))):
            try:
                txt = open(path, encoding="utf-8").read()
                if not txt.startswith("---"):
                    continue
                end = txt.find("\n---", 3)
                fm = txt[3:end] if end != -1 else ""
                name = re.search(r"^name:\s*(.+)$", fm, re.M)
                desc = re.search(r"^description:\s*(.+)$", fm, re.M)
                if not name:
                    continue
                nm = name.group(1).strip().strip('"').strip("'")
                ds = desc.group(1).strip().strip('"').strip("'") if desc else ""
                if nm:
                    out.append({"name": nm, "description": ds})
            except Exception:
                continue
    except Exception as e:
        logger.warning("registry load failed: %s", e)
    return out


def _glm_creds():
    env = {}
    try:
        with open(ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    key = env.get("GLM_API_KEY") or os.environ.get("GLM_API_KEY")
    url = env.get("SPECIALIST_ROUTER_URL") or DEFAULT_URL
    model = env.get("SPECIALIST_ROUTER_MODEL") or DEFAULT_MODEL
    return key, url, model


def _forced_route(user_message, specs):
    """One forced classification call -> chosen specialist name, or None (incl. 'none')."""
    key, url, model = _glm_creds()
    if not key:
        logger.warning("no GLM_API_KEY; specialist_router inactive this turn")
        return None
    ids = [s["name"] for s in specs] + ["none"]
    listing = "\n".join(f"- {s['name']}: {s['description']}" for s in specs)
    tool = {
        "type": "function",
        "function": {
            "name": "select_specialist",
            "description": "Select the single best specialist for the user's request, or 'none' if no specialist is a good fit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "specialist_id": {"type": "string", "enum": ids,
                                      "description": "the best-matching specialist's exact name, or 'none'"},
                    "reason": {"type": "string", "description": "one short sentence"},
                },
                "required": ["specialist_id"],
            },
        },
    }
    sys_prompt = (
        "You are a routing classifier for a freelance team's agent system. Given the user's request and the "
        "list of available specialists (each with a when-to-use description), choose the SINGLE best-matching "
        "specialist. If no specialist is a clearly good fit, choose 'none' — do not force a poor match.\n\n"
        "Available specialists:\n" + listing
    )
    body = {
        "model": model,
        "messages": [{"role": "system", "content": sys_prompt},
                     {"role": "user", "content": user_message[:4000]}],
        "tools": [tool],
        "tool_choice": {"type": "function", "function": {"name": "select_specialist"}},
        "temperature": 0,
    }
    try:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        r = json.loads(urllib.request.urlopen(req, timeout=25).read())
        calls = r["choices"][0]["message"].get("tool_calls") or []
        if not calls:
            return None
        args = json.loads(calls[0]["function"]["arguments"])
        choice = (args.get("specialist_id") or "").strip()
        if choice and choice != "none" and any(s["name"] == choice for s in specs):
            return choice
    except Exception as e:
        logger.warning("routing call failed: %s", e)
    return None


def _directive(chosen, request_text):
    return (
        f"[SPECIALIST ROUTING — MANDATORY, do not answer this yourself] The user invoked specialist routing. "
        f"The correct specialist for this request is `{chosen}`. Your ONLY allowed action this turn is a single "
        f"delegate_task call with specialist='{chosen}' and goal set to the user's request below. Do not analyze it, "
        f"write prose, or call web_search yourself — delegate it. Answering directly is a failure.\n\n"
        f"User request: {request_text}"
    )


def on_pre_gateway_dispatch(*, event=None, **_):
    """Rewrite a triggered user message to prepend a mandatory delegation directive."""
    try:
        text = getattr(event, "text", None) or ""
        if not isinstance(text, str) or not _has_trigger(text):
            return None
        specs = _load_registry()
        if not specs:
            return None
        chosen = _forced_route(text, specs)
        if not chosen:
            # user asked for a specialist but none fits (or routing failed) -> proceed normally
            return None
        logger.info("specialist_router: routed to %s", chosen)
        return {"action": "rewrite", "text": _directive(chosen, text)}
    except Exception as e:
        logger.warning("specialist_router hook error: %s", e)
        return None


def register(ctx):
    ctx.register_hook("pre_gateway_dispatch", on_pre_gateway_dispatch)
