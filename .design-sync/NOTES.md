# design-sync notes — sky.boss

Published to **sky.boss Design System**
(`0843e40b-241a-457c-b264-f61d8af6bf11`), created 2026-09-01.

## Shape

sky.boss is a CSS design system: one stylesheet, `cli/canvas/static/sb.css`,
and no components to import. The design-sync skill's converter bundles React
from a `dist/` and does not apply; the layout is produced off-script by
`.design-sync/scripts/` and checked with the skill's own
`package-validate.mjs`, which has a first-class tokens-only path. It exits
clean.

**The colour roles are not in any stylesheet.** `cli/theme.py` owns them and
the server injects them into the page at runtime, so `tokens.css` is
**generated** by asking `theme.py` for `css_root()` — never transcribed. A
hand-copied hex would be the second palette that module exists to prevent.

**`tokens.css` therefore contains six-digit hexes, and must never be written
into `cli/`.** `tests/test_theme.py` scans `PROJECT_ROOT / "cli"` for `*.py`,
`*.css`, `*.js`, `*.tcss` and fails on `#rrggbb` outside `theme.py`. The build
writes to a scratch directory; nothing generated lands in the repo.

## What ships

- `tokens.css` — the 11 roles from `theme.py`, plus `--sb-scale: 1.15`, which is
  what `sb ui` ships as its default (`cli/canvas/__init__.py`). The stylesheet
  falls back to 1 if it is absent.
- `sb.css` — verbatim, the whole surface
- `styles.css` — the two, in order
- `preview/` — 8 cards: window, marks, topbar, rail, bands, controls, roles, scale

## Preview markup came from a live canvas, not from reading the CSS

`scripts/capture.mjs` starts nothing itself; run `sb ui --no-browser --port
8766`, then point it at the page. It drives the palette exactly as an operator
would and dumps the real DOM. Every card's markup is copied from what the app
actually emitted — the window card is a captured `.tile`, marks and all.

Three things that cost a cycle each and would cost it again:

- **`waitUntil: "networkidle"` never fires.** The canvas holds its session
  stream open by design, so the network is never idle and the wait times out
  at 30s. Use `domcontentloaded` plus an explicit `waitForSelector`.
- **A row's markup is not what the CSS suggests.** The rail's kind label is
  pushed right by `.tool-name { flex: 1 }` inside a `button.tool`, and the gap
  at the right edge is `.tool-edit` / `.tool-drop` reserving space while
  transparent. Omitting them clipped the label; the CSS alone did not say so.
- **`.canvas.tile` needs `--sb-cols`**, which `app.js` sets inline. A card must
  set it too or the grid collapses.

**The rail shows the operator's real saved tools.** They come from
`$SB_HOME/tools.toml`, which is machine-specific and outside the repo. The
cards use invented names (`build-log`, `ship-it`, `disk-free`) on purpose —
nothing from a live rail should reach a published project.

## Verification

`scripts/check-cards.mjs` captures a render signature of every element,
disables every stylesheet, re-captures, and fails if the two match — which
proves the design system is doing the work rather than that a file loaded.
8/8 pass. `scripts/verify-names.mjs` checks every class and token named in
`conventions.md` against the built CSS: 59 classes, 23 tokens, all verified.

Two refinements that matter if you re-run it: a var the stylesheet **reads**
but never defines is still real (`--sb-cols` is set by the page, and telling
the reader to set it is correct), and a dot after a word character is a file
extension, not a class — `build.log` was being read as `.log`.

**Read renders at full size.** A downscaled montage made the top bar look
broken and the modal in the sibling jam.sense sync look translucent; measured
computed styles contradicted both. Only the clipped rail label was real.

## Two things the cards fixed

- The **top bar** is built for a full application window and compresses to
  illegibility at card width. `.sp-wide` in `card-frame.css` gives it a
  realistic width and lets the card scroll rather than shrinking the surface
  it documents.
- **`sb.css` sets `body { overflow: hidden; height: 100% }`** because the
  canvas manages its own scrolling. `card-frame.css` undoes exactly those two
  for a card viewport, and `conventions.md` tells the design agent to do the
  same for a page that scrolls. Nothing else is overridden.
