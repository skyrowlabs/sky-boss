"""Tab completion, derived from the command tree rather than described again.

Same reasoning as dispatch: a hand-written list of commands to complete is a
list somebody forgets to update, and the completion that drifts from the CLI is
worse than none because it teaches the wrong verb. Everything here is read off
Click's own objects and the same registries `tb run` dispatches from.
"""

from __future__ import annotations

import rich_click as click

from cli import cli

def _positional_candidates(command: click.Command) -> list[str]:
    """Nothing yet.

    This used to complete job and task names off the registries. Both went with
    the job layer; the hook stays because completing a positional is the thing a
    surface is for, and the next registry that lands should plug in here rather
    than growing a second completion path.
    """
    return []


def resolve(path: list[str], root: click.Command | None = None) -> click.Command:
    """Walk as deep into the tree as the typed words go.

    Anything that is not a subcommand — an option, a value, an argument — is
    stepped over rather than stopping the walk, so `group verb thing --ru` still
    completes against `group verb`.

    ``root`` exists for the same reason `dispatch` takes one: the real tree is
    two leaf commands at the moment, which is not enough shape to test a walk
    against. The surface always passes the real one.
    """
    command: click.Command = root or cli
    for token in path:
        if isinstance(command, click.Group) and token in command.commands:
            command = command.commands[token]
    return command


def _option_names(command: click.Command) -> list[str]:
    options = {
        opt
        for param in command.params
        for opt in getattr(param, "opts", [])
        if opt.startswith("--")
    }
    # Root flags stay reachable at any depth, the way they are on the CLI.
    options.update({"--json", "--help"})
    return sorted(options)


def candidates(line: str, root: click.Command | None = None) -> tuple[str, list[str]]:
    """The token being typed, and everything it could become.

    Split on whitespace rather than with shlex: a half-typed quote is normal
    while typing and must not raise where the user would only see a dead key.
    """
    words = line.split()
    if not line or line.endswith((" ", "\t")):
        prefix, path = "", words
    else:
        prefix, path = (words[-1] if words else ""), words[:-1]

    if path and path[0] == "tb":
        path = path[1:]

    command = resolve(path, root)

    if prefix.startswith("-"):
        pool = _option_names(command)
    elif isinstance(command, click.Group):
        pool = sorted(command.commands)
        if command is (root or cli):
            # Surface verbs are typed at the top level like any other word, so
            # they complete like one. `names()` drops anything Click already
            # owns, so this can never offer a shadowed verb.
            from cli.tui.verbs import names as surface_verbs

            pool = sorted(set(pool) | set(surface_verbs()))
    else:
        pool = _positional_candidates(command)

    return prefix, [name for name in pool if name.startswith(prefix)]


def _common_prefix(names: list[str]) -> str:
    if not names:
        return ""
    shortest = min(names, key=len)
    for index, char in enumerate(shortest):
        if any(name[index] != char for name in names):
            return shortest[:index]
    return shortest


def complete(line: str, root: click.Command | None = None) -> tuple[str, list[str]]:
    """The line after completing it, and any ambiguity left to show.

    A single match is filled in and a space added, because the next thing is
    always another word. Several matches extend as far as they agree and then
    hand back the list — the shell contract everyone already has in their
    fingers.
    """
    prefix, matches = candidates(line, root)
    if not matches:
        return line, []
    if len(matches) == 1:
        return line[: len(line) - len(prefix)] + matches[0] + " ", []

    shared = _common_prefix(matches)
    if len(shared) > len(prefix):
        return line[: len(line) - len(prefix)] + shared, matches
    return line, matches
