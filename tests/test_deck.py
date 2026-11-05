"""`sb deck` — the tmux command center. See [[command-deck]].

**No test here runs tmux.** Every call goes through `skyboss.deck.RUNNER`, which
`FakeTmux` replaces; it records argv and answers from a small model of a server.
"""

from __future__ import annotations

import functools
import json
import re
import shlex
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


ROOT_KEYS = (
    "bind-key    -T root   MouseDown1Pane     select-pane -t = \\; send-keys -M\n"
    "bind-key    -T root   MouseDown1Status   switch-client -t =\n"
    "bind-key    -T root   MouseDrag1Border   resize-pane -M\n"
    "bind-key -r -T root   C-c                display-message fx-operator-binding\n"
)


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
        self.sourced: list[str] = []

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
        if verb == "list-keys":
            return Answer(asked=True, out=ROOT_KEYS)
        if verb == "source-file":
            self.sourced.append(Path(args[-1]).read_text())
            return Answer(asked=True)
        if verb == "kill-session":
            name = target.lstrip("=")
            for wid in self.order.pop(name, []):
                for pane in [p for p, b in self.panes.items() if b["window"] == wid]:
                    del self.panes[pane]
            return Answer(asked=True)
        if verb == "swap-window":
            a, b = self.windows[args[args.index("-s") + 1]], self.windows[target]
            a["index"], b["index"] = b["index"], a["index"]
            return Answer(asked=True)
        if verb == "break-pane":
            pane = args[args.index("-s") + 1]
            session = target.strip("=:")
            self.serial += 1
            wid = f"@{self.serial}"
            self.order.setdefault(session, []).append(wid)
            index = max((self.windows[w]["index"] for w in self.order[session] if w in self.windows), default=-1) + 1
            self.windows[wid] = {"session": session, "index": index, "name": args[args.index("-n") + 1], "agent": ""}
            self.panes[pane]["window"] = wid
            return Answer(asked=True, out=f"{wid}\n")
        if verb == "set-option":
            if "-u" in args:
                self.windows[args[args.index("-t") + 1]]["agent"] = ""
                return Answer(asked=True)
            if args[:1] == ["-p"] and args[3] == "@sb-deck":
                self.panes[args[2]]["role"] = args[4]
            elif args[:1] == ["-w"] and args[3] == "@sb-agent":
                self.windows[args[2]]["agent"] = args[4]
            elif args[:1] == ["-w"]:
                self.windows[args[2]].setdefault("opts", {})[args[3]] = args[4]
            elif args[0] == "-t":
                if not args[1].endswith(":"):
                    # Real tmux reads a pane target here and refuses a bare `=name`.
                    return Answer(asked=True, code=1, err=f"no such session: {args[1]}\n")
                self.options[(args[1], args[2])] = args[3]
            return Answer(asked=True)
        if verb == "list-panes":
            return Answer(asked=True, out=self.listing(target.lstrip("=")))
        if verb == "show-options":
            if args == ["-t", target]:
                listed = [f"{name} {value}" for (where, name), value in self.options.items() if where == target]
                return Answer(asked=True, out="\n".join(listed) + "\n")
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
        for wid in sorted(self.order.get(session, []), key=lambda w: self.windows[w]["index"]):
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

    def tabs(self) -> list[str]:
        """The inner session's window names, in tab order."""
        order = sorted(self.order.get("sb-agents", []), key=lambda w: self.windows[w]["index"])
        return [self.windows[w]["name"] for w in order]

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


def created_in(fake, session):
    return next(call for call in fake.find("new-session") if call[call.index("-s") + 1] == session)


def test_bare_deck_opens_the_pin_as_the_first_tab_and_attaches(fake, home, tmp_path, said):
    home(f'pin = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\nargs = ["--model", "opus"]\n')
    result = invoke("deck")
    # CliRunner has no terminal, so outside tmux it refuses to attach and says how.
    assert result.exit_code == 1 and "tmux attach -t =sb" in said(result)
    created = created_in(fake, "sb-agents")
    assert created[created.index("--") + 1 :] == ["claude", "--model", "opus"]
    assert created[created.index("-c") + 1] == str(tmp_path)
    assert fake.tabs() == ["ws"]


