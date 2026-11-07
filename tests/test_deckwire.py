"""The line under the tab row: its shape, how it draws, and how it lands."""

import re

import pytest

from skyboss import deckwire, theme
from skyboss.deckwire import DRAW, FADE, HOLD, Flight, Sent, Tail, compose, read_entry

pytestmark = pytest.mark.unit

GROUND = "bg=#000000 fg=#ffffff"
HUES = {"api": "#3fc1ff", "web": "#ff8800", "docs": "#22cc66"}
CENTRES = {"api": 4, "web": 14, "docs": 24}


def row(flights, now):
    return compose(flights, CENTRES, HUES, now, GROUND)


def drawn(frame):
    return re.sub(r"#\[[^\]]*\]", "", frame)


def test_a_line_leaves_down_runs_along_and_enters_up_in_either_direction():
    assert drawn(row([Flight("api", "web", 0.0)], DRAW)).strip() == "╰─────────╯"
    assert drawn(row([Flight("web", "api", 0.0)], DRAW)).strip() == "╰─────────╯"


def test_a_line_grows_from_its_sender():
    assert drawn(row([Flight("api", "web", 0.0)], DRAW / 2)).strip() == "╰─────"
    assert drawn(row([Flight("web", "api", 0.0)], DRAW / 2)).strip() == "─────╯"


def test_lines_sharing_a_sender_join():
    flights = [Flight("web", "api", 0.0), Flight("web", "docs", 0.0)]
    assert drawn(row(flights, DRAW)).strip() == "╰─────────┴─────────╯"


def test_a_line_holds_the_senders_hue_until_received():
    frame = row([Flight("api", "web", 0.0)], 500.0)
    assert f"fg={HUES['api']}" in frame and HUES["web"] not in frame


def test_a_received_line_takes_the_receivers_hue_then_fades():
    flight = Flight("api", "web", 0.0, landed=10.0)
    assert f"fg={HUES['web']}" in row([flight], 10.0 + HOLD / 2)
    faded = row([flight], 10.0 + HOLD + FADE / 2)
    assert HUES["web"] not in faded and drawn(faded).strip() == "╰─────────╯"
    assert flight.over(10.0 + HOLD + FADE)


def test_a_message_taken_in_at_once_still_draws_out_first():
    flight = Flight("api", "web", 0.0, landed=0.0)
    assert flight.lands_at() == DRAW and f"fg={HUES['api']}" in row([flight], DRAW / 2)


def test_a_line_gives_up_on_a_receiver_that_never_reads():
    flight = Flight("api", "web", 0.0)
    assert not flight.over(deckwire.PATIENCE) and flight.over(deckwire.PATIENCE + 1)


def test_a_tab_out_of_view_draws_nothing():
    assert compose([Flight("api", "web", 0.0)], {"api": 4}, HUES, DRAW, GROUND) == ""


def test_a_fade_runs_from_the_colour_to_the_ground():
    assert theme.fade("#3fc1ff", 1.0) == "#3fc1ff" and theme.fade("#3fc1ff", 0.0) == theme.SURFACE


def test_a_transcript_past_is_not_news_and_a_torn_line_waits(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text("old\n")
    tail = Tail()
    assert tail.read(path) == []
    with path.open("a") as handle:
        handle.write("new\ntorn")
    assert tail.read(path) == ["new"]
    with path.open("a") as handle:
        handle.write(" line\n")
    assert tail.read(path) == ["torn line"]


def test_a_failed_send_is_not_a_message():
    asked = {"t": "web"}
    line = (
        '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t"}]},'
        '"toolUseResult":{"success":false,"msg_id":"m"}}'
    )
    assert read_entry(line, asked) is None


def test_a_send_pairs_its_call_with_its_result():
    asked = {}
    call = '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t","name":"SendMessage","input":{"to":"web"}}]}}'
    result = (
        '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t"}]},'
        '"toolUseResult":{"success":true,"msg_id":"m"}}'
    )
    assert read_entry(call, asked) is None and read_entry(result, asked) == Sent("web", "m")


def test_a_message_absorbed_mid_turn_is_received_too():
    origin = '{"kind":"peer","msg_id":"m","name":"api"}'
    line = '{"type":"attachment","attachment":{"type":"queued_command","origin":' + origin + "}}"
    assert read_entry(line, {}) == {"kind": "peer", "msg_id": "m", "name": "api"}
