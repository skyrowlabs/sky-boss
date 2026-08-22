"""--refresh — the terminal's rendering of the refresh rule. See [[refresh]].

The properties worth defending: the cadence is honored without consulting real
time, `run` never takes the flag, `--refresh` and `--json` refuse each other,
and a bare flag on a keyword adopts the keyword's own field. The mechanism is
asserted against the pure layer (`Residency`, `loop`) with an injected clock —
proving a five-second cadence must not cost five seconds of suite.
"""

import json

from click.testing import CliRunner

from cli import cli
from cli.output import Result
from cli.resident import Residency, loop, reside


class Clock:
    def __init__(self, now: float = 1_766_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def ok_result() -> Result:
    return Result(ok=True)


# ============================================================================
# The pure layer
# ============================================================================


def test_the_first_run_is_always_due():
    state = Residency("x", 30, Clock())
    assert state.due()


def test_a_run_is_due_again_only_after_the_interval():
    clock = Clock()
    state = Residency("x", 30, clock)
    state.begin()
    state.finish(ok_result())
    assert not state.due()
    clock.sleep(29)
    assert not state.due()
    clock.sleep(1)
    assert state.due()


def test_the_chrome_reads_the_same_two_numbers_the_canvas_bar_does():
    """interval and last_run — the countdown rule inherited from [[canvas]],
    computed nowhere else."""
    from cli.chrome import countdown

    clock = Clock()
    state = Residency("jam-prs", 30, clock)
    state.begin()
    state.finish(ok_result())
    clock.sleep(18)
    facts = state.chrome()
    assert facts.shape == "resident"
    assert facts.interval == 30 and facts.last_run is not None
    assert countdown(facts, clock()) == 12


def test_a_run_in_flight_wears_running_and_a_finished_one_its_verdict():
    clock = Clock()
    state = Residency("x", 30, clock)
    state.begin()
    assert state.chrome().attention == "running"
    clock.sleep(2)
    failed = Result(ok=False)
    state.finish(failed)
    assert state.chrome().attention == "failed"
    assert state.chrome().duration_s == 2


def test_the_loop_runs_when_due_and_only_redraws_otherwise():
    """The mechanism, not the timing: 61 ticks at interval 30 is exactly
    three runs — the first, and one per elapsed interval."""
    clock = Clock()
    runs, frames = [], []
    state = Residency("x", 30, clock)
    loop(
        state,
        run_once=lambda: (runs.append(clock()), ok_result())[1],
        draw=lambda result: frames.append(result is not None),
        sleep=clock.sleep,
        ticks=61,
    )
    assert len(runs) == 3
    # A tick that ran draws twice: the running frame, then the result.
    assert len(frames) == 61 + 3
    assert frames.count(True) == 3


def test_the_loop_is_bounded_under_test_and_touches_no_real_time():
    """The guard bounds time as well as frames — the loop is synchronous and
    pull-driven, so a hang cannot hide in it."""
    clock = Clock()
    state = Residency("x", 5, clock)
    loop(state, ok_result, lambda _: None, clock.sleep, ticks=10)
    assert clock.now == 1_766_000_000.0 + 10


def test_reside_renders_bands_around_the_body_and_leaves_on_interrupt():
    """The whole rendering, driven to a bound with no screen and no real
    clock; Ctrl-C mid-loop is the way out, not a failure."""
    from rich.console import Console

    clock = Clock()
    recording = Console(record=True, width=60, force_terminal=True)

    def run_once() -> Result:
        return Result(ok=True, data="the body")

    reside(
        "jam-prs", 30, run_once,
        clock=clock, sleep=clock.sleep, console=recording, screen=False, ticks=3,
    )
    text = recording.export_text()
    assert "jam-prs" in text and "refresh 30s" in text
    assert "the body" in text
    assert "ok" in text

    def interrupted() -> Result:
        raise KeyboardInterrupt

    reside(
        "jam-prs", 30, interrupted,
        clock=clock, sleep=clock.sleep, console=recording, screen=False, ticks=3,
    )  # returning at all is the assertion


# ============================================================================
# The flag on the tree
# ============================================================================


def test_run_never_takes_refresh():
    """The absence is the act/observe split made visible. Not a future
    option — a rejected one, recorded in the constitution."""
    result = CliRunner().invoke(cli, ["run", "--refresh", "5", "--", "true"])
    assert result.exit_code == 2
    assert "No such option" in result.output

    help_text = CliRunner().invoke(cli, ["run", "--help"]).output
    assert "--refresh" not in help_text


def test_read_and_data_offer_refresh_in_help():
    for command in ("read", "data"):
        help_text = CliRunner().invoke(cli, [command, "--help"]).output
        assert "--refresh" in help_text


def test_refresh_and_json_refuse_each_other():
    """An endless stream of envelopes on a pipe that expects one has no
    consumer; a machine that wants a cadence is what the canvas API is for."""
    for command in ("read", "data"):
        result = CliRunner().invoke(cli, ["--json", command, "--refresh", "5", "--", "true"])
        assert result.exit_code == 2
        assert "refuse each other" in result.output
        # And nothing envelope-shaped leaked to stdout on the way out.
        assert not result.output.strip().startswith("{")


def test_a_refresh_of_zero_is_a_usage_error_on_read_and_data():
    result = CliRunner().invoke(cli, ["read", "--refresh", "0", "--", "true"])
    assert result.exit_code == 2


def test_a_resident_read_runs_through_the_loop(monkeypatch):
    """The command hands the loop its own snapshot closure — proven by
    intercepting reside() rather than by waiting on a real residency."""
    calls = {}

    def fake_reside(source, interval, run_once, **kwargs):
        calls["source"] = source
        calls["interval"] = interval
        calls["result"] = run_once()

    monkeypatch.setattr("cli.resident.reside", fake_reside)
    result = CliRunner().invoke(cli, ["read", "--refresh", "7", "--", "printf", "hi"])
    assert result.exit_code == 0
    assert calls["interval"] == 7
    assert calls["source"] == "read -- printf hi"
    assert calls["result"].data == "hi"


# ============================================================================
# Keywords
# ============================================================================


def declare(tmp_path, toml_text):
    from cli.tools import register

    (tmp_path / "tools.toml").write_text(toml_text)
    return register(cli, home=tmp_path)


def undeclare():
    from cli.tools import tools as tools_group

    for name in [
        n for n, c in list(tools_group.commands.items()) if getattr(c, "tb_saved", False)
    ]:
        del tools_group.commands[name]


def test_a_keyword_runs_once_unless_the_flag_is_given(tmp_path):
    """The refresh field is the *canvas* default cadence; residency in a
    terminal is always asked for explicitly."""
    try:
        declare(tmp_path, '[tool.prs]\nargv = ["data", "--", "printf", "[]"]\nrefresh = 30\n')
        result = CliRunner().invoke(cli, ["--json", "tools", "prs"])
        assert json.loads(result.stdout)["ok"] is True  # ran once, exited
    finally:
        undeclare()


def test_a_bare_refresh_on_a_keyword_adopts_its_own_field(tmp_path, monkeypatch):
    calls = {}

    def fake_reside(source, interval, run_once, **kwargs):
        calls["interval"] = interval

    monkeypatch.setattr("cli.resident.reside", fake_reside)
    try:
        declare(tmp_path, '[tool.prs]\nargv = ["data", "--", "printf", "[]"]\nrefresh = 30\n')
        result = CliRunner().invoke(cli, ["tools", "prs", "--refresh"])
        assert result.exit_code == 0
        assert calls["interval"] == 30
    finally:
        undeclare()


def test_an_explicit_value_outranks_the_field(tmp_path, monkeypatch):
    calls = {}
    monkeypatch.setattr(
        "cli.resident.reside", lambda source, interval, run_once, **kw: calls.update(interval=interval)
    )
    try:
        declare(tmp_path, '[tool.prs]\nargv = ["data", "--", "printf", "[]"]\nrefresh = 30\n')
        assert CliRunner().invoke(cli, ["tools", "prs", "--refresh", "5"]).exit_code == 0
        assert calls["interval"] == 5
    finally:
        undeclare()


def test_a_bare_refresh_on_a_keyword_with_no_field_asks_for_a_value(tmp_path):
    try:
        declare(tmp_path, '[tool.prs]\nargv = ["data", "--", "printf", "[]"]\n')
        result = CliRunner().invoke(cli, ["tools", "prs", "--refresh"])
        assert result.exit_code == 2
        assert "declares no refresh" in result.output
    finally:
        undeclare()


def test_a_keyword_that_acts_has_no_refresh_option_at_all(tmp_path):
    """Same visibility rule as `run` itself: the option does not exist, so
    the split shows in --help rather than in a runtime refusal."""
    try:
        declare(tmp_path, '[tool.deploy]\nargv = ["run", "--", "true"]\n')
        result = CliRunner().invoke(cli, ["tools", "deploy", "--refresh"])
        assert result.exit_code == 2
        assert "No such option" in result.output
    finally:
        undeclare()