def test_the_tabs_session_comes_first_so_the_tab_pane_has_something_to_attach_to(fake, home):
    invoke("deck")
    assert [call[call.index("-s") + 1] for call in fake.find("new-session")] == ["sb-agents", "sb"]
    assert fake.tabs() == ["shell"] and "--" not in created_in(fake, "sb-agents")


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


def test_the_deck_dresses_every_window_it_made_and_never_the_server(fake, home):
    invoke("deck")
    options = [call[2:] for call in fake.find("set-option")]
    for wid in fake.windows:
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
    assert "pin 'ghost'" in said(result) and "no tab" in said(result)
    assert fake.tabs() == ["shell"]
    assert set(fake.roles()) == {"tabs", "queue", "messages"}


# ============================================================================
# Profiles
# ============================================================================


PROFILE = """
[profile.core]
primary = "ws"
tabs = ["jam", "mind", "ws", "jam"]
[agent.ws]
cwd = "{d}"
[agent.jam]
cwd = "{d}"
[agent.mind]
cwd = "{d}"
"""


def test_a_profile_parses_with_its_order():
    config, problems = parse({"profile": {"core": {"primary": "ws", "tabs": ["jam", "mind"]}}})
    assert problems == [] and config.profiles["core"].order() == (["ws", "jam", "mind"], [])


@pytest.mark.parametrize(
    "body, phrase",
    [
        ({"primary": 3}, "primary must be an agent name"),
        ({"tabs": "jam"}, "tabs must be a list"),
        ({"tabs": [""]}, "tabs must be a list"),
        ({}, "names no primary and no tabs"),
        ("core", "not a table"),
    ],
)
def test_a_bad_profile_is_skipped_and_named(body, phrase):
    config, problems = parse({"profile": {"core": body}})
    assert "core" not in config.profiles and any(phrase in p for p in problems)


def test_an_unknown_profile_key_is_named_and_the_profile_kept():
    config, problems = parse({"profile": {"core": {"primary": "ws", "pin": "x"}}})
    assert "core" in config.profiles and problems == ["profile 'core': unknown key 'pin' — ignored"]


def test_a_repeated_name_is_one_tab_and_a_warning():
    names, problems = deck_.Profile("core", "ws", ["jam", "ws", "jam"]).order()
    assert names == ["ws", "jam"] and len(problems) == 2 and "listed twice — one tab" in problems[0]


def test_pin_is_a_profile_with_a_primary_and_no_tabs():
    assert Config(pin="ws").profile(None) == deck_.Profile("pin", "ws", [])
    assert Config().profile(None) is None


def test_a_profile_opens_its_tabs_in_order_primary_first(fake, home, tmp_path, said):
    home(PROFILE.format(d=tmp_path))
    result = invoke("deck", "--profile", "core")
    assert fake.tabs() == ["ws", "jam", "mind"]
    assert said(result).count("listed twice") == 2


def test_a_profile_on_a_live_deck_opens_only_what_is_missing_and_restores_the_order(fake, home, tmp_path):
    home(PROFILE.format(d=tmp_path))
    fake.session("sb")
    fake.add("sb-agents", "shell", role="shell")
    fake.add("sb-agents", "mind", agent="mind", role="agent")
    invoke("deck", "--profile", "core")
    assert [c[c.index("-n") + 1] for c in fake.find("new-window")] == ["ws", "jam"]
    assert fake.tabs() == ["ws", "jam", "mind", "shell"]
    assert fake.find("swap-window")
    fake.calls.clear()
    invoke("deck", "--profile", "core")
    assert not {"new-window", "swap-window", "new-session"} & set(fake.verbs())


def test_an_unresolvable_tab_is_a_warning_and_no_tab(fake, home, tmp_path, said):
    home(PROFILE.format(d=tmp_path) + '[profile.more]\ntabs = ["ghost", "jam"]\n')
    result = invoke("deck", "--profile", "more")
    assert "profile 'more' 'ghost'" in said(result) and fake.tabs() == ["jam"]


def test_an_unknown_profile_names_the_known_ones(fake, home, tmp_path, said):
    home(PROFILE.format(d=tmp_path))
    result = invoke("deck", "--profile", "nope")
    assert result.exit_code == 2 and "profiles: core" in said(result) and fake.calls == []


def test_profile_is_refused_beside_a_subcommand(fake, home):
    assert invoke("deck", "--profile", "core", "queue").exit_code == 2


# ============================================================================
# The controller: window 0's panes and their two shapes
# ============================================================================


