"""A folder is routed by a row for **itself**, never by a row for something inside it.

The predicate `check_doc_tables.py` enforces:

    A subfolder is routed by its own `README.md` or its own path. A routed
    folder is not descended into, because its row owns everything below it.

Two properties of it are subtle enough to regress silently, and neither is
visible in the pass/fail of a tree that happens to be correct today.

**The exactness rule.** `docs/reports/regular/README.md` must not vouch for
`docs/reports/`. It is the reason the directory pattern is a second regex with a
lookahead rather than a branch of the file one, and getting it wrong makes the
check green for a folder nobody routed -- the exact failure it exists to catch.

**Not descending into a routed folder.** This is what keeps `docs/implementations/spec/`
out of scope with no special case, and it must hold at any depth: a depth cutoff
gets the same answer here by accident and the wrong one for a future
`docs/reports/releases/v1.2/`.

Written by proto.pilot against this template's API and adopted here, so the
predicate's tests ship beside the script rather than in one adopter's tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_doc_tables as tables
from scripts.check_doc_tables import _DOC_DIR, _DOC_PATH, unrouted

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "text",
    [
        "`docs/reports/regular/README.md`",
        "`docs/rules/docs.md`",
        "| **Rules** | rules/testing.md | `docs/rules/testing.md` |",
    ],
)
def test_a_row_for_a_file_never_routes_its_folder(text: str) -> None:
    assert _DOC_DIR.findall(text) == [], "a file row vouched for its parent folder"


@pytest.mark.parametrize(
    "text,expected",
    [("`docs/rules/`", "docs/rules/"), ("(`docs/reports/regular/`)", "docs/reports/regular/")],
)
def test_a_row_for_a_folder_routes_it(text: str, expected: str) -> None:
    assert _DOC_DIR.findall(text) == [expected]


def test_nested_documents_are_seen_at_all(tmp_path: Path) -> None:
    """The bug that made the reverse check decorative below the top level."""
    assert _DOC_PATH.findall("`docs/rules/testing.md`") == ["docs/rules/testing.md"]
    assert _DOC_PATH.findall("`docs/reports/releases/v1.2/audit.md`") == ["docs/reports/releases/v1.2/audit.md"]


def _tree(root: Path, *relative: str) -> None:
    for rel in relative:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# doc\n", encoding="utf-8")


def test_an_unrouted_folder_is_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tables, "PROJECT_ROOT", tmp_path)
    _tree(tmp_path, "docs/parked/idea.md")
    assert unrouted(tmp_path / "docs", set()) == (["docs/parked"], [])


def test_a_routed_folder_owns_everything_below_it(tmp_path: Path, monkeypatch) -> None:
    """No depth cutoff: the walk stops at the routed folder, however deep it goes."""
    monkeypatch.setattr(tables, "PROJECT_ROOT", tmp_path)
    _tree(tmp_path, "docs/archive/README.md", "docs/archive/spec/one.md", "docs/archive/spec/deep/two.md")

    by_readme = unrouted(tmp_path / "docs", {"docs/archive/README.md"})
    assert by_readme == ([], ["docs/archive"]), "a routed folder was descended into"

    by_path = unrouted(tmp_path / "docs", {"docs/archive"})
    assert by_path == ([], ["docs/archive"]), "routing by path did not stop the walk"


def test_routing_a_child_does_not_route_its_parent(tmp_path: Path, monkeypatch) -> None:
    """The exactness rule, end to end rather than at the regex."""
    monkeypatch.setattr(tables, "PROJECT_ROOT", tmp_path)
    _tree(tmp_path, "docs/reports/regular/README.md", "docs/reports/stray.md")

    stranded, routed = unrouted(tmp_path / "docs", {"docs/reports/regular/README.md"})
    assert stranded == ["docs/reports"], "the child's row vouched for the parent"
    assert routed == ["docs/reports/regular"]


#: Every path is one the template ships and cannot lose: `dev check doc-refs` reads
#: a `docs/` path in a comment as a claim. `docs/reports/` holds no `.md` of its
#: own, so the walk has to descend through it rather than stop at it.
FIXTURE_DOCS = [
    "docs/rules/commits.md",
    "docs/TODO/README.md",
    "docs/TODO/_TEMPLATE.md",
    "docs/reports/regular/README.md",
]


@pytest.mark.parametrize(
    "row,expected",
    [
        ("- **Rules** (`docs/rules/`)", ["docs/rules"]),
        ("- **Backlog** (`docs/TODO/README.md`)", ["docs/TODO"]),
        ("- **Deep** (`docs/reports/regular/README.md`)", ["docs/reports/regular"]),
        ("- **A plan template** (`docs/TODO/_TEMPLATE.md`)", []),
    ],
    ids=lambda v: v[:40] if isinstance(v, str) else "",
)
def test_a_table_row_routes_through_to_the_walk(row: str, expected: list, tmp_path: Path, monkeypatch) -> None:
    """From a table row to the folders the walk reports routed, with nothing skipped.

    The template's own test (`tests/test_docs_pipeline.py`) asks `referenced()`
    what a row routes. That proves the set; this proves the consumer of the set
    agrees, which is the only place the three ways of routing a folder meet.
    """
    monkeypatch.setattr(tables, "PROJECT_ROOT", tmp_path)
    _tree(tmp_path, *FIXTURE_DOCS)
    table = tmp_path / "DOCS_INDEX.md"
    table.write_text(row + "\n", encoding="utf-8")
    monkeypatch.setattr(tables, "TABLES", [table])

    _, routed = tables.unrouted(tmp_path / "docs", tables.referenced())
    assert routed == expected, f"{row!r} routed {routed}, expected {expected}"
