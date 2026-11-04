#!/usr/bin/env python3
"""`repo-report` — the worked example every other job is copied from.

Two stages, and keeping them apart is the whole design:

* **Collection** (this module) is deterministic stdlib Python. It gathers facts
  and produces the same answer twice. It is what makes a finding reproducible.
* **Triage** is a headless agent reading those facts. It makes the calls a
  script cannot — what is a risk, what is noise, what changed meaningfully.

A job that skips collection and asks an agent to go and look produces a
different answer every night, and none of them can be checked.

Copy this file's shape for a new job: collect into a plain dict, hand it to
`agent_runner.run_triage`, return its exit code.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.docs import plans, release_window  # noqa: E402
from scripts.paths import PROJECT_ROOT, TODO_DIR  # noqa: E402
from scripts.reporting import agent_runner, shellout  # noqa: E402


def _git(*args: str) -> str:
    return shellout.run(["git", *args], cwd=str(PROJECT_ROOT), capture_output=True, text=True).stdout.strip()


def collect() -> dict[str, object]:
    """Facts about the current release window. No judgements — those are the
    agent's job, and mixing the two makes both unverifiable."""
    window = release_window.window()
    commit_range = str(window["commit_range"])

    log = _git("log", "--pretty=%s", commit_range).splitlines()
    types = Counter(line.split("(")[0].split(":")[0].strip() for line in log if ":" in line)

    churn = Counter()
    for line in _git("log", "--name-only", "--pretty=format:", commit_range).splitlines():
        if line.strip():
            churn[line.strip()] += 1

    tank = [p for p in plans.scan(TODO_DIR) if not p.auto_generated]

    return {
        "window": window,
        "commit_count": len(log),
        "commit_types": dict(types.most_common()),
        "most_changed_files": churn.most_common(20),
        "holding_tank": {
            "total": len(tank),
            "by_status": dict(Counter(p.shelf_status for p in tank)),
            "ready_queue": [p.slug for p in tank if p.shelf_status == "ready"],
            "awaiting_review": [{"slug": p.slug, "pr": p.review_pr} for p in tank if p.shelf_status == "in-review"],
        },
        # The agent is told how many findings it is looking at, so the ledger
        # can refuse an `ok` that reports findings and writes nothing.
        "finding_count": 0,
    }


def main() -> int:
    return agent_runner.run_triage("repo-report", collect())


if __name__ == "__main__":
    raise SystemExit(main())
