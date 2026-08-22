"""The toolbox — commands the operator saved.

A tool is a **name plus a tb argv**. `tb jam-pr-list` expands to
`tb data --cwd … -- jam pr list --json` and runs it. That is the whole model,
and everything below is the consequences of keeping it that small.

**Tools are registered into the Click tree, not held in a list.** tb's hardest
invariant is that nothing keeps a command table — the palette walks the live
tree, so it cannot offer a command that does not exist. A toolbox that was a
second list of commands would break that on day one. Registering them instead
means `tb tools <name>`, `tb --help`, the palette, and shell completion all
work with no code anywhere else.

**Saved commands live behind the `tools` group** (round 2 — they were on the
root until 2026-08-22). The builtin/operator line is the sharpest line in the
design, and on the root it was invisible in the one listing that matters most.
Nesting also retired the shadowing rule into structure: `tb tools run`
collides with nothing, so "a builtin always wins" stopped being validation.
`-t` is an argv spelling of `tools`, rewritten at the root — see cli/__init__.

**The argv is a tb argv, never a shell argv.** A tool cannot name an arbitrary
executable, because a tool that could would be a second `tb run` — one that
skips the read/write distinction the design rests on. Everything a tool wants is
reachable through `run` or `data`, and going through them is what keeps `tb run`
the single command that acts.

**Nothing here writes.** Creation is `$EDITOR`. The canvas server is remote code
execution bound to a port; a route that wrote a file tb will later *execute*
would convert a transient compromise into a persistent one. See [[tools]].
"""

from __future__ import annotations

import re
import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path

import rich_click as click

from cli.canvas.catalog import walk
from cli.canvas.watch import INTERVALS
from cli.helpers import TB_HOME
from cli.output import Result, emit

TOOLS_FILE = "tools.toml"

# The shape of a name that can be a Click command and a shell word at once. No
# leading dash (it would parse as an option), no dots or slashes, no spaces.
_NAME = re.compile(r"\A[a-z0-9][a-z0-9-]*\Z")

# Old spellings, kept only to say what the new one is. Hard renames carry no
# aliases — one operator, one tools.toml — so the whole cost of a rename is
# one loud message here rather than a second name to test forever.
RENAMED = {"wrap": "data"}


@dataclass(frozen=True)
class Tool:
    """One saved command, already validated."""

    name: str
    argv: list[str]
    description: str = ""
    refresh: int = 0
    acts: bool = False
    resident: bool = False


def home_file(home: Path | None = None) -> Path:
    return (home or TB_HOME) / TOOLS_FILE


def read(home: Path | None = None) -> dict:
    """The raw TOML, or an empty mapping.

    An absent home is not a problem to report. A fresh clone has no tools and
    saying so on every invocation would be noise, so this degrades to nothing
    declared rather than raising or warning.
    """
    path = home_file(home)
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        # A file that exists and cannot be parsed *is* worth reporting — the
        # operator wrote it and is expecting it to work. Reported as a problem
        # rather than raised, because one broken file must not stop tb running.
        return {"__error__": f"{path}: {exc}"}


def parse(
    raw: dict,
    commands: dict[str, bool],
    resident: frozenset[str] = frozenset(),
) -> tuple[list[Tool], list[str]]:
    """Validate declarations against the live tree. Pure — reads no file.

    `commands` maps a runnable tb command to whether it acts. There is no
    shadowing check any more: round 2 moved saved commands behind the `tools`
    group, where `[tool.run]` collides with nothing — the rule became
    structure. Only the *shape* of a name is still validated.

    Returns the tools that survived and a problem for each that did not. **One
    bad entry must not cost the operator the other nine**, so nothing here
    raises: a malformed tool is skipped and named.
    """
    problems: list[str] = []
    if "__error__" in raw:
        return [], [raw["__error__"]]

    tools: list[Tool] = []
    seen: set[str] = set()

    for name, body in (raw.get("tool") or {}).items():
        problem = _check(name, body, commands, seen, resident)
        if problem:
            problems.append(f"tool {name!r}: {problem}")
            continue
        seen.add(name)
        argv = [_expand(part) for part in body["argv"]]
        tools.append(
            Tool(
                name=name,
                argv=argv,
                description=str(body.get("description", "")),
                refresh=int(body.get("refresh", 0)),
                acts=commands[argv[0]],
                resident=argv[0] in resident,
            )
        )

    return tools, problems