def test_window_zero_is_the_tabs_and_the_tools_only(fake, home, tmp_path):
    home(f'pin = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\n')
    invoke("deck")
    roles = fake.roles()
    assert set(roles) == {"tabs", "queue", "messages"}
    assert len({fake.panes[p]["window"] for p in roles.values()}) == 1
    assert set(fake.roles("sb-agents")) == {"agent"}


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


def test_the_columns_plan():
    assert deck_.plan("columns", "%T", "%Q", "%M") == [
        ["join-pane", "-d", "-h", "-s", "%Q", "-t", "%T"],
        ["join-pane", "-d", "-v", "-s", "%M", "-t", "%Q"],
        ["resize-pane", "-t", "%Q", "-x", "25%"],
        ["resize-pane", "-t", "%Q", "-y", "50%"],
    ]


def test_the_stack_plan():
    assert deck_.plan("stack", "%T", "%Q", "%M") == [
        ["join-pane", "-d", "-v", "-s", "%Q", "-t", "%T"],
        ["join-pane", "-d", "-h", "-s", "%M", "-t", "%Q"],
        ["resize-pane", "-t", "%Q", "-y", "30%"],
        ["resize-pane", "-t", "%Q", "-x", "50%"],
    ]


def test_a_plan_with_no_tools_moves_nothing():
    assert deck_.plan("columns", "%T", None, None) == []


def test_bare_deck_lays_a_new_controller_out_in_columns(fake, home):
    invoke("deck")
    roles = fake.roles()
    moves = [call[1:] for call in fake.calls if call[1] in ("join-pane", "resize-pane")]
    assert moves == deck_.plan("columns", roles["tabs"], roles["queue"], roles["messages"])
    assert fake.options[("=sb:", "@sb-layout")] == "columns"


def deck_built(fake, home, tmp_path):
    home(f'pin = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\n[agent.jam]\ncwd = "{tmp_path}"\n')
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
    assert moves == deck_.plan(shape, roles["tabs"], roles["queue"], roles["messages"])
    assert fake.panes == before
    assert not {"kill-pane", "respawn-pane", "kill-window", "split-window", "new-window"} & set(fake.verbs())
    assert fake.options[("=sb:", "@sb-layout")] == shape


def test_the_deck_source_never_kills_or_respawns_a_pane():
    source = Path(deck_.__file__).read_text()
    assert not re.search(r"kill-pane|respawn-pane|kill-window|kill-server", source)


def test_kill_session_appears_only_in_the_exit_command():
    """Recomputed from the source: every `kill-session` literal sits inside `end_sessions`."""
    import ast

    tree = ast.parse(Path(deck_.__file__).read_text())
    owners = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for inner_node in ast.walk(node):
                if isinstance(inner_node, ast.Constant) and "kill-session" in str(inner_node.value):
                    owners.add(node.name)
    assert owners == {"end_sessions"}


def test_a_round_two_pinned_pane_moves_into_the_tabs_with_its_process(fake, home, tmp_path):
    controller, agent = fake.add("sb", "deck", agent="ws", role="agent", pid=4242)
    for role in ("tabs", "queue", "messages"):
        fake.panes[fake._new_pane(controller)]["role"] = role
    fake.session("sb-agents")
    invoke("deck")
    (moved,) = fake.find("break-pane")
    assert moved[moved.index("-s") + 1] == agent and moved[moved.index("-t") + 1] == "=sb-agents:"
    assert fake.panes[agent]["pid"] == 4242 and "ws" in fake.tabs()
    assert fake.windows[controller]["agent"] == "" and fake.find("join-pane")


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
    assert not {"join-pane", "resize-pane", "split-window", "new-session", "new-window"} & set(fake.verbs())


def test_bare_deck_rebuilds_a_tabs_session_that_has_gone(fake, home, tmp_path):
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


def window_of(fake, agent):
    return next(wid for wid, w in fake.windows.items() if w["agent"] == agent)


def test_open_starts_a_tab_in_the_inner_session(fake, home, tmp_path):
    deck_built(fake, home, tmp_path)
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


def test_open_selects_a_tab_that_is_already_open(fake, home, tmp_path):
    home(f'[agent.jam]\ncwd = "{tmp_path}"\n')
    fake.session("sb")
    fake.session("sb-agents")
    tab, _ = fake.add("sb-agents", "jam", agent="jam", role="agent")
    result = invoke("--json", "deck", "open", "jam")
    assert result.exit_code == 0
    assert "new-window" not in fake.verbs()
    assert fake.find("select-window")[0] == ["tmux", "select-window", "-t", tab]


