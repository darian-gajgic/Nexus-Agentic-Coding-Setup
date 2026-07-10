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
            {"key": "dispatch.fallback_enabled", "label": "Overload fallback enabled", "type": "bool",
             "default": "1",
             "help": "When a model is overloaded upstream (Z.AI 429 load-shedding at peak hours), "
                     "retry once on the fallback model instead of failing: task dispatches retry in a "
                     "fresh session, JARVIS chat retries the turn in the same conversation."},
            {"key": "dispatch.fallback_model", "label": "Overload fallback model", "type": "str",
             "default": "glm-5-turbo",
             "help": "Model that takes over when the primary model (e.g. glm-5.2) is overloaded — "
                     "used by both task dispatch and JARVIS chat. Turn the switch above off to never fall back."},
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
            {"key": "judge.auto_scope", "label": "Auto-judge scope", "type": "str",
             "default": "high_stakes",
             "help": "N5: which quality-mode deliverables the closed loop judges automatically. "
                     "'high_stakes' (default = today's behavior) judges only high-stakes work; "
                     "'all_quality' judges EVERY quality-mode deliverable with a domain rubric "
                     "(+1 judge call each) so the loop auto-retries non-high-stakes work too."},
            {"key": "judge.on_blind_reject", "label": "Judge before a blind retry", "type": "bool",
             "default": "0",
             "help": "N7: when an approval is rejected with NO feedback and the current version "
                     "was never judged, run the frontier judge first so the retry carries real "
                     "findings instead of re-running on nothing."},
        ],
    },
    {
        "id": "super", "title": "Super Result (grounded critic loop)",
        "desc": "A frontier critic with evidence access re-verifies each deliverable in a disposable "
                "sandbox, files line-anchored findings as review comments, and loops the work until "
                "SHIP, convergence, or the round cap. Model = the 'frontier judge' purpose.",
        "items": [
            {"key": "super.critic_cmd", "label": "Critic command template", "type": "command",
             "default": "cverify {file} {domain} {sandbox}",
             "help": "Tokens: {file} {domain} {sandbox} and optional {model}. Gates stub this — "
                     "restore after testing."},
            {"key": "super.max_rounds", "label": "Max automatic rounds", "type": "int",
             "default": "3", "min": 1, "max": 6,
             "help": "Critic → rework rounds before the loop escalates to you."},
            {"key": "super.timeout_s", "label": "Critic timeout (s)", "type": "int",
             "default": "1500", "min": 120, "max": 3600,
             "help": "Hard cap on one critic run (sandboxed, with tool use — minutes are normal)."},
            {"key": "super.max_findings", "label": "Max findings per round", "type": "int",
             "default": "25", "min": 3, "max": 40,
             "help": "Findings beyond this are dropped least-severe-first."},
            {"key": "super.fanout_default", "label": "Wizard fan-out by default", "type": "bool",
             "default": "1",
             "help": "Super Result projects plan independent parallel perspectives + a reconciler "
                     "where the goal allows it."},
            {"key": "super.fanout_n", "label": "Fan-out width", "type": "int",
             "default": "3", "min": 2, "max": 4,
             "help": "Parallel investigators/drafts the wizard plans for analysis/content goals."},
            {"key": "super.keep_sandbox", "label": "Keep critic sandboxes (debug)", "type": "bool",
             "default": "0",
             "help": "Leave app/workspaces/_critic/<id> in place after a run — debugging only."},
            {"key": "frontier.max_concurrent", "label": "Max concurrent frontier calls", "type": "int",
             "default": "2", "min": 1, "max": 8,
             "help": "Global cap on simultaneous Claude-CLI runs (grounded critic + frontier "
                     "judge) — one subscription with hard usage ceilings. Excess calls wait; "
                     "rate-limit/quota failures back off and requeue instead of escalating."},
        ],
    },
    {
        "id": "quality", "title": "Quality autopilot",
        "desc": "Compounding quality levers (QUALITY-AUTOPILOT-PLAN-2026-07-10): golden "
                "exemplars, the project decision log, operator-edit distillation, and the "
                "two-axis autopilot presets. All default to today's behavior.",
        "items": [
            {"key": "framing.brief_mode", "label": "Brief mode (project running-brief)", "type": "bool",
             "default": "0",
             "help": "Q4: when on, workflow members deep in the pipeline lean on the project "
                     "DECISION LOG for cross-stage context instead of a longer reading list "
                     "(only their direct predecessors' deliverables are injected either way). "
                     "Saves tokens on long projects."},
            {"key": "pipeline.tests_first", "label": "Acceptance-tests-first (coding)", "type": "bool",
             "default": "1",
             "help": "Q3: coding pipelines have the spec stage deliver an executable "
                     "acceptance/ suite + RUN.md derived from the acceptance criteria; the "
                     "implementer must make them pass without editing acceptance/, and the "
                     "verifier checks the acceptance-file hashes before running them. Buys the "
                     "oracle once — the tests, not prose, are the contract."},
            {"key": "replan.auto_draft", "label": "Auto-draft replan proposals", "type": "bool",
             "default": "0",
             "help": "N6: when a project stalls (a stage fails terminally, or the final "
                     "inspection fails with no automatic fix round left), draft the recovery "
                     "plan automatically so it is already waiting when you open the project. "
                     "APPLY still needs your approval — only the wait in the middle disappears."},
            {"key": "exemplars.enabled", "label": "Golden-exemplar retrieval", "type": "bool",
             "default": "1",
             "help": "Q1: inject the operator's own best past work (SHIP'd, high-scoring, same "
                     "domain/client) as MUST-READ few-shot exemplars for content/research/"
                     "analysis deliverables — the quality bar to match. Never for code."},
            {"key": "exemplars.min_score", "label": "Exemplar minimum self-score", "type": "float",
             "default": "3.5", "min": 0, "max": 10,
             "help": "Q1: a past deliverable qualifies as an exemplar only at/above this "
                     "self-score (parsed from its rubric self-score line)."},
            {"key": "exemplars.max", "label": "Exemplars per task", "type": "int",
             "default": "2", "min": 1, "max": 5,
             "help": "Q1: how many exemplar paths to inject (curated examples win ties)."},
            {"key": "exemplars.max_age_months", "label": "Exemplar max age (months)", "type": "int",
             "default": "12", "min": 1, "max": 60,
             "help": "L3 lifecycle: past-work exemplars older than this age out (unless "
                     "re-confirmed by a newer SHIP); the candidate pool is capped at "
                     "exemplars.max×3 so stale 'excellence' can't anchor new work."},
            {"key": "lessons.auto_distill", "label": "Auto-distill operator corrections", "type": "bool",
             "default": "1",
             "help": "Q2/N8: on a schedule, turn the operator's corrections (rejections, "
                     "review comments, rejected→accepted diffs, learning notes) into durable "
                     "PLAYBOOK/RUBRIC/STYLE-VOICE deltas — filed as ONE approval per domain. "
                     "The WRITE to the knowledge base always waits for your one-click approval."},
            {"key": "lessons.min_evidence", "label": "Min new evidence to distill", "type": "int",
             "default": "5", "min": 1, "max": 50,
             "help": "Q2: a domain needs at least this many NEW correction items before a "
                     "distillation call runs (one frontier call per domain)."},
            {"key": "lessons.cron", "label": "Distillation schedule (cron)", "type": "str",
             "default": "0 4 * * 1",
             "help": "Q2: when the autonomous distillation sweep fires (default weekly, "
                     "Monday 04:00). Manual 'Distill lessons' runs any time regardless."},
            {"key": "lessons.cmd", "label": "Distillation command template", "type": "command",
             "default": "cdistill {domain} {evidence}",
             "help": "Tokens: {domain} {evidence} and optional {model}. The resolved frontier "
                     "model is exported as JUDGE_MODEL. Gates stub this — restore after testing."},
            {"key": "autopilot.default_involvement", "label": "Default involvement", "type": "str",
             "default": "assisted",
             "help": "Q7a axis 1 (How much should I ask you?): full_auto | assisted | manual. "
                     "The preset a new task/project starts with — full_auto closes the loops and "
                     "only checkpoints at plan/final/escalation/irreversible; assisted (default) "
                     "keeps fix-rounds closed but pauses Super Result checkpoints; manual only "
                     "detects and recommends."},
            {"key": "autopilot.default_spend", "label": "Default spending profile", "type": "str",
             "default": "optimal",
             "help": "Q7a axis 2 (How much should this cost?): eco | optimal | smart. Sets model "
                     "routing, Super Result, fan-out width, round caps, auto-judge scope and the "
                     "token budget multiplier (×0.5/×1/×2). 'optimal' is balanced (best result "
                     "per fuel — validated in the deferred benchmark phase)."},
            {"key": "autopilot.auto_approve_ship_hours", "label": "Auto-approve SHIP after (hours)",
             "type": "int", "default": "0", "min": 0, "max": 336,
             "help": "Q7b: in Full Auto only, a SHIP-verdict FINAL deliverable approval may "
                     "auto-approve after this many hours (0 = never, the default). NEVER applies "
                     "to rejections, escalations, Super Result checkpoints, high-stakes work, or "
                     "any irreversible action (guardrail rule 2)."},
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
        "id": "voice", "title": "JARVIS voice",
        "desc": "Local speech models. STT falls back to CPU automatically when the GPU is contended.",
        "items": [
            {"key": "voice.tts_voice", "label": "TTS voice (Piper)", "type": "str", "default": "",
             "help": "Path to a Piper .onnx voice (relative to the app dir), or empty for the base "
                     "voice. Downloaded US-male options in models/voices/: "
                     "models/voices/en_US-ryan-high.onnx (confident, clear — recommended), "
                     "en_US-lessac-high.onnx (professional, neutral), en_US-joe-medium.onnx (calmer, "
                     "deeper). Must be 22050 Hz; a missing/broken file falls back to the base voice."},
            {"key": "voice.tts_speed", "label": "TTS speaking speed", "type": "float",
             "default": "1.0", "min": 0.5, "max": 2.0,
             "help": "Playback pace multiplier — 1.0 is the voice's native speed, 1.25 is 25% "
                     "faster, 0.9 slower. Applies to the next spoken sentence (no restart)."},
            {"key": "voice.stt_model", "label": "STT model (faster-whisper)", "type": "str",
             "default": "large-v3",
             "help": "The machine's ONE shared STT model (JARVIS voice-in + dictation + "
                     "meetings). large-v3 = most accurate, weights already cached; "
                     "large-v3-turbo = faster alternative (downloads on first use). "
                     "Applies at the next worker spawn."},
            {"key": "voice.stt_device", "label": "STT device", "type": "str", "default": "auto",
             "help": "auto = CUDA with automatic CPU fallback on GPU errors; or force cuda / cpu. "
                     "Applies at the next worker spawn."},
            {"key": "voice.stt_compute", "label": "STT compute type (CUDA)", "type": "str",
             "default": "int8_float16",
             "help": "CUDA precision: int8_float16 ≈ 2GB VRAM for large-v3 (recommended on the "
                     "shared 12GB card — what the old dictation tool ran), float16 ≈ 3.3GB for a "
                     "marginal accuracy gain. CPU always uses int8."},
            {"key": "voice.stt_idle_timeout", "label": "STT idle unload (s)", "type": "int",
             "default": "300", "min": 60, "max": 3600,
             "help": "Seconds of STT inactivity before the worker process is killed, freeing "
                     "100% of its VRAM (weights + CUDA context). Dictation and meetings reset "
                     "the timer on every segment; the next use pays a ~4-8s warm-up (hidden by "
                     "warm-on-mic-press / warm-on-hotkey)."},
            {"key": "voice.stt_language", "label": "STT language", "type": "str", "default": "en",
             "help": "ISO code spoken to JARVIS (en, de, …). Empty = autodetect per utterance. "
                     "Ignored by english-only (*.en) checkpoints. Dictation manages its own "
                     "language (dictation.language + live cycling)."},
        ],
    },
    {
        "id": "vision", "title": "JARVIS vision",
        "desc": "Local visual models on the shared 12GB GPU. The VLM frees VRAM promptly so it "
                "doesn't block other models.",
        "items": [
            {"key": "vision.vlm_keep_alive", "label": "VLM keep-alive after use", "type": "str",
             "default": "60s",
             "help": "How long ollama keeps the vision LLM (qwen3-vl, ~8GB) warm after JARVIS "
                     "looks at something — the timer resets on each look, so it frees the card "
                     "this long after the LAST look. 60s keeps an active webcam Q&A responsive "
                     "while still freeing VRAM once you're done; 0 unloads immediately (cold "
                     "reload on every look); 5m holds it longer for heavy vision sessions."},
            {"key": "vision.idle_timeout", "label": "Vision worker idle kill (s)", "type": "int",
             "default": "600", "min": 60, "max": 3600,
             "help": "Seconds of vision inactivity before the SigLIP/SDXL worker process is "
                     "killed (full VRAM reclaim). Lower to 300 for a uniform ≤5-min unload "
                     "policy; the next frame pays a worker respawn + model reload."},
        ],
    },
    {
        "id": "dictation", "title": "Dictation",
        "desc": "System-wide dictation (absorbed from WisprFlow 2026-07-10): hotkey → record → "
                "shared STT → LLM cleanup → type into the focused window. Non-restart keys "
                "apply at the next dictation session.",
        "items": [
            {"key": "dictation.enabled", "label": "Dictation enabled", "type": "bool",
             "default": "1", "restart": True,
             "help": "Master switch for the dictation subsystem (hotkey listener, control "
                     "socket, overlay). Off = JARVIS voice-in still works; only system-wide "
                     "dictation stops."},
            {"key": "dictation.hotkey_keycode", "label": "Hotkey (evdev keycode)", "type": "int",
             "default": "425", "min": 1, "max": 767, "restart": True,
             "help": "evdev keycode that toggles recording. 425 = KEY_PRESENTATION (the "
                     "dedicated mic key on this Acer). Find codes with evtest."},
            {"key": "dictation.hotkey_debounce_ms", "label": "Hotkey debounce (ms)", "type": "int",
             "default": "250", "min": 0, "max": 2000, "restart": True,
             "help": "Duplicate-press suppression window — this laptop reports the hotkey from "
                     "TWO input devices per press; the debounce collapses them."},
            {"key": "dictation.language", "label": "Dictation language", "type": "str",
             "default": "en",
             "help": "Default session language (en/de/ro). The overlay's language button (or "
                     "the `lang` socket command) cycles per-session without changing this."},
            {"key": "dictation.beam_size", "label": "STT beam size", "type": "int",
             "default": "5", "min": 1, "max": 10,
             "help": "Decode beam for dictation (5 = WisprFlow's accuracy-leaning setting; "
                     "JARVIS voice-in uses 3 for latency)."},
            {"key": "dictation.auto_stop", "label": "Auto-stop on silence", "type": "bool",
             "default": "0",
             "help": "Stop recording automatically after the silence window instead of waiting "
                     "for the second hotkey press."},
            {"key": "dictation.vad_rms_threshold", "label": "VAD RMS threshold", "type": "float",
             "default": "0.010", "min": 0.001, "max": 0.2,
             "help": "Energy level counted as speech. Raise if background noise keeps "
                     "auto-stop from firing."},
            {"key": "dictation.silence_ms", "label": "Auto-stop silence (ms)", "type": "int",
             "default": "900", "min": 200, "max": 5000,
             "help": "Silence duration that ends the recording when auto-stop is on."},
            {"key": "dictation.max_seconds", "label": "Segment length cap (s)", "type": "int",
             "default": "300", "min": 30, "max": 1800,
             "help": "Per-SEGMENT boundary, not a stop: reaching it cuts at the next pause and "
                     "keeps recording while the finished segment is transcribed and typed. "
                     "(WisprFlow silently DISCARDED everything past its 120s cap — fixed here.)"},
            {"key": "dictation.input_device", "label": "Input device", "type": "str",
             "default": "",
             "help": "sounddevice input name/index; empty = system default mic."},
            {"key": "dictation.llm_enable", "label": "LLM cleanup", "type": "bool",
             "default": "1",
             "help": "Polish the raw transcript (punctuation, fillers) with a small local LLM "
                     "before typing. Any failure falls back to the raw transcript."},
            {"key": "dictation.llm_url", "label": "Cleanup ollama URL", "type": "str",
             "default": "http://localhost:11435",
             "help": "The ISOLATED cleanup ollama (f16 KV cache — the system ollama's q4_0 KV "
                     "garbles small models). Unit: nexus-cleanup-llm.service."},
            {"key": "dictation.llm_model", "label": "Cleanup model", "type": "str",
             "default": "gemma3:4b",
             "help": "Model on the cleanup ollama used for the transcript polish."},
            {"key": "dictation.llm_keep_alive", "label": "Cleanup keep-alive", "type": "str",
             "default": "2m",
             "help": "How long ollama keeps the cleanup model in VRAM after a dictation "
                     "(~2.9GB). Sent per-request; short = frees the shared card sooner."},
            {"key": "dictation.llm_timeout", "label": "Cleanup timeout (s)", "type": "int",
             "default": "60", "min": 5, "max": 300,
             "help": "Cleanup call budget; on timeout the raw transcript is typed instead."},
            {"key": "dictation.llm_max_words", "label": "Cleanup max words", "type": "int",
             "default": "1800", "min": 100, "max": 10000,
             "help": "Transcripts longer than this skip the LLM entirely (gemma3's 4096-token "
                     "context would silently drop the BEGINNING of longer inputs)."},
            {"key": "dictation.inject_method", "label": "Injection method", "type": "str",
             "default": "type",
             "help": "type = layout-aware ydotool keystrokes (works in terminals AND GUIs, any "
                     "layout); paste = wl-copy + paste chord; clipboard = copy only. Degrades "
                     "to clipboard automatically when ydotoold is unavailable."},
            {"key": "dictation.paste_chord", "label": "Paste chord", "type": "str",
             "default": "ctrl+v",
             "help": "Chord for inject_method=paste: ctrl+v, ctrl+shift+v (terminals) or "
                     "shift+insert."},
            {"key": "dictation.key_delay_ms", "label": "Typing key delay (ms)", "type": "int",
             "default": "4", "min": 0, "max": 100,
             "help": "Delay between injected key events; raise if apps drop characters."},
            {"key": "dictation.trailing_space", "label": "Trailing space", "type": "bool",
             "default": "1",
             "help": "Append a space after each dictation (newline in note mode) so "
                     "consecutive dictations don't run together."},
            {"key": "dictation.note_mode", "label": "Note mode at boot", "type": "bool",
             "default": "0", "restart": True,
             "help": "Start with one-sentence-per-line formatting on. The overlay's Note "
                     "button toggles it live per-session."},
            {"key": "dictation.overlay", "label": "On-screen overlay", "type": "bool",
             "default": "1",
             "help": "The status pill (listening/processing/meeting) with Meeting/Note/"
                     "Language buttons. Needs tkinter (apt python3-tk)."},
            {"key": "dictation.overlay_python", "label": "Overlay interpreter", "type": "str",
             "default": "",
             "help": "Python with tkinter for the overlay subprocess; empty = auto-detect."},
            {"key": "dictation.meeting_dir", "label": "Meeting transcripts dir", "type": "str",
             "default": "~/wf-meetings",
             "help": "Where meeting-*.md transcripts land (kept at the WisprFlow path so old "
                     "transcripts stay in one place). The Meetings tab reads this."},
            {"key": "dictation.meeting_vad_floor", "label": "Meeting VAD floor", "type": "float",
             "default": "0.02", "min": 0.001, "max": 0.5,
             "help": "Per-channel speech energy floor for meeting segmentation."},
            {"key": "dictation.meeting_silence_ms", "label": "Meeting silence (ms)", "type": "int",
             "default": "700", "min": 200, "max": 5000,
             "help": "Silence that closes a meeting speech segment."},
            {"key": "dictation.meeting_min_speech_ms", "label": "Meeting min speech (ms)",
             "type": "int", "default": "300", "min": 100, "max": 5000,
             "help": "Segments shorter than this are discarded as noise."},
            {"key": "dictation.meeting_max_seg_s", "label": "Meeting max segment (s)", "type": "int",
             "default": "24", "min": 5, "max": 120,
             "help": "Hard per-segment cap so a monologue still transcribes incrementally."},
            {"key": "dictation.meeting_beam_size", "label": "Meeting beam size", "type": "int",
             "default": "3", "min": 1, "max": 10,
             "help": "Decode beam for meeting segments (3 = throughput-leaning)."},
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
