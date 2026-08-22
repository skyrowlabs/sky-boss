# toolbox

`tb` — a command palette over a window canvas, and two commands that reach other tools.

**This is young.** It had a job layer, an asset register, a check suite and a watch system; all of
it was removed on 2026-08-20 to design that half over from a clean base. What is left is the part
worth keeping: an output contract, a palette, and a surface that drives the real command tree
rather than mirroring it.

## What it does

| Command | Does |
|---|---|
| `tb run -- <argv>` | Runs a command and reports what it printed. The only command that acts |
| `tb data -- <argv>` | Reads another CLI's JSON as data, so a window can keep it fresh |
| `tb ui` | Opens the canvas |

```bash
tb run -- echo hello
tb --json data -- ip -j -br addr
tb ui
```

`--` separates tb's flags from the command's own.

## The canvas

`tb ui` opens a command palette over a canvas of windows. Every command opens a window; windows
tile or float, drag, and stack. A window you pin re-runs its command on a cadence — 5s to 5m — and
that clock lives in the server, keyed to the connection, so **a watcher pauses when you close the
window and keeps running when you only minimize it.** A browser timer could not promise the second
half: a hidden page has its timers clamped to about one fire per minute.

Only reads get a cadence. `tb run` executes whatever argv you hand it, so it is never given one —
re-running a read is a refresh, and re-running a write is a scheduler nobody asked for. Choosing
`wrap` over `run` is how you assert this argv is a read.

`tb ui --scale` sets how big the surface renders — every size derives from it, and it defaults to
2. `--size WIDTH,HEIGHT` sets the window geometry; otherwise the profile remembers where you left
it. `--kiosk` goes full-screen with no frame, for a wall display, and cannot be resized.

The window is a native webview, so it is frameless by request, resizable, and moved by dragging
the surface's own top bar — none of which a browser can do, since no web API lets a page move its
own window. `--browser` opens it in Chromium instead and `--no-browser` serves only, which is the
mode to develop in.

**On KDE the title bar comes back anyway.** GTK asks for no decorations and KWin draws one
regardless. Right-click the title bar → *More Actions* → *No Border* hides it for that window
only; to make it stick, add a rule matched on the window class:

```ini
# ~/.config/kwinrulesrc
[General]
rules=toolbox

[toolbox]
Description=toolbox
noborder=true
noborderrule=2
wmclass=toolbox
wmclasscomplete=false
wmclassmatch=1
```

Then `qdbus6 org.kde.KWin /KWin reconfigure`. The surface carries its own close button, so removing
the frame does not strand you.

The server binds loopback on an ephemeral port and dies with the window. It runs commands, so it
requires a per-launch token in a custom header — which also forces a CORS preflight that is never
answered, so a page on another site cannot reach it even blind.

## Install

Requires Python 3.13+ and git.

```bash
git clone <this repo> ~/toolbox
cd ~/toolbox
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ln -s ~/toolbox/tb ~/.local/bin/tb        # anywhere on your PATH
```

Fish completions, if you use fish:

```bash
_TB_COMPLETE=fish_source tb > ~/.config/fish/completions/tb.fish
```

> **fish users on CachyOS:** the shipped fish config defines `alias tb='nc termbin.com 9999'`,
> and a fish function shadows PATH. Add `functions --query tb; and functions --erase tb` to
> `~/.config/fish/config.fish`.

## The contract

Every command returns a `Result` envelope and never prints. All rendering goes through
`cli/output.py`, so the CLI, `--json` and the canvas are three consumers of one thing rather than
three formatters.

| Exit | Meaning |
|---|---|
| `0` | ok |
| `1` | hard failure |
| `3` | partial — some of the work succeeded |

Not `2`: Click uses it for usage errors, so a caller branching on exit codes would read a typo as
a degraded run.

`--json` is a root-group flag. Under it stdout carries the envelope and nothing else; warnings
still go to stderr, so a pipeline is never broken by a degraded source.

## Where things live

| Where | Holds | Versioned |
|---|---|---|
| this repo | code, tests, docs | here |
| `~/.local/state/tb/` | input history, stall dumps | never |

`$TB_STATE` overrides the second. There is no operator content directory any more — nothing
declares anything yet.

## Development

```bash
.venv/bin/python -m pytest              # fast: no network
pip install -r requirements-dev.txt
```

### Working on the surface with it open

| Editing | Picked up |
|---|---|
| `cli/canvas/static/*.css` | **live** — swapped in place, windows keep their state |
| Any other static file | **live** — the page reloads itself, losing open windows |
| Any Python | **never — restart** |

```bash
tb ui --no-browser --port 8765          # then open http://127.0.0.1:8765/
```

Save a file and the page reacts within about half a second — the server fingerprints `static/` on
the session stream it is already running and pushes a frame. A CSS edit is swapped in place, so
every window keeps its position, its pin, its chips and its last result while you adjust the
styling. Anything else is a full reload, which does lose the open windows, because the module
graph is already evaluated and half-old JavaScript holding live state is worse than starting over.

The frontend has **no automated tests** — there is no JS test runner and adding one means npm — so
the pure parts (`unwrap`, `suggest`, `roleFor`, `planReload`) are where a mistake will not be
caught for you.

**Python is not hot-reloadable here and deliberately is not made so.** A reload would leave a live
session holding watchers registered against the old code, and the result would not be a crash,
which is the problem — it would be stale behaviour that looks right.

`CLAUDE.md` carries the conventions and the decisions that have already been argued out.
