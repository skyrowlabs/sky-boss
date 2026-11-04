"""`report status --json` carries the envelope sky.boss reads, and a cron schedule is read correctly."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanning import scanned  # noqa: E402
from scripts.reporting import cron_schedule, overnight, run_ledger, status  # noqa: E402
from scripts.reporting.jobs import JOBS  # noqa: E402
from tests.shell import module  # noqa: E402

FIELDS = {
    "job",
    "cadence",
    "schedule",
    "last_run",
    "last_age",
    "result",
    "duration_s",
    "overdue",
    "intentionally_off",
    "unscheduled_reason",
    "next_run",
}


@pytest.fixture(autouse=True)
def ledger(monkeypatch, tmp_path):
    path = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(run_ledger, "ledger_path", lambda: path)
    return path


def test_the_envelope_has_every_field_for_every_job():
    result = CliRunner().invoke(module("report").report, ["status", "--json"])
    envelope = json.loads(result.output)
    assert set(envelope) == {"generated", "jobs"}
    entries = scanned(envelope["jobs"], "status entries", least=len(JOBS))
    assert all(set(entry) == FIELDS for entry in entries)


def test_a_job_that_never_ran_is_overdue_unless_it_is_off():
    for entry in status.jobs(datetime(2026, 11, 4, 12, tzinfo=UTC)):
        assert entry["last_age"] == "never" and entry["overdue"] == (not entry["intentionally_off"])


def test_a_run_after_the_last_fire_is_not_overdue(ledger):
    job = scanned([j for j in JOBS if j.key == "overnight"], "the overnight job")[0]
    ledger.write_text(
        json.dumps(
            {"job": job.key, "outcome": "ok", "started": "2026-11-04T11:00:00Z", "finished": "2026-11-04T11:00:05Z"}
        )
        + "\n",
        encoding="utf-8",
    )
    entry = next(e for e in status.jobs(datetime(2026, 11, 4, 11, 30, tzinfo=UTC)) if e["job"] == job.key)
    assert not entry["overdue"] and entry["last_age"] == "29m ago" and entry["duration_s"] == 5


def test_cron_is_read_as_cron_reads_it():
    monday = datetime(2026, 11, 2, 0, 0)
    assert cron_schedule.fires_at("0 0 1 * 1", monday), "day-of-month and day-of-week are ORed"
    assert not cron_schedule.fires_at("0 0 1 * 1", datetime(2026, 11, 3, 0, 0))
    after = datetime(2026, 11, 4, 1, 0)
    assert cron_schedule.next_fire("0 3 * * 0", after, first_week_only=True) == datetime(2026, 12, 6, 3, 0)
    assert cron_schedule.previous_fire("0 22 * * 6", after) == datetime(2026, 10, 31, 22, 0)


def test_a_night_with_nothing_due_still_writes_a_digest():
    text = overnight.digest(datetime(2026, 11, 4, 12, tzinfo=UTC))
    assert text.startswith("# Overnight") and ("idle" in text or "attention" in text)
