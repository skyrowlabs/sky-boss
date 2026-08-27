"""Leaving a resident view. See [[refresh]] round 2 and [[follow]] round 2.

The properties worth defending: `q` and `Esc` end the loop, an arrow key does
not, a non-terminal degrades to a plain sleep rather than failing, and the
terminal is restored on every exit path — a residency that left cbreak behind
would hand the operator a shell that does not echo.
"""

import io

from cli import keys


def test_the_leave_keys_are_q_and_esc():
    assert keys.leaves("q") and keys.leaves("Q") and keys.leaves("\x1b")


def test_an_ordinary_key_does_not_leave():
    for key in ("a", "j", " ", "\n", None):
        assert not keys.leaves(key)


def test_a_stream_that_is_not_a_terminal_gets_a_sleeper_not_an_error():
    """Degrade, never fail: piped stdin still gets a working resident loop,
    with Ctrl-C as the way out."""
    with keys.reader(io.StringIO("q")) as wait:
        assert wait(0) is None


def test_a_closed_stream_is_not_a_terminal():
    stream = io.StringIO()
    stream.close()
    with keys.reader(stream) as wait:
        assert wait(0) is None


def pty_pair():
    """A real terminal, which is the only honest way to test cbreak. Read-only
    text mode on the secondary — `r+` asks for seekability a pty cannot give."""
    import os
    import pty

    primary, secondary = pty.openpty()
    return primary, os.fdopen(secondary, "r", buffering=1)


def test_a_real_terminal_is_restored_even_when_the_body_raises():
    import os
    import termios

    primary, stream = pty_pair()
    before = termios.tcgetattr(stream.fileno())
    try:
        try:
            with keys.reader(stream):
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert termios.tcgetattr(stream.fileno()) == before
    finally:
        stream.close()
        os.close(primary)


def test_a_real_terminal_reports_the_key_pressed():
    import os

    primary, stream = pty_pair()
    try:
        with keys.reader(stream) as wait:
            os.write(primary, b"q")
            assert wait(1.0) == "q"
    finally:
        stream.close()
        os.close(primary)


def test_an_arrow_key_does_not_close_the_view():
    """An arrow arrives as Esc `[` `A`. Reading only its first byte would make
    Up quit — and leave two bytes for the shell that gets the terminal back."""
    import os

    primary, stream = pty_pair()
    try:
        with keys.reader(stream) as wait:
            os.write(primary, b"\x1b[A")
            key = wait(1.0)
            assert key == "\x1b"
            # ...but the sequence was drained, so nothing is left to misread.
            assert wait(0) is None
    finally:
        stream.close()
        os.close(primary)
