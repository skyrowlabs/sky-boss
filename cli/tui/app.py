"""The surface itself.

A one-row banner at the top, the transcript and the rail sharing the middle,
and the REPL region pinned to the bottom. The region is split: the input on
its first row — directly under the rule, level with the help pane's title, so
the line and its explanation read across — with candidate names beneath it.

The region is at the foot of the screen because that is where a terminal puts
its prompt and the transcript grows toward it. Inside the region the input is
at the *top*, because everything else there describes it: candidates below,
help to the right, both hanging off the line above them.

Every line typed goes through :mod:`cli.tui.dispatch`, so this module renders
and schedules — it decides nothing about what a command means.

The one rule that cannot be relaxed: **a dispatch never runs on the event
loop.** `check unpushed` walks ~/src, `check tools` shells out to
half a dozen CLIs, and `run` blocks for the whole duration of a job. Any of
those on the loop freezes the surface on precisely the commands worth
watching, and a surface that freezes is worse than the shell it replaced.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import socket
import sys
import threading
import time
from collections import deque
from datetime import datetime

from rich.text import Text
from textual import on, work
from textual.events import Click, MouseDown, MouseMove, MouseUp
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import ModalScreen
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, RichLog, Static

from cli.jobs import LANES, load_jobs
from cli.output import EXIT_OK, EXIT_PARTIAL, TUI_THEME
from cli.theme import BG, BORDER, BRAND, SURFACE, SURFACE_2, TEXT, TEXT_2, TEXT_3
from cli.tui.complete import complete
from cli.tui.dispatch import Dispatch, dispatch
from cli.tui.help import view as help_view
from cli.tui.launch import view as launch_view
from cli.tui.verbs import resolve as resolve_verb
from cli.tui.watchdog import Watchdog
from cli.tui.history import History
from cli.tui.live import (
    expected_seconds,
    lanes,
    last_run,
    ledger_size,
    recent_runs,
    summarize,
)
from cli.watch import load_watches, signature as watch_signature

# The undarkened roles. The CLI's are derived to survive an unknown terminal;
# this surface paints its own background and does not need that concession.
ACCENT_STYLE = TUI_THEME.styles["tb.accent"]
MUTED = TUI_THEME.styles["tb.muted"]
LABEL = TUI_THEME.styles["tb.label"]
FAIL = TUI_THEME.styles["tb.fail"]
WARN = TUI_THEME.styles["tb.warn"]
OK = TUI_THEME.styles["tb.ok"]
NUM = TUI_THEME.styles["tb.num"]
SECTION = TUI_THEME.styles["tb.accent"]

BUSY_GLYPH = "●"
FREE_GLYPH = "·"
FILLED = "▰"
EMPTY = "▱"
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# What a typed line looks like in the transcript. Shared with the tests so the
# two cannot disagree about what an echoed line is.
ECHO_PREFIX = "▸ "
BAR_CELLS = 10

# The two numbers that keep a large result from freezing the surface, and the
# one that keeps a long session from growing without bound. See `write_body`,
# and Round 2 of the tui feature doc for the measurements behind them.
#
# TRANSCRIPT_MAX_LINES is a ceiling on what one write may put on screen. It is
# far above any output worth scrolling and far below where the cost starts to
# hurt: nobody reads the 60,000th line of a traceback, they re-run with --json
# or open the log, and both of those are one keystroke away.
TRANSCRIPT_MAX_LINES = 10_000
# Written a slice at a time, because RichLog.write is superlinear in the size of
# a single renderable. Chunking the same 80k lines costs 1.48s against 7.62s.
WRITE_CHUNK_LINES = 1_000
# Scrollback, bounded. Unset, the transcript is a leak with no upper limit in a
# surface designed to be left open for days.
LOG_MAX_LINES = 50_000

# The name, on one row, above everything. It is chrome and nothing else reads
# it, so it is deliberately outside the REPL row budget below.
BANNER_TEXT = "TACKLEBOX"
BANNER_ROWS = 1

# The region holds only the line being typed, now that the live state has moved
# to the rail. Six rows: a border, the input on the last one, and the rest to
# candidate names — which is more room than the two rows they used to get.
REPL_ROWS = 6
BORDER_ROWS = 1
PROMPT_ROWS = 1
COMPLETION_ROWS = REPL_ROWS - BORDER_ROWS - PROMPT_ROWS
assert COMPLETION_ROWS >= 1, "the region has no room left for candidates"

# The rail, right of the transcript. Wide enough for a timestamp, a job name and
# an outcome without truncating the common case.
RAIL_WIDTH = 34

# Below this the rail costs the transcript more than it is worth: on an 80
# column terminal it would leave 46 columns for output, narrower than most
# tables reflow to. Hidden rather than squeezed — output is what this is for.
RAIL_MIN_TOTAL_WIDTH = 100

# What the feed falls back to before the rail has been laid out and can be asked
# how tall it is.
UPDATE_ROWS = 5

# Only used before the pane has been laid out, on the very first paint.
HELP_WIDTH = 34
HELP_ROWS = 5

# Rich needs a width to wrap tables to before the text ever reaches a widget.
# Falls back only for the first paint, before the body has been laid out.
FALLBACK_WIDTH = 100

# The strip's whole value is being current. A second is frequent enough to
# catch a short job and cheap enough that nobody notices: it reads /proc/locks
# and the last few KB of the ledger.
TICK_SECONDS = 1.0
# Faster than the tick, so a stall is measured against a recent beat rather than
# against whenever the last repaint happened to land.
WATCHDOG_BEAT_SECONDS = 0.5

# The progress row is the one thing that has to look alive, and it only ticks
# this fast while something is actually running.
PROGRESS_SECONDS = 0.1


class PromptInput(Input):
    """The input line, with shell-shaped history recall and completion.

    Textual's Input is single-line and leaves up/down unbound, so they bubble —
    binding them here rather than on the app keeps them from competing with
    scrolling the output pane.
    """

    BINDINGS = [
        Binding("up", "history_prev", show=False),
        Binding("down", "history_next", show=False),
        # Tab is focus-next everywhere else in Textual, and there is nowhere
        # else to focus here. priority takes it back for completion.
        Binding("tab", "complete", show=False, priority=True),
        # Input already binds ctrl+d to delete-right, and a non-priority app
        # binding never sees it — which left the documented quit key doing
        # nothing at all. Readline's contract settles it without losing the
        # forward delete: ^D leaves only when there is nothing to delete.
        Binding("ctrl+d", "delete_or_quit", show=False, priority=True),
    ]

    def __init__(self, history: History, **kwargs) -> None:
        super().__init__(**kwargs)
        self.history = history

    def _recall(self, line: str | None) -> None:
        if line is None:
            return
        self.value = line
        self.cursor_position = len(line)

    def action_history_prev(self) -> None:
        self._recall(self.history.prev())

    def action_history_next(self) -> None:
        self._recall(self.history.next())

    def action_delete_or_quit(self) -> None:
        if self.value:
            self.action_delete_right()
        else:
            self.app.exit()

    def action_complete(self) -> None:
        """Extend on the first press, list on the second — the shell contract."""
        line, matches = complete(self.value)
        if line != self.value:
            self.value = line
            self.cursor_position = len(line)
            self.app.show_candidates([])
        else:
            self.app.show_candidates(matches)


class Separator(Static):
    """A draggable divider. Textual 8.2 ships no splitter, so this is the whole
    mechanism: capture the mouse on press so moves keep arriving after the
    pointer leaves the one-column strip, report each move as a delta, release
    on let-go.

    It resizes nothing itself. The app owns the clamps, because only the app
    knows what the other side of the divider needs to stay usable.
    """

    class Dragged(Message):
        def __init__(self, separator: "Separator", delta: int) -> None:
            super().__init__()
            self.separator = separator
            self.delta = delta

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.dragging = False

    def on_mouse_down(self, event: MouseDown) -> None:
        self.dragging = True
        # Without capture the drag dies the moment the pointer moves off a
        # strip one column wide, which is every drag.
        self.capture_mouse()
        event.stop()

    def on_mouse_move(self, event: MouseMove) -> None:
        if self.dragging and event.delta_x:
            self.post_message(self.Dragged(self, event.delta_x))

    def on_mouse_up(self, event: MouseUp) -> None:
        if self.dragging:
            self.dragging = False
            self.release_mouse()
            event.stop()


class Expanded(ModalScreen):
    """A truncated pane, in full.

    The rail and the help pane are narrow by design and cut everything to fit.
    That is the right default and a bad dead end, so the cut version is a
    click away from the whole thing. Chrome only — the transcript is never
    truncated in the first place, and is `markup=False` precisely so command
    output is never interpreted.
    """

    BINDINGS = [
        Binding("escape", "dismiss", "close", show=False),
        Binding("q", "dismiss", "close", show=False),
    ]

    def __init__(self, title: str, body: Text) -> None:
        super().__init__()
        self.heading = title
        self.body = body

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(Text(self.heading, style=ACCENT_STYLE), id="expanded-title")
            yield Static(self.body)
            yield Static(Text("esc to close", style=MUTED))

    def on_click(self) -> None:
        self.dismiss()


class TackleBox(App):
    """tb, held open."""

    TITLE = "tackle-box"

    # A file, not a class attribute, so `textual run --dev` can watch it and
    # re-parse on save. An inline stylesheet gives the watcher nothing to watch,
    # which is why editing colours used to cost a restart per iteration.
    # See cli/tui/tb.tcss and Round 3 of the tui feature doc.
    CSS_PATH = "tb.tcss"

    def get_css_variables(self) -> dict[str, str]:
        """The palette, injected rather than interpolated.

        Textual CSS takes variables, so the design system crosses into the
        stylesheet as `$tb-*` names and `cli/theme.py` stays the only place a
        hex is written. Moving the stylesheet into a file made this load-bearing
        rather than merely tidy: `test_no_module_outside_the_palette_names_a_colour`
        globs `cli/**/*.py`, so a `.tcss` full of hexes would have passed it in
        silence. The test now covers `*.tcss` as well, and this is what lets the
        file satisfy it.

        These are the tokens *unmodified*, unlike the CLI's, which are darkened
        to survive an unknown terminal. The surface paints its own void, so it
        is the one place the brand can be shown at full strength.
        """
        return {
            **super().get_css_variables(),
            "tb-surface": BG,
            "tb-panel": SURFACE,
            "tb-input": SURFACE_2,
            "tb-border": BORDER,
            "tb-text": TEXT,
            "tb-muted": TEXT_2,
            "tb-dim": TEXT_3,
            "tb-accent": BRAND,
            "tb-rail": str(RAIL_WIDTH),
            "tb-repl": str(REPL_ROWS),
        }

    BINDINGS = [
        # Shell conventions: ^C abandons the line you are typing, ^D leaves.
        # ^C is Textual's own quit binding, so it needs priority to be taken
        # over. ^D is bound on the input instead — see PromptInput. ^Q is the
        # unconditional way out, and the only one that works if a thread wedges.
        Binding("ctrl+c", "cancel_line", "cancel", priority=True, show=False),
        Binding("ctrl+q", "quit", "quit", show=False),
        Binding("ctrl+l", "clear", "clear", show=False),
        # The two-trip problem: `auto status` hands you a run_id and the next
        # thing you always want is that run's log. This types it for you, as a
        # real dispatch, so the transcript shows what it ran.
        Binding("ctrl+o", "last_log", "last log", show=False),
    ]

    def __init__(
        self, history: History | None = None, watches: dict | None = None
    ) -> None:
        super().__init__()
        self.history = history or History()
        self.watchdog = Watchdog()
        # One dispatch at a time. Two concurrent `tb run`s would contend for the
        # same lane lock and one would come back `skipped`, which is a confusing
        # way to find out you double-typed.
        self.queue: deque[str] = deque()
        self.busy = False
        self.running_line = ""
        self.started_at = 0.0
        self.expected = None
        self.frame = 0
        # name -> (exit code or None if it could not run, monotonic time taken).
        # Empty until the first refresh, which is why a watch reads "…" rather
        # than "clear" before it has ever run.
        self.watched: dict[str, tuple[int | None, float]] = {}
        self.watching: set[str] = set()
        # Whether anything has reached the transcript. See `idle`.
        self.written = False
        # The last dispatch's envelopes, kept so `inspect` never re-runs.
        self.last_envelopes: tuple[dict, ...] = ()
        self.last_envelope_line = ""
        # Injectable for the same reason History is: the suite must stay free of
        # subprocesses, and a watch is a real dispatch that shells out.
        # Injected rosters never reload: the suite must stay free of the real
        # watch directory, and a test that quietly re-read it would depend on
        # whose machine it ran on.
        self.watches_are_injected = watches is not None
        self.watches: dict = watches or {}
        self.watch_errors: list[str] = []
        self.watch_defs_signature: tuple | None = None
        if not self.watches_are_injected:
            # Loaded here as well as on the tick so the first paint has them.
            self.refresh_watch_defs()

    # ------------------------------------------------------------------ chrome

    def compose(self) -> ComposeResult:
        yield Static(BANNER_TEXT, id="banner")
        # The transcript and the rail share the middle. Live state sits beside
        # the thing it describes rather than beside the thing you type: lanes
        # and progress are about the run, and the run's output is right there.
        with Horizontal(id="middle"):
            yield Static(id="launch")
            yield RichLog(
                id="body",
                highlight=False,
                markup=False,
                wrap=False,
                auto_scroll=True,
                max_lines=LOG_MAX_LINES,
            )
            yield Separator(id="railsep")
            with Vertical(id="rail"):
                yield Static(id="lanes")
                yield Static(id="progress")
                yield Static(id="watches")
                yield Static(id="updates")
        # The region is now only the line being typed: candidates on the left
        # above the input, and what the line resolves to on the right.
        with Horizontal(id="repl"):
            with Vertical(id="inputpane"):
                with Horizontal(id="promptrow"):
                    yield Static("tb ▸", id="brand")
                    yield PromptInput(
                        self.history, id="prompt", placeholder="check, run <job>…"
                    )
                yield Static(id="completions")
            yield Separator(id="replsep")
            yield Static(id="helppane")

    def on_mount(self) -> None:
        self.query_one(PromptInput).focus()
        self.refresh_help("")
        self.refresh_launch()
        # Off-loop, so it still runs when the loop does not — which is the only
        # condition it exists to report. Its beat is a separate timer from the
        # tick: a tick that got slow enough to matter is exactly the case that
        # must still be recorded, and beating from inside `tick` would mean the
        # beat stopped for the same reason the dump would never be written.
        self.watchdog.start()
        self.set_interval(WATCHDOG_BEAT_SECONDS, self.watchdog.beat)
        self.tick()
        self.set_interval(TICK_SECONDS, self.tick)
        self.progress_timer = self.set_interval(
            PROGRESS_SECONDS, self.refresh_progress, pause=True
        )
        # The banner names the surface now, so the hint is only the keys.
        self.query_one(RichLog).write(
            Text(
                "⇥ complete  ↑↓ history  ^O last log  ^L clear  ^D quit",
                style=MUTED,
            )
        )

    def on_unmount(self) -> None:
        # The watchdog stops with the app that owns it. Being a daemon means it
        # cannot hold the process open, which is not the same as being free: it
        # wakes every second for as long as it runs, so anything building several
        # apps in one process — the suite builds ~30 — accumulates a poller per
        # app. That is real background load, and it showed up as a timing-
        # sensitive test flaking roughly one run in six.
        self.watchdog.stop()

    @property
    def idle(self) -> bool:
        """Idle is *the transcript is empty*, not *nothing is running*.

        Which makes ^L a way home rather than a way to a blank pane, and means
        a long job started from a fresh surface still shows its output.

        Tracked rather than read off the widget. `RichLog.lines` is the obvious
        source and is unusable here: while the launch screen is up the
        transcript is `display: none`, so it has no size, so a write renders no
        lines — and the surface could never leave the state it was measuring.
        """
        return not self.written

    def write_body(self, renderable) -> None:
        """The one way anything reaches the transcript.

        Single path so `written` cannot drift from what is actually on screen —
        `action_last_log` writes without an echo, and that alone is enough to
        leave the launch screen up over a non-empty transcript.

        Being the single path is also what makes it the one place a large result
        can be bounded, and it has to be bounded somewhere. `RichLog.write` is
        superlinear in the size of one renderable — 80,000 lines blocks for 7.7s
        here and 120,000 for 17.5s — and it runs on the event loop, because
        Textual widgets are not thread-safe and `call_from_thread` is the right
        boundary. So a single chatty command freezes the surface on exactly the
        output worth watching, with no key still live to escape it.

        The founding rule was "a dispatch never runs on the event loop", and it
        is honoured: `work` is a thread worker. But it names the wrong unit. The
        *result* comes back through `call_from_thread` and is rendered here, on
        the loop, and that was unbounded from the first commit. The rule that
        actually holds the surface open is that **no single turn may be
        unbounded**, and rendering a result is a turn like any other.
        """
        self.written = True
        log = self.query_one(RichLog)
        for chunk in _bounded_chunks(renderable):
            log.write(chunk)

    def refresh_launch(self) -> None:
        idle = self.idle
        self.query_one("#launch", Static).set_class(not idle, "hidden")
        self.query_one(RichLog).set_class(idle, "hidden")
        # The rail says what the launch screen already says, with less room.
        # Showing both prints the watch list twice on one screen.
        self.query_one("#rail", Vertical).set_class(idle or self.rail_too_narrow, "hidden")
        self.query_one("#railsep", Separator).set_class(idle or self.rail_too_narrow, "hidden")
        if not idle:
            return

        held = [lane.name for lane in lanes() if lane.busy]
        jobs, _problems = load_jobs()
        cards = []
        for name in sorted(self.watches):
            glyph, style, age = self._watch_state(name)
            watch = self.watches[name]
            verdict = self._watch_verdict(name)
            definition = f"{watch.command} · every {_every(watch.every)}"
            if age:
                definition += f" · {age} ago"
            cards.append((name, glyph, style, verdict, definition))

        self.query_one("#launch", Static).update(
            launch_view(
                jobs=len(jobs),
                watches=cards,
                lanes_held=held,
                ledger_runs=ledger_size(),
                recent=[
                    (_clock(entry), str(entry.get("job", "?")), str(entry.get("outcome", "?")),
                     entry.get("outcome") == "ok")
                    for entry in recent_runs(3)
                ],
                stall_dump=self._stall_dump(),
            )
        )

    def _stall_dump(self) -> str | None:
        """The stall file, if one is there to be read.

        Checked on the tick rather than once at start, so a freeze that happens
        *this* session is reported the moment the surface comes back — which is
        the case where the operator is still watching and can say what they did.
        """
        try:
            return str(self.watchdog.path) if self.watchdog.path.exists() else None
        except OSError:
            return None

    def _watch_verdict(self, name: str) -> str:
        seen = self.watched.get(name)
        if seen is None:
            return "…" if name in self.watching else "not yet run"
        code, _when = seen
        if code == EXIT_OK:
            return "clear"
        if code == EXIT_PARTIAL:
            return "degraded"
        return "can't read"

    @property
    def rail_too_narrow(self) -> bool:
        return self.size.width < RAIL_MIN_TOTAL_WIDTH

    def on_resize(self) -> None:
        """Hide the rail rather than let it squeeze the transcript.

        A rail on an 80 column terminal leaves 46 for output, which is below
        what most tb tables reflow to — and `--help` is a fixed 80 whatever we
        ask for, so it would clip outright. Output is what the surface is for;
        the rail is what it can afford.
        """
        # The rail hides when the terminal is too narrow to afford it, and
        # again while the launch screen is up. refresh_launch owns both.
        self.refresh_launch()
        # Every pane just changed width, so what fits in them changed with it.
        # Dropping this leaves the help pane holding its pre-layout fallback
        # width, which is wider than the pane and wraps instead of truncating.
        self.refresh_help()
        self.tick()
        # The panes changed width, so what fits in them changed with it.
        self.refresh_help()
        self.tick()

    def tick(self) -> None:
        """The once-a-second repaint of everything that is not the output."""
        self.refresh_lanes()
        self.refresh_updates()
        self.refresh_progress()
        self.refresh_watch_defs()
        self.refresh_watches()
        self.render_watches()
        if self.idle:
            self.refresh_launch()

    def _rail_width(self) -> int:
        """Usable columns inside the rail, or the fallback before first layout."""
        return self.query_one("#rail", Vertical).content_size.width or (RAIL_WIDTH - 3)

    @staticmethod
    def _section(title: str) -> Text:
        # Nothing in the rail may wrap: a wrapped lane row pushes the section
        # below it off the bottom, and the rail has no scrollbar.
        return Text(title, style=SECTION, no_wrap=True, overflow="ellipsis")

    def refresh_lanes(self) -> None:
        """One row per lane, live.

        This is the part a one-shot command cannot do. `tb auto status` reads
        the ledger, and the ledger only learns about a run once it has ended —
        so a lane held right now, and by what, is invisible from the CLI. The
        lane system is the job layer's headline feature and until now you could
        only ever find out afterwards that it had done something.
        """
        width = self._rail_width()
        line = self._section("LANES")
        for lane in lanes():
            line.append("\n")
            if lane.busy:
                line.append(f"{BUSY_GLYPH} ", style=WARN)
                line.append(f"{lane.name:<12}", style=LABEL)
                line.append(_fit(lane.holder or "", width - 14), style=MUTED)
            else:
                line.append(f"{FREE_GLYPH} ", style=MUTED)
                line.append(f"{lane.name:<12}", style=MUTED)
        self.query_one("#lanes", Static).update(line)

    def refresh_updates(self) -> None:
        target = self.query_one("#updates", Static)
        width = self._rail_width()
        # One row goes to the heading; ask the widget how many are left rather
        # than keeping a constant that a resize would make wrong.
        rows = max(1, (target.content_size.height or UPDATE_ROWS) - 1)
        line = self._section("RECENT")
        entries = recent_runs(rows)
        if not entries:
            line.append("\n")
            line.append("no runs recorded", style=MUTED)
            target.update(line)
            return
        # Job name gets whatever the clock and the outcome do not need.
        name_width = max(6, width - 6 - 8)
        for entry in entries:
            line.append("\n")
            line.append(f"{_clock(entry):<6}", style=MUTED)
            line.append(
                f"{_fit(str(entry.get('job', '?')), name_width):<{name_width}} ", style=LABEL
            )
            outcome = str(entry.get("outcome", "?"))
            line.append(outcome[:7], style=OK if outcome == "ok" else FAIL)
        target.update(line)

    def refresh_progress(self) -> None:
        """The one row that has to look alive, restacked for a narrow column.

        On the old wide strip the bar, the label and the timing shared a line.
        In 31 columns they cannot, so each gets its own — which also means the
        job name has room to be read rather than clipped after four words.
        """
        target = self.query_one("#progress", Static)
        width = self._rail_width()
        line = self._section("NOW")

        if not self.busy:
            line.append("\n")
            line.append(_fit(socket.gethostname(), width - 6), style=LABEL)
            line.append("  idle", style=MUTED)
            entry = last_run()
            if entry is not None:
                label, went_well = summarize(entry)
                line.append("\n")
                line.append("last ", style=MUTED)
                line.append(_fit(label, width - 5), style=OK if went_well else FAIL)
            target.update(line)
            return

        elapsed = time.monotonic() - self.started_at
        line.append("\n")
        if self.expected:
            filled = min(BAR_CELLS, int(BAR_CELLS * elapsed / self.expected))
            over = elapsed > self.expected
            line.append(FILLED * filled, style=WARN if over else NUM)
            line.append(EMPTY * (BAR_CELLS - filled), style=MUTED)
            timing = f"{elapsed:.1f}s / ~{self.expected:.1f}s"
            if over:
                # An estimate that has been exceeded is information, not a bar
                # to leave pinned at full pretending it is nearly done.
                line.append("  over", style=WARN)
        else:
            self.frame = (self.frame + 1) % len(SPINNER)
            line.append(SPINNER[self.frame], style=NUM)
            timing = f"{elapsed:.1f}s"

        line.append("\n")
        line.append(_fit(self.running_line, width), style=LABEL)
        line.append("\n")
        line.append(timing, style=MUTED)
        if self.queue:
            line.append(f"  ({len(self.queue)} queued)", style=MUTED)
        target.update(line)

    def refresh_watch_defs(self) -> None:
        """Re-read the watch definitions if any of them changed.

        Job definitions have always been live — `refresh_launch` calls
        `load_jobs` every tick — and watches were not, because `load_watches`
        ran once in `__init__`. Two YAML files in the same home, edited the same
        way, and one of them silently did nothing until a restart. Nothing on
        screen said which was which, which is what made it cost time rather than
        merely being a limitation.

        Results survive a reload for any watch whose command is unchanged. A
        reload is usually one file being edited, and blanking the whole rail
        back to "not yet run" would throw away every other watch's answer to pay
        for it. A watch whose command *did* change is a different question, so
        its old answer is dropped.
        """
        if self.watches_are_injected:
            return

        seen = watch_signature()
        if seen == self.watch_defs_signature:
            return
        self.watch_defs_signature = seen

        loaded, self.watch_errors = load_watches()
        host = socket.gethostname()
        fresh = {n: w for n, w in loaded.items() if w.applies_to(host)}

        previous = self.watches
        self.watched = {
            name: result
            for name, result in self.watched.items()
            if name in fresh
            and name in previous
            and fresh[name].command == previous[name].command
        }
        self.watches = fresh

    def refresh_watches(self) -> None:
        """Start any watch that is due. Never blocks, never queues.

        Deliberately not on `self.queue`: a watch must not make you wait to run
        a command, and your command must not delay a watch. Two concurrent
        dispatches are safe here only because a watch may name nothing but a
        read verb — see cli/watch.py.
        """
        now = time.monotonic()
        for name, watch in self.watches.items():
            if name in self.watching:
                continue
            seen = self.watched.get(name)
            if seen is not None and now - seen[1] < watch.every:
                continue
            self.watching.add(name)
            self.run_watch(name, watch.command)

    @work(thread=True, group="watch")
    def run_watch(self, name: str, command: str) -> None:
        # Its own group, so Textual does not treat it as replacing the
        # dispatch worker — the two are meant to overlap.
        try:
            # redirect=False: sys.stdout is process-global and this runs
            # alongside the foreground dispatch, which keeps it.
            code = dispatch(command, redirect=False, theme=TUI_THEME).exit_code
        except Exception:
            # Reads as "cannot see" rather than "clear". A status board that
            # collapses those two is worse than none.
            code = None
        self.call_from_thread(self.watch_finished, name, code)

    def watch_finished(self, name: str, code: int | None) -> None:
        self.watched[name] = (code, time.monotonic())
        self.watching.discard(name)
        self.render_watches()

    def render_watches(self) -> None:
        target = self.query_one("#watches", Static)
        width = self._rail_width()
        line = self._section("WATCH")

        if self.watch_errors:
            # A refused definition is shown, not swallowed. A watch that
            # silently vanished would leave the rail looking like it reported.
            line.append("\n")
            line.append(_fit(f"{len(self.watch_errors)} refused", width), style=FAIL)
        if not self.watches:
            line.append("\n")
            line.append("nothing watched", style=MUTED)
            target.update(line)
            return

        name_width = max(6, width - 12)
        for name in sorted(self.watches):
            glyph, style, label = self._watch_state(name)
            line.append("\n")
            line.append(f"{glyph} ", style=style)
            line.append(f"{_fit(name, name_width):<{name_width}} ", style=LABEL)
            line.append(label, style=style)
        target.update(line)

    def _watch_state(self, name: str) -> tuple[str, object, str]:
        """Exit code to a glyph, a style and an age.

        The codes are tb's contract, not a guess: 0 ok, 3 partial, 1 a hard
        failure and 2 Click's usage error. The last two mean the check could
        not reach a verdict, which must never render as a clean one.
        """
        seen = self.watched.get(name)
        if seen is None:
            return ("○", MUTED, "…" if name in self.watching else "")
        code, when = seen
        age = _age(time.monotonic() - when)
        if code == EXIT_OK:
            return (BUSY_GLYPH, OK, age)
        if code == EXIT_PARTIAL:
            return (BUSY_GLYPH, WARN, age)
        return ("⚠", FAIL, "can't read")

    # --------------------------------------------------- progressive disclosure

    # Wide enough that nothing truncates twice, and taller than any pane.
    EXPANDED_WIDTH = 90
    EXPANDED_ROWS = 60

    def expand(self, title: str, body: Text) -> None:
        self.push_screen(Expanded(title, body))

    @on(Click, "#helppane")
    def expand_help(self) -> None:
        line = self.query_one(PromptInput).value
        self.expand(
            f"help — {line.strip() or 'tb'}",
            help_view(line, width=self.EXPANDED_WIDTH, rows=self.EXPANDED_ROWS),
        )

    @on(Click, "#updates")
    def expand_updates(self) -> None:
        body = Text()
        for entry in recent_runs(self.EXPANDED_ROWS):
            if body:
                body.append("\n")
            body.append(f"{_clock(entry):<7}", style=MUTED)
            body.append(f"{str(entry.get('job', '?')):<24}", style=LABEL)
            outcome = str(entry.get("outcome", "?"))
            body.append(f"{outcome:<9}", style=OK if outcome == "ok" else FAIL)
            duration = entry.get("duration_s")
            body.append(f"{duration}s" if duration is not None else "", style=NUM)
        self.expand("recent runs", body or Text("no runs recorded", style=MUTED))

    @on(Click, "#watches")
    def expand_watches(self) -> None:
        body = Text()
        for name in sorted(self.watches):
            glyph, style, label = self._watch_state(name)
            if body:
                body.append("\n")
            body.append(f"{glyph} ", style=style)
            body.append(f"{name:<14}", style=LABEL)
            body.append(f"{self.watches[name].command:<24}", style=MUTED)
            body.append(label, style=style)
        for problem in self.watch_errors:
            body.append("\n")
            body.append(problem, style=FAIL)
        self.expand("watches", body or Text("nothing watched", style=MUTED))

    # ------------------------------------------------------------- separators

    # Below these a pane stops being able to say anything. The rail's floor is
    # the width of a lane row; the input's is a short command plus its prompt.
    MIN_RAIL = 18
    MIN_INPUT = 24
    MIN_HELP = 16

    @on(Separator.Dragged)
    def drag(self, event: Separator.Dragged) -> None:
        """Resize the pane the divider owns, clamped so neither side vanishes.

        Dragging is not persisted. Remembering it means a config file and a
        schema, and the defaults should be shown to be wrong first.
        """
        if event.separator.id == "railsep":
            # The rail is right of its divider, so dragging left widens it.
            pane, floor, delta = self.query_one("#rail", Vertical), self.MIN_RAIL, -event.delta
            room = self.size.width - self.MIN_HELP
        else:
            pane, floor, delta = (
                self.query_one("#inputpane", Vertical),
                self.MIN_INPUT,
                event.delta,
            )
            room = self.size.width - self.MIN_HELP
        # `styles.width` sets the outer box; `size` reports the content box.
        # Reading the wrong one silently subtracts the padding on every drag,
        # so the clamp lands short of the floor it names.
        pane.styles.width = _clamp(
            pane.outer_size.width + delta, floor, max(floor, room)
        )
        # Both panes just changed width, so what fits in them changed with it.
        self.refresh_help()
        self.tick()

    def show_candidates(self, matches: list[str]) -> None:
        """Completions belong in the region, not mixed into the transcript."""
        self.query_one("#completions", Static).update(
            Text("  ".join(matches), style=MUTED)
        )

    # ----------------------------------------------------------------- actions

    def action_clear(self) -> None:
        self.query_one(RichLog).clear()
        # Clearing takes you home rather than to a blank pane.
        self.written = False
        self.refresh_launch()

    def action_cancel_line(self) -> None:
        self.query_one(PromptInput).value = ""
        self.history.reset()
        self.show_candidates([])

    def action_last_log(self) -> None:
        """Open the most recent run's log, without retyping its id."""
        entry = last_run()
        if entry is None or not entry.get("job") or not entry.get("run_id"):
            self.write_body(Text("no runs recorded yet", style=MUTED))
            self.refresh_launch()
            return
        self.start(f"auto log {shlex.quote(entry['job'])} --run {shlex.quote(entry['run_id'])}")

    # ---------------------------------------------------------------- dispatch

    def refresh_help(self, line: str | None = None) -> None:
        """Explain the line as it is typed. Cheap enough to do on the loop.

        Width and row budget come from the widget rather than a constant, so a
        dragged separator or a resized terminal changes what fits without any
        of this needing to know it happened.
        """
        pane = self.query_one("#helppane", Static)
        size = pane.content_size
        if line is None:
            line = self.query_one(PromptInput).value
        pane.update(
            help_view(line, width=size.width or HELP_WIDTH, rows=size.height or HELP_ROWS)
        )

    @on(Input.Changed, "#prompt")
    def typing(self, event: Input.Changed) -> None:
        self.refresh_help(event.value)

    @on(Input.Submitted, "#prompt")
    def submit(self, event: Input.Submitted) -> None:
        line = event.value.strip()
        event.input.value = ""
        self.show_candidates([])
        if not line:
            return
        self.history.append(line)
        self.start(line)

    def start(self, line: str) -> None:
        """Put a line into the transcript and the queue. The only way in.

        A surface verb is answered here instead of being queued: it renders
        something already in hand and starts no work, so making it wait behind
        a running job would be theatre. `resolve_verb` returns None for
        anything Click knows, so no real command can be intercepted.
        """
        self.echo(line)
        match = resolve_verb(line)
        if match is not None:
            verb, args = match
            message = verb.action(self, args)
            if message is not None:
                self.write_body(message)
                self.write_body(Text(""))
            return
        self.queue.append(line)
        self.pump()

    def echo(self, line: str) -> None:
        """Put the typed line in the transcript, so the pane reads as a session."""
        prompt = Text(ECHO_PREFIX, style=MUTED)
        prompt.append(line, style=ACCENT_STYLE)
        # The echo is the first thing written, so this is where idle ends.
        self.write_body(prompt)
        self.refresh_launch()

    def pump(self) -> None:
        if self.busy or not self.queue:
            return
        self.busy = True
        line = self.queue.popleft()
        self.running_line = line
        self.started_at = time.monotonic()
        # Read once, here, rather than on every progress frame — it walks the
        # ledger, and this is the only moment the answer can change.
        self.expected = expected_seconds(line)
        self.progress_timer.resume()
        self.refresh_progress()
        # Width is read here, on the loop, because the worker must not touch a
        # widget from its thread.
        self.work(line, self.query_one(RichLog).size.width or FALLBACK_WIDTH)

    @work(thread=True)
    def work(self, line: str, width: int) -> None:
        result = dispatch(line, width=width, theme=TUI_THEME)
        self.call_from_thread(self.finished, result)

    def finished(self, result: Dispatch) -> None:
        self.last_envelopes = result.envelopes
        self.last_envelope_line = result.line
        if result.text:
            self.write_body(Text.from_ansi(result.text.rstrip("\n")))
        elif result.ok:
            self.write_body(Text("(no output)", style=MUTED))
        if not result.ok:
            self.write_body(Text(f"exit {result.exit_code}", style=FAIL))
        self.write_body(Text(""))
        self.busy = False
        self.running_line = ""
        self.progress_timer.pause()
        self.tick()
        self.pump()


