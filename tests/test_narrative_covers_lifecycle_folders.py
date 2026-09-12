"""Every documented lifecycle folder has a role, and the role is written down.

`scripts/paths.py::NARRATIVE` is the set of directories whose documents describe
**a state other than the present one** — a plan naming a file it intends to
create, a memo naming code it ruled out. Every resolve-check excludes them by
role, because firing on them is firing on the thing they exist to do.

`docs/rules/docs.md` publishes the folder table an adopter files by. Those two
have to agree, and for `docs/research/` they did not: it is described there as
holding "a thing that is **not a plan**", where "rejected ideas keep their memo
rather than being deleted", and it was absent from `NARRATIVE`. stash.flow found
it by filing 17 documents of concept work exactly where the table says to and
watching a resolve-check redden on one for citing a path that is supposed to be
dead. Nothing failed upstream, because a fresh scaffold ships that folder empty
— the disagreement is only observable once somebody uses it.

**A partition, not a list.** Every folder in the table is either narrative or
declared present-tense with a reason. The alternative is what happened: a folder
whose absence from `NARRATIVE` is indistinguishable from a decision that it does
not belong there. Both directions are checked, so an entry that stops being true
fails rather than sitting as a decision nobody re-made.

**Both halves of the partition live in `scripts/paths.py`, and this file reads
them.** `PRESENT_TENSE` shipped here for one release and was a second home for a
ruling `NARRATIVE`'s own comment already carries — so an adopter who accepted
that comment's invitation and appended a folder found this file red, telling
them to delete an entry inside a shipped test. That edit is precisely the
divergence the append seam next to `NARRATIVE` exists to prevent. dream.doll and
stash.flow hit the two assertions independently, from real runs, on the same
day. Classify a folder once, in the file that argues the case.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import DOCS_DIR, NARRATIVE, PRESENT_TENSE, PROJECT_ROOT, SCRIPTS_DIR  # noqa: E402
from tests.scanning import scanned  # noqa: E402

#: The file the seam and the region live in. Read as text, not imported: the
#: question is where a line SITS, which importing the module cannot answer.
PATHS_FILE = SCRIPTS_DIR / "paths.py"

RULES = DOCS_DIR / "rules" / "docs.md"


def _table_folders() -> list:
    """The `docs/...` locations named in the lifecycle table of `docs/rules/docs.md`.

    Scoped to the table whose header names a Location column, so prose
    elsewhere in the file that mentions a folder is not read as a row.
    """
    lines = RULES.read_text(encoding="utf-8").splitlines()
    found, inside = [], False
    for line in lines:
        if line.startswith("|") and "Location" in line:
            inside = True
            continue
        if inside and not line.startswith("|"):
            break
        if inside:
            found += [match.rstrip("/") for match in re.findall(r"`(docs/[^`]+)`", line)]
    return found


def _is_narrative(folder: str) -> bool:
    """True when the folder is in NARRATIVE, or under one taken at its parent."""
    path = PROJECT_ROOT / folder
    return any(path == role or role in path.parents for role in NARRATIVE)


def test_every_lifecycle_folder_is_classified() -> None:
    """No folder in the published table is left without a role."""
    folders = scanned(_table_folders(), f"lifecycle folders in {RULES.name}", least=2)
    unclassified = [f for f in folders if not _is_narrative(f) and f not in PRESENT_TENSE]
    assert not unclassified, (
        f"{RULES.name} tells an adopter to file in {unclassified}, and "
        f"scripts/paths.py says nothing about whether those describe the present. "
        f"Append them to NARRATIVE or PRESENT_TENSE in that file's "
        f"`Your own lifecycle folders` region, with the reason."
    )


def test_no_present_tense_entry_has_gone_stale() -> None:
    """An exemption is checked against the thing it exempts, on every run."""
    folders = _table_folders()
    gone = [f for f in PRESENT_TENSE if f not in folders]
    assert not gone, (
        f"PRESENT_TENSE (scripts/paths.py) names {gone}, which {RULES.name} no longer lists — "
        f"an exemption is a decision only while the thing it exempts exists. Remove it as an "
        f"append in that file's `Your own lifecycle folders` region, rather than as an edit to "
        f"the literal:\n" + "".join(f"    PRESENT_TENSE.pop({f!r}, None)\n" for f in gone)
    )
    both = [f for f in PRESENT_TENSE if _is_narrative(f)]
    assert not both, (
        f"PRESENT_TENSE (scripts/paths.py) names {both}, which NARRATIVE now covers. One folder, "
        f"one role. Remove it as an append in that file's `Your own lifecycle folders` region — "
        f"the template owns the lines inside that literal and edits them, so a removal spelled "
        f"there conflicts on every upgrade:\n" + "".join(f"    PRESENT_TENSE.pop({f!r}, None)\n" for f in both)
    )


#: Append-shaped lines, which are the ones the region exists to hold. The set is
#: the spellings `scripts/paths.py` offers, and it is deliberately not a general
#: python parse: an adopter writes one of these idioms or they are not following
#: the seam at all, and a regex that matched more would start firing on the
#: template's own prose about them.
_APPEND_IDIOMS = (
    re.compile(r"^\s*NARRATIVE\s*\+="),
    re.compile(r"^\s*NARRATIVE\s*=\s*tuple\("),
    re.compile(r"^\s*PRESENT_TENSE\s*\|="),
    re.compile(r"^\s*PRESENT_TENSE\s*\.(update|pop)\("),
    re.compile(r"^\s*PRESENT_TENSE\["),
)

_REGION_MARKER = "# ── Your own lifecycle folders"


def test_your_appends_are_inside_the_region() -> None:
    """An append above the marker keeps the old behaviour and says nothing about it.

    **The silent state this exists for.** When the region arrived, an existing
    append merged cleanly and git ordered it either side of the marker depending
    on exactly where it sat — so a tree could take the release, see zero
    conflicts, and still be holding its append hard against the prose block the
    template edits. It keeps the pre-region behaviour, a clean first merge and a
    conflict on the next re-run, while every signal says it is covered.

    `scripts/paths.py` claimed the append always landed below. It does not, and
    the claim was generalised from one synthetic case. dream.doll measured the
    counterexample and asked for this check instead of a corrected sentence,
    which is the right trade: placement is a fact about this file, so this file's
    own suite can settle it and nobody has to believe a release note.

    Vacuous on a fresh scaffold, which ships no appends — so what is asserted is
    that the MARKER was found. Without that this passes on a file the region was
    deleted from, which is the one edit that would make it matter.
    """
    lines = PATHS_FILE.read_text(encoding="utf-8").splitlines()
    marker = [i for i, line in enumerate(lines) if line.startswith(_REGION_MARKER)]
    scanned(marker, f"`{_REGION_MARKER}` markers in {PATHS_FILE.name}", least=1)
    assert len(marker) == 1, (
        f"{PATHS_FILE.name} has {len(marker)} region markers. An adopter cannot be told to append "
        f"below `the` marker unless there is exactly one."
    )

    above = [
        f"{PATHS_FILE.name}:{number}: {line.strip()}"
        for number, line in enumerate(lines[: marker[0]], start=1)
        if any(idiom.match(line) for idiom in _APPEND_IDIOMS)
    ]
    assert not above, (
        "these appends sit ABOVE the `Your own lifecycle folders` marker:\n  "
        + "\n  ".join(above)
        + "\n\nThey work today and will conflict on the next upgrade that re-runs before the base "
        "advances, because they share an insertion point with the template's own text. Move them "
        "below the marker — it is a cut and paste, and nothing else has to change. If one arrived "
        "there by an upgrade rather than by you, that is expected: git placed it, and moving it is "
        "the whole remedy."
    )
