# Vendored runtime deps (no build step — this repo has no npm)

## threejsm/ — three.js r160 example addons

13 files copied verbatim from `https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/`
with ONE mechanical rewrite: the bare `'three'` import specifier is replaced by the exact
core URL every 3D module already imports —
`https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js` — so the browser module
cache keeps a SINGLE shared THREE instance (never use `/+esm`: it resolves to a different
build artifact = a second THREE instance). Relative imports between the files
(`./Pass.js`, `../shaders/CopyShader.js`) are untouched; the jsm directory layout is
preserved so they resolve as-is.

Reproduce/upgrade:
```bash
for f in loaders/GLTFLoader.js utils/BufferGeometryUtils.js libs/meshopt_decoder.module.js \
         postprocessing/{EffectComposer,RenderPass,ShaderPass,MaskPass,Pass,UnrealBloomPass,OutputPass}.js \
         shaders/{CopyShader,LuminosityHighPassShader,OutputShader}.js; do
  curl -sSfL "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/$f" -o "vendor/threejsm/$f"
  sed -i "s|from 'three'|from 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js'|g" "vendor/threejsm/$f"
done
```

On a three.js version bump: re-vendor into a NEW directory (e.g. `threejsm-r1xx/`) and
update the import paths in jarvis3d.js — internal relative imports between vendored files
carry no `?v=` cache-buster, so a new directory is the reliable cache invalidation.
Consumers (jarvis3d.js) import these dynamically with a `?v=N` query; `index.html` `?v=`
bumps do NOT reach these URLs.

Only jarvis3d.js may import these (the `verify.sh` gate bans the string "three" in
index.html — keep it that way).

## lipsync/lipsync-en.mjs — TalkingHead English viseme timeline

From `met4citizen/TalkingHead` `modules/lipsync-en.mjs` (MIT, © 2023-2024 Mika Suominen;
source commit pinned in the file header). Standalone, zero imports.
API: `new LipsyncEn()`, `wordsToVisemes(preProcessText(text))` →
`{ words, visemes[], times[], durations[] }` in relative units (Oculus viseme set:
sil/aa/E/I/O/U/PP/FF/TH/DD/kk/CH/SS/nn/RR).
