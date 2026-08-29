"""The tools — commands the operator saved.

A tool is a **name plus a sky.boss argv**. `sb jam-pr-list` expands to
`sb data --cwd … -- jam pr list --json` and runs it. That is the whole model,
and everything below is the consequences of keeping it that small.

**Tools are registered into the Click tree, not held in a list.** sky.boss's hardest
invariant is that nothing keeps a command table — the palette walks the live
tree, so it cannot offer a command that does not exist. A tools list that was a
second list of commands would break that on day one. Registering them instead
means `sb tools <name>`, `sb --help`, the palette, and shell completion all
work with no code anywhere else.

**Saved commands live behind the `tools` group** (round 2 — they were on the
root until 2026-08-22). The builtin/operator line is the sharpest line in the
design, and on the root it was invisible in the one listing that matters most.
Nesting also retired the shadowing rule into structure: `sb tools run`
collides with nothing, so "a builtin always wins" stopped being validation.
`-t` is an argv spelling of `tools`, rewritten at the root — see cli/__init__.

**The argv is a sky.boss argv, never a shell argv.** A tool cannot name an arbitrary
executable, because a tool that could would be a second `sb run` — one that
skips the read/write distinction the design rests on. Everything a tool wants is
reachable through `run` or `data`, and going through them is what keeps `sb run`
the single command that acts.

**No *surface* writes this file, and sky.boss only ever appends to it.** Round 3
narrowed "nothing here writes" rather than reversing it: the argument under
that sentence was about the canvas server — remote code execution bound to a
port, where a *route* that wrote a file sky.boss later runs would turn a transient
compromise into a persistent one. None of that describes `--save`, typed by
the operator in their own shell at the same trust level as `$EDITOR`. So
there is still no route and still no button; there is `save()`, which
**appends one block and never touches a line the operator wrote**. Editing and
deleting stay `$EDITOR`'s. See [[tools]].
"""

from __future__ import annotations

import re
import shlex
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import rich_click as click

from cli.canvas.catalog import walk
from cli.canvas.watch import INTERVALS
from cli.helpers import INVOCATION, SB_HOME
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
    highlight: str = ""
    # A label the surfaces sort under, never part of the address: the
    # address `sb tools jam-pr-list` is unchanged and there is no group you
    # can invoke, so names stay globally unique — the word typed never
    # carries the group. Empty
    # means ungrouped, which is where a tool goes when it says nothing.
    # See [[tools]] round 5.
    group: str = ""


@dataclass(frozen=True)
class Group:
    """One declared group.

    A group is a **label the surfaces sort under**, never part of an address —
    `sb tools prs`, never `sb tools jam prs`, and names stay globally unique
    because the word typed never carries the group. See [[tools]] round 5.

    Round 6 lets one be *declared*, which is what gives an **empty** group
    somewhere to exist. The rule both halves live under:

        A group exists if any command names it, or if it is declared.
        Neither implies the other.

    So a `group = "jam"` with no `[group.jam]` is exactly as valid as it was
    before this table existed, and `[group.archive]` with nothing pointing at
    it is a group with no commands rather than a declaration nobody honoured.
    """

    name: str
    description: str = ""


def home_file(home: Path | None = None) -> Path:
    return (home or SB_HOME) / TOOLS_FILE


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
        # rather than raised, because one broken file must not stop sky.boss running.
        return {"__error__": f"{path}: {exc}"}


