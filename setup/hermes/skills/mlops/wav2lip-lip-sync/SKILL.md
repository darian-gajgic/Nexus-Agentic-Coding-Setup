---
name: wav2lip-lip-sync
description: "Set up and run Wav2Lip neural lip-sync inference — clone, patch for modern PyTorch/GPU, download checkpoints, extract reference face, produce lip-synced video."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [wav2lip, lip-sync, talking-head, video-generation, pytorch, blackwell, legacy-model-patch]
    category: mlops
    related_skills: [spike, comfyui]
---

# Wav2Lip Neural Lip-Sync

Set up and run Wav2Lip — a neural lip-sync model that takes a reference face
image/video and an audio file, then produces a video where the face's mouth
moves in sync with the audio. Runs entirely locally on GPU.

Load this skill when the user asks to: set up Wav2Lip, run lip-sync inference,
build a talking-head avatar, or integrate Wav2Lip into a web app or pipeline.

## Repository & Checkpoints

**Repo:** https://github.com/Rudrabha/Wav2Lip (clone to your project's ml-env area)

**Required checkpoints (both free):**

| Model | Purpose | Size | Source |
|-------|---------|------|--------|
| `wav2lip_gan.pth` | Main lip-sync model (GAN variant — better visual quality) | 146 MB | Google Drive: file ID `15G3U08c8xsCkOqQxE38Z2XXDnPcOptNk` |
| `s3fd.pth` | S3FD face detection model (bundled in repo's face_detection module) | 86 MB | https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth |

**Placement:**
```
Wav2Lip/
├── checkpoints/wav2lip_gan.pth          # main model
├── face_detection/detection/sfd/s3fd.pth # face detector (must be here)
```

**Download commands:**
```bash
# s3fd (direct URL — reliable)
curl -L -o face_detection/detection/sfd/s3fd.pth \
  https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth

# wav2lip_gan (Google Drive — use gdown)
pip install gdown
gdown 15G3U08c8xsCkOqQxE38Z2XXDnPcOptNk -O checkpoints/wav2lip_gan.pth
```

A non-GAN variant (`wav2lip.pth`) also exists — more accurate lip-sync but
worse visual quality. For the GAN variant, see the README's model table.

## CRITICAL: Do NOT Install the Repo's requirements.txt

Wav2Lip's `requirements.txt` pins ancient versions (torch==1.1.0, numpy==1.17.1,
opencv-python==4.1.0.25, librosa==0.7.0). Installing these will destroy a
working modern CUDA environment. Instead, install compatible runtime deps
into your existing venv:

```bash
/home/your-env/bin/pip install librosa scipy opencv-python tqdm dlib gdown
```

The Wav2Lip model code itself is architecture-compatible with torch 2.x —
only the dependency APIs and a few import paths need patching.

## Compatibility Patches (Modern PyTorch + New GPU Architectures)

The repo was written for torch 1.1 (circa 2020). Four patches are needed for
torch 2.x on any GPU architecture (Blackwell sm_120, Ada, Ampere, etc.).
Apply all four before first inference. See `references/compat-patches.md` for
exact file paths, line numbers, and before/after diffs.

1. **`torch.utils.model_zoo` removed in torch 2.x** — patch `sfd_detector.py`
   and `api.py` to fall back to `torch.hub.load_state_dict_from_url`.
2. **`torch.load()` defaults to `weights_only=True` in torch 2.6+** — old
   checkpoints (wav2lip_gan.pth, s3fd.pth) fail to load. Add
   `weights_only=False` to all `torch.load()` calls.
3. **`cv2.cv2.ROTATE_90_CLOCKWISE` typo** — double-qualified name. Fix to
   `cv2.ROTATE_90_CLOCKWISE` in `inference.py`.
4. **`import torch` missing in `sfd_detector.py`** — relied on transitive
   star-import from `detect.py`. Add explicit `import torch`.
5. **`librosa.filters.mel()` positional args changed in librosa 0.10+** —
   may need keyword args (`sr=`, `n_fft=`) in `audio.py` line 100.
   Test first; only patch if the error appears.

The S3FD face detector and Wav2Lip model both use standard conv/batchnorm
layers — no custom CUDA kernels — so they run on any compute capability that
the installed PyTorch supports, including Blackwell sm_120.

## Inference Command

```bash
cd /path/to/Wav2Lip && /path/to/env/bin/python inference.py \
  --checkpoint_path checkpoints/wav2lip_gan.pth \
  --face /path/to/reference.jpg \
  --audio /path/to/audio.wav \
  --outfile /path/to/output.mp4 \
  --pads 0 10 0 0 \
  --face_det_batch_size 8 \
  --wav2lip_batch_size 16
```

