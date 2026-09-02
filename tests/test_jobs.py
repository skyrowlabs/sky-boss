"""`sb job` — a schedule sky.boss issues and owns. See [[jobs]].

**Nothing here touches the real `~/.config/systemd/user/`.** `units_dir()`
resolves through `XDG_CONFIG_HOME`, which systemd itself honours, so redirecting
it is the standard rather than a hole opened for the suite. Five foreign unit
files sit in the real directory on the machine this was written on, and a test
that wrote there would be writing something that fires.

The properties worth defending: a name cannot escape the unit directory, a shell
string is refused, one bad definition never costs the others, state is read back
rather than remembered, `cannot tell` is not `nothing installed`, and an `sb-`
unit with no declaration behind it is reported loudly because it still fires.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli import cli
from cli.jobs import (
    Job,
    Unit,
    home_file,
    orphans,
    parse,
    rows_of,
    state_of,
    timer_elapses,
    unit_state,
    units_dir,
    view_of,
)

COMMANDS = {"run": True, "data": False, "read": False}


def a_body(**over):
    body = {"argv": ["run", "--", "echo", "hi"]}
    body.update(over)
    return body


def declared(name="nightly", **over):
    return {"job": {name: a_body(**over)}}


# ============================================================================
# The declaration
# ============================================================================


def test_a_job_is_parsed():
    jobs, problems = parse(declared(schedule="daily 06:00", lane="read-only"), COMMANDS)
    assert problems == []
    assert jobs[0].name == "nightly" and jobs[0].schedule == "daily 06:00"
    assert jobs[0].service == "sb-nightly.service" and jobs[0].timer == "sb-nightly.timer"


@pytest.mark.parametrize("name", ["../escape", "a/b", "sb nightly", "Nightly", "-lead", ""])
def test_a_name_that_could_escape_the_unit_directory_is_refused(name):
    """**A security check, not a tidiness one.** The name becomes a filename in
    a directory sky.boss is allowed to touch and its neighbours are not."""
    _, problems = parse({"job": {name: a_body()}}, COMMANDS)
    assert len(problems) == 1 and "lowercase letters" in problems[0]


def test_a_shell_string_is_refused_by_name():
    """Accepting one would give every job a shell, with its globbing, quoting
    and injection surface, for no benefit. The message says which mistake it
    was rather than the generic list-of-strings complaint."""
    _, problems = parse(declared(argv="sb roll-call | grep x"), COMMANDS)
    assert len(problems) == 1 and "not a shell string" in problems[0]


def test_argv_must_start_with_a_sky_boss_command():
    """Otherwise a job is a second `sb run` that skips the act/observe split."""
    _, problems = parse(declared(argv=["curl", "example.com"]), COMMANDS)
    assert len(problems) == 1 and "must start with a sb command" in problems[0]


def test_an_unknown_key_is_named_and_ignored():
    jobs, problems = parse(declared(retries=3), COMMANDS)
    assert problems == ["job 'nightly': unknown key 'retries' — ignored"]
    assert len(jobs) == 1, "an unknown key must not cost the declaration"


def test_an_unknown_top_level_table_is_named():
    """The silence this repeats: a typo'd table name parsed clean, declared
    nothing, and read exactly like a fresh clone."""
    _, problems = parse({"jobs": {"nightly": a_body()}}, COMMANDS)
    assert problems == ["unknown table 'jobs' — ignored"]


def test_one_bad_definition_does_not_cost_the_others():
    """A loader that raises on one malformed job takes down the whole
    schedule."""
    jobs, problems = parse(
        {"job": {"good": a_body(), "bad": a_body(timeout="soon")}}, COMMANDS
    )
    assert [j.name for j in jobs] == ["good"]
    assert len(problems) == 1 and "timeout" in problems[0]


def test_a_schedule_is_optional_and_means_manual():
    jobs, problems = parse(declared(), COMMANDS)
    assert problems == [] and jobs[0].schedule == ""


def test_there_is_no_default_timeout():
    """`CLAUDE.md` records what one costs: a 60s ceiling killed any long run
    while `--timeout` was accepted and then overridden. An agentic job may
    legitimately run for an hour."""
    jobs, _ = parse(declared(), COMMANDS)
    assert jobs[0].timeout == 0


def test_an_unreadable_file_is_one_problem_and_no_jobs():
    jobs, problems = parse({"__error__": "boom"}, COMMANDS)
    assert jobs == [] and problems == ["boom"]


# ============================================================================
# Reading systemd back
# ============================================================================


def test_the_unit_directory_follows_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert units_dir() == tmp_path / "systemd" / "user"


def a_job(**over):
    return Job(name="nightly", argv=["run", "--", "echo", "hi"], **over)


def test_declared_but_not_installed():
    assert state_of(a_job(schedule="daily"), Unit(file=False)) == "declared"


def test_no_schedule_reads_manual():
    assert state_of(a_job(), Unit(file=False)) == "manual"


def test_on_disk_and_not_enabled_is_installed():
    """Generating never enables, so this is a normal resting state and not an
    error."""
    assert state_of(a_job(schedule="daily"), Unit(file=True, enabled="disabled")) == "installed"


def test_enabled_reads_enabled():
    assert state_of(a_job(schedule="daily"), Unit(file=True, enabled="enabled")) == "enabled"


def test_a_unit_for_a_job_that_no_longer_asks_to_be_scheduled_is_drift():
    """The state a manager that trusts its own model can never report: a
    disagreement between what was declared and what the machine will do."""
    assert state_of(a_job(), Unit(file=True, enabled="enabled")) == "drifted"


def test_cannot_tell_is_not_nothing_installed():
    """Collapsing them would report a machine sky.boss cannot inspect as a
    machine with no jobs on it — the same third answer [[agent-sessions]]
    needed."""
    assert state_of(a_job(schedule="daily"), Unit(known=False)) == "unknown"


def test_an_orphan_unit_is_found(tmp_path, monkeypatch):
    """The one case where a *missing* job is more dangerous than a broken one:
    an orphan still fires, forever, and nothing declares it."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "systemd" / "user").mkdir(parents=True)
    (tmp_path / "systemd" / "user" / "sb-ghost.timer").write_text("")
    (tmp_path / "systemd" / "user" / "sb-known.timer").write_text("")
    (tmp_path / "systemd" / "user" / "arch-update.timer").write_text("")
    found, listed = orphans({"known"})
    assert found == ["sb-ghost.timer"] and listed is True


