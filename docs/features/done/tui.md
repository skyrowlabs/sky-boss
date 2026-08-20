---
slug: tui
title: tb tui — a persistent surface over the envelope
status: complete
created: 2026-08-19
updated: 2026-08-20
agent_value: 3
key_files:
  - cli/output.py            # capture(); the module still owns every byte
  - cli/tui/dispatch.py      # drives the real Click tree
  - cli/tui/live.py          # /proc/locks and the ledger tail
  - cli/tui/complete.py      # candidates read off the tree and the registries
  - cli/tui/app.py           # the surface
  - cli/tui/history.py
  - cli/__init__.py          # tb tui registered as a surface
  - tests/test_taxonomy.py   # the write-invariant ratchet, extended to surfaces
  - tests/test_tui_dispatch.py
  - tests/test_tui_live.py
  - tests/test_tui_complete.py
  - tests/test_tui_app.py
  - cli/tui/watchdog.py      # round 2: detects a blocked loop from off it
  - cli/tui/launch.py        # round 2: points at the stall dump when there is one
  - tests/test_tui_watchdog.py
  - cli/tui/tb.tcss          # round 3: the stylesheet, so --dev can reload it
  - cli/watch.py             # round 3: signature(), the guard on re-parsing
  - tests/test_theme.py      # round 3: the no-hex ratchet extended to *.tcss
---

# tb tui — a persistent surface over the envelope

## Why

The dominant use of `tb` is a two-beat loop: **trigger something, then read what it did.**
The one-shot CLI serves the first beat well and the second one badly.

```
$ tb check                 # a rollup you want to keep on screen while you act on it
$ tb auto status           # ...gone, and now you have a run_id
$ tb auto log <run_id>     # ...gone, and the rollup that sent you here is long scrolled off
```

Three concrete failures, in increasing order of how much they matter.

**Reports scroll away.** `tb check` produces exactly the kind of output you want to keep visible
while you work through it, and the next command buries it — interleaved, in a scrollback shared
with every unrelated thing the shell has printed today.

**Reading a log is always two trips.** `tb auto status` hands you a `run_id`; the single most
common next action is `tb auto log <run_id>`. That is a copy-paste between two commands for the
most predictable follow-up in the entire tool.

**There is no way to see what is running right now, and there structurally cannot be.** This is
the real one. A one-shot command samples state and exits. `tb auto status` reads the ledger,
which is a record of runs that have *finished* — `run_job` appends its entry after the process
exits. Lanes held at this instant, a job currently in flight, a lock left stale by a killed run:
none of these are observable except by happening to run a command inside the window.

That last failure indicts the job layer's headline feature. Lanes exist so that a job queues or
refuses rather than overlapping, and CLAUDE.md calls that "the thing cron comments cannot do."
Today you can only ever learn it happened afterwards, by reading a `skipped` outcome in the
ledger. **The mechanism is invisible while it is doing its job.**

There is a fourth reason that is about where this repo is going rather than where it is. The jobs
feature exists so that long work runs "without a terminal babysitting it" — and agentic runs are
just jobs with a Claude runner. A persistent surface is the natural place to watch that work
without babysitting it, which is the half of the problem the ledger does not solve.

## Shape

**The TUI is a third consumer of the `Result` envelope, not a second CLI.**

That sentence is the entire design, and it is only available because `docs/features/
output-contract.md` already shipped: commands return data and never print, and `cli/output.py`
owns every byte that reaches the terminal. The output contract was written for a human, a rollup,
and MCP. A TUI is the fourth reader of the same envelope and costs almost nothing extra.

### Dispatch drives the real Click tree

The TUI does not maintain a command table. It hands the typed line to Click:

```python
cli.main(args=shlex.split(line), prog_name="tb", standalone_mode=False, obj={})
```

`standalone_mode=False` makes Click **return** the exit code instead of calling `sys.exit`, and
raise `UsageError` instead of printing and dying. Verified against the current tree: `check`
returns 3, `auto list` returns 0, `nope` raises `NoSuchCommand`, `info --bogus` raises
`NoSuchOption`.

This is the same argument the taxonomy made about the MCP allowlist. A hand-maintained mirror of
the command surface is a list somebody forgets to update; driving the real tree makes it a
property. **A command added next year appears in the TUI with no TUI change, with its real help,
its real usage errors, and its real exit code.**

### Capture stays inside output.py

`cli/output.py` is the module that claims to own every byte. It keeps that claim — capture is a
context manager there, not a hack in the TUI:

```python
with capture(width=...) as buf:      # swaps console/err_console for Console(file=buf,
    rc = dispatch(line)              # force_terminal=True), plus redirect_stdout/stderr
text = buf.ansi()                    # as a backstop
```

