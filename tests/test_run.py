"""tb run — the one door that writes.

The property under test is uniformity: a defined job, an internal task, and
loose argv must all take a lane, land in the ledger, and produce a log. If any
of the three can skip that, the "nothing changes state without a record" claim
in docs/features/done/command-taxonomy.md is false.
"""

import json

import pytest
from click.testing import CliRunner

from cli import cli
from cli.jobs import Job, JobError, lane_lock, parse_job
from cli.output import Result
from cli.run import REGISTRY, Task, adhoc_job, run_task


def _envelope(res):
    return json.loads(res.stdout)


# ---------------------------------------------------------------- dispatch


def test_no_target_lists_jobs_and_tasks(tb_home):
    """Both kinds, because `tb run <target>` dispatches by name across both.

    The job side has to be seeded: definitions are the operator's and live
    outside the repo now, so with an empty home there is nothing but tasks and
    this would pass for the wrong reason.
    """
    jobs = tb_home / "jobs"
    jobs.mkdir(parents=True, exist_ok=True)
    (jobs / "seeded.yaml").write_text(
        "name: seeded\nrun: [echo, hi]\nlane: read-only\n"
    )
    try:
        res = CliRunner().invoke(cli, ["--json", "run"])
        kinds = {row["kind"] for row in _envelope(res)["data"]}
        assert kinds == {"job", "task"}
    finally:
        (jobs / "seeded.yaml").unlink()


def test_unknown_target_names_what_is_known():
    res = CliRunner().invoke(cli, ["--json", "run", "nosuchthing"])
    data = _envelope(res)["data"]

    assert _envelope(res)["ok"] is False
    assert res.exit_code == 1
    assert "asset-refresh" in data["known"], "tasks are listed, not just jobs"


def test_loose_argv_without_a_lane_is_refused_with_the_fix():
    """Ad-hoc work must name its lane, and the error has to say so.

    Guessing a lane is the failure this prevents: a default of read-only would
    let an ad-hoc migration run underneath a committing job.
    """
    res = CliRunner().invoke(cli, ["--json", "run", "echo", "hello"])
    data = _envelope(res)["data"]

    assert _envelope(res)["ok"] is False
    assert "--lane" in data["hint"]


# ---------------------------------------------------------------- ad-hoc


def test_adhoc_name_cannot_collide_with_a_job_name():
    """`adhoc:` is a reserved namespace, and parse_job is what reserves it.

    A colon is perfectly legal in a Linux filename, so `jobs/adhoc:echo.yaml`
    would otherwise load fine and sit in the ledger indistinguishable from an
    ad-hoc run of the same name.
    """
    from pathlib import Path

    job = adhoc_job(["/usr/bin/echo", "hi"], "read-only", 30)
    assert job.name == "adhoc:echo"

    with pytest.raises(JobError, match="reserved for ad-hoc"):
        parse_job({"name": job.name, "run": ["true"], "lane": "read-only"},
                  Path("adhoc:echo.yaml"))


def test_adhoc_run_is_recorded_like_any_job(tmp_path):
    from cli.jobs import run_job

    entry = run_job(adhoc_job(["true"], "read-only", 30), state_dir=tmp_path,
                    lock_path=tmp_path / "lane.lock")

    assert entry["outcome"] == "ok"
    assert entry["lane"] == "read-only"
    ledger = [json.loads(x) for x in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert ledger[-1]["job"] == "adhoc:true"


# ---------------------------------------------------------------- tasks


def test_every_registered_task_runs_with_no_arguments():
    """The runner invokes tasks with no arguments; a task needing one breaks at runtime."""
    for task in REGISTRY:
        assert task.lane in {"read-only", "committing"}
        assert callable(task.run)


def test_task_is_recorded_with_the_same_ledger_shape(tmp_path):
    task = Task("fake", "", "read-only", lambda: Result(data={"did": "work"}))
    entry = run_task(task, state_dir=tmp_path, lock_path=tmp_path / "lane.lock")

    assert entry["outcome"] == "ok"
    assert entry["exit"] == 0
    assert entry["command"] == ["<internal>", "fake"]
    assert set(entry) == {"run_id", "job", "lane", "started", "duration_s",
                          "exit", "outcome", "log", "command"}, "same shape as a subprocess job"


def test_task_returning_partial_records_partial(tmp_path):
    def _partial():
        r = Result(data={})
        r.degrade("something drifted")
        return r

    entry = run_task(Task("fake", "", "read-only", _partial), state_dir=tmp_path,
                     lock_path=tmp_path / "lane.lock")
    assert entry["outcome"] == "partial"
    assert entry["exit"] == 3


def test_a_crashing_task_is_recorded_not_raised(tmp_path):
    """Silence in the ledger must never mean "fine" — including when tb's own code breaks."""
    def _boom():
        raise RuntimeError("write failed halfway")

    entry = run_task(Task("fake", "", "committing", _boom), state_dir=tmp_path,
                     lock_path=tmp_path / "lane.lock")

    assert entry["outcome"] == "failed"
    assert "write failed halfway" in (tmp_path / "logs" / f"{entry['run_id']}.log").read_text()


def test_a_task_cannot_jump_a_busy_lane(tmp_path):
    lock = tmp_path / "lane.lock"
    ran = []
    task = Task("fake", "", "committing", lambda: ran.append(1) or Result())

    with lane_lock("committing", lock) as held:
        assert held
        entry = run_task(task, state_dir=tmp_path, lock_path=lock)

    assert entry["outcome"] == "skipped"
    assert ran == [], "the task body must not have run"


# ---------------------------------------------------------------- the guard


def test_a_definition_may_not_invoke_tb_run():
    """`tb run` writes the ledger itself, so a job invoking it records twice."""
    from pathlib import Path

    with pytest.raises(JobError, match="ledger twice"):
        parse_job(
            {"name": "loop", "run": ["tb", "run", "asset-refresh"], "lane": "read-only"},
            Path("loop.yaml"),
        )


def test_the_guard_survives_an_absolute_path_to_tb():
    from pathlib import Path

    with pytest.raises(JobError, match="ledger twice"):
        parse_job(
            {"name": "loop", "run": ["/home/you/.local/bin/tb", "run", "x"], "lane": "read-only"},
            Path("loop.yaml"),
        )


def test_no_definition_can_invoke_tb_run(tmp_path):
    """The rule is enforced at parse time, which is the only place it can be.

    This used to load the repo's own job files and check they obeyed it. Those
    files are the operator's now and live outside the repo, so the repo cannot
    vouch for them — and a test that read them would depend on whose machine
    it ran on. Parse time is where the rule actually lives.
    """
    import yaml

    from cli.jobs import JobError, parse_job

    path = tmp_path / "recursive.yaml"
    with pytest.raises(JobError):
        parse_job(
            yaml.safe_load("name: recursive\nrun: [tb, run, doctor]\nlane: read-only\n"),
            path,
        )
