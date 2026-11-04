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

import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import rich_click as click

from skyboss import agents as agents_
from skyboss.chrome import ago
from skyboss.helpers import PROJECT_ROOT, SB_HOME, child_env, mark
from skyboss.messages import messages_result
from skyboss.output import Result, emit, warn_now
from skyboss.view import describe

DECK_FILE = "deck.toml"
DEFAULT_SESSION = "sb"
TOP_LEVEL_KEYS = frozenset({"session", "pin"})
TOP_LEVEL_TABLES = frozenset({"agent"})
AGENT_KEYS = frozenset({"cwd", "args"})

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

# Pane roles. `agent` runs claude; `tabs` is the nested client showing the inner
# session; `shell` is the inner session's first window, so it is never empty.
AGENT, TABS, QUEUE, MESSAGES, SHELL = "agent", "tabs", "queue", "messages", "shell"

# The inner session holding one window per project agent. Its status bar is the tab row.
INNER_SUFFIX = "-agents"

# The controller's two shapes, and its sizes. Constants until somebody needs to declare them.
COLUMNS, STACK = "columns", "stack"
LAYOUTS = (COLUMNS, STACK)
WORKSPACE_WIDTH = "45%"
TOOLS_WIDTH = "25%"
HALF = "50%"
QUEUE_REFRESH = 5
MESSAGES_REFRESH = 10

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

    @property
    def argv(self) -> list[str]:
        return ["claude", *self.args]

    @property
    def directory(self) -> str:
        return os.path.expandvars(os.path.expanduser(self.cwd))


@dataclass
class Config:
    session: str = DEFAULT_SESSION
    pin: str = ""
    agents: dict[str, Agent] = field(default_factory=dict)


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
        config.agents[name] = Agent(name=name, cwd=body["cwd"], args=list(body.get("args", [])))
    return config, problems


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
    return None


def load(home: Path | None = None) -> tuple[Config, list[str]]:
    return parse(read(home))


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


def dress(window_id: str) -> list[str]:
    """The deck's two window options, on one of its windows. Problems, never raises."""
    problems = []
    for option, value in (("window-size", "latest"), ("allow-passthrough", "on")):
        answer = tmux("set-option", "-w", "-t", window_id, option, value)
        if not answer.ok:
            problems.append(f"could not set {option} on the deck window — {_said(answer)}")
    return problems


def _ids(answer: Answer) -> tuple[str, str]:
    parts = answer.out.split()
    if not answer.ok or len(parts) != 2:
        raise DeckError(f"tmux did not open the window — {_said(answer)}")
    return parts[0], parts[1]


def inner(session: str) -> str:
    """The session holding the project agents, one window each."""
    return f"{session}{INNER_SUFFIX}"


def start(session: str, agent: Agent, *, new_session: bool = False) -> tuple[str, list[str]]:
    """A window running `claude` in the agent's directory. Its window id, and problems."""
    directory = agent.directory
    if not Path(directory).is_dir():
        raise DeckError(f"{agent.name}: cwd {directory} is not a directory ({agent.source})")
    if shutil.which("claude", path=child_env().get("PATH")) is None:
        raise DeckError("claude is not on PATH")
    where = ["new-session", "-d", "-s", session] if new_session else ["new-window", "-d", "-t", f"={session}:"]
    answer = tmux(*where, "-P", "-F", "#{window_id} #{pane_id}", "-n", agent.name, "-c", directory, "--", *agent.argv)
    window_id, pane_id = _ids(answer)
    tmux("set-option", "-w", "-t", window_id, AGENT_OPTION, agent.name)
    tmux("set-option", "-p", "-t", pane_id, ROLE_OPTION, AGENT)
    return window_id, dress(window_id)


def sb_argv(*words: str) -> list[str]:
    """This sky.boss, by absolute path: a pane must not find another `sb` on PATH."""
    return [str(PROJECT_ROOT / "sb"), *words]


def queue_argv() -> list[str]:
    return sb_argv("deck", "queue", "--refresh", str(QUEUE_REFRESH), "--screen")


def messages_argv() -> list[str]:
    return sb_argv("deck", "messages", "--refresh", str(MESSAGES_REFRESH), "--screen")


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


def ensure_inner(session: str) -> tuple[bool, list[str]]:
    """Create the inner session if it is absent: a shell window, a tab row on top, the mouse on."""
    name = inner(session)
    present = has_session(name)
    if present is None:
        raise DeckError("tmux could not be run — is it installed?")
    if present:
        return False, []
    answer = tmux(
        "new-session", "-d", "-s", name, "-P", "-F", "#{window_id} #{pane_id}", "-n", SHELL, "-c", str(Path.home())
    )
    window_id, pane_id = _ids(answer)
    tmux("set-option", "-p", "-t", pane_id, ROLE_OPTION, SHELL)
    options = (("mouse", "on"), ("status", "on"), ("status-position", "top"))
    return True, dress(window_id) + _session_options(name, options)


