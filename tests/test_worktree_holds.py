"""`dev worktree drop` asks the tree it is deleting whether anybody is in it.

`drop` had two guards and both describe the tree's **contents**: uncommitted
changes, and commits on no remote. Neither says whether somebody is *using* it.
A test run does not dirty a tree and does not create commits, so a checkout with
a live `suite` hold is clean, pushed, and was removed with a green tick — out
from under a running job. Reproduced end-to-end before it was fixed.

## Why the argument to `holders()` is the whole fix

Holds are per-checkout: `PROJECT_ROOT` resolves from `scripts/paths.py`'s own
location and a worktree has its own copy, so each checkout owns its
`tmp/tree-locks/`. That is a good property — a hold here cannot strand a sibling
— and it is a trap for exactly this caller. The obvious repair, calling
`holders()` with no argument, reads *this* tree's directory, finds nothing, and
reports "nothing is holding it" about a tree it never looked at. It would have
looked fixed and passed a test that only checked the unheld case.

So both directions are asserted, and the held case is what distinguishes the
real fix from the plausible one. jam.sense supplied the general form after
measuring this design against theirs: **a job reasoning about a tree other than
its own needs a directory it can name, not a module constant.**

A *dead* hold must not block, and that is asserted too — a crashed holder that
wedges the drop forever teaches people to pass `--force` by reflex, which
disables the guard for the live case it exists for.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import tree_lock  # noqa: E402


def _write_hold(root: Path, pid: int, *, owner: str, age_s: float = 0.0) -> None:
    lock_dir = tree_lock.lock_dir_for(root)
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / f"suite-{pid}.json").write_text(
        json.dumps({"kind": "suite", "pid": pid, "branch": "feature", "owner": owner, "started": time.time() - age_s}),
        encoding="utf-8",
    )


def test_lock_dir_is_per_checkout(tmp_path):
    """Two trees, two directories — the property that makes a hold local."""
    assert tree_lock.lock_dir_for(tmp_path / "a") != tree_lock.lock_dir_for(tmp_path / "b")
    assert tree_lock.lock_dir_for() == tree_lock.LOCK_DIR


def test_holders_reads_the_tree_it_is_given(tmp_path):
    """The assertion the plausible fix fails.

    A bare `holders()` would answer about the tree running the test, which holds
    nothing — indistinguishable from a correct answer until the day it matters.
    """
    _write_hold(tmp_path, pid=__import__("os").getpid(), owner="a-live-suite")

    assert [h.owner for h in tree_lock.holders(root=tmp_path)] == ["a-live-suite"]
    assert tree_lock.holders(root=tmp_path / "somewhere-else") == []


def test_a_dead_holder_does_not_wedge_the_tree(tmp_path):
    """A pid that is gone holds nothing, however recently it said otherwise."""
    _write_hold(tmp_path, pid=999_999, owner="crashed-job", age_s=7200)

    assert tree_lock.holders(root=tmp_path) == []
