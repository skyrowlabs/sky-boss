"""A push to a protected branch needs a green stamp, judged per ref by the pushed tree.

Real git against a bare remote, because the hook's input is git's own stdin format.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.git import green_stamp
from scripts.git import install_merge_drivers as imd

pytestmark = pytest.mark.unit

BASE = "develop"
RELEASE = "main"
HOOK = imd.HOOK_SOURCE
ENV = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")} | {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, env=ENV)


def _git(cwd: Path, *args: str) -> str:
    done = _run(cwd, *args)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _commit(repo: Path, text: str) -> str:
    (repo / "file.txt").write_text(text, encoding="utf-8")
    _git(repo, "add", "file.txt")
    _git(repo, "commit", "-qm", text)
    return _git(repo, "rev-parse", "HEAD^{tree}")


def _refused(repo: Path, *refs: str) -> bool:
    """Refused by the hook in particular: git refuses a push for reasons of its own too."""
    pushed = _run(repo, "push", "origin", *refs)
    return pushed.returncode == 1 and "no green stamp" in pushed.stderr


def _stamp(repo: Path, tree: str) -> None:
    stamps = Path(_git(repo, "rev-parse", "--absolute-git-dir")) / green_stamp.STAMPS
    stamps.mkdir(exist_ok=True)
    (stamps / tree).touch()


@pytest.fixture
def repo(tmp_path):
    """A clone with the hook installed, one commit, and a bare remote holding nothing yet."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    work.mkdir()
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _git(work, "init", "-q", "-b", BASE)
    _git(work, "remote", "add", "origin", str(remote))
    hook = work / ".git" / "hooks" / "pre-push"
    hook.parent.mkdir(exist_ok=True)
    shutil.copy(HOOK, hook)
    hook.chmod(0o755)
    _commit(work, "first")
    return work


def test_an_unstamped_tree_is_refused_naming_the_command(repo):
    pushed = _run(repo, "push", "origin", BASE)
    assert pushed.returncode == 1
    assert "check pre-push" in pushed.stderr
    assert _git(repo, "ls-remote", "origin") == ""


def test_a_stamped_tree_passes_and_a_reworded_commit_keeps_the_stamp(repo):
    _stamp(repo, _git(repo, "rev-parse", "HEAD^{tree}"))
    _git(repo, "commit", "-q", "--amend", "-m", "reworded")
    assert _run(repo, "push", "origin", BASE).returncode == 0


def test_the_release_branch_is_judged_too(repo):
    assert _refused(repo, f"HEAD:refs/heads/{RELEASE}")


def test_another_branch_a_tag_and_a_delete_are_not_judged(repo):
    assert _run(repo, "push", "origin", "HEAD:refs/heads/work").returncode == 0
    _git(repo, "tag", "-a", "v1", "-m", "v1")
    assert _run(repo, "push", "origin", "v1").returncode == 0
    assert _run(repo, "push", "--no-verify", "origin", BASE).returncode == 0
    assert _run(repo, "push", "origin", f":{BASE}").returncode == 0


def _hook(repo: Path, *shas_to_refs: tuple[str, str]) -> int:
    """The hook on stdin of our ordering: git chooses the order of a real push."""
    lines = "".join(f"refs/heads/x {sha} {ref} {'0' * 40}\n" for sha, ref in shas_to_refs)
    return subprocess.run(
        [str(repo / ".git" / "hooks" / "pre-push"), "origin", "url"],
        cwd=str(repo),
        input=lines,
        capture_output=True,
        text=True,
        env=ENV,
    ).returncode


def test_an_unjudged_ref_first_clears_nothing(repo):
    head = _git(repo, "rev-parse", "HEAD")
    assert _hook(repo, (head, "refs/heads/work"), (head, f"refs/heads/{BASE}")) == 1


def test_a_stamped_ref_first_clears_nothing(repo):
    stamped = _git(repo, "rev-parse", "HEAD")
    _stamp(repo, _git(repo, "rev-parse", "HEAD^{tree}"))
    _commit(repo, "second")
    unstamped = _git(repo, "rev-parse", "HEAD")
    assert _hook(repo, (stamped, f"refs/heads/{BASE}"), (unstamped, f"refs/heads/{RELEASE}")) == 1


def test_a_fetched_tip_first_clears_nothing(repo):
    assert _run(repo, "push", "--no-verify", "origin", BASE).returncode == 0
    seen = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "second")
    unstamped = _git(repo, "rev-parse", "HEAD")
    assert _hook(repo, (seen, f"refs/heads/{BASE}"), (unstamped, f"refs/heads/{RELEASE}")) == 1


def test_the_pushed_sha_is_judged_not_head(repo):
    stamped = _git(repo, "rev-parse", "HEAD")
    _stamp(repo, _git(repo, "rev-parse", "HEAD^{tree}"))
    _commit(repo, "second")
    assert _run(repo, "push", "origin", f"{stamped}:refs/heads/{BASE}").returncode == 0
    assert _refused(repo, f"HEAD:refs/heads/{BASE}")


