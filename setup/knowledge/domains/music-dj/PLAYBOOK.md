# Music Production & DJ Playbook

Senior operating procedure for the music/DJ arm of the business.
Genre, alias, brand, and audience specifics live in `~/knowledge/BUSINESS-CONTEXT.md`; copy tone lives in `~/knowledge/STYLE-VOICE.md`.
Worked examples below assume house/techno club context — adapt at `{{FILL}}` points.
Quality gates for every deliverable: `RUBRIC.md` in this folder. Worked artifacts: `examples/`.

## Operating principles

1. **Finish ugly, then fix.** A finished mediocre track teaches more than 40 perfect loops; finishing is a separate skill trained only by finishing.
2. **Arrangement is energy management, not sound design.** People react to change (something entering/leaving), not to texture quality.
3. **Mix quiet, in mono, on small speakers first.** If it works at conversation volume on one bad speaker, it works everywhere; the reverse is false.
4. **Reference tracks are the anchor, always level-matched.** Your ears drift within 20 minutes; an unmatched reference (mastered = louder) makes you smash your mix chasing it.
5. **One element owns the sub.** Club systems are effectively mono below ~150 Hz; two things fighting there = mud on the big system no matter how good the studio mix felt.
6. **Loudness is the last decision, never the first.** Mix into headroom (peaks ~ -6 dBFS, no master limiter); loudness gets added once, at the end, on purpose.
7. **A set is one story; track order beats track quality.** Ten good tracks in the right order out-perform ten great tracks in a random walk.
8. **Play the room in front of you, not the set in your head.** The plan is a map, not a contract — the floor votes every 90 seconds.
9. **Two of everything at a gig.** USB, headphones, adapters. The night you skip the backup is the night you need it.
10. **The catalog compounds; single tracks don't.** Consistent finished releases + recorded sets build the asset; one "perfect" track in a drawer builds nothing.

## Task playbooks

### 1. Production workflow (idea → finished master)

Session = one focused block of 60–120 min. Hard cap for a club track: **12 sessions total**. At the cap: ship or kill, no third option.
Version discipline: save-as at every stage change; name `YYYYMMDD_artist_title_STAGE_vN` (e.g. `20260706_velt_basementheat_MIX_v3`). Bounce an MP3 at the end of every session; listen next morning away from the DAW before reopening.

**Stage 1 — Idea (time-box: 30–60 min)**
1. Capture one musical idea: hum into phone, play MIDI, or resample. One idea per project.
2. GATE: can you hum the hook after closing the DAW? No → bank to `ideas/` folder, do not force it.

**Stage 2 — 8-bar sketch (time-box: max 2 sessions)**
1. Build the densest 8–16 bars of the track: drums, bass, hook, one texture. Rough levels only, no mixing.
2. GATE (all must pass, binary):
   - Nod test: loop at club volume — head moves without deciding to.
   - Sandwich test: play it between two reference tracks — embarrassing? kill or fix the core, not the polish.
   - Kick + bass relationship decided (who owns the sub — see Principle 5).
3. Not passing after 2 sessions → bank it, start the next idea. Banked ideas are inventory, not failures.

**Stage 3 — Arrangement (time-box: max 2 sessions)**
1. Duplicate the sketch across the full timeline as blocks FIRST, then carve away (subtractive arranging — faster than additive).
2. Club format defaults: total 5–7 min; DJ intro 16–32 bars of beat-led, melodically sparse material; same for outro. `{{FILL: format norms for your genre/scene}}`
3. Rule of change: something enters or leaves every 8 bars; a structural change every 16–32 bars.
4. Tension before every drop: remove elements (drums out, filter, silence) for 1–4 bars before impact.
5. GATE: play start-to-finish, hands off. Mark every second your attention drops. Fix only the marked spots. Zero marks = stage done.

**Stage 4 — Sound design / fill pass (time-box: 1–2 sessions)**
1. Replace placeholders one element at a time. Max 30 min per sound; timer up → commit what you have or revert to the placeholder.
2. GATE: no sound left that makes you wince; at least one element with identity (you could name the track by it).

**Stage 5 — Mix (time-box: max 2 sessions, start with fresh ears)**
1. Run Playbook 2 (mixdown checklist) top to bottom.
2. GATE: all mix items in `RUBRIC.md` must-pass gates green; earbuds + phone-speaker + car (any 2 of 3) translation check logged.

