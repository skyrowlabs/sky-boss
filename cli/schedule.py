"""`sb schedule` — what fires next, across every project that declares one.

**Derived on demand, never stored.** `CLAUDE.local.md` records the operator's
own rule for the fact this answers: *derive it by reading `crontab -l` — never
copy it into a file, here or there*. That instruction is right, and it is also
the whole problem: the only sanctioned way to learn when a grid runs was to
read a crontab and hold the answer in your head, because writing it down
creates a copy that goes stale. A view is the third option — correct because it
is re-read rather than remembered.

**It schedules nothing.** [[roll-call]]'s boundary, unmoved: the agents that own
a project own its grid. This reads what they publish.

**Two refusals do most of the work here** and both are the same shape as
`sb read` showing bytes verbatim:

- `schedule` is **opaque and never parsed**. `15 5 * * *` is drawn exactly as
  the provider wrote it. Parsing it means a second implementation of cron
  semantics beside the real one, and it will be wrong about DST before it is
  wrong about anything else.
- `next` is **provider-supplied or absent**. sky.boss never computes it from
  `schedule`, because a *wrong* next-fire time is worse than none — it looks
  like an answer.

**This is not the vocabulary [[roll-call]] refuses**, and the distinction is the
one to apply to the next case: *sky.boss may order; only a provider may judge.*
Ordering two timestamps is arithmetic nobody invented. Ranking two status words
is an opinion, and it stays the provider's. See [[schedule]].
"""

from __future__ import annotations

from datetime import datetime

import rich_click as click

from cli.output import Result, emit
from cli.rollcall import Project, ask, home_file, load


def parse_instant(value: str) -> tuple[datetime | None, str | None]:
    """A provider's timestamp as an instant, or the reason it is not one.

    **An offset is required.** A naive timestamp is a declaration error reported
    as one, rather than something to guess a zone for — guessing is how a view
    is confidently six hours wrong. The payload already carries the trap: one
    response, the same jobs, `next_run` stamped `-05:00` and `last_run` stamped
    `+00:00`. A lexical sort is correct today only because 31 values happen to
    share an offset, and a view that sorts "last ran" against "next runs" breaks
    that by construction.
    """
    if not value:
        return None, None
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return None, f"{value!r} is not a timestamp"
    if when.tzinfo is None:
        return None, f"{value!r} has no UTC offset — sky.boss will not guess one"
    return when, None


def rows_of(project: Project, payload) -> tuple[list[dict], list[str]]:
    """One project's schedule rows, and anything wrong with them.

    The provider's own strings are kept and drawn as written, offsets included:
    two projects disagreeing about what time it is should be *visible* rather
    than merged into a resolution nobody made. The parsed instant rides
    alongside for ordering only.
    """
    mapping = project.schedule or {}
    problems: list[str] = []

    source = payload
    key = mapping.get("rows")
    if key:
        if not isinstance(payload, dict) or key not in payload:
            return [], [f"{project.name}: no {key!r} in its payload"]
        source = payload[key]
    if not isinstance(source, list):
        return [], [f"{project.name}: schedule rows are not a list"]

    out: list[dict] = []
    for item in source:
        if not isinstance(item, dict):
            continue
        row = {"project": project.name, "name": str(item.get(mapping["name"], "") or "")}
        for field in ("schedule", "next", "last"):
            key = mapping.get(field)
            row[field] = str(item.get(key, "") or "") if key else ""
        when, problem = parse_instant(row["next"])
        if problem:
            problems.append(f"{project.name}/{row['name']}: {problem}")
        row["_at"] = when
        out.append(row)
    return out, problems


def order(rows: list[dict]) -> list[dict]:
    """By the parsed instant, with everything unscheduled after everything that
    is. A row with no `next` has nowhere honest to sit among rows sorted by
    time, and putting it first would make the *least* certain thing look the
    most imminent."""
    dated = sorted((r for r in rows if r["_at"]), key=lambda r: r["_at"])
    undated = [r for r in rows if not r["_at"]]
    return dated + undated


@click.command(name="schedule")
@click.option("--only", metavar="NAMES", help="Ask only these projects, comma-separated.")
@emit
def schedule(only: str | None) -> Result:
    """What fires next, across every project that declares a schedule.

        sb schedule
        sb schedule --only jam-sense

    An observe — a window may pin it and refresh it on a cadence. It reads what
    each project publishes and never schedules, generates, or edits one.
    """
    result = Result()
    projects, problems = load()
    for problem in problems:
        result.warn(problem)

    wanted = {n.strip() for n in only.split(",")} if only else None
    if wanted:
        missing = wanted - {p.name for p in projects}
        if missing:
            raise click.UsageError(f"no such project: {', '.join(sorted(missing))}")
        projects = [p for p in projects if p.name in wanted]

    declared = [p for p in projects if p.schedule]
    if not projects:
        result.data = []
        if not problems:
            result.warn(f"no projects declared — see {home_file()}")
        return result

    # **Counted, never drawn.** A project with no schedule is the common case
    # and is not an error, but silence about it is indistinguishable from a
    # project whose schedule is empty. The arithmetic is the whole report.
    if len(declared) < len(projects):
        result.warn(
            f"{len(declared)} of {len(projects)} projects declare a schedule — "
            f"no schedule for {', '.join(sorted(p.name for p in projects if not p.schedule))}"
        )
    if not declared:
        result.data = []
        return result

    rows: list[dict] = []
    for project in declared:
        answer = ask_schedule(project)
        if not answer.ok:
            # Named, never omitted — roll-call's rule, and for its reason: a
            # view that quietly drops the project that could not answer is
            # worse than one that says so, because the silence looks like an
            # empty calendar.
            reason = (answer.data or {}).get("error", "did not answer")
            result.warn(f"{project.name}: {reason}")
            result.partial = True
            continue
        found, trouble = rows_of(project, answer.data)
        for problem in trouble:
            result.warn(problem)
        rows.extend(found)

    result.data = [{k: v for k, v in row.items() if k != "_at"} for row in order(rows)]
    return result


def ask_schedule(project: Project) -> Result:
    """The project's payload, read **without** its declared `cols`.

    The operator narrows roll-call's columns to what roll-call draws — for
    jam.sense that is `job,result,last_age,overdue`, which throws `schedule` and
    `next_run` away at the view layer. The schedule mapping names its own
    fields, so it has to see the whole row. Same reader, same subprocess
    contract, one narrowing removed.
    """
    from dataclasses import replace

    return ask(replace(project, cols=""))


# Offered to an agent for the reason `roll-call` is: it takes no argv from its
# caller and reads only what the operator declared. See [[mcp]] round 1.
schedule.sb_mcp = True
