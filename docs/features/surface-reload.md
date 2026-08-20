---
slug: surface-reload
title: Editing tb while tb is open
status: draft
created: 2026-08-20
updated: 2026-08-20
agent_value: 2
key_files: []
---

# Editing tb while tb is open

## Why

The surface is developed with the surface open. That is not an accident of habit — it is the
only way to work on it, because most of what [[surface-panes]] decided is about proportion,
density and colour, and none of those can be judged from a test. The loop is: change a number,
look, change it again.

Today every one of those loops costs a full restart. `Ctrl+C`, `tb tui`, and then re-navigate to
whatever state showed the thing being tuned. It is a second or two of wall clock and a much
larger amount of lost place.

Worse, the cost is not uniform, and the unevenness is the actual complaint. Three kinds of edit
behave three different ways and nothing announces which is which:

- **A job definition** in `$TB_HOME/jobs/` is picked up within a second, because
  `refresh_launch` calls `load_jobs()` on every tick (`cli/tui/app.py:500`).
- **A watch definition** is not picked up at all. `load_watches()` runs once, in `__init__`
  (`cli/tui/app.py:410`). The surface will show you a stale watch roster indefinitely and never
  hint that it is doing so.
- **A stylesheet change** cannot be picked up, because there is no stylesheet — `CSS` is an
  f-string class attribute (`cli/tui/app.py:261`), interpolated once at import.

The watch asymmetry is the one that has actually cost time: two YAML files in the same directory,
edited the same way, and one of them silently does nothing until you happen to restart.

## Shape

**Drive Textual's own reload machinery; do not build a reloader.** Textual already watches
`CSS_PATH` files in dev mode and re-parses them on save. The reason that does nothing here is
that the stylesheet is inline, so there is no file to watch. Give it one.

**The palette must not follow the CSS out of `theme.py`.** The current f-string exists to keep
the `$tb-*` tokens defined in exactly one place, and moving the stylesheet to a file naively
would put nine hexes into it. Textual has the right hook: override `App.get_css_variables()` to
return the tokens, and the `.tcss` file names colours only as `$tb-accent` and friends.

That is strictly *stronger* than what is there now.
`test_no_module_outside_the_palette_names_a_colour` globs `cli/**/*.py`, so a `.tcss` file full
of raw hexes would pass it silently. The test gets extended to cover `*.tcss` in the same change,
which is the whole reason to do this rather than paste hexes into a stylesheet and move on.

**Watches reload on a mtime check, not on every tick.** `load_watches()` parses YAML and stats a
directory; doing that once a second forever to catch an edit made twice a week is the wrong
trade. Stat the watch directory, compare against the last-seen mtime, reload only on change.
Jobs stay as they are — already correct, and already cheap enough that nobody noticed.

**Python is not reloadable and the doc says so out loud.** This is the part worth writing down,
because it looks like it should be easy and it is not:

- Widget classes are already instantiated. `importlib.reload` produces a new class object; the
  live widget tree still holds the old one.
- `set_interval(TICK_SECONDS, self.tick)` captured a bound method at mount. Reload does not
  rebind it.
- `cli/tui/app.py` takes module-level bindings at import — `LANES`, `load_jobs`, `TUI_THEME`,
  every style constant. Reload leaves all of them stale, and stale silently.
- `cli/output.py` owns the thread-local consoles that `capture()` swaps mid-dispatch. Reloading
  it while a worker thread is inside a capture breaks the exact invariant the thread-local design
  exists to hold.

There is a tempting seam — `dispatch()` already takes `root=` for the tests, so a reloaded Click
tree could be handed in without touching the surface. It is still wrong. The Click group
registers its commands at decoration time, so `cli/__init__.py` would have to be reloaded last,
and the surface would then be running a fresh command tree against a widget tree built from stale
imports. `_invoke`'s catch-all would keep that from crashing, which is worse than crashing: wrong
output that looks right.

**Does not do:**

- **No Python hot reload**, by any mechanism — not `importlib.reload`, not a re-exec, not a
  process supervisor that restarts on save. Restart is `Ctrl+D` and `tb tui`, history persists to
  `~/.local/state/tb/tui-history`, and the surface reads all its live state fresh on the next
  tick. There is no session to lose, which is exactly why the cheap answer is good enough.
- **No `--dev` flag on `tb tui`.** Dev mode is `textual run --dev cli.tui.app:TackleBox`, which
  already exists and is already documented by Textual. Wrapping it would be the passthrough
  CLAUDE.md forbids.
- **No config file for the surface.** Pane widths still are not persisted; that was decided in
  [[surface-panes]] and this does not reopen it.
- **Does not touch the freeze.** Losing the ability to exit after an edit is a separate defect
  with a separate mechanism — see [[surface-stall]]. It is not fixed by reloading anything.

## Phases

### Phase 1 — Stylesheet to a file

- [ ] Move the `CSS` body from `cli/tui/app.py` to `cli/tui/tb.tcss`; set `CSS_PATH = "tb.tcss"`
- [ ] Override `get_css_variables()` to return the `$tb-*` tokens from `cli/theme.py`
- [ ] Extend `test_no_module_outside_the_palette_names_a_colour` to glob `*.tcss`
- [ ] Add a test that every `$tb-*` token the stylesheet references is actually defined —
      an undefined Textual CSS variable is a parse-time failure, and it should fail in the
      suite rather than on launch
- [ ] Confirm `textual run --dev cli.tui.app:TackleBox` live-reloads a colour change

### Phase 2 — Watches reload

- [ ] Move the `load_watches()` call out of `__init__` into a `refresh_watch_defs()` guarded by
      the watch directory's mtime
- [ ] Preserve the injected-`watches` test seam — if watches were passed in, never reload
- [ ] Keep `self.watched` results across a reload for watches whose name and command are
      unchanged, so an edit to one watch does not blank the whole rail
- [ ] Test: a watch file appearing after mount is picked up; an injected roster is not

### Phase 3 — Write down what does not reload

- [ ] A short section in `docs/features/done/tui.md`, or a comment at the top of `app.py`,
      recording that Python edits need a restart and why the seam that looks available is not
- [ ] Mention the `textual run --dev` invocation in `README.md` where the surface is described

## Notes

Filled in during implementation.
