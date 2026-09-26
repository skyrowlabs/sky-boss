"""This checkout's idea of the remote's default branch is the branch work lands on.

`refs/remotes/origin/HEAD` is a local pointer, written once by `git clone` and
never refreshed. When a repository changes its default branch afterwards — a
second branch cut when it went public, say — every existing clone keeps pointing
at the old one, and anything that resolves it locally gets the wrong answer.

Dream Doll's pointed at `main` while their base branch, their CI trigger and the
account all said `develop`. Tooling reads that pointer: their own agent session
opened with *"Main branch (you will usually use this for PRs): main"*,
contradicting their contributing rules. Nothing in this tree read it, so nothing
could say so. It is a local read, not an account fact — the class a tree
genuinely can state — and the value to compare against is rendered into this
file.

**An absent pointer passes, and that is a decision rather than a skip.** CI's
checkout and a fresh `git init` have none, and a pointer that does not exist
misleads nobody. The fix, when this fails, is one local command and changes
nothing anybody else sees.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import PROJECT_ROOT  # noqa: E402

BASE_BRANCH = "develop"


def origin_head(root: Path = PROJECT_ROOT) -> Optional[str]:
    """The branch `origin/HEAD` names in this checkout, or None when there is no such pointer."""
    done = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        return None
    return done.stdout.strip().removeprefix("refs/remotes/origin/")


def test_origin_head_is_the_base_branch():
    named = origin_head()
    assert named in (None, BASE_BRANCH), (
        f"refs/remotes/origin/HEAD in this checkout names `{named}`, and this repository's base branch "
        f"is `{BASE_BRANCH}`. The pointer is written at clone time and never refreshed, so anything that "
        f"asks it — an agent harness picking a pull-request target, a script defaulting a diff base — "
        f"gets `{named}`. Refresh it from the remote:\n"
        f"    git remote set-head origin --auto\n"
        f"If `{named}` really is the branch work lands on now, the base branch this tree was rendered "
        f"with is the stale half, and the CI trigger names it too."
    )


def test_the_check_would_actually_catch_one(tmp_path):
    """Seen failing, against a real pointer rather than a stubbed read."""
    identity = ["-c", "user.name=t", "-c", "user.email=t@t.invalid"]

    def git(*args: str) -> None:
        subprocess.run(["git", *identity, *args], cwd=str(tmp_path), check=True, capture_output=True)

    git("init", "-q", "-b", BASE_BRANCH)
    assert origin_head(tmp_path) is None, "a repository with no remote has no pointer"
    git("commit", "-q", "--allow-empty", "-m", "base")
    stale = "not-" + BASE_BRANCH
    git("update-ref", f"refs/remotes/origin/{stale}", "HEAD")
    git("symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{stale}")
    assert origin_head(tmp_path) == stale
