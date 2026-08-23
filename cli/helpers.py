"""Shared plumbing for the tb CLI.

Command modules call these rather than shelling out or building paths directly.
"""

import re
import os
import subprocess
from pathlib import Path

# tb is installed via a symlink on PATH, so the current working directory is
# never a reliable anchor — you run `tb` from wherever you happen to be. Every
# path in this CLI derives from here. See CLAUDE.md § CLI setup.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Machine-written state lives OUTSIDE the repo on purpose. A gitignored
# directory inside the repo is exactly what `git clean -xdf` destroys, and this
# holds things worth keeping across one — the surface's input history, and a
# stall dump if it ever freezes. XDG state also survives a reclone or a move.
STATE_DIR = Path(os.environ.get("TB_STATE") or Path.home() / ".local" / "state" / "tb")

# What the *operator* authored, as opposed to what the machine generated.
# Separate from STATE_DIR on purpose: `rm -rf ~/.local/state/tb` is a reasonable
# thing to do to reset the surface, and it must not also delete every tool the
# operator wrote. Config rather than state, so XDG puts it under ~/.config.
#
# Outside the repo, and with no fallback path into it. Operator content used to
# live in the tree and a machine record carried a tailnet address into every
# commit, so the tool could not be published without publishing the operator.
# An absent home degrades to nothing declared rather than raising.
TB_HOME = Path(os.environ.get("TB_HOME") or Path.home() / ".config" / "tb")

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


# What tb's own wrapper exports so that `python -m cli` resolves against this
# repo rather than against whatever directory you are standing in. Both are
# load-bearing for tb — see CLAUDE.md § CLI setup — and neither is any business
# of a command tb spawns.
#
# `PATH` is deliberately absent. The wrapper prepends its venv's bin to it, and
# stripping that would be tb deciding which `python3` a foreign tool finds,
# which is the operator's business. Scrub what tb added to boot, nothing else.
BOOTSTRAP = ("PYTHONPATH", "PYTHONSAFEPATH")


def child_env(columns: int | None = None, *, stream: bool = False) -> dict[str, str]:
    """The environment a spawned command should see: the operator's, not tb's.

    Without this, `tb run -- python3 -c "import cli"` imports *this* package
    from anywhere on the machine, because `subprocess` inherits the parent
    environment and tb's wrapper put the repo on `PYTHONPATH`.

    It was found by manually testing something else: `tb data -- jam …`
    succeeded from inside this repo when running `jam` directly there fails, and
    the leak was what made it work. See [[subprocess-env]].

    **`columns` tells the child how wide the display is**, and it is the one
    thing tb *adds* rather than scrubs. A tool laying out columns asks its
    stdout how wide the terminal is; under tb that stdout is a pipe, so it
    falls back to a default and the operator gets a different picture from the
    one the same command draws in the same terminal. Passing the real width
    makes tb transparent instead of narrowing. Only where the output is shown
    as text in that terminal — never for `data`, whose bytes are parsed and
    where a wrapped line would be a corrupted one. `LINES` is deliberately not
    set: a tool that thinks it knows the height may decide to paginate, and a
    pager inside a stream is a hang. See [[subprocess-env]] round 2.
    """
    env = {k: v for k, v in os.environ.items() if k not in BOOTSTRAP}
    if columns:
        env["COLUMNS"] = str(columns)
    if stream:
        # **A pipe makes a child's stdout block-buffered**, so a tool that
        # prints a line a minute writes into an 8 KB buffer and tb — and the
        # operator — see nothing until it fills or the process dies. Measured:
        # a child printing every 0.8s produced its first visible line at
        # t+5.1s, all six at once, at exit. With this set, t+0.3s.
        #
        # It is Python-specific and that is honest rather than ideal: the
        # general fix is a pty, which [[follow]] refuses by name, and
        # `stdbuf -oL` does nothing here because Python's text layer is not
        # libc stdio (measured too). What it does cover is every tool in this
        # family — tb's siblings are all Python — and it costs a
        # non-Python child nothing. See [[subprocess-env]] round 3.
        env["PYTHONUNBUFFERED"] = "1"
    return env


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
