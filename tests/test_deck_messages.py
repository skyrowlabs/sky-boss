"""`sb deck messages` — peer messages read from synthetic transcripts. See [[command-deck]].

Every transcript here is written by the test. This repo is public, and a real
transcript is the operator's conversation.
"""

from __future__ import annotations

import functools
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from skyboss import cli
from skyboss import messages as messages_
from skyboss import output
from skyboss.agents import Scan, Session

#: Host-side; no registry, no transcript and no residency of the operator's.
pytestmark = [pytest.mark.unit]

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)


def invoke(*args: str):
    return CliRunner().invoke(cli, list(args))


def session(ident: str, name: str, cwd: str = "/fx/src/a.repo") -> Session:
    return Session(provider="claude", id=ident, name=name, cwd=cwd, status="idle", pid=1)


def peer(sender: str, body: str, msg_id: str | None, stamp: str, **extra) -> dict:
    origin = {"kind": "peer", "name": sender, "body": body, **extra}
    if msg_id is not None:
        origin["msg_id"] = msg_id
    return {"type": "user", "timestamp": stamp, "uuid": f"u-{msg_id or stamp}", "origin": origin}


def write(projects: Path, who: Session, entries: list) -> Path:
    path = messages_.transcript(who, projects)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join((e if isinstance(e, str) else json.dumps(e)) + "\n" for e in entries))
    return path


class Adapter:
    provider = "claude"

    def __init__(self, sessions):
        self.sessions = sessions

    def scan(self):
        return Scan(provider="claude", sessions=list(self.sessions), present=True, read=len(self.sessions))


def test_the_slug_turns_every_non_alphanumeric_into_a_dash():
    assert messages_.slug("/fx/src/sky-boss.v2_x") == "-fx-src-sky-boss-v2-x"


def test_only_peer_entries_are_read(tmp_path):
    who = session("s1", "ws")
    write(
        tmp_path,
        who,
        [
            {"type": "user", "timestamp": "2026-11-04T11:00:00Z", "origin": {"kind": "human"}},
            {"type": "assistant", "timestamp": "2026-11-04T11:01:00Z", "origin": {"kind": "peer", "msg_id": "x"}},
            peer("jam", "hello", "m1", "2026-11-04T11:02:00Z"),
        ],
    )
    found, problems = messages_.collect([who], tmp_path)
    assert [(m.sender, m.receiver, m.body) for m in found] == [("jam", "ws", "hello")] and problems == []


def test_messages_are_deduplicated_by_msg_id_newest_last(tmp_path):
    a, b = session("s1", "ws"), session("s2", "jam")
    write(
        tmp_path, a, [peer("x", "late", "m2", "2026-11-04T11:30:00Z"), peer("x", "early", "m1", "2026-11-04T11:00:00Z")]
    )
    write(tmp_path, b, [peer("x", "early", "m1", "2026-11-04T11:00:00Z")])
    found, _ = messages_.collect([a, b], tmp_path)
    assert [m.msg_id for m in found] == ["m1", "m2"]


def test_a_message_without_a_msg_id_is_kept_and_not_merged(tmp_path):
    who = session("s1", "ws")
    write(
        tmp_path,
        who,
        [peer("sub", "one", None, "2026-11-04T11:00:00Z"), peer("sub", "two", None, "2026-11-04T11:01:00Z")],
    )
    found, _ = messages_.collect([who], tmp_path)
    assert [m.body for m in found] == ["one", "two"]


def test_only_the_last_fifty_are_kept(tmp_path):
    who = session("s1", "ws")
    write(tmp_path, who, [peer("x", f"n{i}", f"m{i}", f"2026-11-04T10:{i:02d}:00Z") for i in range(55)])
    found, _ = messages_.collect([who], tmp_path)
    assert len(found) == 50 and found[0].body == "n5" and found[-1].body == "n54"


def test_a_row_carries_the_first_line_and_sender_to_receiver(tmp_path):
    who = session("s1", "ws")
    write(tmp_path, who, [peer("jam", "\n  first line\nsecond", "m1", "2026-11-04T11:55:00Z")])
    found, _ = messages_.collect([who], tmp_path)
    (row,) = messages_.rows_of(found, NOW)
    assert (row["when"], row["between"], row["message"]) == ("5m", "jam → ws", "first line")


