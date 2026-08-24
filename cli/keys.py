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

# What closes a resident view. `\x1b` is Esc — **bare**, which is the whole
# subtlety: an arrow key also arrives as Esc, followed immediately by more
# bytes. The reader tells them apart by whether anything followed, and returns
# a *name* for the ones that did. See `_sequence`.
LEAVE = frozenset({"q", "Q", "\x1b"})

# The named keys a resident view may act on. Round 2 drained these so that Up
# could not quit; round 3 decodes them instead, because a follow's ring holds
# lines the terminal never printed and scrolling is the only way back to them.
# See [[follow]] round 3.
MOVES = ("up", "down", "pgup", "pgdn", "home", "end")

# Final bytes of the sequences that matter, by their two introducers. `[` is
# the common form and `O` is application-cursor mode, which some terminals put
# the arrow keys into — a reader that knew only `[` would work everywhere until
# it did not.
_FINAL = {"A": "up", "B": "down", "H": "home", "F": "end"}

# The numeric forms, `Esc [ N ~`. Home and End have both spellings in the wild.
_TILDE = {"5": "pgup", "6": "pgdn", "1": "home", "7": "home", "4": "end", "8": "end"}

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
            return _sequence(stream)
        return key

    return wait


def _ready(stream) -> bool:
    """Is there a byte waiting right now? The one place this asks."""
    return bool(select.select([stream], [], [], 0)[0])


def _sequence(stream, ready=_ready) -> str | None:
    """Esc, and whatever followed it: a movement name, or Esc itself.

    **Nothing followed means the operator pressed Esc**, which leaves. Bytes
    followed means a key that reports itself as a sequence, and round 2 threw
    those away so that Up could not quit. Decoding them is the same test with
    the result kept.

    `ready` is injected for the reason every clock here is: there is no
    terminal in the suite, and `select` on a fake stream polls the real stdin
    rather than the fake — which reads as the code being wrong when it is the
    harness.

    Anything unrecognised is consumed and reported as nothing at all — an
    unknown sequence must not fall through to the shell that gets the terminal
    back, and must not be mistaken for a key with a meaning. See [[follow]]
    round 3.
    """
    if not ready(stream):
        return "\x1b"

    introducer = stream.read(1)
    if introducer not in ("[", "O"):
        _drain(stream, ready)
        return None

    body = ""
    while ready(stream):
        char = stream.read(1)
        body += char
        # A sequence ends at its final byte: a letter, or `~` for the numeric
        # forms. Reading further would eat the next keystroke.
        if char.isalpha() or char == "~":
            break

    if body.endswith("~"):
        return _TILDE.get(body[:-1])
    return _FINAL.get(body)


def _drain(stream, ready=_ready) -> None:
    """Swallow the rest of an unrecognised sequence, so none of it reaches the
    shell that gets the terminal back."""
    while ready(stream):
        stream.read(1)
