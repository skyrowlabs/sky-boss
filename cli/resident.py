"""The terminal's resident views — how they draw, and how they are left.

Two of them live here now. `--refresh` ([[refresh]]) is the terminal's
rendering of the refresh rule, and it is what this module was written for;
`hold`, `clip`, `room` and `stream_body` are the parts [[follow]] round 2
found it shares with a stream. Sharing them is not a tidiness argument: `q`
and `Esc` must mean the same thing in every resident view, and two loops
holding their own opinion about leaving would drift the week they were
written.

**The terminal is a surface too.** The refresh rule — re-run a snapshot on a
cadence — lived only in canvas machinery until [[refresh]]; this is the
terminal's rendering of the same rule. The two never share a scheduler: a
terminal residency is owned by its process and dies at Ctrl-C, a canvas
cadence is owned by its stream and dies with its window. Nothing here
survives anything.

**Only observes come here.** `run` does not take the flag — the absence in
its `--help` is the act/observe split made visible — and the canvas is
untouched: its Python-side, connection-keyed clock ([[canvas]]) already does
this job for windows.

**The split below is the same one the suite demands everywhere.** `Residency`
is the pure half — when a run is due, what the chrome facts are — over an
injected clock, so proving a five-second cadence costs no seconds of suite.
`loop` is the driver, bounded by `ticks` under test. `reside` owns the
screen, and is the only part that touches real time by default.
"""

from __future__ import annotations

import time
from typing import Callable

from rich.console import Console, Group
from rich.live import Live
from rich.text import Text

from cli import chrome as chrome_
from cli import keys
from cli.output import THEME, Result, band_text, capture, render

# Room the inline rendering leaves around the body: the two chrome bands, the
# prompt the frame is drawn under, and one line of slack so a redraw never
# pushes its own top off the screen.
_INLINE_MARGIN = 4


class Residency:
    """One resident invocation's state: cadence, verdict, clocks.

    The facts mirror what the canvas keeps per watcher (`interval`,
    `last_run`), because the chrome contract reads the same two numbers
    wherever the countdown is drawn. See [[chrome]].
    """

    def __init__(self, source: str, interval: int, clock: Callable[[], float] = time.time):
        self.source = source
        self.interval = interval
        self._clock = clock
        self.last_run: float | None = None
        self.running_since: float | None = None
        self.ran_at: float | None = None
        self.duration_s: float | None = None
        self.ok = True
        self.partial = False
        self.warnings = 0

    def due(self) -> bool:
        return self.last_run is None or self._clock() - self.last_run >= self.interval

    def begin(self) -> None:
        now = self._clock()
        self.last_run = now
        self.running_since = now

    def finish(self, result: Result) -> None:
        now = self._clock()
        if self.running_since is not None:
            self.duration_s = now - self.running_since
        self.running_since = None
        self.ran_at = now
        self.ok = result.ok
        self.partial = result.partial
        self.warnings = len(result.warnings)

    def chrome(self) -> chrome_.Chrome:
        return chrome_.resident(
            self.source,
            ok=self.ok,
            partial=self.partial,
            warnings=self.warnings,
            ran_at=self.ran_at,
            duration_s=self.duration_s,
            interval=self.interval,
            last_run=self.last_run,
            running_since=self.running_since,
        )


def loop(
    state: Residency,
    run_once: Callable[[], Result],
    draw: Callable[[Result | None], None],
    wait: Callable[[float], str | None],
    *,
    ticks: int | None = None,
) -> None:
    """Run when due, redraw every tick, until the operator leaves.

    `draw` is called with a fresh result when one was produced and None on a
    countdown-only tick — the bands change every second, the body only when
    a run does. `ticks` bounds the loop under test; this loop is synchronous
    and pull-driven, so the bound is on time as well as frames — the hang the
    suite's rules exist to prevent cannot hide in it.

    `wait(seconds)` is the tick *and* the key poll — one primitive, so `q`
    lands the moment it is pressed instead of up to a second later. A plain
    sleep returning None is a valid `wait`, which is what the suite injects
    and what a non-terminal gets. See [[keys]].
    """
    count = 0
    while ticks is None or count < ticks:
        if state.due():
            state.begin()
            draw(None)  # the running frame, so a slow run is visibly in flight
            result = run_once()
            state.finish(result)
            draw(result)
        else:
            draw(None)
        if keys.leaves(wait(keys.TICK)):
            return
        count += 1


