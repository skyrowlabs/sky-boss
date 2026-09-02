"""`sb job` — a schedule sky.boss issues and owns. See [[jobs]].

**systemd is the daemon; sky.boss generates units and reads them back.** Nothing
here holds a clock, stays resident, or supervises anything — the relationship
breeze.brain has to Docker. [[fundamentals]] § Cadence's *nothing of sky.boss's
own survives the last window* stays literally true: what survives is a `.timer`
file, owned by an init system that was already running.

**Nothing here parses a calendar syntax, in either direction.** A `schedule` is
handed to `systemd-analyze calendar` and a fire time is read back from
`systemctl --user list-timers`. [[schedule]]'s refusal to parse cron was never
about *reading* — it was about not owning semantics that belong to something
else, and that is unchanged on the writing side.

**`~/.config/systemd/user/` is shared space, not sky.boss's directory.** Five
foreign unit files sit in it on the machine this was written on. Every generated
unit is `sb-<name>.service` / `sb-<name>.timer`, and nothing here enumerates,
modifies, stops or reports on a unit outside that prefix — except to say that an
`sb-` unit with **no declaration behind it** exists, because that one still
fires.

**State is read back, never remembered.** Every cron manager that keeps a model
of what it installed is eventually wrong about it, silently. `sb job list` asks
systemd and compares.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import subprocess
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import rich_click as click

from cli.helpers import PROJECT_ROOT, SB_HOME, STATE_DIR, child_env
from cli.output import Result, emit
from cli.view import describe

JOBS_FILE = "jobs.toml"

# The keys a `[job.NAME]` table may declare. `argv` is the only required one: a
# job with no `schedule` is manual-only, which is a legitimate thing to declare
# and the state `sb job run` exists for.
JOB_KEYS = frozenset({"argv", "schedule", "lane", "timeout", "description"})
TOP_LEVEL_TABLES = frozenset({"job"})

# **This is a security check, not a tidiness one.** The name becomes a filename
# in `~/.config/systemd/user/`, so a name carrying a slash or a `..` writes
# outside the directory sky.boss is allowed to touch. Same shape a tool name
# takes, enforced here for a harder reason.
NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")

PREFIX = "sb-"


@dataclass
class Job:
    """One declared job. Operator-authored; sky.boss never writes this file."""

    name: str
    argv: list[str]
    schedule: str = ""
    lane: str = ""
    # **No default timeout, deliberately.** `CLAUDE.md` records what one costs:
    # a 60s `DEFAULT_TIMEOUT` killed any long run while `--timeout` was accepted
    # and then overridden — *wrong but looks right* in its purest form. An
    # agentic job may legitimately run for an hour, so a bound is declared by
    # whoever knows, or there is none.
    timeout: int = 0
    description: str = ""

    @property
    def service(self) -> str:
        return f"{PREFIX}{self.name}.service"

    @property
    def timer(self) -> str:
        return f"{PREFIX}{self.name}.timer"


def home_file(home: Path | None = None) -> Path:
    return (home or SB_HOME) / JOBS_FILE


def read(home: Path | None = None) -> dict:
    """The raw TOML, or an empty mapping.

    An absent file degrades to *nothing declared* rather than raising — the rule
    `tools.toml` and `projects.toml` are already read under. A fresh clone has
    no jobs and saying so every invocation is noise.
    """
    path = home_file(home)
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {"__error__": f"{path}: {exc}"}


def parse(raw: dict, commands: dict[str, bool] | None = None) -> tuple[list[Job], list[str]]:
    """Validate declarations. Pure — reads no file, runs nothing.

    **One bad entry must not cost the operator the other five**, and here that
    matters more than it does for a tool: a loader that raises on one malformed
    job takes down the whole schedule.
    """
    if "__error__" in raw:
        return [], [raw["__error__"]]

    jobs: list[Job] = []
    problems: list[str] = []

    for table in raw:
        if table in TOP_LEVEL_TABLES or table == "__error__":
            continue
        kind = "key" if not isinstance(raw[table], dict) else "table"
        problems.append(f"unknown {kind} {table!r} — ignored")

    for name, body in (raw.get("job") or {}).items():
        problem = _check(name, body, commands)
        if problem:
            problems.append(f"job {name!r}: {problem}")
            continue
        for key in body:
            if key not in JOB_KEYS:
                problems.append(f"job {name!r}: unknown key {key!r} — ignored")
        jobs.append(
            Job(
                name=name,
                argv=[str(part) for part in body["argv"]],
                schedule=str(body.get("schedule", "")),
                lane=str(body.get("lane", "")),
                timeout=int(body.get("timeout", 0)),
                description=str(body.get("description", "")),
            )
        )
    return jobs, problems


def _check(name: str, body, commands: dict[str, bool] | None) -> str | None:
    if not isinstance(body, dict):
        return "not a table"
    if not NAME.match(name):
        # See NAME: this one keeps a declaration from writing outside
        # `~/.config/systemd/user/`.
        return "name must be lowercase letters, digits and hyphens"
    argv = body.get("argv")
    if isinstance(argv, str):
        # **A shell string would give every job a shell**, with its globbing,
        # quoting and injection surface, for no benefit. Measured cost, inherited
        # from the design deleted in `051333c`.
        return "argv must be a list of strings, not a shell string"
    if not isinstance(argv, list) or not argv or not all(isinstance(p, str) for p in argv):
        return "argv must be a non-empty list of strings"
    if commands is not None and argv[0] not in commands:
        known = ", ".join(sorted(commands))
        return (
            f"argv must start with a sb command, not {argv[0]!r} — "
            f"one of {known}"
        )
    if "timeout" in body and not isinstance(body["timeout"], int):
        return "timeout must be a whole number of seconds"
    for key in ("schedule", "lane", "description"):
        if key in body and not isinstance(body[key], str):
            return f"{key} must be a string"
    return None


def load(home: Path | None = None) -> tuple[list[Job], list[str]]:
    from cli import cli as root
    from cli.tools import walk

    commands = {entry["name"]: entry["acts"] for entry in walk(root)}
    return parse(read(home), commands)


# ============================================================================
# Reading systemd back
# ============================================================================


def units_dir() -> Path:
    """Where a user unit lives. `XDG_CONFIG_HOME` is honoured because *systemd
    honours it* — this is the real standard, not a knob invented so the suite
    can redirect, which is also what makes the suite able to redirect it."""
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "systemd" / "user"


@dataclass
class Unit:
    """What systemd says about one of our units.

    `known` is the third answer, and it is the same one [[agent-sessions]]
    needed: no `systemctl` on this machine is *cannot tell*, not *nothing is
    installed*. Collapsing them would report a machine sky.boss cannot inspect
    as a machine with no jobs on it.
    """

    file: bool = False  # the unit file exists on disk
    enabled: str = ""  # UnitFileState, as systemd words it
    active: str = ""  # ActiveState, as systemd words it
    next_run: str = ""  # read back, never computed
    known: bool = True


def _systemctl(*args: str) -> tuple[str, bool]:
    """`systemctl --user …`, or `("", False)` when it cannot be asked.

    Never raises and never reports a failure as an empty answer: the boolean is
    *did this machine answer*, which the caller needs to keep `cannot tell`
    apart from `nothing`.
    """
    try:
        done = subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True,
            text=True,
            timeout=10,
            env=child_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return "", False
    return done.stdout, True


def timer_elapses() -> tuple[dict[str, str], bool]:
    """Next elapse per `sb-` timer, as systemd prints it. Never computed here."""
    out, asked = _systemctl("list-timers", "--all", "--no-pager", "--no-legend")
    if not asked:
        return {}, False
    found: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        unit = next((p for p in parts if p.startswith(PREFIX) and p.endswith(".timer")), "")
        if not unit:
            continue
        # Everything before the unit name is NEXT, LEFT, LAST, PASSED — four
        # fields systemd formats for humans. The next-elapse is the leading run
        # of them and `n/a` when there is none; taken verbatim rather than
        # reformatted, because a time sky.boss re-words is a time sky.boss owns.
        head = parts[: parts.index(unit)]
        found[unit] = " ".join(head[:4]) if head else ""
    return found, True


def unit_state(name: str, elapses: dict[str, str] | None = None) -> Unit:
    """One job's real state, asked of systemd and the filesystem."""
    job_timer = f"{PREFIX}{name}.timer"
    on_disk = (units_dir() / job_timer).exists()
    out, asked = _systemctl("show", job_timer, "-p", "UnitFileState", "-p", "ActiveState")
    if not asked:
        return Unit(file=on_disk, known=False)
    fields = dict(
        line.split("=", 1) for line in out.splitlines() if "=" in line
    )
    return Unit(
        file=on_disk,
        enabled=fields.get("UnitFileState", ""),
        active=fields.get("ActiveState", ""),
        next_run=(elapses or {}).get(job_timer, ""),
    )


