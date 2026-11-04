"""`sb deck` — a tmux session holding one window per agent. See [[command-deck]].

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
from pathlib import Path
from typing import Callable

import rich_click as click

from skyboss.helpers import SB_HOME, child_env, mark
from skyboss.output import Result, emit, warn_now

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
AGENT_OPTION = "@sb-agent"
ROLE_OPTION = "@sb-deck"


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
    tmux("set-option", "-p", "-t", pane_id, ROLE_OPTION, "agent")
    return window_id, dress(window_id)


def ensure(config: Config, projects: list) -> tuple[bool, list[str]]:
    """Create the deck session if it is absent. Whether it was created, and problems."""
    present = has_session(config.session)
    if present is None:
        raise DeckError("tmux could not be run — is it installed?")
    if present:
        return False, []

    problems: list[str] = []
    if config.pin:
        pinned, why = resolve(config.pin, config, projects)
        if pinned is not None:
            try:
                _, more = start(config.session, pinned, new_session=True)
                return True, more
            except DeckError as exc:
                why = str(exc)
        problems.append(f"pin {config.pin!r}: {why} — the deck opened without it")

    answer = tmux("new-session", "-d", "-s", config.session, "-P", "-F", "#{window_id} #{pane_id}", "-n", "deck")
    window_id, _ = _ids(answer)
    return True, problems + dress(window_id)


def select(window_id: str) -> None:
    answer = tmux("select-window", "-t", window_id)
    if not answer.ok:
        raise DeckError(f"could not select the window — {_said(answer)}")


def inside_tmux() -> bool:
    return bool(os.environ.get("TMUX"))


def has_terminal() -> bool:
    return sys.stdin.isatty()


def switch(session: str) -> bool:
    """Move this tmux client to the deck. False when not inside tmux."""
    if not inside_tmux():
        return False
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

    **This acts.** The deck is a tmux session with one window per agent, each
    the real `claude`. Declared in `$SB_HOME/deck.toml`, which sky.boss reads and
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
    """A window running `claude` for NAME, or that window if it is open.

        sb deck open jam-sense

    **This acts.** NAME is an `[agent.NAME]` in `deck.toml`, or a project in
    `projects.toml` that declares a `cwd`. Creates the deck first if needed.
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
        listed, _ = panes(config.session)
        window_id = find_window(name, listed)
        opened = window_id is None
        if window_id is None:
            window_id, dressed = start(config.session, agent)
            more += dressed
        select(window_id)
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
        "session": config.session,
        "window": name,
        "opened": opened,
        "created": created,
        "attached": attached,
        "cwd": agent.directory,
        "argv": shlex.join(agent.argv),
        "from": agent.source,
    }
    return result


# **The act/observe bit, asserted on every subcommand** — a nested command that
# never chose inherits observe, and an observe may be given a cadence. See
# [[jobs]] round 1; `tests/test_deck.py` fails on a subcommand that did not choose.
mark(deck, sb_acts=True)
mark(deck_open, sb_acts=True)
