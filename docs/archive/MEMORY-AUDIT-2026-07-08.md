# Nexus Agent OS — GPU/RAM Memory-Management Audit

**Date:** 2026-07-08 · **Machine:** RTX 5070 Ti 12 GB (12227 MiB VRAM) · 30 GiB RAM + 8 GiB swap
**Method:** live system measurement (13:47–14:13) + a 6-subsystem code read of `app/` + an adversarial fact-check pass, all cross-verified against the running process. **Report only — no code or config was changed.**

> **Two honesty notes up front**
> 1. **`nexus.service` restarted at 13:55:50, in the middle of this audit — I did not do it.** All my commands were read‑only, and my analysis sub‑agents' command logs contain no restart. It was not a systemd auto‑restart (`NRestarts=0`), so it came from outside my work (you, or one of the several other `claude` sessions running on this box). It matters only because it reset the `main.py` RAM baseline mid‑measurement — which, as it happens, gave us the single most useful data point (see §4).
> 2. Numbers below are real measurements. Where something is inferred rather than measured, it is marked **(inferred)**.

---

## 1. TL;DR — your two questions answered

**Q1 — "When a local LLM is loaded for a task and finishes, does it unload from the GPU again to free space?"**
**Mostly yes — the unloading machinery works — but one path lets big models camp, and that is what fills your card.**

- **ollama models self‑expire.** I watched the two `llama-server` processes vanish on their own between two snapshots (`/api/ps` went from loaded → `{"models":[]}` with no intervention). Ollama's default 5‑minute `keep_alive` works.
- **The vision VLM (`qwen3-vl:8b`) is the best‑behaved path** — 30 s `keep_alive` *plus* an explicit `keep_alive:0` evict the instant a look‑turn ends and before image‑gen loads (`vision.py:290,319‑332`; `server.py:2148‑2153`).
- **The SigLIP/OCR/SDXL worker frees VRAM by process death** (SIGKILL → the CUDA driver reclaims everything). Clean.
- **Voice Whisper STT** unloads its weights after 300 s idle (`voice.py:325‑333`).
- **The gap:** the **mem0 memory model (`llama3.1:8b`, ~3.4 GB) has no `keep_alive` set** and **`OLLAMA_MAX_LOADED_MODELS` is unset**, so several models are allowed to sit in VRAM at once for up to 5 minutes after each memory write. **That, not a stuck GPU, is your "VRAM at max."**

**Q2 — "Is there a memory leak, or does something need optimising?"**
**No classic Python‑object leak — but there IS a real native‑memory ratchet in `main.py` that behaves like a leak, and the box is genuinely over‑committed (the OOM killer already fired today).**

- I measured the live `main.py`: its Python `[heap]` is only **82 MB**, while anonymous mmap arenas hold **2106 MB**. That ratio is the fingerprint of **glibc malloc‑arena fragmentation** (native buffers from in‑process Whisper/PyAV/onnxruntime spread across ~48–72 threads that never get returned to the OS) — **not** a runaway Python data structure. It climbed **286 MB → 2.35 GB in ~18 min** after the 13:55 restart and reached **3.86 GB / 4.9 GB RSS** on the older instance.
- **A system‑wide OOM already fired at 07:02:35 today** (`global_oom`, `CONSTRAINT_NONE`); its victim was **WisprFlow** (4.5 GB). **Swap is 100 % full and never drains.** The machine is living at the OOM boundary.
- **Biggest single fixable Nexus item:** the `main.py` native ratchet. **Biggest absolute RAM on the box is *not* Nexus** — the Claude Code harness (~6.5 GB across 41 procs) and WisprFlow are larger contributors.

