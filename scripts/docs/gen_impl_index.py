#!/usr/bin/env python3
"""Regenerate ``docs/implementation_index.json`` — the completed-work archive.

The archive answers a different question from the tank: not "what is left" but
"why is it like this". Each entry therefore carries an ``agent_value`` rating —
how much a future agent gains by reading it before touching that system:

  3  key design decisions; read this before modifying the system it describes
  2  useful debugging and rationale context
  1  historical only

Rating every doc `3` makes the field useless, so it defaults to `1` and is
raised deliberately.

Usage:  python scripts/docs/gen_impl_index.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.docs import plans  # noqa: E402
from scripts.output import fail, ok  # noqa: E402
from scripts.paths import IMPL_DIR, PROJECT_ROOT  # noqa: E402

INDEX_PATH = PROJECT_ROOT / "docs" / "implementation_index.json"


def build() -> dict:
    entries = []
    for plan in plans.scan(IMPL_DIR, recursive=True):
        rel = plan.path.relative_to(IMPL_DIR)
        category = rel.parts[0] if len(rel.parts) > 1 else "uncategorized"
        entry = plan.to_entry()
        entry["category"] = str(plan.frontmatter.get("category") or category)
        entry["completed"] = str(plan.frontmatter.get("completed") or plan.updated)
        try:
            entry["agent_value"] = int(plan.frontmatter.get("agent_value") or 1)
        except (TypeError, ValueError):
            entry["agent_value"] = 1
        # Tank-only fields: meaningless once a plan is filed, and a stale
        # `shelf_status: ready` in the archive is actively misleading. The set
        # is `plans.TANK_ONLY` rather than a copy of it — this used to be the
        # copy, and popping here while the *document* kept the field is what let
        # the defect hide: the index rendered clean, `regen.py --check` stayed
        # green, and the doc went on lying. A derived artifact declining to
        # publish a field is not a fix for the field being wrong.
        for key in plans.TANK_ONLY:
            entry.pop(key, None)
        entries.append(entry)

    by_category: dict = {}
    for entry in entries:
        by_category.setdefault(entry["category"], []).append(entry["slug"])
    return {
        "_generated_by": "scripts/docs/gen_impl_index.py",
        "_note": "Generated — never hand-edit. Edit the doc's frontmatter and rerun.",
        "count": len(entries),
        "by_category": {k: sorted(v) for k, v in sorted(by_category.items())},
        "implementations": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit non-zero if stale; write nothing")
    args = parser.parse_args()

    rendered = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        current = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""
        if current != rendered:
            fail("docs/implementation_index.json is stale — run `dev docs index`")
            return 1
        ok("docs/implementation_index.json is current")
        return 0

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(rendered, encoding="utf-8")
    ok(f"wrote docs/implementation_index.json ({json.loads(rendered)['count']} docs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
