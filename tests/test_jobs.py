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
