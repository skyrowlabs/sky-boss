---
slug: surface-design
title: Skyrow palette and the REPL region
status: complete
created: 2026-08-19
updated: 2026-08-19
agent_value: 2
key_files:
  - cli/theme.py
  - cli/output.py
  - cli/__init__.py
  - cli/tui/app.py
---

# Skyrow palette and the REPL region

## Why

Two unrelated-looking problems with one cause: the surface was built to work, not to be looked at
for an hour at a time.

**There are three palettes in this repo and none of them is jeston's.** `cli/output.py` defines a
Tailwind-ish set (violet `#a78bfa`, sky `#38bdf8`), `cli/__init__.py` repeats six of those hexes
by hand in `HELP_CONFIG` so `--help` matches, and the TUI's CSS invents a third for its
chrome. They agree today because they were written the same afternoon. Nothing keeps them in
step, and `jam.sense` has already paid this bill — its brand assets used `#38bcf7` while the app
used `--primary`, and the fix was to *derive* everything from one token file.

skyrow.labs has a design system. jam.sense ships it as a single base theme with the CSS tokens as
the source of truth. tb should look like it belongs to the same shop.

**The transcript-with-a-footer layout wastes the part you actually watch.** Input at the bottom
means the thing you type and the thing you are waiting on sit at opposite ends of the screen. The
status strip is one line, so lanes, the running job and recent history compete for it and mostly
lose. Meanwhile the output pane — which is scrollback, already-happened, read-once — gets every
row that is left.

## Shape

**One palette, `cli/theme.py`, approximating skyrow's tokens. Every consumer derives from it.**

Rich's `Theme`, rich-click's `HELP_CONFIG`, and the TUI's CSS all read the same constants. The
hand-copied hexes in `cli/__init__.py` go away. This inverts the current arrangement, where
`output.py` claimed to own the palette while `__init__.py` quietly kept a copy.

The mapping is an approximation and says so. Two deliberate departures from a literal port:

- **Shared styles use tokens that survive an unknown background.** The CLI runs in whatever
  terminal you happen to be in; the TUI controls its own dark surface. So `tb.accent` is
  `--primary` `#0091d4` (legible on white *and* on navy) rather than the brighter `--accent`
  `#4aabff`, which the TUI is free to use for chrome because it knows what is behind it.
- **Skyrow is dark-first and tb is not, entirely.** Adopting it costs some light-terminal
  legibility. The mid-tones keep it; the bright blues are the ones that suffer, which is why they
  are confined to the TUI.

### The REPL region

Ten rows, pinned to the top, in reading order — you type at the top and the answer builds
downward.

```
┌────────────────────────────────────────────────┐
│ tb ▸ run doctor                                │  1  input
│ drift  tools  unpushed                         │  2  completions
│                                                │  3  (argument completions, later)
│ · read-only                                    │  4  lanes, one row each
│ ● committing   run asset-refresh               │  5
│ ▰▰▰▰▰▱▱▱▱▱  run doctor  4.1s / ~7s             │  6  progress
│ 12:04  doctor         ok       2.1s            │  7  updates
│ 12:01  asset-drift    partial  0.4s            │  8
│ 09:00  unpushed-audit ok       11.2s           │  9
└────────────────────────────────────────────────┘  10 border
  output fills everything below
```

**The progress bar is real, not decoration.** The ledger records `duration_s` for every run, so
for `tb run <job>` the expected duration is the median of that job's past runs and the bar is
proportional to something true. With no history there is nothing to be proportional to, and it
falls back to a spinner rather than inventing a denominator. Overrunning the estimate is shown as
overrun, not as a bar stuck at 100%.

**Completions move out of the output pane.** Today Tab dumps candidates into the transcript,
which mixes chrome into the record of what was run. They belong in the region, above the output.

**Does not do:**

- **No second theme, and no theme switching.** One base palette, the way jam.sense settled it.
  A `--no-color` need is already served by Rich honouring `NO_COLOR`.
- **No token sync tooling.** jam.sense generates its brand assets from its tokens and audits for
  drift because it has a web app and CI. Here the palette is thirty constants in one file; a
  generator would be more machinery than the thing it generates. Copied by hand, with the source
  named in the module docstring.
- **The region is not resizable and its ten rows are not configurable.** Fixed until something
  actually annoys.
- **`tb.*` style names do not change.** The palette behind them does. Command modules that reach
  for `tb.ok` keep working, and nothing outside `cli/theme.py` learns a hex.

## Phases

### Phase 1 — one palette

- [x] `cli/theme.py` — skyrow tokens as named constants, with the source path recorded
- [x] `cli/output.py` builds its Rich `Theme` from them; the palette comment points at the new home
- [x] `cli/__init__.py`'s `HELP_CONFIG` derives from them instead of repeating six hexes
- [x] Test: no hex literal outside `cli/theme.py`, so a fourth palette cannot start