The `redirect_stdout` backstop is load-bearing, not belt-and-braces paranoia. rich-click renders
`--help` through **its own** console, not `cli.output.console`: with only the module swap, help
output escapes to the real stdout and corrupts the screen. Verified — 1,863 bytes, captured only
because of the redirect. Any stray `print` a future command sneaks in is caught by the same net.

Capture yields ANSI text, and the body pane writes it with `Text.from_ansi`. The alternative —
refactoring `_render_*` to return renderables instead of printing — touches all 458 lines of
`output.py` and buys nothing visible. Revisit only if a widget needs to *interact* with a table
(sort it, select a row), which is not what this feature is.

### Textual, because of Rich

Same author as Rich, so `output.py`'s `Table`, `Padding` and `Text` render inside a widget
unchanged. Every other base — prompt_toolkit, urwid, blessed — means reimplementing the render
layer and maintaining two of them forever. textual 8.2.8 is a `py3-none-any` wheel and installs
on 3.14.7 (checked, because CLAUDE.md warns that a dependency may lack wheels at this version).

### Layout

```
┌──────────────────────────────────────────────────┐
│ tb  workstation          lanes: committing ● held   │  status strip — polled
├──────────────────────────────────────────────────┤
│ > check                                          │
│ ● check  3 checks                                │  body — RichLog, the
│   ✓ drift                                        │  captured envelope,
│   ✗ tools   bws: BWS_ACCESS_TOKEN unset          │  verbatim
│   ✗ unpushed  4 problems                         │
├──────────────────────────────────────────────────┤
│ > _                                              │  input — stays live
└──────────────────────────────────────────────────┘
```

The status strip is the part that does not exist today and cannot be retrofitted onto a one-shot
command. It polls the lane locks and the ledger tail on a ~1s tick. Polling two small files is
not worth an inotify dependency.

Held-ness comes from `/proc/locks`, and this is the one part worth getting exactly right.
**Never from whether the lock file exists** — the file outlives the lock, so existence would
report every lane permanently busy after the first job ever ran. And **never by trying to take
the lock**: `lane_lock` is non-blocking, so a probe on a one-second tick would hold the lane for
an instant, and a `tb run` starting in that window would record `skipped`. A monitor must not be
able to cause the condition it monitors. Reading `/proc` cannot.

`/proc/locks` also names the holding pid, so the strip says *what* holds a lane, not merely that
something does. The label is capped at a few argv words: an ad-hoc run is
`tb run --lane L -- <anything>`, and "anything" is exactly where a token would appear.

### Every dispatch runs in a thread worker

Non-negotiable from the first commit. `check_unpushed` walks `~/src`; `check_tools`
shells out to several external CLIs; `tb run` blocks for the entire duration of a job. Running
any of them on the event loop freezes the UI on precisely the commands worth watching, and a TUI
that freezes is worse than the shell it replaced.

One dispatch in flight at a time, further input queued. Concurrency here buys nothing — two
simultaneous `tb run`s would contend for the same lane lock and one would report `skipped`, which
is a confusing way to discover you double-typed.

**This section was true and still insufficient — see Round 2.** The dispatch runs off the loop as
described. The *result* does not: it returns through `call_from_thread(self.finished, result)` and
`finished` writes the whole thing into the `RichLog` in one call, on the loop. For a large output
that write is the expensive half, and it was never on the thread at all. The rule as originally
written — "a dispatch never runs on the event loop" — turns out to name the wrong unit of work.
The rule that actually holds the surface open is **no single turn of the event loop may be
unbounded**, and rendering a result is a turn like any other.

### The write invariant survives

`tb run` remains the only door that writes. The TUI adds no new mutation path: it dispatches
strings through the same Click tree, so a job or task run from the TUI takes the same lane lock,
writes the same ledger entry, and produces the same log as one run from the shell.

The way that breaks is a future convenience — a button that calls `run_task` directly to skip
argv parsing. So it gets a test alongside the taxonomy ratchet: `cli/tui/` imports no mutating
symbol (`run_job`, `run_task`, `seed_inventory`, `refresh_inventory`, `rewrite_derived`) from
anywhere. The TUI's only verb is "dispatch this string."

### Naming

`tb tui`. CLAUDE.md already documents `tb mcp serve` as "the honest exception — a daemon, in none
of the four moods"; this is the second exception of exactly the same kind, a surface over the
envelope rather than a command in a mood. That sentence gets amended rather than the taxonomy.

**Not `tb shell`.** "Shell" implies passthrough, which the conventions forbid outright, and the
name would invite someone to type `git status` into it.

**Does not do:**