def test_open_on_the_pinned_agent_selects_its_tab_rather_than_doubling_it(fake, home, tmp_path):
    deck_built(fake, home, tmp_path)
    result = invoke("--json", "deck", "open", "ws")
    assert result.exit_code == 0 and "new-window" not in fake.verbs()
    assert fake.find("select-window")[0][-1] == window_of(fake, "ws")


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
    assert acts == {
        "open": True,
        "jump": True,
        "layout": True,
        "marks": True,
        "exit": True,
        "queue": False,
        "messages": False,
    }


# ============================================================================
# Tab marks: one writer, window options, the theme
# ============================================================================


def tabbed(fake):
    """A deck with two agent tabs and a shell, by pid."""
    fake.session("sb")
    fake.add("sb-agents", "shell", role="shell", pid=5)
    jam, _ = fake.add("sb-agents", "jam", agent="jam", role="agent", pid=10)
    mind, _ = fake.add("sb-agents", "mind", agent="mind", role="agent", pid=20)
    return jam, mind


def state(fake, wid):
    return fake.windows[wid].get("opts", {}).get("@sb-state")


def test_marks_write_each_tabs_registry_word_once(fake, home, monkeypatch):
    jam, mind = tabbed(fake)
    monkeypatch.setattr(deck_, "parents", lambda proc=None: {})
    written: dict[str, str] = {}
    result = deck_.marks_once("sb", written, [Adapter([a_session(10, "busy")])])
    assert (state(fake, jam), state(fake, mind)) == ("busy", "unregistered")
    assert [r["state"] for r in result.data] == ["busy", "unregistered"]
    assert ("=sb-agents:", "@sb-marked") in fake.options
    fake.calls.clear()
    deck_.marks_once("sb", written, [Adapter([a_session(10, "busy")])])
    assert [c for c in fake.find("set-option") if "@sb-state" in c] == []
    deck_.marks_once("sb", written, [Adapter([a_session(10, "waiting")])])
    assert [c[-1] for c in fake.find("set-option") if "@sb-state" in c] == ["waiting"]


def test_a_shell_tab_gets_no_mark(fake, home, monkeypatch):
    tabbed(fake)
    monkeypatch.setattr(deck_, "parents", lambda proc=None: {})
    deck_.marks_once("sb", {}, [Adapter([])])
    shell = next(w for w, body in fake.windows.items() if body["name"] == "shell")
    assert state(fake, shell) is None


def test_marks_without_a_deck_fail_and_write_nothing(fake, home):
    result = deck_.marks_once("sb", {}, [Adapter([])])
    assert result.ok is False and "set-option" not in fake.verbs()


def test_the_marks_loop_records_its_pid_and_stops_at_its_bound(fake, home, monkeypatch):
    tabbed(fake)
    naps: list[float] = []
    monkeypatch.setattr(deck_, "SLEEP", naps.append)
    monkeypatch.setattr(deck_.agents_, "providers", lambda: [])
    result = invoke("deck", "marks", "--every", "3", "--ticks", "3")
    assert result.exit_code == 0, result.output
    assert naps == [3, 3]
    assert fake.options[("=sb-agents:", "@sb-marks-pid")].isdigit()


def test_the_marks_loop_ends_when_the_deck_is_gone(fake, home, monkeypatch):
    naps: list[float] = []
    monkeypatch.setattr(deck_, "SLEEP", naps.append)
    assert invoke("deck", "marks", "--every", "3").exit_code == 0 and naps == []


def test_the_marks_loop_yields_to_another_live_loop(fake, home, monkeypatch):
    tabbed(fake)
    monkeypatch.setattr(deck_, "_marks_owner", lambda session, proc=None: 1)
    monkeypatch.setattr(deck_, "SLEEP", lambda s: pytest.fail("slept"))
    assert invoke("deck", "marks", "--every", "3").exit_code == 0
    assert not [c for c in fake.find("set-option") if "@sb-state" in c]


def test_marks_ticks_needs_every(fake, home):
    assert invoke("deck", "marks", "--ticks", "2").exit_code == 2


