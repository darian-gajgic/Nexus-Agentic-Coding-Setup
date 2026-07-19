"""Remote meeting capture — MeetingMode fed by a BROWSER microphone.

The local MeetingMode (dictation_meeting.py) records THIS machine's audio.
This module accepts compressed audio chunks uploaded by the dashboard open on
ANY device (the Windows PC, a phone): the browser cycles MediaRecorder every
~15 s so every chunk is a complete standalone container, POSTs it, and the
worker thread here decodes (ffmpeg), gates on a windowed energy VAD, and
transcribes through the machine's ONE shared whisper into the SAME
speaker-labeled live transcript format the Meetings tab already manages.

Single-channel by nature ("Me" = whatever that device's mic hears) — for a
call, speakers instead of a headset put both sides on the mic. A watchdog
auto-finalizes the transcript when the feed dies (tab closed, laptop lid).
"""
from __future__ import annotations

import datetime
import os
import secrets
import subprocess
import threading
import time
from queue import Empty, Full, Queue

import numpy as np

import settings_registry as sreg
import voice

SR = 16000
BLOCK = 512                # 32 ms frames (matches dictation_meeting)
FEED_TIMEOUT_S = 120       # no chunk for this long -> auto-finalize
PARAGRAPH_GAP_S = 15.0     # silence gap that starts a new transcript paragraph
MARKER = "*"


def _cfg_f(key: str, dflt: float) -> float:
    try:
        return float(sreg.conf(f"dictation.{key}") or dflt)
    except (TypeError, ValueError):
        return dflt


def _decode_to_pcm(blob: bytes) -> np.ndarray:
    """Any browser container (webm/opus, ogg, wav, mp4) -> 16 k mono float32."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
         "-i", "pipe:0", "-ar", str(SR), "-ac", "1", "-f", "s16le", "pipe:1"],
        input=blob, capture_output=True, timeout=60)
    if p.returncode != 0 or not p.stdout:
        raise ValueError(f"ffmpeg decode failed: {p.stderr[:200]!r}")
    return np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768.0


def _has_speech(pcm: np.ndarray, floor: float) -> bool:
    """Windowed energy check (the local VAD's 160 ms rolling window, applied
    chunk-wide): a mostly-silent 15 s chunk with 2 s of speech must pass —
    a whole-chunk RMS would average the speech away."""
    n = pcm.size - (pcm.size % BLOCK)
    if n < BLOCK * 5:
        return False
    rms = np.sqrt(np.mean(pcm[:n].reshape(-1, BLOCK) ** 2, axis=1))
    win = np.convolve(rms, np.ones(5) / 5, mode="valid")
    return bool(win.size and float(win.max()) >= floor)


class RemoteMeetingSession:
    """One browser-fed meeting: chunk queue -> decode/VAD/transcribe worker ->
    the same atomic live-transcript writes as the local MeetingSession."""

    def __init__(self, label: str, log, on_close=None):
        self.label = (label or "remote device").strip()[:60]
        self.log = log
        self.on_close = on_close          # called once after finalize (any path)
        self.token = secrets.token_hex(16)
        self.stop_event = threading.Event()
        self.q: Queue = Queue(maxsize=32)
        self.turns: list = []             # [(speaker, text, start, end)]
        self.chunks_seen = 0
        self.last_feed = time.time()
        self._closed = False
        self._close_lock = threading.Lock()
        d = os.path.expanduser(sreg.conf("dictation.meeting_dir") or "~/wf-meetings")
        os.makedirs(d, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.name = f"meeting-{ts}.md"
        self.path = os.path.join(d, self.name)
        self.header = (f"# Meeting transcript — {datetime.datetime.now():%Y-%m-%d %H:%M} "
                       f"(remote: {self.label})\n\n")
        self._flush()
        self.threads = [
            threading.Thread(target=self._worker, daemon=True, name="rmeet-worker"),
            threading.Thread(target=self._watchdog, daemon=True, name="rmeet-watchdog"),
        ]
        for t in self.threads:
            t.start()
        self.log(f"remote meeting: -> {self.path} ({self.label})")

    # -- feed -----------------------------------------------------------------
    def add_chunk(self, blob: bytes) -> int:
        self.last_feed = time.time()
        self.chunks_seen += 1
        try:
            self.q.put(blob, timeout=1.0)
        except Full:   # never block the HTTP path; drop with a visible marker
            self._note("[chunk dropped — transcription backlog]")
            self.log("remote meeting: queue full — dropped a chunk")
        return self.q.qsize()

    # -- worker ---------------------------------------------------------------
    def _worker(self):
        floor = _cfg_f("meeting_vad_floor", 0.02)
        beam = int(_cfg_f("meeting_beam_size", 3))
        lang = (sreg.conf("dictation.language") or "").strip() or None
        while not (self.stop_event.is_set() and self.q.empty()):
            try:
                blob = self.q.get(timeout=0.3)
            except Empty:
                continue
            try:   # one bad chunk never kills the worker (local rule #5)
                pcm = _decode_to_pcm(blob)
                end = time.time()
                start = end - pcm.size / SR
                if not _has_speech(pcm, floor):
                    continue
                t0 = time.time()
                text = voice.transcribe_pcm(pcm, sample_rate=SR, language=lang,
                                            beam_size=beam, vad_filter=True)
                self.log(f"remote meeting: {pcm.size / SR:.1f}s -> "
                         f"{time.time() - t0:.2f}s -> {text[:60]!r}")
                if text:
                    self._append(text, start, end)
            except Exception as e:  # noqa: BLE001
                self.log(f"remote meeting: chunk error ({e!r}) — worker continues")

    def _watchdog(self):
        while not self.stop_event.wait(5):
            if time.time() - self.last_feed > FEED_TIMEOUT_S:
                self.log("remote meeting: feed lost — auto-finalizing")
                self._note("[remote feed lost — meeting auto-closed]")
                self.stop()
                return

    # -- transcript (single channel, paragraph on long pauses) ----------------
    def _append(self, text: str, start: float, end: float):
        if self.turns and self.turns[-1][0] == "Me" \
                and start - self.turns[-1][3] < PARAGRAPH_GAP_S:
            p = self.turns[-1]
            self.turns[-1] = ("Me", p[1] + " " + text, p[2], end)
        else:
            self.turns.append(("Me", text, start, end))
        self._flush()

    def _note(self, text: str):
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
            self.log(f"remote meeting: write failed: {e!r}")

    # -- lifecycle ------------------------------------------------------------
    def stop(self) -> str:
        with self._close_lock:
            if self._closed:
                return self.path
            self._closed = True
        self.stop_event.set()
        for _ in range(200):               # let the worker drain (<=10 s)
            if self.q.empty():
                break
            time.sleep(0.05)
        for t in self.threads:
            if t is not threading.current_thread():
                t.join(timeout=15 if t.name == "rmeet-worker" else 2)
        self._flush()
        self.log(f"remote meeting: saved {self.path} ({len(self.turns)} turns)")
        if self.on_close:
            try:
                self.on_close(self)
            except Exception:  # noqa: BLE001
                pass
        return self.path
