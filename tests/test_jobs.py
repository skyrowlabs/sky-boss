"""Tests for tb auto — job definitions, running, and the ledger.

With no notifier yet the ledger IS the notification surface, so the tests that
matter most are the ones asserting nothing runs unlogged.
"""

import json

import pytest
import yaml

from cli.jobs import (
    DEFAULT_TIMEOUT,
    Job,
    JobError,
    append_ledger,
    load_jobs,
    parse_job,
    run_job,
    tail_text,
)


def write_job(directory, name, **overrides):
    body = {
        "name": name,
        "description": "does a thing",
        "run": ["true"],
        "lane": "read-only",
        "timeout": 5,
    }
    body.update(overrides)
    path = directory / f"{name}.yaml"
    path.write_text(yaml.safe_dump(body))
    return path


# ---------------------------------------------------------------- parsing


def test_parse_minimal_job(tmp_path):
    job = parse_job(
        {"name": "x", "run": ["true"], "lane": "read-only"}, tmp_path / "x.yaml"
    )
    assert job.run == ["true"]
    assert job.timeout == DEFAULT_TIMEOUT
    assert job.schedule is None


@pytest.mark.parametrize(
    "data,fragment",
    [
        ({"run": ["true"], "lane": "read-only"}, "'name' is required"),
        ({"name": "wrong", "run": ["true"], "lane": "read-only"}, "filename says"),
        ({"name": "x", "lane": "read-only"}, "'run' must be"),
        ({"name": "x", "run": "tb doctor", "lane": "read-only"}, "argv, not a shell line"),
        ({"name": "x", "run": [], "lane": "read-only"}, "'run' must be"),
        ({"name": "x", "run": ["true"]}, "'lane' must be"),
        ({"name": "x", "run": ["true"], "lane": "nope"}, "'lane' must be"),
        ({"name": "x", "run": ["true"], "lane": "read-only", "timeout": 0}, "positive integer"),
        ({"name": "x", "run": ["true"], "lane": "read-only", "schedule": 5}, "'schedule' must be"),
        ("not a mapping", "expected a mapping"),
    ],
)
def test_parse_errors_name_the_file_and_the_problem(tmp_path, data, fragment):
    with pytest.raises(JobError) as exc:
        parse_job(data, tmp_path / "x.yaml")
    assert "x.yaml" in str(exc.value)
    assert fragment in str(exc.value)


def test_run_as_a_shell_string_is_rejected(tmp_path):
    """argv, never a shell line — no pipes, globs or redirects by accident."""
    with pytest.raises(JobError):
        parse_job({"name": "x", "run": "tb doctor | grep x", "lane": "read-only"},
                  tmp_path / "x.yaml")


# ---------------------------------------------------------------- loading


def test_one_bad_definition_does_not_hide_the_others(tmp_path):
    """A malformed file must not take the whole schedule down with it."""
    write_job(tmp_path, "good")
    (tmp_path / "bad.yaml").write_text("name: mismatch\nrun: [true]\nlane: read-only\n")

    jobs, problems = load_jobs(tmp_path)
    assert set(jobs) == {"good"}
    assert len(problems) == 1
    assert "bad.yaml" in problems[0]


def test_underscore_files_are_skipped(tmp_path):
    write_job(tmp_path, "good")
    (tmp_path / "_template.yaml").write_text("this: is not a job\n")
    jobs, problems = load_jobs(tmp_path)
    assert set(jobs) == {"good"}
    assert problems == []


def test_invalid_yaml_is_reported_not_raised(tmp_path):
    (tmp_path / "broken.yaml").write_text("name: [unclosed\n")
    jobs, problems = load_jobs(tmp_path)
    assert jobs == {}
    assert "broken.yaml" in problems[0]


def test_missing_directory_is_empty_not_an_error(tmp_path):
    assert load_jobs(tmp_path / "nope") == ({}, [])


# ---------------------------------------------------------------- running


def read_ledger(state_dir):
    return [json.loads(line) for line in (state_dir / "ledger.jsonl").read_text().splitlines()]


def test_successful_run_is_recorded(tmp_path):
    entry = run_job(Job(name="ok", run=["true"], lane="read-only"), state_dir=tmp_path)
    assert entry["outcome"] == "ok"
    assert entry["exit"] == 0
    assert read_ledger(tmp_path)[0]["job"] == "ok"


