---
slug: tui
title: tb tui — a persistent surface over the envelope
status: active
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

#### Phase 5 — streaming — **deferred 2026-08-19, not built**

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

- [ ] Move the `CSS` body to `cli/tui/tb.tcss`; set `CSS_PATH = "tb.tcss"`
- [ ] Override `get_css_variables()` to return the `$tb-*` tokens from `cli/theme.py`
- [ ] Extend `test_no_module_outside_the_palette_names_a_colour` to glob `*.tcss`
- [ ] Test that every `$tb-*` token the stylesheet references is defined — an undefined Textual
      CSS variable fails at parse time, and it should fail in the suite rather than on launch
- [ ] Confirm `textual run --dev cli.tui.app:TackleBox` live-reloads a colour change
- [ ] Move `load_watches()` out of `__init__` into a `refresh_watch_defs()` guarded by the watch
      directory's mtime — not every tick, which is the wrong trade for an edit made twice a week
- [ ] Preserve the injected-`watches` test seam: if watches were passed in, never reload
- [ ] Keep `self.watched` results across a reload for watches whose name and command are
      unchanged, so editing one watch does not blank the rail
- [ ] Test: a watch file appearing after mount is picked up; an injected roster is not
- [ ] Record in `README.md` that Python edits need a restart, and the `textual run --dev` line

**Does not do.** No Python hot reload by any mechanism — not `importlib.reload`, not a re-exec,
not a supervisor that restarts on save. Restart is `^D` and `tb tui`; history persists to
`~/.local/state/tb/tui-history` and every live pane re-reads on the next tick, so there is no
session to lose. That is exactly why the cheap answer is good enough. No `--dev` flag on `tb tui`
— dev mode is `textual run --dev cli.tui.app:TackleBox`, and wrapping it would be the passthrough
CLAUDE.md forbids. No config file for the surface: pane widths still are not persisted, and
[[surface-panes]] decided that.

## Notes

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
