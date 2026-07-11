#!/usr/bin/env python3
"""E2E gate for the STT consolidation (one whisper for the whole machine).

Proves against the LIVE service:
  1. TTS→STT round trip: Piper speaks a phrase, the shared STT worker
     transcribes it back (browser path: bytes → tempfile → worker → text).
  2. Warm endpoint: /api/jarvis/stt/warm loads the model in the background;
     status reports it; the worker subprocess exists (and holds VRAM on cuda).
  3. Kill/respawn: SIGKILL the worker mid-idle → the next request respawns it
     and still answers (one retry allowed if the kill races a request).
  4. Idle kill: shrink voice.stt_idle_timeout → the 15s unloader kills the
     worker → whisper VRAM is 0. Setting restored afterwards.
  5. Device round trip: force voice.stt_device=cpu → transcribe works, engine
     reports cpu → restore (next spawn returns to cuda).
  6. Dictation/meetings API: status shape, meetings list, name validation,
     delete-404, live guard.

Run: ~/nexus-agent-os/.venv/bin/python scripts/verify_stt_e2e.py
Self-cleaning: settings PATCHed back to "" (default) in finally blocks.
"""
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.expanduser("~/nexus-agent-os")
sys.path.insert(0, ROOT)
sys.path.insert(0, ROOT + "/scripts")
import httpx
import urllib3
urllib3.disable_warnings()
import auth

BASE = "https://127.0.0.1:8777"
P, F = 0, 0


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  PASS  {name}")
    else:
        F += 1
        print(f"  FAIL  {name}  {extra}")


def worker_pids():
    try:
        out = subprocess.run(["pgrep", "-f", "stt_worker.py"],
                             capture_output=True, text=True, timeout=5)
        return [int(x) for x in out.stdout.split()]
    except Exception:
        return []


def nvidia_pids():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        pids = {}
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 2 and parts[0].isdigit():
                pids[int(parts[0])] = int(parts[1])
        return pids
    except Exception:
        return {}


def status(c):
    return c.get("/api/jarvis/voice/status").json()


def transcribe(c, wav_bytes):
    return c.post("/api/jarvis/stt",
                  files={"file": ("probe.wav", wav_bytes, "audio/wav")},
                  timeout=180).json()


