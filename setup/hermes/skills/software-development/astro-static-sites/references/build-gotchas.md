# Astro Build Gotchas — Error Transcripts & Fixes

Full transcripts of the two build-breaking errors encountered when building an Astro 4.x static site with `@astrojs/sitemap` and dynamic Markdown routes. Both errors are silent in `npm run dev` and only surface at `npm run build` time.

---

## 1. @astrojs/sitemap Version Mismatch

### Symptom

Build completes all pages successfully, then crashes at the very end during the sitemap integration's `astro:build:done` hook:

```
19:22:48 ▶ src/pages/services/index.astro
19:22:48   └─ /services/index.html (+1ms)
19:22:48 ✓ Completed in 19ms.

Cannot read properties of undefined (reading 'reduce')
  Location:
    /project/node_modules/@astrojs/sitemap/dist/index.js:85:37
  Stack trace:
    at astro:build:done (file:///project/node_modules/@astrojs/sitemap/dist/index.js:85:37)
    at async AstroBuilder.build (...)
```

**Exit code: 1.** All HTML files are generated; only the sitemap XML fails.

### Root Cause

`@astrojs/sitemap` version 3.7.x (latest as of mid-2026) registers a hook called `astro:routes:resolved`:

```js
// @astrojs/sitemap 3.7.x dist/index.js (lines 30-37)
hooks: {
  "astro:routes:resolved": ({ routes }) => {
    _routes = routes;
  },
  "astro:config:done": async ({ config: cfg }) => {
    config = cfg;
  },
```

This hook **does not exist in Astro 4.x** (it was added in Astro 5.x). The hook silently never fires, so `_routes` stays `undefined`. Later, at line 85:

```js
const routeUrls = _routes.reduce((urls, r) => { ... }, []);
//                   ^ undefined.reduce() → crash
```

The error message ("Cannot read properties of undefined (reading 'reduce')") gives zero hint that this is a version compatibility issue. It looks like a bug in the sitemap code.

### Fix

Pin `@astrojs/sitemap` to a version compatible with your Astro major:

```bash
# For Astro 4.x:
npm install @astrojs/sitemap@3.2.1

# For Astro 5.x:
npm install @astrojs/sitemap@latest   # 3.7.x works
```

Specify as an exact version in `package.json` (no caret):

```json
"dependencies": {
  "astro": "^4.16.18",
  "@astrojs/sitemap": "3.2.1"
}
```

### How to verify the fix

```bash
npm run build
# Should end with:
# [@astrojs/sitemap] `sitemap-index.xml` created at `dist`
# [build] Complete!
ls dist/sitemap-*.xml
# dist/sitemap-0.xml  dist/sitemap-index.xml
```

### General lesson

Astro integrations are tightly coupled to Astro's internal hook API. Always check integration compatibility against the **Astro major version**, not just "latest on npm." When a build crashes inside `node_modules/<integration>/dist/`, check:
1. The integration's `package.json` peerDependencies
2. The Astro version's available hooks (changed between 4.x and 5.x)
3. Pin to the integration version that shipped around the same time as your Astro version

---

## 2. import.meta.glob Scope in getStaticPaths

### Symptom

Dynamic route page (`src/pages/services/[slug].astro`) works in `npm run dev` but crashes at build time:

```
19:22:48 ▶ src/pages/services/[slug].astro
19:22:48 [ERROR] [build] Failed to call getStaticPaths for src/pages/services/[slug].astro
serviceFiles is not defined
  Location:
    /project/node_modules/astro/dist/core/render/route-cache.js:28:27
  Stack trace:
    at Module.getStaticPaths (file:///project/dist/pages/services/_slug_.astro.mjs:116:29)
    at getPathsForRoute (file:///project/node_modules/astro/dist/core/build/generate.js:196:31)
```

**Exit code: 1.**

### Root Cause

Astro's static build process isolates `getStaticPaths()` into its own module scope during the build. Variables declared in the `.astro` file's frontmatter top level are **not** accessible inside `getStaticPaths()` at build time, even though they are at dev time.

**Broken pattern:**
```astro
---
// These are in frontmatter top-level scope
const serviceFiles = import.meta.glob('../../content/services/*.md', { eager: true });

export function getStaticPaths() {
  // At build time, this is extracted to a separate module — serviceFiles is undefined here!
  const slugs = Object.keys(serviceFiles).map(...);
  return slugs.map(slug => ({ params: { slug } }));
}

const { slug } = Astro.params;
const service = serviceFiles[`../../content/services/${slug}.md`];  // also undefined
---
```

In dev mode, the module runs as a single unit, so the closure works. In build mode, Astro's build pipeline extracts `getStaticPaths` into a standalone function for the route-generation phase, losing the closure.

### Fix

Call `import.meta.glob()` **inside** `getStaticPaths()`, and pass resolved data via `props`:

```astro
---
export function getStaticPaths() {
  const files = import.meta.glob('../../content/services/*.md', { eager: true });
  const slugs = Object.keys(files).map(path => {
    const m = path.match(/\/([^/]+)\.md$/);
    return m ? m[1] : '';
  }).filter(Boolean);

  return slugs.map(slug => ({
    params: { slug },
    props: {
      data: files[`../../content/services/${slug}.md`].frontmatter,
      slug,
    },
  }));
}

// Access via Astro.props, NOT Astro.params + re-lookup
const { data, slug } = Astro.props;
---
```

Key changes:
1. `import.meta.glob` called inside `getStaticPaths()` — not at top level
2. Data passed through `props` in the return value
3. Page body reads from `Astro.props`, not by re-looking-up files in frontmatter

### How to verify

```bash
npm run build
# Should show:
# ▶ src/pages/services/[slug].astro
#   ├─ /services/custom-coding/index.html
#   ├─ /services/enhancements/index.html
#   └─ /services/ai-development/index.html
```

If you see `Failed to call getStaticPaths` or `X is not defined`, the glob scope is the culprit.

### General lesson

Astro's frontmatter and `getStaticPaths` have different execution contexts at build time. Treat `getStaticPaths` as an isolated function — it should not reference any frontmatter-top-level variables. Pass everything it needs either via its internal `import.meta.glob` call or through the `props` return pattern. The dev server's behavior is misleading here because it doesn't isolate the scope.
