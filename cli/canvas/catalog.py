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
    """Click's one-liner, however the command chose to declare it.

    The first *paragraph*, with its newlines collapsed — not the first line.
    A docstring is hard-wrapped by whoever wrote it, so a line break falls
    wherever eighty columns happened to land: `sb data`'s first line ends
    "An observe — a window may". The palette hid that behind an ellipsis; the
    bench's reference rail does not, and a sentence that stops mid-clause reads
    as a bug in the help rather than in the splitting. See [[workbench]].
    """
    if command.short_help:
        return " ".join(command.short_help.split())
    if command.help:
        paragraph = " ".join(command.help.strip().split("\n\n")[0].split())
        # A paragraph ending in a colon is introducing the example that follows
        # it, and the example is not here — so the colon is a promise the
        # summary cannot keep. Drop back to the last whole sentence.
        while paragraph.endswith(":") and ". " in paragraph:
            paragraph = paragraph.rsplit(". ", 1)[0] + "."
        return paragraph
    return ""


def _options(command: click.Command) -> list[dict]:
    """The flags the palette offers as chips.

    Only actual switches and options — arguments are positional and a chip that
    inserted one would produce an argv nobody meant. `--help` is dropped for the
    same reason a chip toggling it would be a joke: it does not filter anything.

    **A hidden option is not offered either.** `sb run --refresh` exists only to
    refuse well — [[refresh]] rules that an act never takes a cadence, and
    without the option Click answers it with a bare usage error instead of the
    reason. It is `hidden=True`, so `--help` does not list it; the workbench's
    reference rail did, which is the drift *one help string, two surfaces* is
    supposed to make impossible. Found by reading the rail. See [[workbench]]
    round 3.
    """
    out = []
    for param in command.params:
        if not isinstance(param, click.Option) or param.name == "help":
            continue
        if param.hidden:
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

    Groups are not themselves entries: `sb` and a future `sb auto` do nothing
    on their own, and offering them would put a command in the palette that
    opens an empty window.

    A *surface* is not an entry either. `sb ui` is this canvas; offering it
    would let you open a canvas inside the canvas. The flag is set on the
    command object rather than listed here on purpose — a name written down in
    this module is the beginning of the command table the whole design refuses
    to keep, and it would go stale the day the surface is renamed.
    """
    if getattr(command, "sb_surface", False):
        return []
    if isinstance(command, click.Group):
        entries: list[dict] = []
        # A group that runs bare is a leaf as well as a container: `sb tools`
        # with no subcommand renders the tools listing, and a window may
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
            # because the path says nothing: `sb deploy-thing` is one word and
            # the `run` it wraps is invisible from here. Getting this wrong
            # would offer a refresh cadence on a write, which is the one thing
            # the read/write split exists to prevent.
            "acts": getattr(command, "sb_acts", None) or path[:1] == ("run",),
            # Read off the command object, never a list of names here — the
            # same rule `sb_surface` follows two lines up. A name written down
            # in this module is the beginning of the command table the whole
            # design refuses to keep. The sidebar filters on this.
            "saved": getattr(command, "sb_saved", False),
            # A builtin that takes nothing from its caller may opt into the
            # agent surface. Read off the command object, never a list here —
            # the same rule `sb_surface` and `sb_acts` follow. See [[mcp]].
            "mcp": getattr(command, "sb_mcp", False),
            # A saved command may declare the cadence it wants to open on.
            # Zero for everything else, which is what a window starts at now.
            "refresh": getattr(command, "sb_refresh", 0),
            # What a saved command *expands to*, for the surface that edits it.
            # `argv` above is the path you type — `tools drainer` — which is
            # the right answer for running it and no answer at all for opening
            # it in the bench. Empty for everything that is not saved.
            # See [[tools]] round 4.
            "expansion": list(getattr(command, "sb_expansion", ()) or ()),
            # Resident by nature: no cadence control at all — a stream is not
            # refreshed, it is open. `follow` sets this; a saved command
            # inherits it from its expansion like everything else.
            "resident": getattr(command, "sb_resident", False),
        }
    ]


def catalog(root: click.Group | None = None) -> list[dict]:
    """The whole palette. `root` is injectable for the same reason `dispatch`'s
    was: sky.boss is a two-command tree today and has no shape to test a walk on."""
    if root is None:
        from cli import cli as root_group

        root = root_group
    return walk(root)


def entry_for(argv: list[str], entries: list[dict] | None = None) -> dict | None:
    """The catalog entry an sb-level argv names, longest path first.

    Longest first because a saved command lives at `tools <name>` since
    [[tools]] round 2 and inherits its expansion's verdict — matching on
    `argv[0]` alone would call every saved tool a read, including one wrapping
    `run`, which is the one mistake the read/write split exists to prevent.
    Same rule the palette's `suggest` follows, for the same reason.

    None when nothing in the tree answers to it. That is not a failure: a raw
    argv is exactly the case, and the caller decides what an unknown one is.
    """
    if not argv:
        return None
    if entries is None:
        entries = catalog()
    for entry in sorted(entries, key=lambda e: -len(e["argv"])):
        if argv[: len(entry["argv"])] == entry["argv"]:
            return entry
    return None
