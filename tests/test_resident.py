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
        wait=clock.sleep,
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
        clock=clock, wait=clock.sleep, console=recording, screen=False, ticks=3,
    )
    text = recording.export_text()
    assert "jam-prs" in text and "refresh 30s" in text
    assert "the body" in text
    assert "ok" in text

    def interrupted() -> Result:
        raise KeyboardInterrupt

    reside(
        "jam-prs", 30, interrupted,
        clock=clock, wait=clock.sleep, console=recording, screen=False, ticks=3,
    )  # returning at all is the assertion


# ============================================================================
# The flag on the tree
# ============================================================================


def test_run_never_takes_refresh(said):
    """The absence is the act/observe split made visible. Not a future
    option — a rejected one, recorded in the constitution."""
    result = CliRunner().invoke(cli, ["run", "--refresh", "5", "--", "true"])
    assert result.exit_code == 2
    # Named rather than generic since [[delay]]: Click's bare "No such option"
    # teaches nothing to the person whose next instinct is that `--delay` is
    # the same thing wearing a coat. The option is hidden and exists only to
    # refuse well, so it must still not appear in help.
    # Read through `said`: rich-click wraps into a box, so a phrase can be
    # broken by a newline *and* by the border. Asserting on raw output is a
    # test about the terminal rather than about the refusal.
    assert "scheduler nobody asked for" in said(result)
    assert "--delay" in said(result)

    help_text = CliRunner().invoke(cli, ["run", "--help"]).output
    assert "--refresh" not in help_text


def test_read_and_data_offer_refresh_in_help():
    for command in ("read", "data"):
        help_text = CliRunner().invoke(cli, [command, "--help"]).output
        assert "--refresh" in help_text


def test_refresh_and_json_still_refuse_each_other_on_read(said):
    """`read` is verbatim by contract and has no envelope worth streaming, so
    the round-3 refusal stands there. `data` was overruled — see below."""
    result = CliRunner().invoke(cli, ["--json", "read", "--refresh", "5", "--", "true"])
    assert result.exit_code == 2
    assert "refuse each other" in said(result)
    # And nothing envelope-shaped leaked to stdout on the way out.
    assert not said(result).strip().startswith("{")


def test_json_refresh_on_data_streams_instead_of_refusing(monkeypatch):
    """[[refresh]] round 4, reversing round 3 on the operator's ruling.

    `--json` is the flag that *means* machine output, so it was the one thing
    that could not have a cadence. It now takes the same path a pipe does.

    Asserted by intercepting the loop rather than running it: residency is
    endless, and a test that invoked it for real would hang rather than fail —
    which is exactly what happened when this change first landed.
    """
    seen = {}
    monkeypatch.setattr(
        "cli.output.resident_ndjson",
        lambda once, interval, **kw: seen.update(interval=interval, once=once),
    )
    result = CliRunner().invoke(cli, ["--json", "data", "--refresh", "5", "--", "printf", "[]"])
    assert result.exit_code == 0
    assert seen["interval"] == 5


def test_a_refresh_of_zero_is_a_usage_error_on_read_and_data():
    result = CliRunner().invoke(cli, ["read", "--refresh", "0", "--", "true"])
    assert result.exit_code == 2


def test_a_resident_read_runs_through_the_loop(monkeypatch, at_a_terminal):
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
        n for n, c in list(tools_group.commands.items()) if getattr(c, "sb_saved", False)
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


def test_a_bare_refresh_on_a_keyword_adopts_its_own_field(tmp_path, monkeypatch, at_a_terminal):
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


def test_an_explicit_value_outranks_the_field(tmp_path, monkeypatch, at_a_terminal):
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


# ============================================================================
# Leaving, and staying in place — [[refresh]] round 2
# ============================================================================