def room(console: Console) -> int:
    """How many body lines an inline frame may draw on this terminal."""
    return console.height - _INLINE_MARGIN


def clip(body: Text, limit: int, *, tail: bool = False) -> Text:
    """The body, at most `limit` lines, saying so when it cut.

    Inline residency can only repaint what it can address, so a frame taller
    than the terminal would scroll its own top away and append instead of
    replacing. Clipping keeps the redraw honest and keeps [[canvas]]'s rule —
    no single result renders unbounded — in the surface that rule came from.

    **Which end survives is the caller's, and it is not a detail.** A
    snapshot's interesting end is the *top* — headers, the first rows. A
    stream's is the *bottom* — the newest lines. `tail=True` keeps the newest
    and leads with the marker, because for a follow this is not an edge case:
    the ring holds 200 lines against a terminal's forty, so every inline
    frame is clipped, and a follow that kept the head would pin the oldest
    lines on screen and never show a new one. See [[follow]] round 2.
    """
    lines = body.split("\n")
    if limit < 1 or len(lines) <= limit:
        return body
    keep = max(1, limit - 1)
    dropped = len(lines) - keep
    marker = f"{dropped} more lines not shown — --screen for the full view"
    if tail:
        # `Text(marker, style=...)` would set the *base* style of the whole
        # object, and everything appended after it would inherit warn — which
        # is exactly what happened: a follow's ring always outruns the
        # terminal, so every inline frame is clipped and every line came out
        # yellow. The marker is a span, like the head branch's below.
        out = Text()
        out.append(marker, style="tb.warn")
        out.append("\n")
        out.append_text(Text("\n").join(list(lines)[-keep:]))
        return out
    out = Text("\n").join(list(lines)[:keep])
    out.append(f"\n{marker}", style="tb.warn")
    return out


def hold(
    frame: Callable[[], Group],
    *,
    tick: Callable[[], None] | None = None,
    console: Console,
    screen: bool = False,
    ticks: int | None = None,
    wait: Callable[[float], str | None] | None = None,
    transient: bool = False,
    on_key: Callable[[str], bool] | None = None,
) -> None:
    """Draw a frame every tick until the operator leaves.

    The residency a *stream* has: no cadence, no verdict, nothing to re-run —
    a frame that is redrawn, an optional `tick` that advances whatever the
    frame reads, and one way out. `reside` keeps its own loop because it has
    a run to schedule; what both share is this — inline by default, `q`,
    `Esc` and Ctrl-C leave, and `ticks` bounds it under test.

    The caller owns what leaving *means*. `hold` returns; a follow's caller
    kills its child in a `finally`, and that difference is the point rather
    than an inconsistency. See [[follow]] round 2.

    `transient` erases the last frame on the way out, and the default is off
    for the reason above: leaving a follow should leave the tail of the log you
    were watching. A **countdown** is the opposite — its final frame says
    "nothing has run yet" and is a lie the instant it returns, with the output
    of the thing that just ran printing directly beneath it. See [[delay]].
    """

    def run(wait_for: Callable[[float], str | None]) -> None:
        if screen:
            def draw() -> None:
                console.clear()
                console.print(frame())

            with console.screen():
                _turn(draw, tick, wait_for, ticks, on_key)
            return

        # Live owns the cursor and the in-place repaint, exactly as it does
        # for `reside`; `transient=False` leaves the last frame on screen, so
        # leaving a follow leaves the tail of the log you were watching.
        with Live(console=console, auto_refresh=False, transient=transient) as live:
            _turn(lambda: live.update(frame(), refresh=True), tick, wait_for, ticks, on_key)

    try:
        if wait is not None:
            run(wait)
        else:
            with keys.reader() as wait_for:
                run(wait_for)
    except KeyboardInterrupt:
        # Still a way out, and still not a failure.
        pass


