# tackle-box

`tb` — the homebase operator CLI for a workstation and the machines around it. It pairs
**deterministic scripts** with **agentic automations** behind one command, and holds them open in
a terminal surface you can watch work happen in.

It is a personal tool made general. Nothing in this repository describes any particular machine —
your records live in `~/.tackle-box/`, which is yours and separate.

## What it does

| Group | Mood | Owns |
|---|---|---|
| `tb run` | imperative | Run a job, an internal task, or ad-hoc argv — always with a lane, a ledger entry and a log |
| `tb auto` | temporal | Job definitions, lanes, scheduling, ledger, logs |
| `tb info` | descriptive | What a thing *is* |
| `tb check` | evaluative | What is *wrong*. Bare `tb check` runs them all, worst-first |
| `tb tui` | — | A surface over the same output, held open |

Commands are grouped by **what they do to the world**, not by what they act on. The domain axis
grows without bound; this one is closed at four. The property it buys: **`tb run` is the only
door that writes**, so nothing changes state without a ledger entry, because there is no other
way in.

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

## First run

```bash
tb run init-home     # creates ~/.tackle-box and seeds it with templates
tb run asset-seed    # writes the first machine record for this box
tb check             # everything that can judge, worst-first
tb tui               # the surface
```

`tb` works before any of that — `tb check tools` needs nothing — but anything that reads your
machines, jobs or watches will be empty until the home exists.

## Where things live

Three directories, and the rule for each is **who authored the bytes**.

| Where | Holds | Authored by | Versioned |
|---|---|---|---|
| this repo | code, tests, docs, templates | the project | here |
| `~/.tackle-box/` | inventory, jobs, watches | **you** | its own git repo |
| `~/.local/state/tb/` | run ledger, logs | the machine | never |

`$TB_HOME` overrides the middle one.

Your content is separate because it is *yours* — machine records carry addresses, hostnames and
hardware, and a tool you can publish must not carry them with it. It is a git repository of its
own because a machine record's diff is its maintenance log: record the *why* inline as a field
comment and the history answers "when did this change, and what were we thinking".

The ledger stays out of both. It is the one thing here a machine writes rather than a person, it
appends on every run, and versioning it would make `git status` useless within a day.

## Development

```bash
.venv/bin/python -m pytest              # fast: no network, no subprocesses
.venv/bin/python -m pytest -k stripe    # by name
pip install -r requirements-dev.txt     # pytest, and textual-dev for the below
```

### Working on the surface with it open

Three kinds of edit behave three different ways, and it is worth knowing which is which.

| Editing | Picked up |
|---|---|
| A job or watch definition in `~/.tackle-box/` | within a second, no restart |
| `cli/tui/tb.tcss` | on save, under `textual run --dev` |
| Any Python | **never — restart** |

```bash
textual console                             # in one terminal
textual run --dev cli.tui.app:TackleBox     # in another; edit tb.tcss and watch it repaint
```

**Python is not hot-reloadable here and deliberately is not made so.** Widget classes are already
instantiated, timers hold bound methods captured at mount, and `cli/output.py` owns thread-local
consoles that a dispatch may be inside at the moment you reload. The result would not be a crash,
which is the problem — it would be wrong output that looks right.

Restart is cheap and nothing is lost: history persists to `~/.local/state/tb/tui-history`, and
every live pane re-reads its state on the next tick. `^D` on an empty line, then `tb tui`.

If the surface ever appears to hang, it writes `~/.local/state/tb/tui-stall.txt` — every thread's
stack at the moment the event loop stopped — and says so on the launch screen next time it starts.

One doc per feature, for the life of the feature — a change or a fix expands the doc that already
owns it rather than adding a second. Open work is in `docs/features/`; `docs/features/done/` holds
features with no open work, and a doc moves back out when one reopens. `CLAUDE.md` carries the
conventions and the decisions that have already been argued out, including the ones deliberately
rejected.
