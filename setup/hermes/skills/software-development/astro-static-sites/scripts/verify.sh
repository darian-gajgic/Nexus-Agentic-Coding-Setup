#!/usr/bin/env bash
# verify.sh — ad-hoc verification for an Astro static site project.
# Run from the project root:  bash <skill>/scripts/verify.sh
# Compact output: verbose logs go to /tmp; only key lines + VERDICT are echoed
# so the result survives a truncated evidence capture.
#
# Checks: build exit code, HTML page count, sitemap + robots presence,
# sitemap URL entries, meta-description overflow (R10 <=155), JS bundle
# sizes (R9 <5KB), placeholder/kill-list greps, and the full Playwright suite.
# Adapt the META_PAGES list and GREP_PATTERNS to your project.
set -u

fuser -k 4321/tcp >/dev/null 2>&1 || true   # free the port for the test webServer
sleep 1

echo "=== build ==="
npm run build > /tmp/hv-build.log 2>&1; BUILD=$?

# --- static checks ---
PAGES=$(find dist -name '*.html' | wc -l)
SMAP=$([ -f dist/sitemap-index.xml ] && echo yes || echo NO)
ROBOTS=$([ -f dist/robots.txt ] && echo yes || echo NO)
SURLS=$(grep -oE '<loc>' dist/sitemap-0.xml 2>/dev/null | wc -l)

# meta-description overflow (add your page list here)
over=0
for f in dist/index.html dist/about/index.html dist/contact/index.html dist/services/index.html; do
  [ -f "$f" ] || { over=$((over+1)); continue; }
  len=$(grep -oiE 'name="description" content="[^"]*"' "$f" | head -1 | sed 's/.*content="//;s/"$//' | wc -c)
  [ $((len-1)) -gt 155 ] && over=$((over+1))
done

# JS bundle size (R9: no file >5KB = 5120 bytes)
BIGJS=0
for j in dist/_astro/*.js; do [ "$(wc -c < "$j")" -gt 5120 ] && BIGJS=$((BIGJS+1)); done

# placeholder + kill-list greps (adjust patterns to your voice rules)
PRICE=$(grep -rl '\[price\]' src/ | wc -l)   # intentional placeholders
KILL=$(grep -rniE 'delve|unleash|unlock the power|revolutionize|game-changer|fast-paced|seamless|cutting-edge|robust solutions|passionate about|important to note|furthermore|moreover' src/ | wc -l)

# --- Playwright suite (builds, serves dist/, runs all tests) ---
echo "=== playwright ==="
npx playwright test --reporter=dot > /tmp/hv-test.log 2>&1; TEST=$?
PASS_LINE=$(grep -E '[0-9]+ passed' /tmp/hv-test.log | tail -1)

echo "build_exit=$BUILD  test_exit=$TEST"
echo "pages=$PAGES sitemap=$SMAP robots=$ROBOTS sitemap_urls=$SURLS"
echo "meta_over_155=$over  js_bundles_over_5KB=$BIGJS  price_files=$PRICE  killlist_hits=$KILL"
echo "playwright: $PASS_LINE"

if [ "$BUILD" -eq 0 ] && [ "$TEST" -eq 0 ] && [ "$over" -eq 0 ] && [ "$KILL" -eq 0 ] && [ "$BIGJS" -eq 0 ]; then
  echo "VERDICT=PASS"
else
  echo "VERDICT=FAIL"
fi
