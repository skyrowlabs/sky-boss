"""`sb deck`'s interactive and tab-making commands: add, terminal, plus, launch, the launcher, decide.

No test here runs tmux, reads a real key or prompts a real terminal. `FakeTmux`
stands in for the server, and every key the screens read is scripted.
"""

from __future__ import annotations

import contextlib
import json
import os
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

from skyboss import cli
from skyboss import deck as deck_
from skyboss import deckasks, decklaunch, decksave
from skyboss import todos as todos_
from skyboss.deck import Answer
from tests.test_deck import FakeTmux, caller_under, two_tabs, window_of

#: Host-side; nothing here needs a service or a tmux binary.
pytestmark = [pytest.mark.unit]


@pytest.fixture
def fake(monkeypatch, tmp_path):
    server = FakeTmux()
    monkeypatch.setattr(deck_, "RUNNER", server)
    monkeypatch.setattr(deck_.decksave.helpers, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(deck_.agents_, "providers", lambda: [])
    monkeypatch.delenv("TMUX", raising=False)
    (tmp_path / "claude").mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setattr(deck_.shutil, "which", lambda name, path=None: f"/usr/bin/{name}")
    monkeypatch.setattr(deck_.time, "sleep", lambda seconds: None)
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


def invoke(*args: str, input: str | None = None):
    return CliRunner().invoke(cli, list(args), input=input)


def declared(tmp_path: Path) -> dict:
    return tomllib.loads((tmp_path / "deck.toml").read_text())


def running(fake: FakeTmux, profile: str = "") -> None:
    """A deck `sb` already up, opened from `profile` when one is named."""
    fake.session("sb")
    fake.session("sb-agents")
    if profile:
        fake.options[("=sb-agents:", "@sb-profile")] = profile


def keys_from(*keys):
    """A `keys_.reader` that hands out `keys` in order, then None for ever."""
    queue = list(keys)

    @contextlib.contextmanager
    def reader(stream=None):
        yield lambda seconds: queue.pop(0) if queue else None

    return reader


class Picks:
    """A `_picked` answering each popup in turn, recording its title and rows."""

    def __init__(self, *answers):
        self.queue, self.asked = list(answers), []

    def __call__(self, title, rows):
        self.asked.append((title, list(rows)))
        return self.queue.pop(0)


@pytest.fixture
def screen(monkeypatch):
    """A fixed 80x24 terminal for the popups to draw into."""
    monkeypatch.setattr(deck_.shutil, "get_terminal_size", lambda *a: os.terminal_size((80, 24)))


# ============================================================================
# `sb deck add` — a new agent tab, kept in the profile or not
# ============================================================================


def test_add_refuses_a_name_tmux_cannot_hold(fake, home, said):
    result = invoke("deck", "add", "a.b", "--cwd", "/tmp")
    assert result.exit_code == 2 and "cannot be a tab's name" in said(result) and fake.calls == []


def test_add_needs_a_directory_for_a_name_nobody_declared(fake, home, said):
    result = invoke("deck", "add", "scratch")
    assert result.exit_code == 2 and "give it a directory with --cwd" in said(result)


def test_add_refuses_a_declared_name_at_another_directory(fake, home, tmp_path, said):
    home(f'[agent.jam]\ncwd = "{tmp_path}"\n')
    other = tmp_path / "other"
    other.mkdir()
    result = invoke("deck", "add", "jam", "--cwd", str(other))
    assert result.exit_code == 2 and "is already" in said(result) and "pick another name" in said(result)


def test_keep_needs_a_profile_to_keep_the_tab_in(fake, home, tmp_path, said):
    running(fake)
    result = invoke("deck", "add", "scratch", "--cwd", str(tmp_path), "--keep")
    assert result.exit_code == 2 and "no declared profile" in said(result)
    assert not (tmp_path / "deck.toml").exists()


def test_add_without_keep_opens_a_tab_and_writes_nothing(fake, home, tmp_path):
    running(fake)
    result = invoke("--json", "deck", "add", "scratch", "--cwd", str(tmp_path), "--role", "throwaway")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert (data["window"], data["opened"], data["from"], data["cwd"]) == ("scratch", True, "this deck", str(tmp_path))
    window = fake.find("new-window")[0]
    assert window[window.index("-c") + 1] == str(tmp_path) and window_of(fake, "scratch")
    assert not (tmp_path / "deck.toml").exists()


def test_add_with_keep_declares_the_agent_and_lists_it_in_the_profile(fake, home, tmp_path):
    work = tmp_path / "scratch"
    work.mkdir()
    home(f'[agent.ws]\ncwd = "{tmp_path}"\n\n[profile.core]\nprimary = "ws"\ntabs = []\n')
    running(fake, profile="core")
    result = invoke("--json", "deck", "add", "scratch", "--cwd", str(work), "--role", "throwaway", "--keep")
    assert result.exit_code == 0, result.output
    toml = declared(tmp_path)
    assert toml["agent"]["scratch"] == {"cwd": str(work), "role": "throwaway"}
    assert toml["profile"]["core"]["tabs"] == ["scratch"]
    assert json.loads(result.stdout)["data"]["from"] == "deck.toml"
    assert list((tmp_path / "backups").iterdir())


def test_keeping_a_declared_agent_only_adds_it_to_the_profile(fake, home, tmp_path):
    agents = f'[agent.ws]\ncwd = "{tmp_path}"\n[agent.jam]\ncwd = "{tmp_path}"\n'
    home(agents + '\n[profile.core]\nprimary = "ws"\ntabs = []\n')
    running(fake, profile="core")
    assert invoke("--json", "deck", "add", "jam", "--keep").exit_code == 0
    toml = declared(tmp_path)
    assert toml["profile"]["core"]["tabs"] == ["jam"] and set(toml["agent"]) == {"ws", "jam"}


def test_a_keep_that_would_break_deck_toml_is_refused_and_opens_nothing(fake, home, tmp_path, said):
    home('[profile.core]\nprimary = "ws"\ntabs = []\n[agent.ws]\ncwd = "/x"\n')
    running(fake, profile="core")
    (tmp_path / "deck.toml").write_text((tmp_path / "deck.toml").read_text() + "[agent.ws]\n")  # now unparseable
    result = invoke("deck", "add", "scratch", "--cwd", str(tmp_path), "--keep")
    assert result.exit_code != 0 and "new-window" not in fake.verbs()


# ============================================================================
# `sb deck terminal`
# ============================================================================


def test_terminal_opens_a_shell_tab_in_the_directory_given(fake, home, tmp_path):
    running(fake)
    result = invoke("--json", "deck", "terminal", "--cwd", str(tmp_path))
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    window = fake.find("new-window")[0]
    assert window[window.index("-c") + 1] == str(tmp_path) and window[window.index("-n") + 1] == "term"
    assert "--" not in window  # the operator's shell, not `claude`
    assert data == {"session": "sb-agents", "window": data["window"], "cwd": str(tmp_path)}
    assert fake.find("select-window")[0][-1] == data["window"]


def test_terminal_defaults_to_home(fake, home, tmp_path, monkeypatch):
    monkeypatch.setattr(deck_.Path, "home", lambda: tmp_path)
    running(fake)
    data = json.loads(invoke("--json", "deck", "terminal").stdout)["data"]
    assert data["cwd"] == str(tmp_path)


def test_terminal_in_a_missing_directory_fails_and_opens_nothing(fake, home, tmp_path):
    running(fake)
    result = invoke("--json", "deck", "terminal", "--cwd", str(tmp_path / "gone"))
    assert result.exit_code == 1
    assert "is not a directory" in json.loads(result.stdout)["data"]["error"]
    assert "new-window" not in fake.verbs()


# ============================================================================
# The popups' pickers, driven by scripted keys
# ============================================================================


def test_a_pick_moves_with_the_arrows_and_takes_enter(screen):
    keys = iter(["down", "down", "down", "up", "\r"])
    assert deck_._pick("t", ["a", "b", "c"], lambda s: next(keys)) == 1


def test_a_pick_stops_at_either_end(screen):
    keys = iter(["up", "pgdn", "down", "\n"])
    assert deck_._pick("t", ["a", "b", "c"], lambda s: next(keys)) == 2


def test_a_click_picks_the_row_under_it_and_a_click_on_the_title_does_not(screen):
    keys = iter(["click:3:1", "click:3:5"])
    assert deck_._pick("t", ["a", "b", "c"], lambda s: next(keys)) == 2


def test_q_or_escape_leaves_a_pick_with_nothing(screen):
    assert deck_._pick("t", ["a"], lambda s: "q") is None
    assert deck_._pick("t", ["a"], lambda s: "\x1b") is None


def test_a_hover_relights_the_row_and_is_not_an_answer(screen, capsys):
    keys = iter(["hover:3:4", "\r"])
    assert deck_._pick("t", ["a", "b"], lambda s: next(keys)) == 0
    assert capsys.readouterr().out.count("\x1b[2J") == 1


def test_a_quiet_popup_gives_up_after_its_wait(monkeypatch):
    monkeypatch.setattr(deck_, "POPUP_WAIT", 3 * deck_.keys_.TICK)
    waits = []
    assert deck_._popup_key(["x"], lambda y: True, lambda s: waits.append(s)) is None
    assert len(waits) == 3


def test_picked_restores_the_mouse_and_clears_after_the_pick(screen, monkeypatch, capsys):
    monkeypatch.setattr(deck_.keys_, "reader", keys_from("down", "\r"))
    assert deck_._picked("t", ["a", "b"]) == 1
    assert capsys.readouterr().out.endswith(deck_.resident_.MOUSE_OFF + "\x1b[2J\x1b[H")


# ============================================================================
# `sb deck plus` — the `+` popup
# ============================================================================


def test_plus_needs_a_terminal(fake, home, said):
    result = invoke("deck", "plus")
    assert result.exit_code == 2 and "the prompt needs a terminal" in said(result)


@pytest.fixture
def at_a_terminal(monkeypatch):
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)