def test_the_deck_starts_one_marks_job_on_its_own_server(fake, home):
    invoke("deck")
    (job,) = fake.find("run-shell")
    sb = str(deck_.PROJECT_ROOT / "sb")
    assert job[2] == "-b" and job[3] == f"exec {shlex.quote(sb)} deck marks --every 3 >/dev/null 2>&1"


def test_a_live_marks_loop_is_not_started_twice(fake, home, monkeypatch):
    monkeypatch.setattr(deck_, "_marks_owner", lambda session, proc=None: 77)
    invoke("deck")
    assert fake.find("run-shell") == []


def test_the_marks_owner_must_be_a_live_marks_process(fake, home, tmp_path):
    fake.session("sb-agents")
    fake.options[("=sb-agents:", "@sb-marks-pid")] = "123"
    (tmp_path / "123").mkdir()
    (tmp_path / "123" / "cmdline").write_bytes(b"python\0-m\0skyboss\0deck\0marks\0")
    assert deck_._marks_owner("sb", tmp_path) == 123
    (tmp_path / "123" / "cmdline").write_bytes(b"bash\0")
    assert deck_._marks_owner("sb", tmp_path) is None
    assert deck_._marks_owner("sb", tmp_path / "absent") is None


def test_a_tab_format_draws_each_word_and_leaves_status_format_alone(fake, home):
    invoke("deck")
    tab = deck_.tab_format(False)
    for word, label in (
        ("busy", "working"),
        ("waiting", "needs you"),
        ("idle", "quiet"),
        ("unregistered", "unregistered"),
    ):
        assert f"#{{==:#{{@sb-state}},{word}}}" in tab and label in tab
    assert not any("status-format" in c for c in fake.find("set-option"))


def test_tmux_styles_carry_no_comma_and_only_design_system_hues():
    from skyboss import theme

    tokens = {
        theme.BG,
        theme.SURFACE,
        theme.SURFACE_2,
        theme.TEXT,
        theme.TEXT_2,
        theme.TEXT_3,
        theme.BRAND,
        theme.WARN,
        theme.DANGER,
    }
    for style in theme.tmux_styles().values():
        assert "," not in style
        assert set(re.findall(r"#[0-9a-f]{6}", style)) <= tokens


def test_the_theme_lands_on_the_decks_own_sessions_and_windows_only(fake, home):
    invoke("deck")
    calls = fake.find("set-option")
    assert not any("-g" in c for c in calls)
    styled = {(c[c.index("-t") + 1], c[-2]) for c in calls if "status-style" in c or "pane-active-border-style" in c}
    assert ("=sb:", "status-style") in styled and ("=sb-agents:", "status-style") in styled
    window_targets = {target for target, option in styled if option == "pane-active-border-style"}
    assert window_targets == set(fake.windows)


@pytest.mark.parametrize(
    ("scope", "where"), [("deck", ["deck"]), ("outside", ["outside"]), ("all", ["deck", "outside"])]
)
def test_queue_scope_keeps_one_side(fake, home, tmp_path, scope, where):
    fake.add("sb", "jam", agent="jam", role="agent", pid=10)
    result = queue_result([Adapter([a_session(10), a_session(99)])], proc=tmp_path / "absent", scope=scope)
    assert [r["where"] for r in result.data] == where


def test_queue_scope_empty_says_which_side(fake, home, tmp_path):
    result = queue_result([Adapter([a_session(99)])], proc=tmp_path / "absent", scope="deck")
    assert result.data == [] and "no sessions in the deck" in result.warnings


def test_queue_scope_reaches_the_resident_read(fake, home, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        deck_, "_resident", lambda source, once, *rest: seen.setdefault("scope", once.keywords["scope"])
    )
    invoke("deck", "queue", "--scope", "outside")
    assert seen == {"scope": "outside"}


def test_claimed_reads_both_deck_sessions(fake, home, monkeypatch):
    monkeypatch.setattr(deck_, "parents", lambda proc=None: {})
    fake.add("sb", "deck", role="tabs", pid=1)
    fake.add("sb-agents", "jam", agent="jam", role="agent", pid=10)
    assert deck_.claimed([a_session(10), a_session(11)]) == ({"id-10"}, "")
    fake.installed = False
    assert deck_.claimed([])[0] is None


# ============================================================================
# Round 4: the deck's key table, exit, shortcuts
# ============================================================================


