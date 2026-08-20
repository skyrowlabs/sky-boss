"""Tests for the surface: history recall, and that the app actually boots.

The app test drives Textual's headless pilot through `asyncio.run` rather than
adding pytest-asyncio for one case. It dispatches `check --list`, which reads a
registry and touches nothing — the suite stays free of subprocesses.
"""

import asyncio

import pytest

from textual.widgets import RichLog, Static

from cli.tui.app import ECHO_PREFIX
from cli.tui.history import History


@pytest.fixture
def history(tmp_path):
    return History(path=tmp_path / "hist")


# ------------------------------------------------------------------- history


def test_recall_walks_backwards_then_returns_to_an_empty_line(history):
    for line in ("check", "info assets", "auto list"):
        history.append(line)

    assert history.prev() == "auto list"
    assert history.prev() == "info assets"
    assert history.next() == "auto list"
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
    history.append("info assets")
    history.append("check")
    assert history.lines == ["check", "info assets", "check"]


def test_blank_lines_are_not_recorded(history):
    history.append("   ")
    assert history.lines == []


def test_submitting_returns_the_cursor_to_the_new_line_slot(history):
    history.append("check")
    history.append("info assets")
    history.prev()
    history.append("auto list")
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
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test() as pilot:
            await pilot.press(*"check --list")
            await pilot.press("enter")
            # The dispatch runs on a thread; wait for it to hand back.
            for _ in range(200):
                if not app.busy:
                    break
                await pilot.pause(0.02)
            assert not app.busy, "dispatch never completed"
            return app.query_one("#body").lines

    lines = asyncio.run(scenario())
    rendered = "\n".join("".join(segment.text for segment in line._segments) for line in lines)
    assert f"{ECHO_PREFIX}check --list" in rendered
    assert "drift" in rendered and "tools" in rendered and "unpushed" in rendered


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
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test() as pilot:
            for key in keys:
                await pilot.press(key)
                for _ in range(200):
                    if not app.busy:
                        break
                    await pilot.pause(0.02)
            return _rendered(app.query_one("#body").lines)

    if patch is not None:
        original = app_module.last_run
        app_module.last_run = patch
        try:
            return asyncio.run(scenario())
        finally:
            app_module.last_run = original
    return asyncio.run(scenario())


def test_the_log_shortcut_composes_the_line_it_runs(tmp_path):
    # The point of the binding is that the run_id is never retyped — and that
    # the transcript still shows exactly what was run, rather than the surface
    # quietly reading a log file behind your back.
    entry = {"job": "doctor", "run_id": "doctor-20260819T120000-000"}
    rendered = _drive(tmp_path, ["ctrl+o"], patch=lambda *a, **k: entry)
    assert f"{ECHO_PREFIX}auto log doctor --run doctor-20260819T120000-000" in rendered


def test_the_log_shortcut_says_so_when_there_is_nothing_to_show(tmp_path):
    rendered = _drive(tmp_path, ["ctrl+o"], patch=lambda *a, **k: None)
    assert "no runs recorded yet" in rendered


def _keys(tmp_path, keys, prefill=""):
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
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
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            before = (app.query_one("#launch").display, app.query_one(RichLog).display)
            await pilot.press(*"check --list")
            await pilot.press("enter")
            for _ in range(300):
                if not app.busy:
                    break
                await pilot.pause(0.02)
            await pilot.pause()
            return before, (app.query_one("#launch").display, app.query_one(RichLog).display)

    (launch_first, body_first), (launch_after, body_after) = asyncio.run(scenario())
    assert launch_first and not body_first
    assert body_after and not launch_after


def test_clearing_returns_home_rather_than_to_a_blank_pane(tmp_path):
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            await _leave_idle(app, pilot)
            assert not app.query_one("#launch").display
            await pilot.press("ctrl+l")
            await pilot.pause()
            return app.query_one("#launch").display

    assert asyncio.run(scenario())


def test_the_rail_is_not_shown_beside_the_launch_screen(tmp_path):
    """Both list the watches. Side by side they would print them twice."""
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(140, 24)) as pilot:
            await pilot.pause()
            idle_rail = app.query_one("#rail").display
            await _leave_idle(app, pilot)
            return idle_rail, app.query_one("#rail").display

    idle_rail, busy_rail = asyncio.run(scenario())
    assert not idle_rail, "the rail should be hidden while the launch screen is up"
    assert busy_rail, "the rail should return with the transcript"


