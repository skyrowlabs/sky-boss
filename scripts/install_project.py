#!/usr/bin/env python3
"""Install this tree as an editable package, with every extra, when it is one.

A scaffold ships no `[project]` block, so this does nothing until the tree
becomes a real package. From then on, a suite that imports the package fails at
collection unless it is installed. CI's jobs and the setup block both run this
one script, so "green on a fresh tree" and "green in CI" install the same thing.
The setup block once stopped at the requirements file while CI installed the
project, and a fresh clone was red (proto.pilot).

EVERY extra, because a bare `pip install -e .` installs `dependencies` and
stops, and test requirements conventionally live in an extra whose name varies
(`dev`, `test`). The names are read from the file, so there is no list to keep.
Narrow it in your tree if an extra is huge or platform-specific.

Usage:  python scripts/install_project.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import ok, warn  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402

PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def target() -> str | None:
    """The pip target, `.[a,b]` or `.`; None when there is no `[project]` block.

    A malformed `pyproject.toml` raises rather than resolving to "no extras",
    which would install the wrong thing in silence.
    """
    if not PYPROJECT.exists():
        return None
    try:
        import tomllib
    except ImportError:
        if "[project]" not in PYPROJECT.read_text(encoding="utf-8").splitlines():
            return None
        warn("this python has no tomllib, so the extras cannot be read — installing the project bare")
        return "."
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8")).get("project")
    if project is None:
        return None
    extras = sorted(project.get("optional-dependencies") or {})
    return f".[{','.join(extras)}]" if extras else "."


def main() -> int:
    chosen = target()
    if chosen is None:
        ok("no [project] block in this tree — nothing to install")
        return 0
    ok(f"pyproject.toml declares [project] — installing {chosen} editable")
    return subprocess.run([sys.executable, "-m", "pip", "install", "-e", chosen], cwd=PROJECT_ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
