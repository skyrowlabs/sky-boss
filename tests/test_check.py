"""tb check — the group, the rollup, and the one kept alias.

What is worth testing here is not that the checks work (their own suites cover
that) but that the *grouping* holds: a check that explodes must not take the
others with it, and the rollup must never report a hard failure when its job was
only ever to report.
"""

import json

import pytest
from click.testing import CliRunner

from cli import cli
from cli.check import Check, REGISTRY, run_all
from cli.output import EXIT_OK, EXIT_PARTIAL
from cli.output import Result


def _envelope(res):
    return json.loads(res.stdout)


def test_registry_names_are_reachable_as_subcommands():
    """Every registered check must also be invocable on its own.

    A check that only exists inside the rollup cannot be run when it is the one
    you care about, and cannot be named in a job definition.
    """
    from cli.check import check

    for entry in REGISTRY:
        assert entry.name in check.commands


def test_registry_run_callables_take_no_arguments():
    """The rollup invokes every check with no arguments.

    A check whose body requires a parameter would break the rollup the moment it
    was registered, and would break it at runtime rather than at import.
    """
    for entry in REGISTRY:
        entry.run()  # must not raise TypeError


def test_list_names_checks_without_running_them(monkeypatch):
    ran = []

    def _tripwire():
        ran.append(1)
        return Result(data=[])

    monkeypatch.setattr("cli.check.REGISTRY", (Check("fake", "a fake check", _tripwire),))
    res = CliRunner().invoke(cli, ["--json", "check", "--list"])

    assert res.exit_code == EXIT_OK
    assert ran == []
    assert _envelope(res)["data"] == [{"check": "fake", "summary": "a fake check"}]


def test_list_with_a_subcommand_is_a_usage_error():
    res = CliRunner().invoke(cli, ["check", "--list", "tools"])
    assert res.exit_code == 2  # Click's usage-error code, not tb's partial


def test_rollup_is_one_row_per_check_worst_first(monkeypatch):
    def _clean():
        return Result(data=[])

    def _dirty():
        r = Result(data=[])
        r.degrade("something is wrong")
        return r

    monkeypatch.setattr(
        "cli.check.REGISTRY",
        (Check("aaa-clean", "", _clean), Check("zzz-dirty", "", _dirty)),
    )
    res = CliRunner().invoke(cli, ["--json", "check"])
    rows = _envelope(res)["data"]

    assert [r["check"] for r in rows] == ["zzz-dirty", "aaa-clean"]
    assert rows[0]["ok"] is False
    assert rows[1]["ok"] is True
    assert res.exit_code == EXIT_PARTIAL


def test_a_broken_check_degrades_the_rollup_rather_than_failing_it(monkeypatch):
    """One check raising must not hide the others, and must not read as tb breaking.

    Exit 1 would mean tb itself failed. The rollup ran, caught the explosion, and
    reported it — that is the rollup working, so it exits 3 like any other
    "something needs you" verdict.
    """
    monkeypatch.delenv("TB_DEBUG", raising=False)

    def _boom():
        raise RuntimeError("the probe exploded")

    def _clean():
        return Result(data=[])

    monkeypatch.setattr(
        "cli.check.REGISTRY",
        (Check("boom", "", _boom), Check("fine", "", _clean)),
    )
    res = CliRunner().invoke(cli, ["--json", "check"])
    envelope = _envelope(res)

    assert envelope["ok"] is True, "the rollup did its job; only a check failed"
    assert envelope["partial"] is True
    assert res.exit_code == EXIT_PARTIAL

    rows = {r["check"]: r for r in envelope["data"]}
    assert rows["boom"]["ok"] is False
    assert "the probe exploded" in rows["boom"]["detail"]
    assert rows["fine"]["ok"] is True, "the surviving check still reported"


def test_broken_check_reraises_under_tb_debug(monkeypatch):
    monkeypatch.setenv("TB_DEBUG", "1")

    def _boom():
        raise RuntimeError("the probe exploded")

    monkeypatch.setattr("cli.check.REGISTRY", (Check("boom", "", _boom),))
    with pytest.raises(RuntimeError):
        run_all()


def test_sub_check_warnings_are_carried_up_with_their_source(monkeypatch):
    """The rollup shows one row per check, so the detail has to survive somewhere.

    Without the prefix, "1 uncommitted" in the warning list is unattributable
    once several checks are reporting.
    """

    def _dirty():
        r = Result(data=[])
        r.degrade("house.fly: 1 uncommitted")
        return r

    monkeypatch.setattr("cli.check.REGISTRY", (Check("unpushed", "", _dirty),))
    res = CliRunner().invoke(cli, ["--json", "check"])

    assert _envelope(res)["warnings"] == ["unpushed: house.fly: 1 uncommitted"]


def test_doctor_alias_and_check_tools_do_the_same_work():
    alias = CliRunner().invoke(cli, ["--json", "doctor", "--quick"])
    grouped = CliRunner().invoke(cli, ["--json", "check", "tools", "--quick"])

    assert _envelope(alias)["data"] == _envelope(grouped)["data"]


def test_envelope_records_how_the_command_was_reached():
    """The alias is not a rename — the envelope names the path actually used.

    An MCP consumer reading `command` wants to know which verb it invoked, not
    which implementation happened to be underneath.
    """
    alias = CliRunner().invoke(cli, ["--json", "doctor", "--quick"])
    grouped = CliRunner().invoke(cli, ["--json", "check", "tools", "--quick"])

    assert _envelope(alias)["command"] == "doctor"
    assert _envelope(grouped)["command"] == "check.tools"
