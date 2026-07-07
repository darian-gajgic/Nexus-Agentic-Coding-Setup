# Agentic Coding Setup — Issues Log (RESOLVED 2026-07-03)

> Every problem hit while building the Jarvis neural-avatar. Status after the fix pass.

## Summary
- 16 issues logged. **12 now FIXED**, 1 user-decision (I-002), 1 partially mitigated (I-014),
  2 were positive findings. The single most impactful fix: runtime tests now mandatory (I-015).

## FIXED in this pass
- **I-001** Memory limit too small → raised memory_char_limit 2200→6000, user 1375→3000 (config).
- **I-012** Audio/video desync → finish() now stops audio when video ends; single idempotent finish.
- **I-016** `_thinking` noise in chat → suppressed (tool name filter).
- **I-007** No canonical test command → CLAUDE.md now documents static + runtime + per-edit gates.
- **I-004** Subagents reinstall existing deps → encoded "check installed first" in delegation skill.
- **I-005** delegate_task misused for status checks → skill says poll filesystem artifacts instead.
- **I-008** Subagent iteration budget exhausted by setup → skill says split setup/execute, one coherent unit + gate per subagent.
- **I-006** /tmp verify scripts re-flagged → project now has a real canonical test (verify_jarvis_e2e.py) — no more ad-hoc /tmp scripts.
- (I-003, I-009, I-010, I-015 already fixed during the build.)

## OPEN / DEFERRED
- **I-002** web_extract backend (Brave Free is search-only). DEFERRED — user decision. Firecrawl self-hostable/free is the recommended option.
- **I-014** computer_use capture broken on Wayland. PARTIALLY MITIGATED — Playwright (headless) now covers web-UI visual testing; computer_use (full desktop) still needs a cua-driver upgrade or xdg-desktop-portal/PipeWire. Not blocking for web work.

## POSITIVE findings (kept for the record)
- **I-013/I-011** Well-scoped subagents + a verifiable gate complete reliably; subagents independently converge on the same bug diagnosis as the orchestrator (validates delegation).

---

## Original issue detail (for reference)

### I-001 [FRICTION] Memory store perpetually near-full
FIXED: memory.memory_char_limit raised to 6000, user_char_limit to 3000.

### I-002 [SETUP] web_extract backend not configured
DEFERRED: configure firecrawl (self-hostable, free) or tavily/exa. User decision on cost/hosting.

### I-003 [BUG] Paperclip quickstart permissions
FIXED locally (override.yml + data-dir chown). Upstream quickstart bug; documented in harness skill.

### I-004 [FRICTION] Subagent built dlib from source unnecessarily
FIXED (process): delegation skill now instructs "check installed deps first."

### I-005 [BUG] delegate_task misused for status check
FIXED (process): skill says poll filesystem artifacts, never spawn a subagent to check status.

### I-006 [FRICTION] /tmp verify scripts re-flagged by change-tracker
FIXED: project now has a canonical runtime test; ad-hoc /tmp scripts no longer needed.

### I-007 [SETUP] No canonical test command
FIXED: CLAUDE.md "Test / Verify" section documents the three gates (static / runtime / per-edit).

### I-008 [FRICTION] Subagent hit iteration limit before final step
FIXED (process): skill says split setup vs execute; one coherent unit + verifiable gate per subagent.

### I-009 [BUG] Wav2Lip audio.py vs modern librosa
FIXED: keyword args (sr=, n_fft=).

### I-010 [BUG] Wav2Lip checkpoint was TorchScript
FIXED: load_model() handles both state_dict and TorchScript modules.

### I-012 [BUG] Audio/video desync
FIXED: single finish() stops audio when video ends; idempotent.

### I-013 [SETUP, POSITIVE] Well-scoped subagent completed fully
KEPT: the working pattern — one coherent unit + a verifiable gate per subagent.

### I-015 [CRITICAL BUG] SSE event-name mismatch — reply silently dropped
FIXED + LESSON: static gates insufficient; runtime tests now mandatory. The #1 finding.

### I-016 [BUG] `_thinking` rendered as tool noise
FIXED: suppressed.

### I-014 [BUG] computer_use broken on Wayland
PARTIALLY MITIGATED: Playwright covers web-UI testing. Full-desktop capture still needs a driver fix.
