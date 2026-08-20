"""tb check — the evaluative mood.

Every command in this group has one shape: read some state, judge it against an
expectation, and return rows carrying ``ok``. That is exactly the shape the
output contract renders as a status list, which is why the bare ``tb check``
rollup below needs no per-check special casing — it only has to ask each check
whether it came back clean.

**Nothing in this group writes.** That is not a style convention: it is the
property that lets the MCP surface expose the whole group without an allowlist.
A check that needs to change something is not a check; it is a job.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

import rich_click as click

from cli.assets import check_drift
from cli.doctor import check_tools
from cli.output import Result, emit
from cli.unpushed import check_unpushed


@dataclass(frozen=True)
class Check:
    """One registered check.

    ``run`` takes no arguments on purpose. The rollup has to be able to invoke
    every check identically, so anything configurable belongs in the subcommand's
    own flags and must have a usable default.
    """

    name: str
    summary: str
    run: Callable[[], Result]


REGISTRY: tuple[Check, ...] = (
    Check("drift", "This machine vs its inventory record", check_drift),
    Check("tools", "External CLIs installed and authenticated", check_tools),
    Check("unpushed", "Work that exists on only one disk", check_unpushed),
)


def _detail(sub: Result) -> str | None:
    """One line summarizing a sub-check, for the rollup's detail column."""
    if not sub.ok:
        error = sub.data.get("error") if isinstance(sub.data, dict) else None
        return f"check failed: {error}" if error else "check failed"
    if not sub.partial:
        return None
    if len(sub.warnings) == 1:
        return sub.warnings[0]
    return f"{len(sub.warnings)} problems"


def run_all() -> Result:
    """Run every registered check and roll the verdicts into one status list.

    One row per *check*, not per item. The checks return heterogeneous data —
    doctor's rows are keyed by tool, unpushed's by repo — so the rollup reduces
    each to a single verdict rather than trying to merge shapes that have nothing
    in common.
    """
    rows: list[dict] = []
    result = Result()

    for entry in REGISTRY:
        try:
            sub = entry.run()
        except Exception as exc:  # noqa: BLE001 — one broken check must not hide the rest
            if os.environ.get("TB_DEBUG"):
                raise
            rows.append(
                {
                    "check": entry.name,
                    "ok": False,
                    "detail": f"{exc.__class__.__name__}: {exc}",
                }
            )
            result.degrade(f"{entry.name}: the check itself failed — {exc}")
            continue

        # A sub-check that is `partial` found problems; that is its verdict, not
        # a degraded run. Both collapse to "not clean" for the rollup.
        clean = sub.ok and not sub.partial
        rows.append({"check": entry.name, "ok": clean, "detail": _detail(sub)})

        for warning in sub.warnings:
            result.warn(f"{entry.name}: {warning}")
        if not clean:
            result.partial = True

    rows.sort(key=lambda row: (row["ok"], row["check"]))
    result.data = rows

    # Deliberately never `ok=False`. The rollup reporting that four checks failed
    # is the rollup working, the same reasoning `tb check tools` applies to
    # itself. Exit 3 is "something needs you"; exit 1 would mean tb broke.
    return result


@click.group(invoke_without_command=True)
@click.option("--list", "list_only", is_flag=True, help="Name the checks without running them.")
@click.pass_context
def check(ctx: click.Context, list_only: bool) -> None:
    """Read state, judge it, return a verdict. Writes nothing.

    With no subcommand, runs every check and reports worst-first.
    """
    if ctx.invoked_subcommand is not None:
        if list_only:
            raise click.UsageError("--list takes no subcommand")
        return
    # `_rollup` is emit-wrapped, so calling it here picks up this group's own
    # context — the envelope is named "check" and the exit code is set for us.
    _rollup(list_only)


@emit
def _rollup(list_only: bool) -> Result:
    if list_only:
        return Result(data=[{"check": entry.name, "summary": entry.summary} for entry in REGISTRY])
    return run_all()


from cli.assets import drift as drift_cmd  # noqa: E402
from cli.doctor import tools as tools_cmd  # noqa: E402
from cli.unpushed import unpushed as unpushed_cmd  # noqa: E402

check.add_command(drift_cmd)
check.add_command(tools_cmd)
check.add_command(unpushed_cmd)