def test_a_leave_key_ends_the_loop_before_its_ticks_are_spent():
    """`q` is the way a view is closed. It must not wait for the tick to be
    over, and it must not need the bound to stop the loop."""
    clock = Clock()
    frames = []
    state = Residency("x", 30, clock)
    keys_pressed = iter([None, None, "q"])

    def wait(seconds):
        clock.sleep(seconds)
        return next(keys_pressed, None)

    loop(state, ok_result, lambda r: frames.append(r), wait, ticks=100)
    # Three ticks drawn, then gone — not a hundred.
    assert clock.now == 1_766_000_000.0 + 3


def test_esc_leaves_and_an_ordinary_key_does_not():
    for key, expected_ticks in (("\x1b", 1), ("j", 5)):
        clock = Clock()
        state = Residency("x", 30, clock)
        loop(state, ok_result, lambda _: None, lambda s: (clock.sleep(s), key)[1], ticks=5)
        assert clock.now == 1_766_000_000.0 + expected_ticks


def test_the_body_is_clipped_to_the_room_inline_has():
    """An inline redraw can only repaint what it can address, so a frame
    taller than the terminal would append instead of replacing."""
    from rich.text import Text

    from cli.resident import clip

    body = Text("\n".join(f"line {i}" for i in range(50)))
    out = clip(body, 10)
    lines = out.plain.split("\n")
    assert len(lines) == 10
    assert "more lines not shown" in lines[-1]
    assert "--screen" in lines[-1]


def test_a_body_that_fits_is_left_exactly_alone():
    from rich.text import Text

    from cli.resident import clip

    body = Text("one\ntwo\nthree")
    assert clip(body, 10).plain == body.plain


def test_the_alternate_screen_is_no_longer_the_default():
    """The reversal, asserted where it is easiest to regress. Round 1 took the
    screen and the output vanished on exit; inline leaves the last frame the
    way a one-shot does."""
    import inspect

    from cli.resident import reside

    assert inspect.signature(reside).parameters["screen"].default is False


def test_read_and_data_offer_screen_in_help(said):
    for command in ("read", "data"):
        help_text = said(CliRunner().invoke(cli, [command, "--help"]))
        assert "--screen" in help_text
        assert "alternate screen" in help_text


def test_the_refresh_help_says_how_to_leave(said):
    """Help is the doc ([[refresh]]) — and the one thing the operator needed
    and could not find was the way out."""
    for command in ("read", "data"):
        help_text = said(CliRunner().invoke(cli, [command, "--help"]))
        assert "q, Esc or Ctrl-C to leave" in help_text


def test_the_screen_flag_reaches_the_resident_loop(monkeypatch, at_a_terminal):
    seen = {}
    monkeypatch.setattr(
        "cli.resident.reside",
        lambda source, interval, run_once, **kw: seen.update(kw),
    )
    CliRunner().invoke(cli, ["read", "--refresh", "5", "--screen", "--", "printf", "hi"])
    assert seen["screen"] is True
    seen.clear()
    CliRunner().invoke(cli, ["read", "--refresh", "5", "--", "printf", "hi"])
    assert seen["screen"] is False


# ============================================================================
# Which end the clip keeps — [[follow]] round 2
# ============================================================================


def test_a_stream_body_is_clipped_from_the_tail_with_the_marker_leading():
    """A snapshot's interesting end is the top; a stream's is the bottom. The
    shared helper takes a direction rather than being correct for its first
    caller and silently wrong for its second."""
    from rich.text import Text

    from cli.resident import clip

    body = Text("\n".join(f"line {i}" for i in range(50)))
    out = clip(body, 10, tail=True).plain.split("\n")
    assert len(out) == 10
    assert "more lines not shown" in out[0]  # the marker leads, where the
    assert out[1:] == [f"line {i}" for i in range(41, 50)]  # dropped lines went


def test_the_head_clip_is_untouched_by_the_direction_landing():
    from rich.text import Text

    from cli.resident import clip

    body = Text("\n".join(f"line {i}" for i in range(50)))
    out = clip(body, 10).plain.split("\n")
    assert out[:9] == [f"line {i}" for i in range(9)]
    assert "more lines not shown" in out[-1]


