"""Tests for the surface: history recall, and that the app actually boots.

The app test drives Textual's headless pilot through `asyncio.run` rather than
adding pytest-asyncio for one case. It dispatches `run -- true`, which is a
registry and touches nothing — the suite stays free of subprocesses.
"""

import asyncio

import pytest

from textual.widgets import Static

from cli.tui.app import Transcript

from cli.tui.app import ECHO_PREFIX
from cli.tui.history import History


@pytest.fixture
def history(tmp_path):
    return History(path=tmp_path / "hist")


# ------------------------------------------------------------------- history


def test_recall_walks_backwards_then_returns_to_an_empty_line(history):
    for line in ("run -- date", "run -- echo hi", "run --help"):
        history.append(line)

    assert history.prev() == "run --help"
    assert history.prev() == "run -- echo hi"
    assert history.next() == "run --help"
    # One past the newest is the slot where you compose something new. Without
    # it, down-arrow strands you on the last command with no way back to empty.
    assert history.next() == ""
    assert history.next() is None


def test_recall_stops_at_the_oldest(history):
    history.append("check")
    assert history.prev() == "check"
    assert history.prev() is None


def test_consecutive_duplicates_are_not_recorded(history):
    history.append("check")
    history.append("check")
    assert history.lines == ["check"]


def test_a_repeat_that_is_not_consecutive_is_recorded(history):
    history.append("check")
    history.append("run -- echo hi")
    history.append("check")
    assert history.lines == ["check", "run -- echo hi", "check"]


def test_blank_lines_are_not_recorded(history):
    history.append("   ")
    assert history.lines == []


def test_submitting_returns_the_cursor_to_the_new_line_slot(history):
    history.append("check")
    history.append("run -- echo hi")
    history.prev()
    history.append("run -- echo hi")
    assert history.cursor == len(history.lines)


def test_history_survives_a_restart(tmp_path):
    first = History(path=tmp_path / "hist")
    first.append("check")
    assert History(path=tmp_path / "hist").lines == ["check"]


def test_an_unreadable_history_does_not_prevent_starting(tmp_path):
    # A convenience must never be load-bearing enough to stop the surface.
    assert History(path=tmp_path / "nope" / "hist").lines == []


def test_history_is_trimmed_to_the_limit(tmp_path):
    history = History(path=tmp_path / "hist", limit=3)
    for index in range(10):
        history.append(f"line {index}")
    assert history.lines == ["line 7", "line 8", "line 9"]


# ----------------------------------------------------------------------- app


def test_the_surface_boots_and_dispatches(tmp_path):
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test() as pilot:
            await pilot.press(*"run -- true")
            await pilot.press("enter")
            # The dispatch runs on a thread; wait for it to hand back.
            for _ in range(200):
                if not app.busy:
                    break
                await pilot.pause(0.02)
            assert not app.busy, "dispatch never completed"
            return app.transcript()

    rendered = asyncio.run(scenario())
    assert f"{ECHO_PREFIX}run -- true" in rendered
    # `run -- true` is the cheapest real dispatch there is: one builtin that
    # prints nothing and exits 0. It still renders an envelope rather than
    # nothing, which is the part worth asserting.
    assert rendered.strip() != f"{ECHO_PREFIX}run -- true"


async def _leave_idle(app, pilot):
    """The rail and the launch screen are mutually exclusive, so a test about
    the rail has to put something in the transcript first."""
    from rich.text import Text

    app.write_body(Text("x"))
    app.refresh_launch()
    await pilot.pause()


def _rendered(lines):
    return "\n".join("".join(segment.text for segment in line._segments) for line in lines)


def _drive(tmp_path, keys, patch=None):
    from cli.tui import app as app_module
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test() as pilot:
            for key in keys:
                await pilot.press(key)
                for _ in range(200):
                    if not app.busy:
                        break
                    await pilot.pause(0.02)
            return app.transcript()

    if patch is not None:
        original = app_module.last_run
        app_module.last_run = patch
        try:
            return asyncio.run(scenario())
        finally:
            app_module.last_run = original
    return asyncio.run(scenario())