def _bounded_chunks(renderable):
    """A renderable as the slices `write_body` should hand to the log.

    Anything that is not a `Text` passes straight through — the rail's renderables
    are a handful of lines by construction, and only a command result is ever
    large enough to matter.

    A `Text` is truncated to `TRANSCRIPT_MAX_LINES` and then yielded in slices.
    Truncating is what bounds the cost; slicing is what makes the bounded cost
    cheap, and the two are not alternatives. Nothing is lost by the truncation:
    the whole envelope is still on `last_envelopes` for `inspect`, and a job's
    output is still whole in its log.
    """
    if not isinstance(renderable, Text):
        yield renderable
        return

    # Cut on the plain string before splitting into `Text` objects. Splitting
    # first is correct but costs a `Text` per line for lines that are about to
    # be thrown away — 200,000 of them still hitched the loop for 0.6s, which is
    # most of a freeze for output nobody was going to see. `split` with a maxsplit
    # leaves the whole remainder as one string, so counting it is a C-level scan.
    plain = renderable.plain
    head = plain.split("\n", TRANSCRIPT_MAX_LINES)
    dropped = 0
    if len(head) > TRANSCRIPT_MAX_LINES:
        remainder = head[-1]
        dropped = remainder.count("\n") + 1
        renderable = renderable[: len(plain) - len(remainder) - 1]

    lines = renderable.split("\n")
    newline = Text("\n")
    for start in range(0, len(lines), WRITE_CHUNK_LINES):
        yield newline.join(lines[start : start + WRITE_CHUNK_LINES])

    if dropped > 0:
        yield Text(
            f"… {dropped:,} more lines not shown — `inspect` for the envelope, "
            "or read the log with `auto log`",
            style=WARN,
        )


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _every(seconds: int) -> str:
    """An interval as it was written, near enough: 30s, 15m, 1h."""
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def _age(seconds: float) -> str:
    """Compact enough for the rail. Staleness is the point: a watch that last
    ran an hour ago is not telling you about now."""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    return f"{int(seconds // 3600)}h"


