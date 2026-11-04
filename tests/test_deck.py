"""`sb deck` — the tmux command center. See [[command-deck]].

**No test here runs tmux.** Every call goes through `skyboss.deck.RUNNER`, which
`FakeTmux` replaces; it records argv and answers from a small model of a server.
"""

from __future__ import annotations

import functools
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from skyboss import cli
from skyboss import deck as deck_
from skyboss import output
from skyboss.agents import Scan, Session
from skyboss.deck import (
    Agent,
    Answer,
    Config,
    Pane,
    find_window,
    parents,
    parse,
    parse_panes,
    queue_result,
    queue_rows,
    resolve,
    tree,
)

#: Host-side; nothing here needs a service or a tmux binary.
pytestmark = [pytest.mark.unit]


class FakeTmux:
    """A tmux server reduced to sessions, windows and panes, recorded call by call.

    Panes carry the roles and window options the deck writes, so a listing is
    whatever the deck itself built.
    """

    def __init__(self, *, extended="on", installed=True):
        self.calls: list[list[str]] = []
        self.windows: dict[str, dict] = {}
        self.panes: dict[str, dict] = {}
        self.order: dict[str, list[str]] = {}
        self.options: dict[tuple[str, str], str] = {}
        self.extended = extended
        self.installed = installed
        self.current = ""
        self.serial = 0
        self.replaced: list[list[str]] = []

    @property
    def sessions(self) -> set[str]:
        return set(self.order)

    def session(self, name: str) -> None:
        """A session that exists already, with one window and nothing the deck put there."""
        self._new_window(name, "zsh")

    def add(self, session: str, window: str, *, agent: str = "", role: str = "", pid: int = 0) -> tuple[str, str]:
        wid, pid_ = self._new_window(session, window, pid=pid)
        self.windows[wid]["agent"] = agent
        self.panes[pid_]["role"] = role
        return wid, pid_

    def _new_window(self, session: str, name: str, pid: int = 0) -> tuple[str, str]:
        self.serial += 1
        wid = f"@{self.serial}"
        index = len(self.order.setdefault(session, []))
        self.order[session].append(wid)
        self.windows[wid] = {"session": session, "index": index, "name": name, "agent": ""}
        return wid, self._new_pane(wid, pid)

    def _new_pane(self, wid: str, pid: int = 0) -> str:
        self.serial += 1
        pane = f"%{self.serial}"
        self.panes[pane] = {"window": wid, "pid": pid or 1000 + self.serial, "role": "", "argv": []}
        return pane

    def __call__(self, argv, replace=False):
        self.calls.append(list(argv))
        if not self.installed:
            return Answer(asked=False, err="No such file or directory: 'tmux'")
        if replace:
            self.replaced.append(list(argv))
            return Answer(asked=True)
        verb, args = argv[1], argv[2:]
        command = args[args.index("--") + 1 :] if "--" in args else []
        target = args[args.index("-t") + 1] if "-t" in args else ""
        if verb == "has-session":
            return Answer(asked=True, code=0 if target.lstrip("=") in self.order else 1)
        if verb in ("new-session", "new-window"):
            session = args[args.index("-s") + 1] if verb == "new-session" else target.strip("=:")
            name = args[args.index("-n") + 1] if "-n" in args else ""
            wid, pane = self._new_window(session, name)
            self.panes[pane]["argv"] = command
            return Answer(asked=True, out=f"{wid} {pane}\n")
        if verb == "split-window":
            pane = self._new_pane(target)
            self.panes[pane]["argv"] = command
            return Answer(asked=True, out=f"{pane}\n")
        if verb == "set-option":
            if args[:1] == ["-p"] and args[3] == "@sb-deck":
                self.panes[args[2]]["role"] = args[4]
            elif args[:1] == ["-w"] and args[3] == "@sb-agent":
                self.windows[args[2]]["agent"] = args[4]
            elif args[0] == "-t":
                if not args[1].endswith(":"):
                    # Real tmux reads a pane target here and refuses a bare `=name`.
                    return Answer(asked=True, code=1, err=f"no such session: {args[1]}\n")
                self.options[(args[1], args[2])] = args[3]
            return Answer(asked=True)
        if verb == "list-panes":
            return Answer(asked=True, out=self.listing(target.lstrip("=")))
        if verb == "show-options":
            if "extended-keys" in args:
                return Answer(asked=True, out=f"{self.extended}\n")
            return Answer(asked=True, out=self.options.get((target, args[-1]), "") + "\n")
        if verb == "display-message":
            if args[-1] == "#{socket_path}":
                return Answer(asked=True, out="/tmp/fx-socket\n")
            return Answer(asked=True, out=f"{self.current}\n")
        return Answer(asked=True)

    def listing(self, session: str) -> str:
        lines = []
        for wid in self.order.get(session, []):
            window = self.windows[wid]
            for pane, body in self.panes.items():
                if body["window"] == wid:
                    fields = [
                        wid,
                        str(window["index"]),
                        window["name"],
                        window["agent"],
                        pane,
                        str(body["pid"]),
                        body["role"],
                    ]
                    lines.append("\t".join(fields) + "\n")
        return "".join(lines)

    def roles(self, session: str = "sb") -> dict[str, str]:
        """Role → pane id, in the controller window."""
        return {
            body["role"]: pane
            for pane, body in self.panes.items()
            if self.windows[body["window"]]["session"] == session and body["role"]
        }

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


