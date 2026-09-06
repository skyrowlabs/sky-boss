"""Shared plumbing for the sky.boss CLI.

Command modules call these rather than shelling out or building paths directly.
"""

import re
import os
import subprocess
from pathlib import Path

import click

# sky.boss is installed via a symlink on PATH, so the current working directory is
# never a reliable anchor — you run `sb` from wherever you happen to be. Every
# path in this CLI derives from here. See CLAUDE.md § CLI setup.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Machine-written state lives OUTSIDE the repo on purpose. A gitignored
# directory inside the repo is exactly what `git clean -xdf` destroys, and this
# holds things worth keeping across one — the surface's input history, and a
# stall dump if it ever freezes. XDG state also survives a reclone or a move.
STATE_DIR = Path(os.environ.get("SB_STATE") or Path.home() / ".local" / "state" / "sb")

# What the *operator* authored, as opposed to what the machine generated.
# Separate from STATE_DIR on purpose: `rm -rf ~/.local/state/sb` is a reasonable
# thing to do to reset the surface, and it must not also delete every tool the
# operator wrote.
#
# A visible dotdir, not `~/.config/sb` — settled 2026-08-23 at the operator's
# word. XDG would put config under `~/.config`, and the argument for a visible
# dotdir is that this one is *edited by hand and often*: tools, formats and
# projects are content, not settings a program wrote for itself. `$SB_HOME`
# overrides it either way, which is what the suite uses.
#
# Outside the repo, and with no fallback path into it. Operator content used to
# live in the tree and a machine record carried a tailnet address into every
# commit, so the tool could not be published without publishing the operator.
# An absent home degrades to nothing declared rather than raising.


def _default_home() -> Path:
    """`~/.sky-boss`, or the pre-rename `~/.toolbox` while that is the only one.

    The 2026-08-27 rename moved this directory, and it holds the only files in
    the system the operator wrote by hand. Moving it silently is the worst
    available failure: an absent home degrades to *nothing declared* rather than
    raising, so every saved tool, format and project would simply stop existing
    with no error to read.

    So the old path keeps working while it is the one that is there. The moment
    `~/.sky-boss` exists the fallback stops applying — it is a bridge for an
    operator who has not moved yet, not a second supported location, and there
    is deliberately no merge: two homes at once would make *which* tools.toml
    you are editing a coin toss.
    """
    home = Path.home() / ".sky-boss"
    if not home.exists():
        legacy = Path.home() / ".toolbox"
        if legacy.exists():
            return legacy
    return home


SB_HOME = Path(os.environ.get("SB_HOME") or _default_home())

# The argv this process was invoked with, after the root's `-t` rewrite and
# before Click consumed any of it. Set once by `Root.main` in cli/__init__.py.
#
# It exists for one caller: `--save` writes down **what you typed** rather than
# rebuilding a line from parsed options, because a saved tool whose expansion
# does not match the line that created it fails invisibly until the day it runs
# ([[tools]] round 3). `sys.argv` cannot serve that — under a `CliRunner` it is
# pytest's argv — so the record is taken where the real args arrive, which is
# the one place both the terminal and the suite pass through. Mutated in place
# so importers keep the same list.
INVOCATION: list[str] = []


# What sky.boss's own wrapper exports so that `python -m cli` resolves against this
# repo rather than against whatever directory you are standing in. Both are
# load-bearing for sky.boss — see CLAUDE.md § CLI setup — and neither is any business
# of a command sky.boss spawns.
#
# `PATH` is deliberately absent. The wrapper prepends its venv's bin to it, and
# stripping that would be sky.boss deciding which `python3` a foreign tool finds,
# which is the operator's business. Scrub what sky.boss added to boot, nothing else.
BOOTSTRAP = ("PYTHONPATH", "PYTHONSAFEPATH")


