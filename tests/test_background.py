"""What a session has running beside it: read from a sub-agent's record and the process tree."""

from __future__ import annotations

import json
import os

import pytest

from skyboss import background
from skyboss import deck as deck_

pytestmark = pytest.mark.unit

NOW = 1_000_000.0


def write_agent(projects, name, wrote, **meta):
    folder = projects / "-repo" / "abc" / "subagents"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.meta.json").write_text(json.dumps(meta))
    transcript = folder / f"{name}.jsonl"
    transcript.write_text("not read\n")
    os.utime(transcript, (wrote, wrote))


def test_a_sub_agent_says_how_long_ago_it_wrote_and_leaves_once_quiet(tmp_path):
    write_agent(tmp_path, "new", NOW - 5, agentType="Explore", description="find the seam")
    write_agent(tmp_path, "newer", NOW - 1, agentType="Plan", description="draft")
    write_agent(tmp_path, "old", NOW - background.RECENT - 1, agentType="Plan", description="gone")
    jobs = background.subagents("/repo", "abc", tmp_path, NOW)
    assert [job.label for job in jobs] == ["Plan: draft", "Explore: find the seam"]
    assert jobs[1].age == "5s"


def test_a_session_with_no_sub_agents_has_none(tmp_path):
    assert background.subagents("/repo", "nothing", tmp_path, NOW) == []


def test_an_unreadable_record_is_skipped(tmp_path):
    write_agent(tmp_path, "ok", NOW, agentType="Plan", description="draft")
    write_agent(tmp_path, "bad", NOW)
    (tmp_path / "-repo" / "abc" / "subagents" / "bad.meta.json").write_text("{not json")
    assert len(background.subagents("/repo", "abc", tmp_path, NOW)) == 1


WRAPPER = (
    "/usr/bin/bash\0-c\0source /home/x/.claude/shell-snapshots/snapshot.sh 2>/dev/null || true && "
    "eval 'sleep 60 && echo '\"'\"'done'\"'\"'\nsecond line' && pwd -P >| /tmp/cwd\0"
)


def fake_proc(tmp_path, **commands):
    (tmp_path / "uptime").write_text("100.0 1.0\n")
    for pid, cmdline in commands.items():
        folder = tmp_path / pid[1:]
        folder.mkdir()
        (folder / "cmdline").write_bytes(cmdline.encode())
        (folder / "stat").write_text("1 (bash) S " + " ".join(["0"] * 18) + " 0\n")
    return tmp_path


def test_only_a_wrapped_shell_counts_and_shows_its_own_command(tmp_path):
    proc = fake_proc(tmp_path, p10=WRAPPER, p11="npm\0exec\0some-mcp\0")
    jobs = background.shells(1, {10: 1, 11: 1, 12: 2}, proc)
    assert [(job.kind, job.label) for job in jobs] == [("shell", "sleep 60 && echo 'done'")]


def test_a_wrapper_it_cannot_read_is_still_a_shell():
    assert background.command_of("bash -c source shell-snapshots/x") == "shell"


def test_a_count_leaves_out_what_is_not_there():
    agent, shell = background.Job("agent", "a", ""), background.Job("shell", "s", "")
    assert background.counted([agent, agent, shell]) == "2a 1s"
    assert background.counted([shell]) == "1s" and background.counted([]) == ""


def row(ident="abc", jobs=()):
    return {"id": ident, "where": "deck", "bg": "▸ 1s" if jobs else "", "jobs": list(jobs), "window": "ws"}


def test_a_queue_row_unfolds_only_when_opened():
    job = background.Job("shell", "sleep 60", "3s").to_dict()
    rows = [row(jobs=[job]), row("def")]
    assert deck_.unfolded(rows, set()) == rows
    drawn = deck_.unfolded(rows, {"abc"})
    assert [r["window"] for r in drawn] == ["ws", "  ↳ shell", "ws"]
    assert drawn[0]["bg"] == "▾ 1s" and (drawn[1]["name"], drawn[1]["up"]) == ("sleep 60", "3s")
    assert drawn[1]["where"] == ""  # so a folded pane's count of deck rows stays a count of sessions


def test_a_click_folds_and_unfolds_a_row_with_jobs_and_nothing_else():
    pane = deck_.DeckPane("sb", lambda r: True, role=deck_.QUEUE)
    job = background.Job("shell", "sleep 60", "3s").to_dict()
    pane.lines = ["┌ deck queue ┐", "window", "──────", "ws", "jam"]
    pane.rows = [row(jobs=[job]), row("def")]
    assert pane.on_key("click:2:4") and pane.open == {"abc"}
    assert pane.on_key("click:2:4") and pane.open == set()
    assert not pane.on_key("click:2:5") and pane.open == set()
    assert not pane.on_key("click:2:2")


def test_every_deck_pane_is_padded_and_the_view_keeps_its_columns():
    assert deck_.DeckPane("sb", lambda r: True, role=deck_.QUEUE).pad == 1
    job = background.Job("shell", "sleep 60", "3s").to_dict()
    filled = {**{key: "" for key in (*deck_.INLINE, *deck_.HIDDEN)}, **row(jobs=[job])}
    rows = deck_.unfolded([filled], {"abc"})
    assert {column["key"] for column in deck_.view_of(rows)["columns"]} == set(deck_.INLINE)
