"""Fail a suite whose coverage drops below its baseline, within a tolerance.

A ratchet, not a target. The distinction matters: a test written to move a
percentage covers the lines that were cheapest to reach, which are the lines
least likely to be wrong. The number exists to stop coverage sliding while
nobody is looking — not to be optimised.

The tolerance absorbs honest run-to-run variance (an env-gated branch, a
skipped optional dependency) without absorbing a real regression.

Usage:
    pytest --cov --cov-report=xml:tmp/coverage.xml && python scripts/check_coverage_budget.py --suite unit
    python scripts/check_coverage_budget.py --suite unit --json

`--json` reports on **every** path, including the ones that pass. A ratchet a
dashboard can only read when it is red tells you nothing about the direction it
has been moving, which is the only thing a ratchet is for.

**A percentage is a claim about a population, so the baseline is refused while
the population contains none of the subject.** A tree on the day it is
scaffolded measures the shell and nothing else, at whatever rate the shell's own
tests happen to reach — and `--update` there records that as this project's
coverage. It is not: the first module of your own that lands covered at less
than the shell's rate then reads as a regression you caused, on a tree where
coverage of your code went from nothing to something. Measured on a fresh
`agentic` scaffold, `--update` locked in 69.69% and five lightly-tested product
modules took it to 63.72% — red, with nothing regressed.

The floor the scaffolder ships, `0.00%`, cannot fail and is the honest value
until the suite covers source of your own. `own_statements` is the question.

The refusal is only the **degenerate** case, and the range above zero is where
the judgement lives. It is shown rather than judged for one measured reason:

> **`populated repository` is the wrong predicate for `populated measured set`.**

stash.flow found that from an adopted tree — 2222 statements measured, 1935 of
them the scaffold's — and the mechanism is the coverage configuration rather
than the repository's history. With no `[tool.coverage]` section, coverage
measures what the run *imports*, and what the scaffold's own tests import is the
scaffold's own scripts. Product source that is not yet under test contributes
nothing to the denominator however old the repository is.

That matters because it is the predicate anybody would reach for, and it fails
in the reassuring direction: *this repo is populated, so the number must be
about us.* With the obvious predicate wrong and no second one going spare, the
composition has to be **shown** instead of inferred — so both paths that record
or recommend the number state it, and the fact prints before the instruction.

No threshold is invented, because nothing here knows the distribution of adopted
trees and a number that guessed at it would be worse than the reader's own eyes.
Zero earns a refusal because zero is the one point where no judgement is
possible.

## The comparison is over your own code, and that reverses an earlier ruling

**This file used to compare the whole measured set, and said why**: the shell's
package and `scripts/` are this tree's code from its first commit, so a
regression in them is real whatever else is measured, and the suppression above
was narrow on purpose — *it stops the paths that write the number down, never
the comparison.* That was true while the shell sat still. It does not: every
`skeletor-upgrade` rewrites it, so the whole-set percentage moves on a commit
the adopter did not write, and the drop message — *cover what you changed* —
sends them to code they cannot sensibly change.

proto.pilot measured it. Its nightly reached this ratchet for the first time
after an upgrade fixed an unrelated collection failure, and went red at 86.88%
against 87.43%. Of 277 new misses, its product package contributed none:
`scripts/` +139, the shell +60, `tests/` +78, and every file it checked was in
`.skeletor.json`. The subject's coverage was flat; the ratchet was measuring
the template.

So `own_baseline_pct` is a rate over **your own population**: measured files the
manifest does not name, outside `tests/`. Tests are excluded because a test file
is very nearly all executed by being run, so counting it lifts the rate in
proportion to how much testing you write rather than how much of your code it
reaches. The whole-set rate is still reported on every path and in `--json`,
and a drop prints both.

What that gives up, stated rather than discovered:

* **Coverage of the shell is ratcheted nowhere.** Not here, and not in the
  generator, which runs every scaffold's suite but records no baseline for it.
* **A scaffold file you have edited is not yours to this check.** The manifest
  is read for its key set only — see `scripts.paths.SCAFFOLD_MANIFEST` — and
  the key set cannot tell an edited file from an untouched one.
* **A coverage `source` changes the filenames** the report carries, from
  repository-relative to source-relative, and then nothing matches the manifest:
  every measured file reads as yours. That over-counts in the direction of the
  old behaviour, which is the safe one.

**`baseline_pct` is the old key, and it is not reinterpreted.** A number
recorded over one population compared against a rate over another would be
wrong silently, in whichever direction the two happened to differ. A tree that
still carries it gets the old comparison, the split, and the command that
migrates it; the shipped `0.0` is the floor rather than a recording, so it says
nothing. The template's own `coverage_budget.json` still ships that key, on
purpose: every tree that has baselined edited that line, and renaming it there
would conflict in each one for no change in behaviour. `--update` writes the
new key and removes the old.

**What the old figure was made of cannot be recovered by this script.** The
report it was computed from lived in gitignored `tmp/`, and the budget kept one
number. mind.head needed it to decide whether to migrate, and this checker
cannot run at a commit older than `scripts.paths.SCAFFOLD_MANIFEST`. What worked
was by hand: check out the recording commit, re-run coverage, and split that
report against that commit's `.skeletor.json` — files it names are the shell,
`tests/` is out, the rest is yours. Theirs reproduced the old 91.16% exactly and
showed their own code at 90.65%, so the drop had been the shell's.

**An own baseline with none of your code measured is a failure**, not the
fresh-tree pass it resembles. The rate is undefined, but the baseline says there
was code of yours under test, and a run that no longer imports it is the
regression this file exists for — a renamed package, a suite that stopped
collecting it.

Without a manifest none of this is answerable, and the old key and the old
comparison are what such a tree gets: *I cannot tell* is not *none of it is
yours*, as below.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import detail, emit, fail, ok  # noqa: E402
from scripts.paths import PROJECT_ROOT, SCAFFOLD_MANIFEST, TESTS_DIR, TMP_DIR  # noqa: E402

BUDGET = TESTS_DIR / "coverage_budget.json"
DEFAULT_XML = TMP_DIR / "coverage.xml"


#: A name rather than a parenthesised tuple in the `except`: at a 3.14 target black
#: rewrites `except (A, B):` into PEP 758's `except A, B:` and at every other target
#: keeps it, so the literal is not black-clean at every `--python` this renders. A
#: name formats the same everywhere. stash.flow, from a tree with a 3.14 floor.
_UNREADABLE_BUDGET = (OSError, ValueError)


def _own_lines(root: ET.Element) -> Optional[List[ET.Element]]:
    """Every measured `<line>` in a file of this project's own, or `None` without a manifest.

    Own means *not named by `.skeletor.json`* and *not under `tests/`* — the
    module docstring says why tests are out. One function so the count and the
    rate cannot disagree about the population.
    """
    if not SCAFFOLD_MANIFEST.exists():
        return None
    try:
        scaffolded = set(json.loads(SCAFFOLD_MANIFEST.read_text(encoding="utf-8")).get("files", {}))
    except _UNREADABLE_BUDGET:
        return None
    tests = TESTS_DIR.relative_to(PROJECT_ROOT).as_posix() + "/"
    return [
        line
        for cls in root.iterfind("packages/package/classes/class")
        if (name := cls.get("filename") or "") not in scaffolded and not name.startswith(tests)
        for line in cls.findall("lines/line")
    ]


def own_rate(root: ET.Element) -> Optional[float]:
    """The line rate over `_own_lines`, as a percentage; `None` when there is
    no manifest to ask or nothing of yours was measured."""
    lines = _own_lines(root)
    if not lines:
        return None
    return 100.0 * sum(1 for line in lines if int(line.get("hits", "0")) > 0) / len(lines)


def own_statements(root: ET.Element) -> Optional[int]:
    """How many of the measured statements are this project's own.

    A percentage is a claim about a population, and this is the one question
    that decides whether the population contains the subject at all. On the day
    a tree is scaffolded the answer is **zero**: every measured file is the
    shell, covered by the shell's own tests, and a baseline recorded then is the
    template's coverage of the template wearing this project's name.

    `.skeletor.json` names every path the scaffolder wrote, so a measured file
    that is not in it is the project's — tests excepted, see `_own_lines`. Only
    the key set is read — see `scripts.paths.SCAFFOLD_MANIFEST` for why nothing
    else in there is ours to interpret.

    Returns `None` when there is no manifest to ask, which is a real state and
    not a failure: a tree can be adopted by hand or have deleted the file. The
    difference between *none of this is yours* and *I cannot tell* is exactly
    the difference between a refusal and a caveat, so it is a third value rather
    than a zero.
    """
    lines = _own_lines(root)
    return None if lines is None else len(lines)


#: Printed wherever a refusal or a "not yet" needs its reason.
NOTHING_OF_YOURS = (
    "every measured statement belongs to the scaffold this tree was started from, "
    "so this percentage is not yet a fact about this project"
)


class Reading(NamedTuple):
    """One coverage report, read once, so the two paths below cannot disagree about it."""

    whole: float
    own: Optional[int]
    mine: Optional[float]
    measured: dict
    composition: str


def read(root: ET.Element, tolerance: float) -> Reading:
    whole = float(root.get("line-rate", 0)) * 100
    own = own_statements(root)
    mine = own_rate(root)
    measured = {
        "whole_pct": round(whole, 2),
        "own_pct": None if mine is None else round(mine, 2),
        "tolerance_pts": tolerance,
        # On every path, including the ones that pass. The ratio alone cannot
        # say whether it is about this project, and a dashboard reading only
        # the ratio has no way to ask. `null` is "no manifest to ask".
        "own_statements": own,
        "total_statements": int(root.get("lines-valid", 0)),
    }
    # What the ratio hides, stated wherever the number is written down,
    # recommended, or found wanting. A measured fact, not a threshold.
    composition = f"{own} of {measured['total_statements']} measured statements are your own"
    if mine is not None:
        composition += f", covered at {mine:.2f}% (whole measured set: {whole:.2f}%)"
    return Reading(whole, own, mine, measured, composition)


def record(suite: str, budget: dict, entry: dict, reading: Reading) -> Tuple[dict, int]:
    """`--update`: write the baseline down, or refuse to."""
    if reading.own == 0:
        fail(f"{suite}: refusing to record a baseline — {NOTHING_OF_YOURS}")
        detail("Baseline once the suite covers source of your own; until then 0.00% is the honest floor.")
        return {"state": "unrepresentative", **reading.measured}, 1
    if reading.mine is None:
        # No manifest: the old population is the only one there is.
        key, stale, recorded = "baseline_pct", "own_baseline_pct", reading.whole
    else:
        key, stale, recorded = "own_baseline_pct", "baseline_pct", reading.mine
    entry[key] = round(recorded, 2)
    entry.pop(stale, None)
    BUDGET.write_text(json.dumps(budget, indent=2) + "\n", encoding="utf-8")
    ok(f"{suite} baseline set to {recorded:.2f}%")
    if reading.own is not None:
        detail(reading.composition)
    return {"state": "updated", key: round(recorded, 2), **reading.measured}, 0


def compare(suite: str, entry: dict, tolerance: float, reading: Reading) -> Tuple[dict, int]:
    """Measure against the baseline, on the population the baseline was recorded over.

    The old key is honoured as written: a figure recorded over one population,
    compared against another, would be wrong silently. See "The comparison is
    over your own code" above.
    """
    own, mine, measured = reading.own, reading.mine, reading.measured
    if "own_baseline_pct" in entry and mine is None and own is not None:
        baseline = float(entry["own_baseline_pct"])
        measured = {"basis": "own", "own_baseline_pct": baseline, **measured}
        if baseline > 0:
            fail(f"{suite}: none of your own code was measured, against an own baseline of {baseline:.2f}%")
            detail("The suite no longer reaches source of your own — a renamed package, or tests that stopped")
            detail("collecting it. If that is intended, record the new state with --update.")
            return {"state": "below", **measured}, 1
        ok(f"{suite}: nothing of your own measured yet (baseline {baseline:.2f}%)")
        return {"state": "unrepresentative", **measured}, 0

    if "own_baseline_pct" in entry and mine is not None:
        basis, observed, baseline = "own", mine, float(entry["own_baseline_pct"])
    else:
        basis, observed, baseline = "whole", reading.whole, float(entry.get("baseline_pct", 0.0))
    # Every `--json` key names one population on every path, and they are the
    # budget file's own names. v0.40.0 reported an own-code baseline as
    # `baseline_pct`, the key that had meant the whole set the day before, so a
    # dashboard comparing across trees or across history made the silent
    # cross-population comparison this file exists to refuse (proto.pilot).
    # `observed_pct` had the same defect and is gone from the own basis, where
    # `own_pct` already says it.
    if basis == "own":
        measured = {"basis": basis, "own_baseline_pct": baseline, **measured}
    else:
        measured = {"basis": basis, "observed_pct": round(observed, 2), "baseline_pct": baseline, **measured}
    # Which population the figure is about, on the line a reader actually reads.
    over = " of your own code" if basis == "own" else ""
    # The old key, still recorded over the whole set, which an upgrade moves.
    # The shipped 0.0 is the floor, not a recording, so it says nothing.
    migrate = basis == "whole" and mine is not None and baseline > 0

    def migration() -> None:
        detail("This baseline is over the whole measured set, which a skeletor upgrade moves without you.")
        detail("Record it over your own code instead:")
        detail(f"  python scripts/check_coverage_budget.py --suite {suite} --update")

    if observed < baseline - tolerance:
        fail(f"{suite}: {observed:.2f}%{over} vs baseline {baseline:.2f}% (tolerance {tolerance})")
        if own is not None:
            detail(reading.composition)
        if migrate:
            migration()
        else:
            detail("Cover what you changed, or say in the commit body why the drop is correct.")
        return {"state": "below", **measured}, 1

    if observed > baseline + tolerance:
        ok(f"{suite}: {observed:.2f}%{over} — above baseline {baseline:.2f}%.")
        if own == 0:
            # The invitation is the whole defect. A fresh tree is ALWAYS above
            # its shipped 0.00% floor, so this line printed "lock it in" on the
            # very first coverage run of every scaffold — telling the reader to
            # undo the one thing the scaffolder got right.
            detail(f"Not yet: {NOTHING_OF_YOURS}.")
            return {"state": "unrepresentative", **measured}, 0
        if own is not None:
            detail(reading.composition)
        detail(f"Lock it in: python scripts/check_coverage_budget.py --suite {suite} --update")
        return {"state": "above", **measured}, 0

    ok(f"{suite}: {observed:.2f}%{over} (baseline {baseline:.2f}%)")
    if migrate:
        migration()
    return {"state": "within", **measured}, 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="unit")
    parser.add_argument("--xml", type=Path, default=DEFAULT_XML)
    parser.add_argument("--update", action="store_true", help="record the observed percentage as the new baseline")
    parser.add_argument("--json", action="store_true", help="the machine-readable result on stdout")
    args = parser.parse_args()

    def done(payload: dict, status: int) -> int:
        """One exit, one payload. Emitting per-branch is how a path loses its."""
        if args.json:
            emit({"suite": args.suite, **payload})
        return status

    if not args.xml.exists():
        # Same reason as `check_skip_budget.py`, and found the same day: a
        # ratchet that cannot read its report has not passed, it has not run.
        # This one was latent rather than live — its only workflow does produce
        # the report — which is exactly how the pair should be read. One graceful
        # degradation was already degrading into a pass; the other was one
        # edited workflow away from it.
        fail(f"no coverage report at {args.xml} — run pytest with --cov-report=xml:{args.xml} first")
        detail("Nothing was measured, so nothing is being ratcheted. See docs/rules/testing.md.")
        return done({"state": "no-report", "xml": str(args.xml)}, 1)

    budget = json.loads(BUDGET.read_text(encoding="utf-8"))
    entry = budget["suites"].get(args.suite)
    if entry is None:
        fail(f"suite '{args.suite}' has no entry in tests/coverage_budget.json — add one")
        return done({"state": "unbudgeted"}, 1)

    tolerance = float(budget.get("tolerance_pts", 0.5))
    reading = read(ET.parse(args.xml).getroot(), tolerance)
    if args.update:
        return done(*record(args.suite, budget, entry, reading))
    return done(*compare(args.suite, entry, tolerance, reading))


if __name__ == "__main__":
    raise SystemExit(main())