def _check(
    name: str,
    body,
    commands: dict[str, bool],
    seen: set[str],
    resident: frozenset[str] = frozenset(),
) -> str | None:
    """The reason this declaration is unusable, or None."""
    if not isinstance(body, dict):
        return "not a table"
    if not _NAME.match(name):
        return "name must be lowercase letters, digits and hyphens"
    if name in seen:
        return "declared twice"

    argv = body.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(p, str) for p in argv):
        return "argv must be a non-empty list of strings"
    if argv[0] in RENAMED:
        # The migration message. A hard rename with no alias means a saved tool
        # still saying the old word must fail *loudly by name* — and `tb tools`
        # listing what failed to load is exactly where the operator whose tool
        # vanished will look. See [[refresh]].
        return f"{argv[0]!r} was renamed {RENAMED[argv[0]]!r} — edit the tool's argv"
    if argv[0] not in commands:
        # Names the alternative rather than just refusing: the mistake this
        # catches is someone writing a shell command, and the fix is to say
        # which tb command would have run it.
        return (
            f"argv must start with a tb command, not {argv[0]!r} — "
            "put it behind `run` or `data`"
        )

    if "every" in body:
        # The field-side half of the same migration `RENAMED` handles for
        # commands: one word for one number, `refresh`, flag and field alike.
        return "'every' was renamed 'refresh' — edit the tool"

    refresh = body.get("refresh", 0)
    if not isinstance(refresh, int) or isinstance(refresh, bool):
        return "refresh must be an integer number of seconds"
    if refresh and argv[0] in resident:
        # A stream is not refreshed, it is open. Declaring a cadence on a
        # follow would load fine and mean nothing — the "wrong but looks
        # right" failure this loader exists to catch.
        return f"refresh is not allowed on a follow (`{argv[0]}` is resident by nature)"
    if refresh and commands[argv[0]]:
        # The same rule the canvas enforces by hiding the pin control: only a
        # read may be given a cadence, because re-running a read is a refresh
        # and re-running a write is a scheduler nobody asked for.
        return f"refresh is not allowed on a tool that acts (`{argv[0]}` writes)"
    if refresh not in INTERVALS:
        # Not pedantry: the surface cycles the interval through this list, and
        # a window starting on a value outside it would jump to 0 on the first
        # click rather than to the next cadence up.
        return f"refresh must be one of {', '.join(str(i) for i in INTERVALS)}"

    return None


def _expand(part: str) -> str:
    """`~` in an argv is expanded — the whole point is that these are the
    operator's own paths. Only a leading `~`, so a value that merely contains
    one is left alone."""
    return str(Path(part).expanduser()) if part.startswith("~") else part


def load(
    commands: dict[str, bool],
    home: Path | None = None,
    resident: frozenset[str] = frozenset(),
) -> tuple[list[Tool], list[str]]:
    """Every declared tool, and every reason one was skipped."""
    return parse(read(home), commands, resident)


# ============================================================================
# Registration
# ============================================================================

# Why a module global. Loading happens at import, before any Click context
# exists, so a problem found there has nowhere to be reported yet. Nothing
# prints at import — `tb tools` surfaces these, which is where someone whose
# tool did not appear will look.
PROBLEMS: list[str] = []


def _expansion(tool: Tool) -> str:
    return "tb " + shlex.join(tool.argv)