- **It is not a shell.** No arbitrary argv passthrough to the system. The input accepts `tb`
  command lines only, with the leading `tb` optional. Foreign argv has exactly one door —
  `tb run --lane L -- argv` — and it goes through the ledger like everything else.
- **No streaming of in-flight jobs in the shipped shell.** `run_job` captures with
  `subprocess.run` and writes the log after exit, so the body shows completed logs. Fixing that
  is Phase 5, deliberately last, because it changes CLI behaviour and should be judged there.
- **No editing.** Not a file browser, not a YAML editor for `jobs/`. `$EDITOR` exists.
- **No remote.** Runs on workstation against local state. Tailnet fan-out is `asset-remote`'s job.
- **No second rendering path.** If output looks wrong in the TUI, the fix goes in `output.py` and
  the CLI gets it too. No TUI-only formatting, ever — that is how the contract rots.
- **It does not become the default.** `tb <command>` stays a one-shot CLI. Scripts, systemd
  timers and MCP never touch this, and nothing in the CLI may start depending on it.
- **No config file, no theming, no mouse-first design.** Keybindings hard-coded until something
  actually annoys. The palette already lives in `THEME`.

## Phases

### Round 1 — build the surface (2026-08-19)

#### Phase 1 — capture and dispatch, headless

The whole risky part, and all of it testable without a terminal.

- [x] `capture()` context manager in `cli/output.py` — swaps `console`/`err_console` for
      `Console(file=buf, force_terminal=True)`, wraps `redirect_stdout`/`redirect_stderr`,
      restores both on exit including on exception
- [x] `cli/tui/dispatch.py` — `dispatch(line) -> Dispatch(text, exit_code)`; `shlex.split`,
      strip an optional leading `tb`, drive `cli.main(standalone_mode=False)`
- [x] Catch `UsageError`, `Exit` and `Abort` into the returned text rather than letting them
      escape; an unknown command is a line in the body, never a crash
- [x] Tests: exit codes survive (`check` → 3, `auto list` → 0); usage errors are captured not
      raised; `--help` leaks nothing to the real stdout; a `--json` line leaves parseable JSON in
      the buffer; capture restores the globals after an exception

#### Phase 2 — the app shell

- [x] `textual` added to `requirements.txt`
- [x] `cli/tui/app.py` — status strip, `RichLog` body, `Input` footer
- [x] Every dispatch through `run_worker(thread=True)`; one in flight, further input queued
- [x] Echo the typed line into the body before running, so the pane reads as a transcript
- [x] Input history with ↑/↓, persisted to `~/.local/state/tb/tui-history` — state dir, not the
      repo, same reasoning as the ledger
- [x] Ctrl+L clears the body, Ctrl+D quits, Ctrl+C cancels the current input line
- [x] `tb tui` registered in `cli/__init__.py`
- [x] Test: `cli/tui/` imports no mutating symbol

#### Phase 3 — live state, the reason this exists

- [x] Status strip polls lane locks and the ledger tail on a ~1s tick
- [x] A held lane names what holds it, from `/proc/locks`
- [x] ~~A held lane with no run in flight renders as a stale lock~~ — **not built: the state
      cannot occur.** `flock` is released by the kernel when the holder dies (verified under
      `SIGKILL`), so "held" and "a live process holds it" are the same fact. See Notes.
- [x] Last ledger entry with its outcome, colour-mapped through the existing `THEME`
- [x] A shortcut opens the last run's log in the body without retyping the `run_id` — the
      two-trip problem from **Why**, closed

#### Phase 4 — completion

- [x] Tab completion from Click's own tree, so it cannot drift from the CLI
- [x] Job and task names complete from the same registries `tb run` uses

#### Phase 5 — streaming — **deferred 2026-08-19, still not built**

Still the right call after building the rest, and left open rather than cancelled. Judge it on
the CLI's merits. It changes `run_job` for every caller, and the TUI is not
sufficient reason on its own.

- [ ] `run_job` → `Popen` with incremental write to `log_path`
- [ ] `tb auto log --follow`
- [ ] Body pane follows a running job

### Round 2 — stop the surface freezing (2026-08-20)

The surface can be locked up by a single command, and when it locks up there is no way out —
`^D` does nothing, `^C` does nothing, and the screen stays drawn showing stale state. It looks
like a hang with no cause, which is why it went unexplained: the surface is still *painted*, so
nothing suggests the event loop is the thing that stopped.

The reported trigger was "after a code change", and that is a coincidence of workflow rather than
a mechanism. What follows a code change is a command run to see whether it worked, and after a bad
edit that command returns an enormous amount of text — a repeated traceback, a runaway warning
loop, a log tail. **The size of the output is the trigger. The code change is what tends to
produce it.**