def test_a_foreign_unit_is_never_reported(tmp_path, monkeypatch):
    """Five foreign unit files sit in that directory on a real machine. Nothing
    outside the `sb-` prefix is sky.boss's to mention."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "systemd" / "user").mkdir(parents=True)
    (tmp_path / "systemd" / "user" / "openclaw-gateway.service").write_text("")
    found, _ = orphans(set())
    assert found == []


def test_an_absent_unit_directory_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nowhere"))
    found, listed = orphans(set())
    assert found == [] and listed is True


def test_a_machine_with_no_systemctl_says_it_could_not_ask(monkeypatch):
    monkeypatch.setattr("cli.jobs._systemctl", lambda *a: ("", False))
    assert unit_state("nightly").known is False
    assert timer_elapses() == ({}, False)


def test_a_fire_time_is_read_back_verbatim(monkeypatch):
    """Never computed here, and never re-worded: a time sky.boss reformats is a
    time sky.boss owns."""
    line = "Wed 2026-09-02 06:00:00 CDT 8h Tue 2026-09-01 06:00:00 CDT 15h sb-nightly.timer sb-nightly.service"
    monkeypatch.setattr("cli.jobs._systemctl", lambda *a: (line, True))
    found, asked = timer_elapses()
    assert asked is True
    assert found["sb-nightly.timer"] == "Wed 2026-09-02 06:00:00 CDT"


# ============================================================================
# The command
# ============================================================================


def _home(tmp_path, body: str):
    (tmp_path / "jobs.toml").write_text(body)
    return tmp_path


def run(tmp_path, monkeypatch, *args, xdg=None):
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.jobs.SB_HOME", tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg or tmp_path / "xdg"))
    return CliRunner().invoke(cli, ["--json", "job", *args])


ONE = """
[job.nightly]
argv     = ["run", "--", "echo", "hi"]
schedule = "daily 06:00"
lane     = "read-only"
"""


def test_the_list_draws_declared_jobs(tmp_path, monkeypatch):
    _home(tmp_path, ONE)
    body = json.loads(run(tmp_path, monkeypatch, "list").stdout)
    assert body["ok"] is True
    assert [r["name"] for r in body["data"]] == ["nightly"]
    assert body["data"][0]["schedule"] == "daily 06:00"


def test_running_the_group_bare_is_the_list(tmp_path, monkeypatch):
    _home(tmp_path, ONE)
    bare = json.loads(run(tmp_path, monkeypatch).stdout)
    listed = json.loads(run(tmp_path, monkeypatch, "list").stdout)
    assert bare["data"] == listed["data"]


def test_no_jobs_declared_says_so(tmp_path, monkeypatch):
    _home(tmp_path, "")
    body = json.loads(run(tmp_path, monkeypatch, "list").stdout)
    assert body["data"] == []
    assert any("no jobs declared" in w for w in body["warnings"])


def test_an_orphan_makes_the_answer_partial(tmp_path, monkeypatch):
    """Loud, because it fires. `partial` is the exit code that says so without
    anything having to read the sentence."""
    _home(tmp_path, ONE)
    xdg = tmp_path / "xdg"
    (xdg / "systemd" / "user").mkdir(parents=True)
    (xdg / "systemd" / "user" / "sb-ghost.timer").write_text("")
    result = run(tmp_path, monkeypatch, "list", xdg=xdg)
    body = json.loads(result.stdout)
    assert body["partial"] is True and result.exit_code == 3
    assert any("still fires" in w for w in body["warnings"])


def test_the_view_is_authored_and_hides_the_argv(tmp_path, monkeypatch):
    _home(tmp_path, ONE)
    body = json.loads(run(tmp_path, monkeypatch, "list").stdout)
    view = body["view"]
    assert view["authored"] is True
    assert [c["key"] for c in view["columns"]] == ["name", "state", "schedule", "next", "lane"]
    assert set(view["hidden"]) == {"argv", "timeout", "description", "enabled", "active"}


def test_the_view_describes_every_key_and_invents_none():
    rows = rows_of([a_job(schedule="daily")], {"nightly": Unit()})
    view = view_of(rows)
    named = {c["key"] for c in view["columns"]} | set(view["hidden"])
    assert named == set(rows[0])


# ============================================================================
# Running one — the ledger, the lane, and the five outcomes
# ============================================================================

import fcntl  # noqa: E402
import subprocess  # noqa: E402

from cli.jobs import append, execute, jobs_state, lane_lock, ledger_path, new_run_id, sb_executable  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    """A scratch `$SB_STATE`, so no test writes the real ledger."""
    target = tmp_path / "state"
    monkeypatch.setattr("cli.jobs.STATE_DIR", target)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "rt"))
    (tmp_path / "rt").mkdir()
    return target


def test_the_ledger_lives_under_state_not_home(state):
    """The home holds what the operator wrote; the state holds what the machine
    did. `rm -rf` on the state must not delete a schedule."""
    assert ledger_path() == state / "jobs" / "ledger.jsonl"
    assert jobs_state() == state / "jobs"


def test_a_run_id_survives_two_runs_in_one_second():
    """The stamp makes it sortable; the suffix is what keeps them apart."""
    assert new_run_id("j") != new_run_id("j")


def test_the_lane_lock_belongs_to_a_boot(tmp_path, monkeypatch):
    """A stale lock file surviving a reboot is a lane that can never be entered
    again."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert lane_lock("read-only") == tmp_path / "sb" / "lane-read-only.lock"


