"""Scrolling a follow. See [[follow]] round 3.

Everything here is arithmetic over injected numbers — there is no terminal in
the suite and a viewport that needed one would be untestable for the same
reason the key reader is.
"""

import io

import pytest

from cli import keys
from cli.resident import Viewport


def ready(stream) -> bool:
    """`select` on a fake stream polls the *real* stdin, which reads as the
    code being wrong when it is the harness. Injected instead."""
    pos = stream.tell()
    rest = stream.read()
    stream.seek(pos)
    return bool(rest)


def decode(text: str):
    stream = io.StringIO(text)
    stream.read(1)
    return keys._sequence(stream, ready)


# ── The key reader ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sequence,name",
    [
        ("\x1b[A", "up"), ("\x1b[B", "down"),
        ("\x1b[5~", "pgup"), ("\x1b[6~", "pgdn"),
        ("\x1b[H", "home"), ("\x1b[F", "end"),
        ("\x1b[1~", "home"), ("\x1b[4~", "end"),
        # Application-cursor mode. A reader that knew only `[` would work
        # everywhere until it did not.
        ("\x1bOA", "up"), ("\x1bOF", "end"),
    ],
)
def test_a_movement_key_decodes_to_a_name(sequence, name):
    assert decode(sequence) == name


def test_a_bare_esc_still_leaves():
    """The whole subtlety: an arrow key also arrives as Esc. Nothing following
    is what tells them apart, and round 2 already had that test — it just threw
    the answer away."""
    assert decode("\x1b") == "\x1b"
    assert keys.leaves(decode("\x1b"))


def test_a_movement_key_does_not_leave():
    for name in keys.MOVES:
        assert not keys.leaves(name)


def test_an_unknown_sequence_is_consumed_and_means_nothing():
    """It must not fall through to the shell that gets the terminal back, and
    must not be mistaken for a key with a meaning."""
    stream = io.StringIO("\x1b[Z")
    stream.read(1)
    assert keys._sequence(stream, ready) is None
    assert stream.read() == ""


# ── The viewport ────────────────────────────────────────────────────────────


def test_a_view_starts_following():
    assert Viewport().parked is False


def test_scrolling_up_parks():
    view = Viewport()
    assert view.move("up", height=10, held=50, dropped=0) is True
    assert view.parked is True


def test_up_at_the_top_does_not_park_a_following_view():
    """The band would announce a state the operator did not ask for."""
    view = Viewport()
    assert view.move("up", height=50, held=10, dropped=0) is False
    assert view.parked is False


def test_end_resumes_following():
    view = Viewport()
    view.move("home", height=10, held=50, dropped=0)
    assert view.move("end", height=10, held=50, dropped=0) is True
    assert view.parked is False


def test_scrolling_back_to_the_bottom_resumes_rather_than_parking_there():
    """Otherwise the view would sit still at the tail while lines arrived,
    which is not what returning to the end means."""
    view = Viewport()
    view.move("up", height=10, held=50, dropped=0)
    view.move("down", height=10, held=50, dropped=0)
    assert view.parked is False


def test_home_goes_to_the_oldest_line_still_held():
    view = Viewport()
    view.move("home", height=10, held=50, dropped=120)
    assert view.anchor == 120


def test_a_page_moves_a_screenful():
    view = Viewport()
    view.move("pgup", height=10, held=100, dropped=0)
    assert view.anchor == 80


def test_movement_is_clamped_at_both_ends():
    view = Viewport()
    for _ in range(50):
        view.move("pgup", height=10, held=100, dropped=0)
    assert view.anchor == 0


def test_the_anchor_is_absolute_so_eviction_walks_the_view_to_the_top():
    """A ring holding the last 200 of 5,000 lines still knows *which* 200. An
    offset counted from the oldest held line would slide under the operator
    every time a line arrived."""
    view = Viewport()
    view.move("home", height=10, held=200, dropped=0)
    lines = list(range(200))
    seen = []
    for dropped in (0, 5, 20):
        _, first, last = view.window(lines, height=10, dropped=dropped)
        seen.append((view.anchor, first, last))
    assert seen == [(0, 1, 10), (5, 1, 10), (20, 1, 10)]


def test_a_following_window_is_the_tail():
    view = Viewport()
    shown, first, last = view.window(list(range(100)), height=10, dropped=0)
    assert shown == list(range(90, 100))
    assert (first, last) == (91, 100)


def test_a_window_smaller_than_the_room_is_all_of_it():
    view = Viewport()
    shown, first, last = view.window([1, 2, 3], height=10, dropped=0)
    assert shown == [1, 2, 3]
    assert (first, last) == (1, 3)


def test_a_parked_window_holds_still_while_the_ring_grows():
    """The only behaviour that makes scrolling worth having — a view that
    snapped back on every arriving line would be unusable on exactly the busy
    log you scrolled up to read."""
    view = Viewport()
    view.move("home", height=5, held=50, dropped=0)
    first_pass, _, _ = view.window(list(range(50)), height=5, dropped=0)
    grown, _, _ = view.window(list(range(80)), height=5, dropped=0)
    assert first_pass == grown == [0, 1, 2, 3, 4]


def test_a_key_that_is_not_a_movement_changes_nothing():
    view = Viewport()
    assert view.move("x", height=10, held=50, dropped=0) is False
