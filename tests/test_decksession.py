"""Deck sessions: their records, the migration from tmux names, and `sb deck session`. See [[command-deck]] round 25."""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

import pytest

from skyboss import deck as deck_
from skyboss import decksave, decksession, deckwatch
from skyboss import todos as todos_
from tests.test_deck import FakeTmux, invoke

pytestmark = [pytest.mark.unit]


@pytest.fixture
def fake(monkeypatch, tmp_path):
    server = FakeTmux()
    monkeypatch.setattr(deck_, "RUNNER", server)
    monkeypatch.setattr(deck_.decksave.helpers, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(deck_.agents_, "providers", lambda: [])
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    return server


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An isolated `$SB_HOME` with a `deck.toml` writer."""
    monkeypatch.setattr(deck_, "SB_HOME", tmp_path)
    monkeypatch.setattr("skyboss.rollcall.SB_HOME", tmp_path)

    def write(text: str) -> Path:
        (tmp_path / "deck.toml").write_text(text)
        return tmp_path

    return write


def record(name: str) -> decksession.Record:
    found = decksession.load(name)
    assert found is not None, f"no record for {name}"
    return found


def saved(name, *agents, profile=""):
    decksave.save(name, decksave.Saved([decksave.Tab(a, f"id-{a}", "/src") for a in agents], profile=profile))


def test_the_migration_records_every_old_deck_under_its_tmux_name(fake, home, tmp_path):
    home('[profile.skyrow-workspace]\nsession = "sb"\ntabs = ["ws"]\n[profile.sky-boss]\ntabs = ["boss"]\n')
    saved("sb", "ws")  # written before round 24, so the save names no profile
    saved("sb-2", "jam")
    saved("sb-3", "jam")
    saved("sb-sky-boss", "boss", profile="sky-boss")
    todos_.add("sb-skyrow-core", "ws", "a todo left behind")
    os.utime(decksave.path_for("sb-2"), (1000, 1000))
    written = deck_.migrated(deck_.load()[0])
    labels = {r.name: (r.profile, r.label) for r in written}
    assert labels == {
        "sb": ("skyrow-workspace", "skyrow-workspace 1"),
        "sb-2": ("", "ad hoc 2"),
        "sb-3": ("", "ad hoc 3"),
        "sb-sky-boss": ("sky-boss", "sky-boss 1"),
        "sb-skyrow-core": ("", "ad hoc 1"),
    }
    assert record("sb-2").created == 1000
    assert deck_.migrated(deck_.load()[0]) == []
    assert 'session = "sb"' in (tmp_path / "deck.toml").read_text()


def test_a_listing_reads_an_unmigrated_session_without_writing_it(fake, home):
    saved("sb-2", "jam")
    data = json.loads(invoke("--json", "deck", "session", "list").output)["data"]
    assert [(row["session"], row["label"], row["tabs"]) for row in data] == [("sb-2", "ad hoc 2", 1)]
    assert decksession.load("sb-2") is None


def test_a_listing_puts_running_first_and_names_a_deleted_profile(fake, home):
    home('[profile.core]\ntabs = ["ws"]\n')
    decksession.create("sb-core-1", "core", "core 1", now=100)
    decksession.create("sb-gone-1", "gone", "gone 1", now=300)
    decksession.create("sb-1", "", "ad hoc 1", now=200)
    fake.session("sb-core-1")
    fake.session("sb-core-1-agents")
    todos_.add("sb-1", "ws", "open")
    data = json.loads(invoke("--json", "deck", "session", "list").output)["data"]
    assert [row["session"] for row in data] == ["sb-core-1", "sb-gone-1", "sb-1"]
    assert data[0]["running"] and data[1]["profile_gone"] and data[2]["holds"] == "1 todo"


def test_a_session_rename_sets_its_label_and_keeps_its_tmux_name(fake, home):
    decksession.create("sb-1", "", "ad hoc 1")
    assert invoke("deck", "session", "rename", "sb-1", "release  week").exit_code == 0
    assert record("sb-1").label == "release week"
    assert invoke("deck", "session", "rename", "nope", "x").exit_code == 2


def test_a_session_delete_takes_its_directory_and_says_what_went(fake, home):
    saved("sb-1", "ws", "jam")
    todos_.add("sb-1", "ws", "one")
    todos_.add("sb-1", "ws", "two", book=todos_.DECISIONS)
    result = invoke("--json", "deck", "session", "delete", "sb-1", "--yes")
    said = json.loads(result.output)["data"]["deleted"]
    assert "2 tab resume links, 1 todo, 1 decision, 0 asks, 0 chosen watchers" in said
    assert not (decksession.root() / "sb-1").exists()


def test_a_delete_asks_first_off_a_terminal_it_needs_yes(fake, home):
    saved("sb-1", "ws")
    assert invoke("deck", "session", "delete", "sb-1").exit_code == 2
    assert (decksession.root() / "sb-1").exists()


def test_a_running_session_is_never_deleted_and_the_way_out_is_named(fake, home, said):
    saved("sb-1", "ws")
    fake.session("sb-1-agents")
    result = invoke("deck", "session", "delete", "sb-1", "--yes")
    assert result.exit_code == 1 and "`sb deck exit` there first" in said(result)
    assert (decksession.root() / "sb-1").exists()


def test_a_profile_rename_moves_its_sessions_by_their_record(fake, home, tmp_path):
    path = home('[profile.core]\nprimary = "ws"\n[agent.ws]\ncwd = "/src"\n') / "deck.toml"
    decksession.create("sb-core-1", "core", "core 1")
    fake.session("sb-core-1")
    fake.session("sb-core-1-agents")
    result = invoke("--json", "deck", "profile", "rename", "core", "main")
    assert result.exit_code == 0, result.output
    assert "main" in tomllib.loads(path.read_text())["profile"]
    assert record("sb-core-1").profile == "main"
    assert fake.options[("=sb-core-1-agents:", "@sb-profile")] == "main"


def test_a_resumed_session_takes_its_profile_from_the_record(fake, home, tmp_path):
    home(f'[profile.main]\nprimary = "ws"\nbrief = "hello"\n[agent.ws]\ncwd = "{tmp_path}"\n')
    saved("sb-core-1", "ws", profile="core")
    decksession.create("sb-core-1", "main", "core 1")
    config = deck_.load()[0]
    config.session = "sb-core-1"
    back = deck_.restored(config, [])
    assert back is not None and back.name == "main" and back.brief == "hello"


def test_profile_new_edit_and_show(fake, home, tmp_path, said):
    path = home(f'[agent.ws]\ncwd = "{tmp_path}"\n[agent.jam]\ncwd = "{tmp_path}"\n') / "deck.toml"
    assert invoke("deck", "profile", "new", "core", "--primary", "ws", "--tab", "jam").exit_code == 0
    assert tomllib.loads(path.read_text())["profile"]["core"] == {"primary": "ws", "tabs": ["jam"]}
    unknown = invoke("deck", "profile", "new", "two", "--primary", "ghost")
    assert unknown.exit_code == 2 and "no agent 'ghost'" in said(unknown)
    path.write_text(path.read_text() + 'columns = [["todos"]]\n')
    assert invoke("deck", "profile", "edit", "core", "--remove", "ws", "--brief", "be brief").exit_code == 0
    assert tomllib.loads(path.read_text())["profile"]["core"] == {
        "primary": "jam",
        "brief": "be brief",
        "columns": [["todos"]],
    }
    shown = json.loads(invoke("--json", "deck", "profile", "show", "core").output)["data"]
    assert shown["primary"] == "jam" and shown["brief"] == "be brief" and shown["sessions"] == []
    emptied = invoke("deck", "profile", "edit", "core", "--remove", "jam")
    assert emptied.exit_code == 2 and "no agents" in said(emptied)


def test_todo_reads_a_stopped_session_named_by_flag_and_leaves_sb_deck_as_it_was(fake, home, monkeypatch):
    monkeypatch.setenv("SB_DECK", "sb")
    todos_.add("sb-core-1", "ws", "in the stopped one")
    result = invoke("--json", "deck", "todo", "--session", "sb-core-1", "list", "--all")
    assert result.exit_code == 0, result.output
    assert "in the stopped one" in result.output
    assert os.environ["SB_DECK"] == "sb"
    assert invoke("deck", "todo", "--session", "nope", "list").exit_code == 2


def test_a_stopped_session_with_nothing_saved_reopens_its_profiles_agents(fake, home, tmp_path):
    home(f'[profile.core]\nprimary = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\n')
    decksession.create("sb-core-1", "core", "core 1")
    config = deck_.load()[0]
    config.session = "sb-core-1"
    profile, _ = deck_.resumed_deck(config, [], None, [])
    assert profile is not None and profile.name == "core"


def test_a_profile_chosen_while_its_session_runs_starts_a_second_session(fake, home, tmp_path):
    home(f'[profile.core]\nprimary = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\n')
    decksession.create("sb-core-1", "core", "core 1")
    fake.session("sb-core-1")
    fake.session("sb-core-1-agents")
    config = deck_.load()[0]
    profile, _, fresh = deck_.chosen_deck(config, ("profile", ("core",)), [])
    assert profile is not None and profile.name == "core" and not fresh
    assert config.session == "sb-core-2" and record("sb-core-2").label == "core 2"


def test_two_sessions_of_one_profile_share_no_todos_decisions_or_watchers(fake, home):
    decksession.create("sb-core-1", "core", "core 1")
    decksession.create("sb-core-2", "core", "core 2")
    todos_.add("sb-core-1", "ws", "only in one")
    todos_.add("sb-core-1", "ws", "ruled in one", book=todos_.DECISIONS)
    deckwatch.save("sb-core-1", {"s1:b7": deckwatch.Watcher("s1:b7", "ws", "shell", "tail -f log", 60.0).record()})
    one, two = decksession.holds("sb-core-1"), decksession.holds("sb-core-2")
    assert (one.todos, one.decisions, one.watchers) == (1, 1, 1)
    assert (two.todos, two.decisions, two.watchers) == (0, 0, 0)
    listed = invoke("--json", "deck", "todo", "--session", "sb-core-2", "list", "--all")
    assert listed.exit_code == 0 and "only in one" not in listed.output
    deck_.delete_session("sb-core-2")
    assert decksession.holds("sb-core-1").todos == 1


def test_sb_deck_warns_that_a_profiles_session_key_is_unused(fake, home, tmp_path, said):
    path = home(f'[profile.core]\nsession = "old"\nprimary = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\n') / "deck.toml"
    result = invoke("deck", "--profile", "core")
    assert "`session = 'old'` is no longer used" in said(result)
    assert 'session = "old"' in path.read_text()
