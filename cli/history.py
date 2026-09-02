"""`sb history` — how did this go the last seven nights. See [[history]].

**Every other observe here is *now*.** `run`, `read`, `follow`, `data`,
`roll-call` and `agents` all answer a question about the present; `schedule`
answers one about the future. The question an operator actually asks about a
nightly job is about the past, and a single green row says the last run was
fine while saying nothing about whether that is normal.

**This reads a provider's ledger. It is not sky.boss's own history**, which does
not exist and is not close — `docs/open.md` item 6. The distinction is kept in
the open rather than papered over, because a `history` that answered a narrower
question than its label is exactly the failure this repo keeps naming.

**The reader is `sb data`'s, whole.** No second opinion about what `--from`
means, and no private line loop — which matters more here than anywhere: an
append-only ledger is being written while it is read, and `parse_text` is where
the torn last line is counted and reported. A hand-rolled `splitlines` here
would drop it in silence. See [[jsonl-reads]] round 4.

**`outcome` is drawn, never judged.** The provider's word is shown as written
and never totalled, ranked, or coloured into a verdict — [[roll-call]]'s
refusal, which bites harder here than it did in [[schedule]]: a schedule row
says *when*, and a history row is the *how it went* sky.boss is not entitled to
interpret. Ordering by time is arithmetic; deciding what `partial` is worth is
not.

**It shows less than `sb data` does, on purpose.** Four columns out of a
ten-field record, because the mapping is the vocabulary round 2 folds across
projects. The whole record is one command away and the help says which.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import rich_click as click

from cli.output import Result, emit
from cli.rollcall import Project, _expand, home_file, load
from cli.schedule import elapsed, now_utc, parse_instant
from cli.view import describe

# What the table draws, and what it keeps but does not draw. The provider's own
# string is **hidden rather than dropped**, which is [[schedule]]'s rule and its
# reason: a machine reading the envelope still gets the timestamp with the
# offset the provider wrote, and a view describes without filtering.
INLINE = ("project", "name", "outcome", "ago")
HIDDEN = ("when", "at")

DEFAULT_LAST = 20


def read_ledger(project: Project) -> tuple[Result, str]:
    """The provider's rows, and the path they came from.

    Resolution goes through [[state-root]] rather than joining paths here, so a
    naming mismatch between `projects.toml` and the root gets the sentence that
    feature exists to produce — *no state directory `jam`; the root holds
    `jam-sense`* — instead of a missing-file error that reads identically to a
    project which has simply not written anything yet.
    """
    from cli import capture as capture_
    from cli.agentstate import resolve
    from cli.data import parse_text

    mapping = project.history or {}
    result = Result()
    declared = _expand(mapping.get("path", ""))
    # An absolute or `~`-prefixed path is taken as written; anything else is a
    # path *under the project's state directory*, which is the address the seam
    # was designed around and the reason nothing here maintains a second table.
    target = declared if Path(declared).is_absolute() else f"{project.name}:{declared}"
    path, problem = resolve(target)
    if problem:
        result.ok = False
        result.data = {"error": problem}
        return result, target

    fmt, trouble = capture_.resolve(mapping.get("from") or "jsonl")
    if trouble:
        result.ok = False
        result.data = {"error": trouble}
        return result, path

    try:
        text = Path(path).read_text()
    except OSError as exc:
        # A project that publishes a ledger and has not written one yet is the
        # normal early state, not an exception.
        result.ok = False
        result.data = {"source": path, "error": exc.strerror or str(exc)}
        return result, path

    # `no_shape` because this command authors its own view. Everything else is
    # the ordinary reader, torn-line accounting included.
    return parse_text(text, {"source": path}, fmt, result, None, None, None, True), path


def rows_of(project: Project, payload, now: datetime) -> tuple[list[dict], list[str]]:
    """One project's history rows, and anything wrong with them."""
    mapping = project.history or {}
    problems: list[str] = []
    if not isinstance(payload, list):
        return [], [f"{project.name}: the ledger did not read as a list of records"]

    out: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        raw = str(item.get(mapping["when"], "") or "")
        when, problem = parse_instant(raw)
        if problem:
            problems.append(f"{project.name}: {problem}")
        outcome = mapping.get("outcome")
        out.append(
            {
                "project": project.name,
                "name": str(item.get(mapping["name"], "") or ""),
                # Absent rather than invented when the project declares no
                # outcome field: a ledger that records only what ran and when
                # is a legitimate ledger, and an empty cell says so.
                "outcome": str(item.get(outcome, "") or "") if outcome else "",
                "ago": elapsed(when, now),
                "when": raw,
                "at": when.timestamp() if when else "",
                "_at": when,
            }
        )
    return out, problems


