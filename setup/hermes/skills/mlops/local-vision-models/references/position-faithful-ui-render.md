# Position-faithful UI rendering

The technique that takes a UI redraw from 1/10 (unrecognizable) to ~8/10
(recognizable, values correct, graphs in the right place). Use whenever the
task is "reconstruct / redraw / reproduce this screenshot" AND the goal is
a faithful likeness, not just a schematic.

## The core mistake: stacking vs. placing

A generic card-dumping renderer takes extracted (label, value) pairs and
emits them in a vertical flex/grid — stacked one under the next. On any
real dashboard this scores ~1/10 because the original layout is two-
dimensional: cards sit in a specific column, at specific y-coordinates,
with graphs at specific positions relative to their labels.

**The fix is to honor measured coordinates.** Extract every element's
bounding box (from OCR for text, from pixel-band detection for graphs),
then render each element with `position:absolute; left:{x}px; top:{y}px`
at its measured location. Do not stack. The output jumps from 1/10 to ~8/10
on the same extraction data, with zero change to what was extracted — only
to where it is placed.

## The extraction steps (all pixel-measured, no guessing)

1. **Sidebar strip**: detect by sampling the leftmost ~90px column average.
   Render as a solid vertical strip.
2. **Graph bands**: scan for horizontal bands of accent-colored pixels in
   the card column (x > ~900 for a typical right-of-sidebar layout). Each
   contiguous band of reddish rows (count > ~60/row) is one graph. Record
   its (y0, y1, x0, x1). Classify mode: `area` if fill fraction > ~20%,
   else `line`.
3. **Label + value pairs**: OCR all words with bounding boxes, cluster
   into text rows by y-center (band ~14px). For each known label regex,
   find the row whose text matches AND whose center-x is in the card
   column (> ~900). The value is the next text row within ~55px below,
   with sidebar/neighbor words stripped first.
4. **Theme**: average a few semantic regions — sidebar bg, a card panel
   area, the accent color (mean of reddish pixels), the app bg.

See `scripts/render-faithful.py` for the working implementation.

## OCR label-value pairing pitfalls (all hit in practice)

The label-above-value heuristic is fragile. These are the failure modes
that cost exact-value accuracy, in order of how often they bite:

### Pitfall 1 — sidebar words merged into the value row

OCR's row-clustering groups words by y-center. A sidebar label ("Drive",
"Ethernet Connection") at a similar y to the card's value gets merged into
the same text row: `"Drive 1.85 GHz"`. The value row's center-x then looks
like it's in the sidebar zone, and a naive `cx > 900` guard rejects it,
losing the value.

**Fix:** strip the known sidebar prefix BEFORE checking position or matching.
Maintain a prefix regex: `^(Drive|Ethernet Connection|Wi-Fi Connection|
Battery|Properties|Sensors|©|Neu|cpu\d+)\s*`. Strip, then match the value
regex against what remains. Do not gate the value row on `cx > 900` after
the label is already confirmed in the card column.

### Pitfall 2 — two-column value rows ("0% 0%")

When two adjacent cards share a value row (e.g. Video Encoder / Video
Decoder each showing "0%", OCR reads the row as `"0% 0%"`). A single
`(\d+%)` match returns the left value for both fields — the Decoder value
is lost.

**Fix:** detect the two-percent pattern `^(\d+%)\s+(\d+%)$` explicitly.
Left field gets group(1) with a bbox over the left half of the row; right
field gets group(2) with a bbox over the right half. Split the row's
x-range at its midpoint.

### Pitfall 3 — label text dropped by OCR ("Power" alone)

OCR sometimes drops a word: label reads `"Power"` not `"Power Usage"`.
A strict `^Power\s*Usage$` regex misses it.

**Fix:** make label regexes tolerant of dropped words: `^Power(\s*Usage)?$`.
Same for any multi-word label where OCR can fragment it.

### Pitfall 4 — value below a DIFFERENT label's row

When labels are close vertically, the "next row within 55px" heuristic can
cross into the next card's label row. Always confirm the candidate row
matches the VALUE regex, not just "is nearby."

### Pitfall 5 — graph above the label, not below

Some layouts put the graph ABOVE its label (big number + graph row above
the label row). If you only look for graphs below each label, you miss
them. Assign graphs by y-overlap with the (label..value) span, not by
"nearest graph below."

## Graph-to-label assignment by y-overlap

Don't assign each graph to the nearest label by center-distance — that
misassigns when labels are close. Instead compute the y-overlap between
each graph's (y0,y1) and each label's vertical span (label.y - margin ..
value.y + margin). Assign the graph to the label with the most overlap,
above a threshold (~15px). Each graph → one label; each label → at most
one graph.

## Rendering the traced graph as SVG

The pixel tracer returns points in image coordinates. To render in a
viewport-scaled SVG, normalize the points to the graph's bbox:

```
xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
xmin,xmax = min(xs),max(xs); ymin,ymax = min(ys),max(ys)
coords = [((p[0]-xmin)/(xmax-xmin)*gw, gh-(p[1]-ymin)/(ymax-ymin)*gh) for p in pts]
# SVG: polyline points=coords, plus a filled polygon if mode=='area'
```

`gh-(p[1]-ymin)/...` flips y so that "higher in the image" (lower y) maps
to "higher on the graph" — without this the graph renders upside-down.

## Honest scope (what this can and can't do)

Position-faithful rendering gets the STRUCTURE right: every card at its
measured (x,y), every value exact (OCR), every graph traced at its real
position with its real shape. It does NOT achieve pixel-perfect fidelity:

- Icon glyphs are stand-ins (SVG approximations, not the real icons)
- Fonts are a sans-serif approximation, not the system font
- Card border radii and padding are approximate, not measured
- Anti-aliasing on graph strokes differs from the original
- Complex scenes (wallpapers, overlapping windows, photographic content,
  thumbnails of other images) do not generalize — this technique is for
  structured single-window dashboards/apps

Declare these limits to the user. A position-faithful redraw of a
dashboard is ~8/10, not 10/10, and that's an honest ceiling for this
architecture. Higher fidelity needs pixel synthesis or a generative
image model conditioned on the extracted structure.

## The render recipe

1. Build the HTML at the ORIGINAL image resolution (e.g. 2560x1600), with
   every element `position:absolute` at measured coords.
2. Scale the whole container down via CSS `transform: scale(...)` so it
   fits the viewport.
3. Screenshot the container with headless Chromium (Playwright). See
   `references/blind-image-reconstruction.md` for the chrome-linux64 path
   gotcha.
4. Make a side-by-side composite (original | render) at matched height so
   the user can score fidelity honestly.
