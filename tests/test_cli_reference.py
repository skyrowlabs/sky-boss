"""The command reference in `docs/CLI.md` must match the CLI.

**Nothing keeps a command table.** That rule is why `cli/tui/` dispatches through
the real Click tree instead of mirroring it, and why the MCP allowlist is a
property of where a command lives rather than a list somebody maintains. A
hand-written CLI reference would be the first thing in the repo to break it —
and the first to be wrong, because a reference is read exactly when someone does
not already know the answer.

So the reference is walked off the live tree and this test fails when the file
disagrees. Regenerate rather than hand-edit:

    TB_WRITE_CLI_DOC=1 .venv/bin/python -m pytest -k cli_reference

Only the block between the markers is generated; the rest of that page is prose.
"""

from __future__ import annotations

import os

import rich_click as click

from cli import cli
from cli.helpers import PROJECT_ROOT

DOC = PROJECT_ROOT / "docs" / "CLI.md"

START = "<!-- reference:start -->"
END = "<!-- reference:end -->"

# `tb run` is the only door that writes. Stated here as data because the
# reference prints it in a column, and a reader deciding whether a command is
# safe to hand an agent should not have to infer it from prose.
WRITING_ROOT = "run"

# The reference reads in mood order — act, schedule, describe, judge — because
# that is the order the page explains, and alphabetical would open on `tb auto`
# and bury `tb run` in the middle. Surfaces and the alias come last: neither is
# a mood. Anything unlisted sorts after, alphabetically, so a new top-level
# command appears in the reference the day it lands rather than being dropped.
MOOD_ORDER = ("run", "auto", "info", "check", "tui", "doctor")


def walk(group: click.Group = cli, prefix: str = "tb") -> list[tuple[str, click.Command]]:
    """Every command, by the name it is *registered under*.

    Not `cmd.name`. `tb doctor` is registered as an alias onto the same Command
    object as `tb check tools`, whose `.name` is "tools" — walking by `.name`
    silently documents a command called `tb tools`, which does not exist.
    """
    def rank(item: tuple[str, click.Command]) -> tuple[int, str]:
        name = item[0]
        order = MOOD_ORDER if prefix == "tb" else ()
        return (order.index(name) if name in order else len(order), name)

    found: list[tuple[str, click.Command]] = []
    for name, command in sorted(group.commands.items(), key=rank):
        path = f"{prefix} {name}"
        found.append((path, command))
        if isinstance(command, click.Group):
            found.extend(walk(command, path))
    return found


def _summary(command: click.Command) -> str:
    if command.short_help:
        return command.short_help
    return (command.help or "").strip().split("\n\n")[0].replace("\n", " ").strip()


def _writes(path: str) -> str:
    return "**yes**" if path.split()[1] == WRITING_ROOT else "no"


def _params(command: click.Command) -> tuple[list, list]:
    arguments, options = [], []
    for param in command.params:
        if isinstance(param, click.Argument):
            arguments.append(param)
        elif "--help" not in param.opts:
            options.append(param)
    return arguments, options


# click 8.3 marks "no default given" with a sentinel rather than None. Printing
# it renders `Sentinel.UNSET` in the Default column, which reads like a value.
UNSET = getattr(click.core, "UNSET", None)


def _default(param) -> str:
    if param.required or param.default is None or param.default is UNSET:
        return "—"
    if getattr(param, "is_flag", False):
        return "on" if param.default else "off"
    if isinstance(param.default, (list, tuple)):
        return "—" if not param.default else f"`{' '.join(map(str, param.default))}`"
    return f"`{param.default}`"


def _type_of(param) -> str:
    """The type, and for a choice the choices themselves.

    "choice" alone tells a reader they must pick from a set without telling them
    what the set is, which is the one question a reference exists to answer.
    """
    choices = getattr(param.type, "choices", None)
    if choices:
        return " · ".join(f"`{choice}`" for choice in choices)
    return param.type.name


def _detail(path: str, command: click.Command, level: int = 4) -> list[str]:
    lines = [f"{'#' * level} `{path}`", ""]

    help_text = (command.help or "").strip()
    if help_text:
        for paragraph in help_text.split("\n\n"):
            lines += [" ".join(paragraph.split()), ""]

    arguments, options = _params(command)

    if arguments:
        lines += ["| Argument | Type | Required |", "|---|---|---|"]
        for param in arguments:
            required = "yes" if param.required else "no"
            name = param.metavar or param.name.upper()
            lines.append(f"| `{name}` | {_type_of(param)} | {required} |")
        lines.append("")

    if options:
        lines += ["| Option | Type | Default | Description |", "|---|---|---|---|"]
        for param in options:
            flags = ", ".join(f"`{opt}`" for opt in param.opts)
            kind = "flag" if getattr(param, "is_flag", False) else _type_of(param)
            lines.append(
                f"| {flags} | {kind} | {_default(param)} | {(param.help or '').strip() or '—'} |"
            )
        lines.append("")

    if isinstance(command, click.Group):
        if command.invoke_without_command:
            lines += [
                f"Runs with no subcommand: `{path}` on its own does the work below.",
                "",
            ]
        else:
            lines += [f"A group. `{path}` on its own prints help.", ""]

    return lines


