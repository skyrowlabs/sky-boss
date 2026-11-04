"""`sb deck` — the tmux command center. See [[command-deck]].

**No test here runs tmux.** Every call goes through `skyboss.deck.RUNNER`, which
`FakeTmux` replaces; it records argv and answers from a small model of a server.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from skyboss import cli
from skyboss import deck as deck_
from skyboss.deck import Agent, Answer, Config, find_window, parse, parse_panes, resolve

#: Host-side; nothing here needs a service or a tmux binary.
pytestmark = [pytest.mark.unit]


class FakeTmux:
    """A tmux server reduced to sessions, windows and panes, recorded call by call."""

    def __init__(self, *, sessions=(), extended="on", installed=True):
        self.calls: list[list[str]] = []
        self.sessions = set(sessions)
        self.extended = extended
        self.installed = installed
        self.listing = ""
        self.windows = 0
        self.replaced: list[list[str]] = []

    def __call__(self, argv, replace=False):
        self.calls.append(list(argv))
        if not self.installed:
            return Answer(asked=False, err="No such file or directory: 'tmux'")
        if replace:
            self.replaced.append(list(argv))
            return Answer(asked=True)
        verb, args = argv[1], argv[2:]
        if verb == "has-session":
            return Answer(asked=True, code=0 if args[1].lstrip("=") in self.sessions else 1)
        if verb == "new-session":
            self.sessions.add(args[args.index("-s") + 1])
            return self._window()
        if verb == "new-window":
            return self._window()
        if verb == "split-window":
            self.windows += 1
            return Answer(asked=True, out=f"%{self.windows}\n")
        if verb == "list-panes":
            return Answer(asked=True, out=self.listing)
        if verb == "show-options":
            return Answer(asked=True, out=f"{self.extended}\n")
        return Answer(asked=True)

    def _window(self):
        self.windows += 1
        return Answer(asked=True, out=f"@{self.windows} %{self.windows}\n")

    def verbs(self) -> list[str]:
        return [call[1] for call in self.calls]

    def find(self, verb: str) -> list[list[str]]:
        return [call for call in self.calls if call[1] == verb]


@pytest.fixture
def fake(monkeypatch):
    server = FakeTmux()
    monkeypatch.setattr(deck_, "RUNNER", server)
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(deck_.shutil, "which", lambda name, path=None: f"/usr/bin/{name}")
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


def invoke(*args: str):
    return CliRunner().invoke(cli, list(args))


# ============================================================================
# Config
# ============================================================================


def test_an_absent_file_declares_nothing_and_says_nothing(tmp_path):
    config, problems = deck_.load(tmp_path)
    assert (config.session, config.pin, config.agents, problems) == ("sb", "", {}, [])


def test_a_declared_agent_parses_with_its_args():
    config, problems = parse(
        {"session": "work", "pin": "ws", "agent": {"ws": {"cwd": "~/src/ws", "args": ["--model", "opus"]}}}
    )
    assert problems == []
    assert config.session == "work" and config.pin == "ws"
    assert config.agents["ws"].argv == ["claude", "--model", "opus"]


def test_a_typod_table_is_named_not_silent():
    _, problems = parse({"agnet": {"ws": {"cwd": "/x"}}})
    assert problems == ["unknown table 'agnet' — ignored"]


@pytest.mark.parametrize(
    "body, phrase",
    [
        ({"args": []}, "cwd must be a non-empty string"),
        ({"cwd": "/x", "args": "--model opus"}, "not a shell string"),
        ({"cwd": "/x", "args": [1]}, "list of strings"),
        ("not-a-table", "not a table"),
    ],
)
def test_a_bad_agent_is_skipped_and_named(body, phrase):
    config, problems = parse({"agent": {"ws": body, "ok": {"cwd": "/y"}}})
    assert list(config.agents) == ["ok"]
    assert any(phrase in p for p in problems)


def test_an_unknown_agent_key_is_reported_and_the_agent_kept():
    config, problems = parse({"agent": {"ws": {"cwd": "/x", "model": "opus"}}})
    assert "ws" in config.agents
    assert problems == ["agent 'ws': unknown key 'model' — ignored"]


@pytest.mark.parametrize("session", ["a.b", "a:b", "", 3])
def test_a_session_tmux_would_rename_falls_back_to_the_default(session):
    config, problems = parse({"session": session})
    assert config.session == "sb" and problems


def test_an_unreadable_file_is_one_problem(tmp_path):
    (tmp_path / "deck.toml").write_text("session = [")
    config, problems = deck_.load(tmp_path)
    assert config.agents == {} and len(problems) == 1


# ============================================================================
# Resolution: deck.toml first, then projects.toml
# ============================================================================


class P:
    def __init__(self, name, cwd=""):
        self.name, self.cwd = name, cwd


def test_a_deck_agent_wins_over_a_project_of_the_same_name():
    config = Config(agents={"jam": Agent("jam", "/deck")})
    agent, _ = resolve("jam", config, [P("jam", "/project")])
    assert agent is not None and agent.cwd == "/deck"


def test_a_project_cwd_is_the_fallback():
    agent, _ = resolve("jam", Config(), [P("jam", "/project")])
    assert agent is not None and (agent.cwd, agent.source) == ("/project", "projects.toml")


def test_a_project_without_a_cwd_says_so():
    agent, why = resolve("jam", Config(), [P("jam")])
    assert agent is None and "declares no cwd" in why


def test_an_unknown_name_lists_what_is_known():
    agent, why = resolve("nope", Config(agents={"ws": Agent("ws", "/x")}), [P("jam", "/p"), P("bare")])
    assert agent is None and "known: jam, ws" in why


# ============================================================================
# Reading panes back
# ============================================================================


LISTING = "@1\t0\tws\tws\t%1\t100\tagent\n@1\t0\tws\tws\t%2\t101\tqueue\n@2\t1\tzsh\t\t%3\t200\t\n"


def test_list_panes_output_parses_and_a_bad_line_is_skipped():
    panes = parse_panes(LISTING + "garbage\n@3\tx\ty\t\t%4\t1\t\n")
    assert [(p.window_id, p.pid, p.role) for p in panes] == [
        ("@1", 100, "agent"),
        ("@1", 101, "queue"),
        ("@2", 200, ""),
    ]


def test_a_window_is_found_by_its_agent_before_its_name():
    panes = parse_panes("@1\t0\tjam\t\t%1\t1\t\n@2\t1\trenamed\tjam\t%2\t2\tagent\n")
    assert find_window("jam", panes) == "@2"
    assert find_window("renamed", panes) == "@2"
    assert find_window("absent", panes) is None


# ============================================================================
# `sb deck` — create, dress, attach
# ============================================================================


def test_bare_deck_creates_the_pinned_window_and_attaches(fake, home, tmp_path):
    home(f'pin = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\nargs = ["--model", "opus"]\n')
    result = invoke("deck")
    # CliRunner has no terminal, so outside tmux it refuses to attach and says how.
    assert result.exit_code == 1 and "tmux attach -t =sb" in result.output
    created = fake.find("new-session")[0]
    assert created[created.index("--") + 1 :] == ["claude", "--model", "opus"]
    assert created[created.index("-c") + 1] == str(tmp_path)


def test_bare_deck_execs_attach_at_a_terminal(fake, home, monkeypatch):
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)
    result = invoke("deck")
    assert result.exit_code == 0, result.output
    assert fake.replaced == [["tmux", "attach-session", "-t", "=sb"]]


def test_inside_tmux_the_client_switches_instead(fake, home, monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/socket,1,0")
    fake.sessions.add("sb")
    result = invoke("deck")
    assert result.exit_code == 0, result.output
    assert fake.find("switch-client") == [["tmux", "switch-client", "-t", "=sb"]]
    assert not fake.replaced and "new-session" not in fake.verbs()


def test_the_deck_dresses_its_window_and_never_the_server(fake, home):
    invoke("deck")
    options = [call[2:] for call in fake.find("set-option")]
    assert ["-w", "-t", "@1", "window-size", "latest"] in options
    assert ["-w", "-t", "@1", "allow-passthrough", "on"] in options
    assert not any("-g" in o or "-s" in o for o in options)


def test_extended_keys_off_is_reported_and_never_set(fake, home):
    fake.extended = "off"
    result = invoke("deck")
    assert "extended-keys is off" in result.output
    assert not any("extended-keys" in call for call in fake.find("set-option"))


def test_bare_deck_refuses_json_before_touching_tmux(fake, home):
    result = invoke("--json", "deck")
    assert result.exit_code == 2 and fake.calls == []


def test_no_tmux_is_a_sentence(fake, home):
    fake.installed = False
    result = invoke("deck")
    assert result.exit_code == 1 and "tmux could not be run" in result.output


def test_an_unresolvable_pin_opens_the_deck_without_it(fake, home):
    home('pin = "ghost"\n')
    result = invoke("deck")
    assert "pin 'ghost'" in result.output
    assert fake.find("new-session") and "--" not in fake.find("new-session")[0]


# ============================================================================
# `sb deck open`
# ============================================================================


def test_open_starts_a_window_in_the_agents_cwd(fake, home, tmp_path):
    home(f'[agent.jam]\ncwd = "{tmp_path}"\n')
    fake.sessions.add("sb")
    result = invoke("--json", "deck", "open", "jam")
    assert result.exit_code == 0, result.output
    window = fake.find("new-window")[0]
    assert window[window.index("-n") + 1] == "jam" and window[-1] == "claude"
    assert ["tmux", "set-option", "-w", "-t", "@1", "@sb-agent", "jam"] in fake.calls
    assert fake.find("select-window") == [["tmux", "select-window", "-t", "@1"]]


def test_open_selects_a_window_that_is_already_open(fake, home, tmp_path):
    home(f'[agent.jam]\ncwd = "{tmp_path}"\n')
    fake.sessions.add("sb")
    fake.listing = "@7\t2\tjam\tjam\t%9\t300\tagent\n"
    result = invoke("--json", "deck", "open", "jam")
    assert result.exit_code == 0
    assert "new-window" not in fake.verbs()
    assert fake.find("select-window") == [["tmux", "select-window", "-t", "@7"]]


def test_open_refuses_a_name_nobody_declared(fake, home):
    result = invoke("deck", "open", "ghost")
    assert result.exit_code == 2 and fake.calls == []


def test_open_refuses_a_cwd_that_is_not_there(fake, home, tmp_path):
    home(f'[agent.jam]\ncwd = "{tmp_path / "gone"}"\n')
    fake.sessions.add("sb")
    result = invoke("--json", "deck", "open", "jam")
    assert result.exit_code == 1 and "is not a directory" in result.output
    assert "new-window" not in fake.verbs()


# ============================================================================
# The rules that are not negotiable
# ============================================================================


def test_the_deck_never_types_into_a_pane():
    """No key injection: a deck that could answer a prompt is a second permission path."""
    source = Path(deck_.__file__).read_text()
    assert not re.search(r"send-keys|send_keys|send-prefix|paste-buffer", source)


def test_every_deck_subcommand_chooses_its_act_bit():
    """Recomputed from the group's membership, so the next subcommand cannot inherit observe."""
    group = deck_.deck
    undecided = [name for name, command in group.commands.items() if not hasattr(command, "sb_acts")]
    assert hasattr(group, "sb_acts") and not undecided, undecided
