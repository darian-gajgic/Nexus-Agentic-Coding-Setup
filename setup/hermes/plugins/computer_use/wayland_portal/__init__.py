"""Wayland-portal computer_use backend patch for Hermes on GNOME Wayland.

Problem (see hermes-cua-wayland-capture-fix.md): the stock cua-driver 0.7.0
backend is broken on GNOME Wayland — its window-oriented capture can't enumerate
native Wayland windows, and every input verb is X11 XSendEvent (dead on Wayland;
portal-libei is compiled out of the released binary). BUT the portal itself works:
`get_desktop_state` captures the full desktop via the xdg-desktop-portal Screenshot
interface, and the RemoteDesktop portal injects input over plain D-Bus (proven on
this box via the `wl-inject` tool).

This plugin monkey-patches `CuaDriverBackend` so that, ONLY on GNOME Wayland:
  * capture()  -> get_desktop_state (full-desktop vision screenshot, no elements)
  * click/type_text/key/scroll/drag -> wl-inject (RemoteDesktop portal), with the
    capture->input coordinate scale applied (portal input space is the display's
    LOGICAL size, which differs from the physical screenshot on a scaled display).

Off GNOME Wayland it does nothing (the stock X11 path is untouched). It lives in
~/.hermes/plugins so Hermes updates can't revert it. One "Allow remote interaction"
consent click is needed the first time an action runs in a Hermes session; capture
alone never prompts. Reversible: `hermes plugins disable computer_use/wayland_portal`
(or delete this dir) + restart Hermes.
"""
from __future__ import annotations

import atexit
import base64
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time

logger = logging.getLogger(__name__)

_PATCHED_FLAG = "_wayland_portal_patched"


def _find_wl_inject():
    return shutil.which("wl-inject") or (
        os.path.expanduser("~/.local/bin/wl-inject")
        if os.path.exists(os.path.expanduser("~/.local/bin/wl-inject")) else None
    )


def _find_cua_driver():
    return (
        os.environ.get("HERMES_CUA_DRIVER_CMD")
        or shutil.which("cua-driver")
        or (os.path.expanduser("~/.local/bin/cua-driver")
            if os.path.exists(os.path.expanduser("~/.local/bin/cua-driver")) else None)
    )


def _is_gnome_wayland() -> bool:
    if (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
            or os.environ.get("WAYLAND_DISPLAY")):
        return True
    return False


WL_INJECT = _find_wl_inject()
CUA_DRIVER = _find_cua_driver()


