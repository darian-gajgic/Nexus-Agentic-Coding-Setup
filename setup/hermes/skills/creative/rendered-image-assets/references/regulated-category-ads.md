# Regulated-category typography-only ads — worked example & scripts

Reference for the `rendered-image-assets` skill. Session: vaping harm-reduction
Instagram ad (1080×1080, 2026-07-06). Distills the reusable patterns for
nicotine/alcohol/pharma/cannabis ad assets where product imagery is a liability.

## Why typography-only (not SVG hero)

The apple-juice worked example uses an inline SVG glass illustration as the hero —
and that's the right call for food/beverage. For regulated categories, the same SVG
hero pattern becomes a liability: an abstract vape silhouette still glamorizes the
product. The vaping ad replaced the hero with a **300px teal "3"** — the Cochrane
statistic IS the visual anchor. The viewer's eye hits the number, reads the headline
next to it, and the proof citation sells the credibility.

This pattern works for any regulated category where the message is comparative-
effectiveness or risk-communication rather than product appeal:

- **Pharma:** "3 in 10 patients achieved remission" — stat-as-hero, no pill illustration.
- **Alcohol harm-reduction:** "40% fewer injuries" — stat-as-hero, no glass illustration.
- **Cannabis:** "CBD reduced seizures by 39%" — stat-as-hero, no leaf illustration.

## Layout anatomy (validated on the vaping ad)

The 1080×1080 canvas breaks into horizontal bands:

```
y=68–155px    Eyebrow: audience pill (left) + qualifier text (right)
y=165–560px   HERO: giant stat number (left, 300px) + headline/subhead (right)
y=600–700px   Proof line: study name, scope, year
y=718–830px   Switch/risk message: bold directive + dual-use warning
y=850–885px   CTA: single action, accent color
y=1000–1080px Footer: disclaimer (left) + logo placeholder (right)
```

All elements positioned absolutely against the canvas — same discipline as the
SVG-hero pattern, just with the hero replaced by type.

## Hashtag include/exclude lists

### Vaping / nicotine harm-reduction

**Include (12):** `#smokingcessation #quitsmoking #harmreduction #stopsmoking
#publichealth #smokefree #cessation #nicotinefree #quitsmokingsupport #smokingquit
#adultsmokers #evidencebased`

**Exclude (6+):** `#vape #vaping #vapelife #vapenation #ecig #vapecommunity`

### Generalization rule

For any regulated category, the exclude list is: any hashtag that names the product
as a lifestyle/identity rather than a health intervention. If the tag could appear on
a user-generated lifestyle post, it's wrong for a compliance-gated ad.

## Caption checks (ready-to-run)

Save as a script and run after writing the caption block. Verifies reading level,
hook length, CTA count, exclamation discipline, and we/you ratio.

```python
import re, sys

def check_caption(caption: str) -> dict:
    words = caption.split()
    sentences = [s for s in re.split(r'[.!?]+', caption) if s.strip()]
    words_clean = [w for w in words if any(c.isalpha() for c in w)]
    word_count = len(words_clean)
    sent_count = len(sentences)
    words_per_sent = word_count / sent_count

    # Syllable count (simple heuristic)
    total_syllables = 0
    for w in words_clean:
        w_low = re.sub(r'[^a-z]', '', w.lower())
        count = 0
        prev_vowel = False
        for c in w_low:
            is_vowel = c in 'aeiouy'
            if is_vowel and not prev_vowel:
                count += 1
            prev_vowel = is_vowel
        if w_low.endswith('e'):
            count = max(1, count - 1)
        total_syllables += max(1, count)

    syll_per_word = total_syllables / word_count
    flesch = 206.835 - 1.015 * words_per_sent - 84.6 * syll_per_word
    fk_grade = 0.39 * words_per_sent + 11.8 * syll_per_word - 15.59

    # Hook = first sentence
    hook = sentences[0].strip() if sentences else caption
    hook_len = len(hook)

    you_count = len(re.findall(r'\b(you|your|you\'re)\b', caption.lower()))
    we_count = len(re.findall(r'\b(we|our|us)\b', caption.lower()))
    excl = caption.count('!')

    results = {
        'word_count': word_count,           # target 95–135
        'fk_grade': round(fk_grade, 1),     # target ≤ 8
        'flesch_ease': round(flesch, 1),    # target ≥ 55
        'hook_chars': hook_len,             # target ≤ 125 (IG truncation)
        'exclamation_marks': excl,          # target 0 or 1
        'you_count': you_count,
        'we_count': we_count,
    }
    return results

# Usage: pass your caption as a string, print the dict, eyeball against targets.
```

