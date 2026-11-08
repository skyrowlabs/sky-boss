"""The launcher `sb deck` opens with no profile: its rows, its keys, and its edits to deck.toml."""

from __future__ import annotations

import tomllib

import pytest

from skyboss import decklaunch as dl

pytestmark = pytest.mark.unit

FOLDERS = [("ws", "/src/ws", True), ("boss", "/src/boss", True), ("new", "/src/new", False)]


def launch(**kwargs):
    running = kwargs.pop("running", False)
    saved = [] if running else [("sb", "core", 3)]
    rows = dl.rows_of([], saved, {"core": 3, "solo": 1}, FOLDERS, running)
    return dl.Launch(rows, running=running, **kwargs)


def test_the_last_deck_is_the_first_row_and_not_offered_while_one_runs():
    assert launch().rows[0] == dl.Row(dl.RESUME, "sb", "resume core (sb), 3 tabs")
    assert launch(running=True).rows[-1].kind == dl.SAVE_DECK


def test_rows_go_resume_profiles_folders_then_add():
    assert [row.kind for row in launch().rows] == ["resume", "profile", "profile", "folder", "folder", "folder", "add"]


def test_space_ticks_a_folder_and_enter_starts_the_ticked_in_screen_order():
    state, _ = dl.step(launch(at=4), " ")
    state, _ = dl.step(state, "up")
    state, _ = dl.step(state, " ")
    _, outcome = dl.step(state, "\r")
    assert outcome == dl.Outcome(dl.START, state.rows[3], ("ws", "boss"))


def test_enter_on_an_unticked_folder_starts_that_one():
    _, outcome = dl.step(launch(at=5), "\r")
    assert outcome is not None and outcome.names == ("new",)


def test_enter_opens_a_profile_or_the_last_deck():
    assert dl.step(launch(at=0), "\r")[1] == dl.Outcome(dl.OPEN, launch().rows[0])
    assert dl.step(launch(at=1), "\r")[1] == dl.Outcome(dl.OPEN, launch().rows[1])


def test_running_decks_come_first_and_a_profile_opens_beside_this_one():
    rows = dl.rows_of([("sb-core", "core", 2)], [("sb", "", 1)], {"core": 2}, [], running=True)
    assert [(r.kind, r.text) for r in rows[:2]] == [
        ("attach", "attach core (sb-core), 2 tabs"),
        ("resume", "resume sb, 1 tab"),
    ]
    state = dl.Launch(rows, running=True, at=2)
    assert dl.step(state, "\r")[1] == dl.Outcome(dl.OPEN, rows[2])


def test_save_needs_a_tick_and_delete_needs_a_declared_row():
    state, outcome = dl.step(launch(), "s")
    assert outcome is None and "tick" in state.note
    state, outcome = dl.step(launch(at=5), "d")
    assert outcome is None and "declared" in state.note
    assert dl.step(launch(at=1), "d")[1] == dl.Outcome(dl.DELETE, launch().rows[1])


def test_a_click_ticks_a_folder_and_opens_anything_else():
    state, outcome = dl.step(launch(), None, clicked_row=3)
    assert outcome is None and state.ticked == {"ws"}
    assert dl.step(launch(), None, clicked_row=1)[1] == dl.Outcome(dl.OPEN, launch().rows[1])


def test_the_screen_heads_each_section_and_marks_the_ticks():
    text = [line for line, _ in dl.screen(launch(ticked={"ws"}), 80)]
    assert "Profiles" in text and "Agent folders" in text
    assert any(line.startswith("   [x] ws") for line in text)


DECK = """# operator prose about the core profile
[profile.core]
primary = "ws"
tabs = ["boss"]

# why solo exists
[profile.solo]
primary = "boss"

[agent.ws]
cwd = "/src/ws"

[agent.loose]
cwd = "/src/loose"
"""


def test_deleting_a_profile_takes_its_comment_and_keeps_the_next_blocks():
    new = dl.edited(DECK, drop_profile="core")
    assert "core" not in new and new.startswith("# why solo exists\n[profile.solo]")
    assert set(tomllib.loads(new)["profile"]) == {"solo"}


def test_an_agent_a_profile_lists_is_not_deleted():
    with pytest.raises(ValueError, match="core"):
        dl.edited(DECK, drop_agent="ws")
    assert set(tomllib.loads(dl.edited(DECK, drop_agent="loose"))["agent"]) == {"ws"}


def test_a_saved_profile_puts_the_first_name_primary():
    new = dl.edited(DECK, add_profile=("pair", dl.body_of(("boss", "ws"), ("/tmp",))))
    assert tomllib.loads(new)["profile"]["pair"] == {"primary": "boss", "tabs": ["ws"], "terminals": ["/tmp"]}
    with pytest.raises(ValueError, match="already"):
        dl.edited(DECK, add_profile=("core", dl.body_of(("ws",))))


def test_replacing_a_profile_keeps_its_comment_and_its_other_keys():
    text = DECK.replace('tabs = ["boss"]', 'tabs = ["boss"]\nbrief_file = "core.md"')
    new = dl.edited(text, set_profile=("core", {"primary": "boss", "tabs": ["ws"], "brief_file": "core.md"}))
    assert new.startswith("# operator prose about the core profile\n[profile.core]")
    assert tomllib.loads(new)["profile"]["core"] == {"primary": "boss", "tabs": ["ws"], "brief_file": "core.md"}
