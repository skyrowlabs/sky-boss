"""`worktree new --base` cuts from origin, and from the local branch only when origin says it has none."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.shell import module  # noqa: E402

worktree = module("worktree")


def git(cwd: Path, *args: str) -> None:
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", *identity, *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def clone(tmp_path, monkeypatch):
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "--quiet", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "--quiet", str(origin), str(work))
    git(work, "commit", "--quiet", "--allow-empty", "-m", "first")
    git(work, "push", "--quiet", "origin", "HEAD:main")
    git(work, "branch", "local-only")
    monkeypatch.setattr(worktree, "PROJECT_ROOT", work)
    monkeypatch.setattr(worktree, "run", lambda argv: subprocess.run(argv, cwd=work, capture_output=True))
    return work


def test_a_branch_on_origin_comes_from_origin(clone):
    assert worktree.start_point("main") == "origin/main"


def test_a_branch_only_here_is_cut_locally(clone):
    assert worktree.start_point("local-only") == "local-only"


def test_a_branch_nowhere_stays_origins_to_fail(clone):
    assert worktree.start_point("nowhere") == "origin/nowhere"


def test_an_unreachable_origin_never_falls_back(clone):
    git(clone, "remote", "set-url", "origin", str(clone.parent / "gone.git"))
    assert worktree.start_point("local-only") == "origin/local-only"
