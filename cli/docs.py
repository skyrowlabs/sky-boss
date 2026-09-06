"""``dev docs`` — the documentation lifecycle.

Everything here is mechanical on purpose. The docs discipline in
``docs/rules/docs.md`` only survives if following it is cheaper than not, and
these commands are what make it cheaper.
"""

from __future__ import annotations

import shutil
import sys

import click

from cli.helpers import PROJECT_ROOT, detail, fail, git, item, line, ok, run, script, step, warn

# Imported, not redefined. These were declared here *and* in `scripts/docs/plans.py`
# — two owners for the two directories the whole docs lifecycle moves files between.
from scripts.paths import IMPL_DIR, TODO_DIR  # noqa: E402


@click.group()
def docs() -> None:
    """Documentation indexes, plan filing, and report windows."""


@docs.command()
@click.option("--check", "check_only", is_flag=True, help="report staleness; write nothing")
def index(check_only: bool) -> None:
    """Regenerate (or verify) every derived docs artifact."""
    sys.exit(script("scripts/docs/regen.py", *(["--check"] if check_only else [])))


@docs.command(name="release-window")
@click.option("--release", help="resolve a frozen release's window")
@click.option("--apply", "apply_", is_flag=True, help="stamp the anchor onto in-flight reports")
@click.option("--only", help="with --apply: stamp exactly one report")
@click.option("--check", "check_only", is_flag=True, help="validate every anchor")
def release_window(release: str, apply_: bool, only: str, check_only: bool) -> None:
    """Resolve, stamp, or validate the report window."""
    args = []
    if release:
        args += ["--release", release]
    if apply_:
        args += ["--apply"]
    if only:
        args += ["--only", only]
    if check_only:
        args += ["--check"]
    sys.exit(script("scripts/docs/release_window.py", *args))


@docs.command(name="freeze-release")
@click.option("--tag", required=True, help="the release tag whose window is closing")
@click.option("--dry-run", is_flag=True, help="show what would happen, changing nothing")
def freeze_release(tag: str, dry_run: bool) -> None:
    """Close the report window at a release and freeze the editions.

    Run this AFTER the narrative pass that rewrites each report for the closing
    window — this does the mechanical half only, and a frozen edition carrying a
    window it does not describe is worse than an unfrozen one.
    """
    args = ["--tag", tag] + (["--dry-run"] if dry_run else [])
    sys.exit(script("scripts/docs/freeze_release.py", *args))


@docs.command()
@click.argument("slug")
@click.option("--category", required=True, help="subdirectory under docs/implementations/")
@click.option("--dry-run", is_flag=True, help="show what would happen, changing nothing")
@click.option("--force", is_flag=True, help="file the plan even with open tasks")
def file(slug: str, category: str, dry_run: bool, force: bool) -> None:
    """Move a completed plan from the holding tank to the archive.

    Does the whole sequence — `git mv`, frontmatter, both indexes, both READMEs —
    and **commits nothing**. Read the diff before you commit it: a filing is the
    one docs operation that silently invalidates links in two directions.
    """
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.docs import plans  # imported late so `--help` needs no repo scan

    source = TODO_DIR / f"{slug}.md"
    if not source.exists():
        fail(f"no such plan: docs/TODO/{slug}.md")
        candidates = sorted(p.stem for p in TODO_DIR.glob("*.md") if slug in p.stem)
        if candidates:
            detail(f"did you mean: {', '.join(candidates)}")
        sys.exit(1)

    plan = plans.load(source)
    if plan.auto_generated:
        fail(f"{slug} is agent-managed (auto_generated: true) — its producing job recreates it.")
        detail("Filing it would leave a zombie behind. Nothing to do here.")
        sys.exit(1)

    open_tasks = plan.open_tasks()
    if open_tasks and not force:
        fail(f"{slug} still has {len(open_tasks)} unchecked task(s):")
        for task in open_tasks[:5]:
            item(task)
        detail("Tick them, mark them (~operator)/(~deferred), or pass --force.")
        sys.exit(1)

    target = IMPL_DIR / category / f"{slug}.md"
    if target.exists():
        fail(f"already archived: {target.relative_to(PROJECT_ROOT)}")
        sys.exit(1)

    step(f"git mv docs/TODO/{slug}.md docs/implementations/{category}/{slug}.md")
    if dry_run:
        warn("dry run — nothing changed")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    # `git mv` and not `mv`: a plain move leaves the old path tracked, so the
    # plan exists in both trees and "what is left to do" stops being answerable.
    if run(["git", "mv", str(source), str(target)]).returncode != 0:
        shutil.move(str(source), str(target))
        run(["git", "add", str(target)])

    # Strip the tank-only header lines, then let the backfill strip their
    # frontmatter twins. Both halves are needed and neither is sufficient: a
    # header beats frontmatter by design, so cleaning the frontmatter alone
    # leaves the plan reporting its old shelf to every reader forever — which
    # is exactly what happened, for as long as this step did not exist.
    #
    # This lives here rather than in the backfill because the backfill runs on
    # every `docs index` and must not rewrite anybody's prose. A filing is the
    # one deliberate moment that knows the plan has stopped being a tank plan.
    text = target.read_text(encoding="utf-8")
    stripped = plans.strip_tank_headers(text)
    if stripped != text:
        target.write_text(stripped, encoding="utf-8")
        step("removed the tank-only header lines")

    script("scripts/docs/regen.py")
    ok(f"filed {slug} → docs/implementations/{category}/")
    detail()
    detail("Next, repoint what cited the old path (repoint, never delete):")
    detail("  dev check doc-refs")
    detail("  dev check doc-links")