**Stage 6 — Master / finalize (time-box: 1 session)**
1. Run Playbook 3.
2. GATE: loudness in target range and written down; true peak under ceiling; clean top and tail (no clicks); filename + metadata correct.
3. Move export to `final/`. Score against `RUBRIC.md`. High-stakes → escalate (see bottom).

**Anti-loop rules (apply to every stage)**
- "One more pass" requires a written list of specific fixes. No list → no pass → export.
- Flip-flopping (undoing your own last change) twice in a row = done. Stop.
- Ear fatigue: 45–60 min on, 10 min silence. Never trust a judgment made after 2h continuous listening.

### 2. Mixdown checklist

Run in order. Numbers are defaults for club music at 44.1/48 kHz, 24-bit.

1. **Gain-stage.**
   - All faders down. Kick in first: peak ~ -8 dBFS on its channel.
   - Balance every other element against the kick, at low volume, before any plugin.
   - Master bus peaks -6 to -3 dBFS at the loudest section.
   - NO limiter/maximizer/clipper on the master while mixing. None.
2. **Mono the low end.**
   - Everything below 100–150 Hz summed to mono (utility/mono-maker on the bass/sub group).
   - Stereo-widened sub = kill-list offense (RUBRIC.md).
3. **Decide the sub owner.**
   - Kick OR bass owns the fundamental — pick one, write it in the session notes.
   - Sidechain the other (2–4 dB duck; 6+ dB only as an intentional pump effect) or EQ-carve it.
4. **High-pass by default.** Everything that is not kick/bass/sub gets a high-pass:
   - pads/synths 150–300 Hz, hats/shakers 300–500 Hz, FX/reverb returns 200+ Hz.
   - Sweep the exact point by ear, but ON is the default state.
5. **EQ decision logic.**
   - Cut before boost. Boosts: wide (Q < 1.5) and small (< 3 dB).
   - Needing > 6 dB of boost = the source is wrong; replace the sound, don't EQ harder.
   - Problem-zone map: boom 60–120 Hz, mud 200–400 Hz, boxy 400–800 Hz, harsh 2–5 kHz.
6. **Fix masking in pairs.**
   - Solo kick+bass, then lead+pads: sweep to find the fight frequency.
   - Cut it 2–4 dB in the LESS important element of the pair. Never boost both.
7. **Reference A/B (mandatory).**
   - 2–3 references imported into the project, gain-dropped ~6 dB to match your unmastered bus (match by LUFS meter or careful ear — never A/B louder vs quieter).
   - Every 20–30 min: 15 s reference, 15 s yours, ONE property per pass (low end → lead level → top/width).
8. **Monitor discipline.**
   - Default volume = conversation level. Loud only in short bursts for excitement/low-end weight.
   - Full mono fold-down at least twice per mix session.
   - If the drop loses obvious power in mono → fix width/phase before touching anything else.
9. **Automation pass.** Rides and FX throws are arrangement glue — do them after the static balance is right, not instead of it.
10. **STOP conditions (any one = export and sleep on it):**
    - All rubric mix gates pass and translation check logged.
    - Your changes are < 0.5 dB and you're reversing yourself.
    - Next-morning listen produces < 3 concrete notes.

### 3. Mastering prep + loudness

**Path A — sending to a mastering engineer (default for lead releases):**
1. Deliver 24-bit WAV, project sample rate, peaks -6 to -3 dBFS, limiter OFF (keep bus glue comp/saturation only if it is "the sound" — say so in the notes).
2. Include: 1–2 reference masters, target use (club/streaming), any known concerns ("sub feels big at 55 Hz").
3. On return, QC yourself: full listen on monitors + earbuds, check top/tail, check true peak, A/B vs your mix at matched loudness. Do not approve the same day you receive it.

**Path B — minimal self-master (promos, secondary tracks):**
1. Fresh ears (next day minimum). New session or fresh chain on the final mixdown bounce.
2. Chain order: corrective EQ (moves < 2 dB) → glue compression (1–2 dB GR, slow attack ~30 ms, auto/0.1–0.3 s release) → optional saturation → stereo check (NOT widening the lows) → limiter LAST.
3. Limiter ceiling: **-1.0 dBTP** for anything hitting streaming/lossy encoders; -0.3 dBTP acceptable for club-only WAV.
4. Loudness targets (verify current numbers before each release cycle):
   - Modern club house/techno master: **-7 ±1 LUFS integrated**; do not exceed -6 without a reason you can say out loud.
   - Streaming platforms normalize around -14 LUFS integrated (Spotify; Apple ~-16). Do NOT master to -14 — master for the club range above; normalization turning you down is fine and preserves punch.
   - Limiter gain reduction on the loudest section: ≤ 4 dB for a dynamic master; > 6 dB = smashed, back off (kill-list offense at > 8 dB).
