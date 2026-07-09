# JARVIS Hologram Avatar Redesign — Implementation Plan

## Context

The JARVIS tab's 3D avatar (`app/static/jarvis3d.js`) currently renders a 7,000-point
particle bust baked from a head scan (`head_points.json`). It has **no facial rig**: lip
sync is a raw RMS-loudness → jaw-drop mapping, and the eyes only blink (no gaze at all) —
which is why the mouth and eyes "look completely wrong". The user wants it replaced with a
proper **hologram head** in the style of their reference video
(`/home/sinep/Videos/3d-hologram.webm`): a dense glowing **violet point-lattice bald human
head** on black — wireframe grid + dots, fresnel rim glow, subtle shimmer, bloom halo.

**Scope: ONLY the avatar.** Layout, chat, sessions, command deck, memory galaxy, backend
(TTS/STT/SSE) all stay as-is. Zero backend changes.

**User decisions (locked, asked 2026-07-09):**
1. Head model = realistic bald head **with full ARKit-52 blendshapes** (three.js "facecap"
   model; Ready Player Me GLB as licensing fallback).
2. Lip sync = **text-aligned visemes + live audio modulation**, fully client-side
   (vendored MIT `lipsync-en.mjs` from met4citizen/TalkingHead).
3. Idle motion = **always face the user** (subtle sway/breathing/gaze; NO turntable).

## Before you start

- Read `docs/JARVIS-VOICE.md` §0 (app/CLAUDE.md mandates this before editing JARVIS code).
- `app/` is the LIVE working tree (`~/nexus-agent-os` symlinks into it). Restart only via
  `systemctl --user restart nexus`. Pre-commit hook runs `app/scripts/verify.sh`.
- Look at the reference: extract frames with
  `ffmpeg -i /home/sinep/Videos/3d-hologram.webm -vf fps=1/2 <scratch>/f-%02d.png` and view them.
- Line numbers below are from 2026-07-09 and will drift — anchor on function names.

## Hard constraints (all verified)

- **No build step / npm / bundler.** Vanilla JS; three.js 0.160.0 dynamically imported from
  `https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js` (same URL in jarvis3d.js,
  memory3d.js, nexus3d.js → browser module cache = ONE shared THREE instance).
- `verify.sh` gate rejects the string `"three"` in `index.html` — vendored files are imported
  dynamically from inside jarvis3d.js only. Do NOT add an import map.
- Public API must survive (verify.sh greps + app.js callers):
  `window.Jarvis3D = { mount, dispose, setMode, setLevel, setAnimations, toggleGalaxy }`
  — extend additively with `speak(rec, audioCtx)` + `stopSpeech()`.
- Canvas must keep `className='jarvis3d-canvas'` (`verify_jarvis_e2e.py` waits on that selector).
- The **memory galaxy + camera fly-through + matrix backdrop** live inside jarvis3d.js
  (~lines 401–981: `buildGalaxyData`, fly mode, picking, `toggleGalaxy`, `onMemorySelect`)
  — preserve them untouched; only the head build + head animation are replaced.
- TTS: Piper, 22050 Hz mono int16 PCM streamed per-sentence over WS `/ws/jarvis/tts`;
  client schedules chunks gaplessly on the AudioContext timeline through one AnalyserNode
  (fftSize 256). The client knows each sentence's **text** and its **exact scheduled
  start/duration** — the foundation of the lip sync design.
- Manual cache-busting: bump the current `?v=N` for jarvis3d.js / app.js / style.css in
  `app/static/index.html` (~lines 102–105).
- Browser renders on the Intel iGPU (hybrid laptop) — keep the perf budget (below).

## Verified technical facts (design agent checked r160 source — trust these)

1. **Morph targets work on all three renderables natively in r160.** The renderer's morph
   path keys on `geometry.morphAttributes` only (three.module.js `setProgram` ~line 30400),
   fires for `THREE.Points` and `ShaderMaterial` alike. A custom ShaderMaterial needs ONLY
   `#include <morphtarget_pars_vertex>` before `main()` and
   `vec3 transformed = vec3(position); #include <morphtarget_vertex>` inside — morph
   uniforms/texture are bound on the program automatically. Share ONE BufferGeometry across
   occluder/wireframe/points and assign the SAME `morphTargetInfluences` array instance to
   all three objects → one write drives everything. `morphTargetsRelative=true` (GLTFLoader)
   means deltas add. Delete `geometry.morphAttributes.normal` after load (halves the morph
   texture; morphed normals unneeded).
