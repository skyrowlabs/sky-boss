"""The job registry — one source of truth for schedule, identity and autonomy.

Three things are derived from this module and therefore cannot drift apart: the
crontab, the `dev report` subcommands, and the status viewer. Before it existed,
the schedule was a hand-maintained string living several hundred lines from the
functions it described, and forgetting one half was silent — a command nobody
schedules, or a cron line pointing at a subcommand that does not exist.

`tests/test_reporting_jobs.py` asserts the registry and the CLI agree in both
directions.

## The grid is load-bearing, not cosmetic

Two rules generate it:

1. **Only one committing job may be in flight at a time.** Nearly every job
   spawns a headless agent that edits and commits the same git tree, and several
   regenerate the same derived docs. Run concurrently, they race on git and on
   those files. Jobs that commit nothing may share a window.

2. **Weekly work is partitioned by weekday, not packed into one night.** A lane
   per weekday, sized at several times the observed run length. The margin is
   the point: a block sized to today's runtime is a bet that runtime never
   grows, and it leaves no room for the next job.

Adjacency within a night is deliberate too — whichever job regenerates a shared
index last wins, so the one whose pass should include the other's edits goes
second.

The nightly spine is a **pipeline**: agents commit, then a gate job checks what
they committed, then a repair job fixes what the gate found, then a digest
reports the night as a closed set. Ordering the heavy agents *after* the gates
would leave every agent commit ungated until the following night.

Stdlib only — imported by host-side jobs that must not grow dependencies.
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import allowlist  # noqa: E402
from scripts.paths import PROJECT_ROOT, SCRIPTS_DIR  # noqa: E402

#: Where every cron line appends its raw output. The structured per-run outcome
#: lives in the ledger; this is the transcript.
CRON_LOG = "tmp/reporting/cron.log"

#: Deliberate "do not schedule this" decisions, with reasons.
SCHEDULE_ALLOWLIST = SCRIPTS_DIR / "reporting_schedule_allowlist.yaml"

#: The repo path used in generated crontab lines.
#:
#: Derived, never baked in at scaffold time. A literal absolute path is wrong
#: the moment the repo is cloned or moved somewhere else — and cron fails
#: silently, so nobody finds out until a report stops arriving. It also made
#: `black` red on arrival for anyone whose checkout path was long enough to
#: push the assignment past the line limit.
CRON_CWD = str(PROJECT_ROOT)

#: Minutes every job here waits after its cron slot. Every checkout on a host
#: shares one crontab, so trees with the same registry would all start at the same
#: minute; the default spreads them by a hash of this checkout's path, which
#: keeps the order of this tree's own jobs. Set an int to pin it; 0 turns it off.
SCHEDULE_OFFSET_PINNED: int | None = None
OFFSET_SPAN_MINUTES = 30


def schedule_offset() -> int:
    """This checkout's delay after every cron slot, in minutes."""
    if SCHEDULE_OFFSET_PINNED is not None:
        return SCHEDULE_OFFSET_PINNED
    return int(hashlib.sha256(CRON_CWD.encode()).hexdigest(), 16) % OFFSET_SPAN_MINUTES


@dataclass(frozen=True)
class Seat:
    """An identity a job's agent runs as: whose Claude account it bills, whose GitHub it acts as."""

    name: str
    what: str
    credential_env: str | None = None  # holds a `claude setup-token` token; None is the ambient login
    gh_token_env: str | None = None  # holds a GitHub token for `gh` and pushes; None is gh's own login


#: Every identity a job may run as. `personal` is whoever is logged into `claude`
#: and `gh` here. An automation seat is a row naming the variables its tokens
#: live in, e.g. `Seat("team", "the automation seat", "TEAM_CLAUDE_TOKEN", "TEAM_GH_TOKEN")`,
#: each declared in .env.example and marked `# secret`.
SEATS = (Seat("personal", "whoever is logged into `claude` and `gh` on this host"),)

#: Which seat a run uses. The cron block sets it to CRON_SEAT; unset is DEFAULT_SEAT.
SEAT_ENV = "SB_SEAT"
DEFAULT_SEAT = "personal"
#: The seat scheduled jobs run as, written into the generated cron block.
CRON_SEAT = "personal"


class SeatError(ValueError):
    """A seat that is unknown, or named with no credential to run it."""


def resolve_seat(env: Mapping[str, str] | None = None) -> Seat:
    """The seat a run started now would use; a typo raises rather than billing `personal`."""
    raw = ((os.environ if env is None else env).get(SEAT_ENV) or DEFAULT_SEAT).strip().lower()
    for seat in SEATS:
        if seat.name == raw:
            return seat
    raise SeatError(f"{SEAT_ENV}={raw!r} is not a seat; expected one of {', '.join(s.name for s in SEATS)}")


