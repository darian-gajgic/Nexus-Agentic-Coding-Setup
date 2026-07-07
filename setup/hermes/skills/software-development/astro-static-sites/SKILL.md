---
name: astro-static-sites
description: "Build multi-page static websites with Astro — brochure sites, portfolios, marketing landing pages, docs sites, blogs — where the deliverable is static HTML/CSS/JS shipped to a free CDN (Netlify, Vercel, Cloudflare Pages, GitHub Pages). Covers project bootstrap, content collections via Markdown, dynamic routes with getStaticPaths, component architecture, theme toggle with no-FOUC, sitemap/SEO, Netlify Forms, and the version-compat and glob-scope gotchas that break builds."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [astro, static-site, ssg, brochure, portfolio, marketing-site, netlify, markdown, content-collections, dark-theme, seo, sitemap]
    related_skills: [claude-design, popular-web-designs, web-dashboard-apps]
---

# Astro Static Sites

Build multi-page static websites with Astro — the component-based static site generator that ships zero JavaScript by default. Use this for brochure sites, portfolios, service/business marketing sites, docs, and blogs where the deliverable is static HTML deployed to a free CDN.

## When To Use

- User asks for a static website, brochure site, portfolio, landing page set, or marketing site with multiple pages
- Spec mentions Astro, static output, Netlify/Vercel/Cloudflare Pages, or "zero JS"
- Building a multi-page site from a detailed PLAN/SPEC document
- Site needs Markdown-driven content (blog, docs, service catalog)
- Project needs forms but no backend (Netlify Forms, Formspree)

## When NOT To Use

- **Single HTML artifact / one-off landing page** → `claude-design` (faster, no project scaffold)
- **Real-time dashboard with live data/WebSocket** → `web-dashboard-apps`
- **Full app with auth, database, API routes** → use Next.js/SvelteKit/Remix in the user's repo
- **Throwaway 2-3 variant comparison** → `sketch`

## Project Bootstrap

### Minimal init (no interactive prompts needed)

Don't run `npm create astro@latest` interactively — it asks 5+ questions. Instead, write `package.json` + `astro.config.mjs` + `tsconfig.json` directly and run `npm install`. This is faster and reproducible.

**package.json** (known-good versions as of 2026-07):
```json
{
  "name": "my-site",
  "type": "module",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "astro dev",
    "build": "astro build",
    "preview": "astro preview",
    "astro": "astro"
  },
  "dependencies": {
    "astro": "^4.16.18",
    "@astrojs/sitemap": "3.2.1"
  }
}
```

**astro.config.mjs**:
```js
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://example.netlify.app',  // required for sitemap + OG URLs
  output: 'static',
  integrations: [sitemap()],
});
```

**tsconfig.json**:
```json
{ "extends": "astro/tsconfigs/strict" }
```

Then `npm install` and `npm run dev` (serves on `localhost:4321`).

### CRITICAL: Pin @astrojs/sitemap to 3.2.1 for Astro 4.x

**This is the #1 build-breaking gotcha.** If you let npm resolve `@astrojs/sitemap` to its latest (3.7.x as of mid-2026), it registers an `astro:routes:resolved` hook that **does not exist in Astro 4.x**. The hook silently never fires, `_routes` stays `undefined`, and the build crashes at the very end with:

```
Cannot read properties of undefined (reading 'reduce')
  Location: node_modules/@astrojs/sitemap/dist/index.js:85:37
```

All your pages build fine — the crash happens in the sitemap integration's `astro:build:done` hook. The error message gives no hint that it's a version mismatch.

**Fix:** pin `@astrojs/sitemap` to `3.2.1` (or whatever the latest 3.x was when your Astro 4.x released). Specify it as an exact version, not a caret range:
```bash
npm install @astrojs/sitemap@3.2.1
```

When Astro 5.x is the target, the latest sitemap works. Always check integration compatibility against the Astro major version, not just "latest."

### File structure