def test_the_key_table_is_set_on_the_two_deck_sessions_only(fake, home):
    invoke("deck")
    tables = {(c[c.index("-t") + 1], c[-1]) for c in fake.find("set-option") if "key-table" in c}
    assert tables == {("=sb:", "sb-deck-sb"), ("=sb-agents:", "sb-deck-sb")}


def test_every_binding_lands_in_the_decks_table_and_nothing_is_global(fake, home):
    invoke("deck")
    for call in fake.find("bind-key"):
        assert call[2:4] == ["-T", "sb-deck-sb"], call
    assert not any("-g" in call for call in fake.calls if call[1] in ("set-option", "bind-key"))
    (sourced,) = fake.sourced
    assert all(" -T sb-deck-sb " in line for line in sourced.splitlines())


def test_root_is_copied_so_the_mouse_still_works_in_the_deck():
    copied = deck_.mirrored_root(ROOT_KEYS, "sb-deck-sb")
    assert "-T sb-deck-sb   MouseDown1Pane     select-pane -t = \\; send-keys -M" in copied
    assert "MouseDrag1Border" in copied and " root " not in copied


def test_ctrl_c_is_never_bound(fake, home):
    """Ctrl-C is claude's own: one press interrupts a turn, two end it."""
    invoke("deck")
    bound = [call[4] for call in fake.find("bind-key")]
    assert "C-c" not in bound and "C-c" not in "".join(fake.sourced)
    assert not any(argv[3] == "C-c" for argv in deck_.deck_bindings("sb"))


def test_exit_asks_first_and_names_what_ends():
    (ctrl_q,) = [argv for argv in deck_.deck_bindings("sb") if argv[3] == "C-q"]
    assert ctrl_q[4:6] == ["confirm-before", "-p"]
    assert ctrl_q[6] == "end the deck sb and its #{@sb-agent-count} agent sessions? (y/n)"
    assert "deck exit" in ctrl_q[7]


def test_the_close_box_asks_and_any_other_status_click_still_selects():
    (click_,) = [argv for argv in deck_.deck_bindings("sb") if argv[3] == "MouseDown1Status"]
    assert click_[4:7] == ["if-shell", "-F", "#{==:#{mouse_status_range},exit}"]
    assert click_[7].startswith("confirm-before") and click_[8] == "switch-client -t ="


def test_the_bar_shows_every_shortcut_and_the_close_box():
    bar = deck_.hints()
    for key in (*deck_.SHORTCUTS.values(), "C-q"):
        assert key in bar
    assert "#[range=user|exit]" in bar and "✕" in bar


def test_exit_stops_the_marks_loop_then_kills_exactly_the_two_deck_sessions(fake, home, monkeypatch):
    tabbed(fake)
    fake.session("work")
    killed = []
    monkeypatch.setattr(deck_, "_marks_owner", lambda session, proc=None: 4321)
    monkeypatch.setattr(deck_.os, "kill", lambda pid, sig: killed.append(pid))
    result = invoke("--json", "deck", "exit")
    assert result.exit_code == 0, result.output
    assert killed == [4321]
    assert [c[3] for c in fake.find("kill-session")] == ["=sb-agents", "=sb"]
    assert fake.sessions == {"work"}
    assert json.loads(result.stdout)["data"]["agents"] == 2


def test_exit_without_a_deck_is_a_usage_error(fake, home):
    assert invoke("deck", "exit").exit_code == 2 and "kill-session" not in fake.verbs()


def test_the_shortcuts_drive_tmux_alone():
    """Every shortcut is a tmux command or the deck's own `sb`; none types into a pane."""
    for argv in deck_.deck_bindings("sb"):
        assert argv[4] in ("confirm-before", "if-shell", "set-option", "previous-window", "next-window")


def test_a_scroll_key_binds_both_its_commands():
    """A bare `;` ends the bind-key and runs the rest at once; an escaped one stays in the binding."""
    (older,) = [argv for argv in deck_.deck_bindings("sb") if argv[3] == "M-u"]
    assert "\\;" in older and ";" not in older
    assert older[-1] == "#{e|+:#{@sb-scroll-seq},1}"


# ============================================================================
# Round 4: the panes' view state — scroll, the outside toggle
# ============================================================================


def rows_of_n(n):
    return Result_(data=[{"n": i, "where": "deck" if i % 2 else "outside"} for i in range(n)])


def Result_(**kwargs):
    from skyboss.output import Result

    return Result(**kwargs)


