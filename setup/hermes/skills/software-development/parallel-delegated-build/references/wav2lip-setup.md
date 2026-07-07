# Wav2Lip setup on modern GPU (Blackwell sm_120 / torch 2.14 / librosa 0.11)

Session-verified patches for running Wav2Lip (Rudrabha/Wav2Lip, a 2020-era repo) on a 2026
machine. The upstream repo breaks on modern libraries; these are the fixes that got inference
working in /home/sinep/ml-env (torch 2.14.0.dev+cu130, CUDA 13.0, RTX 5070 Ti).

Do NOT install the repo's `requirements.txt` — it pins torch 1.1 / numpy 1.17 and would
destroy the working CUDA env. Install modern compatible deps instead:
`librosa==0.11.0 scipy opencv-python tqdm numba dlib gdown` into the ML venv.

## Patches (file → fix)

### audio.py line ~100 — librosa mel() signature changed to keyword-only
```
- return librosa.filters.mel(hp.sample_rate, hp.n_fft, n_mels=hp.num_mels, fmin=hp.fmin, fmax=hp.fmax)
+ return librosa.filters.mel(sr=hp.sample_rate, n_fft=hp.n_fft, n_mels=hp.num_mels, fmin=hp.fmin, fmax=hp.fmax)
```
Symptom: `TypeError: mel() takes 0 positional arguments but 2 positional arguments`.

### inference.py — torch.load needs weights_only=False (torch 2.x default flipped)
```
- checkpoint = torch.load(checkpoint_path)
+ checkpoint = torch.load(checkpoint_path, weights_only=False)
```
Apply in `_load()` (both the cuda and cpu/map_location branches).

### inference.py — load_model() must handle TorchScript-exported checkpoints
The gdown-sourced `wav2lip_gan.pth` (146MB) is a TorchScript archive, not a pickle dict —
`checkpoint["state_dict"]` raises `NotImplementedError`. Detect and use the module directly:
```python
checkpoint = _load(path)
if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
    s = checkpoint["state_dict"]
    new_s = {k.replace('module.', ''): v for k, v in s.items()}
    model.load_state_dict(new_s, strict=False)
else:
    model = checkpoint          # TorchScript module — already a complete callable model
model = model.to(device)
return model.eval()
```

### face_detection/detection/sfd/sfd_detector.py + api.py
- `torch.utils.model_zoo` → `torch.hub.load_state_dict_from_url` (model_zoo removed in torch 2.x).
- Add explicit `import torch` at top of sfd_detector.py (was relying on a transitive star-import).

### inference.py — cv2 enum path
`cv2.cv2.ROTATE_90_CLOCKWISE` → `cv2.ROTATE_90_CLOCKWISE`.

## Reference face extraction (Task 0.2, worked)
- Sample face.mp4 at ~1fps with ffmpeg → ~42 candidate frames.
- Score each with dlib frontal face detector + variance-of-Laplacian (sharpness); pick highest.
- Square crop centered on the detected face box, resize to 512×512.
- Output: static/avatar/reference.jpg. Target sharpness ≥ ~300 for clean lip-sync.

## Benchmark (verified working, 2026-07-03)
- 1s test audio → 3.5s wall (incl. ~2s model load + ffmpeg encode), 22 frames, <1GB VRAM.
- 5s sentence → 3.7s wall. Comfortably within the "live feel" target (1-3s render/sentence).
- Model loads as TorchScript, runs on CUDA Blackwell (sm_120) with no kernel rebuild needed.

## Verify the output is a real face (not garbage), since vision models may not be on the plan
Extract a frame with ffmpeg, then:
```python
import cv2, dlib
det = dlib.get_frontal_face_detector()
img = cv2.cvtColor(cv2.imread("frame.jpg"), cv2.COLOR_BGR2GRAY)
faces = det(img, 1)   # ≥1 face => valid output
```
This structural check works without any vision API and catches "model produced noise" failures.
