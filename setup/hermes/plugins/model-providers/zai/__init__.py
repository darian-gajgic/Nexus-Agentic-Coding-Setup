"""ZAI / GLM provider profile — USER OVERRIDE (reasoning_effort-aware).

Overrides the bundled zai profile (same-name, last-writer-wins). The bundled
ZaiProfile emits only ``extra_body={"thinking":{"type":"enabled"|"disabled"}}``
and never sends ``reasoning_effort``, leaving the model at Z.AI's server
default. This override sends ``reasoning_effort`` explicitly (top-level, as a
sibling of ``thinking``).

Wire contract (verified empirically 2026-07-06 against api.z.ai coding
endpoint — an invalid value returns error 1210 listing the accepted set):
``reasoning_effort ∈ {none, minimal, low, medium, high, xhigh, max}`` — the
FULL scale is valid, not just the two levels (high/max) Z.AI markets for
GLM-5.2. The Hermes scale therefore passes through 1:1, except xhigh -> "max"
(Z.AI's documented top tier; docs.z.ai/guides/llm/glm-5.2 recommends max for
complex tasks). The param measurably modulates ALL thinking-capable GLMs, not
only 5.2 (glm-4.5-air on a trivial prompt: minimal=73 / default=190 / max=756
reasoning tokens) — so light "air"/"flash" models are capped at "medium":
they are the cheap mechanical tier and a global xhigh would silently burn
~10x reasoning tokens on them.

Lives in ~/.hermes/plugins/model-providers/zai/ so it survives ``hermes update``
(the repo is never touched). Delete this file to revert to the bundled profile.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

_log = logging.getLogger(__name__)
_LOGGED_EFFORTS: set = set()  # effort values already announced (log-once, M4)

_GLM_VERSION_RE = re.compile(r"^glm-(\d+)(?:\.(\d+))?")

# Hermes effort scale -> Z.AI reasoning_effort. The wire accepts the full
# scale (none/minimal/low/medium/high/xhigh/max — verified via error 1210);
# pass through faithfully, with xhigh mapped to Z.AI's documented top tier.
_EFFORT_MAP = {
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "max",
    "max": "max",
}

# Cheap mechanical tier: cap effort so a global xhigh doesn't burn ~10x
# reasoning tokens on models picked precisely for speed/cost (measured on
# glm-4.5-air: minimal=73 / default=190 / max=756 reasoning tokens for a
# trivial prompt).
_EFFORT_ORDER = ("minimal", "low", "medium", "high", "max")
_LIGHT_MODEL_CAP = "medium"
_WIRE_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}

# Operator-set per-model default efforts, published by the Nexus Settings tab
# to ~/.hermes/model-efforts.json (mtime-cached read per call, no restart).
_EFFORTS_FILE = os.path.expanduser("~/.hermes/model-efforts.json")
_efforts_cache: dict = {"mtime": 0.0, "efforts": {}}

# Per-session API keys (Nexus Settings v2), published to
# ~/.hermes/session-keys.json — {"sessions": {"api_…": {"api_key": "…"}}}.
# Same mtime-cached bridge pattern as model-efforts. A hit becomes a
# per-request Authorization header (the OpenAI SDK merges request headers
# OVER the client's env-key auth); a miss = env GLM_API_KEY, the pre-bridge
# behavior. NEVER log the key.
_SESSION_KEYS_FILE = os.path.expanduser("~/.hermes/session-keys.json")
_session_keys_cache: dict = {"mtime": 0.0, "sessions": {}}


def _session_entries(session_id: str | None) -> dict:
    """The session's full bridge entry ({} on miss). NEXUS CORE-MOD
    (session-effort): entries may now carry 'effort' next to 'api_key' —
    the dispatch's per-task reasoning effort (mode × task-type aware)."""
    if not session_id:
        return {}
    try:
        mtime = os.stat(_SESSION_KEYS_FILE).st_mtime
        if mtime != _session_keys_cache["mtime"]:
            import json as _json
            with open(_SESSION_KEYS_FILE) as f:
                data = _json.load(f)
            _session_keys_cache["sessions"] = {
                str(k): v
                for k, v in (data.get("sessions") or {}).items()
                if isinstance(v, dict)}
            _session_keys_cache["mtime"] = mtime
    except Exception:
        return {}
    return _session_keys_cache["sessions"].get(session_id) or {}


def _session_api_key(session_id: str | None) -> str | None:
    v = _session_entries(session_id).get("api_key")
    return str(v) if v else None


