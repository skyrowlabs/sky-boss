"""Shared helpers for the CLI package.

Status lines are **not** defined here. They come from `scripts/output.py`, which
`scripts/` can import too — a vocabulary only half the tree can reach is one the
other half retypes. This module re-exports them so a command module has one
import, and so the re-export list is the only thing to change if that ever moves.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path in the tree — can be imported. The `./dev` wrapper exports
# PYTHONPATH, but `python -m cli` from a different cwd does not, and a helper
# that only imports under one invocation is a helper nobody trusts.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import (  # noqa: E402
    SYMBOLS,
    badge,
    detail,
    die,
    emit,
    fail,
    item,
    line,
    ok,
    shell,
    skip,
    step,
    summarize,
    warn,
)
from scripts.paths import PROJECT_ROOT  # noqa: E402

#: Re-exported on purpose — listed so flake8 does not read them as unused, and
#: so `from .helpers import ok` keeps working from every command module.
__all__ = [
    "PROJECT_ROOT",
    "SYMBOLS",
    "absolutize_path_env",
    "badge",
    "current_branch",
    "detail",
    "die",
    "emit",
    "fail",
    "git",
    "item",
    "line",
    "module",
    "ok",
    "run",
    "script",
    "shell",
    "skip",
    "step",
    "summarize",
    "warn",
]


def absolutize_path_env() -> None:
    """Make every ``PATH`` entry absolute before anything spawns a child.

    A relative entry — the ``PATH=.venv/bin:$PATH`` prefix people write by hand —
    is re-resolved against *each process's own cwd*. An interpreter found through
    one keeps that relative path as ``sys.executable``, so every child that
    chdirs (a test running from a tmp dir, a subprocess with ``cwd=``) loses it.
    The failure looks like a missing package, which sends you to the wrong place.
    """
    entries = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            entry = os.getcwd()  # POSIX reads an empty entry as the cwd
        entries.append(entry if os.path.isabs(entry) else os.path.abspath(entry))
    os.environ["PATH"] = os.pathsep.join(entries)


def run(cmd: Sequence[str], *, cwd: Optional[Path] = None, check: bool = False, capture: bool = False):
    """Run a command from the project root, echoing it unless capturing."""
    if not capture:
        shell(" ".join(str(c) for c in cmd))
    return subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd or PROJECT_ROOT),
        check=check,
        text=True,
        capture_output=capture,
    )


def script(name: str, *args: str) -> int:
    """Run a repo script *by path* with the interpreter running this CLI."""
    return run([sys.executable, str(PROJECT_ROOT / name), *args]).returncode


def module(name: str, *args: str) -> int:
    """Run an installed module (``python -m name``) with this CLI's interpreter.

    Separate from `script` because `script` joins its first argument onto
    `PROJECT_ROOT`: `script("-m", "pytest", ...)` silently becomes the path
    `<root>/-m` and every run fails on a file that was never going to exist.
    A flag is not a path, so it needs its own door.
    """
    return run([sys.executable, "-m", name, *args]).returncode


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=False
    ).stdout.strip()


def current_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD")