def test_a_missing_transcript_is_counted_not_skipped(tmp_path):
    found, problems = messages_.collect([session("s1", "ws"), session("s2", "jam")], tmp_path)
    assert found == [] and problems == ["2 session(s) have no transcript where expected: ws, jam"]


def test_an_unreadable_transcript_is_counted(tmp_path):
    who = session("s1", "ws")
    messages_.transcript(who, tmp_path).mkdir(parents=True)
    _, problems = messages_.collect([who], tmp_path)
    assert problems == ["1 transcript(s) could not be read: ws"]


def test_a_torn_peer_line_is_counted(tmp_path):
    who = session("s1", "ws")
    write(tmp_path, who, ['{"type": "user", "origin": {"kind": "peer"', peer("x", "ok", "m1", "2026-11-04T11:00:00Z")])
    found, problems = messages_.collect([who], tmp_path)
    assert len(found) == 1 and problems == ["1 peer line(s) did not parse — skipped"]


def test_the_envelope_has_an_authored_view(tmp_path):
    who = session("s1", "ws")
    write(tmp_path, who, [peer("jam", "hi", "m1", "2026-11-04T11:00:00Z")])
    result = messages_.messages_result([Adapter([who])], tmp_path, NOW)
    assert result.view["authored"] is True
    assert [c["key"] for c in result.view["columns"]] == ["when", "between", "message"]


def test_no_messages_says_how_many_sessions_it_read(tmp_path):
    who = session("s1", "ws")
    write(tmp_path, who, [])
    result = messages_.messages_result([Adapter([who])], tmp_path, NOW)
    assert result.data == [] and result.warnings == ["no messages — 1 live session(s) read, none received one"]


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    who = session("s1", "ws")
    write(tmp_path, who, [peer("jam", "[/x] hi", "m1", "2026-11-04T11:00:00Z")])
    monkeypatch.setattr(messages_.agents_, "providers", lambda: [Adapter([who])])
    monkeypatch.setattr(messages_, "projects_dir", lambda: tmp_path)
    return tmp_path


def test_the_command_draws_a_body_with_markup_in_it(synthetic, said):
    result = invoke("deck", "messages")
    assert result.exit_code == 0, result.output
    assert "jam → ws" in said(result) and "[/x] hi" in said(result)


def test_messages_refuses_ticks_without_refresh(synthetic):
    assert invoke("deck", "messages", "--ticks", "2").exit_code == 2


@pytest.fixture
def reside_calls(monkeypatch):
    calls: list[dict] = []

    def fake_reside(source, interval, run_once, **kwargs):
        calls.append({"source": source, "interval": interval, "result": run_once(), **kwargs})

    monkeypatch.setattr("skyboss.resident.reside", fake_reside)
    return calls


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(output, "resident_ndjson", functools.partial(output.resident_ndjson, sleep=lambda s: None))


def test_ticks_reaches_reside_as_runs_exactly_as_data_does(synthetic, reside_calls, at_a_terminal):
    assert invoke("deck", "messages", "--refresh", "3", "--ticks", "6").exit_code == 0
    assert invoke("data", "--refresh", "3", "--ticks", "6", "--", "printf", "[]").exit_code == 0
    mine, data = reside_calls
    assert mine["source"] == "deck messages" and mine["result"].data[0]["from"] == "jam"
    assert (mine["runs"], mine["interval"]) == (data["runs"], data["interval"]) == (6, 3)


def test_ticks_counts_ndjson_envelopes_exactly_as_data_does(synthetic, no_sleep):
    mine = invoke("deck", "messages", "--refresh", "1", "--ticks", "3").stdout.splitlines()
    data = invoke("data", "--refresh", "1", "--ticks", "3", "--", "printf", "[]").stdout.splitlines()
    assert [json.loads(line)["tick"] for line in mine] == [json.loads(line)["tick"] for line in data] == [1, 2, 3]


def test_json_never_resides_even_at_a_terminal(synthetic, reside_calls, at_a_terminal, no_sleep):
    result = invoke("--json", "deck", "messages", "--refresh", "1", "--ticks", "2")
    assert result.exit_code == 0 and reside_calls == []
    assert [json.loads(line)["tick"] for line in result.stdout.splitlines()] == [1, 2]


# ============================================================================
# Fitting the pane: rows trimmed to the height, never lines
# ============================================================================


