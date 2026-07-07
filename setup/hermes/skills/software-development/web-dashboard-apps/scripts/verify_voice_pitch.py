#!/usr/bin/env python3
"""Verify the gender of a TTS voice by estimating its fundamental frequency (f0).

Use after swapping a Piper (or any) TTS voice model to confirm the change took
effect and the gender is correct. Male voices: 85-180 Hz. Female: 165-255 Hz.

CRITICAL: uses an autocorrelation pitch tracker, NOT FFT. A naive FFT peak in
the 60-300 Hz band picks up formants (resonance peaks), not the fundamental f0,
and misreports a male voice (~168 Hz) as ~195-208 Hz — making you wrongly think
the swap failed. Autocorrelation finds the true periodicity.

Usage:
  # From a WAV file:
  python verify_voice_pitch.py /path/to/voice.wav

  # From a running /talk endpoint (pulls the muxed MP4, extracts audio):
  python verify_voice_pitch.py --endpoint https://127.0.0.1:8777 \\
      --text "Hello there. Testing the new voice now."

Dependencies: numpy, wave (stdlib), and ffmpeg on PATH for the --endpoint mode.
"""
import sys, wave, subprocess, tempfile, os, argparse
import numpy as np


def f0_autocorr(sig, sr, frame=2048, hop=1024, silence_db=-40):
    """Estimate median fundamental frequency via normalized autocorrelation.

    For each frame, find the lag (in the 60-300 Hz range) whose
    autocorrelation peaks highest; that lag corresponds to the pitch period.
    Returns the median across voiced frames, or 0 if none found.
    """
    if len(sig) < frame:
        return 0
    rms_threshold = 10 ** (silence_db / 20) * np.std(sig.astype(np.float64))
    f0s = []
    for i in range(0, len(sig) - frame, hop):
        seg = sig[i:i + frame].astype(np.float64) * np.hanning(frame)
        if np.sqrt(np.mean(seg ** 2)) < rms_threshold:
            continue  # skip silence
        ac = np.correlate(seg, seg, 'full')[frame - 1:]
        if ac[0] == 0:
            continue
        ac = ac / ac[0]
        lo, hi = int(sr / 300), int(sr / 60)  # lag range for 60-300 Hz
        region = ac[lo:hi]
        if len(region) == 0:
            continue
        pk = lo + int(np.argmax(region))
        if ac[pk] < 0.25:  # not periodic enough (unvoiced/noise)
            continue
        # parabolic interpolation around the peak for sub-sample accuracy
        if 0 < pk < len(ac) - 1:
            a, b, c = ac[pk - 1], ac[pk], ac[pk + 1]
            denom = a - 2 * b + c
            p = pk + 0.5 * (a - c) / denom if denom != 0 else pk
        else:
            p = pk
        f0s.append(sr / p)
    return int(np.median(f0s)) if f0s else 0


def gender_for(f0):
    if f0 == 0:
        return "UNKNOWN (no voiced frames)"
    if f0 < 165:
        return f"MALE ({f0} Hz)"
    if f0 > 180:
        return f"FEMALE ({f0} Hz)"
    return f"AMBIGUOUS ({f0} Hz, overlap zone)"


def from_wav(path):
    w = wave.open(path)
    data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    f0 = f0_autocorr(data, w.getframerate())
    w.close()
    return f0


def from_endpoint(url, text):
    mp4 = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    try:
        subprocess.run(
            ["curl", "-sk", "-X", "POST", url, "-H", "Content-Type: application/json",
             "-d", f'{{"text":"{text}"}}', "--output", mp4, "--max-time", "120"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-i", mp4, "-vn", "-acodec", "pcm_s16le", wav],
            check=True, capture_output=True,
        )
        return from_wav(wav)
    finally:
        for p in (mp4, wav):
            try:
                os.unlink(p)
            except OSError:
                pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Verify TTS voice gender via f0.")
    ap.add_argument("wav", nargs="?", help="path to a WAV file")
    ap.add_argument("--endpoint", help="/talk endpoint URL to pull audio from")
    ap.add_argument("--text", default="Hello there. Testing the voice now.",
                    help="text to synthesize (with --endpoint)")
    args = ap.parse_args()

    if args.endpoint:
        f0 = from_endpoint(args.endpoint, args.text)
    elif args.wav:
        f0 = from_wav(args.wav)
    else:
        ap.error("provide a WAV path or --endpoint")

    print(f"f0 = {f0} Hz")
    print(f"gender: {gender_for(f0)}")
    print("ranges: male 85-180 Hz, female 165-255 Hz")
    sys.exit(0 if f0 else 1)
