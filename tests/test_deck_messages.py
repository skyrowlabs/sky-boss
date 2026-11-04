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