def outer_created(fake):
    return next(call for call in fake.find("new-session") if call[call.index("-s") + 1] == "sb")


def test_bare_deck_creates_the_pinned_window_and_attaches(fake, home, tmp_path, said):
    home(f'pin = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\nargs = ["--model", "opus"]\n')
    result = invoke("deck")
    # CliRunner has no terminal, so outside tmux it refuses to attach and says how.
    assert result.exit_code == 1 and "tmux attach -t =sb" in said(result)
    created = outer_created(fake)
    assert created[created.index("--") + 1 :] == ["claude", "--model", "opus"]
    assert created[created.index("-c") + 1] == str(tmp_path)


def test_the_inner_session_comes_first_so_the_tab_pane_has_something_to_attach_to(fake, home):
    invoke("deck")
    sessions = [call[call.index("-s") + 1] for call in fake.find("new-session")]
    assert sessions == ["sb-agents", "sb"]
    inner = fake.find("new-session")[0]
    assert "--" not in inner and inner[inner.index("-n") + 1] == "shell"


def test_bare_deck_execs_attach_at_a_terminal(fake, home, monkeypatch):
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)
    result = invoke("deck")
    assert result.exit_code == 0, result.output
    assert fake.replaced == [["tmux", "attach-session", "-t", "=sb"]]


