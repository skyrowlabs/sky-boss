"""Every entry in `scripts/doc_refs_allowlist.yaml` still exempts a reference that exists.

The file this replaced (`.github/scripts/.validate-ignore`) was a fifth
allowlist with no reasons and no staleness check, outside the `*_allowlist.yaml`
pattern the other four share — so an entry whose reference had been repointed
stayed forever, and the path could come back for a real doc pre-exempted.
Measured on a fresh tree: a meaningless entry appended, every gate green.
"""

from __future__ import annotations

import pytest

from scripts import allowlist
from scripts.paths import SCRIPTS_DIR
from tests.repo_files import present
from tests.scanning import scanned

pytestmark = pytest.mark.unit

ALLOWLIST = SCRIPTS_DIR / "doc_refs_allowlist.yaml"

#: A name rather than a parenthesised tuple in the `except`: at a 3.14 target
#: black rewrites `except (A, B):` into PEP 758's `except A, B:`, so the literal
#: is not black-clean at every `--python` this renders. Same as the checker.
_UNREADABLE = (UnicodeDecodeError, OSError)


def _tracked_text() -> str:
    """The tree as it stands: tracked or not yet staged, never a file already deleted.

    `ls-files` alone read the index, so a file an upgrade had just written kept
    its entries "stale" until staged, and a deleted one kept them alive (stash.flow).
    """
    out = []
    for path in present("*"):
        if path == ALLOWLIST or not path.is_file():
            continue
        try:
            out.append(path.read_text(encoding="utf-8"))
        except _UNREADABLE:
            continue
    return "\n".join(out)


def test_every_entry_still_exempts_something():
    entries = allowlist.read(ALLOWLIST)
    scanned(entries, "doc-reference exemptions", least=1)
    text = _tracked_text()
    stale = allowlist.stale(entries, lambda key: None if key in text else "nothing in the tree references it")
    assert not stale, "\n".join(stale)