def test_exit_three_is_partial_not_failure():
    """The whole reason partial has its own exit code."""
    from cli.jobs import OUTCOME_BY_EXIT

    assert OUTCOME_BY_EXIT[3] == "partial"
    assert OUTCOME_BY_EXIT[1] == "failed"


def test_failing_run_is_recorded(tmp_path):
    entry = run_job(Job(name="bad", run=["false"], lane="read-only"), state_dir=tmp_path)
    assert entry["outcome"] == "failed"
    assert read_ledger(tmp_path)[0]["outcome"] == "failed"


def test_partial_run_is_recorded(tmp_path):
    job = Job(name="p", run=["sh", "-c", "exit 3"], lane="read-only")
    entry = run_job(job, state_dir=tmp_path)
    assert entry["outcome"] == "partial"


def test_timeout_is_a_recorded_outcome_not_an_exception(tmp_path):
    """Silence in the ledger must never mean 'fine'."""
    job = Job(name="slow", run=["sleep", "5"], lane="read-only", timeout=1)
    entry = run_job(job, state_dir=tmp_path)
    assert entry["outcome"] == "timeout"
    assert read_ledger(tmp_path)[0]["outcome"] == "timeout"


def test_unstartable_job_is_recorded_as_refused(tmp_path):
    job = Job(name="nope", run=["definitely-not-a-real-binary-xyz"], lane="read-only")
    entry = run_job(job, state_dir=tmp_path)
    assert entry["outcome"] == "refused"
    assert read_ledger(tmp_path)[0]["outcome"] == "refused"


def test_output_is_captured_to_its_own_log(tmp_path):
    job = Job(name="chatty", run=["sh", "-c", "echo hello; echo oops >&2"], lane="read-only")
    entry = run_job(job, state_dir=tmp_path)
    from pathlib import Path

    captured = Path(entry["log"]).read_text()
    assert "hello" in captured and "oops" in captured


def test_every_run_appends_a_line(tmp_path):
    job = Job(name="ok", run=["true"], lane="read-only")
    for _ in range(3):
        run_job(job, state_dir=tmp_path)
    assert len(read_ledger(tmp_path)) == 3


def test_ledger_lines_are_independent(tmp_path):
    """Append-only and line-sized: a truncated last line cannot corrupt the rest."""
    ledger = tmp_path / "ledger.jsonl"
    append_ledger({"a": 1}, ledger)
    append_ledger({"b": 2}, ledger)
    with ledger.open("a") as handle:
        handle.write('{"c": incomplete')

    lines = ledger.read_text().splitlines()
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"b": 2}
    with pytest.raises(json.JSONDecodeError):
        json.loads(lines[2])


# ---------------------------------------------------------------- tail


def test_tail_joins_with_newlines_not_commas():
    """A list would render as a comma-joined blob; log output is lines."""
    assert tail_text("a\n\nb\nc\n", count=2) == "b\nc"


# ---------------------------------------------------------------- reading


from datetime import datetime, timedelta, timezone  # noqa: E402

from cli.jobs import (  # noqa: E402
    SEVERITY,
    humanize_age,
    is_overdue,
    job_status,
    last_runs,
    parse_duration,
    prune,
    read_ledger,
)

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def entry(job, outcome="ok", ago_hours=1, run_id=None, log=None):
    started = NOW - timedelta(hours=ago_hours)
    return {
        "run_id": run_id or f"{job}-{ago_hours}",
        "job": job,
        "started": started.isoformat(),
        "duration_s": 1.0,
        "exit": 0 if outcome == "ok" else 3,
        "outcome": outcome,
        "log": log or f"/tmp/{job}-{ago_hours}.log",
        "command": ["true"],
    }


def test_read_ledger_skips_a_truncated_last_line(tmp_path):
    """A run killed mid-write must not cost you the history before it."""
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps(entry("a")) + "\n"
        + json.dumps(entry("b")) + "\n"
        + '{"job": "c", "trunc'
    )
    got = read_ledger(tmp_path)
    assert [e["job"] for e in got] == ["a", "b"]


def test_read_ledger_missing_file_is_empty(tmp_path):
    assert read_ledger(tmp_path) == []


