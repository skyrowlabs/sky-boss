"""`.env.example` and the source agree about which environment names exist.

The file's own header says every value the application reads must appear in
it, and ran in one direction only: it shipped `<PREFIX>_ENV` and `LOG_LEVEL`
for the template's whole life and nothing read either, in any adopter tree.
Both directions are held now. A name declared here is read somewhere in the
tracked source; a `<PREFIX>_*` name the source reads is declared here.

The read side is scoped to the shell's prefix, `<PREFIX>` from
`STATE_ROOT_ENV`. A product sharing that prefix is in scope, and its settings
are declared like the shell's: stash.flow's prefix is `STASH`, and its six
product names were real findings. A product under another prefix is not. Tests
are left out of the read side, because a fixture's `monkeypatch.setenv` names a
variable it invented (sky.boss). A declared name is "read" if it appears as a
word in any tracked source file, tests included: the readers go through
constants (`STATE_ROOT_ENV`), so a call-site regex would miss them.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from scripts.paths import PROJECT_ROOT, STATE_ROOT_ENV, TESTS_DIR
from tests.scanning import scanned

pytestmark = pytest.mark.unit

ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
PREFIX = STATE_ROOT_ENV.rsplit("_STATE_ROOT", 1)[0]
_DECLARED = re.compile(r"^#?\s*([A-Z][A-Z0-9_]*)=", re.MULTILINE)
SOURCE_SUFFIXES = {".py", ".sh", ".yml", ".yaml", ".toml", ".cjs", ".js", ".mjs", ".ts"}
#: A name, not a parenthesised tuple: at a 3.14 target black rewrites `except (A, B):`.
_UNREADABLE = (UnicodeDecodeError, OSError)


def declared() -> set[str]:
    return set(_DECLARED.findall(ENV_EXAMPLE.read_text(encoding="utf-8")))


def source_text(tests: bool = True) -> str:
    names = subprocess.run(
        ["git", "ls-files", "-z"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=True
    ).stdout.split("\0")
    out = []
    for name in names:
        path = PROJECT_ROOT / name
        if not name or path.suffix not in SOURCE_SUFFIXES or not path.is_file():
            continue
        if not tests and path.is_relative_to(TESTS_DIR):
            continue
        try:
            out.append(path.read_text(encoding="utf-8"))
        except _UNREADABLE:
            continue
    return "\n".join(out)


def test_every_declared_name_is_read_somewhere():
    names = scanned(declared(), "names declared in .env.example", least=1)
    text = source_text()
    dead = sorted(n for n in names if not re.search(rf"\b{re.escape(n)}\b", text))
    assert not dead, f".env.example declares names nothing in the tree reads: {dead}"


def prefixed_names_read(text: str) -> set[str]:
    """`<PREFIX>_*` names the source reads as environment: quoted, or `$VAR` in shell.

    Not any identifier with the prefix: a Python constant called `PROBE_DIR` in
    a tree whose CLI is `probe` is a path, and the grid found exactly that.
    """
    quoted = rf"""(?<=["']){re.escape(PREFIX)}_[A-Z0-9_]+(?=["'])"""
    shell = rf"\$\{{?({re.escape(PREFIX)}_[A-Z0-9_]+)"
    return set(re.findall(quoted, text)) | set(re.findall(shell, text))


def test_every_prefixed_name_the_source_reads_is_declared():
    text = source_text(tests=False)
    read = scanned(prefixed_names_read(text), f"{PREFIX}_* names in source", least=1)
    undeclared = sorted(read - declared())
    assert not undeclared, f"the source reads {PREFIX}_* names .env.example does not declare: {undeclared}"
