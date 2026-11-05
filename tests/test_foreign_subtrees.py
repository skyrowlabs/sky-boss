"""`is_foreign` matches a declared subtree and what is under it, and nothing else.

Every walking check reads it, so a prefix match that caught `vendored/` for
`vendor` would silently drop this tree's own files from all of them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import paths  # noqa: E402


@pytest.mark.parametrize(
    "rel, foreign",
    [
        ("vendor", True),
        ("vendor/lib/x.py", True),
        (Path("vendor") / "docs" / "a.md", True),
        ("vendored/x.py", False),
        ("src/vendor/x.py", False),
        ("notes/x.md", False),
    ],
)
def test_a_declared_subtree_and_only_it_is_foreign(monkeypatch, rel, foreign):
    monkeypatch.setattr(paths, "FOREIGN", ("vendor",))
    assert paths.is_foreign(rel) is foreign


def test_every_declared_subtree_is_a_directory_here():
    missing = [entry for entry in paths.FOREIGN if not (paths.PROJECT_ROOT / entry).is_dir()]
    assert not missing, f"FOREIGN names subtrees this tree does not have: {missing}. Delete the append."
