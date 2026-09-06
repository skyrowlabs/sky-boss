#!/usr/bin/env python3
"""Backfill frontmatter onto plan docs that lack it, or refresh what is derived.

Runs before both index generators. It is a **backfill**, not an authority: every
field it writes can be overridden by an explicit header line in the doc body,
and the override always wins. The split matters — a maintainer who corrects a
mis-inferred status must not have the correction erased by the next run.

Never inferred, here or anywhere: ``blocked_on``, ``queue_order``, ``review_pr``.
A guessed gate files a plan under a session nobody will hold; a guessed order is
the accident the numbering exists to replace; a guessed PR number sends a
reviewer to the wrong diff. Each is worse than an honest blank.

Usage:  python scripts/docs/add_frontmatter.py [--force] [--todo|--impl]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.docs import frontmatter, plans  # noqa: E402
from scripts.output import item, ok  # noqa: E402
from scripts.paths import IMPL_DIR, PROJECT_ROOT, TODO_DIR  # noqa: E402


def _derive(plan: plans.Plan, archive: bool) -> dict:
    data = dict(plan.frontmatter)
    data["title"] = plan.title
    data["slug"] = plan.slug
    data.setdefault("summary", "")
    data.setdefault("tags", [])
    if plan.updated:
        data["updated"] = plan.updated

    if archive:
        rel = plan.path.relative_to(IMPL_DIR)
        data["category"] = data.get("category") or (rel.parts[0] if len(rel.parts) > 1 else "uncategorized")
        data.setdefault("agent_value", 1)
        data.setdefault("completed", plan.updated or "")
        for key in plans.TANK_ONLY:
            data.pop(key, None)
        return data

    data["shelf_status"] = plan.shelf_status
    data["priority"] = plan.priority
    # Explicit-only fields: written through when the doc declares one, removed
    # when it does not, so the JSON never keeps a value the doc has dropped.
    for key, value in (
        ("blocked_on", plan.blocked_on),
        ("queue_order", plan.queue_order),
        ("review_pr", plan.review_pr),
    ):
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="rewrite docs that already have frontmatter")
    parser.add_argument("--todo", action="store_true", help="holding tank only")
    parser.add_argument("--impl", action="store_true", help="archive only")
    args = parser.parse_args()

    targets = []
    if not args.impl:
        targets += [(p, False) for p in plans.scan(TODO_DIR)]
    if not args.todo:
        targets += [(p, True) for p in plans.scan(IMPL_DIR, recursive=True)]

    written = 0
    for plan, archive in targets:
        # The tank branch is a **backfill**: it fills in what is missing and
        # then leaves the doc alone, so a maintainer's frontmatter survives.
        #
        # The archive branch is not a backfill. It is the normalisation a filing
        # performs — strip the tank-only fields, add `category`/`completed` —
        # and it has to run on a doc that *already has* frontmatter, because
        # every doc being filed does. Sharing this guard made it unreachable in
        # the only case it exists for: the archive branch had never once run
        # during a real filing, and every plan filed by every tree scaffolded
        # from this shell kept its old `shelf_status` forever. It is idempotent,
        # so always running it costs a comparison.
        if plan.frontmatter and not args.force and not archive:
            continue
        derived = _derive(plan, archive)
        if derived == plan.frontmatter:
            continue
        frontmatter.write(plan.path, derived, plan.body)
        written += 1
        item(f"{plan.path.relative_to(PROJECT_ROOT)}")

    ok(f"frontmatter: {written} doc(s) updated, {len(targets) - written} already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