def test_idle_is_tracked_rather_than_read_off_the_hidden_transcript(tmp_path):
    """RichLog.lines is the obvious source and unusable: while the launch
    screen is up the transcript is display:none, so it has no size, renders no
    lines, and the surface could never leave the state it was measuring."""
    from rich.text import Text

    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            # The trap: written while hidden, so lines stays empty.
            app.write_body(Text("something"))
            hidden_lines = len(app.query_one(RichLog).lines)
            app.refresh_launch()
            await pilot.pause()
            return hidden_lines, app.idle, app.query_one(RichLog).display

    hidden_lines, idle, body_shown = asyncio.run(scenario())
    assert hidden_lines == 0, "precondition: a hidden RichLog renders nothing"
    assert not idle and body_shown


# -------------------------------------------------------- envelope inspector


def test_inspect_shows_the_last_envelope_without_running_anything(tmp_path):
    """--json used to mean running the command a second time. For a check that
    is wasteful; for `tb run` it is a second execution of the job."""
    from cli.tui.app import Expanded, TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.press(*"check --list")
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
    assert shown and '"command": "check"' in text


def test_inspect_with_nothing_captured_says_so_rather_than_running_one(tmp_path):
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.press(*"inspect")
            await pilot.press("enter")
            await pilot.pause(0.1)
            return app.busy, list(app.queue), _rendered(app.query_one(RichLog).lines)

    busy, queue, body = asyncio.run(scenario())
    assert not busy and queue == []
    assert "nothing captured" in body


def test_a_surface_verb_does_not_enter_the_dispatch_queue(tmp_path):
    """It renders something already in hand. Queueing it behind a running job
    would be theatre."""
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
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
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, height)) as pilot:
            await _leave_idle(app, pilot)
            return {
                name: app.query_one(name).region
                for name in ("#banner", "#body", "#repl", "#prompt", "#completions")
            }

    at = asyncio.run(scenario())
    assert at["#banner"].y == 0
    assert at["#body"].y == BANNER_ROWS
    assert at["#body"].bottom <= at["#repl"].y
    assert at["#repl"].bottom == height


def test_the_input_is_the_first_row_of_the_region_not_the_last(tmp_path):
    """The region sits at the foot of the screen, but the input sits at the
    top of the region — directly under the rule, level with the help pane's
    title, so a line and its explanation read across. Everything else in the
    region describes that line and hangs below or beside it."""
    from cli.tui.app import BORDER_ROWS, TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            return {
                name: app.query_one(name).region
                for name in ("#repl", "#prompt", "#completions", "#helppane")
            }

    at = asyncio.run(scenario())
    # First row inside the region, once its top rule is accounted for.
    assert at["#prompt"].y == at["#repl"].y + BORDER_ROWS
    # Candidates hang below the line they complete, not at the foot of the pane.
    assert at["#completions"].y == at["#prompt"].bottom
    # Level with the help pane's first row, which is the point of the move.
    assert at["#helppane"].y == at["#prompt"].y


def test_the_rail_sits_right_of_the_transcript(tmp_path):
    from cli.tui.app import BANNER_ROWS, TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            await _leave_idle(app, pilot)
            return {n: app.query_one(n).region for n in ("#banner", "#body", "#rail", "#repl")}

    at = asyncio.run(scenario())
    assert at["#body"].y == BANNER_ROWS  # transcript still starts under the banner
    assert at["#rail"].x >= at["#body"].right
    assert at["#rail"].y == at["#body"].y  # side by side, not stacked
    assert at["#rail"].bottom <= at["#repl"].y


def test_a_narrow_terminal_hides_the_rail_instead_of_squeezing_the_output(tmp_path):
    """Below the threshold the rail costs more than it is worth: it would
    leave the transcript narrower than tb's tables reflow to."""
    from cli.tui.app import RAIL_MIN_TOTAL_WIDTH, TackleBox

    async def scenario(width):
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(width, 24)) as pilot:
            await _leave_idle(app, pilot)
            rail = app.query_one("#rail")
            return rail.display, app.query_one("#body").region.width

    narrow_shown, narrow_body = asyncio.run(scenario(RAIL_MIN_TOTAL_WIDTH - 1))
    wide_shown, wide_body = asyncio.run(scenario(RAIL_MIN_TOTAL_WIDTH + 20))

    assert not narrow_shown, "the rail should be hidden below the threshold"
    assert wide_shown
    # Hidden means the transcript actually gets the width back.
    assert narrow_body == RAIL_MIN_TOTAL_WIDTH - 1


