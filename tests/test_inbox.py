"""`inbox` reads the lanes back, counts a job's captures once, and never calls an unread lane empty."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.lanes import LANES, SESSION, SOURCE_CAP, source_line  # noqa: E402
from tests.shell import module  # noqa: E402

inbox = module("inbox")


def issue(number: int, source: str = "") -> dict:
    return {"number": number, "title": f"t{number}", "body": source_line(source) if source else "", "createdAt": ""}


def test_the_filer_is_read_from_the_attribution_line():
    assert inbox.source_of(f"## Finding\nx\n\n{source_line('nightly')}\n") == "nightly"
    assert inbox.source_of("no attribution") == SESSION


def test_age_is_whole_days_and_unknown_when_unparseable():
    now = datetime(2026, 10, 14, tzinfo=UTC)
    assert inbox.age_days("2026-10-11T09:00:00Z", now) == 2
    assert inbox.age_days("", now) is None


def pr(*conclusions: str, labels: tuple = (), number: int = 7) -> dict:
    checks = [{"name": f"job-{c.lower()}", "status": "COMPLETED", "conclusion": c} for c in conclusions]
    named = [{"name": label} for label in labels]
    return {"number": number, "title": "bump", "createdAt": "", "labels": named, "statusCheckRollup": checks}


@pytest.fixture
def quiet_gh(monkeypatch):
    """No lane holds anything, so a test reads only the pull request listing."""
    monkeypatch.setattr(inbox, "open_captures", lambda lane: [])
    monkeypatch.setattr(inbox, "open_dependabot_prs", lambda: [])


def test_only_a_failure_class_job_is_named_and_cancelled_fallout_is_not():
    row = inbox.waiting_row(pr("FAILURE", "TIMED_OUT", "STARTUP_FAILURE", "CANCELLED", "SUCCESS"))
    assert row["state"] == "red"
    assert row["jobs"] == ["job-failure", "job-startup_failure", "job-timed_out"]


def test_a_commit_status_counts_by_its_context_and_state():
    status = {"context": "ci/external", "state": "ERROR"}
    assert inbox.waiting_row({**pr(), "statusCheckRollup": [status]})["jobs"] == ["ci/external"]


def test_cancelled_alone_never_reads_as_clean():
    row = inbox.waiting_row(pr("CANCELLED", "SUCCESS"))
    assert row["state"] == "cancelled" and row["jobs"] == []


def test_held_says_so_and_a_red_hold_says_both():
    assert inbox.waiting_row(pr("SUCCESS", labels=(inbox.HELD_LABEL,)))["state"] == "held"
    both = inbox.waiting_row(pr("FAILURE", labels=(inbox.HELD_LABEL,)))
    assert both["state"] == "red" and "runtime major" in both["reason"]


@pytest.mark.parametrize("conclusions", [("SUCCESS",), (), ("SKIPPED", "NEUTRAL")])
def test_what_auto_merge_will_handle_is_not_waiting_on_a_person(conclusions):
    assert inbox.waiting_row(pr(*conclusions)) is None


def test_a_waiting_pull_request_is_listed_and_stops_the_all_clear(quiet_gh, monkeypatch):
    monkeypatch.setattr(inbox, "open_dependabot_prs", lambda: [pr("FAILURE"), pr("SUCCESS", number=8)])
    output = CliRunner().invoke(inbox.inbox, []).output
    assert "#7 bump" in output and "job-failure" in output and "#8" not in output
    assert "nothing is open" not in output
    payload = json.loads(CliRunner().invoke(inbox.inbox, ["--json"]).output)
    assert [row["number"] for row in payload["waiting"]] == [7]


def test_a_listing_that_failed_is_unread_and_never_the_all_clear(quiet_gh, monkeypatch):
    monkeypatch.setattr(inbox, "open_dependabot_prs", lambda: None)
    output = CliRunner().invoke(inbox.inbox, []).output
    assert "could not be listed" in output and "nothing is open" not in output
    assert json.loads(CliRunner().invoke(inbox.inbox, ["--json"]).output)["waiting"] is None


def test_a_job_at_its_cap_is_named_and_a_person_never_is(monkeypatch):
    mine = [issue(n, "nightly") for n in range(SOURCE_CAP)] + [issue(99)]
    monkeypatch.setattr(inbox, "open_captures", lambda lane: mine)
    assert inbox.capped(inbox.read_lanes()) == {"nightly": SOURCE_CAP}, "every lane lists them; each counts once"


def test_an_unread_lane_is_never_reported_as_an_empty_inbox(quiet_gh, monkeypatch):
    monkeypatch.setattr(inbox, "open_captures", lambda lane: None if lane is LANES[0] else [])
    output = CliRunner().invoke(inbox.inbox, []).output
    assert "not an empty inbox" in output and "nothing is open" not in output
    payload = json.loads(CliRunner().invoke(inbox.inbox, ["--json"]).output)
    assert payload["lanes"][LANES[0].key] is None
