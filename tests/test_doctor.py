"""`doctor` reads GitHub through one stubbed function, and an unread fact is never reported as fine."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import GITHUB_DIR  # noqa: E402
from tests.shell import module  # noqa: E402

doctor = module("doctor")
REPO = "repos/{owner}/{repo}"


def stub(monkeypatch, answers: dict) -> None:
    """`gh api` answering from `answers`; a path not in it is unreadable, an int is that HTTP status."""

    def gh_api(path: str):
        answer = answers.get(path)
        if answer is None or isinstance(answer, int):
            raise doctor.Unreadable(f"stubbed: {path}", answer)
        return answer

    monkeypatch.setattr(doctor, "gh_api", gh_api)


def checks_path(branch: str = doctor.BASE_BRANCH) -> str:
    return f"{REPO}/branches/{branch}/protection/required_status_checks"


def test_a_default_branch_other_than_the_base_is_a_problem(monkeypatch):
    stub(monkeypatch, {REPO: {"default_branch": "elsewhere"}})
    assert doctor.default_branch().state == doctor.PROBLEM
    stub(monkeypatch, {REPO: {"default_branch": doctor.BASE_BRANCH}})
    assert doctor.default_branch().state == doctor.OK


def test_release_pull_request_needs_the_permission_or_a_token(monkeypatch):
    if not doctor.RELEASE_CONFIG.exists():
        assert doctor.release_pull_request().state == doctor.NOT_APPLICABLE
        return
    denied = {f"{REPO}/actions/permissions/workflow": {"can_approve_pull_request_reviews": False}}
    stub(monkeypatch, {**denied, f"{REPO}/actions/secrets": {"secrets": []}})
    assert doctor.release_pull_request().state == doctor.PROBLEM
    stub(monkeypatch, {**denied, f"{REPO}/actions/secrets": {"secrets": [{"name": "APP_ID"}]}})
    assert doctor.release_pull_request().state == doctor.PROBLEM, "half the App pair is not a token"
    org = {"secrets": [{"name": n} for n in doctor.APP_PAIR]}
    stub(monkeypatch, {**denied, f"{REPO}/actions/organization-secrets": org})
    assert doctor.release_pull_request().state == doctor.OK
    stub(monkeypatch, denied)
    assert doctor.release_pull_request().state == doctor.UNKNOWN


def test_the_release_secrets_are_the_ones_ci_reads():
    if not doctor.RELEASE_CONFIG.exists():
        assert doctor.release_pull_request().state == doctor.NOT_APPLICABLE, "no release job, so no secrets to name"
        return
    ci = (GITHUB_DIR / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for name in (doctor.RELEASE_TOKEN, *doctor.APP_PAIR):
        assert f"secrets.{name}" in ci, f"doctor checks {name}, which ci.yml no longer reads"


WORKFLOW = """
jobs:
  gate:
    name: CI Gate
  unit:
    name: pytest ${{ matrix.python }}
    strategy:
      matrix:
        python: ['3.12', '3.14']
  unit-result:
    name: pytest
"""


def on_branch(branch: str, required, workflow: str = WORKFLOW) -> dict:
    """Stub answers: `branch` requires `required` and holds one workflow file."""
    ref = f"?ref={branch}"
    listing = [{"name": "ci.yml", "path": ".github/workflows/ci.yml"}]
    content = {"content": base64.b64encode(workflow.encode()).decode()}
    return {
        checks_path(branch): {"contexts": required} if isinstance(required, list) else required,
        f"{REPO}/contents/.github/workflows{ref}": listing,
        f"{REPO}/contents/.github/workflows/ci.yml{ref}": content,
    }


@pytest.mark.parametrize(
    "required, state",
    [
        (["CI Gate", "pytest"], "ok"),
        (["pytest 3.14"], "problem"),
        (["pytest 9.9"], "problem"),
        (["unit (3.12)"], "problem"),
        (["a job nobody wrote"], "problem"),
        (["codecov/patch"], "unknown"),
        (404, "ok"),
    ],
)
def test_a_required_check_must_be_a_job_that_reports_and_never_a_matrix_leg(monkeypatch, required, state):
    stub(monkeypatch, on_branch("main", required))
    assert doctor.required_checks("main").state == state


def test_a_branch_is_judged_by_its_own_workflows_not_this_checkout(monkeypatch):
    without = WORKFLOW.replace("  unit-result:\n    name: pytest\n", "")
    stub(monkeypatch, on_branch("main", ["pytest"], without))
    assert doctor.required_checks("main").state == doctor.PROBLEM, "mind.head, 2026-10-02"
    stub(monkeypatch, {checks_path("main"): {"contexts": ["pytest"]}})
    assert doctor.required_checks("main").state == doctor.UNKNOWN, "unreadable workflows are never this checkout's"


def test_the_checks_ci_yml_tells_you_to_require_are_jobs_and_its_legs_are_not():
    jobs = doctor.workflow_jobs([(GITHUB_DIR / "workflows" / "ci.yml").read_text(encoding="utf-8")])
    assert doctor.classify("CI Gate", jobs) == doctor.classify("pytest", jobs) == "job"
    assert doctor.classify("pytest 3.12", jobs) == "leg"


def test_nothing_readable_is_never_summarised_as_fine(monkeypatch):
    stub(monkeypatch, {})
    result = CliRunner().invoke(doctor.doctor, [])
    assert result.exit_code == 0 and "none is wrong" not in result.output
    facts = json.loads(CliRunner().invoke(doctor.doctor, ["--json"]).output)["facts"]
    states = {f["state"] for f in facts}
    assert doctor.UNKNOWN in states and states <= {doctor.UNKNOWN, doctor.NOT_APPLICABLE}


def test_every_long_lived_branch_has_its_required_checks_asked(monkeypatch):
    asked = []

    def required_checks(branch: str):
        asked.append(branch)
        return doctor.Fact(branch, doctor.OK, "")

    monkeypatch.setattr(doctor, "required_checks", required_checks)
    stub(monkeypatch, {})
    doctor.gather()
    assert asked == list(dict.fromkeys((doctor.BASE_BRANCH, doctor.RELEASE_BRANCH)))


def test_an_inapplicable_fact_is_listed_and_not_counted(monkeypatch):
    monkeypatch.setattr(doctor, "RELEASE_CONFIG", doctor.RELEASE_CONFIG.with_name("absent.json"))
    unprotected = {checks_path(): 404, checks_path(doctor.RELEASE_BRANCH): 404}
    stub(monkeypatch, {REPO: {"default_branch": doctor.BASE_BRANCH}, **unprotected})
    result = CliRunner().invoke(doctor.doctor, [])
    assert "the release job can open its pull request" in result.output and "applicable facts" in result.output
