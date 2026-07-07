# WCAG Color Contrast on Dark Themes

The single most common reason a polished dark-theme Astro site fails its
accessibility gate. An accent color that looks vivid and reads fine on the page
background silently drops below WCAG AA (4.5:1 for normal text) when the same
color is used on an elevated card surface.

## Why it happens

Dark themes define `--color-bg` (page) and `--color-bg-elevated` (cards). The
page background is near-black (`#0a0a0f`); elevated cards are slightly lighter
(`#13131a`). An accent used for both links-in-prose AND links-in-cards is only
verified against the page background during build. The card is lighter, so the
contrast drops — sometimes below 4.5:1.

## The recurring offenders (from a real acceptance gate)

| Element | FG | BG surface | Ratio | Verdict |
|---|---|---|---|---|
| Accent link in prose | `#6366f1` | page `#0a0a0f` | 4.6:1 | PASS |
| Accent "Learn more →" on a card | `#6366f1` | card `#13131a` | **4.1:1** | **FAIL** |
| White text on accent button | `#ffffff` | `#6366f1` bg | **4.5:1** | **FAIL** (4.47, rounds under) |
| White text on darkened button | `#ffffff` | `#5457e6` bg | 5.4:1 | PASS |
| Hover-shade text on card | `#818cf8` | card `#13131a` | 6.2:1 | PASS |

## The fixes (2 lines of CSS)

**Fix 1 — accent text on elevated surfaces:** use the hover shade, not the base
accent. In the component that renders text/links on cards:
```css
/* ServiceCard.astro — "Learn more" link */
.card-link { color: var(--color-accent-hover); }  /* #818cf8, not #6366f1 */
```

**Fix 2 — white-on-accent buttons in dark theme:** darken the button background
for dark theme only (light theme keeps the base accent):
```css
/* global.css — dark-theme button override */
[data-theme="dark"] .btn-primary { background: #5457e6; }
```

## Verify

```bash
# Lighthouse installs on first npx run; reads individual audits, not just composite
npx lighthouse http://localhost:4321/ --only-categories=accessibility --quiet
# Before fix:  Accessibility 95/100, color-contrast audit = 0.00 (FAIL)
# After fix:   color-contrast audit = 1.0 (PASS)
```

Important: a composite Accessibility score of 95 does NOT mean "no failed
audits." Lighthouse weights audits; a single color-contrast fail only drops the
score ~5 points. Read the individual `color-contrast` audit result.

## Rule of thumb

For every accent color in the design system, compute its contrast ratio against
BOTH the page background AND the elevated-surface background. If either is under
4.5:1, that color cannot be used for normal-weight text on that surface — use the
hover shade (lighter) for text, or darken the surface-tint for filled controls.