def test_clipping_a_stream_does_not_repaint_the_body():
    """The defect the operator reported as "the default colour for `sb follow`
    is yellow". `Text(marker, style=...)` sets the *base* style of the whole
    object, so everything appended after the dropped-lines marker inherited
    warn — and because a follow's ring always outruns the terminal, every
    inline frame is clipped and every line came out yellow. The marker is a
    span, not a base style."""
    from rich.text import Text

    from cli.resident import clip

    body = Text()
    for i in range(40):
        body.append("value", style="sb.num")
        body.append(f" {i}\n")

    out = clip(body, 10, tail=True)
    assert out.style == ""  # nothing inherits the marker's warn
    warn = [s for s in out.spans if str(s.style) == "sb.warn"]
    assert len(warn) == 1
    assert out.plain[warn[0].start : warn[0].end].startswith("31 more lines")
    # ...and the body's own roles survived the cut.
    assert any(str(s.style) == "sb.num" for s in out.spans)


# ============================================================================
# A cadence needs a screen — [[refresh]] round 3
# ============================================================================


def test_a_piped_refresh_on_read_is_still_a_usage_error_not_a_silence():
    """The defect round 3 closed: `--refresh … | cat` rendered 0 bytes and never
    exited, because `rich.Live` owns a cursor and a pipe has none. Residency is
    endless, so the caller did not get a wrong answer — it hung, and a refusal
    is a sentence where a hang is not.

    Still the answer for `read`, whose output is verbatim text. `data` answers
    it a different way now — with a stream of envelopes. See round 4."""
    result = CliRunner().invoke(cli, ["read", "--refresh", "2", "--", "printf", "hi"])
    assert result.exit_code == 2
    assert "needs a terminal" in result.output


def test_the_refusal_names_the_fix():
    result = CliRunner().invoke(cli, ["read", "--refresh", "2", "--", "printf", "hi"])
    assert "drop it for a single read" in result.output


def test_a_piped_refresh_on_data_streams_ndjson(monkeypatch):
    """The reversal itself: off a terminal, `data --refresh` goes to the NDJSON
    loop instead of raising. Intercepted, never run — endless by nature."""
    seen = {}
    monkeypatch.setattr(
        "cli.output.resident_ndjson",
        lambda once, interval, **kw: seen.update(interval=interval),
    )
    result = CliRunner().invoke(cli, ["data", "--refresh", "2", "--", "printf", "[]"])
    assert result.exit_code == 0
    assert seen["interval"] == 2


def test_screen_does_not_exempt_it():
    """The alternate screen is *more* of a terminal requirement, not less."""
    result = CliRunner().invoke(
        cli, ["read", "--refresh", "2", "--screen", "--", "printf", "hi"]
    )
    assert result.exit_code == 2


def test_a_single_read_is_untouched_off_a_terminal():
    """The refusal is about the cadence, not about the pipe. Everything without
    `--refresh` must keep working exactly as it did — this is the whole reason
    it is a usage error on one flag rather than a mode."""
    result = CliRunner().invoke(cli, ["read", "--", "printf", "hi"])
    assert result.exit_code == 0
    assert "hi" in result.output


def test_the_refusal_fires_before_save_writes(tmp_path, monkeypatch):
    """Same ordering its sibling documents: `--save` writes before it runs, so a
    refusal raised inside the resident path would fire after the append — a name
    taken, a file changed, and a failure reported."""
    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)
    result = CliRunner().invoke(
        cli, ["read", "--refresh", "30", "--save", "prs", "--", "printf", "hi"]
    )
    assert result.exit_code == 2
    assert not (tmp_path / "tools.toml").exists()


