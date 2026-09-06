"""Every test file declares which environment runs it.

This is what makes marker-based registration work: a file joins a suite by
declaring a marker, and nothing else needs updating — no CI step, no runner
case, no CLI entry. The guarantee only holds if *every* file declares one, so an
undeclared file fails the unit suite rather than silently never running.
"""

from __future__ import annotations

import configparser
import re
import sys
import tomllib
from pathlib import Path

import pytest

from scanning import scanned

pytestmark = [pytest.mark.unit]

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cli.test_cmds import SUITES  # noqa: E402


def declared_markers() -> set:
    """The marker vocabulary, read from the config pytest itself reads.

    It was a literal here, which made a fourth home for one list: this set,
    `tests/pytest.ini`, `pyproject.toml`, and `SUITES` in `cli/test_cmds.py`.
    Nothing checked them, and `tests/pytest.ini` carries the instruction *"keep
    the two in sync"* — the shape this shell's own history says loses.

    Deriving matters more than tidiness, because of `--strict-markers`: a marker
    in this set but absent from the config is one pytest **refuses to collect**,
    while this check blesses every file using it. The gate that enforces markers
    would be certifying a vocabulary the runner rejects.
    """
    config = configparser.ConfigParser()
    config.read(TESTS_DIR / "pytest.ini")
    return {line.split(":")[0].strip() for line in config["pytest"]["markers"].strip().splitlines()}


_PYTESTMARK = re.compile(r"^pytestmark\s*=\s*(?P<value>.+)$", re.MULTILINE)
_MARKER = re.compile(r"pytest\.mark\.(?P<name>\w+)")


def _test_files():
    return scanned(
        sorted(p for p in TESTS_DIR.rglob("test_*.py") if "__pycache__" not in p.parts),
        f"test_*.py under {TESTS_DIR}",
    )


def test_every_test_file_declares_a_suite_marker():
    undeclared = []
    for path in _test_files():
        source = path.read_text(encoding="utf-8")
        match = _PYTESTMARK.search(source)
        if not match:
            undeclared.append(str(path.relative_to(TESTS_DIR)))
            continue
        if not _MARKER.findall(match.group("value")):
            undeclared.append(str(path.relative_to(TESTS_DIR)))

    assert not undeclared, (
        "These test files declare no module-wide pytestmark, so no suite runs them:\n  "
        + "\n  ".join(undeclared)
        + "\n\nAdd one at module level, e.g.  pytestmark = [pytest.mark.unit]"
    )


def test_declared_markers_are_registered():
    """A typo'd marker silently matches nothing — --strict-markers only catches
    markers pytest is *asked* about, not ones a file assigns itself."""
    unknown = {}
    for path in _test_files():
        match = _PYTESTMARK.search(path.read_text(encoding="utf-8"))
        if not match:
            continue
        names = set(_MARKER.findall(match.group("value"))) - declared_markers()
        if names:
            unknown[str(path.relative_to(TESTS_DIR))] = sorted(names)

    assert not unknown, f"Unregistered markers (add them to tests/pytest.ini): {unknown}"


def test_every_config_declares_the_same_markers():
    """`tests/pytest.ini` and `pyproject.toml` must agree about the vocabulary.

    Two configs exist for a real reason — pytest reads the nearest one, so the
    root copy applies when it is invoked without a `tests/` path and the inner
    one when it is not — and the reason does not make them safe. They drift the
    ordinary way: somebody adds a suite, edits the file they had open, and the
    new suite works from one directory and errors from the other under
    `--strict-markers`.

    Recomputed from both files rather than compared against a list here, which
    would be a fifth home for the same set.
    """
    root = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = {m.split(":")[0].strip() for m in root["tool"]["pytest"]["ini_options"]["markers"]}

    drift = sorted(declared ^ declared_markers())

    assert not drift, f"pyproject.toml and tests/pytest.ini disagree about markers: {drift}"


def test_every_suite_the_cli_offers_is_a_declared_marker():
    """A suite the CLI can run must be one pytest will collect.

    `SUITES` carries help text and whether the suite needs the stack, so it is
    not a copy of the vocabulary and cannot be derived from it. What it must not
    do is name a marker nothing declares: under `--strict-markers` that suite
    errors on every invocation, and the failure reads as a broken test run
    rather than as a typo in a registry.
    """
    unknown = set(SUITES) - declared_markers()

    assert not unknown, f"the CLI offers suites pytest will not collect: {sorted(unknown)}"
