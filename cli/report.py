"""``dev report`` — the scheduled-job surface.

Every subcommand here has a matching entry in ``scripts/reporting/jobs.py``, and
every entry there has a subcommand. ``tests/test_reporting_jobs.py`` asserts both
directions: a command nobody schedules and a cron line pointing at a command
that does not exist are both silent failures, and each has happened.
"""

from __future__ import annotations

import importlib
import json
import os
import sys

import click

from .helpers import PROJECT_ROOT, badge, detail, fail, line, ok, skip, warn

#: tests/test_cli_smoke.py runs this module's argument-less commands for real.
SMOKE_EXECUTES = True

sys.path.insert(0, str(PROJECT_ROOT))


@click.group()
def report() -> None:
    """Scheduled self-maintenance jobs."""


def _run_module(job_key: str) -> None:
    from scripts.reporting.jobs import JOBS_BY_KEY, in_first_week

    job = JOBS_BY_KEY[job_key]

    # Monthly jobs ride a weekly lane because cron ORs day-of-month against
    # day-of-week, so "first Sunday" is not expressible in cron fields. The gate
    # is enforced HERE, once, rather than in each monthly job.
    if job.first_week_only and not in_first_week():
        skip(f"{job_key}: monthly job, not the first week — skipping")
        sys.exit(0)

    module = importlib.import_module(f"scripts.reporting.{job.module}")
    sys.exit(module.main())


def _register() -> None:
    """Generate one subcommand per registry entry.

    Generated rather than hand-written on purpose: a hand-written list is a
    second registry, and the drift between two registries is exactly what this
    module exists to make impossible.
    """
    from scripts.reporting.jobs import JOBS

    for job in JOBS:

        def make(key: str, cadence: str, writes: str):
            @click.command(name=key, help=f"{cadence} — writes {writes}")
            @click.option("--dry-run", is_flag=True, help="run the deterministic stage only; record nothing")
            def command(dry_run: bool) -> None:
                if dry_run:
                    from scripts.reporting.agent_runner import DRY_RUN_ENV

                    os.environ[DRY_RUN_ENV] = "1"
                _run_module(key)

            return command

        report.add_command(make(job.key, job.cadence, job.writes))


_register()


@report.command()
@click.option("--print", "print_", is_flag=True, help="emit the block for `crontab -e`")
@click.option("--check", "check_", is_flag=True, help="does the LIVE crontab match the registry?")
@click.option("--install", "install", is_flag=True, help="replace this tree's block; keep every other line")
def cron(print_: bool, check_: bool, install: bool) -> None:
    """The crontab, generated from the registry."""
    from scripts.reporting.jobs import JOBS, SEAT_ENV, _allowlisted, crontab_block, host_zone_disagreement

    if print_ or not (check_ or install):
        click.echo(crontab_block())
        return

    from scripts.reporting import shellout

    listed = shellout.run(["crontab", "-l"], capture_output=True, text=True)
    if listed.returncode == shellout.MISSING:
        fail("this host has no `crontab` command, so nothing here is scheduled")
        detail("The registry is in scripts/reporting/jobs.py; install cron to run it unattended.")
        sys.exit(1)
    if listed.returncode != 0 and "no crontab" not in listed.stderr:
        fail(f"`crontab -l` failed: {listed.stderr.strip() or listed.returncode}")
        sys.exit(1)
    live = listed.stdout if listed.returncode == 0 else ""
    if install:
        _install(live)
        return
    exempt = _allowlisted()
    missing, off = [], []
    for job in JOBS:
        if job.key in exempt:
            off.append(f"{job.key}: off (intentional) — {exempt[job.key]}")
            continue
        # `job.needle()`, not a bare key: a crontab holds every project on the
        # machine, and a sibling repo's line for the same key read as ours.
        if job.needle() not in live:
            missing.append(job.key)

    for entry in off:
        skip(entry)

    if missing:
        fail(f"{len(missing)} registered job(s) are not in the live crontab: {', '.join(missing)}")
        detail()
        detail("'Registered' is not 'installed'. Install with:")
        detail("  dev report cron --install")
        detail("It replaces this tree's block and keeps every other line in your crontab.")
        detail()
        detail("If a job is deliberately off, give it a reason in")
        detail("scripts/reporting_schedule_allowlist.yaml — an unexplained gap reads")
        detail("identically to a job that silently stopped running.")
        sys.exit(1)

    # Unset resolves to the default seat and every job still reports ok, so absence
    # is the silent failure (jam.sense's REPORTING_SEAT); the generated block sets it.
    if not any(line.strip().startswith(f"{SEAT_ENV}=") for line in live.splitlines()):
        fail(f"the live crontab declares no {SEAT_ENV}, so no job here names the identity it runs as")
        detail("  dev report cron --install   # writes the block, which sets it")
        sys.exit(1)

    disagreement = host_zone_disagreement()
    if disagreement:
        fail(f"cron fires in this host's time, and it is not the schedule's: {disagreement}")
        detail("Set the host's zone, or SCHEDULE_TZ in scripts/reporting/jobs.py, so every fire time is true.")
        sys.exit(1)

    ok(f"the live crontab matches the registry ({len(JOBS) - len(off)} scheduled, {len(off)} intentionally off)")