**Highest‑leverage fixes (all report‑only, none applied):**
1. `OLLAMA_MAX_LOADED_MODELS=1` (+ optional `OLLAMA_KEEP_ALIVE`) — stops the VRAM pile‑up. *Minutes, no code.*
2. `MALLOC_ARENA_MAX=2` (or `LD_PRELOAD` jemalloc/tcmalloc) on `nexus.service` — targets the native ratchet. *One line; A/B to confirm the win.*
3. Add `keep_alive` to the Hermes‑side mem0 model — frees ~3.4 GB promptly after each memory write.
4. Relieve host RAM (WisprFlow / Claude `bg-spare` count) so the box stops sitting at the OOM edge.

---

## 2. What you actually observed — reproduced and decomposed

Your description ("VRAM at max, GPU idle; RAM full") is **exactly right**, and it reproduced live at **14:13** while I was writing this:

**VRAM: 10888 / 12227 MiB (89 %), GPU‑util 2 %, 20 W.** Per‑process:

| Process | VRAM | Nexus? | What it is |
|---|---:|---|---|
| WisprFlow `wf_daemon.py` | 3272 MiB | **No — external** | Voice dictation app; permanent pin (~27 % of the card) |
| ollama `llama-server` (`llama3.1:8b`) | 3444 MiB | No — Hermes **mem0** | The memory model, resident on default keep‑alive |
| `main.py` (voice Whisper STT + CUDA ctx) | 2024 MiB | **Yes** | ~1.5 GB Whisper + ~0.16 GB CUDA context |
| `vision_worker.py` (SigLIP) | 1992 MiB | **Yes** | Vision embedder, active |
| ollama runner stub | 10 MiB | — | — |

**Key correction to first impressions:** the "at max" state is **mem0's `llama3.1:8b` + Whisper + SigLIP + WisprFlow co‑resident** — the **VLM (`qwen3-vl`) was not even loaded**. GPU‑util 2 % means the card is *idle between requests*, not wedged: **loaded ≠ busy.** A model sitting in VRAM with no in‑flight tokens shows ~0 % util and a low power state (P8). Nothing is stuck; several things are simply *resident at once*.

