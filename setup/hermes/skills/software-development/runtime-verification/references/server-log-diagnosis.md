# Server-Log Diagnosis of Intermittent Failures

When a user reports a bug that **does not reproduce in your controlled test
harness**, the production server logs are the fastest path to root cause.
Controlled tests fire requests sequentially or in low volume; production usage
creates concurrency, timing pressure, and resource contention that expose
failures your tests can't trigger.

## When to use this

- User says "it's slow / delayed / sometimes breaks" but your single-call test works fine.
- The bug is intermittent — works on the first call, fails on follow-ups.
- You see GPU/CPU spikes in monitoring but can't explain the behavior from code alone.
- You've tried 2+ code fixes and the user still reports the problem.

## The technique

### 1. Read the server's actual request log

The server logs every HTTP request with status code. Scan for the failing
pattern:

```bash
# systemd service
journalctl --user -u <service> --since "20 min ago" --no-pager | grep -E "<endpoint>.*(500|error)"

# Or the Hermes background process log
# process(action='log', session_id=<id>)
```

**What you're looking for:** the STATUS CODE PATTERN across a burst of
requests, not just individual errors. The critical signal is often the
*sequence* — e.g. a combined endpoint returning 500 while its component
endpoints succeed:

```
POST /api/combined   → 500 Error    ← path A failed under load
POST /api/component   → 200 OK      ← path B succeeded, its output played
POST /api/combined   → 200 OK      ← retry succeeded 5s later
```

This sequence tells you: one path fails, another succeeds, and the user sees
the successful path's output immediately but the failed path's output delayed.
That gap IS the reported bug.

### 2. Correlate the 500s with the user's symptom

Map each log entry to what the user observed:
- `/component` succeeds → its output plays immediately
- `/combined` 500s → the combined feature degrades (e.g. fallback to audio-only)
- `/combined` eventually succeeds → the delayed feature appears late

The time between the first success and the first combined success is the
visible delay the user reported.

### 3. Reproduce the concurrency that triggers it

Intermittent 500s under load are caused by **resource contention**:
- GPU lock contention (two model inferences hitting the same lock)
- VRAM exhaustion (multiple subprocess model loads in parallel)
- Database connection pool exhaustion
- File handle / temp file races

Fire concurrent requests matching the real usage pattern:

```python
import threading, subprocess
results = {}
def call(i):
    r = subprocess.run(["curl","-sk","-X","POST",url,"-d",body,
        "-w","%{http_code}","--max-time","120"], capture_output=True, text=True)
    results[i] = r.stdout.strip()
threads = [threading.Thread(target=call, args=(i,)) for i in range(1,6)]
for t in threads: t.start()
for t in threads: t.join()
fails = [i for i in range(1,6) if results[i] != "200"]
```

If the controlled sequential test passes but the concurrent test fails → you've
found the trigger. Now read the server error for the actual exception.

### 4. Read the actual error body

```bash
curl -sk -X POST <url> -H "Content-Type: application/json" -d '<body>' --max-time 60
# If it returns binary (success), trigger under concurrent load to force the 500
```

The 500 response body contains the real exception (OOM, lock timeout,
RuntimeError). Read it completely — it names the exact resource that failed.

## Common root cause: double-work from parallel combined + component calls

A combined endpoint (e.g. `/talk` = TTS synthesis + lip-sync render) that
internally calls the same model as a standalone endpoint (`/tts`) will **double
the GPU work** when the frontend calls both in parallel. Each sentence triggers
TTS twice, competing for the same `_tts_lock`, plus a Wav2Lip subprocess — all
piling up. Under this pressure, the combined endpoint intermittently 500s and
the frontend falls back to the component-only path (audio without face).

**Fix:** call the combined endpoint ONCE. If you need both audio and video,
the muxed output already contains both tracks — play the same blob in a muted
`<video>` (face) and an `<audio>` element (voice). No double synthesis, no lock
contention.

**General principle:** never call a combined endpoint AND its component
endpoints in parallel — the combined one already does the component's work
internally, so you're paying for it twice and creating contention. When
converting a frontend from "split fetch" to "combined fetch," also check that
the combined endpoint isn't internally re-doing the component's work — if it
is, the double-work persists server-side even after the frontend calls only
once. In the `/talk` case, `/talk` internally calls `synthesize()` then
`render_bytes()`, so a single `/talk` call is the correct unit.

## Anti-pattern: theorizing without logs

The most expensive mistake is to read the code, form a theory about why it's
slow, and start patching — without ever looking at the server logs. The logs
tell you exactly which request failed and when. Code-reading gives you
plausible-sounding theories that may not match reality.

**Always:** before proposing a fix for an intermittent bug, read the server
logs and identify the exact failing request + error. Then your fix targets the
real cause, not a theory.

## Anti-pattern: building an idle-unload feature and forgetting to test reload

When adding idle model unloading (free GPU memory after N seconds of
inactivity), the unload path is easy to test but the **reload** path is the one
that actually matters for correctness. A model that unloads but doesn't
re-load on the next request breaks the feature silently — the first request
after idle works (model was still loaded), the second fails, and the user
reports "it stopped working after a minute."

Test the full cycle: trigger a call → confirm loaded → wait past timeout →
confirm unloaded → trigger another call → confirm reloaded. (2026-07-05:
nexus-agent-os voice model idle-unload — verified unload at ~72s and verified
reload on the next /tts call.)
