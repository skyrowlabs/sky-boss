"""`.github/pyright-deps.txt` has a caller, and it declares the whole environment.

Two files now describe the same environment — the `test` job's install steps and
`.github/pyright-deps.txt` — so Rule 11 in `AGENTS.md` says a drift check owns
the pair. This is that check.

## The two halves, and they fail in opposite directions

**Live.** A dependency set nothing installs from is configuration justified by a
comment rather than by a caller, which is the state this file exists to end: the
declaration sat here for six releases with no consumer at all, its header
describing a workflow job this tree does not have. Nobody had asked the question,
because nothing asks it — a file with no reader never goes red.

**Complete.** `reportMissingImports` is `none`, so a package pyright cannot
import does not fail the check; it becomes `Unknown`, stops constraining
anything, and the fallout surfaces as errors in files the commit never touched.
So a dependency set that is *smaller* than what the job installs is not a
stricter check, it is a differently-wrong one — and this file would be the thing
telling the lie, because its header claims to be a superset. That claim is only
worth having if something recomputes it.

## Why the template's own gate is not what runs here

`tests/test_pyright_deps.py` ships with skeletor and is declined in this tree:
its scan wants at least two workflow jobs running pyright, and this tree has one
pytest job — a python matrix rather than several marker jobs, which is round 7's
*steps rather than jobs* showing up in somebody else's scan. Round 22 tried
restoring it and got two independent failures, neither of them the assertion it
was interested in.

The name is deliberately not the template's. `tests/test_pyright_scope.py`
records what happens when a gate written locally and a gate shipped upstream
occupy the same path: the manifest classifies by hash, so a file that is new
there and old here arrives as a clean addition backed by nothing, and no diff of
bytes can see that the two have the same *purpose*. Under a different name the
template's gate lands visibly, as an addition, and somebody gets to choose. **Keep
one of the two.** Running both under two names is the drift this whole file is
about, one level up.

## Scope, stated because it is narrower than it looks

This asks whether the *declaration* covers what the *job* installs. It does not
ask whether either is the right set — that is `pyrightconfig.json`'s question and
`tests/test_pyright_scope.py` owns it — and it cannot ask whether the packages
resolve on a runner, which is a fact about a machine no unit test is standing on.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanning import scanned  # noqa: E402
from scripts.paths import GITHUB_DIR, PROJECT_ROOT  # noqa: E402
from scripts.yaml_text import read_uncommented  # noqa: E402

DEPS = GITHUB_DIR / "pyright-deps.txt"
WORKFLOWS = GITHUB_DIR / "workflows"

#: A job header at the workflow's job indent. Same shape as
#: `test_pre_push_covers_ci.py`'s, and for the same reason: the question is
#: per-job, and a whole-file scan would pair a `pip install` in one job with a
#: pyright call in another.
_JOB = re.compile(r"^  (?P<id>[A-Za-z_][A-Za-z0-9_-]*):\s*$", re.MULTILINE)

#: A `pip install` and its arguments, stopping at a newline or a shell separator
#: so one install cannot swallow the next one's flags.
_PIP_INSTALL = re.compile(r"pip install\b(?P<args>[^\n;&|]*)")

#: **Every** `-r` in those arguments, not the first. `pip install -r a -r b`
#: measured as `['a']` under the obvious regex, and the failure is silent in
#: exactly the direction that matters here: an under-collected job install set
#: makes this gate green over the file it was supposed to catch.
_DASH_R = re.compile(r"-r\s+(?P<target>[\w./-]+)")


def _requirements_in(text: str, relative_to: Path) -> set:
    """Every requirements file `text` installs from, as repo-relative posix paths.

    Normalised through `resolve()` because the two sides spell the same file
    differently and must still compare equal: `ci.yml` installs
    `scripts/requirements.txt` from the checkout root, and `pyright-deps.txt`
    reaches it as `../scripts/requirements.txt` from `.github/`. Comparing raw
    strings would report every file as missing while every file was present.
    """
    found = set()
    for install in _PIP_INSTALL.finditer(text):
        for match in _DASH_R.finditer(install.group("args")):
            target = (relative_to / match.group("target")).resolve()
            found.add(target.relative_to(PROJECT_ROOT).as_posix())
    return found


def _declared() -> set:
    """The `-r` closure of `pyright-deps.txt`, including the file itself.

    Followed rather than read flat: this file is includes rather than a package
    list, so a one-level read would report it as declaring nothing at all.
    Cycles terminate on `seen`.
    """
    reached, queue, seen = set(), [DEPS], set()
    while queue:
        path = queue.pop()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        reached.add(path.resolve().relative_to(PROJECT_ROOT).as_posix())
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#")[0].strip()
            if line.startswith("-r"):
                queue.append((path.parent / line[2:].strip()).resolve())
    return reached


def _jobs_running_pyright() -> dict:
    """`{job id: everything that job installs}`, for jobs that type-check.

    Enrolment is `pyright` plus `--project` in the job body, which is what
    separates a call from a mention of `pyrightconfig.json`. Comments are masked
    first — `scripts/yaml_text.py` owns that, and it is load-bearing in the
    direction that hurts: a commented-out call would enrol a job that runs
    nothing, and this gate would then hold a real file against an imaginary one.
    """
    found = {}
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        text = read_uncommented(workflow)
        bounds = [(m.group("id"), m.end()) for m in _JOB.finditer(text)]
        for index, (job, start) in enumerate(bounds):
            end = bounds[index + 1][1] if index + 1 < len(bounds) else len(text)
            body = text[start:end]
            if "pyright" in body and "--project" in body:
                found[f"{workflow.name}:{job}"] = _requirements_in(body, PROJECT_ROOT)
    return found


def test_the_scan_finds_a_job_that_type_checks():
    """The positive control, and the assertion this tree spent six releases failing.

    `least=1` rather than the template's 2, which is the whole reason that gate
    could not run here: this tree type-checks in a STEP inside its one pytest
    job, so there is exactly one job to find and there always will be until the
    matrix becomes several marker jobs. A floor of two is unsatisfiable by a
    correct configuration, and a gate that a correct tree cannot pass is one an
    adopter deletes.
    """
    scanned(_jobs_running_pyright(), "workflow jobs running pyright", least=1)


def test_the_declaration_has_a_caller():
    """A dependency set nothing installs is a comment wearing a file's clothes."""
    jobs = _jobs_running_pyright()
    deps = DEPS.relative_to(PROJECT_ROOT).as_posix()
    orphaned = sorted(job for job, installs in jobs.items() if deps not in installs)
    assert not orphaned, (
        f"these jobs run pyright without installing `{deps}`: {orphaned}\n"
        f"Either install it there, or delete the file — it declares an environment nothing "
        "provisions, which is configuration justified by a comment rather than by a caller."
    )


