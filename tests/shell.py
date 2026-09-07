"""The shell's package, reached through its recorded name.

`cli` is the most collided-with package name in a python monorepo, so
`--shell-package` renames it. `scripts/paths.py` holds the name — written there
by the scaffolder — and everything else asks that module rather than spelling
it.

## Why this is a module and not six `importlib` calls

Six call sites needed the same two lines, and a convention you have to remember
to apply is a registry with no enforcement. It is also the difference between a
rename that works and one that half-works: a static `from cli.test_cmds import
SUITES` is the single thing a rename cannot survive, and it fails at collection
time with `ModuleNotFoundError`, which reads as a broken tree rather than as a
missed site.

## The name is a value here and never a token in an import

A placeholder cannot appear in an `import` statement — `from <token>.x import y`
does not parse — which is why the name arrives as a **string** and this module
turns it into a module object through `importlib`. An earlier version drew the
wider conclusion that the name could not be written down at all and had
`paths.py` *discover* it by looking for a root `__main__.py`. That broke every
adopter whose own product is a `python -m` CLI, because two candidates is the
ordinary case rather than the impossible one.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import SHELL_PACKAGE  # noqa: E402

__all__ = ["SHELL_PACKAGE", "module", "group"]


def module(name: str = "") -> ModuleType:
    """The shell package, or one module inside it."""
    return importlib.import_module(f"{SHELL_PACKAGE}.{name}" if name else SHELL_PACKAGE)


def group():
    """The root click group.

    Named `cli` inside the package whatever the package is called — the group
    and the directory shared a name once, and only the directory moves. That is
    the artefact sky.boss's own rename produced: a `sed` over `from cli import
    cli` gave `from x import x`, renaming the group as well.
    """
    return module().cli