@docs.command(name="queue-order")
@click.argument("slug")
@click.argument("position", type=int)
def queue_order(slug: str, position: int) -> None:
    """Set a ready plan's position in the build queue.

    Refuses a position another plan already claims, and names a free one — two
    plans at the same number reintroduces the alphabetical tiebreak the
    numbering exists to remove.
    """
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.docs import plans

    source = TODO_DIR / f"{slug}.md"
    if not source.exists():
        fail(f"no such plan: docs/TODO/{slug}.md")
        sys.exit(1)

    taken = {p.queue_order: p.slug for p in plans.scan(TODO_DIR) if p.queue_order is not None and p.slug != slug}
    if position in taken:
        free = next(n for n in range(position, position + 1000) if n not in taken)
        fail(f"position {position} is held by '{taken[position]}' — {free} is free")
        sys.exit(1)

    text = source.read_text(encoding="utf-8")
    lines = text.splitlines()
    new_line = f"> **Queue-Order**: {position}"
    # Named `existing`, not `line`: `line` is the stdout writer imported above,
    # and a loop variable that shadows it turns the next call into a TypeError.
    for i, existing in enumerate(lines):
        if existing.startswith("> **Queue-Order**:"):
            lines[i] = new_line
            break
    else:
        anchor = next((i for i, existing in enumerate(lines) if existing.startswith("> **Priority**:")), None)
        if anchor is None:
            anchor = next((i for i, existing in enumerate(lines) if existing.startswith("> **Shelf-Status**:")), 0)
        lines.insert(anchor + 1, new_line)
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")

    script("scripts/docs/regen.py")
    ok(f"{slug} is now at queue position {position}")
    line()
    line("Resulting run order:")
    from scripts.docs.queue_order import run_order

    ready = sorted(
        (p for p in plans.scan(TODO_DIR) if p.shelf_status == "ready"), key=lambda p: run_order(p.to_entry())
    )
    for i, plan in enumerate(ready, 1):
        pos = plan.queue_order if plan.queue_order is not None else "—"
        line(f"   {i}. [{pos}] {plan.slug} ({plan.priority})")


@docs.command()
def status() -> None:
    """One screen: what is in the tank, and what is at the front of the queue."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.docs import plans
    from scripts.docs.queue_order import run_order

    tank = plans.scan(TODO_DIR)
    counts: dict = {}
    for plan in tank:
        counts[plan.shelf_status] = counts.get(plan.shelf_status, 0) + 1

    line(f"Holding tank: {len(tank)} plans on {git('rev-parse', '--abbrev-ref', 'HEAD')}")
    for status_name in plans.SHELF_STATUSES:
        if counts.get(status_name):
            line(f"   {status_name:<12} {counts[status_name]}")

    ready = sorted(
        (p for p in tank if p.shelf_status == "ready" and not p.auto_generated), key=lambda p: run_order(p.to_entry())
    )
    if ready:
        line()
        line("Ready queue (run order):")
        for i, plan in enumerate(ready[:10], 1):
            pos = plan.queue_order if plan.queue_order is not None else "—"
            line(f"   {i}. [{pos}] {plan.slug} ({plan.priority})")

    review = [p for p in tank if p.shelf_status == "in-review"]
    if review:
        line()
        line("Awaiting your review:")
        for plan in review:
            line(f"   · {plan.slug} → {plan.review_pr or 'no PR recorded'}")
