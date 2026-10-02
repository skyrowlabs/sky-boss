import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
const OUT = join(process.argv[2], 'preview');
mkdirSync(OUT, { recursive: true });

const page = (group, title, body, note) => `<!-- @dsCard group="${group}" -->
<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<link rel="stylesheet" href="_card.css"></head>
<body>
<div class="sp-title">${title}</div>
${body}
${note ? `<p class="sp-note">${note}</p>` : ''}
</body></html>
`;
const cards = {};

// A window, exactly as the canvas emits it (captured from a live `sb ui`).
cards['window'] = page('Canvas', 'Window', `
<div class="canvas tile" style="--sb-cols: 1">
  <div class="win focus">
    <div class="title">
      <span class="dot"></span><span class="num">#1</span>
      <span class="cmd">read -- ls -la /etc/hosts</span>
      <span class="age">2s ago</span>
      <div class="spacer"></div>
      <span class="addtag">＋tag</span>
      <button class="sbtn">PIN</button>
      <button class="sbtn">WRAP</button>
      <button class="sbtn plain" title="refresh now">⟳</button>
      <button class="sbtn plain" title="close">✕</button>
    </div>
    <div class="chips"><span class="label">LINKED</span><button class="chip">--screen</button></div>
    <div class="body"><pre class="raw stream"><span class="ln">-rw-r--r-- <span class="mk-num">1</span> root root <span class="mk-num">185</span> Mar <span class="mk-num">21</span> <span class="mk-num">09:36</span> <span class="mk-path">/etc/hosts</span></span><span class="ln">-rw-r--r-- <span class="mk-num">1</span> root root   <span class="mk-num">9</span> Mar <span class="mk-num">21</span> <span class="mk-num">09:36</span> <span class="mk-path">/etc/hostname</span></span></pre></div>
    <div class="foot"><span>showing last 2</span><div class="spacer"></div><span class="hint">ok · 0.04s</span></div>
  </div>
</div>`, 'Every command opens one of these. <span class="mk-path">.tile</span> needs <span class="mk-path">--sb-cols</span>; the canvas sets it.');

cards['marks'] = page('Canvas', 'Highlight marks', `
<div class="canvas tile" style="--sb-cols: 1"><div class="win"><div class="body">
<pre class="raw stream">
<span class="ln"><span class="mk-ok">✓</span> ok — a shape the tinter recognised</span>
<span class="ln"><span class="mk-warn">⚠</span> warn — something to look at</span>
<span class="ln"><span class="mk-fail">✗</span> fail — it did not work</span>
<span class="ln">a number <span class="mk-num">1284</span> and a clock <span class="mk-num">09:36</span></span>
<span class="ln">a path <span class="mk-path">/var/log/agent.log</span></span>
<span class="ln">a reference <span class="mk-ref">#123</span></span>
<span class="ln">an <span class="mk-accent">accent</span>, something <span class="mk-muted">muted</span>, something <span class="mk-bold">bold</span></span>
</pre></div></div></div>`,
'Tint is <b>shape</b>, never judgement — a timestamp, a number, a path. sky.boss ships no ERROR/WARN vocabulary; the operator declares their own under <span class="mk-path">[highlight.NAME]</span>.');

cards['topbar'] = page('Chrome', 'Top bar', `
<div class="sp-wide">
<div class="bar">
  <span class="brand">SKY.BOSS</span>
  <span class="host">127.0.0.1:8766</span>
  <div class="seg nav"><button class="on">canvas</button><button>workbench</button><button>schedule</button></div>
  <div class="barpal"><span class="chev">sb ▸</span><input placeholder="type a command"></div>
  <div class="spacer"></div>
  <span class="stat">TASKS<b>0</b></span><span class="stat">WINDOWS<b>1</b></span>
  <span class="stat">WATCHERS<b>0</b></span><span class="stat">ATTENTION<b>0</b></span>
  <div class="seg"><button class="on">tiled</button><button>floating</button></div>
  <button class="quit" title="close sky.boss">✕</button>
</div>
</div>`, 'The top bar <b>is</b> the title bar — the shell is frameless. A nav entry may only name a screen that exists.');

cards['rail'] = page('Chrome', 'Tools rail', `
<div class="tools" style="width:70rem;position:relative">
  <div class="tools-head"><span>TOOLS</span><input class="tools-filter" placeholder="filter"></div>
  <div class="tools-list">
    <div class="tool-group-row"><div class="tool-group"><span class="tool-chevron">▾</span><span class="tool-group-name">DEPLOY</span></div></div>
    <div class="tool-row"><button class="tool"><span class="tool-name">build-log</span></button><span class="tool-kind">follow</span><span class="tool-edit">✎</span><span class="tool-drop">✕</span></div>
    <div class="tool-row"><button class="tool"><span class="tool-name">ship-it</span><span class="tool-acts">!</span></button><span class="tool-kind">run</span><span class="tool-edit">✎</span><span class="tool-drop">✕</span></div>
    <div class="tool-group-row"><div class="tool-group"><span class="tool-chevron">▾</span><span class="tool-group-name">CHECKS</span></div></div>
    <div class="tool-row"><button class="tool"><span class="tool-name">disk-free</span></button><span class="tool-kind">data</span><span class="tool-edit">✎</span><span class="tool-drop">✕</span></div>
  </div>
  <div class="tools-foot"><span>sb -t &lt;tool&gt;</span></div>
</div>`,
'A group is <b>declared</b>, never inferred from a name prefix. The <span class="mk-warn">!</span> marks a tool that acts — a warning, not one badge among four.');

