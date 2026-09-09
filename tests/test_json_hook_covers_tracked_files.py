"""`check-json`'s exclude, against the JSON this repository actually tracks.

The hook parses every tracked `.json` as strict JSON, and JSONC files — `//`
comments, trailing commas — are not that. Two ship here already
(`pyrightconfig.json`, and `.vscode/settings.json` written by
`scripts/gen_vscode_queries.py`), so the exclude is a list, and a list is the
thing this repository's Rule 2 says to be suspicious of: **it goes stale by
addition.** Add a third JSONC file and nothing complains until `pre-commit run
--all-files` fails on the commit that adds it, which is the commit where it
reads as your mistake rather than as a config that never covered you.

That is not hypothetical. The template shipped exactly this: `.vscode/settings.json`
arrived, the exclude still named `pyrightconfig.json` alone, and a fresh tree
could not commit its own generated file. It was invisible upstream because the
scaffolder makes the first commit with `--no-verify` — correctly, the hooks are
not installed yet — so the failure lands on the adopter's *second* commit.

**Both directions, because an exclude is an allowlist.** An entry whose file
became real JSON has outlived its reason, and leaving it is worse than untidy:
the path can come back later for something that genuinely is JSON and arrive
pre-exempted, which is an exemption nobody chose.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import PROJECT_ROOT  # noqa: E402
from tests.repo_files import tracked  # noqa: E402
from tests.scanning import scanned  # noqa: E402

PRECOMMIT = PROJECT_ROOT / ".pre-commit-config.yaml"


def _tracked_json() -> list:
    """Tracked `.json`, as the repo-relative names pre-commit matches against."""
    return [path.relative_to(PROJECT_ROOT).as_posix() for path in tracked("*.json")]


def _check_json_exclude() -> str:
    """The `exclude:` regex the config gives `check-json`, read not repeated.

    Bounded to the hook's own block: an unbounded search would fall through to
    the next hook's exclude when this one has none, and answer confidently with
    somebody else's pattern.
    """
    config = PRECOMMIT.read_text(encoding="utf-8")
    block = re.search(r"- id: check-json\b.*?(?=\n\s*- id: |\n\s*- repo: |\Z)", config, re.S)
    assert block, "no check-json hook in .pre-commit-config.yaml"
    found = re.search(r"^\s+exclude: '([^']*)'", block.group(0), re.M)
    return found.group(1) if found else ""


def _parses(path: Path) -> bool:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return False
    return True


def test_every_tracked_json_the_hook_sees_is_parseable() -> None:
    """What `check-json` is handed, it can read."""
    exclude = _check_json_exclude()
    pattern = re.compile(exclude) if exclude else None
    seen = scanned(_tracked_json(), "tracked .json files")
    excluded = {name for name in seen if pattern and pattern.match(name)}
    unreadable = [name for name in seen if name not in excluded and not _parses(PROJECT_ROOT / name)]
    assert not unreadable, (
        f"these are tracked, not excluded, and are not strict JSON, so "
        f"`pre-commit run --all-files` fails on them: {unreadable}. "
        f"If they are JSONC on purpose, add them to check-json's exclude in "
        f"{PRECOMMIT.name} with the reason."
    )


def test_no_exclusion_has_outlived_its_reason() -> None:
    """An excluded file that parses fine is an entry to delete, not to keep."""
    exclude = _check_json_exclude()
    if not exclude:
        pytest.skip("check-json has no exclude in this tree")
    pattern = re.compile(exclude)
    excluded = [name for name in _tracked_json() if pattern.match(name)]
    # Not `scanned`: an exclude that matches nothing tracked is itself the
    # finding this test reports, and asserting non-empty first would raise the
    # wrong error for it.
    assert excluded, f"check-json excludes {exclude!r}, which matches no tracked file — a dead entry"
    stale = [name for name in excluded if _parses(PROJECT_ROOT / name)]
    assert not stale, (
        f"these are excluded from check-json but parse as strict JSON, so the "
        f"exclusion no longer buys anything: {stale}. Delete the entry rather "
        f"than re-justifying it — a path that comes back later for real JSON "
        f"would arrive pre-exempted."
    )