```
project/
├── astro.config.mjs
├── package.json
├── tsconfig.json
├── netlify.toml          # [build] command="npm run build", publish="dist"
├── public/
│   ├── favicon.svg
│   ├── robots.txt        # Must contain "Sitemap: <site-url>/sitemap-index.xml"
│   └── og-default.svg    # OG image (SVG works, PNG traditional)
├── src/
│   ├── components/       # Nav.astro, Footer.astro, Button.astro, SEO.astro, etc.
│   ├── content/
│   │   └── services/     # Markdown files with frontmatter
│   │       ├── item-one.md
│   │       └── item-two.md
│   ├── layouts/
│   │   └── BaseLayout.astro
│   ├── pages/
│   │   ├── index.astro
│   │   ├── about.astro
│   │   ├── 404.astro
│   │   └── catalog/
│   │       ├── index.astro
│   │       └── [slug].astro   # dynamic route
│   └── styles/
│       └── global.css
└── tests/
    └── *.spec.ts
```

## Dynamic Routes with Markdown Content

### CRITICAL: import.meta.glob must be INSIDE getStaticPaths

Astro's static build isolates `getStaticPaths()` into its own scope. A `const files = import.meta.glob(...)` declared in the frontmatter **top level** is NOT visible inside `getStaticPaths()` — you get `ReferenceError: files is not defined` at build time, even though it works in `astro dev`.

**Wrong (fails in build, works in dev):**
```astro
---
const files = import.meta.glob('../../content/*.md', { eager: true });  // top-level

export function getStaticPaths() {
  return Object.keys(files).map(...)  // ReferenceError at build time!
}
---
```

**Right (call the glob inside the function):**
```astro
---
export function getStaticPaths() {
  const files = import.meta.glob('../../content/*.md', { eager: true });
  const slugs = Object.keys(files).map(path => {
    const m = path.match(/\/([^/]+)\.md$/);
    return m ? m[1] : '';
  }).filter(Boolean);

  return slugs.map(slug => ({
    params: { slug },
    props: { data: files[`../../content/${slug}.md`].frontmatter, slug },
  }));
}

const { data, slug } = Astro.props;
---
```

Pass the resolved data via `props`, not by re-looking-up `Astro.params.slug` in the frontmatter (that also fails in some Astro versions). The `props` pattern is the robust one.

### Markdown frontmatter → typed page

```markdown
---
title: "Custom coding"
slug: "custom-coding"
summary: "One-paragraph summary for SEO and card."
price: "[price]"
included:
  - "Bullet point one"
  - "Bullet point two"
process:
  - "Step one"
  - "Step two"
faq:
  - q: "Question?"
    a: "Answer."
---
```

Access in the page via `Astro.props.data.title`, `.included` (array), `.faq` (array of `{q, a}`).

## Component Architecture

### BaseLayout.astro (every page uses this)

```astro
---
import '../styles/global.css';
import Nav from '../components/Nav.astro';
import Footer from '../components/Footer.astro';
import SEO from '../components/SEO.astro';

interface Props { title: string; description: string; image?: string; }
const { title, description, image } = Astro.props;
---
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="icon" type="image/svg+xml" href="/favicon.svg" />

  <!-- Fonts with font-display: swap (Lighthouse requirement) -->
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />

  <SEO title={title} description={description} image={image} />

  <!-- Theme init: BEFORE paint, try/catch for private mode -->
  <script is:inline>
    (function () {
      try {
        var t = localStorage.getItem('theme');
        document.documentElement.setAttribute('data-theme', (t === 'light' || t === 'dark') ? t : 'dark');
      } catch (e) {
        document.documentElement.setAttribute('data-theme', 'dark');
      }
    })();
  </script>
</head>
<body>
  <Nav />
  <main><slot /></main>
  <Footer />
</body>
</html>
```

Key points:
- `data-theme="dark"` on `<html>` as the default (dark-first)
- Inline theme script uses `is:inline` so Astro doesn't process/bundle it — it runs synchronously before paint, preventing FOUC
- `try/catch` around `localStorage` for private browsing mode
- `preconnect` to font origins for faster font load

### SEO.astro (unique title + meta description + OG tags per page)

