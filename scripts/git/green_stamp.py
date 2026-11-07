"""The record that a full `check pre-push` passed on one tree, read by `scripts/hooks/pre-push`.

A stamp is an empty file named for `HEAD^{tree}`, in `green-stamps/` under the git
common dir, so a linked worktree shares it and a reworded commit keeps it. Only a
full run on a clean tree writes one: uncommitted changes mean the gates read
something no commit holds, and `--quick` skips the suites.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.output import detail, warn
from scripts.paths import PROJECT_ROOT

#: The hook spells this directory too, and tests/test_green_stamp.py holds the two together.
STAMPS = "green-stamps"


def _git(*args: str) -> str | None:
    done = subprocess.run(["git", *args], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else None


def clean_tree() -> str | None:
    """`HEAD^{tree}` when the checkout holds nothing beside it, otherwise `None`."""
    if _git("status", "--porcelain") != "":
        return None
    return _git("rev-parse", "HEAD^{tree}")


def stamp_path(tree: str) -> Path:
    return PROJECT_ROOT / (_git("rev-parse", "--git-common-dir") or ".git") / STAMPS / tree


def record(tree: str | None) -> None:
    """Stamp `tree`, the clean tree the gates started on, if the checkout still is that tree."""
    if tree is None or clean_tree() != tree:
        detail("Not stamped: the checkout had uncommitted changes, so this run proves nothing about a commit.")
        return
    stamp = stamp_path(tree)
    try:
        stamp.parent.mkdir(exist_ok=True)
        stamp.touch()
    except OSError as error:
        warn(f"green, but the stamp could not be written: {error}")
        return
    detail(f"Stamped tree {tree[:12]}: a push of it to a protected branch will pass.")