def fifty(tmp_path) -> Session:
    who = session("s1", "ws")
    write(tmp_path, who, [peer("jam", f"note {i:02d}", f"m{i}", f"2026-11-04T11:{i:02d}:00Z") for i in range(50)])
    return who


class Clock:
    def __init__(self):
        self.now = 1_766_000_000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        return None


def test_a_short_screen_keeps_the_header_and_the_newest_rows(tmp_path):
    from rich.console import Console

    from skyboss.deck import keep_last
    from skyboss.resident import reside

    who = fifty(tmp_path)
    once = functools.partial(messages_.messages_result, [Adapter([who])], tmp_path, NOW)
    clock = Clock()
    console = Console(record=True, width=100, height=14, force_terminal=True)
    reside(
        "deck messages",
        10,
        once,
        clock=clock,
        wait=clock.sleep,
        console=console,
        screen=True,
        ticks=2,
        fit=keep_last("message(s)"),
    )
    text = console.export_text()
    assert "WHEN" in text and "note 49" in text
    assert "note 00" not in text and "note 39" not in text
    assert "earlier message(s) not shown — the newest" in text


def test_the_fit_is_measured_per_frame(tmp_path):
    from rich.text import Text

    from skyboss.deck import keep_last
    from skyboss.resident import fitted

    result = messages_.messages_result([Adapter([fifty(tmp_path)])], tmp_path, NOW)

    def drawn(r):
        return Text("HEADER\n" + "\n".join(row["message"] for row in r.data))

    for limit, keep in ((11, 9), (21, 19)):
        shown = fitted(result, drawn(result), limit, keep_last("message(s)"), drawn).plain.split("\n")
        assert len(shown) <= limit and shown[0] == f"{50 - keep} earlier message(s) not shown — the newest {keep} fit"
        assert shown[1] == "HEADER" and shown[-1] == "note 49" and len(shown) - 2 == keep


def test_a_body_that_fits_is_untouched(tmp_path):
    from rich.text import Text

    from skyboss.deck import keep_last
    from skyboss.resident import fitted

    result = messages_.messages_result([Adapter([fifty(tmp_path)])], tmp_path, NOW)
    body = Text("small")
    assert fitted(result, body, 100, keep_last("message(s)"), lambda r: Text("redrawn")) is body


def test_the_queue_keeps_its_first_rows_because_waiting_sorts_first():
    from skyboss.deck import keep_first
    from skyboss.output import Result

    trimmed, marker = keep_first("row(s)")(Result(data=[1, 2, 3, 4]), 3)
    assert trimmed.data == [1, 2, 3] and marker == "1 more row(s) not shown — waiting comes first"


def test_json_and_a_pipe_carry_all_fifty(tmp_path, monkeypatch, no_sleep):
    who = fifty(tmp_path)
    monkeypatch.setattr(messages_.agents_, "providers", lambda: [Adapter([who])])
    monkeypatch.setattr(messages_, "projects_dir", lambda: tmp_path)
    assert len(json.loads(invoke("--json", "deck", "messages").stdout)["data"]) == 50
    lines = invoke("deck", "messages", "--refresh", "1", "--ticks", "1", "--screen").stdout.splitlines()
    assert len(json.loads(lines[0])["data"]) == 50


# ============================================================================
# Filling the pane: one line per row at every width
# ============================================================================


def drawn_at(result, width):
    from skyboss.output import capture, filled, render

    with capture(width=width) as captured, filled():
        render(result, as_json=False)
    return _plain(captured.text)


def _plain(text):
    from rich.text import Text

    return Text.from_ansi(text).plain


def long_rows(tmp_path):
    who = session("s1", "a-session-with-a-long-registry-name")
    body = "a first line long enough to need clipping in any pane narrower than a whole monitor " * 2
    write(tmp_path, who, [peer(f"sender-{i}", body, f"m{i}", f"2026-11-04T11:{i:02d}:00Z") for i in range(6)])
    return messages_.messages_result([Adapter([who])], tmp_path, NOW)


@pytest.mark.parametrize("width", [24, 40, 63, 100, 180])
def test_every_row_is_one_line_at_every_width(tmp_path, width):
    lines = drawn_at(long_rows(tmp_path), width).rstrip("\n").split("\n")
    assert all(len(line) <= width for line in lines), [len(line) for line in lines]
    notes = [line for line in lines if " did not" in line]
    assert lines[1].startswith("─") and len(lines) == 2 + 6 + len(notes) and len(notes) <= 1


