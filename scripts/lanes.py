"""The capture lanes — one registry for every label this tree files agent work into.

A lane is a GitHub label plus the shape of a body that may be filed under it. It
is a registry because four things need the same answer and had, before this, no
way to agree:

* ``cli/bug.py`` and ``cli/task.py``, which file into one.
* ``scripts/gen_vscode_queries.py``, which renders the editor's issue views from
  the set — so a lane that exists is a lane you can see.
* ``gh label create``, run once per lane at setup, because a label that does not
  exist makes ``gh issue create --label`` fail with a message about the label
  rather than about the capture.
* ``tests/test_lanes.py``, which is what makes the three above provably one set.

**Why a registry rather than a constant in each command.** The template shipped
``dev bug`` with ``--label agent-bug`` as a default argument and nothing that
read it back. Filing worked; the queue was invisible. A second intake written the
same way would have been a second invisible queue, and the two would have
disagreed about their own label the first time one was renamed — which is the
failure this shell exists to prevent, in the one module whose whole job is to
stop a finding being lost.

The design is jam.sense's. Theirs is a ``Capture`` descriptor driving one engine
with two shapes, and their reason for it is the one that generalises: *a second,
subtly-different copy of a capture is how the next intake loses a finding.*

**What is deliberately not here: the drain.** A lane names the job key that would
empty it, and this template ships no such job — ``scripts/reporting/jobs.py``
(SCAFFOLD-OPTIONAL scripts/reporting/jobs.py — it arrives with the agentic tier,
and every reader below tests for it rather than assuming it)
ships exactly one fully-worked entry on purpose, and a registry seeded with keys
whose modules do not exist is a registry whose own tests are red on arrival. So
:func:`drainer_of` answers *honestly* rather than optimistically, and every
consumer renders what it gets: a fresh tree's queues are drained by you, and say
so. Add a job with the lane's ``drainer_job`` key and every consumer picks up its
schedule with no second edit.
"""

from __future__ import annotations

from typing import Any, List, NamedTuple, Optional, Tuple

from scripts.paths import SCRIPTS_DIR


class Section(NamedTuple):
    """One required part of a capture body.

    Required, all of them, in every lane. A capture missing a section is not a
    smaller capture — it is one whose reader has to come back and ask, and the
    person who could have answered has moved on. The refusal is the feature.
    """

    #: The flag name (``--finding``) and the ``## Finding`` heading it becomes.
    name: str
    #: Shown in ``--help``. What the section must actually say, not what it is
    #: called — ``path:line + what is wrong`` rather than ``the finding``.
    help: str
    #: Wrap the value in a code fence in the rendered issue body. For sections
    #: whose content is a command somebody will copy: a fenced block survives
    #: GitHub's markdown intact, and an unfenced one has its underscores eaten
    #: and its newlines joined, which is how a reproduction stops reproducing.
    fenced: bool = False


#: A defect found while doing something else. Every section here answers a
#: question the fixer would otherwise have to come back for, and `reproduce` is
#: the one that makes it a bug report rather than a rumour.
BUG_SECTIONS: Tuple[Section, ...] = (
    Section("finding", "path:line + what is wrong"),
    Section("reproduce", "exact command; observed vs expected", fenced=True),
    Section("scope", "what is in, and what is explicitly out"),
    Section("acceptance", "the assertions; the command that must pass"),
)

#: Small work that is not a defect. It cannot answer `--reproduce` — there is no
#: failure to reproduce — which is exactly why a flag on the bug intake was the
#: wrong shape and this is a second lane. `why` is not decoration: it is what
#: stops a task queue becoming a wish list.
TASK_SECTIONS: Tuple[Section, ...] = (
    Section("what", "the change itself, in terms of the files it touches"),
    Section("why", "what is worse today because this has not been done"),
    Section("acceptance", "the assertions; the command that must pass"),
)


class Lane(NamedTuple):
    """One capture queue: a label, the body it accepts, and who empties it."""

    #: The subcommand that files into it — ``dev bug``, ``dev task``.
    key: str
    #: The GitHub label. The queue IS this label; nothing else identifies it.
    label: str
    #: Hex, no leading ``#`` — what ``gh label create --color`` wants.
    color: str
    description: str
    sections: Tuple[Section, ...]
    #: Shown in the editor's issue view. Human words, because that is where it
    #: is read; the label is the machine name and is shown in the query itself.
    title: str
    #: The `scripts/reporting/jobs.py` key of the job that would drain this
    #: queue. Nothing here asserts it exists — see :func:`drainer_of`, and this
    #: module's docstring for why shipping the job would be worse.
    drainer_job: str
    emoji: str