def ensure(config: Config, projects: list) -> tuple[bool, list[str]]:
    """Create the deck if it is absent, or put back a controller pane that has gone.

    Window 0 is the controller: the pinned agent, the inner session's tab pane,
    the queue and the messages. Whether the outer session was created, and problems.
    """
    present = has_session(config.session)
    if present is None:
        raise DeckError("tmux could not be run — is it installed?")
    _, problems = ensure_inner(config.session)
    if present:
        _, more = arrange(config.session, layout_of(config.session), force=False)
        return False, problems + more

    socket = socket_path(inner(config.session))
    window_id = ""
    if config.pin:
        pinned, why = resolve(config.pin, config, projects)
        if pinned is not None:
            try:
                window_id, more = start(config.session, pinned, new_session=True)
                problems += more
            except DeckError as exc:
                why = str(exc)
        if not window_id:
            problems.append(f"pin {config.pin!r}: {why} — the deck opened without it")
    if not window_id:
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
    problems += _session_options(config.session, (("mouse", "on"),))
    _, more = arrange(config.session, COLUMNS, force=True, socket=socket)
    return True, problems + more


def layout_of(session: str) -> str:
    answer = tmux("show-options", "-v", "-t", scope(session), LAYOUT_OPTION)
    shape = answer.out.strip() if answer.ok else ""
    return shape if shape in LAYOUTS else COLUMNS


def controller(listed: list[Pane]) -> str | None:
    """The window holding the deck's tool panes, else the lowest-numbered window."""
    for pane in listed:
        if pane.role in (TABS, QUEUE, MESSAGES):
            return pane.window_id
    ordered = sorted(listed, key=lambda p: p.window_index)
    return ordered[0].window_id if ordered else None


def plan(
    shape: str, workspace: str | None, tabs: str | None, queue: str | None, messages: str | None
) -> list[list[str]]:
    """The tmux calls that put four panes in `shape`. Pure, and only ever moves or resizes.

    columns: workspace | tabs | queue over messages.  stack: workspace over tabs | queue over messages.
    """
    left = [p for p in (workspace, tabs) if p]
    right = [p for p in (queue, messages) if p]
    anchor = (left or right or [None])[0]
    calls: list[list[str]] = []

    def join(source: str, target: str, flag: str) -> None:
        calls.append(["join-pane", "-d", flag, "-s", source, "-t", target])

    def resize(pane: str, axis: str, size: str) -> None:
        calls.append(["resize-pane", "-t", pane, axis, size])

    if anchor is None:
        return calls
    if shape == COLUMNS and len(left) == 2:
        join(left[1], left[0], "-h")
    if right and right[0] != anchor:
        join(right[0], left[-1] if shape == COLUMNS else left[0], "-h")
    if len(right) == 2:
        join(right[1], right[0], "-v")
    if shape == STACK and len(left) == 2:
        join(left[1], left[0], "-v")

    if shape == COLUMNS and len(left) == 2:
        resize(left[0], "-x", WORKSPACE_WIDTH)
    if shape == STACK and len(left) == 2:
        resize(left[0], "-y", HALF)
    if left and right:
        resize(right[0], "-x", TOOLS_WIDTH)
    if len(right) == 2:
        resize(right[0], "-y", HALF)
    return calls


def arrange(session: str, shape: str, *, force: bool, socket: str | None = None) -> tuple[list[str], list[str]]:
    """Put back any missing tool pane, then lay the controller out — by moving panes only.

    Nothing here restarts a pane, so every `claude` keeps its process. With
    `force` off, the shape is redrawn only when a pane had to be put back, so an
    operator's own resizing survives a bare `sb deck`. The roles created, and problems.
    """
    listed, answer = panes(session)
    if not answer.ok:
        return [], [f"could not list the deck's panes — {_said(answer)}"]
    window_id = controller(listed)
    if window_id is None:
        return [], [f"deck {session!r} has no window to arrange"]
    here = [p for p in listed if p.window_id == window_id]
    roles: dict[str, str] = {}
    for pane in here:
        roles.setdefault(pane.role, pane.pane_id)

    created: list[str] = []
    problems: list[str] = []
    wanted = {
        TABS: lambda: tabs_argv(session, socket if socket is not None else socket_path(session)),
        QUEUE: queue_argv,
        MESSAGES: messages_argv,
    }
    for role, argv in wanted.items():
        if role in roles:
            continue
        made = tmux("split-window", "-d", "-t", window_id, "-P", "-F", "#{pane_id}", "--", *argv())
        pane_id = made.out.strip()
        if not made.ok or not pane_id:
            problems.append(f"could not open the {role} pane — {_said(made)}")
            continue
        tmux("set-option", "-p", "-t", pane_id, ROLE_OPTION, role)
        roles[role] = pane_id
        created.append(role)

    if not (force or created):
        return created, problems
    for call in plan(shape, roles.get(AGENT), roles.get(TABS), roles.get(QUEUE), roles.get(MESSAGES)):
        moved = tmux(*call)
        if not moved.ok:
            problems.append(f"could not arrange the deck ({call[0]}) — {_said(moved)}")
            break
    problems += _session_options(session, ((LAYOUT_OPTION, shape),))
    return created, problems


