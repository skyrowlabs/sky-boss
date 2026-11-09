"""The `+`'s start list and its edit to `deck.toml`. See [[command-deck]] round 16."""

from __future__ import annotations

import re
import tomllib

import pytest

from skyboss import deck as deck_
from skyboss import deckplus, decksave, tools

pytestmark = [pytest.mark.unit]

DECK = """# the operator's own words
[agent.ws]
cwd = "~/src/ws"  # kept

[profile.core]
primary = "ws"
tabs    = ["a", "b",
           "c"]
brief   = \"\"\"
Keep this.\"\"\"

[profile.bare]
primary = "ws"
"""


def test_a_tab_joins_a_profile_whose_list_spans_lines_and_nothing_else_moves():
    new = deckplus.with_tab(DECK, "core", "d")
    assert tomllib.loads(new)["profile"]["core"]["tabs"] == ["a", "b", "c", "d"]
    assert new.replace(', "d"', "") == DECK


@pytest.mark.parametrize(
    "tabs, want",
    [("tabs = []", ["x"]), ('tabs = ["a",]', ["a", "x"]), ('tabs = [\n  "a",\n]', ["a", "x"])],
)
def test_every_shape_of_tabs_list_takes_a_name(tabs, want):
    text = f"[profile.p]\n{tabs}\n"
    assert tomllib.loads(deckplus.with_tab(text, "p", "x"))["profile"]["p"]["tabs"] == want


def test_a_profile_with_no_tabs_key_gets_one():
    assert tomllib.loads(deckplus.with_tab(DECK, "bare", "x"))["profile"]["bare"]["tabs"] == ["x"]


def test_the_edit_declares_the_agent_and_keeps_every_comment():
    new = deckplus.edited(DECK, "new", "/src/new", 'a "quoted" role', "core")
    parsed = tomllib.loads(new)
    assert parsed["agent"]["new"] == {"cwd": "/src/new", "role": 'a "quoted" role'}
    assert "# the operator's own words" in new and "# kept" in new


def test_a_list_that_ends_on_a_comment_is_refused_rather_than_guessed_at():
    text = '[profile.p]\ntabs = [\n  "a", # first\n]\n'
    with pytest.raises(ValueError, match="deck.toml"):
        deckplus.edited(text, "x", "", "", "p")


def test_an_absent_profile_is_refused():
    with pytest.raises(ValueError, match="no \\[profile.nope\\]"):
        deckplus.edited(DECK, "x", "", "", "nope")


def test_a_write_backs_up_first_and_keeps_the_old_bytes(tmp_path):
    path = tmp_path / "deck.toml"
    path.write_text(DECK)
    kept = deckplus.write(path, "session = 'x'\n")
    assert kept is not None and kept.parent.name == "backups" and kept.read_text() == DECK
    assert path.read_text() == "session = 'x'\n"


def test_tools_backups_keep_their_own_names(tmp_path):
    (tmp_path / "tools.toml").write_text("[tool.x]\n")
    kept = tools.backup(tmp_path, stamp="1")
    assert kept is not None and kept.name == "tools.1.toml"


def test_the_list_is_declared_first_then_each_new_folder(tmp_path):
    for name in ("mine", "new", ".hidden", "no good"):
        (tmp_path / name).mkdir()
    (tmp_path / "a-file").write_text("")
    found = deckplus.places([("agent", str(tmp_path / "mine"), "deck.toml")], [str(tmp_path)], re.compile(r"^\w+$"))
    assert [(p.name, p.declared, bool(p.problem)) for p in found] == [
        ("agent", True, False),
        ("new", False, False),
        ("no-good", False, True),
    ]


def test_a_folder_whose_name_is_taken_says_so(tmp_path):
    (tmp_path / "jam").mkdir()
    found = deckplus.places([("jam", "/elsewhere", "deck.toml")], [str(tmp_path)], re.compile(r".+"))
    assert "taken" in found[1].problem


def test_a_root_that_is_missing_offers_nothing_and_does_not_raise(tmp_path):
    assert deckplus.places([], [str(tmp_path / "gone")], re.compile(r".+")) == []


def test_the_prompt_scrolls_to_keep_the_cursor_on_screen():
    assert deckplus.window(50, 0, 10) == 0
    assert deckplus.window(50, 25, 10) == 20
    assert deckplus.window(50, 49, 10) == 40
    assert deckplus.window(3, 2, 10) == 0


