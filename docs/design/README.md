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

## `readme-banner.png`

The README's banner, derived from `cli-header.png` rather than drawn again — the wordmark exists
once, and a second hand-made copy of it is the drift this directory is here to prevent.

Two changes, both made by **moving the mockup's own pixels**, so no font had to be matched:

- **The `v0.4.1` segment is gone.** It is the number the mockup was drawn with, not one toolbox
  has ever been at — `git describe` currently answers with a bare hash. `cli/banner.py` already
  refuses to print a version it is not; a README claiming one in the first thing a reader sees
  would be the same lie in a louder place. What is left, `by SKYROW.LABS · tb --help`, cannot
  go stale.
- **The byline is re-centred** under the wordmark's own extent (x 283–746), and the stray
  `#202428` column down the source's left edge is squared off to the panel colour.

Saved at **2x with nearest-neighbour** and displayed at `width="799"`, so the pixel art is exact
on a HiDPI screen and averages back to the source pixels on a 1x one. Nearest-neighbour matters:
any smooth resample turns 5x7 block letters to mush, which is the same reason `cli/banner.py`
samples the grid instead of scaling the image.

**If `cli-header.png` changes, re-derive this rather than editing it.**
