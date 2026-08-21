"""tb run — the one command that acts.

It runs an argv and reports what happened. The declarative job layer that used
to sit behind it — lanes, the ledger, logs, job definitions — was removed on
2026-08-20 to start that design over, so what is left to test is small and
worth keeping honest: the envelope shape, the exit-code mapping, and the two
failure modes that are not a non-zero exit.
"""

import json
import os
import sys

from click.testing import CliRunner

from cli import cli
from cli.helpers import child_env


def _envelope(res):
    """Parse stdout, not `output`.

    Warnings go to stderr precisely so stdout stays parseable, and reading the
    mixed stream would hide the one bug this arrangement exists to prevent.
    """
    return json.loads(res.stdout)


def _run(*args):
    return CliRunner().invoke(cli, ["--json", "run", *args])


def test_a_successful_command_reports_its_output():
    res = _run("--", "echo", "hello")
    envelope = _envelope(res)

    assert res.exit_code == 0
    assert envelope["ok"] is True
    assert envelope["data"]["stdout"].strip() == "hello"
    assert envelope["data"]["exit_code"] == 0
    assert envelope["data"]["argv"] == ["echo", "hello"]


def test_a_failing_command_is_a_hard_failure_not_a_partial():
    """`partial` means some of the work succeeded. A command that exited
    non-zero did not partly run — it ran, and it failed."""
    res = _run("--", "false")
    envelope = _envelope(res)

    assert res.exit_code == 1
    assert envelope["ok"] is False
    assert envelope["partial"] is False
    assert envelope["data"]["exit_code"] != 0


def test_a_missing_command_says_so_rather_than_raising():
    res = _run("--", "definitely-not-a-real-binary-xyz")
    envelope = _envelope(res)

    assert res.exit_code == 1
    assert envelope["ok"] is False
    assert "no such command" in envelope["data"]["error"]


def test_a_timeout_is_reported_as_a_timeout():
    res = _run("--timeout", "1", "--", "sleep", "30")
    envelope = _envelope(res)

    assert res.exit_code == 1
    assert "timed out" in envelope["data"]["error"]


def test_stderr_on_an_otherwise_clean_run_is_a_warning_not_a_failure():
    """Plenty of well-behaved tools write to stderr and exit 0. Treating that
    as failure would make the envelope lie; ignoring it would hide it."""
    res = _run("--", "sh", "-c", "echo oops >&2")
    envelope = _envelope(res)

    assert res.exit_code == 0
    assert envelope["ok"] is True
    assert envelope["warnings"] == ["wrote to stderr"]
    assert envelope["data"]["stderr"].strip() == "oops"


def test_the_argv_is_never_run_through_a_shell():
    """`shell=True` would make `tb run -- echo '$HOME'` expand. Nothing here
    builds a command string, so there is nothing for a shell to reinterpret."""
    res = _run("--", "echo", "$HOME")
    assert _envelope(res)["data"]["stdout"].strip() == "$HOME"


def test_run_requires_something_to_run():
    res = CliRunner().invoke(cli, ["run"])
    assert res.exit_code == 2, "a usage error, which is Click's 2 and never tb's"


# ============================================================================
# The subprocess boundary
# ============================================================================


def test_a_spawned_command_does_not_inherit_tbs_import_path(tmp_path):
    """tb's wrapper puts this repo on PYTHONPATH so `python -m cli` resolves.
    A command tb runs is not tb and must not get it — otherwise a wrapped
    Python tool imports *this* package from anywhere on the machine.

    Asserted as the property an operator would check by hand rather than by
    inspecting the environment, so a change to how the wrapper bootstraps
    cannot quietly satisfy it.
    """
    result = CliRunner().invoke(
        cli,
        ["--json", "run", "--cwd", str(tmp_path), "--",
         sys.executable, "-c", "import cli"],
    )
    envelope = json.loads(result.stdout)
    assert envelope["data"]["exit_code"] != 0
    assert "ModuleNotFoundError" in envelope["data"]["stderr"]


def test_the_scrub_is_two_variables_and_not_a_clean_room(monkeypatch):
    """A wrapped tool needs HOME, PATH, SSH_AUTH_SOCK and whatever tokens the
    operator's shell would have given it. Only what tb added to boot is taken."""
    monkeypatch.setenv("PYTHONPATH", "/somewhere")
    monkeypatch.setenv("PYTHONSAFEPATH", "1")
    monkeypatch.setenv("TB_A_REAL_VARIABLE", "kept")

    env = child_env()
    assert "PYTHONPATH" not in env
    assert "PYTHONSAFEPATH" not in env
    assert env["TB_A_REAL_VARIABLE"] == "kept"
    # PATH is the operator's: the wrapper prepends its venv's bin, and stripping
    # that would be tb choosing which python3 a foreign tool finds.
    assert env["PATH"] == os.environ["PATH"]


def test_multi_line_output_renders_as_a_block_not_a_folded_cell(capsys):
    """An aligned table folded into a key/value cell wraps at the column edge
    and loses the alignment that was the reason to look at it."""
    from cli.output import Result, render

    render(Result("run", data={"exit_code": 0, "stdout": "PR     STATE\n#952   draft\n"}),
           as_json=False)
    out = capsys.readouterr().out
    assert "PR     STATE" in out
