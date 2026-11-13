"""`pr land` waits for checks that register late, stops before the merge, and watches the merge's push runs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.shell import module  # noqa: E402

pr = module("pr")
SHA = "a" * 40
MERGED = "b" * 40


def check(name: str, conclusion: str = "SUCCESS", status: str = "COMPLETED") -> dict:
    return {"name": name, "status": status, "conclusion": conclusion, "detailsUrl": f"https://x/{name}"}


class GitHub:
    """A scripted `git` and `gh`: each `pr view` of the checks pops the next state, and the last one repeats."""

    def __init__(self, views: list[dict], runs: list[list[dict]] | None = None, branch: str = "topic") -> None:
        self.views, self.runs, self.branch, self.calls = views, runs or [[]], branch, []

    def __call__(self, *argv: str) -> subprocess.CompletedProcess:
        self.calls.append(argv)
        out = ""
        if argv[:3] == ("git", "rev-parse", "--abbrev-ref"):
            out = self.branch
        elif argv[:2] == ("git", "rev-parse"):
            out = SHA
        elif argv[:3] == ("gh", "pr", "view") and "statusCheckRollup" in argv[-1]:
            out = json.dumps(self.views.pop(0) if len(self.views) > 1 else self.views[0])
        elif argv[:3] == ("gh", "pr", "view") and "mergeCommit" in argv[-1]:
            out = json.dumps({"state": "MERGED", "mergeCommit": {"oid": MERGED}})
        elif argv[:3] == ("gh", "pr", "view"):
            out = json.dumps({"number": 7, "url": "https://x/pull/7", "state": "OPEN", "isDraft": True})
        elif argv[:3] == ("gh", "run", "list"):
            out = json.dumps(self.runs.pop(0) if len(self.runs) > 1 else self.runs[0])
        return subprocess.CompletedProcess(argv, 0, out, "")

    def ran(self, *head: str) -> bool:
        return any(call[: len(head)] == head for call in self.calls)


@pytest.fixture
def land(monkeypatch):
    def invoke(fake, *args: str, pre_push_code: int = 0):
        @click.command()
        @click.option("--quick", is_flag=True)
        def pre_push(quick: bool) -> None:
            raise SystemExit(pre_push_code)

        monkeypatch.setattr(pr, "run", fake)
        monkeypatch.setattr(pr, "pre_push", pre_push)
        monkeypatch.setattr(pr, "POLL", 0)
        return CliRunner().invoke(pr.pr, ["land", "--timeout", "1", *args])

    return invoke


def test_it_waits_for_checks_to_register_and_stops_before_the_merge(land):
    gate, clean = [check("CI Gate")], "CLEAN"
    late = [
        *[{"headRefOid": "old", "statusCheckRollup": gate, "mergeStateStatus": clean}] * 2,
        *[{"headRefOid": SHA, "statusCheckRollup": [], "mergeStateStatus": clean}] * 2,
        {"headRefOid": SHA, "statusCheckRollup": gate, "mergeStateStatus": clean},
        {"headRefOid": SHA, "statusCheckRollup": [*gate, check("pytest", "", "QUEUED")], "mergeStateStatus": "BLOCKED"},
        {"headRefOid": SHA, "statusCheckRollup": [*gate, check("pytest")], "mergeStateStatus": clean},
    ]
    fake = GitHub(late)
    result = land(fake)
    assert result.exit_code == 0, result.output
    assert len(fake.views) == 1, "it read a merge state before the ready run's checks had settled"
    assert f"gh pr merge 7 --merge --match-head-commit {SHA}" in result.output
    assert fake.ran("gh", "pr", "ready", "7") and not fake.ran("gh", "pr", "merge")


def test_a_failed_check_is_red_and_prints_no_merge(land):
    red = {"headRefOid": SHA, "statusCheckRollup": [check("CI Gate"), check("pytest", "CANCELLED")]}
    result = land(GitHub([{**red, "mergeStateStatus": "BLOCKED"}]))
    assert result.exit_code == 1 and "pytest" in result.output and "gh pr merge" not in result.output


def test_merge_is_pinned_and_a_failed_push_run_on_the_merge_is_red(land):
    green = {"headRefOid": SHA, "statusCheckRollup": [check("CI Gate")], "mergeStateStatus": "CLEAN"}
    runs = [[{"name": "CI", "status": "in_progress", "conclusion": "", "url": "u"}]]
    runs.append([{"name": "CI", "status": "completed", "conclusion": "failure", "url": "u"}])
    fake = GitHub([green], runs)
    result = land(fake, "--merge")
    assert fake.ran("gh", "pr", "merge", "7", "--merge", "--match-head-commit", SHA)
    assert fake.ran("gh", "run", "list", "--commit", MERGED, "--event", "push")
    assert result.exit_code == 1 and "CI" in result.output


@pytest.mark.parametrize("branch, dirty", [("develop", ""), ("topic", " M README.md")])
def test_it_refuses_the_base_branch_and_a_dirty_tree_before_pushing(land, branch, dirty):
    fake = GitHub([{}], branch=branch)
    base = fake.__call__

    def with_status(*argv: str):
        done = base(*argv)
        return subprocess.CompletedProcess(argv, 0, dirty, "") if argv[:2] == ("git", "status") else done

    assert land(with_status).exit_code == 2 and not fake.ran("git", "push")


def test_a_red_pre_push_pushes_nothing(land):
    fake = GitHub([{}])
    assert land(fake, pre_push_code=1).exit_code == 1 and not fake.ran("git", "push")
