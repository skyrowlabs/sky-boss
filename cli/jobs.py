"""tb auto — homebase job management.

Jobs are declared in `jobs/*.yaml`, run here, and recorded to a durable ledger
outside the repo. With no notifier yet, **that ledger is the notification
surface**, so nothing runs unlogged — failures, timeouts and refusals to start
all leave a record.

This manages homebase jobs only. jam.sense keeps its own scheduler; see
CLAUDE.md § Boundary.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import rich_click as click
import yaml

from cli.helpers import PROJECT_ROOT, STATE_DIR, TB_HOME
from cli.output import Result, emit

JOBS_DIR = TB_HOME / "jobs"
JOB_STATE_DIR = STATE_DIR / "jobs"
LEDGER = JOB_STATE_DIR / "ledger.jsonl"
LOG_DIR = JOB_STATE_DIR / "logs"

LANES = ("read-only", "committing")
DEFAULT_TIMEOUT = 600

# Job exit codes carry the same meaning as tb's own — which is the point of
# giving `partial` its own code. A job exiting 3 means "something needs
# attention" without anything having to parse its output.
OUTCOME_BY_EXIT = {0: "ok", 1: "failed", 3: "partial"}

UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
UNIT_PREFIX = "tb-"

# Bare systemd shorthands pass straight through; anything else is translated and
# then handed to systemd-analyze, which is the only authority worth trusting on
# calendar syntax.
BARE_SCHEDULES = ("hourly", "daily", "weekly", "monthly", "yearly")
_DAILY_AT = re.compile(r"^daily\s+(\d{1,2}):(\d{2})$")
_WEEKLY_AT = re.compile(r"^weekly\s+([A-Za-z]{3})\s+(\d{1,2}):(\d{2})$")


class JobError(ValueError):
    """A job definition that cannot be loaded. Always names the file."""


@dataclass(frozen=True)
class Job:
    name: str
    run: list[str]
    lane: str
    description: str = ""
    timeout: int = DEFAULT_TIMEOUT
    schedule: str | None = None
    # Command-line fragments that must not be running when this job starts.
    # Cron jobs are not systemd units, so nothing can mutex against them; this
    # is the one guard tb can apply unilaterally.
    avoid: tuple[str, ...] = ()
    source: Path | None = None

    @property
    def installed(self) -> bool:
        """Whether a generated systemd timer exists for this job (Phase 3)."""
        return (Path.home() / ".config/systemd/user" / f"tb-{self.name}.timer").exists()


def parse_job(data: object, source: Path) -> Job:
    """Validate one definition. Every error names the file and the problem."""
    where = source.name

    if not isinstance(data, dict):
        raise JobError(f"{where}: expected a mapping at the top level")

    name = data.get("name")
    if not name or not isinstance(name, str):
        raise JobError(f"{where}: 'name' is required and must be a string")
    if name != source.stem:
        raise JobError(f"{where}: 'name' is {name!r} but the filename says {source.stem!r}")
    # A colon is legal in a Linux filename, so the `adhoc:` prefix `tb run`
    # synthesizes is only a reserved namespace if this refuses it. Without the
    # check, `jobs/adhoc:echo.yaml` would sit in the ledger indistinguishable
    # from an ad-hoc run of the same name.
    if ":" in name:
        raise JobError(f"{where}: 'name' may not contain ':' — reserved for ad-hoc runs")

    run = data.get("run")
    if not isinstance(run, list) or not run or not all(isinstance(a, str) for a in run):
        raise JobError(f"{where}: 'run' must be a non-empty list of strings (argv, not a shell line)")
    # `tb run` is itself a ledger-writing verb, so a definition that invokes it
    # records the same execution twice — once for the outer runner and once for
    # the inner one — and the durations nest misleadingly. Definitions name leaf
    # verbs.
    if len(run) >= 2 and Path(run[0]).name == "tb" and run[1] == "run":
        raise JobError(
            f"{where}: 'run' must not invoke 'tb run' — it would write the ledger twice. "
            "Name the leaf verb the job actually does."
        )

    lane = data.get("lane")
    if lane not in LANES:
        raise JobError(f"{where}: 'lane' must be one of {', '.join(LANES)} (got {lane!r})")

    timeout = data.get("timeout", DEFAULT_TIMEOUT)
    if not isinstance(timeout, int) or timeout <= 0:
        raise JobError(f"{where}: 'timeout' must be a positive integer of seconds")

    schedule = data.get("schedule")
    if schedule is not None and not isinstance(schedule, str):
        raise JobError(f"{where}: 'schedule' must be a string when present")

    avoid = data.get("avoid", [])
    if not isinstance(avoid, list) or not all(isinstance(a, str) for a in avoid):
        raise JobError(f"{where}: 'avoid' must be a list of command-line fragments")

    return Job(
        name=name,
        run=list(run),
        lane=lane,
        description=str(data.get("description") or "").strip(),
        timeout=timeout,
        schedule=schedule,
        avoid=tuple(avoid),
        source=source,
    )


def load_jobs(directory: Path | None = None) -> tuple[dict[str, Job], list[str]]:
    """Every job definition, plus one message per file that failed to load.

    A malformed file does not prevent the others from loading — one bad
    definition must not hide the whole schedule.
    """
    directory = directory or JOBS_DIR
    jobs: dict[str, Job] = {}
    problems: list[str] = []

    if not directory.exists():
        return jobs, problems

    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            jobs[path.stem] = parse_job(yaml.safe_load(path.read_text()), path)
        except JobError as exc:
            problems.append(str(exc))
        except yaml.YAMLError as exc:
            problems.append(f"{path.name}: not valid YAML ({exc.__class__.__name__})")

    return jobs, problems


# ============================================================================
# Running
# ============================================================================


def _now() -> datetime:
    return datetime.now(timezone.utc)


def append_ledger(entry: dict, ledger: Path | None = None) -> None:
    """One JSON object per line, opened for append.

    Append-only and line-sized on purpose: a run killed mid-write can lose its
    own line but never corrupt the ones before it.
    """
    ledger = ledger or LEDGER
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
        handle.flush()


def run_job(job: Job, state_dir: Path | None = None, lock_path: Path | None = None) -> dict:
    """Run a job to completion and record it. Always records.

    A job that times out, cannot start, or loses its lane is a recorded outcome
    rather than an exception — the ledger is the notification surface, and
    silence in it must never mean "fine".
    """
    state_dir = state_dir or JOB_STATE_DIR
    log_dir = state_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    started = _now()
    run_id = f"{job.name}-{started:%Y%m%dT%H%M%S}-{started.microsecond // 1000:03d}"
    log_path = log_dir / f"{run_id}.log"

    began = time.monotonic()
    exit_code: int | None = None
    output = ""

    blocking = [p for pattern in job.avoid for p in matching_processes(pattern)]

    with lane_lock(job.lane, lock_path) as acquired:
        if blocking:
            outcome = "skipped"
            output = "did not start; matched an avoid pattern:\n" + "\n".join(blocking)
        elif not acquired:
            outcome = "skipped"
            output = f"lane {job.lane!r} is busy; did not start"
        else:
            try:
                proc = subprocess.run(
                    job.run, capture_output=True, text=True, timeout=job.timeout, check=False
                )
                exit_code = proc.returncode
                output = (proc.stdout or "") + (proc.stderr or "")
                outcome = OUTCOME_BY_EXIT.get(exit_code, "failed")
            except subprocess.TimeoutExpired as exc:
                outcome = "timeout"
                output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            except (OSError, FileNotFoundError) as exc:
                # Could not start at all — a missing binary, usually. Still a run.
                outcome = "refused"
                output = f"could not start: {exc}"

    duration = round(time.monotonic() - began, 3)
    log_path.write_text(output)

    entry = {
        "run_id": run_id,
        "job": job.name,
        "lane": job.lane,
        "started": started.isoformat(),
        "duration_s": duration,
        "exit": exit_code,
        "outcome": outcome,
        "log": str(log_path),
        "command": job.run,
    }
    append_ledger(entry, state_dir / "ledger.jsonl")
    return entry


def _summary(description: str, width: int = 56) -> str | None:
    """First line, truncated. A listing is a listing, not documentation."""
    if not description:
        return None
    first = description.strip().splitlines()[0].strip()
    return first if len(first) <= width else first[: width - 1].rstrip() + "\u2026"


def tail_text(text: str, count: int = 10) -> str:
    """Last lines of a run's output, as one newline-joined string.

    A string rather than a list: the renderer joins a list of strings with
    commas, which turns captured log output into an unreadable blob. Newlines
    are what log output actually is.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-count:])