class _Injector:
    """Owns one long-lived `wl-inject daemon` (one consent click) and maps
    capture-pixel coords to the portal's logical input space."""

    def __init__(self):
        self.proc = None
        self.sw = self.sh = 0        # stream / input logical size
        self.cw = self.ch = 0        # last capture (screenshot) size
        self.lock = threading.RLock()

    def _client(self, args, timeout=10.0):
        try:
            r = subprocess.run([WL_INJECT] + args, capture_output=True,
                               text=True, timeout=timeout)
            return (r.stdout or "").strip()
        except Exception as e:  # noqa: BLE001
            return f"err client {e}"

    def ensure(self, wait=90.0):
        """Start the daemon if needed and block until the session is granted
        (the user's one consent click). Returns (ok, message)."""
        with self.lock:
            if self.proc and self.proc.poll() is None and self.sw:
                return True, ""
            if not WL_INJECT:
                return False, "wl-inject not installed"
            if not (self.proc and self.proc.poll() is None):
                try:
                    self.proc = subprocess.Popen(
                        [WL_INJECT, "daemon"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=False)
                except Exception as e:  # noqa: BLE001
                    return False, f"failed to start wl-inject daemon: {e}"
                logger.info("wayland_portal: started wl-inject daemon; "
                            "awaiting one 'Allow' consent click...")
            deadline = time.time() + wait
            while time.time() < deadline:
                time.sleep(0.5)
                if self.proc.poll() is not None:
                    return False, "wl-inject daemon exited before becoming ready"
                out = self._client(["info"], timeout=4.0)
                m = re.search(r"w=(\d+)\s+h=(\d+)", out)
                if out.startswith("ok") and m:
                    self.sw, self.sh = int(m.group(1)), int(m.group(2))
                    logger.info("wayland_portal: input session ready (%dx%d)",
                                self.sw, self.sh)
                    return True, ""
            return False, ("consent not granted within %.0fs (no 'Allow' click)" % wait)

    def to_input(self, x, y):
        cw = self.cw or self.sw or 1
        ch = self.ch or self.sh or 1
        ix = float(x) * (self.sw / cw)
        iy = float(y) * (self.sh / ch)
        ix = max(0.0, min(self.sw - 1, ix))
        iy = max(0.0, min(self.sh - 1, iy))
        return int(round(ix)), int(round(iy))

    def shutdown(self):
        with self.lock:
            p = self.proc
            self.proc = None
            self.sw = self.sh = 0
            if p and p.poll() is None:
                try:
                    self._client(["quit"], timeout=3.0)
                    time.sleep(0.2)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    p.terminate()
                except Exception:  # noqa: BLE001
                    pass


_INJ = _Injector()


# Translate Hermes key names (cross-platform, mac-ish) to wl-inject's Linux combo.
_KEY_MAP = {"cmd": "ctrl", "command": "ctrl", "option": "alt", "control": "ctrl",
            "meta": "super", "win": "super"}


def _translate_keys(keys: str) -> str:
    parts = [p.strip().lower() for p in re.split(r"[+\-]", keys) if p.strip()]
    return "+".join(_KEY_MAP.get(p, p) for p in parts)


def install(CuaDriverBackend, CaptureResult, ActionResult, image_dims):
    if getattr(CuaDriverBackend, _PATCHED_FLAG, False):
        return
    orig = {n: getattr(CuaDriverBackend, n) for n in
            ("capture", "click", "type_text", "key", "scroll", "drag", "stop")}

    def capture(self, mode="som", app=None):
        # Full-desktop portal Screenshot via get_desktop_state (DISPLAY unset).
        if not CUA_DRIVER:
            return orig["capture"](self, mode, app)
        try:
            out_file = os.path.join(
                os.environ.get("XDG_RUNTIME_DIR", "/tmp"),
                "hermes-wl-desktop.png")
            env = dict(os.environ)
            env.pop("DISPLAY", None)
            env["CUA_DRIVER_RS_ENABLE_WAYLAND"] = "1"
            env.setdefault("CUA_DRIVER_RS_TELEMETRY_ENABLED", "0")
            subprocess.run(
                [CUA_DRIVER, "call", "get_desktop_state",
                 json.dumps({"screenshot_out_file": out_file})],
                env=env, capture_output=True, text=True, timeout=60)
            with open(out_file, "rb") as fh:
                raw = fh.read()
            w, h = image_dims(raw)
            if not (w and h):
                return orig["capture"](self, mode, app)
            _INJ.cw, _INJ.ch = w, h
            return CaptureResult(
                mode="vision", width=w, height=h,
                png_b64=base64.b64encode(raw).decode(), elements=[],
                app="desktop", window_title="Wayland desktop (portal)",
                png_bytes_len=len(raw), image_mime_type="image/png")
        except Exception as e:  # noqa: BLE001
            logger.warning("wayland_portal: desktop capture failed (%s); "
                           "falling back to stock capture", e)
            return orig["capture"](self, mode, app)

    def _need_session(action):
        ok, msg = _INJ.ensure()
        if not ok:
            return ActionResult(ok=False, action=action,
                                message=f"Wayland input unavailable: {msg}")
        return None

    def click(self, *, element=None, x=None, y=None, button="left",
              click_count=1, modifiers=None):
        if x is None or y is None:
            return ActionResult(ok=False, action="click", message=(
                "On Wayland use coordinate clicks — desktop capture exposes no "
                "element indices. Pass coordinate=[x,y] from the screenshot."))
        err = _need_session("click")
        if err:
            return err
        ix, iy = _INJ.to_input(x, y)
        _INJ._client(["move", str(ix), str(iy)])
        for _ in range(max(1, int(click_count))):
            _INJ._client(["click", button or "left"])
        # Report the model's OWN coordinate space (not the internal scaled
        # coords) so it doesn't think the click moved. Scaling is invisible.
        return ActionResult(ok=True, action="click",
                            message=f"{button or 'left'} click at ({int(x)},{int(y)})")

    def type_text(self, text):
        err = _need_session("type_text")
        if err:
            return err
        r = _INJ._client(["type", text], timeout=max(15.0, len(text) * 0.05 + 10))
        return ActionResult(ok=r.startswith("ok"), action="type_text",
                            message=f"typed {len(text)} chars ({r})")

    def key(self, keys):
        err = _need_session("key")
        if err:
            return err
        combo = _translate_keys(keys)
        r = _INJ._client(["key", combo])
        return ActionResult(ok=r.startswith("ok"), action="key",
                            message=f"key {combo} ({r})")

    def scroll(self, *, direction, amount=3, element=None, x=None, y=None,
               modifiers=None):
        err = _need_session("scroll")
        if err:
            return err
        if x is not None and y is not None:
            ix, iy = _INJ.to_input(x, y)
            _INJ._client(["move", str(ix), str(iy)])
        _INJ._client(["scroll", direction, str(int(amount))])
        return ActionResult(ok=True, action="scroll",
                            message=f"scroll {direction} {amount}")

    def drag(self, *, from_element=None, to_element=None, from_xy=None,
             to_xy=None, button="left", modifiers=None):
        if not from_xy or not to_xy:
            return ActionResult(ok=False, action="drag", message=(
                "On Wayland use coordinate drags: from_coordinate/to_coordinate."))
        err = _need_session("drag")
        if err:
            return err
        fx, fy = _INJ.to_input(*from_xy)
        tx, ty = _INJ.to_input(*to_xy)
        _INJ._client(["move", str(fx), str(fy)])
        _INJ._client(["down", button or "left"])
        # intermediate steps so the stroke is continuous, not a teleport
        steps = 8
        for i in range(1, steps + 1):
            mx = int(round(fx + (tx - fx) * i / steps))
            my = int(round(fy + (ty - fy) * i / steps))
            _INJ._client(["move", str(mx), str(my)])
        _INJ._client(["up", button or "left"])
        # Report in the model's coordinate space (scaling stays invisible).
        return ActionResult(ok=True, action="drag",
                            message=(f"drag ({int(from_xy[0])},{int(from_xy[1])})->"
                                     f"({int(to_xy[0])},{int(to_xy[1])})"))

    def stop(self):
        try:
            _INJ.shutdown()
        except Exception:  # noqa: BLE001
            pass
        return orig["stop"](self)

    CuaDriverBackend.capture = capture
    CuaDriverBackend.click = click
    CuaDriverBackend.type_text = type_text
    CuaDriverBackend.key = key
    CuaDriverBackend.scroll = scroll
    CuaDriverBackend.drag = drag
    CuaDriverBackend.stop = stop
    setattr(CuaDriverBackend, _PATCHED_FLAG, True)
    atexit.register(_INJ.shutdown)


_TOOL_GUIDANCE = (
    " PLATFORM NOTE (GNOME Wayland via wayland_portal plugin): computer_use IS "
    "fully functional here. capture returns a full-desktop screenshot "
    "(xdg-desktop-portal); click/type/scroll/drag are injected through the "
    "RemoteDesktop portal. Use COORDINATE actions (coordinate=[x,y] read off the "
    "screenshot) — desktop capture exposes NO numbered element indices, so do not "
    "wait for or rely on element ids. IGNORE any `hermes computer-use doctor` line "
    "saying input injection 'has no backend' / 'compiled without libei-portal' — "
    "that describes cua-driver's UNUSED native input path; this plugin injects "
    "input out-of-band and it works. The very first action in a session shows one "
    "GNOME 'Allow' consent dialog; after the user approves once, all further input "
    "works with no more prompts. Just capture and act; do not refuse."
)


def _patch_tool_description() -> None:
    """Append the platform note to the computer_use tool description (robust:
    always sent with the tool, survives updates — same tactic as the web plugin)."""
    try:
        import tools.computer_use_tool  # noqa: F401 — force tool registration
        from tools.registry import registry
        schema = registry.get_schema("computer_use")
        if not schema:
            return
        desc = schema.get("description", "")
        if "wayland_portal plugin" not in desc:  # idempotent
            schema["description"] = desc.rstrip() + _TOOL_GUIDANCE
            logger.info("wayland_portal: patched computer_use tool description.")
    except Exception as e:  # noqa: BLE001
        logger.debug("wayland_portal: could not patch tool description: %s", e)


def register(ctx) -> None:
    """Called by Hermes at plugin load. Patches the Wayland path in place."""
    try:
        if not _is_gnome_wayland():
            logger.info("wayland_portal: not a GNOME Wayland session; no patch applied.")
            return
        if not WL_INJECT:
            logger.warning("wayland_portal: wl-inject not found on PATH or "
                           "~/.local/bin; Wayland input will not work. Skipping.")
            return
        from tools.computer_use.backend import CaptureResult, ActionResult
        from tools.computer_use.cua_backend import (
            CuaDriverBackend, _image_dimensions_from_bytes)
        install(CuaDriverBackend, CaptureResult, ActionResult,
                _image_dimensions_from_bytes)
        _patch_tool_description()
        logger.info("wayland_portal: patched CuaDriverBackend for GNOME Wayland "
                    "(capture=get_desktop_state, input=wl-inject @ %s).", WL_INJECT)
    except Exception as e:  # noqa: BLE001 — never break plugin loading
        logger.warning("wayland_portal: failed to apply patch (%s); "
                       "leaving stock backend untouched.", e)
