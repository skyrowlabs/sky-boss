"""A stall must be able to explain itself.

The surface froze once for a reason that took a morning to find: `RichLog.write`
is superlinear in the size of one renderable and runs on the event loop, so a
single chatty command blocked long enough that no key was ever read. Every
symptom pointed the wrong way — the screen stayed *drawn*, so it looked like a
shutdown problem rather than a loop problem, and the obvious suspect (a 300s
thread join on exit) was the wrong one.

None of that needed to be guesswork. A blocked event loop is trivially
detectable from outside it: something off-loop watches a number that something
on-loop keeps bumping. When the number stops moving, dump every thread's stack
and the blocking call names itself.

**The watcher is a daemon thread**, which matters twice. It cannot itself delay
interpreter exit — `cli/tui/app.run` leaves through `os._exit` only when a
*non-daemon* thread is still alive, and a watchdog that tripped that check would
make every ordinary exit a hard one. And it keeps running while the loop is
wedged, which is the entire point: an async task could not report this, because
the thing it would report is the reason it is not running.
"""

from __future__ import annotations

import faulthandler
import threading
import time
from datetime import datetime
from pathlib import Path

from cli.helpers import STATE_DIR

STALL_PATH = STATE_DIR / "tui-stall.txt"

# Long enough that a legitimately expensive turn does not cry wolf, and short
# enough to catch a freeze while it is still the thing the operator is looking at.
STALL_SECONDS = 5.0

# How often the watcher looks. It sleeps in these increments, so it also bounds
# how long `stop()` takes to be noticed.
POLL_SECONDS = 1.0


class Watchdog:
    """Watches the event loop from off it, and writes a dump when it stops.

    Deliberately split so the interesting half needs no thread and no clock:
    `beat` and `check` are ordinary methods over an injectable clock, and the
    thread is a loop around `check`. A test that had to actually stall a real
    event loop for five seconds would be five seconds of suite for one
    assertion.
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        stall_after: float = STALL_SECONDS,
        poll: float = POLL_SECONDS,
        clock=time.monotonic,
    ) -> None:
        self.path = STALL_PATH if path is None else path
        self.stall_after = stall_after
        self.poll = poll
        self._clock = clock
        self._last_beat = clock()
        # One dump per stall, not one per poll. A ten-minute freeze should leave
        # one legible file, not six hundred appends of the same stack.
        self._reported = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------- on the loop

    def beat(self) -> None:
        """Called from a loop timer. The only thing that proves the loop runs."""
        self._last_beat = self._clock()
        self._reported = False

    # ------------------------------------------------------------ off the loop

    def stalled_for(self) -> float:
        return self._clock() - self._last_beat

    def check(self) -> bool:
        """Dump if the loop has gone quiet. True if this call wrote one."""
        if self._reported or self.stalled_for() < self.stall_after:
            return False
        self._reported = True
        self.dump()
        return True

    def dump(self) -> None:
        """Every thread's stack, appended, with enough context to read it later.

        Failure here is swallowed on purpose. This is diagnostics for a surface
        that is *already* in trouble, and an unwritable state directory must not
        turn a recoverable freeze into a crashed watchdog.
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as handle:
                handle.write(
                    f"\n=== tb tui: event loop stalled {self.stalled_for():.1f}s "
                    f"at {datetime.now().isoformat(timespec='seconds')} ===\n"
                    "The loop is blocked by whichever frame below is on the "
                    "MainThread.\n\n"
                )
                handle.flush()
                faulthandler.dump_traceback(file=handle, all_threads=True)
        except OSError:
            pass

    # ------------------------------------------------------------------ thread

    def start(self) -> None:
        if self._thread is not None:
            return
        self._last_beat = self._clock()
        self._thread = threading.Thread(
            target=self._watch, name="tb-tui-watchdog", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _watch(self) -> None:
        while not self._stop.wait(self.poll):
            self.check()