def _turn(
    draw: Callable[[], None],
    tick: Callable[[], None] | None,
    wait: Callable[[float], str | None],
    ticks: int | None,
    on_key: Callable[[str], bool] | None = None,
) -> None:
    count = 0
    while ticks is None or count < ticks:
        draw()
        key = wait(keys.TICK)
        if keys.leaves(key):
            return
        # A key that moved the view redraws on the next pass without advancing
        # the tick — a scroll that waited a second for its own keypress would
        # feel broken. The count still advances, so `ticks` bounds the loop
        # whatever the operator presses. See [[follow]] round 3.
        moved = bool(key) and on_key is not None and on_key(key)
        if not moved and tick is not None:
            tick()
        count += 1


class Viewport:
    """Where a parked follow is looking, as arithmetic over a ring.

    **Scrolling parks; nothing else does.** Following is the absence of an
    anchor, not a flag beside one — so a view that has never been scrolled is
    byte-identical to one from before this existed, and `End` is a single
    assignment back to that state.

    The anchor is an **absolute** line number, counted from the first line the
    stream ever produced, and that is the whole reason eviction is harmless.
    A ring holding the last 200 of 5,000 lines still knows which 200 they are;
    an offset counted from the oldest held line would silently slide under the
    operator every time a line arrived. Clamping an absolute anchor to what is
    still held makes the view walk to the top and stop there, which is both
    correct and what it looks like. See [[follow]] round 3.
    """

    def __init__(self) -> None:
        self.anchor: int | None = None

    @property
    def parked(self) -> bool:
        return self.anchor is not None

    def follow(self) -> None:
        self.anchor = None

    def move(self, key: str, *, height: int, held: int, dropped: int) -> bool:
        """Act on a movement key. True if it changed anything.

        `held` is how many lines the ring has; `dropped` how many it has
        already let go, which together give the absolute number of its oldest.
        Returns False for a key that could not move — pressing `up` at the top
        must not park a view that was following, or the band would announce a
        state the operator did not ask for.
        """
        if key not in keys.MOVES:
            return False
        if key == "end":
            was = self.parked
            self.follow()
            return was

        oldest, newest_top = dropped, dropped + max(0, held - height)
        current = self.anchor if self.parked else newest_top
        step = {"up": -1, "down": 1, "pgup": -height, "pgdn": height}.get(key)
        target = oldest if key == "home" else current + step

        target = max(oldest, min(target, newest_top))
        # Scrolling back to the bottom resumes following rather than parking
        # there, so the view starts moving again on its own — which is what the
        # operator means by returning to the end.
        if target >= newest_top:
            was = self.parked
            self.follow()
            return was or current != newest_top
        if self.anchor == target:
            return False
        self.anchor = target
        return True

    def window(self, lines: list, *, height: int, dropped: int) -> tuple[list, int, int]:
        """The lines to draw, and their 1-based place among the ones held.

        Numbered against what the ring *holds* rather than against everything
        it has seen, because that is what the band's `of N` already means and
        two numbering schemes in one line would be worse than none.
        """
        held = len(lines)
        if not self.parked:
            shown = lines[-height:] if height < held else lines
            return shown, held - len(shown) + 1, held

        top = max(0, min(self.anchor - dropped, max(0, held - height)))
        self.anchor = top + dropped
        return lines[top : top + height], top + 1, min(top + height, held)


