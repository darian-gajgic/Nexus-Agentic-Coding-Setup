# Music & DJ Quality Rubric

Scoreable gate for four artifact types: **track/master**, **DJ set plan**, **gig prep**, **release plan**.
Procedure: (1) check must-pass gates for the artifact type — any FAIL blocks shipping; (2) score the applicable dimensions 0–4; (3) scan the kill list — any hit caps the verdict at "revise".
**Ship verdict:** all gates PASS + no kill-list hits + score ≥ 70% of applicable maximum + no dimension ≤ 1.
High-stakes artifacts additionally go through `cjudge` (see PLAYBOOK.md, escalation section).

## Must-pass gates (binary)

**Track / master**
- [ ] No clipping: true peak ≤ -1.0 dBTP (or the stated club ceiling), measured with a meter, number written in the notes.
- [ ] Integrated LUFS measured and inside the stated target ±1 LU (club default -7 ±1; verify current numbers).
- [ ] Low end below ~150 Hz verified mono (correlation/utility check, not by ear alone).
- [ ] Full mix checked in mono at least once; drop does not collapse.
- [ ] A/B'd against ≥ 2 level-matched references; reference names logged.
- [ ] Full-length listen logged on ≥ 2 playback systems (monitors + earbuds/car/phone).
- [ ] DJ-usable intro and outro (16+ bars beat-led) OR explicitly tagged non-club format.
- [ ] Exported per naming convention, correct metadata, filed in `final/`.

**DJ set plan**
- [ ] Every planned transition has BPM and key noted.
- [ ] No silent BPM jump > 3 without an explicit transition device noted (cut, breakdown, acapella).
- [ ] At least one planned energy reset/valley per 45 min of set length.
- [ ] Contingency present: SAFE list of ≥ 5 named tracks + at least one colder-crowd and one hotter-crowd branch.
- [ ] First 3 and last 2 tracks explicitly named.

**Gig prep**
- [ ] Two physical music backups confirmed loaded and mounted-tested.
- [ ] Set time, slot type, and fee/terms confirmed in writing.
- [ ] Tech spec of the booth known (mixer, players, monitors) or a written fallback plan exists.
- [ ] Recording method for the set arranged.

**Release plan**
- [ ] Every action has a calendar date AND an owner. Zero "TBD".
- [ ] Distributor upload scheduled ≥ 21 days before release date (verify current platform specifics).
- [ ] Editorial pitch scheduled ≥ 7 days before release (verify), with pitch copy drafted.
- [ ] Presave/streaming link live before the first public announcement post.
- [ ] Asset list complete with specs (artwork 3000×3000, snippets, canvas) and file locations.

## Scored dimensions (0 = absent, 2 = competent, 4 = professional)

1. **Arrangement momentum** (track)
   - 2: Correct sections, but changes only land on 32-bar marks; attention dips mid-section.
   - 4: Something enters/leaves every 8–16 bars; tension device before every drop; zero dead zones on a hands-off listen.
2. **Low-end management** (track)
   - 2: Kick and bass both audible but pump or blur on some bass notes; small-speaker translation partial.
   - 4: One clear sub owner; groove readable on a phone speaker; identical weight in mono and stereo.
3. **Mix translation** (track)
   - 2: Good on the main monitors; noticeably harsh or bass-light on one other system.
   - 4: Recognizably the same balance on 3+ systems; only character changes, not decisions.
4. **Sound identity** (track)
   - 2: Clean, competent, preset-shaped; nothing you could name the track by.
   - 4: At least one signature element a listener could describe back to you after one listen.
5. **Set arc coherence** (set plan / recorded set)
   - 2: Good tracks; energy is a plateau or a random walk; peaks arrive unearned.
   - 4: Deliberate waves; every peak is set up by a valley; the closer resolves the night's story.
6. **Transition craft** (set plan / recorded set)
   - 2: Beatmatched, but every blend is the same-length EQ swap regardless of material.
   - 4: Technique varies with material (cut, long blend, loop, drop-swap, FX); key-aware exactly where melodic overlap demands it.
7. **Promo execution readiness** (release plan)
   - 2: Actions listed but copy unwritten, dates approximate, assets "in progress".
   - 4: Dated actions with owners, finished copy and assets linked, numeric checkpoint (e.g. presave count at D-7) with a pre-decided response.
8. **Contingency depth** (set plan / gig prep)
   - 2: A SAFE list exists but no trigger conditions; one generic "if it's not working" note.
   - 4: Named branch plans with observable triggers (floor %, hands, bar drift) and specific named tracks per branch.

Applicable maxima: track = 16 (dims 1–4), set/gig = 12 (dims 5, 6, 8), release = 4 (dim 7). Ship threshold 70%: track ≥ 12, set/gig ≥ 9, release = 3+.

## How to log a review

1. Copy this block into the artifact's notes (or the review message):
   `RUBRIC vX | artifact: <file/plan> | gates: PASS/FAIL (list fails) | dims: n/max | kills: none/<item> | verdict: SHIP / REVISE / ESCALATE`
2. FAIL or kill hit → verdict REVISE with the specific line quoted; never "needs polish".
3. High-stakes (per PLAYBOOK escalation list) → verdict ESCALATE even on a perfect score; `cjudge` gets artifact + this rubric.

## Kill list — automatic "revise", no discussion

- Loudness-war master: limiter gain reduction > 8 dB, or audible pumping on the drop, or louder-but-smaller than the reference.
- Stereo-widened content below 100 Hz.
- Intro longer than 2 minutes before any drum appears, uncredited to a stated artistic reason.
- Set plan whose energy only goes up (monotonic climb, no valleys).
- Every transition in a set identical (same length, same EQ move, 20 times).
- Key clash on a long melodic blend that a Camelot check would have caught.
- White-noise riser + snare roll into every single drop in the track.
- Warm-up plan containing the headliner's signature tracks or peak-time bombs in the first hour.
- Any "TBD" date or unowned action in a release plan.
- Export named `final_final_v3_REAL.wav` or similar — naming convention exists, use it.
- Announcement posted with no live link/presave to click.
- Master approved same-day with no fresh-ears listen logged.