def test_the_progress_row_restacks_for_the_narrow_column(tmp_path):
    """Bar, label and timing shared a line on the old wide strip. In 31
    columns they cannot, and nothing in the rail may wrap."""
    from cli.tui.app import RAIL_WIDTH, TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            app.busy = True
            app.running_line = "run a-job-with-a-deliberately-long-name --lane committing"
            app.started_at = 0.0
            app.expected = None
            app.refresh_progress()
            await pilot.pause()
            return str(app.query_one("#progress").render())

    rendered = asyncio.run(scenario())
    assert rendered.startswith("NOW")
    for line in rendered.split("\n"):
        assert len(line) <= RAIL_WIDTH


def _watch(command="check drift", every=900):
    from cli.watch import Watch

    return {"w": Watch(name="w", command=command, every=every)}


async def _with_watch(app, pilot):
    """Attach a watch whose worker is recorded rather than run.

    Never let a test actually dispatch one: a watch is a real command, and the
    suite's whole claim is that it shells out to nothing.
    """
    started = []
    app.run_watch = lambda name, command: started.append((name, command))
    app.watches = _watch()
    await pilot.pause()
    return started


def test_a_watch_that_cannot_run_reads_unreadable_not_clear(tmp_path):
    """The home group's rule, generalised: a board that collapses "reports
    clear" into "cannot see" is worse than no board."""
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            await _with_watch(app, pilot)
            app.watch_finished("w", None)  # the dispatch itself blew up
            return str(app.query_one("#watches").render())

    assert "can't read" in asyncio.run(scenario())


def test_a_hard_failure_is_not_rendered_as_a_clean_verdict(tmp_path):
    """1 and 2 mean the check never reached a verdict. Only 0 and 3 did."""
    from cli.output import EXIT_OK, EXIT_PARTIAL
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            await _with_watch(app, pilot)
            seen = {}
            for code in (EXIT_OK, EXIT_PARTIAL, 1, 2, None):
                app.watch_finished("w", code)
                seen[code] = str(app.query_one("#watches").render())
            return seen

    seen = asyncio.run(scenario())
    assert "can't read" not in seen[0] and "can't read" not in seen[3]
    for code in (1, 2, None):
        assert "can't read" in seen[code], f"exit {code} rendered as a verdict"


def test_a_watch_refresh_does_not_queue_behind_a_dispatch(tmp_path):
    """The whole point of the read-only restriction is that these overlap. A
    watch on self.queue would make you wait to run a command, and a command
    would delay every watch behind it."""
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            started = await _with_watch(app, pilot)
            started.clear()
            app.busy = True  # pretend a dispatch is in flight
            app.refresh_watches()
            await pilot.pause()
            return started, list(app.queue)

    started, queue = asyncio.run(scenario())
    assert started == [("w", "check drift")], "the watch never started while busy"
    assert queue == [], "a watch must never enter the dispatch queue"


def test_a_watch_is_not_restarted_while_it_is_still_running(tmp_path):
    """Otherwise a check slower than its own interval stacks up copies of
    itself, and `check tools` is exactly that shape."""
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            started = await _with_watch(app, pilot)
            started.clear()
            for _ in range(5):
                app.refresh_watches()
            return started

    assert len(asyncio.run(scenario())) == 1


def test_a_watch_reads_as_unknown_before_it_has_ever_run(tmp_path):
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            await _with_watch(app, pilot)
            app.watched.clear()
            app.render_watches()
            return str(app.query_one("#watches").render())

    # Never "clear" on the strength of having no information.
    assert "○" in asyncio.run(scenario())


# ------------------------------------------------- progressive disclosure


def test_clicking_a_truncated_pane_shows_it_whole(tmp_path):
    from cli.tui.app import Expanded, TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.press(*"check drift")
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
    assert "Limit to one or more sections" in full


def test_the_transcript_is_never_parsed_as_markup(tmp_path):
    """Disclosure is chrome-only. RichLog is markup=False so a tool printing
    a bracketed path keeps it — that is why chrome, not the transcript, got
    the clickable treatment."""
    from rich.text import Text

    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 24)) as pilot:
            body = app.query_one(RichLog)
            assert not body.markup
            app.write_body(Text("[/home/you] [bold]not a style[/bold]"))
            app.refresh_launch()
            await pilot.pause()
            return _rendered(body.lines)

    rendered = asyncio.run(scenario())
    assert "[/home/you]" in rendered and "[bold]" in rendered


# ------------------------------------------------------------- separators


