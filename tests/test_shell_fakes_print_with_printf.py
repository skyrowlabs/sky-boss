"""A `/bin/sh` fake in this suite prints an expansion with `printf`, never `echo`.

dash, `/bin/sh` on Ubuntu runners, expands backslash escapes in `echo`'s
arguments, and bash does not. A fake that echoes a variable holding `\\n`
prints one thing on a host whose `/bin/sh` is bash and another in CI (v0.82.0).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanning import scanned  # noqa: E402
from scripts.paths import TESTS_DIR  # noqa: E402

pytestmark = pytest.mark.unit

SHEBANGS = ("#!/bin/sh", "#!/usr/bin/env sh")
ECHO_EXPANSION = re.compile(r"\becho\s+[^;|&]*\$")


def literals(source: str) -> list[str]:
    """Every string literal, an f-string's constant parts joined in order."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            found.append("".join(str(part.value) for part in node.values if isinstance(part, ast.Constant)))
    return found


def sh_fakes(paths: list[Path]) -> list[tuple[Path, str]]:
    return [
        (path, text)
        for path in paths
        for text in literals(path.read_text(encoding="utf-8"))
        if text.lstrip().startswith(SHEBANGS)
    ]


def echoes(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if ECHO_EXPANSION.search(line)]


def test_no_sh_fake_echoes_an_expansion() -> None:
    fakes = scanned(sh_fakes(sorted(TESTS_DIR.rglob("*.py"))), "/bin/sh fakes in tests/")
    found = [f"{path.name}: {line}" for path, text in fakes for line in echoes(text)]
    assert not found, "use printf '%s\\n' \"$VAR\" instead:\n" + "\n".join(found)


def test_the_predicate_tells_an_expansion_from_a_literal() -> None:
    bang = SHEBANGS[0]
    assert echoes(f'{bang}\necho "$*" >> log\n') == ['echo "$*" >> log']
    assert echoes(f"{bang}\necho refused >&2; exit 1\nprintf '%s\\n' \"$X\"\n") == []
