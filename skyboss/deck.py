"""`sb deck` — a tmux controller over the operator's agents. See [[command-deck]].

**The deck acts, and says so on every subcommand.** It starts the real `claude`
in a window and moves the operator between windows. It never types into an
agent: there is no key injection anywhere in this module, and a test greps for
it, because a deck that could answer a prompt would be a second permission path.

**It never edits the operator's config.** Not `~/.tmux.conf`, not `~/.claude/`.
`window-size` and `allow-passthrough` are window options, so they are set on the
deck's own windows; `extended-keys` is a server option, so it is read and
reported, never set.

**Every tmux call goes through `RUNNER`**, one function the suite replaces, so
no test needs a tmux binary.

**Two sessions, one server.** The outer session's window 0 is the controller;
project agents are windows of an inner session, shown by a nested client in the
middle pane, so the inner status bar is the tab row. Session options (`mouse`,
`status`) are set per session, never with `-g`.
"""

from __future__ import annotations

import functools
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
import tomllib
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import rich_click as click

from skyboss import agents as agents_
from skyboss import column as column_
from skyboss import decksave
from skyboss import keys as keys_
from skyboss import resident as resident_
from skyboss import theme
from skyboss import todos as todos_
from skyboss.chrome import ago, clock
from skyboss.helpers import PROJECT_ROOT, SB_HOME, child_env, mark

#: The Claude Code plugin every deck tab loads with `--plugin-dir`; see `plugin/` at the repo root.
PLUGIN_DIR = PROJECT_ROOT / "plugin"
from skyboss.messages import message_result, messages_result
from skyboss.output import Result, emit, warn_now
from skyboss.view import describe

DECK_FILE = "deck.toml"
DEFAULT_SESSION = "sb"
TOP_LEVEL_KEYS = frozenset({"session", "pin", "panes", "themes", "theme_base"})
TOP_LEVEL_TABLES = frozenset({"agent", "profile"})
AGENT_KEYS = frozenset({"cwd", "args", "role", "colour"})
PROFILE_KEYS = frozenset({"primary", "tabs", "brief"})

# tmux rewrites `.` and `:` in a session name, so a name carrying either would
# be a session the deck could create and then never find again.
SESSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
# A window name is only a label — every lookup goes by window id — so a dot is
# fine here, which `skyrowlabs.com`-shaped project names need.
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# User options the deck writes on what it starts, and reads back to find it.
# Window: which agent this window was opened for. Pane: what the deck put there.
# Session: which shape the controller window was last arranged in.
AGENT_OPTION = "@sb-agent"
ROLE_OPTION = "@sb-deck"
LAYOUT_OPTION = "@sb-layout"
# Window: the registry's word for the tab's session. Session: when the marks were last
# written (deck, for the footer), and the pid of the one loop that writes them (tabs).
STATE_OPTION = "@sb-state"
COLOUR_OPTION = "@sb-colour"
MARKED_OPTION = "@sb-marked"
MARKS_PID_OPTION = "@sb-marks-pid"
# The folded tool panes, comma-separated, on the deck session: each pane reads it every frame.
FOLDED_OPTION = "@sb-folded"
# The hidden ones: a pane that finds its role here ends its own residency, so no pane is ever killed.
HIDDEN_OPTION = "@sb-hidden"
# How long `arrange` waits for a hidden pane to close itself, polled every `HIDE_POLL` seconds.
HIDE_WAIT = 3.0
HIDE_POLL = 0.2

# Pane roles. `agent` runs claude; `tabs` is the nested client showing the inner
# session; `shell` is the inner session's first window, so it is never empty.
AGENT, TABS, QUEUE, MESSAGES, SHELL = "agent", "tabs", "queue", "messages", "shell"
TODOS = "todos"
DECISIONS = "decisions"
# The right column's panes, in their default order; `skyboss/column.py` holds the operator's choice.
TOOL_ROLES = (QUEUE, MESSAGES, TODOS, DECISIONS)

# The inner session holding one window per project agent. Its status bar is the tab row.
INNER_SUFFIX = "-agents"

# The controller's two shapes, and its sizes. Constants until somebody needs to declare them.
COLUMNS, STACK, GRID = "columns", "stack", "grid"
LAYOUTS = (COLUMNS, STACK, GRID)
TOOLS_WIDTH = "25%"
TOOLS_HEIGHT = "30%"
#: Each of a grid's two columns, so two panes fit across: the tabs keep the rest.
GRID_COLUMN = "20%"
GRID_TABS = "60%"
HALF = "50%"
# One cadence for every tool pane, on the clock's multiples of it, so the footer's one countdown is true of all.
TOOLS_REFRESH = 5
# A folded pane's size: one line in columns, a narrow strip in stack.
FOLDED_HEIGHT = "1"
FOLDED_WIDTH = "16"
MARKS_EVERY = 3

# The registry's word for a session held at a permission prompt (measured on Claude
# Code 2.1.318), and sky.boss's word for a deck window whose process has no record.
WAITING = "waiting"
UNREGISTERED = "unregistered"


# ============================================================================
# Config: $SB_HOME/deck.toml
# ============================================================================


@dataclass
class Agent:
    """One thing the deck can open: a `claude` in a directory."""

    name: str
    cwd: str
    args: list[str] = field(default_factory=list)
    source: str = DECK_FILE
    # One line the operator wrote about this agent, printed beside it in every roster.
    role: str = ""
    # A hue from `theme.hue_names`, chosen over the one the theme would give it.
    colour: str = ""

    @property
    def argv(self) -> list[str]:
        return ["claude", *self.args]

    @property
    def picks_session(self) -> bool:
        """The operator's own args already say which conversation this is, so a save stays out."""
        flags = ("-r", "-c", "--resume", "--continue", "--session-id", "--fork-session")
        return any(a in flags or a.startswith(("--resume=", "--session-id=")) for a in self.args)

    def launch(self, brief: str = "", themed: bool = False, resume: str = "") -> list[str]:
        """What the deck runs: `claude` named after its tab and told it is in a deck.

        The operator's own `-n`/`--name` or appended system prompt wins over the deck's. `themed`
        selects the agent's console theme for this session only, under the operator's own `--settings`.
        `resume` is a session id: Claude Code keeps that session's first brief and ignores this one.
        """
        named = any(a in ("-n", "--name") or a.startswith("--name=") for a in self.args)
        prompted = any(a.startswith("--append-system-prompt") for a in self.args)
        ours = ([] if named else ["-n", self.name]) + (
            [] if prompted or not brief else ["--append-system-prompt", brief]
        )
        # The deck's own plugin, for this session only: its skills ship with this sky.boss, and
        # nothing is installed into the operator's Claude Code configuration.
        ours += ["--plugin-dir", str(PLUGIN_DIR)]
        if resume:
            ours += ["--resume", resume]
        if themed and not any(a == "--settings" or a.startswith("--settings=") for a in self.args):
            ours += ["--settings", json.dumps({"theme": f"custom:{theme_slug(self.name)}"})]
        return ["claude", *ours, *self.args]

    @property
    def directory(self) -> str:
        return os.path.expandvars(os.path.expanduser(self.cwd))


@dataclass
class Profile:
    """A set of tabs to open together: the primary first, then `tabs` in order."""

    name: str
    primary: str = ""
    tabs: list[str] = field(default_factory=list)
    # The operator's own text, appended to the brief of every agent this profile launches.
    brief: str = ""

    def order(self) -> tuple[list[str], list[str]]:
        """Each name once, primary first, and a problem per repeat."""
        names: list[str] = []
        problems: list[str] = []
        for name in [self.primary, *self.tabs] if self.primary else self.tabs:
            if name in names:
                problems.append(f"profile {self.name!r}: {name!r} is listed twice — one tab")
                continue
            names.append(name)
        return names, problems


@dataclass
class Config:
    session: str = DEFAULT_SESSION
    pin: str = ""
    agents: dict[str, Agent] = field(default_factory=dict)
    profiles: dict[str, Profile] = field(default_factory=dict)
    panes: list[str] = field(default_factory=list)
    # Each tab's Claude Code takes a theme accented in its agent's deck hue, on `theme_base`.
    themes: bool = True
    theme_base: str = ""

    def profile(self, name: str | None) -> Profile | None:
        """The named profile, or `pin` as a profile with a primary and no tabs, or none.

        Raises `KeyError` for a name nobody declared.
        """
        if name:
            return self.profiles[name]
        return Profile(name="pin", primary=self.pin) if self.pin else None


def home_file(home: Path | None = None) -> Path:
    return (home or SB_HOME) / DECK_FILE


def read(home: Path | None = None) -> dict:
    """The raw TOML, or an empty mapping when there is no file — nothing declared."""
    path = home_file(home)
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {"__error__": f"{path}: {exc}"}


def parse(raw: dict) -> tuple[Config, list[str]]:
    """Validate the declaration. Pure, and never raises.

    A typo'd table is named rather than silently ignored — `[agnet.x]` must not
    read the same as a fresh home ([[roll-call]]'s parser set the rule).
    """
    config = Config()
    if "__error__" in raw:
        return config, [raw["__error__"]]
    problems: list[str] = []

    for key in raw:
        if key in TOP_LEVEL_KEYS or key in TOP_LEVEL_TABLES:
            continue
        kind = "table" if isinstance(raw[key], dict) else "key"
        problems.append(f"unknown {kind} {key!r} — ignored")

    if "session" in raw:
        session = raw["session"]
        if isinstance(session, str) and SESSION.match(session):
            config.session = session
        else:
            problems.append(f"session must be letters, digits, '-' or '_' — using {DEFAULT_SESSION!r}")

    if "pin" in raw:
        if isinstance(raw["pin"], str):
            config.pin = raw["pin"]
        else:
            problems.append("pin must be an agent name — ignored")

    if "panes" in raw:
        panes = raw["panes"]
        if isinstance(panes, list) and all(isinstance(p, str) for p in panes):
            unknown = [p for p in panes if p not in TOOL_ROLES]
            if unknown:
                problems.append(
                    f"panes: unknown {', '.join(map(repr, unknown))} — the panes are {', '.join(TOOL_ROLES)}"
                )
            config.panes = [p for p in panes if p in TOOL_ROLES]
        else:
            problems.append("panes must be a list of pane names — ignored")

    if "themes" in raw:
        if isinstance(raw["themes"], bool):
            config.themes = raw["themes"]
        else:
            problems.append("themes must be true or false — ignored")
    if "theme_base" in raw:
        base = raw["theme_base"]
        if base in THEME_BASES:
            config.theme_base = base
        else:
            problems.append(f"theme_base must be one of {', '.join(THEME_BASES)} — ignored")

    tables = raw.get("agent", {})
    if not isinstance(tables, dict):
        problems.append("agent must be a table of [agent.NAME] tables — ignored")
        tables = {}
    for name, body in tables.items():
        problem = _check(name, body)
        if problem:
            problems.append(f"agent {name!r}: {problem}")
            continue
        for key in body:
            if key not in AGENT_KEYS:
                problems.append(f"agent {name!r}: unknown key {key!r} — ignored")
        colour = body.get("colour", "")
        if colour and colour not in theme.hue_names():
            problems.append(f"agent {name!r}: colour must be one of {', '.join(theme.hue_names())} — ignored")
            colour = ""
        config.agents[name] = Agent(
            name=name,
            cwd=body["cwd"],
            args=list(body.get("args", [])),
            role=body.get("role", "").strip(),
            colour=colour,
        )

    tables = raw.get("profile", {})
    if not isinstance(tables, dict):
        problems.append("profile must be a table of [profile.NAME] tables — ignored")
        tables = {}
    for name, body in tables.items():
        problem = _check_profile(body)
        if problem:
            problems.append(f"profile {name!r}: {problem}")
            continue
        for key in body:
            if key not in PROFILE_KEYS:
                problems.append(f"profile {name!r}: unknown key {key!r} — ignored")
        config.profiles[name] = Profile(
            name=name, primary=body.get("primary", ""), tabs=list(body.get("tabs", [])), brief=body.get("brief", "")
        )
    return config, problems


def _check_profile(body) -> str | None:
    if not isinstance(body, dict):
        return "not a table"
    primary = body.get("primary", "")
    if not isinstance(primary, str):
        return "primary must be an agent name"
    tabs = body.get("tabs", [])
    if not isinstance(tabs, list) or not all(isinstance(t, str) and t for t in tabs):
        return "tabs must be a list of agent names"
    if not primary and not tabs:
        return "names no primary and no tabs"
    if not isinstance(body.get("brief", ""), str):
        return "brief must be text"
    return None


def _check(name: str, body) -> str | None:
    if not isinstance(body, dict):
        return "not a table"
    if not NAME.match(name):
        return "name must be letters, digits, '.', '-' or '_'"
    cwd = body.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return "cwd must be a non-empty string"
    args = body.get("args", [])
    if isinstance(args, str):
        return "args must be a list of strings, not a shell string"
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return "args must be a list of strings"
    role = body.get("role", "")
    if not isinstance(role, str) or "\n" in role.strip():
        return "role must be one line of text"
    return None


def load(home: Path | None = None) -> tuple[Config, list[str]]:
    config, problems = parse(read(home))
    # Declared here and not in `parse`, which is pure: every reader of an agent's colour comes through this.
    theme.DECLARED_HUES.clear()
    theme.DECLARED_HUES.update({name: agent.colour for name, agent in config.agents.items() if agent.colour})
    return config, problems


def resolve(name: str, config: Config, projects: list) -> tuple[Agent | None, str]:
    """`[agent.NAME]` first, then a `projects.toml` project's `cwd`, or why not."""
    if name in config.agents:
        return config.agents[name], ""
    project = next((p for p in projects if p.name == name), None)
    if project is not None:
        if not NAME.match(name):
            return None, "that project's name cannot be a window name"
        if not project.cwd:
            return None, f"project {name!r} in projects.toml declares no cwd"
        return Agent(name=name, cwd=project.cwd, source="projects.toml"), ""
    known = sorted(set(config.agents) | {p.name for p in projects if p.cwd})
    hint = f" (known: {', '.join(known)})" if known else ""
    return None, f"not declared — add [agent.{name}] to {DECK_FILE} or a cwd in projects.toml{hint}"


def _projects() -> list:
    """Declared projects, for the `cwd` fallback. Their problems are roll-call's to report."""
    from skyboss import rollcall

    projects, _ = rollcall.load()
    return projects


# ============================================================================
# The runner — every tmux call goes through here
# ============================================================================


@dataclass
class Answer:
    """What one tmux call said. `asked` is False when tmux could not be run at all."""

    asked: bool
    code: int = 0
    out: str = ""
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.asked and self.code == 0


def system(argv: list[str], replace: bool = False) -> Answer:
    """Run `argv`, or with `replace` become it. The operator's environment, not ours."""
    env = child_env()
    if replace:
        try:
            os.execvpe(argv[0], argv, env)
        except OSError as exc:
            return Answer(asked=False, err=str(exc))
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=10, env=env, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return Answer(asked=False, err=str(exc))
    return Answer(asked=True, code=done.returncode, out=done.stdout, err=done.stderr)


#: The one injectable runner. The suite replaces this; nothing else calls `system`.
RUNNER: Callable[..., Answer] = system


def tmux(*args: str, replace: bool = False) -> Answer:
    return RUNNER(["tmux", *args], replace=replace)


class DeckError(Exception):
    """tmux could not do what the deck asked; the message is the sentence to show."""


def _said(answer: Answer) -> str:
    return (answer.err or answer.out).strip() or ("tmux could not be run" if not answer.asked else "no reason given")


# ============================================================================
# Reading the deck back
# ============================================================================


PANE_FORMAT = "\t".join(
    [
        "#{window_id}",
        "#{window_index}",
        "#{window_name}",
        "#{" + AGENT_OPTION + "}",
        "#{pane_id}",
        "#{pane_pid}",
        "#{" + ROLE_OPTION + "}",
    ]
)


@dataclass(frozen=True)
class Pane:
    window_id: str
    window_index: int
    window: str
    agent: str
    pane_id: str
    pid: int
    role: str


