#!/usr/bin/env python3
"""Runtime gate — Settings v2 (docs/SPEC-SETTINGS-V2.md).

Proves against the LIVE server: the settings schema/registry endpoint, the
encrypted credential store (masked round-trip, plaintext never leaves the
API), the per-user model registry + purpose routing (validation + isolation),
task-model validation, judge model/env plumbing, and the session-keys bridge.
Self-cleaning: every probe row is deleted, every touched setting restored.
Multi-user-preserving (same-machine owner token via _gate_auth).
"""
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _gate_auth  # noqa: E402

BASE = "https://127.0.0.1:8777"
COOKIES = _gate_auth.owner_cookie()
C = httpx.Client(base_url=BASE, verify=False, cookies=COOKIES, timeout=30)

PASS = 0
FAIL = 0


def chk(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}  {detail}")


def main():
    probe = f"probe{uuid.uuid4().hex[:6]}"
    probe_key = "sk-probe-" + uuid.uuid4().hex
    cred_id = model_id = task_id = None
    prev_cost = None
    prev_easy_override = None

    try:
        # ── 1. Settings schema/registry ──
        print("── settings schema ──")
        r = C.get("/api/settings/schema")
        chk("schema endpoint answers", r.status_code == 200, r.text[:100])
        sch = r.json()
        secs = {s["id"] for s in sch.get("sections", [])}
        chk("registry sections complete",
            {"dispatch", "judge", "integrations", "paths", "auth", "watchdog"} <= secs, str(secs))
        chk("schema carries purposes", "frontier_judge" in (sch.get("purposes") or {}))
        items = [i for s in sch["sections"] for i in s["items"]]
        chk("every item has label+type+default+effective",
            all("label" in i and "type" in i and "default" in i and "effective" in i for i in items))
        chk("previously env-only settings exposed",
            {"hermes.api_base", "qdrant.url", "cost.per_1m_tokens", "pr.cmd",
             "onboarding.root", "watchdog.interval_s", "auth.force"}
            <= {i["key"] for i in items})

        # settings PATCH round-trip on a boot-read key (harmless live) + restore
        prev_cost = C.get("/api/settings", params={"prefix": "cost."}).json()["settings"] \
            .get("cost.per_1m_tokens")
        r = C.patch("/api/settings", json={"cost.per_1m_tokens": "3.5"})
        chk("new-prefix key writable", r.status_code == 200, r.text[:100])
        got = C.get("/api/settings", params={"prefix": "cost."}).json()["settings"]
        chk("new-prefix key readable", got.get("cost.per_1m_tokens") == "3.5", str(got))
        r = C.patch("/api/settings", json={"cost.per_1m_tokens": "not-a-number"})
        chk("registry validation rejects garbage", r.status_code == 400, r.text[:100])
        prev_enabled = C.get("/api/settings").json()["settings"].get("dispatch.enabled")
        r = C.patch("/api/settings", json={"dispatch.enabled": ""})
        chk("clearing a seeded bool pins its default (not delete)",
            r.status_code == 200 and C.get("/api/settings").json()["settings"]
            .get("dispatch.enabled") == "1", r.text[:100])
        if prev_enabled not in (None, "1"):
            C.patch("/api/settings", json={"dispatch.enabled": prev_enabled})

        # ── 2. Credentials: masked round-trip, no plaintext ever ──
        print("── credentials ──")
        r = C.post("/api/credentials", json={"provider": probe, "value": "short"})
        chk("too-short key rejected", r.status_code == 400)
        r = C.post("/api/credentials", json={"provider": "BAD SLUG!", "value": probe_key})
        chk("bad provider slug rejected", r.status_code == 400)
        r = C.post("/api/credentials", json={"provider": probe, "value": probe_key,
                                             "label": "gate probe"})
        chk("credential saved", r.status_code == 200, r.text[:150])
        body = r.json()
        cred_id = (body.get("credential") or {}).get("id")
        chk("save response masked (hint only, no value)",
            probe_key not in json.dumps(body)
            and body["credential"]["hint"] == probe_key[-4:], json.dumps(body)[:150])
        r = C.get("/api/credentials")
        listing = json.dumps(r.json())
        chk("list shows the row, never the plaintext",
            probe in listing and probe_key not in listing)
        import secrets_store
        chk("stored encrypted (raw DB row is not the plaintext)",
            probe_key not in json.dumps(
                __import__("database").query_one(
                    "SELECT enc_value FROM credentials WHERE id=?", (cred_id,))),
            "plaintext at rest!")
        chk("execution path resolves the plaintext",
            secrets_store.resolve_key("u_owner", probe) == probe_key)

        # isolation: a FOREIGN user's credential must be invisible
        import database as db
        db.execute("INSERT INTO credentials (id, user_id, provider, label, enc_value, hint, "
                   "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                   (f"cred-gate-foreign", "u_gate_foreign", probe, "",
                    secrets_store.encrypt("sk-foreign-1234567890"), "7890",
                    time.time(), time.time()))
        r = C.get("/api/credentials")
        chk("foreign user's credential invisible",
            "cred-gate-foreign" not in json.dumps(r.json()))
        r = C.delete("/api/credentials/cred-gate-foreign")
        chk("foreign credential delete = 404", r.status_code == 404)

        # ── 2b. Machine default keys (admin view/rotation — ~/.hermes/.env) ──
        print("── machine default keys ──")
        r = C.get("/api/credentials/defaults")
        chk("defaults endpoint answers (admin)", r.status_code == 200, r.text[:100])
        defs = {d["provider"]: d for d in r.json().get("defaults", [])}
        chk("zai default listed with its env var",
            defs.get("zai", {}).get("env") == "GLM_API_KEY")
        chk("anthropic default = CLI-managed (not env-editable)",
            "managed" in defs.get("anthropic", {}))
        chk("defaults response is masked (hints ≤4 chars, no values)",
            all(len(d.get("hint") or "") <= 4 for d in defs.values()))
        r = C.put("/api/credentials/defaults/anthropic", json={"value": "sk-" + "y" * 20})
        chk("CLI-managed provider not rotatable via env", r.status_code == 400)
        r = C.put("/api/credentials/defaults/nonsense", json={"value": "sk-" + "x" * 20})
        chk("unknown default provider rejected", r.status_code == 400)
        r = C.put("/api/credentials/defaults/zai", json={"value": "short"})
        chk("too-short default key rejected", r.status_code == 400)
        # the WRITER is proven on a scratch env file — never the live ~/.hermes/.env
        import secrets_store as ss
        scratch_env = Path(os.environ.get("TMPDIR", "/tmp")) / f"gate-env-{probe}"
        scratch_env.write_text("OTHER=1\n# [disabled by gate] GLM_API_KEY=old\nKEEP=2\n")
        prev_env_val = os.environ.get("GLM_API_KEY")
        try:
            row = ss.set_default_key("zai", "sk-gate-default-12345", env_file=str(scratch_env))
            txt = scratch_env.read_text()
            chk("anchored rewrite replaces the (commented) line",
                "GLM_API_KEY=sk-gate-default-12345" in txt and "old" not in txt, txt)
            chk("other env lines preserved", "OTHER=1" in txt and "KEEP=2" in txt)
            chk("env file left 0600", oct(scratch_env.stat().st_mode & 0o777) == "0o600")
            chk("rotation response masked", row["hint"] == "2345" and "value" not in row)
            scratch_env.write_text("OTHER=1\n")
            ss.set_default_key("zai", "sk-gate-append-6789", env_file=str(scratch_env))
            chk("missing key appended",
                "GLM_API_KEY=sk-gate-append-6789" in scratch_env.read_text())
        finally:
            if prev_env_val is None:
                os.environ.pop("GLM_API_KEY", None)
            else:
                os.environ["GLM_API_KEY"] = prev_env_val
            scratch_env.unlink(missing_ok=True)

        # ── 3. Model registry + purpose routing ──
        print("── model registry ──")
        r = C.get("/api/models")
        chk("models endpoint answers", r.status_code == 200)
        mods = r.json()
        chk("registry has a cli-route judge model",
            any(m["route"] == "cli" for m in mods["models"]))
        chk("Opus 4.8 judge model present (Settings v2 seed)",
            any(m["model_id"] == "claude-opus-4-8" for m in mods["models"]))
        chk("all four purposes resolve",
            all(mods["assignments"].get(p) for p in
                ("complicated", "easy", "mechanical", "frontier_judge")),
            str(mods["assignments"]))
        chk("task_models list non-empty", len(mods["task_models"]) >= 1)

        r = C.post("/api/models", json={"provider": probe, "model_id": f"{probe}-m1",
                                        "route": "nonsense"})
        chk("bad route rejected", r.status_code == 400)
        r = C.post("/api/models", json={"provider": probe, "model_id": f"{probe}-m1",
                                        "label": "gate probe", "route": "hermes",
                                        "credential_id": cred_id})
        chk("model row created", r.status_code == 200, r.text[:150])
        model_id = (r.json().get("model") or {}).get("id")
        r = C.get("/api/models")
        chk("created model listed + task-routable",
            f"{probe}-m1" in json.dumps(r.json())
            and f"{probe}-m1" in r.json()["task_models"])

        r = C.put("/api/models/assignments", json={"frontier_judge": model_id})
        chk("hermes-route model refused for judge purpose", r.status_code == 400)
        r = C.put("/api/models/assignments", json={"nonsense_purpose": model_id})
        chk("unknown purpose rejected", r.status_code == 400)
        r = C.put("/api/models/assignments", json={"easy": model_id})
        chk("personal purpose override accepted", r.status_code == 200, r.text[:100])
        prev_easy_override = True
        mods = C.get("/api/models").json()
        chk("override visible with source=user",
            mods["assignments"]["easy"] == model_id
            and mods["assignment_sources"]["easy"] == "user")
        chk("resolution follows the override (db layer)",
            db.resolve_assignment("u_owner", "easy")["model_id"] == f"{probe}-m1")
        r = C.put("/api/models/assignments", json={"easy": None})
        prev_easy_override = None
        chk("override cleared back to global",
            r.status_code == 200
            and C.get("/api/models").json()["assignment_sources"]["easy"] == "global")

        # foreign model row invisible + undeletable
        db.execute("INSERT INTO user_models (id, user_id, provider, model_id, route, enabled, "
                   "created_at, updated_at) VALUES (?,?,?,?, 'hermes', 1, ?, ?)",
                   ("mdl-gate-foreign", "u_gate_foreign", probe, f"{probe}-foreign",
                    time.time(), time.time()))
        chk("foreign user's model invisible",
            "mdl-gate-foreign" not in json.dumps(C.get("/api/models").json()))
        chk("foreign model delete = 404",
            C.delete("/api/models/mdl-gate-foreign").status_code == 404)

        # ── 4. Task model validation + dispatch resolution ──
        print("── routing application ──")
        r = C.post("/api/tasks", json={"title": f"[GATE-SETTINGS] {probe}",
                                       "description": "settings gate probe",
                                       "model": "totally-unknown-model"})
        chk("unknown task model rejected", r.status_code == 400, r.text[:100])
        r = C.post("/api/tasks", json={"title": f"[GATE-SETTINGS] {probe}",
                                       "description": "settings gate probe",
                                       "status": "backlog",
                                       "model": f"{probe}-m1",
                                       "depends_on": []})
        chk("registry model accepted on a task", r.status_code == 200, r.text[:150])
        task_id = r.json().get("id")
        import hermes_dispatch as hd
        chk("dispatch resolves explicit model",
            hd.resolve_task_model({"model": f"{probe}-m1", "user_id": "u_owner"})
            == f"{probe}-m1")
        chk("dispatch resolves owner default for NULL model",
            hd.resolve_task_model({"model": None, "user_id": "u_owner"})
            == db.default_task_model("u_owner"))

        # session-keys bridge (scratch file — never the live bridge)
        scratch = Path(os.environ.get("TMPDIR", "/tmp")) / f"gate-session-keys-{probe}.json"
        orig_file = hd._SESSION_KEYS_FILE
        hd._SESSION_KEYS_FILE = str(scratch)
        try:
            hd.publish_session_key(f"api_gate_{probe}", "u_owner", f"{probe}-m1")
            data = json.loads(scratch.read_text())
            chk("bridge entry carries the owner's key",
                data["sessions"][f"api_gate_{probe}"]["api_key"] == probe_key, str(data)[:120])
            chk("bridge file is 0600", oct(scratch.stat().st_mode & 0o777) == "0o600")
            hd.remove_session_key(f"api_gate_{probe}")
            chk("bridge entry removed at finalize",
                f"api_gate_{probe}" not in json.loads(scratch.read_text())["sessions"])
            hd.publish_session_key(f"api_gate2_{probe}", "u_owner", "glm-5.2")
            chk("no credential for provider = no bridge entry (env default)",
                f"api_gate2_{probe}" not in json.loads(scratch.read_text()).get("sessions", {}))
        finally:
            hd._SESSION_KEYS_FILE = orig_file
            scratch.unlink(missing_ok=True)

        # ── 5. Judge model + env plumbing (stubbed judge.cmd) ──
        print("── frontier judge ──")
        import evals as ev
        jm, _jk = ev.judge_model_for("u_owner")
        chk("owner's judge purpose resolves to a cli model", bool(jm), str(jm))
        stub = Path(os.environ.get("TMPDIR", "/tmp")) / f"gate-judge-stub-{probe}.sh"
        stub.write_text("#!/bin/bash\necho \"model-token=$2 env-model=${JUDGE_MODEL:-none} "
                        "env-key=${JUDGE_ANTHROPIC_API_KEY:-none}\"\necho 'VERDICT: SHIP'\n")
        stub.chmod(0o755)
        deliv = Path(os.environ.get("TMPDIR", "/tmp")) / f"gate-judge-deliv-{probe}.md"
        deliv.write_text("gate probe deliverable")
        prev_judge = db.get_setting("judge.cmd")
        try:
            db.set_setting("judge.cmd", f"{stub} {{file}} {{model}}")
            out = ev.run_judge_cmd(str(deliv), "marketing",
                                   model="claude-opus-4-8", api_key="sk-gate-judge")
            chk("{model} token replaced in judge.cmd", "model-token=claude-opus-4-8" in out, out[:150])
            chk("JUDGE_MODEL exported to the judge", "env-model=claude-opus-4-8" in out)
            chk("per-user key exported to the judge", "env-key=sk-gate-judge" in out)
            out = ev.run_judge_cmd(str(deliv), "marketing")
            chk("legacy call (no model) stays clean",
                "env-model=none" in out and "env-key=none" in out, out[:150])
        finally:
            db.set_setting("judge.cmd", prev_judge or "cjudge {file} {domain}")
            stub.unlink(missing_ok=True)
            deliv.unlink(missing_ok=True)
        chk("judge.cmd restored",
            db.get_setting("judge.cmd") == (prev_judge or "cjudge {file} {domain}"))

    finally:
        # ── cleanup (idempotent — safe on partial failure) ──
        import database as db
        if task_id:
            C.delete(f"/api/tasks/{task_id}")
        if prev_easy_override:
            C.put("/api/models/assignments", json={"easy": None})
        if model_id:
            C.delete(f"/api/models/{model_id}")
        if cred_id:
            C.delete(f"/api/credentials/{cred_id}")
        db.execute("DELETE FROM credentials WHERE id='cred-gate-foreign'")
        db.execute("DELETE FROM user_models WHERE id='mdl-gate-foreign'")
        db.execute("DELETE FROM tasks WHERE title LIKE '[GATE-SETTINGS]%'")
        if prev_cost:
            C.patch("/api/settings", json={"cost.per_1m_tokens": prev_cost})
        else:
            C.patch("/api/settings", json={"cost.per_1m_tokens": ""})

    # cleanup proof
    r = C.get("/api/models")
    chk("cleanup: no probe models left", probe not in json.dumps(r.json()))
    r = C.get("/api/credentials")
    chk("cleanup: no probe credentials left", probe not in json.dumps(r.json()))

    print(f"\nSETTINGS V2 GATE: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
