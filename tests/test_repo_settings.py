"""The settings profile is compared, reported and applied from one declaration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import repo_settings  # noqa: E402
from tests.scanning import scanned  # noqa: E402
from tests.shell import module  # noqa: E402

doctor = module("doctor")
settings = module("settings")
REPO = "repos/{owner}/{repo}"
WANTED = {s.key: s.want for s in repo_settings.REPOSITORY}


def analysis(status: str) -> dict:
    return {s.key: {"status": status} for s in repo_settings.PUBLIC_ONLY}


def stub(monkeypatch, repo: dict, alerts_on: bool = True) -> list:
    """`gh api` reads answered from `repo`; every write is recorded and never sent."""

    def gh_api(path: str):
        if path == REPO:
            return repo
        if path == f"{REPO}/vulnerability-alerts" and alerts_on:
            return None
        raise doctor.Unreadable(f"stubbed: {path}", 404)

    written: list = []
    monkeypatch.setattr(doctor, "gh_api", gh_api)
    monkeypatch.setattr(settings, "gh_api", gh_api)
    monkeypatch.setattr(settings, "gh_write", lambda *call: written.append(call))
    return written


def test_a_matching_repository_needs_no_patch():
    rows = scanned(repo_settings.compare({**WANTED, "visibility": "private"}), "declared settings", least=6)
    assert repo_settings.patch_body(rows) == {}
    assert [r.setting.key for r in rows if not r.applies] == [s.key for s in repo_settings.PUBLIC_ONLY]


def test_public_visibility_is_read_from_github_and_turns_on_scanning():
    rows = repo_settings.compare({**WANTED, "visibility": "public", "security_and_analysis": analysis("disabled")})
    body = repo_settings.patch_body(rows)
    assert body == {"security_and_analysis": {s.key: {"status": "enabled"} for s in repo_settings.PUBLIC_ONLY}}


def test_a_setting_github_did_not_report_is_unknown_and_never_fine(monkeypatch):
    stub(monkeypatch, {"visibility": "public", "description": "d"})
    states = {f.name: f.state for f in doctor.repository_settings()}
    assert scanned([s for s in states.values() if s == doctor.UNKNOWN], "unreported settings", least=8)


def test_settings_previews_and_writes_only_with_apply(monkeypatch):
    drifted = {**WANTED, "allow_squash_merge": True, "visibility": "private", "description": ""}
    written = stub(monkeypatch, drifted, alerts_on=False)
    preview = CliRunner().invoke(settings.settings, [])
    assert preview.exit_code == 0 and "allow_squash_merge" in preview.output and written == []
    applied = CliRunner().invoke(settings.settings, ["--apply"])
    assert applied.exit_code == 0, applied.output
    patch, put = written
    assert patch[0] == "PATCH" and patch[2]["allow_squash_merge"] is False and "description" in patch[2]
    assert put[:2] == ("PUT", f"{REPO}/vulnerability-alerts")


def test_alerts_off_is_a_problem_and_on_is_fine(monkeypatch):
    stub(monkeypatch, WANTED, alerts_on=False)
    assert doctor.dependabot_alerts().state == doctor.PROBLEM
    stub(monkeypatch, WANTED)
    assert doctor.dependabot_alerts().state == doctor.OK
