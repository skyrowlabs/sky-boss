"""`inbox` reads the lanes back, counts a job's captures once, and never calls an unread lane empty."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
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
    now = datetime(2026, 10, 14, tzinfo=timezone.utc)
    assert inbox.age_days("2026-10-11T09:00:00Z", now) == 2
    assert inbox.age_days("", now) is None


def test_a_job_at_its_cap_is_named_and_a_person_never_is(monkeypatch):
    mine = [issue(n, "nightly") for n in range(SOURCE_CAP)] + [issue(99)]
    monkeypatch.setattr(inbox, "open_captures", lambda lane: mine)
    assert inbox.capped(inbox.read_lanes()) == {"nightly": SOURCE_CAP}, "every lane lists them; each counts once"


def test_an_unread_lane_is_never_reported_as_an_empty_inbox(monkeypatch):
    monkeypatch.setattr(inbox, "open_captures", lambda lane: None if lane is LANES[0] else [])
    output = CliRunner().invoke(inbox.inbox, []).output
    assert "not an empty inbox" in output and "nothing is open" not in output
    payload = json.loads(CliRunner().invoke(inbox.inbox, ["--json"]).output)
    assert payload["lanes"][LANES[0].key] is None
