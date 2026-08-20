"""The refresh clock. It lives here, in Python, keyed to a connection.

The operator's rule is that a watcher **pauses when its window closes and keeps
running when the window is merely minimized.** That sounds like a UI detail and
is actually the decision about where the scheduler lives.

It cannot be a browser timer. A minimized window is a hidden page, and Chrome
clamps a hidden page's timers to roughly one fire per minute — so a five-second
watcher would quietly become a sixty-second one at the exact moment you stopped
being able to see that it had. The mockup drives refresh from `setInterval`;
that is the one thing in it that does not survive contact with the requirement.

A connection expresses the rule exactly. A window holds a stream open for as
long as it exists; minimizing does not drop a socket and closing does. So a
`Session` owns its watchers, and when the stream ends every watcher in it stops.
Nothing survives the last window, which is why this is a scheduler and not a
daemon.

**The interesting half needs no event loop and no real clock.** `due` and
`fire_now` are ordinary methods over an injectable clock, exactly as
`cli/tui/watchdog.py` split itself, and for the same reason: a test that had to
wait five real seconds to prove a five-second cadence would be five seconds of
suite for one assertion.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# The cadences the surface offers. 0 means pinned but manual — the window stays
# and refreshes only when asked.
INTERVALS = (0, 5, 30, 60, 300)


@dataclass
class Watcher:
    """One window's standing request to re-run its command."""

    window_id: str
    argv: list[str]
    interval: int = 0
    last_run: float = 0.0
    # Set while a run is in flight. A slow command must not stack up behind
    # itself: a `jam pr list` taking 8s on a 5s cadence would otherwise queue
    # runs forever and each tick would fall further behind.
    running: bool = False

    def due(self, now: float) -> bool:
        if not self.interval or self.running:
            return False
        return (now - self.last_run) >= self.interval


@dataclass
class Session:
    """The watchers belonging to one open stream.

    The stream is the lifetime. There is no unregister-on-close to forget,
    because closing the stream drops the whole session.
    """

    id: str
    clock: object = time.monotonic
    watchers: dict[str, Watcher] = field(default_factory=dict)

    def now(self) -> float:
        return self.clock()

    def set(self, window_id: str, argv: list[str], interval: int) -> Watcher:
        """Register or re-point a watcher. Idempotent per window.

        Changing the cadence restarts the count from now rather than measuring
        against the previous run, so bumping 5s to 300s does not fire once more
        immediately on the way past.
        """
        watcher = self.watchers.get(window_id)
        if watcher is None:
            watcher = Watcher(window_id=window_id, argv=list(argv))
            self.watchers[window_id] = watcher
        watcher.argv = list(argv)
        if watcher.interval != interval:
            watcher.interval = interval
            watcher.last_run = self.now()
        return watcher

    def drop(self, window_id: str) -> None:
        self.watchers.pop(window_id, None)

    def due(self) -> list[Watcher]:
        """Every watcher whose cadence has come round. Pure — fires nothing."""
        now = self.now()
        return [w for w in self.watchers.values() if w.due(now)]

    def claim(self, watcher: Watcher) -> None:
        """Mark a watcher as in flight, so the next tick skips it."""
        watcher.running = True
        watcher.last_run = self.now()

    def release(self, watcher: Watcher) -> None:
        watcher.running = False
