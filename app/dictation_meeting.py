"""Meeting-mode dual-channel transcription for Nexus dictation
(port of local-wisprflow wf_meeting.py).

Captures TWO streams and labels them by source (no ML diarization needed):
  * the microphone             -> "Me"
  * the default sink's MONITOR -> "Client"  (= whatever is playing, e.g. the call)

Both are captured via ffmpeg's PulseAudio input (pipewire-pulse) — sounddevice
hangs on monitor sources on this box, and `pw-record --target <sink>` silently
falls back to the mic for Bluetooth monitors. Each stream is segmented on
silence with a lightweight energy VAD and transcribed through the machine's
ONE shared whisper (voice.transcribe_pcm — the STT worker serializes calls),
then written to a live, speaker-labeled transcript:

    Client: ...

    Me: ...

Headphones give clean separation; the transcript is faithful (no LLM rewrite).

Bug fixes vs the WisprFlow original (audit 2026-07-10, plan Part 0):
  #3  channel SUPERVISION: an ffmpeg death / EOF / capture exception no longer
      silently kills the channel forever — the channel re-resolves the
      PipeWire node (devices move on BT reconnect), restarts ffmpeg with
      backoff, and writes a visible marker line into the transcript.
  #4  mic-bleed dedup is gated on TEMPORAL OVERLAP (the segments' wall-clock
      ranges must actually overlap), not text similarity alone — two speakers
      legitimately saying the same short phrase in sequence is kept.
  #5  the segment queue is bounded and the worker loop is fully guarded — one
      bad segment logs a marker instead of killing transcription permanently.
  #6  stop() reaps its ffmpeg processes (wait+kill) and joins its threads.

Deliberate deviation from the consolidation plan's "append-only writes" idea:
the atomic tmp+os.replace rewrite is KEPT — same-speaker merging and the
bleed-replace both mutate the transcript's tail, the file is only tens of KB,
and atomic replace is already crash-safe. (The audit rated the rewrite an
inefficiency, not a correctness bug.)
"""
from __future__ import annotations

import datetime
import difflib
import json
import os
import subprocess
import threading
import time
from collections import deque
from queue import Empty, Full, Queue

import numpy as np

import voice

SR = 16000
BLOCK = 512  # 32 ms frames
MARKER = "*"  # pseudo-speaker for supervision/status marker lines


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def resolve_default_nodes():
    """(sink_name, source_name) for the current PipeWire defaults; the sink's
    monitor = Client. Resolved by node.name at runtime because PipeWire node
    IDs move across reboots/BT connects."""
    try:
        data = json.loads(subprocess.check_output(["pw-dump"], text=True, timeout=5))
    except Exception:  # noqa: BLE001
        return None, None
    sink = source = None
    for o in data:
        if (o.get("type") == "PipeWire:Interface:Metadata"
                and o.get("props", {}).get("metadata.name") == "default"):
            for m in o.get("metadata", []):
                if m.get("key") == "default.audio.sink":
                    sink = (m.get("value") or {}).get("name")
                elif m.get("key") == "default.audio.source":
                    source = (m.get("value") or {}).get("name")
    return sink, source


