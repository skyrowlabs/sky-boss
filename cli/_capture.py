"""One capture mechanism, worn by every lane in ``scripts/lanes.py``.

Underscore-prefixed because ``cli/__init__.py`` discovers commands by
module name, and this module exports a command *factory* rather than a command.
A public name here would put a ``dev capture`` in ``--help`` that nobody can
usefully run — the lane is the thing you file into, and it is already the
subcommand.

**Why one engine and not one module per intake.** Everything a capture does —
compose the body, refuse an incomplete one, ensure the label exists, file it,
fall back to disk when ``gh`` cannot — is identical across lanes. What differs is
four fields, and those live in the registry. jam.sense arrived at the same split
after writing the second intake, and stated the reason better than a fresh
argument would: *this module's whole job is to stop a finding being lost, and a
second, subtly-different copy of it is how the next intake loses one.*

**There is no ``--label`` override, and its removal is the point.** The template
shipped one on ``dev bug``, defaulting to the lane label and accepting
anything. A capture filed under some other label is a capture nothing lists,
nothing drains, and no editor view shows — the queue *is* the label, so an
override is a way to file into a queue that does not exist. Pick the lane by
picking the subcommand.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence

import click

from scripts.lanes import (
    LANES,
    SESSION,
    SOURCE_CAP,
    SOURCE_ENV,
    Lane,
    drain_note,
    job_registry,
    source_line,
)
from scripts.paths import TMP_DIR

from .helpers import PROJECT_ROOT, current_branch, detail, git, ok, warn

#: Where a capture goes when `gh` cannot file it. One directory per lane, so the
#: fallback partitions the same way the labels do — a flat queue would need its
#: own field to say which lane a file belonged to, which is a second copy of
#: something the path can hold for free.
QUEUE = TMP_DIR / "captures"


def compose(lane: Lane, summary: str, values: dict, source: str = SESSION) -> str:
    """The issue body: one ``##`` section per registry section, in registry order.

    The headings are derived from the section names rather than written out,
    which is what keeps a lane's ``--help``, its body and its template the same
    list. A hand-written body template was the obvious alternative and is how
    the sections and the prose asking for them drift apart.
    """
    parts = []
    for section in lane.sections:
        value = f"```\n{values[section.name]}\n```" if section.fenced else values[section.name]
        parts += [f"## {section.name.replace('_', ' ').title()}", value, ""]
    parts += [
        "---",
        f"_Captured on `{current_branch()}` at `{git('rev-parse', '--short', 'HEAD')}`_",
        source_line(source),
    ]
    return "\n".join(parts)


def capture_source() -> Optional[str]:
    """The job the runner names in the environment, or `None` for a person.

    Any value set is a job key to be checked, `session` included (mind.head), so
    nothing set in the environment can file uncapped.

    Set by the job runner an agentic tree ships, never typed. A flag the agent had
    to remember was a cap it could skip by forgetting (stash.flow, node-zero,
    mind.head), and a key it typed could be mistyped into a fresh cap (proto.pilot).
    """
    return os.environ.get(SOURCE_ENV, "").strip() or None


def standing(source: str) -> Optional[List[str]]:
    """Titles of `source`'s open captures across every lane; `None` if unknown.

    Keyed by issue number, so an issue carrying two lane labels counts once.
    """
    found: Dict[int, str] = {}
    for lane in LANES:
        issues = open_captures(lane)
        if issues is None:
            return None
        for issue in issues:
            if source_line(source) in issue["body"]:
                found[issue["number"]] = issue["title"]
    return list(found.values())


def open_captures(lane: Lane) -> Optional[List[dict]]:
    """A lane's open issues, oldest first; `None` if `gh` could not list them.

    The one place a lane is read back, shared by the cap and by `dev inbox`.
    """
    args = ["gh", "issue", "list", "--label", lane.label, "--state", "open"]
    args += ["--limit", "200", "--json", "number,title,body,createdAt"]
    try:
        result = subprocess.run(args, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return sorted(json.loads(result.stdout or "[]"), key=lambda issue: issue.get("createdAt", ""))


def refusal(source: Optional[str], summary: str, count: Callable[[], Optional[List[str]]]) -> str:
    """Why a capture must not be filed, or `""`. A person is never capped.

    `count` is asked last, so a refusal decidable here makes no `gh` call (node-zero).
    """
    if source is None:
        return ""
    registry = job_registry()
    if registry is None or source not in registry.JOBS_BY_KEY:
        return f"{source!r} is not a registered job"
    open_titles = count()
    if open_titles is None:
        return f"could not list {source}'s open captures, so its cap cannot be checked"
    if summary in open_titles:
        return f"{source} already has this open: {summary!r}"
    if len(open_titles) >= SOURCE_CAP:
        return f"{source} has {len(open_titles)} open captures, at its cap of {SOURCE_CAP}"
    return ""


def _ensure_label(lane: Lane) -> bool:
    """Create the lane's label, idempotently. True if it exists afterwards.

    Called only after a filing attempt has already failed, never speculatively.
    A ``gh label create --force`` on every capture is a write to the repository
    on the success path, which is both noise in the audit log and a permission a
    capture does not otherwise need — and the label is missing exactly once per
    repository, on the first capture into a lane.
    """
    args = ["gh", "label", "create", lane.label, "--color", lane.color]
    args += ["--description", lane.description, "--force"]
    result = subprocess.run(
        args,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _file_issue(lane: Lane, summary: str, body: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", "issue", "create", "--title", summary, "--body", body, "--label", lane.label],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )


def run_capture(lane: Lane, summary: str, values: dict, local: bool) -> None:
    """File one capture, or leave it on disk saying so."""
    source = capture_source()
    body = compose(lane, summary, values, source or SESSION)

    if not local:
        # Checked here, not asked of the filer: an unattended job is told to count
        # its own open captures, and a rule it must remember is one it can forget.
        refused = refusal(source, summary, lambda: standing(source or SESSION))
        if refused:
            warn(f"not filed — {refused}")
            detail("Leave the finding in your report; it is not lost, only not queued.")
            sys.exit(1)
        result = _file_issue(lane, summary, body)
        if result.returncode != 0 and lane.label in result.stderr and _ensure_label(lane):
            # The first capture into a lane, in a repository whose labels nobody
            # has created. Retried once, and once only: a second failure is
            # about `gh`, the network or the remote, and retrying those here
            # just delays the fallback that already handles them.
            detail(f"created the {lane.label} label")
            result = _file_issue(lane, summary, body)

        if result.returncode == 0:
            ok(f"{lane.emoji} captured: {result.stdout.strip()}")
            detail(f"{lane.label} — {drain_note(lane)}")
            detail("Mention this in your response so the user can kill it if they disagree.")
            return
        stderr = result.stderr.strip()
        why = stderr.splitlines()[-1] if stderr else "unknown"
        warn(f"gh failed ({why}) — falling back to a local capture")

    lane_queue = QUEUE / lane.key
    lane_queue.mkdir(parents=True, exist_ok=True)
    fields = {"summary": summary, "label": lane.label, "source": source or SESSION, **values}
    record = json.dumps(fields, indent=2)
    # Exclusive create: five captures in one second wrote one file (node-zero).
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path, n = lane_queue / f"{stamp}.json", 0
    while True:
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(record)
            break
        except FileExistsError:
            n += 1
            path = lane_queue / f"{stamp}-{n}.json"
    ok(f"captured locally: {path.relative_to(PROJECT_ROOT)}")


def capture_command(lane: Lane, help_text: str, epilog: str = "") -> click.Command:
    """Build ``dev <lane.key>`` from the registry.

    The options are generated from ``lane.sections``, which is what makes the
    refusal and the registry the same fact: a section added to the registry is a
    flag the command demands, with no second edit here. All of them are
    ``required`` — see :class:`scripts.lanes.Section` for why that is the
    feature rather than an inconvenience.
    """

    def command(summary: str, local: bool, **values: str) -> None:
        run_capture(lane, summary, values, local)

    command.__doc__ = help_text
    command.__name__ = lane.key

    fallback = f"{QUEUE.relative_to(PROJECT_ROOT)}/{lane.key}/"
    decorators: Sequence[Callable] = [
        click.option("--local", is_flag=True, help=f"write to {fallback} instead of opening an issue"),
        *[click.option(f"--{s.name}", required=True, help=s.help) for s in reversed(lane.sections)],
        click.argument("summary"),
        click.command(name=lane.key, epilog=epilog),
    ]
    built: object = command
    for decorate in decorators:
        built = decorate(built)
    # Asserted rather than cast. `click.option` and friends are untyped enough
    # that a cast would be a promise; this is the same line of code checking
    # the promise, and it fires at import time — where a broken factory is a
    # tree whose CLI does not start, not a test that fails later.
    assert isinstance(built, click.Command)
    return built
