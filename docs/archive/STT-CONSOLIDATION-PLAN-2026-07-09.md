# One STT Model for the Whole Machine — Design & Brainstorm Doc

> **⛔ SUPERSEDED — IMPLEMENTED 2026-07-10, with a DIFFERENT topology than this doc
> recommends.** The operator overrode the B1 recommendation: Nexus owns EVERYTHING —
> the one whisper (large-v3 in the killable `app/stt_worker.py` subprocess) AND the
> full dictation UX (hotkey/cleanup/typing/overlay/meetings, ported into
> `app/dictation*.py` with the 2026-07-10 bug-audit fixes: the silent 120s cap and the
> adaptive-GPU-monitor OOM-kill loop are gone). All three wf-* services are disabled;
> `wf-cleanup-llm` renamed → `nexus-cleanup-llm.service` (same ~/.ollama-wf models).
> `~/local-wisprflow/` stays on disk untouched as the rollback. Current truth lives in
> `app/CLAUDE.md` ("STT consolidation") + `app/docs/JARVIS-VOICE.md` §0.-1; the
> implementation plan was `~/.claude/plans/quiet-conjuring-anchor.md`.

**Status:** ~~PARKED for a dedicated session. NOT implemented.~~ This is the "Batch 10" feature from the stability work (`FIX-RUNBOOK-2026-07-08.md` §10) — split out here so it can be designed properly on its own. **The stability bugfix work (Batches 1-9) is DONE, verified, and pushed; this doc is the only remaining thread and it is a FEATURE, not a fix.**
**Date:** 2026-07-09
**Read alongside:** `FIX-RUNBOOK-2026-07-08.md` §10, memory `[[nexus-stability-audit-2026-07-08]]`.

---

## 1. The goal (one sentence)

Today **two separate programs each load their own speech-to-text (STT) model into the shared 12 GB GPU** — the user's WisprFlow dictation tool and Nexus's JARVIS voice-in. Consolidate to **ONE STT model that both use**, to free VRAM (and stop the two competing for the card, which is what starves the JARVIS vision VLM — see the stability audit).