def _install(live: str) -> None:
    """Write the merged crontab, after saving the one it replaces."""
    from datetime import UTC, datetime

    from scripts.paths import TMP_DIR
    from scripts.reporting import shellout
    from scripts.reporting.jobs import merged_crontab

    backup = TMP_DIR / "reporting" / f"crontab-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.bak"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(live, encoding="utf-8")
    merged = merged_crontab(live)
    wrote = shellout.run(["crontab", "-"], input=merged, capture_output=True, text=True)
    if wrote.returncode != 0:
        fail(f"`crontab -` refused the merged crontab: {wrote.stderr.strip()}")
        detail(f"Nothing changed. The live crontab is saved at {backup.relative_to(PROJECT_ROOT)}.")
        sys.exit(1)
    kept = len(live.splitlines())
    ok(f"installed this tree's block; {len(merged.splitlines())} lines now, from {kept}")
    detail(f"The crontab it replaced is at {backup.relative_to(PROJECT_ROOT)}.")


@report.command()
@click.option("--json", "as_json", is_flag=True, help="the machine envelope sky.boss reads")
def status(as_json: bool) -> None:
    """Every job: last result, how long ago, whether it is overdue, when it runs next."""
    from scripts.reporting import status as standing

    envelope = standing.envelope()
    if as_json:
        click.echo(json.dumps(envelope, indent=2))
        return
    for entry in envelope["jobs"]:
        if entry["intentionally_off"]:
            skip(f"{entry['job']:<14} off — {entry['unscheduled_reason']}")
            continue
        if entry["scheduled_in_cron"] is False:
            warn(f"{entry['job']:<14} NOT INSTALLED — it never runs until `report cron --install`")
            continue
        row = f"{entry['job']:<14} {entry['result']:<9} {entry['last_age']:<10} next {entry['next_run'] or '—'}"
        (warn if entry["overdue"] else ok)(row + ("  OVERDUE" if entry["overdue"] else ""))


@report.command()
@click.option("-n", "--limit", default=20, show_default=True)
def watch(limit: int) -> None:
    """Recent runs as a timeline: what ran, what it decided, and what it wrote."""
    from scripts.reporting import run_ledger
    from scripts.reporting.jobs import JOBS

    entries = run_ledger.recent(limit)
    if not entries:
        warn("no runs recorded yet")
        return

    # The symbols come from `scripts/output.py`. A viewer that spells its own
    # is a second vocabulary, and this one already disagreed with the runner's.
    for entry in entries:
        row = f"{badge(entry['outcome'])} {entry['started']}  {entry['job']:<16}"
        if entry.get("committed"):
            row += f"  → {entry['committed']}"
        if entry.get("reason"):
            row += f"  ({entry['reason'][:80]})"
        line(row)

    line()
    for job in JOBS:
        last = run_ledger.last_run(job.key)
        if last is None:
            warn(f"{job.key} has never run — scheduled {job.cadence}")