def child_env(
    columns: int | None = None,
    *,
    stream: bool = False,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """The environment a spawned command should see: the operator's, not sky.boss's.

    Without this, `sb run -- python3 -c "import cli"` imports *this* package
    from anywhere on the machine, because `subprocess` inherits the parent
    environment and sky.boss's wrapper put the repo on `PYTHONPATH`.

    It was found by manually testing something else: `sb data -- jam …`
    succeeded from inside this repo when running `jam` directly there fails, and
    the leak was what made it work. See [[subprocess-env]].

    **`columns` tells the child how wide the display is**, and it is the one
    thing sky.boss *adds* rather than scrubs. A tool laying out columns asks its
    stdout how wide the terminal is; under sky.boss that stdout is a pipe, so it
    falls back to a default and the operator gets a different picture from the
    one the same command draws in the same terminal. Passing the real width
    makes sky.boss transparent instead of narrowing. Only where the output is shown
    as text in that terminal — never for `data`, whose bytes are parsed and
    where a wrapped line would be a corrupted one. `LINES` is deliberately not
    set: a tool that thinks it knows the height may decide to paginate, and a
    pager inside a stream is a hang. See [[subprocess-env]] round 2.

    **`extra` is the operator's `--env`, and it is applied last** — over
    `COLUMNS` and `PYTHONUNBUFFERED` both. The two above are sky.boss adding a
    fact it *knows*: it has a terminal, so it knows the width; a pipe is
    block-buffered, so it knows the delay. Nothing lets it know what a tool
    would have *printed* to a terminal, and a tool that asks `isatty()` and
    stays quiet is the one failure in this class with no symptom. Only the
    tool's author knows, and they wrote it down as a variable — so the operator
    declares it, and a declaration about this child beats sky.boss's guess about
    every child. See [[subprocess-env]] round 4.
    """
    env = {k: v for k, v in os.environ.items() if k not in BOOTSTRAP}
    if columns:
        env["COLUMNS"] = str(columns)
    if stream:
        # **A pipe makes a child's stdout block-buffered**, so a tool that
        # prints a line a minute writes into an 8 KB buffer and sky.boss — and the
        # operator — see nothing until it fills or the process dies. Measured:
        # a child printing every 0.8s produced its first visible line at
        # t+5.1s, all six at once, at exit. With this set, t+0.3s.
        #
        # It is Python-specific and that is honest rather than ideal: the
        # general fix is a pty, which [[follow]] refuses by name, and
        # `stdbuf -oL` does nothing here because Python's text layer is not
        # libc stdio (measured too). What it does cover is every tool in this
        # family — sky.boss's siblings are all Python — and it costs a
        # non-Python child nothing. See [[subprocess-env]] round 3.
        env["PYTHONUNBUFFERED"] = "1"
    if extra:
        env.update(extra)
    return env


def parse_env(pairs: tuple[str, ...] | list[str]) -> dict[str, str]:
    """`--env NAME=VALUE` occurrences into a mapping, or a usage error.

    One parser for four commands and the canvas's two resolvers, so a token the
    terminal accepts is a token an accruing window accepts. See
    [[subprocess-env]] round 4.

    **A token with no `=` is refused rather than ignored.** `--env FOO` is
    someone reaching for the shell's `export`, and silently dropping it would
    leave a window that runs, exits 0, and is missing the output the flag was
    added to produce — which is the exact failure this round exists to remove,
    reintroduced by the fix for it.

    A value may be empty (`--env FOO=`) and may contain `=`; only the first one
    splits. **Unsetting is not offered**: an empty variable and an absent one
    are different things to a tool that checks, and `BOOTSTRAP` stays the only
    removal sky.boss performs.
    """
    out: dict[str, str] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not name:
            raise click.UsageError(
                f"--env takes NAME=VALUE, not {pair!r} "
                "(a value may be empty: --env NAME=)"
            )
        out[name] = value
    return out


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int | None = 30,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Run a subprocess and return the completed process.

    Never shell=True: every caller passes an argv list, so nothing here is
    exposed to shell quoting bugs. Callers inspect returncode themselves —
    a non-zero exit is usually a degraded source to warn about, not a crash.
    """
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
        check=check,
        env=child_env(),
    )


# A duration the operator writes by hand: `90s`, `15m`, `2h`, `3d`. One parser,
# because two flags in two docs taking `15m` is exactly the shape that ends with
# `2h` meaning two hours in one place and two minutes in another — see [[delay]]
# and [[file-follow]] round 2. A bare number is **seconds**, spelled out here so
# nobody has to guess: `--due 900` and `--due 15m` are the same expectation.
_DURATION = re.compile(r"\A(\d+)([smhd]?)\Z")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "": 1}


def parse_duration(value: str) -> int:
    """`15m` → 900. Raises `ValueError` on anything else.

    Loudly, at parse time, rather than at the first tick — a watcher that has
    been running for an hour is the worst possible moment to discover that its
    interval never meant anything. Zero is rejected for the same reason: a
    duration of nothing is a typo in every context that takes one.
    """
    match = _DURATION.match((value or "").strip().lower())
    if not match:
        raise ValueError(
            f"not a duration: {value!r} — use 90s, 15m, 2h or 3d (a bare number is seconds)"
        )
    amount = int(match.group(1))
    if amount == 0:
        raise ValueError("a duration of zero says nothing — leave the flag off instead")
    return amount * _UNITS[match.group(2)]
