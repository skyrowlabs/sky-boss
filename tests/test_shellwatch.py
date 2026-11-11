"""Shells a deck tab left running: a stuck wait loop is certain, a long unbounded one a hint."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from skyboss import deck as deck_
from skyboss import shellwatch
from skyboss import todos as todos_

pytestmark = pytest.mark.unit

LOOP = 'until ! pgrep -f "unshare --user --map-root-user --net"; do sleep 5; done; echo ran'
#: The loop's shell (10) and its sleep (11) under the tab's claude (1).
PARENTS = {10: 1, 11: 10, 20: 1}


def shell(command=LOOP, seconds=60.0, pid=10):
    return shellwatch.Shell(pid, "500", command, seconds)


def test_a_pgrep_full_pattern_is_found_past_its_options():
    assert shellwatch.patterns(LOOP) == ["unshare --user --map-root-user --net"]
    assert shellwatch.patterns("while [ \"$(pgrep -u me -f 'check pre-push')\" ]; do :; done") == ["check pre-push"]
    assert shellwatch.patterns("while pgrep foo; do sleep 1; done") == []


def test_a_loop_whose_pattern_matches_only_itself_is_stuck():
    lines = {10: f"bash -c {LOOP}", 11: "sleep 5", 20: "vim notes"}
    found = shellwatch.verdict(shell(), "busy", PARENTS, lines)
    assert found is not None
    kind, why = found
    assert kind == shellwatch.STUCK and "never end" in why


def test_a_loop_whose_process_is_still_there_waits_rightly():
    lines = {10: f"bash -c {LOOP}", 30: "unshare --user --map-root-user --net sh"}
    assert shellwatch.verdict(shell(), "busy", PARENTS, lines) is None


def test_a_loop_whose_pattern_misses_its_own_line_is_left_alone():
    command = "while pgrep -f 'ch[e]ck pre-push'; do sleep 5; done"
    assert shellwatch.verdict(shell(command), "idle", PARENTS, {10: command}) is None


def test_a_long_unbounded_shell_in_a_finished_turn_is_a_hint():
    long = shellwatch.LONG_AFTER + 1
    assert (shellwatch.verdict(shell("tail -f log", long), "shell", PARENTS, {}) or ("",))[0] == shellwatch.LONG
    assert shellwatch.verdict(shell("tail -f log", long), "busy", PARENTS, {}) is None
    assert shellwatch.verdict(shell("timeout 3h tail -f log", long), "idle", PARENTS, {}) is None
    assert shellwatch.verdict(shell("for i in $(seq 1 60); do gh run view; done", long), "idle", PARENTS, {}) is None


def noted(agent):
    todo = todos_.load("sb", agent, todos_.DECISIONS)
    assert todo is not None
    return todo.items


def test_the_sweep_notes_a_stuck_shell_once_and_closes_the_note_when_it_ends(monkeypatch):
    running = [shell()]
    monkeypatch.setattr(deck_, "panes", lambda name: ([], SimpleNamespace(ok=True)))
    monkeypatch.setattr(deck_, "deck_windows", lambda *a: ([("@1", "proto-pilot", "shell", None, 1)], set()))
    monkeypatch.setattr(deck_, "parents", lambda proc: PARENTS)
    monkeypatch.setattr(shellwatch, "command_lines", lambda proc: {10: LOOP})
    monkeypatch.setattr(shellwatch, "shells_of", lambda pid, parent_of, proc: running)
    deck_.watch_shells("sb", adapters=[])
    deck_.watch_shells("sb", adapters=[])
    items = noted("proto-pilot")
    assert len(items) == 1 and items[0].kind == todos_.NOTICE and items[0].text.startswith("stuck shell 10")
    running.clear()
    deck_.watch_shells("sb", adapters=[])
    closed = noted("proto-pilot")[0]
    assert closed.done and closed.ruling == "the shell ended" and not closed.untold


def fake_proc(tmp_path, processes: dict[int, tuple[str, int]], uptime: float = 1000.0):
    """A `/proc` holding each pid's NUL-joined cmdline and a stat whose field 22 is its start tick."""
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "uptime").write_text(f"{uptime} 0.0\n")
    (proc / "self").mkdir()
    for pid, (cmdline, start) in processes.items():
        (proc / str(pid)).mkdir()
        (proc / str(pid) / "cmdline").write_bytes(cmdline.replace(" ", "\0").encode() + b"\0")
        fields = ["S", "1"] + ["0"] * 17 + [str(start)]
        (proc / str(pid) / "stat").write_text(f"{pid} (fx (shell)) {' '.join(fields)}\n")
    return proc


def test_command_lines_reads_every_process_and_skips_what_is_not_one(tmp_path):
    proc = fake_proc(tmp_path, {7: ("pgrep -f x", 1)})
    (proc / "8").mkdir()  # gone between the listing and the read
    assert shellwatch.command_lines(proc) == {7: "pgrep -f x"}
    assert shellwatch.command_lines(tmp_path / "absent") == {}


def test_shells_of_unwraps_each_snapshot_shell_and_times_it(tmp_path, monkeypatch):
    monkeypatch.setattr(shellwatch.os, "sysconf", lambda name: 100)
    wrapper = "bash -c source /x/shell-snapshots/s.sh && eval 'sleep 5' < /dev/null"
    proc = fake_proc(tmp_path, {10: (wrapper, 40000), 11: ("vim notes", 1)}, uptime=1000.0)
    (found,) = shellwatch.shells_of(1, {10: 1, 11: 1}, proc)
    assert (found.pid, found.start, found.seconds) == (10, "40000", 600.0)
    assert found.command == "sleep 5"  # the command inside the wrapper, not the wrapper


def test_a_shell_whose_start_cannot_be_read_has_run_for_no_time(tmp_path):
    assert shellwatch.running_seconds(99, tmp_path) == 0.0


def test_a_pattern_that_is_not_a_regex_is_never_stuck():
    assert shellwatch.verdict(shell('while pgrep -f "(["; do sleep 1; done'), "idle", PARENTS, {}) is None


def test_a_valued_pgrep_option_does_not_read_as_the_pattern():
    assert shellwatch.patterns("pgrep -u me -f 'job x'") == ["job x"]
    assert shellwatch.patterns("pgrep --pidfile p --full 'job y'") == ["job y"]
    assert shellwatch.patterns("pgrep 'unclosed") == []


def test_the_seen_file_round_trips_and_a_broken_one_reads_as_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(shellwatch.helpers, "STATE_DIR", tmp_path)
    shellwatch.write_seen("sb", {"10:500": {"agent": "a", "text": "t"}, "bad": "x"})  # type: ignore[dict-item]
    assert shellwatch.read_seen("sb") == {"10:500": {"agent": "a", "text": "t"}}
    shellwatch.seen_path("sb").write_text("[]")
    assert shellwatch.read_seen("sb") == {}