def test_the_messages_fit_follows_the_offset_and_says_where_it_is():
    pane = deck_.DeckPane("sb", lambda row: True, scroll=True)
    fit = deck_.keep_last("message(s)", pane)
    shown, marker = fit(rows_of_n(30), 10)
    assert [r["n"] for r in shown.data] == list(range(20, 30)) and marker == "newest · 20 earlier message(s) not shown"
    pane.move("pgup")
    shown, marker = fit(rows_of_n(30), 10)
    assert [r["n"] for r in shown.data] == list(range(10, 20))
    assert marker == "↑ 10 back · 10 earlier · End or M-e: newest"
    pane.move("home")
    assert [r["n"] for r in fit(rows_of_n(30), 10)[0].data] == list(range(0, 10)) and pane.offset == 20
    assert pane.move("end") and fit(rows_of_n(30), 10)[1].startswith("newest")


def test_scroll_keys_move_by_line_page_and_wheel():
    pane = deck_.DeckPane("sb", lambda row: True, scroll=True)
    pane.page = 7
    for key, offset in (
        ("up", 1),
        ("wheelup", 4),
        ("pgup", 11),
        ("down", 10),
        ("wheeldown", 7),
        ("pgdn", 0),
        ("pgdn", 0),
    ):
        pane.on_key(key)
        assert pane.offset == offset, key
    assert pane.on_key("q") is False


def test_a_pane_that_does_not_scroll_takes_no_keys():
    pane = deck_.DeckPane("sb", lambda row: True)
    assert pane.on_key("up") is False and pane.offset == 0 and not pane.counted


def test_a_shortcut_is_adopted_on_the_next_frame_and_not_at_start(fake, home):
    fake.session("sb")
    fake.options[("=sb:", "@sb-scroll")] = "older"
    fake.options[("=sb:", "@sb-scroll-seq")] = "4"
    pane = deck_.DeckPane("sb", lambda row: True, scroll=True)
    pane.shape(rows_of_n(3))
    assert pane.offset == 0
    fake.options[("=sb:", "@sb-scroll-seq")] = "5"
    pane.shape(rows_of_n(3))
    assert pane.offset == pane.page
    fake.options[("=sb:", "@sb-scroll")] = "newest"
    fake.options[("=sb:", "@sb-scroll-seq")] = "6"
    pane.shape(rows_of_n(3))
    assert pane.offset == 0


@pytest.mark.parametrize(
    "keeps",
    [lambda row: row.get("where") == "deck", lambda row: bool(row.get("from_agent") or row.get("to_agent"))],
    ids=["queue", "messages"],
)
def test_both_panes_read_the_one_outside_toggle(fake, home, keeps):
    fake.session("sb")
    pane = deck_.DeckPane("sb", keeps)
    rows = Result_(data=[{"where": "deck", "from_agent": "jam"}, {"where": "outside"}])
    assert len(pane.shape(rows).data) == 2
    fake.options[("=sb:", "@sb-hide-outside")] = "1"
    shaped = pane.shape(rows)
    assert len(shaped.data) == 1 and "1 outside row(s) hidden — M-h shows them" in shaped.warnings


def test_the_tool_panes_are_handed_their_control(fake, home, monkeypatch):
    seen = []
    monkeypatch.setattr(deck_, "_resident", lambda source, once, *rest: seen.append((source, rest[-1])))
    invoke("deck", "queue", "--refresh", "5")
    invoke("deck", "messages", "--refresh", "5")
    (queue_source, queue_pane), (messages_source, messages_pane) = seen
    assert not queue_pane.wheel and messages_pane.wheel and messages_pane.counted


# ============================================================================
# Round 4: agent colours
# ============================================================================


def test_slots_follow_tab_order_with_the_primary_first(fake):
    fake.add("sb-agents", "ws", agent="ws", role="agent")
    fake.add("sb-agents", "shell", role="shell")
    fake.add("sb-agents", "jam", agent="jam", role="agent")
    listed = parse_panes(fake.listing("sb-agents"))
    slots = deck_.agent_slots(listed)
    names = {fake.windows[w]["name"]: slot for w, slot in slots.items()}
    assert names == {"ws": 0, "jam": 1}