# ============================================================================
# Lanes — mutual exclusion, enforced here rather than by systemd
# ============================================================================


def lane_lock_path(lane: str) -> Path:
    """Per-lane lock file, on tmpfs so it cannot outlive a reboot.

    A stale lock file that survives a crash would silently wedge a lane forever,
    which is the worst failure mode available to a mutex.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return Path(runtime) / f"tb-lane-{lane}.lock"


@contextmanager
def lane_lock(lane: str, path: Path | None = None):
    """Advisory, non-blocking. Yields True if the lane was ours to take.

    Non-blocking on purpose: a job that waits its turn silently is a job whose
    schedule is now a lie. Skipping and recording it is the honest outcome.
    """
    path = path or lane_lock_path(lane)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w")
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()


# ============================================================================
# Unit generation
# ============================================================================


def to_oncalendar(schedule: str) -> str:
    """A job schedule as a systemd OnCalendar expression.

    Validated by `systemd-analyze calendar`, not by a parser of ours — calendar
    syntax is systemd's to define, and reimplementing it would drift.
    """
    text = schedule.strip()
    lowered = text.lower()

    if lowered in BARE_SCHEDULES:
        expression = lowered
    elif (match := _DAILY_AT.match(lowered)):
        expression = f"*-*-* {int(match.group(1)):02d}:{match.group(2)}:00"
    elif (match := _WEEKLY_AT.match(lowered)):
        day = match.group(1).capitalize()
        expression = f"{day} *-*-* {int(match.group(2)):02d}:{match.group(3)}:00"
    else:
        # Assume it is already an OnCalendar expression; systemd will say.
        expression = text

    probe = subprocess.run(
        ["systemd-analyze", "calendar", expression],
        capture_output=True, text=True, check=False,
    )
    if probe.returncode != 0:
        raise JobError(f"schedule {schedule!r} is not a valid systemd calendar expression")
    return expression


def resolve_exec(run: list[str]) -> str:
    """ExecStart line with an absolute program path.

    systemd user units get a minimal PATH that does not include ~/.local/bin, so
    a bare `tb` would simply not be found at 6am with nobody watching.
    """
    program = shutil.which(run[0])
    if program is None:
        raise JobError(f"cannot find {run[0]!r} on PATH — systemd units need an absolute path")
    return " ".join([program, *(shlex.quote(arg) for arg in run[1:])])


def unit_files(job: Job) -> tuple[str, str]:
    """The .service and .timer text for a job."""
    if not job.schedule:
        raise JobError(f"{job.name}: cannot install a job with no schedule")

    exec_start = resolve_exec(job.run)
    oncalendar = to_oncalendar(job.schedule)
    # A unit Description is a one-liner; a folded YAML block is not.
    description = _summary(job.description, width=72) or job.name

    service = f"""# Generated by tb — do not edit. Source: jobs/{job.name}.yaml