def build_reference() -> str:
    commands = walk()

    lines = [START, ""]
    lines += ["### Every command", ""]
    lines += ["| Command | Writes | What it does |", "|---|---|---|"]
    for path, command in commands:
        lines.append(f"| `{path}` | {_writes(path)} | {_summary(command)} |")
    lines.append("")

    for path, command in commands:
        if " " in path.removeprefix("tb "):
            continue  # a subcommand; it is printed under its group below
        lines += _detail(path, command, level=3)
        for sub_path, sub in commands:
            if sub_path.startswith(f"{path} ") and sub_path.count(" ") == path.count(" ") + 1:
                lines += _detail(sub_path, sub)

    lines.append(END)
    return "\n".join(lines)


def _split(text: str) -> tuple[str, str]:
    assert START in text, f"{DOC.name} has no {START} marker"
    assert END in text, f"{DOC.name} has no {END} marker"
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    return before, after


def test_the_reference_matches_the_cli():
    text = DOC.read_text()
    before, after = _split(text)
    expected = before + build_reference() + after

    if os.environ.get("TB_WRITE_CLI_DOC"):
        DOC.write_text(expected)
        return

    assert text == expected, (
        "docs/CLI.md is out of date — regenerate it with\n"
        "  TB_WRITE_CLI_DOC=1 .venv/bin/python -m pytest -k cli_reference"
    )


def test_every_command_is_documented():
    """A command absent from the reference is a command nobody finds."""
    text = DOC.read_text()
    missing = [path for path, _ in walk() if f"`{path}`" not in text]
    assert not missing, f"not in the reference: {missing}"


def test_the_alias_is_documented_under_the_name_you_type():
    """`tb doctor` and `tb check tools` are one Command object, so they cannot
    drift — but the object is named "tools", and walking by `.name` would print
    a `tb tools` that does not exist."""
    paths = {path for path, _ in walk()}
    assert "tb doctor" in paths
    assert "tb tools" not in paths
    assert "tb check tools" in paths


def test_every_command_says_what_it_does():
    """An undocumented command in a reference is worse than an absent one — it
    looks covered."""
    silent = [path for path, command in walk() if not _summary(command)]
    assert not silent, f"no help text: {silent}"


def test_only_run_writes():
    """The property the whole taxonomy exists for, asserted rather than
    described. If a second writing root ever lands, this fails and the reference
    stops claiming something untrue."""
    from cli.jobs import auto

    writing = {path for path, _ in walk() if _writes(path) == "**yes**"}
    assert all(path.startswith("tb run") for path in writing)
    # `auto` schedules, which is the one write-adjacent thing outside `run`.
    assert isinstance(auto, click.Group)


def test_the_reference_reads_in_mood_order():
    """Alphabetical would open on `tb auto` and bury `tb run`, which is the one
    command whose position on the page carries meaning."""
    tops = [path for path, _ in walk() if path.count(" ") == 1]
    assert tops[:4] == ["tb run", "tb auto", "tb info", "tb check"]


def test_a_new_top_level_command_would_still_be_listed():
    """MOOD_ORDER is a preferred order, not an allowlist. A command missing from
    it must sort last rather than vanish from the reference."""
    import rich_click as click

    group = click.Group("tb")
    group.add_command(click.Command("zebra", help="Last alphabetically."))
    group.add_command(click.Command("run", help="First by mood."))
    group.add_command(click.Command("newthing", help="Not in MOOD_ORDER."))

    assert [p for p, _ in walk(group)] == ["tb run", "tb newthing", "tb zebra"]


def test_an_unset_default_is_not_printed_as_a_value():
    """click 8.3 marks "no default" with a sentinel. Rendering it gives a
    Default column reading `Sentinel.UNSET`, which looks like a real value."""
    reference = build_reference()
    assert "Sentinel" not in reference
    assert "UNSET" not in reference


def test_a_leaf_top_level_command_gets_one_heading():
    """`tb run` is a command, not a group, so it must not be introduced by a
    section heading and then repeated as its own subheading."""
    reference = build_reference()
    assert reference.count("### `tb run`") == 1
    # The group case still nests: a heading for `tb check`, then one per verb.
    assert "### `tb check`" in reference
    assert "#### `tb check drift`" in reference


def test_a_choice_option_names_its_choices():
    """"choice" alone says a reader must pick from a set without saying what
    the set is — the one question a reference exists to answer."""
    from cli.jobs import LANES

    reference = build_reference()
    for lane in LANES:
        assert f"`{lane}`" in reference, f"lane {lane} is not in the reference"