def orphans(declared: set[str]) -> tuple[list[str], bool]:
    """`sb-` timers on disk with no declaration behind them.

    **The one case where a missing job is more dangerous than a broken one**:
    an orphan still fires, forever, and `jobs.toml` says nothing about it. This
    is the only reason anything here enumerates the shared directory, and it
    reads names only.
    """
    try:
        found = sorted(p.name for p in units_dir().glob(f"{PREFIX}*.timer"))
    except OSError:
        return [], False
    return [u for u in found if u[len(PREFIX) : -len(".timer")] not in declared], True


def state_of(job: Job, unit: Unit) -> str:
    """One word for what is true, and `drifted` is the one that earns this.

    Every other state is a fact about a file. `drifted` is a *disagreement* —
    between what the operator declared and what the machine will actually do —
    and it is the state a manager that trusts its own model can never report.
    """
    if not unit.known:
        return "unknown"
    if not unit.file:
        return "declared" if job.schedule else "manual"
    if not job.schedule:
        # A unit exists for a job that no longer asks to be scheduled.
        return "drifted"
    if unit.enabled in ("enabled", "enabled-runtime"):
        return "enabled"
    # On disk and not enabled: generated, or disabled outside sky.boss. Both are
    # the same fact and neither is an error — generating never enables.
    return "installed"


