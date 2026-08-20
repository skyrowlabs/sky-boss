"""Tests for tb unpushed — work that exists on only one disk."""

import subprocess

import pytest

from cli.unpushed import find_repos, inspect_repo


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "work"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "t")
    (path / "a.txt").write_text("hello")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "first")
    return path


def test_repo_with_no_remote_is_exposed(repo):
    """The case that describes this repo itself: committed, but on one disk."""
    row = inspect_repo(repo)
    assert row["ok"] is False
    assert row["has_remote"] is False
    assert "only on this disk" in row["detail"]


def test_uncommitted_changes_are_exposed(repo):
    (repo / "b.txt").write_text("new")
    row = inspect_repo(repo)
    assert row["ok"] is False
    assert row["uncommitted"] == 1


def test_pushed_and_clean_repo_is_ok(repo, tmp_path):
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")

    row = inspect_repo(repo)
    assert row["ok"] is True
    assert row["detail"] == "clean"
    assert row["unpushed"] == 0


def test_unpushed_commits_are_exposed(repo, tmp_path):
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")

    (repo / "c.txt").write_text("more")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "second")

    row = inspect_repo(repo)
    assert row["ok"] is False
    assert row["unpushed"] == 1


def test_remote_without_upstream_branch_is_exposed(repo, tmp_path):
    """A remote nothing tracks is not a backup."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
    git(repo, "remote", "add", "origin", str(bare))

    row = inspect_repo(repo)
    assert row["ok"] is False
    assert "no upstream" in row["detail"]


def test_find_repos_is_shallow(tmp_path):
    """A repo nested inside a checkout is usually a vendored dependency."""
    outer = tmp_path / "project"
    (outer / ".git").mkdir(parents=True)
    nested = outer / "vendor" / "dep"
    (nested / ".git").mkdir(parents=True)

    assert find_repos((tmp_path,)) == [outer]


def test_find_repos_skips_non_repos(tmp_path):
    (tmp_path / "notarepo").mkdir()
    assert find_repos((tmp_path,)) == []


def test_missing_root_is_not_an_error(tmp_path):
    assert find_repos((tmp_path / "nope",)) == []