def test_the_declaration_reaches_every_requirements_file_the_job_installs():
    """A leaner declared set is not a stricter check, just a differently-wrong one.

    The direction is the point. Extra packages in `pyright-deps.txt` are fine —
    pyright seeing more than the tests do costs nothing. Packages the job
    installs and this file does not reach are the failure, because the header
    promises a superset and `reportMissingImports: none` means pyright will not
    mention the shortfall; it reports the consequences instead, in files nobody
    touched.
    """
    declared = _declared()
    for job, installs in sorted(_jobs_running_pyright().items()):
        missing = sorted(installs - declared - {DEPS.relative_to(PROJECT_ROOT).as_posix()})
        assert not missing, (
            f"{job} installs these, and `{DEPS.relative_to(PROJECT_ROOT).as_posix()}` does not reach them:\n  "
            + "\n  ".join(missing)
            + f"\nAdd an `-r` for each. pyright resolves its interpreter from that job's venv, so a "
            "package the tests get and the type check does not becomes `Unknown` — it stops "
            "constraining anything and the fallout lands in files the commit never touched."
        )


def test_the_closure_follows_more_than_one_hop():
    """`_declared` is a graph walk, and a walk tested on a flat file proves nothing.

    `pyright-deps.txt` is *only* includes, so if the walk silently stopped at
    depth one it would return the file itself and nothing else — and the
    assertion above would then report every requirements file as missing, which
    is loud. The reverse mistake is the quiet one: a walk that returned
    everything under the root would make that assertion unfailable. So the floor
    is checked here rather than inferred from a green run elsewhere.
    """
    declared = scanned(_declared(), "files reachable from pyright-deps.txt", least=2)
    assert DEPS.relative_to(PROJECT_ROOT).as_posix() in declared, "the walk lost its own starting point"
