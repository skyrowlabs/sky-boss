"""The launcher `sb deck` opens with no profile: its rows, its keys, and its edits to deck.toml."""

from __future__ import annotations

import tomllib

import pytest

from skyboss import decklaunch as dl

pytestmark = pytest.mark.unit

FOLDERS = [("ws", "/src/ws", True), ("boss", "/src/boss", True), ("new", "/src/new", False)]
SESSIONS = [
    dl.SessionLine("sb-core-2", "core 2", "core", tabs=4, live=True, holds="3 todos, 1 decision"),
    dl.SessionLine("sb-3", "ad hoc 3", tabs=1, age="12d ago"),
]
PROFILES = [dl.ProfileLine("core", ("ws", "boss"), "ws", 2), dl.ProfileLine("solo", ("boss",), "boss", 0)]


def launch(**kwargs):
    running = kwargs.pop("running", False)
    rows = dl.rows_of(SESSIONS, PROFILES, FOLDERS, running)
    return dl.Launch(rows, running=running, **kwargs)


def kinds(state):
    return [row.kind for row in state.rows]


def test_rows_go_sessions_profiles_then_agents_each_ending_in_its_add_row():
    assert kinds(launch()) == [
        "session",
        "session",
        "profile",
        "profile",
        "new-profile",
        "folder",
        "folder",
        "folder",
        "add",
    ]
    assert kinds(launch(running=True))[5] == "save-deck"


def test_a_session_row_says_running_its_profile_tabs_and_what_it_holds():
    first, second = launch().rows[:2]
    assert first.text.startswith("● core 2") and first.text.endswith("core · 4 tabs · running · 3 todos, 1 decision")
    assert second.text.startswith("○ ad hoc 3") and second.text.endswith("1 tab · 12d ago")
    gone = dl.rows_of([dl.SessionLine("sb-x", "old 1", "old", gone=True, tabs=2, age="1d ago")], [], [])
    assert gone[0].text.startswith("○ old 1 (profile gone)") and " old ·" not in gone[0].text


def test_a_profile_row_stars_its_primary_and_counts_its_sessions():
    assert launch().rows[2].text.endswith("ws*, boss · 2 sessions")


def test_tab_and_shift_tab_jump_between_sections():
    state, _ = dl.step(launch(), "\t")
    assert state.at == 2
    state, _ = dl.step(state, "\t")
    assert state.rows[state.at].kind == "folder"
    state, _ = dl.step(state, "\t")
    assert state.at == 0
    state, _ = dl.step(state, "btab")
    assert state.rows[state.at].kind == "folder"


def test_the_hint_lists_only_the_keys_the_row_takes():
    assert dl.hint(launch()) == "enter attach  d delete  r rename  f fresh  tab section  q quit"
    assert dl.hint(launch(at=1)).startswith("enter resume")
    assert dl.hint(launch(at=2)).startswith("enter new session  e edit  d delete  r rename")
    assert dl.hint(launch(at=7)) == "space tick  enter start ad hoc  tab section  q quit"
    assert "d delete" in dl.hint(launch(at=5)) and "open tab" in dl.hint(launch(at=6, running=True))


def test_session_keys_ask_for_their_action_on_that_row():
    rows = launch().rows
    for key, action in (("\r", dl.OPEN), ("d", dl.DELETE), ("r", dl.RENAME), ("f", dl.FRESH)):
        assert dl.step(launch(at=1), key)[1] == dl.Outcome(action, rows[1])


def test_profile_keys_and_the_new_profile_row():
    rows = launch().rows
    for key, action in (("\r", dl.OPEN), ("e", dl.EDIT), ("d", dl.DELETE), ("r", dl.RENAME)):
        assert dl.step(launch(at=2), key)[1] == dl.Outcome(action, rows[2])
    assert dl.step(launch(at=4), "\r")[1] == dl.Outcome(dl.EDIT)
    assert dl.step(launch(at=2), "f")[1] is None


def test_enter_on_the_deck_you_are_in_says_so():
    rows = dl.rows_of([dl.SessionLine("sb", "core 1", "core", live=True, here=True)], [], [], running=True)
    state, outcome = dl.step(dl.Launch(rows, running=True), "\r")
    assert outcome is None and "you are in" in state.note and "here" in rows[0].text


def test_space_ticks_a_folder_and_enter_starts_the_ticked_in_screen_order():
    state, _ = dl.step(launch(at=6), " ")
    state, _ = dl.step(state, "up")
    state, _ = dl.step(state, " ")
    _, outcome = dl.step(state, "\r")
    assert outcome == dl.Outcome(dl.START, state.rows[5], ("ws", "boss"))


def test_enter_on_an_unticked_folder_starts_that_one():
    _, outcome = dl.step(launch(at=7), "\r")
    assert outcome is not None and outcome.names == ("new",)


def test_save_needs_a_tick_and_delete_needs_a_declared_folder():
    state, outcome = dl.step(launch(at=5), "s")
    assert outcome is None and "tick" in state.note
    state, outcome = dl.step(launch(at=7), "d")
    assert outcome is None and "declared" in state.note
    assert dl.step(launch(at=5), "d")[1] == dl.Outcome(dl.DELETE, launch().rows[5])


