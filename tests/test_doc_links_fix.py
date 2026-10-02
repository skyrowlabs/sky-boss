"""`check_doc_links.py --fix` repoints a fragment, and refuses to guess.

The refusals are the interesting half. A repair tool that is right most of the
time is worse than none: a fragment repointed to the wrong section reads as
correct forever, whereas a dead one announces itself on the next run. So the
cases below pin what it must **decline** to touch as hard as what it fixes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import check_doc_links as links  # noqa: E402


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A miniature docs tree the checker treats as the whole repo."""
    (tmp_path / "docs").mkdir()
    # Every path the checker reads, not just the root. They are bound at import
    # from `scripts.paths`, so patching the root alone would leave `_suggest`
    # rglobbing the real repository — see scripts/paths.py on why redirecting a
    # tree properly is a design decision rather than a variable.
    monkeypatch.setattr(links, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(links, "DOCS_DIR", tmp_path / "docs")
    monkeypatch.setattr(links, "IGNORE_FILE", tmp_path / ".validate-ignore")
    monkeypatch.setattr(links, "SCAN_ROOTS", ["docs"])

    def write(name: str, body: str) -> Path:
        path = tmp_path / "docs" / name
        path.write_text(body, encoding="utf-8")
        return path

    return write


def test_a_new_root_document_is_enrolled_by_existing(tmp_path, monkeypatch):
    """A fourth root `.md` is checked without anybody adding it to anything.

    This was a hand-written list of the three the template ships, so a fresh
    tree was complete and every real tree diverged from there — most reliably
    through `CHANGELOG.md`, which Release Please writes at the root and which is
    the document most made of links. The checker printed `0 broken links` over
    it: a clean report on a file it had never opened.

    The assertion is on the **set**, not on four names. Naming the fourth would
    reproduce the bug one entry later.
    """
    monkeypatch.setattr(links, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(links, "SCAN_ROOTS", [])
    for name in ("README.md", "CHANGELOG.md", "NOTES.md"):
        (tmp_path / name).write_text("# x\n", encoding="utf-8")
    (tmp_path / "not-markdown.txt").write_text("x\n", encoding="utf-8")

    found = {p.name for p in links.markdown_files()}

    assert found == {"README.md", "CHANGELOG.md", "NOTES.md"}, found


def test_a_broken_link_in_a_root_document_is_reported(tmp_path, monkeypatch):
    """Planted, because a green run after a widening proves nothing.

    The widening above makes the checker *look* at a root document. Only a
    deliberately broken link proves it also *reports* on one — which is the half
    that failed before, and the half a passing suite cannot distinguish from a
    file nobody read.
    """
    monkeypatch.setattr(links, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(links, "DOCS_DIR", tmp_path / "docs")
    monkeypatch.setattr(links, "IGNORE_FILE", tmp_path / ".validate-ignore")
    monkeypatch.setattr(links, "SCAN_ROOTS", [])
    (tmp_path / "NOTES.md").write_text("# N\n\nSee [gone](does-not-exist.md).\n", encoding="utf-8")

    dead_paths, _, _ = links.scan()

    assert any("NOTES.md" in entry for entry in dead_paths), dead_paths


def test_repoints_a_heading_that_grew(tree):
    """The common case: somebody made a heading more specific."""
    source = tree("a.md", "# A\n\nSee [the reason](b.md#why-this-exists).\n")
    tree("b.md", "# B\n\n## Why This Exists As Its Own Checker\n")

    assert links.repoint_fragments() == [
        "docs/a.md: '#why-this-exists' → '#why-this-exists-as-its-own-checker' in docs/b.md"
    ]
    assert "b.md#why-this-exists-as-its-own-checker" in source.read_text(encoding="utf-8")


def test_repoints_a_heading_that_shrank(tree):
    source = tree("a.md", "# A\n\n[x](b.md#testing-rules-for-agents).\n")
    tree("b.md", "# B\n\n## Testing Rules\n")

    assert links.repoint_fragments()
    assert "b.md#testing-rules)" in source.read_text(encoding="utf-8")


def test_refuses_when_two_headings_match(tree):
    """Two candidates means a human chooses. Nothing is written."""
    source = tree("a.md", "# A\n\n[x](b.md#testing).\n")
    tree("b.md", "# B\n\n## Testing Rules\n\n## Testing Budgets\n")
    before = source.read_text(encoding="utf-8")

    assert links.repoint_fragments() == []
    assert source.read_text(encoding="utf-8") == before


def test_refuses_when_no_heading_matches(tree):
    """The section did not move, it went — that is a sentence to rewrite."""
    source = tree("a.md", "# A\n\n[x](b.md#deleted-entirely).\n")
    tree("b.md", "# B\n\n## Something Unrelated\n")
    before = source.read_text(encoding="utf-8")

    assert links.repoint_fragments() == []
    assert source.read_text(encoding="utf-8") == before


def test_never_rewrites_a_broken_path(tree):
    """Where a file went is a judgement call, so `--fix` does not make it."""
    source = tree("a.md", "# A\n\n[x](gone.md#why-this-exists).\n")
    tree("b.md", "# B\n\n## Why This Exists As Its Own Checker\n")
    before = source.read_text(encoding="utf-8")

    assert links.repoint_fragments() == []
    assert source.read_text(encoding="utf-8") == before
    assert links.scan()[0], "the broken path must still be reported"


@pytest.fixture
def sibling(tmp_path, monkeypatch):
    """A repository with a checkout beside it, which `tree` cannot express.

    `tree` puts the repository at `tmp_path` itself, so there is nowhere to
    *be* outside it. This one nests, which makes `../../sibling/GUIDE.md` a
    path that genuinely resolves — and that is the whole difficulty. The link
    is not broken. It is unanswerable.
    """
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (tmp_path / "sibling").mkdir()
    (tmp_path / "sibling" / "GUIDE.md").write_text("# Guide\n\n## Real Heading\n", encoding="utf-8")
    monkeypatch.setattr(links, "PROJECT_ROOT", root)
    monkeypatch.setattr(links, "DOCS_DIR", root / "docs")
    monkeypatch.setattr(links, "IGNORE_FILE", root / ".validate-ignore")
    monkeypatch.setattr(links, "SCAN_ROOTS", ["docs"])

    def write(name: str, body: str) -> Path:
        path = root / "docs" / name
        path.write_text(body, encoding="utf-8")
        return path

    return write


def test_a_link_that_leaves_the_repo_is_named_and_not_judged(sibling, tmp_path):
    """This crashed: `relative_to(PROJECT_ROOT)` on a target outside the root
    raises `ValueError`, so one link into a sibling checkout took the whole
    check down, in a traceback that named pathlib and not the link.

    Both halves are asserted, because the cheap repair is the quieter bug.
    Skipping such a link *silently* would trade a crash for an unchecked link
    inside a clean report, which is the failure this checker exists to prevent.
    """
    guide = tmp_path / "sibling" / "GUIDE.md"
    assert guide.exists(), "only a plant if the target really resolves — otherwise this tests 'does not exist'"
    sibling("a.md", "# A\n\n[out](../../sibling/GUIDE.md#no-such-anchor)\n")

    dead_paths, dead_anchors, outside = links.scan()

    assert (dead_paths, dead_anchors) == ([], []), "a neighbour's headings are not this tree's verdict"
    assert outside == ["docs/a.md: '../../sibling/GUIDE.md#no-such-anchor'"], outside


def test_fix_does_not_repoint_across_a_repo_boundary(sibling, tmp_path):
    """The second `relative_to`, which the first one's crash hid.

    `--fix` runs `repoint_fragments()` before `scan()`, so every run that
    reached the reported crash had already survived this site — and only an
    anchor with exactly one obvious successor gets far enough to format the
    report at all. Two sites, one bug, and the anchor you reach for first
    exercises neither of them.
    """
    guide = tmp_path / "sibling" / "GUIDE.md"
    assert links._successor("heading", links.headings(guide)) == "real-heading", "the fixture must be repointable"
    source = sibling("a.md", "# A\n\n[out](../../sibling/GUIDE.md#heading)\n")
    before = source.read_text(encoding="utf-8")

    assert links.repoint_fragments() == []
    assert source.read_text(encoding="utf-8") == before


def test_a_symlink_out_of_the_repo_is_still_the_repo(sibling, tmp_path):
    """The boundary is where the link points, not where the file ends up.

    `Path.resolve()` follows symlinks, so deciding on the resolved path would
    put every in-repo document that happens to be a symlink out of scope —
    silently, and exactly in the repositories that use one to give a file a
    single home.
    """
    (tmp_path / "sibling" / "SHARED.md").write_text("# Shared\n\n## A Section\n", encoding="utf-8")
    linked = tmp_path / "repo" / "docs" / "shared.md"
    linked.symlink_to(tmp_path / "sibling" / "SHARED.md")
    assert linked.resolve() == (tmp_path / "sibling" / "SHARED.md"), "the plant must actually leave the tree"
    sibling("a.md", "# A\n\n[x](shared.md#gone-entirely)\n")

    _, dead_anchors, outside = links.scan()

    assert outside == [], outside
    assert any("shared.md" in entry for entry in dead_anchors), dead_anchors


def test_leaves_links_inside_code_fences_alone(tree):
    """A link in a fenced example is illustration, not a reference.

    This is what the offset-preserving mask buys: the fix rewrites by position
    in the original text, so a masked region must not be edited *and* must not
    shift the offsets of the links after it.
    """
    source = tree(
        "a.md",
        "# A\n\n```\n[example](b.md#why-this-exists)\n```\n\nReal: [x](b.md#why-this-exists).\n",
    )
    tree("b.md", "# B\n\n## Why This Exists As Its Own Checker\n")

    assert len(links.repoint_fragments()) == 1
    body = source.read_text(encoding="utf-8")
    assert "[example](b.md#why-this-exists)" in body, "the fenced example was rewritten"
    assert "Real: [x](b.md#why-this-exists-as-its-own-checker)." in body


def test_fixes_a_same_file_fragment(tree):
    source = tree("a.md", "# A\n\n[jump](#the-old-name)\n\n## The Old Name Of This Section\n")

    assert links.repoint_fragments()
    assert "(#the-old-name-of-this-section)" in source.read_text(encoding="utf-8")


def test_fix_is_idempotent(tree):
    """A second run has nothing to do — the first one made the link valid."""
    tree("a.md", "# A\n\n[x](b.md#why-this-exists).\n")
    tree("b.md", "# B\n\n## Why This Exists As Its Own Checker\n")

    assert len(links.repoint_fragments()) == 1
    assert links.repoint_fragments() == []
    assert links.scan() == ([], [], [])
