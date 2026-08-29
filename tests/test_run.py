"""`sb run` — the one command that acts.

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
    """`shell=True` would make `sb run -- echo '$HOME'` expand. Nothing here
    builds a command string, so there is nothing for a shell to reinterpret."""
    res = _run("--", "echo", "$HOME")
    assert _envelope(res)["data"]["stdout"].strip() == "$HOME"


def test_run_requires_something_to_run():
    res = CliRunner().invoke(cli, ["run"])
    assert res.exit_code == 2, "a usage error, which is Click's 2 and never sb's"


# ============================================================================
# The subprocess boundary
# ============================================================================


def test_a_spawned_command_does_not_inherit_tbs_import_path(tmp_path):
    """sky.boss's wrapper puts this repo on PYTHONPATH so `python -m cli` resolves.
    A command sky.boss runs is not sky.boss and must not get it — otherwise a wrapped
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
    operator's shell would have given it. Only what sky.boss added to boot is taken."""
    monkeypatch.setenv("PYTHONPATH", "/somewhere")
    monkeypatch.setenv("PYTHONSAFEPATH", "1")
    monkeypatch.setenv("SB_A_REAL_VARIABLE", "kept")

    env = child_env()
    assert "PYTHONPATH" not in env
    assert "PYTHONSAFEPATH" not in env
    assert env["SB_A_REAL_VARIABLE"] == "kept"
    # PATH is the operator's: the wrapper prepends its venv's bin, and stripping
    # that would be sky.boss choosing which python3 a foreign tool finds.
    assert env["PATH"] == os.environ["PATH"]


def test_multi_line_output_renders_as_a_block_not_a_folded_cell(capsys):
    """An aligned table folded into a key/value cell wraps at the column edge
    and loses the alignment that was the reason to look at it."""
    from cli.output import Result, render

    render(Result("run", data={"exit_code": 0, "stdout": "PR     STATE\n#952   draft\n"}),
           as_json=False)
    out = capsys.readouterr().out
    assert "PR     STATE" in out


# ── Round 1: once, later ────────────────────────────────────────────────────
#
# The clock is injected throughout, for the reason the whole chrome module is:
# proving a five-minute delay must not cost five minutes of suite.


def test_a_pending_write_carries_no_cadence():
    """`act` says it never carries a countdown and that still holds. What it
    refuses is a *cadence* — a write happening again unattended forever. This
    is one write happening once, later, which is why `fires_at` is a different
    field from `interval`."""
    from cli import chrome as chrome_

    facts = chrome_.pending("run -- ./deploy.sh", fires_at=1000.0)
    assert facts.shape == "act"
    assert facts.attention == "pending"
    assert facts.interval == 0 and facts.last_run is None


def test_the_countdown_says_what_is_left_and_how_to_stop_it():
    """A countdown you cannot see a way out of is one you watch helplessly."""
    from cli import chrome as chrome_

    facts = chrome_.pending("run -- ./deploy.sh", fires_at=1298.0)
    top, bottom = chrome_.status_lines(facts, 1000.0, 78)
    assert "runs in 4m" in top and "q cancels" in top
    assert "nothing has run yet" in bottom


def test_a_delay_that_reaches_its_moment_fires():
    from cli.run import _await

    ticks = iter([1000.0, 1000.0, 1003.0, 1003.0, 1003.0])
    assert _await(("true",), 2, clock=lambda: next(ticks), wait=lambda _: None, **_quiet()) is True


def test_leaving_the_countdown_cancels_and_nothing_runs():
    """Cancellation is not a flag, it is the clock: `hold` returns both when
    the operator leaves and when its ticks run out, and does not say which."""
    from cli.run import _await

    assert _await(("true",), 300, clock=lambda: 1000.0, wait=lambda _: "q", **_quiet()) is False


def test_cancelling_exits_non_zero():
    """A script that could not tell the difference would deploy on a
    keystroke."""
    import cli.run as run_

    calls = []
    original = run_._await
    run_._await = lambda *a, **k: False
    try:
        result = CliRunner().invoke(cli, ["run", "--delay", "5m", "--", "echo", "no"])
        assert result.exit_code == 1
        assert "no" not in result.output
    finally:
        run_._await = original
    assert calls == []


def test_a_malformed_delay_is_refused_before_anything_waits(said):
    result = CliRunner().invoke(cli, ["run", "--delay", "soon", "--", "true"])
    assert result.exit_code == 2
    assert "not a duration" in said(result)


def test_delay_and_refresh_refuse_each_other_by_naming_the_reason(said):
    result = CliRunner().invoke(cli, ["run", "--refresh", "5", "--delay", "5m", "--", "true"])
    assert result.exit_code == 2
    assert "scheduler nobody asked for" in said(result)


def _quiet():
    """A console that renders nowhere, so a countdown test prints nothing."""
    import io

    from rich.console import Console

    return {"console": Console(file=io.StringIO(), width=80), "ticks": 1}


# ---------------------------------------------------------------------------
# Round 4 — the envelope both surfaces build
# ---------------------------------------------------------------------------


def test_envelope_for_is_the_one_place_an_outcome_becomes_a_run_envelope():
    """The canvas accrues too now, and must not re-decide any of this beside
    `cli/run.py`. See [[follow]] round 4."""
    from cli.run import envelope_for
    from cli.stream import Outcome

    ok = envelope_for(["true"], Outcome(0, 0.1, "hi\n", ""), None)
    # `data` is None on success: the lines already reached the surface, on the
    # streams they arrived on. Nothing is delivered twice.
    assert ok.ok is True and ok.data is None and ok.warnings == []

    noisy = envelope_for(["x"], Outcome(0, 0.1, "", "chatter\n"), None)
    assert noisy.ok is True and noisy.warnings == ["wrote to stderr"]

    # A failure does not also warn about its stderr — the exit code said it.
    failed = envelope_for(["x"], Outcome(2, 0.1, "", "boom\n"), None)
    assert failed.ok is False and failed.warnings == []

    late = envelope_for(["sleep"], Outcome(-1, 60.0, "", "", timed_out=True), 60)
    assert late.ok is False
    assert late.data == {"argv": ["sleep"], "error": "timed out after 60s", "duration_s": 60.0}


# --- [[subprocess-env]] round 4: --env --------------------------------------


def test_env_reaches_the_child(tmp_path):
    """The whole point, end to end: a variable the operator declared is one the
    command can read."""
    from click.testing import CliRunner

    from cli import cli

    result = CliRunner().invoke(
        cli,
        ["--json", "run", "--env", "SB_DECLARED=hello", "--",
         "python3", "-c", "import os; print(os.environ['SB_DECLARED'])"],
    )
    assert result.exit_code == 0, result.output
    assert "hello" in result.output


def test_env_without_a_value_is_a_usage_error_before_anything_runs(tmp_path):
    """A dropped flag would leave a run that exits 0 and is missing the output
    the flag was added to produce — this round's own failure."""
    from click.testing import CliRunner

    from cli import cli

    marker = tmp_path / "ran"
    result = CliRunner().invoke(
        cli,
        ["run", "--env", "NOPE", "--",
         "python3", "-c", f"open({str(marker)!r}, 'w').write('x')"],
    )
    assert result.exit_code == 2  # Click's usage error
    assert "NAME=VALUE" in result.output
    assert not marker.exists(), "the command ran despite a refused --env"
