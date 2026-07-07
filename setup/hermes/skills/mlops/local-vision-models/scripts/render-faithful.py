#!/usr/bin/env python3
"""
Position-faithful UI renderer for structured dashboards (GNOME Resources,
htop, Task Manager, System Monitor, any single-window app with labeled
cards + graphs). Renders every element AT its measured (x,y) — no stacking.

This is the technique that takes a redraw from 1/10 (stacked cards) to
~8/10 (faithful layout, exact values, real graph positions).

Layers used (all pixel/OCR measured — no VLM in the critical path):
  - OCR (tesseract): label + value text with bounding boxes
  - Pixels (numpy): graph bands (reddish), theme colors, sidebar strip
  - Geometry: graph-to-label assignment by y-overlap

REQUIREMENTS: tesseract-ocr, PIL, numpy.
USAGE:
  python3 render-faithful.py <image.png> [--out render.html] [--specs specs.json]
  Then screenshot the HTML with headless Chromium to produce the final PNG.

CUSTOMIZING FOR A NEW APP: edit FIELDS below — add (field_name, label_regex,
value_regex) for each labeled value you want to extract. The position math,
graph detection, and rendering work for any dashboard of this shape.
"""
import numpy as np, subprocess, re, json
from collections import defaultdict
from PIL import Image