5. Keep three files forever: pre-master mix (-6 dBFS peaks), 24-bit WAV master, 320 kbps MP3 promo. Distributors generally take 24-bit WAV directly (verify current platform specifics).
6. QC identical to Path A step 3.

### 4. DJ set curation

1. **Rate energy 1–10** on every candidate track, on YOUR consistent scale. Write it in the track comment/tag field. Re-rate after playing it out — booth reality overrides studio opinion.
2. **Design the arc for the slot** (see Playbook 5 for slot types).
   - Peak-time default: start 6–7, waves up to 9–10, land 7–8.
   - Never monotonic — plan a valley (deeper/breakdown-heavy track) every 20–30 min so peaks read as peaks.
   - Put the single biggest moment at the 80–85% mark of the slot, not the last track.
3. **BPM lane.** Set the lane before picking tracks (e.g. house 122–126, peak techno 128–134 `{{FILL: your lane}}`).
   - Plan the drift direction (up / plateau / up-then-land).
   - Max ±2–3 BPM per transition silently; bigger jumps only as a designed moment (breakdown, FX cut, acapella bridge).
4. **Harmonic plan (Camelot).** Analyze all keys before planning.
   - Safe moves: same code, ±1 same letter, letter swap same number. +2 = energy-boost trick, best on percussive sections.
   - A full stop/FX cut resets the key context — jumps across silence are always legal.
   - RULE: key is a tiebreaker, not a law — never pick a worse track because it's in key; clashes only really hurt on long blends of melodic material.
5. **Crate = playlists by role, not genre:** OPENERS / GROOVERS / LIFTERS / PEAK BOMBS / RESETS / CLOSERS / SAFE (5–8 tracks that have never failed you). Crate for a set = 3× the set length in minutes.
6. **Cue points standardized on every track:** pad 1 = mix-in point, pad 2 = first drop, pad 3 = breakdown, pad 4 = mix-out. Same layout every track — booth decisions must be muscle memory.
7. **Plan hard only the first 3 and last 2 tracks.** The middle is lanes + roles, chosen live.
8. **Read the crowd (checkable signals):**
   - Hands up / singing → extend the moment; do NOT rush the next peak.
   - Hips moving, heads down → groove is right; stay in lane, change nothing big.
   - Phones filming → peak is landing (good). Phones scrolling + bar drift → you lost them: change energy within 2 tracks, from the SAFE list first.
9. **Adaptation rule:** change ONE variable at a time (BPM, energy, genre). If a change flops, next track = SAFE list, no experiments twice in a row.
10. Worked example with full table + contingencies: `examples/dj-set-blueprint.md`.

### 5. Gig preparation checklist

**T-7 to T-2 days**
1. Confirm in writing: set time, slot type, fee/guestlist, who plays before/after you. (Money terms per `~/knowledge/BUSINESS-CONTEXT.md`.)
2. Get the tech spec: mixer model, player count + generation, booth monitor situation.
3. Build the crate for the slot type (below). Remove every "maybe" track — booth decision fatigue is real.

