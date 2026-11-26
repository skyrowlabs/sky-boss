"""One reader for the one question this tree asks of `.skeletor.json`: which paths it names.

The manifest is the scaffolder's record of what it wrote, and it is a supported
deletion — so every answer here is three-valued. `skeletor_wrote(path)` is
`True`, `False`, or `None` when there is no manifest to ask, and a caller that
collapses `None` into either answer makes the coverage-baseline mistake
(measuring the template and calling it yours) in the reassuring direction.

Before this module `check_coverage_budget.py`, `tests/test_coverage_population.py`
and mind.head's own `tests/test_lint_exemptions.py` each parsed the file, each
right about the key its caller used. Not cached: a caller that points it at a
synthetic manifest (the coverage tests do) must get that manifest's answer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.paths import PROJECT_ROOT, SCAFFOLD_MANIFEST

#: A name, not a parenthesised tuple: at a 3.14 target black rewrites `except (A, B):`.
_UNREADABLE = (OSError, ValueError)


def scaffolded_paths(path: Path = SCAFFOLD_MANIFEST) -> frozenset[str] | None:
    """Every repo-relative path the manifest at `path` names, or `None` without a readable one."""
    files = recorded_hashes(path)
    return None if files is None else frozenset(files)


def recorded_hashes(path: Path = SCAFFOLD_MANIFEST) -> dict[str, str] | None:
    """`{repo-relative path: hash of what skeletor wrote}`, or `None` without a readable manifest."""
    if not path.exists():
        return None
    try:
        files: dict[str, str] = json.loads(path.read_text(encoding="utf-8")).get("files", {})
    except _UNREADABLE:
        return None
    return files


def skeletor_wrote(path: Path | str, manifest: Path = SCAFFOLD_MANIFEST) -> bool | None:
    """Whether the scaffolder wrote `path`; `None` when there is no manifest to ask."""
    names = scaffolded_paths(manifest)
    if names is None:
        return None
    rel = Path(path)
    if rel.is_absolute():
        rel = rel.relative_to(PROJECT_ROOT)
    return rel.as_posix() in names


#: The README's version badge, which `skeletor-upgrade` moves with `skeletor_ref`.
VERSION_BADGE = PROJECT_ROOT / "docs" / "assets" / "skeletor-version.svg"
#: The badge names the bare tag a ref starts with, or `untagged` (the scaffolder's rule).
_BARE_TAG = re.compile(r"v\d+\.\d+\.\d+(?=-|$)")
_BADGE_VALUE = re.compile(r'aria-label="skeletor: ([^"]+)"')


def badge_value(ref: str) -> str:
    """What the version badge says for `ref`."""
    match = _BARE_TAG.match(ref)
    return match.group(0) if match else "untagged"


def unfinished_upgrade(path: Path = SCAFFOLD_MANIFEST, badge: Path = VERSION_BADGE) -> list[str]:
    """Why the manifest at `path` records an upgrade that has not finished; empty when it has.

    A held-back run leaves `pending_added`, and a committed one hides that the base
    never advanced. A badge that disagrees with `skeletor_ref` says the same thing.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except _UNREADABLE:
        return []
    if not isinstance(data, dict):
        return []
    found = []
    pending = data.get("pending_added") or {}
    if pending:
        found.append(f"pending_added holds {len(pending)} file(s) a held-back run added: {sorted(pending)}")
    shown, ref = badge_says(badge), data.get("skeletor_ref") or ""
    if shown and shown != badge_value(ref):
        found.append(f"{badge.name} says {shown}, and skeletor_ref is {ref or 'missing'}")
    return found


def badge_says(badge: Path = VERSION_BADGE) -> str | None:
    """The value the version badge shows, or `None` without one."""
    if not badge.is_file():
        return None
    shown = _BADGE_VALUE.search(badge.read_text(encoding="utf-8"))
    return shown.group(1) if shown else None