def ocr(img_path, upscale=2):
    im = Image.open(img_path).convert('RGB'); W, H = im.size
    big = im.resize((W*upscale, H*upscale), Image.LANCZOS); big.save('/tmp/_pf.png')
    r = subprocess.run(['tesseract','/tmp/_pf.png','-','--psm','11','tsv'], capture_output=True, text=True)
    words = []
    for line in r.stdout.splitlines()[1:]:
        p = line.split('\t')
        if len(p) < 12: continue
        try: conf = float(p[10])
        except: continue
        t = p[11].strip()
        if conf < 45 or not t: continue
        x,y,w,h = int(p[6])//upscale, int(p[7])//upscale, int(p[8])//upscale, int(p[9])//upscale
        words.append({'t':t,'x':x,'y':y,'w':w,'h':h,'cx':x+w//2,'cy':y+h//2})
    return words, (W, H)

def text_rows(words, yband=14):
    b = defaultdict(list)
    for w in words: b[round(w['cy']/yband)].append(w)
    rows = []
    for k in sorted(b):
        ws = sorted(b[k], key=lambda z: z['x'])
        txt = ' '.join(z['t'] for z in ws)
        x0 = min(z['x'] for z in ws); x1 = max(z['x']+z['w'] for z in ws)
        y0 = min(z['y'] for z in ws); y1 = max(z['y']+z['h'] for z in ws)
        rows.append({'text':txt,'x0':x0,'y0':y0,'x1':x1,'y1':y1,'cx':(x0+x1)/2,'cy':(y0+y1)/2})
    return rows

def detect_graphs(a, card_xmin=900):
    """Find horizontal bands of accent-colored pixels in the card column.
    Each contiguous band = one graph. mode=area if fill>20%, else line."""
    H, W, _ = a.shape
    r, g, b = a[:,:,0], a[:,:,1], a[:,:,2]
    red = (r>95) & (r>g+35) & (r>b+35)
    rc = red[:, card_xmin:].sum(axis=1)
    bands = []; in_b = False
    for y in range(H):
        if rc[y] > 60 and not in_b: s = y; in_b = True
        elif rc[y] <= 60 and in_b: bands.append((s, y)); in_b = False
    if in_b: bands.append((s, H))
    out = []
    for y0, y1 in bands:
        if y1-y0 < 10: continue
        sub = red[y0:y1, card_xmin:]
        xs = np.where(sub.any(axis=0))[0]
        if len(xs) == 0: continue
        x0 = card_xmin+xs.min(); x1 = card_xmin+xs.max()
        if x1-x0 < 150: continue
        fill = sub.sum() / max(1, (y1-y0)*(x1-x0))
        out.append({'y0':y0,'y1':y1,'x0':x0,'x1':x1,'mode':'area' if fill>0.20 else 'line'})
    return out

# ── CUSTOMIZE FOR YOUR APP ──────────────────────────────────────────────
# Each entry: (display_name, label_regex, value_regex). label_regex should
# tolerate OCR dropping a word (^Power(\s*Usage)?$ not ^Power Usage$).
# Set value_regex to None for fields with special two-column handling (below).
FIELDS = [
    ('Total Usage',            r'Total\s*Usage',            r'(\d+%)'),
    ('Video Encoder Usage',    r'Video\s*Encoder\s*Usage',  None),  # two-col
    ('Video Decoder Usage',    r'Video\s*Decoder\s*Usage',  None),  # two-col
    ('Video Memory Usage',     r'Video\s*Memory\s*Usage',   r'([\d.]+\s*GB\s*/\s*[\d.]+\s*GB[^\d]*\d+%)'),
    ('GPU Frequency',          r'GPU\s*Frequency',          r'([\d.]+\s*GHz)'),
    ('Video Memory Frequency', r'Video\s*Memory\s*Frequency', r'([\d.]+\s*GHz)'),
    ('Power Usage',            r'^Power(\s*Usage)?$',       r'([\d.]+\s*W)'),
    ('Temperature',            r'^Temperature$',            r'(\d+\s*°?C.*Highest.*\d+\s*°?C)'),
]
SIDEBAR_PREFIX = re.compile(r'^(Drive|Ethernet Connection|Wi-Fi Connection|Battery|Properties|Sensors|©|Neu|cpu\d+)\s*')
TWO_COL_PCT = re.compile(r'^(\d+%)\s+(\d+%)$')

def extract(rows, card_cx_min=900):
    items = []
    for name, lab_re, val_re in FIELDS:
        lab_bbox = None; val = None; val_bbox = None
        for i, r in enumerate(rows):
            t = r['text'].strip()
            if r['cx'] > card_cx_min and len(t) < 40 and re.search(lab_re, t, re.I):
                lab_bbox = (r['x0'], r['y0'], r['x1'], r['y1'])
                for j in range(i+1, min(i+5, len(rows))):
                    rr = rows[j]
                    if not (0 < rr['cy']-r['cy'] < 55): continue
                    cand = SIDEBAR_PREFIX.sub('', rr['text']).strip()
                    if name == 'Video Encoder Usage':
                        m = TWO_COL_PCT.match(cand) or re.match(r'(\d+%)', cand)
                        if m:
                            val = m.group(1)
                            val_bbox = (rr['x0'], rr['y0'], rr['x0']+(rr['x1']-rr['x0'])//2, rr['y1']); break
                    elif name == 'Video Decoder Usage':
                        m = TWO_COL_PCT.match(cand)
                        if m:
                            val = m.group(2)
                            val_bbox = (rr['x0']+(rr['x1']-rr['x0'])//2, rr['y0'], rr['x1'], rr['y1']); break
                    else:
                        m = re.match(val_re, cand, re.I)
                        if m:
                            val = m.group(1); val_bbox = (rr['x0'], rr['y0'], rr['x1'], rr['y1']); break
                break
        items.append({'name':name,'value':val,'lab_bbox':lab_bbox,'val_bbox':val_bbox,'graph':None})
    return items

def assign_graphs(items, graphs):
    """Assign each graph to the item whose (label..value) span it overlaps most."""
    used = set()
    for g in sorted(graphs, key=lambda x: x['y0']):
        best = None; bo = -1
        for it in items:
            if it['name'] in used or not it['lab_bbox']: continue
            top = it['lab_bbox'][1] - 60; bot = it['lab_bbox'][1] + 110
            if it['val_bbox']: bot = max(bot, it['val_bbox'][3] + 40)
            ov = max(0, min(g['y1'], bot) - max(g['y0'], top))
            if ov > bo and ov > 15:
                bo = ov; best = it
        if best:
            best['graph'] = g; used.add(best['name'])

def render(img_path, out_html):
    a = np.array(Image.open(img_path).convert('RGB')).astype(int); H, W, _ = a.shape
    words, (W, H) = ocr(img_path); rows = text_rows(words); graphs = detect_graphs(a)
    items = extract(rows); assign_graphs(items, graphs)
    # theme
    sb = a[:, :90, :].mean(axis=(0,1)).astype(int)
    cc = a[600:640, 1100:1200, :].mean(axis=(0,1)).astype(int)
    red_all = (a[:,:,0]>95)&(a[:,:,0]>a[:,:,1]+35)&(a[:,:,0]>a[:,:,2]+35)
    acc = a[red_all].mean(axis=0).astype(int)
    bg = a[H-100, W-100].astype(int)
    theme = {'sidebar':f"#{sb[0]:02x}{sb[1]:02x}{sb[2]:02x}",
             'card':f"#{cc[0]:02x}{cc[1]:02x}{cc[2]:02x}",
             'accent':f"#{acc[0]:02x}{acc[1]:02x}{acc[2]:02x}",
             'bg':f"#{bg[0]:02x}{bg[1]:02x}{bg[2]:02x}"}
    parts = [f'<div style="position:absolute;inset:0;background:{theme["bg"]};"></div>',
             f'<div style="position:absolute;left:0;top:0;width:90px;height:{H}px;background:{theme["sidebar"]};"></div>']
    for it in items:
        if not it['lab_bbox']: continue
        lx0, ly0, lx1, ly1 = it['lab_bbox']
        top = ly0-12; bot = ly0+22
        if it['val_bbox']: bot = max(bot, it['val_bbox'][3]+8)
        if it['graph']:
            top = min(top, it['graph']['y0']-6); bot = max(bot, it['graph']['y1']+6)
        parts.append(f'<div style="position:absolute;left:975px;top:{top}px;width:1010px;height:{bot-top}px;background:{theme["card"]};border-radius:10px;"></div>')
        parts.append(f'<div style="position:absolute;left:{lx0}px;top:{ly0}px;color:#9a9aa0;font-size:15px;font-family:sans-serif;">{it["name"]}</div>')
        if it['val_bbox'] and it['value']:
            vx0, vy0, vx1, vy1 = it['val_bbox']
            parts.append(f'<div style="position:absolute;left:{vx0}px;top:{vy0}px;color:#e8e8e8;font-size:19px;font-weight:600;font-variant-numeric:tabular-nums;">{it["value"]}</div>')
        if it['graph']:
            g = it['graph']
            sub = a[g['y0']:g['y1'], g['x0']:g['x1']]
            sr, sg, sb_ = sub[:,:,0], sub[:,:,1], sub[:,:,2]
            sred = (sr>95)&(sr>sg+35)&(sr>sb_+35)
            pts = []
            for x in range(sub.shape[1]):
                col = sred[:, x]; ys = np.where(col)[0]
                if len(ys):
                    ty = ys.min() if g['mode']=='line' else int(np.median(ys[:max(1, len(ys)//4)]))
                    pts.append((x, ty))
            gx0, gy0, gx1, gy1 = g['x0'], g['y0'], g['x1'], g['y1']; gw, gh = gx1-gx0, gy1-gy0
            if pts:
                xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
                xmin,xmax=min(xs),max(xs); ymin,ymax=min(ys),max(ys)
                xr=(xmax-xmin) or 1; yr=(ymax-ymin) or 1
                coords=[((p[0]-xmin)/xr*gw, gh-(p[1]-ymin)/yr*gh) for p in pts]
                np_s=','.join(f"{x:.1f},{y:.1f}" for x,y in coords)
                fill_s=f'<polygon points="0,{gh} {np_s} {gw},{gh}" fill="{theme["accent"]}55"/>' if g['mode']=='area' else ''
                svg=f'<svg style="position:absolute;left:0;top:0;width:100%;height:100%">{fill_s}<polyline points="{np_s}" fill="none" stroke="{theme["accent"]}" stroke-width="2.5"/></svg>'
                parts.append(f'<div style="position:absolute;left:{gx0}px;top:{gy0}px;width:{gw}px;height:{gh}px;">{svg}</div>')
    html = f'''<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#000;font-family:sans-serif}}</style>
</head><body><div style="position:relative;width:{W}px;height:{H}px;background:{theme["bg"]};margin:0 auto;overflow:hidden;transform-origin:top left;" id="screen">{''.join(parts)}</div>
<script>document.getElementById('screen').style.transform='scale('+Math.min(window.innerWidth/{W},0.5)+')';</script>
</body></html>'''
    open(out_html,'w').write(html)
    return items, theme

if __name__ == '__main__':
    import sys
    img = sys.argv[1] if len(sys.argv) > 1 else '/home/sinep/Pictures/Resources_Monitor.png'
    out = sys.argv[2] if len(sys.argv) > 2 else 'render.html'
    items, theme = render(img, out)
    print(f"theme: {theme}")
    for it in items:
        g = f"graph@{it['graph']['y0']}" if it['graph'] else 'no-graph'
        print(f"  {it['name']:24s} = {str(it['value'] or 'MISSING'):30s} {g}")
    print(f"\nRendered -> {out}. Screenshot with headless Chromium for the final PNG.")