def make_command(tool: Tool) -> click.Command:
    """A Click command that re-dispatches into the tree.

    The sub-context is built with the *tool's* name as its `info_name` and the
    `tools` group's context as its parent, so the envelope comes back saying
    `tools.jam-pr-list` rather than `data`. Round 1 said the bare name, because
    `data` was an implementation detail the operator did not type; `tools.` is
    something they *do* type, and the dotted path is the standing convention.

    It takes no arguments, so `tb jam-pr-list 945` is a usage error rather than
    something appended to the argv. A tool that took arguments would be a shell
    function, and this is not a shell.
    """

    @click.command(name=tool.name, short_help=tool.description or _expansion(tool))
    @click.pass_context
    def command(ctx: click.Context, refresh: int | None = None) -> None:
        from cli import cli as root

        args = list(tool.argv[1:])
        if refresh is not None:
            # Bare `--refresh` (Click hands over the flag_value, 0) adopts the
            # tool's own field — the canvas default cadence, asked for
            # explicitly. A keyword in the terminal still runs once unless
            # the flag is given; residency is never ambient.
            interval = tool.refresh if refresh == 0 else refresh
            if interval <= 0:
                raise click.UsageError(
                    f"{tool.name} declares no refresh — give a value: --refresh 30"
                )
            args = ["--refresh", str(interval), *args]

        target = root.get_command(ctx, tool.argv[0])
        sub_ctx = target.make_context(tool.name, args, parent=ctx.parent)
        with sub_ctx:
            target.invoke(sub_ctx)

    # A property on the command, inherited from the expansion like `acts` —
    # the catalog reads it to withhold the cadence control from stream
    # windows, saved or typed alike.
    command.tb_resident = tool.resident

    if not tool.acts and not tool.resident:
        # Only a snapshot observe may take a cadence; on a tool that acts —
        # or one that is resident by nature — the option does not exist at
        # all, which keeps the split visible in `--help` as it is on `run`.
        command = click.option(
            "--refresh",
            is_flag=False,
            flag_value=0,
            default=None,
            type=click.IntRange(min=0),
            metavar="[SECONDS]",
            help="Stay resident, re-running every N seconds (bare: the tool's own refresh).",
        )(command)

    command.help = (
        f"{tool.description}\n\nA saved command. Runs:\n\n    {_expansion(tool)}"
        if tool.description
        else f"A saved command. Runs:\n\n    {_expansion(tool)}"
    )
    # A property on the command, so the catalog reads it the way it reads
    # `tb_surface` rather than by consulting a list of names.
    command.tb_saved = True
    command.tb_refresh = tool.refresh
    command.tb_argv = tuple(tool.argv)
    # Inherited, never declared. The catalog reads this rather than the command
    # path, because the path of `tb deploy-thing` says nothing about the `run`
    # hiding inside it.
    command.tb_acts = tool.acts
    return command


def register(root: click.Group, home: Path | None = None) -> list[str]:
    """Put every declared tool behind the `tools` group. Returns the problems.

    Registration targets the group rather than the root (round 2): the
    builtin/operator line is the sharpest line in the design, and nesting is
    what makes it visible in `tb --help`. It is also what retired the
    shadowing rule into structure — a saved `run` lives at `tb tools run` and
    collides with nothing.

    `commands` and `resident` are still read off the *root's* walk, because a
    tool's argv starts with a root-level tb command and inherits its verdicts.
    """
    entries = walk(root)
    commands = {entry["name"]: entry["acts"] for entry in entries}
    resident = frozenset(entry["name"] for entry in entries if entry.get("resident"))
    loaded, problems = load(commands, home, resident)
    for tool in loaded:
        tools.add_command(make_command(tool))
    return problems


@click.group(invoke_without_command=True)
@click.pass_context
def tools(ctx: click.Context) -> None:
    """The toolbox — the operator's saved commands, behind their own door.

    Bare, it lists what is declared. An observe — it runs nothing:

        tb tools

    It reports what is declared and, importantly, what was declared and
    refused — a tool that fails to load is otherwise invisible, and the
    operator who wrote it has no way to tell it apart from one they forgot to
    write.

    A saved command runs behind this group, spelled long or short:

        tb tools jam-pr-list --refresh 30
        tb -t jam-pr-list --refresh 30

    A tool's `refresh` field is a default, never a cadence in force — the
    canvas opens the tool's window at it and a bare `--refresh` adopts it, but
    in a terminal a saved command always runs once unless the flag is given.
    """
    if ctx.invoked_subcommand is None:
        _listing()


@emit
def _listing() -> Result:
    """The bare `tb tools` rendering — one door for "what did I declare".

    Formats ride in the same listing (see [[capture]]): this is already the
    one place the operator looks for "what did I declare, and what was
    refused", and a second listing command would split that. Their load
    problems land in the same degrade list a tool's do.
    """
    from cli import capture as capture_

    result = Result()
    declared = [
        {
            "name": name,
            "description": command.short_help or "",
            "runs": " ".join(("tb", *_argv_of(command))),
            "acts": getattr(command, "tb_acts", False),
            "refresh": getattr(command, "tb_refresh", 0),
        }
        for name, command in sorted(tools.commands.items())
        if getattr(command, "tb_saved", False)
    ]

    formats, format_problems = capture_.load_formats()
    result.data = {
        "tools": declared,
        "formats": [
            {"name": fmt.name, "kind": fmt.kind, "description": fmt.description}
            for fmt in sorted(formats, key=lambda f: f.name)
        ],
    }

    for problem in (*PROBLEMS, *format_problems):
        result.degrade(problem)

    return result


def _argv_of(command: click.Command) -> tuple[str, ...]:
    return getattr(command, "tb_argv", ())