```astro
---
interface Props { title: string; description: string; image?: string; }
const { title, description, image = '/og-default.svg' } = Astro.props;
const siteUrl = Astro.site?.toString().replace(/\/$/, '') || 'https://example.netlify.app';
const ogImage = `${siteUrl}${image}`;
---
<title>{title}</title>
<meta name="description" content={description} />
<meta property="og:type" content="website" />
<meta property="og:title" content={title} />
<meta property="og:description" content={description} />
<meta property="og:image" content={ogImage} />
<meta property="og:url" content={siteUrl} />
<meta name="twitter:card" content="summary_large_image" />
```

Meta description must be ≤155 chars. Verify with: `grep -r '<meta name="description"' dist/ | awk -F'content="' '{print $2}' | awk -F'"' '{print length($1), $1}'`

## Theme Toggle (dark default, no FOUC)

```astro
<!-- ThemeToggle.astro -->
<button id="theme-toggle" aria-label="Toggle color theme">
  <svg class="icon-moon"><!-- moon --></svg>
  <svg class="icon-sun"><!-- sun --></svg>
</button>

<style>
  .icon-moon { display: block; }
  .icon-sun { display: none; }
  [data-theme="light"] .icon-moon { display: none; }
  [data-theme="light"] .icon-sun { display: block; }
</style>

<script>
  document.getElementById('theme-toggle')?.addEventListener('click', () => {
    try {
      const cur = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('theme', next);
    } catch (e) {
      // Private mode: toggle visually only
      const cur = document.documentElement.getAttribute('data-theme') || 'dark';
      document.documentElement.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
    }
  });
</script>
```

The CSS custom properties switch via `[data-theme="light"] { --color-bg: #fff; ... }` override on `:root` defaults.

## Responsive Nav (hamburger < 768px)

Desktop nav is `display: flex` at ≥768px. Mobile shows a hamburger button that toggles a `.nav-open` class on the mobile menu. Use plain JS — no framework needed:

```javascript
hamburger.addEventListener('click', () => {
  const open = menu.classList.toggle('nav-open');
  hamburger.classList.toggle('is-open', open);
  hamburger.setAttribute('aria-expanded', String(open));
});
```

Hide the mobile menu with `display: none` by default, `display: flex` when `.nav-open`. At ≥768px, hide `.nav-mobile-controls` and `.nav-mobile-menu` entirely via media query.

## Forms (Netlify Forms + local demo mode)

Netlify Forms requires: `data-netlify="true"`, `name="contact"`, and a hidden `<input name="form-name" value="contact">`. Add `netlify-honeypot="bot-field"` for spam protection.

The submit handler must keep two failure modes separate so BOTH the success and error states are testable. **Do not** `throw` on `!resp.ok` and catch everything together — that routes every HTTP error through the catch, and if the catch has a localhost demo branch (it should), the production error path becomes unreachable in tests. Handle the HTTP-error-status directly; reserve `catch` for genuine network failures.

```javascript
try {
  const resp = await fetch('/', { method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: new URLSearchParams(data) });
  if (resp.ok) {
    showSuccess();              // real Netlify POST returned 200/204
  } else {
    showError(); reenableButton();  // server responded 4xx/5xx — real failure, show error
  }
} catch (e) {
  // Network-level failure (fetch threw). No backend in dev/preview → demo success
  // so the UX is reviewable locally. On a production host, show the error.
  const local = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  if (local) { showSuccess(); } else { showError(); reenableButton(); }
}
```

**Testing the form deterministically:** use Playwright `page.route('**/', r => r.fulfill({status: 200}))` to force the success path and `status: 500` to force the error path — no need to deploy or stub `window.location` (which is non-configurable in modern browsers; see pitfalls). With the handler structured as above, a 500 response hits `!resp.ok` → `showError()` directly, bypassing the localhost demo branch.

**Formspree fallback**: change the `action` attribute (and the `fetch` URL) to the Formspree endpoint. One-line swap, same form structure.

## Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

Use `0.01ms` not `0s` — some browsers treat `0s` as "unset" and ignore the override.