def test_plus_with_nothing_declared_says_what_to_add(fake, home, at_a_terminal, monkeypatch):
    monkeypatch.setattr(deck_, "_picked", Picks(0))
    result = invoke("deck", "plus")
    assert result.exit_code == 0 and "nothing to open — add roots" in result.output


def test_plus_cancelled_at_the_first_question_opens_nothing(fake, home, at_a_terminal, monkeypatch, tmp_path):
    home(f'[agent.jam]\ncwd = "{tmp_path}"\n')
    monkeypatch.setattr(deck_, "_picked", Picks(None))
    assert invoke("deck", "plus").exit_code == 0 and fake.calls == []


def test_plus_terminal_opens_a_shell_in_the_folder_picked(fake, home, at_a_terminal, monkeypatch, tmp_path):
    home(f'[agent.jam]\ncwd = "{tmp_path}"\n')
    running(fake)
    picked = Picks(1, 0)
    monkeypatch.setattr(deck_, "_picked", picked)
    result = invoke("deck", "plus")
    assert result.exit_code == 0, result.output
    assert [title for title, _ in picked.asked] == ["Open a new tab", "Which folder?"]
    assert picked.asked[1][1] == [f"jam  {tmp_path}"]
    window = fake.find("new-window")[0]
    assert window[window.index("-c") + 1] == str(tmp_path) and "--" not in window


def test_plus_agent_on_a_declared_folder_opens_that_agent(fake, home, at_a_terminal, monkeypatch, tmp_path):
    home(f'[agent.jam]\ncwd = "{tmp_path}"\n')
    running(fake)
    monkeypatch.setattr(deck_, "_picked", Picks(0, 0))
    assert invoke("deck", "plus").exit_code == 0
    window = fake.find("new-window")[0]
    assert window[window.index("--") + 1 : window.index("--") + 4] == ["claude", "-n", "jam"]