### Phase 2 — the REPL region

- [x] Input to the top, region of exactly ten rows, output below
- [x] Lanes get a row each; the one-line status strip goes away
- [x] Completions render in the region, not in the output pane
- [x] Updates: the last few ledger entries, refreshed on the existing tick
- [x] TUI CSS derives from `cli/theme.py`

### Phase 3 — progress

- [x] Expected duration from the median of a job's past runs in the ledger
- [x] Proportional bar when an estimate exists, spinner when it does not, overrun shown as overrun
- [x] Test: the estimate is absent for an unknown job and present after runs are recorded

## Notes

**Shipped 2026-08-19.** All three phases.

**Phase 2.** The ten rows are computed, not written down: everything but the updates feed has a
fixed claim and the feed takes the remainder, so adding a third lane costs the feed a row instead
of silently clipping one. A test asserts the parts still sum to ten.

The echo prefix became a shared constant. Two tests asserted the literal `"> "`, and changing the
glyph broke them — which is the right failure, but the fix is for the tests to read the prefix
from the module rather than to restate it.

**Phase 3.** `expected_seconds` takes an injectable entry list, because otherwise testing the
median meant writing a real ledger. It excludes `skipped` and `refused`: both record a near-zero
duration since nothing ran, and left in, a couple of lane collisions would make every job look
instant — the estimate would be worst exactly when lanes are contended, which is when you are
most likely to be watching.

**Phase 1.** Textual CSS takes its own `$name: value;` variable definitions, so the palette
crosses into the stylesheet as a generated `$tb-*` preamble concatenated onto the plain CSS. The
obvious alternative — an f-string over the whole sheet — would have meant doubling every brace in
a stylesheet, and `%`-formatting is worse still because CSS uses bare `%` for percentages.

`tb.accent` moved from violet to `--primary` `#0091d4`, which is a real change to CLI output and
not only to the surface. That is the intent: one theme means the command line gets it too.

**Bottom-anchored, 2026-08-19 (after completion).** The region moved from the top of the screen
to the bottom, and a one-row `TACKLEBOX` banner took the top row. This reverses the reasoning
recorded above — the original claim was that typing at the top put the thing you are waiting on
next to the thing you typed. In use it lost to the older convention: a terminal's input is on the
last row, and the transcript growing *toward* the prompt rather than away from it is what every
shell has trained the eye to expect.

Inside the region the order reversed with it, so it now runs ambient → immediate top to bottom:
updates feed, lanes, progress, completions, input. Completions sit directly above the line they
complete, which is the one adjacency that has to hold. Their two rows are
`content-align-vertical: bottom` for the same reason — top-aligned, a single line of candidates
floated a row clear of the input.

The row budget is unchanged at ten; the banner is deliberately outside it, since it is chrome and
nothing reads it. The layout is asserted on widget geometry rather than compose order — child
order would still pass if the CSS put the region somewhere else, and position is the whole
promise. See `test_the_banner_is_the_top_row_and_the_region_the_bottom` in
`tests/test_tui_app.py`; an earlier test of the same property named the input as the screen's
last row, which stopped being true — see [[surface-panes]].

**Corrected 2026-08-19 — the palette was approximated from the wrong file.** This doc records
deriving the theme from jam.sense's `web-app/static/css/tokens/`. Those are *jam.sense's app
tokens*. Skyrow Labs has an actual design system with its own `colors_and_type.css`, and every
hue here was wrong against it: background `#0a1929` vs `#05090e`, brand `#4aabff` vs `#38bdf8`,
success `#4caf50` vs `#4ade80`. It also assigns an accent per project — jam.sense sky blue,
breeze.brain wind green, mind.head signal yellow — which the approximation collapsed into one.

The irony is on the record: the commit that shipped this cited jam.sense's brand assets using
`#38bcf7` while its app used `--primary` as precisely the drift to avoid, and then shipped the
app side as the brand.

**What survived was the reasoning, not the values.** This doc argued that shared roles must pick
colours that survive an unknown terminal background, since the CLI renders into whoever's
terminal while the TUI owns its own. That was right, and measurement makes it unarguable: the
system's tokens score 2.14:1 (brand) and 1.44:1 (warn) against white. So `theme.py` now carries
the system verbatim *and* a set of CLI derivations — the smallest darkening of each token that
clears 3.5:1 on both backgrounds — with a test measuring the floor. See [[surface-panes]] for the
surfaces those two renderings feed.

The system file is vendored at `docs/design/` so "copied verbatim" is a test rather than a claim.