def _keys(tmp_path, keys, prefill=""):
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test() as pilot:
            if prefill:
                app.query_one("#prompt").value = prefill
                app.query_one("#prompt").cursor_position = 0
            for key in keys:
                await pilot.press(key)
            await pilot.pause(0.05)
            return app.is_running, app.query_one("#prompt").value

    return asyncio.run(scenario())


def test_ctrl_d_leaves_when_the_line_is_empty(tmp_path):
    # Textual's Input binds ctrl+d to delete-right, so a plain app-level
    # binding never sees the key and the documented way out does nothing.
    # A pty smoke test caught this; the headless suite had not.
    running, _ = _keys(tmp_path, ["ctrl+d"])
    assert not running


def test_ctrl_d_still_deletes_forward_when_there_is_text(tmp_path):
    # Readline's contract. ^D is the only forward delete on a keyboard without
    # a Delete key, so taking it outright would cost more than it gained.
    running, value = _keys(tmp_path, ["ctrl+d"], prefill="check")
    assert running and value == "heck"


def test_ctrl_c_abandons_the_line_without_leaving(tmp_path):
    # Input binds ctrl+c to copy and Textual binds it to quit; the surface
    # needs it to mean neither.
    running, value = _keys(tmp_path, ["ctrl+c"], prefill="check")
    assert running and value == ""


def test_ctrl_q_always_leaves(tmp_path):
    # The unconditional exit, and the only one that helps if a thread wedges.
    running, _ = _keys(tmp_path, ["ctrl+q"])
    assert not running


def test_the_region_row_budget_adds_up():
    """The row budget is the layout. The region holds only the line being
    typed now — lanes, progress and the feed live in the rail, whose height
    comes from the terminal rather than from a constant here."""
    from cli.tui import app as module

    claimed = module.BORDER_ROWS + module.PROMPT_ROWS + module.COMPLETION_ROWS
    assert claimed == module.REPL_ROWS == 6


# ------------------------------------------------------------ launch screen


def test_the_launch_screen_is_up_at_start_and_gone_once_you_type(tmp_path):
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            before = (app.query_one("#launch").display, app.query_one(Transcript).display)
            await pilot.press(*"run -- true")
            await pilot.press("enter")
            for _ in range(300):
                if not app.busy:
                    break
                await pilot.pause(0.02)
            await pilot.pause()
            return before, (app.query_one("#launch").display, app.query_one(Transcript).display)

    (launch_first, body_first), (launch_after, body_after) = asyncio.run(scenario())
    assert launch_first and not body_first
    assert body_after and not launch_after


def test_clearing_returns_home_rather_than_to_a_blank_pane(tmp_path):
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 24)) as pilot:
            await _leave_idle(app, pilot)
            assert not app.query_one("#launch").display
            await pilot.press("ctrl+l")
            await pilot.pause()
            return app.query_one("#launch").display

    assert asyncio.run(scenario())




def test_idle_is_tracked_rather_than_read_off_the_hidden_transcript(tmp_path):
    """Asking the widget is the obvious source and unusable: while the launch
    screen is up the transcript is display:none, so it has no size and renders
    nothing, and the surface could never leave the state it was measuring."""
    from rich.text import Text

    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            # The trap: written while hidden, so lines stays empty.
            app.write_body(Text("something"))
            hidden_lines = sum(
                len(block.query(Static))
                for block in app.query_one(Transcript).query(".turn")
                if block.region.height
            )
            app.refresh_launch()
            await pilot.pause()
            return hidden_lines, app.idle, app.query_one(Transcript).display

    hidden_lines, idle, body_shown = asyncio.run(scenario())
    assert hidden_lines == 0, "precondition: a hidden RichLog renders nothing"
    assert not idle and body_shown