def parse_panes(text: str) -> list[Pane]:
    """`list-panes -F PANE_FORMAT` output into panes. A malformed line is skipped."""
    out: list[Pane] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 7:
            continue
        wid, index, window, agent, pane_id, pid, role = parts
        try:
            out.append(Pane(wid, int(index), window, agent, pane_id, int(pid), role))
        except ValueError:
            continue
    return out


def has_session(session: str) -> bool | None:
    """True, False, or None when tmux could not be asked."""
    answer = tmux("has-session", "-t", f"={session}")
    if not answer.asked:
        return None
    return answer.code == 0


def panes(session: str) -> tuple[list[Pane], Answer]:
    answer = tmux("list-panes", "-s", "-t", f"={session}", "-F", PANE_FORMAT)
    return (parse_panes(answer.out) if answer.ok else []), answer


def find_window(name: str, listed: list[Pane]) -> str | None:
    """The window opened for `name`, else one merely called `name`."""
    for pane in listed:
        if pane.agent == name:
            return pane.window_id
    for pane in listed:
        if pane.window == name:
            return pane.window_id
    return None


def extended_keys_note() -> str | None:
    """A sentence when the server's `extended-keys` is off. Read, never set."""
    answer = tmux("show-options", "-s", "-v", "extended-keys")
    if answer.ok and answer.out.strip() == "off":
        return (
            "tmux extended-keys is off on this server, so modified keys such as Shift+Enter reach claude "
            "unmodified — set it in your own tmux config; sky.boss reads it and never sets it"
        )
    return None


# ============================================================================
# Acting on the deck
# ============================================================================


def dress(window_id: str, *, tab: bool = False) -> list[str]:
    """The deck's window options, on one of its windows. Problems, never raises.

    Window options rather than session ones because tmux has no per-session
    window option: the borders and tab styles are set window by window.
    """
    problems = []
    options = (("window-size", "latest"), ("allow-passthrough", "on"), *window_options(tab))
    for option, value in options:
        answer = tmux("set-option", "-w", "-t", window_id, option, value)
        if not answer.ok:
            problems.append(f"could not set {option} on the deck window — {_said(answer)}")
    return problems


# ============================================================================
# The bars: theme and tab marks
# ============================================================================


TAB_ROWS = 3


def tab_cell(row: int, current: bool) -> str:
    """One row of one tab's box: 0 the top edge, 1 the name, 2 the bottom edge.

    A box is the name's width plus a space each side, so its edges are the name
    with every character replaced. The ground says what the agent is doing:
    `busy` is lit, `waiting` is the warn block, anything else is plain. The
    current tab's edge is drawn in its agent's hue. Every row carries the
    window's range, so a click anywhere on a box selects that tab.
    """
    style = theme.tmux_styles()
    state = "#{" + STATE_OPTION + "}"
    colour = "#{" + COLOUR_OPTION + "}"
    bar = style["bar"]
    edge = f"#{{?{colour},#[fg={colour} bold],#[{style['label']}]}}" if current else f"#[{style['tab-edge']}]"
    plain = f"#{{?{colour},#[fg={colour}],#[{style['tab']}]}}"
    if row == 1:
        idle = f"#{{?#{{==:{state},{UNREGISTERED}}},#[{style['unregistered']}],{plain}}}"
        ground = (
            f"#{{?#{{==:{state},busy}},#[{style['tab-working']}],"
            f"#{{?#{{==:{state},{WAITING}}},#[{style['needs-you']}],{idle}}}}}"
        )
        body = f"{edge}│{ground} #W #[{bar}]{edge}│"
    else:
        left, right = ("╭", "╮") if row == 0 else ("╰", "╯")
        body = f"{edge}{left}─#{{s/./─/:window_name}}─{right}"
    return f"#[range=window|#{{window_index}}]{body}#[norange nobold {bar}] "


WORDMARK = ("skyrow", ".labs")
#: What the footer calls a deck opened from no declared profile.
DECK_LABEL = "sky.boss deck"
#: Blank cells each side of the mark.
MARK_PAD = 2
#: Drawn on all three rows between the mark and the first tab, and in the footer after the wordmark.
SEPARATOR = "│"


def tab_lefts() -> tuple[tuple[str, ...], int]:
    """The tab bar's left end, one format per row, and its visible width.

    The SL mark padded each side, then a separator on every row before the tabs.
    """
    style = theme.tmux_styles()
    bar = style["bar"]
    pad = " " * MARK_PAD
    separator = f"#[{style['tab-edge']}]{SEPARATOR}#[{bar}] "
    lefts = tuple(f"#[{bar}]{pad}{mark}#[{bar}]{pad}{separator}" for mark in theme.tmux_mark())
    width = MARK_PAD + theme.MARK_WIDTH + MARK_PAD + len(SEPARATOR) + 1
    return lefts, width


def wordmark() -> str:
    """`skyrow` white and `.labs` brand, both bold, as a tmux format."""
    style = theme.tmux_styles()
    # `nobold`: a colour change does not end tmux's bold, which would run on into what follows.
    return f"#[{style['wordmark']}]{WORDMARK[0]}#[{style['label']}]{WORDMARK[1]}#[nobold {style['bar']}]"


def marks_text() -> str:
    """The footer's word for when the marks loop last wrote, as a tmux format."""
    marked = "#{" + MARKED_OPTION + "}"
    return f"marks #{{?{marked},{marked},not running}} "


def tab_row(row: int, left: str) -> str:
    """`status-format[row]` for the tab bar: `left`, then the tabs' boxes as a tmux list.

    A list that will not fit is scrolled by tmux to keep the current tab in view. Each row scrolls
    alone, so every `left` is one width to give all three the same room, and so the same scroll.
    """
    current = f"#[list=focus]{tab_cell(row, True)}#[list=on]"
    cells = f"#[list=on]#{{W:{tab_cell(row, False)},{current}}}#[nolist]"
    return f"#[align=left]{left}{cells}"


#: The row under the tabs, drawn only while they overflow; `@sb-scrollbar` holds it.
SCROLLBAR_OPTION = "@sb-scrollbar"


def tab_width(name: str) -> int:
    """A tab's visible width: its box (`│ name │`) and the space after it."""
    return len(name) + 5


def visible_span(widths: list[int], current: int, room: int) -> tuple[int, int, int] | None:
    """What of the tab list tmux shows in `room` cells: (start, end, total), or None when all fit.

    tmux's own rule (`format_draw_put_list`): centre the focused tab, clamped at either end.
    """
    total = sum(widths)
    if total <= room or room <= 0:
        return None
    focus_start = sum(widths[:current])
    centre = focus_start + widths[current] // 2 if widths else 0
    start = 0 if centre < room // 2 else centre - room // 2
    start = min(start, total - room)
    return start, start + room, total


