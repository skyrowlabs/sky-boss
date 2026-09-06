#!/usr/bin/env python3
"""The one place that decides what order `ready` plans are worked in.

Two things consume this order and they must agree: whatever *builds* the ready
queue (an agent, a scheduled job, or you reading the list) and
``rebuild_todo_readme.py``, which *publishes* it. They used to sort separately
in the project this was extracted from, and drifted exactly as you would
expect — the README published positions 30, 50, 60, 40, 90 within one priority
block while the job built them 30, 40, 50, 60, 90.

**A published order that is not the real order is worse than no order**, because
it invites a reader to plan around a sequence that will not happen. So the
ordering lives here and is *imported*, never reimplemented.
"""

from __future__ import annotations

from typing import Tuple

#: Priority rank, lowest first. Priority is the SECOND key, not the first: it
#: answers "how much does this matter", which is a different question from
#: "what should be built first", and several plans can honestly share one.
PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

#: Where an absent or unrecognised priority sorts: after everything named,
#: never before it. An unreadable priority must not win the queue.
PRIORITY_RANK_DEFAULT = len(PRIORITY_RANK)

#: Where a plan with no explicit ``Queue-Order`` sorts. Deliberately not 0 — an
#: unnumbered plan must never displace a numbered one, because the whole point
#: of the number is that somebody chose it. Absence is not a choice.
UNORDERED = 10_000


def priority_rank(entry: dict) -> int:
    """Rank an entry's ``priority``, tolerating absent and unknown values."""
    return PRIORITY_RANK.get(str(entry.get("priority") or "").strip().lower(), PRIORITY_RANK_DEFAULT)


def queue_position(entry: dict) -> int:
    """The plan's declared position, or :data:`UNORDERED` if it has none.

    A malformed value (``"soon"``, ``[]``, ``""``) sorts last rather than
    raising or silently winning the queue.
    """
    raw = entry.get("queue_order")
    try:
        return int(raw) if raw is not None else UNORDERED
    except (TypeError, ValueError):
        return UNORDERED


def run_order(entry: dict) -> Tuple[int, int, str]:
    """Sort key: declared queue order, then priority, then slug.

    Three keys, each covering the previous one's blind spot:

    ============= ==================================== ===========================
    Key           Answers                              Why it is not enough alone
    ============= ==================================== ===========================
    queue_order   what to build **first**              absent on older plans
    priority      how much a plan **matters**          plans can share one
    slug          keeps equal ranks **deterministic**  arbitrary
    ============= ==================================== ===========================

    The slug tiebreak matters as much as the other two: equal-ranked plans must
    come out in the same order on every run, or a plan can sit at position N one
    night and N+1 the next and never be reached by a run budget on either.
    """
    return (queue_position(entry), priority_rank(entry), str(entry.get("slug") or ""))