def test_plus_agent_on_a_new_folder_asks_a_name_and_keeps_it_when_told(
    fake, home, at_a_terminal, monkeypatch, tmp_path
):
    root = tmp_path / "src"
    (root / "scratch").mkdir(parents=True)
    home(f'roots = ["{root}"]\n[agent.ws]\ncwd = "{tmp_path}"\n\n[profile.core]\nprimary = "ws"\ntabs = []\n')
    running(fake, profile="core")
    picked = Picks(0, 1, 0)
    monkeypatch.setattr(deck_, "_picked", picked)
    result = invoke("deck", "plus", input="scratchy\nthrowaway\n")
    assert result.exit_code == 0, result.output
    assert picked.asked[2] == ("Keep this tab?", ["add to profile core", "this deck only"])
    toml = declared(tmp_path)
    assert toml["agent"]["scratchy"] == {"cwd": str(root / "scratch"), "role": "throwaway"}
    assert toml["profile"]["core"]["tabs"] == ["scratchy"]


def test_plus_refuses_a_typed_name_tmux_cannot_hold(fake, home, at_a_terminal, monkeypatch, tmp_path):
    root = tmp_path / "src"
    (root / "scratch").mkdir(parents=True)
    home(f'roots = ["{root}"]\n')
    running(fake)
    monkeypatch.setattr(deck_, "_picked", Picks(0, 0))
    result = invoke("deck", "plus", input="a.b\n\n")
    assert result.exit_code == 0 and "cannot be a tab's name" in result.output
    assert "new-window" not in fake.verbs()


def test_plus_closed_at_keep_opens_nothing(fake, home, at_a_terminal, monkeypatch, tmp_path):
    home(f'[agent.ws]\ncwd = "{tmp_path}"\n[agent.jam]\ncwd = "{tmp_path}"\n[profile.core]\nprimary = "ws"\n')
    running(fake, profile="core")
    monkeypatch.setattr(deck_, "_picked", Picks(0, 1, None))
    assert invoke("deck", "plus").exit_code == 0
    assert "new-window" not in fake.verbs()


def test_plus_says_why_a_tab_failed_to_open(fake, home, at_a_terminal, monkeypatch, tmp_path):
    home(f'[agent.jam]\ncwd = "{tmp_path / "gone"}"\n')
    running(fake)
    monkeypatch.setattr(deck_, "_picked", Picks(0, 0))
    result = invoke("deck", "plus")
    assert result.exit_code == 0 and "gone" in result.output


# ============================================================================
# `sb deck launch` — the launcher inside a running deck
# ============================================================================


def test_launch_needs_a_terminal_and_a_running_deck(fake, home, monkeypatch, said):
    assert "needs a terminal" in said(invoke("deck", "launch"))
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)
    result = invoke("deck", "launch")
    assert result.exit_code == 2 and "no deck is running" in said(result)


def test_a_launch_quit_without_a_choice_switches_nothing(fake, home, at_a_terminal, monkeypatch):
    running(fake)
    monkeypatch.setattr(deck_, "launcher", lambda running: None)
    assert invoke("deck", "launch").exit_code == 0 and "switch-client" not in fake.verbs()


def test_launch_attaching_another_deck_switches_the_named_client_to_it(fake, home, at_a_terminal, monkeypatch):
    running(fake)
    fake.session("other")
    fake.session("other-agents")
    monkeypatch.setattr(deck_, "launcher", lambda running: (decklaunch.ATTACH, ("other",)))
    assert invoke("deck", "launch", "--client", "/dev/pts/3").exit_code == 0
    assert fake.find("switch-client") == [["tmux", "switch-client", "-c", "/dev/pts/3", "-t", "=other"]]
    assert "new-session" not in fake.verbs()


def test_launch_of_a_profile_starts_its_deck_beside_this_one(fake, home, at_a_terminal, monkeypatch, tmp_path):
    home(f'[agent.ws]\ncwd = "{tmp_path}"\n\n[profile.core]\nprimary = "ws"\ntabs = []\nsession = "core"\n')
    running(fake)
    monkeypatch.setattr(deck_, "launcher", lambda running: (decklaunch.PROFILE, ("core",)))
    assert invoke("deck", "launch").exit_code == 0
    assert {"core", "core-agents"} <= fake.sessions
    assert fake.find("switch-client")[-1] == ["tmux", "switch-client", "-t", "=core"]


# ============================================================================
# The launcher's loop: each outcome, scripted
# ============================================================================


class Outcomes:
    """A `_launch_once` returning each scripted outcome, recording each screen it was given."""

    def __init__(self, *scripted):
        self.queue, self.shown = list(scripted), []

    def __call__(self, launch):
        self.shown.append(launch)
        step = self.queue.pop(0)
        return step(launch) if callable(step) else (launch, step)


QUIT = decklaunch.Outcome(decklaunch.QUIT)


def row_named(launch, name):
    return next(row for row in launch.rows if row.name == name)


def test_the_launcher_quits_with_nothing_chosen(fake, home, monkeypatch, capsys):
    monkeypatch.setattr(deck_, "_launch_once", Outcomes(QUIT))
    assert deck_.launcher(running=False) is None
    assert capsys.readouterr().out.endswith("\x1b[2J\x1b[H")


def test_the_launcher_lists_decks_profiles_and_folders(fake, home, monkeypatch, tmp_path):
    root = tmp_path / "src"
    (root / "loose").mkdir(parents=True)
    home(f'roots = ["{root}"]\n[agent.ws]\ncwd = "{tmp_path}"\n[profile.core]\nprimary = "ws"\n')
    decksave.save("old", decksave.Saved(profile="core", tabs=[decksave.Tab("ws", "id-1", str(tmp_path))]))
    once = Outcomes(QUIT)
    monkeypatch.setattr(deck_, "_launch_once", once)
    deck_.launcher(running=False)
    rows = [(row.kind, row.name) for row in once.shown[0].rows]
    assert rows == [("resume", "old"), ("profile", "core"), ("folder", "ws"), ("add", "")]


def test_opening_a_profile_row_returns_it(fake, home, monkeypatch, tmp_path):
    home(f'[agent.ws]\ncwd = "{tmp_path}"\n[profile.core]\nprimary = "ws"\n')
    monkeypatch.setattr(
        deck_,
        "_launch_once",
        Outcomes(lambda launch: (launch, decklaunch.Outcome(decklaunch.OPEN, row_named(launch, "core")))),
    )
    assert deck_.launcher(running=False) == ("profile", ("core",))