# -------------------------------------------------------- envelope inspector


def test_inspect_shows_the_last_envelope_without_running_anything(tmp_path):
    """--json used to mean running the command a second time. For a check that
    is wasteful; for `tb run` it is a second execution of the job."""
    from cli.tui.app import Expanded, TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.press(*"run -- true")
            await pilot.press("enter")
            for _ in range(300):
                if not app.busy:
                    break
                await pilot.pause(0.02)
            captured = app.last_envelopes
            # If this were a re-run, busy would go true again.
            await pilot.press(*"inspect")
            await pilot.press("enter")
            await pilot.pause(0.1)
            shown = isinstance(app.screen, Expanded)
            text = "\n".join(str(w.render()) for w in app.screen.query(Static)) if shown else ""
            return captured, app.busy, shown, text

    captured, busy, shown, text = asyncio.run(scenario())
    assert captured, "the dispatch should have captured an envelope"
    assert not busy, "inspect must not start a dispatch"
    assert shown and '"command": "run"' in text


def test_inspect_with_nothing_captured_says_so_rather_than_running_one(tmp_path):
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.press(*"inspect")
            await pilot.press("enter")
            await pilot.pause(0.1)
            return app.busy, list(app.queue), app.transcript()

    busy, queue, body = asyncio.run(scenario())
    assert not busy and queue == []
    assert "nothing captured" in body


def test_a_surface_verb_does_not_enter_the_dispatch_queue(tmp_path):
    """It renders something already in hand. Queueing it behind a running job
    would be theatre."""
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            app.busy = True  # a dispatch is notionally in flight
            app.start("inspect")
            await pilot.pause()
            return list(app.queue)

    assert asyncio.run(scenario()) == []


def test_the_banner_is_the_top_row_and_the_region_the_bottom(tmp_path):
    """Asserted on geometry rather than compose order.

    Child order would still pass if the CSS floated a pane somewhere else, and
    position is the whole promise: banner above, transcript in the middle,
    region at the foot of the screen.
    """
    from cli.tui.app import BANNER_ROWS, TackleBox

    height = 24

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, height)) as pilot:
            await _leave_idle(app, pilot)
            return {
                name: app.query_one(name).region
                for name in ("#banner", "#body", "#repl", "#prompt", "#completions")
            }

    at = asyncio.run(scenario())
    assert at["#banner"].y == 0
    # The region is directly under the banner, and the transcript under it, so
    # the newest result sits against the line that asked for it.
    assert at["#repl"].y == BANNER_ROWS
    assert at["#body"].y == at["#repl"].bottom
    assert at["#body"].bottom == height


def test_the_input_is_the_first_row_of_the_region_not_the_last(tmp_path):
    """The region sits at the foot of the screen, but the input sits at the
    top of the region — directly under the rule, level with the help pane's
    title, so a line and its explanation read across. Everything else in the
    region describes that line and hangs below or beside it."""
    from cli.tui.app import BORDER_ROWS, TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            return {
                name: app.query_one(name).region
                for name in ("#repl", "#prompt", "#completions", "#helppane")
            }

    at = asyncio.run(scenario())
    # The rule sits on the bottom edge, so the input is the
    # region's very first row. It is still the *first*, which is the part that
    # was never about where the region sits.
    assert at["#prompt"].y == at["#repl"].y
    # Candidates hang below the line they complete, not at the foot of the pane.
    assert at["#completions"].y == at["#prompt"].bottom
    # Level with the help pane's first row, which is the point of the move.
    assert at["#helppane"].y == at["#prompt"].y






















# ------------------------------------------------- progressive disclosure