Measured here, one `RichLog.write()` of a single large `Text`:

| lines in one write | loop blocked |
|---|---|
| 20,000 | 0.42 s |
| 40,000 | 1.95 s |
| 80,000 | 7.69 s |
| 120,000 | 17.47 s |

Superlinear, so it does not degrade gently. Extrapolated, 300,000 lines is about two minutes of
frozen surface and a million is around twenty — indistinguishable from a permanent hang, and
reachable from one `tb auto log` on a chatty job.

Two things ruled out by measurement rather than by reading:

- **Not garbage collection.** The same write with `gc.disable()` costs 7.33 s against 7.62 s.
- **Not accumulation.** A transcript grown to 20,000 lines by 25 successive writes never blocks
  for more than 0.038 s. The cost is the size of a *single* write, not the size of the log.
  `RichLog` is nonetheless unbounded (`max_lines` unset), which is a leak worth closing here even
  though it is not the freeze.

**The fix is to bound the write and chunk what remains.** (The spec said "chunk and yield
between chunks"; the yield turned out to be unnecessary once the ceiling was in — see Notes.) `write_body` is already the single
path to the transcript, so there is exactly one site. This is faster as well as more responsive,
which is the part worth recording — same 80,000 lines:

| | total | worst single block |
|---|---|---|
| one write | 7.62 s | 7.62 s |
| 1,000-line chunks | 1.48 s | 0.337 s |

Five times cheaper in total and twenty-two times better at the thing that matters. Chunking is not
a trade; the one-shot path was simply the bad one. This is also the first half of Phase 5's
streaming, arriving for an unrelated reason.

There is a **second, independent defect** underneath, which the binding comment at
`cli/tui/app.py:373` already half-knows ("^Q is the unconditional way out, and the only one that
works if a thread wedges"). `@work(thread=True)` runs on asyncio's default `ThreadPoolExecutor`.
`App.exit()` calls `workers.cancel_all()`, but cancelling a *thread* worker only cancels the
awaiting task — the thread runs on. `asyncio.Runner.close()` then joins it with
`asyncio.constants.THREAD_JOIN_TIMEOUT`, **300 seconds** on Python 3.14. A genuinely wedged
dispatch costs five minutes of dead terminal after the UI has gone. Fixing the freeze does not fix
this and `^Q` does not either.

- [x] Bound `write_body`: truncate on the plain string, then write in ~1,000-line slices
- [x] Truncate a single dispatch's transcript output at a ceiling (10,000 lines), with a marker
      naming the dropped line count and pointing at `inspect` / `auto log`
- [x] Set `max_lines` on the `RichLog`
- [x] Leave without joining a wedged dispatch worker — `run()` owns its loop and exits through
      `os._exit` when one is still alive. No grace period and no second `^Q` needed; see Notes
- [x] Test: a parked worker is detected, a daemon thread is not, the loop is ours, and a wedged
      worker does not delay leaving
- [x] Daemon watchdog thread, heartbeated by a loop timer, dumping all thread stacks to
      `$STATE_DIR/tui-stall.txt` on a stall past threshold
- [x] The launch screen points at the dump when one exists, so it gets found
- [x] Test: a 200,000-line dispatch result never blocks the loop past ~0.3 s, asserted with a
      heartbeat timer in `run_test()` rather than by eye
- [x] Test: the truncation marker appears and `last_envelopes` still holds the full envelope
- [x] Test: ordinary output is neither truncated nor reordered by chunking
- [x] Test: the transcript is bounded, and one result always fits inside the scrollback
- [x] Test: the stall dump is written when the loop is deliberately blocked, reported once per
      stall rather than once per poll, and survives an unwritable state directory

**Does not do.** Rendering does not go back on a thread — Textual widgets are not thread-safe and
`call_from_thread` is the right boundary; the fix is to make the on-loop work small and
interruptible, not to move it. Truncation belongs to the surface, never to the command: a
command's envelope is the contract ([[output-contract]]) and `--json` keeps emitting all of it.
No pager and no scrollback search — reading a large log is `tb auto log`'s job. No timeouts on
internal tasks: `cli/run.py` argues deliberately that an internal task must not be interrupted
mid-write, and that still holds; this makes a wedged task survivable, not impossible.

### Round 3 — editing tb while tb is open (2026-08-20)

The surface is developed with the surface open, because most of what Round 1 and
[[surface-panes]] decided is about proportion, density and colour, and none of that can be judged
from a test. The loop is: change a number, look, change it again. Every one of those loops costs a
full restart today.

The cost is not uniform, and the unevenness is the actual complaint. Three kinds of edit behave
three different ways and nothing announces which is which:

- **A job definition** is picked up within a second — `refresh_launch` calls `load_jobs()` every
  tick.
- **A watch definition** is never picked up. `load_watches()` runs once, in `__init__`. The rail
  shows a stale roster indefinitely and gives no hint that it is doing so.
- **A stylesheet change** cannot be picked up, because there is no stylesheet — `CSS` is an
  f-string class attribute, interpolated once at import.

**Drive Textual's own reload machinery; do not build a reloader.** Textual already watches
`CSS_PATH` files in dev mode and re-parses on save. The reason that does nothing here is that the
stylesheet is inline. Give it a file.

**The palette must not follow the CSS out of `theme.py`.** Override `App.get_css_variables()` to
return the `$tb-*` tokens, so the `.tcss` names colours only as `$tb-accent` and friends. This is
strictly stronger than what is there now: `test_no_module_outside_the_palette_names_a_colour`
globs `cli/**/*.py`, so a `.tcss` full of raw hexes would pass it silently. Extending that test to
`*.tcss` in the same change is most of the reason to do this properly rather than paste hexes into
a stylesheet.

**Python is not reloadable, and the doc says so out loud** — this is the part that looks easy and
is not. Widget classes are already instantiated, so `importlib.reload` leaves the live tree
holding the old class. `set_interval` captured a bound method at mount. `app.py` takes
module-level bindings at import (`LANES`, `load_jobs`, `TUI_THEME`, every style constant) and
reload leaves them stale, silently. `cli/output.py` owns the thread-local consoles `capture()`
swaps mid-dispatch, so reloading it while a worker is inside a capture breaks the invariant the
thread-local design exists to hold.

There is a tempting seam — `dispatch()` already takes `root=` for the tests, so a reloaded Click
tree could be handed in without touching the surface. It is still wrong: the Click group registers
commands at decoration time, so `cli/__init__.py` would reload last and the surface would run a
fresh command tree against a widget tree built from stale imports. `_invoke`'s catch-all would
keep that from crashing, which is worse than crashing — wrong output that looks right.

- [x] Move the `CSS` body to `cli/tui/tb.tcss`; set `CSS_PATH = "tb.tcss"`
- [x] Override `get_css_variables()` to return the `$tb-*` tokens from `cli/theme.py`
- [x] Extend `test_no_module_outside_the_palette_names_a_colour` to glob `*.tcss`
- [x] Test that every `$tb-*` token the stylesheet references is defined — an undefined Textual
      CSS variable fails at parse time, and it should fail in the suite rather than on launch
- [x] Test that the stylesheet defines no `$tb-*` of its own, so a token has one source
- [x] Confirm `textual run --dev cli.tui.app:TackleBox` live-reloads a colour change
- [x] Add `textual-dev` to `requirements-dev.txt` — the documented command needs it
- [x] Move `load_watches()` out of `__init__` into a `refresh_watch_defs()` guarded by a change
      signature — not every tick, which is the wrong trade for an edit made twice a week
- [x] Preserve the injected-`watches` test seam: if watches were passed in, never reload
- [x] Keep `self.watched` results across a reload for watches whose name and command are
      unchanged, so editing one watch does not blank the rail
- [x] Test: a watch appearing, being edited in place, or being removed is picked up; an
      injected roster is not; and an idle tick re-parses nothing
- [x] Record in `README.md` that Python edits need a restart, and the `textual run --dev` line

**Does not do.** No Python hot reload by any mechanism — not `importlib.reload`, not a re-exec,
not a supervisor that restarts on save. Restart is `^D` and `tb tui`; history persists to
`~/.local/state/tb/tui-history` and every live pane re-reads on the next tick, so there is no
session to lose. That is exactly why the cheap answer is good enough. No `--dev` flag on `tb tui`
— dev mode is `textual run --dev cli.tui.app:TackleBox`, and wrapping it would be the passthrough
CLAUDE.md forbids. No config file for the surface: pane widths still are not persisted, and
[[surface-panes]] decided that.

### Round 4 — newest first, prompt on top (2026-08-20)

**This reverses Round 1's layout decision, and the original argument is worth keeping visible.**
Round 1 put the REPL region at the foot because "that is where a terminal puts its prompt and the
transcript grows toward it." That is a true description of a terminal, and it is the wrong model
for this surface. A terminal's prompt is at the bottom because its transcript is *append-only
scrollback you have already read*. Here the transcript is a stack of results you are working
through, and the thing you most want to look at is the one that just arrived. Putting the newest
result at the bottom means every dispatch pushes it under the prompt and you read downward toward
the thing you are typing into.

Inverted: **the region is at the top and the newest result sits directly beneath it.** The result
you just asked for is adjacent to the line you asked with, and nothing moves out from under you
while you read.

Inside the region nothing changes. The input stays at the *top* of it with candidates below and
help to the right, because Round 1's reason for that still holds — everything else in the region
describes the input line and hangs off it.

**Within a turn, content still reads top-to-bottom.** Only the *turns* are stacked newest-first.
Reversing the lines inside a result would turn every table upside down, which is not what "newest
first" means to anyone.

```
  banner
  ▸ check drift           ← the line you are typing
  candidates | help
──────────────────────────
  ▸ check drift           ← the turn that just finished
  <its output, read normally>

  ▸ auto status           ← the turn before it
  <its output>
```

**`RichLog` cannot do this.** It appends, and there is no prepend — the only way to get
newest-first out of it is to clear and rewrite the whole log on every turn, which is O(total) per
turn and would undo Round 2 by reintroducing exactly the unbounded on-loop render that froze the
surface. So the transcript becomes a `VerticalScroll` of **turn blocks**, each block a container
mounted at the top.

That makes the turn an explicit thing rather than an implicit one, and it exposes an ordering bug
that the flat transcript merely hid. `start()` echoes at the moment you press enter, but a line
typed while a dispatch is running is *queued* — so two echoes can happen before the first result
arrives. In a flat log that renders as echo, echo, output, output: already wrong, but readable. In
turn blocks the second turn would swallow the first turn's output. **So the queue carries the
block**, and a result is written into the block its own line opened.

Round 2's per-write truncation is unchanged and still does the bounding work. `max_lines` on the
`RichLog` is replaced by a cap on retained turns, which is the same idea in the unit this layout
actually has.

- [x] Move the REPL region above the transcript; `border-bottom` rather than `border-top`
- [x] Replace the `RichLog` with a `Transcript` container that mounts turn blocks newest-first
- [x] A turn block is opened by `start()`, carried on the queue, and written into by `finished()`
- [x] `write_body` with no turn open starts one, so the mount hint and `last log` still work
- [x] Cap retained turns; drop the oldest from the bottom
- [x] New content scrolls to the top, not the end
- [x] Give the app `transcript()` and `turns()` so tests stop reading widget internals
- [x] Test: turns stack newest-first and content within a turn does not
- [x] Test: a line queued behind a running dispatch gets its own block, in order
- [x] Test: the region sits above the transcript, and the rail still sits beside it
- [x] Test: Round 2's freeze guard still holds against the new widget

**Does not do.** No configuration switch between the two orders — [[surface-panes]] refused a
config file for the surface and this does not reopen it; the layout is a decision, not a
preference. Content within a turn is not reversed. The rail is untouched: it is live state, not
transcript, and has no order to invert.

## Notes

**Round 4 — inverting the surface (2026-08-20).** The design predicted one ordering bug and the
implementation found it was real, plus a second nobody predicted.

*The predicted one.* `start()` echoes when you press enter, but a line typed while a dispatch is
running is queued — so two blocks can be open before the first result lands. The round said "the
queue carries the block", and it does. What the design got wrong was assuming that was enough:
the first implementation also assigned the new block to `self.turn`, which is the block the
*running* dispatch writes into. So typing a second line while the first was still running
redirected the first one's output into the second one's block. The test caught it on the first
run. `start()` now opens a block without claiming `self.turn`; only `pump()` claims it, because
only `pump()` knows which line actually started.

*The unpredicted one.* The keys hint at mount used to be written straight to the `RichLog`,
bypassing `write_body` — and therefore bypassing `written = True`. Routing it through the single
door made the surface consider itself non-idle from the first frame, so the launch screen never
appeared. `idle` is "the transcript is empty", and chrome the surface printed to itself does not
count; `write_body` takes `marks_written` for exactly that one caller. Worth knowing that the old
bypass was load-bearing rather than sloppy.

`Static` has no public accessor for the renderable it was given — `.renderable` does not exist in
Textual 8. Rather than reach into `_Static__content`, each line keeps its source `Text` on the
widget, which is what `transcript()` and `turns()` read. That is the same coupling those
accessors were added to remove, so it would have been an odd place to reintroduce it.

Seventeen tests failed on the first run of the new layout, and almost all of them for the same
reason: they read `RichLog.lines` and unpacked Rich segments by hand. They were coupled to the
widget rather than to the behaviour, so every one broke for a reason a reader of the test would
not recognise. They go through `transcript()` now.

**Round 3 — reload (2026-08-20).** The stylesheet move made an existing test load-bearing that
had been merely tidy. `test_no_module_outside_the_palette_names_a_colour` globs `cli/**/*.py`;
the moment the stylesheet became a `.tcss`, the single most natural place in the repo to paste a
hex was outside the only test that looks for one. Extending the glob was not symmetry, it was the
reason the move was safe to make. All three palette guards were verified by breaking the thing
they describe and watching them fail.

`textual-dev` was not installed. The documented `textual run --dev` line would have been a
command that does not exist, so it is in `requirements-dev.txt` now.

**A directory mtime is not enough**, which is the one thing here worth not rediscovering. The
spec said "guarded by the watch directory's mtime", and a directory's mtime moves when a file is
added, removed or renamed — but **not** when an existing file's contents change. That is the
common case and precisely the one that had been broken: an edited definition would have gone on
being ignored, with the guard making it look deliberate. `signature()` carries each file's size
and mtime as well.

Results survive a reload for any watch whose command is unchanged. A reload is usually one file
being edited, and blanking the rail back to "not yet run" would throw away every other watch's
answer to pay for it. A changed command drops its result, because a different command is a
different question and the old answer is not an answer to it.

Verified through the real tick rather than only by unit test: a watch added while the surface is
open appears on the next tick, and twenty idle ticks re-parse nothing.

While in `cli/watch.py`, its module docstring still said definitions are "versioned in the repo".
They moved to `$TB_HOME` in [[operator-home]]; corrected.

**Round 2, phase 2 — leaving (2026-08-20).** The spec called for a grace period and a
double-`^Q`. Neither shipped, because both assumed the join was unavoidable and it is not:
`App.run()` takes a `loop` parameter. Owning the loop skips `asyncio.run`'s
`shutdown_default_executor`, and leaving through `os._exit` skips the atexit join that
`concurrent.futures` registers. There are *two* joins, and a grace period would have been a timer
racing the first of them. Measured out of process with a parked worker: 300 s to 0.24 s.

The hard exit is conditional on a live non-daemon thread rather than unconditional, which turned
out to matter for phase 3 — the watchdog is a thread, and a non-daemon one would have made every
ordinary exit take the hard path.

**Round 2, phase 3 — the watchdog (2026-08-20).** Detection has to be off-loop, which sounds
obvious written down and is worth stating anyway: an async task cannot report a blocked loop,
because the thing it would report is the reason it is not running. So a daemon thread watches a
number that a loop timer bumps.

The beat is a timer separate from `tick` rather than a line inside it. A tick slow enough to
matter is precisely the case that must still be recorded, and beating inside `tick` would mean
the beat stopped for the same reason the dump would never be written.

The dump is `faulthandler.dump_traceback(all_threads=True)`, which names the blocking frame
directly — verified end to end against a deliberately blocked loop, where it named the blocking
function by name. Against the original bug it would have pointed at `RichLog.write` in one read,
rather than a morning and four measurement harnesses.

Two things noticed here and deliberately not fixed here:

- **`STATE_DIR` is not redirected for the suite the way `TB_HOME` is.** `conftest.py` is emphatic
  that a test must never read the operator's home, and the same argument applies to state — but
  `STATE_DIR` is a bare `Path.home()` constant with no env override. This round dodged it by
  stubbing the app in the exit tests rather than letting `run()` build a real one. Adding a
  `TB_STATE` override is a change to what [[operator-home]] owns, so it belongs there.
- **`inspect` renders a whole envelope into a `Static` inside a modal**, which is a second
  unbounded on-loop render by the same argument that made `write_body` one. It has not bitten,
  because an envelope is structured data rather than a log tail, but it is the same shape of bug.

**Round 2 — the freeze (2026-08-20).** Diagnosed before any code changed; the measurement tables
above are the evidence for the design rather than a record of surprises. Three hypotheses were
wrong and each is worth not re-testing.

*Not the thread-join at exit.* Real, confirmed, and a genuine second bug — but it produces "screen
clears, shell never returns". The reported symptom was the surface still drawn, which is the loop,
not shutdown. The operator's answer to that one question is what made the diagnosis tractable;
without it the obvious suspect was the 300 s join, and it was the wrong suspect.

*Not `/proc` reads on the tick.* `lanes()` reads `/proc/locks` and `/proc/PID/cmdline` every second
on the loop, and `_describe` on a process in uninterruptible sleep genuinely can block. But it has
no relationship to output size and the measured numbers were nowhere near.

*Not `Text.from_ansi`.* It parses 2.7 MB in 0.099 s. The parse was never the cost; the render into
strips was. Reading `RichLog.write` does not reveal this — every step in it looks O(n), and the
quadratic term was never located. It did not need to be: the fix is not to hand it a giant
renderable, and chunking is measurably better on every axis.

The lasting correction is to the Shape section above. "A dispatch never runs on the event loop"
was the founding rule and it was too narrow — it names the *dispatch* as the unit, when the unit
is the *turn*. Rendering the result is a turn, and it was unbounded from the first commit.

**Phase 1.** Dispatch takes an injectable `root` group, which the spec did not call for. The
exit-code tests need commands with known outcomes, and the real ones walk `~/src` and
shell out to half a dozen CLIs — dispatching real `check` would have put a multi-second,
network-adjacent test in a suite that is 3s and neither. The surface always passes the real tree.

Usage errors and crashes render through `output.err_console` *inside* the capture rather than
being returned as a separate `error` field for the UI to style. Same reason the contract exists:
the moment the surface formats anything itself, there are two rendering paths to keep in step.

**Phase 2.** Three things the spec did not anticipate:

`ctrl+c` is Textual's own quit binding, so cancelling the input line needs `priority=True` to
take it. That leaves no interrupt for a wedged dispatch — a thread worker cannot be cancelled
from the event loop — so `ctrl+q` is bound to quit as an escape hatch alongside `ctrl+d`.

History recall needs a cursor slot one past the newest line, the position the user is in while
composing something new. Without it, down-arrow strands you on the last command with no way back
to an empty box, which is the one thing every shell gets right and is immediately noticeable.

The app test drives Textual's headless pilot through `asyncio.run` rather than taking on
pytest-asyncio for a single case. It dispatches `check --list`, which reads a registry.

The taxonomy ratchet caught `tb tui` on the first run, as designed. It now keeps `MOODS`,
`SURFACES` and `ALIASES` as three sets rather than one widened one: the moods are closed and
carry the read/write promise, the other two do not, and collapsing them would quietly retire the
argument a new top-level word has to win.

**Phase 3.** The spec asked the strip to distinguish a stale lock from a busy lane, and that
state does not exist. `flock` is held by an open file descriptor, so the kernel releases it when
the holder dies — verified by `SIGKILL`ing a holder and immediately re-acquiring. There is no
"held by nobody".

The real hazard is the mirror image of the one specced, and it is live: the lock **file** is left
behind after release, so anything deciding busy-ness by `path.exists()` would report every lane
permanently held from the first job onward. `jobs.py` already knows this — the file is on tmpfs
so it cannot outlive a reboot — but a naive reader of that comment would draw the wrong
conclusion, which is roughly what the spec did.

Probing by attempting the lock would have been worse than wrong. `lane_lock` is `LOCK_NB`, so a
one-second tick would take the lane for an instant, and a `tb run` starting inside that window
would fail to acquire and record `skipped`. The surface would have been causing the exact
condition it was built to display. `/proc/locks` is read-only and gives the holding pid for free.

The write-invariant ratchet fired on `live.py` and was wrong to: it grepped source text, and the
module's docstring *explains* that `run_job` records only after a process exits — which is the
entire argument for showing live lane state. Prose about the banned thing is not a reach for it.
The test now walks the AST for imports and referenced names, and was re-verified against a
deliberate `from cli.run import run_task` before being trusted again.

**Phase 4.** Completion resolves by walking the tree and *stepping over* anything that is not a
subcommand, so a typed job name does not strand it — `auto log doctor --ru` still completes
against `auto log`. Splitting on whitespace rather than with shlex is deliberate: a half-typed
quote is completely normal while typing, and shlex would raise where the user would only see Tab
become a dead key.

Which positional a command takes decides what it completes to, read off the parameter rather than
listed anywhere: `name` means job names, and `run`\'s `target` means jobs *and* internal tasks,
since those are the two registries the imperative mood dispatches from. A new command taking
`name` completes for free.

Tab is `focus_next` everywhere else in Textual and there is nowhere else to focus here, so the
binding needs `priority=True` — the same treatment `ctrl+c` needed.

Pre-implementation findings, verified 2026-08-19 against the tree at `57b0e19`:

- `cli.main(args, standalone_mode=False, obj={})` returns the exit code — `check` → 3,
  `auto list` → 0 — and raises `NoSuchCommand` / `NoSuchOption` for bad input.
- Swapping `cli.output.console` alone does **not** capture `--help`; rich-click uses its own
  console. `redirect_stdout` is required and does capture it.
- `textual` 8.2.8 is `py3-none-any`, so 3.14.7 is fine.
- `cli/jobs.py:219` runs jobs with `subprocess.run(capture_output=True)` and writes `log_path`
  at line 234, after exit. Nothing lands on disk mid-run — which also means `tb auto log` on a
  running job has nothing to read today. That is why streaming is Phase 5 and not Phase 1.
