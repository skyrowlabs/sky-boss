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
WANTED = {**{s.key: s.want for s in repo_settings.REPOSITORY}, "permissions": {"admin": True}}
LABELS = f"{REPO}/labels?per_page=100"


def analysis(status: str) -> dict:
    return {s.key: {"status": status} for s in repo_settings.PUBLIC_ONLY}


def stub(monkeypatch, repo: dict, alerts_on: bool = True, updates_on: bool = True) -> list:
    """`gh api` reads answered from `repo`; every write is recorded and never sent."""

    def gh_api(path: str):
        if path == REPO:
            return repo
        if path == f"{REPO}/vulnerability-alerts" and alerts_on:
            return None
        if path == f"{REPO}/automated-security-fixes":
            return {"enabled": updates_on, "paused": False}
        if path == LABELS:
            return [{"name": "dependencies"}]
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
    written = stub(monkeypatch, drifted, alerts_on=False, updates_on=False)
    preview = CliRunner().invoke(settings.settings, [])
    assert preview.exit_code == 0 and "allow_squash_merge" in preview.output and written == []
    applied = CliRunner().invoke(settings.settings, ["--apply"])
    assert applied.exit_code == 0, applied.output
    assert "allow_squash_merge: on → off" in preview.output
    patch, put, updates, *labels = written
    assert patch[0] == "PATCH" and patch[2]["allow_squash_merge"] is False and "description" in patch[2]
    assert put[:2] == ("PUT", f"{REPO}/vulnerability-alerts")
    assert updates[:2] == ("PUT", f"{REPO}/automated-security-fixes"), "security updates follow alerts"
    assert all(call[:2] == ("POST", f"{REPO}/labels") for call in labels)


def test_alerts_off_is_a_problem_and_on_is_fine(monkeypatch):
    stub(monkeypatch, WANTED, alerts_on=False)
    assert doctor.dependabot_alerts().state == doctor.PROBLEM
    stub(monkeypatch, WANTED)
    assert doctor.dependabot_alerts().state == doctor.OK


def test_security_updates_off_is_a_problem_and_on_is_fine(monkeypatch):
    stub(monkeypatch, WANTED, updates_on=False)
    assert doctor.security_updates().state == doctor.PROBLEM
    stub(monkeypatch, WANTED)
    assert doctor.security_updates().state == doctor.OK


def test_alerts_are_unknown_to_a_token_that_is_not_an_admin(monkeypatch):
    stub(monkeypatch, {**WANTED, "permissions": {"admin": False}}, alerts_on=False)
    assert doctor.dependabot_alerts().state == doctor.UNKNOWN


def test_a_fact_names_the_setting_and_says_what_was_found():
    rows = repo_settings.compare({**WANTED, "has_wiki": True, "visibility": "private"})
    problem = next(f for f in doctor.repository_settings({**WANTED, "has_wiki": True}) if f.name == "setting has_wiki")
    assert problem.state == doctor.PROBLEM and problem.detail.startswith("on; should be off"), problem
    assert any(r.setting.key == "has_wiki" and r.have is True for r in rows)


def test_the_labels_dependabot_applies_are_read_from_its_config(tmp_path):
    """A synthetic config: this tree may own its dependabot.yml (sky.boss's labels nothing)."""
    config = tmp_path / "dependabot.yml"
    config.write_text(
        "updates:\n  - package-ecosystem: pip\n    labels: [dependencies]\n    # labels: [commented]\n"
        "  - package-ecosystem: npm\n    labels: ['dependencies', \"ci\"]\n",
        encoding="utf-8",
    )
    assert scanned(repo_settings.dependabot_labels(config), "labels", least=2) == ["dependencies", "ci"]
    assert repo_settings.dependabot_labels(tmp_path / "absent.yml") == []
    config.write_text(
        "updates:\n  - package-ecosystem: pip\n    labels:\n      - dependencies\n      - 'ci'\n    schedule:\n",
        encoding="utf-8",
    )
    assert repo_settings.dependabot_labels(config) == ["dependencies", "ci"], "block style must be read too"


def test_a_label_a_workflow_adds_is_wanted_too(tmp_path):
    (tmp_path / "workflows").mkdir()
    (tmp_path / "dependabot.yml").write_text(
        "updates:\n  - package-ecosystem: pip\n    labels: [dependencies]\n", encoding="utf-8"
    )
    (tmp_path / "workflows" / "merge.yml").write_text(
        "steps:\n  - run: |\n      addLabels({ issue_number: 1, labels: ['runtime-major'] })\n"
        "      # addLabels({ labels: ['commented'] })\n",
        encoding="utf-8",
    )
    assert scanned(repo_settings.labels_wanted(tmp_path), "labels", least=2) == ["dependencies", "runtime-major"]
