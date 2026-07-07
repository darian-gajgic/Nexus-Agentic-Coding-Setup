# Three.js 3D Avatar Pattern (No Build Step)

Complete implementation of a JARVIS-style 3D animated head using Three.js loaded
via CDN. Self-contained class, vanilla JS, no npm/bundler/ES modules required.

Tested with Three.js r169 on Chrome/Firefox. ~300 lines, ~11KB.

## Setup

```html
<!-- In <head>, before app.js -->
<script src="https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.min.js"></script>
<script src="/static/avatar.js"></script>
<script src="/static/app.js"></script>
```

The avatar.js file defines a single `JARVISAvatar` class.

## Class API

| Method | Purpose |
|--------|---------|
| `mount(container)` | Append WebGL canvas into a DOM element |
| `setMode(mode)` | `idle` \| `listening` \| `thinking` \| `talking` |
| `setAudioLevel(amp)` | 0..1 amplitude for lip-sync jaw movement |
| `dispose()` | Destroy renderer, geometries, materials, canvas |

## Key Implementation Details

### Head Construction

- Skull: `IcosahedronGeometry(1.0, 2)` with vertices stretched vertically (y*1.2)
  and back flattened (z*0.92 if z<0) for a head-like shape. `flatShading: true`
  gives a faceted crystal look.
- Wireframe overlay: same geometry at `scale(1.01)`, `MeshBasicMaterial` with
  `wireframe: true, opacity: 0.12` for holographic effect.
- Jaw: `SphereGeometry` lower hemisphere, separate mesh that translates down and
  rotates based on audio amplitude.
- Eyes: `SphereGeometry(0.14)` with emissive material + `Sprite` glow textures
  (generated via `CanvasTexture` radial gradient).

### Lip-Sync (Web Audio API)

```javascript
// In TTS playback — connect Audio element to AnalyserNode
const source = ctx.createMediaElementSource(audioEl);
const analyser = ctx.createAnalyser();
analyser.fftSize = 256;
source.connect(analyser);
analyser.connect(ctx.destination);

// Per-frame loop:
analyser.getByteFrequencyData(dataArray);
const avg = sum / dataArray.length / 255;  // 0..1
avatar.setAudioLevel(avg * 2.5);  // amplify for visible jaw movement
```

The avatar smoothly interpolates jaw position: `currentJaw += (target - currentJaw) * 0.25`

### Mode-Reactive Animation

| Mode | Emissive | Ring Speed | Extra |
|------|----------|------------|-------|
| idle | 0.12 + slow pulse | 0.8x | breathing scale, blink |
| listening | 0.25 + fast pulse | 2x | cyan glow |
| thinking | 0.2 + rapid pulse | 1.5x | extra head rotation |
| talking | 0.3 steady | 1.2x | jaw lip-sync |

### Eye Blinking

Random interval (2-6s), blink duration ~125ms via decrementing phase counter.
Eye scale Y follows `abs(cos((1-phase) * PI))` for smooth open-close-open.

### Disposal (CRITICAL)

```javascript
dispose() {
  this.disposed = true;
  this.renderer.setAnimationLoop(null);
  window.removeEventListener('resize', this._resizeHandler);
  this.renderer.dispose();
  // Remove canvas from DOM
  this.renderer.domElement.parentNode?.removeChild(this.renderer.domElement);
  // Walk scene, dispose every geometry + material
  this.scene.traverse(obj => {
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) {
      Array.isArray(obj.material)
        ? obj.material.forEach(m => m.dispose())
        : obj.material.dispose();
    }
  });
}
```

Without disposal, each view switch leaks a WebGL context. Browsers cap at ~16
active contexts — after that, new canvases render as black rectangles silently.

### Particle Ring

64 `Points` orbiting the head at radius ~1.6, each with slightly different speed
and y-offset. Animated by directly updating BufferAttribute positions each frame.
`AdditiveBlending` + `depthWrite: false` for glow effect.

## Integration Into Dashboard

```javascript
// On view enter:
function renderJarvisView() {
  $('#content').innerHTML = `... layout with #jAvatarWrap div ...`;
  if (typeof THREE !== 'undefined') {
    avatar = new JARVISAvatar();
    avatar.mount($('#jAvatarWrap'));
  }
}

// On mode change (mic start, TTS play, etc.):
avatar.setMode('listening');

// During TTS playback (per animation frame):
avatar.setAudioLevel(amplitudeFromAnalyser);

// On view leave (CRITICAL — prevents WebGL context leak):
if (avatar) { avatar.dispose(); avatar = null; }
```

## Gotchas

- `createMediaElementSource(audioEl)` can only be called ONCE per Audio element.
  Create a fresh `new Audio(blobUrl)` for each TTS sentence.
- `AudioContext` requires user gesture to start on some browsers. Resume it on
  first mic/click interaction: `ctx.resume()`.
- `IcosahedronGeometry` vertex modification must call `computeVertexNormals()`
  after deformation, or lighting looks wrong.
- `setPixelRatio(Math.min(devicePixelRatio, 2))` — unbounded DPR on retina/4K
  displays tanks FPS.
