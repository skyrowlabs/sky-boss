"""Without Release Please, the CI gate is the commit-msg hook run over the range.

sky.boss measured two ways it was weaker than the hook: it passed only the
subject, so the one-subject-line rule could never fire, and it skipped the
hook entirely for bots, where the hook's own comment exempts them from the
length cap alone.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts import check_commit_subjects as gate

pytestmark = pytest.mark.unit

BOT = "dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>"
PERSON = "A Person <person@example.com>"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repository with no Release Please config, so the hook is the contract."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    monkeypatch.setattr(gate, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(gate, "RELEASE_CONFIG", tmp_path / "absent.json")
    return tmp_path


def commit(repo: Path, text: str, author: str) -> tuple:
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "--no-verify", "--author", author, "-m", text],
        cwd=str(repo),
        check=True,
        env={**os.environ, "GIT_COMMITTER_NAME": "c", "GIT_COMMITTER_EMAIL": "c@example.com"},
    )
    inspected = gate.subjects("-1")
    assert inspected, "git could not read the commit just made"
    return tuple(inspected[0])


def found(repo: Path, text: str, author: str = PERSON) -> list:
    return gate.unreadable([commit(repo, text, author)], gate.hook_types())


def test_a_second_subject_line_in_the_body_is_refused(repo):
    assert found(repo, "feat(x): one change\n\nfix(y): and a second one")


def test_a_bot_is_exempt_from_the_length_cap_only(repo, monkeypatch):
    long = "build(deps): bump " + "a" * 60
    assert len(long) > 72
    # Set both ways here, so a tree holding the switch at False takes this test unchanged (sky.boss).
    monkeypatch.setattr(gate, "BOTS_EXEMPT_FROM_LENGTH", True)
    assert not found(repo, long, BOT)
    assert found(repo, long + " then.", BOT), "a bot's trailing period passed: the whole hook was skipped"
    assert found(repo, long, PERSON)
    monkeypatch.setattr(gate, "BOTS_EXEMPT_FROM_LENGTH", False)
    assert found(repo, long, BOT)
