import { chromium } from 'playwright';
import { pathToFileURL } from 'node:url';
import { readdirSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const OUT = process.argv[2], DIR = join(OUT, 'preview');
mkdirSync(join(OUT, '../cards'), { recursive: true });
const browser = await chromium.launch({ executablePath: '/usr/bin/chromium' });
const results = [];

// A signature of how every element actually renders. Comparing it with the
// stylesheets disabled proves the design system is doing the work — the one
// thing a preview card exists to demonstrate.
const SIG = () => [...document.body.querySelectorAll('*')].map((e) => {
  const c = getComputedStyle(e), r = e.getBoundingClientRect();
  return [c.color, c.backgroundColor, c.fontFamily, c.fontSize, c.borderRadius,
    c.borderTopWidth, c.borderBottomWidth, Math.round(r.width), Math.round(r.height)].join('|');
}).join(';');

for (const f of readdirSync(DIR).filter((x) => x.endsWith('.html')).sort()) {
  const page = await browser.newPage({ viewport: { width: 720, height: 420 } });
  const failed = [], errors = [];
  page.on('requestfailed', (r) => failed.push(r.url()));
  page.on('response', (r) => { if (r.status() >= 400) failed.push(`${r.status()} ${r.url()}`); });
  page.on('pageerror', (e) => errors.push(String(e)));

  await page.goto(pathToFileURL(join(DIR, f)).href, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);

  const m = await page.evaluate((sigSrc) => {
    const sig = new Function('return (' + sigSrc + ')()');
    const styled = sig();
    const fonts = new Set([...document.body.querySelectorAll('*')]
      .map((e) => getComputedStyle(e).fontFamily.split(',')[0].replace(/"/g, '').trim())
      .filter((x) => x && x !== 'sans-serif'));
    const offscreen = [...document.body.querySelectorAll('*')]
      .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right < 1 || r.left > 1400); }).length;
    // Now strip every stylesheet and re-measure.
    for (const s of document.styleSheets) { try { s.disabled = true; } catch { /* cross-origin sheet — nothing to toggle */ } }
    const bare = sig();
    for (const s of document.styleSheets) { try { s.disabled = false; } catch { /* see above */ } }
    return { styled, bare, fonts: [...fonts], offscreen,
      textLen: document.body.innerText.trim().length, height: document.body.scrollHeight };
  }, SIG.toString());

  await page.screenshot({ path: join(OUT, '../cards', f.replace('.html', '.png')), fullPage: true });
  await page.close();

  const changed = m.styled !== m.bare;
  const dsFonts = m.fonts.filter((x) => /ui-monospace|JetBrains Mono|monospace/.test(x));
  const bad = [];
  if (failed.length) bad.push(`requests:${failed.length}`);
  if (errors.length) bad.push(`js:${errors.length}`);
  if (!changed) bad.push('stylesheet has NO effect');
  if (!dsFonts.length) bad.push('no DS font applied');
  if (m.textLen < 20) bad.push('no text');
  if (m.offscreen > 0) bad.push(`offscreen:${m.offscreen}`);
  results.push({ card: f, changed, fonts: dsFonts, textLen: m.textLen, height: m.height,
    verdict: bad.length ? bad.join(' / ') : 'ok' });
}
await browser.close();
const bad = results.filter((r) => r.verdict !== 'ok');
console.log(results.map((r) =>
  `${r.verdict === 'ok' ? 'ok  ' : 'FAIL'} ${r.card.replace('.html', '').padEnd(24)} styled=${r.changed ? 'yes' : 'NO '} fonts=${r.fonts.length} text=${String(r.textLen).padStart(4)} h=${String(r.height).padStart(4)}${r.verdict === 'ok' ? '' : '  <- ' + r.verdict}`).join('\n'));
console.log(`\n${results.length - bad.length}/${results.length} cards verified`);
process.exit(bad.length ? 1 : 0);
