"""The palette's suggestions, read off the live Click tree.

**Nothing here keeps a command table.** That was the TUI's hardest-won
invariant and it is the one worth carrying into a surface that renders in a
browser, because the failure mode is worse here: a terminal at least shows you
the error when you run a command that does not exist, whereas a palette that
offers it has already told you it does.

So the catalog is derived on every request. A command added next year appears
in the palette with its real one-liner and its real options, and this module
does not change.

Introspection only — walking the tree never runs a command. Execution goes out
of process entirely; see `cli/canvas/runner.py` for why.
"""

from __future__ import annotations

import rich_click as click


def _summary(command: click.Command) -> str:
    """Click's one-liner, however the command chose to declare it."""
    if command.short_help:
        return command.short_help
    if command.help:
        return command.help.strip().split("\n")[0]
    return ""


def _options(command: click.Command) -> list[dict]:
    """The flags the palette offers as chips.

    Only actual switches and options — arguments are positional and a chip that
    inserted one would produce an argv nobody meant. `--help` is dropped for the
    same reason a chip toggling it would be a joke: it does not filter anything.
    """
    out = []
    for param in command.params:
        if not isinstance(param, click.Option) or param.name == "help":
            continue
        flag = max(param.opts, key=len)
        out.append(
            {
                "flag": flag,
                "help": param.help or "",
                "is_flag": bool(param.is_flag),
                "takes_value": not param.is_flag,
            }
        )
    return out


def walk(command: click.Command, path: tuple[str, ...] = ()) -> list[dict]:
    """Every runnable leaf under this command, deepest name first.

    Groups are not themselves entries: `tb` and a future `tb auto` do nothing
    on their own, and offering them would put a command in the palette that
    opens an empty window.

    A *surface* is not an entry either. `tb ui` is this canvas; offering it
    would let you open a canvas inside the canvas. The flag is set on the
    command object rather than listed here on purpose — a name written down in
    this module is the beginning of the command table the whole design refuses
    to keep, and it would go stale the day the surface is renamed.
    """
    if getattr(command, "tb_surface", False):
        return []
    if isinstance(command, click.Group):
        entries: list[dict] = []
        # A group that runs bare is a leaf as well as a container: `tb tools`
        # with no subcommand renders the toolbox listing, and a window may
        # hold that open. A plain group still is not an entry — opening a
        # window on one would run nothing and show nothing.
        if path and command.invoke_without_command:
            entries.extend(_leaf(command, path))
        for name in sorted(command.commands):
            entries.extend(walk(command.commands[name], path + (name,)))
        return entries

    return _leaf(command, path)


def _leaf(command: click.Command, path: tuple[str, ...]) -> list[dict]:
    return [
        {
            "name": " ".join(path),
            "argv": list(path),
            "summary": _summary(command),
            "options": _options(command),
            # Every leaf is a read unless it is the one door that writes. The
            # distinction is not cosmetic: only a read may be given a refresh
            # cadence, because re-running a read is a refresh and re-running a
            # write is a scheduler nobody asked for. The mockup encoded the
            # same rule before any of this existed.
            # A saved command carries the verdict of whatever it expands to,
            # because the path says nothing: `tb deploy-thing` is one word and
            # the `run` it wraps is invisible from here. Getting this wrong
            # would offer a refresh cadence on a write, which is the one thing
            # the read/write split exists to prevent.
            "acts": getattr(command, "tb_acts", None) or path[:1] == ("run",),
            # Read off the command object, never a list of names here — the
            # same rule `tb_surface` follows two lines up. A name written down
            # in this module is the beginning of the command table the whole
            # design refuses to keep. The sidebar filters on this.
            "saved": getattr(command, "tb_saved", False),
            # A saved command may declare the cadence it wants to open on.
            # Zero for everything else, which is what a window starts at now.
            "refresh": getattr(command, "tb_refresh", 0),
            # Resident by nature: no cadence control at all — a stream is not
            # refreshed, it is open. `follow` sets this; a saved command
            # inherits it from its expansion like everything else.
            "resident": getattr(command, "tb_resident", False),
        }
    ]


def catalog(root: click.Group | None = None) -> list[dict]:
    """The whole palette. `root` is injectable for the same reason `dispatch`'s
    was: tb is a two-command tree today and has no shape to test a walk on."""
    if root is None:
        from cli import cli as root_group

        root = root_group
    return walk(root)
