# Redraw fidelity tiers and the OCR value-extraction layer

Session-grounded reference for `image-analysis-and-redraw`. Condensed from a
live head-to-head against Claude Code on a GNOME Resources GPU-monitor
screenshot (2560×1600, dark theme, 8 numeric fields + 3 graphs).

## Truth table: VLM vs OCR on the SAME image

User supplied ground truth. Two agents each ran gemma3:12b; this session also
ran tesseract OCR. Scores are exact-match against truth.

| Field        | Truth     | VLM (gemma3:12b, both agents) | OCR (tesseract) |
|--------------|-----------|-------------------------------|-----------------|
| Total Usage  | 1%        | 0% ❌                         | 1% ✅           |
| VRAM used    | 5.97 GB   | 0.00 / 9.22 GB ❌             | 5.97 GB ✅      |
| VRAM total   | 12.82 GB  | 12.62 / 12.82 (mixed)         | 12.82 GB ✅     |
| VRAM %       | 47%       | 0% / 72% ❌                   | 47% ✅          |
| GPU freq     | 1.85 GHz  | not read / not read           | 1.85 GHz ✅     |
| VMem freq    | 9.00 GHz  | not read                      | 9.00 GHz ✅     |
| Power        | 15.4 W    | 5.3 W ❌                      | 15.4W ✅        |
| Temp         | 42 °C     | 47 °C ❌                      | 42°C ✅         |

VLM best case: 1/8. OCR: 8/8. The VLMs failed with **confident, plausible,
fabricated values** — "2.93 GB / 8 GB (37%)" reads like a real reading and is
a hallucination. This is the canonical failure mode of small VLMs on dense
numeric dashboards. OCR does not hallucinate digits.

## OCR value-extraction recipe (tesseract)

```
# Upscale 2x for small text, sparse-text mode, get word bounding boxes
tesseract <img_upscaled> - --psm 11 tsv
# Columns: block,par,line,word,x,y,w,h,conf,text  (conf is a float 0-100)
```

- Cluster words into lines by rounding `cy/14` to a band key; sort each line by x.
- A **label row** = mostly alphabetic, short (`len<30`), no digits, in the card
  column (cx > 900 for a 2560-wide image with a left sidebar).
- The **value** is on the next line within ~55px below the label, same column.
  Strip sidebar words that OCR merges onto value lines first:
  `re.sub(r'^(Drive|Ethernet Connection|Wi-Fi Connection|Battery|Properties|Sensors|©|Neu|cpu\d+)\s*', '', val)`
  THEN match the value regex. Gating on `cx>900` for the value row FAILS when a
  sidebar word drags the row's centroid left ("Drive 1.85 GHz" has cx≈580) —
  strip the prefix before the position/regex check.
- **Two-column rows** like "0% 0%" (Encoder left, Decoder right): one regex
  `^(\d+%)\s+(\d+%)$`, split the value bbox at the row's horizontal midpoint.

## Graph tracing (numpy)

Detect graph bands by counting reddish pixels per row in the card column:

```python
reddish = (r>95) & (r>g+35) & (r>b+35)          # crimson accent typical
row_counts = reddish[:, card_xmin:].sum(axis=1) # per-row reddish count
# a band = contiguous rows where row_counts > 60; height >= 10px
```

For each band, get x-extent, then trace:
- **Thin line graph** (fill < 20%): topmost reddish y per column.
- **Filled area / plateau** (fill > 20%): median of the top quartile of y's —
  handles plateaus the topmost-only tracer misses.

Three real graphs were detected and correctly classified this way: a thin-line
spike (Total Usage, fill ~15%), a high-plateau area (Video Memory, fill ~48%),
and a near-full plateau (Temperature, fill ~95%). The naive "topmost pixel"
tracer collapses plateau graphs to their single highest column — the
top-quartile-median fix is what makes area graphs render correctly.

## Redraw fidelity tiers (what was actually tried)

