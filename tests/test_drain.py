"""The lane drainers stand down without an agent, and open a draft PR only from a commit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.reporting import agent_runner, drain  # noqa: E402

DRAIN = drain.Drain(job_key="agent-task", lane_key="task")


class World:
    """`gh`, `git` and the agent, answered from fields; every call is recorded."""

    def __init__(self, issues=None, heads=(), gh_ok=True, agent_commits=True):
        self.issues, self.heads, self.gh_ok, self.agent_commits = issues or [], list(heads), gh_ok, agent_commits
        self.head, self.calls, self.agent_ran = "aaa", [], False
        self.recorded: list = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        out, code = "", 0
        if argv[:3] == ["gh", "issue", "list"]:
            out, code = json.dumps(self.issues), 0 if self.gh_ok else 1
        elif argv[:3] == ["gh", "pr", "list"]:
            out = json.dumps([{"headRefName": h} for h in self.heads])
        elif argv[:2] == ["git", "rev-parse"]:
            out = self.head
        elif argv[0] == "agent":
            self.agent_ran = True
            if self.agent_commits:
                self.head = "bbb"
            out = '{"total_cost_usd": 1.5, "num_turns": 7, "usage": {"input_tokens": 4}}'
        return subprocess.CompletedProcess(argv, code, out, "")


@pytest.fixture
def world(monkeypatch):
    def install(**kwargs):
        made = World(**kwargs)
        monkeypatch.setattr(drain.shellout, "run", made)
        monkeypatch.setattr(agent_runner, "current_branch", lambda: "main")
        monkeypatch.setattr(agent_runner, "tree_is_clean", lambda: True)
        monkeypatch.setattr(agent_runner, "agent_argv", lambda prompt: ["agent", prompt])
        monkeypatch.setattr(drain.run_ledger, "record", made.recorded.append)
        return made

    return install


def issue(number, comments=0):
    body = [{"body": drain.ATTEMPT_MARKER}] * comments
    return {"number": number, "title": f"t{number}", "body": "b", "createdAt": f"2026-01-0{number}", "comments": body}


def test_an_empty_lane_is_declined_without_an_agent(world):
    made = world()
    assert drain.run(DRAIN, base_branch="main") == 0
    assert not made.agent_ran and [r.outcome for r in made.recorded] == ["declined"]


def test_an_unreadable_lane_fails_rather_than_reading_as_empty(world):
    made = world(issues=[issue(1)], gh_ok=False)
    assert drain.run(DRAIN, base_branch="main") == 1
    assert not made.agent_ran and made.recorded[0].outcome == "failed"


def test_an_issue_with_an_open_draft_or_spent_attempts_is_skipped(world):
    made = world(issues=[issue(1), issue(2, comments=drain.MAX_ATTEMPTS)], heads=[drain.branch_for(DRAIN, 1)])
    drain.run(DRAIN, base_branch="main")
    assert not made.agent_ran and made.recorded[0].outcome == "declined"


def test_a_dry_run_names_the_issue_and_records_nothing(world, monkeypatch):
    monkeypatch.setenv(agent_runner.DRY_RUN_ENV, "1")
    made = world(issues=[issue(3)])
    assert drain.run(DRAIN, base_branch="main") == 0
    assert not made.agent_ran and made.recorded == []


def test_a_commit_becomes_a_draft_pr_on_the_lanes_branch(world):
    made = world(issues=[issue(2), issue(1)])
    assert drain.run(DRAIN, base_branch="main") == 0
    created = next(c for c in made.calls if c[:3] == ["gh", "pr", "create"])
    assert "--draft" in created and created[created.index("--head") + 1] == drain.branch_for(DRAIN, 1)
    assert made.recorded[0].outcome == "ok" and made.recorded[0].committed == "bbb"
    assert (made.recorded[0].cost_usd, made.recorded[0].num_turns, made.recorded[0].tokens) == (1.5, 7, 4)


def test_no_commit_is_a_failure_and_opens_nothing(world):
    made = world(issues=[issue(1)], agent_commits=False)
    assert drain.run(DRAIN, base_branch="main") == 1
    assert not any(c[:3] == ["gh", "pr", "create"] for c in made.calls)
    assert ["git", "branch", "-D", drain.branch_for(DRAIN, 1)] in made.calls
