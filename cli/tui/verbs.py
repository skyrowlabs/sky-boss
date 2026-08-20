"""View verbs — the only kind of verb a surface may own.

A surface renders the envelope every command returns; it is deliberately not a
fifth mood, and its one verb is "dispatch a string". That rule exists so
`tb run` stays the single door that writes, and it is not relaxed here: these
verbs change *what is shown* and never what exists. `inspect` reads an envelope
already in hand. [[pinned-watches]] adds `watch` and `unwatch`, which move a
declared watch between the rail and a pane.

**Checked after the real tree, never before.** A surface verb that shadowed a
tb command would be the worst kind of drift — typing a real command and
silently getting something else. So the tree is asked first, and this table
only sees words Click has no answer for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import rich_click as click

from cli import cli


@dataclass(frozen=True)
class Verb:
    name: str
    summary: str
    # Takes the app and the remaining argv; returns a line for the transcript,
    # or None if the verb has already put its result on screen.
    action: Callable


def _known_to_click(word: str) -> bool:
    return isinstance(cli, click.Group) and word in cli.commands


def registry() -> dict[str, Verb]:
    """Built on call rather than at import, so the actions can close over the
    app without this module importing the surface."""
    from cli.tui.actions import ACTIONS

    return {verb.name: verb for verb in ACTIONS}


def resolve(line: str) -> tuple[Verb, list[str]] | None:
    """The surface verb this line names, if any, and its arguments.

    Returns None for anything Click already answers, so no tb command can be
    shadowed by a verb added here later.
    """
    words = line.split()
    if words and words[0] == "tb":
        words = words[1:]
    if not words:
        return None
    head = words[0]
    if _known_to_click(head):
        return None
    verb = registry().get(head)
    return (verb, words[1:]) if verb else None


def names() -> list[str]:
    """For completion, so surface verbs are as discoverable as real commands."""
    return sorted(name for name in registry() if not _known_to_click(name))
