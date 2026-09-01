import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/usr/bin/chromium' });
const p = await b.newPage({ viewport: { width: 1400, height: 900 } });
const errs = [];
p.on('pageerror', (e) => errs.push(String(e)));
p.on('console', (m) => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
await p.goto('http://127.0.0.1:8766/', { waitUntil: 'domcontentloaded' });
await p.waitForSelector('#root > *', { timeout: 15000 });
await p.waitForTimeout(1200);
await p.screenshot({ path: 'sb-canvas.png', fullPage: false });
const info = await p.evaluate(() => {
  const pick = (sel) => { const e = document.querySelector(sel); return e ? e.outerHTML.slice(0, 900) : null; };
  const classes = new Set();
  document.querySelectorAll('*').forEach((e) => e.classList.forEach((c) => classes.add(c)));
  return {
    rootChildren: [...document.querySelector('#root')?.children ?? []].map((e) => e.className),
    liveClasses: [...classes].sort(),
    bar: pick('.bar'), rail: pick('.rail') ?? pick('[class*=rail]'), palette: pick('.palette'),
  };
});
console.log(JSON.stringify({ errors: errs, ...info }, null, 1).slice(0, 3500));
await b.close();
