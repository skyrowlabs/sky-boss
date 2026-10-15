"""``dev inbox`` — what the capture lanes hold, read back.

``dev bug`` and ``dev task`` file into labelled GitHub issues, and a
capture that succeeds into a queue nobody looks at is indistinguishable, from the
filer's side, from one that was acted on. This is the reading half: every open
capture per lane, oldest first, with who filed it, and every job at its cap, since
a capped job files nothing more until somebody reads what it already filed.

It reads and never closes anything. A lane it could not list is reported as
unread, never as empty.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import click

from scripts.lanes import LANES, SESSION, SOURCE_CAP, drain_note, source_line

from ._capture import open_captures
from .helpers import detail, emit, item, ok, step, warn

#: The attribution line as a pattern, derived from the line itself so the two cannot drift.
_BEFORE, _AFTER = source_line("\0").split("\0")
_SOURCE = re.compile(re.escape(_BEFORE) + "(.+?)" + re.escape(_AFTER))


def source_of(body: str) -> str:
    """Who filed a capture; a body with no attribution line was filed by a person."""
    found = _SOURCE.search(body or "")
    return found.group(1) if found else SESSION


#: A name rather than a parenthesised tuple in the `except`: at a 3.14 target black
#: rewrites `except (A, B):` into PEP 758's `except A, B:`. A name formats the same everywhere.
_UNPARSEABLE = (AttributeError, ValueError)


def age_days(created: str, now: Optional[datetime] = None) -> Optional[int]:
    try:
        then = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except _UNPARSEABLE:
        return None
    return ((now or datetime.now(timezone.utc)) - then).days


def read_lanes() -> Dict[str, Optional[List[dict]]]:
    """`{lane key: its open captures}`, with `None` for a lane that could not be listed."""
    lanes: Dict[str, Optional[List[dict]]] = {}
    for lane in LANES:
        issues = open_captures(lane)
        lanes[lane.key] = (
            None
            if issues is None
            else [
                {
                    "number": issue["number"],
                    "title": issue["title"],
                    "source": source_of(issue.get("body", "")),
                    "age_days": age_days(issue.get("createdAt", "")),
                }
                for issue in issues
            ]
        )
    return lanes


def capped(lanes: Dict[str, Optional[List[dict]]]) -> Dict[str, int]:
    """Jobs at their cap, counting an issue once however many lanes it carries."""
    seen: Dict[int, str] = {}
    for issues in lanes.values():
        for issue in issues or []:
            seen[issue["number"]] = issue["source"]
    counts: Dict[str, int] = {}
    for source in seen.values():
        if source != SESSION:
            counts[source] = counts.get(source, 0) + 1
    return {source: n for source, n in counts.items() if n >= SOURCE_CAP}


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Print the lanes as JSON.")
def inbox(as_json: bool) -> None:
    """List every open capture, per lane, oldest first.

    \b
    Reads and never closes anything. A lane that could not be listed is
    reported as unread, never as empty.
    """
    lanes = read_lanes()
    at_cap = capped(lanes)
    if as_json:
        emit({"lanes": lanes, "at_cap": at_cap, "cap": SOURCE_CAP})
        return
    for lane in LANES:
        issues = lanes[lane.key]
        if issues is None:
            warn(f"{lane.title}: could not be listed (is gh installed and signed in?)")
            continue
        step(f"{lane.title} — {len(issues)} open, {drain_note(lane)}")
        for issue in issues:
            age = "?" if issue["age_days"] is None else f"{issue['age_days']}d"
            item(f"#{issue['number']} {issue['title']}  ({issue['source']}, {age})")
    detail()
    for source, count in sorted(at_cap.items()):
        warn(f"{source} is at its cap ({count} of {SOURCE_CAP}): it files nothing more until these are closed")
    unread = [lane.title for lane in LANES if lanes[lane.key] is None]
    if unread:
        warn(f"{len(unread)} lane(s) unread: {', '.join(unread)} — this is not an empty inbox")
    elif not any(lanes.values()):
        ok("every lane read, and nothing is open")