2. **facecap.glb** (three.js repo r160 tag, `examples/models/gltf/facecap.glb`, 332,808 B):
   - mesh "head": 2,694 verts / 5,032 tris, all **52 ARKit blendshapes** via
     `extras.targetNames` (facecap naming uses `_L/_R` suffixes, e.g. `eyeBlink_L`).
   - "eyeLeft"/"eyeRight" meshes (530 verts each, no morphs) under pivot nodes
     `grp_eyeLeft`/`grp_eyeRight` → **gaze = rotate the pivots**, plus `eyeLook*` morphs at
     ~0.6 coupling for lid/socket follow.
   - "teeth" mesh (614 verts, static) → include in the occluder only, dark.
   - ⚠️ **KTX2 gotcha**: `KHR_texture_basisu` is in `extensionsRequired` → GLTFLoader
     **throws at parse** without a KTX2Loader. We never use the texture → strip it OFFLINE
     (build script below). `EXT_meshopt_compression` stays (vendored MeshoptDecoder handles
     it); `KHR_mesh_quantization` is natively supported. DRACO not needed.
   - License: no explicit model license; credited "Face Cap (bannaflak.com)" in the three.js
     example. Keep that credit in jarvis3d.js + build script (same pattern as the existing
     Lee Perry-Smith attribution). Clean-license fallback: Ready Player Me GLB with
     `?morphTargets=ARKit,Oculus%20Visemes` — only mapping table + node names change.
