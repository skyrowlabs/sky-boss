"""The WATCHERS pane: what deck agents leave running, chosen in a tick list. See [[command-deck]] round 23."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from skyboss import deck as deck_
from skyboss import deckwatch
from skyboss.agents import Scan, Session
from tests.test_deck import FakeTmux, invoke

pytestmark = pytest.mark.unit

NOW = 1_000_000.0
WRAPPER = (
    "/usr/bin/bash\0-c\0source /home/x/.claude/shell-snapshots/snapshot.sh 2>/dev/null || true && "
    "eval 'while true; do date; sleep 5; done' && pwd -P >| /tmp/cwd\0"
)


@pytest.fixture
def sb_state(tmp_path, monkeypatch):
    """A state directory of this test's own: the shared one carries one test's choice into the next."""
    from skyboss import helpers

    monkeypatch.setattr(helpers, "STATE_DIR", tmp_path / "state")
    return tmp_path / "state"


def watcher(key="s:b1", owner="ws", kind="shell", command="tail -f log", seconds=60.0, **more):
    return deckwatch.Watcher(key, owner, kind, command, seconds, **more)


def stat_at(mtime):
    return lambda path: SimpleNamespace(st_mtime=mtime)


def gone(path):
    raise FileNotFoundError(path)


def texts(rows):
    return [row["watchers"] for row in rows]


# ============================================================================
# Sources
# ============================================================================


def fake_proc(tmp_path, children):
    """A /proc with `uptime`, the tab's claude at pid 10, and each `(pid, fd 1 target)` under it."""
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "uptime").write_text("100.0 1.0\n")
    for pid, parent, cmdline in [(10, 1, "claude\0"), *((pid, 10, WRAPPER) for pid, _ in children)]:
        folder = proc / str(pid)
        folder.mkdir()
        (folder / "cmdline").write_bytes(cmdline.encode())
        (folder / "stat").write_text(f"{pid} (bash) S {parent} " + " ".join(["0"] * 17) + " 0\n")
    for pid, target in children:
        (proc / str(pid) / "fd").mkdir()
        (proc / str(pid) / "fd" / "1").symlink_to(target)
    return proc


def test_a_tab_lists_its_shell_by_task_and_its_monitor_by_pid(tmp_path):
    proc = fake_proc(tmp_path, [(11, "/tmp/claude-1/-src/s1/tasks/b7.output"), (12, "socket:[4]")])
    found = deckwatch.tab_watchers("ws", "s1", "/src", 10, deck_.parents(proc), proc, tmp_path, NOW)
    assert [(w.key, w.kind, w.command) for w in found] == [
        ("s1:b7", "shell", "while true; do date; sleep 5; done"),
        ("s1:monitor:12:0", "monitor", "while true; do date; sleep 5; done"),
    ]
    assert found[0].path.endswith("tasks/b7.output") and found[1].path == ""


def write_job(root, ident, **state):
    folder = root / ident
    folder.mkdir(parents=True)
    (folder / "state.json").write_text(json.dumps(state))
    return folder


def test_a_daemon_job_is_labelled_by_its_cwd_state_and_detail_and_pins_is_not_one(tmp_path):
    write_job(
        tmp_path,
        "a1",
        state="working",
        detail="Checking CI",
        cwd="/src/jam",
        name="JS",
        updatedAt="1970-01-12T13:46:30Z",
    )
    write_job(tmp_path, "b2", state="done", detail="merged", cwd="/src/sky", name="", updatedAt="1970-01-12T13:40:00Z")
    (tmp_path / "pins.json").write_text("{}")
    found, problems = deckwatch.daemon_jobs(tmp_path, NOW)
    assert not problems and [w.key for w in found] == ["job:a1", "job:b2"]
    assert found[0].owner == deckwatch.DAEMON and found[0].label() == "JS · /src/jam · working: Checking CI"
    assert not found[0].ended and found[1].ended and found[1].command == "b2 · /src/sky"


def test_no_jobs_folder_is_no_jobs_and_an_unreadable_state_is_still_listed(tmp_path):
    assert deckwatch.daemon_jobs(tmp_path / "absent", NOW) == ([], [])
    (tmp_path / "c3").mkdir()
    (tmp_path / "c3" / "state.json").write_text("{not json")
    (job,) = deckwatch.daemon_jobs(tmp_path, NOW)[0]
    assert job.key == "job:c3" and job.state.startswith("unreadable")


# ============================================================================
# Streams
# ============================================================================


def test_a_stream_line_keeps_what_was_drawn_last_and_drops_control_codes():
    assert deckwatch.clean("10%\r50%\r\x1b[32mdone\x1b[0m\t!") == "done  !"


