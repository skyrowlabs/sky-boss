"""A test that needs full history must run in a job that fetches it.

`tests/test_docs_name_live_code.py` asks git whether a name was ever defined
here. `git log --all` answers "no" for everything in a shallow clone, so the
check would pass by *seeing* nothing rather than by *finding* nothing — and it
refuses instead, asserting the clone is not shallow. `ci.yml` sets
`fetch-depth: 0` on the job that runs it, which is what makes that assertion
pass honestly.

**Those two facts live in different files and nothing connected them.** sky.boss
hand-merged `ci.yml` at v0.16.0, kept every job and every `needs:` edge, and
dropped `fetch-depth: 0` from their test job — the file's own comment named a
different job as the one that needs history, so the omission read as
deliberate. Their CI went red on both matrix legs two hours later.

Their statement of the class, and it is why this file is not about
`fetch-depth`:

> The thing lost in a hand-merge was not a `needs:` edge but a **job-scoped
> setting a test in a different file depends on** — and it failed loudly only
> because that test refuses instead of passing vacuously. Yours does; the next
> one might not.

So the coupling is asserted here, statically, where a resolver meets it before
the push rather than after. `tests/test_workflow_job_graph.py` does this for
the `needs:` graph and `tests/test_ci_ratchet_inputs.py` for an artifact a
ratchet reads; this is the third edge of the same shape.

## Two routes, because the first version only had one

A suite is *history-dependent* if any test file in it checks for
`.git/shallow`; its marker comes from that file's `pytestmark`; the jobs come
from the workflows by which marker they select with `-m`.

**That reaches nothing that is not a pytest test**, and sky.boss found the
counterexample in the tree that produced the rule: `scripts/docs/`'s release
window shells out to `rev-list`, runs in `docs-validation.yml`, and is not a
test at all. Against a shallow clone it returns a **well-formed window
describing nothing** — no tags, no parentless commit, a range opening at the
graft boundary, valid JSON, no warning. Measured on a real repository: 63
commits from a full clone, 0 from a `--depth 1` clone.

So the second route reads **scripts**: a script under `scripts/` that shells
out to `git log` or `rev-list` is history-dependent, and every job invoking it
by path must fetch history. Same shape, one instrument wider.

Every workflow is scanned, not just `ci.yml`, because that is where the second
route was hiding.

## Discovered, never listed

A list of job names here would be a second home for a fact the workflows
already state, and it would be wrong in the first tree that renamed a job —
which is most of them, since these are the files adopters hand-merge. sky.boss
verified this file's derivation against a tree whose job names share nothing
with the template's.

## What it still cannot see

A history reader invoked some way other than by its path — through a shell
helper, a `make` target, a wrapper. sky.boss's own scoping is the honest one:
the general discriminator is *does this job run anything that shells out to
git history*, and that has no clean structural handle. Neither of us has a
better proposal than the two routes below and the counterexample that produced
the second.
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
from scripts.paths import GITHUB_DIR, TESTS_DIR  # noqa: E402
from scripts.yaml_text import read_uncommented  # noqa: E402

CI = GITHUB_DIR / "workflows" / "ci.yml"
WORKFLOWS = GITHUB_DIR / "workflows"
SCRIPTS_ROOT = TESTS_DIR.parent / "scripts"

#: The tell that a test refuses to run against a shallow clone: it *tests for*
#: the path git writes, on one line. Matched on the path rather than on a helper
#: name, because the path is the fact and a helper is a spelling — and on the
#: `.exists()` beside it, because the bare literal is not enough.
#:
#: sky.boss asked whether the null was readable rather than accepting it
#: recorded, and it was not. Probed with three planted files: a docstring merely
#: naming `"shallow"`, a module assigning the path without testing it, and a
#: real refusal. The first version enrolled **all three**. The false positives
#: were conservative — an over-enrolled marker demands more history, never
#: less — which is exactly why nothing would have surfaced them.
#:
#: What survives: a file that both names the path and calls `.exists()` on the
#: same line, without asserting, still enrols. Narrower than "mentions it
#: anywhere" and not the structural answer, which would be an `ast` walk for an
#: `.exists()` call under an `assert`. Recorded rather than claimed closed.
_NEEDS_HISTORY = re.compile(r"""["']shallow["'][^\n]*\.exists\(""")

#: A script that reads git history. `--all` is on the `log` form because a
#: plain `git log` of HEAD is answerable in a shallow clone and only the
#: whole-history question is not.
_READS_HISTORY = re.compile(r"""["']rev-list["']|log["'],\s*["']--all|log\s+--all""")

_JOB = re.compile(r"^  (?P<id>[A-Za-z0-9_-]+):$", re.MULTILINE)
_MARKER_IN_FILE = re.compile(r"pytestmark\s*=\s*\[?pytest\.mark\.(?P<name>\w+)")
_DASH_M = re.compile(r"-m\s+(?P<marker>\w+)")
_FETCH_DEPTH_ZERO = re.compile(r"fetch-depth:\s*0")


def history_dependent_markers() -> set:
    """Markers of every suite holding a test that refuses a shallow clone."""
    markers = set()
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if _NEEDS_HISTORY.search(text) and ".git" in text:
            markers.update(_MARKER_IN_FILE.findall(text))
    return markers


def history_dependent_scripts() -> set:
    """Every script under `scripts/` that shells out to whole-history git."""
    return {
        path.relative_to(SCRIPTS_ROOT.parent).as_posix()
        for path in sorted(SCRIPTS_ROOT.rglob("*.py"))
        if "__pycache__" not in path.parts and _READS_HISTORY.search(path.read_text(encoding="utf-8"))
    }


def jobs_needing_history(markers: set, scripts: set) -> dict:
    """`{"<workflow>:<job>": its body}` for every job reaching either route."""
    needing = {}
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        text = read_uncommented(workflow)
        bounds = [(m.group("id"), m.start()) for m in _JOB.finditer(text)]
        for index, (job, start) in enumerate(bounds):
            end = bounds[index + 1][1] if index + 1 < len(bounds) else len(text)
            body = text[start:end]
            if markers & set(_DASH_M.findall(body)) or any(script in body for script in scripts):
                needing[f"{workflow.name}:{job}"] = body
    return needing


def test_the_scan_finds_every_side():
    """Any side coming back empty would make the assertion below vacuous."""
    markers = scanned(sorted(history_dependent_markers()), "suites that refuse a shallow clone")
    scripts = scanned(sorted(history_dependent_scripts()), "scripts that read whole git history")
    scanned(jobs_needing_history(set(markers), set(scripts)), "jobs running either")


def test_every_job_that_reads_history_fetches_it():
    markers, scripts = history_dependent_markers(), history_dependent_scripts()
    shallow = sorted(
        job for job, body in jobs_needing_history(markers, scripts).items() if not _FETCH_DEPTH_ZERO.search(body)
    )
    assert not shallow, (
        f"these jobs read whole git history and check out shallow: {shallow}. Add `fetch-depth: 0` "
        f"to their `actions/checkout` step. The suites are {sorted(markers)} and the scripts are "
        f"{sorted(scripts)}. `git log --all` and `rev-list` answer for a graft boundary in a shallow "
        "clone rather than failing — a name that was always here reads as never defined, and a "
        "release window comes back well-formed and describing nothing. Both refuse rather than "
        "answering wrongly, so without the depth those jobs go red; this test is what turns that "
        "into a red `check pre-push` instead."
    )
