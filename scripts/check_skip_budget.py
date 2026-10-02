#!/usr/bin/env python3
"""Fail a suite whose skip count exceeds its budget.

Skips are how a test suite quietly stops testing. A run reporting
"340 passed, 176 skipped" reads as green and proves much less than it appears
to — and nothing surfaces the drift, because each individual skip was
reasonable when it was added.

The budget makes the count a number somebody has to change on purpose.

Usage:
    pytest ... --junitxml=tmp/junit.xml && python scripts/check_skip_budget.py --suite unit
    python scripts/check_skip_budget.py --suite unit --json

`--json` reports on **every** path, including the ones that pass. A ratchet a
dashboard can only read when it is red says nothing about the direction it has
been moving, which is the only thing a ratchet is for.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import detail, emit, fail, item, ok  # noqa: E402
from scripts.paths import TESTS_DIR, TMP_DIR  # noqa: E402

BUDGET = TESTS_DIR / "skip_budget.json"
DEFAULT_JUNIT = TMP_DIR / "junit.xml"


def count_skips(junit: Path) -> tuple:
    root = ET.parse(junit).getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    total = sum(int(s.get("tests", 0)) for s in suites)
    reasons = [
        (case.get("classname", ""), skip.get("message", ""))
        for suite in suites
        for case in suite.iter("testcase")
        for skip in case.iter("skipped")
    ]
    return skipped, total, reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="unit")
    parser.add_argument("--junit", type=Path, default=DEFAULT_JUNIT)
    parser.add_argument("--update", action="store_true", help="record the observed count as the new ceiling")
    parser.add_argument("--json", action="store_true", help="the machine-readable result on stdout")
    args = parser.parse_args()

    def done(payload: dict, status: int) -> int:
        """One exit, one payload. Emitting per-branch is how a path loses its."""
        if args.json:
            emit({"suite": args.suite, **payload})
        return status

    if not args.junit.exists():
        # A ratchet with nothing to read has not passed; it has not run. This
        # warned and exited 0 for as long as the tree existed, and `ci.yml` ran
        # pytest without `--junitxml` — so the check that exists to catch a
        # suite quietly stopping testing was itself quietly not testing, on
        # every push, in every scaffold. stash.flow found it by writing the
        # report by hand and watching a green step turn red.
        #
        # There is no case where "I could not measure" is the same answer as
        # "the budget is respected", so there is no warn-and-pass path here.
        fail(f"no junit report at {args.junit} — run pytest with --junitxml={args.junit} first")
        detail("Nothing was measured, so nothing is being ratcheted. See docs/rules/testing.md.")
        return done({"state": "no-report", "junit": str(args.junit)}, 1)

    budget = json.loads(BUDGET.read_text(encoding="utf-8"))
    entry = budget["suites"].get(args.suite)
    if entry is None:
        fail(f"suite '{args.suite}' has no entry in tests/skip_budget.json — add one")
        return done({"state": "unbudgeted"}, 1)

    skipped, total, reasons = count_skips(args.junit)
    ceiling = int(entry["max_skipped"])
    measured = {"skipped": skipped, "total": total, "ceiling": ceiling}

    if args.update:
        entry["max_skipped"] = skipped
        BUDGET.write_text(json.dumps(budget, indent=2) + "\n", encoding="utf-8")
        ok(f"{args.suite} budget set to {skipped}")
        return done({"state": "updated", **measured}, 0)

    if skipped > ceiling:
        fail(f"{args.suite}: {skipped} skipped, budget {ceiling} ({total} tests)")
        for classname, message in reasons[:10]:
            item(f"{classname}: {message[:100]}")
        detail()
        detail("Fix the skip, or raise the budget IN THIS COMMIT and justify it in the body.")
        return done({"state": "over", "reasons": [f"{c}: {m}" for c, m in reasons], **measured}, 1)

    if skipped < ceiling:
        ok(f"{args.suite}: {skipped} skipped, under the {ceiling} budget.")
        detail(f"Lower it in this commit: python scripts/check_skip_budget.py --suite {args.suite} --update")
        return done({"state": "under", **measured}, 0)

    ok(f"{args.suite}: {skipped} skipped (at budget)")
    return done({"state": "at", **measured}, 0)


if __name__ == "__main__":
    raise SystemExit(main())