def test_starting_new_folders_declares_them_then_returns_them(fake, home, monkeypatch, tmp_path):
    root = tmp_path / "src"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    home(f'roots = ["{root}"]\n')
    start = decklaunch.Outcome(decklaunch.START, names=("a", "b"))
    monkeypatch.setattr(deck_, "_launch_once", Outcomes(start))
    assert deck_.launcher(running=False) == ("start", ("a", "b"))
    assert declared(tmp_path)["agent"] == {"a": {"cwd": str(root / "a")}, "b": {"cwd": str(root / "b")}}


def test_a_start_that_cannot_be_declared_stays_and_says_why(fake, home, monkeypatch, tmp_path):
    root = tmp_path / "src"
    (root / "a").mkdir(parents=True)
    home(f'roots = ["{root}"]\nbroken = \n')
    monkeypatch.setattr(deck_, "load", lambda: (deck_.Config(roots=[str(root)]), []))
    once = Outcomes(decklaunch.Outcome(decklaunch.START, names=("a",)), QUIT)
    monkeypatch.setattr(deck_, "_launch_once", once)
    assert deck_.launcher(running=False) is None
    assert "nothing was written" in once.shown[1].note


def test_inside_a_deck_a_started_folder_opens_as_a_tab_and_the_screen_stays(fake, home, monkeypatch, tmp_path):
    home(f'[agent.ws]\ncwd = "{tmp_path}"\n')
    running(fake)
    once = Outcomes(decklaunch.Outcome(decklaunch.START, names=("ws",)), QUIT)
    monkeypatch.setattr(deck_, "_launch_once", once)
    assert deck_.launcher(running=True) is None
    assert window_of(fake, "ws") and once.shown[1].ticked == set()
    assert once.shown[1].note.startswith(f"trusted {tmp_path}")  # what opening it warned is the note


def test_a_delete_confirmed_with_y_drops_the_profile(fake, home, monkeypatch, tmp_path):
    home(f'[agent.ws]\ncwd = "{tmp_path}"\n[profile.core]\nprimary = "ws"\n')
    monkeypatch.setattr(deck_.keys_, "reader", keys_from("y"))
    drop = lambda launch: (launch, decklaunch.Outcome(decklaunch.DELETE, row_named(launch, "core")))  # noqa: E731
    once = Outcomes(drop, QUIT)
    monkeypatch.setattr(deck_, "_launch_once", once)
    deck_.launcher(running=False)
    assert "profile" not in declared(tmp_path) and once.shown[1].note == "deleted core"


def test_a_delete_answered_anything_but_y_keeps_the_agent(fake, home, monkeypatch, tmp_path):
    home(f'[agent.ws]\ncwd = "{tmp_path}"\n')
    monkeypatch.setattr(deck_.keys_, "reader", keys_from("n"))
    drop = lambda launch: (launch, decklaunch.Outcome(decklaunch.DELETE, row_named(launch, "ws")))  # noqa: E731
    monkeypatch.setattr(deck_, "_launch_once", Outcomes(drop, QUIT))
    deck_.launcher(running=False)
    assert "ws" in declared(tmp_path)["agent"]


def test_save_writes_the_ticked_folders_as_a_profile(fake, home, monkeypatch, tmp_path):
    home(f'[agent.ws]\ncwd = "{tmp_path}"\n[agent.jam]\ncwd = "{tmp_path}"\n')
    monkeypatch.setattr(deck_.click, "prompt", lambda *a, **k: "core")
    once = Outcomes(decklaunch.Outcome(decklaunch.SAVE, names=("jam", "ws")), QUIT)
    monkeypatch.setattr(deck_, "_launch_once", once)
    deck_.launcher(running=False)
    assert declared(tmp_path)["profile"]["core"] == {"primary": "jam", "tabs": ["ws"]}
    assert once.shown[1].note == "saved profile core"


@pytest.mark.parametrize("typed, note", [("", "not saved"), ("a b", "cannot be a profile's name")])
def test_save_under_no_name_or_a_bad_one_writes_nothing(fake, home, monkeypatch, tmp_path, typed, note):
    home(f'[agent.ws]\ncwd = "{tmp_path}"\n')
    monkeypatch.setattr(deck_.click, "prompt", lambda *a, **k: typed)
    once = Outcomes(decklaunch.Outcome(decklaunch.SAVE, names=("ws",)), QUIT)
    monkeypatch.setattr(deck_, "_launch_once", once)
    deck_.launcher(running=False)
    assert note in once.shown[1].note and "profile" not in declared(tmp_path)


def test_the_cursor_follows_its_row_by_name_across_a_redraw(fake, home, monkeypatch, tmp_path):
    home(f'[agent.ws]\ncwd = "{tmp_path}"\n[agent.jam]\ncwd = "{tmp_path}"\n')
    moved = lambda launch: (decklaunch.Launch(launch.rows, set(), 1), decklaunch.Outcome(decklaunch.NEW))  # noqa: E731
    monkeypatch.setattr(deck_, "_new_folder", lambda config: "nothing")
    once = Outcomes(moved, QUIT)
    monkeypatch.setattr(deck_, "_launch_once", once)
    deck_.launcher(running=False)
    assert once.shown[1].at == 1 and once.shown[1].note == "nothing"


# ============================================================================
# The launcher's screen loop and the folder browser
# ============================================================================


def test_launch_once_reads_keys_until_an_outcome(screen, monkeypatch):
    rows = decklaunch.rows_of([], [], {"core": 1, "two": 2}, [])
    monkeypatch.setattr(deck_.keys_, "reader", keys_from("click:2:1", "down", "\r"))
    launch, outcome = deck_._launch_once(decklaunch.Launch(rows))
    assert outcome.row is not None and (outcome.action, outcome.row.name) == (decklaunch.OPEN, "two")
    assert launch.at == 1