def test_last_runs_takes_the_most_recent_per_job():
    entries = [entry("a", ago_hours=5), entry("a", ago_hours=1), entry("b", ago_hours=3)]
    latest = last_runs(entries)
    assert latest["a"]["run_id"] == "a-1"
    assert set(latest) == {"a", "b"}


# ---------------------------------------------------------------- silence is not success


def test_never_run_job_does_not_read_as_passing():
    """The specific way a pull-based surface fails: quietly reassuring."""
    row = job_status(Job(name="x", run=["true"], lane="read-only"), None, now=NOW)
    assert row["ok"] is None
    assert row["state"] == "never"
    assert "never run" in row["detail"]


def test_scheduled_job_that_never_ran_is_overdue():
    job = Job(name="x", run=["true"], lane="read-only", schedule="daily 06:00")
    row = job_status(job, None, now=NOW)
    assert row["state"] == "overdue"
    assert row["ok"] is False


def test_missed_schedule_does_not_read_as_passing():
    """A stale success is still a failure to run."""
    job = Job(name="x", run=["true"], lane="read-only", schedule="daily 06:00")
    stale = entry("x", outcome="ok", ago_hours=72)
    row = job_status(job, stale, now=NOW)
    assert row["state"] == "overdue"
    assert row["ok"] is False


def test_recent_scheduled_success_is_fine():
    job = Job(name="x", run=["true"], lane="read-only", schedule="daily 06:00")
    row = job_status(job, entry("x", ago_hours=2), now=NOW)
    assert row["ok"] is True
    assert row["state"] == "ok"


def test_unscheduled_job_is_never_overdue():
    job = Job(name="x", run=["true"], lane="read-only")
    assert is_overdue(job, entry("x", ago_hours=10_000), now=NOW) is False


def test_partial_is_not_ok():
    job = Job(name="x", run=["true"], lane="read-only")
    row = job_status(job, entry("x", outcome="partial"), now=NOW)
    assert row["ok"] is False
    assert "partial" in row["detail"]


def test_worst_sorts_first():
    order = sorted(["ok", "never", "partial", "overdue", "failed"], key=lambda s: SEVERITY[s])
    assert order == ["failed", "overdue", "partial", "never", "ok"]


# ---------------------------------------------------------------- age + duration


def test_humanize_age():
    assert humanize_age(NOW - timedelta(seconds=10), NOW) == "just now"
    assert humanize_age(NOW - timedelta(minutes=5), NOW) == "5m ago"
    assert humanize_age(NOW - timedelta(hours=3), NOW) == "3h ago"
    assert humanize_age(NOW - timedelta(days=2), NOW) == "2d ago"
    assert humanize_age(NOW - timedelta(days=21), NOW) == "3w ago"


@pytest.mark.parametrize("text,expected", [
    ("30m", timedelta(minutes=30)),
    ("24h", timedelta(hours=24)),
    ("7d", timedelta(days=7)),
    ("2w", timedelta(weeks=2)),
])
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


def test_parse_duration_rejects_nonsense():
    with pytest.raises(ValueError):
        parse_duration("banana")


# ---------------------------------------------------------------- prune


def test_prune_keeps_the_most_recent_per_job(tmp_path):
    (tmp_path / "logs").mkdir()
    lines = []
    for i in range(6):
        log = tmp_path / "logs" / f"a-{i}.log"
        log.write_text("x")
        lines.append(json.dumps(entry("a", ago_hours=6 - i, run_id=f"a-{i}", log=str(log))))
    (tmp_path / "ledger.jsonl").write_text("\n".join(lines) + "\n")

    stats = prune(tmp_path, keep_per_job=2)
    assert stats["entries_before"] == 6
    assert stats["entries_kept"] == 2
    assert [e["run_id"] for e in read_ledger(tmp_path)] == ["a-4", "a-5"]


def test_prune_removes_only_orphaned_logs(tmp_path):
    (tmp_path / "logs").mkdir()
    kept_log = tmp_path / "logs" / "a-1.log"
    orphan = tmp_path / "logs" / "gone.log"
    kept_log.write_text("keep")
    orphan.write_text("orphan")
    (tmp_path / "ledger.jsonl").write_text(
        json.dumps(entry("a", run_id="a-1", log=str(kept_log))) + "\n"
    )

    stats = prune(tmp_path, keep_per_job=50)
    assert stats["logs_removed"] == 1
    assert kept_log.exists()
    assert not orphan.exists()