def all_panes(session: str) -> list[Pane]:
    """The controller's panes, then the inner session's: every window the deck may hold an agent in."""
    listed, _ = panes(session)
    if has_session(inner(session)):
        more, _ = panes(inner(session))
        listed = listed + more
    return listed


def locate(name: str, session: str) -> tuple[str, str | None]:
    """Where `name`'s window is: `inner`, `outer`, or nowhere. A tab first, then the pinned agent."""
    if has_session(inner(session)):
        tabs, _ = panes(inner(session))
        window_id = find_window(name, tabs)
        if window_id is not None:
            return "inner", window_id
    outer, _ = panes(session)
    for pane in outer:
        if pane.agent == name:
            return "outer", pane.window_id
    return "", None


def focus(session: str, where: str, window_id: str) -> None:
    """Bring `window_id` forward: a tab in the inner session, with the controller in front of the outer."""
    select(window_id)
    if where == "inner":
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
@click.pass_context
def deck(ctx: click.Context) -> None:
    """Create the deck if it is absent, then attach to it.

        sb deck
        sb deck open jam-sense
        sb deck layout stack

    **This acts.** Window 0 is the controller: the pinned `claude`, a tab row of
    project agents (an inner session, `<session>-agents`), and the queue over
    the messages. Declared in `$SB_HOME/deck.toml`, which sky.boss reads and
    never writes. Inside tmux it switches this client; outside, it becomes
    `tmux attach`, so it emits no envelope.
    """
    if ctx.invoked_subcommand is not None:
        return
    if _as_json():
        raise click.UsageError("deck attaches a terminal and emits no envelope — --json has no meaning here")
    config, problems = load()
    try:
        _, more = ensure(config, _projects())
    except DeckError as exc:
        raise click.ClickException(str(exc)) from exc
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
@emit
def deck_open(name: str) -> Result:
    """A tab running `claude` for NAME, or that tab if it is open.

        sb deck open jam-sense

    **This acts.** NAME is an `[agent.NAME]` in `deck.toml`, or a project in
    `projects.toml` that declares a `cwd`. The tab is a window of the inner
    session, `<session>-agents`, drawn in the controller's middle pane. Creates
    the deck first if needed; the pinned agent is selected rather than doubled.
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
        where, window_id = locate(name, config.session)
        opened = window_id is None
        if window_id is None:
            where = "inner"
            window_id, dressed = start(inner(config.session), agent)
            more += dressed
        focus(config.session, where, window_id)
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
        "session": config.session if where == "outer" else inner(config.session),
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
    where, window_id = locate(name, config.session)
    if window_id is None:
        names = sorted({p.agent for p in all_panes(config.session) if p.agent})
        raise click.UsageError(f"no agent {name!r} in deck {config.session!r} (agents: {', '.join(names) or 'none'})")
    try:
        focus(config.session, where, window_id)
        attached = switch(config.session)
    except DeckError as exc:
        result.ok = False
        result.data = {"error": str(exc)}
        return result
    session = config.session if where == "outer" else inner(config.session)
    result.data = {"session": session, "window": name, "attached": attached}
    return result


@deck.command(name="layout")
@click.argument("shape", type=click.Choice(LAYOUTS))
@emit
def deck_layout(shape: str) -> Result:
    """Lay the controller window out as `columns` or `stack`.

        sb deck layout stack

    **This acts**, on panes and never on what runs in them: it moves and resizes
    panes, so every `claude` keeps its process. A tool pane that has gone is put
    back first. columns: workspace | tabs | queue over messages. stack: workspace
    over tabs | queue over messages.
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
    for problem in more + arranged:
        result.warn(problem)
    if arranged:
        result.partial = True
    result.data = {"session": config.session, "layout": shape, "created": ", ".join(created)}
    return result


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
    return _resident("deck messages", messages_result, refresh, ticks, screen)


