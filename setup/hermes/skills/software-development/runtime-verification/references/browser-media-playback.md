# Browser Media Playback — autoplay policy & A/V sync

The single most common reason a talking-head / lip-sync / voice feature "works in
tests, fails for the user": Chrome's autoplay policy.

## The rule that breaks things

Chrome (and all Chromium browsers) **reject unmuted `video.play()` / `audio.play()`
unless a user gesture (click, tap, keypress) is active in the call stack**. The
gesture unlocks playback for that element, but the unlock is fragile:

- A programmatic `play()` on a follow-up clip — after streaming finishes, in a
  `setTimeout`, or in a resolved Promise far from the original click — is often
  **outside** the gesture context and gets silently rejected with
  `NotAllowedError: play() failed because the user didn't interact with the document first`.
- The FIRST clip usually plays (gesture still warm). The 2nd, 3rd, Nth clips freeze.
  Symptom: "first sentence works, follow-up sentences the face doesn't move."

## Muted video is never blocked

`video.muted = true` makes `play()` **always allowed**, on every clip, with no
gesture. This is the robust pattern for any animated face / visualizer / avatar:
play the video MUTED for the face, carry the voice via a separate audio element.

## Robust pattern: muted video + separate persistent audio

```
// One persistent audio element, unlocked once by the mic-click gesture,
// reused for every clip so play() is never rejected.
function audioEl() {
  if (!state.audioEl) state.audioEl = new Audio();
  return state.audioEl;
}

function playClip(audioBlob, videoBlob) {
  return new Promise(resolve => {
    const audio = audioEl();
    const video = state.avatarVideo;
    let aReady = false, vReady = !videoBlob, started = false;
    const done = () => { cleanup(); resolve(); };
    const tryStart = () => {
      if (started || !aReady || !vReady) return;
      started = true;
      video.play().catch(()=>{});        // muted → never blocked
      audio.play().catch(done);           // gesture-unlocked → plays
    };
    audio.oncanplay = () => { aReady = true; tryStart(); };
    audio.onended = done;
    audio.src = URL.createObjectURL(audioBlob);
    if (videoBlob) {
      video.muted = true;                 // THE KEY LINE
      video.oncanplay = () => { vReady = true; tryStart(); };
      video.src = URL.createObjectURL(videoBlob);
    }
  });
}
```

Both start at the same instant when both are ready → no drift. The lip-sync
video is generated FROM the audio (Wav2Lip), so durations match by construction.

## Why NOT to mux audio into the video and play unmuted

A single muxed MP4 played `muted=false` seems simpler ("one source, can't drift"),
and it IS in sync — but it gets **autoplay-blocked on follow-up clips**. The
"can't drift" property is worthless if `play()` is rejected. Prefer muted video +
separate audio.

## How to test WITHOUT masking the bug

Playwright's `--autoplay-policy=no-user-gesture-required` launch arg DISABLES the
restriction entirely. Any test using it will pass while the real browser fails.
For the final verification pass:

```python
# WRONG — masks the autoplay bug:
b = chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])

# RIGHT — reproduces real Chrome:
b = chromium.launch(args=["--ignore-certificate-errors"])  # NO autoplay-policy flag
```

Instrument both elements to catch rejections:
```python
pg.evaluate("""()=>{
  window._vReject=0; window._aOK=0; window._aReject=0;
  const vp=HTMLVideoElement.prototype.play, ap=HTMLAudioElement.prototype.play;
  HTMLVideoElement.prototype.play=function(){return vp.call(this).catch(e=>{window._vReject++;throw e})};
  HTMLAudioElement.prototype.play=function(){return ap.call(this).then(r=>{window._aOK++;return r}).catch(e=>{window._aReject++;throw e})};
}""")
# After flow: assert window._vReject==0 and window._aReject==0
```

## Cache-busting (the other silent killer)

`<script src="/static/app.js">` with no query string gets cached by the browser.
When you edit app.js, the user's browser keeps serving the OLD version. Every
"fix" is invisible to them. Always use `app.js?v=N` and bump N on each deploy.
Symptom: "I fixed it but it's even worse now" — they're running stale code.