def test_a_click_ticks_a_folder_and_opens_anything_else():
    state, outcome = dl.step(launch(), None, clicked_row=5)
    assert outcome is None and state.ticked == {"ws"}
    assert dl.step(launch(), None, clicked_row=2)[1] == dl.Outcome(dl.OPEN, launch().rows[2])


def test_the_screen_heads_each_section_with_its_keys_and_marks_the_ticks():
    text = [line for line, _ in dl.screen(launch(ticked={"ws"}), 120)]
    assert any(line.startswith("Sessions") and "f fresh" in line for line in text)
    assert any(line.startswith("Profiles") and "e edit" in line for line in text)
    assert any(line.startswith("Agents") and "s save as profile" in line for line in text)
    assert any(line.startswith("   [x] ws") for line in text)


def test_no_sessions_yet_is_said_rather_than_drawn_as_nothing():
    text = [line for line, _ in dl.screen(dl.Launch(dl.rows_of([], PROFILES, FOLDERS)), 120)]
    assert any("none yet" in line for line in text)


# ============================================================================
# The profile editor
# ============================================================================


def editor():
    return dl.editor_of("core", ["ws", "boss", "jam"], {"primary": "boss", "tabs": ["ws"], "brief": "hi"})


def test_the_editor_lists_the_profiles_agents_first_primary_leading():
    state = editor()
    assert state.rows == ["boss", "ws", "jam"] and state.ticked == {"boss", "ws"} and state.primary == "boss"
    assert dl.editor_body(state) == {"primary": "boss", "tabs": ["ws"], "brief": "hi", "brief_file": ""}


def test_the_editor_ticks_makes_primary_and_moves_rows():
    state, _ = dl.editor_step(editor(), "down")
    state, _ = dl.editor_step(state, "down")
    state, _ = dl.editor_step(state, "p")
    assert state.primary == "jam" and "jam" in state.ticked
    state, _ = dl.editor_step(state, "[")
    assert state.rows == ["boss", "jam", "ws"] and state.at == 1
    state, _ = dl.editor_step(state, "down")
    state, _ = dl.editor_step(state, " ")
    assert dl.editor_body(state)["tabs"] == ["boss"]


def test_unticking_the_primary_passes_the_lead_to_the_first_ticked():
    state, _ = dl.editor_step(editor(), " ")
    assert state.primary == "ws" and dl.editor_body(state) == {
        "primary": "ws",
        "tabs": [],
        "brief": "hi",
        "brief_file": "",
    }


def test_the_editor_writes_on_enter_only_with_a_tick_and_asks_for_the_brief():
    empty = dl.editor_of("", ["ws"])
    state, outcome = dl.editor_step(empty, "\r")
    assert outcome is None and "tick" in state.note
    assert dl.editor_step(editor(), "\r")[1] == dl.SAVE
    assert dl.editor_step(editor(), "b")[1] == "brief" and dl.editor_step(editor(), "B")[1] == "brief_file"
    assert dl.editor_step(editor(), "q")[1] == dl.QUIT
    text = [line for line, _ in dl.editor_screen(editor(), 80)]
    assert text[0] == "Profile core" and "brief: hi" in text and any("boss  primary" in line for line in text)


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


def test_git_roots_goes_above_the_first_table_and_keeps_its_comment():
    text = 'session = "sb"\n\n# the workspace\n[agent.a]\ncwd = "/a"\n'
    new = dl.edited(text, git_roots=["~/src"])
    assert new == 'session = "sb"\ngit_roots = ["~/src"]\n\n# the workspace\n[agent.a]\ncwd = "/a"\n'


def test_git_roots_replaces_a_list_that_spans_lines():
    new = dl.edited('git_roots = [\n  "/src/a",\n  "/src/b",\n]\nsession = "sb"\n', git_roots=["/src/c"])
    assert tomllib.loads(new) == {"git_roots": ["/src/c"], "session": "sb"}


def test_a_profile_rename_moves_its_header_and_keeps_its_comment_and_keys():
    new = dl.edited(DECK, rename_profile=("core", "main"))
    assert "# operator prose about the core profile\n[profile.main]\nprimary" in new
    assert tomllib.loads(new)["profile"]["main"] == {"primary": "ws", "tabs": ["boss"]}
    with pytest.raises(ValueError, match="already"):
        dl.edited(DECK, rename_profile=("core", "solo"))


def test_a_long_list_keeps_the_cursor_and_the_footer_on_screen():
    rows = dl.rows_of([], [], [(f"f{n}", f"/f{n}", False) for n in range(40)])
    state = dl.Launch(rows, at=25, note="said")
    lines = dl.screen(state, 80)
    drawn = dl.visible(lines, state, 12)
    assert len(drawn) == 12 and any(lines[n][1] == 25 for n in drawn) and lines[drawn[-1]][0] == "said"
