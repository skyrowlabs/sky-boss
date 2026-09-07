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


def _normalise(value) -> list:
    """One shape for a setting, whichever file it was read from.

    `pyproject.toml` gives a real list and a real int; `pytest.ini` gives a
    string that may be newline-separated. Comparing them raw would report every
    key as drifted, which is a gate nobody can keep green.
    """
    if isinstance(value, str):
        return [line.strip() for line in value.strip().splitlines() if line.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value]
    return [str(value).strip()]


def _ini_settings() -> dict:
    config = configparser.ConfigParser()
    config.read(TESTS_DIR / "pytest.ini")
    return {key: _normalise(value) for key, value in config["pytest"].items()}


def _toml_settings() -> dict:
    root = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return {key: _normalise(value) for key, value in root["tool"]["pytest"]["ini_options"].items()}


#: Resolved against rootdir, which differs between the two files by
#: construction. Compared for presence, never for value. See the note below.
_ROOTDIR_RELATIVE = frozenset({"pythonpath", "testpaths"})


def test_every_config_declares_the_same_settings():
    """`tests/pytest.ini` and `pyproject.toml` must agree about every key.

    Two configs exist for a real reason — pytest reads the nearest one, so the
    root copy applies when it is invoked without a `tests/` path and the inner
    one when it is not — and the reason does not make them safe. They drift the
    ordinary way: somebody adds a setting, edits the file they had open, and the
    suite behaves one way from `tests/` and another from the root.

    **This compared `markers` and nothing else**, while the two files also share
    `addopts`, `filterwarnings` and `timeout` — one of four keys gated, and the
    one gated was the one whose drift is loudest under `--strict-markers`. So
    the quiet three were the unguarded ones. sky.boss hit the general form with
    an async suite that collected and never ran under one invocation and ran
    under the other, because `asyncio_mode` was set in a single file.

    Both directions, and every key: a setting present in one file and absent
    from the other is exactly the async case, and it is invisible to any check
    that only compares the keys they happen to share.

    Recomputed from both files rather than compared against a list here, which
    would be a third home for every one of these settings.
    """
    ini, toml = _ini_settings(), _toml_settings()
    # `least=4`: the four keys this template ships. A scan feeding a comparison
    # is unobservable at one key, and at zero it would agree with anything.
    scanned(sorted(set(ini) | set(toml)), "settings across the two pytest configs", least=4)

    only_ini = sorted(set(ini) - set(toml))
    only_toml = sorted(set(toml) - set(ini))
    # **Presence is compared for every key; value for every key that is not a
    # path.** `pythonpath` and `testpaths` are resolved against *rootdir*, and
    # rootdir is whichever directory holds the config pytest found — so the two
    # files necessarily spell the same two paths differently (`..`/`.` against
    # `.`/`tests`) and textual identity is the *wrong* assertion for them. There
    # is no assignment that satisfies it while both files stay correct: this
    # tree measured `rootdir: …/tests, configfile: pytest.ini` for a run given
    # `tests/`, and `rootdir: …/sky-boss, configfile: pyproject.toml` without.
    #
    # Local divergence from the template, reported upstream the day the widened
    # check shipped — it is the first tree to set either key in both files.
    # Presence is still compared, which is what catches the async case the
    # widening exists for: a key in one file and not the other.
    differ = sorted(key for key in set(ini) & set(toml) if key not in _ROOTDIR_RELATIVE and ini[key] != toml[key])

    assert not (only_ini or only_toml or differ), (
        "tests/pytest.ini and pyproject.toml disagree — pytest reads whichever is nearest, so a "
        "suite behaves differently depending on the path it was invoked with.\n"
        f"  only in tests/pytest.ini: {only_ini or 'none'}\n"
        f"  only in pyproject.toml:   {only_toml or 'none'}\n"
        f"  set in both, different:   {differ or 'none'}"
    )


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