def parse(
    raw: dict,
    commands: dict[str, bool],
    resident: frozenset[str] = frozenset(),
) -> tuple[list[Tool], list[str]]:
    """Validate declarations against the live tree. Pure — reads no file.

    `commands` maps a runnable sky.boss command to whether it acts. There is no
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
                highlight=str(body.get("highlight", "")),
                group=str(body.get("group", "")),
            )
        )

    return tools, problems


def parse_groups(raw: dict) -> tuple[list[Group], list[str]]:
    """Declared groups, and a problem for each declaration that is unusable.

    A separate pure function rather than a third value out of `parse`, so
    nothing that already calls `parse` or `load` has to change. Same contract
    as `parse` otherwise: nothing raises, and one bad declaration costs only
    itself.
    """
    problems: list[str] = []
    if "__error__" in raw:
        return [], [raw["__error__"]]

    groups: list[Group] = []
    seen: set[str] = set()
    for name, body in (raw.get("group") or {}).items():
        problem = _check_group(name, body, seen)
        if problem:
            problems.append(f"group {name!r}: {problem}")
            continue
        seen.add(name)
        groups.append(Group(name=name, description=str(body.get("description", ""))))
    return groups, problems


def _check_group(name: str, body, seen: set[str]) -> str | None:
    if not isinstance(body, dict):
        return "not a table"
    if not _NAME.match(name):
        # The same shape a tool name takes, and for the reason round 5 gave:
        # a group is a key as well as a caption.
        return "name must be lowercase letters, digits and hyphens"
    if name in seen:
        return "declared twice"
    description = body.get("description", "")
    if not isinstance(description, str):
        return "description must be a string"
    return None


def sections(tools: list[Tool], groups: list[Group]) -> list[dict]:
    """Every group that exists, in the order the surfaces draw it.

    **The union and its order are computed here, not in the rail.** Round 5 had
    `app.js` hold the ordering rule; that was one copy too many the moment a
    group could also be declared, because the rail would then need to know
    about a file it never reads. Same argument [[table-views]] made for
    `cli/view.py`: the deciding half goes where pytest reaches it.

    Alphabetical, and the ungrouped are not in here at all — they are the
    bucket every surface draws last, and giving them an entry would make them a
    group that could be deleted.
    """
    declared = {group.name: group for group in groups}
    counts: dict[str, int] = {}
    for tool in tools:
        if tool.group:
            counts[tool.group] = counts.get(tool.group, 0) + 1

    return [
        {
            "name": name,
            "description": declared[name].description if name in declared else "",
            "declared": name in declared,
            "count": counts.get(name, 0),
        }
        for name in sorted(set(declared) | set(counts))
    ]


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
        # still saying the old word must fail *loudly by name* — and `sb tools`
        # listing what failed to load is exactly where the operator whose tool
        # vanished will look. See [[refresh]].
        return f"{argv[0]!r} was renamed {RENAMED[argv[0]]!r} — edit the tool's argv"
    if argv[0] not in commands:
        # Names the alternative rather than just refusing: the mistake this
        # catches is someone writing a shell command, and the fix is to say
        # which sky.boss command would have run it.
        return (
            f"argv must start with a sb command, not {argv[0]!r} — "
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
    highlight = body.get("highlight", "")
    if highlight:
        if not isinstance(highlight, str):
            return "highlight must be the name of a declared ruleset"
        if argv[0] not in resident:
            # Declared rules tint a *stream*. On a snapshot read the field
            # would load fine and mean nothing — the "wrong but looks right"
            # failure this loader exists to catch. See [[highlight]] round 3.
            return f"highlight is only for a follow (`{argv[0]}` is not resident)"

    group = body.get("group", "")
    if not isinstance(group, str):
        return "group must be a string"
    if group and not _NAME.match(group):
        # The same shape a tool name takes, because a group is a *key* as well
        # as a caption: the collapsed-state store is keyed on it and the writer
        # splices it. A free-text label makes `jam ` and `jam` two groups that
        # look like one. The rail uppercases it, which is where the caption is.
        return "group must be lowercase letters, digits and hyphens"

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


def load_groups(home: Path | None = None) -> tuple[list[Group], list[str]]:
    """Every declared group, and every reason one was skipped."""
    return parse_groups(read(home))


# ============================================================================
# Registration
# ============================================================================

# Why a module global. Loading happens at import, before any Click context
# exists, so a problem found there has nowhere to be reported yet. Nothing
# prints at import — `sb tools` surfaces these, which is where someone whose
# tool did not appear will look.
PROBLEMS: list[str] = []

#: The declared groups, captured by `register` at the same moment the tools
#: are. Read from the file *once*: a listing that re-read the home would show
#: groups from disk beside tools from the tree, and those two can disagree the
#: instant anything writes. See [[tools]] round 6.
GROUPS: list[Group] = []


def _expansion(tool: Tool) -> str:
    return "sb " + shlex.join(tool.argv)


def make_command(tool: Tool) -> click.Command:
    """A Click command that re-dispatches into the tree.

    The sub-context is built with the *tool's* name as its `info_name` and the
    `tools` group's context as its parent, so the envelope comes back saying
    `tools.jam-pr-list` rather than `data`. Round 1 said the bare name, because
    `data` was an implementation detail the operator did not type; `tools.` is
    something they *do* type, and the dotted path is the standing convention.

    It takes no arguments, so `sb jam-pr-list 945` is a usage error rather than
    something appended to the argv. A tool that took arguments would be a shell
    function, and this is not a shell.
    """

    @click.command(name=tool.name, short_help=tool.description or _expansion(tool))
    @click.pass_context
    def command(ctx: click.Context, refresh: int | None = None) -> None:
        from cli import cli as root

        args = list(tool.argv[1:])
        if tool.highlight:
            # Inherited, never re-asked: the tool declared its vocabulary, so
            # every invocation of it carries the flag the operator would have
            # typed. Same shape as `refresh`, minus the negotiation — a
            # ruleset has no "off by default" reading to respect.
            args = ["--highlight", tool.highlight, *args]
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
    command.sb_resident = tool.resident
    # The sky.boss argv this keyword stands for. The catalog ships it so the
    # bench can open a saved tool for editing; nothing else reads it, and a
    # surface that re-derived it would be guessing at the file. See [[tools]]
    # round 4.
    command.sb_expansion = list(tool.argv)

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
    # `sb_surface` rather than by consulting a list of names.
    command.sb_saved = True
    command.sb_refresh = tool.refresh
    # Declared, not inherited — unlike `acts`, a group is a statement about
    # where the operator wants to see this, which nothing can derive. Rides the
    # same path every other property does: a property on the command, never a
    # name written down in a module. See [[tools]] round 5.
    command.sb_group = tool.group
    # Carried so a surface that *rewrites* this tool can restate it. A replace
    # is a restatement, which only works if every declared field is reachable
    # from the surface doing the restating — otherwise the writer accepts an
    # incomplete statement as a complete one. See [[tools]] round 6.
    command.sb_highlight = tool.highlight
    command.sb_argv = tuple(tool.argv)
    # Inherited, never declared. The catalog reads this rather than the command
    # path, because the path of `sb deploy-thing` says nothing about the `run`
    # hiding inside it.
    command.sb_acts = tool.acts
    return command


def reload(root: click.Group, home: Path | None = None) -> list[str]:
    """Drop every registered tool and read the file again. Returns the problems.

    For a long-lived process. `register` runs once at CLI boot, which is right
    for a command that exits — but the canvas server lives for hours, and a
    tool saved from the workbench would otherwise not exist as far as its own
    surface was concerned until you restarted it. The name would be refused
    (that check reads the file) while the rail claimed the tool was not there:
    a surface disagreeing with itself.

    Dropping first is what makes it a *reload* rather than an accumulation —
    `add_command` replaces by name, so a re-register alone would never notice a
    tool the operator deleted in `$EDITOR`.

    This is the catalog's own doctrine one level down: **derived on every
    request, never kept.** See [[workbench]] round 3.
    """
    for name, command in list(tools.commands.items()):
        if getattr(command, "sb_saved", False):
            del tools.commands[name]
    return register(root, home)


def register(root: click.Group, home: Path | None = None) -> list[str]:
    """Put every declared tool behind the `tools` group. Returns the problems.

    Registration targets the group rather than the root (round 2): the
    builtin/operator line is the sharpest line in the design, and nesting is
    what makes it visible in `sb --help`. It is also what retired the
    shadowing rule into structure — a saved `run` lives at `sb tools run` and
    collides with nothing.

    `commands` and `resident` are still read off the *root's* walk, because a
    tool's argv starts with a root-level sky.boss command and inherits its verdicts.
    """
    entries = walk(root)
    commands = {entry["name"]: entry["acts"] for entry in entries}
    resident = frozenset(entry["name"] for entry in entries if entry.get("resident"))
    loaded, problems = load(commands, home, resident)
    for tool in loaded:
        tools.add_command(make_command(tool))
    groups, group_problems = load_groups(home)
    GROUPS[:] = groups
    return problems + group_problems


@click.group(invoke_without_command=True)
@click.pass_context
def tools(ctx: click.Context) -> None:
    """The tools — the operator's saved commands, behind their own door.

    Bare, it lists what is declared. An observe — it runs nothing:

        sb tools

    It reports what is declared and, importantly, what was declared and
    refused — a tool that fails to load is otherwise invisible, and the
    operator who wrote it has no way to tell it apart from one they forgot to
    write.

    A saved command runs behind this group, spelled long or short:

        sb tools jam-pr-list --refresh 30
        sb -t jam-pr-list --refresh 30

    A tool's `refresh` field is a default, never a cadence in force — the
    canvas opens the tool's window at it and a bare `--refresh` adopts it, but
    in a terminal a saved command always runs once unless the flag is given.
    """
    if ctx.invoked_subcommand is None:
        _listing()


@emit
def _listing() -> Result:
    """The bare `sb tools` rendering — one door for "what did I declare".

    Formats and highlight rulesets ride in the same listing (see [[capture]],
    [[highlight]]): this is already the one place the operator looks for "what
    did I declare, and what was refused", and a second listing command would
    split that. Their load problems land in the same degrade list a tool's do.
    """
    from cli import capture as capture_

    result = Result()
    saved = [
        (name, command)
        for name, command in tools.commands.items()
        if getattr(command, "sb_saved", False)
    ]
    # Groups alphabetical, tools alphabetical within them, the ungrouped last.
    # Declaration order was the tempting alternative — the file is hand-written
    # and its order is an assertion — and it lost to the fact that the catalog
    # already sorts: honouring file order means threading a position index
    # through a structure that exists to read properties off command objects,
    # to buy an ordering the operator can have by naming a group.
    saved.sort(key=lambda pair: (not _group_of(pair[1]), _group_of(pair[1]), pair[0]))
    declared = [
        {
            "name": name,
            # Omitted rather than empty, so a file with no groups declared
            # produces the listing it produced before groups existed — the
            # column renderer takes every key of every row, so an absent key
            # is an absent column. See [[tools]] round 5.
            **({"group": _group_of(command)} if _group_of(command) else {}),
            "description": command.short_help or "",
            "runs": " ".join(("sb", *_argv_of(command))),
            "acts": getattr(command, "sb_acts", False),
            "refresh": getattr(command, "sb_refresh", 0),
        }
        for name, command in saved
    ]

    from cli import highlight as highlight_

    # Declared groups ride the same listing, for the reason the formats do:
    # one door for "what did I declare, and what was refused". Without this an
    # empty group would be visible in the rail and invisible from the terminal,
    # which is the CLI/rail divergence round 5 was built to avoid.
    formats, format_problems = capture_.load_formats()
    # Declared highlight rulesets ride the same listing as the formats beside
    # them in the file: one door for "what did I declare, and what was
    # refused". See [[highlight]] round 3.
    rulesets, highlight_problems = highlight_.load_rulesets()
    result.data = {
        "tools": declared,
        "groups": [
            {
                "name": section["name"],
                "description": section["description"],
                "commands": section["count"],
                "declared": section["declared"],
            }
            for section in sections(registered(), GROUPS)
        ],
        "formats": [
            {"name": fmt.name, "kind": fmt.kind, "description": fmt.description}
            for fmt in sorted(formats, key=lambda f: f.name)
        ],
        "highlights": [
            {"name": rs.name, "rules": len(rs.rules), "description": rs.description}
            for rs in sorted(rulesets, key=lambda r: r.name)
        ],
    }

    for problem in (*PROBLEMS, *format_problems, *highlight_problems):
        result.degrade(problem)

    return result


def _argv_of(command: click.Command) -> tuple[str, ...]:
    return getattr(command, "sb_argv", ())


def _group_of(command: click.Command) -> str:
    return getattr(command, "sb_group", "")


def registered() -> list[Tool]:
    """Every registered tool, off the tree rather than off the file.

    The tree is what actually ran `register`, so this cannot disagree with what
    `sb tools` lists or what the palette offers. Only the fields `sections`
    needs are filled — this is a view of the registration, not a re-parse.
    """
    return [
        Tool(name=name, argv=list(_argv_of(command)), group=_group_of(command))
        for name, command in tools.commands.items()
        if getattr(command, "sb_saved", False)
    ]


# ============================================================================
# Saving — the one write, and it only ever appends
# ============================================================================
#
# See [[tools]] round 3. The rule this lives under: **sky.boss never touches a line
# the operator wrote.** Round-tripping the file would mean a TOML *writer*
# (the stdlib only reads) deciding how a hand-written file should look —
# comments dropped, argv lists reflowed, keys reordered. Appending one block
# sidesteps all of it and buys the stronger claim. It is also why there is no
# overwrite: you cannot edit in place if you never rewrite.


def saved_argv(invocation: list[str], command: str) -> list[str]:
    """The sky.boss argv to save, taken from the line that is running.

    **What you typed, minus the flag that asked.** Not rebuilt from parsed
    options: a tool whose expansion does not match the line that created it is
    the failure this feature would otherwise introduce, and it would stay
    invisible until the day the tool ran.

    Three things the scan has to get right:

    - It starts at the **command word**, so root flags (`--json`) are dropped —
      a tool's argv begins with a sky.boss command by contract.
    - It stops looking at `--`. Everything after that belongs to the wrapped
      tool, and a `--save` in *there* is the foreign command's own flag. Click
      never parsed it as ours, so neither does this.
    - `--refresh` is **lifted out of the argv into the tool's field**, because
      a cadence baked into a saved argv would make `sb tools <name>` go
      resident on its own. Residency is never ambient ([[refresh]]): the field
      is the canvas's starting cadence and a terminal keyword still runs once.
    """
    try:
        start = invocation.index(command)
    except ValueError:  # pragma: no cover — Click found it, so it is there
        raise click.UsageError(f"cannot tell what to save from: sb {' '.join(invocation)}")

    out: list[str] = []
    skip = False
    for token in invocation[start:]:
        if skip:
            skip = False
            continue
        if token == "--":
            # Everything past here is the wrapped tool's, verbatim.
            out.append(token)
            out.extend(invocation[invocation.index(token, start) + 1 :])
            break
        if token == "--save" or token == "--refresh":
            skip = True  # the space-separated form takes the next token too
            continue
        if token.startswith("--save=") or token.startswith("--refresh="):
            continue
        out.append(token)
    return out


def cadence_of(invocation: list[str], command: str) -> int:
    """The `--refresh` in force on this invocation, as the tool's field.

    Zero when there is none. Read off the same argv rather than off Click's
    parsed value so that the two halves of `saved_argv` — what is lifted out
    and what is written down — cannot disagree.
    """
    tokens = invocation[invocation.index(command) :]
    for index, token in enumerate(tokens):
        if token == "--":
            break
        if token == "--refresh" and index + 1 < len(tokens):
            value = tokens[index + 1]
            return int(value) if value.lstrip("-").isdigit() else 0
        if token.startswith("--refresh="):
            value = token.split("=", 1)[1]
            return int(value) if value.lstrip("-").isdigit() else 0
    return 0


def _toml_string(value: str) -> str:
    """One TOML basic string. Escaped by hand, because the stdlib only reads.

    Deliberately small: an argv part is text, and the four escapes TOML needs
    for text are backslash, quote, and the two control characters that could
    plausibly appear in one. Anything more exotic would be a sign the argv is
    not what it claims to be.
    """
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def block(
    name: str,
    argv: list[str],
    refresh: int = 0,
    description: str = "",
    group: str = "",
    highlight: str = "",
) -> str:
    """The text appended to `tools.toml` for one saved tool.

    `description` since [[tools]] round 4: `--save` cannot supply one — it saves
    by example and the example was an argv — but a surface that authors a tool
    can ask, and a list of saved commands without descriptions is a list of
    argvs you have to read to recognise.
    """
    parts = ", ".join(_toml_string(part) for part in argv)
    lines = [f"[tool.{name}]"]
    if description:
        lines.append(f"description = {_toml_string(description)}")
    # Above `argv` with `description`, because both say what this *is* and the
    # argv says what it does. An empty group is ungrouped and writes no line at
    # all, so clearing the bench's field removes it from the block rather than
    # leaving `group = ""` behind. See [[tools]] round 5.
    if group:
        lines.append(f"group = {_toml_string(group)}")
    lines.append(f"argv = [{parts}]")
    if refresh:
        lines.append(f"refresh = {refresh}")
    # Every declared field a tool can carry has to be here, or a rewrite drops
    # it silently. `highlight` was missing from round 4 until round 6 measured
    # it: a followed tool declaring a ruleset came back without one, and the
    # only evidence was a stream that stopped being tinted. A test walks the
    # dataclass so the next field added cannot repeat it.
    if highlight:
        lines.append(f"highlight = {_toml_string(highlight)}")
    return "\n".join(lines) + "\n"


#: How many backups of `tools.toml` to keep. Every mutating write copies the
#: current file first, at the operator's request when rule 4 was relaxed
#: ([[tools]] round 4). Twenty is a day of heavy editing and a few kilobytes;
#: the point is that "undo" is a `cp` rather than a feature.
BACKUPS_KEPT = 20

#: A table header at column 0 — `[tool.x]`, `[highlight.y]`. What ends a block.
_HEADER = re.compile(r"^\[[^\[\]]+\]\s*(#.*)?$")


def command_table(root=None) -> tuple[dict[str, bool], frozenset[str]]:
    """`(commands, resident)` off the live Click tree, as `register` derives them.

    One derivation, so the writer and the loader cannot disagree about what a
    sky.boss command is. Walking the real tree rather than keeping a list is the
    catalog's own doctrine ([[canvas]]): a table would drift the day a command
    was added.
    """
    if root is None:
        from cli import cli as root_group

        root = root_group
    entries = walk(root)
    return (
        {entry["name"]: entry["acts"] for entry in entries},
        frozenset(entry["name"] for entry in entries if entry.get("resident")),
    )


def write_problem(
    name: str,
    argv: list[str],
    refresh: int = 0,
    home: Path | None = None,
    root=None,
    group: str = "",
    highlight: str = "",
) -> str | None:
    """Why this tool cannot be written, or None.

    **Every refusal the loader makes, made first.** A tool that writes cleanly
    and then fails to load is the worst of both — it is on disk, it is not in
    the tree, and the only evidence is a line in `sb tools`. So this runs
    `_check`, the loader's own function, against a body built from the same
    fields the write is about to serialise. Two implementations of this rule
    would disagree the day one of them changed.

    It deliberately does **not** refuse a name that already exists: round 4
    made create and replace one call, because they are one intent. The shape of
    a name is still checked, and a file sky.boss cannot parse is still refused —
    splicing into a document whose structure is unknown is how a tool is lost.
    """
    if not _NAME.match(name or ""):
        return f"{name!r} cannot be a tool name — lowercase letters, digits and hyphens"

    existing = read(home)
    if "__error__" in existing:
        return f"{existing['__error__']} — fix the file before writing into it"

    commands, resident = command_table(root)
    body: dict = {"argv": list(argv)}
    if refresh:
        body["refresh"] = refresh
    if group:
        body["group"] = group
    if highlight:
        body["highlight"] = highlight
    return _check(name, body, commands, set(), resident)


def backup(home: Path | None = None, stamp: str | None = None) -> Path | None:
    """Copy `tools.toml` aside before it is rewritten. None if there is nothing
    to copy.

    Before every mutating write, not on a timer and not on a schedule: the file
    being replaced is the only thing worth keeping, and the moment it is about
    to stop existing is the only moment that is true.

    Kept in `$SB_HOME/backups/` rather than beside the file, so `ls ~/.sky-boss`
    still shows three config files and not a drift of dated ones.
    """
    path = home_file(home)
    if not path.exists() or not path.stat().st_size:
        return None
    when = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    into = path.parent / "backups"
    into.mkdir(parents=True, exist_ok=True)
    kept = into / f"tools.{when}.toml"
    # A second is not fine-grained enough: editing a tool and deleting another
    # inside the same second would leave one backup where the operator was
    # promised two, and the one it left would be the wrong one.
    bump = 1
    while kept.exists():
        kept = into / f"tools.{when}-{bump}.toml"
        bump += 1
    kept.write_bytes(path.read_bytes())
    # Oldest first by name, which is why the stamp is sortable.
    existing = sorted(into.glob("tools.*.toml"))
    for stale in existing[:-BACKUPS_KEPT]:
        stale.unlink()
    return kept


def block_range(text: str, name: str, table: str = "tool") -> tuple[int, int] | None:
    """The line range `[TABLE.NAME]` occupies, as `[start, end)`. None if absent.

    **Located by line, not by round-tripping the document.** `tools.toml` is
    hand-written and carries the operator's prose — in this repo, a five-line
    comment about why `--cwd` is required for a sibling CLI. Parsing the whole
    file and re-serialising it would reformat every block including the ones
    nobody asked to change; splicing one line range leaves every other byte
    identical *by construction*, which is a stronger guarantee than any
    round-trip offers. See [[tools]] round 4.

    The range starts at the header, so **comments above a block are outside it**
    and survive an edit. They are the operator's prose and may still be true of
    the tool that replaces this one.
    """
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start is None:
            if stripped == f"[{table}.{name}]":
                start = i
            continue
        if _HEADER.match(stripped):
            return (start, i)
    return None if start is None else (start, len(lines))


def _with_leading_comments(lines: list[str], start: int) -> int:
    """Walk back over the comment lines *touching* a block header.

    Contiguous comments — no blank line between — unambiguously describe the
    block below them, so a delete takes them with it. A comment separated by a
    blank line is a section heading for whatever follows and stays. Getting
    this wrong in either direction destroys the operator's writing or litters
    their file with prose about a tool that no longer exists.
    """
    i = start
    while i > 0 and lines[i - 1].lstrip().startswith("#"):
        i -= 1
    return i


def write_block(
    name: str,
    argv: list[str],
    refresh: int = 0,
    description: str = "",
    home: Path | None = None,
    group: str = "",
    highlight: str = "",
) -> dict:
    """Create or replace one tool. Returns what happened, and where the backup went.

    Create and replace are one call because they are one intent — *this name
    should run this argv* — and asking the caller to know which it is means the
    surface holds an opinion about the file's current contents that may be one
    tick out of date.
    """
    problem = write_problem(name, argv, refresh, home, group=group, highlight=highlight)
    if problem:
        raise click.UsageError(problem)

    path = home_file(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    kept = backup(home)
    fresh = block(name, argv, refresh, description, group, highlight)

    span = block_range(text, name)
    if span is None:
        joiner = "" if not text else ("" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n"))
        path.write_text(text + joiner + fresh, encoding="utf-8")
        action = "created"
    else:
        lines = text.splitlines(keepends=True)
        start, end = span
        # The old block's trailing blank lines are separation, not content, and
        # they belong to the *file*. Shrink the range to leave them where they
        # are rather than consuming and re-emitting them — dropping them glues
        # the replacement to the next block, and re-emitting them as well
        # doubles them. Both still parse, and both read as sky.boss having
        # reformatted something nobody asked it to touch.
        while end > start and not lines[end - 1].strip():
            end -= 1
        path.write_text("".join(lines[:start]) + fresh + "".join(lines[end:]), encoding="utf-8")
        action = "replaced"
    return {
        "name": name,
        "action": action,
        "file": str(path),
        "runs": "sb " + shlex.join(argv),
        **({"group": group} if group else {}),
        **({"highlight": highlight} if highlight else {}),
        **({"refresh": refresh} if refresh else {}),
        **({"backup": str(kept)} if kept else {}),
    }


def remove_block(name: str, home: Path | None = None) -> dict:
    """Delete one tool. Raises if it is not there — a silent no-op on a delete
    reads as success and leaves the operator believing a command is gone."""
    path = home_file(home)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    span = block_range(text, name)
    if span is None:
        raise click.UsageError(f"{name!r} is not a tool in {path}")

    kept = backup(home)
    lines = text.splitlines(keepends=True)
    start, end = span
    start = _with_leading_comments(lines, start)
    remaining = "".join(lines[:start]) + "".join(lines[end:])
    path.write_text(remaining, encoding="utf-8")
    return {
        "name": name,
        "action": "deleted",
        "file": str(path),
        **({"backup": str(kept)} if kept else {}),
    }


def group_problem(name: str, description: str = "") -> str | None:
    """Why this group cannot be written, or None.

    The loader's own check, asked before the write — the rule round 4 set for
    tools and there is no reason a group gets a second opinion.
    """
    return _check_group(name, {"description": description}, set())


def write_group(name: str, description: str = "", home: Path | None = None) -> dict:
    """Create or replace `[group.NAME]`. Backed up first, like every write."""
    problem = group_problem(name, description)
    if problem:
        raise click.UsageError(f"group {name!r}: {problem}")

    path = home_file(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    kept = backup(home)

    lines = [f"[group.{name}]"]
    if description:
        lines.append(f"description = {_toml_string(description)}")
    fresh = "\n".join(lines) + "\n"

    span = block_range(text, name, table="group")
    if span is None:
        joiner = "" if not text else ("" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n"))
        path.write_text(text + joiner + fresh, encoding="utf-8")
        action = "created"
    else:
        rows = text.splitlines(keepends=True)
        start, end = span
        while end > start and not rows[end - 1].strip():
            end -= 1
        path.write_text("".join(rows[:start]) + fresh + "".join(rows[end:]), encoding="utf-8")
        action = "replaced"
    return {
        "name": name,
        "action": action,
        "file": str(path),
        **({"description": description} if description else {}),
        **({"backup": str(kept)} if kept else {}),
    }


def remove_group(name: str, home: Path | None = None) -> dict:
    """Delete `[group.NAME]`. Refused while any command still names it.

    **The refusal is here, not in the button.** A surface that only declines to
    *draw* a control has not refused anything — the sentence round 5 wrote
    about `/api/trial`, and it applies to every gesture a page can make up.

    It names the commands rather than just counting them, because "3 commands
    are still in it" leaves you opening the file to find out which.

    Deleting a group never deletes a command. A cascade here would be the
    surface deciding that *delete this label* meant *delete this work*.
    """
    path = home_file(home)
    text = path.read_text(encoding="utf-8") if path.exists() else ""

    raw = read(home)
    holders = sorted(
        tool
        for tool, body in (raw.get("tool") or {}).items()
        if isinstance(body, dict) and body.get("group") == name
    )
    if holders:
        raise click.UsageError(
            f"{name!r} still holds {_plural(len(holders))}: {', '.join(holders)} — "
            "move them out first"
        )

    span = block_range(text, name, table="group")
    if span is None:
        raise click.UsageError(f"{name!r} is not a declared group in {path}")

    kept = backup(home)
    rows = text.splitlines(keepends=True)
    start, end = span
    start = _with_leading_comments(rows, start)
    path.write_text("".join(rows[:start]) + "".join(rows[end:]), encoding="utf-8")
    return {
        "name": name,
        "action": "deleted",
        "file": str(path),
        **({"backup": str(kept)} if kept else {}),
    }


def _plural(count: int) -> str:
    return "1 command" if count == 1 else f"{count} commands"


def name_problem(name: str, home: Path | None = None) -> str | None:
    """Why this name cannot be saved, or None.

    Split out of `save` for the workbench, which has to answer the question
    *before* offering the button rather than after the write. That ordering is
    not cosmetic: **`--save` writes before it runs** ([[tools]] round 3), so a
    refusal discovered afterwards is a refusal discovered too late — and the
    name cannot be reused, because a duplicate is refused and editing stays
    `$EDITOR`'s. See [[workbench]] round 3.

    One implementation, asked twice. A surface holding its own copy of the name
    rule would be a second opinion about what sky.boss will accept, and the two would
    disagree the day the rule changed.
    """
    if not _NAME.match(name or ""):
        return f"{name!r} cannot be a tool name — lowercase letters, digits and hyphens"

    existing = read(home)
    if "__error__" in existing:
        # Appending to a file sky.boss cannot parse would bury the operator's real
        # problem under a second one.
        return f"{existing['__error__']} — fix the file before saving into it"
    declared = (existing.get("tool") or {}).get(name)
    if declared is not None:
        runs = " ".join(str(part) for part in (declared.get("argv") or []))
        return f"{name!r} is already a tool — it runs `sb {runs}`. Edit the file to change it."
    return None


def save(
    name: str,
    argv: list[str],
    refresh: int = 0,
    home: Path | None = None,
) -> Path:
    """Append one tool. Returns the file it was written to.

    Refuses rather than overwrites: a name already declared is an edit, and
    edits are `$EDITOR`'s. Refuses a cadence the surface cannot cycle to, for
    the same reason the loader does — a tool that writes cleanly and then
    fails to load is the worst of both.
    """
    problem = name_problem(name, home)
    if problem:
        raise click.UsageError(problem)

    if refresh and refresh not in INTERVALS:
        allowed = ", ".join(str(i) for i in INTERVALS)
        raise click.UsageError(f"a saved refresh must be one of {allowed} — got {refresh}")

    path = home_file(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Append, with a blank line ahead of the block when the file already has
    # content and does not end in one. Nothing above is read back and rewritten.
    with path.open("a", encoding="utf-8") as handle:
        if path.stat().st_size:
            handle.write("\n")
        handle.write(block(name, argv, refresh))
    return path


def save_invocation(name: str, command: str, invocation: list[str] | None = None) -> dict:
    """Save the line that is running, as `name`. The three observes' one call.

    Reads the recorded invocation rather than Click's parsed values — see
    `saved_argv` for why, and `INVOCATION` in cli/helpers.py for why it is
    recorded at all. `invocation` is injectable so the suite can hand one in
    without a process.

    Returns what the envelope should say: the name, the file it went to, and
    the expansion it will run. **What it will run** is the half worth carrying
    — it is the operator's one chance to notice that the saved line is not the
    line they meant, while they still remember what they typed.
    """
    line = INVOCATION if invocation is None else invocation
    argv = saved_argv(line, command)
    refresh = cadence_of(line, command)
    path = save(name, argv, refresh)
    return {
        "name": name,
        "file": str(path),
        "runs": "sb " + shlex.join(argv),
        **({"refresh": refresh} if refresh else {}),
    }
