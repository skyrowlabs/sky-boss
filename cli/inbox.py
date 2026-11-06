"""``dev inbox`` — what the capture lanes hold, read back.

``dev bug`` and ``dev task`` file into labelled GitHub issues, and a
capture that succeeds into a queue nobody looks at is indistinguishable, from the
filer's side, from one that was acted on. This is the reading half: every open
capture per lane, oldest first, with who filed it, and every job at its cap, since
a capped job files nothing more until somebody reads what it already filed.

Beside the lanes it lists the open Dependabot pull requests waiting on a person:
red on CI, held as a runtime major, or stopped by a cancelled run. Auto-merge
handles the rest, so a green or running one is not listed.

It reads and never closes anything. A lane or listing it could not read is
reported as unread, never as empty.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime

import click

from scripts.lanes import LANES, SESSION, SOURCE_CAP, drain_note, source_line

from ._capture import open_captures
from .helpers import PROJECT_ROOT, detail, emit, item, ok, step, warn

#: tests/test_cli_smoke.py runs this module's argument-less commands for real.
SMOKE_EXECUTES = True

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


def age_days(created: str, now: datetime | None = None) -> int | None:
    try:
        then = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except _UNPARSEABLE:
        return None
    return ((now or datetime.now(UTC)) - then).days


def read_lanes() -> dict[str, list[dict] | None]:
    """`{lane key: its open captures}`, with `None` for a lane that could not be listed."""
    lanes: dict[str, list[dict] | None] = {}
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


#: Conclusions that name a cause. A red pull request's rollup is mostly cancelled
#: fallout, so listing every check that is not green buries the job that failed.
FAILURE_CLASS = frozenset({"FAILURE", "TIMED_OUT", "STARTUP_FAILURE", "ERROR"})

#: What `dependabot-auto-merge.yml` labels a major it will not merge.
HELD_LABEL = "dependabot-runtime-major"


def open_dependabot_prs() -> list[dict] | None:
    """Dependabot's open pull requests; `None` if `gh` could not list them."""
    args = ["gh", "pr", "list", "--author", "app/dependabot", "--state", "open", "--limit", "200"]
    args += ["--json", "number,title,createdAt,labels,statusCheckRollup"]
    try:
        result = subprocess.run(args, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return sorted(json.loads(result.stdout or "[]"), key=lambda pr: pr.get("createdAt", ""))


def _conclusion(check: dict) -> str:
    """A check run's conclusion, or a commit status's state: the rollup carries both shapes."""
    return (check.get("conclusion") or check.get("state") or "").upper()


def waiting_row(pr: dict) -> dict | None:
    """The row for a pull request waiting on a person, or `None` if it is not."""
    checks = pr.get("statusCheckRollup") or []
    jobs = sorted({c.get("name") or c.get("context") or "?" for c in checks if _conclusion(c) in FAILURE_CLASS})
    held = HELD_LABEL in {label.get("name") for label in pr.get("labels") or []}
    if jobs:
        state, reason = "red", "CI failed, so auto-merge waits"
    elif any(_conclusion(c) == "CANCELLED" for c in checks):
        state, reason = "cancelled", "CI was cancelled, so nothing has judged it"
    elif held:
        state, reason = "held", "a runtime major, which never merges itself"
    else:
        return None
    if held and state != "held":
        reason += "; held as a runtime major too"
    row = {"number": pr["number"], "title": pr["title"], "state": state, "reason": reason, "jobs": jobs}
    return {**row, "age_days": age_days(pr.get("createdAt", ""))}


def read_waiting() -> list[dict] | None:
    """The rows `inbox` lists, oldest first; `None` when the listing failed."""
    prs = open_dependabot_prs()
    return None if prs is None else [row for row in map(waiting_row, prs) if row]


def capped(lanes: dict[str, list[dict] | None]) -> dict[str, int]:
    """Jobs at their cap, counting an issue once however many lanes it carries."""
    seen: dict[int, str] = {}
    for issues in lanes.values():
        for issue in issues or []:
            seen[issue["number"]] = issue["source"]
    counts: dict[str, int] = {}
    for source in seen.values():
        if source != SESSION:
            counts[source] = counts.get(source, 0) + 1
    return {source: n for source, n in counts.items() if n >= SOURCE_CAP}


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Print the lanes as JSON.")
def inbox(as_json: bool) -> None:
    """List every open capture, per lane, oldest first.

    \b
    Then every open Dependabot pull request waiting on a person. Reads and
    never closes anything. A lane or listing that could not be read is reported
    as unread, never as empty.
    """
    lanes = read_lanes()
    at_cap = capped(lanes)
    waiting = read_waiting()
    if as_json:
        emit({"lanes": lanes, "at_cap": at_cap, "cap": SOURCE_CAP, "waiting": waiting})
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
    if waiting:
        step(f"Dependabot — {len(waiting)} waiting on a person")
    for pr in waiting or []:
        age = "?" if pr["age_days"] is None else f"{pr['age_days']}d"
        failed = f": {', '.join(pr['jobs'])}" if pr["jobs"] else ""
        item(f"#{pr['number']} {pr['title']}  ({pr['state']}{failed}, {age}) {pr['reason']}")
    detail()
    for source, count in sorted(at_cap.items()):
        warn(f"{source} is at its cap ({count} of {SOURCE_CAP}): it files nothing more until these are closed")
    unread = [lane.title for lane in LANES if lanes[lane.key] is None]
    if waiting is None:
        warn("Dependabot's pull requests could not be listed (is gh installed and signed in?)")
    if unread:
        warn(f"{len(unread)} lane(s) unread: {', '.join(unread)} — this is not an empty inbox")
    elif waiting is not None and not waiting and not any(lanes.values()):
        ok("every lane read, and nothing is open")
