"""Every entry in `scripts/doc_refs_allowlist.yaml` still exempts a reference that exists.

The file this replaced (`.github/scripts/.validate-ignore`) was a fifth
allowlist with no reasons and no staleness check, outside the `*_allowlist.yaml`
pattern the other four share — so an entry whose reference had been repointed
stayed forever, and the path could come back for a real doc pre-exempted.
Measured on a fresh tree: a meaningless entry appended, every gate green.
"""

from __future__ import annotations

import subprocess

import pytest

from scripts import allowlist
from scripts.paths import PROJECT_ROOT, SCRIPTS_DIR
from tests.scanning import scanned

pytestmark = pytest.mark.unit

ALLOWLIST = SCRIPTS_DIR / "doc_refs_allowlist.yaml"

#: A name rather than a parenthesised tuple in the `except`: at a 3.14 target
#: black rewrites `except (A, B):` into PEP 758's `except A, B:`, so the literal
#: is not black-clean at every `--python` this renders. Same as the checker.
_UNREADABLE = (UnicodeDecodeError, OSError)


def _tracked_text() -> str:
    names = subprocess.run(
        ["git", "ls-files", "-z"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=True
    ).stdout.split("\0")
    out = []
    for name in names:
        path = PROJECT_ROOT / name
        if not name or path == ALLOWLIST or not path.is_file():
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
