"""`report status --json` carries the envelope sky.boss reads, and a cron schedule is read correctly."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanning import scanned  # noqa: E402
from scripts.reporting import cron_schedule, jobs, overnight, run_ledger, status  # noqa: E402
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
    "scheduled_in_cron",
    "unscheduled_reason",
    "next_run",
}


@pytest.fixture(autouse=True)
def ledger(monkeypatch, tmp_path):
    path = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(run_ledger, "ledger_path", lambda: path)
    return path


@pytest.fixture(autouse=True)
def crontab(monkeypatch, tmp_path):
    """Every job installed, no install recorded and no offset; a test narrows any of them."""
    monkeypatch.setattr(jobs, "SCHEDULE_OFFSET_PINNED", 0)
    live = {"text": "\n".join(job.cron_line() for job in JOBS)}
    monkeypatch.setattr(status, "_crontab", lambda: live["text"])
    monkeypatch.setattr(status, "INSTALL_BACKUPS", tmp_path / "no-backups")
    return live


def test_a_job_missing_from_the_crontab_is_not_installed_rather_than_overdue(crontab):
    crontab["text"] = ""
    entries = scanned([e for e in status.jobs() if not e["intentionally_off"]], "scheduled jobs")
    assert all(e["scheduled_in_cron"] is False and not e["overdue"] for e in entries)
    crontab["text"] = None
    assert all(e["scheduled_in_cron"] is None for e in status.jobs())


def test_the_checkouts_offset_moves_every_fire_time(monkeypatch):
    monkeypatch.setattr(jobs, "SCHEDULE_OFFSET_PINNED", 7)
    delay = timedelta(minutes=7)
    for entry in scanned([e for e in status.jobs() if e["next_run"]], "scheduled entries"):
        slot = datetime.fromisoformat(entry["next_run"]).replace(tzinfo=None) - delay
        job = jobs.JOBS_BY_KEY[entry["job"]]
        assert cron_schedule.next_fire(job.cron, slot - timedelta(minutes=1), job.first_week_only) == slot, entry


def test_a_slot_before_the_install_is_not_a_missed_run(monkeypatch, tmp_path):
    now = datetime(2026, 11, 4, 12, tzinfo=UTC)
    entries = scanned([e for e in status.jobs(now) if not e["intentionally_off"]], "scheduled jobs")
    assert all(e["overdue"] for e in entries)
    tmp_path.joinpath("backups").mkdir()
    tmp_path.joinpath("backups", "crontab-20261104T115900Z.bak").write_text("", encoding="utf-8")
    monkeypatch.setattr(status, "INSTALL_BACKUPS", tmp_path / "backups")
    assert not any(e["overdue"] for e in status.jobs(now))


def test_the_envelope_has_every_field_for_every_job():
    result = CliRunner().invoke(module("report").report, ["status", "--json"])
    envelope = json.loads(result.output)
    assert set(envelope) == {"generated", "jobs"}
    entries = scanned(envelope["jobs"], "status entries", least=len(JOBS))
    assert all(set(entry) == FIELDS for entry in entries)


def test_every_time_in_the_envelope_carries_its_offset(ledger):
    ledger.write_text(
        json.dumps(
            {"job": JOBS[0].key, "outcome": "ok", "started": "2026-11-04T11:00:00Z", "finished": "2026-11-04T11:00:05Z"}
        )
        + "\n",
        encoding="utf-8",
    )
    entries = scanned(status.jobs(datetime(2026, 11, 4, 12, tzinfo=UTC)), "status entries")
    stamps = [e[k] for e in entries for k in ("last_run", "next_run") if e[k]]
    assert scanned(stamps, "timestamps", least=2)
    assert all(datetime.fromisoformat(stamp.replace("Z", "+00:00")).tzinfo for stamp in stamps), stamps


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
