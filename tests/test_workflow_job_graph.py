"""Every `needs:` and every `needs.<job>` names a job that exists.

Removing a job is ordinary. The reference that outlives it is never in the block
you edited, and the failure it produces is the least legible one GitHub has:

> **A `needs:` naming a job that does not exist is not a red job — it is a
> `startup_failure`.** The workflow is rejected before scheduling, so there are
> zero jobs, no logs, `gh run view --log-failed` answers "log not found", and
> nothing on the commit names the line.

Found by proto.pilot, who took the `ui` suite's documented exemption — nothing
in their tree is marked `ui`, so they set `scheduled=False` and deleted the job
— and hit it on the next push. Nothing local objected: valid YAML, every
pre-push gate green, and `test_ci_runs_every_suite.py` satisfied, because about
a suite with no marker and no job the registry and the workflows agree
perfectly. The template shipped `needs: [lint, unit-tests, integration, ui]` and
documented deleting `ui` in the same breath.

`actionlint` would catch it and is not the answer here. It runs against what
skeletor ships, in skeletor's own verifier, where the job is still present. This
failure happens in a tree that has edited the file — which is precisely the
place the shipped checks have to live.

## The expression direction

`needs.<job>.outputs.x` in an `if:` is the same mistake with a quieter result:
an unknown context is not an error, it evaluates to null, the condition is false
and the job is skipped. Branch protection accepts a skipped required check, so
the PR merges having run less than it reports. Same job set, same parse, one
more assertion.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanning import scanned  # noqa: E402
from scripts.paths import GITHUB_DIR  # noqa: E402
from scripts.yaml_text import read_uncommented  # noqa: E402

WORKFLOWS = GITHUB_DIR / "workflows"

#: A top-level key of the `jobs:` mapping — two spaces in, nothing after the
#: colon. Deliberately not a YAML parse: this tree ships no YAML library, and
#: the shape being read is two levels deep and fixed by Actions' own schema.
_JOB = re.compile(r"^  (?P<id>[A-Za-z_][A-Za-z0-9_-]*):\s*$", re.MULTILINE)
_JOBS_BLOCK = re.compile(r"^jobs:\s*$", re.MULTILINE)
_NEEDS_INLINE = re.compile(r"^\s+needs:\s*(?P<value>\S.*)$", re.MULTILINE)
_NEEDS_BLOCK = re.compile(r"^\s+needs:\s*$\n(?P<items>(?:\s+-\s+\S+\n)+)", re.MULTILINE)
_NEEDS_CONTEXT = re.compile(r"\bneeds\.(?P<id>[A-Za-z_][A-Za-z0-9_-]*)\b")


def workflows() -> list:
    return scanned(sorted(WORKFLOWS.glob("*.yml")), "workflow files", least=2)


def jobs_in(text: str) -> set:
    """The job ids declared in `text`."""
    start = _JOBS_BLOCK.search(text)
    return {m.group("id") for m in _JOB.finditer(text, start.end())} if start else set()


def needs_in(text: str) -> set:
    """Every job id named by a `needs:`, inline or block.

    The inline form is normalised from its **string** shape as well as its list
    shape. `needs: ui` is a bare scalar, and iterating a string yields
    characters — proto.pilot's first version of this reported four bogus
    findings on a correct workflow for exactly that reason.
    """
    named = set()
    for match in _NEEDS_INLINE.finditer(text):
        value = match.group("value").strip().strip("[]")
        named.update(part.strip().strip("'\"") for part in value.split(",") if part.strip())
    for match in _NEEDS_BLOCK.finditer(text):
        named.update(line.strip().lstrip("-").strip().strip("'\"") for line in match.group("items").splitlines())
    return {name for name in named if name}


def test_the_scan_reads_real_jobs():
    """A parser that found no jobs would make both assertions below vacuous.

    `needs` is asserted too: a workflow here certainly has one, so a `needs_in`
    that matched nothing would leave "every reference resolves" trivially true.
    """
    found = {}
    for path in workflows():
        text = read_uncommented(path)
        found[path.name] = (jobs_in(text), needs_in(text))

    total_jobs = scanned([j for jobs, _ in found.values() for j in jobs], "jobs across the workflows", least=3)
    total_needs = [n for _, needs in found.values() for n in needs]

    assert total_needs, f"no `needs:` found in any workflow — the parser is broken. Saw: {found}"
    assert len(total_jobs) >= 3, found


def test_every_needs_names_a_job_in_the_same_workflow():
    dangling = {}
    for path in workflows():
        text = read_uncommented(path)
        missing = sorted(needs_in(text) - jobs_in(text))
        if missing:
            dangling[path.name] = missing

    assert not dangling, (
        f"a `needs:` names a job that does not exist: {dangling}. GitHub rejects the whole "
        "workflow before scheduling — that is a `startup_failure` with zero jobs and no logs, "
        "not a red check. Delete the reference along with the job."
    )


def test_every_needs_context_names_a_job_in_the_same_workflow():
    unknown = {}
    for path in workflows():
        text = read_uncommented(path)
        declared = jobs_in(text)
        missing = sorted({m.group("id") for m in _NEEDS_CONTEXT.finditer(text)} - declared)
        if missing:
            unknown[path.name] = missing

    assert not unknown, (
        f"an expression reads `needs.<job>` for a job that does not exist: {unknown}. An unknown "
        "context is not an error — it evaluates to null, the condition is false, and the job is "
        "SKIPPED. Branch protection accepts a skipped required check."
    )