def test_clicking_a_truncated_pane_shows_it_whole(tmp_path):
    from cli.tui.app import Expanded, TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.press(*"run")
            await pilot.pause(0.1)
            narrow = str(app.query_one("#helppane").render())
            await pilot.click("#helppane")
            await pilot.pause(0.1)
            assert isinstance(app.screen, Expanded)
            full = "\n".join(str(w.render()) for w in app.screen.query(Static))
            return narrow, full

    narrow, full = asyncio.run(scenario())
    # The pane truncates; the expansion is the escape hatch from that.
    assert "…" in narrow
    assert "Give up after this many seconds." in full


def test_the_transcript_is_never_parsed_as_markup(tmp_path):
    """Disclosure is chrome-only. A tool printing a bracketed path keeps it —
    that is why chrome, not the transcript, got the clickable treatment.

    The `RichLog` this used to assert on carried `markup=False`. Blocks are
    `Static`s now, and a `Static` given an already-built `Text` never parses
    markup at all: the bracket survives because it was never a tag.
    """
    from rich.text import Text

    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 24)) as pilot:
            app.write_body(Text("[/home/you] [bold]not a style[/bold]"))
            app.refresh_launch()
            await pilot.pause()
            return app.transcript()

    rendered = asyncio.run(scenario())
    assert "[/home/you]" in rendered and "[bold]" in rendered


# ------------------------------------------------------------- separators




def test_a_divider_cannot_be_dragged_past_a_pane_it_would_erase(tmp_path):
    """One divider left, between the input and the help pane. The rail's went
    with the rail."""
    from cli.tui.app import Separator, TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(140, 24)) as pilot:
            await _leave_idle(app, pilot)
            sep = app.query_one("#replsep", Separator)
            for _ in range(20):  # shove it hard, into the pane it would erase
                app.post_message(Separator.Dragged(sep, -40))
                await pilot.pause()
            return app.query_one("#inputpane").outer_size.width

    from cli.tui.app import TackleBox as App

    assert asyncio.run(scenario()) >= App.MIN_INPUT


def test_the_input_pane_takes_twice_the_help_pane(tmp_path):
    """The command line is the longest string on the surface; the help pane is
    built to truncate. That is why the split is 2fr/1fr and not even."""
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(96, 24)) as pilot:
            await pilot.pause()
            return (
                app.query_one("#inputpane").region.width,
                app.query_one("#helppane").region.width,
            )

    wide, narrow = asyncio.run(scenario())
    assert wide > narrow
    assert abs(wide - 2 * narrow) <= 2  # 2fr/1fr, give or take the border


def test_the_help_pane_tracks_the_line_being_typed(tmp_path):
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(96, 24)) as pilot:
            await pilot.press(*"ru")
            await pilot.pause(0.1)
            return str(app.query_one("#helppane").render())

    # No dispatch was run; the pane explains the line without one.
    assert "Run a command" in asyncio.run(scenario())


def test_the_banner_names_the_surface(tmp_path):
    from cli.tui.app import BANNER_TEXT, TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test() as pilot:
            await pilot.pause()
            return str(app.query_one("#banner").render())

    assert BANNER_TEXT in asyncio.run(scenario())


def test_completions_render_in_the_region_not_the_transcript(tmp_path):
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test() as pilot:
            app.query_one("#prompt").value = ""
            app.query_one("#prompt").cursor_position = 0
            await pilot.press("tab")
            await pilot.pause(0.05)
            shown = app.query_one("#completions").render()
            return str(shown), app.transcript()

    completions, body = asyncio.run(scenario())
    assert "run" in completions and "tui" in completions
    # Chrome in the transcript would mix it into the record of what was run.
    assert "run  tui" not in body


# ------------------------------------------------------- a large result
#
# The surface used to be freezable by one chatty command. `RichLog.write` is
# superlinear in the size of a single renderable and runs on the event loop, so
# a big enough result blocked long enough that no key — including the ones that
# leave — was ever read. These pin the two halves of the fix.


