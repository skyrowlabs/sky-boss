"""`default_range()` returns ONE git argument, naming exactly what a push would send.

`scripts/check_commit_subjects.py::default_range` is imported by adopters' own
scripts — sky.boss's `check_commit_style.py` does — so its return shape is
released API, as much as its name is. v0.33.0 returned `"HEAD --not --remotes"`,
three arguments in one string that only the template's own caller split, and
sky.boss's importer broke at run time. Nothing in the template could see it,
because every caller the template can see was updated in the same commit.

So this pins the contract rather than the implementation: the value has no
spaces, and `git log <value>` in a real repository lists exactly the commits the
push would send — for a first push, and with an upstream, and with no remote.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.check_commit_subjects as subjects  # noqa: E402

IDENTITY = ["-c", "user.name=t", "-c", "user.email=t@t.invalid"]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *IDENTITY, *args], cwd=str(root), capture_output=True, text=True, check=True).stdout


def _range_in(root: Path, monkeypatch) -> str:
    monkeypatch.setattr(subjects, "PROJECT_ROOT", root)
    found = subjects.default_range()
    assert isinstance(found, str) and " " not in found.strip(), (
        f"default_range() returned {found!r}, which is not one git argument. Adopters pass it to git as "
        f"one; a string that needs splitting breaks every caller the template cannot see."
    )
    return found


def _sent(root: Path, commit_range: str) -> list:
    return _git(root, "log", "--format=%s", commit_range).split("\n")[:-1]


def test_a_first_push_names_every_unpushed_commit(tmp_path, monkeypatch):
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _git(tmp_path, "init", "-q", "-b", "develop", str(work))
    _git(work, "commit", "-q", "--allow-empty", "-m", "chore: pushed already")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-q", "origin", "develop")
    _git(work, "checkout", "-q", "-b", "feature")
    _git(work, "commit", "-q", "--allow-empty", "-m", "fix: first")
    _git(work, "commit", "-q", "--allow-empty", "-m", "fix: second")
    found = _range_in(work, monkeypatch)
    assert _sent(work, found) == ["fix: second", "fix: first"], (
        f"{found!r} does not name exactly the two unpushed commits — a first push sends both, and "
        f"HEAD alone checked one and printed ✅ (proto.pilot, measured)."
    )


def test_with_an_upstream_and_with_no_remote(tmp_path, monkeypatch):
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _git(tmp_path, "init", "-q", "-b", "develop", str(work))
    _git(work, "commit", "-q", "--allow-empty", "-m", "chore: base")
    assert _range_in(work, monkeypatch) == "-1", "with no remote at all, HEAD alone is the honest answer"
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-q", "-u", "origin", "develop")
    _git(work, "commit", "-q", "--allow-empty", "-m", "fix: unpushed")
    found = _range_in(work, monkeypatch)
    assert _sent(work, found) == ["fix: unpushed"], f"{found!r} with an upstream must name the unpushed commit"


def test_an_empty_remote_and_an_all_pushed_branch(tmp_path, monkeypatch):
    """The two ends proto.pilot and Dream Doll ran: no shared history, and nothing to send."""
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _git(tmp_path, "init", "-q", "-b", "develop", str(work))
    _git(work, "commit", "-q", "--allow-empty", "-m", "chore: years of history")
    _git(work, "remote", "add", "origin", str(remote))
    assert (
        _range_in(work, monkeypatch) == "-1"
    ), "a remote with no history in common is the no-remote case: the whole history is not what to check"
    _git(work, "push", "-q", "origin", "develop")
    _git(work, "checkout", "-q", "-b", "feature")
    found = _range_in(work, monkeypatch)
    assert _sent(work, found) == [], f"{found!r}: everything is pushed, so the push sends nothing"