def test_a_tail_is_the_last_lines_and_none_when_the_file_is_not_there(tmp_path):
    path = tmp_path / "b1.output"
    path.write_text("one\n\ntwo\nthree\nfour\nfive\n")
    assert deckwatch.tail(str(path)) == ["two", "three", "four", "five"]
    assert deckwatch.tail(str(tmp_path / "missing")) is None


def test_a_timeline_line_reads_as_its_time_state_and_detail():
    at = datetime.fromtimestamp(NOW, timezone.utc).isoformat()
    lines = deckwatch.timeline([json.dumps({"at": at, "state": "working", "detail": "Reading CI"}), "plain"])
    assert lines[0].endswith(" working · Reading CI") and lines[1] == "plain"


def test_a_stream_ends_running_quiet_ended_or_gone():
    live = watcher(path="/t/b1.output")
    assert deckwatch.ending(live, {}, NOW, stat_at(NOW - 2))[0] == "running"
    assert deckwatch.ending(live, {}, NOW, stat_at(NOW - 300)) == ("quiet", "untouched 5m")
    assert deckwatch.ending(None, {"path": "/t/b1.output"}, NOW, stat_at(NOW))[0] == "ended"
    assert deckwatch.ending(None, {"path": "/t/b1.output"}, NOW, gone)[0] == "gone"
    assert deckwatch.ending(watcher(kind="monitor"), {}, NOW) == ("", "")


# ============================================================================
# The pane's rows
# ============================================================================


def test_none_chosen_says_how_many_run_and_how_to_pick_never_nothing():
    rows = deckwatch.rows_of([watcher(), watcher("s:b2")], {}, 0, NOW, "M-g picks")
    assert texts(rows) == ["2 watchers running · M-g picks"]
    assert texts(deckwatch.rows_of([], {}, 0, NOW, "M-g picks")) == ["nothing running to watch · M-g picks"]


def test_a_chosen_shell_is_a_header_its_last_lines_and_its_end(tmp_path):
    path = tmp_path / "b1.output"
    path.write_text("tick 1\ntick 2\n")
    shell, other = watcher(path=str(path)), watcher("s:b2")
    rows = deckwatch.rows_of([shell, other], {shell.key: shell.record()}, 0, NOW, "M-g", stat=stat_at(NOW - 120))
    assert texts(rows) == [
        "ws · shell tail -f log · running 1m",
        "  tick 1",
        "  tick 2",
        "  · quiet · untouched 2m",
        "1 more running · M-g",
    ]
    assert rows[0]["kind"] == "head" and rows[-1]["kind"] == "note"
    assert {row["running"] for row in rows} == {2} and {row["chosen"] for row in rows} == {1}


def test_a_monitor_is_a_header_alone_and_an_ended_one_says_so():
    monitor = watcher("s:monitor:12:0", kind="monitor")
    chosen = {monitor.key: monitor.record()}
    assert texts(deckwatch.rows_of([monitor], chosen, 0, NOW, "")) == ["ws · monitor tail -f log · running 1m"]
    ended = deckwatch.rows_of([], chosen, 2, NOW, "")
    assert texts(ended) == [
        "ws · monitor tail -f log",
        "  · ended · no longer running",
        "2 ended and dropped since the last pick",
    ]


def test_a_chosen_job_streams_its_timeline(tmp_path):
    folder = write_job(tmp_path, "a1", state="working", detail="CI", cwd="/src", name="JS", updatedAt="")
    (folder / "timeline.jsonl").write_text(
        json.dumps({"at": "1970-01-12T13:46:40Z", "state": "working", "detail": "CI"}) + "\n"
    )
    (job,), _ = deckwatch.daemon_jobs(tmp_path, NOW)
    rows = deckwatch.rows_of([job], {job.key: job.record()}, 0, NOW, "", stat=stat_at(NOW))
    assert rows[0]["watchers"].startswith("daemon · job JS · /src · working: CI")
    assert rows[1]["watchers"].endswith("working · CI") and rows[2]["watchers"].startswith("  · running")


# ============================================================================
# watchers.json and the sweep
# ============================================================================


def test_a_choice_survives_a_reload_and_the_sweep_drops_and_counts_what_ended(sb_state):
    kept, ended = watcher("s:b1"), watcher("s:b2")
    deckwatch.save("sb", {kept.key: kept.record(), ended.key: ended.record()})
    assert set(deckwatch.load("sb")[0]) == {"s:b1", "s:b2"}
    assert deckwatch.sweep("sb", [kept]) == 1
    chosen, dropped, problems = deckwatch.load("sb")
    assert set(chosen) == {"s:b1"} and dropped == 1 and not problems
    assert deckwatch.path_for("sb").parent.name == "sb" and deckwatch.path_for("sb").with_name("column.json")