**T-1 day**
4. Export to **two** USB sticks.
   - FAT32 is the universal safe format; exFAT only if all players are confirmed current-gen (verify against the venue's players).
   - Mount-test both sticks on a player or in export mode — an unverified backup is not a backup.
5. Re-analyze anything new (BPM/key/grid); manually check beatgrids on anything you plan to loop.
6. Pack list (binary check each item):
   - 2 USBs in different pockets/bags.
   - Headphones + spare earbuds; 6.3 mm headphone adapter.
   - USB-C/lightning adapters; phone with an emergency 60-min mix downloaded offline.

**Day of**
7. Arrive 30–60 min before your slot. Listen to the room and the DJ before you.
8. Load your USB on the actual player BEFORE your slot starts (during the prior DJ's set, politely).
9. Agree handover with the outgoing DJ: their last track's BPM and roughly what it is.
10. Gain-stage: channel trims so meters peak amber, never red — red on a club mixer = audible distortion on the big system.
11. Record the set (mixer USB, recorder, or phone in the booth). Review within 48 h; log 3 things that worked and 3 that didn't.

**Slot-type rules**
- **Warm-up:** the room is the client, not your ego. Stay 2+ energy points and several BPM below the headliner's expected start; NO peak bombs, NO tracks the headliner is known for. Success metric: floor fuller at handover than at your start.
- **Peak-time:** deliver the arc; biggest material lives here; shorter intros, more contrast.
- **Closing:** permission to be emotional/weird; ride energy down with intent. Pre-pick 2–3 candidate last tracks — the final track is the one thing everyone remembers.

**After**
12. Thank promoter same night; follow up within 48 h with the recording link and availability. Log the gig (fee, attendance, what popped) in `~/knowledge/feedback/`.

### 6. Release & promo plan (indie single, 4-week runway)

Full worked plan with dates, assets, and email copy: `examples/release-promo-plan.md`. Summary procedure:

1. **W-4 (D-28):** master approved (rubric + escalation if lead release). Artwork final 3000×3000. Metadata locked (title, artist, ISRC/UPC via distributor). Upload to distributor — 4 weeks lead keeps you eligible for editorial pitching (verify current platform specifics). Release day: pick Friday and stay consistent.
2. **W-3 (D-21):** Spotify for Artists editorial pitch — hard floor is 7 days pre-release, do it NOW at D-21 with every field filled (verify current requirements). Build asset pack: presave link, 3–5 vertical snippets (15–30 s), canvas loop, one-liner + 100-word bio.
3. **W-2 (D-14):** announce + presave push. Personalized outreach wave: independent playlists, blogs, radio shows, and 10–30 relevant DJs with a one-line ask. Schedule the content calendar (tie into `~/knowledge/domains/content-creation/`, tone per `~/knowledge/STYLE-VOICE.md`).
4. **W-1 (D-7):** content drip (snippet, countdown, behind-the-scenes). Check presave count against threshold; below threshold → add content volume, not spend, unless budget pre-approved.
5. **Release week:** out-now everywhere on D-0, push own channels (email/DM list), thank and repost every supporter same day, submit to user-generated playlists, play it in sets and post the clip.
6. **W+1/W+2:** second wave (visualizer, live clip, remix/edit tease). Pull stats at D+14 into `~/knowledge/feedback/` — streams, saves, playlist adds, follower delta. Every action in the plan has a date and an owner or it does not exist.

## Junior mistakes

1. **Loopitis** — 40 perfect 8-bar loops, zero tracks → hard gate: arrangement starts by sketch session 2, cap 12 sessions total.
2. **Mixing into a limiter from minute one** → mix to -6 dBFS headroom; loudness is stage 6 only.
3. **Stereo sub / wide bass** → mono below 100–150 Hz, non-negotiable.
4. **Boost-only EQ** → cut first; > 6 dB boost means replace the sound.
5. **A/B against mastered references at full loudness** → drop references ~6 dB to match; loudness always wins an unfair A/B.
6. **Mixing loud all session** → conversation level is the default; loud is a spot-check.
7. **Buying plugins instead of finishing** → tool freeze: no new purchases until the next 2 tracks are in `final/`.
8. **8-minute intro nobody asked for** → DJ intro is 16–32 bars; get to the point.
9. **Warm-up DJ playing peak bombs at 23:00** → slot discipline (Playbook 5); you're building the headliner's room.
10. **Key-clashing long melodic blends** → check Camelot on melodic overlaps; or cut short on percussion instead.
11. **One USB, no backup** → two sticks, two locations on your body.
12. **Releasing with 3 days lead then wondering where the playlists are** → 4-week runway, pitch at D-21.
13. **Loudness-war master** (limiter slammed 8+ dB) → ≤ 4 dB GR target; punch beats loud after normalization anyway.
14. **Red-lining the club mixer** → amber peaks; the system limiter turning on is not "energy".
15. **Never posting until the track is out** → the promo starts at D-14 minimum; audiences need 5+ touches before release day.

## Escalate to frontier review when…

High-stakes = money, reputation, or rights on the line. Run the artifact + `RUBRIC.md` through `cjudge` for a second review, and block on must-pass gate failures. A human makes the final call.

Escalate ALWAYS for:
1. Final master before distributor upload (any lead release).
2. Set plan for: paid headline slot, room > 300 cap, festival, or anything recorded/streamed for publication.
3. Release/promo plan before W-4 kickoff if budget is committed (ads, PR, video spend).
4. Anything involving rights, exclusivity, or contracts (label deal, remix agreement, booking contract) — legal/business review, not just quality review.
5. Public statements during a promo cycle that could read as controversy (check against `~/knowledge/STYLE-VOICE.md` first).

Do NOT escalate: sketches, banked ideas, bar-gig set plans, routine content posts — rubric self-check is enough.