## Custom 404

`src/pages/404.astro` → builds to `dist/404.html`. Astro static output serves this automatically for unknown routes. Include `<Nav>` and `<Footer>` so the 404 page is navigable. Test: `curl -s -o /dev/null -w "%{http_code}" http://localhost:4321/nonexistent` should return `404`.

## SEO Checklist

- [ ] Unique `<title>` per page (verify: `grep -r '<title>' dist/ | wc -l` = page count)
- [ ] Meta description ≤155 chars on every page
- [ ] OG tags (`og:title`, `og:description`, `og:image`) on every page
- [ ] `sitemap-index.xml` + `sitemap-0.xml` in `dist/`
- [ ] `robots.txt` with `Sitemap: <site-url>/sitemap-index.xml`
- [ ] `site:` set in `astro.config.mjs` (required for sitemap generation)

## Performance

Astro ships zero JS by default. The only JS is: theme toggle script (~0.5KB), nav toggle (~0.3KB), form handler (~1KB). All inlined by Astro's `<script>` processing. No framework runtime.

Homepage page weight budget: HTML (~10KB) + CSS (~7KB) + 3 tiny JS chunks (~2KB) + Google Fonts (swap, non-blocking) = well under 100KB. The 300KB budget is easy to hit.

## Build & Deploy

```bash
npm run build    # → dist/ with all HTML + sitemap
npm run preview  # serves dist/ on localhost:4321
```

**Netlify**: `netlify.toml` with `[build] command = "npm run build"`, `publish = "dist"`. Netlify Forms auto-detected from `data-netlify="true"`. Deploy = push to main.

## Pitfalls

