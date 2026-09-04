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


# ============================================================================
# Generating units — and refusing to install one twice
# ============================================================================

from cli.jobs import (  # noqa: E402
    busy_lines,
    calendar,
    collisions,
    payload,
    service_unit,
    timer_unit,
)

# Captured verbatim from the real `systemd-analyze calendar` on 2026-09-01, so
# what is parsed here is what systemd actually prints. **Nothing in this file
# shells out to it**: `systemd-analyze`, `crontab` and a working
# `systemctl --user` are all things a CI container may not have, and a test whose
# environment differs from CI's is a test about your machine.
NORMALIZED = """  Original form: 06:00
Normalized form: *-*-* 06:00:00
    Next elapse: Wed 2026-09-02 06:00:00 CDT
"""
REJECTED = "Failed to parse calendar specification 'daily 06:00': Invalid argument\n"


@pytest.fixture(autouse=True)
def no_real_systemctl(monkeypatch):
    """No test may reach the real user manager — `uninstall` issues a
    `disable --now`, and the suite must never issue one."""
    monkeypatch.setattr("cli.jobs._systemctl", lambda *a: ("", True))


def canned(stdout="", code=0, stderr=""):
    def fake(*a, **k):
        return subprocess.CompletedProcess(a[0], code, stdout, stderr)

    return fake


def test_a_valid_schedule_comes_back_normalised(monkeypatch):
    monkeypatch.setattr("cli.jobs.subprocess.run", canned(NORMALIZED))
    assert calendar("06:00") == ("*-*-* 06:00:00", "")


def test_systemd_owns_the_refusal(monkeypatch):
    """A second implementation of calendar syntax would be wrong about DST
    before it was wrong about anything else. `daily 06:00` is a real rejection —
    it was in this feature's own spec until systemd said no."""
    monkeypatch.setattr("cli.jobs.subprocess.run", canned(code=1, stderr=REJECTED))
    normalized, trouble = calendar("daily 06:00")
    assert normalized == "" and "systemd rejected" in trouble


def test_a_manual_job_has_nothing_to_install():
    assert calendar("")[1].startswith("no schedule declared")


