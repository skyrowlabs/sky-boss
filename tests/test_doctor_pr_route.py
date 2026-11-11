"""`doctor`'s facts for a job that lands its report through an auto-merging pull request.

What a report pull request needs is a property of the account and of cron's
environment, which no file states: a required check nothing it starts defines,
or a `gh` logged in only through the session's keyring, leaves it open forever.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest

from scripts.reporting import jobs
from tests.shell import module

pytestmark = pytest.mark.unit

doctor = module("doctor")
REPO = "repos/{owner}/{repo}"
BASE = doctor.BASE_BRANCH
JOB = next(job for job in jobs.JOBS if job.writes.startswith("docs/"))

PR_WORKFLOW = """
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
jobs:
  gate:
    name: CI Gate
  unit:
    name: pytest ${{ matrix.python }}
    strategy:
      matrix:
        python: ['3.12', '3.14']
  lint:
    name: Lint
    if: needs.gate.outputs.full == 'true'
"""

PUSH_ONLY = """
on:
  push:
jobs:
  release:
    name: Release
"""


def stub(monkeypatch, required, workflows: dict[str, str]) -> None:
    """`gh api` answering: `BASE` requires `required` and holds `workflows`, by file name."""
    ref = f"?ref={BASE}"
    answers = {
        f"{REPO}/branches/{BASE}/protection/required_status_checks": {"contexts": required},
        f"{REPO}/contents/.github/workflows{ref}": [
            {"name": name, "path": f".github/workflows/{name}"} for name in workflows
        ],
    }
    for name, text in workflows.items():
        encoded = base64.b64encode(text.encode()).decode()
        answers[f"{REPO}/contents/.github/workflows/{name}{ref}"] = {"content": encoded}

    def gh_api(path: str):
        if path not in answers:
            raise doctor.Unreadable(f"stubbed: {path}")
        return answers[path]

    monkeypatch.setattr(doctor, "gh_api", gh_api)


@pytest.mark.parametrize(
    "trigger, starts",
    [
        ("pull_request", True),
        ("[push, pull_request]", True),
        ("\n  push:", False),
        ("\n  pull_request:\n    types: [ready_for_review]", False),
        (f"\n  pull_request:\n    branches: [{BASE}]", True),
        ("\n  pull_request:\n    branches: [elsewhere]", False),
        (f"\n  pull_request:\n    branches-ignore: [{BASE}]", False),
        ("\n  pull_request:\n    paths: ['src/**']", False),
        ("\n  pull_request:\n    paths: ['**']", True),
        ("\n  pull_request:\n    paths-ignore: ['docs/**']", False),
        ("\n  pull_request:\n    paths: ['**', '!docs/**']", False),
        ("\n  pull_request:\n    paths-ignore: ['*.md']", True),
    ],
)
def test_a_report_pull_request_starts_a_workflow_only_through_its_filters(trigger, starts):
    assert doctor.pr_triggers(f"on: {trigger}\njobs: {{}}\n", BASE, [JOB.writes]) is starts


@pytest.mark.parametrize(
    "required, extra, state",
    [
        (["CI Gate", "Lint", "pytest 3.12"], {}, "ok"),
        (["Release"], {"release.yml": PUSH_ONLY}, "problem"),
        (["a job nobody wrote"], {}, "problem"),
        ([], {}, "ok"),
    ],
)
def test_each_required_check_must_be_defined_by_a_workflow_the_pull_request_starts(monkeypatch, required, extra, state):
    """A job skipped by its own `if:` counts (Lint); a push-only job's check never reports."""
    stub(monkeypatch, required, {"ci.yml": PR_WORKFLOW, **extra})
    fact = doctor.report_pull_request_checks([JOB])
    assert fact.state == state, fact
    if state == "problem":
        assert JOB.key in fact.detail and required[0] in fact.detail, fact