- **@astrojs/sitemap version mismatch crashes the build.** Sitemap 3.7.x uses the `astro:routes:resolved` hook which doesn't exist in Astro 4.x. Pin to `3.2.1` for Astro 4.x. Error: `Cannot read properties of undefined (reading 'reduce')` at `sitemap/dist/index.js:85`. See `references/build-gotchas.md`.
- **import.meta.glob is NOT visible inside getStaticPaths() if declared at frontmatter top level.** Call the glob inside the function body, or pass data via `props`. Error: `ReferenceError: files is not defined` at build time (works in dev, fails in build). See `references/build-gotchas.md`.
- **Astro processes `<script>` tags by default** — bundling and hoisting them. Use `<script is:inline>` for scripts that must run synchronously in-place (theme init script in `<head>`). Without `is:inline`, the theme script gets deferred and you get FOUC.
- **`Astro.site` is undefined if you don't set `site` in astro.config.mjs.** Sitemap generation and OG URL construction both depend on it. Always set `site: 'https://yourdomain.com'`.
- **Google Fonts `<link>` must include `display=swap`** in the URL (`&display=swap`) for `font-display: swap` to apply. Just adding `font-display: swap` in CSS `@font-face` doesn't work when loading via Google's CSS.
- **`tsconfig.json` extending `astro/tsconfigs/strict`** can surface type errors in `.astro` frontmatter that don't affect the build. If a type error blocks dev but the build passes, use `astro/tsconfigs/base` instead or suppress with `// @ts-ignore`.
- **Playwright tests for Astro dev server**: the dev server runs on port 4321. For production-build tests, use `npm run preview` (also 4321). Configure `webServer` in `playwright.config.ts` to auto-start.
- **CRITICAL — test against `astro preview`, NOT `astro dev`, for "no console errors".** The dev server injects an Astro dev-toolbar (`/node_modules/astro/dist/runtime/client/dev-toolbar/...`) that emits `504 (Outdated Optimize Dep)` console errors on every file change — 20+ per page during HMR. These are Vite dev-server artifacts, NOT site bugs, but a `page.on('console')` error-collector test will fail on them. The production build has no dev toolbar. Set `playwright.config.ts` `webServer.command` to `npm run build && npm run preview`. The spec's own verification commands (Lighthouse, "no console errors") implicitly assume the production build for the same reason. See `references/testing-gotchas.md`.
- **Sitemaps are BUILD-only.** The dev server does NOT serve `/sitemap-index.xml` — it returns the 404 page (HTTP 404) for that path. Don't `curl`/assert the sitemap against `astro dev`; run `npm run build` and check `dist/sitemap-index.xml` on disk, or test it via `astro preview`.
- **Astro strips TypeScript from client `<script>` tags at build.** `const form = document.getElementById('f') as HTMLFormElement` in a `.astro` `<script>` compiles fine — the `as ...` casts are removed and the output is clean JS. You do NOT need `<script lang="ts">` or is:inline for this. Verify: `grep -E ' as [A-Z]' dist/_astro/*.js` should return nothing.
- **Test-only gotchas (don't lose an hour to these):** (1) `window.location` is non-configurable — you CANNOT override `location.hostname` via `addInitScript`/`Object.defineProperty` to test host-dependent branches; use Playwright `page.route` to control the response instead. (2) Chromium clamps reduced-motion `transition-duration` to `1e-5s`, not `0s` — assert `<= 0.001` (parsed float), never `=== '0s'`. (3) A `Locator` matching multiple elements fails `toBeVisible()` with a strict-mode violation — scope the selector (e.g. `.contact-info a[href^="mailto:"]`, not bare `a[href^="mailto:"]`).
- **SVG OG images work** but some social platforms (LinkedIn) prefer PNG/JPG. If OG image rendering matters cross-platform, generate a PNG. SVG is fine for a placeholder.
- **Don't run `npm create astro@latest` interactively in a script** — it has 5+ prompts. Write the config files directly and `npm install`.
- **WCAG contrast on ELEVATED surfaces, not just the page background (dark-theme trap).** An accent color that passes AA on the page `--color-bg` (`#0a0a0f`) can FAIL on an elevated card `--color-bg-elevated` (`#13131a`). Indigo `#6366f1` = 4.6:1 on page bg (PASS) but 4.1:1 on a card bg (FAIL). Two recurring offenders: (1) accent-colored text/links sitting on cards (e.g. a "Learn more →" span) — use the hover shade `--color-accent-hover` (`#818cf8` ≈ 6.2:1 on card bg) for text on elevated surfaces; (2) white text on an accent-colored button — darken the dark-theme button bg to `#5457e6` (white-on-`#5457e6` ≈ 5.4:1) instead of `#6366f1` (≈4.5:1, fails by a hair). Always verify with `npx lighthouse <url> --only-categories=accessibility` and read the `color-contrast` audit result (installs on first run). See `references/accessibility-contrast.md`.
- **Verify contrast before delivery, not at final audit.** A color-contrast failure only costs ~2 lines of CSS to fix if caught during build, but blocks the delivery gate if found at acceptance review. Run Lighthouse accessibility once on the styled site before declaring the build done.

## Reference Files

- `references/build-gotchas.md` — Full error transcripts and fixes for the sitemap version crash and the import.meta.glob scope issue, with reproduction steps and the exact working code patterns.
- `references/testing-gotchas.md` — Playwright testing traps: dev-vs-preview console noise, build-only sitemaps, non-configurable `window.location`, reduced-motion `1e-5s` clamp, strict-locator multi-match, compact-output discipline.
- `references/accessibility-contrast.md` — WCAG contrast on elevated dark-theme surfaces: why `#6366f1` passes on page bg but fails on card bg, the 2-line CSS fix (hover shade for text, `#5457e6` for buttons), and how to verify with Lighthouse.
- `scripts/verify.sh` — Reusable ad-hoc verification: build + page/sitemap/robots checks + meta-overflow + JS-bundle-size greps + full Playwright suite, compact output ending in `VERDICT=PASS/FAIL`. Copy into a project root and run `bash verify.sh`.

## Related Skills

- `claude-design` — single HTML artifact (use when one page suffices, no project scaffold needed)
- `popular-web-designs` — real design systems (Stripe, Linear, Vercel) as reference for visual styling
- `web-dashboard-apps` — FastAPI+SQLite real-time apps (different class: server-side, not static)