def test_no_systemd_analyze_refuses_rather_than_writing_an_unvalidated_unit(monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr("cli.jobs.subprocess.run", missing)
    assert "not available" in calendar("06:00")[1]


# ---------------------------------------------------------------- the units


def test_exec_start_goes_through_the_command_never_the_raw_argv():
    """The difference between a scheduler and a cron line: going through
    `sb job run` means a timed run takes the lane, honours the timeout and
    writes the ledger exactly as a manual one does. A unit that ran the argv
    directly would bypass all three, silently, for the runs nobody watches."""
    text = service_unit(a_job(schedule="06:00"), "*-*-* 06:00:00")
    assert "ExecStart=" in text
    exec_line = next(ln for ln in text.splitlines() if ln.startswith("ExecStart="))
    assert exec_line.endswith("/sb job run nightly")
    assert "echo" not in text, "the job's own argv must not appear in the unit"


CONTROLLING = (
    "Conflicts", "Requires", "Requisite", "BindsTo", "PartOf",
    "Before", "After", "Wants", "Upholds", "OnFailure",
)


@pytest.mark.parametrize("directive", CONTROLLING)
def test_a_generated_unit_never_controls_another_unit(directive):
    """`~/.config/systemd/user/` is shared space — five foreign unit files sit
    in it on a real machine.

    `Conflicts=` is called out by name because it was the original plan and is
    the expensive mistake: it *stops* the conflicting unit rather than waiting
    or refusing, so a scheduled job would kill a running one. Preemption, not
    mutual exclusion. Lanes are a `flock` for exactly this reason.
    """
    job = a_job(schedule="06:00")
    for text in (service_unit(job, ""), timer_unit(job, "")):
        assert f"{directive}=" not in text


def test_the_only_foreign_unit_named_is_the_enable_target():
    """`WantedBy=timers.target` is how every timer is enabled — the mechanism,
    not a reference to somebody's unit. It is the single exception and it is
    pinned here so a second one cannot arrive quietly."""
    job = a_job(schedule="06:00")
    named = set()
    for text in (service_unit(job, ""), timer_unit(job, "")):
        for line in text.splitlines():
            for word in line.replace("=", " ").split():
                if word.endswith((".service", ".timer", ".target")):
                    named.add(word)
    assert named - {"sb-nightly.service", "sb-nightly.timer"} == {"timers.target"}


def test_a_timer_does_not_catch_up_on_a_missed_run():
    """No `Persistent=`. It would fire a missed run at the next boot, which cron
    does not do — and these jobs are being migrated off cron, so matching what
    they did is the less surprising default."""
    assert "Persistent=" not in timer_unit(a_job(schedule="06:00"), "")


def test_a_generated_unit_says_it_is_generated():
    """An edit here is invisible to `sb job list` and is overwritten on the next
    install. Saying so in the file is the only place a person editing it will
    look."""
    assert "Generated by sky.boss" in service_unit(a_job(schedule="06:00"), "")


# ---------------------------------------------------------- the collision


def test_the_payload_is_the_work_without_sky_boss_wrapping():
    """`jam report overnight` is what the operator's crontab line says too,
    which is why a collision can be found without either clock being parsed."""
    assert payload(Job("j", ["run", "--", "jam", "report", "overnight"])) == (
        "jam report overnight"
    )


def test_a_payload_too_short_to_check_says_so_rather_than_clean(monkeypatch):
    """Matching `true` against every crontab line would find a collision in
    somebody's PATH, and reporting no match for it would be worse — a detector
    that counts what it caught and never counts whether it could look answers
    `0` for both."""
    clashes, unchecked = collisions(Job("j", ["run", "--", "true"]))
    assert clashes == [] and "too short" in unchecked


def test_a_foreign_unit_running_the_same_work_is_a_collision(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    units = tmp_path / "systemd" / "user"
    units.mkdir(parents=True)
    (units / "legacy.service").write_text("[Service]\nExecStart=/usr/bin/jam report overnight\n")
    monkeypatch.setattr("cli.jobs.subprocess.run", canned(code=1))  # no crontab
    clashes, unchecked = collisions(Job("j", ["run", "--", "jam", "report", "overnight"]))
    assert unchecked == ""
    assert clashes == [("legacy.service", "ExecStart=/usr/bin/jam report overnight")]


def test_our_own_units_are_not_a_collision_with_ourselves(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    units = tmp_path / "systemd" / "user"
    units.mkdir(parents=True)
    (units / "sb-nightly.service").write_text("[Service]\nExecStart=/x/sb job run nightly\n")
    monkeypatch.setattr("cli.jobs.subprocess.run", canned(code=1))
    lines, _ = busy_lines()
    assert lines == []


def test_a_crontab_comment_is_not_a_schedule(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "none"))
    monkeypatch.setattr(
        "cli.jobs.subprocess.run",
        canned("# 0 2 * * * jam report overnight\n30 2 * * * jam report overnight\n"),
    )
    lines, scopes = busy_lines()
    assert [ln for _, ln in lines] == ["30 2 * * * jam report overnight"]
    assert "crontab" in scopes


# ---------------------------------------------------------------- install

INSTALLABLE = """
[job.nightly]
argv     = ["run", "--", "jam", "report", "overnight"]
schedule = "06:00"
"""


def installing(monkeypatch, *, clashes=()):
    monkeypatch.setattr("cli.jobs.calendar", lambda s: ("*-*-* 06:00:00", "") if s else ("", "no"))
    monkeypatch.setattr("cli.jobs.collisions", lambda j: (list(clashes), ""))


def test_install_writes_two_units_and_does_not_enable(tmp_path, monkeypatch, state):
    """Generating never enables — nothing fires until the operator runs the line
    this prints."""
    _home(tmp_path, INSTALLABLE)
    installing(monkeypatch)
    body = json.loads(run(tmp_path, monkeypatch, "install", "nightly").stdout)
    assert body["ok"] is True and body["data"]["enabled"] is False
    units = tmp_path / "xdg" / "systemd" / "user"
    assert (units / "sb-nightly.service").exists() and (units / "sb-nightly.timer").exists()
    assert "enable --now sb-nightly.timer" in body["data"]["enable_with"]


def test_install_refuses_a_collision_and_names_it(tmp_path, monkeypatch, state):
    _home(tmp_path, INSTALLABLE)
    installing(monkeypatch, clashes=[("crontab", "30 2 * * * jam report overnight")])
    result = run(tmp_path, monkeypatch, "install", "nightly")
    body = json.loads(result.stdout)
    assert body["ok"] is False and result.exit_code == 1
    assert body["data"]["found"][0]["line"] == "30 2 * * * jam report overnight"
    assert any("deactivate it first" in w for w in body["warnings"])
    # **Nothing is written on a refusal.** A half-install is the double-fire.
    assert not (tmp_path / "xdg" / "systemd" / "user").exists()


def test_force_installs_alongside_and_says_both_will_fire(tmp_path, monkeypatch, state):
    _home(tmp_path, INSTALLABLE)
    installing(monkeypatch, clashes=[("crontab", "30 2 * * * jam report overnight")])
    body = json.loads(run(tmp_path, monkeypatch, "install", "nightly", "--force").stdout)
    assert body["ok"] is True
    assert any("both will fire" in w for w in body["warnings"])


def test_an_invalid_schedule_writes_nothing(tmp_path, monkeypatch, state):
    _home(tmp_path, INSTALLABLE)
    monkeypatch.setattr("cli.jobs.calendar", lambda s: ("", "systemd rejected it"))
    result = run(tmp_path, monkeypatch, "install", "nightly")
    assert json.loads(result.stdout)["ok"] is False and result.exit_code == 1
    assert not (tmp_path / "xdg" / "systemd" / "user").exists()


def test_an_uncheckable_collision_is_reported_not_assumed_clean(tmp_path, monkeypatch, state):
    _home(tmp_path, INSTALLABLE)
    monkeypatch.setattr("cli.jobs.calendar", lambda s: ("*-*-* 06:00:00", ""))
    monkeypatch.setattr("cli.jobs.collisions", lambda j: ([], "'x' is too short to check"))
    body = json.loads(run(tmp_path, monkeypatch, "install", "nightly").stdout)
    assert any("collision not checked" in w for w in body["warnings"])


def test_install_of_an_unknown_job_names_the_declared_ones(tmp_path, monkeypatch, state):
    _home(tmp_path, INSTALLABLE)
    result = run(tmp_path, monkeypatch, "install", "nope")
    assert result.exit_code == 2 and "nightly" in result.output


# -------------------------------------------------------------- uninstall


def test_uninstall_removes_only_our_units(tmp_path, monkeypatch, state):
    _home(tmp_path, INSTALLABLE)
    units = tmp_path / "xdg" / "systemd" / "user"
    units.mkdir(parents=True)
    for name in ("sb-nightly.timer", "sb-nightly.service", "arch-update.timer"):
        (units / name).write_text("")
    body = json.loads(run(tmp_path, monkeypatch, "uninstall", "nightly").stdout)
    assert set(body["data"]["removed"]) == {"sb-nightly.timer", "sb-nightly.service"}
    assert (units / "arch-update.timer").exists(), "a foreign unit is never ours to remove"


def test_uninstall_works_for_an_orphan_whose_declaration_is_gone(tmp_path, monkeypatch, state):
    """Which is how an orphan gets cleaned up — the state `sb job list` reports
    loudly has to have a way out."""
    _home(tmp_path, "")
    units = tmp_path / "xdg" / "systemd" / "user"
    units.mkdir(parents=True)
    (units / "sb-ghost.timer").write_text("")
    body = json.loads(run(tmp_path, monkeypatch, "uninstall", "ghost").stdout)
    assert body["data"]["removed"] == ["sb-ghost.timer"]


def test_uninstalling_nothing_says_so(tmp_path, monkeypatch, state):
    _home(tmp_path, INSTALLABLE)
    body = json.loads(run(tmp_path, monkeypatch, "uninstall", "nightly").stdout)
    assert body["data"]["removed"] == []
    assert any("nothing to remove" in w for w in body["warnings"])


@pytest.mark.parametrize("name", ["../escape", "a/b", "Nightly"])
def test_uninstall_refuses_a_name_that_could_escape(name, tmp_path, monkeypatch, state):
    """The argument is not read from `jobs.toml`, so it gets the check the
    declaration would have had."""
    _home(tmp_path, INSTALLABLE)
    result = run(tmp_path, monkeypatch, "uninstall", name)
    assert result.exit_code == 2


# ============================================================================
# The act/observe bit
# ============================================================================


def test_every_job_subcommand_chooses_its_act_bit():
    """**A nested acting command defaults to observe**, and an observe may be
    given a refresh cadence — which for `sb job run` would be the *scheduler
    nobody asked for* that rule exists to prevent.

    `cli/canvas/catalog.py` derives `acts` from a **top-level** `run`, so
    anything under a group can only act by declaring `sb_acts`. All three
    acting subcommands here shipped without it and the catalog called them
    observes; nothing failed, and it was found by reading the catalog.

    So the gate is recomputed from the group's real membership rather than
    listing the three that were wrong — a list would have pinned these and
    stayed silent on the next one. `sb job enable` fails this test until
    somebody decides.
    """
    from cli.jobs import job as group

    undecided = [
        name for name, command in group.commands.items()
        if not hasattr(command, "sb_acts")
    ]
    assert not undecided, f"these must declare sb_acts: {undecided}"


def test_the_acting_subcommands_reach_the_catalog_as_acts():
    """The declaration is only worth having if the surface reads it: this is the
    property that keeps a cadence off them."""
    from cli.canvas.catalog import catalog

    entries = catalog()
    rows = entries["commands"] if isinstance(entries, dict) and "commands" in entries else entries
    acting = {row["name"] for row in rows if row.get("acts")}
    assert {"job run", "job install", "job uninstall"} <= acting
    assert "job list" not in acting and "job" not in acting


def test_every_outcome_the_code_produces_is_one_the_module_declares():
    """`OUTCOMES` was defined, documented with the reason there are five of them
    rather than two, and **read by nothing** — the five words were spelled as
    literals at six sites and the tuple sat beside them as decoration. An
    undocumented rule at least reads as unknown; a documented one with no code
    under it reads as settled, which is the worse failure of the two.

    So this recomputes the set from the source rather than listing the sites it
    knows about — listing them would pin these six and stay silent on the
    seventh. A sixth outcome, or a typo in a comparison that would silently
    never match, fails here.

    Found 2026-09-04 by sweeping this repo for the shape jam.sense reported.
    """
    import ast

    from cli.helpers import PROJECT_ROOT
    from cli.jobs import OUTCOMES

    tree = ast.parse((PROJECT_ROOT / "cli" / "jobs.py").read_text())
    found: set[str] = set()

    def strings(node: ast.AST) -> set[str]:
        return {
            n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }

    def names_outcome(node: ast.AST) -> bool:
        """A target, or a subscript, that is the outcome itself."""
        if isinstance(node, ast.Name):
            return node.id == "outcome"
        if isinstance(node, ast.Subscript):
            return isinstance(node.slice, ast.Constant) and node.slice.value == "outcome"
        return False

    for node in ast.walk(tree):
        # `outcome = "timeout"`, and `outcome, code = "ok", None`
        if isinstance(node, ast.Assign) and node.value is not None:
            targets = []
            for t in node.targets:
                targets.extend(t.elts if isinstance(t, ast.Tuple) else [t])
            if any(names_outcome(t) for t in targets):
                found |= strings(node.value)
        # `{"outcome": "refused"}`
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "outcome"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    found.add(value.value)
        # `record["outcome"] != "ok"` — a comparison against a word that is not
        # an outcome never matches, and nothing else would say so.
        elif isinstance(node, ast.Compare) and names_outcome(node.left):
            for other in node.comparators:
                found |= strings(other)

    assert found, "found no outcome strings at all — the walk has stopped working"
    undeclared = found - set(OUTCOMES)
    assert not undeclared, (
        f"cli/jobs.py produces or compares outcomes that OUTCOMES does not declare: "
        f"{sorted(undeclared)}"
    )
    unproduced = set(OUTCOMES) - found
    assert not unproduced, (
        f"OUTCOMES declares outcomes nothing produces: {sorted(unproduced)} — "
        "either the code stopped writing them or the tuple has outlived them"
    )