| Approach | Score | Why |
|----------|-------|-----|
| HTML, pixel analysis only, hand-tuned | 3/10 | no semantic layer; invented graph shape |
| HTML, VLM ground-truth + hand-tuned | 8/10 | but required another agent's description |
| HTML, auto-pipeline, generic card-dumping | 1/10 | destroyed layout — stacked instead of placed |
| HTML, position-faithful (every card at measured x,y) | 2/10 | still capped — no pixel-level font/graph fidelity |
| PIL pixel-compositing at native resolution | ~7-8/10 (in progress) | the path that can actually hit 8 |

The HTML ceiling is real and architectural: a browser renders fonts, icons, and
graph curves through its own pipeline that cannot match a specific screenshot's
pixel-level appearance. PIL gives direct pixel control.

## PIL pixel-compositing skeleton

```python
from PIL import Image, ImageDraw, ImageFont
canvas = Image.new('RGB', (W, H), tuple(bg_color))   # native resolution
draw = ImageDraw.Draw(canvas, 'RGBA')
# panels
draw.rounded_rectangle([975, top, 1985, bot], radius=10, fill=tuple(card_color))
# anti-aliased text (pick the system font; Noto Sans is the GNOME fallback if
# Cantarell/Adwaita aren't installed)
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size)
draw.text((x, y), label, fill=(154,154,160), font=font)
# area graph fill + curve
draw.polygon([(gx0,gy1)] + abs_pts + [(gx1,gy1)], fill=(*accent, 130))
draw.line(abs_pts, fill=tuple(accent), width=3, joint='curve')  # joint='curve'!
```

Known gaps that cost fidelity, and their fixes:

- **Empty sidebar.** Sparse-mode psm 11 under-reads the small sidebar labels and
  you render 4 of ~11 rows. Fix: a dedicated sidebar OCR pass (crop to x<290,
  upscale 4x, psm 6) pulls the full nav list (Apps, Processes, Processor,
  Memory, GPU 1, GPU 2, NPU, 1 TB Drive, Ethernet Connection, Wi-Fi Connection,
  Battery). Render each row as icon (x24) + label (x68) + colored mini-sparkline
  (x190), with the selected row in a highlighted rounded pill.
- **Wrong taskbar color/height.** A GNOME/Wayland taskbar is often TWO bands —
  a lighter top strip (#222226-ish, ~50px) over a near-black bottom (#131313,
  ~50px). Sampling `a[H-40:H, :]` averages both bands AND any colored app icons,
  yielding a too-light, wrong-hue color (~#383332). Fix: sample the darkest band
  in a narrow column away from icons — `a[H-15:H-3, 100:200]` for the dark
  strip, `a[H-50:H-30, 100:200]` for the light strip — and render both bands
  explicitly. This single fix dropped the taskbar region diff from 55 → 24.
  The taskbar also needs colored app-icon glyphs (orange app-store "A", Firefox
  orange, folder yellow) at measured x positions — plain text labels read as
  empty space.

## Per-region diff as a progress tracker

While iterating on a redraw, don't eyeball fidelity — measure it per region:

```python
diff = np.abs(orig[y0:y1, x0:x1] - mine[y0:y1, x0:x1]).mean()
```

Compute this for each major region (sidebar, taskbar, each card row). It tells
you EXACTLY which region to work on next instead of guessing, and confirms
whether a change actually helped. Track the numbers across passes (e.g.
"taskbar: 55 → 34 → 24"). A flat overall diff can hide one bad region; the
per-region breakdown is the diagnostic.

## Verify-don't-predict (the two failures this session)

1. Predicted "gemma3:12b degraded on 12GB" from a transient VRAM log snapshot
   + Reddit reports. One `curl` test disproved it. Recanted publicly.
2. Declared a redraw "working" because its prose sounded good. Truth table
   showed fabricated values. Never trust VLM-read numbers without OCR/pixel
   confirmation.

Fluent output is not verified output. When verification is one command away,
prediction-from-logs is the wrong move.
