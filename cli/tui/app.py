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
loop.** `check unpushed` walks ~/skyrow.labs, `check tools` shells out to
half a dozen CLIs, and `run` blocks for the whole duration of a job. Any of
those on the loop freezes the surface on precisely the commands worth
watching, and a surface that freezes is worse than the shell it replaced.
"""

from __future__ import annotations

import shlex
import socket
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
from cli.tui.history import History
from cli.tui.live import (
    expected_seconds,
    lanes,
    last_run,
    ledger_size,
    recent_runs,
    summarize,
)
from cli.watch import load_watches

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

    # Textual CSS takes variables, so the palette crosses into the stylesheet as
    # $tb-* definitions rather than as interpolated hexes. Nothing below names a
    # colour; cli/theme.py is the only place that does.
    #
    # These are the design system's tokens *unmodified*, unlike the CLI's, which
    # are darkened to survive an unknown terminal. The surface paints its own
    # void, so it is the one place the brand can be shown at full strength.
    CSS = f"""
    $tb-surface: {BG};
    $tb-panel: {SURFACE};
    $tb-input: {SURFACE_2};
    $tb-border: {BORDER};
    $tb-text: {TEXT};
    $tb-muted: {TEXT_2};
    $tb-dim: {TEXT_3};
    $tb-accent: {BRAND};
    $tb-rail: {RAIL_WIDTH};
    $tb-repl: {REPL_ROWS};
    """ + """
    Screen { layout: vertical; background: $tb-surface; color: $tb-text; }

    #banner {
        height: 1;
        background: $tb-panel;
        color: $tb-accent;
        text-style: bold;
        padding: 0 1;
    }

    #repl {
        height: $tb-repl;
        layout: horizontal;
        background: $tb-panel;
        border-top: solid $tb-border;
        padding: 0 1;
    }

    /* The input takes the larger share: a command line is the longest string
       on the surface, and the help pane is built to truncate. */
    #inputpane { width: 2fr; }
    #helppane { width: 1fr; padding: 0 0 0 1; }

    #promptrow { height: 1; }
    #brand { width: 5; color: $tb-accent; text-style: bold; }
    #prompt {
        width: 1fr;
        height: 1;
        border: none;
        padding: 0;
        background: $tb-panel;
        color: $tb-text;
    }
    #prompt:focus { border: none; }

    /* Top-aligned, so candidates sit directly under the line they complete
       rather than floating clear of it at the foot of the pane. */
    #completions { height: 1fr; color: $tb-dim; }

    /* Nothing in the chrome may wrap. Truncation is Textual's job, not
       Python's: a width measured at call time is the pre-layout fallback on
       the first paint and stale after every drag, and the pane is the only
       thing that reliably knows how wide it is. The _fit() helpers still run,
       so the "…" lands on a word boundary the widget would cut mid-character;
       this is the backstop that makes a stale width harmless. */
    #helppane, #launch, #lanes, #progress, #watches, #updates, #completions {
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }

    /* Chrome for the two widgets defined above. Their own DEFAULT_CSS parses
       in a scope with no $tb-* bound, so the palette can only reach them from
       here — and cli/theme.py stays the only file naming a colour. */
    Separator { width: 1; height: 1fr; background: $tb-border; }
    Separator:hover { background: $tb-accent; }

    Expanded { align: center middle; }
    Expanded > VerticalScroll {
        width: 80%;
        max-width: 100;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: solid $tb-border;
        background: $tb-panel;
    }
    #expanded-title { text-style: bold; }

    #middle { height: 1fr; }

    /* The idle state. Exactly one of these two is ever displayed. */
    #launch { width: 1fr; padding: 1 1; background: $tb-surface; }
    #launch.hidden, #body.hidden { display: none; }

    #body {
        width: 1fr;
        padding: 0 1;
        background: $tb-surface;
        scrollbar-size-vertical: 1;
    }

    #rail {
        width: $tb-rail;
        background: $tb-panel;
        padding: 0 1;
    }
    #rail.hidden, #railsep.hidden { display: none; }

    /* A blank row between sections; without it the three headings read as one
       list with words capitalised at random. */
    #lanes { height: auto; margin-bottom: 1; }
    #progress { height: auto; margin-bottom: 1; }
    #watches { height: auto; margin-bottom: 1; }
    #updates { height: 1fr; }
    """

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
        if watches is None:
            loaded, self.watch_errors = load_watches()
            host = socket.gethostname()
            self.watches = {n: w for n, w in loaded.items() if w.applies_to(host)}
        else:
            self.watches, self.watch_errors = watches, []

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
            )
        )

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


def run() -> None:
    TackleBox().run()
