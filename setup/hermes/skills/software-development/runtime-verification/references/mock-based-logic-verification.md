# Mock-based logic verification — when the real runtime can't run in-session

## When this applies

You changed branching/control-flow logic in a Python service whose real runtime needs
heavy native dependencies — a GPU-resident ML model (faster-whisper/CTranslate2), audio
hardware, a database cluster, a cloud API. You can't exercise the real flow in-session
(no GPU, no mic, no credentials). But the LOGIC you changed — state transitions, condition
branches, parameter passing — is pure Python and testable in isolation.

## The technique: inject fakes, assert on observable calls

1. **Import the module** (avoid `__main__` side effects — import as a module, not a script).
2. **Instantiate the class without triggering heavy init** — don't call `load_model()`,
   `connect()`, etc. Just `obj = MyClass(config)` and manually set `obj.asr = FakeASR()`.
3. **Fake the external dependency** with a class that records its call arguments:

```python
class FakeASR:
    """Records language passed to each transcribe() call."""
    def __init__(self):
        self.calls = []
    def transcribe(self, audio, language=None, **kw):
        self.calls.append(language)
        class Seg:
            text = f"[{language}] hello"
        return ([Seg()], {})
```

4. **Drive the method under test** and assert on the fake's recorded state:

```python
d = Daemon(DEFAULTS)
d.asr = FakeASR()
d.active_device = "cpu"
d.transcribe(audio)
assert len(d.asr.calls) == 1          # no re-run when state didn't change
assert d.asr.calls[0] == "en"
```

5. **For state-mutation-during-call scenarios** (concurrency), have the fake mutate the
   object's state mid-call to simulate another thread:

```python
class SwitchingASR(FakeASR):
    def transcribe(self, audio, language=None, **kw):
        self.calls.append(language)
        if not hasattr(self, "_switched"):
            self._switched = True
            d_ref.session_lang = "de"   # simulate socket-thread mutation mid-call
        return ([Seg()], {})

d_ref = Daemon(DEFAULTS)
d_ref.asr = SwitchingASR()
d_ref.transcribe(audio)
assert len(d_ref.asr.calls) == 2        # old result discarded, re-ran with new lang
assert d_ref.asr.calls == ["en", "de"]
```

## What this verifies vs. what it doesn't

| Verifies (logic) | Does NOT verify (contract) |
|---|---|
| Branching: did the re-run fire? | Does faster-whisper actually accept `language="de"`? |
| Parameter passing: was the right lang passed? | Does the audio format match what CTranslate2 expects? |
| State transitions: cycle wraps correctly | Thread safety of the real CTranslate2 call |
| No-persistence: session_lang never hits disk | Performance / timing under real load |

**Mock-based logic verification is a COMPLEMENT to runtime integration testing, not a
replacement.** Use it to prove your logic is correct when you can't run the real thing.
Then flag clearly: "ad-hoc verification of logic; the user must still run the real
end-to-end flow to confirm the contract holds."

## The mid-call state re-check pattern (general)

When a blocking call can't be aborted and mutable state may change on another thread
during it:

```python
state_before = self._eff_state()
result = self.blocking_call(state_before)
state_after = self._eff_state()
if state_after != state_before:
    result = self.blocking_call(state_after)   # discard stale, re-run with current
```

This costs at most one wasted call. Cleaner than trying to abort a non-cancellable native
call (CTranslate2, libcurl, subprocess). The pattern applies to any mutable-session-state
+ blocking-operation pair: language during ASR, output device during audio render, model
selection during inference, etc.

## Session provenance

- **2026-07-05**: local-wisprflow language-cycle feature. Tested `_cycle_lang()` cycle
  order, `handle("lang")` dispatch, mid-transcription re-check logic, and no-persistence
  using FakeASR mocks — all without a GPU or faster-whisper installed. 40/40 checks.
  Real end-to-end testing (actual German audio → German transcript) deferred to the user.