def _write_and_time(tmp_path, text):
    """Write `text` to the transcript and report the worst single loop block.

    The heartbeat is the whole point: asserting on the *duration of the write
    call* would pass just as well if the write were merely fast, and what has to
    hold is that the loop kept getting turns. A timer that never fires is the
    failure this is looking for.
    """
    import time

    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 40)) as pilot:
            # The transcript is `display: none` while the launch screen is up,
            # so a RichLog with no size defers every write instead of doing one.
            # Measuring against a hidden widget measures nothing.
            await _leave_idle(app, pilot)
            beats = []
            last = time.monotonic()

            def beat():
                nonlocal last
                now = time.monotonic()
                beats.append(now - last)
                last = now

            app.set_interval(0.01, beat)
            await pilot.pause()
            last = time.monotonic()
            app.write_body(text)
            await pilot.pause()
            await pilot.pause()
            return max(beats or [0.0]), app.transcript()

    return asyncio.run(scenario())


def test_a_huge_result_does_not_freeze_the_surface(tmp_path):
    from rich.text import Text

    # Comfortably past where the old path became unusable: 120k lines blocked
    # the loop for 17.5s before this was bounded.
    worst, _ = _write_and_time(tmp_path, Text("\n".join(f"line {n}" for n in range(200_000))))
    assert worst < 1.0, f"the event loop was blocked for {worst:.2f}s"


def test_a_huge_result_is_truncated_and_says_so(tmp_path):
    from rich.text import Text

    from cli.tui.app import TRANSCRIPT_MAX_LINES

    over = TRANSCRIPT_MAX_LINES + 5_000
    _, rendered = _write_and_time(tmp_path, Text("\n".join(f"line {n}" for n in range(over))))

    assert "line 0" in rendered, "the beginning of the output is what gets kept"
    assert f"line {TRANSCRIPT_MAX_LINES - 1}" in rendered
    assert f"line {over - 1}" not in rendered, "nothing past the ceiling should be on screen"
    # The count is what makes truncation honest rather than silent.
    assert "5,000 more lines not shown" in rendered
    assert "inspect" in rendered


def test_ordinary_output_is_not_truncated_or_reordered(tmp_path):
    from rich.text import Text

    _, rendered = _write_and_time(tmp_path, Text("\n".join(f"line {n}" for n in range(2_500))))

    assert "more lines not shown" not in rendered
    body = [line for line in rendered.splitlines() if line.startswith("line ")]
    # Chunking must not disturb order — it writes 1,000 at a time and the
    # slices have to arrive in the order they were cut.
    assert body == [f"line {n}" for n in range(2_500)]


def test_the_transcript_is_bounded(tmp_path):
    """Counted in turns now, which is the unit this layout has. A turn is
    already bounded at TRANSCRIPT_MAX_LINES by `write_body`, so the product of
    the two is the ceiling — the transcript cannot grow without limit in a
    surface designed to be left open for days."""
    from cli.tui.app import MAX_TURNS, TackleBox

    async def scenario():
        from rich.text import Text

        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 40)) as pilot:
            await _leave_idle(app, pilot)
            _no_dispatch(app)
            for n in range(MAX_TURNS + 25):
                app.start(f"turn {n}")
                app.busy = False  # let the next one start rather than queue
            await pilot.pause()
            return app.turns()

    turns = asyncio.run(scenario())
    assert len(turns) <= MAX_TURNS
    # The oldest go, not the newest — dropping from the wrong end would throw
    # away the thing you are looking at.
    assert f"turn {MAX_TURNS + 24}" in turns[0]


def test_a_non_text_renderable_still_reaches_the_transcript(tmp_path):
    """The rail's renderables and anything else that is not a Text must pass
    through untouched — the bounding is for command output, not for chrome."""
    from rich.table import Table

    from cli.tui.app import _bounded_chunks

    table = Table()
    assert list(_bounded_chunks(table)) == [table]


