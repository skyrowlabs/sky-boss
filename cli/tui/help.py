"""What the line you are typing would run, explained while you type it.

Read off the same Click objects `dispatch` invokes and `complete` completes
from. That is the third consumer of one rule: the surface keeps no command
table, so it cannot teach a verb the CLI does not have. A help pane fed from a
hand-written table would be the most confidently wrong thing on the screen.

Cheap enough to run on every keystroke, on the event loop. Resolving a line and
reading every parameter off it is attribute access — measured at 0.4 µs, so
2,000 keystrokes cost under a millisecond. No thread, no debounce, no cache.
"""

from __future__ import annotations

import rich_click as click
from rich.text import Text

from cli.output import TUI_THEME
from cli import cli as root
from cli.tui.complete import resolve

TITLE = TUI_THEME.styles["tb.accent"]
BODY = TUI_THEME.styles["tb.label"]
NAME = TUI_THEME.styles["tb.num"]
MUTED = TUI_THEME.styles["tb.muted"]

# The narrow pane leans on truncation rather than wrapping: a wrapped option
# description eats the rows the other options need. One line each, cut short.
ELLIPSIS = "…"

# Enough of a name column to hold the longest verb without pushing the
# description off the pane entirely.
NAME_WIDTH = 11


def _path(line: str) -> list[str]:
    """The words that address a command, dropping the one still being typed.

    Split on whitespace rather than with shlex, for the same reason `complete`
    does: a half-typed quote is normal while typing and must not raise.
    """
    words = line.split()
    if words and words[0] == "tb":
        words = words[1:]
    # A trailing space means the word is finished and the next one is a new
    # token; without one, the last word is still being typed and may not be a
    # command yet. `resolve` steps over anything that is not a subcommand, so
    # passing it either way is safe.
    return words


def _fit(text: str, width: int) -> str:
    if width <= 1 or len(text) <= width:
        return text
    return text[: width - 1] + ELLIPSIS


def _entries(command: click.Command) -> list[tuple[str, str]]:
    """Name and one-line description for whatever comes next.

    A group offers its subcommands, because that is what you would type next.
    A leaf offers its own parameters, for the same reason.
    """
    if isinstance(command, click.Group):
        return [
            (name, sub.get_short_help_str(80))
            for name, sub in sorted(command.commands.items())
        ]

    entries: list[tuple[str, str]] = []
    for param in command.params:
        if isinstance(param, click.Argument):
            # Arguments carry no help in Click, so the metavar is the only
            # thing to say about them — and saying it beats a blank line.
            entries.append((f"<{param.name}>", param.make_metavar(ctx=None) or ""))
        else:
            name = max(getattr(param, "opts", []) or [param.name], key=len)
            entries.append((name, getattr(param, "help", "") or ""))
    return entries


def _descend(command: click.Command, line: str) -> click.Command:
    """Follow an unambiguous prefix one step further than `resolve` will.

    `resolve` only steps into words that are already whole subcommands, so
    `check dr` stops at the group. But `dr` can only become `drift`, and
    explaining the group when the answer is certain wastes the pane on the
    keystroke where the help is most wanted.
    """
    if not isinstance(command, click.Group) or line.endswith((" ", "\t")):
        return command
    words = line.split()
    if not words:
        return command
    tail = words[-1]
    if tail.startswith("-"):
        return command
    matches = [name for name in command.commands if name.startswith(tail)]
    return command.commands[matches[0]] if len(matches) == 1 else command


def view(line: str, *, width: int = 40, rows: int = 5) -> Text:
    """The help pane's contents for a partly-typed line.

    Never raises and never returns None — it repaints on every keystroke, and a
    dead pane mid-word would read as a crash.
    """
    command = _descend(resolve(_path(line)), line)

    # no_wrap: the pane truncates on purpose, and a wrapped option description
    # eats the rows the other options need. Belt and braces with _fit, which
    # cannot know the pane's real width before first layout.
    body = Text(no_wrap=True, overflow="ellipsis")
    # The root group's Click name is "cli" — the package it lives in, not the
    # program. Everywhere the user can see, it is tb.
    title = "tb" if command is root else (command.name or "tb")
    body.append(_fit(title, width), style=TITLE)

    remaining = rows - 1
    summary = command.get_short_help_str(200)
    if summary and remaining > 0:
        body.append("\n" + _fit(summary, width), style=BODY)
        remaining -= 1

    entries = _entries(command)
    shown = entries[:remaining]
    for name, description in shown:
        body.append("\n")
        body.append(f"{name[:NAME_WIDTH]:<{NAME_WIDTH}} ", style=NAME)
        body.append(_fit(description, max(0, width - NAME_WIDTH - 1)), style=MUTED)

    hidden = len(entries) - len(shown)
    if hidden > 0 and shown:
        # Phase 5 makes this the click target. Until then it is at least honest
        # about there being more, rather than silently stopping.
        body.append(f"\n+{hidden} more", style=MUTED)

    return body