def test_dragging_the_rail_divider_resizes_the_rail(tmp_path):
    from cli.tui.app import Separator, TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(140, 24)) as pilot:
            await _leave_idle(app, pilot)
            before = app.query_one("#rail").outer_size.width
            sep = app.query_one("#railsep", Separator)
            # Dragging left widens the rail: it lives right of its divider.
            app.post_message(Separator.Dragged(sep, -8))
            await pilot.pause()
            return before, app.query_one("#rail").outer_size.width

    before, after = asyncio.run(scenario())
    assert after == before + 8


def test_a_divider_cannot_be_dragged_past_a_pane_it_would_erase(tmp_path):
    from cli.tui.app import Separator, TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(140, 24)) as pilot:
            await _leave_idle(app, pilot)
            sep = app.query_one("#railsep", Separator)
            for _ in range(20):  # shove it hard the other way
                app.post_message(Separator.Dragged(sep, 40))
                await pilot.pause()
            return app.query_one("#rail").outer_size.width

    from cli.tui.app import TackleBox as App

    assert asyncio.run(scenario()) >= App.MIN_RAIL


def test_the_input_pane_takes_twice_the_help_pane(tmp_path):
    """The command line is the longest string on the surface; the help pane is
    built to truncate. That is why the split is 2fr/1fr and not even."""
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
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
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(96, 24)) as pilot:
            await pilot.press(*"check dr")
            await pilot.pause(0.1)
            return str(app.query_one("#helppane").render())

    # No dispatch was run; the pane explains the line without one.
    assert "drift" in asyncio.run(scenario())


def test_the_banner_names_the_surface(tmp_path):
    from cli.tui.app import BANNER_TEXT, TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test() as pilot:
            await pilot.pause()
            return str(app.query_one("#banner").render())

    assert BANNER_TEXT in asyncio.run(scenario())


def test_completions_render_in_the_region_not_the_transcript(tmp_path):
    from cli.tui.app import TackleBox

    async def scenario():
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test() as pilot:
            app.query_one("#prompt").value = "auto l"
            app.query_one("#prompt").cursor_position = 6
            await pilot.press("tab")
            await pilot.pause(0.05)
            shown = app.query_one("#completions").render()
            return str(shown), _rendered(app.query_one("#body").lines)

    completions, body = asyncio.run(scenario())
    assert "list" in completions and "log" in completions
    # Chrome in the transcript would mix it into the record of what was run.
    assert "list  log" not in body


# ------------------------------------------------------- a large result
#
# The surface used to be freezable by one chatty command. `RichLog.write` is
# superlinear in the size of a single renderable and runs on the event loop, so
# a big enough result blocked long enough that no key — including the ones that
# leave — was ever read. These pin the two halves of the fix. See Round 2 of the
# tui feature doc.


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
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
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
            return max(beats or [0.0]), _rendered(app.query_one("#body").lines)

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
    from cli.tui.app import LOG_MAX_LINES, TRANSCRIPT_MAX_LINES

    assert LOG_MAX_LINES >= TRANSCRIPT_MAX_LINES, (
        "a single result must fit in the scrollback, or one command would evict "
        "its own first line"
    )

    from cli.tui.app import TackleBox

    async def scenario():
        from rich.text import Text

        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 40)) as pilot:
            await _leave_idle(app, pilot)
            for _ in range(12):
                app.write_body(Text("\n".join(f"x {n}" for n in range(TRANSCRIPT_MAX_LINES))))
            await pilot.pause()
            return len(app.query_one("#body").lines)

    assert asyncio.run(scenario()) <= LOG_MAX_LINES


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
        app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
        async with app.run_test(size=(120, 40)) as pilot:
            await _leave_idle(app, pilot)
            app.finished(result)
            await pilot.pause()
            return app.last_envelopes, _rendered(app.query_one("#body").lines)

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


# --------------------------------------------------- watch definitions reload
#
# Jobs have always been live; watches were loaded once in __init__ and never
# again. Two YAML files in the same home, edited the same way, and one silently
# did nothing until a restart. See Round 3 of the tui feature doc.


def _watch_file(directory, name, command="check tools", every="30s"):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.yaml").write_text(f"command: {command}\nevery: {every}\n")


def _app_watching(tmp_path, monkeypatch, directory):
    from cli.tui import app as app_module
    from cli.tui.app import TackleBox

    monkeypatch.setattr(app_module, "watch_signature", lambda: _sig(directory))
    monkeypatch.setattr(app_module, "load_watches", lambda: _load(directory))
    return TackleBox(history=History(path=tmp_path / "hist"))


