"""When a five-field cron schedule fires: the last fire before a moment, and the next one after.

`dev report status` needs both to say whether a job is overdue and when it runs
next. Stdlib only, and only the cron syntax this registry uses: `*`, numbers,
`a-b` ranges, `a,b` lists and `*/n` or `a-b/n` steps. Day-of-month and day-of-week
are ORed when both are restricted, as cron does. Times are naive and on the
schedule clock (`jobs.now_local`), because a crontab fires in local time.
"""

from __future__ import annotations

from datetime import datetime, timedelta

#: How far either search looks. A monthly job on a weekly lane (`first_week_only`)
#: can be five weeks from its next fire; past this the schedule is reported as unknown.
HORIZON = timedelta(days=40)

_BOUNDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def _field(spec: str, low: int, high: int) -> set[int]:
    values: set[int] = set()
    for part in spec.split(","):
        body, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if body == "*":
            start, stop = low, high
        elif "-" in body:
            start, stop = (int(x) for x in body.split("-", 1))
        else:
            start = stop = int(body)
        values.update(range(start, stop + 1, step))
    return values


def parse(cron: str) -> tuple[set[int], ...]:
    """The five fields as sets of allowed values; raises ValueError on anything else."""
    fields = cron.split()
    if len(fields) != 5:
        raise ValueError(f"{cron!r} is not five cron fields")
    sets = tuple(_field(spec, low, high) for spec, (low, high) in zip(fields, _BOUNDS, strict=True))
    minutes, hours, days, months, weekdays = sets
    if 7 in weekdays:
        weekdays.add(0)
    return minutes, hours, days, months, weekdays


def fires_at(cron: str, when: datetime) -> bool:
    minutes, hours, days, months, weekdays = parse(cron)
    if when.minute not in minutes or when.hour not in hours or when.month not in months:
        return False
    dom_any, dow_any = cron.split()[2] == "*", cron.split()[4] == "*"
    dom, dow = when.day in days, (when.weekday() + 1) % 7 in weekdays
    if dom_any or dow_any:
        return dom and dow
    return dom or dow


def _search(cron: str, start: datetime, direction: int, first_week_only: bool) -> datetime | None:
    minutes, hours = parse(cron)[:2]
    when = start.replace(second=0, microsecond=0)
    day = when.replace(hour=0, minute=0)
    stop = start + direction * HORIZON
    while (day <= stop) if direction > 0 else (day >= stop.replace(hour=0, minute=0)):
        for hour in sorted(hours, reverse=direction < 0):
            for minute in sorted(minutes, reverse=direction < 0):
                candidate = day.replace(hour=hour, minute=minute)
                if (candidate <= when) if direction > 0 else (candidate >= when):
                    continue
                if fires_at(cron, candidate) and (not first_week_only or candidate.day <= 7):
                    return candidate
        day += direction * timedelta(days=1)
    return None


def previous_fire(cron: str, before: datetime, first_week_only: bool = False) -> datetime | None:
    """The last time `cron` fired strictly before `before`, or None within the horizon."""
    return _search(cron, before, -1, first_week_only)


def next_fire(cron: str, after: datetime, first_week_only: bool = False) -> datetime | None:
    """The next time `cron` fires strictly after `after`, or None within the horizon."""
    return _search(cron, after, 1, first_week_only)
