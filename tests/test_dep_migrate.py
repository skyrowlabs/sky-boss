"""`dep-migrate` drafts one held runtime major per run, and the suite it runs itself decides the outcome."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import PROJECT_ROOT  # noqa: E402
from scripts.reporting import agent_runner, dep_migrate  # noqa: E402


class World:
    """`gh`, `git` and the agent, answered from fields; every call is recorded."""

    def __init__(self, held=None, agent_commits=True):
        self.held, self.agent_commits = held or [], agent_commits
        self.head, self.calls, self.agent_argv = "aaa", [], None
        self.recorded: list = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        out = ""
        if argv[:3] == ["gh", "pr", "list"]:
            out = json.dumps(self.held if "--label" in argv else [])
        elif argv[:2] == ["git", "rev-parse"]:
            out = self.head
        elif argv[0] == "agent":
            self.agent_argv = list(argv)
            out = '{"result": "renamed the client call", "total_cost_usd": 0.5}'
            if self.agent_commits:
                self.head = "bbb"
        return subprocess.CompletedProcess(argv, 0, out, "")


@pytest.fixture
def world(monkeypatch):
    def install(green=True, **kwargs):
        made = World(**kwargs)
        monkeypatch.setattr(dep_migrate.shellout, "run", made)
        monkeypatch.setattr(dep_migrate, "suite", lambda: (green, "suite output"))
        monkeypatch.setattr(agent_runner, "current_branch", lambda: "main")
        monkeypatch.setattr(agent_runner, "tree_is_clean", lambda: True)
        monkeypatch.setattr(agent_runner, "agent_argv", lambda prompt: ["agent", prompt])
        monkeypatch.delenv(agent_runner.AGENT_CMD_VAR, raising=False)
        monkeypatch.setattr(dep_migrate.run_ledger, "record", made.recorded.append)
        return made

    return install


def held(number, labels=()):
    return {
        "number": number,
        "title": f"bump lib from 1 to 2 (#{number})",
        "body": "release notes",
        "headRefName": f"dependabot/pip/lib-{number}",
        "labels": [{"name": dep_migrate.RUNTIME_MAJOR_LABEL}, *({"name": name} for name in labels)],
        "createdAt": f"2026-01-0{number}",
    }


def calls(made, *prefix):
    return [call for call in made.calls if call[: len(prefix)] == list(prefix)]


def test_nothing_held_is_declined_without_an_agent(world):
    made = world(held=[held(1, [dep_migrate.FAILED_LABEL]), held(2, [dep_migrate.NOT_NEEDED_LABEL])])
    assert dep_migrate.run(base_branch="main") == 0
    assert made.agent_argv is None and made.recorded[0].outcome == "declined"


def test_green_opens_a_draft_that_links_the_dependabot_pr_and_leaves_it_open(world):
    made = world(held=[held(2), held(1)])
    assert dep_migrate.run(base_branch="main") == 0
    created = calls(made, "gh", "pr", "create")[0]
    assert "--draft" in created and created[created.index("--head") + 1] == dep_migrate.branch_for(1)
    assert "#1" in created[created.index("--body") + 1] and not calls(made, "gh", "pr", "close")
    assert ["git", "switch", "-c", dep_migrate.branch_for(1), "FETCH_HEAD"] in made.calls
    assert made.recorded[0].outcome == "ok" and made.recorded[0].cost_usd == 0.5
    assert made.agent_argv[-2:] == ["--max-turns", str(dep_migrate.MAX_TURNS)]


def test_red_labels_the_dependabot_pr_and_opens_nothing(world):
    made = world(held=[held(1)], green=False)
    assert dep_migrate.run(base_branch="main") == 0
    assert not calls(made, "gh", "pr", "create")
    assert ["gh", "pr", "edit", "1", "--add-label", dep_migrate.FAILED_LABEL] in made.calls
    assert "renamed the client call" in calls(made, "gh", "pr", "comment")[0][-1]
    assert made.recorded[0].outcome == "declined" and made.recorded[0].agent_ran


def test_green_with_no_commit_is_labelled_not_needed(world):
    made = world(held=[held(1)], agent_commits=False)
    assert dep_migrate.run(base_branch="main") == 0
    assert ["gh", "pr", "edit", "1", "--add-label", dep_migrate.NOT_NEEDED_LABEL] in made.calls
    assert not calls(made, "gh", "pr", "create")


def test_a_custom_agent_command_bounds_itself(world, monkeypatch):
    made = world(held=[held(1)])
    monkeypatch.setenv(agent_runner.AGENT_CMD_VAR, "agent {prompt}")
    dep_migrate.run(base_branch="main")
    assert "--max-turns" not in made.agent_argv


def test_the_merge_workflow_writes_the_label_this_job_reads():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "dependabot-auto-merge.yml").read_text(encoding="utf-8")
    assert workflow.count(f"labels: ['{dep_migrate.RUNTIME_MAJOR_LABEL}']") == 2, "both merge paths label it"
