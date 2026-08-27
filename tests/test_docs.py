"""Cross-document links. See CLAUDE.md § Feature workflow.

The convention is `[[slug]]`, never a relative path, and the reason is in
CLAUDE.md: *a path breaks the moment that feature reopens* — a doc moving
between `docs/features/` and `docs/features/done/` would invalidate every
reference to it. Slugs survive that move.

**What they do not survive is never having been written.** The rot moved
rather than went away: on 2026-08-27 this suite gained the check and
immediately found two slugs pointing at documents that did not exist — `keys`,
cited from `cli/resident.py` twice and from `tests/test_keys.py`, and `theme`,
cited from `cli/banner.py` and from the header doc itself. Both had been dead
long enough that nobody could say when they broke, which is exactly the
argument for a test rather than a habit.

(Those two are named in backticks rather than in the link form, because this
file is inside the tree it scans — writing the example as a real reference
made the check fail on its own docstring. That is the check working.)

So this is the slug-shaped version of a dead-link checker. It is deliberately
not a general Markdown link checker: `[[slug]]` is the only cross-reference
form this repo uses, and checking the one form that exists beats checking five
that do not.
"""

import re
from pathlib import Path

import pytest

from cli.helpers import PROJECT_ROOT

# `[[…]]` is also legal prose when the subject *is* the convention. Each entry
# names a slug that is written down deliberately and resolves to nothing.
ALLOWED: dict[str, str] = {
    # The literal placeholder, in the sentence that defines the convention.
    "slug": "the convention's own placeholder, not a reference",
    # [[tools]] round 2's record of the 2026-08-22 rename, which rewrote 16
    # links that pointed at `[[toolbox]]`. Naming the old slug is the point of
    # the sentence; resolving it would mean the rename had not happened.
    "toolbox": "a dated record of a slug that was retired",
}

LINK = re.compile(r"\[\[([a-z0-9][a-z0-9-]*)\]\]")
SEARCHED = {".md", ".py", ".js", ".css", ".toml", ".html"}
SKIPPED = {".git", ".venv", "vendor", "node_modules", "__pycache__"}


def _slugs_on_disk() -> dict[str, Path]:
    """Every doc that a `[[slug]]` could name, keyed by its stem."""
    return {p.stem: p for p in (PROJECT_ROOT / "docs").rglob("*.md")}


def _references() -> dict[str, set[str]]:
    """Every `[[slug]]` written anywhere, mapped to the files writing it."""
    found: dict[str, set[str]] = {}
    for path in PROJECT_ROOT.rglob("*"):
        if path.suffix not in SEARCHED or not path.is_file():
            continue
        if SKIPPED & set(path.parts):
            continue
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for match in LINK.finditer(text):
            rel = str(path.relative_to(PROJECT_ROOT))
            found.setdefault(match.group(1), set()).add(rel)
    return found


def test_every_slug_reference_resolves_to_a_document():
    """A `[[slug]]` naming nothing is worse than a relative path naming
    nothing, because it *looks* like it survived the move that broke it."""
    docs = _slugs_on_disk()
    dangling = {
        slug: sorted(where)
        for slug, where in _references().items()
        if slug not in docs and slug not in ALLOWED
    }
    assert not dangling, "slug references with no docs/**/<slug>.md: " + "; ".join(
        f"[[{slug}]] cited by {', '.join(where)}" for slug, where in sorted(dangling.items())
    )


def test_the_allowlist_does_not_outlive_its_reason():
    """An allowlist entry that starts resolving is no longer an exception, and
    an entry nobody writes any more is a line to delete. Either way the list
    has stopped describing the tree."""
    docs, refs = _slugs_on_disk(), _references()
    for slug, why in ALLOWED.items():
        assert slug not in docs, (
            f"[[{slug}]] is allowlisted as {why!r} but docs/**/{slug}.md now exists — "
            "drop the entry and let the real check cover it"
        )
        assert slug in refs, (
            f"[[{slug}]] is allowlisted as {why!r} but nothing writes it any more — "
            "drop the entry"
        )


@pytest.mark.parametrize("required", ["open", "ideas", "fundamentals"])
def test_the_documents_claude_md_promises_are_there(required):
    """CLAUDE.md sends a reader to these by name. It is the first thing a new
    contributor reads, and the repo went public with more than one of those."""
    assert required in _slugs_on_disk(), f"CLAUDE.md refers to docs/**/{required}.md"