def test_a_terminal_still_goes_resident(at_a_terminal, monkeypatch):
    reached = {}
    monkeypatch.setattr(
        "cli.resident.reside",
        lambda source, interval, run_once, **kw: reached.update(interval=interval),
    )
    result = CliRunner().invoke(cli, ["read", "--refresh", "7", "--", "printf", "hi"])
    assert result.exit_code == 0
    assert reached == {"interval": 7}


# ============================================================================
# The stream a pipe gets — [[refresh]] round 4
# ============================================================================


def test_each_tick_is_one_line_and_carries_its_number(capsys):
    """NDJSON: one object per line, in order, so a consumer sees tick N before
    tick N+1 exists. Bounded by `ticks` and driven by an injected clock — the
    rule `CLAUDE.md` states as *bound every wait* and *assert against the
    mechanism, not the timing*."""
    from cli.output import Result, resident_ndjson

    made = []

    def once():
        made.append(1)
        return Result(data={"rows": [{"n": len(made)}]})

    resident_ndjson(once, 5, clock=lambda: 1756000000.0, sleep=lambda _: None, ticks=3)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 3
    assert [json.loads(ln)["tick"] for ln in lines] == [1, 2, 3]
    assert [json.loads(ln)["data"]["rows"][0]["n"] for ln in lines] == [1, 2, 3]


def test_a_tick_line_is_the_single_shot_envelope_plus_two_keys(capsys):
    """The contract that makes this cheap to consume: each line is exactly what
    `sb --json data` prints for that tick, plus `tick` and `at`. A slimmer
    per-tick record would be a second data contract to keep in step."""
    from cli.output import Result, resident_ndjson

    result = Result(data={"rows": [{"a": 1}]}, warnings=["careful"])
    resident_ndjson(lambda: result, 5, clock=lambda: 1756000000.0, sleep=lambda _: None, ticks=1)
    line = json.loads(capsys.readouterr().out.strip())

    assert set(line) - set(result.to_dict()) == {"tick", "at"}
    for key, value in result.to_dict().items():
        assert line[key] == value, key


def test_the_tick_timestamp_is_an_instant_not_a_wall_clock(capsys):
    """`08:50:02` is what a band draws for a human reading one screen. A machine
    consumer needs an unambiguous instant, and a bare time-of-day is not one."""
    from cli.output import Result, resident_ndjson

    resident_ndjson(
        lambda: Result(data={}), 5, clock=lambda: 1756000000.0, sleep=lambda _: None, ticks=1
    )
    at = json.loads(capsys.readouterr().out.strip())["at"]
    assert at.startswith("2025-") or at.startswith("2026-")
    assert at.endswith("+00:00") or at.endswith("Z")


def test_a_warning_rides_the_line_and_is_not_reprinted_every_tick(capsys):
    """A one-shot prints warnings to stderr as well, because a human may be
    reading either. A stream would reprint the same warning forever, and nothing
    is lost — `warnings` is a field on every line."""
    from cli.output import Result, resident_ndjson

    resident_ndjson(
        lambda: Result(data={}, warnings=["careful"]),
        5,
        clock=lambda: 1756000000.0,
        sleep=lambda _: None,
        ticks=2,
    )
    captured = capsys.readouterr()
    assert all(json.loads(ln)["warnings"] == ["careful"] for ln in captured.out.splitlines() if ln.strip())
    assert "careful" not in captured.err


def test_a_consumer_that_leaves_ends_the_stream_without_reporting_a_failure():
    """`… --refresh 2 | head -3` is a normal way to use this, and the consumer
    leaving is how it ends. Left unhandled the BrokenPipeError surfaced as
    `✗ data failed` on stderr — the inverse of this repo's usual bug: telling
    the operator something broke when nothing did."""
    import contextlib
    import io

    from cli.output import Result, resident_ndjson

    class Closed(io.StringIO):
        def write(self, _):
            raise BrokenPipeError(32, "Broken pipe")

    ticks = []

    def once():
        ticks.append(1)
        return Result(data={})

    with contextlib.redirect_stdout(Closed()):
        resident_ndjson(once, 5, clock=lambda: 1756000000.0, sleep=lambda _: None, ticks=9)

    # Stopped at the first refused write rather than running to `ticks`.
    assert ticks == [1]


