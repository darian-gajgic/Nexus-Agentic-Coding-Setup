# Test-Contract Mining for Visual Refactors

When redesigning the UI/visual layer of an app that has existing test coverage, many tests assert
on **source code string content** rather than runtime DOM. These are invisible constraints — if you
rewrite a file and drop or rename a CSS class the test checks for, it fails even though the app
works fine. Mine the tests BEFORE writing redesigned code.

## The technique

### 1. Find all source-level assertions

```bash
grep -n "toContain\|toMatch\|expect(" tests/**/*.test.ts
```

Filter to assertions that read a source file and check its content. Typical pattern:

```typescript
const source = fs.readFileSync(path.join(process.cwd(), "src", "app", "page.tsx"), "utf-8");
expect(source).toContain("grid-cols-2");
expect(source).not.toContain("w-[");
```

### 2. Build a per-file contract

For each source file the tests read, list what MUST appear and what MUST NOT appear:

**`src/app/page.tsx`** (read by R11 responsive test):
- MUST contain: `grid-cols-2`, `md:grid-cols-3`, `lg:grid-cols-4`
- MUST NOT contain: `w-[`, `min-w-[400`

**`src/app/category/[slug]/page.tsx`** (read by R11):
- MUST contain: `grid-cols-2`, `md:grid-cols-3`, `lg:grid-cols-4`

**`src/app/globals.css`** (read by R11):
- MUST contain: `44px`

**`src/components/AddToCartButton.tsx`** (read by R11):
- MUST contain: `min-h-[44px]`

**`src/components/CartLineControls.tsx`** (read by R11):
- MUST contain: `min-h-[44px]`

**`src/app/layout.tsx`** (read by R11):
- MUST contain: `max-w-6xl`, `mx-auto`, `px-4`

### 3. Carry strings forward verbatim

`toContain` is a substring match — the exact string just needs to appear ANYWHERE in the file. You
have full flexibility in HOW you use it:

- `grid-cols-2` — keep the grid responsive breakpoint classes on the product grid container. You
  can change gap values, add parent wrappers, restructure sections around it.
- `min-h-[44px]` — keep on the interactive elements (buttons, inputs). You can change all other
  classes on those elements.
- `44px` in CSS — keep the `min-height: 44px` rule for `button, a.btn`. You can add any other CSS.
- `max-w-6xl mx-auto px-4` — keep on the main container in layout. You can restructure everything
  around it.

### 4. What you CAN freely change

Everything not asserted on:
- Color palette (slate → stone/sand/clay)
- Font families and weights (add next/font/google)
- Typography scale, letter-spacing, tracking
- Border colors, border-radius values, shadow definitions
- Hover/focus/transition effects
- Animation keyframes
- Component internal structure (add sections, wrappers, breadcrumbs)
- SVG content (as long as filenames/dimensions stay the same)
- Any class not explicitly checked by a test

## Worked example: webshop visual redesign (2026-07-06)

**Task:** Elevate a Next.js 14 clothing webshop from flat placeholder styling to a premium editorial
aesthetic (Aritzia/Everlane/COS vibe) while keeping all R1-R12 tests green.

**Approach:**
1. Read all 6 test files. Found R11 was the only one with source-level string assertions.
2. Extracted the 6-file contract above.
3. Designed the new system (warm-neutral palette, Fraunces+Inter fonts, refined shadows/animations).
4. Wrote 13 redesigned code files — each carrying its required strings.
5. Regenerated 12 SVG product images (same filenames, 400×400 viewBox).
6. Ran all 4 gates: typecheck, lint, test (20/20 pass), build — all green first try.

**Result:** Zero iterations spent fixing test failures. The test-contract mining step front-loaded
the constraint discovery that would otherwise have caused 3-5 failed test runs.

## Pitfall: tests that check NEGATIVE assertions

`expect(source).not.toContain("w-[")` is just as binding. If your redesign uses arbitrary width
values like `w-[400px]`, the negative assertion fails. Either avoid arbitrary values in that file or
use standard Tailwind width utilities (`w-full`, `w-auto`, `max-w-*`).

## Pitfall: tests that check functional behavior too

Some tests in the same suite may check actual runtime behavior (DB queries, API responses, cart
logic). These are NOT affected by visual changes — but confirm you haven't accidentally touched the
files they exercise (api routes, lib utilities, prisma schema). The rule "don't touch the functional
core" covers this.
