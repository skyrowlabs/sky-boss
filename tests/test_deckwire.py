"""The line under the tab row: its shape, how it draws, and how it fades."""

import re

import pytest

from skyboss import deckwire, theme

pytestmark = pytest.mark.unit

HUE = "#3fc1ff"
GROUND = "bg=#000000 fg=#ffffff"


def drawn(frame):
    return re.sub(r"#\[[^\]]*\]", "", frame)


def text(cells):
    return "".join(cells[column] for column in sorted(cells))


def test_a_line_leaves_down_runs_along_and_enters_up_in_either_direction():
    assert text(deckwire.glyphs(2, [6])) == "╰───╯" == text(deckwire.glyphs(6, [2]))


def test_a_sender_between_its_receivers_taps_the_line():
    assert text(deckwire.glyphs(4, [0, 8])) == "╰───┴───╯"


def test_a_line_grows_from_the_sender_and_ends_whole():
    frames = deckwire.frames(10, [30], HUE, GROUND)
    assert drawn(frames[0]).strip() == "╰───" and drawn(frames[deckwire.DRAW_FRAMES - 1]).endswith("╯")
    backwards = deckwire.frames(30, [10], HUE, GROUND)
    assert drawn(backwards[0]).strip() == "───╯"


def test_a_line_keeps_its_place_as_it_fades_toward_the_bar():
    frames = deckwire.frames(10, [30], HUE, GROUND)
    assert len(frames) == deckwire.DRAW_FRAMES + deckwire.HOLD_FRAMES + len(deckwire.FADES)
    assert drawn(frames[-1]) == drawn(frames[deckwire.DRAW_FRAMES - 1]) and HUE not in frames[-1]


def test_a_fade_runs_from_the_colour_to_the_ground():
    assert theme.fade(HUE, 1.0) == HUE and theme.fade(HUE, 0.0) == theme.SURFACE