def _sig(directory):
    from cli.watch import signature

    return signature(directory)


def _load(directory):
    from cli.watch import load_watches

    return load_watches(directory)


def test_a_watch_added_after_start_is_picked_up(tmp_path, monkeypatch):
    watches = tmp_path / "watches"
    watches.mkdir()
    app = _app_watching(tmp_path, monkeypatch, watches)

    assert app.watches == {}, "nothing declared yet"

    _watch_file(watches, "tools")
    app.refresh_watch_defs()

    assert set(app.watches) == {"tools"}


def test_a_watch_edited_in_place_is_picked_up(tmp_path, monkeypatch):
    watches = tmp_path / "watches"
    _watch_file(watches, "tools", command="check tools")
    app = _app_watching(tmp_path, monkeypatch, watches)
    assert app.watches["tools"].command == "check tools"

    _watch_file(watches, "tools", command="check drift")
    app.refresh_watch_defs()

    assert app.watches["tools"].command == "check drift"


def test_a_removed_watch_leaves_the_rail(tmp_path, monkeypatch):
    watches = tmp_path / "watches"
    _watch_file(watches, "tools")
    _watch_file(watches, "drift", command="check drift")
    app = _app_watching(tmp_path, monkeypatch, watches)
    assert set(app.watches) == {"tools", "drift"}

    (watches / "drift.yaml").unlink()
    app.refresh_watch_defs()

    assert set(app.watches) == {"tools"}


def test_an_unchanged_watch_keeps_its_last_result_across_a_reload(tmp_path, monkeypatch):
    """A reload is usually one file being edited. Blanking every other watch
    back to "not yet run" would throw away answers to pay for that."""
    watches = tmp_path / "watches"
    _watch_file(watches, "tools")
    _watch_file(watches, "drift", command="check drift")
    app = _app_watching(tmp_path, monkeypatch, watches)

    app.watched = {"tools": (0, 100.0), "drift": (1, 100.0)}

    # Edit one of them; the other must keep its answer.
    _watch_file(watches, "drift", command="check drift", every="1h")
    app.refresh_watch_defs()

    assert app.watched["tools"] == (0, 100.0)
    assert "drift" in app.watched, "only `every` changed — the answer still stands"


def test_a_watch_whose_command_changed_drops_its_result(tmp_path, monkeypatch):
    """A different command is a different question, so the old answer is not an
    answer to it — showing it would be reporting the wrong thing as current."""
    watches = tmp_path / "watches"
    _watch_file(watches, "tools", command="check tools")
    app = _app_watching(tmp_path, monkeypatch, watches)
    app.watched = {"tools": (0, 100.0)}

    _watch_file(watches, "tools", command="check drift")
    app.refresh_watch_defs()

    assert "tools" not in app.watched


def test_an_injected_roster_is_never_reloaded(tmp_path, monkeypatch):
    """The suite must stay free of the real watch directory: a test that quietly
    re-read it would depend on whose machine it ran on."""
    from cli.tui import app as app_module
    from cli.tui.app import TackleBox

    called = []
    monkeypatch.setattr(app_module, "watch_signature", lambda: called.append("sig") or ())
    monkeypatch.setattr(app_module, "load_watches", lambda: called.append("load") or ({}, []))

    app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
    app.refresh_watch_defs()
    app.refresh_watch_defs()

    assert called == [], "an injected roster must not touch the real directory"


def test_re_reading_is_guarded_so_the_tick_does_not_parse_yaml(tmp_path, monkeypatch):
    """The signature is a readdir and a stat; the parse is what it guards."""
    from cli.tui import app as app_module

    watches = tmp_path / "watches"
    _watch_file(watches, "tools")

    loads = []

    def counting_load():
        loads.append(1)
        return _load(watches)

    monkeypatch.setattr(app_module, "watch_signature", lambda: _sig(watches))
    monkeypatch.setattr(app_module, "load_watches", counting_load)

    from cli.tui.app import TackleBox

    app = TackleBox(history=History(path=tmp_path / "hist"))
    assert len(loads) == 1, "loaded once at start, so the first paint has them"

    for _ in range(50):
        app.refresh_watch_defs()

    assert len(loads) == 1, "nothing changed, so nothing should have been re-parsed"

    _watch_file(watches, "tools", command="check drift")
    app.refresh_watch_defs()
    assert len(loads) == 2
