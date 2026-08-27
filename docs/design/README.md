# Vendored design source

`skyrow-colors_and_type.css` is Skyrow Labs' design system token file, copied unmodified from the
design-system bundle. It is here so that `cli/theme.py`'s claim to have copied it verbatim is
**checkable** rather than asserted — `tests/test_theme.py` parses this file and fails if any
token in `theme.py` has drifted from it.

That is the whole reason it is vendored. It is not a second palette and nothing imports it at
runtime; the Python constants remain the ones every consumer derives from.

**If the design system moves,** replace this file and let the test tell you which constants in
`theme.py` need updating. Do not edit `theme.py` alone — that is exactly the drift the file
exists to catch, and it is what happened once already: the palette was approximated from
jam.sense's app tokens and every hue was wrong for a week.

---

## The two PNGs, and `render-mark.py`

**Neither PNG is a source.** `ART` in `cli/banner.py` is the picture; both files here are renders
of it, produced by `render-mark.py` from the repo root:

```bash
.venv/bin/python docs/design/render-mark.py
```

This direction is new as of 2026-08-27 and it is the point. Round 1 of [[header]] measured `ART`
*off* `cli-header.png` — 11.2px per column, 8.86px per row — which made the PNG the original and
the tuple a transcription. That is exactly the arrangement in which one can change and the other
cannot: the `tb` → `sb` rename moved the word `banner.py` prints without moving the drawing beside
it, so `sb --help` greeted you with **sky.boss** next to a picture of a toolbox lettered `TOOLBOX`.
Now they cannot disagree, because there is only one of them.

### `cli-header.png`

The mark alone — one square per art pixel, at the palette's own values, plus the byline. Nothing
here picks a colour; they all come from `cli/theme.py`, which is the rule `tests/test_theme.py`
enforces inside `cli/` and this directory keeps by hand.

### `readme-banner.png`

Real `sb --help`, captured through a **pty** and painted back. It has to be a pty: the mark refuses
to draw when it is not talking to a terminal, so a screenshot of it cannot be taken by reading
stdout. This is the same rasteriser round 1 used to check the icon's proportions, which is still
the only honest check — the suite proves the mechanism but cannot see whether the tower looks like
a tower.

Two things are **drawn rather than typed**, both because a font cannot be relied on: the half-block
`▀` (a font's metrics leave hairlines between rows) and the prompt's `❯` (whatever `fc-match
monospace` resolves to may not carry U+276F, and the first regeneration put tofu in the corner).

Displayed at `width="799"` against a 960px render, so the block letters stay crisp on a HiDPI
screen.

### Neither render carries a version

`cli/banner.py` prints the real `git describe`, because a header stating a version it is not is
worse than one with none. Both renders drop that segment, for two reasons that happen to agree. A
README is read long after any hash means anything, so `36927d9-dirty` in the first thing a reader
sees is the same lie in a louder place. And a PNG that embeds `git describe` changes on **every
commit**, which would make a regenerated design file a permanent diff. What is left,
`by SKYROW.LABS · sb --help`, cannot go stale — and re-running the script with `ART` unchanged is
byte-for-byte a no-op, which is the property that makes "if in doubt, re-run it" safe advice.

**If the mark changes, re-run the script. Do not edit either PNG.**
