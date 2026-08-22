"""Leaving a resident view. See [[refresh]] round 2.

**Ctrl-C is the answer for interrupting something; this is a view you close.**
Every pager and full-screen tool the operator already reaches for takes `q`,
and a resident read that could only be killed was the surprise that produced
this module — the operator's words were *"we need a flag to exit out, like q
or esc"*.

**Degrade, never fail.** A key reader needs a real terminal: raw mode on a
file descriptor that has one. When stdin is a pipe, a file, or a test's
`StringIO` there is simply no reader and Ctrl-C remains the way out — the
resident loop still runs, still redraws, and never raises for the lack.

**The wait and the poll are one primitive.** The loop already paused a second
between frames; this replaces that sleep with a bounded wait *for a key*, so
`q` lands immediately rather than up to a second later, and no second timer
has to be reconciled with the first.
"""

from __future__ import annotations

import contextlib
import select
import sys
from typing import Callable, Iterator

# What closes a resident view. `\x1b` is Esc — bare, which is why the reader
# drains what follows it (see `_drain`): an arrow key arrives as Esc + `[` + a
# letter, and treating its first byte as Esc would make arrow keys quit.
LEAVE = frozenset({"q", "Q", "\x1b"})

# The tick a resident loop redraws on. Here rather than in the loop because it
# is now the timeout of a `select`, not the argument of a sleep.
TICK = 1.0


def leaves(key: str | None) -> bool:
    return key is not None and key in LEAVE


@contextlib.contextmanager
def reader(stream=None) -> Iterator[Callable[[float], str | None]]:
    """Yield `wait(seconds) -> key | None`, cbreak for as long as it is held.

    The yielded callable waits up to `seconds` for a keypress and returns it,
    or returns None if the time passed quietly — so a caller uses it exactly
    where it used to sleep.

    The terminal is restored on every exit path, exception included. A
    residency that left the terminal in cbreak would hand the operator back a
    shell that does not echo, which is a worse bug than the one this fixes.
    """
    if not _is_tty(stream := stream or sys.stdin):
        # No terminal, no reader — and no error. The loop sleeps as before.
        yield _sleeper()
        return

    import termios
    import tty

    fd = stream.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield _waiter(stream)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def _is_tty(stream) -> bool:
    try:
        return bool(stream) and stream.isatty() and stream.fileno() >= 0
    except (AttributeError, OSError, ValueError):
        # A closed or fake stream is not a terminal. Asking is the whole test.
        return False


def _sleeper() -> Callable[[float], str | None]:
    import time

    def wait(seconds: float) -> str | None:
        time.sleep(seconds)
        return None

    return wait


def _waiter(stream) -> Callable[[float], str | None]:
    def wait(seconds: float) -> str | None:
        ready, _, _ = select.select([stream], [], [], seconds)
        if not ready:
            return None
        key = stream.read(1)
        if key == "\x1b":
            _drain(stream)
        return key

    return wait


def _drain(stream) -> None:
    """Swallow the rest of an escape sequence.

    An arrow key is Esc `[` `A`. Without this its first byte reads as a bare
    Esc and pressing Up would close the window — and the two remaining bytes
    would then land in the shell that gets the terminal back.
    """
    while select.select([stream], [], [], 0)[0]:
        stream.read(1)
