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
from pathlib import Path

from scripts.paths import PROJECT_ROOT, SCAFFOLD_MANIFEST


def scaffolded_paths(path: Path = SCAFFOLD_MANIFEST) -> frozenset[str] | None:
    """Every repo-relative path the manifest at `path` names, or `None` without a readable one."""
    if not path.exists():
        return None
    try:
        files = json.loads(path.read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError):
        return None
    return frozenset(files)


def skeletor_wrote(path: Path | str, manifest: Path = SCAFFOLD_MANIFEST) -> bool | None:
    """Whether the scaffolder wrote `path`; `None` when there is no manifest to ask."""
    names = scaffolded_paths(manifest)
    if names is None:
        return None
    rel = Path(path)
    if rel.is_absolute():
        rel = rel.relative_to(PROJECT_ROOT)
    return rel.as_posix() in names