def _resident(source: str, once: Callable[[], Result], refresh: int | None, ticks: int | None, screen: bool) -> Result:
    """One read, or the same read on a cadence — `sb data`'s resident path, shared.

    The deck's panes take `--screen`: a pane the operator drags to a new size
    must redraw whole, not leave the old inline frames above the new one.
    """
    if ticks is not None and refresh is None:
        raise click.UsageError("--ticks needs --refresh — a single read already stops after one")
    if refresh is not None:
        from skyboss import output, resident

        if _as_json() or not output.stdout_is_terminal():
            output.resident_ndjson(once, refresh, runs=ticks)
        else:
            resident.reside(source, refresh, once, screen=screen, runs=ticks)
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


def _row(where: str, window: str, status: str, session, pid: int, now: datetime) -> dict:
    started = session.started if session else None
    return {
        "where": where,
        "window": window,
        "status": status,
        "name": session.name if session else "",
        "up": ago((now - started).total_seconds()) if started else "",
        "cwd": session.cwd if session else "",
        "pid": pid,
        "id": session.id if session else "",
        "started": started.isoformat() if started else "",
    }


def _waiting_first(rows: list[dict]) -> list[dict]:
    """The provider's word, compared literally: sky.boss orders and does not judge."""
    return sorted(rows, key=lambda row: row["status"] != WAITING)


def queue_rows(listed: list[Pane], sessions: list, parent_of: dict[int, int], now: datetime) -> list[dict]:
    """One row per deck window, waiting first; then every live session outside the deck.

    A window the deck started whose process has no registry record is drawn as
    `unregistered` — Claude Code's trust dialog writes none — rather than left out.
    """
    by_pid = {s.pid: s for s in sessions if s.pid}
    claimed: set[str] = set()
    windows: dict[str, list[Pane]] = {}
    for pane in sorted(listed, key=lambda p: p.window_index):
        windows.setdefault(pane.window_id, []).append(pane)

    inside: list[dict] = []
    for group in windows.values():
        label = group[0].agent or group[0].window
        found = False
        for pane in group:
            for pid in tree(pane.pid, parent_of):
                session = by_pid.get(pid)
                if session is not None and session.id not in claimed:
                    claimed.add(session.id)
                    found = True
                    inside.append(_row("deck", label, session.status, session, session.pid, now))
        agent = next((p for p in group if p.role == "agent"), None)
        if not found and agent is not None:
            inside.append(_row("deck", label, UNREGISTERED, None, agent.pid, now))

    outside = [_row("outside", "", s.status, s, s.pid, now) for s in sessions if s.id not in claimed]
    return _waiting_first(inside) + _waiting_first(outside)


INLINE = ("where", "window", "status", "name", "up", "cwd")
HIDDEN = ("pid", "id", "started")


def view_of(rows: list[dict]) -> dict:
    """Authored: these keys are sky.boss's own, so there is an order to state and nothing to infer.

    `status` and `window` are floored at their own width: the queue exists to show
    those two words, and `unregister…` would be a different word.
    """
    columns = [describe(key, rows) for key in INLINE]
    for column in columns:
        if column["key"] in ("status", "window"):
            column["min"] = column["max"]
    return {
        "columns": columns,
        "details": [],
        "hidden": list(HIDDEN),
        "authored": True,
    }


def queue_result(adapters: list | None = None, proc: Path = Path("/proc")) -> Result:
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

    result.data = queue_rows(listed, sessions, parents(proc), datetime.now(timezone.utc))
    if not result.data:
        result.warn(agents_.empty_reason(tally, len(chosen)))
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
@emit
def deck_queue(refresh: int | None, ticks: int | None, screen: bool) -> Result:
    """Which agent sessions are waiting on you, deck windows first.

        sb deck queue
        sb deck queue --refresh 5

    An observe — a window may pin it. One row per deck window with its `claude`
    pid and the registry's `status` word, `waiting` first; a window with no
    record reads `unregistered`. Live sessions outside the deck follow.
    """
    return _resident("deck queue", queue_result, refresh, ticks, screen)


# **The act/observe bit, asserted on every subcommand** — a nested command that
# never chose inherits observe, and an observe may be given a cadence. See
# [[jobs]] round 1; `tests/test_deck.py` fails on a subcommand that did not choose.
mark(deck, sb_acts=True)
mark(deck_open, sb_acts=True)
mark(deck_jump, sb_acts=True)
mark(deck_layout, sb_acts=True)
mark(deck_queue, sb_acts=False)
mark(deck_messages, sb_acts=False)
