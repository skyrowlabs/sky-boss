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
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import rich_click as click

from skyboss import agents as agents_
from skyboss.chrome import ago
from skyboss.helpers import PROJECT_ROOT, SB_HOME, child_env, mark
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
AGENT_OPTION = "@sb-agent"
ROLE_OPTION = "@sb-deck"

# The queue pane's cadence and height. Constants until somebody needs to declare them.
QUEUE_REFRESH = 5
QUEUE_LINES = 10

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


def queue_argv() -> list[str]:
    """What the queue pane runs: this sky.boss, by absolute path, on a cadence."""
    return [str(PROJECT_ROOT / "sb"), "deck", "queue", "--refresh", str(QUEUE_REFRESH)]


def ensure(config: Config, projects: list) -> tuple[bool, list[str]]:
    """Create the deck session if it is absent. Whether it was created, and problems.

    Window 0 is the pinned agent with the queue in a pane below it, or the queue
    alone when nothing is pinned or the pin cannot be opened.
    """
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
                window_id, more = start(config.session, pinned, new_session=True)
                return True, more + _queue_pane(window_id)
            except DeckError as exc:
                why = str(exc)
        problems.append(f"pin {config.pin!r}: {why} — the deck opened with the queue alone")

    answer = tmux(
        "new-session",
        "-d",
        "-s",
        config.session,
        "-P",
        "-F",
        "#{window_id} #{pane_id}",
        "-n",
        "queue",
        "--",
        *queue_argv(),
    )
    window_id, pane_id = _ids(answer)
    tmux("set-option", "-p", "-t", pane_id, ROLE_OPTION, "queue")
    return True, problems + dress(window_id)


def _queue_pane(window_id: str) -> list[str]:
    """The queue, split below the pinned agent without taking focus."""
    answer = tmux(
        "split-window",
        "-d",
        "-v",
        "-l",
        str(QUEUE_LINES),
        "-t",
        window_id,
        "-P",
        "-F",
        "#{pane_id}",
        "--",
        *queue_argv(),
    )
    pane_id = answer.out.strip()
    if not answer.ok or not pane_id:
        return [f"could not open the queue pane — {_said(answer)}"]
    tmux("set-option", "-p", "-t", pane_id, ROLE_OPTION, "queue")
    return []


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


@deck.command(name="jump")
@click.argument("name")
@emit
def deck_jump(name: str) -> Result:
    """Select the deck window for NAME.

        sb deck jump jam-sense

    **This acts** — on the operator, not the agent: it moves which window is in
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
    listed, _ = panes(config.session)
    window_id = find_window(name, listed)
    if window_id is None:
        names = sorted({p.agent or p.window for p in listed})
        raise click.UsageError(f"no window {name!r} in deck {config.session!r} (windows: {', '.join(names) or 'none'})")
    try:
        select(window_id)
        attached = switch(config.session)
    except DeckError as exc:
        result.ok = False
        result.data = {"error": str(exc)}
        return result
    result.data = {"session": config.session, "window": name, "attached": attached}
    return result


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
@emit
def deck_queue(refresh: int | None, ticks: int | None) -> Result:
    """Which agent sessions are waiting on you, deck windows first.

        sb deck queue
        sb deck queue --refresh 5

    An observe — a window may pin it. One row per deck window with its `claude`
    pid and the registry's `status` word, `waiting` first; a window with no
    record reads `unregistered`. Live sessions outside the deck follow.
    """
    if ticks is not None and refresh is None:
        raise click.UsageError("--ticks needs --refresh — a single read already stops after one")
    if refresh is not None:
        from skyboss import output, resident

        if _as_json() or not output.stdout_is_terminal():
            output.resident_ndjson(queue_result, refresh, runs=ticks)
        else:
            resident.reside("deck queue", refresh, queue_result, runs=ticks)
        raise click.exceptions.Exit(0)
    return queue_result()


# **The act/observe bit, asserted on every subcommand** — a nested command that
# never chose inherits observe, and an observe may be given a cadence. See
# [[jobs]] round 1; `tests/test_deck.py` fails on a subcommand that did not choose.
mark(deck, sb_acts=True)
mark(deck_open, sb_acts=True)
mark(deck_jump, sb_acts=True)
mark(deck_queue, sb_acts=False)
