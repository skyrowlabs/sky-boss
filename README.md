# tackle-box

`tb` — a terminal surface, and one command that runs things.

**This is a scaffold.** It had a job layer, an asset register, a check suite and a watch system;
all of it was removed on 2026-08-20 to design that half over from a clean base. What is left is
the part worth keeping: an output contract, a palette, and a TUI that dispatches through the real
command tree rather than mirroring it.

## What it does

| Command | Does |
|---|---|
| `tb run -- <argv>` | Runs a command and reports what it printed |
| `tb tui` | Holds tb open — input at the top, newest result under it |

```bash
tb run -- echo hello
tb --json run -- ls -la
tb tui
```

`--` separates tb's flags from the command's own.

## Install

Requires Python 3.13+ and git.

```bash
git clone <this repo> ~/tackle-box
cd ~/tackle-box
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ln -s ~/tackle-box/tb ~/.local/bin/tb        # anywhere on your PATH
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
`cli/output.py`, so the CLI, `--json` and the surface are three consumers of one thing rather than
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
pip install -r requirements-dev.txt     # pytest, and textual-dev for the below
```

### Working on the surface with it open

| Editing | Picked up |
|---|---|
| `cli/tui/tb.tcss` | on save, under `textual run --dev` |
| Any Python | **never — restart** |

```bash
textual console                             # in one terminal
textual run --dev cli.tui.app:TackleBox     # in another; edit tb.tcss and watch it repaint
```

**Python is not hot-reloadable here and deliberately is not made so.** Widget classes are already
instantiated, timers hold bound methods captured at mount, and `cli/output.py` owns thread-local
consoles a dispatch may be inside at the moment you reload. The result would not be a crash, which
is the problem — it would be wrong output that looks right.

Restart is cheap: history persists to `~/.local/state/tb/tui-history`. `^D` on an empty line, then
`tb tui`.

If the surface ever appears to hang it writes `~/.local/state/tb/tui-stall.txt` — every thread's
stack at the moment the event loop stopped — and says so on the launch screen next time it starts.

`CLAUDE.md` carries the conventions and the decisions that have already been argued out.
