# sky.boss — how to build with it

sky.boss is an operator surface: a canvas of windows over a command palette,
rendered in one stylesheet. This is a **CSS design system**, not a component
library — there is nothing to import and no provider to wrap. You style with
colour **roles** and a fixed class vocabulary, both shipped here.

## Setup

Link `styles.css` and write markup. It pulls the roles and then `sb.css`, which
is the entire surface.

Three things are unusual and load-bearing:

- **Dark only, and monospace throughout.** `body` is `3rem/1.45 var(--mono)`.
  There is no light theme and no proportional font anywhere.
- **Every size is `rem`, and `1rem` is four scaled pixels.** `--sb-scale` is the
  one number the whole surface is measured in — `html` is
  `font-size: calc(4px * var(--sb-scale))`. Divide any design pixel by four to
  get its rem: 12px is `3rem`, 6px is `1.5rem`. `tokens.css` sets `1.15`, what
  the app ships. **Never write a `px`** — a hairline left at `1px` becomes a
  thread when the surface scales up.
- **`sb.css` is written for a full-window application.** It sets
  `body { overflow: hidden; height: 100% }` because the canvas manages its own
  scrolling. Override those two if you are building a page that scrolls.

## Colour is a role, never a value

Eleven roles, generated from `cli/theme.py` — the only place in the project
allowed to name a hex, and a test fails on one anywhere else. Honour that here:
**never write a hex or an `rgba()`.**

| Role | Use |
|---|---|
| `--sb-bg` | the void, under everything — never pure black |
| `--sb-surface` `--sb-surface-2` | panels; inset wells and inputs |
| `--sb-text` `--sb-text-2` `--sb-text-3` | body · secondary · structure, not reading text |
| `--sb-brand` | the accent: focus, selection, the live thing |
| `--sb-ok` `--sb-warn` `--sb-danger` | outcome |
| `--sb-border` | declared borders |

Tints are **derived with `color-mix` against those roles**, never written out —
an `rgba(56, 189, 248, .12)` is a hex by another name. Four are pre-derived and
you should reach for them first: `--sb-tint` (brand at 14%, a soft fill),
`--sb-edge` (brand at 30%, a lit border), `--sb-hair` (text at 8%, the default
hairline), `--sb-sink` (bg at 70%, a scrim). Geometry: `--r-sm` `--r-md`
`--r-lg` for corners, `--hair` for border width, `--lift` for the one shadow.

## The class vocabulary

- **Window** — `.canvas.tile` (needs `--sb-cols`) wraps `.win`, optionally
  `.focus`. Inside: `.title` (with `.dot` `.num` `.cmd` `.age` `.spacer`
  `.addtag`), `.chips`, `.body` holding `pre.raw.stream`, and `.foot` with
  `.hint`. A dead window takes `.dead-band`.
- **Marks** — what the tinter puts on a line: `.mk-ok` `.mk-warn` `.mk-fail`
  `.mk-num` `.mk-path` `.mk-ref` `.mk-accent` `.mk-muted` `.mk-bold`, each on a
  span inside `.ln`. **Tint is shape, never judgement** — a timestamp, a number,
  a path. There is no ERROR/WARN vocabulary; the operator declares their own.
- **Bands** — what a follow window knows about its output: `.band` with `.top`
  or `.foot`, carrying `.band-src`, `.band-att` (`.bad` when dead),
  `.band-warn`, `.band-hint`. **Quiet and dead are different words.**
- **Chrome** — `.bar` (the top bar *is* the title bar) with `.brand` `.host`
  `.seg` `.barpal` `.chev` `.stat` `.quit`; the rail is `.tools` with
  `.tools-head` `.tools-filter` `.tools-list` `.tool-row` `.tool` `.tool-name`
  `.tool-kind` `.tool-acts`, and `.tools-foot`.
- **Controls** — `.sbtn` plus `.on` `.plain` `.danger`; `.chip` plus `.on`
  inside `.chips`; `.dot` plus `.task` `.bad`.

For layout of your own, write plain CSS in `rem` and use the roles above. There
are no utility classes.

## Two rules the surface itself keeps

They are worth honouring in anything built to look like sky.boss:

- **Only a read may refresh.** Re-running a read is a refresh; re-running a
  write is a scheduler nobody asked for. A thing that acts is marked, not
  labelled — the `!` in the rail is a warning, not one badge among four.
- **A surface must not claim what it cannot see.** A band reading `quiet` over a
  dead stream is a false statement, not stale data. Say "no evidence" rather
  than "clear".

## Where the truth is

- `tokens.css` — the roles, generated; do not edit
- `sb.css` — the whole surface, one file, commented with the reasoning
- `README.md` — the full class index

## A typical build

```html
<div class="canvas tile" style="--sb-cols: 1">
  <div class="win focus">
    <div class="title">
      <span class="dot"></span><span class="num">#1</span>
      <span class="cmd">read -- tail -f build.log</span>
      <div class="spacer"></div>
      <button class="sbtn">PIN</button>
    </div>
    <div class="body">
      <pre class="raw stream"><span class="ln">built <span class="mk-num">184</span> files <span class="mk-ok">✓</span></span></pre>
    </div>
    <div class="foot"><span class="hint">ok · 0.04s</span></div>
  </div>
</div>
```
