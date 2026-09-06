"""A ratchet step must come after the step that writes what it reads.

stash.flow found the shape, and it is the worst arrangement a check can be in:
`ci.yml` ran `scripts/check_skip_budget.py` in a job that never produced
`tmp/junit.xml`, so the ratchet printed *"no junit report"* and exited **0** on
every push, in every scaffold, since the tree was first generated. The check
that exists to catch a suite quietly stopping testing was itself quietly not
testing — a graceful degradation that degrades into a pass.

The first fix is in the checker: a missing report is a failure now, because
*"I could not measure"* and *"the budget is respected"* are not the same answer.
That turns the silence into a red CI run. This file turns it into a red **unit
test**, which is one whole CI cycle earlier and, in the generator that ships
these workflows, is the difference between the template finding it and every
repository generated from the template finding it.

## Enrolment is by pattern at both ends

A ratchet is any `scripts/check_*.py` naming a file under `tmp/` — today that
finds the skip and coverage budgets, and it will find the next one without
anybody adding a row here. What it requires is that the artifact's filename
appears **earlier in the same job**, which is the only place it could have been
written: a later job is a different runner with a different filesystem.

Earlier *in the job's text* is the same thing as an earlier step, so this reads
offsets rather than parsing steps. What it cannot see is a report that arrives
by `download-artifact` under a name that is not the filename; the remedy there
is to name the file, which is worth doing anyway.

A ratchet may be pointed at a report other than its default — the nightly runs
`check_skip_budget.py` twice, once per marker, because a skip count belongs to
the run that produced it. So the artifact required is the one named **on the
invocation** when there is one, and the script's own default otherwise. Reading
only the default would have made the correct workflow the red one.

## Why the workflows are read with comments blanked

Because this hunts for a *requirement*, and the string most likely to appear in
a job that has not done the thing is a comment saying it should.
`# TODO: add --junitxml here` satisfies a substring check perfectly, so the
false pass would be exactly correlated with the defect. `scripts/yaml_text.py`
owns the masking and carries the two gates that learned it the expensive way.
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
from scripts.paths import GITHUB_DIR, SCRIPTS_DIR  # noqa: E402
from scripts.yaml_text import read_uncommented  # noqa: E402

WORKFLOWS = GITHUB_DIR / "workflows"

#: `TMP_DIR / "junit.xml"` — the artifact a ratchet reads *by default*, declared
#: where it is used rather than listed here. Read from the source and not
#: imported: a checker that cannot be imported on this host would otherwise drop
#: out of the scan silently, which is the exemption problem this suite refuses.
_ARTIFACT = re.compile(r"""TMP_DIR\s*/\s*["'](?P<artifact>[^"'/]+)["']""")

#: An explicit report on the invocation — `--junit tmp/junit-unit.xml`. Matched
#: by shape rather than by flag name, because the flag differs per ratchet and a
#: second list of them would be the thing Rule 2 forbids.
_OVERRIDE = re.compile(r"tmp/(?P<artifact>[\w.\-]+)")

#: A job header: two spaces, an identifier, a colon, nothing else on the line.
_JOB = re.compile(r"^  (?P<id>[A-Za-z_][A-Za-z0-9_-]*):\s*$", re.MULTILINE)


def ratchets() -> dict:
    """`{script filename: artifact filename}` for every ratchet that reads one."""
    found = {}
    for script in sorted(SCRIPTS_DIR.glob("check_*.py")):
        match = _ARTIFACT.search(script.read_text(encoding="utf-8"))
        if match:
            found[script.name] = match.group("artifact")
    return found


def jobs(path: Path) -> dict:
    """`{job id: the job's text}`, split on the job headers, comments blanked."""
    text = read_uncommented(path)
    starts = [(m.group("id"), m.start()) for m in _JOB.finditer(text)]
    bounds = [
        (name, start, starts[i + 1][1] if i + 1 < len(starts) else len(text)) for i, (name, start) in enumerate(starts)
    ]
    return {name: text[start:end] for name, start, end in bounds}


def invocations() -> list:
    """Every (workflow, job, script, artifact, offset) where a ratchet is run.

    Per line, not per job: the nightly runs one ratchet twice with a different
    report each time, and a job-level search would see the first and call it the
    only one.
    """
    known = ratchets()
    found = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for job, body in jobs(path).items():
            offset = 0
            for line in body.splitlines(keepends=True):
                for script, default in known.items():
                    if script in line:
                        override = _OVERRIDE.search(line)
                        artifact = override.group("artifact") if override else default
                        found.append((path.name, job, script, artifact, offset + line.index(script)))
                offset += len(line)
    return found


def test_the_scan_finds_ratchets_and_the_jobs_that_run_them():
    """Both ends, because either one going empty passes the assertion below.

    `least=2` on the ratchets is the fixture rule: with one, "every ratchet"
    and "this ratchet" are the same set, and a filter that selects nothing
    cannot be told from one that selects everything.
    """
    scanned(ratchets(), "scripts/check_*.py reading a tmp/ artifact", least=2)
    scanned(invocations(), "workflow steps running a ratchet")


def test_a_ratchet_reads_a_report_its_own_job_produced():
    """The artifact is named earlier in the job, or the ratchet reads nothing."""
    for workflow, job, script, artifact, consumer in invocations():
        body = jobs(WORKFLOWS / workflow)[job]
        producer = body.find(artifact)
        assert 0 <= producer < consumer, (
            f"{workflow}: job '{job}' runs {script}, which reads tmp/{artifact}, but no earlier "
            f"step in that job writes {artifact}. The ratchet will report that it found no "
            "report — a check with nothing to read has not passed, it has not run."
        )