def scrollbar(span: tuple[int, int, int], room: int, offset: int) -> str:
    """A one-line scrollbar `room` cells long, after `offset` blank cells: the visible span lit."""
    style = theme.tmux_styles()
    start, end, total = span
    lo = start * room // total
    hi = max(lo + 1, -(-end * room // total))
    return (
        f"#[{style['bar']}]{' ' * offset}#[{style['scroll-track']}]{'─' * lo}"
        f"#[{style['scroll-thumb']}]{'━' * (hi - lo)}#[{style['scroll-track']}]{'─' * (room - hi)}"
    )


def border_follows_tab(session: str) -> list[str]:
    """The controller's active border in the current tab's colour, the brand before a tab has one."""
    answer = tmux("display-message", "-p", "-t", f"={inner(session)}:", "#{" + COLOUR_OPTION + "}")
    colour = answer.out.strip() if answer.ok else ""
    style = f"fg={colour}" if colour.startswith("#") else theme.tmux_styles()["border-active"]
    set_ = tmux("set-option", "-w", "-t", f"={session}:", "pane-active-border-style", style)
    return [] if set_.ok else [f"could not colour the deck's border — {_said(set_)}"]


def scroll_once(session: str) -> list[str]:
    """Show the scrollbar row under the tabs if they overflow their client, and hide it if not."""
    name = inner(session)
    colouring = border_follows_tab(session)
    clients = tmux("list-clients", "-t", f"={name}", "-F", "#{client_width}")
    windows = tmux("list-windows", "-t", f"={name}", "-F", "#{window_active}\t#{window_name}")
    if not (clients.ok and windows.ok):
        return [f"could not measure the deck's tab row — {_said(clients if not clients.ok else windows)}"]
    widths = [int(w) for w in clients.out.split() if w.isdigit()]
    if not widths:
        return colouring
    rows = [line.split("\t", 1) for line in windows.out.splitlines() if "\t" in line]
    current = next((n for n, (active, _) in enumerate(rows) if active == "1"), 0)
    _, left = tab_lefts()
    room = min(widths) - left
    span = visible_span([tab_width(label) for _, label in rows], current, room)
    if span is None:
        return colouring + _session_options(name, (("status", str(TAB_ROWS)), (SCROLLBAR_OPTION, "")))
    bar = ((SCROLLBAR_OPTION, scrollbar(span, room, left)), ("status", str(TAB_ROWS + 1)))
    return colouring + _session_options(name, bar)


def window_options(tab: bool) -> tuple[tuple[str, str], ...]:
    style = theme.tmux_styles()
    common = (
        ("pane-border-style", style["border"]),
        ("pane-active-border-style", style["border-active"]),
        ("window-status-style", style["tab"]),
        ("window-status-current-style", style["tab-current"]),
    )
    return common


def shared_countdown(every: int = TOOLS_REFRESH) -> str:
    """Seconds to the tool panes' next refresh, as a tmux format: they refresh on the clock's
    multiples of `every`, so this is `every - now % every`. `%s` is strftime's epoch, which
    tmux expands before the arithmetic, and `%%` survives that as the modulus."""
    return f"#{{e|-:{every},#{{e|%%:%s,{every}}}}}"


#: The footer's one row: tmux's default with the window list left out, as the deck has one window.
FOOTER_FORMAT = (
    "#[align=left]#{T;=/#{status-left-length}:status-left}#[norange default]"
    "#[align=right]#{T;=/#{status-right-length}:status-right}"
)


def bar_options(tabs: bool, profile: str = "") -> tuple[tuple[str, str], ...]:
    """Session options for a deck bar. The footer names the deck after `profile` and says when
    the marks were last written."""
    style = theme.tmux_styles()
    label = profile or DECK_LABEL
    lefts: tuple[str, ...] = ()
    if tabs:
        lefts, width = tab_lefts()
        left = lefts[1]
    else:
        tick = shared_countdown()
        word = "".join(WORDMARK)
        width = len(f" {word} {SEPARATOR} {label} ⟳ next in {TOOLS_REFRESH}s marks not running ") + 1
        left = (
            f"#[{style['bar']}] {wordmark()} #[{style['tab-edge']}]{SEPARATOR}"
            f"#[{style['label']}] {label} #[nobold {style['working']}]⟳ next in {tick}s "
            f"#[{style['quiet']}]{marks_text()}#[{style['bar']}]"
        )
    options: tuple[tuple[str, str], ...] = (
        ("status-style", style["bar"]),
        ("status-left", left),
        # tmux's default of 10 cut the label to "sky.boo…"; this is the label's visible width.
        ("status-left-length", str(width)),
    )
    if not tabs:
        # The countdown is tmux's own arithmetic on the clock, so it has to redraw every second.
        options += (("status-interval", "1"),)
    if tabs:
        options += (("status", str(TAB_ROWS)),)
        options += tuple((f"status-format[{row}]", tab_row(row, lefts[row])) for row in range(TAB_ROWS))
        options += ((f"status-format[{TAB_ROWS}]", "#{" + SCROLLBAR_OPTION + "}"),)
    else:
        options += (("status-right", hints()), ("status-right-length", "140"), ("status-format[0]", FOOTER_FORMAT))
    return options


# ============================================================================
# Keys: a table only the deck uses
# ============================================================================

# Shortcuts in the deck's table, and the status-bar hint for each. None collides
# with Claude Code 2.1.318's own keys or with tmux's root defaults; see [[command-deck]]
# round 4 for the check. Ctrl-C is never bound: it is claude's own.
EXIT_KEY = "C-q"
SHORTCUTS = {
    "outside": "M-h",
    "layout": "M-l",
    "previous": "M-,",
    "next": "M-.",
    "older": "M-u",
    "newest": "M-e",
    "column": "M-s",
    "fold": "M-c",
    "clear": "M-x",
}
NEVER_BOUND = frozenset({"C-c"})
# Session options the panes read each frame, and the marks loop keeps the agent count in.
HIDE_OPTION = "@sb-hide-outside"
SCROLL_OPTION = "@sb-scroll"
SCROLL_SEQ_OPTION = "@sb-scroll-seq"
AGENT_COUNT_OPTION = "@sb-agent-count"
EXIT_RANGE = "exit"
LAYOUT_RANGE = "layout"


def key_table(session: str) -> str:
    """One table per deck, so two decks on one server cannot drive each other."""
    return f"sb-deck-{session}"


def mirrored_root(listing: str, table: str) -> str:
    """`list-keys -T root`, rebound into `table`. tmux never falls back to root from a session's
    `key-table`, so without these a deck would lose the mouse: tab clicks, border drags, the wheel.
    A Ctrl-C binding is dropped rather than copied."""
    out = []
    for line in listing.splitlines():
        match = re.match(r"^(bind-key\s+(?:-r\s+)?-T\s+)root(\s+)(\S+)(\s.*)$", line)
        if match is None or match.group(3) in NEVER_BOUND:
            continue
        out.append(f"{match.group(1)}{table}{match.group(2)}{match.group(3)}{match.group(4)}")
    return "\n".join(out) + ("\n" if out else "")


def quiet(*words: str) -> str:
    """`sb WORDS` for a `run-shell`, exiting 0 always: tmux prints a non-zero exit over the current pane."""
    return f"{shlex.quote(str(PROJECT_ROOT / 'sb'))} {' '.join(words)} >/dev/null 2>&1 || true"


def job(*words: str) -> str:
    return f'run-shell -b "{quiet(*words)}"'


def next_layout() -> str:
    """The layout after this one, as a tmux format: columns, stack, grid, and round."""
    now = "#{" + LAYOUT_OPTION + "}"
    return f"#{{?#{{==:{now},{STACK}}},{GRID},#{{?#{{==:{now},{GRID}}},{COLUMNS},{STACK}}}}}"


def deck_bindings(session: str) -> list[list[str]]:
    """The deck's own bindings, as `bind-key` argv. Pure, so the suite reads exactly what is bound."""
    table = key_table(session)
    outer, tabs = scope(session), scope(inner(session))
    sb = shlex.quote(str(PROJECT_ROOT / "sb"))
    cycle = job("deck", "layout", next_layout())
    clicked = "#{==:#{mouse_status_range}," + LAYOUT_RANGE + "}"

    count = "#{" + AGENT_COUNT_OPTION + "}"
    ask = (
        f'confirm-before -p "end the deck {session} and its {count} agent sessions? (y/n)" ' f"'{job('deck', 'exit')}'"
    )
    seq = "#{e|+:#{" + SCROLL_SEQ_OPTION + "},1}"
    hide = "#{" + HIDE_OPTION + "}"

    def scroll(word: str) -> list[str]:
        # `\;` rather than `;`: a bare one would end the bind-key and run the rest at once.
        then = ["\\;", "set-option", "-F", "-t", outer, SCROLL_SEQ_OPTION, seq]
        return ["set-option", "-t", outer, SCROLL_OPTION, word, *then]

    keys = SHORTCUTS
    return [
        ["bind-key", "-T", table, EXIT_KEY, *ask_argv(session, ask)],
        [
            "bind-key",
            "-T",
            table,
            "MouseDown1Status",
            "if-shell",
            "-F",
            "#{==:#{mouse_status_range}," + EXIT_RANGE + "}",
            ask,
            f"if-shell -F '{clicked}' '{cycle}' 'switch-client -t ='",
        ],
        ["bind-key", "-T", table, keys["outside"], "set-option", "-F", "-t", outer, HIDE_OPTION, f"#{{?{hide},,1}}"],
        ["bind-key", "-T", table, keys["layout"], *shlex.split(cycle)],
        ["bind-key", "-T", table, keys["previous"], "previous-window", "-t", tabs],
        ["bind-key", "-T", table, keys["next"], "next-window", "-t", tabs],
        ["bind-key", "-T", table, keys["older"], *scroll("older")],
        ["bind-key", "-T", table, keys["newest"], *scroll("newest")],
        [
            "bind-key",
            "-T",
            table,
            keys["column"],
            "display-popup",
            "-E",
            "-w",
            "72",
            "-h",
            str(len(column_.TOOLS) + 4),
            f"exec {sb} deck column pick",
        ],
        # The focused pane's own role names what folds; anything else says so rather than doing nothing.
        [
            "bind-key",
            "-T",
            table,
            keys["fold"],
            "run-shell",
            "-b",
            f"{sb} deck column fold '#{{{ROLE_OPTION}}}' >/dev/null 2>&1 "
            f"|| tmux display-message '{keys['fold']} folds a right-column pane: focus one first' || true",
        ],
        # Both books, counted from the envelopes (one `"cleared"` line per list), so a press with nothing done says 0.
        [
            "bind-key",
            "-T",
            table,
            keys["clear"],
            "run-shell",
            "-b",
            f"t=$({sb} --json deck todo clear 2>/dev/null | grep -c '\"cleared\"'); "
            f"d=$({sb} --json deck decide clear 2>/dev/null | grep -c '\"cleared\"'); "
            'tmux display-message "cleared done todos from $t list(s) and decided items from $d" || true',
        ],
    ]


def ask_argv(session: str, ask: str) -> list[str]:
    """The exit prompt as argv for `bind-key`, which takes a command rather than a string."""
    return shlex.split(ask)


def install_keys(session: str) -> list[str]:
    """Mirror root into the deck's table, bind the deck's keys over it, and point both sessions at it."""
    table = key_table(session)
    problems: list[str] = []
    listing = tmux("list-keys", "-T", "root")
    if listing.ok:
        problems += _source(mirrored_root(listing.out, table))
    else:
        problems.append(f"could not read tmux's root keys, so the deck has no mouse bindings — {_said(listing)}")
    for argv in deck_bindings(session):
        answer = tmux(*argv)
        if not answer.ok:
            problems.append(f"could not bind {argv[3]} — {_said(answer)}")
    for name in (session, inner(session)):
        problems += _session_options(name, (("key-table", table),))
    return problems


def _source(text: str) -> list[str]:
    """`source-file` a generated config: bindings as tmux prints them are not argv."""
    if not text:
        return []
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".tmux", prefix="sb-deck-", delete=False) as handle:
        handle.write(text)
        path = handle.name
    try:
        answer = tmux("source-file", path)
    finally:
        Path(path).unlink(missing_ok=True)
    return [] if answer.ok else [f"could not copy tmux's root keys into the deck — {_said(answer)}"]


def hints() -> str:
    """The outer bar's right end: each shortcut, the ▦ that changes layout, the ✕ that ends the deck."""
    style = theme.tmux_styles()
    k = SHORTCUTS
    parts = [
        f"{k['outside']} outside",
        f"{k['layout']} layout",
        f"{k['previous']} {k['next']} tab",
        f"{k['older']} {k['newest']} messages",
        f"{k['column']} panes",
        f"{k['fold']} fold",
        f"{k['clear']} clear done",
        f"{EXIT_KEY} exit",
    ]
    return (
        f"#[{style['quiet']}]{'  '.join(parts)} "
        f"#[range=user|{LAYOUT_RANGE}]#[{style['label']}] ▦ #[nobold norange]"
        f"#[range=user|{EXIT_RANGE}]#[{style['exit']}] ✕ #[norange]#[{style['bar']}]"
    )


def windows_states(listed: list[Pane], sessions: list, parent_of: dict[int, int]) -> dict[str, str]:
    """Window id → the registry word of the session running there, `unregistered` for a quiet agent pane."""
    states: dict[str, str] = {}
    for window_id, label, status, session, pid in deck_windows(listed, sessions, parent_of)[0]:
        held = states.get(window_id)
        if held is None or (status == WAITING) or (status == "busy" and held != WAITING):
            states[window_id] = status
    return states


def transcript_exists(ident: str) -> bool:
    """Whether Claude Code still holds this session: `--resume` on a lost id ends the tab at once."""
    return any((claude_dir() / "projects").glob(f"*/{ident}.jsonl"))


def resume_lookup(session: str, problems: list[str], fresh: bool = False) -> Callable[[Agent], str]:
    """Which saved session an agent resumes, empty for a new one. A save it cannot use goes in `problems`."""
    saved, more = (decksave.Saved(), []) if fresh else decksave.load(session)
    problems += more
    tabs = {tab.agent: tab for tab in saved.tabs}
    if not tabs:
        return lambda agent: ""
    live = {s.id for s in agents_.fold(agents_.providers())[0]}

    def resumed(agent: Agent) -> str:
        tab = tabs.get(agent.name)
        if tab is None or agent.picks_session:
            return ""
        if tab.id in live:
            problems.append(f"{agent.name}: its saved session is open elsewhere — this tab started new")
            return ""
        if not transcript_exists(tab.id):
            problems.append(f"{agent.name}: its saved session {tab.id} is gone — this tab started new")
            return ""
        return tab.id

    return resumed


def restored(config: Config, problems: list[str]) -> Profile | None:
    """The saved tabs as a profile, so `sb deck` reopens what was open. None with nothing saved."""
    saved, more = decksave.load(config.session)
    problems += more
    if not saved.tabs:
        return None
    declared = config.profiles.get(saved.profile)
    return Profile(
        name=saved.profile or "saved",
        primary=saved.primary,
        tabs=[tab.agent for tab in saved.tabs],
        brief=declared.brief if declared else "",
    )


def live_tabs(listed: list[Pane], sessions: list, parent_of: dict[int, int]) -> tuple[list[decksave.Tab], list[str]]:
    """Each agent tab's session in tab order, and the agents with no session to save."""
    agents = {p.window_id: p.agent or p.window for p in listed if p.role == AGENT}
    held: dict[str, decksave.Tab] = {}
    for window_id, _, _, session, _ in deck_windows(listed, sessions, parent_of)[0]:
        if window_id in agents and session is not None and window_id not in held:
            held[window_id] = decksave.Tab(agents[window_id], session.id, session.cwd)
    return list(held.values()), [name for window_id, name in agents.items() if window_id not in held]


def ruling_line(n: int, item: todos_.Item) -> str:
    """What an agent reads in its tab when the operator rules from the DECISIONS pane."""
    return f'The operator ruled on your decision {n}, "{item.text}": {item.ruling}'


def tell_rulings(session: str, listed: list[Pane], states: dict[str, str], labels: dict[str, str]) -> list[str]:
    """Type one untold ruling into each idle agent's tab. Never into a busy tab or a scrolled pane."""
    problems: list[str] = []
    for pane in listed:
        agent = labels.get(pane.window_id, "")
        if pane.role != AGENT or states.get(pane.window_id) != "idle":
            continue
        try:
            found = todos_.next_untold(session, agent)
        except ValueError as exc:
            problems.append(f"{agent}: {exc}")
            continue
        scrolled = tmux("display-message", "-p", "-t", pane.pane_id, "#{pane_in_mode}")
        if found is None or not scrolled.ok or scrolled.out.strip() == "1":
            continue
        n, item = found
        typed = tmux("send-keys", "-t", pane.pane_id, "-l", ruling_line(n, item))
        sent = tmux("send-keys", "-t", pane.pane_id, "Enter") if typed.ok else typed
        if sent.ok:
            todos_.told(session, agent, n)
        else:
            problems.append(f"could not tell {agent!r} a ruling — {_said(sent)}")
    return problems


def write_save(session: str, tabs: list[decksave.Tab]) -> list[str]:
    """Save `tabs` with the deck's primary and profile. A problem if it could not be written."""
    saved = decksave.Saved(tabs, deck_primary(session), deck_profile(session))
    try:
        decksave.save(session, saved)
    except OSError as exc:
        return [f"could not save the deck's tabs — {exc}"]
    return []


def autosave(session: str, tabs: list[decksave.Tab]) -> list[str]:
    """Fold the live tabs into the save when they changed it, so a reboot finds them."""
    saved, problems = decksave.load(session)
    kept = decksave.merged(saved.tabs, tabs)
    if problems or kept == saved.tabs:
        return []
    return write_save(session, kept)


def save_now(session: str, adapters: list | None = None) -> tuple[list[decksave.Tab], list[str]]:
    """Save exactly the open tabs, keeping the last session of one that has none now. Tabs, and problems."""
    listed, answer = panes(inner(session))
    if not answer.ok:
        return [], [f"could not list the deck's tabs — {_said(answer)}"]
    sessions, problems, _ = agents_.fold(adapters if adapters is not None else agents_.providers())
    tabs, missing = live_tabs(listed, sessions, parents())
    saved, more = decksave.load(session)
    problems = [*problems, *more]
    tabs += [tab for tab in saved.tabs if tab.agent in missing]
    unsaved = sorted(set(missing) - {tab.agent for tab in tabs})
    if unsaved:
        problems.append(f"no session to save for {', '.join(unsaved)}")
    return tabs, problems + write_save(session, tabs)


def marks_once(
    session: str, written: dict[str, str], adapters: list | None = None, colours: dict[str, str] | None = None
) -> Result:
    """Write each tab's state where it changed, and the time it was written. Acts on tmux only."""
    result = Result()
    name = inner(session)
    present = has_session(name)
    if not present:
        result.ok = False
        result.data = {"error": f"no deck tabs {name!r} — `sb deck` starts them"}
        return result
    listed, answer = panes(name)
    if not answer.ok:
        result.degrade(f"could not list the deck's tabs — {_said(answer)}")
    sessions, problems, _ = agents_.fold(adapters if adapters is not None else agents_.providers())
    for problem in problems:
        result.warn(problem)
    parent_of = parents()
    states = windows_states(listed, sessions, parent_of)
    labels = {p.window_id: p.agent or p.window for p in listed}
    rows = []
    for window_id, word in states.items():
        changed = written.get(window_id) != word
        if changed:
            set_ = tmux("set-option", "-w", "-t", window_id, STATE_OPTION, word)
            if set_.ok:
                written[window_id] = word
            else:
                result.degrade(f"could not mark {labels.get(window_id, window_id)!r} — {_said(set_)}")
        rows.append({"window": labels.get(window_id, window_id), "state": word, "written": changed})
    for problem in write_colours(session, listed, colours if colours is not None else {}):
        result.degrade(problem)
    for problem in scroll_once(session):
        result.degrade(problem)
    for problem in tell_rulings(session, listed, states, labels):
        result.degrade(problem)
    if answer.ok:
        for problem in autosave(session, live_tabs(listed, sessions, parent_of)[0]):
            result.degrade(problem)
    count = str(len({p.window_id for p in listed if p.role == AGENT}))
    for problem in _session_options(session, ((MARKED_OPTION, clock(time.time())), (AGENT_COUNT_OPTION, count))):
        result.degrade(problem)
    result.data = rows
    return result


def marks_argv() -> list[str]:
    return sb_argv("deck", "marks", "--every", str(MARKS_EVERY))


def start_marks(session: str) -> list[str]:
    """Start the one marks loop for this deck unless it is running. A tmux background job, so it ends with the server."""
    if _marks_owner(session) is not None:
        return []
    command = shlex.join(marks_argv()) + " >/dev/null 2>&1 || true"
    answer = tmux("run-shell", "-b", command)
    return [] if answer.ok else [f"could not start the tab marks — {_said(answer)}"]


def _marks_owner(session: str, proc: Path = Path("/proc")) -> int | None:
    """The pid of a live marks loop recorded on the tabs session, or none."""
    answer = tmux("show-options", "-v", "-t", scope(inner(session)), MARKS_PID_OPTION)
    pid = answer.out.strip() if answer.ok else ""
    if not pid.isdigit():
        return None
    try:
        command = (proc / pid / "cmdline").read_bytes().split(b"\0")
    except OSError:
        return None
    return int(pid) if b"deck" in command and b"marks" in command else None


#: Injectable for the suite, which must never sleep.
SLEEP: Callable[[float], None] = time.sleep


def _ids(answer: Answer) -> tuple[str, str]:
    parts = answer.out.split()
    if not answer.ok or len(parts) != 2:
        raise DeckError(f"tmux did not open the window — {_said(answer)}")
    return parts[0], parts[1]


def inner(session: str) -> str:
    """The session holding the project agents, one window each."""
    return f"{session}{INNER_SUFFIX}"


def start(
    session: str, agent: Agent, *, new_session: bool = False, brief: str = "", resume: str = ""
) -> tuple[str, list[str]]:
    """A window running `claude` in the agent's directory, briefed. Its window id, and problems."""
    directory = agent.directory
    if not Path(directory).is_dir():
        raise DeckError(f"{agent.name}: cwd {directory} is not a directory ({agent.source})")
    if shutil.which("claude", path=child_env().get("PATH")) is None:
        raise DeckError("claude is not on PATH")
    where = ["new-session", "-d", "-s", session] if new_session else ["new-window", "-d", "-t", f"={session}:"]
    config, _ = load()
    if config.themes:
        # Written before the launch, so the console finds its theme at start; the slot is the next tab's.
        listed, _ = panes(session) if not new_session else ([], None)
        slot = len(agent_slots(listed))
        write_theme(agent.name, theme.agent_colour(agent.name, slot), theme_base(config))
    argv = agent.launch(brief, themed=config.themes, resume=resume)
    answer = tmux(*where, "-P", "-F", "#{window_id} #{pane_id}", "-n", agent.name, "-c", directory, "--", *argv)
    window_id, pane_id = _ids(answer)
    tmux("set-option", "-w", "-t", window_id, AGENT_OPTION, agent.name)
    tmux("set-option", "-p", "-t", pane_id, ROLE_OPTION, AGENT)
    return window_id, dress(window_id, tab=True)


# ============================================================================
# Console themes: each tab's Claude Code accented in its agent's hue
# ============================================================================
#
# On unless `themes = false` in deck.toml (Jeston's ruling, 2026-11-05). The one place
# sky.boss writes into Claude Code's configuration: `sb-<agent>.json` files in its
# themes directory, and only those. A tab selects its theme for its own session with
# `--settings`, so Claude Code outside the deck keeps the operator's theme.

#: Claude Code's built-in presets, the only values a custom theme's `base` may take.
THEME_BASES = ("dark", "light", "dark-daltonized", "light-daltonized", "dark-ansi", "light-ansi")
#: The theme tokens that carry the accent: the spinner and assistant label, and the input box border.
THEME_TOKENS = ("claude", "promptBorder")
#: The ground under a sent message. Dark bases only: this ground under a light base's dark text is unreadable.
MESSAGE_GROUND_TOKEN = "userMessageBackground"


def claude_dir() -> Path:
    """Claude Code's configuration directory: `CLAUDE_CONFIG_DIR`, else `~/.claude`. Read at call time."""
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".claude"


def theme_slug(agent: str) -> str:
    return f"sb-{agent}"


def theme_base(config: Config) -> str:
    """The declared `theme_base`, else the operator's own theme if it is a preset, else `dark`."""
    if config.theme_base:
        return config.theme_base
    try:
        chosen = json.loads((claude_dir() / "settings.json").read_text()).get("theme")
    except (OSError, ValueError, AttributeError):
        chosen = None
    return chosen if chosen in THEME_BASES else "dark"


def theme_body(agent: str, colour: str, base: str) -> dict:
    overrides = {token: colour for token in THEME_TOKENS}
    if not base.startswith("light"):
        overrides[MESSAGE_GROUND_TOKEN] = theme.HEAD_GROUND
    return {"name": f"sky.boss · {agent}", "base": base, "overrides": overrides}


def write_theme(agent: str, colour: str, base: str) -> list[str]:
    """Write `sb-<agent>.json` if its content would change, through a rename. Problems, never raises."""
    import tempfile

    folder = claude_dir() / "themes"
    path = folder / f"{theme_slug(agent)}.json"
    text = json.dumps(theme_body(agent, colour, base), indent=2) + "\n"
    try:
        if path.is_file() and path.read_text() == text:
            return []
        folder.mkdir(parents=True, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=folder, prefix=f".{path.stem}.", suffix=".json")
        with os.fdopen(handle, "w") as out:
            out.write(text)
        os.replace(temp, path)
    except OSError as exc:
        return [f"could not write {agent}'s console theme — {exc}"]
    return []


# ============================================================================
# The brief: what an agent the deck starts is told about the deck
# ============================================================================

# Session option on the tabs session: the agent the operator coordinates from.
PRIMARY_OPTION = "@sb-primary"
# The profile the deck was last opened with, so a later tab gets its brief.
PROFILE_OPTION = "@sb-profile"


def roster(config: Config, projects: list, planned: list[Agent], primary: str) -> list[tuple[str, str, str]]:
    """(name, directory, role) for each agent in the deck at a launch, primary first, then tab order.

    Read from tmux and the declarations only; never from a transcript.
    """
    names = [primary] if primary else []
    if has_session(inner(config.session)):
        listed, _ = panes(inner(config.session))
        tabs = {p.window_id: p.agent for p in listed if p.role == AGENT and p.agent}
        names += [tabs[w] for w in _window_order([p for p in listed if p.window_id in tabs])]
    names += [agent.name for agent in planned]
    rows: list[tuple[str, str, str]] = []
    for name in dict.fromkeys(names):
        agent = next((a for a in planned if a.name == name), None) or resolve(name, config, projects)[0]
        rows.append((name, agent.directory if agent else "", agent.role if agent else ""))
    return rows


#: Fixed lines of the brief sky.boss writes. The roster (one line per agent) and a
#: profile's own `brief` are not counted: both grow with what the operator declared.
BRIEF_LIMIT = 12


def brief(name: str, session: str, rows: list[tuple[str, str, str]], primary: str, extra: str = "") -> str:
    """The system prompt appended at launch. Plain, short, and true at the moment it is built.

    What an agent does comes from its `role` in the roster, primary included; a
    profile's `brief` is the operator's own words and follows unedited.
    """

    def entry(who: str, where: str, role: str) -> str:
        parts = [f"{who}{' (primary)' if who == primary else ''}", where, role]
        return "- " + " — ".join(part for part in parts if part)

    lines = [
        f'You are "{name}", started by the operator as an agent in a sky.boss deck (tmux session "{session}").',
        "The deck's other agents are peer Claude Code sessions; message one by its name with SendMessage.",
        "List them with `sb agents --scope deck` (the deck's own view: name, status, repo), or with",
        "ListAgents (every session on this machine, the deck's and others).",
        "Agents in the deck at your launch, primary first:",
        *[entry(*row) for row in rows],
        "Tabs open and close, so check the live list before assuming a peer is there;",
        "`sb deck brief` reprints this with the deck as it stands now.",
        "The operator sees every message between agents in the deck's MESSAGES pane, and answers",
        "an agent's prompts by clicking its tab.",
        'Keep todos with `sb deck todo add "<text>"` / `done <n>` (TODOS pane). Each decision you need from the',
        'operator: `sb deck decide add "<question>" --option "<choice>"` (DECISIONS pane); its ruling is typed into your tab.',
    ]
    text = "\n".join(lines)
    return f"{text}\n\n{extra.strip()}" if extra.strip() else text


def deck_profile(session: str) -> str:
    """The name of the declared profile this deck was opened from, empty if none."""
    answer = tmux("show-options", "-v", "-t", scope(inner(session)), PROFILE_OPTION)
    return answer.out.strip() if answer.ok else ""


def deck_profile_brief(config: Config) -> str:
    profile = config.profiles.get(deck_profile(config.session))
    return profile.brief if profile else ""


def deck_primary(session: str) -> str:
    answer = tmux("show-options", "-v", "-t", scope(inner(session)), PRIMARY_OPTION)
    return answer.out.strip() if answer.ok else ""


def sb_argv(*words: str) -> list[str]:
    """This sky.boss, by absolute path: a pane must not find another `sb` on PATH."""
    return [str(PROJECT_ROOT / "sb"), *words]


def queue_argv() -> list[str]:
    return sb_argv("deck", "queue", "--refresh", str(TOOLS_REFRESH), "--screen")


def todos_argv() -> list[str]:
    return sb_argv("deck", "todo", "list", "--all", "--refresh", str(TOOLS_REFRESH), "--screen")


def decisions_argv() -> list[str]:
    return sb_argv("deck", "decide", "list", "--all", "--refresh", str(TOOLS_REFRESH), "--screen")


def messages_argv() -> list[str]:
    return sb_argv("deck", "messages", "--refresh", str(TOOLS_REFRESH), "--screen")


def tabs_argv(session: str, socket: str) -> list[str]:
    """A tmux client on the inner session, nested in a pane of the outer one.

    `TMUX` is unset for the child because tmux refuses to nest otherwise, and the
    socket is named because, with `TMUX` unset, a client finds only the default one.
    """
    server = ["-S", socket] if socket else []
    return ["env", "-u", "TMUX", "tmux", *server, "attach-session", "-t", f"={inner(session)}"]


def socket_path(session: str) -> str:
    answer = tmux("display-message", "-p", "-t", f"={session}", "#{socket_path}")
    return answer.out.strip() if answer.ok else ""


def scope(session: str) -> str:
    """A session as an option target. `set-option -t` reads a pane target, which refuses a bare `=name`."""
    return f"={session}:"


def _session_options(session: str, options: tuple[tuple[str, str], ...]) -> list[str]:
    """Session options, set on the deck's own session only — never `-g`."""
    problems = []
    for option, value in options:
        answer = tmux("set-option", "-t", scope(session), option, value)
        if not answer.ok:
            problems.append(f"could not set {option} on {session!r} — {_said(answer)}")
    return problems


def ensure_inner(
    session: str, first: Agent | None = None, first_brief: str = "", first_resume: str = ""
) -> tuple[bool, list[str]]:
    """Create the inner session if it is absent, with a tab row on top and the mouse on.

    Its first window is `first`'s `claude` when there is one, so a profile's
    primary is the first tab; otherwise a shell, because a session cannot be empty.
    """
    name = inner(session)
    present = has_session(name)
    if present is None:
        raise DeckError("tmux could not be run — is it installed?")
    if present:
        return False, []
    problems: list[str] = []
    if first is not None:
        try:
            _, problems = start(name, first, new_session=True, brief=first_brief, resume=first_resume)
            return True, problems + _inner_options(name)
        except DeckError as exc:
            problems.append(str(exc))
    answer = tmux(
        "new-session", "-d", "-s", name, "-P", "-F", "#{window_id} #{pane_id}", "-n", SHELL, "-c", str(Path.home())
    )
    window_id, pane_id = _ids(answer)
    tmux("set-option", "-p", "-t", pane_id, ROLE_OPTION, SHELL)
    return True, problems + dress(window_id, tab=True) + _inner_options(name)


def _inner_options(name: str) -> list[str]:
    return _session_options(name, (("mouse", "on"), ("status-position", "top"), *bar_options(True)))


def ensure(
    config: Config, projects: list, profile: Profile | None = None, fresh: bool = False
) -> tuple[bool, list[str]]:
    """Create the deck if it is absent, put back a controller pane that has gone, and open the profile's tabs.

    Window 0 is the controller: the tab pane (a client on the inner session)
    beside the queue and the messages. Whether the outer session was created, and problems.
    """
    present = has_session(config.session)
    if present is None:
        raise DeckError("tmux could not be run — is it installed?")
    names, problems = profile.order() if profile else ([], [])
    agents: list[Agent] = []
    for name in names:
        agent, why = resolve(name, config, projects)
        if agent is None:
            label = "pin" if profile and profile.name == "pin" else f"profile {profile.name!r}" if profile else ""
            problems.append(f"{label} {name!r}: {why} — no tab".strip())
            continue
        agents.append(agent)

    primary = profile.primary if profile and profile.primary else deck_primary(config.session)
    rows = roster(config, projects, agents, primary)

    def told(agent: Agent) -> str:
        return brief(agent.name, config.session, rows, primary, profile.brief if profile else "")

    resumed = resume_lookup(config.session, problems, fresh)
    first = agents[0] if agents else None
    created_inner = not has_session(inner(config.session))
    first_resume = resumed(first) if first and created_inner else ""
    _, more = ensure_inner(config.session, first, told(first) if first else "", first_resume)
    problems += more
    if profile and profile.primary:
        problems += _session_options(inner(config.session), ((PRIMARY_OPTION, profile.primary),))
    if profile and profile.name in config.profiles:
        # Read back by `open`, so a tab opened later gets this profile's brief too.
        problems += _session_options(inner(config.session), ((PROFILE_OPTION, profile.name),))
    created = not present
    if present:
        _, more = arrange(config.session, layout_of(config.session), force=False)
        problems += more
    else:
        socket = socket_path(inner(config.session))
        answer = tmux(
            "new-session",
            "-d",
            "-s",
            config.session,
            "-P",
            "-F",
            "#{window_id} #{pane_id}",
            "-n",
            "deck",
            "--",
            *tabs_argv(config.session, socket),
        )
        window_id, pane_id = _ids(answer)
        tmux("set-option", "-p", "-t", pane_id, ROLE_OPTION, TABS)
        problems += dress(window_id)
        problems += _session_options(config.session, (("mouse", "on"), *bar_options(False)))
        _, more = arrange(config.session, COLUMNS, force=True, socket=socket)
        problems += more
    problems += open_tabs(config.session, agents, told, resumed)
    problems += dress_sessions(config.session)
    return created, problems


#: The tool panes whose ground the deck paints, so a name may be drawn at full strength.
PAINTED_ROLES = frozenset(TOOL_ROLES)


def paint(pane_id: str) -> list[str]:
    """The theme's ground on one deck pane, focused or not. A pane option, so nothing else changes."""
    ground = theme.tmux_styles()["pane"]
    problems = []
    for option in ("window-style", "window-active-style"):
        answer = tmux("set-option", "-p", "-t", pane_id, option, ground)
        if not answer.ok:
            problems.append(f"could not paint a deck pane — {_said(answer)}")
    return problems


def dress_sessions(session: str) -> list[str]:
    """The bars and the key table, on both deck sessions. Re-applied on every `sb deck`, so an
    older deck picks them up; `mouse` is set only when a session is made, as it is the operator's."""
    problems = _session_options(session, bar_options(False, deck_profile(session)))
    problems += _session_options(inner(session), bar_options(True))
    outer, _ = panes(session)
    for pane in outer:
        if pane.role in PAINTED_ROLES:
            problems += paint(pane.pane_id)
    problems += _session_options(session, ((AGENT_COUNT_OPTION, str(agent_count(session))),))
    listed, _ = panes(inner(session))
    problems += write_colours(session, listed, {})
    return problems + install_keys(session) + install_hooks(session) + scroll_once(session)


#: What changes the tab row's fit: its client's width, which tab is current, and how many there are.
SCROLL_HOOKS = ("client-resized", "session-window-changed", "window-linked", "window-unlinked")


def scroll_hooks(session: str) -> list[list[str]]:
    """The `set-hook` argv that re-measure the tab row when its fit can change. Pure, for the suite."""
    return [["set-hook", "-t", scope(inner(session)), hook, job("deck", "scroll")] for hook in SCROLL_HOOKS]


def install_hooks(session: str) -> list[str]:
    problems = []
    for argv in scroll_hooks(session):
        answer = tmux(*argv)
        if not answer.ok:
            problems.append(f"could not hook {argv[3]} — {_said(answer)}")
    return problems


def agent_count(session: str) -> int:
    listed, _ = panes(inner(session))
    return len({p.window_id for p in listed if p.role == AGENT})


def open_tabs(
    session: str,
    agents: list[Agent],
    told: Callable[[Agent], str] = lambda agent: "",
    resumed: Callable[[Agent], str] = lambda agent: "",
) -> list[str]:
    """A tab for each agent that has none, briefed, then the profile's tabs moved to the front in its order.

    Moving is `swap-window`, which moves a window and restarts nothing.
    """
    problems: list[str] = []
    name = inner(session)
    listed, _ = panes(name)
    for agent in agents:
        if find_window(agent.name, listed) is None:
            try:
                _, more = start(name, agent, brief=told(agent), resume=resumed(agent))
                problems += more
            except DeckError as exc:
                problems.append(str(exc))
    if not agents:
        return problems
    listed, _ = panes(name)
    for position, agent in enumerate(agents):
        windows = _window_order(listed)
        wanted = find_window(agent.name, listed)
        if wanted is None or position >= len(windows) or windows[position] == wanted:
            continue
        answer = tmux("swap-window", "-d", "-s", wanted, "-t", windows[position])
        if not answer.ok:
            problems.append(f"could not put {agent.name!r} in profile order — {_said(answer)}")
            break
        listed, _ = panes(name)
    return problems


def _window_order(listed: list[Pane]) -> list[str]:
    seen: dict[str, int] = {}
    for pane in listed:
        seen.setdefault(pane.window_id, pane.window_index)
    return sorted(seen, key=seen.__getitem__)


def layout_of(session: str) -> str:
    answer = tmux("show-options", "-v", "-t", scope(session), LAYOUT_OPTION)
    shape = answer.out.strip() if answer.ok else ""
    return shape if shape in LAYOUTS else COLUMNS


def controller(listed: list[Pane]) -> str | None:
    """The window holding the deck's tool panes, else the lowest-numbered window."""
    for pane in listed:
        if pane.role in (TABS, *TOOL_ROLES):
            return pane.window_id
    ordered = sorted(listed, key=lambda p: p.window_index)
    return ordered[0].window_id if ordered else None


def plan(shape: str, tabs: str | None, tools: list[str], folded: frozenset[str] = frozenset()) -> list[list[str]]:
    """The tmux calls that put the deck's panes in `shape`. Pure, and only ever moves or resizes.

    columns: tabs | the tools stacked.  stack: tabs over the tools side by side.
    grid: tabs | two columns of two, read across; with fewer than four tools it is columns.
    `tools` are pane ids in the column's order; a pane in `folded` is drawn as one
    line (columns, grid) or a narrow strip (stack), and the others share the rest.
    """
    calls: list[list[str]] = []

    def join(source: str, target: str, *flags: str) -> None:
        calls.append(["join-pane", "-d", *flags, "-s", source, "-t", target])

    def resize(pane: str, axis: str, size: str) -> None:
        calls.append(["resize-pane", "-t", pane, axis, size])

    if not tools:
        return calls
    if shape == GRID and len(tools) == len(TOOL_ROLES):
        first, second, third, fourth = tools
        if tabs:
            join(first, tabs, "-h", "-f")
        join(second, first, "-h")
        join(third, first, "-v")
        join(fourth, second, "-v")
        if tabs:
            resize(tabs, "-x", GRID_TABS)
        resize(first, "-x", GRID_COLUMN)
        for top, bottom in ((first, third), (second, fourth)):
            if top not in folded and bottom not in folded:
                resize(top, "-y", HALF)
            for pane in (top, bottom):
                if pane in folded:
                    resize(pane, "-y", FOLDED_HEIGHT)
        return calls
    if shape == GRID:
        shape = COLUMNS
    across, along = ("-h", "-v") if shape == COLUMNS else ("-v", "-h")
    if tabs:
        # Full-window (-f): the tools' column must not inherit the tab pane's share of a stack,
        # or a later join lands in a one-row pane and tmux refuses it.
        join(tools[0], tabs, across, "-f")
    for before, after in zip(tools, tools[1:]):
        join(after, before, along)
    if tabs:
        resize(tools[0], "-x" if shape == COLUMNS else "-y", TOOLS_WIDTH if shape == COLUMNS else TOOLS_HEIGHT)
    axis = "-y" if shape == COLUMNS else "-x"
    open_ = [pane for pane in tools if pane not in folded]
    share = f"{100 // len(open_)}%" if open_ else HALF
    for pane in open_[:-1]:
        resize(pane, axis, share)
    # Folded last, so the room they give up goes to their open neighbours.
    for pane in tools:
        if pane in folded:
            resize(pane, axis, FOLDED_HEIGHT if shape == COLUMNS else FOLDED_WIDTH)
    return calls


def arrange(session: str, shape: str, *, force: bool, socket: str | None = None) -> tuple[list[str], list[str]]:
    """Put back any missing tool pane, then lay the controller out — by moving panes only.

    Nothing here restarts a pane, so every `claude` keeps its process. An agent
    pane in the controller (a round 2 deck's pinned agent) moves into the tabs
    with `break-pane`. With `force` off, the shape is redrawn only when a pane
    had to move or be put back, so the operator's own resizing survives a bare
    `sb deck`. The column's choice (`skyboss/column.py`) says which tool panes
    show, in what order, and which are folded. A hidden pane closes itself on
    reading the hidden set, and this waits a bounded time for it before laying
    out. The roles created, and problems.
    """
    config, _ = load()
    chosen, problems = column_.load(session, config.panes)
    listed, answer = panes(session)
    if not answer.ok:
        return [], [f"could not list the deck's panes — {_said(answer)}"]
    window_id = controller(listed)
    if window_id is None:
        return [], [f"deck {session!r} has no window to arrange"]
    here = [p for p in listed if p.window_id == window_id]
    problems += _move_agents_to_tabs(session, [p for p in here if p.role == AGENT])
    roles: dict[str, str] = {}
    for pane in here:
        if pane.role != AGENT:
            roles.setdefault(pane.role, pane.pane_id)

    hidden = [role for role in TOOL_ROLES if role in chosen.hidden]
    folded = [role for role in chosen.shown if chosen.folded(role)]
    problems += _session_options(session, ((HIDDEN_OPTION, ",".join(hidden)), (FOLDED_OPTION, ",".join(folded))))
    closed = [role for role in hidden if role in roles]
    if closed:
        roles, problems = _await_closed(session, window_id, roles, closed, problems)

    created: list[str] = []
    makers = {
        TABS: lambda: tabs_argv(session, socket if socket is not None else socket_path(inner(session))),
        QUEUE: queue_argv,
        MESSAGES: messages_argv,
        TODOS: todos_argv,
        DECISIONS: decisions_argv,
    }
    for role in (TABS, *chosen.shown):
        argv = makers[role]
        if role in roles:
            continue
        made = tmux("split-window", "-d", "-t", window_id, "-P", "-F", "#{pane_id}", "--", *argv())
        pane_id = made.out.strip()
        if not made.ok or not pane_id:
            problems.append(f"could not open the {role} pane — {_said(made)}")
            continue
        tmux("set-option", "-p", "-t", pane_id, ROLE_OPTION, role)
        if role in PAINTED_ROLES:
            problems += paint(pane_id)
        roles[role] = pane_id
        created.append(role)

    moved = any(p.role == AGENT for p in here)
    if not (force or created or closed or moved):
        return created, problems
    tools = [roles[role] for role in chosen.shown if role in roles]
    for call in plan(shape, roles.get(TABS), tools, frozenset(roles[role] for role in folded if role in roles)):
        answer = tmux(*call)
        if not answer.ok:
            problems.append(f"could not arrange the deck ({call[0]}) — {_said(answer)}")
            break
    problems += _session_options(session, ((LAYOUT_OPTION, shape),))
    return created, problems


def _await_closed(
    session: str, window_id: str, roles: dict[str, str], closing: list[str], problems: list[str]
) -> tuple[dict[str, str], list[str]]:
    """Wait, bounded, for each hidden pane to end itself; the roles still standing, and problems."""
    waited = 0.0
    while True:
        listed, answer = panes(session)
        live = {p.pane_id for p in listed if p.window_id == window_id} if answer.ok else set(roles.values())
        left = [role for role in closing if roles.get(role) in live]
        if not left or waited >= HIDE_WAIT:
            break
        _sleep(HIDE_POLL)
        waited += HIDE_POLL
    for role in closing:
        if role in left:
            problems.append(
                f"the hidden {role} pane has not closed itself after {HIDE_WAIT:.0f}s — it is left in place"
            )
        else:
            roles.pop(role, None)
    return roles, problems


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _move_agents_to_tabs(session: str, agents: list[Pane]) -> list[str]:
    """Each agent pane in the controller becomes a tab, process and all."""
    problems: list[str] = []
    for pane in agents:
        name = pane.agent or pane.window
        answer = tmux(
            "break-pane", "-d", "-s", pane.pane_id, "-t", scope(inner(session)), "-n", name, "-P", "-F", "#{window_id}"
        )
        window_id = answer.out.strip()
        if not answer.ok or not window_id:
            problems.append(f"could not move {name!r} into the tabs — {_said(answer)}")
            continue
        tmux("set-option", "-w", "-t", window_id, AGENT_OPTION, name)
        tmux("set-option", "-w", "-u", "-t", pane.window_id, AGENT_OPTION)
        problems += dress(window_id, tab=True)
    return problems


def all_panes(session: str) -> list[Pane]:
    """The controller's panes, then the inner session's: every window the deck may hold an agent in."""
    listed, _ = panes(session)
    if has_session(inner(session)):
        more, _ = panes(inner(session))
        listed = listed + more
    return listed


def locate(name: str, session: str) -> str | None:
    """`name`'s tab in the inner session, or none."""
    if not has_session(inner(session)):
        return None
    tabs, _ = panes(inner(session))
    return find_window(name, tabs)


def focus(session: str, window_id: str) -> None:
    """Bring a tab forward, with the controller in front of the outer session."""
    select(window_id)
    listed, _ = panes(session)
    home = controller(listed)
    if home is not None:
        select(home)


def select(window_id: str) -> None:
    answer = tmux("select-window", "-t", window_id)
    if not answer.ok:
        raise DeckError(f"could not select the window — {_said(answer)}")


def inside_tmux() -> bool:
    return bool(os.environ.get("TMUX"))


def has_terminal() -> bool:
    """A closed stdin (`None`) is no terminal, not a crash."""
    stdin = sys.stdin
    return bool(stdin is not None and stdin.isatty())


def current_session() -> str:
    """The session of the pane this runs in, or empty when tmux will not say."""
    target = ["-t", os.environ["TMUX_PANE"]] if os.environ.get("TMUX_PANE") else []
    answer = tmux("display-message", "-p", *target, "#{session_name}")
    return answer.out.strip() if answer.ok else ""


def switch(session: str) -> bool:
    """Move this tmux client to the deck. False when not inside tmux.

    From inside the deck it moves nothing: switching the nested client in the
    tab pane to the outer session would draw the deck inside itself.
    """
    if not inside_tmux():
        return False
    if current_session() in (session, inner(session)):
        return True
    answer = tmux("switch-client", "-t", f"={session}")
    if not answer.ok:
        raise DeckError(f"could not switch to the deck — {_said(answer)}")
    return True


def _as_json() -> bool:
    return bool((click.get_current_context().find_root().obj or {}).get("as_json"))


# ============================================================================
# Commands
# ============================================================================


@click.group(name="deck", invoke_without_command=True)
@click.option("--profile", "profile_name", metavar="NAME", help="Open this [profile.NAME]'s tabs: its primary first.")
@click.option("--fresh", is_flag=True, help="Starting a deck: forget the save, and start every tab new.")
@click.pass_context
def deck(ctx: click.Context, profile_name: str | None, fresh: bool) -> None:
    """Create the deck if it is absent, open a profile's tabs, then attach.

        sb deck
        sb deck --profile core
        sb deck --fresh
        sb deck open jam-sense
        sb deck layout stack

    **This acts.** Window 0 is the controller: a tab row of live `claude`s (an
    inner session, `<session>-agents`) beside the queue, the messages and the todos. Each
    tab shows its session's state. Declared in `$SB_HOME/deck.toml`, which
    sky.boss reads and never writes: `[agent.NAME]` takes `cwd`, `args` and a
    one-line `role`; `[profile.NAME]` takes `primary`, `tabs` and a `brief`
    appended to every agent it launches. Each agent is told the roster, roles
    included, at launch. A deck that is not running comes back as it was saved:
    with no `--profile` it reopens the saved tabs, and any tab with a saved
    session resumes it. Inside tmux it switches this client;
    outside, it becomes `tmux attach`, so it emits no envelope.
    """
    if ctx.invoked_subcommand is not None:
        if profile_name or fresh:
            raise click.UsageError("--profile and --fresh open a deck — give them to `sb deck` alone")
        return
    if _as_json():
        raise click.UsageError("deck attaches a terminal and emits no envelope — --json has no meaning here")
    config, problems = load()
    try:
        profile = config.profile(profile_name)
    except KeyError:
        known = ", ".join(sorted(config.profiles)) or "none declared"
        raise click.UsageError(f"no profile {profile_name!r} in {DECK_FILE} (profiles: {known})") from None
    starting = has_session(inner(config.session)) is False
    if starting and fresh:
        decksave.clear(config.session)
    elif starting and not profile_name:
        profile = restored(config, problems) or profile
    try:
        _, more = ensure(config, _projects(), profile, fresh)
    except DeckError as exc:
        raise click.ClickException(str(exc)) from exc
    more += start_marks(config.session)
    note = extended_keys_note()
    warn_now(problems + more + ([note] if note else []))

    try:
        if switch(config.session):
            return
    except DeckError as exc:
        raise click.ClickException(str(exc)) from exc
    if not has_terminal():
        raise click.ClickException(
            f"deck {config.session!r} is ready, and there is no terminal here to attach it to — "
            f"run `tmux attach -t ={config.session}`"
        )
    answer = tmux("attach-session", "-t", f"={config.session}", replace=True)
    if not answer.ok:
        raise click.ClickException(f"could not attach — {_said(answer)}")


@deck.command(name="open")
@click.argument("name")
@click.option("--fresh", is_flag=True, help="Start this tab new, even with a saved session.")
@emit
def deck_open(name: str, fresh: bool) -> Result:
    """A tab running `claude` for NAME, or that tab if it is open.

        sb deck open jam-sense

    **This acts.** NAME is an `[agent.NAME]` in `deck.toml`, or a project in
    `projects.toml` that declares a `cwd`. The tab is a window of the inner
    session, `<session>-agents`, drawn in the controller. Creates the deck first
    if needed. The new agent is briefed with the deck as it stands now; agents
    already running are not told about it, so the brief says to check the live list.
    A saved session is resumed, and keeps the brief it started with.
    """
    result = Result()
    config, problems = load()
    for problem in problems:
        result.warn(problem)
    projects = _projects()
    agent, why = resolve(name, config, projects)
    if agent is None:
        raise click.UsageError(f"no agent {name!r}: {why}")

    try:
        created, more = ensure(config, projects)
        more += start_marks(config.session)
        window_id = locate(name, config.session)
        opened = window_id is None
        if window_id is None:
            # Briefed with the deck as it stands now; agents already running are not updated.
            primary = deck_primary(config.session)
            rows = roster(config, projects, [agent], primary)
            told = brief(agent.name, config.session, rows, primary, deck_profile_brief(config))
            resume = resume_lookup(config.session, more, fresh)(agent)
            window_id, dressed = start(inner(config.session), agent, brief=told, resume=resume)
            more += dressed
        focus(config.session, window_id)
        attached = switch(config.session)
    except DeckError as exc:
        result.ok = False
        result.data = {"error": str(exc)}
        return result

    for problem in more:
        result.warn(problem)
    note = extended_keys_note()
    if note:
        result.warn(note)
    result.data = {
        "session": inner(config.session),
        "window": name,
        "opened": opened,
        "created": created,
        "attached": attached,
        "cwd": agent.directory,
        "argv": shlex.join(agent.argv),
        "from": agent.source,
    }
    return result


@deck.command(name="jump")
@click.argument("name")
@emit
def deck_jump(name: str) -> Result:
    """Select the deck tab for NAME.

        sb deck jump jam-sense

    **This acts** — on the operator, not the agent: it moves which tab is in
    front, and switches this client to the deck when run inside tmux.
    """
    result = Result()
    config, problems = load()
    for problem in problems:
        result.warn(problem)
    present = has_session(config.session)
    if present is None:
        result.ok = False
        result.data = {"error": "tmux could not be run — is it installed?"}
        return result
    if not present:
        raise click.UsageError(f"no deck session {config.session!r} — `sb deck` starts one")
    window_id = locate(name, config.session)
    if window_id is None:
        names = sorted({p.agent for p in all_panes(config.session) if p.agent})
        raise click.UsageError(f"no agent {name!r} in deck {config.session!r} (agents: {', '.join(names) or 'none'})")
    try:
        focus(config.session, window_id)
        attached = switch(config.session)
    except DeckError as exc:
        result.ok = False
        result.data = {"error": str(exc)}
        return result
    result.data = {"session": inner(config.session), "window": name, "attached": attached}
    return result


@deck.command(name="layout")
@click.argument("shape", type=click.Choice(LAYOUTS))
@emit
def deck_layout(shape: str) -> Result:
    """Lay the controller window out as `columns`, `stack` or `grid`.

        sb deck layout stack

    **This acts**, on panes and never on what runs in them: it moves and resizes
    panes, so every `claude` keeps its process. A tool pane that has gone is put
    back first. columns: tabs | the panes stacked. stack: tabs over the panes side
    by side. grid: tabs | the four panes two by two, or columns with fewer showing.
    """
    result = Result()
    config, problems = load()
    for problem in problems:
        result.warn(problem)
    present = has_session(config.session)
    if present is None:
        result.ok = False
        result.data = {"error": "tmux could not be run — is it installed?"}
        return result
    if not present:
        raise click.UsageError(f"no deck session {config.session!r} — `sb deck` starts one")
    try:
        _, more = ensure_inner(config.session)
    except DeckError as exc:
        result.ok = False
        result.data = {"error": str(exc)}
        return result
    more += _session_options(config.session, (("mouse", "on"),))
    more += _session_options(inner(config.session), (("mouse", "on"),))
    created, arranged = arrange(config.session, shape, force=True)
    more += dress_sessions(config.session)
    for problem in more + arranged:
        result.warn(problem)
    if arranged:
        result.partial = True
    result.data = {"session": config.session, "layout": shape, "created": ", ".join(created)}
    return result


@deck.group(name="column")
def deck_column() -> None:
    """The deck's right column: which tool panes show, in what order, and which are folded.

        sb deck column show
        sb deck column fold todos
        sb deck column pick

    `show` observes. `fold` and `pick` act: they save the choice under
    `$SB_STATE` and re-lay the column, moving and resizing panes only (a hidden
    pane is closed; it is a read, and showing it again re-runs it). `pick` is
    the chooser the deck opens on M-s; `fold` is what M-c runs on the focused pane.
    `panes = [...]` in `deck.toml` sets the starting order.
    """


def _column_rows(chosen: column_.Column) -> list[dict]:
    return [
        {
            "pane": role,
            "label": column_.LABELS[role],
            "shown": role not in chosen.hidden,
            "folded": chosen.folded(role),
        }
        for role in chosen.order
    ]


def _apply_column(session: str, chosen: column_.Column) -> Result:
    result = Result()
    column_.save(session, chosen)
    present = has_session(session)
    if present:
        _, problems = arrange(session, layout_of(session), force=True)
        for problem in problems:
            result.warn(problem)
        result.partial = bool(problems)
    elif present is None:
        result.warn("tmux could not be run — the choice is saved and applies when the deck next lays out")
    else:
        result.warn(f"no deck session {session!r} — the choice is saved and applies when `sb deck` starts one")
    result.data = _column_rows(chosen)
    return result


@deck_column.command(name="show")
@emit
def deck_column_show() -> Result:
    """The right column's panes in order, each shown or hidden, folded or open.

        sb deck column show

    An observe: it reads the saved choice and changes nothing.
    """
    result = Result()
    config, problems = load()
    chosen, more = column_.load(config.session, config.panes)
    for problem in problems + more:
        result.warn(problem)
    result.data = _column_rows(chosen)
    return result


@deck_column.command(name="fold")
@click.argument("pane")
@emit
def deck_column_fold(pane: str) -> Result:
    """Fold PANE to one line, or unfold it.

        sb deck column fold todos

    **This acts.** A folded pane draws its label and counts in one line (a
    narrow strip in the stack layout), and its neighbours take the room.
    """
    if pane not in column_.TOOLS:
        raise click.UsageError(f"{pane!r} is not a right-column pane — the panes are {', '.join(column_.TOOLS)}")
    config, _ = load()
    chosen, _ = column_.load(config.session, config.panes)
    chosen.collapsed = column_.toggle(chosen.collapsed, pane)
    return _apply_column(config.session, chosen)


@deck_column.command(name="pick")
@emit
def deck_column_pick() -> Result:
    """Choose the right column's panes, their order and their folding, on a terminal.

        sb deck column pick

    **This acts** when you press Enter: the choice is saved and the column re-laid.
    q or Esc leaves with nothing changed. The deck opens this in a popup on M-s.
    """
    from rich.console import Console

    from skyboss import keys
    from skyboss.output import THEME

    if not has_terminal():
        raise click.UsageError("pick needs a terminal — use `sb deck column fold`, or M-s inside the deck")
    config, _ = load()
    chosen, _ = column_.load(config.session, config.panes)
    with keys.reader() as wait_for:
        picked = column_.pick(chosen, Console(theme=THEME, highlight=False), wait_for)
    if picked is None:
        result = Result()
        result.data = _column_rows(chosen)
        result.warn("cancelled — nothing changed")
        return result
    return _apply_column(config.session, picked)


@deck.command(name="reload")
@emit
def deck_reload() -> Result:
    """Re-apply the deck's settings and restart its tool panes on this sky.boss's code.

        sb deck reload

    **This acts**, and kills nothing: the bars, keys and colours are set again,
    and each tool pane and the marks loop is asked to close itself and is then
    opened fresh. Agent tabs are untouched. A pane from before round 5 of [[command-deck]] cannot be
    asked, so it is named in the result: press q in it, then run this again.
    """
    result = Result()
    config, problems = load()
    for problem in problems:
        result.warn(problem)
    present = has_session(config.session)
    if present is None:
        result.ok = False
        result.data = {"error": "tmux could not be run — is it installed?"}
        return result
    if not present:
        raise click.UsageError(f"no deck session {config.session!r} — `sb deck` starts one")
    chosen, more = column_.load(config.session, config.panes)
    listed, _ = panes(config.session)
    window_id = controller(listed) or ""
    roles = {p.role: p.pane_id for p in listed if p.window_id == window_id and p.role in TOOL_ROLES}
    cycling = [role for role in chosen.shown if role in roles]
    more += _session_options(config.session, ((HIDDEN_OPTION, ",".join(TOOL_ROLES)),))
    _, waited = _await_closed(config.session, window_id, dict(roles), cycling, [])
    stuck = [role for role in cycling if any(role in line for line in waited)]
    for role in stuck:
        more.append(f"the {role} pane predates reload and kept running — press q in it, then `sb deck reload` again")
    created, arranged = arrange(config.session, layout_of(config.session), force=True)
    marks = restart_marks(config.session)
    more += arranged + dress_sessions(config.session) + marks
    for problem in more:
        result.warn(problem)
    result.partial = bool(stuck or arranged or marks)
    result.data = {"session": config.session, "restarted": ", ".join(created), "kept": ", ".join(stuck)}
    return result


@deck.command(name="marks")
@click.option(
    "--every",
    type=click.IntRange(min=1),
    default=None,
    metavar="SECONDS",
    help="Keep writing every N seconds until the deck is gone. The deck starts one such loop itself.",
)
@click.option("--ticks", type=click.IntRange(min=1), default=None, metavar="N", help="With --every: stop after N.")
@emit
def deck_marks(every: int | None, ticks: int | None) -> Result:
    """Write each tab's session state onto its tmux window, for the tab row to draw.

        sb deck marks
        sb deck marks --every 3

    **This acts**: it sets the `@sb-state` window option on the deck's own tabs,
    and nothing else. One loop serves the whole deck and writes only what
    changed; the tab row's right end says when it last wrote.
    """
    if ticks is not None and every is None:
        raise click.UsageError("--ticks needs --every — a single write already stops after one")
    config, problems = load()
    written: dict[str, str] = {}
    if every is None:
        result = marks_once(config.session, written)
        for problem in problems:
            result.warn(problem)
        return result

    coloured: dict[str, str] = {}
    own = str(os.getpid())
    _session_options(inner(config.session), ((MARKS_PID_OPTION, own),))
    count = 0
    while ticks is None or count < ticks:
        count += 1
        owner = _marks_owner(config.session)
        if not has_session(inner(config.session)) or (owner is not None and str(owner) != own):
            break
        marks_once(config.session, written, colours=coloured)
        if ticks is not None and count >= ticks:
            break
        SLEEP(every)
    raise click.exceptions.Exit(0)


@deck.command(name="scroll")
@emit
def deck_scroll() -> Result:
    """Show the tab row's scrollbar if the tabs overflow, and hide it if not.

        sb deck scroll

    **This acts**, on the deck's own tab bar. tmux scrolls the tabs to keep the
    current one in view; this draws where that view sits. The deck runs it on a
    resize or a tab change, so it is rarely typed.
    """
    result = Result()
    config, problems = load()
    for problem in problems:
        result.warn(problem)
    if not has_session(inner(config.session)):
        result.ok = False
        result.data = {"error": f"no deck tabs {inner(config.session)!r} — `sb deck` starts them"}
        return result
    for problem in scroll_once(config.session):
        result.degrade(problem)
    shown = tmux("show-options", "-v", "-t", scope(inner(config.session)), "status")
    result.data = {"overflowing": shown.ok and shown.out.strip() == str(TAB_ROWS + 1)}
    return result


@deck.command(name="save")
@emit
def deck_save() -> Result:
    """Save each open tab's session, so a later `sb deck` resumes it.

        sb deck save

    **This acts**, on sky.boss's own state. The marks loop saves as it goes, so a
    reboot loses nothing, but it never forgets a tab; this writes exactly the open
    tabs, which is how a closed tab leaves the save. `sb deck exit` does the same.
    """
    result = Result()
    config, problems = load()
    for problem in problems:
        result.warn(problem)
    if not has_session(inner(config.session)):
        raise click.UsageError(f"no deck tabs {inner(config.session)!r} — nothing to save")
    tabs, more = save_now(config.session)
    for problem in more:
        result.degrade(problem)
    result.data = [{"agent": tab.agent, "session": tab.id, "cwd": tab.cwd} for tab in tabs]
    return result


@deck.command(name="exit")
@emit
def deck_exit() -> Result:
    """Save the tabs, then end the deck: stop its marks loop and kill its two tmux sessions.

        sb deck exit

    **This acts, and it is the only deck command that kills anything.** Every
    `claude` in a tab ends with its session, and a later `sb deck` resumes it.
    Nothing outside the deck's two sessions is touched. Ctrl-Q or the ✕ in the deck's bar asks first, then runs this.
    """
    config, problems = load()
    result = Result()
    for problem in problems:
        result.warn(problem)
    present = [name for name in (inner(config.session), config.session) if has_session(name)]
    if not present:
        raise click.UsageError(f"no deck session {config.session!r} — nothing to end")
    agents = agent_count(config.session) if inner(config.session) in present else 0
    saved: list[decksave.Tab] = []
    if inner(config.session) in present:
        saved, more = save_now(config.session)
        for problem in more:
            result.warn(problem)
    stopped = stop_marks(config.session)
    ended, failed = end_sessions(present)
    for name, why in failed:
        result.degrade(f"could not end {name!r} — {why}")
    result.data = {"ended": ", ".join(ended), "agents": agents, "marks": stopped, "saved": len(saved)}
    return result


def stop_marks(session: str) -> str:
    """Stop the marks loop, if one is live. Its pid, or empty."""
    import signal

    pid = _marks_owner(session)
    if pid is None:
        return ""
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return ""
    return str(pid)


def restart_marks(session: str) -> list[str]:
    """Put the marks loop on this sky.boss's code, waiting for the old one to leave."""
    stop_marks(session)
    waited = 0.0
    while _marks_owner(session) is not None:
        if waited >= HIDE_WAIT:
            return ["the marks loop kept running on its old code — `sb deck reload` again"]
        _sleep(HIDE_POLL)
        waited += HIDE_POLL
    return start_marks(session)


def end_sessions(names: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Kill exactly these sessions, the tabs first. The one place the deck kills anything."""
    ended: list[str] = []
    failed: list[tuple[str, str]] = []
    for name in names:
        answer = tmux("kill-session", "-t", f"={name}")
        if answer.ok:
            ended.append(name)
        else:
            failed.append((name, _said(answer)))
    return ended, failed


@deck.command(name="messages")
@click.option(
    "--refresh",
    type=click.IntRange(min=1),
    default=None,
    metavar="SECONDS",
    help="Stay resident and re-read every N seconds. Off a terminal, one NDJSON envelope per tick.",
)
@click.option(
    "--ticks",
    type=click.IntRange(min=1),
    default=None,
    metavar="N",
    help="With --refresh: stop after N refreshes and exit 0.",
)
@click.option(
    "--screen",
    is_flag=True,
    help="With --refresh: redraw on the alternate screen, as the deck's own panes do.",
)
@emit
def deck_messages(refresh: int | None, ticks: int | None, screen: bool) -> Result:
    """Messages agent sessions sent each other, newest last.

        sb deck messages
        sb deck messages --refresh 10

    An observe. One row per message a live session received: when, sender →
    receiver, and the first line. The last 50, read from each live session's
    transcript; a transcript that cannot be read is counted in a warning.
    """
    config, _ = load()
    pane = DeckPane(
        config.session, lambda row: bool(row.get("from_agent") or row.get("to_agent")), scroll=True, role=MESSAGES
    )
    # Colour only where the deck paints the ground: in its pane, not in whatever terminal ran this.
    once = functools.partial(messages_result, place=placement, paint=bool(refresh and screen))
    return _resident("deck messages", once, refresh, ticks, screen, keep_last("message(s)", pane), pane)


@deck.command(name="message")
@click.argument("key")
@click.option("--page", is_flag=True, help="On a terminal, read it in a pager (q closes), as the deck's popup does.")
@emit
def deck_message(key: str, page: bool) -> Result:
    """One message whole: who sent it, to whom, when, and the full body.

        sb deck message <key>

    An observe. KEY is the `key` a row of `sb --json deck messages` carries;
    clicking a row in the MESSAGES pane opens this in a popup.
    """
    result = message_result(key, place=placement)
    if page and result.ok and has_terminal() and not _as_json():
        _page(result.data)
        raise click.exceptions.Exit(0)
    return result


def _page(data: dict) -> None:
    """The message through `less -R`, or printed and held for a key when there is no less."""
    import io

    from rich.console import Console

    from skyboss import messages as messages_
    from skyboss.output import THEME

    width = shutil.get_terminal_size().columns
    buffer = io.StringIO()
    Console(
        file=buffer, theme=THEME, highlight=False, force_terminal=True, color_system="truecolor", width=width
    ).print(messages_.page(data))
    less = shutil.which("less")
    if less:
        # `-+F`: an operator's LESS may quit at once on a short page, which would close the popup unread.
        subprocess.run([less, "-R", "-c", "-+F", "-Pq closes"], input=buffer.getvalue(), text=True, env=child_env())
        return
    sys.stdout.write(buffer.getvalue() + "\n(any key closes)")
    sys.stdout.flush()
    with keys_.reader() as wait_for:
        while wait_for(60.0) is None:
            pass


def keep_last(noun: str, pane: DeckPane | None = None) -> Callable[[Result, int], tuple[Result, str]]:
    """The newest `keep` rows, or `keep` rows ending `pane.offset` back from them, with a line saying where."""

    def fit(result: Result, keep: int) -> tuple[Result, str]:
        rows = result.data
        offset = pane.within(len(rows), keep) if pane is not None else 0
        end = len(rows) - offset
        start = max(0, end - keep)
        shown = replace(result, data=rows[start:end])
        if pane is not None:
            pane.rows = shown.data
        if pane is None:
            return shown, f"{start} earlier {noun} not shown — the newest {keep} fit"
        if offset:
            return shown, f"↑ {offset} back · {start} earlier · End or {SHORTCUTS['newest']}: newest"
        return shown, f"newest · {start} earlier {noun} not shown" if start else "newest"

    return fit


class DeckPane(resident_.Control):
    """A deck tool pane's view state: the outside toggle and the scroll, read from the deck session.

    The pane reads its session's options each frame and writes none: a shortcut
    sets an option, and the pane adopts it. Its own keys move only its own offset.
    """

    def __init__(
        self,
        session: str,
        keeps: Callable[[dict], bool],
        *,
        scroll: bool = False,
        top: bool = False,
        role: str = "",
    ) -> None:
        self.session = session
        self.role = role
        self.head = "sb.deck.head"
        # MESSAGES and DECISIONS open a clicked row in a popup; `rows` and `lines` are what the last frame drew.
        self.clicks = role in (MESSAGES, DECISIONS)
        self.rows: list[dict] = []
        self.lines: list[str] = []
        self.fold = False
        self.keeps = keeps
        self.counted = scroll
        self.wheel = scroll
        # A top-anchored pane scrolls by its own keys only; M-u and M-e belong to MESSAGES.
        self.top = top
        self.offset = 0
        self.page = 10
        self.total = 10**6
        self.hide = False
        self.hidden = 0
        self.seq: str | None = None

    def poll(self) -> None:
        answer = tmux("show-options", "-t", scope(self.session))
        options = session_options(answer.out) if answer.ok else {}
        self.hide = bool(options.get(HIDE_OPTION))
        self.fold = bool(self.role) and self.role in options.get(FOLDED_OPTION, "").split(",")
        if self.role and self.role in options.get(HIDDEN_OPTION, "").split(","):
            raise resident_.Leave
        seq = options.get(SCROLL_SEQ_OPTION, "")
        if self.seq is not None and seq != self.seq and not self.top:
            self.move("pgup" if options.get(SCROLL_OPTION) == "older" else "end")
        self.seq = seq

    def shape(self, result: Result) -> Result:
        self.poll()
        self.hidden = 0
        if not self.hide or not isinstance(result.data, list):
            return result
        kept = [row for row in result.data if self.keeps(row)]
        self.hidden = len(result.data) - len(kept)
        return replace(result, data=kept)

    def note(self) -> str:
        # Information, so the footer and not a warning; the count stays so hidden never reads as none.
        return f"{self.hidden} outside hidden · {SHORTCUTS['outside']} shows" if self.hidden else ""

    def folded(self) -> bool:
        return self.fold

    def shared_clock(self) -> bool:
        # Every deck pane refreshes together; the outer bar's footer draws the one clock.
        return True

    def summary(self, result: Result | None) -> str:
        if result is None:
            return f"{column_.LABELS.get(self.role, self.role)} · nothing has run yet"
        rows = result.data if isinstance(result.data, list) else []
        return column_.summary(self.role, rows, ok=result.ok, note=self.note())

    def on_key(self, key: str) -> bool:
        cell = keys_.clicked(key)
        if cell is not None:
            row = clicked_row(self.lines, self.rows, cell[1])
            if self.clicks and row is not None and row.get("key"):
                open_message(row["key"])
            elif self.clicks and row is not None and row.get("kind") == "item":
                open_decision(str(row["agent"]), int(row["n"]))
            return False
        return self.wheel and self.move(key)

    def framed(self, lines: list[str]) -> None:
        self.lines = lines

    def move(self, key: str) -> bool:
        steps = {"up": 1, "down": -1, "wheelup": 3, "wheeldown": -3, "pgup": self.page, "pgdn": -self.page}
        if self.top:
            # Counted from the top: down reveals later rows, Home returns.
            steps = {name: -step for name, step in steps.items()}
        was = self.offset
        if key == ("home" if self.top else "end"):
            self.offset = 0
        elif key == ("end" if self.top else "home"):
            self.offset = 10**6
        elif key in steps:
            self.offset = max(0, self.offset + steps[key])
        # Clamped here, against the last drawing, so `down` at the top moves at once.
        self.offset = min(self.offset, max(0, self.total - self.page))
        return self.offset != was

    def within(self, total: int, keep: int) -> int:
        """The offset to draw with `keep` rows of `total`. Read-only: the fit tries several `keep`s."""
        self.total, self.page = total, max(1, keep)
        return min(self.offset, max(0, total - keep))


def session_options(text: str) -> dict[str, str]:
    """`show-options` output as a mapping, unquoted as tmux quoted it (an empty value prints as `''`)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        name, _, value = line.partition(" ")
        try:
            words = shlex.split(value)
        except ValueError:
            words = [value.strip()]
        out[name] = words[0] if words else ""
    return out


def clicked_row(lines: list[str], rows: list[dict], y: int) -> dict | None:
    """The table row drawn on screen line `y` (one-based), or None.

    A deck table is its header, a rule of `─`, then one line per row, so rows count from the line
    after the first all-rule line; the top band starts `┌` and is never taken for it.
    """
    rule = next((i for i, line in enumerate(lines) if line.strip() and set(line.strip()) == {"─"}), None)
    if rule is None:
        return None
    index = y - 1 - (rule + 1)
    return rows[index] if 0 <= index < len(rows) else None


#: The message popup: room for a message to read, with the deck still in view around it.
POPUP_SIZE = ("60%", "50%")


def message_popup_argv(key: str) -> list[str]:
    """`display-popup` reading one message."""
    sb = shlex.quote(str(PROJECT_ROOT / "sb"))
    return popup_argv(" message ", f"exec {sb} deck message --page {shlex.quote(key)}")


def decision_popup_argv(agent: str, n: int) -> list[str]:
    """`display-popup` offering one decision's choices."""
    sb = shlex.quote(str(PROJECT_ROOT / "sb"))
    return popup_argv(" decision ", f"exec {sb} deck decide rule {shlex.quote(agent)} {n}")


def popup_argv(title: str, command: str) -> list[str]:
    """`display-popup` on the void the deck paints, so agent hues stay legible."""
    style = theme.tmux_styles()
    width, height = POPUP_SIZE
    return [
        "display-popup",
        "-E",
        "-w",
        width,
        "-h",
        height,
        "-s",
        style["pane"],
        "-S",
        style["border-active"],
        "-T",
        title,
        command,
    ]


def open_message(key: str) -> None:
    _open_popup(message_popup_argv(key))


def open_decision(agent: str, n: int) -> None:
    _open_popup(decision_popup_argv(agent, n))


def _open_popup(argv: list[str]) -> None:
    """Open the popup and return at once: the pane keeps drawing while the operator reads."""
    try:
        subprocess.Popen(
            ["tmux", *argv],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=child_env(),
            start_new_session=True,
        )
    except OSError:
        pass


def keep_first(noun: str) -> Callable[[Result, int], tuple[Result, str]]:
    """The first `keep` rows, with a line counting the rest. The queue sorts `waiting` first."""

    def fit(result: Result, keep: int) -> tuple[Result, str]:
        rows = result.data
        return replace(result, data=rows[:keep]), f"{len(rows) - keep} more {noun} not shown — waiting comes first"

    return fit


def keep_from_top(noun: str, pane: DeckPane) -> Callable[[Result, int], tuple[Result, str]]:
    """`keep` rows starting `pane.offset` down from the top, with a line saying where."""

    def fit(result: Result, keep: int) -> tuple[Result, str]:
        rows = result.data
        start = pane.within(len(rows), keep)
        below = max(0, len(rows) - start - keep)
        shown = replace(result, data=rows[start : start + keep])
        pane.rows = shown.data
        if start:
            where = f"{below} {noun} below" if below else "the end"
            return shown, f"↓ {start} down · {where} · Home: top"
        return shown, f"top · {below} more {noun} below" if below else "top"

    return fit


def _resident(
    source: str,
    once: Callable[[], Result],
    refresh: int | None,
    ticks: int | None,
    screen: bool,
    fit: Callable[[Result, int], tuple[Result, str]],
    control: resident_.Control | None = None,
) -> Result:
    """One read, or the same read on a cadence — `sb data`'s resident path, shared.

    The deck's panes take `--screen`: a pane the operator drags to a new size
    must redraw whole, not leave the old inline frames above the new one. On
    that screen `fit` trims rows to the height, counting what it left out;
    `--json` and a pipe always carry every row.
    """
    if ticks is not None and refresh is None:
        raise click.UsageError("--ticks needs --refresh — a single read already stops after one")
    if refresh is not None:
        from skyboss import output

        if _as_json() or not output.stdout_is_terminal():
            output.resident_ndjson(once, refresh, runs=ticks)
        else:
            resident_.reside(
                source,
                refresh,
                once,
                screen=screen,
                runs=ticks,
                fit=fit,
                fill=screen,
                control=control if screen else None,
            )
        raise click.exceptions.Exit(0)
    return once()


# ============================================================================
# The queue — who is waiting on the operator
# ============================================================================


def parents(proc: Path = Path("/proc")) -> dict[int, int]:
    """Every process's parent, read from `/proc/<pid>/stat`. Empty when there is no `/proc`."""
    out: dict[int, int] = {}
    try:
        entries = list(proc.iterdir())
    except OSError:
        return out
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
        except OSError:
            continue
        # Field 4, read after the last `)` because the comm may contain one.
        fields = stat[stat.rfind(")") + 2 :].split()
        if len(fields) > 1 and fields[1].isdigit():
            out[int(entry.name)] = int(fields[1])
    return out


def tree(root: int, parent_of: dict[int, int]) -> list[int]:
    """`root` and every descendant, breadth first. A pane may run `claude` through a shell."""
    children: dict[int, list[int]] = {}
    for pid, ppid in parent_of.items():
        children.setdefault(ppid, []).append(pid)
    seen = [root]
    for pid in seen:
        seen.extend(c for c in sorted(children.get(pid, [])) if c not in seen)
    return seen


def _row(where: str, window: str, status: str, session, pid: int, now: datetime, colour: str = "") -> dict:
    started = session.started if session else None
    state = STATES.get(status, status)
    return {
        "where": where,
        "window": window,
        "window_parts": [[window, colour or None]],
        "state": state,
        "state_parts": [[state, "sb.warn" if status == WAITING else "sb.accent" if status == "busy" else None]],
        "status": status,
        "name": session.name if session else "",
        "up": ago((now - started).total_seconds()) if started else "",
        "cwd": session.cwd if session else "",
        "pid": pid,
        "id": session.id if session else "",
        "started": started.isoformat() if started else "",
    }


# The deck's word for each registry word, most active first: the order NEEDS YOU sorts in.
# `shell` is Claude Code's own word for a session running a shell command; `unregistered`
# is a deck window whose agent pane has no record at all, so it comes last.
STATES = {WAITING: "needs you", "busy": "busy", "shell": "shell", "idle": "idle", UNREGISTERED: UNREGISTERED}


def _by_activity(rows: list[dict]) -> list[dict]:
    """Needs you, busy, shell, idle, unregistered, then any other word; compared literally."""
    rank = {word: n for n, word in enumerate(STATES)}
    return sorted(rows, key=lambda row: rank.get(row["status"], len(rank)))


def deck_windows(listed: list[Pane], sessions: list, parent_of: dict[int, int]) -> tuple[list[tuple], set[str]]:
    """Each deck window's sessions as `(window_id, label, status, session, pid)`, and the ids claimed.

    A window the deck started an agent in whose process has no registry record
    is `unregistered` — Claude Code's trust dialog writes none — rather than left out.
    """
    by_pid = {s.pid: s for s in sessions if s.pid}
    claimed: set[str] = set()
    windows: dict[str, list[Pane]] = {}
    for pane in sorted(listed, key=lambda p: p.window_index):
        windows.setdefault(pane.window_id, []).append(pane)

    entries: list[tuple] = []
    for window_id, group in windows.items():
        label = group[0].agent or group[0].window
        found = False
        for pane in group:
            for pid in tree(pane.pid, parent_of):
                session = by_pid.get(pid)
                if session is not None and session.id not in claimed:
                    claimed.add(session.id)
                    found = True
                    entries.append((window_id, label, session.status, session, session.pid))
        agent = next((p for p in group if p.role == AGENT), None)
        if not found and agent is not None:
            entries.append((window_id, label, UNREGISTERED, None, agent.pid))
    return entries, claimed


def placement(sessions: list) -> dict[str, tuple[str, int]]:
    """Session id → the deck agent it runs as and that agent's tab slot, for sessions in a deck tab."""
    config, _ = load()
    if not has_session(inner(config.session)):
        return {}
    listed, _ = panes(inner(config.session))
    slots = agent_slots(listed)
    entries, _ = deck_windows(listed, sessions, parents())
    return {
        session.id: (label, slots[window_id])
        for window_id, label, _, session, _ in entries
        if session is not None and window_id in slots
    }


def agent_slots(listed: list[Pane]) -> dict[str, int]:
    """Window id → colour slot: agent tabs in tab order, so the primary is slot 0."""
    order = _window_order([p for p in listed if p.role == AGENT])
    return {window_id: slot for slot, window_id in enumerate(order)}


def write_colours(session: str, listed: list[Pane], written: dict[str, str]) -> list[str]:
    """Each agent tab's colour as a window option, where it changed. The tab format reads it."""
    problems = []
    labels = {p.window_id: p.agent or p.window for p in listed}
    config, _ = load()
    for window_id, slot in agent_slots(listed).items():
        colour = theme.agent_colour(labels[window_id], slot)
        if written.get(window_id) == colour:
            continue
        if config.themes:
            # Claude Code reloads a changed theme file, so a moved tab's console follows its colour.
            problems += write_theme(labels[window_id], colour, theme_base(config))
        answer = tmux("set-option", "-w", "-t", window_id, COLOUR_OPTION, colour)
        if answer.ok:
            written[window_id] = colour
        else:
            problems.append(f"could not colour a tab — {_said(answer)}")
    return problems


def claimed(sessions: list) -> tuple[set[str] | None, str]:
    """The ids of the sessions running in a deck pane, or None and why the deck could not be read."""
    config, _ = load()
    present = has_session(config.session)
    if present is None:
        return None, "tmux could not be run, so the deck could not be read"
    if not present:
        return set(), ""
    _, ids = deck_windows(all_panes(config.session), sessions, parents())
    return ids, ""


def queue_rows(
    listed: list[Pane], sessions: list, parent_of: dict[int, int], now: datetime, paint: bool = False
) -> list[dict]:
    """One row per deck window, most active first; then every live session outside the deck, the same way.

    Painted, a window's name takes its tab's colour, as MESSAGES and TODOS draw it.
    """
    entries, claimed = deck_windows(listed, sessions, parent_of)
    slots = agent_slots(listed)

    def colour(window_id: str, label: str) -> str:
        return theme.agent_role(label, slots[window_id]) if paint and window_id in slots else ""

    inside = [
        _row("deck", label, status, session, pid, now, colour(window_id, label))
        for window_id, label, status, session, pid in entries
    ]
    outside = [_row("outside", "", s.status, s, s.pid, now) for s in sessions if s.id not in claimed]
    return _by_activity(inside) + _by_activity(outside)


INLINE = ("where", "window", "state", "name", "up", "cwd")
HIDDEN = ("window_parts", "state_parts", "status", "pid", "id", "started")


def view_of(rows: list[dict]) -> dict:
    """Authored: these keys are sky.boss's own, so there is an order to state and nothing to infer.

    `status` and `window` are floored at their own width: the queue exists to show
    those two words, and `unregister…` would be a different word.
    """
    columns = [describe(key, rows) for key in INLINE]
    for column in columns:
        if column["key"] in ("state", "window"):
            column["min"] = column["max"]
            column["segments"] = f"{column['key']}_parts"
    return {
        "columns": columns,
        "details": [],
        "hidden": list(HIDDEN),
        "authored": True,
    }


def queue_result(
    adapters: list | None = None, proc: Path = Path("/proc"), scope: str = "all", paint: bool = False
) -> Result:
    """The queue's envelope. Every way it could not look is a warning, so empty is never ambiguous."""
    result = Result()
    config, problems = load()
    for problem in problems:
        result.warn(problem)

    chosen = adapters if adapters is not None else agents_.providers()
    sessions, registry_problems, tally = agents_.fold(chosen)
    for problem in registry_problems:
        result.warn(problem)
    if tally.unverified:
        result.warn(f"{tally.unverified} session(s) drawn unverified — no /proc to confirm the process")

    listed: list[Pane] = []
    present = has_session(config.session)
    if present is None:
        result.degrade("tmux could not be run — no deck windows read, so every session here is listed as outside")
    elif not present:
        result.warn(f"no deck session {config.session!r} — every session here is outside the deck")
    else:
        listed, answer = panes(config.session)
        if not answer.ok:
            result.degrade(f"could not list the deck's windows — {_said(answer)}")
        if has_session(inner(config.session)):
            tabs, answer = panes(inner(config.session))
            listed += tabs
            if not answer.ok:
                result.degrade(f"could not list the deck's tabs — {_said(answer)}")

    rows = queue_rows(listed, sessions, parents(proc), datetime.now(timezone.utc), paint)
    result.data = rows if scope == "all" else [r for r in rows if r["where"] == scope]
    if not result.data:
        result.warn(f"no sessions {agents_.PLACES[scope]}" if rows else agents_.empty_reason(tally, len(chosen)))
        return result
    result.view = view_of(result.data)
    return result


@deck.command(name="queue")
@click.option(
    "--refresh",
    type=click.IntRange(min=1),
    default=None,
    metavar="SECONDS",
    help="Stay resident and re-read every N seconds. Off a terminal, one NDJSON envelope per tick.",
)
@click.option(
    "--ticks",
    type=click.IntRange(min=1),
    default=None,
    metavar="N",
    help="With --refresh: stop after N refreshes and exit 0.",
)
@click.option(
    "--screen",
    is_flag=True,
    help="With --refresh: redraw on the alternate screen, as the deck's own panes do.",
)
@click.option(
    "--scope",
    type=click.Choice(agents_.SCOPES),
    default="all",
    show_default=True,
    help="deck: rows for deck windows. outside: every other live session.",
)
@emit
def deck_queue(refresh: int | None, ticks: int | None, screen: bool, scope: str) -> Result:
    """Which agent sessions are waiting on you, deck windows first.

        sb deck queue
        sb deck queue --refresh 5

    An observe — a window may pin it. One row per deck window with its `claude`
    pid and the registry's `status` word, `waiting` first; a window with no
    record reads `unregistered`. Live sessions outside the deck follow.
    """
    once = functools.partial(queue_result, scope=scope, paint=bool(refresh and screen))
    config, _ = load()
    pane = DeckPane(config.session, lambda row: row.get("where") == "deck", role=QUEUE)
    return _resident("deck queue", once, refresh, ticks, screen, keep_first("row(s)"), pane)


# ============================================================================
# Todos — each agent's own list, written from its own tab
# ============================================================================


@deck.command(name="brief")
@click.argument("name", required=False)
@emit
def deck_brief(name: str | None) -> Result:
    """The brief a deck agent is given, rebuilt now with the live roster.

        sb deck brief
        sb deck brief stash-flow

    An observe. Inside a tab, that tab's brief; NAME previews another agent's.
    An agent started before the deck briefed it, or before a peer opened, reads
    this to catch up — the deck never types into a running agent.
    """
    result = Result()
    config, problems = load()
    for problem in problems:
        result.warn(problem)
    present = has_session(inner(config.session))
    if not present:
        result.ok = False
        result.data = {"error": f"no deck session {config.session!r} — start one with `sb deck`"}
        return result
    who = name or caller_tab(config.session)
    if who is None:
        result.ok = False
        result.data = {
            "error": f"not running inside a tab of deck {config.session!r} — name an agent to preview its brief"
        }
        return result
    projects = _projects()
    primary = deck_primary(config.session)
    rows = roster(config, projects, [], primary)
    if who not in (row[0] for row in rows):
        result.warn(f"{who!r} has no tab in deck {config.session!r}; this is the brief it would get if opened")
    result.data = {
        "agent": who,
        "session": config.session,
        "primary": primary,
        "peers": [{"name": n, "cwd": d, "role": r} for n, d, r in rows if n != who],
        "brief": brief(who, config.session, rows, primary, deck_profile_brief(config)),
    }
    return result


def caller_tab(session: str, pid: int | None = None, parent_of: dict[int, int] | None = None) -> str | None:
    """The deck tab whose pane runs this process, by the process tree; None outside every tab.

    Never by name: a session outside the deck may carry a tab's name, and it is
    not that tab. The walk goes up the parent chain to an agent pane's pid.
    """
    listed, _ = panes(inner(session))
    owners = {p.pid: p.agent for p in listed if p.role == AGENT and p.agent}
    if not owners:
        return None
    parent_of = parents() if parent_of is None else parent_of
    current, seen = os.getpid() if pid is None else pid, set()
    while current and current not in seen:
        if current in owners:
            return owners[current]
        seen.add(current)
        current = parent_of.get(current, 0)
    return None


def tab_order(session: str) -> list[tuple[str, int]]:
    """(agent, colour slot) in tab order with the primary first — the slot is the tab's own colour."""
    listed, _ = panes(inner(session))
    agents = [p for p in listed if p.role == AGENT and p.agent]
    slots = agent_slots(listed)
    order: list[tuple[str, int]] = []
    for window_id in _window_order(agents):
        name = next(p.agent for p in agents if p.window_id == window_id)
        if name not in (n for n, _ in order):
            order.append((name, slots.get(window_id, 0)))
    primary = deck_primary(session)
    return sorted(order, key=lambda pair: pair[0] != primary)


def _todo_owner(session: str) -> tuple[str | None, str]:
    """The calling tab's agent, or None and the sentence saying why it cannot be named."""
    present = has_session(inner(session))
    if present is None:
        return None, "tmux could not be run — is it installed?"
    if not present:
        return None, f"no deck session {session!r} — a todo or decision list belongs to a deck tab, and there is none"
    agent = caller_tab(session)
    if agent is None:
        return None, (
            f"not running inside a tab of deck {session!r} — a list belongs to the tab whose pane runs "
            "the caller, so add, done and rm refuse anywhere else"
        )
    return agent, ""


def _todo_change(change: Callable[[str, str], todos_.TodoList]) -> Result:
    result = Result()
    config, problems = load()
    for problem in problems:
        result.warn(problem)
    agent, why = _todo_owner(config.session)
    if agent is None:
        result.ok = False
        result.data = {"error": why}
        return result
    try:
        todo = change(config.session, agent)
    except (IndexError, ValueError) as exc:
        result.ok = False
        result.data = {"error": f"{agent}: {exc}"}
        return result
    result.data = {
        "session": config.session,
        "agent": agent,
        "updated": todo.updated,
        "open": todo.open,
        "items": [
            {"n": n, "text": item.text, "done": item.done, **({"ruling": item.ruling} if item.ruling else {})}
            for n, item in enumerate(todo.items, start=1)
        ],
    }
    return result


@deck.group(name="todo")
def deck_todo() -> None:
    """Each deck agent's own todo list, drawn in the deck's TODOS pane.

        sb deck todo add "write the parser test"
        sb deck todo done 1
        sb deck todo list

    `add`, `done` and `rm` act, on the list of the tab they run in — found
    through the process tree, so they refuse outside a deck tab. `list` observes.
    Lists live under `$SB_STATE`, never in a repo or `$SB_HOME`.
    """


@deck_todo.command(name="add")
@click.argument("text")
@emit
def deck_todo_add(text: str) -> Result:
    """Add TEXT to this tab's list.

        sb deck todo add "write the parser test"

    **This acts**, on the list of the tab it runs in, and refuses anywhere else.
    """
    if not todos_.clean(text):
        raise click.UsageError("a todo needs some text")
    return _todo_change(lambda session, agent: todos_.add(session, agent, text))


@deck_todo.command(name="done")
@click.argument("n", type=click.IntRange(min=1))
@emit
def deck_todo_done(n: int) -> Result:
    """Mark item N of this tab's list done.

        sb deck todo done 1

    **This acts.** The item stays, dimmed and ticked, so the operator sees what moved.
    """
    return _todo_change(lambda session, agent: todos_.done(session, agent, n))


@deck_todo.command(name="rm")
@click.argument("n", type=click.IntRange(min=1))
@emit
def deck_todo_rm(n: int) -> Result:
    """Remove item N from this tab's list.

        sb deck todo rm 2

    **This acts.** Later items renumber.
    """
    return _todo_change(lambda session, agent: todos_.remove(session, agent, n))


@deck_todo.command(name="clear")
@emit
def deck_todo_clear() -> Result:
    """Remove every done item from every agent's list in the deck.

        sb deck todo clear

    **This acts**, on all the deck's lists, from anywhere: it is the operator's
    tidy-up, bound to M-x in the deck with `decide clear`. Open items stay; a list
    with nothing done is untouched.
    """
    return _book_clear(todos_.TODOS, "done item")


def _book_clear(book: str, noun: str) -> Result:
    result = Result()
    config, problems = load()
    for problem in problems:
        result.warn(problem)
    cleared, unreadable = todos_.clear_done(config.session, book)
    for problem in unreadable:
        result.warn(problem)
    result.data = [{"agent": agent, "cleared": n} for agent, n in cleared.items()]
    if not cleared:
        result.warn(f"nothing to clear — no {book} list in deck {config.session!r} has a {noun}")
    return result


@deck_todo.command(name="list")
@click.option("--all", "every", is_flag=True, help="Every agent's list, even from inside a tab.")
@click.option(
    "--refresh",
    type=click.IntRange(min=1),
    default=None,
    metavar="SECONDS",
    help="Stay resident and re-read every N seconds. Off a terminal, one NDJSON envelope per tick.",
)
@click.option(
    "--ticks",
    type=click.IntRange(min=1),
    default=None,
    metavar="N",
    help="With --refresh: stop after N refreshes and exit 0.",
)
@click.option(
    "--screen",
    is_flag=True,
    help="With --refresh: redraw on the alternate screen, as the deck's own panes do.",
)
@emit
def deck_todo_list(every: bool, refresh: int | None, ticks: int | None, screen: bool) -> Result:
    """The todo lists, grouped by agent in tab order, primary first.

        sb deck todo list
        sb deck todo list --all

    An observe. Inside a tab, that tab's list; elsewhere, or with `--all`, every
    agent's. Each heading says when its list last changed; an agent that never
    wrote one reads `no list kept`, and one with nothing left reads `nothing open`.
    """
    return _book_list(todos_.TODOS, "deck todo", every, refresh, ticks, screen)


def _book_list(book: str, source: str, every: bool, refresh: int | None, ticks: int | None, screen: bool) -> Result:
    """`todo list` and `decide list`: one book's lists, this tab's alone from inside one."""
    config, _ = load()
    mine = None if every else caller_tab(config.session)

    def once() -> Result:
        order = tab_order(config.session)
        if mine is not None:
            order = [pair for pair in order if pair[0] == mine] or [(mine, 0)]
        return todos_.result_of(config.session, order, paint=bool(refresh and screen), only=mine, book=book)

    pane = DeckPane(config.session, lambda row: True, scroll=True, top=True, role=book)
    return _resident(source, once, refresh, ticks, screen, keep_from_top("row(s)", pane), pane)


LIST_OPTIONS = (
    click.option("--all", "every", is_flag=True, help="Every agent's list, even from inside a tab."),
    click.option(
        "--refresh",
        type=click.IntRange(min=1),
        default=None,
        metavar="SECONDS",
        help="Stay resident and re-read every N seconds. Off a terminal, one NDJSON envelope per tick.",
    ),
    click.option(
        "--ticks",
        type=click.IntRange(min=1),
        default=None,
        metavar="N",
        help="With --refresh: stop after N refreshes and exit 0.",
    ),
    click.option(
        "--screen",
        is_flag=True,
        help="With --refresh: redraw on the alternate screen, as the deck's own panes do.",
    ),
)


def _list_options(command: Callable) -> Callable:
    for option in reversed(LIST_OPTIONS):
        command = option(command)
    return command


@deck.group(name="decide")
def deck_decide() -> None:
    """Each deck agent's open decisions for the operator, drawn in the DECISIONS pane.

        sb deck decide add "take the template's ci.yml step, or hold ours?" \\
            --option "take it" --option "hold ours"
        sb deck decide done 1 "take it"
        sb deck decide list

    Record one wherever you would otherwise write a question for the operator
    into a report. `add`, `done` and `rm` act, on the list of the tab they run
    in, and refuse anywhere else. `list` observes. Nothing is inferred: a
    decision exists because an agent recorded it. The operator rules by clicking
    one in the pane, which opens `rule`, and the marks loop types the ruling into
    the agent's tab once it is idle.
    """


@deck_decide.command(name="add")
@click.argument("question")
@click.option("--option", "options", multiple=True, metavar="CHOICE", help="A choice to offer. Give one per choice.")
@emit
def deck_decide_add(question: str, options: tuple[str, ...]) -> Result:
    """Record QUESTION as open, on this tab's list, with the choices to offer.

        sb deck decide add "take the template's ci.yml step, or hold ours?" \\
            --option "take it" --option "hold ours"

    **This acts**, on the list of the tab it runs in, and refuses anywhere else.
    With no `--option` the operator types the ruling.
    """
    if not todos_.clean(question):
        raise click.UsageError("a decision needs a question")
    if not all(todos_.clean(option) for option in options):
        raise click.UsageError("an --option needs words")
    if len(options) > len(RULING_KEYS):
        raise click.UsageError(f"a decision offers at most {len(RULING_KEYS)} choices")
    return _todo_change(lambda session, agent: todos_.add(session, agent, question, todos_.DECISIONS, options))


#: The keys that pick a choice; `t` types a ruling instead and `q` closes without one.
RULING_KEYS = "123456789"


def ruling_screen(agent: str, n: int, item: todos_.Item, width: int) -> list[tuple[str, str]]:
    """The popup's lines, each with the key a click on it stands for, empty for none. Pure."""
    room = max(10, width - 6)
    lines: list[tuple[str, str]] = [(f"{agent} asks ({n}):", ""), ("", "")]
    lines += [(line, "") for line in textwrap.wrap(item.text, room)]
    lines.append(("", ""))
    if item.done:
        lines += [(line, "") for line in textwrap.wrap(f"ruled: {item.ruling or 'closed'}", room)]
        return [*lines, ("", ""), ("[q] close", "q")]
    for key, option in zip(RULING_KEYS, item.options):
        wrapped = textwrap.wrap(option, room) or [""]
        lines += [(f"[{key}] {wrapped[0]}", key), *((f"    {more}", key) for more in wrapped[1:])]
    return [*lines, ("[t] type a ruling", "t"), ("[q] close without ruling", "q")]


def chosen_key(key: str | None, lines: list[tuple[str, str]]) -> str:
    """The action a keypress or a click stands for, empty if it stands for none."""
    cell = keys_.clicked(key)
    if cell is not None:
        return lines[cell[1] - 1][1] if 1 <= cell[1] <= len(lines) else ""
    offered = {action for _, action in lines if action}
    if keys_.leaves(key):
        return "q"
    return key if key in offered else ""


def _ask_ruling(agent: str, n: int, item: todos_.Item) -> str:
    """The operator's ruling from the popup, empty if they closed it without one."""
    lines = ruling_screen(agent, n, item, shutil.get_terminal_size().columns)
    sys.stdout.write(resident_.MOUSE_ON + "\x1b[2J\x1b[H" + "\r\n".join(line for line, _ in lines))
    sys.stdout.flush()
    action = ""
    try:
        with keys_.reader() as wait_for:
            while not action:
                action = chosen_key(wait_for(60.0), lines)
    finally:
        sys.stdout.write(resident_.MOUSE_OFF)
        sys.stdout.flush()
    if action == "t":
        return todos_.clean(click.prompt("\nruling", default="", show_default=False))
    return item.options[RULING_KEYS.index(action)] if action in RULING_KEYS else ""


@deck_decide.command(name="rule")
@click.argument("agent")
@click.argument("n", type=click.IntRange(min=1))
def deck_decide_rule(agent: str, n: int) -> None:
    """Rule on AGENT's decision N: what a click in the DECISIONS pane opens.

        sb deck decide rule skeletor 2

    **This acts**, and only for the operator: it needs a terminal, and refuses
    inside a tab, as an agent does not rule. Offers the decision's choices, or a
    typed ruling. The agent is told in its tab once it is idle.
    """
    config, problems = load()
    warn_now(problems)
    if not has_terminal():
        raise click.ClickException("a ruling is the operator's, and there is no terminal here to ask on")
    if caller_tab(config.session) is not None:
        raise click.ClickException("a ruling is the operator's, so this refuses inside a deck tab")
    todo = todos_.load(config.session, agent, todos_.DECISIONS)
    if todo is None or not 1 <= n <= len(todo.items):
        raise click.ClickException(f"{agent} has no decision {n}")
    ruling = _ask_ruling(agent, n, todo.items[n - 1])
    if ruling:
        todos_.rule(config.session, agent, n, ruling)


@deck_decide.command(name="done")
@click.argument("n", type=click.IntRange(min=1))
@click.argument("ruling", required=False, default="")
@emit
def deck_decide_done(n: int, ruling: str) -> Result:
    """Close decision N with the operator's RULING.

        sb deck decide done 1 "take it"

    **This acts.** The decision stays, ticked, with its ruling beside it.
    """
    return _todo_change(lambda session, agent: todos_.done(session, agent, n, book=todos_.DECISIONS, ruling=ruling))


@deck_decide.command(name="rm")
@click.argument("n", type=click.IntRange(min=1))
@emit
def deck_decide_rm(n: int) -> Result:
    """Remove decision N, one recorded by mistake. Later ones renumber.

        sb deck decide rm 2

    **This acts.**
    """
    return _todo_change(lambda session, agent: todos_.remove(session, agent, n, book=todos_.DECISIONS))


@deck_decide.command(name="clear")
@emit
def deck_decide_clear() -> Result:
    """Remove every decided item from every agent's decisions in the deck.

        sb deck decide clear

    **This acts**, on all the deck's decision lists, from anywhere. Open questions
    stay. M-x in the deck runs this with `todo clear`.
    """
    return _book_clear(todos_.DECISIONS, "decided item")


@deck_decide.command(name="list")
@_list_options
@emit
def deck_decide_list(every: bool, refresh: int | None, ticks: int | None, screen: bool) -> Result:
    """The open decisions, grouped by agent, the most recently changed list first.

        sb deck decide list --all

    An observe. Inside a tab, that tab's list; elsewhere, or with `--all`, every
    agent that has recorded one. When none has, it says so in a row.
    """
    return _book_list(todos_.DECISIONS, "deck decide", every, refresh, ticks, screen)


# **The act/observe bit, asserted on every subcommand** — a nested command that
# never chose inherits observe, and an observe may be given a cadence. See
# [[jobs]] round 1; `tests/test_deck.py` fails on a subcommand that did not choose.
mark(deck, sb_acts=True)
mark(deck_open, sb_acts=True)
mark(deck_jump, sb_acts=True)
mark(deck_layout, sb_acts=True)
mark(deck_marks, sb_acts=True)
mark(deck_exit, sb_acts=True)
mark(deck_decide_rule, sb_acts=True)
mark(deck_save, sb_acts=True)
mark(deck_scroll, sb_acts=True)
mark(deck_queue, sb_acts=False)
mark(deck_messages, sb_acts=False)
mark(deck_message, sb_acts=False)
mark(deck_brief, sb_acts=False)
mark(deck_todo, sb_acts=True)
mark(deck_todo_add, sb_acts=True)
mark(deck_todo_done, sb_acts=True)
mark(deck_todo_rm, sb_acts=True)
mark(deck_todo_clear, sb_acts=True)
mark(deck_reload, sb_acts=True)
mark(deck_column, sb_acts=True)
mark(deck_column_show, sb_acts=False)
mark(deck_column_fold, sb_acts=True)
mark(deck_column_pick, sb_acts=True)
mark(deck_decide, sb_acts=True)
mark(deck_decide_add, sb_acts=True)
mark(deck_decide_done, sb_acts=True)
mark(deck_decide_rm, sb_acts=True)
mark(deck_decide_clear, sb_acts=True)
mark(deck_decide_list, sb_acts=False)
mark(deck_todo_list, sb_acts=False)