[Unit]
Description=tackle-box job: {description}

[Service]
Type=oneshot
ExecStart={exec_start}
TimeoutStartSec={job.timeout}
WorkingDirectory={PROJECT_ROOT}
"""

    timer = f"""# Generated by tb — do not edit. Source: jobs/{job.name}.yaml
[Unit]
Description=tackle-box timer: {description}

[Timer]
OnCalendar={oncalendar}
# Run a missed job once the machine is back, rather than skipping the day.
Persistent=true

[Install]
WantedBy=timers.target
"""
    return service, timer


def _unit_names(name: str) -> tuple[str, str]:
    return f"{UNIT_PREFIX}{name}.service", f"{UNIT_PREFIX}{name}.timer"


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *args], capture_output=True, text=True, check=False
    )


def install_job(job: Job, unit_dir: Path | None = None, enable: bool = True) -> dict:
    """Write and enable a job's units.

    Only ever writes paths under the `tb-` prefix. `~/.config/systemd/user/` is
    shared space — this machine already has arch-update.timer and
    openclaw-gateway.service in it.
    """
    unit_dir = unit_dir or UNIT_DIR
    service_name, timer_name = _unit_names(job.name)
    service_text, timer_text = unit_files(job)

    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / service_name).write_text(service_text)
    (unit_dir / timer_name).write_text(timer_text)

    enabled = False
    if enable:
        _systemctl("daemon-reload")
        enabled = _systemctl("enable", "--now", timer_name).returncode == 0

    return {"job": job.name, "service": service_name, "timer": timer_name, "enabled": enabled}


def uninstall_job(name: str, unit_dir: Path | None = None, disable: bool = True) -> dict:
    """Remove a job's units. Refuses anything outside the tb- prefix."""
    unit_dir = unit_dir or UNIT_DIR
    service_name, timer_name = _unit_names(name)

    for unit in (service_name, timer_name):
        if not unit.startswith(UNIT_PREFIX):  # unreachable by construction; kept as a guard
            raise JobError(f"refusing to touch {unit}: not a tb-generated unit")

    if disable:
        _systemctl("disable", "--now", timer_name)

    removed = []
    for unit in (timer_name, service_name):
        path = unit_dir / unit
        if path.exists():
            path.unlink()
            removed.append(unit)

    if disable and removed:
        _systemctl("daemon-reload")

    return {"job": name, "removed": removed}


