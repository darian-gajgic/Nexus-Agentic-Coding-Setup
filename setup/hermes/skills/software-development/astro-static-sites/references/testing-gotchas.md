# Astro Playwright Testing Gotchas

Lessons from building + testing a 7-page Astro brochure site (task-a130394d).
Each cost real debugging time; capturing so the next site doesn't pay it again.

## 1. Test against `astro preview`, NOT `astro dev`, for console-error checks

**Symptom:** a "no console errors on any page" test (`page.on('console', m => { if (m.type()==='error') ... })`) fails with 20+ errors per page:
```
Failed to load resource: the server responded with a status of 504 (Outdated Optimize Dep)
TypeError: Failed to fetch dynamically imported module: http://localhost:4321/node_modules/astro/dist/runtime/client/dev-toolbar/apps/audit/index.js?v=...
```

**Root cause:** the Astro dev server injects a dev-toolbar client app. On every HMR / file change, Vite marks its deps outdated and the toolbar's dynamic imports 404/504. This is a **dev-server artifact**, not a site bug — the production build has no toolbar.

**Fix:** set `playwright.config.ts` `webServer.command` to build-then-preview:
```ts
webServer: {
  command: 'npm run build && npm run preview -- --port 4321',
  url: 'http://localhost:4321',
  reuseExistingServer: !process.env.CI,
  timeout: 120_000,
}
```
The spec's own verification commands (Lighthouse, "no console errors") implicitly assume the production build for this reason.

**Use `astro dev`** for HMR-driven development; use `astro preview` for anything asserting on console output, performance, or production behavior.

## 2. Sitemaps are build-only — dev serves a 404 for `/sitemap-index.xml`

`curl http://localhost:4321/sitemap-index.xml` against `astro dev` returns the 404 page (HTTP 404), not the sitemap. The `@astrojs/sitemap` integration only runs in the build. To test the sitemap, either:
- `npm run build` then `cat dist/sitemap-index.xml`, or
- test via `astro preview` (which serves the built file).

## 3. Astro strips TypeScript from client `<script>` tags

A `.astro` `<script>` block containing `const form = document.getElementById('f') as HTMLFormElement` compiles cleanly — Astro removes the `as ...` casts and ships plain JS. You do NOT need `lang="ts"`. Verify: `grep -E ' as [A-Z][A-Za-z]+' dist/_astro/*.js` should be empty.

This means the **same** `<script>` source serves dev and prod identically (both compiled). Don't confuse this with the `is:inline` concern — `is:inline` is about *timing/processing* (inline-sync vs hoisted-bundled), not about TypeScript.

## 4. `window.location` is non-configurable — you cannot stub hostname

To test a form handler that branches on `location.hostname` (e.g. localhost demo mode), `Object.defineProperty(window, 'location', { value: {...} })` via `addInitScript` **silently fails** — `window.location` is a non-configurable, non-writable special object in modern browsers. The handler still sees the real `localhost`.

**Fix:** don't stub the host. Make the branch testable by structure (see the form pattern in SKILL.md: handle `!resp.ok` directly, reserve `catch` for network failure) and use Playwright `page.route` to control the response:
```ts
await page.route('**/', r => r.fulfill({ status: 500, body: 'Error' }));  // force error
await page.route('**/', r => r.fulfill({ status: 200, body: 'OK' }));     // force success
await page.route('**/', r => r.abort('failed'));                          // force network failure
```

## 5. Chromium reduced-motion clamps to `1e-5s`, not `0s`

When testing `prefers-reduced-motion: reduce`, Chromium reports `transition-duration: 1e-05s` (not `0s`). Assert the parsed float, not a string:
```ts
const d = await page.locator('.nav-link').first()
  .evaluate(el => parseFloat(getComputedStyle(el).transitionDuration));
expect(d).toBeLessThanOrEqual(0.001);  // NOT .toBe('0s')
```
(Note: the CSS rule itself should use `0.01ms` for cross-browser reliability — see SKILL.md reduced-motion section.)

## 6. `Locator.toBeVisible()` is strict — multi-element matches throw

`page.locator('a[href^="mailto:"]')` fails `toBeVisible()` with a strict-mode violation if there are two mailto links (one in content, one in footer). Scope the selector: `page.locator('.contact-info a[href^="mailto:"]').first()`.

## 7. Compact verification output (so PASS survives truncation)

When a verification run's output is captured/truncated by a guardrail, a verbose Playwright list-report can push the final `VERDICT=PASS` line out of the captured window. Use `--reporter=dot` and echo only the summary line + verdict. The `scripts/verify.sh` in this skill does exactly this.
