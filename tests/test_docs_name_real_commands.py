"""A command written in a `bash` block is a command this CLI actually has.

The developer guide's **first command did not exist**, for long enough that it
shipped. `AGENTS.md` explained on the same page that it never had — the two
files were separate copies of one instruction, and nothing could see them
disagree. That is the failure this repository's Rule 1 is about, arriving in
prose rather than in code.

## Why this reads code blocks and not prose

The obvious version — every `dev <word>` anywhere in the docs must resolve —
cannot be built. A doc legitimately names a command that does not exist in at
least three ways, and they are indistinguishable to a matcher:

1. **Narrative about something never implemented.** `AGENTS.md` explains that an
   earlier draft opened with a `setup` subcommand the CLI has never had. Naming
   it is the point of the sentence.
2. **Narrative about a wrong name.** A repo with two binaries warns readers
   about typing the other one. The command is named *as the error to recognise*.
3. **A plan for something unbuilt.** A spec in the holding tank naming the
   commands it will add is what a plan **is** — unboundedly, forever.

A fenced ```bash block is different in kind: it is not describing a command, it
is telling you to run one. That single scoping rule removes all three classes,
because each of them is a sentence. Class 3 is excluded twice over, since the
tank is skipped by role — the same exclusion `test_docs_name_live_code.py` makes,
read from `scripts/paths.py` rather than spelled again.

Measured rather than assumed, on a freshly generated tree: 24 invocations inside
bash blocks, 0 false positives. The prose two paragraphs above names `setup`
three times and is correctly ignored.

## Its neighbour is not a copy of it

``test_docs_name_live_code.py`` sits beside this one and the two names differ by
one word. They share the by-role exclusion above and nothing else: that one asks
git whether a doc names a *callable* this repository once defined and removed;
this one asks the click registry whether a *command* somebody is being told to
run exists. Different inputs, different oracles, neither subsuming the other.
Whoever tidies this directory later should merge neither into the other — the
survivor would silently stop asking one of the two questions.

## Why it introspects click instead of running anything

Walking the group tree is exact and costs nothing. Shelling out `--help` per
command would be two dozen subprocesses to learn what the registry already
knows, and would make the check depend on the venv being built.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import click  # noqa: E402

from scanning import scanned  # noqa: E402
from scripts.paths import PROJECT_ROOT, TODO_DIR  # noqa: E402
from tests.shell import group  # noqa: E402

#: `--shell-package` moves the package, never the group inside it — see
#: `tests/shell.py`.
ROOT = group()

CLI_NAME = "dev"

#: A fenced shell block. `console` and `sh` are included because a doc that
#: picked a different fence label is making the same claim.
BLOCK = re.compile(r"```(?:bash|sh|console)\n(.*?)```", re.DOTALL)

#: `dev <group> [<command>]`, however it is introduced — bare, `./`-prefixed,
#: or mid-line after a pipe or `&&`.
INVOCATION = re.compile(rf"(?:^|\s|\./)\b{re.escape(CLI_NAME)}\s+([a-z][a-z-]*)(?:\s+([a-z][a-z-]*))?")


def known_commands() -> set:
    """Every valid command path, from click's own registry."""
    paths = set()

    def walk(command, prefix: tuple) -> None:
        for name, child in getattr(command, "commands", {}).items():
            paths.add(prefix + (name,))
            if isinstance(child, click.Group):
                walk(child, prefix + (name,))

    walk(ROOT, ())
    return paths


def invocations() -> dict:
    """Every command a shell block tells a reader to run, and where."""
    found: dict = {}
    for path in sorted(PROJECT_ROOT.rglob("*.md")):
        if TODO_DIR in path.parents or "node_modules" in path.parts or ".venv" in path.parts:
            continue
        for body in BLOCK.findall(path.read_text(encoding="utf-8", errors="replace")):
            for raw in body.splitlines():
                line = raw.split("#")[0].strip()
                match = INVOCATION.search(line) if line else None
                if match:
                    parts = tuple(group for group in match.groups() if group)
                    found.setdefault(parts, set()).add(str(path.relative_to(PROJECT_ROOT)))
    return scanned(found, f"`{CLI_NAME} ...` invocation(s) in shell blocks")


def test_every_documented_command_exists():
    known = known_commands()
    dead = []
    for parts, where in sorted(invocations().items()):
        if parts in known or any(path[: len(parts)] == parts for path in known):
            continue
        dead.append(f"{CLI_NAME} {' '.join(parts)} — in {', '.join(sorted(where))}")

    assert not dead, (
        "shell blocks telling a reader to run a command this CLI does not have:\n  "
        + "\n  ".join(dead)
        + f"\nRun `./{CLI_NAME} --help` for what exists. If the doc is describing a command "
        "rather than prescribing it, take it out of the ```bash block — that is the line "
        "this check draws."
    )
