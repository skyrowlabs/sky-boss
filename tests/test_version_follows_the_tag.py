"""`VERSION` is never behind the newest release tag, and what Release Please bumps agrees with it.

Release Please bumps from the manifest, so a tree switched from tag versioning
arrives at the template's `0.1.0` while already tagged later, and its first
release PR measures from the wrong number (the v0.72.0 switch rehearsal). Ahead
is fine: a release PR raises `VERSION` before its tag exists.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import GITHUB_DIR, PROJECT_ROOT  # noqa: E402

VERSION = PROJECT_ROOT / "VERSION"
MANIFEST = GITHUB_DIR / ".release-please-manifest.json"


def numbers(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version.split("-")[0])[:3])


def newest_tag() -> str | None:
    """The newest `v<digits>` tag reachable from HEAD, or None when there is none."""
    found = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    return found.stdout.strip() or None if found.returncode == 0 else None


def test_the_manifest_agrees_with_version():
    if not VERSION.exists():
        return  # versioned by tag alone
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8")).get(".")
    version = VERSION.read_text(encoding="utf-8").strip()
    disagree = f"{MANIFEST.name} says {recorded!r} and VERSION {version!r}"
    assert recorded == version, f"{disagree}; Release Please reads the manifest"


def test_version_is_not_behind_the_newest_tag():
    tag = newest_tag()
    if not VERSION.exists() or tag is None:
        return  # versioned by tag alone, or nothing released yet
    version = VERSION.read_text(encoding="utf-8").strip()
    released = tag.lstrip("v")
    assert numbers(version) >= numbers(tag), (
        f"VERSION is {version} but {tag} is already released here, so the next release "
        f"PR would measure from {version}. Seed both: printf '%s\\n' {released} > VERSION, "
        f'and set "." to "{released}" in {MANIFEST.relative_to(PROJECT_ROOT)}.'
    )


def test_a_version_behind_a_tag_is_seen():
    assert numbers("0.1.0") < numbers("v0.3.0") and numbers("0.4.0") >= numbers("v0.3.0")
    assert numbers("1.2.3-rc.1") == (1, 2, 3)


def versioned_extra_files() -> list[tuple[str, str]]:
    """`(path, version)` for each json `extra-files` entry at `$.version` that holds one."""
    config = GITHUB_DIR / "release-please-config.json"
    if not config.exists():
        return []
    found = []
    for package in json.loads(config.read_text(encoding="utf-8")).get("packages", {}).values():
        for entry in package.get("extra-files") or []:
            path = PROJECT_ROOT / entry.get("path", "") if isinstance(entry, dict) else None
            if not path or entry.get("type") != "json" or entry.get("jsonpath") != "$.version":
                continue
            if path.is_file():
                version = json.loads(path.read_text(encoding="utf-8")).get("version")
                if isinstance(version, str):
                    found.append((entry["path"], version))
    return found


def test_every_versioned_extra_file_agrees_with_version():
    """Release Please bumps these with VERSION, so they must start equal (dream-doll)."""
    if not VERSION.exists():
        return  # versioned by tag alone
    version = VERSION.read_text(encoding="utf-8").strip()
    behind = [f"{path} says {found}" for path, found in versioned_extra_files() if found != version]
    assert not behind, f"VERSION is {version}, but " + "; ".join(behind) + ". Set each to VERSION's number."