def _session_effort(session_id: str | None) -> str | None:
    """NEXUS CORE-MOD (session-effort): per-session reasoning effort published
    by the Nexus dispatch — the mode/task-type-aware choice; most specific,
    wins over the per-model operator default (the dispatch is already
    tier-aware, so no extra light-model cap applies here)."""
    v = str(_session_entries(session_id).get("effort") or "").strip().lower()
    return v if v in _WIRE_EFFORTS else None


def _operator_effort(model: str | None) -> str | None:
    try:
        mtime = os.stat(_EFFORTS_FILE).st_mtime
        if mtime != _efforts_cache["mtime"]:
            import json as _json
            with open(_EFFORTS_FILE) as f:
                data = _json.load(f)
            _efforts_cache["efforts"] = {
                str(k).lower(): str(v).lower()
                for k, v in (data.get("efforts") or {}).items()
                if str(v).lower() in _WIRE_EFFORTS}
            _efforts_cache["mtime"] = mtime
    except Exception:
        return None
    return _efforts_cache["efforts"].get((model or "").lower())


def _is_light_model(model: str | None) -> bool:
    m = (model or "").lower()
    return "air" in m or "flash" in m


def _effective_effort(effort: str, model: str | None,
                      session_effort: str | None = None) -> str:
    # NEXUS CORE-MOD (session-effort): the dispatch's per-task effort is the
    # most specific signal (mode × task type × tier) — it wins first.
    if session_effort:
        return _EFFORT_MAP.get(session_effort, session_effort)
    # An explicit operator default for this model wins over the config value.
    op = _operator_effort(model)
    if op:
        return op
    if _is_light_model(model) and effort in _EFFORT_ORDER and \
            _EFFORT_ORDER.index(effort) > _EFFORT_ORDER.index(_LIGHT_MODEL_CAP):
        return _LIGHT_MODEL_CAP
    return effort


def _model_supports_thinking(model: str | None) -> bool:
    """GLM thinking-capable model families: glm-4.5 and later (4.5, 4.6, 5…)."""
    m = (model or "").strip().lower()
    match = _GLM_VERSION_RE.match(m)
    if not match:
        return False
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    return (major, minor) >= (4, 5)


class ZaiProfile(ProviderProfile):
    """Z.AI / GLM — extra_body.thinking + explicit reasoning_effort."""

    def build_api_kwargs_extras(
        self, *, reasoning_config: dict | None = None, model: str | None = None, **context
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        extra_body: dict[str, Any] = {}
        top_level: dict[str, Any] = {}

        # Per-session key override FIRST — it must apply to every zai request
        # (also non-thinking models, which early-return below). top_level is
        # merged into api_kwargs unconditionally by the transport.
        _skey = _session_api_key(context.get("session_id"))
        if _skey:
            top_level["extra_headers"] = {"Authorization": f"Bearer {_skey}"}

        if not _model_supports_thinking(model):
            return extra_body, top_level

        _sef = _session_effort(context.get("session_id"))  # NEXUS CORE-MOD (session-effort)
        if isinstance(reasoning_config, dict):
            enabled = reasoning_config.get("enabled") is not False
            extra_body["thinking"] = {"type": "enabled" if enabled else "disabled"}
            if enabled:  # reasoning_effort only applies while thinking is on
                extra_body["reasoning_effort"] = _effective_effort(
                    _EFFORT_MAP.get(reasoning_config.get("effort"), "max"), model,
                    session_effort=_sef,
                )
        else:
            # No explicit preference: make the tier-appropriate top effort
            # explicit rather than relying on the server default.
            extra_body["thinking"] = {"type": "enabled"}
            extra_body["reasoning_effort"] = _effective_effort("max", model,
                                                               session_effort=_sef)

        # Log the effective effort ONCE per (model, value) at INFO — a per-call
        # WARNING put ~1.7k noise lines into errors.log in three days and
        # drowned out real errors (remediation item M4).
        effort = extra_body.get("reasoning_effort")
        key = (model, effort)
        if key not in _LOGGED_EFFORTS:
            _LOGGED_EFFORTS.add(key)
            _log.info("[zai-override] model=%s reasoning_effort=%s (logged once per pair)",
                      model, effort)
        return extra_body, top_level


zai = ZaiProfile(
    name="zai",
    aliases=("glm", "z-ai", "z.ai", "zhipu"),
    env_vars=("GLM_API_KEY", "ZAI_API_KEY", "Z_AI_API_KEY"),
    display_name="Z.AI (GLM)",
    description="Z.AI / GLM — Zhipu AI models (reasoning_effort-aware override)",
    signup_url="https://z.ai/",
    fallback_models=(
        "glm-5.2",
        "glm-5",
        "glm-4-9b",
    ),
    base_url="https://api.z.ai/api/paas/v4",
    default_aux_model="glm-4.5-flash",
)

register_provider(zai)
