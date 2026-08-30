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

## The renders

**No PNG here is a source.** Every one is produced by a script, from the thing it is a picture of:

```bash
.venv/bin/python docs/design/render-mark.py     # the mark, the banner, the icon, the session
node docs/design/render-canvas.mjs              # the canvas
```

| File | Rendered from | Byte-stable? |
|---|---|---|
| `cli-header.png` | `ART` in `cli/banner.py` | yes |
| `readme-banner.png` | real `sb --help` through a pty | yes |
| `app-icon.png` | `ART`, on a square | yes |
| `readme-session.png` | real commands through a pty | **no** — the band carries a wall clock |
| `readme-canvas.png` | a real `sb ui`, driven over CDP | **no** — port, session id, relative ages |

**The last two change on every render, and that is worth knowing before you run the script.** The
first three are byte-for-byte no-ops when their source has not moved, which is what makes *if in
doubt, re-run it* safe advice for them. It is not safe advice for the screenshots: a band reading
`ran 16:28:18` and a header reading `127.0.0.1:35855` differ every time, so re-rendering them
produces a diff whether or not anything changed. **Re-render those two deliberately — when what
they show has actually moved — not as a reflex.** Same reasoning that keeps `git describe` out of
the banner, arriving as a constraint on when to run rather than on what to draw.

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

### `readme-session.png` and `readme-canvas.png`

The README's two screenshots, and the reason they are scripts rather than screen grabs: a hand-taken
picture of a UI goes stale silently, and nothing can tell you it has.

Both **isolate `$SB_HOME` and `$SB_STATE`** and seed the home from `tools.example.toml`. This is not
tidiness. The first canvas capture was taken against the real home and came back with the operator's
own saved tools drawn down the left — a private checkout's job names, in a picture bound for a public
README. It is the obligation `tests/conftest.py` states for the suite, arriving somewhere no test can
look: *inside a PNG*. Both also copy `sample/` to a neutral temporary directory rather than reading it
in place, because the path is drawn in a window title and the path to a checkout names whoever's home
it sits in.

`render-canvas.mjs` drives a real `sb ui` over the Chrome DevTools Protocol, using the global
`WebSocket` that node 22 ships — so it costs no dependency, the same argument that made `node --test`
free. It types into the palette rather than screenshotting a blank canvas, because a surface whose
whole point is that you type at it is not photographed empty. It fails loudly if no palette renders or
no window opens: a blank page screenshots perfectly well, and a green run that wrote a picture of
nothing is this repo's favourite failure wearing a new hat.

**If the mark changes, re-run `render-mark.py`. Do not edit any PNG.**
