#!/usr/bin/env python3
"""Auto-reflection for specialist agents (offline, salience-gated, human-approved).

Reads the specialist completion log (~/.hermes/agents/.reflection_log.jsonl,
appended by delegate_tool when a specialist child finishes), and for each new
entry asks a STRONG model (GLM) whether there is ONE concrete reusable lesson
worth remembering. Only clearly-salient, novel (embedding-deduped), confident
drafts become PROPOSALS in ~/.hermes/agents/.pending_lessons.json — which a human
approves/edits/rejects in the nexus Specialists tab. Nothing is written to a
specialist's memory here; approval (in nexus) does the write via mem0_curate.py.

This is the OWASP ASI06 "review gate": no auto-re-ingestion of an agent's own
output into trusted memory. Runs on a systemd timer. Fail-soft throughout.
"""
import os
import re
import json
import uuid
import math
import fcntl
import datetime
import urllib.error
import urllib.request
from pathlib import Path

AGENTS = Path(os.path.expanduser("~/.hermes/agents"))
LOG = AGENTS / ".reflection_log.jsonl"
QUEUE = AGENTS / ".pending_lessons.json"
QUEUE_LOCK = AGENTS / ".pending_lessons.lock"
STATE = AGENTS / ".reflect_state.json"
OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
CONF_FLOOR = 0.55       # discard low-confidence drafts
DEDUP_SIM = 0.86        # discard if too similar to an existing lesson


def _env(key):
    try:
        for line in open(os.path.expanduser("~/.hermes/.env")):
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def _mem0_cfg():
    try:
        return json.loads(open(os.path.expanduser("~/.hermes/mem0.json")).read())
    except Exception:
        return {}


class _DraftUnavailable(Exception):
    """Transport/config failure — the entry was NOT judged; retry next run."""