def test_the_executable_is_absolute():
    """A generated unit has no PATH worth relying on, and a manual run and a
    timed run must not execute two different sky.bosses."""
    assert sb_executable().startswith("/") and sb_executable().endswith("/sb")


def test_the_ledger_is_one_object_per_line(state):
    append({"job": "a"})
    append({"job": "b"})
    lines = ledger_path().read_text().splitlines()
    assert [json.loads(line)["job"] for line in lines] == ["a", "b"]


@pytest.mark.parametrize(
    "code,outcome",
    [(0, "ok"), (3, "partial"), (1, "failed"), (2, "failed"), (7, "failed")],
)
def test_the_envelopes_three_codes_map_and_everything_else_is_failure(
    code, outcome, state, monkeypatch, tmp_path
):
    """This is where `partial` finally does real work rather than being tidy: a
    wrapper branches on the exit status without parsing a byte of output."""

    def fake(*a, **k):
        return subprocess.CompletedProcess(a[0], code)

    monkeypatch.setattr("cli.jobs.subprocess.run", fake)
    record = execute(a_job(), tmp_path / "x.log")
    assert record["outcome"] == outcome and record["exit"] == code


def test_a_timeout_is_a_recorded_outcome_not_an_exception(state, monkeypatch, tmp_path):
    """With the ledger standing in for a notifier, a run that vanished without a
    line is indistinguishable from one that never happened."""

    def fake(*a, **k):
        raise subprocess.TimeoutExpired(a[0], 1)

    monkeypatch.setattr("cli.jobs.subprocess.run", fake)
    record = execute(a_job(timeout=1), tmp_path / "x.log")
    assert record["outcome"] == "timeout" and record["exit"] is None


