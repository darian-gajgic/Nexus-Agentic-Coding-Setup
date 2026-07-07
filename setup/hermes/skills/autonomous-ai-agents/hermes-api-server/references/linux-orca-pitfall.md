# Pitfall: Orca Screen Reader Triggered by cua-driver on GNOME/Linux

## Symptom

On Linux (GNOME, Wayland or X11), calling `computer_use(action="capture")` or
any cua-driver action that touches the AT-SPI accessibility bus can flip GNOME's
`screen-reader-enabled` gsetting to `true`. This auto-starts **Orca**, the GNOME
screen reader, which begins narrating everything on screen through the speakers
at full volume. The user experiences this as their PC suddenly "reading out
everything on the screen via loudspeaker."

This is disruptive and scary — the user will interrupt the session to report it.

## Root Cause

cua-driver connects to `org.a11y.Bus` (AT-SPI) to drive the accessibility tree
for element discovery and input synthesis. On GNOME, Orca monitors this bus and
auto-starts when it detects accessibility events, flipping the gsetting.

## The Fix (3 steps, in order)

```bash
# 1. Disable the gsetting that triggers auto-start
gsettings set org.gnome.desktop.a11y.applications screen-reader-enabled false

# 2. Kill Orca (it may respawn if you skip step 1)
killall orca
# or: pkill -9 -f orca

# 3. Verify it's actually dead (GNOME respawns it while the gsetting is true)
pgrep -x orca    # should output nothing
```

**Critical ordering:** if you `killall orca` before setting the gsetting to
`false`, GNOME will respawn Orca within seconds. Disable the setting first, then
kill. `kill -9` may be needed if `killall` doesn't take.

## Prevention

If you plan to use `computer_use` on a Linux/GNOME session, proactively disable
the gsetting before the first capture call:

```bash
gsettings set org.gnome.desktop.a11y.applications screen-reader-enabled false
```

This is a one-time per-login-session fix — the setting persists across reboots
once set to false, but a GNOME update or accessibility dialog can re-enable it.

## Additional Note: Screenshot Tools on Wayland

On a Wayland session, traditional screenshot tools may also fail:
- `gnome-screenshot` falls back to X11 and produces 0-size images
- `grim` (Wayland-native) may not be installed
- The `computer_use` capture itself may fail with a generic error

The `hermes computer-use doctor` command reports this as:
```
⏭️ wayland_backend: Wayland session detected, but the experimental backend is opt-in.
   Set CUA_DRIVER_RS_ENABLE_WAYLAND=1 to enable native Wayland.
```

If you need screenshots on Wayland, install `grim` and `slurp`, or set the
`CUA_DRIVER_RS_ENABLE_WAYLAND=1` environment variable before starting the Hermes
session. However, the AT-SPI input path (clicking, typing) still works on
Wayland even without the native backend — it's only screen capture that's
affected.

## When This Applies

- Any Linux desktop running GNOME (Ubuntu, Fedora, etc.)
- Both Wayland and X11 sessions (the AT-SPI trigger is session-type independent)
- The user does NOT need to have Orca enabled beforehand — cua-driver's bus
  connection can trigger it from a clean state
