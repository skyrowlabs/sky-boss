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
    import subprocess

    # A reaped child rather than a literal: any fixed number can be a live pid here.
    child = subprocess.Popen([sys.executable, "-c", ""])
    child.wait()
    _write_hold(tmp_path, pid=child.pid, owner="crashed-job", age_s=7200)

    assert tree_lock.holders(root=tmp_path) == []


def _git(cwd: Path, *args: str) -> str:
    import subprocess

    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _repo(tmp_path: Path) -> Path:
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "develop")
    for key, value in (("user.name", "t"), ("user.email", "t@example.invalid"), ("commit.gpgsign", "false")):
        _git(main, "config", key, value)
    _git(main, "commit", "-q", "--allow-empty", "-m", "chore: root")
    return main


def test_another_trees_unpushed_branch_does_not_block_a_drop(tmp_path):
    """Branches are shared by every worktree, and a branch survives removal (sky.boss)."""
    from tests.shell import module

    main = _repo(tmp_path)
    _git(main, "switch", "-q", "-c", "feat/elsewhere")
    _git(main, "commit", "-q", "--allow-empty", "-m", "feat: unpushed, in the main tree")
    _git(main, "worktree", "add", "-q", "-b", "feat/here", str(tmp_path / "wt"))
    _git(tmp_path / "wt", "commit", "-q", "--allow-empty", "-m", "feat: unpushed, on this tree's branch")

    assert module("worktree").stranded(tmp_path / "wt") == []


def test_a_detached_heads_own_commit_blocks_a_drop(tmp_path):
    from tests.shell import module

    main = _repo(tmp_path)
    _git(main, "worktree", "add", "-q", "--detach", str(tmp_path / "wt"))
    _git(tmp_path / "wt", "commit", "-q", "--allow-empty", "-m", "feat: on no branch")

    lost = module("worktree").stranded(tmp_path / "wt")
    assert len(lost) == 1 and "on no branch" in lost[0]


def test_a_linked_environment_is_ignored(tmp_path):
    """`worktree new` makes these symlinks, and `.venv/` matches only a directory."""
    repo = _repo(tmp_path)
    shipped = Path(__file__).resolve().parents[1] / ".gitignore"
    (repo / ".gitignore").write_text(shipped.read_text(encoding="utf-8"), encoding="utf-8")
    for name in (".venv", "node_modules"):
        (repo / name).symlink_to(tmp_path)
    assert _git(repo, "status", "--porcelain").split() == ["??", ".gitignore"]


@pytest.mark.parametrize(("theirs", "linked"), [("same", True), ("other", False)])
def test_node_modules_is_borrowed_only_while_the_lockfiles_agree(tmp_path, monkeypatch, theirs, linked):
    from tests.shell import module

    worktree = module("worktree")
    primary, target = tmp_path / "primary", tmp_path / "target"
    (primary / "node_modules").mkdir(parents=True)
    target.mkdir()
    (primary / "package-lock.json").write_text("same", encoding="utf-8")
    (target / "package-lock.json").write_text(theirs, encoding="utf-8")
    monkeypatch.setattr(worktree, "PROJECT_ROOT", primary)
    worktree._link_node_modules(target)
    assert (target / "node_modules").is_symlink() is linked