def test_a_paths_filter_that_skips_the_report_file_is_a_problem(monkeypatch):
    filtered = PR_WORKFLOW.replace("    types:", "    paths: ['src/**']\n    types:")
    stub(monkeypatch, ["CI Gate"], {"ci.yml": filtered})
    fact = doctor.report_pull_request_checks([JOB])
    assert fact.state == "problem" and "CI Gate" in fact.detail, fact


def test_no_publishing_job_makes_the_route_not_applicable(monkeypatch):
    monkeypatch.setattr(jobs, "AUTO_PUSH", set())
    assert [fact.state for fact in doctor.pr_route()] == ["not applicable"]


def test_only_the_block_running_from_this_checkout_is_installed():
    ours, theirs = (f"cd {path} && ./x report y" for path in ("/here", "/elsewhere"))
    live = "\n".join(
        [jobs.BLOCK_BEGIN, theirs, jobs.BLOCK_END, "MAILTO=x", jobs.BLOCK_BEGIN, "PATH=/p", ours, jobs.BLOCK_END]
    )
    assert jobs.installed_block(live.replace("./x", "./dev"), "/here") is not None
    assert jobs.installed_block(live.replace("./x", "./dev"), "/nowhere") is None
    assert jobs.cron_env(["# PATH=/no", "PATH=/p", "S=v", "0 3 * * * cd /here"], "/var/empty-home") == {
        "HOME": "/var/empty-home",
        "PATH": "/p",
        "S": "v",
    }


@pytest.fixture
def cron(tmp_path, monkeypatch):
    """A crontab holding this checkout's block, its PATH a directory of fake `gh` and `git`.

    Both fakes fail when a variable from this test's own environment reaches them,
    so a pass means cron's environment was rebuilt, not inherited.
    """
    tools = tmp_path / "tools"
    tools.mkdir()
    checkout = str(tmp_path / "checkout")
    Path(checkout).mkdir()
    block = [jobs.BLOCK_BEGIN, f"PATH={tools}:/usr/bin:/bin", f"0 3 * * * cd {checkout} && ./dev report x"]
    # A marker file, not a variable, says "fail": no variable of this test's reaches the fake.
    script = '#!/bin/sh\n[ -z "$LEAKED_FROM_SESSION" ] || exit 9\n[ ! -e "{tools}/{name}.fails" ] || exit 1\n'
    for name in ("gh", "git"):
        (tools / name).write_text(script.format(tools=tools, name=name), encoding="utf-8")
        (tools / name).chmod(0o755)
    listing = "\n".join([*block, jobs.BLOCK_END])
    (tools / "crontab").write_text(f"#!/bin/sh\ncat <<'EOF'\n{listing}\nEOF\n", encoding="utf-8")
    (tools / "crontab").chmod(0o755)
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("LEAKED_FROM_SESSION", "1")
    monkeypatch.setattr(jobs, "CRON_CWD", checkout)
    monkeypatch.setattr(jobs, "main_checkout", lambda root=None: None)
    return checkout


def test_gh_and_origin_are_asked_under_crons_environment_only(cron, monkeypatch):
    assert [fact.state for fact in doctor.cron_route(jobs)] == ["ok", "ok"]
    (Path(os.environ["PATH"].split(os.pathsep)[0]) / "gh.fails").touch()
    gh, git = doctor.cron_route(jobs)
    assert (gh.state, git.state) == ("problem", "ok"), (gh, git)


def test_a_worktree_measures_the_checkout_the_crontab_names_and_says_so(cron, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "CRON_CWD", str(tmp_path / "a-worktree"))
    monkeypatch.setattr(jobs, "main_checkout", lambda root=None: cron)
    facts = doctor.cron_route(jobs)
    assert all(fact.state == "ok" and cron in fact.detail and "worktree" in fact.detail for fact in facts), facts


def test_no_installed_block_is_unknown_never_fine(cron, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "CRON_CWD", str(tmp_path / "not-installed"))
    assert [fact.state for fact in doctor.cron_route(jobs)] == ["unknown", "unknown"]
