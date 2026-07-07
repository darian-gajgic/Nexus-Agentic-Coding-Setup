// ═══════════════════════════════════════════════════════════
// NEXUS — BROWSER VERIFY
// Loads the page in a real headless browser, checks JARVIS view
// renders, 3D avatar mounts, no JS console errors.
// Usage: node scripts/browser-verify.mjs
// ═══════════════════════════════════════════════════════════
import { chromium } from 'playwright';

const BASE = process.env.BASE_URL || 'http://localhost:8777';
const errors = [];
const passed = [];
let exitCode = 0;

function ok(name) { passed.push(name); }
function fail(name, detail) { errors.push({ name, detail }); }

async function run() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  // Collect console errors
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push({ name: 'console.error', detail: msg.text() });
  });
  page.on('pageerror', err => {
    errors.push({ name: 'pageerror', detail: err.message });
  });

  // 1. Load index page
  try {
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
    ok('index.html loads without network errors');
  } catch (e) {
    fail('index.html loads', e.message);
    await browser.close();
    return;
  }

  // 2. Check static assets loaded
  const appjsLoaded = await page.evaluate(() => typeof init === 'function');
  if (appjsLoaded) ok('app.js loaded, init() exists');
  else fail('app.js loaded', 'init() function not found');

  const threeLoaded = await page.evaluate(() => typeof THREE !== 'undefined');
  if (threeLoaded) ok('Three.js loaded');
  else fail('Three.js loaded', 'THREE global not found');

  const avatarClassExists = await page.evaluate(() => typeof JARVISAvatar === 'function');
  if (avatarClassExists) ok('JARVISAvatar class available');
  else fail('JARVISAvatar class', 'class not found globally');

  // 3. Navigate to JARVIS view
  try {
    // Click the JARVIS nav item
    await page.click('[data-view="jarvis"]');
    await page.waitForTimeout(2000); // boot sequence
    ok('clicked JARVIS nav, no crash');
  } catch (e) {
    fail('navigate to JARVIS', e.message);
  }

  // 4. Check JARVIS DOM elements exist
  const jarvisBoot = await page.$('#jarvisBoot');
  if (jarvisBoot) ok('JARVIS boot overlay rendered');
  else fail('JARVIS boot overlay', '#jarvisBoot not found');

  // Wait for boot to finish
  await page.waitForTimeout(3000);

  const jarvisLayout = await page.$('.jarvis-layout');
  if (jarvisLayout) ok('JARVIS layout rendered after boot');
  else fail('JARVIS layout', '.jarvis-layout not found after boot');

  const avatarWrap = await page.$('#jAvatarWrap');
  if (avatarWrap) ok('#jAvatarWrap container exists');
  else fail('#jAvatarWrap', 'container not found');

  // 5. Check 3D avatar mounted (canvas inside avatar wrap)
  const avatarCanvas = await page.$('#jAvatarWrap canvas');
  if (avatarCanvas) ok('Three.js canvas mounted in avatar container');
  else fail('avatar canvas', 'no <canvas> inside #jAvatarWrap');

  // 6. Check reactor canvas
  const reactorCanvas = await page.$('#jReactor');
  if (reactorCanvas) ok('arc reactor canvas exists');
  else fail('arc reactor canvas', '#jReactor not found');

  // 7. Check chat input
  const chatInput = await page.$('#jInput');
  if (chatInput) ok('chat input exists');
  else fail('chat input', '#jInput not found');

  // 8. Check feed area
  const feed = await page.$('#jFeed');
  if (feed) ok('chat feed exists');
  else fail('chat feed', '#jFeed not found');

  // 9. Check side panels loaded data
  const hermesStatus = await page.$eval('#jHermesStatus', el => el.textContent).catch(() => null);
  if (hermesStatus && hermesStatus !== '—') ok(`Hermes status loaded: ${hermesStatus}`);
  else fail('Hermes status', `got "${hermesStatus}"`);

  const voiceStatus = await page.$eval('#jVoiceStatus', el => el.textContent).catch(() => null);
  if (voiceStatus && voiceStatus !== '—') ok(`Voice status loaded: ${voiceStatus}`);
  else fail('Voice status', `got "${voiceStatus}"`);

  // 10. Type a message and verify input works
  try {
    await page.fill('#jInput', 'test message');
    const val = await page.$eval('#jInput', el => el.value);
    if (val === 'test message') ok('chat input accepts text');
    else fail('chat input', `expected "test message", got "${val}"`);
  } catch (e) {
    fail('chat input interaction', e.message);
  }

  // 11. Navigate away and back — verify no memory leak / crash
  try {
    await page.click('[data-view="dashboard"]');
    await page.waitForTimeout(500);
    await page.click('[data-view="jarvis"]');
    await page.waitForTimeout(2000);
    const layout2 = await page.$('.jarvis-layout');
    if (layout2) ok('view switching dashboard->jarvis works');
    else fail('view switching', 'jarvis layout missing after re-entry');
  } catch (e) {
    fail('view switching', e.message);
  }

  // Screenshot for evidence
  await page.screenshot({ path: 'scripts/screenshot-jarvis.png' });
  ok('screenshot saved');

  await browser.close();
}

await run();

// Report
console.log('\n═══════════════════════════════════════');
for (const p of passed) console.log(`  \x1b[32mPASS\x1b[0m  ${p}`);
for (const e of errors) console.log(`  \x1b[31mFAIL\x1b[0m  ${e.name} — ${e.detail}`);
console.log('═══════════════════════════════════════');
console.log(`  ${passed.length} passed, ${errors.length} failed`);
if (errors.length > 0) exitCode = 1;
process.exit(exitCode);
