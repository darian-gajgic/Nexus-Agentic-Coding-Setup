# models/ — runtime model files (NOT tracked in git)

These land here at install time; git only carries this README.

- `piper_voice.onnx` (+ `.json`) — JARVIS TTS voice, Piper "en_US-ryan-high".
  Download: https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/ryan/high
  (rename to `piper_voice.onnx` / `piper_voice.onnx.json`).
- `piper_voice_female_backup.onnx` — optional; the previous female voice, kept
  locally as a fallback only.

Wav2Lip weights live in `/home/sinep/Wav2Lip` (see `docs/JARVIS-VOICE.md`).
