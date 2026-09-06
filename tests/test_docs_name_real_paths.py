"""A doc naming a source or config file must name one that exists.

stash.flow found the instance from an adopted tree: `docs/rules/testing.md` said
*"use the fixtures in `tests/fixtures.py`"* and no tier has ever shipped that
file. A prescription, in a rules file, naming a helper the reader does not have —
present since the template first existed.

## Three gates were in position and each excluded it by construction

That is the part worth writing down, because none of them was broken.

* `test_docs_name_live_code.py` asks whether a doc names a callable this tree
  *once defined and no longer does*, which it puts to `git log`. A file that was
  never defined is outside that question — and it is outside it because of the
  decision that makes that gate allowlist-free. Its docstring argues, correctly,
  that "every backticked thing must resolve" has a false-positive rate that
  makes it useless. That argument is about **callables**; it got applied to
  paths by adjacency.
* `check_source_doc_refs.py` runs source → doc. This is doc → code, the other
  direction, and its first line says so.
* `check_doc_links.py` reads markdown links. This is a backticked bare path.

## Why the scope is code and config, never `.md`

Measured rather than assumed, on freshly generated trees at three tiers: 31–38
distinct path-shaped backticks each, **one** dangling, and no exemption needed.
Widening to `.md` costs that immediately — a skill naming `../reports/x.md` as an
example, a job prompt naming the report it will write — because a document
naming a document is usually naming one that does not exist *yet*. That is the
docs pipeline's question, and `check_doc_links.py` and the two indexes already
ask it. A source or config path has no such tense: either the file is here or
the sentence is wrong.

The same measurement is why paths resolve against the repo root **or** the citing
document's directory. `docs/TODO/README.md` says `../implementations/`, which is
correct and dangles against the root; seven of the first sixteen findings were
that, and they were the predicate's error rather than the tree's.

## What it enumerates, and what it refuses to

Tracked files, never a walk of the disk. `rglob` reads `.venv/` and
`.pytest_cache/` — six documents from other people's packages in stash.flow's
tree — and the verdict is then **machine-dependent**, which is worse than a
false positive because the second person to hit it cannot reproduce the first
person's red. It passed here for a reason no better than luck: pyright ships a
large bundled README that happens to contain no path-shaped inline code.

Narrative stages are out by role, from `scripts.paths.NARRATIVE`. A plan saying
*"move `scripts/old_check.py` into `scripts/checks/`"* names a path that must
not exist once the plan is done, and a resolve-check fires on it for being a
plan. That set lives in `scripts/paths.py` rather than here because the roles
are the part a generator cannot know: this template ships `docs/TODO/` and can
name it; it cannot know an adopter froze their concept work in `explore/`.

## Why this ships instead of living in the generator

skeletor cannot run it. Its own prose names these files the way a *scaffold*
sees them — `tests/scanning.py`, not `template/core/tests/scanning.py` — because
that is how the reader will meet them, which is the right choice and makes the
paths unresolvable at the generator's root. Measured there: nine template-rooted
references, none dangling, one exemption needed for a placeholder form. The
check is cheap in exactly the coordinate system the generator cannot use, so it
ships, runs in every adopting tree, and reports from all of them.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_files import reference_docs  # noqa: E402

from scanning import scanned  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402

#: Inline code, which is how prose names a file here. A fenced block is the
#: other way, and `test_docs_name_real_commands.py` owns that one — a fence is
#: a command to run, this is a file to open.
_BACKTICKED = re.compile(r"`([^`\n]+)`")

#: Path-shaped: at least one separator, no spaces, no placeholder brackets.
_PATHISH = re.compile(r"^[\w.][\w./-]*/[\w./-]+$")

#: Source and config only — see the docstring. `.md` is the docs pipeline's.
_CODE = (".py", ".yml", ".yaml", ".json", ".toml", ".cfg", ".ini", ".sh", ".txt")


def cited_paths() -> dict:
    """`{cited path: the documents citing it}` for source and config paths.

    Enumeration and scoping both come from `tests/repo_files.py` — tracked
    files only, narrative stages excluded by role. The first version of this
    gate walked the tree with `rglob` and had neither, which is the same slip
    twice: the parts of `test_docs_name_live_code.py` that were argued in prose
    transferred, and the parts that were *implemented* did not.
    """
    found = {}
    for doc in reference_docs():
        for match in _BACKTICKED.finditer(doc.read_text(encoding="utf-8")):
            token = match.group(1).strip()
            if _PATHISH.match(token) and token.endswith(_CODE):
                found.setdefault(token, set()).add(doc)
    return found


def test_the_scan_finds_the_citations():
    """`least` is above 1 because the scan feeds a filter.

    With one citation, "every cited path" and "this cited path" are the same
    set, so the extension filter and the existence test are both unobservable.
    A generated tree cites dozens; a tree citing under ten has had its docs
    renamed out from under this scan.
    """
    scanned(cited_paths(), "source and config paths cited in docs", least=10)


def test_every_cited_path_exists():
    """Resolved against the repo root, or against the citing document.

    **Collected, then asserted once.** An `assert` inside the loop reports the
    alphabetically first finding and says nothing about the rest — which is a
    negative assertion over the remainder, this repository's count-vs-set rule
    with failures substituted for tests. `docs/DEVELOPMENT.md` already ships the
    principle: *"Every gate runs even after one fails. One fix per round trip is
    the thing this exists to avoid."* This gate broke it in the situation where
    the whole list matters most, which is arrival: an adopting tree meets every
    finding at once, and reads one.

    proto.pilot supplied the instance. Theirs landed red with five findings and
    printed one, so they concluded an exclusion they had written was
    unnecessary — it was necessary by three, all of them behind the first
    `assert`, alphabetically.
    """
    dangling = []
    for token, citing in sorted(cited_paths().items(), key=lambda item: item[0]):
        if (PROJECT_ROOT / token).exists() or any((doc.parent / token).exists() for doc in citing):
            continue
        where = ", ".join(sorted(str(doc.relative_to(PROJECT_ROOT)) for doc in citing))
        dangling.append(f"`{token}` — cited by {where}")

    assert not dangling, (
        f"{len(dangling)} cited path(s) are not in this tree — not at the repo root and not "
        "beside the document citing them. A rules file naming a helper the reader does not "
        "have is an instruction that cannot be followed: point each at a real file, or say "
        "what to create.\n  " + "\n  ".join(dangling)
    )