def test_prune_is_a_noop_on_an_empty_state_dir(tmp_path):
    assert prune(tmp_path)["entries_kept"] == 0


# ---------------------------------------------------------------- lanes


from cli.jobs import (  # noqa: E402
    UNIT_PREFIX,
    install_job,
    lane_lock,
    resolve_exec,
    to_oncalendar,
    uninstall_job,
    unit_files,
)


def test_lane_lock_is_exclusive(tmp_path):
    lock = tmp_path / "lane.lock"
    with lane_lock("read-only", lock) as first:
        assert first is True
        with lane_lock("read-only", lock) as second:
            assert second is False


def test_lane_lock_releases(tmp_path):
    lock = tmp_path / "lane.lock"
    with lane_lock("read-only", lock):
        pass
    with lane_lock("read-only", lock) as again:
        assert again is True


def test_busy_lane_records_skipped_rather_than_running(tmp_path):
    """A job that waited silently would make its schedule a lie."""
    job = Job(name="x", run=["true"], lane="read-only")
    lock = tmp_path / "lane.lock"
    with lane_lock("read-only", lock):
        entry = run_job(job, state_dir=tmp_path, lock_path=lock)

    assert entry["outcome"] == "skipped"
    assert entry["exit"] is None
    assert read_ledger(tmp_path)[0]["outcome"] == "skipped"


def test_skipped_is_neither_pass_nor_fail():
    """The lane held is the mutex working, not a fault."""
    job = Job(name="x", run=["true"], lane="read-only")
    row = job_status(job, entry("x", outcome="skipped"), now=NOW)
    assert row["ok"] is None


def test_different_lanes_do_not_block_each_other(tmp_path):
    with lane_lock("read-only", tmp_path / "a.lock") as first:
        with lane_lock("committing", tmp_path / "b.lock") as second:
            assert first and second


# ---------------------------------------------------------------- schedules


@pytest.mark.parametrize("schedule,expected", [
    ("daily", "daily"),
    ("hourly", "hourly"),
    ("daily 06:00", "*-*-* 06:00:00"),
    ("daily 6:00", "*-*-* 06:00:00"),
    ("weekly Sun 09:00", "Sun *-*-* 09:00:00"),
    ("*-*-* 03:15:00", "*-*-* 03:15:00"),
])
def test_schedule_translates_to_oncalendar(schedule, expected):
    assert to_oncalendar(schedule) == expected


def test_invalid_schedule_is_rejected_by_systemd_not_by_us():
    with pytest.raises(JobError):
        to_oncalendar("every other tuesday")


# ---------------------------------------------------------------- units


def test_unit_uses_an_absolute_program_path():
    """systemd user units get a minimal PATH without ~/.local/bin."""
    line = resolve_exec(["true", "--flag"])
    assert line.startswith("/")
    assert "--flag" in line


def test_resolve_exec_fails_loudly_on_a_missing_program():
    with pytest.raises(JobError):
        resolve_exec(["definitely-not-a-real-binary-xyz"])


def test_unit_files_reference_nothing_outside_the_tb_prefix():
    """~/.config/systemd/user is shared space, not tb's directory."""
    job = Job(name="demo", run=["true"], lane="read-only",
              schedule="daily 06:00", description="a demo")
    service, timer = unit_files(job)

    for text in (service, timer):
        for token in text.split():
            if token.endswith((".service", ".timer")):
                assert token.startswith(UNIT_PREFIX), token
    assert "timers.target" in timer  # the one allowed foreign target, and it is a target


def test_cannot_install_a_job_with_no_schedule():
    with pytest.raises(JobError):
        unit_files(Job(name="x", run=["true"], lane="read-only"))


def test_install_and_uninstall_only_touch_tb_files(tmp_path):
    foreign = tmp_path / "arch-update.timer"
    foreign.write_text("not ours")

    job = Job(name="demo", run=["true"], lane="read-only", schedule="daily 06:00")
    install_job(job, unit_dir=tmp_path, enable=False)
    assert (tmp_path / "tb-demo.timer").exists()
    assert (tmp_path / "tb-demo.service").exists()

    result = uninstall_job("demo", unit_dir=tmp_path, disable=False)
    assert sorted(result["removed"]) == ["tb-demo.service", "tb-demo.timer"]
    assert foreign.read_text() == "not ours"
    assert foreign.exists()