def test_truncating_the_transcript_does_not_touch_the_envelope(tmp_path):
    """Truncation is only ever a display decision.

    This is what makes the ceiling defensible: the surface stops *showing* the
    rest, it does not stop *having* it. `inspect` renders `last_envelopes`, and
    a run's output is whole in its log either way.
    """
    from cli.tui.app import TRANSCRIPT_MAX_LINES, TackleBox
    from cli.tui.dispatch import Dispatch

    envelope = {"ok": True, "data": {"rows": list(range(50))}, "warnings": []}
    huge = "\n".join(f"line {n}" for n in range(TRANSCRIPT_MAX_LINES + 2_000))
    result = Dispatch("check --list", huge, 0, (envelope,))

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 40)) as pilot:
            await _leave_idle(app, pilot)
            app.finished(result)
            await pilot.pause()
            return app.last_envelopes, app.transcript()

    envelopes, rendered = asyncio.run(scenario())

    assert "2,000 more lines not shown" in rendered, "the transcript was bounded"
    assert envelopes == (envelope,), "the envelope survived whole"
    assert envelopes[0]["data"]["rows"][-1] == 49


# ------------------------------------------------------------- leaving
#
# A thread worker cannot be cancelled. `App.exit()` calls `workers.cancel_all()`,
# which for a thread cancels only the awaiting task — so a wedged `tb run` used
# to cost 300s of dead terminal (asyncio's THREAD_JOIN_TIMEOUT) after the UI had
# visibly gone. Measured out of process: 300s -> 0.24s. These pin the mechanism
# rather than the duration, so the suite stays free of subprocesses.


def test_a_parked_worker_thread_is_noticed(tmp_path):
    import threading

    from cli.tui.app import _worker_thread_still_running

    assert not _worker_thread_still_running(), "nothing should be running yet"

    release = threading.Event()
    worker = threading.Thread(target=release.wait, daemon=False)
    worker.start()
    try:
        assert _worker_thread_still_running()
    finally:
        release.set()
        worker.join()

    assert not _worker_thread_still_running()


def test_a_daemon_thread_is_not_a_reason_to_leave_hard(tmp_path):
    """The stall watchdog is a daemon and must not make every exit a hard one —
    only threads a clean interpreter exit would actually wait for count."""
    import threading

    from cli.tui.app import _worker_thread_still_running

    release = threading.Event()
    watchdog = threading.Thread(target=release.wait, daemon=True)
    watchdog.start()
    try:
        assert not _worker_thread_still_running()
    finally:
        release.set()
        watchdog.join()


class _StubApp:
    """Stands in for the whole surface.

    Patching `TackleBox.run` is not enough: `run()` constructs the app, and a
    real one loads history from the state directory. `TB_HOME` is redirected for
    the suite but `STATE_DIR` is not, so building one here would read whatever
    the machine happens to have — the failure conftest exists to prevent.
    """

    seen: dict = {}

    def __init__(self):
        import threading

        self.watchdog = type("W", (), {"stop": lambda self: None})()
        _StubApp.seen = {}

    def run(self, **kwargs):
        _StubApp.seen = kwargs


def test_the_surface_runs_on_a_loop_it_owns(monkeypatch):
    """Not `asyncio.run`. Owning the loop is what skips the first of the two
    joins; the second is skipped by leaving through `os._exit`."""
    import asyncio as _asyncio

    from cli.tui import app as app_module

    monkeypatch.setattr(app_module, "TackleBox", _StubApp)
    monkeypatch.setattr(app_module, "_worker_thread_still_running", lambda: False)
    app_module.run()

    assert isinstance(_StubApp.seen.get("loop"), _asyncio.AbstractEventLoop)


