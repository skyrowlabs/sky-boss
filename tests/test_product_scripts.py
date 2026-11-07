"""Each `[project.scripts]` entry answers for its commands, the way the shell does.

The shell's gates read one CLI. A tree's product CLI was covered by none of them, so a
doc could name a command it no longer has. Each entry is its own population with its
own runner and no floor, since a tree may declare none.

`--help` only, in process, because a product's argument-less commands collect, block on
a terminal or rewrite data. `SMOKE_EXECUTES` does not apply. A group's own callback
still runs on the way to a subcommand's `--help`, as it does for anyone who types it.

Commands are walked by shape rather than by `isinstance`: Typer carries its own copy
of click, so its groups are not `click.Group`. An entry that cannot be imported or
walked is a finding, never a skip, or it would leave the population in silence.

The shell's output contract stays out: a product's output is not the shell's to rule.
"""

from __future__ import annotations

import contextlib
import functools
import importlib
import io
import re
import sys
import tomllib
from pathlib import Path

import click
import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_files import reference_docs  # noqa: E402
from scripts import allowlist  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402
from tests.test_docs_name_real_commands import BLOCK  # noqa: E402

ALLOWLIST = Path(__file__).resolve().parent / "product_scripts_allowlist.yaml"
SOURCES = (PROJECT_ROOT, PROJECT_ROOT / "src")
#: A name, not a parenthesised tuple: at a 3.14 target black rewrites `except (A, B):`.
_IMPORT_FAILURES = (Exception, SystemExit)


def declared(pyproject: Path = PROJECT_ROOT / "pyproject.toml") -> dict[str, str]:
    """`{script name: "module:attribute"}`, empty for a tree with no such table."""
    if not pyproject.exists():
        return {}
    return tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {}).get("scripts", {})


def load(target: str):
    """The command `target` names, normalised; raises `LookupError` saying why it cannot be walked."""
    module_name, _, attribute = target.partition(":")
    sys.path[:0] = [str(path) for path in SOURCES if str(path) not in sys.path]
    try:
        found = importlib.import_module(module_name)
        for part in attribute.split("."):
            found = getattr(found, part)
    except _IMPORT_FAILURES as error:
        raise LookupError(f"{target} cannot be imported: {error!r}") from error
    if type(found).__module__.split(".")[0] == "typer":
        found = importlib.import_module("typer.main").get_command(found)
    if not callable(getattr(found, "main", None)) or not hasattr(found, "params"):
        raise LookupError(f"{target} is {type(found).__name__}, not a click or Typer command, so it cannot be walked")
    return found


def children(command) -> dict:
    return getattr(command, "commands", None) or {}


def paths(command, prefix: tuple = ()) -> list[tuple]:
    """The path to every command under `command`, groups included, itself first."""
    found = [prefix]
    for name, child in sorted(children(command).items()):
        found += paths(child, (*prefix, name))
    return found


def help_failure(command, path: tuple, name: str) -> str | None:
    """Why `<name> <path> --help` failed, in process, or None."""
    typed = " ".join((name, *path))
    out = io.StringIO()
    code: object = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            command.main(args=[*path, "--help"], prog_name=name)
    except SystemExit as stopped:
        code = stopped.code or 0
    except Exception as error:
        return f"`{typed} --help` raised {error!r}"
    if code != 0:
        return f"`{typed} --help` exited {code}: {out.getvalue().strip()[-200:]}"
    return None if out.getvalue().strip() else f"`{typed} --help` printed nothing"


def dead_word(command, words: tuple) -> tuple | None:
    """The path up to the first word `command` has no such subcommand for, or None.

    Only as deep as groups go: a word after a leaf is a positional, and so is one a
    group takes as an argument.
    """
    node = command
    for depth, word in enumerate(words, start=1):
        if not hasattr(node, "commands"):
            return None
        if word not in children(node):
            takes_words = any(getattr(p, "param_type_name", "") == "argument" for p in node.params)
            return None if takes_words else words[:depth]
        node = children(node)[word]
    return None


def invocation(name: str) -> re.Pattern:
    """`<name>` in command position, `.venv/bin/` or `./` allowed, then its leading bare words."""
    start = r"(?:^|(?:&&|\|\||[;|$])\s*)(?:\./)?(?:\.venv/bin/)?"
    return re.compile(rf"{start}{re.escape(name)}((?:\s+[a-z][a-z0-9-]*)*)")


