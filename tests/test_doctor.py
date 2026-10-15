"""`doctor` reads GitHub through one stubbed function, and an unread fact is never reported as fine."""

from __future__ import annotations

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


def checks_path() -> str:
    return f"{REPO}/branches/{doctor.BASE_BRANCH}/protection/required_status_checks"


def test_a_default_branch_other_than_the_base_is_a_problem(monkeypatch):
    stub(monkeypatch, {REPO: {"default_branch": "elsewhere"}})
    assert doctor.default_branch().state == doctor.PROBLEM
    stub(monkeypatch, {REPO: {"default_branch": doctor.BASE_BRANCH}})
    assert doctor.default_branch().state == doctor.OK


def test_release_pull_request_needs_the_permission_or_a_token(monkeypatch):
    if not doctor.RELEASE_CONFIG.exists():
        assert doctor.release_pull_request() is None, "a tree with no release pull request has no such fact"
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
    # Diverged from skeletor: guarded as `release_pull_request` is, since doctor reads no secret
    # without a release config, and this tree's ci.yml has no release job (skeletor-adoption round 7).
    if not doctor.RELEASE_CONFIG.exists():
        assert doctor.release_pull_request() is None, "doctor reads release secrets only with a release config"
        return
    ci = (GITHUB_DIR / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for name in (doctor.RELEASE_TOKEN, *doctor.APP_PAIR):
        assert f"secrets.{name}" in ci, f"doctor checks {name}, which ci.yml no longer reads"


def test_a_required_check_no_job_reports_is_a_problem(monkeypatch):
    real = sorted(doctor.workflow_job_names())
    assert real, "found no job names in the workflows"
    stub(monkeypatch, {checks_path(): {"contexts": [real[0], "a job nobody wrote"]}})
    assert doctor.required_checks().state == doctor.PROBLEM
    stub(monkeypatch, {checks_path(): {"checks": [{"context": f"{real[0]} (3.12)"}]}})
    assert doctor.required_checks().state == doctor.OK
    stub(monkeypatch, {checks_path(): {"contexts": ["codecov/patch"]}})
    assert doctor.required_checks().state == doctor.UNKNOWN
    stub(monkeypatch, {checks_path(): 404})
    assert doctor.required_checks().state == doctor.OK


def test_a_templated_job_name_matches_what_it_renders_to():
    assert doctor.resolves("unit (3.12, ubuntu)", {"unit (${{ matrix.python }}, ${{ matrix.os }})"})
    assert not doctor.resolves("lint", {"unit (${{ matrix.python }})"})


def test_nothing_readable_is_never_summarised_as_fine(monkeypatch):
    stub(monkeypatch, {})
    result = CliRunner().invoke(doctor.doctor, [])
    assert result.exit_code == 0 and "none is wrong" not in result.output
    facts = json.loads(CliRunner().invoke(doctor.doctor, ["--json"]).output)["facts"]
    assert facts and {f["state"] for f in facts} == {doctor.UNKNOWN}