def test_a_job_that_finished_is_dropped_by_the_sweep(sb_state):
    job = watcher("job:a1", owner="daemon", kind="job", state="done", ended=True)
    deckwatch.save("sb", {job.key: job.record()})
    assert deckwatch.sweep("sb", [job]) == 1 and deckwatch.load("sb")[0] == {}


def test_an_unreadable_choice_is_a_problem_and_the_sweep_leaves_it_alone(sb_state):
    deckwatch.path_for("sb").parent.mkdir(parents=True)
    deckwatch.path_for("sb").write_text("{not json")
    assert deckwatch.load("sb")[2] and deckwatch.sweep("sb", []) == 0
    assert deckwatch.path_for("sb").read_text() == "{not json"


# ============================================================================
# The picker
# ============================================================================


def picker(*ticked):
    rows = [
        watcher("s:b1"),
        watcher("s:b2", kind="monitor"),
        watcher("job:a1", owner="daemon", kind="job", state="done"),
    ]
    return deckwatch.Pick(rows, ticked=set(ticked))


def test_the_picker_groups_by_tab_then_daemon_with_kind_command_and_age():
    lines = [text for text, _ in deckwatch.screen(picker("s:b1"), 120)]
    assert lines[2] == "ws" and lines[3] == " > [x] shell     1m  tail -f log"
    assert lines[4].startswith("   [ ] monitor") and lines[6] == "daemon" and "tail -f log · done" in lines[7]
    ended = deckwatch.Pick([watcher("job:a1", owner="daemon", kind="job", state="done", ended=True)])
    assert deckwatch.screen(ended, 120)[3][0] == " > [ ] job   1m  ended · tail -f log · done"


def test_the_picker_ticks_any_number_none_included():
    pick, outcome = deckwatch.step(picker(), " ")
    assert pick.ticked == {"s:b1"} and outcome is None
    pick, _ = deckwatch.step(pick, None, clicked_row=2)
    assert pick.ticked == {"s:b1", "job:a1"}
    assert deckwatch.step(pick, "a")[0].ticked == {"s:b1", "s:b2", "job:a1"}
    pick, _ = deckwatch.step(pick, "n")
    assert pick.ticked == set() and deckwatch.step(pick, "\r")[1] == deckwatch.SAVE
    assert deckwatch.step(pick, "q")[1] == deckwatch.QUIT


def test_an_empty_picker_says_nothing_runs_and_still_saves_none():
    pick = deckwatch.Pick([])
    assert ("  nothing is running to watch", None) in deckwatch.screen(pick, 80)
    assert deckwatch.step(pick, " ") == (pick, None) and deckwatch.step(pick, "\r")[1] == deckwatch.SAVE


def test_a_chosen_watcher_that_ended_keeps_its_record_until_unticked():
    was = {"s:old": {"owner": "ws", "kind": "shell", "command": "x", "path": ""}}
    pick = deckwatch.Pick([watcher("s:b1")], ticked={"s:old", "s:b1"})
    assert set(deckwatch.chosen_of(pick, was)) == {"s:b1", "s:old"}
    assert deckwatch.chosen_of(deckwatch.Pick([watcher()], ticked=set()), was) == {}


# ============================================================================
# The deck: the pane, its key and its title
# ============================================================================


class Adapter:
    provider = "claude"

    def __init__(self, sessions):
        self.sessions = sessions

    def scan(self):
        return Scan(provider="claude", sessions=list(self.sessions), present=True, read=len(self.sessions))


