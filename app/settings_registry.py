"""NEXUS Agent OS — declarative settings registry (Settings v2).

One entry per operational setting so the Settings tab can render, validate and
save EVERYTHING the program needs without code changes per key. Defaults here
are the values the code actually falls back to today — a fresh install with an
empty settings table behaves identically to before Settings v2.

Env-backed entries (env=...) resolve setting → environment → default, so the
historical env-var configuration keeps working until a value is saved in the
UI. restart=True marks values read at process start (module constants) — the
UI shows a restart hint instead of pretending they apply live.
"""
import os

import database as db

PURPOSES = {
    "complicated": "Complicated tasks — real deliverables, hard thinking, all dev-pipeline stages (default model)",
    "easy": "Easy tasks — light/simple work",
    "mechanical": "Mechanical tasks — formatting, extraction, conversions",
    "frontier_judge": "Frontier judge — scores high-stakes deliverables and eval runs against the domain rubric",
}

WORKER_PURPOSES = ("complicated", "easy", "mechanical")

SECTIONS = [
    {
        "id": "dispatch", "title": "Dispatch & budgets",
        "desc": "Real task execution through Hermes: feature flag, token budgets and concurrency lanes.",
        "items": [
            {"key": "dispatch.enabled", "label": "Real dispatch enabled", "type": "bool", "default": "1",
             "help": "Master switch — off pauses every worker lane (queued tasks wait)."},
            {"key": "dispatch.default_task_budget", "label": "Default task budget (tokens)", "type": "int",
             "default": "5000000", "min": 10000,
             "help": "Per-task token budget when the task doesn't set its own."},
            {"key": "dispatch.daily_cap", "label": "Daily token cap", "type": "int",
             "default": "10000000", "min": 10000,
             "help": "All dispatches together stop for the day at this total."},
            {"key": "dispatch.max_concurrent_total", "label": "Max concurrent dispatches (total)", "type": "int",
             "default": "8", "min": 1, "max": 32,
             "help": "Hermes gateway caps ~10 concurrent runs — stay under it."},
            {"key": "dispatch.max_concurrent_per_model", "label": "Max concurrent per model", "type": "int",
             "default": "8", "min": 1, "max": 32,
             "help": "Z.AI's concurrency limit is per model (~10). Per-model overrides live in Models & routing."},
            {"key": "dispatch.max_turn_seconds", "label": "Max seconds per dispatched turn", "type": "int",
             "default": "2700", "min": 60, "max": 21600,
             "help": "Hard wall-clock cap on one agent turn before it's cut off."},
            {"key": "dispatch.resume_quiet_s", "label": "Resume quiet window (s)", "type": "int",
             "default": "600", "min": 30, "max": 7200,
             "help": "After a worker crash, wait this long for the orphaned Hermes run to finish before re-engaging."},
        ],
    },
    {
        "id": "judge", "title": "Frontier judge",
        "desc": "The judge command scores deliverables against the domain rubric. The model comes from the "
                "'frontier judge' purpose in Models & routing.",
        "items": [
            {"key": "judge.cmd", "label": "Judge command template", "type": "command",
             "default": "cjudge {file} {domain}",
             "help": "Tokens: {file} {domain} and optional {model}. The resolved judge model is also exported "
                     "as JUDGE_MODEL to the subprocess. Gates stub this — restore after testing."},
        ],
    },
    {
        "id": "integrations", "title": "Services & integrations",
        "desc": "Where Nexus finds its companion services. Values apply after a service restart.",
        "items": [
            {"key": "hermes.api_base", "label": "Hermes API base URL", "type": "str",
             "default": "http://127.0.0.1:8642", "env": "HERMES_API_BASE", "restart": True,
             "help": "The Hermes agent gateway every task/JARVIS session runs through."},
            {"key": "qdrant.url", "label": "Qdrant URL (memory)", "type": "str",
             "default": "http://localhost:6333", "env": "MEM0_QDRANT_URL",
             "help": "Vector store behind the memory galaxy and mem0."},
            {"key": "langfuse.base_url", "label": "Langfuse base URL", "type": "str",
             "default": "http://localhost:3000", "env": "HERMES_LANGFUSE_BASE_URL",
             "help": "Observability tab data source. Langfuse API keys are managed under Providers & credentials "
                     "(provider 'langfuse_public' / 'langfuse_secret') or ~/.hermes/.env."},
            {"key": "cost.per_1m_tokens", "label": "Cost per 1M tokens (USD)", "type": "float",
             "default": "2.0", "env": "NEXUS_COST_PER_1M_TOKENS", "restart": True,
             "help": "Used for projected-cost displays."},
        ],
    },
    {
        "id": "paths", "title": "Knowledge & commands",
        "desc": "Business-Brain roots and command templates.",
        "items": [
            {"key": "onboarding.root", "label": "Knowledge root", "type": "path", "default": "",
             "help": "Business Brain root directory. Empty = ~/knowledge."},
            {"key": "evals.corpus_root", "label": "Eval corpus root", "type": "path", "default": "",
             "help": "Eval briefs root. Empty = <knowledge root>/domains."},
            {"key": "pr.cmd", "label": "PR creation command template", "type": "command",
             "default": "gh pr create --head {branch} --base {base} --title {title} --body-file {bodyfile}",
             "help": "Tokens: {branch} {base} {title} {bodyfile}. Used by the Create-PR button on repo tasks."},
        ],
    },
    {
        "id": "auth", "title": "Access control",
        "desc": "Login is automatic once a second active user exists; user management lives in Users & access.",
        "items": [
            {"key": "auth.force", "label": "Force login even with a single user", "type": "bool", "default": "0",
             "help": "Turn on to require the login wall on a single-user machine too."},
        ],
    },
    {
        "id": "watchdog", "title": "Watchdog",
        "desc": "Self-healing for worker lanes.",
        "items": [
            {"key": "watchdog.interval_s", "label": "Sweep interval (s)", "type": "int",
             "default": "10", "min": 3, "max": 300, "help": "How often the watchdog checks lanes."},
            {"key": "watchdog.stale_threshold_s", "label": "Stale heartbeat threshold (s)", "type": "int",
             "default": "150", "min": 30, "max": 3600,
             "help": "A lane silent this long counts as stuck and is restarted (if enabled)."},
            {"key": "watchdog.stale_claim_s", "label": "Stale claim release (s)", "type": "int",
             "default": "3600", "min": 300, "max": 86400,
             "help": "A claimed-but-untouched task is released back to the queue after this long."},
            {"key": "watchdog.restart_on_stuck", "label": "Restart stuck lanes", "type": "bool", "default": "1"},
            {"key": "watchdog.restart_on_dead", "label": "Restart dead lanes", "type": "bool", "default": "1"},
        ],
    },
]

