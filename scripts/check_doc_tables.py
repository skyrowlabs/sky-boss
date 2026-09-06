#!/usr/bin/env python3
"""Every doc under `docs/` is reachable from the agent-facing index tables.

`AGENTS.md` and `.github/DOCS_INDEX.md` are how an agent decides what to read.
A document in neither is a document that will not be loaded — which is the same,
from the agent's point of view, as a document that does not exist. The failure
is silent and permanent: nothing ever surfaces the omission.

The reverse direction matters as much. A table row pointing at a deleted file
sends a reader to a dead path and, worse, implies the subject is still covered.

## Two questions, because `docs/` is not flat

A loose doc in `docs/` is registered by name. A **subfolder** is registered by
one row for the folder — its `README.md`, or the folder path itself — and that
row then owns everything below it. `docs/TODO/README.md` has always been a row
for exactly this reason; the plans it indexes are its business, not the tables'.

That second question went unasked for a long time, and the cost was quiet in the
way this whole shell exists to prevent: the check reported *"4 doc(s), all
registered"* in a tree holding fifteen. The three `docs/reports/` edition folders
each had a README that nothing anywhere pointed at. A gate that answers a
narrower question than its name is worse than no gate, because the green is read
as covering the wider one — so the count now names what was enumerated.

The recursion stops at a routed folder rather than descending, which is what
keeps a category leaf like `docs/implementations/spec/` out of scope by
construction instead of by allowlist: its parent's generated README indexes it.

Usage:  python scripts/check_doc_tables.py [--json]

`--json` is additive, never a second code path: the payload goes to stdout and
the explanation to stderr, so `... --json | jq` and a human run are the same run.
See `scripts/output.py`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Set

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import detail, emit, fail, item, ok  # noqa: E402
from scripts.paths import DOCS_DIR, GITHUB_DIR, PROJECT_ROOT  # noqa: E402

#: The agent-facing index tables. `AGENTS.md` is where the rules live and
#: `CLAUDE.md` is a pointer to it, but both are read: a tree adopted from
#: somewhere else may still keep its table in `CLAUDE.md`, and a doc registered
#: in a file that exists is registered. A table that is absent contributes
#: nothing rather than failing.
TABLES = [
    PROJECT_ROOT / "AGENTS.md",
    PROJECT_ROOT / "CLAUDE.md",
    GITHUB_DIR / "DOCS_INDEX.md",
]

#: The root `docs/README.md` is the reader's entry point *into* the index, not
#: an entry *in* it. A **subfolder's** README is the opposite — it is precisely
#: that folder's routing row, which is why `docs/TODO/README.md` has always been
#: one — so the exemption is the root's alone and does not inherit.
EXEMPT = {"README.md"}

#: Any doc path, at any depth. It matched only `docs/<name>.md` until a tree
#: shipped seven files in `docs/rules/`, which meant every nested row was
#: invisible in **both** directions: it could not satisfy a registration, and a
#: row left pointing at a deleted `docs/rules/*.md` could never be reported
#: dangling. A pattern that silently ignores most of the tree it names is the
#: harder half of this bug, because nothing about it looks wrong.
_DOC_PATH = re.compile(r"docs/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.md")

#: A folder named as a folder — `docs/rules/` — which is how a flat shelf of
#: per-domain conventions is better described than by naming each file.
#:
#: The trailing lookahead is load-bearing and its absence is what this comment
#: used to describe rather than enforce. Without it the pattern matches the
#: *directory portion of a file path*, so a row naming `docs/rules/commits.md` —
#: one file among several — routed the whole folder. The old comment asserted
#: exactly the property the regex lacked, which is the worst place for a gap to
#: sit: a reviewer checks the code against the comment, so the comment launders
#: it. Reported by proto.pilot, who measured it rather than reading it.
#:
#: The consequence is permissive, not loud. `stranded()` under-reports, so the
#: gate stays green over a folder nothing actually points at — which is the
#: failure this check exists to remove, one door along.
_DOC_DIR = re.compile(r"docs/(?:[A-Za-z0-9_.-]+/)+(?![A-Za-z0-9_.-])")

#: A folder's OWN README routes it, and only its own. `docs/TODO/README.md`
#: vouches for `docs/TODO`; `docs/reports/regular/README.md` vouches for
#: `docs/reports/regular` and NOT for `docs/reports`. This is deliberate and the
#: shipped index depends on it — three folders here are routed this way and no
#: other — so the lookahead above could not simply be tightened without it.
#:
#: The old comment named the parent-vouching hazard, which never happened: the
#: pattern is greedy, so it matched the longest prefix and only that. The hazard
#: it missed is the one above. A comment can be wrong about the danger *and*
#: wrong about the mechanism while sounding careful about both.
_FOLDER_INDEX = "/README.md"


def referenced() -> Set[str]:
    seen: Set[str] = set()
    for table in TABLES:
        if table.exists():
            text = table.read_text(encoding="utf-8")
            paths = _DOC_PATH.findall(text)
            seen |= set(paths)
            seen |= {ref.rstrip("/") for ref in _DOC_DIR.findall(text)}
            seen |= {p[: -len(_FOLDER_INDEX)] for p in paths if p.endswith(_FOLDER_INDEX)}
    return seen


def unrouted(directory: Path, listed: Set[str]) -> list:
    """Subfolders holding docs that no table row reaches.

    A folder is routed by its own `README.md` or by its own path — checked
    exactly, never by a row for something inside it. A routed folder is not
    descended into, because its README owns what is below it.
    """
    found = []
    for child in sorted(p for p in directory.iterdir() if p.is_dir() and not p.name.startswith(".")):
        rel = child.relative_to(PROJECT_ROOT).as_posix()
        if f"{rel}/README.md" in listed or rel in listed:
            continue
        if any(child.glob("*.md")):
            found.append(rel)
        found += unrouted(child, listed)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    on_disk = {f"docs/{p.name}" for p in DOCS_DIR.glob("*.md") if p.name not in EXEMPT}
    listed = referenced()

    unregistered = sorted(on_disk - listed)
    stranded = sorted(unrouted(DOCS_DIR, listed))
    dangling = sorted(ref for ref in listed - on_disk if ref.endswith(".md") and not (PROJECT_ROOT / ref).exists())

    if args.json:
        emit(
            {
                "registered": len(on_disk),
                "routed_folders": sum(1 for p in DOCS_DIR.rglob("*") if p.is_dir()) - len(stranded),
                "unregistered": unregistered,
                "stranded": stranded,
                "dangling": dangling,
            }
        )

    status = 0
    if unregistered:
        fail("docs not registered in AGENTS.md or .github/DOCS_INDEX.md:")
        for ref in unregistered:
            item(ref)
        detail("An unregistered doc is one no agent will load. Add it to both tables.")
        status = 1
    if stranded:
        fail("docs subfolders no index table routes to:")
        for ref in stranded:
            item(f"{ref}/")
        detail("Add one row per folder — its README.md, or the folder path — to AGENTS.md")
        detail("and .github/DOCS_INDEX.md. The row then covers everything below it.")
        status = 1
    if dangling:
        fail("index rows pointing at files that no longer exist:")
        for ref in dangling:
            item(ref)
        status = 1
    if not status:
        folders = sum(1 for p in DOCS_DIR.rglob("*") if p.is_dir() and not p.name.startswith("."))
        ok(f"{len(on_disk)} loose doc(s) registered, {folders} subfolder(s) routed")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
