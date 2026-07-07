# Blind image reconstruction (no working VLM backend)

When every available vision backend is broken (auxiliary VLM out of
credit, wrong plan entitlement, local VLM producing garbage), you can
still produce a recognizable reconstruction of a screenshot using **raw
pixel analysis** — no model needed. This is the visual-layer complement
to the OCR-first numbers pipeline: OCR gets you the text/values, pixel
analysis gets you the colors, graph shapes, and layout that OCR can't
see.

Use this when a user asks you to "draw / reconstruct / reproduce this
image" and you have no working VLM, or when you need to verify a VLM's
visual claims against ground truth.

## Core principle

Stop guessing. Measure. Everything you'd otherwise invent (graph shape,
panel colors, icon positions, proportions) can be extracted
deterministically with numpy + PIL. A reconstruction built from
measurements scored 79.6% palette-overlap with the original; one built
from guesses scored ~30% and was rated 3/10.

## The four measurements that matter

All via `numpy` on a `PIL.Image.convert('RGB')` array `a` of shape
`(H, W, 3)`.

### 1. Region colors — average over a box, never sample a pixel

```python
def region_avg(a, x0, y0, x1, y1):
    return a[y0:y1, x0:x1, :].mean(axis=(0,1)).astype(int)
```

Sample a single pixel and you'll hit an icon, a border, or anti-aliasing
noise. Average a box inside a uniform region. Verify the box is uniform
(`.std() < 5`) before trusting it — if std is high, you crossed a
boundary; shrink and retry.

### 2. Graph polylines — trace the accent color column by column

Build a mask for the line color (reddish accents: `r>90 & r>g+35 &
r>b+35 & g<130 & b<130`), then for each x-column in the graph's row
band, take the topmost masked y. That gives you the real polyline.

```python
polyline = []
for x in range(x_start, x_end):
    col = mask[y_lo:y_hi, x]
    ys = np.where(col)[0]
    if len(ys):
        polyline.append((x, y_lo + ys.min()))
```

Normalize to (0..1, 0..1) and emit as an SVG `<path>`. The fill area is
the same polygon closed to the baseline. Real KDE/KDE-clone usage graphs
are a flat baseline with sparse spikes — NOT the smooth squiggle you'll
be tempted to draw.

### 3. Icon / row positions — std-dev peaks on a strip

Icons live in a vertical sidebar; rows live in a panel. Both show up as
bands of high pixel variance against a uniform background. Slide a
window down the strip and compute `.std()` per window; peaks = elements.

```python
for y in range(0, H, 2):
    block = a[y:y+48, x_lo:x_hi, :].astype(float)
    strip_var.append((y, block.std()))
# top-N variance peaks, deduped at >40px spacing, = icon centers
```

### 4. Panel / card boundaries — color-classify rows and columns

Classify each pixel as `card-blue` / `bg-dark` / `accent` / `other`, then
threshold row and column sums of the `card-blue` mask to find the
bounding box of each panel. This gives you real geometry (header height,
taskbar height, card x/y extent) without eyeballing.

## Don't fabricate the parts you can't measure

The honest split: pixel analysis gets you **structure, colors, graph
shape, layout** (the schematic layer). It does NOT get you **icon glyph
designs, font rendering, anti-aliased curves**. Use generic SVG stand-ins
for icons positioned at measured coordinates; declare the font limitation
upfront. A reconstruction that admits its limits is more useful than one
that confabulates icons.

## Rendering: headless Chromium via Playwright

Render the reconstruction HTML to PNG for side-by-side comparison.

```python
from playwright.sync_api import sync_playwright
import os
# Hermes bundles chromium under ~/.cache/ms-playwright/. NOTE: the binary
# lives at chrome-linux64/chrome on this host, NOT chrome-linux/chrome
# (the default Playwright probes first). Point at it explicitly:
exec_path = os.path.expanduser(
    '~/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome')
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exec_path, args=['--no-sandbox'])
    pg = b.new_page(viewport={"width": 1280, "height": 820})
    pg.goto("file:///abs/path/reconstruction.html")
    pg.wait_for_timeout(600)
    pg.locator(".screen").screenshot(path="render.png")
    b.close()
```

`pip install --break-system-packages playwright` if the module is missing
(the binary cache is usually already present from MCP/Hermes setup). If
`chrome-linux/chrome` is reported missing, switch to `chrome-linux64/chrome`.

## Objective fidelity check without a VLM

You can't see either image, so score objectively with palette-overlap
(histogram intersection after coarse quantization):

```python
from collections import Counter
def quant(a, levels=8): return (a // (256//levels)) * (256//levels)
oc = Counter(map(tuple, quant(orig_arr).reshape(-1,3)))
mc = Counter(map(tuple, quant(render_arr).reshape(-1,3)))
overlap = sum(min(oc.get(c,0), mc.get(c,0)) for c in oc)
fidelity_pct = 100 * overlap / sum(oc.values())
```

A measured reconstruction lands ~75-80%; a guessed one ~25-35%. This is
the number to report when you can't self-judge visually.

## Limitations (declare these to the user)

- Icon glyphs are stand-ins, not the real artwork.
- Font rendering differs from the original toolkit (browser fonts vs
  Qt/GTK).
- Sub-pixel spacing and border radii are approximate.
- This produces a **schematic likeness**, not a pixel-exact clone. For
  pixel-exact visual fidelity you need a working VLM that actually saw
  the image.