Key flags:
- `--face` — image (.jpg/.png) or video file. If image, `--static=True` is auto-set.
- `--pads` — top/bottom/left/right padding around detected face. Include chin.
- `--wav2lip_batch_size` — reduce to 8–16 for GPUs with <12 GB VRAM.
- `--face_det_batch_size` — reduce if face detection OOMs.
- `--static` — use only the first frame (for single-image lip-sync).
- `--fps` — output framerate (default 25). Only meaningful with static images.

## Extracting a Reference Face

For best lip-sync results, extract a front-facing, well-lit, neutral-mouth
frame from a source video. Use dlib's face detector (more reliable than
OpenCV Haar cascades, which are removed in OpenCV 5.0).

Score candidates by: sharpness (variance of Laplacian), brightness (mean
near 140), face size, and centrality. See `scripts/extract_reference_face.py`
for a ready-to-run script.

**Output:** square crop, 512×512, face centered, JPEG quality 95.

## Integration Pattern (Web App)

For a server that renders lip-sync clips on demand:

1. Load the Wav2Lip model once (lazy singleton) — cold start ~2–3s, reuse after.
2. Shell out to `inference.py` via subprocess, OR import the model directly
   (cleaner but requires PYTHONPATH to include the Wav2Lip repo root).
3. One call per sentence: TTS → wav → Wav2Lip → mp4 → return to client.
4. Expected render time: ~1–3s per sentence on a modern laptop GPU.
5. Models cached under the project (gitignore the checkpoints).

**Frontend integration:** the browser plays the returned mp4 in a muted
`<video>` element while a separate `Audio` element plays the TTS WAV
simultaneously — video provides the visual (mouth moving), audio provides
the sound. If the lipsync fetch fails, fall back to audio-only with a static
face poster. For the full browser-side pattern (dual-track playback,
multi-sentence sequencing, conversation loop, CSS), see the
`web-dashboard-apps` skill's `references/video-avatar-lipsync.md`.

## Pitfalls

1. **OpenCV 5.0 removed `cv2.CascadeClassifier`** — use dlib for face detection
   in your extraction scripts instead. `pip install dlib` (compiles from source,
   ~2 min).
2. **`python3 -c "..."` may be blocked** by security policies on some systems.
   Write scripts to files and execute with `python3 /path/to/script.py` instead.
3. **librosa `mel()` API** — if you see `TypeError: mel() got positional
   argument`, patch `audio.py` `_build_mel_basis()` to use keyword args:
   `librosa.filters.mel(sr=hp.sample_rate, n_fft=hp.n_fft, n_mels=hp.num_mels, fmin=hp.fmin, fmax=hp.fmax)`.
4. **NaN in mel spectrogram** — Wav2Lip raises if mel contains NaN. This
   usually happens with pure silence or TTS audio. Add a small epsilon noise:
   `ffmpeg -f lavfi -i "sine=frequency=440:duration=1" /tmp/test.wav`.
5. **`temp/` directory must exist** — Wav2Lip writes intermediate files there.
   `mkdir -p Wav2Lip/temp` before first run.
6. **Video codec** — inference.py writes `temp/result.avi` (DIVX), then remuxes
   to mp4 via ffmpeg. Ensure ffmpeg is on PATH.
7. **Checkpoint is a TorchScript archive, not a state_dict (most surprising one).**
   The gdown-sourced `wav2lip_gan.pth` loads as a `RecursiveScriptModule`, and
   `load_model()`'s `checkpoint["state_dict"]` raises `NotImplementedError`. The
   `weights_only=False` patch (#2 above) is NOT enough — `torch.load` auto-dispatches
   to `torch.jit.load` for TorchScript files. Fix `load_model()` to detect the type
   and use the TorchScript module directly: `if isinstance(checkpoint, dict) and
   "state_dict" in checkpoint: ...load_state_dict... else: model = checkpoint` (it's
   already a complete callable model — face_encoder_blocks, audio_encoder,
   face_decoder_blocks, output_block). This handles both checkpoint formats.

## Verification

After setup, verify the pipeline works end-to-end:

```bash
# 1. Generate test audio
ffmpeg -y -f lavfi -i "sine=frequency=440:duration=1" -ac 1 -ar 16000 /tmp/test.wav

# 2. Run inference
cd /path/to/Wav2Lip && /path/to/env/bin/python inference.py \
  --checkpoint_path checkpoints/wav2lip_gan.pth \
  --face /path/to/reference.jpg \
  --audio /tmp/test.wav \
  --outfile /tmp/wav2lip_smoketest.mp4

# 3. Verify output
ffprobe -v quiet -print_format json -show_streams /tmp/wav2lip_smoketest.mp4
```

The output should be a valid mp4 with a video stream (25fps) and audio stream.
The face should be visible with the mouth region modified by the model.

## References

- `references/compat-patches.md` — exact file paths, line numbers, and
  before/after diffs for all compatibility patches (torch 2.x / modern GPU)
- `scripts/extract_reference_face.py` — ready-to-run face extraction script
  (dlib-based, scores candidates, outputs 512×512 crop)
