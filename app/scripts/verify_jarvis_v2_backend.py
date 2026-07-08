#!/usr/bin/env python3
"""Backend smoke test for JARVIS v2: visual memory (SigLIP+OCR), VLM describe,
SDXL imagine, file exchange, sessions v2, briefing/events, WS TTS streaming.
Run: ~/nexus-agent-os/.venv/bin/python verify_jarvis_backend.py
"""
import asyncio, io, json, os, ssl, sys, time

ROOT = os.path.expanduser("~/nexus-agent-os")
sys.path.insert(0, ROOT); sys.path.insert(0, ROOT + "/scripts")
import httpx, urllib3
urllib3.disable_warnings()
import auth
from PIL import Image, ImageDraw

BASE = "https://127.0.0.1:8777"
P, F = 0, 0

def ok(name, cond, extra=""):
    global P, F
    if cond: P += 1; print(f"  PASS  {name}")
    else:    F += 1; print(f"  FAIL  {name}  {extra}")

def jpeg(draw_fn, size=(640, 480)):
    img = Image.new("RGB", size, (24, 24, 40))
    draw_fn(ImageDraw.Draw(img))
    b = io.BytesIO(); img.save(b, "JPEG", quality=88)
    return b.getvalue()

async def ws_tts_test(token):
    import websockets
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    chunks, done = 0, False
    t0 = time.time(); first = None
    async with websockets.connect(
            "wss://127.0.0.1:8777/ws/jarvis/tts", ssl=ctx,
            additional_headers={"Cookie": f"nexus_session={token}"}) as ws:
        await ws.send(json.dumps({"text": "Hello, this is a streaming synthesis test."}))
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(msg, bytes):
                chunks += 1
                if first is None: first = time.time() - t0
            else:
                d = json.loads(msg)
                done = d.get("done", False)
                break
    return chunks, done, first

def main():
    token = auth.create_session("u_owner", "jarvis-v2-probe")
    c = httpx.Client(base_url=BASE, verify=False, timeout=180)
    c.cookies.set("nexus_session", token)
    try:
        # ── visual memory: index a frame WITH TEXT (OCR) + one distinct shape ──
        f1 = jpeg(lambda d: (d.rectangle([200, 140, 440, 340], fill=(210, 40, 40)),
                             d.text((210, 380), "PROJECT PHOENIX BUDGET", fill=(240, 240, 240))))
        r = c.post("/api/jarvis/vision/frame", files={"file": ("f.jpg", f1)},
                   params={"kind": "webcam"}).json()
        ok("frame 1 indexed (red box + text)", r.get("indexed") is True, str(r))
        ok("OCR extracted text", (r.get("ocr_chars") or 0) > 5, str(r))

        r2 = c.post("/api/jarvis/vision/frame", files={"file": ("f.jpg", f1)},
                    params={"kind": "webcam"}).json()
        ok("duplicate frame skipped", r2.get("dup") is True, str(r2))

        f2 = jpeg(lambda d: d.ellipse([160, 100, 480, 400], fill=(30, 120, 220)))
        r3 = c.post("/api/jarvis/vision/frame", files={"file": ("f.jpg", f2)},
                    params={"kind": "screen"}).json()
        ok("frame 2 indexed (blue circle)", r3.get("indexed") is True, str(r3))

        s = c.post("/api/jarvis/vision/search", json={"query": "a red box"}).json()
        hits = s.get("hits") or []
        ok("search returns hits", len(hits) >= 2, str(s)[:200])
        ok("red box outranks blue circle",
           hits and hits[0]["file"].endswith("webcam.jpg"),
           str([(h['file'], h['score']) for h in hits[:3]]))
        s2 = c.post("/api/jarvis/vision/search", json={"query": "phoenix budget document"}).json()
        h2 = s2.get("hits") or []
        ok("OCR boost finds text frame", h2 and h2[0]["file"].endswith("webcam.jpg"),
           str([(h['file'], h['score'], h['ocr'][:40]) for h in h2[:3]]))
        fr = c.get(f"/api/jarvis/vision/frame/{hits[0]['file']}")
        ok("stored frame served", fr.status_code == 200 and len(fr.content) > 1000)
        st = c.get("/api/jarvis/vision/status").json()
        ok("vision status counts frames", (st.get("frames") or 0) >= 2, str(st))

        # ── understanding: local VLM ──
        r = c.post("/api/jarvis/see", json={
            "image_b64": __import__("base64").b64encode(f1).decode(),
            "prompt": "What large colored shape is in this image? Answer in one short sentence."})
        d = r.json()
        ok("VLM describe works", r.status_code == 200 and "red" in d.get("description", "").lower(),
           str(d)[:200])

        # ── creation: SDXL-Turbo (first call loads the pipeline — slow) ──
        r = c.post("/api/jarvis/imagine", json={"prompt": "a glowing blue cube on a dark table, studio light"})
        d = r.json()
        ok("imagine generates an image", r.status_code == 200 and d.get("ok"), str(d)[:200])
        if d.get("ok"):
            img = c.get(d["url"])
            ok("generated image downloadable", img.status_code == 200 and len(img.content) > 20000)

        # ── file exchange ──
        r = c.post("/api/jarvis/files", files={"file": ("notes.md", b"# hello jarvis\n")}).json()
        ok("file upload", r.get("ok") is True, str(r))
        names = [f["name"] for f in c.get("/api/jarvis/files").json().get("files", [])]
        ok("file listed (incl. generated image)", "notes.md" in names and len(names) >= 2, str(names))

        # ── sessions v2 ──
        s1 = c.post("/api/jarvis/session").json().get("session_id")
        s2 = c.post("/api/jarvis/session").json().get("session_id")
        ok("fresh sessions differ", s1 and s2 and s1 != s2, f"{s1} {s2}")
        my = c.get("/api/jarvis/my-sessions").json()
        ids = [h["id"] for h in my.get("sessions", [])]
        ok("my-sessions lists both", s1 in ids and s2 in ids and my.get("current") == s2)
        sw = c.post("/api/jarvis/session/switch", json={"id": s1}).json()
        ok("switch back to older session", sw.get("ok") is True
           and c.get("/api/jarvis/my-sessions").json().get("current") == s1)
        ok("switch to foreign session rejected",
           c.post("/api/jarvis/session/switch", json={"id": "api_deadbeef"}).status_code == 404)
        tt = c.post("/api/jarvis/session/title", json={"id": s1, "title": "probe chat"}).json()
        ok("session titling", tt.get("ok") is True)

        # ── briefing + events ──
        b = c.get("/api/jarvis/briefing").json()
        ok("briefing text", isinstance(b.get("text"), str) and len(b["text"]) > 20, str(b)[:120])
        e = c.get("/api/jarvis/events", params={"since": time.time() - 60}).json()
        ok("events endpoint shape", "events" in e and "now" in e)

        # ── WS TTS streaming ──
        chunks, done, first = asyncio.run(ws_tts_test(token))
        ok("WS TTS streams PCM chunks", chunks >= 1 and done, f"chunks={chunks} done={done}")
        ok("first audio chunk fast (<2.5s cold)", first is not None and first < 2.5, f"first={first}")

        # cleanup vision points + files
        c.delete("/api/jarvis/vision")
        for n in names:
            c.delete(f"/api/jarvis/files/{n}")
    finally:
        auth.destroy_session(token)
    print(f"\n=== JARVIS BACKEND RESULT: {P} passed, {F} failed ===")
    sys.exit(1 if F else 0)

main()