def seat_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """The variables that make a child process run as the resolved seat; raises SeatError.

    A seat naming a credential that is unset refuses: falling through to the
    ambient login would bill somebody else and still report ok.
    """
    source = os.environ if env is None else env
    seat = resolve_seat(source)
    out = {}
    for var, child in ((seat.credential_env, "CLAUDE_CODE_OAUTH_TOKEN"), (seat.gh_token_env, "GH_TOKEN")):
        if var is None:
            continue
        if not source.get(var):
            raise SeatError(f"seat {seat.name!r} needs {var}, and it is unset")
        out[child] = source[var]
    return out


#: The timezone every schedule here is expressed in.
#:
#: These describe the HOST's crontab, which fires in the host's local time — so
#: the fire times are local-calendar facts and must not be re-expressed in UTC:
#: they would drift from the cron lines they describe, and drift again by an
#: hour at each DST transition.
#:
#: What they must not be is *implicitly* local. A bare `datetime.now()` means
#: "whatever timezone this machine is in", which is this zone on the host and
#: **UTC** on a CI runner — which is how a whole test file can pass locally and
#: fail in CI for thirteen hours every Saturday. Naming the zone makes the
#: answer identical everywhere, and zoneinfo handles DST.
#:
#: Instants — log stamps, `generated:` fields, staleness — stay UTC and
#: tz-aware. This constant is only for wall-clock schedule arithmetic.
SCHEDULE_TZ = ZoneInfo("America/Chicago")


def now_local() -> datetime:
    """Now on the schedule clock — naive, and identical on every machine."""
    return datetime.now(SCHEDULE_TZ).replace(tzinfo=None)


def host_zone_disagreement(now: datetime | None = None) -> str | None:
    """Why this host's clock is not SCHEDULE_TZ's, or None when every offset agrees.

    Cron fires in host time and every schedule here is read in SCHEDULE_TZ, so a
    host in another zone runs each job at a time nothing here reports. Checked now
    and half a year on, since two zones can agree until one changes for DST.
    """
    now = now or datetime.now(UTC)
    for instant in (now, now + timedelta(days=182)):
        host, ours = instant.astimezone().utcoffset(), instant.astimezone(SCHEDULE_TZ).utcoffset()
        if host != ours:
            zone = f"{SCHEDULE_TZ.key} (UTC{_hours(ours)})"
            return f"on {instant:%Y-%m-%d} this host is UTC{_hours(host)} and the schedule is {zone}"
    return None