**Why it looks permanent:** two of the four are effectively always‑on (WisprFlow is external and never unloads; mem0's model reloads on every memory write and then camps 5 min), so the floor rarely drops below ~6.7 GB even at "idle."

**RAM (14:13): 18 GiB used, 11 GiB available, swap 8/8 GiB full.** Earlier in the audit it was 28 GiB used. **Swap stays 100 % full even when RAM frees** — that is normal Linux behaviour (anonymous pages paged out under the earlier pressure aren't proactively faulted back in). Swap‑full here is a *lag indicator of the morning's OOM‑level pressure*, not live thrashing.

---

## 3. Q1 in detail — GPU / VRAM unload behaviour per model class

| Model | Owner / process | VRAM | Unloads when done? | Verdict |
|---|---|---:|---|---|
| **VLM `qwen3-vl:8b`** | Nexus `vision.py` → ollama | ~6–8 GB | **Immediately** — 30 s keep‑alive + explicit `keep_alive:0` evict | ✅ **Best‑disciplined path** (`vision.py:290,319‑332`; `server.py:2148‑2153`) |
| **SigLIP + OCR + SDXL** | Nexus `vision_worker.py` (subprocess) | ~1–2 GB | **On idle‑kill** — SIGKILL → CUDA reclaims on exit | ✅ Works (`vision.py:110‑120`) |
| **Whisper STT `medium.en`** | Nexus `main.py` (in‑process) | ~1.5 GB | **After 300 s idle** (weights only) | ✅ Weights free; ⚠️ ~158 MiB CUDA context never frees until process exit (`voice.py:17‑27,325‑333`) |
| **Piper TTS** | Nexus `main.py` | **0 (CPU)** | n/a | ✅ |
| **mem0 `llama3.1:8b`** | Hermes mem0 → ollama | ~3.4 GB | **Default 5 min, re‑touched on every memory write** | ⚠️ **No `keep_alive` set → effectively always‑hot** |
| **mem0 `nomic-embed-text`** | Hermes mem0 → ollama | ~0.4 GB | Default 5 min | ⚠️ Tiny but hot (touched on every recall) |

**The two config gaps that produce "VRAM at max"** (both outside Nexus's own code):
- `OLLAMA_MAX_LOADED_MODELS` **unset** → ollama will hold *several* models resident simultaneously. Only `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q4_0` are set on the unit; `OLLAMA_KEEP_ALIVE` and `OLLAMA_NUM_PARALLEL` are also unset.
- mem0's model has no `keep_alive` in `~/.hermes/mem0.json` → 3.4 GB camps for 5 min after each memory write, and memory writes are frequent, so it's essentially pinned.

### VRAM budget — 12227 MiB card

| Scenario | WisprFlow | main.py (STT+ctx) | mem0 LLM | nomic | VLM | vision worker | **Total** | Fit? |
|---|---:|---:|---:|---:|---:|---:|---:|:--:|
| Idle (measured 13:50) | 3304 | 158 | – | – | – | – | **3489** | ✅ |
| **"At max" (measured 14:13)** | 3272 | 2024 | 3444 | – | – | 1992 | **~10888** | ⚠️ 89 % |
| Worst case (VLM turn + memory flush) | ~3300 | ~2000 | ~3400 | ~400 | ~7000 | ~2000 | **~18 GB** | ❌ oversubscribed → CPU‑offload / OOM |

Headroom in the "at max" state is ~1.3 GB. A VLM describe on top of that is what tips ollama into partial CPU‑offload (the code comments at `vision.py:300‑302` already anticipate this).

---

## 4. Q2 in detail — the `main.py` native ratchet (the real RAM story)

**What it is NOT:** a Python‑object leak. The code read cleared every candidate — SSE/chat streams forward‑and‑free (`server.py:2098‑2111`), image/base64 blobs are decoded per request and dropped (`server.py:1975,2011‑2022`), the JARVIS session store is file‑backed metadata (`server.py:1586‑1608`), metrics are pruned and `nexus.db` is ~2.5 MB (`agent_manager.py:222‑223`). There is no unbounded dict/list.

**What it IS — measured directly on the live process (PID 1514126):**

```
RSS 2.35 GB · Private_Dirty 2.29 GB · Anonymous 2.25 GB · 72 threads
[heap]  Rss:   82 MB     ← Python object heap (small)
anon rw-p Rss: 2106 MB   ← glibc malloc arenas + native buffers (the ratchet)
```

An 82 MB Python heap next to 2.1 GB of anonymous mmap arenas is the textbook signature of **glibc per‑thread arena fragmentation**. The driver: **`import voice` at module scope (`server.py:1567`)** pulls the whole faster‑whisper → ctranslate2 + PyAV(ffmpeg) + onnxruntime + CUDA stack into the web server, and repeated STT + per‑call audio/image decode run through `asyncio.to_thread` across dozens of executor threads. Each thread's arena grows to its high‑water mark and glibc never trims it back to the OS.

**Growth proof (the silver lining of the 13:55 restart):** the fresh process started at **286 MB** and climbed to **2.35 GB in ~18 min**; the older instance was at **3.86–4.9 GB**. *Caveat:* that 18‑min rate was under audit‑induced load (my sub‑agents exercised endpoints), so treat the **rate** as an upper bound — but the **mechanism** (native arenas, not Python) is confirmed by the heap/anon split, and it is **only released by a restart**, exactly as observed.

### RAM breakdown — 30 GiB total (who's actually at fault)

| Consumer | RAM | Nexus? | Note |
|---|---:|:--:|---|
| **`main.py`** | 2.4 → 4.9 GB (ratchets) | **Yes** | The native arena ratchet. **The one big fixable Nexus item.** |
| `vision_worker.py` | 1.5–3.4 GB (while alive) | Yes | Reloads ~1.7 GB SigLIP on each respawn |
| 9 × `worker.py` lanes | ~0.25–0.33 GB total | Yes | Lean; 2 are dead E2E test lanes to retire |
| **Nexus cgroup total** | **`current` 8.8 GB / `peak` 12.0 GB** | Yes | — |
| **Claude Code harness** | **~6.5 GB** (26 `claude` + 15 `bg-spare`) | **No** | Largest non‑Nexus RSS (much shared) |
| WisprFlow | ~1–4.5 GB RAM + 3.3 GB VRAM | **No** | Also the 07:02 OOM victim |
| firefox / next-server / clickhouse / hermes gw | ~2 / ~1 / 0.56 / 0.66 GB | No | Other tenants of the same 30 GiB |

**The OOM that already happened:** `07:02:35 … global_oom, CONSTRAINT_NONE … Killed process 3300181 (python) … anon-rss:4574028kB` — that was **WisprFlow**. Nexus's `main.py` *contributes to* the over‑commit that caused it; it was not the direct victim.

---

## 5. Ranked findings

| # | Sev | Subsystem | Type | Finding & impact | Evidence |
|--:|:--:|---|---|---|---|
| 1 | **HIGH** | `main.py` / voice | native ratchet | 2.1 GB (→4.9 GB) of anon mmap arenas from in‑process Whisper/PyAV across many threads; freed only by restart; contributes to the 07:02 OOM. **Confirmed native, not Python.** | measured `[heap]` 82 MB vs anon 2106 MB; `server.py:1567`; `voice.py:17‑27,107‑118` |
| 2 | **HIGH** | ollama config | VRAM pile‑up | `OLLAMA_MAX_LOADED_MODELS` unset + mem0 model has no `keep_alive` → multiple models co‑resident; **this is the "VRAM at max"** (89 % measured, VLM not even loaded). | live 14:13 snapshot; `~/.hermes/mem0.json`; ollama unit env |
| 3 | **MEDIUM** | vision supervision | respawn thrash | `vision_worker` respawned 3× in 11 min while in active use — **too fast for the 600 s idle timer**, so something kills it sub‑timeout. Cause **unconfirmed** (stderr → `DEVNULL` at `vision.py:78` hides it); memory‑pressure OOM‑kill is the leading hypothesis, not proven. Each respawn reloads ~1.7 GB. VRAM itself frees correctly each cycle. | PIDs 1421054/1478880/1485931; `vision.py:44,78,88‑97,110‑120` |
| 4 | **MEDIUM** | Hermes mem0 | no‑unload (config) | `llama3.1:8b` (+nomic) camp ~5 min after every memory write; ~3.8 GB effectively always‑hot. **Lives in `~/.hermes/mem0.json`, not this repo.** | `mem0.json` (no keep_alive key) |
| 5 | **MEDIUM** | `main.py` / voice | oversized baseline | `import voice` at module scope loads Whisper/PyAV/onnxruntime/CUDA into the HTTP server (~200 MB RAM + 158 MiB VRAM it never needs) — the substrate for #1. Vision already avoids this via subprocess. | `server.py:1567`; `voice.py:13,18‑31` |
| 6 | **MEDIUM** | vision | wrong‑direction fallback | SigLIP CUDA→CPU self‑heal reloads as fp32 (~1.7→3.4 GB) into system RAM after a CUDA OOM — trades the *abundant* resource (VRAM self‑frees) for the *scarce* one (RAM) on this box; makes the worker a fatter OOM target (feeds #3). Bounded per worker‑life. | `vision_worker.py:42‑55,74‑87` |
| 7 | **LOW** | worker fleet | oversized baseline | 9 always‑resident `worker.py` lanes; **2 are dead E2E test lanes** (`E2E-Lane`, `E2E-Rival`) left `running`, respawned every boot. Zero VRAM. | agents table; `worker.py:162‑185` |
| 8 | **LOW** | spawn sites | unreaped‑child (pattern) | Kill‑without‑`wait()` in `vision.py:115`, `agent_manager.py:67,88,118`, `app_runner.py:65‑75` — relies on CPython lazy reaping. **The zombies visible right now are NOT Nexus's** (they belong to WisprFlow `wf-keylistener.py` and the desktop `speech-dispatcher`), but the pattern can produce transient Nexus zombies between vision kills. | code refs; live zombie parents 2245680=WisprFlow, 292184=speech-dispatcher |
| 9 | **LOW** | voice | no‑unload | ~158 MiB CUDA context in `main.py` never freed until exit (weights do unload). Fixed cost, not growing. | `voice.py:17‑27`; main.py=158 MiB idle |
| 10 | **LOW** | voice | timer coupling | STT & TTS share one `_last_voice_use`; frequent CPU‑TTS completion speech can keep the 1.5 GB GPU Whisper model resident past its idle window. | `voice.py:65,325‑333` |
| 11 | **LOW/race** | vision | race | Idle‑unloader (15 s thread) can SIGKILL a `>600 s` SDXL generate mid‑request → spurious 500 + needless respawn. Rare. | `vision.py:104‑120,329‑331` |

**Cleared — do NOT chase these:** SSE/chat buffering, base64 image retention, session‑store growth, DB bloat, an in‑process vector store, and the two live **zombies** (both external). `hermes_dispatch.py`/`tools_hub.py` are stateless per call.

---

## 6. Recommendations (report‑only — nothing applied)

### A. Config / env — highest leverage, no code (do first)
| Change | Where | Expected effect | Risk |
|---|---|---|---|
| `OLLAMA_MAX_LOADED_MODELS=1` (or `2` to keep the tiny embedder) | ollama systemd unit | Ends the multi‑model VRAM pile‑up; keeps 4–7 GB free | Medium — serializes local loads; a VLM turn evicts mem0's model → few‑sec cold reload next write |
| `OLLAMA_KEEP_ALIVE` (short, e.g. `2m`) + `OLLAMA_NUM_PARALLEL=1` | ollama systemd unit | Deterministic residency floor | Low |
| `MALLOC_ARENA_MAX=2` (or `LD_PRELOAD=libjemalloc`) | `Environment=` on `nexus.service` | Targets #1; can reclaim GBs by collapsing per‑thread arenas | Low — **A/B to confirm** the byte win before trusting it |
| Add `keep_alive` to mem0 model (+ consider nomic on CPU) | `~/.hermes/mem0.json` | Frees ~3.4 GB promptly after each memory write | Low‑Med (Hermes‑side; too aggressive adds reload latency) |

### B. Nexus code (this repo)
| Change | File:line | Effect | Risk |
|---|---|---|---|
| **Move voice STT+TTS into a subprocess** (mirror `vision_worker.py`) | `server.py:1567`; `voice.py` | Removes ~200 MB RAM + 158 MiB VRAM + the arena ratchet from the web server; reclaimed on idle by killing the child. **Fixes #1, #5, #9 together.** | Medium — needs JSON‑lines IPC, but the vision worker is a proven in‑repo template |
| Reap after every kill (`wait(timeout=2)` / `waitpid(WNOHANG)`) | `vision.py:115`; `agent_manager.py:67,88,118`; `app_runner.py:65‑75` | Removes the Nexus unreaped‑child pattern | Low (guard `ECHILD`; don't block the watchdog thread) |
| Retire the 2 dead E2E lanes; retire in a `finally` | `agent_manager.py:78‑106` | ~72 MB + 2 fewer poll loops | Low |
| Guard idle‑unload against in‑flight ops (in‑flight flag) | `vision.py:88‑120` | Kills the >600 s‑generate race (#11) | Low |
| Route `vision_worker` stderr to a log (not `DEVNULL`) | `vision.py:78` | No RAM saving, but makes #3's root cause finally diagnosable | Low |
| Reconsider SigLIP CPU fallback on this box (evict VLM + retry CUDA once; or cgroup `MemoryHigh` on the worker) | `vision_worker.py:42‑55,74‑87` | Avoids the +1.7 GB RAM step that feeds the OOM loop | Medium (could reintroduce SigLIP CUDA OOMs; test) |
| Smaller/CPU Whisper (`base.en`) or shorter STT idle; decouple STT/TTS timers | `voice.py:62,65,96` | ~1–1.5 GB VRAM headroom + smaller arena high‑water | Med (accuracy vs. reload trade‑off) |

### C. System / non‑Nexus — where the biggest absolute RAM lives
- **WisprFlow** pins 3.3 GB VRAM permanently and was the 07:02 OOM victim — if not actively needed, stopping it returns ~27 % of the card + several GB RAM. *(Not a Nexus component.)*
- **Claude Code harness** ~6.5 GB (26 `claude` + 15 `bg-spare`) — trimming the `bg-spare` pool recovers ~2 GB.
- **Swap** is 100 % full and won't drain — reduce resident pressure (above) rather than relying on swap; the box is over‑committed by *everything together*, not by Nexus alone.

**Priority:** (1) `OLLAMA_MAX_LOADED_MODELS=1` + `MALLOC_ARENA_MAX=2` A/B → (2) mem0 `keep_alive` → (3) voice‑to‑subprocess → (4) relieve host RAM (WisprFlow / bg‑spares) → (5) reaping + E2E cleanup.

---

## 7. How to confirm / monitor

```bash
# ── The decisive #1 test: does main.py ratchet, and does MALLOC_ARENA_MAX fix it? ──
PID=$(systemctl --user show nexus -p MainPID --value)
watch -n 30 "awk '/\\[heap\\]/{h=1} /Rss:/{if(h){print \"heap \"\$2\" kB\"; h=0}}' /proc/$PID/smaps | tail -1; \
  grep -E 'Rss|Private_Dirty' /proc/$PID/smaps_rollup"
# Then: systemctl --user edit nexus  → add Environment=MALLOC_ARENA_MAX=2 → restart → compare growth.

# ── VRAM: per-model unload + co-residency spikes ──
watch -n 2 'nvidia-smi --query-gpu=memory.used,utilization.gpu,power.draw --format=csv,noheader; \
  curl -s localhost:11434/api/ps | python3 -c "import sys,json;print([m[\"name\"] for m in json.load(sys.stdin).get(\"models\",[])])"'
nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv   # per-process VRAM

# ── RAM / swap / the Nexus cgroup ──
watch -n 5 'free -h; systemctl --user show nexus -p MemoryCurrent -p MemoryPeak -p MemorySwapCurrent'

# ── vision_worker respawn thrash (distinct PIDs over time) + OOM kills ──
watch -n 10 'pgrep -af vision_worker.py'
journalctl -k -g "oom|Killed process" --since "-1h"     # bounded; never pipe unbounded journalctl to tail
```

---

## 8. Confidence & open questions

| Claim | Confidence | Basis |
|---|:--:|---|
| ollama models unload on their own | **High** | watched `/api/ps` empty out; VRAM fell 10.7→3.5 GB unaided |
| "VRAM at max" = co‑residency, not a stuck GPU | **High** | live 14:13 decomposition; util 2 % |
| `main.py` growth is native (arena), not a Python leak | **High** | measured `[heap]` 82 MB vs anon 2106 MB on the live process |
| `main.py` grows unbounded vs. plateaus | **Medium** | 286 MB→2.35 GB seen, but under audit load; needs a clean long‑run trace (§7) |
| `MALLOC_ARENA_MAX=2` reclaims "GBs" | **Medium** | mechanism fits; **A/B required** to quantify |
| vision_worker respawns are OOM‑kills | **Low** | timing rules out the idle timer, but stderr is `DEVNULL`; route it to a log to confirm |
| The two live zombies are external (WisprFlow / speech‑dispatcher) | **High** | verified parent PIDs 2245680, 292184 |

*Full file:line evidence for every finding is in the audit sub‑agent outputs; this document is the reconciled, fact‑checked synthesis.*