def test_a_click_on_a_folder_ticks_it(screen, monkeypatch):
    rows = decklaunch.rows_of([], [], {}, [("ws", "/x", True)])
    lines = decklaunch.screen(decklaunch.Launch(rows), 80)
    y = next(n for n, (_, row) in enumerate(lines, 1) if row == 0)
    monkeypatch.setattr(deck_.keys_, "reader", keys_from(f"click:4:{y}", "q"))
    launch, outcome = deck_._launch_once(decklaunch.Launch(rows))
    assert launch.ticked == {"ws"} and outcome.action == decklaunch.QUIT


def browse_to(monkeypatch, *answers):
    picked = Picks(*answers)
    monkeypatch.setattr(deck_, "_picked", picked)
    return picked


def test_new_folder_declares_the_folder_browsed_to(home, monkeypatch, tmp_path):
    (tmp_path / "proj").mkdir()
    monkeypatch.chdir(tmp_path)
    picked = browse_to(monkeypatch, 3, 0)
    home("")
    assert deck_._new_folder(deck_.Config()) == "added proj"
    assert picked.asked[0][1][3] == "proj/"
    assert declared(tmp_path)["agent"]["proj"] == {"cwd": str(tmp_path / "proj")}


def test_new_folder_cancelled_says_nothing(home, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    browse_to(monkeypatch, None)
    assert deck_._new_folder(deck_.Config()) == ""


def test_new_folder_refuses_a_name_already_an_agent(home, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    browse_to(monkeypatch, 0)
    config = deck_.Config(agents={tmp_path.name: deck_.Agent(tmp_path.name, "/elsewhere")})
    assert deck_._new_folder(config) == f"there is an agent {tmp_path.name!r} already"


def test_new_folder_refuses_a_folder_whose_name_cannot_be_a_tab(home, monkeypatch, tmp_path):
    odd = tmp_path / "--"
    odd.mkdir()
    monkeypatch.chdir(odd)
    browse_to(monkeypatch, 0)
    assert "cannot be a tab's name" in deck_._new_folder(deck_.Config())


def test_scanning_a_folder_with_git_projects_lists_them(home, monkeypatch, tmp_path):
    (tmp_path / "one" / ".git").mkdir(parents=True)
    (tmp_path / "two" / ".git").mkdir(parents=True)
    home("")
    monkeypatch.chdir(tmp_path)
    browse_to(monkeypatch, 1)
    said = deck_._new_folder(deck_.Config())
    assert said == f"2 git project(s) under {decklaunch.short(str(tmp_path))}: 2 newly listed"
    assert declared(tmp_path)["git_roots"] == [decklaunch.short(str(tmp_path))]


def test_scanning_a_folder_with_no_git_project_sets_nothing(home, tmp_path):
    home("")
    assert "no git project within" in deck_._toggle_scan(deck_.Config(), str(tmp_path))
    assert declared(tmp_path) == {}


def test_a_scan_counts_the_projects_it_could_not_list(home, tmp_path):
    (tmp_path / "ws" / ".git").mkdir(parents=True)
    (tmp_path / "ok" / ".git").mkdir(parents=True)
    home("")
    config = deck_.Config(agents={"ws": deck_.Agent("ws", "/elsewhere")})
    said = deck_._toggle_scan(config, str(tmp_path))
    assert said.endswith("1 newly listed; 1 not listed, their names are invalid or taken")


def test_scanning_a_scanned_folder_again_stops_listing_it(home, tmp_path):
    home(f'git_roots = ["{tmp_path}", "/kept"]\n')
    config, _ = deck_.load()
    said = deck_._toggle_scan(config, str(tmp_path))
    assert said.startswith("no longer listing") and declared(tmp_path)["git_roots"] == ["/kept"]


def test_the_browser_walks_down_into_the_folder_picked(monkeypatch, tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    picked = browse_to(monkeypatch, 3, 3, 0)
    assert deck_._browsed(deck_.Config()) == (0, str(tmp_path / "a" / "b"))
    assert picked.asked[2][0].endswith("/a/b")


# ============================================================================
# Saving the running deck as a profile, from the launcher
# ============================================================================


def tabs_open(fake, tmp_path):
    running(fake)
    fake.add("sb-agents", "ws", agent="ws", role="agent")
    fake.options[("=sb-agents:", "@sb-primary")] = "ws"
    decksave.save("sb", decksave.Saved(tabs=[decksave.Tab("ws", "id-1", str(tmp_path))]))


def test_save_deck_writes_this_decks_tabs_under_the_name_typed(fake, home, monkeypatch, tmp_path):
    home("")
    tabs_open(fake, tmp_path)
    monkeypatch.setattr(deck_.click, "prompt", lambda *a, **k: "core")
    said = deck_._save_deck_prompt(deck_.Config())
    assert said == "saved profile core: ws"
    assert declared(tmp_path)["profile"]["core"]["primary"] == "ws"
    assert declared(tmp_path)["agent"]["ws"] == {"cwd": str(tmp_path)}


def test_save_deck_over_a_profile_asks_and_a_no_keeps_it(fake, home, monkeypatch, tmp_path):
    home(f'[agent.ws]\ncwd = "{tmp_path}"\n[profile.core]\nprimary = "ws"\nbrief = "kept"\n')
    tabs_open(fake, tmp_path)
    monkeypatch.setattr(deck_.click, "prompt", lambda *a, **k: "core")
    monkeypatch.setattr(deck_.click, "confirm", lambda *a, **k: False)
    config, _ = deck_.load()
    assert deck_._save_deck_prompt(config) == "not saved"
    monkeypatch.setattr(deck_.click, "confirm", lambda *a, **k: True)
    assert deck_._save_deck_prompt(config) == "replaced profile core: ws"
    assert declared(tmp_path)["profile"]["core"]["brief"] == "kept"


@pytest.mark.parametrize("typed, said", [("", "not saved"), ("a b", "cannot be a profile's name")])
def test_save_deck_under_no_name_or_a_bad_one_saves_nothing(fake, home, monkeypatch, typed, said):
    monkeypatch.setattr(deck_.click, "prompt", lambda *a, **k: typed)
    assert said in deck_._save_deck_prompt(deck_.Config())


def test_save_deck_with_no_agent_tabs_says_so(fake, home, monkeypatch):
    running(fake)
    monkeypatch.setattr(deck_.click, "prompt", lambda *a, **k: "core")
    assert deck_._save_deck_prompt(deck_.Config()) == "this deck has no agent tabs to save"


# ============================================================================
# `sb deck decide add` — a question, a choice, or an action
# ============================================================================


def decisions(agent="jam"):
    todo = todos_.load("sb", agent, todos_.DECISIONS)
    return todo.items if todo else []


@pytest.fixture
def in_jams_tab(fake, home, monkeypatch):
    two_tabs(fake)
    caller_under(monkeypatch, 20)


def test_a_decision_with_options_is_recorded_on_the_callers_list(in_jams_tab):
    result = invoke("--json", "deck", "decide", "add", "take it?", "--option", "take it", "--option", "hold ours")
    assert result.exit_code == 0, result.output
    (item,) = decisions()
    assert (item.text, item.options, item.kind) == ("take it?", ["take it", "hold ours"], todos_.CHOICE)


def test_an_action_records_its_argv_folder_and_closing_test(in_jams_tab, tmp_path):
    result = invoke(
        "deck",
        "decide",
        "add",
        "merge it",
        "--run",
        "gh pr merge 49 --merge",
        "--until",
        "pr:49",
        "--cwd",
        str(tmp_path),
    )
    assert result.exit_code == 0, result.output
    (item,) = decisions()
    assert item.kind == todos_.ACTION and item.run == ["gh", "pr", "merge", "49", "--merge"]
    assert (item.cwd, item.until) == (str(tmp_path.resolve()), "pr:49")


def test_a_bare_action_runs_in_the_callers_folder(in_jams_tab, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert invoke("deck", "decide", "add", "renew the certificate", "--action").exit_code == 0
    (item,) = decisions()
    assert (item.kind, item.run, item.cwd) == (todos_.ACTION, [], str(tmp_path))


@pytest.mark.parametrize(
    "args, phrase",
    [
        (["   "], "a decision needs a question"),
        (["x", "--action", "--option", "a"], "an action has no choices"),
        (["x", "--run", "a | b"], "no shell"),
        (["x", "--until", "ci:green"], "--until is one of"),
        (["x", "--option", " "], "an --option needs words"),
        (["x", *[w for n in range(10) for w in ("--option", str(n))]], "at most 9 choices"),
    ],
)
def test_a_malformed_decision_is_refused_and_nothing_is_written(in_jams_tab, said, args, phrase):
    result = invoke("deck", "decide", "add", *args)
    assert result.exit_code == 2 and phrase in said(result) and decisions() == []


def test_a_notice_is_recorded_and_an_empty_one_refused(in_jams_tab, said):
    assert "a notice needs words" in said(invoke("deck", "decide", "note", " "))
    assert invoke("deck", "decide", "note", "alert #36 is open").exit_code == 0
    assert [(i.text, i.kind) for i in decisions()] == [("alert #36 is open", todos_.NOTICE)]


# ============================================================================
# `sb deck decide rule` and `act` — the operator's popups, keys scripted
# ============================================================================


@pytest.fixture
def operator(fake, home, monkeypatch, screen):
    """A terminal outside every deck tab, with Enter-free keys scripted per test."""
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)

    def press(*keys):
        monkeypatch.setattr(deck_.keys_, "reader", keys_from(*keys))

    return press


def test_a_ruling_by_number_records_that_choice(operator):
    todos_.add("sb", "jam", "take it?", todos_.DECISIONS, ("take it", "hold ours"))
    operator("hover:3:2", "x", "2")
    assert invoke("deck", "decide", "rule", "jam", "1").exit_code == 0
    assert (decisions()[0].done, decisions()[0].ruling) == (True, "hold ours")


def test_a_typed_ruling_is_recorded_as_typed(operator):
    todos_.add("sb", "jam", "take it?", todos_.DECISIONS)
    operator("t")
    assert invoke("deck", "decide", "rule", "jam", "1", input="ship  it\n").exit_code == 0
    assert decisions()[0].ruling == "ship it"


def test_a_ruling_closed_with_q_rules_nothing(operator):
    todos_.add("sb", "jam", "take it?", todos_.DECISIONS, ("a",))
    operator("q")
    assert invoke("deck", "decide", "rule", "jam", "1").exit_code == 0 and not decisions()[0].done


def test_a_ruling_on_a_decision_that_is_not_there_is_refused(operator, said):
    result = invoke("deck", "decide", "rule", "jam", "3")
    assert result.exit_code == 1 and "jam has no decision 3" in said(result)


def an_action(run=("make", "ship"), until="", cwd=""):
    todos_.add("sb", "jam", "ship it", todos_.DECISIONS, kind=todos_.ACTION, run=list(run), cwd=cwd, until=until)


def test_an_action_is_the_operators_off_a_terminal_and_inside_a_tab(fake, home, monkeypatch, said):
    an_action()
    assert "no terminal here to ask on" in said(invoke("deck", "decide", "act", "jam", "1"))
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)
    monkeypatch.setattr(deck_, "caller_tab", lambda session: "jam")
    assert "refuses inside a deck tab" in said(invoke("deck", "decide", "act", "jam", "1"))


def test_act_refuses_a_number_with_no_open_action(operator, said):
    todos_.add("sb", "jam", "take it?", todos_.DECISIONS)
    assert "jam has no action 2" in said(invoke("deck", "decide", "act", "jam", "2"))
    assert "is not an open action" in said(invoke("deck", "decide", "act", "jam", "1"))


def test_an_action_already_observed_done_closes_without_asking(operator, monkeypatch):
    an_action(until="pr:49")
    monkeypatch.setattr(deckasks, "observe", lambda *a, **k: deckasks.Seen(closed="PR #49 merged"))
    monkeypatch.setattr(deck_.keys_, "reader", lambda stream=None: pytest.fail("a closed action asked"))
    result = invoke("deck", "decide", "act", "jam", "1")
    assert result.exit_code == 0 and "already done: PR #49 merged" in result.output
    assert (decisions()[0].done, decisions()[0].ruling) == (True, "PR #49 merged")


def test_d_marks_an_action_done_with_nothing_checked(operator):
    an_action()
    operator("d")
    assert invoke("deck", "decide", "act", "jam", "1").exit_code == 0
    assert decisions()[0].ruling == "marked done by the operator, nothing checked it"


@pytest.fixture
def ran(monkeypatch):
    run = Ran()
    monkeypatch.setattr(deck_.subprocess, "run", run)
    return run


class Ran:
    """`subprocess.run`, recorded, exiting `code`."""

    def __init__(self):
        self.calls, self.given, self.code = [], {}, 0

    def __call__(self, argv, cwd=None, env=None, check=False, **given):
        self.calls.append((list(argv), cwd, env))
        self.given = given
        return deck_.subprocess.CompletedProcess(argv, self.code)


def test_r_runs_the_command_shown_in_its_folder_and_a_clean_exit_closes_it(operator, ran, tmp_path):
    an_action(cwd=str(tmp_path))
    operator("r", "x")
    result = invoke("deck", "decide", "act", "jam", "1")
    assert result.exit_code == 0 and "exit 0. Press a key to close." in result.output
    ((argv, cwd, env),) = ran.calls
    assert (argv, cwd) == (["make", "ship"], str(tmp_path)) and "PYTHONSAFEPATH" not in env
    assert decisions()[0].ruling == "ran, exit 0, nothing checked it"


def test_a_failed_run_leaves_the_action_open(operator, ran):
    an_action()
    ran.code = 2
    operator("r", "x")
    assert "exit 2." in invoke("deck", "decide", "act", "jam", "1").output and not decisions()[0].done


def test_a_run_with_a_test_closes_only_when_the_test_sees_it(operator, ran, monkeypatch):
    an_action(until="pr:49")
    seen = iter([deckasks.Seen(), deckasks.Seen()])
    monkeypatch.setattr(deckasks, "observe", lambda *a, **k: next(seen))
    operator("r", "x")
    assert invoke("deck", "decide", "act", "jam", "1").exit_code == 0 and not decisions()[0].done


def test_a_stale_action_offers_no_run(operator, ran, monkeypatch):
    an_action(until="pr:49@abc1234")
    monkeypatch.setattr(deckasks, "observe", lambda *a, **k: deckasks.Seen(stale="head moved to def5678"))
    operator("r", "q")
    assert invoke("deck", "decide", "act", "jam", "1").exit_code == 0 and ran.calls == []


def test_a_command_that_cannot_start_is_exit_127_in_words(monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError("no such file: make")

    monkeypatch.setattr(deck_.subprocess, "run", missing)
    assert deck_.run_action(todos_.Item("x", run=["make"])) == (127, "no such file: make")


# ============================================================================
# `sb deck decide sweep` — actions observed, held state read, shells watched
# ============================================================================


class Listing(FakeTmux):
    """A FakeTmux that also answers the sweep's repo listing and the tab row's measurements."""

    def __init__(self, panes_out="", clients="", windows=""):
        super().__init__()
        self.panes_out, self.clients, self.windows_out = panes_out, clients, windows

    def __call__(self, argv, replace=False):
        if argv[1] == "list-panes" and "-s" in argv:
            self.calls.append(list(argv))
            return Answer(asked=True, out=self.panes_out)
        if argv[1] == "list-clients":
            self.calls.append(list(argv))
            return Answer(asked=True, out=self.clients)
        if argv[1] == "list-windows":
            self.calls.append(list(argv))
            return Answer(asked=True, out=self.windows_out)
        return super().__call__(argv, replace)


def test_deck_repos_names_each_agents_repository_once(monkeypatch):
    out = "agent\t/r/a\nagent\t/r/a/sub\nqueue\t/r/q\nagent\t/r/none\n"
    monkeypatch.setattr(deck_, "RUNNER", Listing(panes_out=out))
    tops = {"/r/a": "/r/a", "/r/a/sub": "/r/a"}

    def read(args, cwd):
        top = tops.get(cwd)
        return deck_.subprocess.CompletedProcess(args, 0 if top else 128, f"{top}\n" if top else "", "")

    monkeypatch.setattr(deckasks, "read", read)
    assert deck_.deck_repos("sb") == ["/r/a"]


def test_the_sweep_closes_observed_actions_and_reads_held_state_when_due(fake, home, monkeypatch, tmp_path):
    an_action(until="pr:49")
    monkeypatch.setattr(deckasks, "observe", lambda *a, **k: deckasks.Seen(closed="PR #49 merged"))
    monkeypatch.setattr(deck_, "deck_repos", lambda session: [str(tmp_path)])
    monkeypatch.setattr(deckasks, "held_of", lambda repo: {"repo": repo, "rows": ["1 unpushed on x"], "unread": []})
    watched = []
    monkeypatch.setattr(deck_, "watch_shells", lambda session: watched.append(session))
    assert invoke("deck", "decide", "sweep").exit_code == 0
    assert decisions()[0].done and watched == ["sb"]
    held = deckasks.read_held("sb")
    assert held is not None and held["repos"] == [{"repo": str(tmp_path), "rows": ["1 unpushed on x"], "unread": []}]


def test_a_fresh_held_reading_is_not_read_again(fake, home, monkeypatch):
    deckasks.write_held("sb", [{"repo": "kept", "rows": [], "unread": []}])
    monkeypatch.setattr(deck_, "deck_repos", lambda session: pytest.fail("read again"))
    monkeypatch.setattr(deck_, "watch_shells", lambda session: [])
    assert invoke("deck", "decide", "sweep").exit_code == 0
    held = deckasks.read_held("sb")
    assert held is not None and held["repos"][0]["repo"] == "kept"


def test_an_unreadable_list_does_not_stop_the_sweep(fake, home, monkeypatch):
    an_action(until="pr:49")
    todos_.path_for("sb", "bad", todos_.DECISIONS).write_text("{not json")
    monkeypatch.setattr(deckasks, "observe", lambda *a, **k: deckasks.Seen(closed="PR #49 merged"))
    monkeypatch.setattr(deck_, "deck_repos", lambda session: [])
    monkeypatch.setattr(deck_, "watch_shells", lambda session: [])
    assert invoke("deck", "decide", "sweep").exit_code == 0 and decisions()[0].done


# ============================================================================
# `sb deck ask` — a hook event on stdin
# ============================================================================


def test_a_permission_request_from_a_tab_becomes_an_asked_row(fake, home, monkeypatch):
    monkeypatch.setattr(deck_, "caller_tab", lambda session: "jam")
    payload = {"hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": {"command": "ls"}}
    result = invoke("deck", "ask", input=json.dumps(payload))
    assert result.exit_code == 0 and result.output == ""
    asks = todos_.load("sb", "jam", todos_.ASKS)
    assert asks is not None and [(i.kind, i.text) for i in asks.items] == [(todos_.ASKED, "Bash: ls")]


def test_a_resumed_tab_is_handed_todays_brief(fake, home, monkeypatch):
    monkeypatch.setattr(deck_, "caller_tab", lambda session: "jam")
    result = invoke("deck", "ask", input=json.dumps({"hook_event_name": "SessionStart", "source": "resume"}))
    reply = json.loads(result.output)["hookSpecificOutput"]
    assert reply["hookEventName"] == "SessionStart" and "this wins" in reply["additionalContext"]


@pytest.mark.parametrize("stdin", ["{not json", "", '["a list"]'])
def test_a_hook_never_fails_whatever_it_is_handed(fake, home, monkeypatch, stdin):
    monkeypatch.setattr(deck_, "caller_tab", lambda session: "jam")
    result = invoke("deck", "ask", input=stdin)
    assert result.exit_code == 0 and result.output == "" and todos_.load("sb", "jam", todos_.ASKS) is None


def test_a_hook_outside_every_tab_writes_nothing(fake, home):
    payload = {"hook_event_name": "PermissionRequest", "tool_name": "Bash"}
    assert invoke("deck", "ask", input=json.dumps(payload)).exit_code == 0
    assert todos_.stored("sb", todos_.ASKS) == []


# ============================================================================
# `sb deck column pick`, `sb deck scroll`, the message pager
# ============================================================================


def test_column_pick_needs_a_terminal(fake, home, said):
    assert "pick needs a terminal" in said(invoke("deck", "column", "pick"))


def test_a_cancelled_column_pick_changes_nothing(fake, home, monkeypatch):
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)
    monkeypatch.setattr(deck_.column_, "pick", lambda column, console, wait_for: None)
    result = invoke("--json", "deck", "column", "pick")
    assert result.exit_code == 0 and "cancelled — nothing changed" in result.stderr
    assert [row["pane"] for row in json.loads(result.stdout)["data"]] == list(deck_.column_.TOOLS)


def test_a_column_pick_is_saved_and_applies_when_the_deck_starts(fake, home, monkeypatch):
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)
    picked = deck_.column_.Column(order=["todos", "queue", "messages", "decisions"], hidden={"queue"})
    monkeypatch.setattr(deck_.column_, "pick", lambda column, console, wait_for: picked)
    result = invoke("--json", "deck", "column", "pick")
    assert result.exit_code == 0 and "applies when `sb deck` starts one" in " ".join(result.stderr.split())
    assert deck_.column_.load("sb")[0].order[0] == "todos" and deck_.column_.load("sb")[0].hidden == {"queue"}


def test_column_show_reads_the_saved_choice(fake, home):
    deck_.column_.save("sb", deck_.column_.Column(collapsed={"todos"}))
    rows = json.loads(invoke("--json", "deck", "column", "show").stdout)["data"]
    assert {row["pane"]: row["folded"] for row in rows}["todos"] is True


def test_column_move_refuses_a_pane_that_is_not_in_the_column(fake, home, said):
    result = invoke("deck", "column", "move", "tabs", "1")
    assert result.exit_code == 2 and "is not a right-column pane" in said(result)


def test_column_move_saves_the_grid_it_asked_for(fake, home):
    assert invoke("--json", "deck", "column", "move", "messages", "1").exit_code == 0
    assert "messages" in deck_.column_.load("sb")[0].columns[0]


def test_scroll_with_no_deck_tabs_fails_and_says_so(fake, home):
    result = invoke("--json", "deck", "scroll")
    assert result.exit_code == 1 and "no deck tabs 'sb-agents'" in json.loads(result.stdout)["data"]["error"]


@pytest.mark.parametrize("width, overflowing", [("400", False), ("40", True)])
def test_scroll_draws_the_bar_only_when_the_tabs_overflow(home, monkeypatch, width, overflowing):
    tabs = "".join(f"{int(n == 0)}\tagent-number-{n}\n" for n in range(8))
    server = Listing(clients=f"{width}\n", windows=tabs)
    monkeypatch.setattr(deck_, "RUNNER", server)
    server.session("sb")
    server.session("sb-agents")
    data = json.loads(invoke("--json", "deck", "scroll").stdout)["data"]
    assert data == {"overflowing": overflowing}


def message():
    return {"between_parts": [["ws", None], "→", ["jam", None]], "at": None, "body": "**hello** there"}


def test_a_message_pages_through_less_and_keeps_less_open_on_a_short_page(fake, ran):
    deck_._page(message())
    ((argv, _, _),) = ran.calls
    assert argv == ["/usr/bin/less", "-R", "-c", "-+F", "-Pq closes"] and "hello" in ran.given["input"]


def test_with_no_less_a_message_is_printed_and_held_for_a_key(monkeypatch, capsys):
    monkeypatch.setattr(deck_.shutil, "which", lambda name, path=None: None)
    monkeypatch.setattr(deck_.keys_, "reader", keys_from(None, "x"))
    deck_._page(message())
    out = capsys.readouterr().out
    assert "hello" in out and out.endswith("(any key closes)")