def _hours(offset: timedelta | None) -> str:
    minutes = int((offset or timedelta()).total_seconds() // 60)
    return f"{'+' if minutes >= 0 else '-'}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


#: What a job is allowed to repair without asking.
#:
#: It defaults to `none`, deliberately: a job added without thinking about blast
#: radius gets NO autonomy rather than inheriting whatever the entry above it
#: had. Widening this is a decision, and it should read like one.
FIX_POLICIES = {
    "none": "reports only; never writes to the repo",
    "own-report": "may write and commit its own report file, nothing else",
    "docs": "may repair generated docs and commit them",
    "code": "may open a pull request; never merges, never pushes to a protected branch",
}

#: Where a job's findings go when it neither fixes them nor rules them out.
#:
#: A report nobody acts on re-derives the same finding every edition: jam.sense's
#: `M-9` sat through ten (`jam-sense@a4894a3ac`). Declared, never inferred —
#: `fix_policy` is what a job may change, which is a different question.
#: `tests/test_reporting_jobs.py` holds every report-writing job to one of these.
SINK_QUEUE = "queue"  # filed with `dev bug`/`task`, attributed and capped per job
SINK_READER = "reader"  # somebody reads the report; `Job.reader` names who, and how often
SINK_NONE = "no-findings"  # the job reports facts and never a finding
SINKS = (SINK_QUEUE, SINK_READER, SINK_NONE)


@dataclass(frozen=True)
class Job:
    """One scheduled job."""

    key: str  # `dev report <key>`
    module: str  # scripts/reporting/<module>.py
    cadence: str  # human-readable, for the docs table
    cron: str  # five cron fields
    writes: str  # what artifact it produces, or "—"
    fix_policy: str = "none"
    commits: bool = False  # does it touch the git tree?
    first_week_only: bool = False  # monthly jobs ride a weekly lane; see below
    heartbeat_var: str | None = None  # env var holding its dead-man-switch URL
    findings_sink: str | None = None  # one of SINKS, for a job that writes a report
    reader: str = ""  # for SINK_READER: who reads it, and how often
    #: False for a job with no agent stage at all; only then may it record `ok`
    #: without one, because `run_ledger` otherwise reads that as a stopped job.
    agent: bool = True

    def needle(self) -> str:
        """What identifies THIS tree's line for this job in a live crontab.

        A crontab is per-user, not per-repository: every project on the machine
        has its lines in the same file. `report cron --check` matched a bare
        `report <key>` against all of `crontab -l`, so a sibling repo running
        the same job key reported ours installed — a green check whose whole
        purpose is to catch a job that is registered and not installed.

        Not `command()` either, which is the other obvious answer and is too
        strict: it pins the redirect, so anybody who sent the log somewhere
        else, or added a flag, gets told their working crontab is missing the
        job. A check that cries wolf about a working crontab gets deleted, and
        then the class it was catching comes back.

        The directory and the wrapper name are what make a line ours, and they
        are the two things a user has no reason to edit. `command()` builds on
        this rather than repeating it — the failure above was one question
        asked in two places, and a second copy here would be the same bug.
        """
        return f"cd {CRON_CWD} && ./dev report {self.key}"

    def command(self) -> str:
        offset = schedule_offset()
        delay = f"sleep {offset * 60} && " if offset else ""
        return f"{delay}{self.needle()} >> {CRON_LOG} 2>&1"

    def cron_line(self) -> str:
        return f"{self.cron} {self.command()}"


#: Monthly jobs take a weekly lane plus `first_week_only`, rather than a
#: `0 0 1 * *` schedule. cron ORs day-of-month against day-of-week, so "first
#: Sunday" is not expressible in cron fields at all, and a bare day-of-month
#: schedule lands on a weekly lane one month in seven. The gate is enforced once,
#: in the runner.
def in_first_week(when: datetime | None = None) -> bool:
    return (when or now_local()).day <= 7


#: Every entry ships its module, prompt and heartbeat variable, because a
#: registry naming modules that do not exist is red on arrival. `repo-report` is
#: the worked example to copy. The two drainers work the capture lanes in
#: `scripts/lanes.py` (one issue each per run, a draft pull request each) and ship
#: switched off in `reporting_schedule_allowlist.yaml`; `overnight` reports on
#: the night, every night, with no agent.
#:
#: Add the rest by copying this shape. `docs/AGENTIC_AUTOMATION.md` § Adding a
#: job lists the five places a new entry touches; `tests/test_reporting_jobs.py`
#: fails if you miss one.
JOBS: list[Job] = [
    Job(
        key="repo-report",
        module="repo_report",
        cadence="Sat 22:00",
        cron="0 22 * * 6",
        writes="docs/reports/regular/repository-report.md",
        fix_policy="own-report",
        commits=True,
        heartbeat_var="HEARTBEAT_REPO_REPORT",
        findings_sink=SINK_QUEUE,
    ),
    Job(
        key="agent-task",
        module="agent_task",
        cadence="nightly 02:15",
        cron="15 2 * * *",
        writes="—",
        fix_policy="code",
        commits=True,
        heartbeat_var="HEARTBEAT_AGENT_TASK",
    ),
    Job(
        key="agent-fix",
        module="agent_fix",
        cadence="nightly 03:15",
        cron="15 3 * * *",
        writes="—",
        fix_policy="code",
        commits=True,
        heartbeat_var="HEARTBEAT_AGENT_FIX",
    ),
    Job(
        key="dep-migrate",
        module="dep_migrate",
        cadence="nightly 04:15",
        cron="15 4 * * *",
        writes="—",
        fix_policy="code",
        commits=True,
        heartbeat_var="HEARTBEAT_DEP_MIGRATE",
    ),
    Job(
        key="overnight",
        module="overnight",
        cadence="nightly 06:30",
        cron="30 6 * * *",
        writes="tmp/reporting/overnight.md",
        heartbeat_var="HEARTBEAT_OVERNIGHT",
        findings_sink=SINK_NONE,
        agent=False,
    ),
]

#: Tools a job's agent may use beyond the tree's allow rules, by job key: Claude's
#: `--allowedTools` patterns, added to the default agent command only. For a tree whose
#: rules are narrower than a job needs (stash-flow); a key no job has fails the suite.
AGENT_TOOLS: dict[str, tuple[str, ...]] = {}

#: Jobs whose runner pushes their commit to the base branch, once it has passed
#: `check pre-push`, when it touches only the job's `writes` file. Off unless a tree
#: adds the key: it writes to that branch unattended, on this host's credentials.
AUTO_PUSH: set[str] = set()

#: **Add your own jobs, and any grant, as an append, in the space between the two
#: frozen rules at the end of this section.** An entry edited into the list above is a
#: change beside every entry a release adds, so it conflicts; an append does not.
#: skeletor's own tree is the first to need it.
#:
#:     JOBS += [Job(key="nightly-check", module="nightly_check", cadence="nightly 01:00", cron="0 1 * * *", writes="—")]
#:     AGENT_TOOLS["repo-report"] = ("Bash(./dev docs *)",)
#:     AUTO_PUSH.add("repo-report")


# ── Extending JOBS ───────────────────────────────────────────────────────────
#
# **Put every append to JOBS, and any comment you write about it, in the space
# between the two frozen rules at the bottom of this block.** skeletor ships that
# space empty and never adds a line to it; `scripts/paths.py` records why there
# are two rules and what the space buys.
#
# ── Nothing below this line is skeletor's ────────────────────────────────────
#
# Everything of yours goes between this rule and the closing one below: appends,
# and any prose you write about them. Both rules are frozen — skeletor does not
# rewrite either block and renders nothing between them, so your insertion point
# is never adjacent to a template line that a release might edit. The
# explanation above IS ordinary prose and does get rewritten, which is why the
# rule sits at the bottom of it rather than at the top.

# Publishes the weekly report to `develop`, so it does not sit local until someone pushes it.
AUTO_PUSH.add("repo-report")


# ── Skeletor's again below this line ─────────────────────────────────────────
#
# The space is bounded on both sides for the reason `scripts/paths.py` measures:
# this file carries template-owned code further down, and one rule alone would
# have certified all of it as yours.

JOBS_BY_KEY: dict[str, Job] = {job.key: job for job in JOBS}


def _allowlisted() -> dict[str, str]:
    """Jobs deliberately registered but NOT scheduled, with their reasons.

    Read through `scripts/allowlist.py`, the one reader every allowlist in this
    repository shares. There were four copies of this parsing and they drifted.
    """
    return allowlist.read(SCHEDULE_ALLOWLIST)


#: The generated block's delimiters, which is what lets an install replace it in place.
BLOCK_BEGIN = "# ── BEGIN generated by"
BLOCK_END = "# ── END generated"


def crontab_block() -> str:
    """The crontab block, generated. Never hand-copy this into `crontab -e`
    from the docs — the registry is the system; the docs table is documentation
    of it, and only one of the two can be wrong without anybody noticing."""
    exempt = _allowlisted()
    lines = [
        f"{BLOCK_BEGIN} `dev report cron --print` ──",
        "# Do not hand-edit. Regenerate after any change to scripts/reporting/jobs.py.",
        "SHELL=/bin/bash",
        # cron does not give you your login PATH. A job that works in your shell
        # and not under cron is almost always this, and it fails by not finding
        # the interpreter — which reads as a broken job rather than a broken PATH.
        f"PATH={os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin')}",
        # The identity every job below runs as; `report cron --check` requires it.
        f"{SEAT_ENV}={CRON_SEAT}",
        f"# Each job starts {schedule_offset()} min after its slot (this checkout's offset).",
        "",
    ]
    for job in JOBS:
        if job.key in exempt:
            lines.append(f"# {job.key}: OFF — {exempt[job.key]}")
            continue
        lines.append(f"# {job.key} — {job.cadence} — {job.writes}")
        lines.append(job.cron_line())
    lines.append(f"{BLOCK_END} ──")
    return "\n".join(lines) + "\n"


def merged_crontab(live: str) -> str:
    """`live` with this tree's block replaced by today's, and every other line kept.

    A crontab is per user, so it holds other projects' lines: piping the block
    into `crontab -` deleted all of them, and the advice said to (skyrow-workspace,
    on a 303-line crontab). A block is this tree's when a line in it runs from
    `CRON_CWD`, so a sibling tree with the same CLI name keeps its own. A stray
    line of ours outside any block is dropped, since the block re-adds it.
    """
    ours = f"cd {CRON_CWD} && ./dev report "
    kept: list[str] = []
    block: list[str] | None = None
    placed = False
    for line in live.splitlines():
        if block is None and line.startswith(BLOCK_BEGIN):
            block = [line]
        elif block is not None:
            block.append(line)
            if line.startswith(BLOCK_END):
                if any(ours in entry for entry in block):
                    kept += [] if placed else crontab_block().splitlines()
                    placed = True
                else:
                    kept += block
                block = None
        elif ours not in line:
            kept.append(line)
    kept += block or []
    if not placed:
        kept += crontab_block().splitlines()
    return "\n".join(kept) + "\n"