## Kill-list sweep (regulated category: vaping/nicotine)

Extended kill-list beyond the general marketing terms — add these for any
vaping/nicotine ad:

```python
KILL_LIST_REGULATED = [
    # General marketing fluff
    'safe', 'harmless', 'risk-free', 'risk free', 'healthy', 'detox',
    'lifestyle', 'cool', 'fun', 'revolutionize', 'game-changer',
    'unleash', 'delve', 'seamless', 'cutting-edge',
    # Vaping/nicotine-specific forbidden safety claims
    '95% safer', '95 safer', '95% less harmful', 'completely safe',
    'no risk', 'harmless', 'good for you',
    # Youth/lifestyle coded
    'trendy', 'vibe', 'flavor', 'flavors', 'delicious',
]
```

**Scope to facing text only** (on-image copy + caption) — never the compliance docs.
See the scoping pitfall in SKILL.md.

## Platform ad-review prep (Meta/Instagram)

For nicotine/tobacco-adjacent ads, Meta's automated review will likely flag the
keywords "nicotine" and "e-cigarettes." Prepare a **review-note submission** to
include with the ad:

```
This is a public-health cessation ad citing Cochrane Living Systematic Review 2025
(high-certainty evidence, 104 studies, 30,000+ participants). No tobacco or
e-cigarette product is shown, sold, or promoted. The call-to-action directs users
to public stop-smoking services (NHS/CDC/state quitlines), not to any commercial
retailer. The ad carries explicit risk disclosures. Audience is restricted to
adults 21+ who currently smoke cigarettes.
```

**Audience targeting setup:**
- Age: 21+ minimum.
- Interests: "quitting smoking," "nicotine patch," "smoking cessation" — NOT
  "vaping," "e-cigarettes," or "vape shops" (those reach never-smokers and youth).
- Custom exclusions: exclude users who follow vape-brand accounts or have
  recently engaged with vape-retailer pages.

## Claims-and-sources table (vaping harm-reduction example)

| # | Claim as it appears | Claim type | Source | Status |
|---|---|---|---|---|
| 1 | "3 more smokers quit per 100" with e-cigs vs NRT | Factual (comparative effectiveness) | Cochrane LSR 2025 | ✅ High-certainty |
| 2 | "Smoking and vaping together may be worse than smoking alone" | Hedged risk claim | NEJM Evidence 2024 (Glantz et al.) | ✅ Correctly hedged with "may" |
| 3 | "Vaping carries risks" | Factual (risk acknowledgment) | NASEM 2018 | ✅ |
| 4 | "Long-term effects are unknown" | Factual (evidence-gap honesty) | Products mass-market ~19 years; latency gap | ✅ |
| — | "safe" / "harmless" / "risk-free" / "95% safer" | **FORBIDDEN** | — | ❌ Absent ✓ |

## Ad-hoc verification summary (run before declaring done)

| Check | Method |
|---|---|
| PNG valid + exact 1:1 aspect | `PIL.Image.open` + `.verify()` + size ratio |
| On-image copy verbatim | Extract HTML text nodes, assert each copy string present |
| Kill-list sweep (scoped) | Facing text only — never compliance docs |
| Caption reading level | Flesch-Kincaid script above, target ≤ Grade 8 |
| Caption discipline | 95–135 words, ≤125-char hook, 1 CTA, 0 exclamations |
| Visual QA | Downscale to 540px JPEG, ask VLM concrete yes/no questions |
| HTML tags balanced | Count `<tag>` vs `</tag>` for html/head/body/style/svg |
| render.py compiles | `py_compile.compile(render_py, doraise=True)` |

Label all as **ad-hoc verification, not suite-green** in the deliverable.