def documented(name: str) -> dict:
    """`{words: docs naming them}` for every run of `name` a shell block prescribes."""
    pattern = invocation(name)
    found: dict = {}
    for doc in sorted(reference_docs()):
        for body in BLOCK.findall(doc.read_text(encoding="utf-8", errors="replace")):
            for raw in body.splitlines():
                match = pattern.search(raw.split("#")[0].strip())
                if match:
                    found.setdefault(tuple(match.group(1).split()), set()).add(str(doc.relative_to(PROJECT_ROOT)))
    return found


@functools.lru_cache(maxsize=1)
def findings() -> tuple:
    """Every `(key, message)` an entry owes an answer for, before the allowlist is read."""
    found = []
    for name, target in sorted(declared().items()):
        try:
            command = load(target)
        except LookupError as error:
            found.append((name, str(error)))
            continue
        for path in paths(command):
            failure = help_failure(command, path, name)
            if failure:
                found.append((" ".join((name, *path)), failure))
        for words, where in sorted(documented(name).items()):
            dead = dead_word(command, words)
            if dead:
                typed = " ".join((name, *dead))
                found.append((typed, f"`{typed}` is in a shell block in {', '.join(sorted(where))} and is no command"))
    return tuple(found)


def covers(key: str, finding_key: str) -> bool:
    return finding_key == key or finding_key.startswith(f"{key} ")


def test_every_entry_answers_for_its_commands():
    excused = allowlist.read(ALLOWLIST)
    open_findings = [message for key, message in findings() if not any(covers(entry, key) for entry in excused)]
    assert not open_findings, (
        "\n".join(open_findings) + f"\nFix the command or the doc, or say why in {ALLOWLIST.name}."
    )


def test_no_entry_in_the_allowlist_has_outlived_its_reason():
    keys = [key for key, _ in findings()]
    stale = allowlist.stale(
        allowlist.read(ALLOWLIST),
        lambda entry: None if any(covers(entry, key) for key in keys) else "it excuses nothing",
    )
    assert not stale, "\n".join([*stale, allowlist.STALE_ADVICE])


def sample() -> click.Group:
    @click.group()
    def top() -> None:
        pass

    @top.group()
    def sub() -> None:
        pass

    @sub.command()
    @click.argument("thing")
    def leaf(thing: str) -> None:
        raise AssertionError("a help walk must never run a command")

    return top


def test_a_word_after_a_leaf_is_a_positional_and_a_word_in_a_group_is_a_command():
    top = sample()
    assert dead_word(top, ("sub", "leaf", "anything", "at-all")) is None
    assert dead_word(top, ("sub", "nope", "leaf")) == ("sub", "nope")
    assert dead_word(top, ("nope",)) == ("nope",)
    assert dead_word(top, ()) is None


def test_the_walk_reaches_every_level_and_help_runs_nothing():
    top = sample()
    assert paths(top) == [(), ("sub",), ("sub", "leaf")]
    assert all(help_failure(top, path, "tool") is None for path in paths(top))


def test_a_nonzero_help_is_reported_with_what_it_said():
    @click.command()
    @click.option("--help", is_eager=True, is_flag=True, callback=lambda *_: sys.exit(2))
    def stone() -> None:
        pass

    assert "exited 2" in (help_failure(stone, (), "tool") or "")


def test_the_venv_form_and_a_chain_are_commands_and_a_mention_is_not():
    pattern = invocation("my-tool")
    assert pattern.search(".venv/bin/my-tool sub leaf x").group(1).split() == ["sub", "leaf", "x"]
    assert pattern.search("true && my-tool sub --flag leaf").group(1).split() == ["sub"]
    assert pattern.search("npm run my-tool sub") is None


def test_an_object_that_is_no_command_cannot_be_walked():
    with pytest.raises(LookupError, match="cannot be walked"):
        load("os.path:join")
    with pytest.raises(LookupError, match="cannot be imported"):
        load("no_such_module_here:main")


def test_a_missing_table_is_an_empty_population(tmp_path):
    assert declared(tmp_path / "pyproject.toml") == {}
    (tmp_path / "pyproject.toml").write_text('[project.scripts]\nmy-tool = "pkg.cli:main"\n', encoding="utf-8")
    assert declared(tmp_path / "pyproject.toml") == {"my-tool": "pkg.cli:main"}
