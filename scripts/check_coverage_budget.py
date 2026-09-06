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
until the suite covers source of your own. `own_statements` is the question, and
the suppression is narrow: it stops the two paths that would WRITE that number
down, never the comparison. A drop below an existing baseline is still a drop.

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
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import detail, emit, fail, ok  # noqa: E402
from scripts.paths import SCAFFOLD_MANIFEST, TESTS_DIR, TMP_DIR  # noqa: E402

BUDGET = TESTS_DIR / "coverage_budget.json"
DEFAULT_XML = TMP_DIR / "coverage.xml"


def own_statements(root: ET.Element) -> Optional[int]:
    """How many of the measured statements are this project's own.

    A percentage is a claim about a population, and this is the one question
    that decides whether the population contains the subject at all. On the day
    a tree is scaffolded the answer is **zero**: every measured file is the
    shell, covered by the shell's own tests, and a baseline recorded then is the
    template's coverage of the template wearing this project's name.

    `.skeletor.json` names every path the scaffolder wrote, so a measured file
    that is not in it is the project's. Only the key set is read — see
    `scripts.paths.SCAFFOLD_MANIFEST` for why nothing else in there is ours to
    interpret.

    Returns `None` when there is no manifest to ask, which is a real state and
    not a failure: a tree can be adopted by hand or have deleted the file. The
    difference between *none of this is yours* and *I cannot tell* is exactly
    the difference between a refusal and a caveat, so it is a third value rather
    than a zero.
    """
    if not SCAFFOLD_MANIFEST.exists():
        return None
    try:
        scaffolded = set(json.loads(SCAFFOLD_MANIFEST.read_text(encoding="utf-8")).get("files", {}))
    except (OSError, ValueError):
        return None
    return sum(
        len(cls.findall("lines/line"))
        for cls in root.iterfind("packages/package/classes/class")
        if cls.get("filename") not in scaffolded
    )


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

    root = ET.parse(args.xml).getroot()
    observed = float(root.get("line-rate", 0)) * 100
    baseline = float(entry["baseline_pct"])
    tolerance = float(budget.get("tolerance_pts", 0.5))
    own = own_statements(root)
    measured = {
        "observed_pct": round(observed, 2),
        "baseline_pct": baseline,
        "tolerance_pts": tolerance,
        # On every path, including the ones that pass. The ratio alone cannot
        # say whether it is about this project, and a dashboard reading only
        # the ratio has no way to ask. `null` is "no manifest to ask".
        "own_statements": own,
        "total_statements": int(root.get("lines-valid", 0)),
    }

    # Nothing measured is this project's own. The ratchet itself is unharmed —
    # it ships at 0.00% and cannot fail there — so this suppresses the two
    # places that would WRITE that number down, and nothing else. A drop below
    # an existing baseline is still a drop: `cli/` and `scripts/` are this
    # tree's code from its first commit, and a regression in them is real
    # whatever the rest of the population looks like.
    nothing_of_yours = (
        "every measured statement belongs to the scaffold this tree was started from, "
        "so this percentage is not yet a fact about this project"
    )

    if args.update and own == 0:
        fail(f"{args.suite}: refusing to record a baseline — {nothing_of_yours}")
        detail("Baseline once the suite covers source of your own; until then 0.00% is the honest floor.")
        return done({"state": "unrepresentative", **measured}, 1)

    # What the ratio hides, stated wherever the number is about to be written
    # down or recommended. It is a measured fact and not a threshold: the
    # refusal above is only the degenerate case, and a baseline that is 99% the
    # shell is still mostly the shell. Nobody can pick the percentage at which
    # that stops mattering, so the reader is given the composition instead of a
    # number somebody guessed.
    composition = f"{own} of {measured['total_statements']} measured statements are your own"

    if args.update:
        entry["baseline_pct"] = round(observed, 2)
        BUDGET.write_text(json.dumps(budget, indent=2) + "\n", encoding="utf-8")
        ok(f"{args.suite} baseline set to {observed:.2f}%")
        if own is not None:
            detail(composition)
        return done({"state": "updated", **measured}, 0)

    if observed < baseline - tolerance:
        fail(f"{args.suite}: {observed:.2f}% vs baseline {baseline:.2f}% (tolerance {tolerance})")
        detail("Cover what you changed, or say in the commit body why the drop is correct.")
        return done({"state": "below", **measured}, 1)

    if observed > baseline + tolerance:
        ok(f"{args.suite}: {observed:.2f}% — above baseline {baseline:.2f}%.")
        if own == 0:
            # The invitation is the whole defect. A fresh tree is ALWAYS above
            # its shipped 0.00% floor, so this line printed "lock it in" on the
            # very first coverage run of every scaffold — telling the reader to
            # undo the one thing the scaffolder got right.
            detail(f"Not yet: {nothing_of_yours}.")
            return done({"state": "unrepresentative", **measured}, 0)
        if own is not None:
            detail(composition)
        detail(f"Lock it in: python scripts/check_coverage_budget.py --suite {args.suite} --update")
        return done({"state": "above", **measured}, 0)

    ok(f"{args.suite}: {observed:.2f}% (baseline {baseline:.2f}%)")
    return done({"state": "within", **measured}, 0)


if __name__ == "__main__":
    raise SystemExit(main())