Why it matters: the 12 GB card is chronically full (WisprFlow ~3.3 GB + Nexus STT ~2 GB + mem0's ollama models + SigLIP/SDXL vision worker). Two whisper models is pure duplication — two processes can never share one in-VRAM instance, so the only way to deduplicate is **one owner, one model, both call it**.

**Non-goal / rejected:** running JARVIS STT on CPU (too slow for responsive voice-in — already rejected).

---

## 2. Current state — the two STT stacks (investigated 2026-07-09)

### 2a. WisprFlow (the user's own tool) — `~/local-wisprflow/`
A **991-line daemon** (`wf_daemon.py`) + `wf_layout.py` + **three systemd user services**: `wf-daemon`, `wf-keylistener`, `wf-cleanup-llm` (all `enabled`). It is genuinely sophisticated — *more* capable than Nexus's STT:

| Aspect | WisprFlow | Anchor (`wf_daemon.py`) |
|---|---|---|
| Model | **large-v3** (higher accuracy) | config `"asr_model": "large-v3"` (~line 49) |
| VRAM strategy | **adaptive GPU↔CPU** — runs whisper on GPU when free; auto-falls to CPU (0 VRAM) when a big LLM occupies the card; keeps a warm CPU baseline so there's no downtime switching | `load_model()` ~340, `_asr_monitor()` ~422, config ~51-61 |
| Load | `_load_whisper(device, compute_type)` builds a `WhisperModel` | ~323-338 |
| Transcribe | `transcribe(self, audio: np.ndarray) -> str` | ~507 |
| Cleanup (SEPARATE from ASR) | LLM pass — **gemma3:4b on an ISOLATED ollama at :11435** (own models dir, f16 KV cache) — punctuates/formats the raw transcript, temp 0, "clean up don't rewrite" | config ~80-90, cleanup call ~555 |
| Injection | **ydotool `type`** into the focused window (its working Wayland solution) | config `"inject_method": "type"` ~136, `"ydotool_bin"` ~138 |
| Extras | global hotkey listener, energy-VAD auto-stop, "meeting mode" | throughout |

**KEY: ASR and cleanup are decoupled.** `transcribe()` (raw ASR) is separate from the gemma3 cleanup step. So a consolidation can swap ONLY the ASR call and leave WisprFlow's cleanup + injection + hotkey untouched.

**ydotool note:** ydotool is FINE here — it is the operator's own, already-working dictation injection. The "ydotool/uinput forbidden" memory rule is about *Hermes autonomously controlling the machine* (computer-use), a different context. Do not "fix" WisprFlow's injection.

### 2b. Nexus JARVIS voice-in — `app/voice.py` + `app/server.py`
| Aspect | Nexus | Anchor |
|---|---|---|
| Model | faster-whisper **medium.en** (default; setting `voice.stt_model`) | `voice.py` `_get_stt()` ~114-125 |
| Load | lazy, on-demand `WhisperModel(model_name, device, compute_type)`; unloads after idle | `voice.py:122`; idle unload via the server's 15s unloader |
| OOM handling (added in Batch 5) | cross-process GPU file-lock (`app/gpu_lock.py`) + CPU-on-first-CUDA-OOM + `gc.collect()` on unload | `voice.py` `_run_transcribe` ~200, `_transcribe_sync` ~223 |
| HTTP surface | **`POST /api/jarvis/stt`** already exists — receives WAV, returns `{text}` via `_voice.transcribe(audio_bytes)` | `server.py:2257-2268` |

**Nexus already exposes an HTTP STT endpoint.** That's a big head start for consolidation — the plumbing to "call STT over HTTP" partly exists.

---

## 3. Decision history

- **First idea (operator):** "fully EMBED the dictation daemon inside the Nexus service" (one program does it all). **REVISED AWAY** after the investigation, because: (a) Nexus restarts often (~10×/session during the fix work) and embedding would make every Nexus restart **kill dictation mid-work**; (b) it would re-implement everything WisprFlow already does well (adaptive VRAM, cleanup, Wayland injection); (c) putting a global hotkey listener + system-wide text injection inside a FastAPI web server is a lot of unrelated surface in one process.
- **Chosen direction: OPTION B — one shared STT model, both call it** (keep the two programs, deduplicate only the model). Less code, less risk, keeps dictation independent of Nexus's lifecycle, same VRAM win.

---

## 4. THE decision to make in the brainstorm session: where does the one model live?

Option B has three concrete topologies. This is the fork that determines the whole implementation — **decide this first.**

| | **B1 — WisprFlow owns it** *(leaning recommended)* | **B2 — Nexus owns it** | **B3 — dedicated STT microservice** |
|---|---|---|---|
| Model lives in | WisprFlow daemon (keeps large-v3 + adaptive VRAM) | Nexus `voice.py` (upgrade to large-v3) | new standalone `stt.service` (systemd), ported from WisprFlow's ASR manager |
| WisprFlow change | add a tiny local HTTP `/stt` endpoint; ASR stays in-process | its `transcribe()` becomes an HTTP client → Nexus `/api/jarvis/stt` | its `transcribe()` → HTTP client to the microservice |
| Nexus change | `voice.py` becomes an HTTP client → WisprFlow's `/stt` (drop the in-process WhisperModel) | keep/upgrade the in-process model; serve both | `voice.py` → HTTP client to the microservice |
| Keeps adaptive-VRAM logic | **YES** (already there) | NO (Nexus doesn't have it — Batch 5 is only CPU-on-OOM) | YES (ported) |
| Keeps WisprFlow cleanup/injection | YES (untouched) | YES (untouched) | YES (untouched) |
| Dictation survives Nexus restart | **YES** (model is in WisprFlow) | NO — ~1s blip on every Nexus restart | YES |
| JARVIS voice survives WisprFlow restart | NO (depends on WisprFlow up) | YES | YES |
| New service to build | no | no | **yes (most work)** |
| Relative effort | low–medium | low–medium | high |

**Recommendation (mine, to be confirmed):** **B1 — WisprFlow owns the model.** Rationale: the *better* ASR setup (large-v3 + adaptive VRAM + warm CPU baseline) already lives in WisprFlow; WisprFlow is the lightweight, always-resident, rarely-restarted daemon, so the STT is more stable there than in the heavier, frequently-restarted Nexus service; and JARVIS voice-in becoming a thin HTTP client is a small, clean change. The one real downside — "if WisprFlow is down, JARVIS voice-in is down" — is acceptable (WisprFlow is far more stable than Nexus, and JARVIS text chat still works without voice). B3 is "more correct" but adds a whole service to maintain for marginal gain over B1.

---

## 5. Sub-decisions (after the topology is chosen)

1. **Which model wins?** large-v3 (WisprFlow's — more accurate, ~3 GB on GPU) is the natural single model. Confirm JARVIS voice-in latency with large-v3 is acceptable (it uses adaptive GPU/CPU, so under VRAM pressure it runs on CPU — a short utterance is still ~1-2 s). Alternative: `large-v3-turbo` (faster, near-large-v3 accuracy) as the shared model. **Benchmark accuracy + latency, pick the winner.**
2. **Audio format contract.** WisprFlow works in `np.ndarray` (float32 PCM); Nexus's `/api/jarvis/stt` takes WAV bytes from the browser (`voice.py` decodes webm/wav/mp3 via ffmpeg). The shared endpoint's input contract must handle both callers — decide on WAV bytes (simplest, both can produce it) or raw PCM.
3. **Endpoint auth/locality.** The shared STT endpoint is localhost-only (both callers are on the same box). Keep it unauthenticated but bound to 127.0.0.1, or reuse Nexus's auth if Nexus owns it. For B1, WisprFlow's `/stt` should be 127.0.0.1-bound, no auth.
4. **Language handling.** Nexus STT uses `voice.stt_language` (default en) and english-only-checkpoint logic (`.en` models). large-v3 is multilingual — confirm the shared model's language default matches both use cases (WisprFlow dictation may want auto/multilingual; JARVIS may want en).
5. **Retire WisprFlow's duplicate?** In B1 there is no duplicate to retire (WisprFlow keeps its model; Nexus drops its). In B2, WisprFlow stops loading its own model. Either way: **leave all WisprFlow files intact**; the only "retire" is the removed model-load, not the program.

---

## 6. Implementation sketch (for the recommended B1)

1. **WisprFlow:** add a minimal local HTTP endpoint (e.g. a tiny `aiohttp`/`http.server` thread inside `wf_daemon.py`, or a 4th micro-service) that accepts audio and returns `{"text": <raw transcript>}` by calling the existing `transcribe()`. 127.0.0.1 only. This exposes the model WisprFlow already has warm. (Do NOT run cleanup here — cleanup is a WisprFlow-dictation concern; JARVIS gets the raw transcript and does its own thing.)
2. **Nexus `voice.py`:** behind a setting (e.g. `voice.stt_backend = local|shared`), make `transcribe()` POST to WisprFlow's `/stt` instead of `_get_stt()`. Keep the in-process faster-whisper path as a **fallback** if WisprFlow is unreachable (so JARVIS voice degrades instead of dying — mirrors the existing self-heal philosophy). Drop the in-process model from the hot path when the shared backend answers.
3. **Verify:** `nvidia-smi` shows ONE whisper model resident; JARVIS voice-in works (via WisprFlow); dictation works; **restart nexus → dictation keeps working** (the whole point); WisprFlow down → JARVIS voice-in falls back to its own model (or degrades gracefully) without crashing.

---

## 7. Constraints & gotchas (don't relearn these)

- **Do NOT delete or restructure WisprFlow** — it's a working tool the user relies on daily. Only add an endpoint / swap a model-load. Leave `~/local-wisprflow/` otherwise intact; it's the fallback.
- **ydotool is fine here** (operator's own dictation injection) — do not touch it, do not swap it for uinput. The "forbidden" rule is Hermes-computer-use context only.
- **Nexus restarts often** — that's exactly why B1 (model in WisprFlow) is preferred; don't put the model somewhere that dies on a Nexus restart if you can avoid it.
- **GPU is shared & tight** — the whole point is VRAM. Keep WisprFlow's adaptive GPU↔CPU logic (it's the smart part); don't regress it into a dumb always-GPU load.
- **Nexus side must stay non-blocking** — `voice.py`'s STT runs off the event loop already (the STT call is threadpooled / the endpoint is fine); an HTTP call to WisprFlow must also not block the loop (it's inside the existing off-loop transcribe path — keep it there).
- **Batch 5's `gpu_lock.py`** exists — if the shared model still touches the GPU from Nexus's side in any config, respect the cross-process lock.
- **This is a FEATURE** — it wants its own verify/smoke discipline, but it is NOT gated by `app/scripts/verify.sh` (WisprFlow is outside the repo). Test manually + by observing `nvidia-smi`.

---

## 8. Done criteria

- Exactly **one** whisper model resident in VRAM (confirm via `nvidia-smi --query-compute-apps`).
- JARVIS voice-in transcribes correctly (via the shared model).
- WisprFlow dictation transcribes correctly (unchanged UX: hotkey → type into focused window, with its cleanup).
- **A `systemctl --user restart nexus` does NOT interrupt dictation** (the acceptance test for choosing B1/B3 over the embed idea).
- VRAM headroom visibly improved (the freed ~2-3 GB gives the JARVIS vision VLM room to load — cross-check the "JARVIS can't see" symptom is gone under load).

---

## 9. Pointers

- Runbook entry: `FIX-RUNBOOK-2026-07-08.md` §10 (has the Option-B decision + sub-tasks).
- WisprFlow: `~/local-wisprflow/wf_daemon.py` (ASR `transcribe()` ~507, `load_model()` ~340, cleanup ~555, config ~40-160), `wf_layout.py`, services `wf-daemon`/`wf-keylistener`/`wf-cleanup-llm`.
- Nexus STT: `app/voice.py` (`_get_stt()` ~114, `_run_transcribe`/`_transcribe_sync` ~200-240), `app/server.py` (`/api/jarvis/stt` ~2257), `app/gpu_lock.py` (Batch 5 GPU arbiter).
- The stability audit that surfaced the VRAM contention: `STABILITY-AUDIT-2026-07-08.md` §3.6, and the "JARVIS can't see = VRAM exhaustion" note in `FIX-RUNBOOK-2026-07-08.md` §8.