3. **lipsync-en.mjs** (met4citizen/TalkingHead, MIT — LICENSE: "Copyright (c) 2023-2024
   Mika Suominen"): standalone, zero imports. `wordsToVisemes(preProcessText(text))` →
   `{visemes[], times[], durations[]}` in relative units, Oculus viseme set
   (sil/aa/E/I/O/U/PP/FF/TH/DD/kk/CH/SS/nn/RR).

## Architecture

```
GLB (facecap_hologram.glb, texture-stripped)
  └─ shared BufferGeometry (world transforms baked in; fit so head height ≈ 26 world
     units, center ≈ y 13 — preserves camera (0,4,88) fov 46 framing + galaxy anchor)
       ├─ occluder Mesh      MeshBasicMaterial #05060f (+ teeth)  renderOrder 0
       ├─ wireframe Mesh     MeshBasicMaterial wireframe, additive, #5b3fd6 op .13  order 1
       └─ Points             custom ShaderMaterial (morph chunks, fresnel rim,
                             twinkle, scanlines, core+halo disc frag)  order 2
     one shared morphTargetInfluences array ← controllers write here each tick
Controllers (CPU, cheap):  VisemeController · BlinkController · GazeController ·
                           IdleController · ModeTint
Post: EffectComposer → RenderPass → UnrealBloomPass(half-res) → OutputPass
Galaxy/matrix/fly-through: UNCHANGED (renders behind, order < 0)
```

Optional: 1-level midpoint subdivision of head geometry for the Points layer only
(2,694 → ~10.4k dots, morph deltas midpoint-averaged) behind a `POINT_SUBDIV` flag —
implement if the raw vertex density looks too sparse vs. the reference video.

## Phases

### P1 — Assets + vendored deps (no behavior change)

1. **`app/scripts/build_facecap_hologram.py`** (new, stdlib-only, follows the attribution
   header pattern of `build_avatar_from_glb.py`): download facecap.glb from the three.js
   r160 tag (`https://github.com/mrdoob/three.js/raw/r160/examples/models/gltf/facecap.glb`)
   if not present, then rewrite the GLB JSON chunk: remove `images`/`textures`/`samplers`,
   `baseColorTexture` from the material, `KHR_texture_basisu`+`KHR_texture_transform` from
   `extensionsUsed`/`extensionsRequired`, drop the 4 animation clips, rebuild the BIN chunk
   without the image bufferView → `app/static/avatar/facecap_hologram.glb` (~150–250 KB).
   Run once, commit the GLB.
2. **Vendor 13 jsm files** → `app/static/vendor/threejsm/` keeping jsm sub-paths, rewriting
   ONLY the bare `'three'` specifier to the exact CDN URL above (sed-able; document in
   `_VENDORING.md`). Import with `?v=1` query from jarvis3d.js (index.html `?v=` bumps don't
   bust vendor URLs). Files (deps verified at r160):
   `loaders/GLTFLoader.js`, `utils/BufferGeometryUtils.js`, `libs/meshopt_decoder.module.js`
   (self-contained), `postprocessing/{EffectComposer,RenderPass,ShaderPass,MaskPass,Pass,
   UnrealBloomPass,OutputPass}.js`, `shaders/{CopyShader,LuminosityHighPassShader,
   OutputShader}.js`.
3. **Vendor `lipsync-en.mjs`** → `app/static/vendor/lipsync/lipsync-en.mjs` with MIT
   attribution header (source: met4citizen/TalkingHead `modules/lipsync-en.mjs`).
4. `bash app/scripts/verify.sh` still green.

### P2 — Hologram rendering (`app/static/jarvis3d.js`)

Replace: procedural sculpt + prebuilt-points build (~lines 93–399), head build inside
`mount()` (~1065–1211), head section of `tick()` (~808–854). Keep: galaxy/matrix/fly
(~401–981), mount/dispose event wiring, pointer camera drift, FX toggle.

1. `loadAddons()` — dynamic import of vendored modules after `loadThree()`;
   `GLTFLoader.setMeshoptDecoder(MeshoptDecoder)`.
2. Load `/static/avatar/facecap_hologram.glb`; find head/eyes/teeth; bake node world
   transforms into Float32 positions (rotate+scale morph POSITION deltas by the 3×3;
   drop NORMAL deltas); fit to the world envelope above; build the 3-renderable ensemble
   with the shared influences array; keep eye pivot groups rotatable.
3. Composer chain; `scene.background = new THREE.Color(0x05050c)` (solid — avoids
   UnrealBloomPass transparent-alpha artifacts); pixelRatio cap **1.5** (currently 2);
   resize → `composer.setSize`; `dispose()` adds `composer.dispose()` +
   `geometry.dispose()` (auto-frees morph textures in r160).
4. Point shader: port the existing manual size-attenuation (`uScale`) + core+halo disc
   fragment; add morph chunks, fresnel rim `pow(1-|dot(vN,vView)|, 2.0)` → brightness
   `0.35+0.9*rim`, per-point twinkle ±22% @0.5–1.5 Hz via `aSeed`, scanline shimmer
   `1+0.12*sin(worldY*1.4 - uTime*2.2)`, rare glitch flicker
   `1-0.15*step(0.992, fract(sin(floor(uTime*3)*91.7)))`.
5. Colors: points `#8a6bff`, wireframe `#5b3fd6`, glints `#b9a5ff`. New violet-based
   `MODE_TINT` multipliers: idle `[1.00,0.95,1.15]`, listening `[0.75,1.15,1.05]` (teal),
   thinking `[1.25,1.10,1.45]`, talking `[1.10,1.00,1.30]` — eased via existing `uTint`.
6. Bloom start values: `UnrealBloomPass(Vector2(w/2,h/2), strength 0.70, radius 0.35,
   threshold 0.12)`.
7. GLB load failure → procedural bald lattice fallback head (same materials, no visemes,
   env-driven pulse) + `console.warn` — never a silent black stage. `head_points.json`
   path is retired.

### P3 — Lip sync

**jarvis3d.js — VisemeController** + API `speak(rec, audioCtx)` / `stopSpeech()`:
- Clock: `t = actx ? actx.currentTime : performance.now()/1000`.
- On activation of a record: `wordsToVisemes(preProcessText(rec.text))`; cache
  `totalRel = times[last]+durations[last]`.
- Each frame: `scale = (rec.end - rec.start)/totalRel` (recomputed — self-corrects as
  chunks arrive, since `rec` is a live object); viseme k active over
  `[rec.start + times[k]*scale, +durations[k]*scale]`; **attack 50 ms / release 120 ms**
  smoothstep envelopes; overlapping visemes combine via max per ARKit target.
- Multiply the whole mouth block by `0.25 + 0.75*clamp(env,0,1)` (env = existing
  fast-attack/slow-release RMS follower from `setLevel`) so real pauses close the mouth;
  keep sibilance: `jawOpen *= (1-0.5*hf)`, `mouthStretch_L/R += 0.2*hf`.
- No active utterance while `mode==='talking'` (mic / unknown text) → audio-only fallback:
  `jawOpen = 0.35*env`, `mouthStretch += 0.25*hf`.

**Viseme → ARKit mapping (starting weights; tune in P6 against real Piper audio):**

| viseme | weights |
|---|---|
| sil | all 0 |
| aa | jawOpen .50 |
| E | jawOpen .22, mouthStretch_L/R .30, mouthSmile_L/R .12 |
| I | jawOpen .12, mouthSmile_L/R .30, mouthStretch_L/R .20 |
| O | jawOpen .40, mouthFunnel .50 |
| U | jawOpen .12, mouthPucker .60, mouthFunnel .20 |
| PP | mouthClose .70, mouthPress_L/R .40, jawOpen .08 |
| FF | mouthRollLower .45, mouthShrugUpper .15, jawOpen .08 |
| TH | tongueOut .35, jawOpen .14 |
| DD | jawOpen .15, mouthShrugUpper .10 |
| kk | jawOpen .14, mouthShrugLower .08 |
| CH | mouthFunnel .35, mouthPucker .25, mouthShrugUpper .20, jawOpen .10 |
| SS | jawOpen .06, mouthStretch_L/R .25, mouthSmile_L/R .15, mouthPress_L/R .15 |
| nn | jawOpen .12, mouthPress_L/R .10 |
| RR | jawOpen .12, mouthPucker .25, mouthFunnel .15 |

**app.js — utterance queue** (function anchors; ~lines 5993–6190):
- `jTTS` state object: add `uq: []`.
- `jarvisSpeak` (sends `{"text": s}` over the WS): push `{text:s, start:-1, end:-1,
  done:false}` per sentence.
- WS binary branch (chunk scheduler, where the schedule time `at` is computed):
  `const cur = jTTS.uq.find(u=>!u.done); if (cur){ if (cur.start<0){ cur.start=at;
  window.Jarvis3D?.speak?.(cur, ctx);} cur.end = at + buf.duration; }` — server is FIFO
  per socket, so first-not-done is always the arriving sentence. Pass the LIVE record.
- `{done}`/`{error}` message branch: mark first not-done record `done=true`.
- Barge-in/teardown — `jarvisStopTTS`, `jarvisTTSReset`, `jarvisTTSMaybeFinish`:
  clear `jTTS.uq` + `window.Jarvis3D?.stopSpeech?.()`.
- HTTP WAV fallback `jarvisSpeakFallback`: once `a.duration` known, call
  `Jarvis3D.speak({text, start: performance.now()/1000, end: start+a.duration, done:true},
  null)` — visemes run on the perf clock, RMS multiplier defaults to 1 (strictly better
  than today's static mouth in fallback).

### P4 — Eyes + idle life

- **BlinkController**: port the existing research-grounded dynamics verbatim
  (~jarvis3d.js:828–840: 80 ms close, brief hold, 220 ms reopen, 2–6 s randomized, 12%
  double-blink) onto `eyeBlink_L/R`; combine with gaze lid-follow via `max()`.
- **GazeController** (state machine): fixation on camera 0.8–2.5 s (75% of the time) |
  offset fixations ±8° yaw / ±5° pitch for 0.4–1.2 s (25%); saccades 60–90 ms smoothstep
  with ~5% overshoot; microsaccades 0.2–0.4° every 0.4–1.0 s; drives `grp_eyeLeft/Right`
  pivot rotations (primary) + `eyeLook*` morphs at 0.6 coupling; blink probability doubles
  at saccade onset. Mode postures: thinking → gaze up-aside (+6° yaw, +8° pitch) +
  `browInnerUp` 0.35; listening → gaze locked on camera + `eyeWide_L/R` 0.12.
- **IdleController**: breathing `scale.y` 1±0.006 @0.22 Hz; head sway yaw ±0.05 rad
  @0.07 Hz + pitch ±0.02 (reuse existing sway with reduced amplitude — **no turntable**);
  listening adds ~3° roll tilt; talking adds env-correlated micro-nods + `browInnerUp`
  0.12 pulse at utterance starts.
- Remove old glint sprites or re-seat on the eyeball surfaces.

### P5 — Integration, polish, cleanup

- Delete legacy: `app/static/avatar/{head_points.json, male_head.glb, reference.jpg,
  base.jpg, frame_*.jpg, frames/}`; dead code paths `buildSculpt`/`buildFromPrebuilt`;
  optionally `app/scripts/build_avatar_from_glb.py` + `build_avatar_pointcloud.py`.
  Server side untouched (Wav2Lip endpoints already 410 Gone; `lipsync.py`'s stale
  `reference.jpg` Path constant is harmless).
- Bump current `?v=` for jarvis3d.js, app.js, style.css in `index.html`.
- `style.css`: retune `.jv2-chip` mode-talking tint from cyan → violet family (~line 1516).
- Docs: update the avatar bullet in `app/CLAUDE.md` + `docs/JARVIS-VOICE.md` §0
  (new architecture, viseme lip sync, Face Cap credit, vendored deps).

### P6 — Verification

1. `bash app/scripts/verify.sh` (256 checks; pre-commit enforces it).
2. Restart via app:verify skill / `systemctl --user restart nexus`;
   UI at `https://localhost:8777` → JARVIS tab.
3. `.venv/bin/python app/scripts/verify_jarvis_e2e.py` (canvas, SSE reply, WS TTS
   SPEAKING, back to idle).
4. Visual: no system chrome exists, but Playwright chromium does
   (`~/.cache/ms-playwright/chromium-1228`) — screenshot idle/thinking/talking states
   (scratch Playwright snippet or `app/scripts/screenshot_all_tabs.py <suffix>` →
   `~/.hermes/cache/screenshots/`). Compare against the reference frames: violet
   dot-lattice head, fresnel rim, bloom halo, faces camera, no spin.
5. Lip sync: chat with voice on — mouth opens only on speech, closes in pauses, visible
   PP/FF closures on words like "people"/"before"; barge-in instantly stills the mouth;
   kill the WS in devtools → HTTP fallback still animates.
6. Eyes: blinks 2–6 s with occasional doubles; camera-dominant gaze with saccades;
   thinking/listening postures show.
7. Galaxy: Memory button fly-through, hover/click-to-edit, return; head↔galaxy links
   still terminate at the skull.
8. FPS ≥55 idle AND talking AND galaxy mode (Playwright RAF counter over 3 s:
   `new Promise(res=>{let n=0,t0=performance.now();(function f(){n++;
   performance.now()-t0<3000?requestAnimationFrame(f):res(n/3)})()})`).
9. Leak check: JARVIS ↔ Dashboard ×10, `performance.memory` stable, no console errors.
10. Regression: `verify_v3_ui.py` + `screenshot_all_tabs.py` clean. Commit (pre-commit
    gate runs verify.sh).

## Perf budget (Intel iGPU renders the browser)

≤13k points + ~5k-tri wireframe + ~7k-tri occluder (trivial); morph texture static after
upload (per-frame cost = 52-float uniform ×3 objects); half-res UnrealBloomPass ≈2–3 ms;
pixelRatio ≤1.5; analyser stays fftSize 256. Escape hatches: quarter-res bloom, disable
`POINT_SUBDIV`.

## Risks & mitigations

1. Morph-texture quirk on Intel iGPU (unlikely — core WebGL2 texelFetch): fallback =
   CPU-blend top-N active deltas into the position attribute (2.7k verts, trivial).
2. facecap license ambiguity: credit retained; RPM GLB is a drop-in swap (mapping table +
   node names only).
3. Text-timeline vs Piper prosody drift within a sentence: sentence-level stretch + RMS
   gating masks it; attack/release smoothing hides ±100 ms; tune comma pause duration if
   needed.
4. Bloom alpha artifacts: avoided via solid scene background (stage CSS vignette sits
   behind an opaque canvas anyway).
5. Galaxy regressions: head fitted to the same world envelope; checklist item 7.
