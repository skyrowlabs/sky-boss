#!/usr/bin/env python3
"""Where an append seam's space is, and which comment lines around it are the template's.

A seam is a file that invites an append in so many words, and bounds a space for
it between two frozen rules. `tests/test_narrative_covers_lifecycle_folders.py`
asks the questions; this module is the one home for **finding** the answers,
because two callers need them and they must agree: the test that reads a tree,
and the scaffolder that records what the template wrote.

## Why a record exists at all

The invitation says *"appends, and any prose you write about them"* go between
the rules. For a release only the appends half was checked — `_appends()` parses
the AST, and a comment is not in the AST — so an adopter's paragraph planted
directly above the opening rule passed a 732-test suite (proto.pilot), and a
whole comment block moved from inside the region into the template's prose
passed 227 (stash.flow, the third time that finding was filed). Prose sitting
hard against the template's last line is exactly what cost proto.pilot a
conflict per release for three releases, while its appends were fine throughout.

The tree cannot tell its own comment from the template's by looking: both are
`#` lines. What separates them is who wrote them, and only the scaffolder knows
that. So at scaffold time it records a digest of every comment line outside the
space, per seam file, in `scripts/seam_prose.json` — and the test asks whether
the tree still carries exactly those, in that order, and names each one it does
not recognise.

That record is a second home for a fact, which this template normally refuses.
It earns the place the way `.skeletor.json`'s hashes do: it is checked against
its source on every run, so it cannot drift unnoticed, and it is written by the
scaffolder and by an upgrade's head render, never by hand.

## What it does not see, on purpose

- **A template comment you deleted.** Removing template prose is a divergence,
  but it does not put your text at the template's insertion point, which is the
  hazard. Only lines the record does not recognise are reported.
- **Prose that is not a comment.** A docstring or a string literal is code, and
  the append check owns code.
- **Your comment on a code line** (`FOO = 1  # mine`). Full-line comments only.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import detail, fail, ok  # noqa: E402
from scripts.paths import PROJECT_ROOT, SCRIPTS_DIR  # noqa: E402

RECORD = SCRIPTS_DIR / "seam_prose.json"

#: The two rules that bound an adopter's space, and the invitation that makes a
#: file a seam. **Assembled from parts, never spelled**: a detector that contains
#: its own needle is its own first finding, and this module is read by the same
#: discovery it implements.
TERMINATOR = "# ── " + " ".join(("Nothing below", "this line is", "skeletor's"))
CLOSER = "# ── " + " ".join(("Skeletor's again", "below this line"))
INVITATION = (" ".join(("**Add", "your own")), " ".join(("as an", "append")))

#: Directories a walk must not enter. Only the scaffolder walks — at that moment
#: the tree is a fresh render with no `.git`, so git cannot be asked — and the
#: test enumerates through git instead.
_SKIP = {"__pycache__", "node_modules", "tmp"}


def invites(text: str) -> bool:
    """Whether this source invites an append, in those words."""
    return all(mark in text for mark in INVITATION)


def bounds(lines: List[str]) -> Dict[str, List[int]]:
    """1-based line numbers of each rule. Callers assert there is exactly one of each."""
    return {
        name: [number for number, line in enumerate(lines, start=1) if line.startswith(rule)]
        for name, rule in (("opening", TERMINATOR), ("closing", CLOSER))
    }


def _digest(line: str) -> str:
    return hashlib.sha256(line.rstrip().encode("utf-8")).hexdigest()[:12]


def outside_comments(lines: List[str]) -> List[Tuple[int, str]]:
    """Every full-line comment outside the space, as (1-based line, digest).

    Both rule lines are outside by this definition, and the frozen block under
    each is too — they are the template's, so they are in the record like any
    other of its lines.
    """
    found = bounds(lines)
    if len(found["opening"]) != 1 or len(found["closing"]) != 1:
        raise ValueError("a seam needs exactly one opening and one closing rule")
    opening, closing = found["opening"][0], found["closing"][0]
    # The frozen block under the opening rule is the template's; the space starts
    # where that comment run ends.
    start = opening
    while start < len(lines) and lines[start].startswith("#"):
        start += 1
    return [
        (number, _digest(line))
        for number, line in enumerate(lines, start=1)
        if line.lstrip().startswith("#") and not start < number < closing
    ]


def unrecognised(recorded: List[str], lines: List[str]) -> List[int]:
    """Line numbers of comments outside the space that the record does not account for.

    A sequence match rather than set membership, because the template repeats
    lines — a bare `#` separator is the most common comment in these files — so
    a set would accept a planted `#` anywhere. Order is what places a line.
    """
    present = outside_comments(lines)
    matcher = difflib.SequenceMatcher(a=recorded, b=[digest for _, digest in present], autojunk=False)
    extra: List[int] = []
    for tag, _, _, low, high in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            extra += [present[index][0] for index in range(low, high)]
    return extra


def _walk(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root).parts
        if any(part.startswith(".") or part in _SKIP for part in parts[:-1]):
            continue
        yield path


def record(root: Path = PROJECT_ROOT) -> Dict[str, List[str]]:
    """Each seam file's outside comments, digested — what the scaffolder writes."""
    seams: Dict[str, List[str]] = {}
    for path in _walk(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        if invites(text):
            seams[path.relative_to(root).as_posix()] = [digest for _, digest in outside_comments(text.splitlines())]
    return seams


def load(path: Path = RECORD) -> Optional[Dict[str, List[str]]]:
    if not path.exists():
        return None
    seams: Dict[str, List[str]] = json.loads(path.read_text(encoding="utf-8"))["seams"]
    return seams


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().split("\n")[0])
    parser.add_argument("--write", action="store_true", help="record the template's comment lines (scaffold time)")
    args = parser.parse_args()
    if not args.write:
        detail("Nothing to do without --write. The check is the test:")
        detail("  pytest tests/test_narrative_covers_lifecycle_folders.py")
        return 0
    try:
        seams = record()
    except ValueError as error:
        fail(f"cannot record the seams: {error}")
        return 1
    if not seams:
        fail("no file in this tree invites an append, so there is nothing to record")
        return 1
    data = {
        "_generated": "by scripts/seams.py --write, at scaffold time. Do not edit: it records which comment "
        "lines skeletor wrote, and an edit makes your own prose read as the template's.",
        "seams": seams,
    }
    RECORD.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ok(f"recorded {len(seams)} seam file(s) in {RECORD.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
