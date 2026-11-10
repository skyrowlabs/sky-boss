"""`sb deck` — the tmux command center. See [[command-deck]].

**No test here runs tmux.** Every call goes through `skyboss.deck.RUNNER`, which
`FakeTmux` replaces; it records argv and answers from a small model of a server.
"""

from __future__ import annotations

import functools
import json
import re
import shlex
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from skyboss import background
from skyboss import chrome as chrome_
from skyboss import cli
from skyboss import deck as deck_
from skyboss import output, todos
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
            if args[:2] == ["-u", "-t"] and args[2].endswith(":"):
                self.options.pop((args[2], args[3]), None)
                return Answer(asked=True)
            if "-u" in args:
                self.windows[args[args.index("-t") + 1]]["agent"] = ""
                return Answer(asked=True)
            if args[:1] == ["-p"] and args[3] == "@sb-deck":
                self.panes[args[2]]["role"] = args[4]
            elif args[:1] == ["-w"] and args[3] == "@sb-agent":
                self.windows[args[2]]["agent"] = args[4]
            elif args[:1] == ["-w"] and args[2] in self.windows:
                self.windows[args[2]].setdefault("opts", {})[args[3]] = args[4]
            elif args[:1] == ["-w"]:
                # `=name:` is that session's current window.
                self.options[(args[2], args[3])] = args[4]
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
            if args[-1] == "#{window_layout}":
                return Answer(asked=True, out="fx-layout\n")
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
def fake(monkeypatch, tmp_path):
    server = FakeTmux()
    monkeypatch.setattr(deck_, "RUNNER", server)
    # A save is deck state: one test's must not reach the next, nor the real registry the fake's pids.
    monkeypatch.setattr(deck_.decksave.helpers, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(deck_.agents_, "providers", lambda: [])
    monkeypatch.delenv("TMUX", raising=False)
    # Console themes are on by default, so a tab started here must not write to the real themes folder.
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
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
    argv = created[created.index("--") + 1 :]
    assert argv[:3] == ["claude", "-n", "ws"] and argv[3] == "--append-system-prompt"
    settings = ["--settings", json.dumps({"theme": "custom:sb-ws"})]
    assert argv[5:] == ["--plugin-dir", str(deck_.PLUGIN_DIR), *settings, "--model", "opus"]
    assert created[created.index("-c") + 1] == str(tmp_path)
    assert fake.tabs() == ["ws"]


def test_the_tabs_session_comes_first_so_the_tab_pane_has_something_to_attach_to(fake, home):
    invoke("deck")
    assert [call[call.index("-s") + 1] for call in fake.find("new-session")] == ["sb-agents", "sb"]
    assert fake.tabs() == ["shell"] and "--" not in created_in(fake, "sb-agents")


def test_bare_deck_execs_attach_at_a_terminal(fake, home, monkeypatch):
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)
    monkeypatch.setattr(deck_, "launcher", lambda running: ("resume", ("sb",)))
    result = invoke("deck")
    assert result.exit_code == 0, result.output
    assert fake.replaced == [["tmux", "attach-session", "-t", "=sb"]]


def test_a_launcher_closed_without_a_choice_starts_nothing(fake, home, monkeypatch):
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)
    monkeypatch.setattr(deck_, "launcher", lambda running: None)
    assert invoke("deck").exit_code == 0
    assert fake.find("new-session") == [] and not fake.replaced


def test_ticked_folders_start_a_deck_of_those_agents(fake, home, monkeypatch, tmp_path):
    for name in ("one", "two"):
        (tmp_path / name).mkdir()
    home(f'[agent.one]\ncwd = "{tmp_path}/one"\n\n[agent.two]\ncwd = "{tmp_path}/two"\n')
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)
    monkeypatch.setattr(deck_, "launcher", lambda running: ("start", ("two", "one")))
    assert invoke("deck").exit_code == 0
    assert launched(fake, "two") and launched(fake, "one")
    first = next(c for c in fake.find("new-session") + fake.find("new-window") if "--" in c)
    assert first[first.index("-n") + 1] == "two"


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
    assert fake.options[("=sb-agents:", "status")] == "4"
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
    assert set(fake.roles()) == {"tabs", "queue", "messages", "todos", "decisions"}


# ============================================================================
# Profiles
# ============================================================================