@pytest.mark.parametrize("width", [60, 120, 200])
def test_the_table_uses_the_whole_width(tmp_path, width):
    lines = drawn_at(long_rows(tmp_path), width).split("\n")
    assert len(lines[1]) == width


def test_without_fill_the_drawing_is_unchanged(tmp_path):
    from skyboss.output import capture, render

    result = long_rows(tmp_path)
    with capture(width=63) as captured:
        render(result, as_json=False)
    assert len(_plain(captured.text).split("\n")[1]) < 63


def test_the_queue_fills_too(tmp_path):
    from skyboss.deck import view_of
    from skyboss.output import Result

    rows = [
        {
            "where": "deck",
            "window": "a-very-long-window-name",
            "status": "unregistered",
            "name": "n" * 30,
            "up": "3m",
            "cwd": "/fx/" + "deep/" * 20,
            "pid": 1,
            "id": "x",
            "started": "",
        }
    ] * 3
    result = Result(data=rows, view=view_of(rows))
    for width in (20, 50, 90):
        lines = drawn_at(result, width).rstrip("\n").split("\n")
        notes = [line for line in lines if " did not" in line]
        assert all(len(line) <= width for line in lines) and len(lines) == 2 + 3 + len(notes)


def test_a_resized_pane_is_refilled_on_the_next_frame(tmp_path):
    from rich.console import Console

    from skyboss.deck import keep_last
    from skyboss.resident import reside

    result = long_rows(tmp_path)
    clock = Clock()
    console = Console(record=True, width=100, height=30, force_terminal=True)

    def wait(seconds):
        console.width = 40
        return clock.sleep(seconds)

    reside(
        "deck messages",
        10,
        lambda: result,
        clock=clock,
        wait=wait,
        console=console,
        screen=True,
        ticks=3,
        fit=keep_last("message(s)"),
        fill=True,
    )
    rules = {len(line) for line in console.export_text().split("\n") if line and set(line) == {"─"}}
    assert {100, 40} <= rules


def test_a_trailing_blank_line_is_counted_against_the_height(tmp_path):
    from rich.console import Console
    from rich.text import Text

    from skyboss.deck import keep_last
    from skyboss.resident import fitted

    result = messages_.messages_result([Adapter([fifty(tmp_path)])], tmp_path, NOW)

    def drawn(r):
        return Text("HEADER\n" + "\n".join(row["message"] for row in r.data) + "\n\n")

    console = Console(width=80)
    shown = fitted(result, drawn(result), 12, keep_last("message(s)"), drawn, console)
    assert len(console.render_lines(shown, console.options, pad=False)) <= 12


def test_the_count_line_never_wraps(tmp_path):
    from rich.console import Console
    from rich.text import Text

    from skyboss.deck import keep_last
    from skyboss.resident import fitted

    result = messages_.messages_result([Adapter([fifty(tmp_path)])], tmp_path, NOW)
    console = Console(width=20)

    def drawn(r):
        return Text("\n".join(row["message"] for row in r.data))

    shown = fitted(result, drawn(result), 10, keep_last("message(s)"), drawn, console)
    first = console.render_lines(shown, console.options, pad=False)[0]
    assert "".join(segment.text for segment in first).startswith("41 earlier")
    assert len(console.render_lines(shown, console.options, pad=False)) <= 10


def test_an_overshooting_trim_takes_back_the_rows_that_fit(tmp_path):
    from rich.console import Console
    from rich.text import Text

    from skyboss.deck import keep_last
    from skyboss.resident import fitted

    result = messages_.messages_result([Adapter([fifty(tmp_path)])], tmp_path, NOW)

    def drawn(r):
        frame = "BOX\n" * 5 if len(r.data) == 50 else ""
        return Text(frame + "HEADER\n" + "\n".join(row["message"] for row in r.data))

    console = Console(width=80)
    lines = fitted(result, drawn(result), 12, keep_last("message(s)"), drawn, console).plain.split("\n")
    assert len(lines) == 12 and lines[0].startswith("40 earlier") and lines[-1] == "note 49"


