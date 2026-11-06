"""Without Release Please, the CI gate is the commit-msg hook run over the range.

sky.boss measured two ways it was weaker than the hook: it passed only the
subject, so the one-subject-line rule could never fire, and it skipped the
hook entirely for bots, where the hook's own comment exempts them from the
length cap alone.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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


def test_a_revert_of_a_valid_subject_passes_and_of_an_invalid_one_does_not(repo):
    assert not found(repo, 'Revert "feat(x): one change"\n\nThis reverts commit 0123456.')
    assert not found(repo, 'Reapply "feat(x): one change"')
    assert not found(repo, 'Revert "Reapply "feat(x): one change""')
    assert found(repo, 'Revert "not a conventional subject"')
    assert found(repo, 'Revert "feat(x): Capital summary"'), "the rules must read the subject inside"
    assert found(repo, 'Revert "feat(x): ' + "a" * 72 + '"'), "the cap applies to the subject inside"


def test_release_please_arm_passes_a_revert_and_counts_it_as_skipped(repo, monkeypatch, capsys):
    config = repo / "release-please-config.json"
    sections = [{"type": "feat", "section": "Features"}]
    config.write_text(json.dumps({"packages": {".": {"changelog-sections": sections}}}), encoding="utf-8")
    monkeypatch.setattr(gate, "RELEASE_CONFIG", config)
    inspected = [commit(repo, "feat(x): one change", PERSON), commit(repo, 'Revert "feat(x): one change"', PERSON)]
    assert not gate.unreadable(inspected, gate.configured_types())
    assert gate.unreadable([commit(repo, 'Revert "docs: no section"', PERSON)], gate.configured_types())
    monkeypatch.setattr(gate, "subjects", lambda commit_range: inspected)
    monkeypatch.setattr(sys, "argv", ["check_commit_subjects.py", "--range", "HEAD"])
    assert gate.main() == 0
    said = capsys.readouterr().err
    assert "1 subject(s) in HEAD are readable" in said and "1 revert subject(s)" in said