cards['bands'] = page('Canvas', 'Bands', `
<div class="canvas tile" style="--sb-cols: 1"><div class="win">
  <div class="band top"><span class="band-src">/var/log/agent.log</span><div class="spacer"></div><span class="band-att">live</span><span class="band-hint">1.2 KB · 40 lines</span></div>
  <div class="body"><pre class="raw stream"><span class="ln">waiting for the next line…</span></pre></div>
  <div class="band foot"><span class="band-warn">due 15m ago</span><div class="spacer"></div><span class="band-hint">quiet 4m</span></div>
</div></div>
<div class="sp-row" style="margin-top:4rem">
  <span class="band-att">live</span><span class="sp-cap">att</span>
  <span class="band-att bad">dead</span><span class="sp-cap">att bad</span>
  <span class="band-warn">late</span><span class="sp-cap">warn</span>
  <span class="band-hint">quiet 4m</span><span class="sp-cap">hint</span>
</div>`,
'A band is what a follow window knows about its own output. <b>Quiet and dead are different words</b>: quiet means a stat happened and nothing changed.');

cards['controls'] = page('Chrome', 'Controls', `
<div class="sp-row">
  <button class="sbtn">PIN</button><span class="sp-cap">sbtn</span>
  <button class="sbtn on">WRAP</button><span class="sp-cap">on</span>
  <button class="sbtn plain">⟳</button><span class="sp-cap">plain</span>
  <button class="sbtn danger">KILL</button><span class="sp-cap">danger</span>
</div>
<div class="chips" style="margin-top:4rem">
  <span class="label">LINKED</span>
  <button class="chip">--screen</button><button class="chip on">--json</button><button class="chip">--cols</button>
</div>
<div class="sp-row" style="margin-top:4rem">
  <span class="dot"></span><span class="sp-cap">ok</span>
  <span class="dot task"></span><span class="sp-cap">task</span>
  <span class="dot bad"></span><span class="sp-cap">bad</span>
</div>`);

cards['roles'] = page('Foundations', 'Colour roles', `
<div class="sp-grid" style="grid-template-columns:repeat(4,1fr)">
${['--sb-bg', '--sb-surface', '--sb-surface-2', '--sb-border', '--sb-text', '--sb-text-2', '--sb-text-3', '--sb-brand', '--sb-ok', '--sb-warn', '--sb-danger']
  .map((t) => `<div class="sp-col"><div class="sp-sw" style="background:var(${t})"></div><span class="sp-cap">${t.replace('--sb-', '')}</span></div>`).join('')}
</div>
<div class="sp-row" style="margin-top:4rem">
${['--sb-tint', '--sb-edge', '--sb-hair', '--sb-sink'].map((t) =>
  `<div class="sp-col" style="flex:1"><div class="sp-sw" style="background:var(${t})"></div><span class="sp-cap">${t.replace('--sb-', '')}</span></div>`).join('')}
</div>`,
'Eleven roles, generated from <span class="mk-path">cli/theme.py</span> — the only module allowed to name a hex. The four below are <b>derived</b> with color-mix, never written out.');

cards['scale'] = page('Foundations', 'Scale', `
<div class="sp-col" style="gap:3rem">
${[['--r-sm', '1rem'], ['--r-md', '2rem'], ['--r-lg', '3.5rem']].map(([t, v]) =>
  `<div class="sp-row"><div style="width:22rem;height:9rem;background:var(--sb-surface-2);border:var(--hair) solid var(--sb-hair);border-radius:var(${t})"></div><span class="sp-cap">${t} — ${v}</span></div>`).join('')}
</div>
<div class="sp-col" style="margin-top:4rem;gap:2rem">
  <span class="sp-cap">type: body is 3rem/1.45, monospace throughout</span>
  <span style="font-size:2.5rem">2.5rem — labels and captions</span>
  <span style="font-size:3rem">3rem — body, the surface default</span>
  <span style="font-size:3.5rem">3.5rem — a title</span>
</div>`,
'<b>Every size is rem, and 1rem is four scaled pixels.</b> <span class="mk-path">--sb-scale</span> drives the whole surface as one thing — 12px is 3rem, 6px is 1.5rem. This card renders at 1.15, what <span class="mk-path">sb ui</span> ships.');

for (const [n, h] of Object.entries(cards)) writeFileSync(join(OUT, `${n}.html`), h);
console.log(JSON.stringify({ cards: Object.keys(cards).length, names: Object.keys(cards) }));