# ============================================================================
# Round 4: keys, the wheel, and a counted line
# ============================================================================


def resident_control():
    from skyboss.resident import Control

    return Control


class Stream:
    def __init__(self, text):
        self.text = text

    def read(self, n):
        out, self.text = self.text[:n], self.text[n:]
        return out


@pytest.mark.parametrize(
    ("raw", "key"),
    [("[<64;10;5M", "wheelup"), ("[<65;1;1M", "wheeldown"), ("[<0;3;4M", None), ("[<64;10;5m", None), ("[A", "up")],
)
def test_an_sgr_wheel_report_is_a_key_and_any_other_report_is_nothing(raw, key):
    from skyboss import keys

    stream = Stream(raw)
    assert keys._sequence(stream, ready=lambda s: bool(s.text)) == key


class Taker(resident_control()):  # type: ignore[misc]
    """A control that takes one key and counts its frames."""

    counted = True
    wheel = True

    def __init__(self):
        self.keys = []
        self.shaped = 0

    def shape(self, result):
        self.shaped += 1
        return result

    def on_key(self, key):
        self.keys.append(key)
        return key == "up"


def test_a_taken_key_redraws_at_once_and_the_wheel_is_reported_on_screen(tmp_path):
    from rich.console import Console

    from skyboss.deck import keep_last
    from skyboss.resident import MOUSE_OFF, MOUSE_ON, reside

    presses = iter(["up", None, None, None])
    clock = Clock()

    def wait(seconds):
        clock.sleep(seconds)
        return next(presses, None)

    control = Taker()
    import io

    sink = io.StringIO()
    console = Console(record=True, width=80, height=20, force_terminal=True, file=sink)
    result = long_rows(tmp_path)
    reside(
        "deck messages",
        10,
        lambda: result,
        clock=clock,
        wait=wait,
        console=console,
        screen=True,
        ticks=2,
        fit=keep_last("message(s)"),
        fill=True,
        control=control,
    )
    written = sink.getvalue()
    # Shaped frames: the result, the redraw the key caused, and the second tick.
    assert control.keys == ["up"] and control.shaped == 3
    assert written.index(MOUSE_ON) < written.rindex(MOUSE_OFF)


def test_a_counted_view_says_newest_even_when_every_row_fits(tmp_path):
    from rich.console import Console
    from rich.text import Text

    from skyboss.deck import DeckPane, keep_last
    from skyboss.resident import fitted

    result = messages_.messages_result([Adapter([fifty(tmp_path)])], tmp_path, NOW)
    pane = DeckPane("sb", lambda row: True, scroll=True)

    def drawn(r):
        return Text("\n".join(row["message"] for row in r.data))

    console = Console(width=80)
    shown = fitted(result, drawn(result), 100, keep_last("message(s)", pane), drawn, console, always=True)
    assert shown.plain.split("\n")[0] == "newest"


def test_a_segmented_cell_is_drawn_in_its_parts_roles(tmp_path):
    from skyboss.output import capture, render

    who = session("s1", "ws")
    write(tmp_path, who, [peer("jam", "hi", "m1", "2026-11-04T11:00:00Z")])
    place = lambda sessions: {"s1": ("sky-boss", 2)}  # noqa: E731
    result = messages_.messages_result([Adapter([who])], tmp_path, NOW, place=place, paint=True)
    assert result.data[0]["between_parts"][2] == ["ws", "sb.agent.sb"]
    with capture(width=80) as captured:
        render(result, as_json=False)
    assert "jam → ws" in _plain(captured.text)


def test_the_fit_keeps_the_scroll_while_it_tries_row_counts(tmp_path):
    from rich.console import Console
    from rich.text import Text

    from skyboss.deck import DeckPane, keep_last
    from skyboss.resident import fitted

    result = messages_.messages_result([Adapter([fifty(tmp_path)])], tmp_path, NOW)
    pane = DeckPane("sb", lambda row: True, scroll=True)
    pane.offset = 5

    def drawn(r):
        return Text("HEADER\n" + "\n".join(row["message"] for row in r.data))

    console = Console(width=80)
    lines = fitted(result, drawn(result), 12, keep_last("message(s)", pane), drawn, console, always=True).plain.split(
        "\n"
    )
    assert pane.offset == 5 and lines[0].startswith("↑ 5 back · ") and lines[-1] == "note 44"
