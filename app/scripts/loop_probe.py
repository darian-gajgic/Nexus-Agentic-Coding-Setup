#!/usr/bin/env python3
"""Runtime gate: event-loop responsiveness (stability audit §3.1).

Polls a cheap async endpoint (/api/activity?limit=1 — the loop canary)
every 50 ms, first idle (baseline), then while every formerly-blocking
endpoint runs concurrently (storm). The loop is de-blocked iff the
canary's max latency stays far below the slowest heavy call — a blocked
loop would stall the canary for the heavy call's full duration.

Usage: .venv/bin/python scripts/loop_probe.py   (server must be running)
"""
import statistics
import sys
import threading
import time

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from _gate_auth import owner_cookie  # noqa: E402

BASE = "https://127.0.0.1:8777"
CK = owner_cookie()


def get(path, timeout=120):
    return requests.get(BASE + path, timeout=timeout, verify=False, cookies=CK)


def post(path, timeout=120, **kw):
    return requests.post(BASE + path, timeout=timeout, verify=False, cookies=CK, **kw)


def poll(stop, lat):
    while not stop.is_set():
        t0 = time.perf_counter()
        r = get("/api/activity?limit=1", timeout=30)
        lat.append((time.perf_counter() - t0, r.status_code))
        time.sleep(0.05)


def stats(lat):
    ms = sorted(x[0] * 1000 for x in lat)
    bad = [c for _, c in lat if c != 200]
    return (f"n={len(ms)} p50={statistics.median(ms):.0f}ms "
            f"p95={ms[int(len(ms) * 0.95)]:.0f}ms max={max(ms):.0f}ms "
            f"non200={len(bad)}")


def main() -> int:
    tasks = get("/api/tasks").json()
    review_target = next((t["id"] for t in tasks
                          if t.get("workspace_path") and t.get("status") == "done"), None)

    heavy = [
        ("GET /api/memory3d?force=1", lambda: get("/api/memory3d?force=1")),
        ("POST /api/usage/refresh", lambda: post("/api/usage/refresh")),
        ("GET /api/deliverables", lambda: get("/api/deliverables")),
        ("GET /api/tools", lambda: get("/api/tools")),
        ("GET /api/skills", lambda: get("/api/skills")),
        ("GET /api/projects", lambda: get("/api/projects")),
    ]
    if review_target:
        heavy.append((f"GET /api/tasks/{review_target}/review",
                      lambda: get(f"/api/tasks/{review_target}/review")))

    lat_a, stop = [], threading.Event()
    t = threading.Thread(target=poll, args=(stop, lat_a))
    t.start(); time.sleep(3); stop.set(); t.join()
    print(f"[baseline ] {stats(lat_a)}")

    lat_b, stop = [], threading.Event()
    t = threading.Thread(target=poll, args=(stop, lat_b))
    results = {}

    def fire(name, fn):
        t0 = time.perf_counter()
        try:
            r = fn()
            results[name] = (r.status_code, time.perf_counter() - t0, len(r.content))
        except Exception as e:
            results[name] = ("EXC:" + str(e)[:60], time.perf_counter() - t0, 0)

    t.start()
    workers = [threading.Thread(target=fire, args=hf) for hf in heavy]
    [w.start() for w in workers]
    [w.join() for w in workers]
    time.sleep(0.5)
    stop.set(); t.join()

    print(f"[storm     ] {stats(lat_b)}")
    for name, (code, dur, size) in sorted(results.items(), key=lambda kv: -kv[1][1]):
        print(f"  heavy: {name:45s} -> {code}  {dur * 1000:6.0f}ms  {size}B")

    slowest = max(dur for _, dur, _ in results.values())
    pmax = max(x[0] for x in lat_b)
    ok = pmax < max(0.3, slowest * 0.25)
    print(f"\nslowest heavy call: {slowest * 1000:.0f}ms | "
          f"poller max during storm: {pmax * 1000:.0f}ms")
    print("LOOP-FREE" if ok else "LOOP-BLOCKED?")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