# ============================================================================
# A bound you can ask for — [[unwatched]] round 1
# ============================================================================


def test_ticks_means_refreshes_on_both_paths(monkeypatch, tmp_path):
    """**The equivalence is the whole reason this flag is safe to ship.**

    A tick is not one thing in this codebase: `resident.loop` and
    `resident._turn` count `keys.TICK` — one *second* — while the NDJSON loop
    counts one *snapshot*. `--ticks 3` therefore had two available meanings for
    the same command, three seconds on a terminal and three refreshes in a
    pipe, which is the "wrong but looks right" failure exactly. It maps to
    `runs` on both paths, and this asserts the two agree.
    """
    seen = {}
    monkeypatch.setattr(
        "cli.output.resident_ndjson",
        lambda once, interval, **kw: seen.setdefault("pipe", kw.get("runs")),
    )
    monkeypatch.setattr(
        "cli.resident.reside",
        lambda *a, **kw: seen.setdefault("tty", kw.get("runs")),
    )

    CliRunner().invoke(cli, ["data", "--refresh", "2", "--ticks", "3", "--", "printf", "[]"])
    at_a_tty = CliRunner().invoke(
        cli, ["--json", "data", "--refresh", "2", "--ticks", "3", "--", "printf", "[]"]
    )
    assert at_a_tty.exit_code == 0
    assert seen["pipe"] == 3


def test_a_run_bound_counts_runs_and_a_tick_bound_counts_turns():
    """The two units, asserted apart. `loop` polls once a second and runs only
    when due, so with a 5-second cadence three turns is *one* run."""
    from cli.resident import Residency, loop

    now = [0.0]
    runs = []

    def wait(_seconds):
        now[0] += 1.0
        return None

    state = Residency("x", 5, clock=lambda: now[0])
    loop(state, lambda: runs.append(1) or Result(), lambda _r: None, wait, ticks=3)
    assert len(runs) == 1, "three one-second turns of a five-second cadence is one run"

    now[0] = 0.0
    runs.clear()
    state = Residency("x", 5, clock=lambda: now[0])
    loop(state, lambda: runs.append(1) or Result(), lambda _r: None, wait, runs=3)
    assert len(runs) == 3, "three runs is three runs whatever the cadence"


def test_the_run_bound_leaves_its_last_frame_behind():
    """Checked after the draw, so the loop ends with its final result on
    screen — the property that makes leaving a residency leave its output."""
    from cli.resident import Residency, loop

    drawn = []
    state = Residency("x", 0, clock=lambda: 0.0)
    loop(
        state,
        lambda: Result(data={"n": len(drawn)}),
        lambda r: drawn.append(r),
        lambda _s: None,
        runs=2,
    )
    assert drawn and drawn[-1] is not None, "the last thing drawn was a result, not a countdown"


def test_ticks_without_refresh_is_refused_on_both_reads(said):
    """A bound with nothing to bound. Ignoring it would look like it was
    honoured — the command does run once and stop — which is the silence this
    repo refuses."""
    for command in ("data", "read"):
        result = CliRunner().invoke(cli, [command, "--ticks", "3", "--", "printf", "hi"])
        assert result.exit_code == 2, command
        assert "needs --refresh" in said(result)


def test_follow_refuses_ticks_and_says_why(said):
    """Not Click's "no such option": the word exists elsewhere meaning
    refreshes, and a follow has none to count. See [[unwatched]] round 2."""
    result = CliRunner().invoke(cli, ["follow", "--ticks", "2", "/tmp/nothing.log"])
    assert result.exit_code == 2
    assert "counts refreshes" in said(result)
