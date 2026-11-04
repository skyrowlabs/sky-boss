"""The lint pins agree everywhere they are written down.

Two versions of a formatter disagree about real formatting. When
`.pre-commit-config.yaml` and CI hold different pins, a file passes locally and
fails in CI with a diff nobody can explain from the error message — the tool
name is the same, so the version never occurs to anyone.

**Three places decide, and none of them is canonical.** `.pre-commit-config.yaml`
pins the commit hook; `scripts/requirements.txt` pins what CI and your `.venv`
install; and what is actually installed is what `dev check` runs. This file
used to call the first one the source of truth, and both halves of that were
wrong.

It named a direction it cannot know. The governed tier's Dependabot updates
`/scripts` — pip cannot write `.pre-commit-config.yaml` — so every lint bump
arrives in `requirements.txt` first, the suite goes red, and the message said
*update requirements.txt*: revert the bot. sky.boss's pull request sat red for
six days on exactly that, `pyright 1.1.411` against `1.1.414`. Which side is
behind is a fact about the last commit, not about the files, so the message says
*make these agree* and names both.

And it compared two declarations while the value that decides the outcome sat
one call away. node-zero's two pins both said `isort==9.0.1` and this was green,
while the `.venv` that `dev check pre-push` runs held 8.0.1 — the tree
formatted under one isort in the hook and another in the check, both passed, and
the gate whose docstring is about exactly that could not see it. That is not the
account-level class that has no instrument: `importlib.metadata` answers it.
"""

from __future__ import annotations

import re
import sys
from fnmatch import fnmatch
from importlib import metadata
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import GITHUB_DIR, PROJECT_ROOT, REQUIREMENTS  # noqa: E402
from tests.scanning import scanned  # noqa: E402

PRECOMMIT = PROJECT_ROOT / ".pre-commit-config.yaml"

#: repo slug fragment -> the name it goes by in requirements.txt
TOOLS = {"flake8": "flake8", "black": "black", "isort": "isort", "pyright": "pyright"}


def _precommit_pins() -> dict:
    text = PRECOMMIT.read_text(encoding="utf-8")
    pins = {}
    # `rev:` for hosted repos; `pyright@X.Y.Z` for the local node-hosted hook.
    for repo, rev in re.findall(r"- repo: https://\S*?/([\w.-]+)\n\s+rev: v?([\d.]+)", text):
        for tool in TOOLS:
            if tool in repo.lower():
                pins[tool] = rev
    for tool, version in re.findall(r"'(\w+)@([\d.]+)'", text):
        if tool in TOOLS:
            pins[tool] = version
    return pins


def _requirements_pins() -> dict:
    pins = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([\d.]+)", line.strip())
        if match and match.group(1) in TOOLS.values():
            pins[match.group(1)] = match.group(2)
    return pins


def test_every_lint_tool_is_pinned_in_precommit():
    pins = _precommit_pins()
    missing = sorted(set(TOOLS) - set(pins))
    assert not missing, f"Unpinned in .pre-commit-config.yaml: {missing}"


def test_requirements_match_precommit():
    precommit, requirements = _precommit_pins(), _requirements_pins()
    mismatched = {
        tool: (precommit[tool], requirements.get(tool))
        for tool in precommit
        if requirements.get(tool) != precommit[tool]
    }
    assert not mismatched, (
        "scripts/requirements.txt disagrees with .pre-commit-config.yaml "
        f"(pre-commit, requirements): {mismatched}\n"
        "Make these agree — at whichever version you mean. If a bot just bumped one "
        "of them, that is usually the newer pin and the other file is the one behind; "
        "a pip updater can only ever write requirements.txt."
    )


def test_installed_tools_match_requirements():
    """What this interpreter has installed is what the pins say.

    Asked of the interpreter running the suite, which is the tree's `.venv` when
    the suite runs the way `dev test` runs it — the same environment
    `dev check` shells out of. A tool missing from it is reported rather than
    skipped: the question is whether the check and the hook run the same
    formatter, and "not installed here" is not a yes.
    """
    requirements = _requirements_pins()
    drift = {}
    for tool, pinned in sorted(requirements.items()):
        try:
            installed = metadata.version(tool)
        except metadata.PackageNotFoundError:
            installed = "not installed"
        if installed != pinned:
            drift[tool] = (pinned, installed)
    assert requirements, "found no lint tool pinned in scripts/requirements.txt, so this compared nothing"
    assert not drift, (
        f"{sys.executable} does not have what scripts/requirements.txt pins "
        f"(pinned, installed): {drift}\n"
        "Reinstall from scripts/requirements.txt. Until you do, the commit hook and "
        "the check format with different versions of one tool, and both pass. A "
        "major bump can reformat files, so give the reinstall its own commit if it "
        "does."
    )


def covers(entry: dict, directory: str) -> bool:
    """Whether a Dependabot entry updates `directory`: named there, or at an ancestor.

    An entry at `/` updates `scripts/requirements.txt` too (sky.boss, measured),
    so matching the directory exactly passed vacuously there.
    """
    named = [entry["directory"]] if "directory" in entry else list(entry.get("directories") or [])
    for spelled in named:
        root = "/" + str(spelled).strip("/")
        if root == "/" or directory == root or directory.startswith(root + "/") or fnmatch(directory, root):
            return True
    return False


def test_dependabot_never_bumps_a_lint_pin_alone():
    """A pip update reaching the requirements file ignores every tool above.

    pip writes `requirements.txt` only, so a lint bump arrives red against
    `.pre-commit-config.yaml` and never merges (mind-head's ruff and mypy, added
    to `TOOLS` and not to the ignore list). No dependabot.yml, or no pip entry
    reaching that file, means nothing bumps these pins, and there is nothing to ask.
    """
    import yaml

    config = GITHUB_DIR / "dependabot.yml"
    if not config.exists():
        return
    directory = "/" + REQUIREMENTS.parent.relative_to(PROJECT_ROOT).as_posix()
    entries = [
        entry
        for entry in (yaml.safe_load(config.read_text(encoding="utf-8")) or {}).get("updates") or []
        if entry.get("package-ecosystem") == "pip" and covers(entry, directory)
    ]
    for entry in entries:
        ignored = {rule.get("dependency-name") for rule in entry.get("ignore") or []}
        unignored = sorted(set(TOOLS.values()) - ignored)
        assert not unignored, (
            f".github/dependabot.yml's pip update for {entry.get('directory') or entry.get('directories')} "
            f"would bump {unignored} alone; add each to its `ignore:` list, since a bump of one pin is red "
            "against the other"
        )


def test_an_entry_reaches_the_requirements_file_from_an_ancestor():
    scanned(
        [d for d in ("/", "/scripts", "scripts/", "/scr*") if covers({"directory": d}, "/scripts")],
        "spellings reaching /scripts",
        least=4,
    )
    assert covers({"directories": ["/app", "/"]}, "/scripts")
    assert not covers({"directory": "/app"}, "/scripts")
