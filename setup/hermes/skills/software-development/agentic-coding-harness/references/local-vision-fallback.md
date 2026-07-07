# Local Vision Fallback (when the vision API isn't billable on the user's plan)

Use this when you need to visually verify an image/screenshot/video-frame the build produced and
the hosted vision model returns 429 ("balance insufficient" / "not included in plan"). On this
user's setup (2026-07-03), GLM-5V-Turbo is NOT billable on the Z.AI Coding Max plan — the
`vision_analyze` tool 429s with code 1113. The free, local alternative is Ollama + llava.

## One-time setup

```bash
ollama pull llava          # ~4.7 GB, free, runs on the local GPU
```

## Calling it from Python (the working pattern)

```python
import requests, base64, json
img_b64 = base64.b64encode(open("/path/to/screenshot.png", "rb").read()).decode()
r = requests.post("http://localhost:11434/api/generate", json={
    "model": "llava",
    "prompt": "Describe this screenshot. Is a human face visible? Is the UI correctly rendered? Be concise.",
    "images": [img_b64],
    "stream": False,
}, timeout=120)
print(r.json().get("response", "(no response)"))
```

## Strengths and limits

- llava is a SMALL model (7B-class). It reliably answers objective questions: "is X present?",
  "is it correctly rendered?", "what text is shown?". For yes/no + presence checks it's trustworthy.
- It CONFABULATES fine details — e.g. it may hallucinate UI labels ("Gender dropdown", "Hair Color
  slider") that aren't in the image. Trust the high-level verdict ("face present", "renders"), do
  NOT trust specific small-text claims unless cross-checked with a pixel/diff or DOM assertion.
- For video files: extract a frame first (`ffmpeg -i video.mp4 -vf "select=eq(n\,10)" -vframes 1 frame.jpg`),
  then analyze the frame. vision tools generally can't ingest video directly.

## When to prefer a deterministic check over any vision model

For "did the model produce real content vs. garbage," a deterministic structural check is stronger
than a vision model's opinion and runs in milliseconds:
- Face output: extract a frame, run a dlib/cv2 face detector — `len(faces) >= 1` proves real content.
- Avatar animating vs. static: pixel-diff two frames (idle vs. speaking) — mean diff > ~3 in the
  avatar region proves it's actually changing, not a frozen poster.
- These never confabulate and cost zero tokens. Use vision only for the subjective residue
  ("is the lip-sync convincing?") that a deterministic check genuinely cannot answer.