def main():
    token = auth.create_session("u_owner", "stt-e2e-probe")
    c = httpx.Client(base_url=BASE, verify=False, timeout=180)
    c.cookies.set("nexus_session", token)
    phrase = "testing one two three, the quick brown fox jumps over the lazy dog"

    try:
        # ── 1. fixture-free round trip: TTS speech IS the STT fixture ──
        r = c.post("/api/jarvis/tts", json={"text": phrase}, timeout=120)
        ok("TTS produced a WAV fixture", r.status_code == 200 and r.content[:4] == b"RIFF",
           f"status={r.status_code}")
        wav = r.content
        t0 = time.time()
        j = transcribe(c, wav)
        text = (j.get("text") or "").lower()
        ok("STT round trip returns text", bool(text), str(j)[:200])
        ok("transcript matches the phrase",
           "quick brown fox" in text and ("one" in text or "1" in text),
           repr(text))
        print(f"        (round trip {time.time() - t0:.1f}s -> {text[:60]!r})")

        st = status(c)
        ok("status: worker alive + loaded",
           st.get("stt_worker_alive") is True and st.get("stt_loaded") is True, str(st))
        ok("status: engine is the worker",
           "[worker]" in (st.get("stt_engine") or ""), st.get("stt_engine", ""))
        pids = worker_pids()
        ok("stt_worker subprocess exists", len(pids) >= 1, str(pids))
        if "cuda" in (st.get("stt_engine") or "") and pids:
            vram = nvidia_pids()
            held = any(p in vram and vram[p] > 500 for p in pids)
            ok("worker holds VRAM on cuda (>500MiB)", held,
               f"pids={pids} vram={vram}")

        # ── 2. warm endpoint (idempotent while loaded) ──
        w = c.post("/api/jarvis/stt/warm").json()
        ok("warm endpoint answers", w.get("loaded") is True or w.get("warming") is True, str(w))

        # ── 3. kill -9 → respawn on next request ──
        for p in worker_pids():
            os.kill(p, 9)
        time.sleep(1)
        j = transcribe(c, wav)
        if j.get("error"):  # the kill may race an in-flight touch — one retry
            j = transcribe(c, wav)
        ok("after SIGKILL the next request respawns + answers",
           "quick brown fox" in (j.get("text") or "").lower(), str(j)[:200])
        ok("fresh worker pid", len(worker_pids()) >= 1, str(worker_pids()))

        # ── 4. idle kill via voice.stt_idle_timeout (60 = the registry minimum) ──
        try:
            r = c.patch("/api/settings", json={"voice.stt_idle_timeout": "60"})
            ok("idle timeout PATCHed to 60s", r.status_code == 200, r.text[:100])
            gone = False
            for _ in range(20):   # ≤100s: 60s idle + 15s unloader tick + margin
                time.sleep(5)
                if not worker_pids():
                    gone = True
                    break
            ok("worker killed after idle (VRAM freed)", gone, str(worker_pids()))
            if gone:
                whisper_vram = [p for p in nvidia_pids() if p in worker_pids()]
                ok("no whisper VRAM after idle kill", not whisper_vram, str(whisper_vram))
                st = status(c)
                ok("status reflects unloaded worker",
                   st.get("stt_worker_alive") is False, str(st))
        finally:
            c.patch("/api/settings", json={"voice.stt_idle_timeout": ""})

        # ── 5. device round trip (cpu force → restore) ──
        try:
            c.patch("/api/settings", json={"voice.stt_device": "cpu"})
            j = transcribe(c, wav)
            st = status(c)
            ok("cpu-forced transcribe works",
               "quick brown fox" in (j.get("text") or "").lower(), str(j)[:200])
            ok("engine reports cpu", "(cpu" in (st.get("stt_engine") or ""),
               st.get("stt_engine", ""))
        finally:
            c.patch("/api/settings", json={"voice.stt_device": ""})

        # ── 6. dictation + meetings API ──
        d = c.get("/api/dictation/status").json()
        ok("dictation status shape",
           "available" in d and ("state" in d or d.get("available") is False), str(d))
        m = c.get("/api/meetings").json()
        ok("meetings list answers", isinstance(m.get("meetings"), list), str(m)[:200])
        r = c.get("/api/meetings/..%2Fetc%2Fpasswd")
        ok("meeting name validation rejects traversal", r.status_code in (400, 404),
           f"status={r.status_code}")
        r = c.get("/api/meetings/meeting-does-not-exist.md")
        ok("missing meeting -> 404", r.status_code == 404, f"status={r.status_code}")
        r = c.delete("/api/meetings/meeting-does-not-exist.md")
        ok("delete missing -> 404", r.status_code == 404, f"status={r.status_code}")

        # ── 7. D4 keepalive + inactivity kill (bugfix 2026-07-12 [26][27]) ──
        # In-process against voice.py: a PRIVATE worker spawns inside THIS gate
        # process, so the stall knobs never touch the server's worker. Proves
        # (i) a long silent decode that emits keepalives survives a tiny
        # inactivity window, (ii) a silent worker is killed promptly + raises.
        import numpy as np
        import voice as _v
        _sr = 16000
        _pcm = (0.2 * np.sin(2 * np.pi * 440.0
                             * np.arange(int(0.8 * _sr)) / _sr)).astype("float32")
        _old_kill = _v.STT_INACTIVITY_KILL_S
        try:
            # knobs must be in the env BEFORE the worker spawns (inherited)
            os.environ["NEXUS_STT_TEST_STALL_S"] = "20"
            _v.warm_stt()
            _t0 = time.time()
            while not _v._stt_loaded and time.time() - _t0 < 150:
                time.sleep(1)
            ok("D4: private gate worker warmed", _v._stt_loaded)
            _v.STT_INACTIVITY_KILL_S = 8.0
            try:
                _v.transcribe_pcm(_pcm, sample_rate=_sr)
                ok("D4: 20s stall WITH keepalives survives an 8s inactivity timer", True)
            except Exception as e:  # noqa: BLE001
                ok("D4: 20s stall WITH keepalives survives an 8s inactivity timer",
                   False, repr(e))
            # silent variant needs a fresh worker that inherits the knob
            _v.STT_INACTIVITY_KILL_S = _old_kill
            _v._kill_stt_worker("gate: respawn with silent-stall knob")
            os.environ["NEXUS_STT_TEST_STALL_SILENT"] = "1"
            _v.warm_stt()
            _t0 = time.time()
            while not _v._stt_loaded and time.time() - _t0 < 150:
                time.sleep(1)
            _v.STT_INACTIVITY_KILL_S = 8.0
            _killed = False
            _t1 = time.time()
            try:
                _v.transcribe_pcm(_pcm, sample_rate=_sr)
            except RuntimeError:
                _killed = True
            ok("D4: silent 20s stall -> inactivity kill + RuntimeError",
               _killed and time.time() - _t1 < 19,
               f"killed={_killed} elapsed={time.time() - _t1:.1f}s")
        finally:
            _v.STT_INACTIVITY_KILL_S = _old_kill
            os.environ.pop("NEXUS_STT_TEST_STALL_S", None)
            os.environ.pop("NEXUS_STT_TEST_STALL_SILENT", None)
            _v._kill_stt_worker("gate cleanup")

    finally:
        c.close()

    print(f"\n  {'ALL PASSED' if F == 0 else 'FAILURES'}: {P} passed, {F} failed")
    return 1 if F else 0


if __name__ == "__main__":
    raise SystemExit(main())