# ============================================================================
# Reserved windows — jam.sense's crontab, read-only
# ============================================================================

# How close counts as a collision. Advisory and deliberately generous: several
# jam.sense jobs run for minutes, one for the better part of an hour.
COLLISION_MINUTES = 30
ELAPSE_ITERATIONS = 8

_ELAPSE = re.compile(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}):\d{2}")


def _cron_field(field: str, low: int, high: int) -> set[int] | None:
    """One cron field as the set of values it matches, or None if unparseable."""
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            part, _, step_text = part.partition("/")
            if not step_text.isdigit():
                return None
            step = int(step_text)
        if part in ("*", ""):
            start, end = low, high
        elif "-" in part:
            begin, _, finish = part.partition("-")
            if not (begin.isdigit() and finish.isdigit()):
                return None
            start, end = int(begin), int(finish)
        elif part.isdigit():
            start = end = int(part)
        else:
            return None
        values.update(v for v in range(start, end + 1) if (v - start) % step == 0)
    return {v for v in values if low <= v <= high} or None


@dataclass(frozen=True)
class CronWindow:
    minutes: set[int]
    hours: set[int]
    weekdays: set[int]      # cron numbering, 0 and 7 both Sunday
    command: str
    raw: str


def parse_crontab(text: str) -> tuple[list[CronWindow], list[str]]:
    """Foreign cron entries as reserved windows, plus anything unparseable.

    Unparseable entries are surfaced rather than dropped: silently ignoring one
    would claim coverage this does not have.
    """
    windows: list[CronWindow] = []
    unreadable: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split(None, 5)
        if len(fields) < 6:
            unreadable.append(stripped[:60])
            continue
        minute, hour, _dom, _month, dow, command = fields[:6]
        minutes = _cron_field(minute, 0, 59)
        hours = _cron_field(hour, 0, 23)
        weekdays = _cron_field(dow, 0, 7)
        if not (minutes and hours and weekdays):
            unreadable.append(stripped[:60])
            continue
        windows.append(CronWindow(minutes, hours, {d % 7 for d in weekdays}, command, stripped[:60]))

    return windows, unreadable


def read_crontab() -> tuple[list[CronWindow], list[str]]:
    """The user's crontab, read-only. tb never writes it."""
    probe = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
    if probe.returncode != 0:
        return [], []
    return parse_crontab(probe.stdout)


def next_elapses(oncalendar: str, iterations: int = ELAPSE_ITERATIONS) -> list[datetime]:
    """Upcoming run times, from systemd rather than from a calendar of ours."""
    probe = subprocess.run(
        ["systemd-analyze", "calendar", f"--iterations={iterations}", oncalendar],
        capture_output=True, text=True, check=False,
    )
    if probe.returncode != 0:
        return []
    return [
        datetime.strptime(f"{date} {clock}", "%Y-%m-%d %H:%M")
        for date, clock in _ELAPSE.findall(probe.stdout)
    ]


def collisions(oncalendar: str, windows: list[CronWindow],
               minutes: int = COLLISION_MINUTES) -> list[dict]:
    """Where a schedule lands inside somebody else's window.

    Advisory only. systemd `Conflicts=` cannot mutex against cron, because cron
    jobs are not units — so this warns at schedule time and nothing enforces it
    at run time.
    """
    found: list[dict] = []
    for elapse in next_elapses(oncalendar):
        # cron weekday: Sunday is 0; Python's weekday(): Monday is 0.
        weekday = (elapse.weekday() + 1) % 7
        for window in windows:
            if weekday not in window.weekdays:
                continue
            for hour in window.hours:
                for minute in window.minutes:
                    delta = abs((hour * 60 + minute) - (elapse.hour * 60 + elapse.minute))
                    if min(delta, 1440 - delta) <= minutes:
                        found.append({
                            "at": elapse.strftime("%a %H:%M"),
                            "clashes_with": f"{hour:02d}:{minute:02d}",
                            "command": window.command[:60],
                        })
                        break
                else:
                    continue
                break
    # one row per distinct clash
    unique = {(f["at"], f["clashes_with"]): f for f in found}
    return list(unique.values())


