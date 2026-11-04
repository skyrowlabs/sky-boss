"""Every registered job's standing: last result, how long ago, whether it is overdue, when it runs next.

One computation behind two readers, `dev report status --json` and the
`overnight` digest, so the two cannot disagree about a job. The envelope is
jam.sense's (`jam-sense@6cda3ca04`, `cli/report.py` `status --json`) cut to the
fields this registry can answer, because sky.boss reads that shape: registering
a tree with it is then a `projects.toml` entry rather than code.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reporting import cron_schedule, run_ledger  # noqa: E402
from scripts.reporting.jobs import JOBS, SCHEDULE_TZ, _allowlisted, now_local  # noqa: E402


def _instant(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
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
    out = []
    for job in JOBS:
        last = run_ledger.last_run(job.key)
        finished = _instant(last.get("finished") if last else None)
        started = _instant(last.get("started") if last else None)
        due = cron_schedule.previous_fire(job.cron, local_now, job.first_week_only)
        upcoming = cron_schedule.next_fire(job.cron, local_now, job.first_week_only)
        intentionally_off = job.key in off
        out.append(
            {
                "job": job.key,
                "cadence": job.cadence,
                "schedule": job.cron,
                "last_run": last.get("finished") if last else None,
                "last_age": humanize_age(finished, now),
                "result": last.get("outcome", "—") if last else "—",
                "duration_s": int((finished - started).total_seconds()) if finished and started else None,
                "overdue": bool(not intentionally_off and due and (finished is None or _local(finished) < due)),
                "intentionally_off": intentionally_off,
                "unscheduled_reason": off.get(job.key),
                # With its offset: a consumer must not guess the zone (sky.boss refuses to).
                "next_run": None if intentionally_off or upcoming is None else _offset(upcoming),
            }
        )
    return out


def envelope(now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    return {"generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "jobs": jobs(now)}