# `session = "sb"` keeps these on the base deck; a profile's own deck name is tested on its own.
PROFILE = """
[profile.core]
session = "sb"
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
    home(PROFILE.format(d=tmp_path) + '[profile.more]\nsession = "sb"\ntabs = ["ghost", "jam"]\n')
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
    assert set(roles) == {"tabs", "queue", "messages", "todos", "decisions"}
    assert len({fake.panes[p]["window"] for p in roles.values()}) == 1
    assert set(fake.roles("sb-agents")) == {"agent"}


def test_every_tool_pane_runs_this_sb_by_absolute_path(fake, home):
    invoke("deck")
    sb = str(deck_.PROJECT_ROOT / "sb")
    argv = {role: fake.panes[pane]["argv"] for role, pane in fake.roles().items()}
    assert argv["queue"] == [sb, "deck", "queue", "--refresh", "5", "--screen"]
    assert argv["messages"] == [sb, "deck", "messages", "--refresh", "5", "--screen"]
    assert argv["todos"] == [sb, "deck", "todo", "list", "--all", "--refresh", "5", "--screen"]
    assert argv["decisions"] == [sb, "deck", "decide", "list", "--all", "--refresh", "5", "--screen"]


def test_the_tab_pane_nests_a_client_with_tmux_unset_on_the_same_server(fake, home):
    invoke("deck")
    argv = fake.panes[fake.roles()["tabs"]]["argv"]
    assert argv == ["env", "-u", "TMUX", "tmux", "-S", "/tmp/fx-socket", "attach-session", "-t", "=sb-agents"]


def test_the_columns_plan():
    assert deck_.plan("columns", "%T", ["%Q", "%M"]) == [
        ["join-pane", "-d", "-h", "-f", "-s", "%Q", "-t", "%T"],
        ["join-pane", "-d", "-v", "-s", "%M", "-t", "%Q"],
        ["resize-pane", "-t", "%Q", "-x", "25%"],
        ["resize-pane", "-t", "%Q", "-y", "50%"],
    ]


def test_the_stack_plan():
    assert deck_.plan("stack", "%T", ["%Q", "%M"]) == [
        ["join-pane", "-d", "-v", "-f", "-s", "%Q", "-t", "%T"],
        ["join-pane", "-d", "-h", "-s", "%M", "-t", "%Q"],
        ["resize-pane", "-t", "%Q", "-y", "30%"],
        ["resize-pane", "-t", "%Q", "-x", "50%"],
    ]


def test_a_plan_with_no_tools_moves_nothing():
    assert deck_.plan("columns", "%T", []) == []


def test_bare_deck_lays_a_new_controller_out_in_columns(fake, home):
    invoke("deck")
    roles = fake.roles()
    moves = [call[1:] for call in fake.calls if call[1] in ("join-pane", "resize-pane")]
    assert moves == deck_.plan("columns", roles["tabs"], [roles[r] for r in deck_.TOOL_ROLES])
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
    assert moves == deck_.plan(shape, roles["tabs"], [roles[r] for r in deck_.TOOL_ROLES])
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
    assert invoke("deck", "layout", "hexagon").exit_code == 2 and fake.calls == []


def test_bare_deck_on_an_existing_deck_keeps_the_operators_sizes(fake, home, tmp_path, monkeypatch):
    deck_built(fake, home, tmp_path)
    monkeypatch.setattr(deck_, "reload_session", lambda config: Result_())
    assert invoke("deck").exit_code == 1
    assert not {"join-pane", "resize-pane", "split-window", "new-session", "new-window"} & set(fake.verbs())
    assert fake.find("select-layout")


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
    assert window[window.index("-n") + 1] == "jam"
    assert window[window.index("--") + 1 : window.index("--") + 4] == ["claude", "-n", "jam"]
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


def test_the_deck_types_into_a_pane_only_to_tell_an_agent_a_ruling():
    """A deck that could answer a prompt is a second permission path, so one function may type, and never at one."""
    source = Path(deck_.__file__).read_text()
    start = source.index("def tell_rulings(")
    end = source.index("\ndef ", start + 1)
    assert not re.search(r"send-keys|send_keys|send-prefix|paste-buffer", source[:start] + source[end:])
    assert "may_tell(state" in source[start:end]
    assert deck_.WAITING not in deck_.TELL_AT_ONCE and not deck_.may_tell(deck_.WAITING, "", datetime.now(timezone.utc))


SCRATCH = "00000000-1111-2222-3333-444444444444"


def ident_session(pid, ident, cwd="/fx/j", name=""):
    return Session("claude", ident, name=name, cwd=cwd, status="busy", pid=pid)


def test_a_session_the_tab_started_sits_under_it_by_process_tree():
    tab, child = ident_session(11, SCRATCH), ident_session(12, "kid", name="live-3a")
    rows = queue_rows([pane("@1", 0, "jam", 10)], [tab, child], {11: 10, 12: 11}, NOW, proc=Path("/nonexistent"))
    assert [row["id"] for row in rows] == [SCRATCH]
    assert rows[0]["bg"] == "▸ 1c" and rows[0]["jobs"][0]["label"] == "live-3a · busy"


def test_a_session_in_a_tabs_scratch_folder_sits_under_it_with_no_process_link():
    tab = ident_session(11, SCRATCH)
    child = ident_session(99, "kid", cwd=f"/tmp/x/{SCRATCH}/scratchpad/probe", name="w-52")
    rows = queue_rows([pane("@1", 0, "jam", 10)], [tab, child], {11: 10}, NOW, proc=Path("/nonexistent"))
    assert [row["id"] for row in rows] == [SCRATCH] and rows[0]["jobs"][0]["label"] == "w-52 · busy"


def test_a_session_with_no_link_to_a_tab_stays_outside():
    tab, other = ident_session(11, SCRATCH), ident_session(99, "cron", cwd="/fx/pool", name="jam-pool")
    rows = queue_rows([pane("@1", 0, "jam", 10)], [tab, other], {11: 10, 99: 1}, NOW, proc=Path("/nonexistent"))
    assert [(row["where"], row["id"]) for row in rows] == [("deck", SCRATCH), ("outside", "cron")]


def test_a_spawned_session_that_ended_stays_for_a_while_then_goes(tmp_path):
    folder = tmp_path / f"-tmp-x-{SCRATCH}-scratchpad-probe"
    folder.mkdir()
    transcript = folder / "kid.jsonl"
    transcript.write_text("{}")
    wrote = transcript.stat().st_mtime
    found = background.ended({SCRATCH}, set(), tmp_path, wrote + 5)
    assert found[SCRATCH][0].label == "scratchpad-probe · ended" and found[SCRATCH][0].kind == background.SESSION
    assert background.ended({SCRATCH}, {"kid"}, tmp_path, wrote + 5) == {}
    assert background.ended({SCRATCH}, set(), tmp_path, wrote + background.RECENT + 1) == {}


def wire_tabs(tmp_path):
    paths = {name: tmp_path / f"{name}.jsonl" for name in ("api", "web")}
    for path in paths.values():
        path.write_text("")
    hues = {"api": "#112233", "web": "#445566"}
    index = {("socket", "/run/web.sock"): "w"}
    return deck_.WireTabs({"a": "api", "w": "web"}, paths, {"api": 5, "web": 20}, hues, index)


def sent_lines(to, msg_id):
    call = {"type": "tool_use", "id": "t1", "name": "SendMessage", "input": {"to": to}}
    result = {"type": "tool_result", "tool_use_id": "t1"}
    answer = {"type": "user", "message": {"content": [result]}, "toolUseResult": {"success": True, "msg_id": msg_id}}
    return json.dumps({"type": "assistant", "message": {"content": [call]}}) + "\n" + json.dumps(answer) + "\n"


def received_line(msg_id, name="api"):
    return json.dumps({"type": "user", "origin": {"kind": "peer", "msg_id": msg_id, "name": name}}) + "\n"


def wire_for(tabs):
    wires = deck_.Wires("sb")
    wires.tabs = tabs
    for path in tabs.paths.values():
        wires.tail.read(path)
    wires.write = lambda frame: None
    return wires


def append(path, text):
    with path.open("a") as handle:
        handle.write(text)


def test_a_line_starts_when_sent_and_waits_for_the_receiver(tmp_path):
    tabs = wire_tabs(tmp_path)
    wires = wire_for(tabs)
    append(tabs.paths["api"], sent_lines("web", "m1"))
    wires.step(1.0)
    wires.step(100.0)
    assert wires.flights["m1"].landed is None
    append(tabs.paths["web"], received_line("m1"))
    wires.step(101.0)
    assert wires.flights["m1"].landed == 101.0
    wires.step(103.0)
    assert not wires.flights


def test_a_sent_message_finds_its_receiver_by_socket_and_by_ref(tmp_path):
    tabs = wire_tabs(tmp_path)
    wires = wire_for(tabs)
    assert wires.receiver_of("uds:/run/web.sock", tabs) == "web" and wires.receiver_of("web [3fa9c1]", tabs) == "web"
    assert wires.receiver_of("stranger", tabs) == ""


def test_a_receipt_with_no_line_seen_leaving_still_draws_one(tmp_path):
    tabs = wire_tabs(tmp_path)
    wires = wire_for(tabs)
    append(tabs.paths["web"], received_line("m2"))
    wires.step(1.0)
    flight = wires.flights["m2"]
    assert (flight.sender, flight.receiver, flight.landed) == ("api", "web", 1.0)


def test_a_message_to_or_from_outside_the_tabs_draws_nothing(tmp_path):
    tabs = wire_tabs(tmp_path)
    wires = wire_for(tabs)
    append(tabs.paths["api"], sent_lines("stranger", "m3"))
    append(tabs.paths["web"], received_line("m4", name="stranger"))
    wires.step(1.0)
    assert not wires.flights


def measured(monkeypatch, client_width, names):
    rows = "".join(f"{int(n == 0)}\t@{n}\t{name}\n" for n, name in enumerate(names))
    answers = {"list-clients": f"{client_width}\n", "list-windows": rows}
    monkeypatch.setattr(deck_, "tmux", lambda *args, **_: deck_.Answer(True, 0, answers[args[0]], ""))
    return deck_.tab_centres("sb", {f"@{n}": name for n, name in enumerate(names)})


def test_a_tab_centre_sits_under_the_middle_of_its_box(monkeypatch):
    _, left = deck_.tab_lefts()
    assert measured(monkeypatch, 200, ["api", "web"]) == {"api": left + 3, "web": left + 8 + 3}


def test_a_tab_scrolled_out_of_view_has_no_centre(monkeypatch):
    _, left = deck_.tab_lefts()
    names = [f"agent-{n}" for n in range(9)]
    centres = measured(monkeypatch, left + deck_.ADD_WIDTH + 30, names)
    assert "agent-0" in centres and "agent-8" not in centres


def test_the_row_under_the_tabs_prefers_the_line_to_the_scrollbar():
    options = dict(deck_.bar_options(True))
    row = options[f"status-format[{deck_.TAB_ROWS}]"]
    assert row.index(deck_.WIRE_OPTION) < row.rindex(deck_.SCROLLBAR_OPTION)


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


def test_rows_sort_needs_you_busy_shell_idle_inside_the_deck_and_outside_follows():
    listed = [pane("@1", 0, "a", 10), pane("@2", 1, "b", 20), pane("@3", 2, "c", 30), pane("@4", 3, "d", 40)]
    sessions = [a_session(10), a_session(20, "waiting"), a_session(30, "busy"), a_session(40, "shell")]
    listed.append(pane("@5", 4, "e", 50))
    rows = queue_rows(listed, [*sessions, a_session(99, "waiting")], {}, NOW)
    assert [(r["where"], r["window"], r["state"]) for r in rows] == [
        ("deck", "b", "needs you"),
        ("deck", "c", "busy"),
        ("deck", "d", "shell"),
        ("deck", "a", "idle"),
        ("deck", "e", "unregistered"),
        ("outside", "", "needs you"),
    ]
    assert rows[0]["status"] == "waiting"  # the provider's word is kept beside the deck's


def test_painted_a_window_name_takes_its_tabs_colour_and_only_then():
    from skyboss import theme

    listed = [pane("@1", 0, "jam-sense", 10)]
    painted = queue_rows(listed, [a_session(10)], {}, NOW, paint=True)[0]
    assert painted["window_parts"] == [["jam-sense", theme.agent_role("jam-sense", 0)]]
    assert queue_rows(listed, [a_session(10)], {}, NOW)[0]["window_parts"] == [["jam-sense", None]]


def test_the_primary_tab_carries_a_star_and_only_it():
    listed = [pane("@1", 0, "lead", 10), pane("@2", 1, "jam", 20)]
    rows = queue_rows(listed, [a_session(10), a_session(20)], {}, NOW, primary="lead")
    marked = {r["window"]: (r["primary"], r["window_parts"]) for r in rows}
    assert marked["lead"] == (True, [["lead", None], [" *", None]])
    assert marked["jam"] == (False, [["jam", None]])
    window = next(c for c in deck_.view_of(rows)["columns"] if c["key"] == "window")
    assert window["max"] >= len("lead *")


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
    assert [c["key"] for c in result.view["columns"]] == ["where", "window", "state", "bg", "name", "up", "cwd"]
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
        "ask": True,
        "open": True,
        "add": True,
        "terminal": True,
        "plus": True,
        "launch": True,
        "profile": True,
        "places": False,
        "jump": True,
        "layout": True,
        "marks": True,
        "exit": True,
        "save": True,
        "queue": False,
        "messages": False,
        "message": False,
        "brief": False,
        "todo": True,
        "decide": True,
        "column": True,
        "reload": True,
        "scroll": True,
        "clear": True,
    }
    assert {name: getattr(c, "sb_acts") for name, c in deck_.deck_column.commands.items()} == {
        "show": False,
        "fold": True,
        "pick": True,
        "move": True,
    }
    for group, more in (
        (deck_.deck_todo, {"clear": True}),
        (deck_.deck_decide, {"clear": True, "rule": True, "act": True, "note": True, "sweep": True}),
    ):
        assert {name: getattr(command, "sb_acts") for name, command in group.commands.items()} == {
            "add": True,
            "done": True,
            "rm": True,
            "list": False,
            **more,
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
    assert ("=sb:", "@sb-marked") in fake.options
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
    assert job[2] == "-b" and job[3] == f"env SB_DECK=sb {shlex.quote(sb)} deck marks --every 3 >/dev/null 2>&1 || true"


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


def test_the_tab_bar_is_three_rows_of_boxes_and_names_no_state_word(fake, home):
    invoke("deck")
    rows = {c[-2]: c[-1] for c in fake.find("set-option") if c[-2].startswith("status-format[")}
    assert sorted(rows) == [f"status-format[{n}]" for n in range(4)]
    # The row under the tabs: the line while one runs, and the scrollbar on overflow.
    assert rows.pop("status-format[3]") == "#{?#{@sb-wire},#{@sb-wire},#{@sb-scrollbar}}"
    assert ("status", "4") in {(c[-2], c[-1]) for c in fake.find("set-option") if "=sb-agents:" in c}
    for row in rows.values():
        assert row.count("#[range=window|#{window_index}]") == 2  # every row clicks, current tab included
        assert not any(word in row for word in ("working", "quiet", "needs you"))
    assert "╭─#{s/./─/:window_name}─╮" in rows["status-format[0]"] and "╰" in rows["status-format[2]"]


def test_a_tabs_ground_is_lit_when_busy_and_the_warn_block_when_waiting():
    from skyboss import theme

    style = theme.tmux_styles()
    name = deck_.tab_cell(1, current=False)
    assert f"#{{?#{{==:#{{@sb-state}},busy}},#[{style['tab-working']}]," in name
    assert f"#{{?#{{==:#{{@sb-state}},waiting}},#[{style['needs-you']}]," in name
    assert theme.contrast(theme.TEXT, theme.WORKING_GROUND) >= theme.DECK_FLOOR


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
        theme.WORKING_GROUND,  # a tint of BRAND, made in theme.py
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
    assert window_targets == {*fake.windows, "=sb:"}  # the current window: the border follows the tab


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
    assert click_[7].startswith("confirm-before")
    assert click_[8].startswith("if-shell -F '#{==:#{mouse_status_range},add}'") and "deck plus" in click_[8]
    assert "#{==:#{mouse_status_range},layout}" in click_[8] and "'switch-client -t ='" in click_[8]


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
        assert argv[4] in (
            "confirm-before",
            "if-shell",
            "set-option",
            "previous-window",
            "next-window",
            "display-popup",
            "run-shell",
        )


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
    assert [r["n"] for r in shown.data] == list(range(20, 30)) and marker == "20 earlier"
    pane.move("pgup")
    shown, marker = fit(rows_of_n(30), 10)
    assert [r["n"] for r in shown.data] == list(range(10, 20))
    assert marker == "↑ 10 back · 10 earlier"
    pane.move("home")
    assert [r["n"] for r in fit(rows_of_n(30), 10)[0].data] == list(range(0, 10)) and pane.offset == 20
    assert pane.move("end") and fit(rows_of_n(30), 10)[1] == "20 earlier"


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
    assert len(shaped.data) == 1 and shaped.warnings == [] and pane.note() == "1 outside hidden · M-h shows"


def test_the_outside_note_is_a_muted_footer_segment_and_not_a_warning():
    import dataclasses

    from skyboss import chrome

    facts = chrome.resident("deck queue", ok=True, partial=False, warnings=0, ran_at=0.0, interval=5)
    _, bottom = chrome.status_bands(dataclasses.replace(facts, note="1 outside hidden · M-h shows"), 0.0, 80)
    assert (" · 1 outside hidden · M-h shows", "sb.muted") in bottom
    assert not any(role == "sb.warn" for _, role in bottom)


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


def test_a_tab_is_its_hue_and_the_active_tabs_box_is_drawn_in_it():
    assert "#{?#{@sb-colour},#[fg=#{@sb-colour}]," in deck_.tab_cell(1, current=False)
    assert "#{?#{@sb-colour},#[fg=#{@sb-colour} bold]," in deck_.tab_cell(0, current=True)
    assert "#[fg=#{@sb-colour} bold]" not in deck_.tab_cell(0, current=False)


def test_the_messages_pane_colours_a_name_exactly_as_its_tab_is_coloured():
    from skyboss import theme
    from skyboss.messages import Message, rows_of

    message = Message(
        at=NOW, sender="jam-sense", receiver="ws", body="hi", msg_id="m", session="id-ws", key="m", sender_id="id-js"
    )
    placed = {"id-ws": ("skyrow-workspace", 0), "id-js": ("jam-sense", 3)}
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
    assert painted == {roles[role] for role in deck_.TOOL_ROLES}
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


# ============================================================================
# The brief: every agent the deck starts knows it is in a deck
# ============================================================================


CORE = """
[profile.core]
session = "sb"
primary = "skyrow-workspace"
tabs = ["stash-flow", "mind-head"]
brief = '''Coordinate through the workspace.
Ask before pushing.'''
[agent.skyrow-workspace]
cwd = "{d}/ws"
role = "coordinates the others"
[agent.stash-flow]
cwd = "{d}/sf"
[agent.mind-head]
cwd = "{d}/mh"
[agent.sky-boss]
cwd = "{d}/sb"
args = ["--name", "boss", "--model", "opus"]
"""


@pytest.fixture
def core(fake, home, tmp_path):
    for sub in ("ws", "sf", "mh", "sb"):
        (tmp_path / sub).mkdir()
    home(CORE.format(d=tmp_path))
    return tmp_path


def launched(fake, name):
    """The argv tmux was asked to run for `name`'s tab."""
    for call in fake.find("new-session") + fake.find("new-window"):
        if "-n" in call and call[call.index("-n") + 1] == name and "--" in call:
            return call[call.index("--") + 1 :]
    raise AssertionError(f"no launch for {name}")


def told(argv):
    return argv[argv.index("--append-system-prompt") + 1]


def test_the_primary_and_a_profile_tab_are_named_and_briefed(core, fake):
    invoke("deck", "--profile", "core")
    primary, tab = launched(fake, "skyrow-workspace"), launched(fake, "stash-flow")
    assert primary[:3] == ["claude", "-n", "skyrow-workspace"] and tab[:3] == ["claude", "-n", "stash-flow"]
    lines = told(primary).split("\n")
    assert (
        lines[0]
        == 'You are "skyrow-workspace", started by the operator as an agent in a sky.boss deck (tmux session "sb").'
    )
    roster_ = [line for line in lines if line.startswith("- ")]
    assert roster_ == [
        f"- skyrow-workspace (primary) — {core}/ws — coordinates the others",
        f"- stash-flow — {core}/sf",
        f"- mind-head — {core}/mh",
    ]
    generated, _, extra = told(primary).partition("\n\n")
    assert extra == "Coordinate through the workspace.\nAsk before pushing."
    assert told(tab).endswith(extra) and "coordinating agent" not in told(primary)
    fixed = [line for line in generated.split("\n") if not line.startswith("- ")]
    assert len(fixed) <= deck_.BRIEF_LIMIT


def test_a_tab_opened_later_gets_the_roster_as_it_stands(core, fake):
    invoke("deck", "--profile", "core")
    fake.options[("=sb-agents:", "@sb-primary")] = "skyrow-workspace"
    invoke("--json", "deck", "open", "mind-head")  # already open: nothing launched
    fake.calls.clear()
    (core / "ex").mkdir()
    home_text = (deck_.SB_HOME / "deck.toml").read_text() + f'[agent.extra]\ncwd = "{core}/ex"\n'
    (deck_.SB_HOME / "deck.toml").write_text(home_text)
    assert invoke("--json", "deck", "open", "extra").exit_code == 0
    argv = launched(fake, "extra")
    assert argv[:3] == ["claude", "-n", "extra"]
    roster_ = [line for line in told(argv).split("\n") if line.startswith("- ")]
    assert roster_[0].startswith("- skyrow-workspace (primary)") and roster_[-1] == f"- extra — {core}/ex"
    assert "coordinating agent" not in told(argv)