# ============================================================================
# Runtime guard
# ============================================================================


def _ancestor_pids() -> set[int]:
    pids: set[int] = set()
    pid = os.getpid()
    while pid > 1 and pid not in pids:
        pids.add(pid)
        try:
            status = Path(f"/proc/{pid}/status").read_text()
            line = next(l for l in status.splitlines() if l.startswith("PPid:"))
            pid = int(line.split()[1])
        except (OSError, StopIteration, ValueError):
            break
    return pids


def matching_processes(pattern: str) -> list[str]:
    """Running processes whose command line contains `pattern`.

    Implemented over /proc rather than with `pgrep -f`, and excluding this
    process and its ancestors. A naive `pgrep -f 'jam report'` matches the shell
    running the check — verified on this machine, where it reported a match with
    nothing of the sort running.
    """
    exclude = _ancestor_pids()
    found: list[str] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) in exclude:
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        cmdline = raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
        if cmdline and pattern in cmdline:
            found.append(cmdline[:100])
    return found


# ============================================================================
# Reading the ledger — with no notifier, this is the notification surface
# ============================================================================

# How overdue is judged before a schedule parser exists (Phase 3). Generous on
# purpose: a job flagged overdue an hour early is noise, and noise is how a
# pull-based surface gets ignored.
PERIOD_SECONDS = {"hourly": 3600, "daily": 86400, "weekly": 604800, "monthly": 2592000}
OVERDUE_FACTOR = 1.5

# Worst first. The point of a pull surface is that the thing needing attention
# is the first thing you see.
SEVERITY = {
    "failed": 0,
    "refused": 0,
    "timeout": 0,
    "overdue": 1,
    "partial": 2,
    "skipped": 3,
    "never": 4,
    "ok": 5,
}

_DURATION = re.compile(r"^(\d+)\s*([smhdw])$")


UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}


def parse_duration(text: str) -> timedelta:
    """`24h`, `7d`, `30m` into a timedelta."""
    match = _DURATION.match(text.strip().lower())
    if not match:
        raise ValueError(f"could not read {text!r} as a duration — try 30m, 24h, 7d")
    amount, unit = int(match.group(1)), match.group(2)
    return timedelta(**{UNITS[unit]: amount})


def read_ledger(state_dir: Path | None = None) -> list[dict]:
    """Every ledger entry, oldest first.

    Malformed lines are skipped rather than fatal. A run killed mid-write can
    leave a truncated last line, and one bad line must not cost you the history.
    """
    ledger = (state_dir or JOB_STATE_DIR) / "ledger.jsonl"
    if not ledger.exists():
        return []

    entries = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and entry.get("job"):
            entries.append(entry)
    return entries


def humanize_age(when: datetime, now: datetime | None = None) -> str:
    seconds = int(((now or _now()) - when).total_seconds())
    if seconds < 60:
        return "just now"
    for limit, divisor, unit in ((3600, 60, "m"), (86400, 3600, "h"), (604800, 86400, "d")):
        if seconds < limit:
            return f"{seconds // divisor}{unit} ago"
    return f"{seconds // 604800}w ago"