def _glm_draft(specialist, goal, outcome):
    """Ask GLM for one atomic lesson or none.

    Returns dict (lesson drafted) or None (GLM judged: nothing to learn).
    Raises _DraftUnavailable when the call could not be made at all — the
    caller must stop consuming the log so the entry is retried next run
    instead of being silently lost.
    """
    key = _env("GLM_API_KEY") or _env("ZAI_API_KEY")
    if not key:
        raise _DraftUnavailable("no GLM/ZAI api key")
    prompt = (
        f"You are the reflection module for a '{specialist}' specialist agent. Review the task it "
        "just completed and decide if there is exactly ONE concrete, reusable lesson worth remembering "
        f"that would improve how the {specialist} handles this kind of task next time.\n\n"
        f"TASK GOAL:\n{goal}\n\nOUTCOME:\n{outcome}\n\n"
        "Rules:\n"
        "- Propose a lesson ONLY on a clear salient signal: a mistake that was fixed, a surprising "
        "result, a better method discovered, or an explicit correction. If the task was routine with "
        'nothing notable to learn, return {"lesson": null}.\n'
        "- The lesson must be a SINGLE atomic behavior rule (one idea), self-contained, phrased as "
        'guidance for next time (e.g. "Prefer X over Y for Z because ..." or "Avoid X because Y").\n'
        "- Do NOT invent anything not supported by the outcome.\n"
        "- GENERALIZE: lessons become GLOBAL knowledge shared across all future work. Strip client "
        "names, company/product names, and any proprietary specifics — state the transferable craft "
        "rule instead. If the lesson cannot be stated without client-identifying details, return "
        '{"lesson": null} (client facts belong in that client\'s own memory, not in lessons).\n\n'
        'Respond ONLY as JSON: {"lesson": "<atomic rule or null>", "insight": "<what was learned, one '
        'sentence>", "confidence": <0.0-1.0>, "type": "rule|fact"}'
    )
    body = {"model": "glm-5.2", "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}]}
    base = (_mem0_cfg().get("_glm_base_url")
            or "https://api.z.ai/api/coding/paas/v4") + "/chat/completions"
    try:
        req = urllib.request.Request(base, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        r = json.loads(urllib.request.urlopen(req, timeout=90).read())
    except urllib.error.HTTPError as e:
        # Deterministic client rejection (bad payload, auth scope, …): this
        # exact entry would fail forever — consume it instead of wedging the
        # queue. 408/429/5xx are transient: halt and retry next run.
        if 400 <= e.code < 500 and e.code not in (408, 429):
            return None
        raise _DraftUnavailable(f"HTTP {e.code}")
    except Exception as e:
        raise _DraftUnavailable(str(e))
    try:
        txt = r["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if not m:
            return None
        d = json.loads(m.group(0))
        if not d.get("lesson"):
            return None
        return d
    except Exception:
        # Malformed reply for THIS entry — judged unusable, don't retry forever.
        return None


def _embed(text):
    try:
        req = urllib.request.Request(f"{OLLAMA}/api/embeddings",
            data=json.dumps({"model": "nomic-embed-text", "prompt": text}).encode(),
            headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=15).read()).get("embedding")
    except Exception:
        return None


def _cos(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _nearest_existing(agent_id, lesson_emb):
    """Nearest existing memory in this specialist's private scope: (text, similarity)."""
    cfg = _mem0_cfg()
    qurl = (cfg.get("oss", {}).get("vector_store", {}).get("config", {}) or {}).get("url", "http://localhost:6333")
    user_id = cfg.get("user_id", "hermes-user")
    try:
        req = urllib.request.Request(f"{qurl}/collections/mem0/points/search",
            data=json.dumps({"vector": lesson_emb, "limit": 1, "with_payload": True,
                             "filter": {"must": [{"key": "user_id", "match": {"value": user_id}},
                                                 {"key": "agent_id", "match": {"value": agent_id}}]}}).encode(),
            headers={"Content-Type": "application/json"})
        res = json.loads(urllib.request.urlopen(req, timeout=10).read()).get("result", [])
        if res:
            top = res[0]
            return (top.get("payload", {}).get("data") or top.get("payload", {}).get("memory"), top.get("score", 0.0))
    except Exception:
        pass
    return (None, 0.0)


def _queue_locked_append(items):
    """Merge new drafts into the pending queue under an exclusive lock,
    re-reading the file first: a run of this script can take minutes (GLM
    call per entry), and nexus's approve/reject endpoint rewrites the same
    file — appending to a stale pre-run copy would resurrect decided items."""
    with open(QUEUE_LOCK, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            try:
                cur = json.loads(QUEUE.read_text()) if QUEUE.exists() else []
            except Exception:
                cur = []
            known = {" ".join(str(x.get("lesson", "")).lower().split()) for x in cur}
            for it in items:
                k = " ".join(str(it.get("lesson", "")).lower().split())
                if k and k in known:
                    continue  # identical draft already pending
                known.add(k)
                cur.append(it)
            QUEUE.write_text(json.dumps(cur, indent=2))
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def main():
    if not LOG.exists():
        return
    state = {}
    try:
        state = json.loads(STATE.read_text()) if STATE.exists() else {}
    except Exception:
        state = {}
    processed = state.get("processed", 0)
    lines = [l for l in LOG.read_text().splitlines() if l.strip()]
    new = lines[processed:]
    if not new:
        return
    fresh = []
    drafted = 0
    consumed = 0
    halted = None
    for raw in new:
        try:
            d = None
            try:
                e = json.loads(raw)
            except Exception:
                e = None
            if e:
                spec, goal, outcome = e.get("specialist"), e.get("goal", ""), e.get("outcome", "")
                if spec and goal:
                    d = _glm_draft(spec, goal, outcome)
        except _DraftUnavailable as exc:
            # GLM unreachable: STOP without consuming this entry — it will be
            # retried next run instead of being silently lost.
            halted = str(exc)
            break
        consumed += 1
        if not d:
            continue
        if float(d.get("confidence", 0)) < CONF_FLOOR:
            continue
        lesson = str(d["lesson"]).strip()
        emb = _embed(lesson)
        near_text, near_sim = _nearest_existing(spec, emb) if emb else (None, 0.0)
        if near_sim >= DEDUP_SIM:
            continue  # already known — never surface a duplicate (avoids rubber-stamping)
        fresh.append({
            "id": uuid.uuid4().hex[:12],
            "specialist": spec,
            "lesson": lesson,                         # How I'll apply it
            "insight": str(d.get("insight", "")),      # What I learned
            "source_goal": goal[:400],
            "source_outcome": str(outcome)[:600],      # confabulation / provenance check
            "similar_existing": near_text,             # diff vs existing (None if novel)
            "similarity": round(near_sim, 3),
            "confidence": float(d.get("confidence", 0)),
            "type": d.get("type", "rule"),
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "status": "pending",
        })
        drafted += 1
    if fresh:
        _queue_locked_append(fresh)
    state_out = {"processed": processed + consumed,
                 "last_run": datetime.datetime.now().isoformat(timespec="seconds"),
                 "last_drafted": drafted}
    if halted:
        state_out["halted"] = halted
    STATE.write_text(json.dumps(state_out))
    msg = f"reflect: processed {consumed} completion(s) -> {drafted} proposal(s) queued"
    if halted:
        msg += f" (halted early, GLM unavailable: {halted[:120]} — {len(new) - consumed} entr(y/ies) kept for retry)"
    print(msg)


if __name__ == "__main__":
    main()