#: Both lanes ship with the command that fills them, which is the whole
#: enrolment rule: **a lane with no producer is a view that is empty forever,
#: and an empty view and a healthy queue render identically.** Adding a lane
#: means adding its intake in the same change; `tests/test_lanes.py` fails
#: otherwise, and `scripts/gen_vscode_queries.py` would otherwise put a
#: permanently-blank pane in the editor of everyone who scaffolds.
LANES: List[Lane] = [
    Lane(
        key="bug",
        label="agent-bug",
        color="d93f0b",
        description="A defect captured mid-session; queued for a fix drainer",
        sections=BUG_SECTIONS,
        title="Agent Bugs",
        drainer_job="agent-bug",
        emoji="🐛",
    ),
    Lane(
        key="task",
        label="agent-task",
        color="0e8a16",
        description="Small self-contained work captured mid-session; queued for a task drainer",
        sections=TASK_SECTIONS,
        title="Agent Tasks",
        drainer_job="agent-task",
        emoji="🧹",
    ),
]

LANES_BY_KEY = {lane.key: lane for lane in LANES}
LANES_BY_LABEL = {lane.label: lane for lane in LANES}


def labels() -> List[str]:
    """Every lane label, in registry order. The set the editor views partition."""
    return [lane.label for lane in LANES]


def job_registry() -> Optional[Any]:
    """`scripts.reporting.jobs` if this tree ships it, else ``None``.

    Typed `Optional[Any]` rather than `Optional[object]`, and that is a real
    choice rather than laziness: the module is resolvable at some tiers and not
    others, so there is no annotation that is true everywhere, and `object`
    makes every attribute access on the result an error at every tier —
    including the ones that ship the module. `Any` says *this is decided at
    runtime*, which is what the `.exists()` guard above already says.

    **The one place this template imports a module it may not ship**, and it is
    one place on purpose. `scripts/reporting/` arrives with the agentic tier, so
    at `core` the import below is unresolvable — and it was written twice, here
    and in `gen_vscode_queries.py`, which is two sites for a construct that
    needs a paragraph of explanation each.

    Imported inside a function rather than at module scope for two reasons, and
    only the second survives a tier change: the registry is optional, and a lane
    is a fact about labels that must not acquire a dependency on the scheduler
    to be read. `gh label create` at setup time needs this module and has no
    business importing a cron registry.

    **THE LIMIT, and this tree cannot see it.** A `.exists()` guard is a runtime
    fact; the `import` under it is syntax, and every static checker reads it
    unconditionally. pyright says nothing here only because
    `reportMissingImports` is `none` in `pyrightconfig.json` — so the tool this
    template ships is the reason the template cannot observe its own hazard, and
    an adopter who runs mypy blocking gets a hard error at `core` on a clean
    upgrade. mind.head reported it from exactly that tree. Two doors if it bites
    you: silence the one line for your checker, or scaffold at a tier that ships
    the registry. It is deliberately not routed through `importlib` to hide it —
    that trades a false error at `core` for no type information at `agentic`,
    which is paying at the tier that has something to check.
    """
    if not (SCRIPTS_DIR / "reporting" / "jobs.py").exists():
        return None
    from scripts.reporting import jobs  # noqa: PLC0415  (see docstring)

    return jobs


def drainer_of(lane: Lane) -> Optional[object]:
    """The registered job that drains this lane, or ``None`` if nothing does.

    Two ways to get ``None`` and they are deliberately the same answer, because
    they are the same fact to everyone downstream: this tier ships no job
    registry at all, or it ships one and no job has claimed this lane's key.
    Either way the queue is drained by a person, and every consumer says so in
    those words.
    """
    registry = job_registry()
    return None if registry is None else registry.JOBS_BY_KEY.get(lane.drainer_job)


def drain_note(lane: Lane) -> str:
    """How this lane is emptied, as the words a reader sees.

    Composed from the job registry rather than stored on the :class:`Lane`,
    because the alternative is a second copy of a schedule the registry already
    owns — and jam.sense measured that copy going stale exactly as you would
    expect: their task lane's prose said 07:00 for two weeks after the 07:00
    fire was retired, one import away from the registry field that said 07:45.
    The string is printed on a path nobody re-reads (a capture that succeeded),
    so drift in it stays invisible until somebody plans around it.

    Falls back to the job's own ``cadence`` prose whenever the schedule is not a
    plain daily ``M H * * *``. A weekly or monthly drainer has no single clock
    time to name, and inventing one would be the defect above with extra steps.
    """
    job = drainer_of(lane)
    if job is None:
        return "nothing drains these"
    fields = getattr(job, "cron", "").split()
    if len(fields) == 5 and fields[2:] == ["*", "*", "*"] and fields[0].isdigit() and fields[1].isdigit():
        return f"{int(fields[1]):02d}:{int(fields[0]):02d} lane"
    return f"{getattr(job, 'cadence', 'scheduled')} lane"
