#!/usr/bin/env python3
"""Render a fixed-dimension HTML/CSS/SVG design to a crisp PNG via headless Chromium.

Copy this next to your design's HTML file, edit SIZE + HTML/OUT paths, run it.
Requires: playwright (and `playwright install chromium` once).

Discipline baked in:
  - device_scale_factor=2  → crisp on retina / zoom / print (logical size unchanged).
  - document.fonts.ready   → webfonts fully loaded before the screenshot.
  - networkidle + settle   → gradients / clip-paths / SVG paint landed.
  - exact clip at logical size → never screenshots outside the artboard.
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

# ---- edit these four lines -----------------------------------------------
SIZE = (1080, 1080)                       # logical target (width, height) in CSS px
DEVICE_SCALE = 2                          # 2 = retina-crisp; 1 = blurry on zoom
HTML = Path(__file__).resolve().parent / "ad.html"
OUT = Path(__file__).resolve().parent / "ad.png"
# --------------------------------------------------------------------------

W, H = SIZE

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(
            viewport={"width": W, "height": H},
            device_scale_factor=DEVICE_SCALE,
        )
        page = await ctx.new_page()
        await page.goto(HTML.resolve().as_uri(), wait_until="networkidle")
        await page.evaluate("document.fonts.ready")
        await page.wait_for_timeout(500)
        await page.screenshot(
            path=str(OUT),
            clip={"x": 0, "y": 0, "width": W, "height": H},
            type="png",
        )
        await browser.close()
    from PIL import Image
    im = Image.open(OUT)
    print(f"OK wrote {OUT.name} ({im.size[0]}x{im.size[1]} actual, "
          f"{W}x{H} logical, {OUT.stat().st_size/1024:.0f} KB)")

asyncio.run(main())