def test_the_operators_name_wins_and_is_not_doubled(core, fake):
    invoke("--json", "deck", "open", "sky-boss")
    argv = launched(fake, "sky-boss")
    assert "-n" not in argv and argv.count("--name") == 1 and argv[argv.index("--name") + 1] == "boss"
    assert "--append-system-prompt" in argv


def test_the_operators_own_prompt_wins_too():
    agent = deck_.Agent("x", "/x", args=["--append-system-prompt-file", "/fx/p.md"])
    plugin = ["--plugin-dir", str(deck_.PLUGIN_DIR)]
    assert agent.launch("brief") == ["claude", "-n", "x", *plugin, "--append-system-prompt-file", "/fx/p.md"]


def test_every_tab_loads_the_decks_plugin_and_it_ships_its_skill():
    """The skill reaches agents in other repos through --plugin-dir; nothing is installed for it."""
    assert deck_.Agent("x", "/x").launch()[-2:] == ["--plugin-dir", str(deck_.PLUGIN_DIR)]
    manifest = json.loads((deck_.PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text())
    skill = (deck_.PLUGIN_DIR / "skills" / "deck-connect" / "SKILL.md").read_text()
    assert manifest["name"] == "sky-boss" and "name: deck-connect" in skill and "sb --json deck brief" in skill


def test_nothing_in_the_brief_comes_from_a_transcript(core, fake, monkeypatch):
    """Built from deck.toml and tmux alone: every transcript and registry read is made to fail."""
    from skyboss import messages

    def refuse(*args, **kwargs):
        raise AssertionError("the brief read a transcript or the registry")

    monkeypatch.setattr(messages, "received", refuse)
    monkeypatch.setattr(messages, "collect", refuse)
    monkeypatch.setattr(deck_.agents_, "fold", refuse)
    invoke("deck", "--profile", "core")
    assert "You are" in told(launched(fake, "mind-head"))


def test_scope_deck_works_from_inside_a_deck_pane(fake, home, monkeypatch, tmp_path):
    """An agent asking from its own tab: TMUX is set, and the same server is asked."""
    monkeypatch.setenv("TMUX", "/tmp/fx-socket,1,1")
    monkeypatch.setenv("TMUX_PANE", "%9")
    monkeypatch.setattr(deck_, "parents", lambda proc=None: {})
    fake.current = "sb-agents"
    fake.add("sb", "deck", role="tabs", pid=1)
    fake.add("sb-agents", "jam", agent="jam", role="agent", pid=10)
    from skyboss import agents

    monkeypatch.setattr(agents, "providers", lambda: [Adapter([a_session(10, name="jam"), a_session(11, name="away")])])
    monkeypatch.setattr(agents, "claims", lambda sessions: ({}, 0))
    result = invoke("--json", "agents", "--scope", "deck")
    assert result.exit_code == 0, result.output
    assert [row["name"] for row in json.loads(result.stdout)["data"]] == ["jam"]
    assert {call[1] for call in fake.calls} <= {"has-session", "list-panes", "show-options"}


def test_queue_scope_and_marks_place_a_session_by_its_pane_never_its_name(fake, home, monkeypatch):
    """Two live sessions called skeletor: only the one whose pid runs in the tab is the deck's."""
    monkeypatch.setattr(deck_, "parents", lambda proc=None: {})
    tab, _ = fake.add("sb-agents", "skeletor", agent="skeletor", role="agent", pid=101)
    fake.session("sb")
    inside = a_session(101, "waiting", name="skeletor")
    outside = a_session(202, "busy", name="skeletor")
    listed = parse_panes(fake.listing("sb-agents"))
    rows = queue_rows(listed, [inside, outside], {}, NOW)
    assert [(r["where"], r["pid"]) for r in rows] == [("deck", 101), ("outside", 202)]
    assert deck_.claimed([inside, outside]) == ({"id-101"}, "")
    assert deck_.windows_states(listed, [outside, inside], {}) == {tab: "waiting"}
    assert set(deck_.placement([inside, outside])) == {"id-101"}


def test_a_tab_opened_later_carries_the_loaded_profiles_brief(core, fake):
    invoke("deck", "--profile", "core")
    assert fake.options[("=sb-agents:", "@sb-profile")] == "core"
    fake.calls.clear()
    assert invoke("--json", "deck", "open", "sky-boss").exit_code == 0
    later = told(launched(fake, "sky-boss"))
    assert "Ask before pushing" in later
    assert f"- skyrow-workspace (primary) — {core}/ws — coordinates the others" in later


@pytest.mark.parametrize(
    "raw, phrase",
    [
        ({"agent": {"x": {"cwd": "/x", "role": 3}}}, "role must be one line of text"),
        ({"agent": {"x": {"cwd": "/x", "role": "two\nlines"}}}, "role must be one line of text"),
        ({"profile": {"p": {"tabs": ["x"], "brief": ["a"]}}}, "brief must be text"),
        ({"profile": {"p": {"tabs": ["x"], "brief": "a", "brief_file": "b.md"}}}, "not both"),
    ],
)
def test_a_bad_role_or_brief_is_a_problem_not_silence(raw, phrase):
    _, problems = parse(raw)
    assert any(phrase in p for p in problems)


def test_role_and_brief_are_known_keys():
    config, problems = parse(
        {"agent": {"x": {"cwd": "/x", "role": "r"}}, "profile": {"p": {"tabs": ["x"], "brief": "b"}}}
    )
    assert problems == [] and config.agents["x"].role == "r" and config.profiles["p"].brief == "b"


def test_a_brief_file_is_read_each_time_from_sb_home(tmp_path):
    (tmp_path / "deck.toml").write_text('[profile.p]\ntabs = ["x"]\nbrief_file = "core-brief.md"\n')
    (tmp_path / "core-brief.md").write_text("Ask before pushing.\n")
    config, problems = deck_.load(tmp_path)
    profile = config.profiles["p"]
    assert problems == [] and deck_.brief_path(profile.brief_file, tmp_path).read_text() == "Ask before pushing.\n"
    profile.brief_file = str(tmp_path / "core-brief.md")
    (tmp_path / "core-brief.md").write_text("Changed.\n")
    assert profile.told() == "Changed.\n"


def test_an_unreadable_brief_file_is_a_problem_and_adds_nothing(tmp_path):
    (tmp_path / "deck.toml").write_text('[profile.p]\ntabs = ["x"]\nbrief_file = "/nowhere/brief.md"\n')
    config, problems = deck_.load(tmp_path)
    assert any("cannot be read" in p for p in problems) and config.profiles["p"].told() == ""


# ============================================================================
# Todos: each agent's own list, owned by the tab whose pane runs the caller
# ============================================================================


@pytest.fixture
def sb_state(tmp_path, monkeypatch):
    from skyboss import helpers

    monkeypatch.setattr(helpers, "STATE_DIR", tmp_path / "state")
    return tmp_path / "state"


def caller_under(monkeypatch, pane_pid):
    """This process's parent chain ends at `pane_pid`, through one shell between."""
    import os

    monkeypatch.setattr(deck_, "parents", lambda proc=None: {os.getpid(): 5000, 5000: pane_pid})


def two_tabs(fake):
    fake.add("sb", "deck", role="tabs", pid=1)
    fake.add("sb-agents", "ws", agent="ws", role="agent", pid=10)
    fake.add("sb-agents", "jam", agent="jam", role="agent", pid=20)
    fake.options[("=sb-agents:", "@sb-primary")] = "ws"


def test_a_same_named_session_outside_the_deck_cannot_write_a_tabs_list(fake, home, sb_state, monkeypatch, said):
    two_tabs(fake)
    caller_under(monkeypatch, 777)  # a `claude -n jam` running outside every deck pane
    result = invoke("deck", "todo", "add", "pretend to be jam")
    assert result.exit_code == 1 and "not running inside a tab of deck 'sb'" in said(result)
    assert not (sb_state / "deck").exists()


def test_add_refuses_with_no_deck_at_all(fake, home, sb_state, said):
    result = invoke("deck", "todo", "add", "x")
    assert result.exit_code == 1 and "no deck session 'sb'" in said(result)


def test_add_done_and_list_round_trip_through_the_callers_tab(fake, home, sb_state, monkeypatch):
    two_tabs(fake)
    caller_under(monkeypatch, 20)
    assert invoke("--json", "deck", "todo", "add", "write  the\nparser test").exit_code == 0
    assert invoke("--json", "deck", "todo", "add", "ship it").exit_code == 0
    done = json.loads(invoke("--json", "deck", "todo", "done", "1").stdout)["data"]
    assert done["agent"] == "jam" and done["session"] == "sb" and done["open"] == 1 and done["updated"]
    assert [(i["text"], i["done"]) for i in done["items"]] == [("write the parser test", True), ("ship it", False)]
    stored = json.loads((sb_state / "deck" / "sb" / "todos" / "jam.json").read_text())
    assert stored["updated"] == done["updated"] and stored["items"][0]["closed"]
    mine = json.loads(invoke("--json", "deck", "todo", "list").stdout)["data"]
    assert {row["agent"] for row in mine} == {"jam"}


def test_done_past_the_end_names_the_length(fake, home, sb_state, monkeypatch, said):
    two_tabs(fake)
    caller_under(monkeypatch, 10)
    invoke("deck", "todo", "add", "one")
    result = invoke("deck", "todo", "done", "4")
    assert result.exit_code == 1 and "no item 4 — the list has 1" in said(result)


def test_rm_removes_and_renumbers(fake, home, sb_state, monkeypatch):
    two_tabs(fake)
    caller_under(monkeypatch, 10)
    for text in ("a", "b", "c"):
        invoke("deck", "todo", "add", text)
    data = json.loads(invoke("--json", "deck", "todo", "rm", "2").stdout)["data"]
    assert [(i["n"], i["text"]) for i in data["items"]] == [(1, "a"), (2, "c")]


def test_kept_lists_lead_newest_first_then_agents_without_one_in_tab_order(fake, home, sb_state, monkeypatch):
    from skyboss import todos

    fake.add("sb", "deck", role="tabs", pid=1)
    for pid, name in ((10, "jam"), (20, "ws"), (30, "mh")):
        fake.add("sb-agents", name, agent=name, role="agent", pid=pid)
    fake.options[("=sb-agents:", "@sb-primary")] = "ws"
    todos.add("sb", "mh", "index")
    todos.add("sb", "gone", "left over")
    caller_under(monkeypatch, 999)
    rows = json.loads(invoke("--json", "deck", "todo", "list").stdout)["data"]
    headings = [row["agent"] for row in rows if row["kind"] == "agent"]
    assert headings == ["gone", "mh"]  # an agent with nothing on its list is not drawn
    assert deck_.tab_order("sb") == [("ws", 1), ("jam", 0), ("mh", 2)]
    assert [r["todos"] for r in rows if r["agent"] == "gone"][0].startswith("gone (no tab)")


def test_any_change_to_a_list_lifts_its_agent_to_the_top(sb_state):
    from skyboss import todos

    todos.add("sb", "ws", "one")
    todos.add("sb", "jam", "two")
    first = [r["agent"] for r in todos.rows_of("sb", [("ws", 0), ("jam", 1)], NOW)[0] if r["kind"] == "agent"]
    todos.done("sb", "ws", 1)
    after = [r["agent"] for r in todos.rows_of("sb", [("ws", 0), ("jam", 1)], NOW)[0] if r["kind"] == "agent"]
    assert (first, after) == (["jam", "ws"], ["ws", "jam"])


def test_a_decision_closes_with_its_ruling_beside_it(sb_state):
    from skyboss import todos

    todos.add("sb", "jam", "hold ci.yml?", book=todos.DECISIONS)
    todos.done("sb", "jam", 1, book=todos.DECISIONS, ruling="take the template's")
    rows, _ = todos.rows_of("sb", [("jam", 0)], NOW, book=todos.DECISIONS)
    assert rows[-1]["decisions"].strip() == "1. ✓ hold ci.yml? → take the template's"
    assert todos.load("sb", "jam") is None  # a separate book from the todo list


def test_decisions_list_only_agents_that_recorded_one_and_say_so_when_none_has(sb_state):
    from skyboss import todos

    empty = todos.result_of("sb", [("ws", 0), ("jam", 1)], book=todos.DECISIONS)
    assert [r["decisions"] for r in empty.data] == ["no agent in deck 'sb' has recorded a decision"]
    assert empty.warnings == []
    todos.add("sb", "jam", "q", book=todos.DECISIONS)
    rows = todos.result_of("sb", [("ws", 0), ("jam", 1)], book=todos.DECISIONS).data
    assert {r["agent"] for r in rows} == {"jam"}


def test_no_list_kept_is_not_nothing_open(sb_state):
    from skyboss import todos

    todos.add("sb", "jam", "one")
    todos.done("sb", "jam", 1)
    rows, problems = todos.rows_of("sb", [("ws", 0), ("jam", 1)], NOW)
    said_of = {r["agent"]: [x["todos"].strip() for x in rows if x["agent"] == r["agent"]] for r in rows}
    assert problems == [] and "ws" not in said_of
    assert said_of["jam"][1:] == ["nothing open", "1. ✓ one"]
    alone, _ = todos.rows_of("sb", [("ws", 0)], NOW, only="ws")
    assert [r["todos"].strip() for r in alone] == ["ws", "no list kept"]  # a tab asking for its own list is told


def test_a_heading_takes_its_tabs_colour_only_when_painted(sb_state):
    from skyboss import theme, todos

    todos.add("sb", "jam-sense", "x")
    (painted, *_), _ = todos.rows_of("sb", [("jam-sense", 0)], NOW, paint=True)
    (plain, *_), _ = todos.rows_of("sb", [("jam-sense", 0)], NOW)
    assert painted["parts"][0] == ["jam-sense", theme.agent_role("jam-sense", 0)]
    assert plain["parts"][0] == ["jam-sense", "sb.accent"] and "updated" in plain["todos"]


def test_an_unreadable_list_is_a_warning_and_reads_as_no_list(sb_state):
    from skyboss import todos

    todos.root("sb").mkdir(parents=True)
    todos.path_for("sb", "jam").write_text("{not json")
    rows, problems = todos.rows_of("sb", [("jam", 0)], NOW, only="jam")
    assert problems and "jam.json unreadable" in problems[0] and rows[1]["todos"].strip() == "no list kept"


def test_the_four_tool_plans_share_the_column_evenly():
    assert deck_.plan("columns", "%T", ["%Q", "%M", "%D", "%C"]) == [
        ["join-pane", "-d", "-h", "-f", "-s", "%Q", "-t", "%T"],
        ["join-pane", "-d", "-v", "-s", "%M", "-t", "%Q"],
        ["join-pane", "-d", "-v", "-s", "%D", "-t", "%M"],
        ["join-pane", "-d", "-v", "-s", "%C", "-t", "%D"],
        ["resize-pane", "-t", "%Q", "-x", "25%"],
        ["resize-pane", "-t", "%Q", "-y", "25%"],
        ["resize-pane", "-t", "%M", "-y", "25%"],
        ["resize-pane", "-t", "%D", "-y", "25%"],
    ]
    assert deck_.plan("stack", "%T", ["%Q", "%M", "%D"])[2] == ["join-pane", "-d", "-h", "-s", "%D", "-t", "%M"]


def test_a_folded_pane_is_one_line_in_columns_and_a_strip_in_stack_and_resized_last():
    columns = deck_.plan("columns", "%T", ["%Q", "%M", "%D"], frozenset({"%M"}))
    assert columns[-2:] == [
        ["resize-pane", "-t", "%Q", "-y", "50%"],
        ["resize-pane", "-t", "%M", "-y", deck_.FOLDED_HEIGHT],
    ]
    stack = deck_.plan("stack", "%T", ["%Q", "%M"], frozenset({"%Q"}))
    assert stack[-1] == ["resize-pane", "-t", "%Q", "-x", deck_.FOLDED_WIDTH]


@pytest.mark.parametrize("shape", ["stack", "columns"])
def test_the_todos_pane_survives_a_layout_switch(fake, home, tmp_path, shape):
    deck_built(fake, home, tmp_path)
    todos_pane = fake.roles()["todos"]
    before = dict(fake.panes[todos_pane])
    assert invoke("--json", "deck", "layout", shape).exit_code == 0
    assert fake.roles()["todos"] == todos_pane and fake.panes[todos_pane] == before


def test_bare_deck_on_a_running_deck_adds_a_missing_todos_pane(fake, home, tmp_path):
    deck_built(fake, home, tmp_path)
    del fake.panes[fake.roles()["todos"]]
    invoke("deck")
    assert "todos" in fake.roles() and fake.find("split-window")


def test_the_brief_tells_an_agent_to_keep_its_todos():
    text = deck_.brief("jam", "sb", [("jam", "/fx/j", "")], "jam")
    assert 'sb deck todo add "<text>"' in text and "AGENT TODOs pane" in text


def test_the_brief_names_the_socket_for_a_name_that_misses():
    text = deck_.brief("jam", "sb", [("jam", "/fx/j", "")], "jam")
    assert "`sb --json agents --scope deck`" in text and "uds:" in text


def test_the_brief_and_the_skill_teach_every_kind_of_ask():
    brief = deck_.brief("jam", "sb", [("jam", "/fx/j", "")], "jam")
    skill = (deck_.PLUGIN_DIR / "skills" / "deck-connect" / "SKILL.md").read_text()
    for text in (brief, skill):
        for form in ("--option", "--run", "--until pr:<n>@<sha>", "--action", 'note "<text>"'):
            assert form in text
        assert "tab that acts on it" in " ".join(text.split())
        assert '--run "gh pr merge <n>' in text and "never left only in prose" in " ".join(text.split())


def test_the_todos_pane_scrolls_from_the_top():
    pane = deck_.DeckPane("sb", lambda row: True, scroll=True, top=True)
    fit = deck_.keep_from_top("row(s)", pane)
    result = Result_(data=list(range(20)))
    shown, line = fit(result, 5)
    assert shown.data == [0, 1, 2, 3, 4] and line == "15 below"
    assert pane.move("down") and fit(result, 5)[0].data == [1, 2, 3, 4, 5]
    assert pane.move("end") and fit(result, 5)[0].data == [15, 16, 17, 18, 19]
    assert pane.move("home") and pane.offset == 0


def test_a_pane_can_scroll_to_its_last_row_after_the_fit_overshoots():
    """The fit's last call is the `keep` it drew, so `end` clamps to a page that was drawn."""
    from rich.text import Text

    from skyboss.resident import fitted

    pane = deck_.DeckPane("sb", lambda row: True, scroll=True, top=True)
    fit = deck_.keep_from_top("row(s)", pane)
    result = Result_(data=[f"row {i}" for i in range(20)])

    def drawn(r):
        return Text("\n".join(["HEADING", *r.data]))

    fitted(result, drawn(result), 8, fit, drawn, always=True)
    pane.move("end")
    shown = fitted(result, drawn(result), 8, fit, drawn, always=True)
    assert shown.plain.rstrip().endswith("row 19")


def test_brief_rebuilds_the_calling_tabs_brief_with_the_live_roster(core, fake, monkeypatch):
    invoke("deck", "--profile", "core")
    fake.options[("=sb-agents:", "@sb-primary")] = "skyrow-workspace"
    monkeypatch.setattr(deck_, "caller_tab", lambda session, **kw: "mind-head")
    result = invoke("--json", "deck", "brief")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert data["agent"] == "mind-head" and data["brief"].startswith('You are "mind-head"')
    assert "Ask before pushing" in data["brief"]
    assert [p["name"] for p in data["peers"]][0] == "skyrow-workspace"
    assert "mind-head" not in [p["name"] for p in data["peers"]]


def test_brief_outside_a_tab_asks_for_a_name_and_previews_one(core, fake, monkeypatch):
    invoke("deck", "--profile", "core")
    monkeypatch.setattr(deck_, "caller_tab", lambda session, **kw: None)
    refused = invoke("--json", "deck", "brief")
    assert refused.exit_code == 1 and "name an agent" in json.loads(refused.stdout)["data"]["error"]
    preview = invoke("--json", "deck", "brief", "stash-flow")
    assert json.loads(preview.stdout)["data"]["brief"].startswith('You are "stash-flow"')


def test_brief_with_no_deck_says_so(fake, home):
    home("")
    result = invoke("--json", "deck", "brief", "x")
    assert result.exit_code == 1 and "no deck session" in json.loads(result.stdout)["data"]["error"]


# ============================================================================
# Round 5: the right column — choosing, hiding and folding panes
# ============================================================================


def test_a_saved_column_keeps_known_panes_once_and_appends_any_it_never_named(sb_state):
    from skyboss import column

    column.path_for("sb").parent.mkdir(parents=True)
    column.path_for("sb").write_text('{"order": ["todos", "ghost", "todos", "queue"], "hidden": ["ghost"]}')
    chosen, problems = column.load("sb")
    assert chosen.order == ["todos", "queue", "messages", "decisions"] and chosen.hidden == set() and not problems


def test_the_declared_panes_order_is_the_default_until_a_choice_is_saved(sb_state):
    from skyboss import column

    assert column.load("sb", ["decisions", "queue"])[0].order == ["decisions", "queue", "messages", "todos"]
    column.save("sb", column.Column(order=["messages", "queue", "todos", "decisions"]))
    assert column.load("sb", ["decisions"])[0].order[0] == "messages"


def test_an_unreadable_column_file_is_said_and_the_default_drawn(sb_state):
    from skyboss import column

    column.path_for("sb").parent.mkdir(parents=True)
    column.path_for("sb").write_text("{nope")
    chosen, problems = column.load("sb")
    assert chosen.order == list(column.TOOLS) and "unreadable" in problems[0]


def test_deck_toml_panes_names_an_unknown_pane():
    config, problems = deck_.parse({"panes": ["todos", "inbox"]})
    assert config.panes == ["todos"] and any("'inbox'" in p for p in problems)


def test_the_chooser_moves_shows_folds_and_never_hides_the_last_pane():
    from skyboss import column

    chosen = column.Column()
    chosen, at, _ = column.press(chosen, 0, "J")
    assert chosen.order[:2] == ["messages", "queue"] and at == 1
    chosen, at, _ = column.press(chosen, at, " ")
    chosen, at, _ = column.press(chosen, at, "c")
    assert "queue" in chosen.hidden and "queue" in chosen.collapsed and not chosen.folded("queue")
    for role in ("messages", "todos"):
        chosen, _, _ = column.press(chosen, chosen.order.index(role), " ")
    last, _, _ = column.press(chosen, chosen.order.index("decisions"), " ")
    assert last.shown == ["decisions"]
    assert column.press(chosen, 0, "\r")[2] == "apply" and column.press(chosen, 0, "q")[2] == "cancel"


def test_a_folded_summary_counts_what_the_pane_would_draw():
    from skyboss import column

    queue = [{"where": "deck", "status": "waiting"}, {"where": "deck", "status": "idle"}, {"where": "outside"}]
    assert column.summary("queue", queue, note="1 outside hidden") == (
        "AGENT LIST · 1 waiting · 2 in deck · 1 outside hidden"
    )
    items = [
        {"kind": "item", "agent": "ws", "done": False},
        {"kind": "item", "agent": "jam", "done": True},
        {"kind": "item", "agent": "jam", "done": False},
    ]
    assert column.summary("decisions", items) == "HUMAN DECISIONS · 2 open · 2 agents"
    assert (
        column.summary("messages", [{"when": "2m", "between": "ws → jam"}])
        == "AGENT COMMUNICATIONS · 1 shown · last 2m ws → jam"
    )
    assert column.summary("todos", [], ok=False).startswith("AGENT TODOs · ✗")


def test_a_pane_reads_its_fold_and_leaves_when_its_role_is_hidden(fake, home):
    from skyboss.resident import Leave

    fake.session("sb")
    pane = deck_.DeckPane("sb", lambda row: True, role="todos")
    fake.options[("=sb:", "@sb-folded")] = "queue,todos"
    pane.shape(Result_(data=[]))
    assert pane.folded() and pane.summary(Result_(data=[])) == "AGENT TODOs · 0 open · 0 agents"
    fake.options[("=sb:", "@sb-hidden")] = "todos"
    with pytest.raises(Leave):
        pane.shape(Result_(data=[]))


def test_hiding_a_pane_lets_it_close_itself_and_the_deck_kills_nothing(fake, home, sb_state, monkeypatch):
    from skyboss import column

    invoke("deck")
    messages = fake.roles()["messages"]
    column.save("sb", column.Column(hidden={"messages"}, collapsed={"todos"}))
    monkeypatch.setattr(deck_, "_sleep", lambda seconds: fake.panes.pop(messages, None))
    fake.calls.clear()
    _, problems = deck_.arrange("sb", "columns", force=True)
    assert problems == [] and "messages" not in fake.roles()
    assert not {"kill-pane", "respawn-pane", "kill-window"} & set(fake.verbs())
    assert fake.options[("=sb:", "@sb-hidden")] == "messages" and fake.options[("=sb:", "@sb-folded")] == "todos"
    roles = fake.roles()
    tools = [roles[r] for r in ("queue", "todos", "decisions")]
    moves = [call[1:] for call in fake.calls if call[1] in ("join-pane", "resize-pane")]
    assert moves == deck_.plan("columns", roles["tabs"], tools, frozenset({roles["todos"]}))


def test_a_hidden_pane_that_does_not_close_is_said_and_left_in_place(fake, home, sb_state, monkeypatch):
    from skyboss import column

    invoke("deck")
    column.save("sb", column.Column(hidden={"queue"}))
    monkeypatch.setattr(deck_, "_sleep", lambda seconds: None)
    _, problems = deck_.arrange("sb", "columns", force=True)
    assert problems == [
        f"the hidden queue pane has not closed itself after {deck_.HIDE_WAIT:.0f}s — it is left in place"
    ]


def test_fold_names_only_a_right_column_pane_and_saves_without_a_deck(fake, home, sb_state, said):
    from skyboss import column

    refused = invoke("deck", "column", "fold", "tabs")
    assert refused.exit_code == 2 and "not a right-column pane" in said(refused)
    folded = invoke("deck", "column", "fold", "todos")
    assert folded.exit_code == 0 and "saved" in said(folded)
    assert column.load("sb")[0].collapsed == {"todos"}


def test_each_bars_label_is_given_room_for_its_whole_width():
    options = dict(deck_.bar_options(False))
    drawn = re.sub(r"#\[[^]]*\]", "", options["status-left"])
    assert drawn.startswith(" skyrow.labs │ sky.boss deck ⟳ next in ")
    wanted = " skyrow.labs │ sky.boss deck ⟳ next in 5s marks not running "
    assert options["status-left-length"] == str(len(wanted) + 1)
    tabs = dict(deck_.bar_options(True))
    _, width = deck_.tab_lefts()
    assert tabs["status-left-length"] == str(width)


def test_the_footer_names_the_deck_after_its_profile_and_leaves_out_the_window_list():
    options = dict(deck_.bar_options(False, "skyrow-workspace"))
    assert " skyrow-workspace " in options["status-left"] and "sky.boss deck" not in options["status-left"]
    assert int(options["status-left-length"]) > int(dict(deck_.bar_options(False))["status-left-length"])
    assert "#{W:" not in options["status-format[0]"]
    assert "status-left" in options["status-format[0]"] and "status-right" in options["status-format[0]"]


def test_dressing_a_deck_names_its_footer_after_the_live_profile(fake):
    fake.options[("=sb-agents:", "@sb-profile")] = "core"
    deck_.dress_sessions("sb")
    assert " core " in fake.options[("=sb:", "status-left")]


def test_the_mark_leads_every_tab_row_at_one_width():
    from skyboss import theme

    lefts, width = deck_.tab_lefts()
    visible = [re.sub(r"#\[[^]]*\]", "", left) for left in lefts]
    assert [len(v) for v in visible] == [width] * 3  # so every row's boxes start in one column
    assert not any("skyrow" in row for row in visible)  # the wordmark is the footer's
    assert all(v.rstrip().endswith(deck_.SEPARATOR) for v in visible)  # the separator spans all three rows
    assert len(theme.tmux_mark()) == 3 and all(len(row) == len(theme.MARK_PIXELS[0]) for row in theme.MARK_PIXELS)
    base = theme.MARK_PIXELS[-2]
    assert base.rstrip(".") == "B" * len(base.rstrip("."))  # the L's base runs under the whole S
    assert set(theme.MARK_PIXELS[0]) == set(theme.MARK_PIXELS[-1]) == {"."}  # centred: a blank row each side
    rows = dict(deck_.bar_options(True))
    assert all(rows[f"status-format[{n}]"].startswith(f"#[align=left]{lefts[n]}") for n in range(3))


def test_the_mark_is_five_cells_a_row_padded_each_side_with_strokes_one_pixel_thick():
    from skyboss import theme

    marks = [re.sub(r"#\[[^]]*\]", "", row) for row in theme.tmux_mark()]
    assert [len(m) for m in marks] == [theme.MARK_WIDTH] * 3 == [5] * 3
    assert all(re.sub(r"#\[[^]]*\]", "", left).startswith(" " * deck_.MARK_PAD) for left in deck_.tab_lefts()[0])
    stem = [row[0] for row in theme.MARK_PIXELS[1:-1]]
    assert set(stem) == {"B"} and all(row[1] == "." for row in theme.MARK_PIXELS[1:-2])  # the L, one pixel


def test_a_sextant_is_the_glyph_for_its_six_pixels():
    from skyboss import theme

    assert theme._sextant((1, 0, 0, 0, 0, 0)) == "\U0001fb00"
    assert theme._sextant((0, 1, 1, 1, 1, 1)) == "\U0001fb3b"
    assert [theme._sextant(b) for b in ((1, 0, 1, 0, 1, 0), (0,) * 6, (1,) * 6)] == ["▌", " ", "█"]


def test_a_cell_refuses_a_third_colour():
    from skyboss import theme

    assert theme._cell(("a", "b") * 3, "g") == "#[fg=a bg=b]▌"
    with pytest.raises(ValueError):
        theme._cell(("a", "b", None, None, None, None), "g")


def test_the_wordmark_is_white_then_brand_and_bold():
    style = deck_.theme.tmux_styles()
    assert deck_.wordmark().startswith(f"#[{style['wordmark']}]skyrow#[{style['label']}].labs")
    assert "bold" in style["wordmark"] and "bold" in style["label"]


def test_clear_drops_every_agents_done_todos_and_leaves_the_rest(home, sb_state):
    todos.add("sb", "one", "keep")
    todos.add("sb", "one", "finished")
    todos.done("sb", "one", 2)
    todos.add("sb", "two", "open")
    before = todos.load("sb", "two")
    result = invoke("--json", "deck", "todo", "clear")
    one, two = todos.load("sb", "one"), todos.load("sb", "two")
    assert before and one and two
    assert json.loads(result.stdout)["data"] == [{"agent": "one", "cleared": 1}]
    assert [i.text for i in one.items] == ["keep"]
    assert two.updated == before.updated  # untouched, so its place in the pane holds


def test_decide_clear_drops_decided_items_and_keeps_open_questions(home, sb_state):
    todos.add("sb", "ws", "ruled", book=todos.DECISIONS)
    todos.done("sb", "ws", 1, book=todos.DECISIONS, ruling="yes")
    todos.add("sb", "ws", "still open", book=todos.DECISIONS)
    result = invoke("--json", "deck", "decide", "clear")
    assert json.loads(result.stdout)["data"] == [{"agent": "ws", "cleared": 1}]
    kept = todos.load("sb", "ws", todos.DECISIONS)
    assert kept and [i.text for i in kept.items] == ["still open"]


def test_an_emptied_list_drops_out_of_the_pane_but_not_out_of_its_own_view(home, sb_state):
    todos.add("sb", "ws", "done soon")
    todos.done("sb", "ws", 1)
    todos.clear_done("sb")
    rows, _ = todos.rows_of("sb", [("ws", 0)], NOW)
    assert not [r for r in rows if r["agent"] == "ws"]
    alone, _ = todos.rows_of("sb", [("ws", 0)], NOW, only="ws")
    assert [r["kind"] for r in alone] == ["agent", "empty"]


def test_clear_with_nothing_done_says_so(home, sb_state, said):
    todos.add("sb", "one", "open")
    result = invoke("deck", "todo", "clear")
    assert result.exit_code == 0 and "nothing to clear" in said(result)


def test_the_clear_key_runs_the_one_clear_that_says_what_it_kept():
    bound = {argv[3]: argv for argv in deck_.deck_bindings("sb")}
    assert "deck clear --notify" in bound[deck_.SHORTCUTS["clear"]][-1]
    assert f"{deck_.SHORTCUTS['clear']} clear done" in deck_.hints()


def test_a_clear_takes_asked_rows_and_keeps_untold_rulings_and_waiting_prompts(home, sb_state):
    from skyboss import deckasks

    todos.add("sb", "ws", "finished")
    todos.done("sb", "ws", 1)
    todos.add("sb", "ws", "ruled", book=todos.DECISIONS)
    todos.rule("sb", "ws", 1, "yes")
    deckasks._put("sb", "ws", todos.PROSE, "shall I?")
    deckasks._put("sb", "jam", todos.ASKED, "Bash: rm x")
    data = json.loads(invoke("--json", "deck", "clear").stdout)["data"]
    assert (data["todos"], data["decided"], data["asked"], data["kept_untold"], data["kept_waiting"]) == (1, 0, 1, 1, 1)
    assert data["said"].endswith("kept 1 ruling not yet typed into its tab and 1 prompt a tab is waiting at")


def test_a_clear_with_nothing_kept_says_only_what_went():
    assert deck_.clear_sentence(2, 1, 0, 0, 0) == "cleared 2 done todos, 1 decided item and 0 asked rows"


def test_tabs_that_fit_need_no_scrollbar_and_tmux_centres_the_current_one_when_they_do_not():
    assert deck_.visible_span([10, 10, 10], 2, 30) is None
    assert deck_.visible_span([10] * 10, 0, 30) == (0, 30, 100)  # at the start, clamped
    assert deck_.visible_span([10] * 10, 5, 30) == (40, 70, 100)  # centred on the current tab
    assert deck_.visible_span([10] * 10, 9, 30) == (70, 100, 100)  # at the end, clamped


def test_the_scrollbar_lights_the_visible_share_of_its_track():
    bar = re.sub(r"#\[[^]]*\]", "", deck_.scrollbar((40, 70, 100), 30, 4))
    assert bar == " " * 4 + "─" * 12 + "━" * 9 + "─" * 9


def test_the_tab_rows_end_at_their_list_so_the_three_scroll_together():
    rows = [deck_.tab_row(n, "") for n in range(3)]
    assert all("#[list=on]" in row and "#[list=focus]" in row for row in rows)
    assert all(row.count("#[nolist]") == 1 and row.index("#[nolist]") < row.index("range=user|add") for row in rows)


def test_the_marks_time_is_in_the_footer_and_not_the_tab_bar():
    footer, tabs = dict(deck_.bar_options(False)), dict(deck_.bar_options(True))
    assert deck_.marks_text() in footer["status-left"]
    assert not any(deck_.MARKED_OPTION in value for value in tabs.values())


def test_the_deck_rescrolls_on_a_resize_or_a_tab_change():
    hooks = {argv[3]: argv for argv in deck_.scroll_hooks("sb")}
    assert set(hooks) == {"client-resized", "session-window-changed", "window-linked", "window-unlinked"}
    assert all(argv[2] == deck_.scope("sb-agents") and "deck scroll" in argv[-1] for argv in hooks.values())


def test_bare_deck_reloads_a_deck_it_finds_running_and_keeps_its_tabs(fake, home, sb_state, monkeypatch):
    invoke("deck")
    before = {role: pane for role, pane in fake.roles().items() if role in deck_.TOOL_ROLES}
    tabs = {pane for pane in fake.panes if pane not in before.values()}
    monkeypatch.setattr(deck_, "_sleep", lambda s: [fake.panes.pop(p, None) for p in before.values()])
    invoke("deck")
    after = {role: pane for role, pane in fake.roles().items() if role in deck_.TOOL_ROLES}
    assert set(after) == set(before) and not set(after.values()) & set(before.values())
    assert tabs <= set(fake.panes) and not {"kill-pane", "respawn-pane", "kill-window"} & set(fake.verbs())


def test_bare_deck_starting_a_deck_reloads_nothing(fake, home, monkeypatch):
    monkeypatch.setattr(deck_, "reload_session", lambda config: pytest.fail("nothing is running to reload"))
    invoke("deck")
    assert fake.roles()


def test_reload_restarts_every_tool_pane_that_closes_itself_and_kills_none(fake, home, sb_state, monkeypatch):
    invoke("deck")
    before = {role: pane for role, pane in fake.roles().items() if role in deck_.TOOL_ROLES}
    monkeypatch.setattr(deck_, "_sleep", lambda s: [fake.panes.pop(p, None) for p in before.values()])
    fake.calls.clear()
    data = json.loads(invoke("--json", "deck", "reload").stdout)
    after = {role: pane for role, pane in fake.roles().items() if role in deck_.TOOL_ROLES}
    assert set(after) == set(before) and not set(after.values()) & set(before.values())
    assert not {"kill-pane", "respawn-pane", "kill-window"} & set(fake.verbs()) and data["ok"]
    assert fake.options[("=sb:", "@sb-hidden")] == ""


def test_reload_puts_the_marks_loop_on_this_code(fake, home, sb_state, monkeypatch):
    invoke("deck")
    owners = iter([41, 41, None, None])
    stopped = []
    monkeypatch.setattr(deck_, "_sleep", lambda s: None)
    monkeypatch.setattr(deck_, "_marks_owner", lambda session: next(owners))
    monkeypatch.setattr(deck_.os, "kill", lambda pid, sig: stopped.append(pid))
    fake.calls.clear()
    assert deck_.restart_marks("sb") == []
    assert stopped == [41] and "run-shell" in fake.verbs()


def test_reload_says_when_the_old_marks_loop_will_not_leave(fake, home, sb_state, monkeypatch):
    monkeypatch.setattr(deck_, "_sleep", lambda s: None)
    monkeypatch.setattr(deck_, "_marks_owner", lambda session: 41)
    monkeypatch.setattr(deck_.os, "kill", lambda pid, sig: None)
    fake.calls.clear()
    assert "old code" in deck_.restart_marks("sb")[0]
    assert "run-shell" not in fake.verbs()


def test_reload_names_a_pane_too_old_to_close_itself(fake, home, sb_state, monkeypatch):
    invoke("deck")
    monkeypatch.setattr(deck_, "_sleep", lambda s: None)
    data = json.loads(invoke("--json", "deck", "reload").stdout)
    assert data["partial"] and any("press q in it" in w for w in data["warnings"])


def test_every_deck_pane_refreshes_on_the_clocks_multiples_and_draws_no_clock_of_its_own():
    from skyboss import chrome
    from skyboss.resident import Residency

    clock = [12.0]
    state = Residency("deck queue", 5, lambda: clock[0], aligned=True)
    state.begin()
    clock[0] = 14.9
    assert not state.due()
    clock[0] = 15.0
    assert state.due()  # 3 seconds after the first run, because 15 is the boundary
    state.finish(output.Result())
    top, bottom = chrome.status_bands(state.chrome(), 15.0, 80)
    drawn = "".join(text for text, _ in top + bottom)
    assert not any(word in drawn for word in ("next in", "refresh", " ran "))
    own = Residency("sb data", 5, lambda: clock[0])
    own.begin()
    own.finish(output.Result())
    top, bottom = chrome.status_bands(own.chrome(), 15.0, 80)
    drawn = "".join(text for text, _ in top + bottom)
    assert all(word in drawn for word in ("next in", "refresh", " ran "))
    assert deck_.DeckPane("sb", lambda row: True).shared_clock()


def test_the_footer_counts_down_to_the_shared_refresh_every_second():
    options = dict(deck_.bar_options(False))
    assert "⟳ next in #{e|-:5,#{e|%%:%s,5}}s" in options["status-left"]
    assert options["status-interval"] == "1" and "status-interval" not in dict(deck_.bar_options(True))
    assert {argv[argv.index("--refresh") + 1] for argv in (deck_.queue_argv(), deck_.messages_argv())} == {"5"}


# ============================================================================
# Console themes
# ============================================================================


def test_themes_and_their_base_are_declared_in_deck_toml():
    config, problems = deck_.parse({"themes": True, "theme_base": "dark-ansi"})
    assert (config.themes, config.theme_base, problems) == (True, "dark-ansi", [])
    config, problems = deck_.parse({"themes": "yes", "theme_base": "neon"})
    assert config.themes and not config.theme_base and len(problems) == 2  # on is the default
    assert not deck_.parse({"themes": False})[0].themes


def test_a_themed_launch_selects_the_agents_theme_and_the_operators_settings_win():
    themed = deck_.Agent("ws", "/x").launch(themed=True)
    assert themed[-2:] == ["--settings", '{"theme": "custom:sb-ws"}']
    assert "--settings" not in deck_.Agent("ws", "/x").launch()
    own = deck_.Agent("ws", "/x", args=["--settings", "/fx/mine.json"]).launch(themed=True)
    assert own.count("--settings") == 1 and own[-1] == "/fx/mine.json"


def test_a_theme_file_is_the_hue_on_both_accents_and_is_rewritten_only_on_change(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert deck_.write_theme("ws", "#38bdf8", "dark-ansi") == []
    path = tmp_path / "themes" / "sb-ws.json"
    body = json.loads(path.read_text())
    assert body["base"] == "dark-ansi"
    assert body["overrides"] == {
        "claude": "#38bdf8",
        "promptBorder": "#38bdf8",
        "userMessageBackground": deck_.theme.HEAD_GROUND,
    }
    stamp = path.stat().st_mtime_ns
    deck_.write_theme("ws", "#38bdf8", "dark-ansi")
    assert path.stat().st_mtime_ns == stamp
    assert sorted(p.name for p in (tmp_path / "themes").iterdir()) == ["sb-ws.json"]  # no temp left behind


def test_the_base_is_the_operators_preset_unless_declared(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert deck_.theme_base(deck_.Config()) == "dark"  # no settings file
    (tmp_path / "settings.json").write_text('{"theme": "light-ansi"}')
    assert deck_.theme_base(deck_.Config()) == "light-ansi"
    (tmp_path / "settings.json").write_text('{"theme": "custom:mine"}')
    assert deck_.theme_base(deck_.Config()) == "dark"  # a custom theme cannot be a base
    assert deck_.theme_base(deck_.Config(theme_base="dark-ansi")) == "dark-ansi"


def test_a_light_base_keeps_its_own_sent_message_ground():
    assert "userMessageBackground" not in deck_.theme_body("ws", "#38bdf8", "light-ansi")["overrides"]


def test_a_themed_deck_writes_each_tabs_theme_before_launching_it(fake, home, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    home(f'pin = "ws"\nthemes = true\ntheme_base = "dark-ansi"\n[agent.ws]\ncwd = "{tmp_path}"\n')
    invoke("deck")
    created = created_in(fake, "sb-agents")
    assert '{"theme": "custom:sb-ws"}' in created
    body = json.loads((tmp_path / "claude" / "themes" / "sb-ws.json").read_text())
    assert body["overrides"]["claude"] == deck_.theme.agent_colour("ws", 0)


def test_an_unthemed_deck_writes_no_theme(fake, home, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    home(f'pin = "ws"\nthemes = false\n[agent.ws]\ncwd = "{tmp_path}"\n')
    invoke("deck")
    assert not (tmp_path / "claude").exists()


# ============================================================================
# Save and resume
# ============================================================================


def tab(agent, ident="id-1"):
    return deck_.decksave.Tab(agent, ident, "/src")


def saved_as(*tabs, primary="", profile=""):
    deck_.decksave.save("sb", deck_.decksave.Saved(list(tabs), primary, profile))


def transcripts(tmp_path, monkeypatch, *idents):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    (tmp_path / "claude" / "projects" / "-src").mkdir(parents=True)
    for ident in idents:
        (tmp_path / "claude" / "projects" / "-src" / f"{ident}.jsonl").write_text("{}\n")


def test_a_resumed_launch_names_its_session_and_an_operators_own_choice_stays_out():
    assert deck_.Agent("x", "/x").launch(resume="id-1")[-2:] == ["--resume", "id-1"]
    assert "--resume" not in deck_.Agent("x", "/x").launch()
    assert deck_.Agent("x", "/x", args=["--continue"]).picks_session
    assert deck_.Agent("x", "/x", args=["--session-id=abc"]).picks_session
    assert not deck_.Agent("x", "/x", args=["--model", "opus"]).picks_session


def test_a_saved_tab_is_never_dropped_by_a_shutdown_that_kills_tabs_first():
    kept = deck_.decksave.merged([tab("jam", "old"), tab("mind")], [tab("jam", "new")])
    assert kept == [tab("jam", "new"), tab("mind")]
    assert deck_.decksave.merged(kept, []) == kept


def test_an_unreadable_save_says_so_and_resumes_nothing(fake, home):
    path = deck_.decksave.path_for("sb")
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    saved, problems = deck_.decksave.load("sb")
    assert saved.tabs == [] and "unreadable" in problems[0]


def test_a_session_with_no_transcript_starts_new_and_says_so(fake, home, tmp_path, monkeypatch):
    transcripts(tmp_path, monkeypatch, "kept")
    saved_as(tab("jam", "kept"), tab("mind", "lost"))
    problems: list[str] = []
    resumed = deck_.resume_lookup("sb", problems)
    assert resumed(deck_.Agent("jam", "/x")) == "kept"
    assert resumed(deck_.Agent("mind", "/x")) == "" and "is gone" in problems[0]
    assert resumed(deck_.Agent("other", "/x")) == ""


def test_a_session_open_elsewhere_is_not_resumed_twice(fake, home, tmp_path, monkeypatch):
    transcripts(tmp_path, monkeypatch, "id-10")
    saved_as(tab("jam", "id-10"))
    monkeypatch.setattr(deck_.agents_, "providers", lambda: [Adapter([a_session(10)])])
    problems: list[str] = []
    assert deck_.resume_lookup("sb", problems)(deck_.Agent("jam", "/x")) == ""
    assert "open elsewhere" in problems[0]


def test_sb_deck_reopens_the_saved_tabs_and_resumes_each(core, fake, tmp_path, monkeypatch):
    transcripts(tmp_path, monkeypatch, "a", "b")
    saved_as(tab("skyrow-workspace", "a"), tab("mind-head", "b"), primary="skyrow-workspace", profile="core")
    invoke("deck")
    assert "a" in launched(fake, "skyrow-workspace")
    assert "b" in launched(fake, "mind-head")
    assert ("=sb-agents:", "@sb-profile") in fake.options


def test_a_named_profile_opens_its_own_tabs_and_resumes_those_it_can(core, fake, tmp_path, monkeypatch):
    transcripts(tmp_path, monkeypatch, "b", "z")
    saved_as(tab("mind-head", "b"), tab("sky-boss", "z"))
    invoke("deck", "--profile", "core")
    assert "b" in launched(fake, "mind-head") and "--resume" not in launched(fake, "stash-flow")
    with pytest.raises(AssertionError):
        launched(fake, "sky-boss")


def test_fresh_forgets_the_save_and_resumes_nothing(core, fake, tmp_path, monkeypatch):
    transcripts(tmp_path, monkeypatch, "a")
    saved_as(tab("skyrow-workspace", "a"))
    invoke("deck", "--fresh", "--profile", "core")
    assert "--resume" not in launched(fake, "skyrow-workspace")
    assert not deck_.decksave.path_for("sb").exists()


def test_fresh_opens_a_deck_so_a_subcommand_refuses_it(fake, home):
    assert invoke("deck", "--fresh", "brief").exit_code == 2


def test_a_running_deck_is_not_restored_over(core, fake, tmp_path, monkeypatch):
    tabbed(fake)
    transcripts(tmp_path, monkeypatch, "a")
    saved_as(tab("skyrow-workspace", "a"))
    fake.calls.clear()
    invoke("deck")
    with pytest.raises(AssertionError):
        launched(fake, "skyrow-workspace")


def test_open_resumes_a_saved_tab_unless_told_fresh(core, fake, tmp_path, monkeypatch):
    transcripts(tmp_path, monkeypatch, "a")
    saved_as(tab("mind-head", "a"))
    invoke("--json", "deck", "open", "mind-head")
    assert "a" in launched(fake, "mind-head")
    fake.calls.clear()
    fake.windows.clear()
    fake.panes.clear()
    fake.order.clear()
    invoke("--json", "deck", "open", "mind-head", "--fresh")
    assert "--resume" not in launched(fake, "mind-head")


def test_the_marks_loop_saves_what_changed_and_only_that(fake, home, monkeypatch):
    tabbed(fake)
    monkeypatch.setattr(deck_, "parents", lambda proc=None: {})
    writes = []
    real = deck_.decksave.save
    monkeypatch.setattr(deck_.decksave, "save", lambda *a: (writes.append(a), real(*a)))
    for _ in range(2):
        deck_.marks_once("sb", {}, [Adapter([a_session(10)])])
    assert len(writes) == 1
    assert [(t.agent, t.id) for t in deck_.decksave.load("sb")[0].tabs] == [("jam", "id-10")]


def test_save_writes_exactly_the_open_tabs(fake, home, monkeypatch):
    tabbed(fake)
    saved_as(tab("closed", "old"), tab("mind", "kept"))
    monkeypatch.setattr(deck_, "parents", lambda proc=None: {})
    monkeypatch.setattr(deck_.agents_, "providers", lambda: [Adapter([a_session(10)])])
    result = invoke("--json", "deck", "save")
    assert result.exit_code == 0, result.output
    assert [(t.agent, t.id) for t in deck_.decksave.load("sb")[0].tabs] == [("jam", "id-10"), ("mind", "kept")]


def test_save_says_which_tab_it_could_not_save(fake, home, monkeypatch):
    tabbed(fake)
    monkeypatch.setattr(deck_, "parents", lambda proc=None: {})
    monkeypatch.setattr(deck_.agents_, "providers", lambda: [Adapter([a_session(10)])])
    result = invoke("--json", "deck", "save")
    assert result.exit_code == 3 and "no session to save for mind" in result.stdout


def test_exit_saves_the_tabs_it_ends(fake, home, monkeypatch):
    tabbed(fake)
    monkeypatch.setattr(deck_, "parents", lambda proc=None: {})
    monkeypatch.setattr(deck_.agents_, "providers", lambda: [Adapter([a_session(10), a_session(20)])])
    data = json.loads(invoke("--json", "deck", "exit").stdout)["data"]
    assert data["saved"] == 2 and len(deck_.decksave.load("sb")[0].tabs) == 2


# Colours by default, decisions by click, the grid, quiet jobs


def jam_decisions() -> list:
    from skyboss import todos

    book = todos.load("sb", "jam", todos.DECISIONS)
    assert book is not None
    return book.items


def test_an_agent_may_declare_a_theme_hue_and_nothing_else(home, tmp_path):
    from skyboss import theme

    home(f'[agent.ws]\ncwd = "{tmp_path}"\ncolour = "mh"\n[agent.jam]\ncwd = "{tmp_path}"\ncolour = "#ff0000"\n')
    config, problems = deck_.load(tmp_path)
    assert config.agents["ws"].colour == "mh" and not config.agents["jam"].colour
    assert len(problems) == 1 and "colour must be one of" in problems[0]
    assert theme.agent_colour("ws", 3) == theme.PRODUCT_HUES["mh"] and theme.agent_role("ws", 3) == "sb.agent.mh"
    (tmp_path / "deck.toml").unlink()
    deck_.load(tmp_path)
    assert not theme.DECLARED_HUES


def test_every_declarable_hue_has_a_role_in_the_deck():
    from skyboss import theme

    assert {f"sb.agent.{hue}" for hue in theme.hue_names()} == set(theme.DECK_ROLES)


def test_the_border_takes_the_current_tabs_colour_and_the_brand_before_it_has_one(fake):
    fake.current = "#a78bfa"
    deck_.border_follows_tab("sb")
    assert fake.options[("=sb:", "pane-active-border-style")] == "fg=#a78bfa"
    fake.current = ""
    deck_.border_follows_tab("sb")
    assert fake.options[("=sb:", "pane-active-border-style")] == deck_.theme.tmux_styles()["border-active"]


def test_every_job_the_deck_hands_tmux_exits_zero(fake):
    """tmux prints a job's non-zero exit over the current pane, in view-mode."""
    commands = [argv for argv in deck_.deck_bindings("sb") if "run-shell" in argv]
    commands += deck_.scroll_hooks("sb")
    assert len(commands) >= 6
    assert all("|| true" in " ".join(argv) and "exec " not in " ".join(argv) for argv in commands)


def test_the_layout_cycles_through_all_three_and_the_footer_button_with_it():
    assert deck_.next_layout() == "#{?#{==:#{@sb-layout},stack},grid,#{?#{==:#{@sb-layout},grid},columns,stack}}"
    (key,) = [argv for argv in deck_.deck_bindings("sb") if argv[3] == deck_.SHORTCUTS["layout"]]
    assert key[4:6] == ["run-shell", "-b"] and deck_.next_layout() in key[6]
    assert "#[range=user|layout]" in deck_.hints()


def test_a_grid_is_two_columns_of_two_read_across():
    calls = deck_.plan("grid", "%0", ["%1", "%2", "%3", "%4"])
    joins = [(c[c.index("-s") + 1], c[c.index("-t") + 1], c[2]) for c in calls if c[0] == "join-pane"]
    assert joins == [("%1", "%0", "-h"), ("%2", "%1", "-h"), ("%3", "%1", "-v"), ("%4", "%2", "-v")]


def test_a_grid_with_fewer_than_four_panes_is_columns():
    assert deck_.plan("grid", "%0", ["%1", "%2"]) == deck_.plan("columns", "%0", ["%1", "%2"])


def test_a_folded_grid_pane_is_one_line_and_its_column_mate_takes_the_room():
    calls = deck_.plan("grid", "%0", ["%1", "%2", "%3", "%4"], frozenset({"%3"}))
    assert ["resize-pane", "-t", "%3", "-y", "1"] in calls
    assert ["resize-pane", "-t", "%1", "-y", "50%"] not in calls
    assert ["resize-pane", "-t", "%2", "-y", "50%"] in calls


def test_a_decision_keeps_its_options_and_a_click_or_a_key_picks_one(sb_state):
    from skyboss import todos

    todos.add("sb", "jam", "take it?", todos.DECISIONS, ("take it", "hold ours"))
    item = jam_decisions()[0]
    lines = deck_.ruling_screen("jam", 1, item, 60)
    row = next(y for y, (text, _) in enumerate(lines, start=1) if text.strip() == "[2] hold ours")
    assert deck_.chosen_key(f"click:3:{row}", lines) == "2" and deck_.chosen_key("1", lines) == "1"
    assert deck_.chosen_key("3", lines) == "" and deck_.chosen_key("click:1:1", lines) == ""
    assert deck_.chosen_key("t", lines) == "t" and deck_.chosen_key(None, lines) == ""


def test_a_decision_with_no_options_offers_typing_and_a_ruled_one_only_closes(sb_state):
    from skyboss import todos

    todos.add("sb", "jam", "what now?", todos.DECISIONS)
    item = jam_decisions()[0]
    assert [action for _, action in deck_.ruling_screen("jam", 1, item, 60) if action] == ["t", "q"]
    todos.rule("sb", "jam", 1, "ship it")
    item = jam_decisions()[0]
    screen = deck_.ruling_screen("jam", 1, item, 60)
    assert [action for _, action in screen if action] == ["q"] and any("ship it" in text for text, _ in screen)


def test_a_decision_popup_titles_each_section_after_a_blank_row(sb_state):
    from skyboss import todos

    todos.add("sb", "jam", "take it?", todos.DECISIONS, ("take it", "hold ours"))
    lines = [text for text, _ in deck_.ruling_screen("jam", 1, jam_decisions()[0], 62)]
    heads = [i for i, text in enumerate(lines) if "─" in text]
    assert [plain(lines[i]).split()[0] for i in heads] == ["jam", "Choose", "Or"]
    assert all(lines[i - 1] == "" for i in heads) and all(len(plain(text)) <= 62 for text in lines)


def test_a_decision_popup_is_small_rounded_and_lightly_bordered(sb_state):
    from skyboss import todos

    todos.add("sb", "jam", "take it?", todos.DECISIONS, ("take it", "hold ours"))
    argv = deck_.decision_popup_argv("jam", 1, jam_decisions()[0])
    shown = deck_.ruling_screen("jam", 1, jam_decisions()[0], deck_.ASK_POPUP_WIDTH - 2)
    assert argv[argv.index("-b") + 1] == "rounded" and argv[argv.index("-S") + 1] == deck_.theme.tmux_styles()["border"]
    assert argv[argv.index("-w") + 1] == str(deck_.ASK_POPUP_WIDTH) and argv[argv.index("-h") + 1] == str(
        len(shown) + 3
    )


def plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_a_click_in_the_decisions_pane_opens_that_decision(monkeypatch):
    opened = []
    monkeypatch.setattr(deck_, "open_decision", lambda agent, n, session: opened.append((agent, n)))
    pane = deck_.DeckPane("sb", lambda row: True, top=True, role=deck_.DECISIONS)
    pane.lines = ["DECISIONS", "──────", "jam", "  1. take it?"]
    pane.rows = [{"kind": "agent", "agent": "jam", "n": ""}, {"kind": "item", "agent": "jam", "n": 1}]
    pane.on_key("click:4:3")
    assert not opened
    pane.on_key("click:4:4")
    assert opened == [("jam", 1)]


def test_a_ruling_is_refused_inside_a_tab_and_off_a_terminal(fake, home, sb_state, monkeypatch):
    from skyboss import todos

    todos.add("sb", "jam", "take it?", todos.DECISIONS)
    assert invoke("deck", "decide", "rule", "jam", "1").exit_code == 1  # CliRunner has no terminal
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)
    monkeypatch.setattr(deck_, "caller_tab", lambda session: "jam")
    assert "inside a deck tab" in invoke("deck", "decide", "rule", "jam", "1").output
    assert not jam_decisions()[0].done


def test_an_untold_ruling_is_typed_once_into_an_idle_tab_and_not_at_once_into_a_busy_one(fake, sb_state):
    from skyboss import todos

    fake.add("sb-agents", "jam", agent="jam", role="agent", pid=10)
    listed, _ = deck_.panes("sb-agents")
    window, labels = listed[0].window_id, {listed[0].window_id: "jam"}
    todos.add("sb", "jam", "take it?", todos.DECISIONS)
    todos.rule("sb", "jam", 1, "hold ours")
    fake.current = "0"
    assert deck_.tell_rulings("sb", listed, {window: "busy"}, labels) == [] and not fake.find("send-keys")
    deck_.tell_rulings("sb", listed, {window: "idle"}, labels)
    typed = fake.find("send-keys")
    assert typed[0][-2:] == ["-l", 'The operator ruled on your decision 1, "take it?": hold ours']
    assert typed[1][-1] == "Enter" and not jam_decisions()[0].untold
    deck_.tell_rulings("sb", listed, {window: "idle"}, labels)
    assert len(fake.find("send-keys")) == 2


def _jam_tab(fake):
    fake.add("sb-agents", "jam", agent="jam", role="agent", pid=10)
    listed, _ = deck_.panes("sb-agents")
    fake.current = "0"
    return listed, listed[0].window_id, {listed[0].window_id: "jam"}


def test_a_stale_todo_is_put_to_an_idle_tab_once_and_counts_again_from_then(fake, sb_state):
    from skyboss import todos

    listed, window, labels = _jam_tab(fake)
    todos.add("sb", "jam", "port the round")
    later = datetime.now(timezone.utc) + timedelta(hours=7)
    assert deck_.tell_rulings("sb", listed, {window: "busy"}, labels, later, 6 * 3600) == []
    assert not fake.find("send-keys")
    deck_.tell_rulings("sb", listed, {window: "idle"}, labels, later, 6 * 3600)
    typed = fake.find("send-keys")
    assert "todo 1 has been open over" in typed[0][-1] and "sb deck todo rm <n>" in typed[0][-1]
    kept = todos.load("sb", "jam")
    assert kept is not None and kept.items[0].checked
    deck_.tell_rulings("sb", listed, {window: "idle"}, labels, later, 6 * 3600)
    assert len(fake.find("send-keys")) == 2


def test_a_ruling_still_to_be_told_goes_before_a_recheck(fake, sb_state):
    from skyboss import todos

    listed, window, labels = _jam_tab(fake)
    todos.add("sb", "jam", "port the round")
    todos.add("sb", "jam", "take it?", todos.DECISIONS)
    todos.rule("sb", "jam", 1, "hold ours")
    later = datetime.now(timezone.utc) + timedelta(hours=7)
    deck_.tell_rulings("sb", listed, {window: "idle"}, labels, later, 6 * 3600)
    assert fake.find("send-keys")[0][-1].startswith("The operator ruled")


def test_no_recheck_when_stale_is_off_or_the_todo_is_fresh(fake, sb_state):
    from skyboss import todos

    listed, window, labels = _jam_tab(fake)
    todos.add("sb", "jam", "port the round")
    later = datetime.now(timezone.utc) + timedelta(hours=7)
    deck_.tell_rulings("sb", listed, {window: "idle"}, labels, later, 0)
    deck_.tell_rulings("sb", listed, {window: "idle"}, labels, datetime.now(timezone.utc), 6 * 3600)
    assert not fake.find("send-keys")


def test_a_stale_todo_is_marked_in_the_pane_and_a_done_one_never_is(sb_state):
    from skyboss import todos

    todos.add("sb", "jam", "port the round")
    todos.add("sb", "jam", "shipped")
    todos.done("sb", "jam", 2)
    later = datetime.now(timezone.utc) + timedelta(hours=7)
    rows, _ = todos.rows_of("sb", [("jam", 0)], later, only="jam")
    marked = ["stale" in "".join(str(p[0]) for p in r["parts"]) for r in rows if r.get("n")]
    assert marked == [True, False]


def test_a_finished_turn_with_a_background_job_takes_a_ruling_at_once(fake, sb_state):
    from skyboss import todos

    fake.add("sb-agents", "jam", agent="jam", role="agent", pid=10)
    listed, _ = deck_.panes("sb-agents")
    todos.add("sb", "jam", "take it?", todos.DECISIONS)
    todos.rule("sb", "jam", 1, "hold ours")
    fake.current = "0"
    deck_.tell_rulings("sb", listed, {listed[0].window_id: "shell"}, {listed[0].window_id: "jam"})
    assert fake.find("send-keys") and not jam_decisions()[0].untold


def test_a_busy_tab_takes_a_ruling_only_once_it_has_waited(fake, sb_state):
    from skyboss import todos

    fake.add("sb-agents", "jam", agent="jam", role="agent", pid=10)
    listed, _ = deck_.panes("sb-agents")
    window, labels = listed[0].window_id, {listed[0].window_id: "jam"}
    todos.add("sb", "jam", "take it?", todos.DECISIONS)
    todos.rule("sb", "jam", 1, "hold ours")
    fake.current = "0"
    closed = datetime.fromisoformat(jam_decisions()[0].closed)
    early = closed + timedelta(seconds=deck_.BUSY_TELL_AFTER - 1)
    late = closed + timedelta(seconds=deck_.BUSY_TELL_AFTER)
    deck_.tell_rulings("sb", listed, {window: "busy"}, labels, now=early)
    assert not fake.find("send-keys") and jam_decisions()[0].untold
    deck_.tell_rulings("sb", listed, {window: "busy"}, labels, now=late)
    assert fake.find("send-keys") and not jam_decisions()[0].untold


def test_a_tab_at_a_prompt_never_takes_a_ruling_however_long_it_waited(fake, sb_state):
    from skyboss import todos

    fake.add("sb-agents", "jam", agent="jam", role="agent", pid=10)
    listed, _ = deck_.panes("sb-agents")
    todos.add("sb", "jam", "take it?", todos.DECISIONS)
    todos.rule("sb", "jam", 1, "hold ours")
    fake.current = "0"
    later = datetime.now(timezone.utc) + timedelta(days=1)
    deck_.tell_rulings("sb", listed, {listed[0].window_id: deck_.WAITING}, {listed[0].window_id: "jam"}, now=later)
    assert not fake.find("send-keys") and jam_decisions()[0].untold


def test_a_scrolled_tab_waits_for_its_ruling(fake, sb_state):
    from skyboss import todos

    fake.add("sb-agents", "jam", agent="jam", role="agent", pid=10)
    listed, _ = deck_.panes("sb-agents")
    todos.add("sb", "jam", "take it?", todos.DECISIONS)
    todos.rule("sb", "jam", 1, "hold ours")
    fake.current = "1"
    deck_.tell_rulings("sb", listed, {listed[0].window_id: "idle"}, {listed[0].window_id: "jam"})
    assert not fake.find("send-keys") and jam_decisions()[0].untold


def test_clearing_keeps_a_ruling_its_agent_has_not_heard(sb_state):
    from skyboss import todos

    todos.add("sb", "jam", "a", todos.DECISIONS)
    todos.add("sb", "jam", "b", todos.DECISIONS)
    todos.rule("sb", "jam", 1, "yes")
    todos.done("sb", "jam", 2, todos.DECISIONS, "no")
    todos.clear_done("sb", todos.DECISIONS)
    assert [item.text for item in jam_decisions()] == ["a"]


def test_a_clear_takes_an_open_notice_as_read_and_keeps_open_asks(sb_state):
    from skyboss import todos

    todos.add("sb", "jam", "news", todos.DECISIONS, kind=todos.NOTICE)
    todos.add("sb", "jam", "take it?", todos.DECISIONS, ("yes",))
    todos.add("sb", "jam", "merge", todos.DECISIONS, kind=todos.ACTION, run=["gh"])
    todos.clear_done("sb", todos.DECISIONS)
    assert [item.text for item in jam_decisions()] == ["take it?", "merge"]


def test_a_titled_band_is_the_label_alone_with_no_corners():
    facts = chrome_.Chrome(source="deck todo", shape="resident", title="AGENT TODOs")
    top, bottom = chrome_.status_lines(facts, 0.0, 30)
    assert top.startswith("AGENT TODOs ─") and top.endswith("─") and len(top) == 30
    assert "┌" not in top and "deck todo" not in top and bottom.startswith("└")


def test_a_titled_band_keeps_the_count_when_the_title_must_give_way():
    facts = chrome_.Chrome(source="x", shape="resident", title="AGENT COMMUNICATIONS", place="26 earlier")
    top, _ = chrome_.status_lines(facts, 0.0, 26)
    assert top.endswith(" 26 earlier") and len(top) == 26


def test_a_band_with_no_title_is_unchanged():
    assert chrome_.status_lines(chrome_.Chrome(source="deck", shape="resident"), 0.0, 20)[0].startswith("┌ deck")


def test_a_fit_with_a_place_keeps_its_count_out_of_the_body():
    from rich.text import Text

    from skyboss.resident import fitted

    said: list[str] = []

    def fit(result, keep):
        return Result_(data=result.data[:keep]), f"{len(result.data) - keep} below"

    def drawn(result):
        return Text("\n".join(str(n) for n in result.data))

    data = Result_(data=list(range(9)))
    shown = fitted(data, drawn(data), 4, fit, drawn, place=said.append)
    assert shown.plain.split("\n") == ["0", "1", "2", "3"] and said[-1] == "5 below"
    assert fitted(data, drawn(data), 20, fit, drawn, place=said.append).plain.count("\n") == 8 and said[-1] == ""


def test_the_book_panes_drop_their_column_heading_and_keep_the_rule(monkeypatch):
    from skyboss import todos as todos_

    rows = [{"kind": "item", "parts": [["a", ""]], "agent": "x", "n": 1}]
    pane = deck_.DeckPane("sb", lambda row: True, top=True, role="decisions")
    pane.poll = lambda: None
    shaped = pane.shape(Result_(data=rows, view=todos_.view_of(rows, "decisions")))
    assert [column["label"] for column in shaped.view["columns"]] == [""]
    with output.capture(width=30) as captured:
        output.render(shaped, as_json=False)
    assert "decisions" not in captured.text.lower() and "─" * 5 in captured.text


def test_a_click_finds_its_row_under_a_titled_band():
    rows = [{"n": 1}, {"n": 2}]
    lines = ["", " AGENT TODOs ──────── ", " ───────── ", " one", " two"]
    assert deck_.clicked_row(lines, rows, 5) == {"n": 2}


def test_a_grid_lays_out_any_split_of_columns():
    calls = deck_.plan("grid", "%0", ["%1", "%2", "%3", "%4"], groups=[["%1"], ["%2", "%3", "%4"]])
    joins = [call[call.index("-s") + 1 : call.index("-s") + 4 : 2] for call in calls if call[0] == "join-pane"]
    assert joins == [["%1", "%0"], ["%2", "%1"], ["%3", "%2"], ["%4", "%3"]]
    assert ["resize-pane", "-t", "%1", "-x", "20%"] in calls
    assert ["resize-pane", "-t", "%2", "-y", "33%"] in calls


def test_three_columns_share_the_room_the_grid_gives_them():
    calls = deck_.plan("grid", "%0", ["%1", "%2", "%3"], groups=[["%1"], ["%2"], ["%3"]])
    assert ["resize-pane", "-t", "%1", "-x", "13%"] in calls and ["resize-pane", "-t", "%2", "-x", "13%"] in calls


def test_a_grid_of_one_column_is_columns():
    assert deck_.plan("grid", "%0", ["%1", "%2"], groups=[["%1", "%2"]]) == deck_.plan("columns", "%0", ["%1", "%2"])


def test_a_profiles_columns_are_read_and_an_unknown_pane_is_named():
    body = {"primary": "a", "columns": [["messages"], ["queue", "todos", "decisions"]]}
    config, problems = deck_.parse({"profile": {"p": body}})
    assert config.profiles["p"].columns == body["columns"] and not problems
    assert any("columns must" in p for p in deck_.parse({"profile": {"p": {"primary": "a", "columns": [["x"]]}}})[1])


def test_the_columns_default_to_two_and_two_read_across():
    assert deck_.column_.Column().groups() == [["queue", "todos"], ["messages", "decisions"]]


def test_a_saved_column_beats_a_declared_one_and_a_hidden_pane_drops_out():
    chosen = deck_.column_.Column(columns=[["todos"], ["queue", "messages", "decisions"]], hidden={"messages"})
    assert chosen.groups([["queue"]]) == [["todos"], ["queue", "decisions"]]


def test_a_pane_no_column_names_joins_the_last():
    assert deck_.column_.Column().groups([["messages"], ["queue"]]) == [["messages"], ["queue", "todos", "decisions"]]


def test_sending_a_pane_puts_it_ahead_of_the_one_clicked():
    groups = [["queue", "todos"], ["messages", "decisions"]]
    assert deck_.column_.send(groups, "todos", "decisions") == [["queue"], ["messages", "todos", "decisions"]]


def test_a_pane_alone_in_its_column_swaps_so_no_column_empties():
    groups = [["messages"], ["queue", "todos", "decisions"]]
    assert deck_.column_.send(groups, "messages", "todos") == [["todos"], ["queue", "messages", "decisions"]]


def test_sending_a_pane_within_its_own_column_changes_nothing():
    groups = [["queue", "todos"], ["messages"]]
    assert deck_.column_.send(groups, "queue", "todos") == groups


def test_the_command_makes_a_new_column_and_refuses_to_empty_one():
    groups = [["queue", "todos"], ["messages"]]
    assert deck_.column_.place(groups, "todos", 3) == [["queue"], ["messages"], ["todos"]]
    with pytest.raises(ValueError, match="alone"):
        deck_.column_.place(groups, "messages", 1)
    with pytest.raises(ValueError, match="not one"):
        deck_.column_.place(groups, "queue", 4)


def test_a_fold_and_a_show_keep_the_columns():
    chosen = deck_.column_.Column(columns=[["queue"], ["messages", "todos", "decisions"]])
    assert deck_.column_.press(chosen, 0, "c")[0].columns == chosen.columns
    assert deck_.column_.press(chosen, 0, " ")[0].columns == chosen.columns
    assert deck_.column_.move(chosen, 0, 1)[0].columns == chosen.columns


def test_columns_survive_a_save():
    chosen = deck_.column_.Column(columns=[["queue"], ["messages", "todos", "decisions"]])
    deck_.column_.save("sb", chosen)
    assert deck_.column_.load("sb")[0].columns == chosen.columns


def clicked_pane(fake, role: str, layout: str = "grid") -> deck_.DeckPane:
    fake.session("sb")
    fake.options[("=sb:", deck_.LAYOUT_OPTION)] = layout
    pane = deck_.DeckPane("sb", lambda row: True, role=role)
    pane.lines = ["", f" {pane.title} ──────── ", " ──────── "]
    return pane


def test_a_title_click_picks_a_pane_up_and_a_second_puts_it_down(fake, home):
    pane = clicked_pane(fake, "todos")
    assert pane.on_key("click:3:2") and fake.options[("=sb:", deck_.MOVING_OPTION)] == "todos"
    assert pane.band_place() == "moving · click a column"
    assert pane.on_key("click:3:2") and pane.moving == "" and pane.band_place() == ""


def test_a_title_click_outside_the_grid_says_where_moving_works(fake, home):
    pane = clicked_pane(fake, "todos", "columns")
    assert pane.on_key("click:3:2") and "grid" in pane.band_place()
    assert ("=sb:", deck_.MOVING_OPTION) not in fake.options


def test_a_click_in_another_pane_sends_the_picked_up_one_there(fake, home, monkeypatch):
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(deck_, "send_pane", lambda *args: sent.append(args) or [])
    pane = clicked_pane(fake, "decisions")
    fake.options[("=sb:", deck_.MOVING_OPTION)] = "todos"
    assert pane.on_key("click:3:9") and sent == [("sb", "todos", "decisions")]


def test_a_todo_row_click_opens_nothing(fake, home, monkeypatch):
    opened: list[tuple] = []
    monkeypatch.setattr(deck_, "open_decision", lambda *args: opened.append(args))
    pane = clicked_pane(fake, "todos")
    pane.lines += [" one"]
    pane.rows = [{"kind": "item", "agent": "a", "n": 1}]
    assert not pane.on_key("click:3:4") and not opened


# ============================================================================
# Several decks: each profile its own session, and each tab told which deck it is in
# ============================================================================


def test_a_tab_acts_on_the_deck_its_environment_names(home, monkeypatch):
    home('session = "work"\n')
    monkeypatch.setenv("SB_DECK", "sb-core")
    config, _ = deck_.load()
    assert (config.session, config.base) == ("sb-core", "work")


@pytest.mark.parametrize(
    "body, expected",
    [({}, "sb-core"), ({"session": "mine"}, "mine")],
)
def test_a_profile_runs_as_its_own_deck(body, expected):
    config, _ = parse({"profile": {"core": {"tabs": ["x"], **body}, "a.b": {"tabs": ["x"]}}})
    assert deck_.deck_session(config, config.profiles["core"]) == expected
    assert deck_.deck_session(config, config.profiles["a.b"]) == "sb-a_b"
    assert deck_.deck_session(config, None) == "sb"


def test_a_profiles_deck_starts_as_its_own_session_and_marks_its_environment(fake, home, tmp_path):
    home(f'[profile.core]\nprimary = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\n')
    invoke("deck", "--profile", "core")  # no terminal to attach to, so only the sessions are asked about
    created = [call for call in fake.find("new-session") if "-s" in call]
    assert {call[call.index("-s") + 1] for call in created} == {"sb-core", "sb-core-agents"}
    assert all(f"SB_DECK=sb-core" in call for call in created)
    assert ["tmux", "set-environment", "-t", "=sb-core", "SB_DECK", "sb-core"] in fake.calls


def test_ticked_folders_start_beside_a_running_base_deck(fake, home, monkeypatch):
    fake.session("sb-agents")
    assert deck_.free_session("sb") == "sb-2"


def test_profile_list_says_which_deck_each_runs_as(fake, home, tmp_path):
    home(f'[profile.core]\nprimary = "ws"\n[agent.ws]\ncwd = "{tmp_path}"\n')
    data = json.loads(invoke("--json", "deck", "profile", "list").output)["data"]
    assert data == [{"profile": "core", "tabs": "ws", "deck": "sb-core", "running": False}]


def test_profile_delete_backs_up_and_removes_only_that_profile(fake, home, tmp_path):
    path = (
        home(f'[agent.ws]\ncwd = "{tmp_path}"\n\n[profile.core]\nprimary = "ws"\n\n[profile.solo]\nprimary = "ws"\n')
        / "deck.toml"
    )
    assert invoke("deck", "profile", "delete", "core").exit_code == 0
    assert "[profile.core]" not in path.read_text() and "[profile.solo]" in path.read_text()
    assert list((tmp_path / "backups").glob("deck.*.toml"))


def test_profile_save_writes_the_decks_tabs_and_keeps_a_replaced_profiles_brief(fake, home, tmp_path, monkeypatch):
    path = (
        home(f'[agent.ws]\ncwd = "{tmp_path}"\n\n[profile.core]\nprimary = "ws"\nbrief_file = "core.md"\n')
        / "deck.toml"
    )
    fake.session("sb-agents")
    monkeypatch.setattr(deck_, "deck_as_profile", lambda config, s: (("ws", "new"), ("/tmp",), {"new": str(tmp_path)}))
    assert invoke("deck", "profile", "save", "core").exit_code != 0
    assert invoke("deck", "profile", "save", "core", "--replace").exit_code == 0
    written = tomllib.loads(path.read_text())
    assert written["profile"]["core"] == {
        "primary": "ws",
        "tabs": ["new"],
        "terminals": ["/tmp"],
        "brief_file": "core.md",
    }
    assert written["agent"]["new"] == {"cwd": str(tmp_path)}


def test_profile_list_says_so_when_there_are_none(monkeypatch, tmp_path):
    monkeypatch.setattr(deck_, "running_decks", lambda: [])
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    out = json.loads(CliRunner().invoke(cli, ["--json", "deck", "profile", "list"]).stdout)
    assert out["data"] == [] and out["ok"] and "no profiles" in out["warnings"][0]