def test_the_fetched_tip_of_a_protected_branch_passes_unstamped(repo):
    assert _run(repo, "push", "--no-verify", "origin", BASE).returncode == 0
    _git(repo, "commit", "-q", "--allow-empty", "-m", "same tree, new commit")
    assert _run(repo, "push", "origin", BASE).returncode == 0
    _commit(repo, "second")
    assert _refused(repo, BASE)


def test_a_linked_worktree_shares_the_stamps_and_the_hook(repo, tmp_path):
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "-q", "--detach", str(linked))
    tree = _commit(linked, "second")
    assert _refused(linked, f"HEAD:refs/heads/{BASE}")
    _stamp(repo, tree)
    assert _run(linked, "push", "origin", f"HEAD:refs/heads/{BASE}").returncode == 0


def test_no_verify_remains(repo):
    assert _run(repo, "push", "--no-verify", "origin", BASE).returncode == 0


def test_the_hook_reads_the_directory_the_stamp_is_written_to():
    assert f"/{green_stamp.STAMPS}" in HOOK.read_text(encoding="utf-8")


@pytest.fixture
def stamping(repo, monkeypatch):
    monkeypatch.setattr(green_stamp, "PROJECT_ROOT", repo)
    return repo


def test_a_clean_tree_is_stamped(stamping):
    tree = _git(stamping, "rev-parse", "HEAD^{tree}")
    assert green_stamp.clean_tree() == tree
    green_stamp.record(tree)
    assert green_stamp.stamp_path(tree).exists()


@pytest.mark.parametrize("name", ["file.txt", "untracked.txt"])
def test_uncommitted_work_is_no_clean_tree(stamping, name):
    (stamping / name).write_text("changed", encoding="utf-8")
    assert green_stamp.clean_tree() is None


def test_a_tree_that_changed_during_the_run_is_not_stamped(stamping, capsys):
    tree = _git(stamping, "rev-parse", "HEAD^{tree}")
    (stamping / "file.txt").write_text("a gate rewrote this", encoding="utf-8")
    green_stamp.record(tree)
    assert not green_stamp.stamp_path(tree).exists()
    assert "Not stamped" in capsys.readouterr().err


@pytest.fixture
def installing(repo, monkeypatch):
    """The repo with no hook yet, and the installer pointed at it."""
    (repo / ".git" / "hooks" / "pre-push").unlink()
    monkeypatch.setattr(imd, "PROJECT_ROOT", repo)
    monkeypatch.setattr(imd, "ATTRIBUTES", repo / ".gitattributes")
    monkeypatch.setattr(imd, "MESSAGE_TEMPLATE", repo / ".gitmessage")
    monkeypatch.setattr(imd, "MARKER", repo / "tmp" / ".regen-owed")
    return repo / ".git" / "hooks" / "pre-push"


def _main(monkeypatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["install_merge_drivers.py", *args])
    return imd.main()


def test_check_is_red_without_the_hook_and_the_installer_makes_it_green(installing, monkeypatch):
    assert _main(monkeypatch, "--check") == 1
    assert _main(monkeypatch) == 0
    assert os.access(installing, os.X_OK)
    assert _main(monkeypatch, "--check") == 0


def test_a_hook_somebody_else_wrote_is_left_alone_and_stays_red(installing, monkeypatch):
    installing.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert _main(monkeypatch) == 1
    assert installing.read_text(encoding="utf-8") == "#!/bin/sh\nexit 0\n"
    assert _main(monkeypatch, "--check") == 1


def test_a_tracked_hook_of_the_trees_own_is_refused_at_install_and_says_so(installing, monkeypatch, capsys):
    source = installing.parent.parent.parent / "own-pre-push"
    source.write_text("#!/bin/sh\n./run-my-check\n", encoding="utf-8")
    monkeypatch.setattr(imd, "HOOK_SOURCE", source)
    assert _main(monkeypatch) == 1
    assert not installing.exists()
    assert _main(monkeypatch, "--check") == 1
    assert "this tree's own hook" in capsys.readouterr().err


def test_an_out_of_date_copy_is_red_and_the_installer_replaces_it(installing, monkeypatch):
    assert _main(monkeypatch) == 0
    installing.write_text(installing.read_text(encoding="utf-8") + "# older\n", encoding="utf-8")
    assert _main(monkeypatch, "--check") == 1
    assert _main(monkeypatch) == 0
    assert _main(monkeypatch, "--check") == 0


def test_deleting_the_tracked_hook_declines_it(installing, monkeypatch, tmp_path):
    monkeypatch.setattr(imd, "HOOK_SOURCE", tmp_path / "declined")
    assert _main(monkeypatch) == 0
    assert not installing.exists()
    assert _main(monkeypatch, "--check") == 0