def _parse_started(entry: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(entry["started"])
    except (KeyError, ValueError, TypeError):
        return None


def last_runs(entries: list[dict]) -> dict[str, dict]:
    """The most recent entry per job."""
    latest: dict[str, dict] = {}
    for entry in entries:
        latest[entry["job"]] = entry
    return latest


def is_overdue(job: Job, last: dict | None, now: datetime | None = None) -> bool:
    """A job whose schedule has clearly been missed.

    Silence must never look like success: an unscheduled job cannot be overdue,
    but a scheduled one that has never run is.
    """
    if not job.schedule:
        return False
    period = next(
        (secs for word, secs in PERIOD_SECONDS.items() if job.schedule.lower().startswith(word)),
        None,
    )
    if period is None:
        return False
    if last is None:
        return True
    started = _parse_started(last)
    if started is None:
        return True
    return ((now or _now()) - started).total_seconds() > period * OVERDUE_FACTOR


def job_status(job: Job, last: dict | None, now: datetime | None = None) -> dict:
    """One row for `tb auto status`.

    `ok` is True only for a clean, current run. A job that has never run reads
    as never-run, and one that missed its schedule reads as overdue — neither
    is allowed to look like success.
    """
    overdue = is_overdue(job, last, now)

    if last is None:
        state, ok = "never", None
        detail = "scheduled but never run" if overdue else "never run"
        if overdue:
            state, ok = "overdue", False
    else:
        outcome = last.get("outcome", "failed")
        started = _parse_started(last)
        age = humanize_age(started, now) if started else "unknown"
        if overdue:
            state, ok = "overdue", False
            detail = f"last ran {age} ({outcome})"
        else:
            state = outcome
            # `skipped` is neither pass nor fail: the lane was busy, which is the
            # mutex working. Repeated skipping is visible in the log, not here.
            ok = True if outcome == "ok" else (None if outcome == "skipped" else False)
            detail = age if outcome == "ok" else f"{outcome} · {age}"

    return {
        "job": job.name,
        "ok": ok,
        "detail": detail,
        "state": state,
        "last_run": last.get("started") if last else None,
    }


def prune(state_dir: Path | None = None, keep_per_job: int = 50) -> dict:
    """Trim the ledger and remove orphaned log files.

    Explicit, never automatic: this is the surface that stands in for
    notification, and quietly deleting it on a schedule nobody asked for is how
    it would lose the run you needed.
    """
    state_dir = state_dir or JOB_STATE_DIR
    entries = read_ledger(state_dir)

    kept: list[dict] = []
    seen: dict[str, int] = {}
    for entry in reversed(entries):
        name = entry["job"]
        seen[name] = seen.get(name, 0) + 1
        if seen[name] <= keep_per_job:
            kept.append(entry)
    kept.reverse()

    ledger = state_dir / "ledger.jsonl"
    if len(kept) != len(entries):
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("".join(json.dumps(e) + "\n" for e in kept), encoding="utf-8")

    referenced = {Path(e["log"]).name for e in kept if e.get("log")}
    removed_logs = 0
    log_dir = state_dir / "logs"
    if log_dir.exists():
        for path in log_dir.glob("*.log"):
            if path.name not in referenced:
                path.unlink()
                removed_logs += 1

    return {
        "entries_before": len(entries),
        "entries_kept": len(kept),
        "logs_removed": removed_logs,
    }


# ============================================================================
# Commands
# ============================================================================


@click.group()
def auto() -> None:
    """Homebase jobs — deterministic and agentic."""


@auto.command(name="list")
@emit
def list_jobs() -> Result:
    """Every declared job."""
    jobs, problems = load_jobs()
    result = Result()
    for problem in problems:
        result.degrade(problem)

    result.data = [
        {
            "job": job.name,
            "lane": job.lane,
            "schedule": job.schedule,
            "installed": job.installed,
            "description": _summary(job.description),
        }
        for job in sorted(jobs.values(), key=lambda j: j.name)
    ]
    return result


# `tb auto run` lived here. It moved to `tb run <job>`: running a job is the
# imperative mood over it, and `auto` is the declarative one. See
# docs/features/command-taxonomy.md.


@auto.command()
@emit
def status() -> Result:
    """Last outcome per job, worst first.

    With no notifier, this is the command that answers what a notification
    would have — so silence never reads as success.
    """
    jobs, problems = load_jobs()
    result = Result()
    for problem in problems:
        result.degrade(problem)

    latest = last_runs(read_ledger())
    rows = [job_status(job, latest.get(name)) for name, job in jobs.items()]
    rows.sort(key=lambda r: (SEVERITY.get(r["state"], 0), r["job"]))

    for row in rows:
        if row["ok"] is False:
            result.degrade(f"{row['job']}: {row['detail']}")

    result.data = rows
    return result


@auto.command()
@click.argument("name")
@click.option("--limit", default=10, show_default=True, help="How many runs to show.")
@click.option("--run", "run_id", default=None, metavar="ID", help="Show one run's captured output.")
@emit
def log(name: str, limit: int, run_id: str | None) -> Result:
    """Recent runs of a job, most recent first."""
    entries = [e for e in read_ledger() if e["job"] == name]
    if not entries:
        return Result(ok=False, data={"error": f"no recorded runs for {name!r}"})

    if run_id:
        match = next((e for e in entries if e["run_id"] == run_id), None)
        if match is None:
            return Result(ok=False, data={"error": f"no run {run_id!r} for {name!r}"})
        path = Path(match["log"])
        if not path.exists():
            return Result(ok=False, data={"error": f"log file is gone: {path}"})
        return Result(data=path.read_text().rstrip() or "(no output)")

    rows = []
    for entry in reversed(entries[-limit:]):
        started = _parse_started(entry)
        rows.append({
            "run": entry["run_id"],
            "ok": entry.get("outcome") == "ok",
            "detail": f"{entry.get('outcome')} · {humanize_age(started) if started else '?'}"
                      f" · {entry.get('duration_s')}s",
        })
    return Result(data=rows)


@auto.command()
@click.argument("window", default="24h")
@emit
def since(window: str) -> Result:
    """Every run across all jobs in a window — the overnight view."""
    try:
        delta = parse_duration(window)
    except ValueError as exc:
        return Result(ok=False, data={"error": str(exc)})

    cutoff = _now() - delta
    rows = []
    for entry in read_ledger():
        started = _parse_started(entry)
        if started is None or started < cutoff:
            continue
        rows.append({
            "job": entry["job"],
            "ok": entry.get("outcome") == "ok",
            "detail": f"{entry.get('outcome')} · {humanize_age(started)} · {entry.get('duration_s')}s",
        })
    rows.reverse()

    result = Result(data=rows)
    failures = [r for r in rows if not r["ok"]]
    for row in failures:
        result.degrade(f"{row['job']}: {row['detail']}")
    if not rows:
        result.data = f"no runs in the last {window}"
    return result


@auto.command(name="prune")
@click.option("--keep", default=50, show_default=True, help="Runs to keep per job.")
@emit
def prune_cmd(keep: int) -> Result:
    """Trim the ledger and remove orphaned log files."""
    return Result(data=prune(keep_per_job=keep))


@auto.command()
@click.argument("name")
@click.option("--no-enable", is_flag=True, help="Write the units but do not enable the timer.")
@emit
def install(name: str, no_enable: bool) -> Result:
    """Generate and enable this job's systemd user units."""
    jobs, _ = load_jobs()
    if name not in jobs:
        return Result(ok=False, data={"error": f"no job named {name!r}",
                                      "known": ", ".join(sorted(jobs)) or "none declared"})
    job = jobs[name]
    try:
        oncalendar = to_oncalendar(job.schedule) if job.schedule else None
        installed = install_job(job, enable=not no_enable)
    except JobError as exc:
        return Result(ok=False, data={"error": str(exc)})

    result = Result(data=installed)
    if oncalendar:
        found, _ = read_crontab()
        clashes = collisions(oncalendar, found)
        for clash in clashes:
            # Advisory: systemd cannot mutex against cron, because cron jobs are
            # not units. The warning is the whole mechanism.
            result.degrade(
                f"{clash['at']} lands within {COLLISION_MINUTES}m of a cron job at "
                f"{clash['clashes_with']} ({clash['command'][:40]})"
            )
        installed["collisions"] = len(clashes)
    return result


@auto.command()
@click.argument("name")
@emit
def uninstall(name: str) -> Result:
    """Disable and remove this job's systemd user units."""
    result = uninstall_job(name)
    if not result["removed"]:
        return Result(ok=False, data={"error": f"no installed units for {name!r}"})
    return Result(data=result)


@auto.command()
@emit
def windows() -> Result:
    """Reserved windows from the crontab — read-only, never written.

    jam.sense's entries are somebody else's schedule. tb derives them so it can
    avoid landing on top of them, and touches nothing.
    """
    found, unreadable = read_crontab()
    result = Result()
    for line in unreadable:
        result.degrade(f"could not read crontab entry: {line}")

    rows = []
    for window in found:
        times = sorted(f"{h:02d}:{m:02d}" for h in window.hours for m in window.minutes)
        rows.append({
            "at": ", ".join(times[:4]) + ("…" if len(times) > 4 else ""),
            "days": "daily" if len(window.weekdays) == 7 else ",".join(
                "SunMonTueWedThuFriSat"[d * 3:d * 3 + 3] for d in sorted(window.weekdays)
            ),
            "command": window.command[:52],
        })
    result.data = rows
    return result