@pytest.fixture
def deck_tab(monkeypatch, tmp_path, sb_state):
    """A deck with one agent tab, `ws`, whose claude runs a background shell and a Monitor."""
    server = FakeTmux()
    monkeypatch.setattr(deck_, "RUNNER", server)
    monkeypatch.setattr(deck_, "SB_HOME", tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    output = tmp_path / "b7.output"
    output.write_text("built\n")
    task = tmp_path / "tmp" / "s1" / "tasks" / "b7.output"
    task.parent.mkdir(parents=True)
    os.symlink(output, task)
    proc = fake_proc(tmp_path, [(11, str(task)), (12, "socket:[4]")])
    session = Session(provider="claude", id="s1", name="ws", cwd="/src", status="idle", pid=10, started=None)
    monkeypatch.setattr(deck_.agents_, "providers", lambda: [Adapter([session])])
    server.session("sb")
    server.add("sb-agents", "ws", agent="ws", role="agent", pid=10)
    write_job(tmp_path / "claude" / "jobs", "a1", state="working", detail="CI", cwd="/src", name="JS", updatedAt="")
    return SimpleNamespace(server=server, proc=proc, task=str(task))


def test_the_deck_gathers_each_tabs_watchers_then_the_daemons(deck_tab):
    found, problems, sure = deck_.gather_watchers("sb", proc=deck_tab.proc)
    assert [(w.owner, w.kind, w.key) for w in found] == [
        ("ws", "shell", "s1:b7"),
        ("ws", "monitor", "s1:monitor:12:0"),
        ("daemon", "job", "job:a1"),
    ]
    assert sure and not problems and found[0].slot == 0


def test_watchers_list_all_names_each_key_and_choose_saves_exactly_those(deck_tab, monkeypatch):
    real = deck_.gather_watchers
    monkeypatch.setattr(deck_, "gather_watchers", lambda session: real(session, proc=deck_tab.proc))
    listed = json.loads(invoke("--json", "deck", "watchers", "list", "--all").stdout)["data"]
    assert [row["key"] for row in listed] == ["s1:b7", "s1:monitor:12:0", "job:a1"]
    assert invoke("deck", "watchers", "choose", "s1:b7").exit_code == 0
    assert set(deckwatch.load("sb")[0]) == {"s1:b7"}
    assert invoke("deck", "watchers", "choose", "ghost").exit_code == 2
    rows = json.loads(invoke("--json", "deck", "watchers", "list").stdout)["data"]
    assert rows[0]["watchers"].startswith("ws · shell") and rows[1]["watchers"] == "  built"
    assert invoke("deck", "watchers", "choose").exit_code == 0 and deckwatch.load("sb")[0] == {}


def test_the_watchers_pane_is_a_fifth_role_with_its_own_argv():
    assert deck_.WATCHERS in deck_.TOOL_ROLES and deck_.column_.LABELS[deck_.WATCHERS] == "WATCHERS"
    assert deck_.watchers_argv()[-5:] == ["watchers", "list", "--refresh", "5", "--screen"]


def test_its_key_opens_the_picker_and_is_no_claude_code_key():
    key = deck_.SHORTCUTS["watchers"]
    (bound,) = [argv for argv in deck_.deck_bindings("sb") if argv[3] == key]
    assert bound[4] == "display-popup" and bound[-1].endswith("deck watchers pick")
    assert key not in {f"M-{letter}" for letter in "bdfyoptvwjm"} and f"{key} watchers" in deck_.hints()


def test_a_click_on_its_title_opens_the_picker_and_in_the_grid_its_label_still_moves_it(monkeypatch):
    opened = []
    monkeypatch.setattr(deck_, "_open_popup", opened.append)
    monkeypatch.setattr(deck_.DeckPane, "poll", lambda self: None)
    pane = deck_.DeckPane("sb", lambda r: True, scroll=True, top=True, role=deck_.WATCHERS)
    pane.lines = ["", " WATCHERS ── M-g pick", " ─────", " 2 watchers running · M-g"]
    pane.rows = [{"kind": "note"}]
    monkeypatch.setattr(deck_, "layout_of", lambda session: deck_.COLUMNS)
    assert not pane.on_key("click:4:2") and len(opened) == 1
    assert not pane.on_key("click:4:4") and len(opened) == 2
    monkeypatch.setattr(deck_, "layout_of", lambda session: deck_.GRID)
    monkeypatch.setattr(deck_, "tmux", lambda *a: deck_.Answer(asked=True))
    assert pane.on_key("click:3:2") and pane.moving == deck_.WATCHERS and len(opened) == 2
    assert pane.lights(4) and not pane.lights(2)


def test_the_sweep_leaves_the_choice_alone_when_the_tabs_cannot_be_read(sb_state, monkeypatch):
    deckwatch.save("sb", {"s1:b7": watcher("s1:b7").record()})
    monkeypatch.setattr(deck_, "gather_watchers", lambda session: ([], ["could not list"], False))
    assert deck_.sweep_watchers("sb") == 0 and set(deckwatch.load("sb")[0]) == {"s1:b7"}


def test_a_detached_deck_is_laid_out_where_five_panes_fit(monkeypatch):
    monkeypatch.setattr(deck_.shutil, "get_terminal_size", lambda: os.terminal_size((80, 24)))
    assert deck_.detached_size() == ["-x", "160", "-y", "48"]
    monkeypatch.setattr(deck_.shutil, "get_terminal_size", lambda: os.terminal_size((220, 60)))
    assert deck_.detached_size() == ["-x", "220", "-y", "60"]