# ---------------------------------------------------------------- reserved windows


from cli.jobs import (  # noqa: E402
    _cron_field,
    collisions,
    matching_processes,
    parse_crontab,
)

JAM_CRONTAB = """# jam.sense agentic reporting — generated by `jam report cron --print`
15 3 * * *    cd ~/skyrow.labs/jam.sense && ./jam report sentinel
# 03:45 is a scheduling constraint, not a preference.
45 3 * * *    cd ~/skyrow.labs/jam.sense && ./jam report integration
20 3,7,11,15,19,23 * * * cd ~/skyrow.labs/jam.sense && ./jam report release
0 0 * * 2     cd ~/skyrow.labs/jam.sense && ./jam report deps
"""


@pytest.mark.parametrize("field,low,high,expected", [
    ("*", 0, 3, {0, 1, 2, 3}),
    ("5", 0, 59, {5}),
    ("1,2,3", 0, 59, {1, 2, 3}),
    ("3,7,11,15,19,23", 0, 23, {3, 7, 11, 15, 19, 23}),
    ("1-4", 0, 59, {1, 2, 3, 4}),
    ("*/15", 0, 59, {0, 15, 30, 45}),
])
def test_cron_field_parsing(field, low, high, expected):
    assert _cron_field(field, low, high) == expected


def test_cron_field_returns_none_when_unparseable():
    assert _cron_field("JAN", 0, 59) is None
    assert _cron_field("*/x", 0, 59) is None


def test_parse_crontab_skips_comments_and_keeps_entries():
    windows, unreadable = parse_crontab(JAM_CRONTAB)
    assert len(windows) == 4
    assert unreadable == []
    assert windows[0].minutes == {15} and windows[0].hours == {3}


def test_unparseable_entries_are_surfaced_not_dropped():
    """Silently ignoring one would claim coverage this does not have."""
    windows, unreadable = parse_crontab("MAYBE 3 * * * do-a-thing\n")
    assert windows == []
    assert len(unreadable) == 1


def test_weekly_entry_restricts_days():
    windows, _ = parse_crontab(JAM_CRONTAB)
    weekly = [w for w in windows if "deps" in w.command][0]
    assert weekly.weekdays == {2}


def test_collision_detected_near_a_cron_job():
    windows, _ = parse_crontab(JAM_CRONTAB)
    assert collisions("*-*-* 03:20:00", windows)


def test_no_collision_in_a_clear_window():
    windows, _ = parse_crontab(JAM_CRONTAB)
    assert collisions("*-*-* 09:00:00", windows) == []


def test_every_four_hours_at_twenty_past_is_caught():
    """The trap that caught the author: :20 recurs six times a day."""
    windows, _ = parse_crontab(JAM_CRONTAB)
    assert collisions("*-*-* 07:15:00", windows)


def test_weekly_cron_does_not_clash_on_other_days():
    windows, _ = parse_crontab("0 12 * * 2  weekly-thing\n")
    # Wednesday 12:00 — same time, wrong day
    assert collisions("Wed *-*-* 12:00:00", windows) == []


# ---------------------------------------------------------------- runtime guard


def test_matching_processes_excludes_our_own_ancestry():
    """`pgrep -f` matches the shell running the check.

    Verified on this machine: checking for 'jam report' reported a match with
    nothing of the sort running, because the checking shell's own command line
    contained the pattern.
    """
    import os

    unique = f"tb-test-pattern-{os.getpid()}"
    assert matching_processes(unique) == []


def test_avoid_pattern_blocks_a_run(tmp_path, monkeypatch):
    monkeypatch.setattr("cli.jobs.matching_processes", lambda pattern: ["/usr/bin/jam report x"])
    job = Job(name="x", run=["true"], lane="read-only", avoid=("jam report",))
    entry = run_job(job, state_dir=tmp_path, lock_path=tmp_path / "l.lock")
    assert entry["outcome"] == "skipped"
    assert "avoid pattern" in (tmp_path / "logs" / f"{entry['run_id']}.log").read_text()


def test_avoid_is_validated(tmp_path):
    with pytest.raises(JobError):
        parse_job({"name": "x", "run": ["true"], "lane": "read-only", "avoid": "jam report"},
                  tmp_path / "x.yaml")