def _fit(text: str, width: int) -> str:
    """Truncate to width. The rail is narrow and nothing in it may wrap."""
    if width <= 1 or len(text) <= width:
        return text
    return text[: width - 1] + "…"


def _clock(entry: dict) -> str:
    try:
        return datetime.fromisoformat(entry["started"]).strftime("%H:%M")
    except (KeyError, TypeError, ValueError):
        return "--:--"


def _worker_thread_still_running() -> bool:
    """Whether anything is left that a clean interpreter exit would wait for."""
    return any(
        thread.is_alive() and not thread.daemon and thread is not threading.main_thread()
        for thread in threading.enumerate()
    )


def run() -> None:
    """Open the surface, and be able to leave it.

    The loop is ours rather than `asyncio.run`'s, and that is the whole point.
    A dispatch runs on a thread worker, and a thread worker cannot be cancelled
    — `App.exit()` calls `workers.cancel_all()`, but for a thread that cancels
    only the awaiting task and the thread itself runs on. Textual does not wait
    for it, so the UI comes down and the terminal is restored promptly. What
    does wait is the interpreter: `asyncio.run` closes its loop with
    `shutdown_default_executor(THREAD_JOIN_TIMEOUT)`, which is **300 seconds**
    on Python 3.14, and `concurrent.futures` registers an atexit hook that joins
    the same pool again. So a wedged `tb run` bought five minutes of dead
    terminal after the surface had visibly gone — and neither ^D nor ^Q could
    do anything about it, because both had already done their part.

    Owning the loop skips the first join; leaving through `os._exit` skips the
    second. That is safe here because the surface holds no unflushed state of
    its own: history is appended when a line is submitted, and the ledger is
    written by the job's own process, which is precisely the process still
    running. Nothing a clean shutdown would protect is in this one.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = TackleBox()
    try:
        app.run(loop=loop)
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        # Not required for correctness — it is a daemon — but leaving it running
        # would keep a dead app's clock ticking in any process that opens two.
        app.watchdog.stop()
        if _worker_thread_still_running():
            os._exit(0)
        loop.close()