def test_inside_tmux_the_client_switches_instead(fake, home, monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/socket,1,0")
    fake.session("sb")
    result = invoke("deck")
    assert result.exit_code == 0, result.output
    assert fake.find("switch-client") == [["tmux", "switch-client", "-t", "=sb"]]
    assert not fake.replaced and "sb" not in [c[c.index("-s") + 1] for c in fake.find("new-session")]


@pytest.mark.parametrize("current", ["sb", "sb-agents"])
def test_inside_the_deck_the_client_is_never_switched(fake, home, monkeypatch, current):
    """Switching the nested client to the outer session would draw the deck inside itself."""
    monkeypatch.setenv("TMUX", "/tmp/socket,1,0")
    fake.session("sb")
    fake.current = current
    assert invoke("deck").exit_code == 0
    assert fake.find("switch-client") == []


def test_the_deck_dresses_its_windows_and_never_the_server(fake, home):
    invoke("deck")
    options = [call[2:] for call in fake.find("set-option")]
    for wid in ("@1", "@3"):
        assert ["-w", "-t", wid, "window-size", "latest"] in options
        assert ["-w", "-t", wid, "allow-passthrough", "on"] in options
    assert not any("-g" in o or "-s" in o for o in options)


def test_mouse_is_on_for_both_sessions_and_the_tab_row_is_on_top(fake, home):
    invoke("deck")
    assert fake.options[("=sb:", "mouse")] == "on"
    assert fake.options[("=sb-agents:", "mouse")] == "on"
    assert fake.options[("=sb-agents:", "status")] == "on"
    assert fake.options[("=sb-agents:", "status-position")] == "top"
    assert ("=sb:", "status") not in fake.options


def test_extended_keys_off_is_reported_and_never_set(fake, home, said):
    fake.extended = "off"
    result = invoke("deck")
    assert "extended-keys is off" in said(result)
    assert not any("extended-keys" in call for call in fake.find("set-option"))


def test_bare_deck_refuses_json_before_touching_tmux(fake, home):
    result = invoke("--json", "deck")
    assert result.exit_code == 2 and fake.calls == []


def test_no_tmux_is_a_sentence(fake, home, said):
    fake.installed = False
    result = invoke("deck")
    assert result.exit_code == 1 and "tmux could not be run" in said(result)


def test_an_unresolvable_pin_opens_the_deck_without_it(fake, home, said):
    home('pin = "ghost"\n')
    result = invoke("deck")
    assert "pin 'ghost'" in said(result)
    created = outer_created(fake)
    assert "claude" not in created and created[created.index("--") + 1 :][:3] == ["env", "-u", "TMUX"]
    assert set(fake.roles()) == {"tabs", "queue", "messages"}


# ============================================================================
# The controller: window 0's panes and their two shapes
# ============================================================================


def test_window_zero_holds_the_workspace_tabs_queue_and_messages(fake, home, tmp_path):
    home(f'pin = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\n')
    invoke("deck")
    roles = fake.roles()
    assert set(roles) == {"agent", "tabs", "queue", "messages"}
    assert len({fake.panes[p]["window"] for p in roles.values()}) == 1


def test_every_tool_pane_runs_this_sb_by_absolute_path(fake, home):
    invoke("deck")
    sb = str(deck_.PROJECT_ROOT / "sb")
    argv = {role: fake.panes[pane]["argv"] for role, pane in fake.roles().items()}
    assert argv["queue"] == [sb, "deck", "queue", "--refresh", "5", "--screen"]
    assert argv["messages"] == [sb, "deck", "messages", "--refresh", "10", "--screen"]


def test_the_tab_pane_nests_a_client_with_tmux_unset_on_the_same_server(fake, home):
    invoke("deck")
    argv = fake.panes[fake.roles()["tabs"]]["argv"]
    assert argv == ["env", "-u", "TMUX", "tmux", "-S", "/tmp/fx-socket", "attach-session", "-t", "=sb-agents"]


def test_the_columns_plan(tmp_path):
    assert deck_.plan("columns", "%A", "%T", "%Q", "%M") == [
        ["join-pane", "-d", "-h", "-s", "%T", "-t", "%A"],
        ["join-pane", "-d", "-h", "-s", "%Q", "-t", "%T"],
        ["join-pane", "-d", "-v", "-s", "%M", "-t", "%Q"],
        ["resize-pane", "-t", "%A", "-x", "45%"],
        ["resize-pane", "-t", "%Q", "-x", "25%"],
        ["resize-pane", "-t", "%Q", "-y", "50%"],
    ]


def test_the_stack_plan():
    assert deck_.plan("stack", "%A", "%T", "%Q", "%M") == [
        ["join-pane", "-d", "-h", "-s", "%Q", "-t", "%A"],
        ["join-pane", "-d", "-v", "-s", "%M", "-t", "%Q"],
        ["join-pane", "-d", "-v", "-s", "%T", "-t", "%A"],
        ["resize-pane", "-t", "%A", "-y", "50%"],
        ["resize-pane", "-t", "%Q", "-x", "25%"],
        ["resize-pane", "-t", "%Q", "-y", "50%"],
    ]


@pytest.mark.parametrize("shape", ["columns", "stack"])
def test_with_no_pin_both_shapes_are_tabs_beside_the_tools(shape):
    assert deck_.plan(shape, None, "%T", "%Q", "%M") == [
        ["join-pane", "-d", "-h", "-s", "%Q", "-t", "%T"],
        ["join-pane", "-d", "-v", "-s", "%M", "-t", "%Q"],
        ["resize-pane", "-t", "%Q", "-x", "25%"],
        ["resize-pane", "-t", "%Q", "-y", "50%"],
    ]


def test_bare_deck_lays_a_new_controller_out_in_columns(fake, home, tmp_path):
    home(f'pin = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\n')
    invoke("deck")
    roles = fake.roles()
    moves = [call[1:] for call in fake.calls if call[1] in ("join-pane", "resize-pane")]
    assert moves == deck_.plan("columns", roles["agent"], roles["tabs"], roles["queue"], roles["messages"])
    assert fake.options[("=sb:", "@sb-layout")] == "columns"


def deck_built(fake, home, tmp_path):
    home(f'pin = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\n')
    invoke("deck")
    fake.calls.clear()


@pytest.mark.parametrize("shape", ["stack", "columns"])
def test_layout_moves_panes_and_restarts_none(fake, home, tmp_path, shape):
    deck_built(fake, home, tmp_path)
    before = {pane: dict(body) for pane, body in fake.panes.items()}
    result = invoke("--json", "deck", "layout", shape)
    assert result.exit_code == 0, result.output
    roles = fake.roles()
    moves = [call[1:] for call in fake.calls if call[1] in ("join-pane", "resize-pane")]
    assert moves == deck_.plan(shape, roles["agent"], roles["tabs"], roles["queue"], roles["messages"])
    assert fake.panes == before
    assert not {"kill-pane", "respawn-pane", "kill-window", "split-window", "new-window"} & set(fake.verbs())
    assert fake.options[("=sb:", "@sb-layout")] == shape


def test_the_deck_source_never_kills_or_respawns_a_pane():
    source = Path(deck_.__file__).read_text()
    assert not re.search(r"kill-pane|respawn-pane|kill-window|kill-session|kill-server", source)


def test_layout_puts_back_a_tool_pane_that_has_gone(fake, home, tmp_path):
    deck_built(fake, home, tmp_path)
    del fake.panes[fake.roles()["messages"]]
    result = invoke("--json", "deck", "layout", "columns")
    assert json.loads(result.stdout)["data"]["created"] == "messages"
    assert len(fake.find("split-window")) == 1 and "messages" in fake.roles()


def test_layout_without_a_deck_says_how_to_start_one(fake, home, said):
    result = invoke("deck", "layout", "stack")
    assert result.exit_code == 2 and "no deck session 'sb'" in said(result)


def test_layout_refuses_a_shape_it_does_not_have(fake, home):
    assert invoke("deck", "layout", "grid").exit_code == 2 and fake.calls == []


def test_bare_deck_on_an_existing_deck_keeps_the_operators_sizes(fake, home, tmp_path):
    deck_built(fake, home, tmp_path)
    assert invoke("deck").exit_code == 1
    assert not {"join-pane", "resize-pane", "split-window", "new-session"} & set(fake.verbs())


def test_bare_deck_rebuilds_an_inner_session_that_has_gone(fake, home, tmp_path):
    deck_built(fake, home, tmp_path)
    for pane in [p for p, b in fake.panes.items() if fake.windows[b["window"]]["session"] == "sb-agents"]:
        del fake.panes[pane]
    del fake.order["sb-agents"]
    del fake.panes[fake.roles()["tabs"]]
    invoke("deck")
    assert [c[c.index("-s") + 1] for c in fake.find("new-session")] == ["sb-agents"]
    assert "tabs" in fake.roles() and fake.find("join-pane")


# ============================================================================
# `sb deck open` — tabs in the inner session
# ============================================================================


def test_open_starts_a_tab_in_the_inner_session(fake, home, tmp_path):
    deck_built(fake, home, tmp_path)
    home(f'pin = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\n[agent.jam]\ncwd = "{tmp_path}"\n')
    result = invoke("--json", "deck", "open", "jam")
    assert result.exit_code == 0, result.output
    window = fake.find("new-window")[0]
    assert window[window.index("-t") + 1] == "=sb-agents:"
    assert window[window.index("-n") + 1] == "jam" and window[-1] == "claude"
    tab = window_of(fake, "jam")
    assert ["tmux", "set-option", "-w", "-t", tab, "@sb-agent", "jam"] in fake.calls
    controller = fake.panes[fake.roles()["tabs"]]["window"]
    assert fake.find("select-window") == [["tmux", "select-window", "-t", w] for w in (tab, controller)]
    assert json.loads(result.stdout)["data"]["session"] == "sb-agents"


def window_of(fake, agent):
    return next(wid for wid, w in fake.windows.items() if w["agent"] == agent)


def test_open_selects_a_tab_that_is_already_open(fake, home, tmp_path):
    home(f'[agent.jam]\ncwd = "{tmp_path}"\n')
    fake.session("sb")
    fake.session("sb-agents")
    tab, _ = fake.add("sb-agents", "jam", agent="jam", role="agent")
    result = invoke("--json", "deck", "open", "jam")
    assert result.exit_code == 0
    assert "new-window" not in fake.verbs()
    assert fake.find("select-window")[0] == ["tmux", "select-window", "-t", tab]


def test_open_on_the_pinned_agent_selects_it_rather_than_doubling_it(fake, home, tmp_path):
    deck_built(fake, home, tmp_path)
    result = invoke("--json", "deck", "open", "ws")
    assert result.exit_code == 0 and "new-window" not in fake.verbs()
    assert json.loads(result.stdout)["data"]["session"] == "sb"


def test_open_refuses_a_name_nobody_declared(fake, home):
    result = invoke("deck", "open", "ghost")
    assert result.exit_code == 2 and fake.calls == []


def test_open_refuses_a_cwd_that_is_not_there(fake, home, tmp_path, said):
    home(f'[agent.jam]\ncwd = "{tmp_path / "gone"}"\n')
    fake.session("sb")
    result = invoke("--json", "deck", "open", "jam")
    assert result.exit_code == 1 and "is not a directory" in said(result)
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


# ============================================================================
# `sb deck jump`
# ============================================================================


def test_jump_selects_the_tab_and_switches_inside_tmux(fake, home, monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/socket,1,0")
    fake.session("sb")
    fake.session("sb-agents")
    tab, _ = fake.add("sb-agents", "jam", agent="jam", role="agent")
    result = invoke("--json", "deck", "jump", "jam")
    assert result.exit_code == 0, result.output
    assert fake.find("select-window")[0] == ["tmux", "select-window", "-t", tab]
    assert fake.find("switch-client") == [["tmux", "switch-client", "-t", "=sb"]]


def test_jump_to_an_absent_tab_names_the_agents_there(fake, home, said):
    fake.session("sb")
    fake.session("sb-agents")
    fake.add("sb-agents", "jam", agent="jam", role="agent")
    result = invoke("deck", "jump", "ghost")
    assert result.exit_code == 2 and "agents: jam" in said(result)


def test_jump_without_a_deck_says_how_to_start_one(fake, home, said):
    result = invoke("deck", "jump", "jam")
    assert result.exit_code == 2 and "no deck session 'sb'" in said(result)


# ============================================================================
# The queue
# ============================================================================


NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
EARLIER = datetime(2026, 11, 4, 11, 0, tzinfo=timezone.utc)


def a_session(pid, status="idle", name=""):
    return Session(
        provider="claude", id=f"id-{pid}", name=name or f"s{pid}", cwd="/src", status=status, pid=pid, started=EARLIER
    )


def pane(wid, index, name, pid, role="agent"):
    return Pane(wid, index, name, name, f"%{pid}", pid, role)


def test_waiting_sorts_first_inside_the_deck_and_outside_follows():
    listed = [pane("@1", 0, "a", 10), pane("@2", 1, "b", 20), pane("@3", 2, "c", 30)]
    sessions = [a_session(10), a_session(20, "waiting"), a_session(30, "busy"), a_session(99, "waiting")]
    rows = queue_rows(listed, sessions, {}, NOW)
    assert [(r["where"], r["window"], r["status"]) for r in rows] == [
        ("deck", "b", "waiting"),
        ("deck", "a", "idle"),
        ("deck", "c", "busy"),
        ("outside", "", "waiting"),
    ]


def test_a_deck_window_with_no_record_is_unregistered_not_hidden():
    rows = queue_rows([pane("@1", 0, "jam", 10)], [], {}, NOW)
    assert [(r["window"], r["status"], r["pid"]) for r in rows] == [("jam", "unregistered", 10)]


def test_claude_under_a_shell_is_found_through_the_process_tree():
    rows = queue_rows([pane("@1", 0, "jam", 10)], [a_session(12, "waiting")], {11: 10, 12: 11, 13: 1}, NOW)
    assert [(r["where"], r["status"], r["pid"]) for r in rows] == [("deck", "waiting", 12)]


def test_a_queue_pane_alone_is_not_a_row():
    rows = queue_rows([pane("@1", 0, "queue", 10, role="queue")], [], {}, NOW)
    assert rows == []


def test_the_word_is_compared_literally():
    """`Waiting` is not `waiting` — sky.boss orders by the provider's word, it does not interpret it."""
    rows = queue_rows([], [a_session(1, "busy"), a_session(2, "Waiting")], {}, NOW)
    assert [r["status"] for r in rows] == ["busy", "Waiting"]


def test_parents_reads_ppid_past_a_comm_with_parentheses(tmp_path):
    for pid, ppid in ((10, 1), (11, 10)):
        (tmp_path / str(pid)).mkdir()
        (tmp_path / str(pid) / "stat").write_text(f"{pid} (a (b) c) S {ppid} 0 0\n")
    (tmp_path / "self").mkdir()
    assert parents(tmp_path) == {10: 1, 11: 10}
    assert tree(10, parents(tmp_path)) == [10, 11]


def test_no_proc_is_an_empty_tree_not_an_error(tmp_path):
    assert parents(tmp_path / "absent") == {}


class Adapter:
    provider = "claude"

    def __init__(self, sessions, present=True):
        self.sessions, self.present = sessions, present

    def scan(self):
        return Scan(provider="claude", sessions=list(self.sessions), present=self.present, read=len(self.sessions))


def test_the_envelope_carries_an_authored_view(fake, home, tmp_path):
    fake.add("sb", "jam", agent="jam", role="agent", pid=10)
    result = queue_result([Adapter([a_session(10, "waiting")])], proc=tmp_path / "absent")
    assert result.ok and result.view["authored"] is True
    assert [c["key"] for c in result.view["columns"]] == ["where", "window", "status", "name", "up", "cwd"]
    assert result.data[0]["status"] == "waiting"


def test_the_queue_finds_agents_in_the_tabs_and_beside_the_tools(fake, home, tmp_path):
    controller, _ = fake.add("sb", "ws", agent="ws", role="agent", pid=10)
    for role in ("tabs", "queue", "messages"):
        fake.panes[fake._new_pane(controller)]["role"] = role
    fake.add("sb-agents", "shell", role="shell", pid=20)
    fake.add("sb-agents", "jam", agent="jam", role="agent", pid=30)
    sessions = [a_session(10), a_session(30, "waiting")]
    result = queue_result([Adapter(sessions)], proc=tmp_path / "absent")
    assert [(r["where"], r["window"], r["status"]) for r in result.data] == [
        ("deck", "jam", "waiting"),
        ("deck", "ws", "idle"),
    ]


def test_no_tmux_is_partial_and_still_lists_every_session(fake, home, tmp_path):
    fake.installed = False
    result = queue_result([Adapter([a_session(10)])], proc=tmp_path / "absent")
    assert result.partial and [r["where"] for r in result.data] == ["outside"]


def test_an_empty_queue_says_what_it_looked_at(fake, home, tmp_path):
    result = queue_result([Adapter([], present=False)], proc=tmp_path / "absent")
    assert result.data == []
    assert any("no deck session" in w for w in result.warnings)
    assert any("no registry present" in w for w in result.warnings)


def test_queue_refuses_ticks_without_refresh(fake, home):
    assert invoke("deck", "queue", "--ticks", "2").exit_code == 2


def test_queue_refresh_off_a_terminal_is_ndjson(fake, home, monkeypatch):
    monkeypatch.setattr(deck_.agents_, "providers", lambda: [Adapter([a_session(10)])])
    monkeypatch.setattr(output, "resident_ndjson", functools.partial(output.resident_ndjson, sleep=lambda s: None))
    result = invoke("deck", "queue", "--refresh", "1", "--ticks", "2")
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    assert result.exit_code == 0 and [line["tick"] for line in lines] == [1, 2]


def test_the_queue_is_an_observe_and_the_rest_act():
    acts = {name: getattr(command, "sb_acts") for name, command in deck_.deck.commands.items()}
    assert acts == {"open": True, "jump": True, "layout": True, "queue": False, "messages": False}