def test_roots_and_terminals_are_read_and_a_bad_roots_is_named():
    config, problems = deck_.parse({"roots": ["~/src"], "profile": {"p": {"primary": "a", "terminals": ["~/src"]}}})
    assert config.roots == ["~/src"] and config.profiles["p"].terminals == ["~/src"] and not problems
    assert any("roots" in p for p in deck_.parse({"roots": "~/src"})[1])


def test_a_save_holds_terminals_and_an_older_save_has_none():
    decksave.save("sb", decksave.Saved(terminals=[decksave.Terminal("term", "/src")]))
    assert decksave.load("sb")[0].terminals == [decksave.Terminal("term", "/src")]
    path = decksave.path_for("sb")
    path.write_text('{"tabs": []}')
    assert decksave.load("sb") == (decksave.Saved(), [])


def test_a_this_deck_only_tab_comes_back_from_its_save():
    decksave.save("sb", decksave.Saved(tabs=[decksave.Tab("one-off", "id", "/src/x")], profile="p"))
    config = deck_.Config()
    profile = deck_.restored(config, [])
    assert profile is not None and profile.tabs == ["one-off"] and config.agents["one-off"].cwd == "/src/x"


def test_terminal_names_count_up_past_what_is_taken():
    def pane(name: str) -> deck_.Pane:
        return deck_.Pane("@1", 0, name, "", "%1", 1, "")

    assert deck_.terminal_name([]) == "term"
    assert deck_.terminal_name([pane("term"), pane("term-2")]) == "term-3"


def test_a_dotted_folder_is_offered_under_a_dashed_name_that_deck_toml_can_hold(tmp_path):
    from skyboss import deck as deck_

    (tmp_path / "skyrowlabs.com").mkdir()
    place = deckplus.places([], [str(tmp_path)], deck_.NAME)[0]
    assert (place.name, place.problem) == ("skyrowlabs-com", "")
    text = deckplus.edited("[profile.p]\ntabs = []\n", place.name, place.cwd, "", "p")
    assert "[agent.skyrowlabs-com]" in text


def test_a_dotted_tab_name_is_refused_with_the_reason():
    from skyboss import deck as deck_

    assert not deck_.NAME.match("skyrowlabs.com") and "dot" in deck_.NAME_RULE


def test_browse_offers_this_folder_then_up_then_visible_subfolders(tmp_path):
    (tmp_path / "b").mkdir()
    (tmp_path / "a").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file").write_text("")
    rows, targets = deckplus.browse(str(tmp_path))
    assert rows[2:] == ["..", "a/", "b/"]
    assert targets == [str(tmp_path), str(tmp_path), str(tmp_path.parent), str(tmp_path / "a"), str(tmp_path / "b")]


def test_browse_at_the_root_has_no_way_up():
    assert ".." not in deckplus.browse("/")[0]


def test_browse_offers_to_stop_a_scan_already_set(tmp_path):
    assert "stop" in deckplus.browse(str(tmp_path), scanned=True)[0][1]
    assert "list every" in deckplus.browse(str(tmp_path))[0][1]


def make_repo(path, marker="dir"):
    path.mkdir(parents=True)
    (path / ".git").mkdir() if marker == "dir" else (path / ".git").write_text("gitdir: x")


def test_git_projects_finds_nested_checkouts_and_worktrees_only(tmp_path):
    make_repo(tmp_path / "a")
    make_repo(tmp_path / "group" / "b", marker="file")
    (tmp_path / "plain").mkdir()
    assert deckplus.git_projects(str(tmp_path)) == [tmp_path / "a", tmp_path / "group" / "b"]


def test_git_projects_stops_at_a_checkout_at_the_depth_and_at_node_modules(tmp_path):
    make_repo(tmp_path / "outer" / "sub" / "x")
    make_repo(tmp_path / "outer" / "sub" / "x" / "nested")
    make_repo(tmp_path / "node_modules" / "dep")
    assert deckplus.git_projects(str(tmp_path)) == [tmp_path / "outer" / "sub" / "x"]
    assert deckplus.git_projects(str(tmp_path), depth=1) == []


def test_a_git_root_lists_new_projects_and_names_a_clash(tmp_path):
    make_repo(tmp_path / "one" / "app")
    make_repo(tmp_path / "two" / "app")
    found = deckplus.places([], [], deck_.NAME, [str(tmp_path)])
    assert [(p.name, p.source, bool(p.problem)) for p in found] == [
        ("app", "git_roots", False),
        ("app", "git_roots", True),
    ]


def test_git_roots_is_read_and_a_bad_one_is_named():
    assert deck_.parse({"git_roots": ["~/src"]})[0].git_roots == ["~/src"]
    assert any("git_roots" in p for p in deck_.parse({"git_roots": "~/src"})[1])