def order(rows: list[dict]) -> list[dict]:
    """Newest first — the opposite of [[schedule]], and for the same reason it
    sorts the other way: the interesting end of the future is the near one, and
    the interesting end of the past is the recent one.

    A row sky.boss could not place in time goes last, exactly as an unscheduled
    row does. Putting it first would make the least certain thing look like the
    most recent."""
    dated = sorted((r for r in rows if r["_at"]), key=lambda r: r["_at"], reverse=True)
    return dated + [r for r in rows if not r["_at"]]


def view_of(rows: list[dict]) -> dict:
    """Authored, not inferred — these are sky.boss's own four keys, so there is
    nothing to infer. Widths come from `cli/view.py` so flex keeps one opinion.
    See [[table-views]] and [[schedule]] round 3."""
    return {
        "columns": [describe(key, rows) for key in INLINE],
        "details": [],
        "hidden": list(HIDDEN),
        "authored": True,
    }


@click.command(name="history")
@click.argument("project", required=False)
@click.option(
    "--last",
    type=int,
    default=DEFAULT_LAST,
    metavar="N",
    help=f"How many of the most recent runs to draw. Default {DEFAULT_LAST}; 0 draws all of them.",
)
@emit
def history(project: str | None, last: int) -> Result:
    """A project's own run ledger, newest first.

        sb history jam-sense
        sb history jam-sense --last 50

    An observe — a window may pin it and refresh it on a cadence. It reads the
    file the project declares under `[project.X.history]` and never writes,
    prunes, or compacts it.

    Four columns out of whatever the provider records. For the whole record,
    read the same file directly: `sb data <project>:<path> --from jsonl`.
    """
    result = Result()
    projects, problems = load()
    for problem in problems:
        result.warn(problem)

    declared = [p for p in projects if p.history]
    if not project:
        # A missing argument that names the candidates, rather than Click's
        # "Missing argument 'PROJECT'", which is true and tells you nothing
        # about which words would have worked.
        if not declared:
            raise click.UsageError(f"no project declares a history — see {home_file()}")
        raise click.UsageError(
            f"name a project: {', '.join(sorted(p.name for p in declared))}"
        )

    found = next((p for p in projects if p.name == project), None)
    if found is None:
        names = sorted(p.name for p in projects)
        known = f" (declared: {', '.join(names)})" if names else ""
        raise click.UsageError(f"no such project: {project}{known}")
    if not found.history:
        # Not an error: the project exists and publishes no ledger. Said out
        # loud rather than drawn as an empty table, which would read as *this
        # project has never run anything*.
        result.data = []
        result.warn(f"{project} declares no history — see {home_file()}")
        return result

    answer, source = read_ledger(found)
    for warning in answer.warnings:
        result.warn(warning)
    if not answer.ok:
        reason = (answer.data or {}).get("error", "did not read")
        result.ok = False
        result.data = {"source": source, "error": reason}
        return result

    now = now_utc()
    rows, trouble = rows_of(found, answer.data, now)
    for problem in trouble:
        result.warn(problem)

    rows = order(rows)
    total = len(rows)
    if last > 0 and total > last:
        # **Never a silent cap.** A truncated table that does not say so reads
        # as the whole history, which is the one thing a history must not do.
        rows = rows[:last]
        result.warn(f"showing the last {last} of {total} runs — `--last 0` for all of them")

    result.data = [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows]
    if result.data:
        result.view = view_of(result.data)
    elif not total:
        result.warn(f"{project} has no runs recorded — {source} is empty")
    return result