INLINE = ("name", "state", "schedule", "next", "lane")
HIDDEN = ("argv", "timeout", "description", "enabled", "active")


def rows_of(jobs: list[Job], states: dict[str, Unit]) -> list[dict]:
    import shlex

    rows = []
    for job in jobs:
        unit = states.get(job.name, Unit())
        rows.append(
            {
                "name": job.name,
                "state": state_of(job, unit),
                "schedule": job.schedule,
                "next": unit.next_run,
                "lane": job.lane,
                "argv": shlex.join(job.argv),
                "timeout": job.timeout,
                "description": job.description,
                "enabled": unit.enabled,
                "active": unit.active,
            }
        )
    return rows


def view_of(rows: list[dict]) -> dict:
    return {
        "columns": [describe(key, rows) for key in INLINE],
        "details": [],
        "hidden": list(HIDDEN),
        "authored": True,
    }


@click.group(name="job", invoke_without_command=True)
@click.pass_context
def job(ctx: click.Context) -> None:
    """Jobs sky.boss issues, and what systemd says about them.

        sb job
        sb job list

    An observe when run bare — it lists, and lists only. Declared in
    `$SB_HOME/jobs.toml`, which sky.boss reads and never writes. The
    subcommands that act say so themselves.
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(job_list)


@job.command(name="list")
@emit
def job_list() -> Result:
    """Every declared job, with the state systemd reports for it.

        sb job list

    An observe. State is **read back** rather than remembered: a job whose unit
    was disabled outside sky.boss, or whose definition has changed since it was
    installed, reads `drifted`.
    """
    result = Result()
    jobs, problems = load()
    for problem in problems:
        result.warn(problem)

    elapses, asked = timer_elapses()
    states = {j.name: unit_state(j.name, elapses) for j in jobs}

    found, listed = orphans({j.name for j in jobs})
    for unit in found:
        # Named loudly: this one is still firing and nothing declares it.
        result.warn(f"{unit} is installed with no declaration behind it — it still fires")
    if found:
        result.partial = True

    if not jobs:
        result.data = []
        if not problems and not found:
            result.warn(f"no jobs declared — see {home_file()}")
        return result

    if not asked:
        # Counting the looking: without systemctl every state is `unknown`, and
        # an unqualified table of them would read as *nothing is installed*.
        result.warn("systemctl --user did not answer — state and next-run are unknown")

    result.data = rows_of(jobs, states)
    result.view = view_of(result.data)
    return result


# ============================================================================
# Running one — the ledger, the lane, and the five outcomes
# ============================================================================

# **Five, not two.** `timeout` and `refused` are *recorded outcomes rather than
# exceptions*: with the ledger standing in for a notifier, a run that vanished
# without a line is indistinguishable from one that never happened. Inherited
# from the design deleted in `051333c`, which had already paid for this.
OUTCOMES = ("ok", "partial", "failed", "timeout", "refused")


def jobs_state() -> Path:
    """Where the ledger and the per-run logs live.

    `$SB_STATE`, not `$SB_HOME`: the home holds what the *operator wrote* and
    the state holds what the *machine did*. `rm -rf` on the state is a
    reasonable way to reset and must not delete a schedule.
    """
    return STATE_DIR / "jobs"


def ledger_path() -> Path:
    return jobs_state() / "ledger.jsonl"


def lane_lock(lane: str) -> Path:
    """The advisory lock file for a lane.

    `$XDG_RUNTIME_DIR` when there is one — a lock belongs to a boot, not to a
    machine, and a stale lock file surviving a reboot is a lane that can never
    be entered again. Falls back to the state directory where there is none.
    """
    base = os.environ.get("XDG_RUNTIME_DIR")
    root = (Path(base) / "sb") if base else (jobs_state() / "lanes")
    root.mkdir(parents=True, exist_ok=True)
    return root / f"lane-{lane}.lock"


def new_run_id(name: str) -> str:
    """`<job>-<utc>-<6 hex>`. The stamp makes it sortable and greppable; the
    suffix is what keeps two runs in the same second apart."""
    when = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{name}-{when}-{secrets.token_hex(3)}"


def append(record: dict, path: Path | None = None) -> None:
    """One JSON object, one line, one `write`, append-only.

    **Kept small on purpose.** A single `write` to an `O_APPEND` file is not
    atomic at arbitrary sizes — the workspace measured an 8 KB append tearing
    against a concurrent reader — and every reader of this file therefore has to
    tolerate a torn last line, which `sb data --from jsonl` already does. Small
    records make the tear rare; they do not make it impossible, and nothing here
    pretends otherwise.
    """
    target = path or ledger_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def sb_executable() -> str:
    """The wrapper, by absolute path.

    Absolute because a generated unit has no `PATH` worth relying on, and the
    same string is used here so a manual run and a timed run cannot execute two
    different sky.bosses.
    """
    return str(PROJECT_ROOT / "sb")


def execute(job: Job, log: Path) -> dict:
    """Run the job's argv, streaming its output into `log`. Never raises.

    **Output goes to a file, not into the envelope.** `sb run` carries what it
    printed because you typed that argv and seeing it is the feature; a job may
    print for an hour unattended, so the envelope carries the *record* and names
    where the bytes went.
    """
    log.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    argv = [sb_executable(), *job.argv]
    outcome, code = "ok", None
    try:
        with log.open("wb") as sink:
            done = subprocess.run(
                argv,
                stdout=sink,
                stderr=subprocess.STDOUT,
                # A declared bound or none. See `Job.timeout`.
                timeout=job.timeout or None,
                env=child_env(),
                cwd=str(Path.home()),
            )
        code = done.returncode
        # The envelope's own three codes, and this is where `partial` finally
        # does real work rather than being tidy: a wrapper branches on the exit
        # status without parsing a byte of output.
        outcome = {0: "ok", 3: "partial"}.get(code, "failed")
    except subprocess.TimeoutExpired:
        outcome = "timeout"
    except OSError as exc:
        # The binary could not start. A recorded outcome, not an exception.
        outcome = "failed"
        with log.open("a", encoding="utf-8") as sink:
            sink.write(f"could not start: {exc}\n")
    finished = datetime.now(timezone.utc)
    return {
        "started": started.isoformat(),
        "finished": finished.isoformat(),
        "duration_s": round((finished - started).total_seconds(), 3),
        "outcome": outcome,
        "exit": code,
    }


@job.command(name="run")
@click.argument("name")
@emit
def job_run(name: str) -> Result:
    """Run one job now, in the foreground.

        sb job run nightly

    **This acts** — it is the job's argv, run once. It takes the job's lane
    before starting and records `refused` if it cannot, so a manual run cannot
    overlap a timed one. Output goes to a log file beside the ledger and the
    envelope names it.
    """
    result = Result()
    jobs, problems = load()
    for problem in problems:
        result.warn(problem)

    found = next((j for j in jobs if j.name == name), None)
    if found is None:
        known = ", ".join(sorted(j.name for j in jobs))
        raise click.UsageError(
            f"no such job: {name}" + (f" (declared: {known})" if known else "")
        )

    run_id = new_run_id(found.name)
    log = jobs_state() / "logs" / f"{run_id}.log"
    record = {"job": found.name, "run_id": run_id, "lane": found.lane, "log": str(log)}

    handle = None
    if found.lane:
        # **Advisory, and non-blocking.** A job that cannot take its lane does
        # not wait — waiting turns a schedule into a queue, and a queue that
        # drains at 3am is a different feature nobody asked for.
        handle = lane_lock(found.lane).open("w")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            record |= {
                "started": datetime.now(timezone.utc).isoformat(),
                "finished": datetime.now(timezone.utc).isoformat(),
                "duration_s": 0,
                "outcome": "refused",
                "exit": None,
            }
            append(record)
            result.partial = True
            result.data = record
            result.warn(f"lane {found.lane!r} is busy — {found.name} did not run")
            return result

    try:
        record |= execute(found, log)
    finally:
        if handle is not None:
            handle.close()

    # Nothing runs unlogged, in any phase — including this one.
    append(record)
    result.data = record
    if record["outcome"] == "partial":
        result.partial = True
    elif record["outcome"] != "ok":
        result.ok = False
        result.warn(f"{found.name} {record['outcome']}" + (
            f" (exit {record['exit']})" if record["exit"] is not None else ""
        ))
    return result