# Every namespace the generic /api/settings endpoint may touch — derived from
# the registry so a new section can't silently miss the whitelist.
PREFIXES = tuple(sorted({i["key"].split(".")[0] + "." for s in SECTIONS for i in s["items"]}
                        | {"dispatch.", "judge.", "model."}))


def _items() -> dict:
    return {i["key"]: i for s in SECTIONS for i in s["items"]}


def item_for(key: str) -> dict | None:
    return _items().get(key)


def conf(key: str, default: str | None = None) -> str:
    """Effective value: settings table → env (registry-declared) → registry
    default → caller default. Always a string (settings storage contract)."""
    item = _items().get(key)
    try:
        v = db.get_setting(key)
    except Exception:
        v = None  # pre-init_db import (first boot) — env/default chain still applies
    if v not in (None, ""):
        return v
    if item and item.get("env"):
        ev = os.environ.get(item["env"], "")
        if ev:
            return ev
    if item is not None:
        return item.get("default", "" if default is None else default)
    return "" if default is None else default


def validate(key: str, value: str) -> str | None:
    """Returns an error string, or None when the value is acceptable."""
    item = _items().get(key)
    if item is None:
        return None  # not registry-managed (e.g. model.effort.*) — endpoint prefix check still applies
    t = item["type"]
    if t == "bool":
        if value not in ("0", "1"):
            return f"{key}: expected 0/1"
    elif t in ("int", "float"):
        try:
            n = int(value) if t == "int" else float(value)
        except ValueError:
            return f"{key}: not a number"
        if item.get("min") is not None and n < item["min"]:
            return f"{key}: below minimum {item['min']}"
        if item.get("max") is not None and n > item["max"]:
            return f"{key}: above maximum {item['max']}"
    elif t in ("command", "str", "path"):
        if len(value) > 2000:
            return f"{key}: too long"
    return None


def schema(values: dict, is_admin: bool) -> dict:
    """The Settings tab payload: sections with per-item effective values."""
    out = []
    for s in SECTIONS:
        sec = {"id": s["id"], "title": s["title"], "desc": s["desc"], "items": []}
        for i in s["items"]:
            sec["items"].append({
                **{k: v for k, v in i.items() if k != "env"},
                "env": i.get("env"),
                "value": values.get(i["key"], ""),
                "effective": conf(i["key"]),
            })
        out.append(sec)
    return {"sections": out, "is_admin": is_admin, "purposes": PURPOSES}
