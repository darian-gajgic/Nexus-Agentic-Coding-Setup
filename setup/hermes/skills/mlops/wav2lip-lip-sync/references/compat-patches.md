# Wav2Lip Compatibility Patches for Modern PyTorch (2.x) + New GPU Architectures

Tested on: torch 2.14.0.dev (cu130), RTX 5070 Ti Laptop GPU (Blackwell sm_120),
numpy 2.4.6, opencv-python 5.0.0.93, librosa 0.11.0, Python 3.14

## Patch 1: `torch.utils.model_zoo` removed in torch 2.x

**Files:** `face_detection/detection/sfd/sfd_detector.py` (line 3),
`face_detection/api.py` (line 4)

**Problem:** `from torch.utils.model_zoo import load_url` — this module was
removed. The replacement is `torch.hub.load_state_dict_from_url`.

**Fix:** Replace each occurrence with:
```python
try:
    from torch.utils.model_zoo import load_url
except ImportError:
    from torch.hub import load_state_dict_from_url as load_url
```

## Patch 2: `torch.load()` defaults to `weights_only=True` in torch 2.6+

**File:** `inference.py` (function `_load`, ~line 160)

**Problem:** Old checkpoint files (wav2lip_gan.pth, s3fd.pth) were saved with
the full state dict format. In torch 2.6+, `torch.load()` defaults to
`weights_only=True`, which rejects these files with:
`UnpicklingError: Weights only load failed.`

**Fix:**
```python
# BEFORE:
def _load(checkpoint_path):
    if device == 'cuda':
        checkpoint = torch.load(checkpoint_path)
    else:
        checkpoint = torch.load(checkpoint_path,
                                map_location=lambda storage, loc: storage)
    return checkpoint

# AFTER:
def _load(checkpoint_path):
    if device == 'cuda':
        checkpoint = torch.load(checkpoint_path, weights_only=False)
    else:
        checkpoint = torch.load(checkpoint_path, weights_only=False,
                                map_location=lambda storage, loc: storage)
    return checkpoint
```

**Also in:** `face_detection/detection/sfd/sfd_detector.py` (line 27) —
the `torch.load(path_to_detector)` call should also get `weights_only=False`.
However, s3fd.pth is a plain state_dict so it may load fine without the flag.
Test first; add if it fails.

## Patch 3: `cv2.cv2.ROTATE_90_CLOCKWISE` typo

**File:** `inference.py` (line ~205)

**Problem:** Double-qualified constant `cv2.cv2.ROTATE_90_CLOCKWISE` —
was always a bug but didn't raise in old OpenCV because `cv2.cv2` was
somehow accessible.

**Fix:**
```python
# BEFORE:
frame = cv2.rotate(frame, cv2.cv2.ROTATE_90_CLOCKWISE)
# AFTER:
frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
```

## Patch 4: Missing `import torch` in `sfd_detector.py`

**File:** `face_detection/detection/sfd/sfd_detector.py` (line 1)

**Problem:** The file uses `torch.load()` (line 27) but does not import torch
directly. It relied on `from .detect import *` bringing torch into scope.
With stricter import resolution in newer Python, this can fail.

**Fix:** Add `import torch` after `import os`:
```python
import os
import torch
import cv2
```

## Patch 5 (conditional): `librosa.filters.mel()` positional args

**File:** `audio.py` (function `_build_mel_basis`, line ~99-101)

**Problem:** librosa 0.10+ changed `mel()` to require keyword arguments.
The old code:
```python
return librosa.filters.mel(hp.sample_rate, hp.n_fft, n_mels=hp.num_mels,
                           fmin=hp.fmin, fmax=hp.fmax)
```
may raise `TypeError: mel() got an unexpected positional argument`.

**Fix:** Use keyword args:
```python
return librosa.filters.mel(sr=hp.sample_rate, n_fft=hp.n_fft,
                           n_mels=hp.num_mels, fmin=hp.fmin, fmax=hp.fmax)
```

**IMPORTANT:** Test first — librosa 0.11.0 was observed to still accept
positional args in some configurations. Only patch if the error actually
appears.

## Summary Table

| # | File | Issue | Torch/OpenCV Version | Always Needed? |
|---|------|-------|---------------------|----------------|
| 1 | `sfd_detector.py`, `api.py` | `model_zoo` removed | torch ≥ 2.0 | Yes |
| 2 | `inference.py` | `weights_only=True` default | torch ≥ 2.6 | Yes |
| 3 | `inference.py` | `cv2.cv2` typo | all versions | Yes |
| 4 | `sfd_detector.py` | missing `import torch` | all versions | Yes |
| 5 | `audio.py` | `mel()` positional args | librosa ≥ 0.10 | Test first |
