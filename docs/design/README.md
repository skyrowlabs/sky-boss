# Vendored design source

`skyrow-colors_and_type.css` is Skyrow Labs' design system token file, copied unmodified from the
design-system bundle. It is here so that `skyboss/theme.py`'s claim to have copied it verbatim is
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
.venv/bin/python docs/design/render-mark.py     # the mark, the hero, the ideas, the icon, the session
node docs/design/render-canvas.mjs              # the canvas
```

| File | Rendered from | Byte-stable? |
|---|---|---|
| `cli-header.png` | `ART` in `skyboss/banner.py` | yes |
| `hero.svg` | `ART`, and the palette in `skyboss/theme.py` | yes |
| `ideas.svg` | the four ideas, and the palette | yes |
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
here picks a colour; they all come from `skyboss/theme.py`, which is the rule `tests/test_theme.py`
enforces inside `skyboss/` and this directory keeps by hand.

### `hero.svg` and `ideas.svg`

The README's opening pictures, written as **SVG** rather than painted, so they stay crisp at any
width and can move. The hero is `ART` as rects at 8px a cell, plus a byline, the tagline and a
roll-call drawn as a canvas window; its motion is SMIL, which GitHub plays inside an `<img>` — the
warning light blinks, the `G` glass flickers in three panes, and a radar ring leaves the light and
lights each roll-call row as it passes. **The roll-call rows are an illustration**, named for nobody's
real project, and the alt text says so. `ideas.svg` is the four ideas as cards; its alt text carries
every sentence, because an image of a sentence is neither searchable nor read aloud.

They replaced `readme-banner.png`, a pty capture of `sb --help`. That went stale every time a command
was added and opened the README on a page of reference text; see [[header]] round 4.

### Neither render carries a version

`skyboss/banner.py` prints the real `git describe`, because a header stating a version it is not is
worse than one with none. `cli-header.png` drops that segment and the hero never had one, for two reasons that happen to agree. A
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
