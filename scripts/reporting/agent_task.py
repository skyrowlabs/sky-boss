#!/usr/bin/env python3
"""`agent-task` — work one issue from the `task` lane into a draft pull request.

A binding over `drain.py`, which holds the stages and the reasons for their order.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reporting import drain  # noqa: E402

DRAIN = drain.Drain(job_key="agent-task", lane_key="task")


def main() -> int:
    return drain.run(DRAIN)


if __name__ == "__main__":
    raise SystemExit(main())
