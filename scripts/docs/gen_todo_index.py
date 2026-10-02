#!/usr/bin/env python3
"""Regenerate ``docs/todo_index.json`` — the machine-readable holding tank.

Its audience is a program, not a reader: "is this already built but parked?"
should be answerable without opening thirty markdown files. The human-readable
half is ``docs/TODO/README.md``, built by ``rebuild_todo_readme.py`` from this
same scan, so the two cannot disagree about what is in the tank.

Usage:  python scripts/docs/gen_todo_index.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.docs import plans  # noqa: E402
from scripts.docs.queue_order import run_order  # noqa: E402
from scripts.output import fail, ok  # noqa: E402
from scripts.paths import PROJECT_ROOT, TODO_DIR  # noqa: E402

INDEX_PATH = PROJECT_ROOT / "docs" / "todo_index.json"


def build() -> dict:
    entries = [p.to_entry() for p in plans.scan(TODO_DIR)]
    by_status: dict = {}
    for entry in entries:
        by_status.setdefault(entry["shelf_status"], []).append(entry["slug"])
    return {
        "_generated_by": "scripts/docs/gen_todo_index.py",
        "_note": "Generated — never hand-edit. Edit the plan's frontmatter or header lines and rerun.",
        "count": len(entries),
        "by_status": {k: sorted(v) for k, v in sorted(by_status.items())},
        # The ready queue is published in RUN order, not alphabetical: this is
        # the list something acts on, and an order nobody will follow is worse
        # than none. Every other section is a reference list, so it stays sorted
        # by slug for a stable diff.
        "ready_queue": [e["slug"] for e in sorted((e for e in entries if e["shelf_status"] == "ready"), key=run_order)],
        "plans": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit non-zero if stale; write nothing")
    args = parser.parse_args()

    rendered = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        current = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""
        if current != rendered:
            fail(f"{INDEX_PATH.relative_to(PROJECT_ROOT)} is stale — run `dev docs index`")
            return 1
        ok(f"{INDEX_PATH.relative_to(PROJECT_ROOT)} is current")
        return 0

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(rendered, encoding="utf-8")
    ok(f"wrote {INDEX_PATH.relative_to(PROJECT_ROOT)} ({json.loads(rendered)['count']} plans)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