def stream_body(lines, ruleset=None) -> Text:
    """A ring of lines as one renderable — the body both follow forms draw.

    `ruleset` is the operator's declared vocabulary, passed through rather
    than consulted here — see [[highlight]] round 3.

    One assembler on purpose: two renderers holding their own opinions about
    how a stderr line looks would drift the week they were written. stdout
    lines are tinted lexically through [[highlight]]; a stderr line is grey,
    because a second channel is not a severity; and tb's own announcements —
    a rotation, a truncation — keep the warning tint, which is what `voice`
    is for. None of them are re-tagged lexically. The text reaches the
    screen verbatim either way, because marks ride beside it, never instead.
    """
    from cli import highlight as highlight_
    from cli.read import strip_ansi

    body = Text()
    for line in lines:
        if line.stderr:
            # Grey, not warn. A tool talking on stderr is using its second
            # channel — progress, banners, a summary — and painting all of it
            # yellow is the same judgment-in-a-regex's-clothes this module
            # refuses elsewhere. tb's *own* voice keeps the warning tint.
            body.append(
                strip_ansi(line.text) + "\n",
                style="tb.warn" if getattr(line, "voice", False) else "tb.label",
            )
        else:
            body.append_text(band_text(highlight_.spans(strip_ansi(line.text), ruleset)))
            body.append("\n")
    return body


def reside(
    source: str,
    interval: int,
    run_once: Callable[[], Result],
    *,
    clock: Callable[[], float] = time.time,
    wait: Callable[[float], str | None] | None = None,
    console: Console | None = None,
    screen: bool = False,
    ticks: int | None = None,
) -> None:
    """The whole resident rendering: bands, body, and a way out.

    **Inline by default** — the frame is drawn below the prompt and redrawn
    in place, so leaving it leaves the last frame on screen exactly as a
    one-shot does. Round 1 took the alternate screen instead, reasoning that
    a residency may redraw for hours and the scrollback is the operator's;
    true, and it optimised for the wrong session. The common one is *run a
    read, look at it, leave* — and there the alternate screen destroys the
    output it was protecting. `screen=True` (`--screen`) keeps the old
    behaviour for the long residency the original argument was about.

    `q`, `Esc` and Ctrl-C all leave. See [[keys]] for why the first two exist
    and why they degrade to nothing without a terminal.

    The body is tb's own rendering, captured — `cli/output.py` owns every
    byte that reaches a terminal, and a surface that renders elsewhere takes
    that claim up rather than routing around it. The bands come from the
    [[chrome]] contract; this module decides nothing about what they say.
    """
    out = console or Console(theme=THEME, highlight=False)
    state = Residency(source, interval, clock)
    body = Text("")

    def frame_for(result: Result | None) -> Group:
        nonlocal body
        if result is not None:
            with capture(width=out.width) as captured:
                render(result, as_json=False)
            body = Text.from_ansi(captured.text)
        facts = state.chrome()
        top, bottom = chrome_.status_bands(facts, clock(), out.width)
        shown = body if screen else clip(body, room(out))
        return Group(band_text(top), shown, band_text(bottom))

    def run(wait_for: Callable[[float], str | None]) -> None:
        if screen:
            def draw(result: Result | None) -> None:
                out.clear()
                out.print(frame_for(result))

            with out.screen():
                loop(state, run_once, draw, wait_for, ticks=ticks)
            return

        # Live owns the cursor and the in-place repaint. `transient=False` is
        # the point of the whole round: the last frame stays on the screen
        # when the loop ends, the way a one-shot's output does.
        with Live(console=out, auto_refresh=False, transient=False) as live:
            loop(
                state,
                run_once,
                lambda result: live.update(frame_for(result), refresh=True),
                wait_for,
                ticks=ticks,
            )

    try:
        if wait is not None:
            run(wait)
        else:
            with keys.reader() as wait_for:
                run(wait_for)
    except KeyboardInterrupt:
        # Still a way out, and still not a failure. Whatever owned the
        # terminal — the screen context, Live, the key reader — has already
        # put it back; leaving quietly is the whole contract.
        pass
