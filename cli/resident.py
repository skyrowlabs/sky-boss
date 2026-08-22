"""The terminal's resident loop — `--refresh`, spelled the way watch(1) works.

**The terminal is a surface too.** The refresh rule — re-run a snapshot on a
cadence — lived only in canvas machinery until [[refresh]]; this module is the
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
from rich.text import Text

from cli import chrome as chrome_
from cli.output import THEME, Result, band_text, capture, render


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
    sleep: Callable[[float], None],
    *,
    ticks: int | None = None,
) -> None:
    """Run when due, redraw every tick, until interrupted.

    `draw` is called with a fresh result when one was produced and None on a
    countdown-only tick — the bands change every second, the body only when
    a run does. `ticks` bounds the loop under test; this loop is synchronous
    and pull-driven, so the bound is on time as well as frames — the hang the
    suite's rules exist to prevent cannot hide in it.
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
        sleep(1)
        count += 1


def reside(
    source: str,
    interval: int,
    run_once: Callable[[], Result],
    *,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    console: Console | None = None,
    screen: bool = True,
    ticks: int | None = None,
) -> None:
    """The whole resident rendering: alternate screen, bands, body, Ctrl-C.

    Alternate screen rather than inline, the way watch(1) and htop do it:
    the scrollback is restored intact on exit, which matters because a
    resident invocation may redraw for hours and a terminal's history is
    the operator's. Ctrl-C is the way out and leaves nothing behind.

    The body is tb's own rendering, captured — `cli/output.py` owns every
    byte that reaches a terminal, and a surface that renders elsewhere takes
    that claim up rather than routing around it. The bands come from the
    [[chrome]] contract; this module decides nothing about what they say.
    """
    out = console or Console(theme=THEME, highlight=False)
    state = Residency(source, interval, clock)
    body = Text("")

    def draw(result: Result | None) -> None:
        nonlocal body
        if result is not None:
            with capture(width=out.width) as captured:
                render(result, as_json=False)
            body = Text.from_ansi(captured.text)
        facts = state.chrome()
        top, bottom = chrome_.status_bands(facts, clock(), out.width)
        frame = Group(band_text(top), body, band_text(bottom))
        out.clear()
        out.print(frame)

    try:
        if screen:
            with out.screen():
                loop(state, run_once, draw, sleep, ticks=ticks)
        else:
            loop(state, run_once, draw, sleep, ticks=ticks)
    except KeyboardInterrupt:
        # The way out, not a failure. The screen context has already put the
        # terminal back; leaving quietly is the whole contract.
        pass
