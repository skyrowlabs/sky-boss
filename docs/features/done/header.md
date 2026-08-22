---
status: complete
created: 2026-08-22
updated: 2026-08-22
agent_value: 2
key_files:
  - cli/banner.py
  - cli/theme.py
  - cli/__init__.py
  - docs/design/cli-header.png
  - tests/test_banner.py
---

# The mark — a header for `tb`

## Why

`tb --help` opened with a title and a subtitle that any Click app would have printed:

```
toolbox — the homebase operator CLI.
Deterministic scripts and agentic automations across a primary workstation and the machines
around it.
```

The operator drew a header instead — `docs/design/cli-header.png`: a pixel toolbox, **TOOLBOX**
in a blocky face, and a byline reading `by SKYROW.LABS · v0.4.1 · tb --help`. The ask was to
make that the header and drop the two lines it replaces.

A terminal cannot show an image. But the source is *pixel art*, which means it does not have to
be shown as an image — it can be **drawn**, and drawn at exactly the fidelity the designer used.

## Shape

**The art is sampled on the PNG's own grid, not scaled down.** The grid was measured rather than
guessed: 11.2px per column, 8.86px per row, a 5x7 face for each letter and an 18x14 glyph for the
toolbox. Sampled there, one art pixel per cell, `TOOLBOX` comes back crisp. Sampled anywhere else
it comes back as mush — the first attempt resampled to a 64-column box and produced letters that
were unreadable at a glance, which is what "just scale the image" means at this size.

**Half-blocks, so the proportions survive.** A terminal cell is about twice as tall as it is wide,
so one art pixel per *cell* renders the mark at double height. `▀` splits a cell into two roughly
square halves — foreground above, background below — putting 14 art rows into 7 terminal rows at
the proportions the mark was drawn with. The panel is 67 columns wide and 8 lines tall including
the byline.

**The picture lives in the source as a picture.** `ART` in `cli/banner.py` is fourteen strings of
`B`/`D`/`W`/`.` — brand, dark slate, light, background. It is legible, diffable and hand-editable;
changing the mark is changing those strings, not re-running a converter. The PNG stays in
`docs/design/` as the thing it was drawn from.

**The mark paints its own background, and that is what licenses its colours.** Every CLI role is
the smallest darkening of its token that clears 3.5:1 against *both* white and the void
([[theme]]), because tb prints into a terminal whose background nobody here knows. The mark
removes that unknown by painting a panel, which puts it in the canvas's position rather than the
CLI's — so it takes `BRAND`, `TEXT`, `TEXT_3` and `SURFACE_2` at full strength.

It is also the **only** answer available, which is the part worth keeping: the mark's hues fail in
opposite directions. The light handle disappears on white; the dark slate disappears on black.
No single colour satisfies a two-sided floor for either of them, so darkening would dim the brand
mark and *still* not make it legible on both.

**The byline carries the real version.** `git describe`, not the mockup's `v0.4.1` — a header
stating a version it is not is worse than one with no version. Which means its length is unknown
at authoring time, so the separators narrow from `   ·   ` to ` · ` first and the version
truncates last, and the line is always exactly the panel's width.

**It refuses to draw rather than degrade badly.** Narrower than the panel, or not a terminal at
all, and `show()` returns False without printing; help falls back to `toolbox  ·  <version>`. A
banner that wraps turns a rectangle into confetti, and a wall of block characters down a pipe is
worse than no header. `--json` gets no paint either, for the same reason nothing decorative goes
out when the envelope was asked for.

**Does not do:**

- **No banner on subcommands.** `tb read --help` is a reference page someone may read three times
  in a day; a banner over every one is a banner nobody sees. Only the root wears it.
- **No image rendering.** No sixel, no kitty graphics, no iTerm inline images. They would each be
  a terminal-capability branch, and the mark already exists in a form every terminal can draw.
- **No colour negotiation.** Rich degrades truecolor to 256 or 16 on its own; tb does not inspect
  `COLORTERM` and pick a palette.
- **No ASCII fallback of the mark.** The small-surface answer is a *name*, not a worse picture.
- **Not a splash screen.** It appears where help appears, and nowhere else — never before a
  command runs.

## Phases

### Round 1 — draw the PNG (2026-08-22)

- [x] **Measure the grid and generate the art.** Letterforms confirmed as 5x7 by sampling; icon
      18x14 on the same grid; composed to 63x14 and embedded as `ART`.
- [x] **`cli/banner.py`.** Half-block rendering, the byline that always fits, and `show()` /
      `plain()` — draw, or say you could not.
- [x] **The mark's colours in `cli/theme.py`**, undarkened, with the reason they sit outside
      `STYLES` written where the next person will look.
- [x] **Wire it to root help** through `Root.format_help`, retiring the title and subtitle. The
      one-line description stays: it is what still earns its place under a logo.
- [x] **Tests.** The art stays a rectangle of known inks, every painted line is the panel's
      width for any version string, narrow and piped surfaces get nothing, subcommands get
      nothing, `--json` gets nothing, and the colours are the design system's own.
- [x] **Verified against a real terminal**, not only the suite — rendered through a pty and
      rasterised to compare against the PNG side by side.

## Notes

### Round 1 — executed (2026-08-22)

What the execution argued back:

- **"Scale the image down" is the wrong instinct and the prototype proved it in one look.** An
  area-averaged 64-column render turned `TOOLBOX` into grey mush, while the *same* resolution
  sampled on the art's own grid was crisp. The resolution was never the problem; the phase
  alignment was. Finding the grid took three measurements and made the rest of the feature easy.
- **The contrast floor could not be satisfied, only stepped outside of — and the reason is
  better than the exemption.** The instinct was to darken the mark's colours like every other CLI
  role. That fails on contact: `W` and `D` fail on *opposite* backgrounds, so there is no pair of
  darkened values that works. Painting a background is not a way around the rule, it is the
  rule's own escape clause — the canvas has used it since it was written. The carve-out is
  asserted by a test that says so, because "correcting" these back is exactly the tidy-looking
  change someone will make.
- **The byline exposed a fragility the mockup hid.** `v0.4.1` fills the panel to the cell, which
  looked like a lucky fit until `git describe` returned `a0b4b6d-dirty` and then
  `1.2.0-14-gabc1234-dirty`. A header whose last line is longer than the rectangle above it is
  visibly broken, so the fit is now computed and tested against a version three times too long.
- **The first wiring leaked a slug into user-facing help.** The root docstring is what `--help`
  prints, and it briefly carried "The mark above is the title… See [[header]]" — a note to the
  next reader of the *source*, printed to every user of the tool. It moved to a comment. Worth
  remembering wherever a docstring is documentation and UI at once, which in Click is everywhere.
- **A pty and a rasteriser were the only honest check.** The suite proves the mechanism; it
  cannot see that the toolbox looks like a toolbox. Capturing real `tb --help` through a pty and
  painting the ANSI back into a PNG put the render next to the source, which is how the icon's
  proportions were confirmed rather than assumed.