class MeetingSession:
    """One meeting: two supervised capture+VAD threads feed a single
    transcribe/writer worker through a bounded queue."""

    def __init__(self, manager, cfg: dict, log):
        self.d = manager           # DictationManager (for _eff_language)
        self.cfg = cfg             # settings snapshot (typed dict)
        self.log = log
        self.stop_event = threading.Event()
        self.segq: Queue = Queue(maxsize=64)   # bounded (#5)
        self.procs: list = []      # live ffmpeg subprocesses
        self.threads: list = []
        # turns: [(speaker, text, start, end)] with same-speaker merging;
        # start/end are wall-clock segment bounds (feeds the temporal dedup #4)
        self.turns: list = []
        self.path = None
        self.header = ""

    # -- lifecycle ------------------------------------------------------------
    def start(self) -> bool:
        sink, source = resolve_default_nodes()
        if not sink or not source:
            self.log("meeting: could not resolve audio nodes via pw-dump")
            return False
        d = os.path.expanduser(self.cfg.get("meeting_dir", "~/wf-meetings"))
        try:
            os.makedirs(d, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            self.log(f"meeting: cannot create {d}: {e!r}")
            return False
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.path = os.path.join(d, f"meeting-{ts}.md")
        self.header = f"# Meeting transcript — {datetime.datetime.now():%Y-%m-%d %H:%M}\n\n"
        self.turns = []
        self._flush()
        self.log(f"meeting: -> {self.path}")
        self.log(f"meeting: Me={source}")
        self.log(f"meeting: Client={sink}.monitor")
        self.threads = [
            threading.Thread(target=self._worker, daemon=True,
                             name="meeting-worker"),
            threading.Thread(target=self._channel, args=("Me",), daemon=True,
                             name="meeting-me"),
            threading.Thread(target=self._channel, args=("Client",), daemon=True,
                             name="meeting-client"),
        ]
        for t in self.threads:
            t.start()
        return True

    def stop(self) -> str:
        self.stop_event.set()
        for p in list(self.procs):
            try:
                p.terminate()
            except Exception:  # noqa: BLE001
                pass
        # let the worker drain queued segments (bounded)
        for _ in range(100):
            if self.segq.empty():
                break
            time.sleep(0.05)
        # reap processes + join threads (#6)
        for p in list(self.procs):
            try:
                p.wait(timeout=2)
            except Exception:  # noqa: BLE001
                try:
                    p.kill()
                    p.wait(timeout=1)
                except Exception:  # noqa: BLE001
                    pass
        for t in self.threads:
            try:
                t.join(timeout=10 if t.name == "meeting-worker" else 3)
            except Exception:  # noqa: BLE001
                pass
            if t.is_alive():
                self.log(f"meeting: {t.name} still finishing at stop (daemon)")
        self.log(f"meeting: saved {self.path} ({len(self.turns)} turns)")
        return self.path

    # -- capture + energy VAD (per channel, SUPERVISED — #3) --------------------
    def _target_for(self, role: str):
        sink, source = resolve_default_nodes()
        if role == "Me":
            return source
        return (sink + ".monitor") if sink else None

    def _channel(self, role: str):
        attempt = 0
        while not self.stop_event.is_set():
            target = self._target_for(role)
            proc = None
            if target:
                try:
                    proc = subprocess.Popen(
                        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                         "-f", "pulse", "-i", target,
                         "-ar", str(SR), "-ac", "1", "-f", "s16le", "-"],
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                except Exception as e:  # noqa: BLE001
                    self.log(f"meeting: ffmpeg spawn failed for {role}: {e!r}")
            started = time.time()
            if proc is not None:
                self.procs.append(proc)
                try:
                    self._capture_loop(proc, role)
                except Exception as e:  # noqa: BLE001
                    self.log(f"meeting: {role} capture error: {e!r}")
                finally:
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except Exception:  # noqa: BLE001
                        try:
                            proc.kill()
                            proc.wait(timeout=1)
                        except Exception:  # noqa: BLE001
                            pass
                    try:
                        self.procs.remove(proc)
                    except ValueError:
                        pass
            if self.stop_event.is_set():
                return
            # unexpected channel death: mark it, re-resolve the node (it may
            # have moved — BT reconnect, Pipewire restart) and restart ffmpeg
            if proc is not None and time.time() - started > 30:
                attempt = 0   # sustained capture -> reset the backoff
            attempt += 1
            if attempt > 8:
                self._note(f"[{role} channel lost — giving up after {attempt - 1} restarts]")
                self.log(f"meeting: {role} channel permanently lost")
                return
            delay = min(2 ** attempt, 30)
            self._note(f"[{role} channel lost — restarting in {delay}s]")
            self.log(f"meeting: {role} channel died — restart {attempt} in {delay}s")
            if self.stop_event.wait(delay):
                return

    def _capture_loop(self, proc, label: str):
        cfg = self.cfg
        floor = float(cfg.get("meeting_vad_floor", 0.02))
        sil_need = float(cfg.get("meeting_silence_ms", 700)) / 1000.0
        min_speech = float(cfg.get("meeting_min_speech_ms", 300)) / 1000.0
        maxseg = float(cfg.get("meeting_max_seg_s", 24))
        nbytes = BLOCK * 2
        win = deque(maxlen=5)      # ~160 ms rolling window -> smooths noise spikes
        preroll = deque(maxlen=6)  # ~190 ms pre-roll so speech onsets aren't clipped
        buf, speaking, silence, seg_start, speech_dur = [], False, 0.0, 0.0, 0.0
        while not self.stop_event.is_set():
            data = proc.stdout.read(nbytes)
            if not data or len(data) < nbytes:
                return   # EOF / ffmpeg died -> the supervisor decides what's next
            frame = np.frombuffer(data, np.int16).astype(np.float32) / 32768.0
            win.append(float(np.sqrt(np.mean(frame ** 2))))
            loud = (sum(win) / len(win)) >= floor      # windowed level
            if not speaking:
                preroll.append(frame)
                if loud:
                    speaking, seg_start = True, time.time()
                    buf, speech_dur, silence = list(preroll), 0.0, 0.0
            else:
                buf.append(frame)                       # keep trailing silence
                if loud:
                    silence = 0.0
                    speech_dur += BLOCK / SR
                else:
                    silence += BLOCK / SR
                if (silence >= sil_need and speech_dur >= min_speech) \
                        or (time.time() - seg_start) >= maxseg:
                    seg, spoke = np.concatenate(buf), speech_dur
                    buf, speaking, silence = [], False, 0.0
                    preroll.clear()
                    if spoke >= min_speech:
                        seg_end = seg_start + seg.size / SR
                        try:
                            self.segq.put((seg_start, seg_end, label, seg),
                                          timeout=1.0)
                        except Full:   # bounded queue (#5): drop, never block capture
                            self.log(f"meeting: segment queue full — dropped a "
                                     f"{seg.size / SR:.1f}s {label} segment")

    # -- transcribe (serialized by the STT worker) + write ----------------------
    def _worker(self):
        cfg = self.cfg
        while not (self.stop_event.is_set() and self.segq.empty()):
            try:
                seg_start, seg_end, label, audio = self.segq.get(timeout=0.3)
            except Empty:
                continue
            try:   # fully guarded (#5): one bad segment never kills the worker
                if audio.size < int(0.2 * SR):
                    continue
                t0 = time.time()
                text = voice.transcribe_pcm(
                    audio, sample_rate=SR,
                    language=self.d._eff_language() or None,
                    beam_size=int(cfg.get("meeting_beam_size", 3)),
                    vad_filter=False)
                self.log(f"meeting: [{label}] {audio.size / SR:.1f}s -> "
                         f"{time.time() - t0:.2f}s -> {text[:60]!r}")
                if text:
                    self._append(label, text, seg_start, seg_end)
            except Exception as e:  # noqa: BLE001
                self.log(f"meeting: segment error ({e!r}) — worker continues")

    @staticmethod
    def _overlap(a_start, a_end, b_start, b_end) -> float:
        return max(0.0, min(a_end, b_end) - max(a_start, b_start))

    def _append(self, label, text, start, end):
        speaker = "Me" if label == "Me" else "Client"
        # Speaker-bleed dedup (matters only WITHOUT headphones): the mic
        # re-captures the client's speaker audio, so the same utterance shows
        # up on BOTH channels — at (nearly) the SAME TIME. Gate on temporal
        # overlap (#4): the two segments must overlap for at least half of the
        # shorter one, THEN text similarity confirms. Two speakers saying the
        # same phrase in sequence has ~zero overlap and is kept.
        if (len(text) >= 5 and self.turns
                and self.turns[-1][0] not in (speaker, MARKER)):
            _, prev_text, prev_start, prev_end = self.turns[-1]
            ov = self._overlap(start, end, prev_start, prev_end)
            min_dur = max(0.1, min(end - start, prev_end - prev_start))
            if ov >= 0.5 * min_dur and _similar(text, prev_text) >= 0.82:
                if speaker == "Client":
                    # replace the bleed "Me" with the clean Client copy
                    self.turns[-1] = ("Client", text, start, end)
                    if len(self.turns) >= 2 and self.turns[-2][0] == "Client":
                        p = self.turns[-2]   # re-merge if it split a Client run
                        self.turns[-2] = ("Client", p[1] + " " + text, p[2], end)
                        self.turns.pop()
                    self.log(f"meeting: bleed pair -> kept Client -> {text[:40]!r}")
                else:
                    self.log(f"meeting: dropped mic-bleed duplicate "
                             f"(overlap {ov:.1f}s) -> {text[:40]!r}")
                self._flush()
                return
        if self.turns and self.turns[-1][0] == speaker:
            p = self.turns[-1]
            self.turns[-1] = (speaker, p[1] + " " + text, p[2], end)
        else:
            self.turns.append((speaker, text, start, end))
        self._flush()

    def _note(self, text: str):
        """A visible supervision/status marker line in the transcript (#3)."""
        now = time.time()
        self.turns.append((MARKER, text, now, now))
        self._flush()

    def _flush(self):
        body = self.header + "\n\n".join(
            (f"*{t}*" if s == MARKER else f"{s}: {t}")
            for s, t, _st, _en in self.turns)
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w") as f:
                f.write(body.rstrip() + "\n")
            os.replace(tmp, self.path)
        except Exception as e:  # noqa: BLE001
            self.log(f"meeting: write failed: {e!r}")