def test_a_binary_that_cannot_start_is_recorded_and_says_so(state, monkeypatch, tmp_path):
    def fake(*a, **k):
        raise OSError(2, "No such file or directory")

    monkeypatch.setattr("cli.jobs.subprocess.run", fake)
    log = tmp_path / "x.log"
    record = execute(a_job(), log)
    assert record["outcome"] == "failed"
    assert "could not start" in log.read_text()


def test_a_declared_bound_is_passed_and_none_is_unbounded(state, monkeypatch, tmp_path):
    seen = {}

    def fake(*a, **k):
        seen["timeout"] = k.get("timeout")
        return subprocess.CompletedProcess(a[0], 0)

    monkeypatch.setattr("cli.jobs.subprocess.run", fake)
    execute(a_job(timeout=30), tmp_path / "x.log")
    assert seen["timeout"] == 30
    execute(a_job(), tmp_path / "x.log")
    assert seen["timeout"] is None


RUNNABLE = """
[job.quiet]
argv = ["run", "--", "echo", "spoken"]

[job.laned]
argv = ["run", "--", "echo", "hi"]
lane = "read-only"
"""


def test_a_real_run_writes_a_ledger_line_and_a_log(tmp_path, monkeypatch, state):
    """End to end through the real wrapper, because the thing being proved is
    that the spawn works at all."""
    _home(tmp_path, RUNNABLE)
    body = json.loads(run(tmp_path, monkeypatch, "run", "quiet").stdout)
    assert body["ok"] is True and body["data"]["outcome"] == "ok"
    assert len(ledger_path().read_text().splitlines()) == 1
    assert "spoken" in Path(body["data"]["log"]).read_text()


def test_output_goes_to_the_log_and_never_into_the_envelope(tmp_path, monkeypatch, state):
    """`sb run` carries what it printed because you typed that argv; a job may
    print for an hour unattended, so the envelope carries the record and names
    where the bytes went."""
    _home(tmp_path, RUNNABLE)
    body = json.loads(run(tmp_path, monkeypatch, "run", "quiet").stdout)
    assert "spoken" not in json.dumps(body["data"])
    assert set(body["data"]) == {
        "job", "run_id", "lane", "log", "started", "finished", "duration_s", "outcome", "exit",
    }


def test_a_busy_lane_refuses_rather_than_waiting(tmp_path, monkeypatch, state):
    """A job that cannot take its lane does not wait — waiting turns a schedule
    into a queue, and a queue that drains at 3am is a different feature nobody
    asked for."""
    _home(tmp_path, RUNNABLE)
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.jobs.SB_HOME", tmp_path)
    held = lane_lock("read-only").open("w")
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = CliRunner().invoke(cli, ["--json", "job", "run", "laned"])
    finally:
        held.close()
    body = json.loads(result.stdout)
    assert body["data"]["outcome"] == "refused" and body["data"]["exit"] is None
    assert body["partial"] is True and result.exit_code == 3
    assert any("is busy" in w for w in body["warnings"])
    # Refused is still a run that happened to a job, and it is on the ledger.
    assert json.loads(ledger_path().read_text())["outcome"] == "refused"


def test_a_job_with_no_lane_takes_no_lock(tmp_path, monkeypatch, state):
    _home(tmp_path, RUNNABLE)
    held = lane_lock("read-only").open("w")
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        body = json.loads(run(tmp_path, monkeypatch, "run", "quiet").stdout)
    finally:
        held.close()
    assert body["data"]["outcome"] == "ok"


def test_an_unknown_job_names_the_declared_ones(tmp_path, monkeypatch, state):
    _home(tmp_path, RUNNABLE)
    result = run(tmp_path, monkeypatch, "run", "nope")
    assert result.exit_code == 2
    assert "quiet" in result.output and "laned" in result.output