def test_tab_colours_are_written_once_and_read_by_the_tab_format(fake):
    ws, _ = fake.add("sb-agents", "skyrow-workspace", agent="skyrow-workspace", role="agent")
    mind, _ = fake.add("sb-agents", "mind-head", agent="mind-head", role="agent")
    scratch, _ = fake.add("sb-agents", "scratch", agent="scratch", role="agent")
    from skyboss import theme

    written: dict[str, str] = {}
    deck_.write_colours("sb", parse_panes(fake.listing("sb-agents")), written)
    assert fake.windows[ws]["opts"]["@sb-colour"] == theme.BRAND
    assert fake.windows[mind]["opts"]["@sb-colour"] == theme.PRODUCT_HUES["mh"]
    assert fake.windows[scratch]["opts"]["@sb-colour"] == theme.AGENT_COLOURS[2]
    fake.calls.clear()
    deck_.write_colours("sb", parse_panes(fake.listing("sb-agents")), written)
    assert fake.find("set-option") == []


def test_a_tab_is_its_hue_and_the_active_tab_a_block_of_it():
    from skyboss import theme

    assert "#{?#{@sb-colour},#[fg=#{@sb-colour} bold],} #W " in deck_.tab_format(False)
    block = f"#[{theme.tmux_styles()['on-hue']} bg=#{{@sb-colour}}]"
    assert f"#{{?#{{@sb-colour}},{block},}} #W " in deck_.tab_format(True)


def test_the_messages_pane_colours_a_name_exactly_as_its_tab_is_coloured():
    from skyboss import theme
    from skyboss.messages import Message, rows_of

    message = Message(at=NOW, sender="jam-sense", receiver="ws", body="hi", msg_id="m", session="s", key="m")
    placed = {"ws": ("skyrow-workspace", 0), "jam-sense": ("jam-sense", 3)}
    (row,) = rows_of([message], NOW, placed, paint=True)
    assert row["between_parts"] == [["jam-sense", "sb.agent.js"], [" → ", "sb.muted"], ["ws", "sb.agent.brand"]]
    assert theme.STYLES["sb.agent.js"] == f"bold {theme.agent_colour('jam-sense', 3)}"
    (unpainted,) = rows_of([message], NOW, placed)
    assert unpainted["between_parts"][0] == ["jam-sense", None] and unpainted["from_agent"] == "jam-sense"
    (outside,) = rows_of([message], NOW, {}, paint=True)
    assert outside["between_parts"][0] == ["jam-sense", None] and outside["from_agent"] == ""


def test_the_tool_panes_are_painted_and_the_tabs_are_not(fake, home):
    from skyboss import theme

    invoke("deck")
    painted = {c[4] for c in fake.find("set-option") if "window-style" in c or "window-active-style" in c}
    roles = fake.roles()
    assert painted == {roles["queue"], roles["messages"]}
    assert all(c[-1] == theme.tmux_styles()["pane"] for c in fake.find("set-option") if "window-style" in c)
    assert not any("-g" in c or "-w" in c for c in fake.find("set-option") if "window-style" in c)


def test_messages_are_painted_only_in_the_pane(fake, home, monkeypatch):
    seen = []
    monkeypatch.setattr(deck_, "_resident", lambda source, once, *rest: seen.append(once.keywords["paint"]))
    invoke("deck", "messages")
    invoke("deck", "messages", "--refresh", "5")
    invoke("deck", "messages", "--refresh", "5", "--screen")
    assert seen == [False, False, True]


def test_the_agent_ramp_is_the_canvas_project_ramp():
    """Recomputed from sb.css, so the canvas and the deck cannot part."""
    from skyboss import theme

    css = (Path(deck_.__file__).parent / "canvas" / "static" / "sb.css").read_text()
    names = {"text": theme.TEXT, "surface-2": theme.SURFACE_2, "ok": theme.OK}
    found: list[tuple[str | None, float]] = [(None, 1.0)]
    for partner, weight in re.findall(
        r"\.pl-s[1-9] \{ --pl-ink: color-mix\(in oklab, var\(--sb-brand\) (\d+)%, var\(--sb-([a-z0-9-]+)\)\); \}", css
    ):
        found.append((names[weight], int(partner) / 100))
    assert tuple(found) == theme.AGENT_RECIPES


def test_an_empty_option_as_tmux_prints_it_is_empty():
    parsed = deck_.session_options("@sb-hide-outside ''\n@sb-scroll older\n@sb-x \"a b\"\n")
    assert parsed == {"@sb-hide-outside": "", "@sb-scroll": "older", "@sb-x": "a b"}