def test_a_wedged_worker_does_not_delay_leaving(monkeypatch):
    import threading

    from cli.tui import app as app_module

    hard_exits = []
    release = threading.Event()
    worker = threading.Thread(target=release.wait, daemon=False)

    monkeypatch.setattr(app_module, "TackleBox", _StubApp)
    monkeypatch.setattr(app_module.os, "_exit", lambda code: hard_exits.append(code))

    worker.start()
    try:
        app_module.run()
    finally:
        release.set()
        worker.join()

    assert hard_exits == [0], "a live worker must be left behind, not joined"


def test_leaving_is_ordinary_when_nothing_is_wedged(monkeypatch):
    """The hard exit is the exception, not the path every session takes."""
    from cli.tui import app as app_module

    hard_exits = []
    monkeypatch.setattr(app_module, "TackleBox", _StubApp)
    monkeypatch.setattr(app_module.os, "_exit", lambda code: hard_exits.append(code))
    monkeypatch.setattr(app_module, "_worker_thread_still_running", lambda: False)

    app_module.run()
    assert hard_exits == []
























# ----------------------------------------------------------- newest first
#
# The region is at the top and turns stack newest-first beneath it. Content *within* a turn still reads top-to-bottom —
# reversing the lines of a table is not what anyone means by "newest first".


def _no_dispatch(app):
    """Stub the thread worker.

    These tests are about which block a line's output lands in, not about what
    Click does with it. Left real, every made-up line here would dispatch, fail,
    and write a usage error into the block being asserted on.
    """
    app.work = lambda line, width: None


def _turns_after(tmp_path, lines):
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            _no_dispatch(app)
            for line in lines:
                app.start(line)
            await pilot.pause()
            return app.turns()

    return asyncio.run(scenario())


def test_turns_stack_newest_first(tmp_path):
    turns = _turns_after(tmp_path, ["first", "second", "third"])

    assert f"{ECHO_PREFIX}third" in turns[0]
    assert f"{ECHO_PREFIX}second" in turns[1]
    assert f"{ECHO_PREFIX}first" in turns[2]


def test_content_within_a_turn_is_not_reversed(tmp_path):
    """The half of "newest first" that must not be applied. A result read
    bottom-up is a table upside down."""
    from rich.text import Text

    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.start("a command")
            app.write_body(Text("row one\nrow two\nrow three"))
            await pilot.pause()
            return app.turns()[0]

    block = asyncio.run(scenario())
    assert block.index("row one") < block.index("row two") < block.index("row three")
    # And the echo leads its own block rather than trailing it.
    assert block.index(ECHO_PREFIX) < block.index("row one")


def test_a_result_lands_in_the_block_its_own_line_opened(tmp_path):
    """The ordering bug the flat transcript hid. A line typed while a dispatch
    is running is queued and echoes immediately, so two blocks can be open
    before the first result arrives — the queue carries the block so a result
    cannot be written into the wrong one."""
    from rich.text import Text

    from cli.tui.app import TackleBox
    from cli.tui.dispatch import Dispatch

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            _no_dispatch(app)
            app.start("first")
            # "first" is now in flight, so "second" queues — and echoes anyway,
            # opening a second block before the first has answered.
            app.start("second")
            assert app.busy and len(app.queue) == 1
            # "first" comes back long after "second" was echoed.
            app.finished(Dispatch("first", "output of first", 0, ()))
            await pilot.pause()
            return app.turns()

    turns = asyncio.run(scenario())
    newest, older = turns[0], turns[1]
    assert f"{ECHO_PREFIX}second" in newest
    assert "output of first" not in newest, "the result landed in the wrong block"
    assert f"{ECHO_PREFIX}first" in older and "output of first" in older


def test_the_freeze_guard_still_holds_for_the_new_widget(tmp_path):
    """The bound is on `write_body`, which is the only door in —
    but the widget behind it changed, so the guard is re-measured rather than
    assumed to have survived."""
    from rich.text import Text

    worst, _ = _write_and_time(tmp_path, Text("\n".join(f"line {n}" for n in range(200_000))))
    assert worst < 1.0, f"the event loop was blocked for {worst:.2f}s"
