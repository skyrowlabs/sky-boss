"""Every registered job's standing: last result, how long ago, whether it is overdue, when it runs next.

One computation behind two readers, `dev report status --json` and the
`overnight` digest, so the two cannot disagree about a job. The envelope is
jam.sense's (`jam-sense@6cda3ca04`, `cli/report.py` `status --json`) cut to the
fields this registry can answer, because sky.boss reads that shape: registering
a tree with it is then a `projects.toml` entry rather than code.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.paths import TMP_DIR  # noqa: E402
from scripts.reporting import cron_schedule, run_ledger, shellout  # noqa: E402
from scripts.reporting.jobs import JOBS, SCHEDULE_TZ, _allowlisted, now_local, schedule_offset  # noqa: E402

#: Where `report cron --install` saves the crontab it replaces, named for the instant.
INSTALL_BACKUPS = TMP_DIR / "reporting"


def _crontab() -> str | None:
    """The live crontab; `""` when there is none or no cron at all; None when unreadable."""
    listed = shellout.run(["crontab", "-l"], capture_output=True, text=True)
    if listed.returncode == 0:
        return listed.stdout
    if listed.returncode == shellout.MISSING or "no crontab" in (listed.stderr or ""):
        return ""
    return None


def _installed_at() -> datetime | None:
    """When `report cron --install` last ran here, read from its newest backup's name."""
    stamps = [_instant(path.stem.removeprefix("crontab-")) for path in INSTALL_BACKUPS.glob("crontab-*.bak")]
    stamps = [stamp for stamp in stamps if stamp]
    return max(stamps, default=None)


def _instant(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        return datetime.strptime(stamp.replace("-", "").replace(":", ""), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _local(instant: datetime) -> datetime:
    return instant.astimezone(SCHEDULE_TZ).replace(tzinfo=None)


def _offset(local: datetime) -> str:
    """A schedule-clock time as ISO 8601 with its UTC offset, as the zone had it then."""
    return local.replace(tzinfo=SCHEDULE_TZ).isoformat()


def humanize_age(instant: datetime | None, now: datetime) -> str:
    if instant is None:
        return "never"
    seconds = int((now - instant).total_seconds())
    if seconds < 60:
        return "just now"
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return "just now"


def jobs(now: datetime | None = None) -> list[dict]:
    """One entry per registered job, in registry order."""
    now = now or datetime.now(UTC)
    local_now = _local(now) if now.tzinfo else now_local()
    off = _allowlisted()
    live = _crontab()
    installed_at = _installed_at()
    out = []
    for job in JOBS:
        last = run_ledger.last_run(job.key)
        finished = _instant(last.get("finished") if last else None)
        started = _instant(last.get("started") if last else None)
        # Every job starts this checkout's offset after its slot, so both fire times shift.
        delay = timedelta(minutes=schedule_offset())
        due = cron_schedule.previous_fire(job.cron, local_now - delay, job.first_week_only)
        upcoming = cron_schedule.next_fire(job.cron, local_now - delay, job.first_week_only)
        due, upcoming = (when + delay if when else None for when in (due, upcoming))
        intentionally_off = job.key in off
        # Absent from the crontab means it never runs, which outranks "overdue"; the
        # same needle `report cron --check` uses. None: the crontab could not be read.
        in_cron = None if live is None else job.needle() in live
        # A slot that passed before the block was installed is not a missed run.
        never_due = finished is None and due is not None and installed_at is not None and due < _local(installed_at)
        out.append(
            {
                "job": job.key,
                "cadence": job.cadence,
                "schedule": job.cron,
                "last_run": last.get("finished") if last else None,
                "last_age": humanize_age(finished, now),
                "result": last.get("outcome", "—") if last else "—",
                "duration_s": int((finished - started).total_seconds()) if finished and started else None,
                "overdue": bool(
                    not intentionally_off
                    and in_cron is not False
                    and not never_due
                    and due
                    and (finished is None or _local(finished) < due)
                ),
                "intentionally_off": intentionally_off,
                "scheduled_in_cron": in_cron,
                "unscheduled_reason": off.get(job.key),
                # With its offset: a consumer must not guess the zone (sky.boss refuses to).
                "next_run": None if intentionally_off or upcoming is None else _offset(upcoming),
            }
        )
    return out


def envelope(now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    return {"generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "jobs": jobs(now)}
