"""The deck lights the clickable row under the mouse, in panes and popups."""

from types import SimpleNamespace
from typing import cast

import pytest
from rich.console import Console
from rich.text import Text

from skyboss import deck, keys
from skyboss import resident as resident_
from skyboss.output import THEME, Result
from skyboss.resident import HOVER_HOLD, MOUSE_HOVER_ON, MOUSE_OFF, Hover, Residency, _Lit, loop, painted
from skyboss.theme import HOVER_SGR

pytestmark = pytest.mark.unit

LINES = ["┌ band", "who", "───", "row one", "row two"]


def pane(rows):
    made = deck.DeckPane("s", lambda row: True, role=deck.MESSAGES)
    made.lines, made.rows = LINES, rows
    return made


def test_a_motion_report_is_a_hover_and_a_press_stays_a_click():
    assert keys._mouse("<35;7;9M") == "hover:7:9"
    assert keys.hovered("hover:7:9") == (7, 9)
    assert keys.hovered("click:7:9") is None
    assert keys.clicked("hover:7:9") is None


def test_hover_goes_out_when_the_mouse_has_been_still():
    now = [0.0]
    hover = Hover(lambda: now[0])
    assert hover.see(4) is True
    assert hover.see(4) is False
    now[0] = HOVER_HOLD + 1
    assert hover.now() == 0
    assert hover.see(4) is True


def test_only_a_row_a_click_would_act_on_lights():
    made = pane([{"key": "m1"}, {"text": "no key"}])
    assert made.on_key("hover:1:4") is True
    assert made.lit() == 4
    assert made.on_key("hover:1:5") is True
    assert made.lit() == 0


def test_a_lit_line_is_rechecked_against_the_latest_frame():
    made = pane([{"key": "m1"}])
    made.on_key("hover:1:4")
    made.lines = ["┌ band"]
    assert made.lit() == 0


@pytest.mark.parametrize(
    "role,row,lights",
    [
        (deck.QUEUE, {"id": "a", "jobs": 2}, True),
        (deck.QUEUE, {"id": "a"}, False),
        (deck.DECISIONS, {"kind": "item"}, True),
        (deck.DECISIONS, {"kind": "group"}, False),
        (deck.TODOS, {"text": "t"}, False),
    ],
)
def test_each_pane_lights_what_its_click_handles(role, row, lights):
    made = deck.DeckPane("s", lambda row: True, role=role)
    made.lines, made.rows = LINES, [row]
    assert made.lights(4) is lights


def test_painted_grounds_the_lit_line_through_its_resets():
    drawn = painted(["plain", "a\x1b[0mb"], 2)
    assert drawn.startswith(MOUSE_HOVER_ON)
    assert HOVER_SGR + "a\x1b[0m" + HOVER_SGR + "b" in drawn
    assert HOVER_SGR + "plain" not in drawn


def test_a_hover_that_changes_nothing_does_not_redraw():
    state = cast(Residency, SimpleNamespace(due=lambda: False))
    drawn = []
    keys_in = iter(["hover:1:1", "hover:1:1", None])
    loop(
        state,
        lambda: Result(),
        drawn.append,
        lambda seconds: next(keys_in),
        ticks=3,
        on_key=lambda key: False,
    )
    assert len(drawn) == 1


def test_a_popup_relights_on_a_hover_and_returns_the_click(capsys):
    keys_in = iter(["hover:1:2", "hover:1:2", "click:1:2"])
    assert deck._popup_key(["a", "b"], lambda y: y == 2, lambda seconds: next(keys_in)) == "click:1:2"
    assert capsys.readouterr().out.count(HOVER_SGR) == 1


def test_mouse_off_also_ends_motion():
    assert "\x1b[?1003l" in MOUSE_OFF
    assert resident_.MOUSE_ON.count("1003") == 0


def test_a_lit_frame_grounds_only_its_line_and_keeps_its_height():
    out = Console(theme=THEME, width=10, force_terminal=True, color_system="truecolor")
    lines = out.render_lines(_Lit(Text("a\nb"), 2), pad=True)
    assert len(lines) == 2
    assert all(seg.style is None or seg.style.bgcolor is None for seg in lines[0])
    assert all(seg.style is not None and seg.style.bgcolor is not None for seg in lines[1])
