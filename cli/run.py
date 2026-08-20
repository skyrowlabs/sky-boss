"""tb run — the imperative mood, and the only door that writes.

Three things reach the ledger through here:

* ``tb run <job>``            a definition from ``jobs/*.yaml``
* ``tb run <task>``           an internal task — tb's own code, registered below
* ``tb run --lane L -- argv`` ad-hoc work, which gets a lane like anything else

All three take a lane lock, land in the ledger, and write a log. That uniformity
is the point: if the only way to change state is this command, then nothing can
change state without leaving a record, and the MCP allowlist collapses from a
maintained list into a single gated verb.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import rich_click as click

from cli.home import init_home
from cli.jobs import (
    JOB_STATE_DIR,
    LANES,
    Job,
    _now,
    append_ledger,
    lane_lock,
    load_jobs,
    run_job,
    tail_text,
)
from cli.output import Result, emit, exit_code


@dataclass(frozen=True)
class Task:
    """An internal task — a write that lives in tb rather than in a subprocess.

    Deliberately has no ``timeout``. A timeout bounds a *foreign* process whose
    runtime you cannot know. An internal task is tb's own code with a known
    runtime, and the writes it performs are the kind you least want interrupted:
    `rewrite_derived` does textual surgery on a YAML file, and a SIGALRM halfway
    through leaves the inventory truncated. Letting it finish is strictly safer
    than bounding it.
    """

    name: str
    summary: str
    lane: str
    run: Callable[[], Result]


REGISTRY: tuple[Task, ...] = (
    Task("init-home", "Create TB_HOME and seed it with templates", "committing", init_home),
)


def _task(name: str) -> Task | None:
    return next((t for t in REGISTRY if t.name == name), None)


def run_task(task: Task, state_dir: Path | None = None, lock_path: Path | None = None) -> dict:
    """Run an internal task, recording it exactly as a subprocess job is recorded.

    Same ledger shape and the same lane. A consumer reading the ledger should not
    have to care whether the work happened in tb or in a child process.
    """
    state_dir = state_dir or JOB_STATE_DIR
    log_dir = state_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    started = _now()
    run_id = f"{task.name}-{started:%Y%m%dT%H%M%S}-{started.microsecond // 1000:03d}"
    log_path = log_dir / f"{run_id}.log"

    began = time.monotonic()
    code: int | None = None
    output = ""

    with lane_lock(task.lane, lock_path) as acquired:
        if not acquired:
            outcome = "skipped"
            output = f"lane {task.lane!r} is busy; did not start"
        else:
            try:
                result = task.run()
                code = exit_code(result)
                # The envelope is the artifact worth keeping — it is what the
                # command would have printed, and it stays greppable.
                output = json.dumps(result.to_dict(), indent=2, default=str)
                outcome = {0: "ok", 1: "failed", 3: "partial"}.get(code, "failed")
            except Exception as exc:  # noqa: BLE001 — a crashed task is a recorded outcome
                outcome = "failed"
                output = f"{exc.__class__.__name__}: {exc}"

    entry = {
        "run_id": run_id,
        "job": task.name,
        "lane": task.lane,
        "started": started.isoformat(),
        "duration_s": round(time.monotonic() - began, 3),
        "exit": code,
        "outcome": outcome,
        "log": str(log_path),
        "command": ["<internal>", task.name],
    }
    log_path.write_text(output)
    append_ledger(entry, state_dir / "ledger.jsonl")
    return entry


def adhoc_job(argv: list[str], lane: str, timeout: int) -> Job:
    """Wrap loose argv in a Job so it goes through exactly one code path.

    The synthesized name carries the `adhoc:` prefix so `tb auto since` shows
    these alongside defined jobs without ever colliding with one — a job name
    must match its filename stem, and a colon cannot appear there.
    """
    return Job(name=f"adhoc:{Path(argv[0]).name}", run=list(argv), lane=lane, timeout=timeout)


def _outcome_result(name: str, entry: dict, lane: str) -> Result:
    """Shared tail: map a ledger entry onto the envelope and exit code."""
    outcome = entry["outcome"]
    result = Result(ok=outcome in {"ok", "partial", "skipped"})

    if outcome == "partial":
        result.partial = True
        result.warn(f"{name}: exited 3 — something needs attention")
    elif outcome == "skipped":
        result.partial = True
        result.warn(f"{name}: lane {lane!r} was busy — did not run")
    elif outcome != "ok":
        result.warn(f"{name}: {outcome}")

    data = dict(entry)
    if outcome != "ok":
        # Show why without making anyone open the log.
        data["tail"] = tail_text(Path(entry["log"]).read_text())
    result.data = data
    return result


def _catalogue() -> Result:
    """What `tb run` with no target can do."""
    jobs, _ = load_jobs()
    rows = [{"target": n, "kind": "job", "lane": j.lane} for n, j in sorted(jobs.items())]
    rows += [{"target": t.name, "kind": "task", "lane": t.lane} for t in REGISTRY]
    return Result(data=rows)


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("target", nargs=-1, type=click.UNPROCESSED)
@click.option(
    "--lane",
    type=click.Choice(sorted(LANES)),
    help="Run loose argv as an ad-hoc job in this lane. Required for ad-hoc work.",
)
@click.option("--timeout", type=int, default=900, show_default=True, help="Ad-hoc timeout, seconds.")
@emit
def run(target: tuple[str, ...], lane: str | None, timeout: int) -> Result:
    """Run a job, an internal task, or ad-hoc work — always through the ledger.

    Exits with the work's own meaning: 0 ok, 3 partial, 1 failed.
    """
    if not target:
        return _catalogue()

    # `--lane` is what selects ad-hoc mode, rather than a bare `--` separator.
    # Click consumes `--`, so it cannot be detected reliably; and requiring an
    # explicit lane is the right rule anyway. The entire value of routing loose
    # argv through tb is the lane lock, and guessing "read-only" for an arbitrary
    # command is precisely the wrong default — it is the guess that lets an
    # ad-hoc migration run underneath a committing job.
    if lane is not None:
        job = adhoc_job(list(target), lane, timeout)
        return _outcome_result(job.name, run_job(job), lane)

    if len(target) > 1:
        return Result(
            ok=False,
            data={
                "error": "a job or task name takes no arguments",
                "hint": "for ad-hoc work name the lane: tb run --lane read-only -- " + " ".join(target),
            },
        )

    name = target[0]

    task = _task(name)
    if task is not None:
        return _outcome_result(name, run_task(task), task.lane)

    jobs, _ = load_jobs()
    if name in jobs:
        return _outcome_result(name, run_job(jobs[name]), jobs[name].lane)

    known = ", ".join(sorted([*jobs, *(t.name for t in REGISTRY)])) or "none declared"
    return Result(ok=False, data={"error": f"no job or task named {name!r}", "known": known})
