"""The CI table in `docs/DEVELOPMENT.md` is a copy of facts that live in CI.

Every cell in it is derived. The branches come from `ci.yml`'s `push:` trigger,
the Release Please claim from that job's `if:`, the job labels from each job's
`name:`, and the event-to-verdict mapping from `.github/scripts/docs-only.cjs`.
A table is the readable form of all that and **not a second opinion about it**.

## Why this exists, which is three defects in one table

`docs-only.cjs` fixed a sentence about draft pull requests three releases
running. The copy of that sentence in `DEVELOPMENT.md` was never fixed, and
nothing could see the disagreement:

* **`Draft PR | CI Gate alone`.** A draft carrying code returns
  `docsOnly: false`, and `node` and `unit-tests` are gated on
  `docs_only != 'true'`, so both run. The table understated a draft by two
  jobs — on the one transition GitHub's model has for escalating.
* **`Push to <release branch>`.** The classifier's push rule is `if (!pr)`,
  which is *any non-PR event*, and the trigger fires on every long-lived
  branch. In a two-branch tree the table named the branch that receives the
  fewest pushes and omitted the one that receives the most, so a reader
  believed their `develop` push had tested nothing.
* **Two missing rows.** A pull request into the release branch classifies
  differently from one into the base branch, and neither row was here.

Found by dream.doll reading the table against the code, in a rendered tree.
Here the table is placeholders and the workflow is placeholders, and the two
agree by looking similar.

## What this gate does NOT check, stated because a green row is read as cover

It does not verify **which jobs run for which event**. That mapping is the
classifier's, it is decided at run time from a payload, and no static reading
of this tree establishes it. `bin/skeletor-verify` executes `docs-only.cjs`
over every event in both branch shapes and asserts the `reason` as well as the
booleans — that is where the mapping is proven, and it is the generator's
question because it needs node and a payload rather than a repository.

So what is asserted here is everything about the table that **is** a static
fact about this tree: the branch sets, the Release Please attribution, and
that every job named exists. A row can still claim the wrong jobs for the
right event and pass.

## Sets, not sequences

The branch comparison is a set comparison. `long_lived_branches()` yields the
base branch first, so a rendered trigger reads `[develop, main]` — but a tree
that hand-maintains its workflow may order the pair the other way, and one
adopter does. Ordering is not the defect this is looking for, and firing on it
would be a red gate for a difference that costs nothing.
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
from scripts.paths import DOCS_DIR, GITHUB_DIR  # noqa: E402
from scripts.yaml_text import uncommented  # noqa: E402

CI = GITHUB_DIR / "workflows" / "ci.yml"
DEVELOPMENT = DOCS_DIR / "DEVELOPMENT.md"
RELEASE_CONFIG = GITHUB_DIR / "release-please-config.json"

#: A row of the pipeline table: `| Event | What runs | ~min |`. The heading and
#: the `---` separator match too and are dropped by the `Push`/`PR` predicates
#: that select rows, never by a count.
_ROW = re.compile(r"^\|(?P<event>[^|]*)\|(?P<runs>[^|]*)\|(?P<cost>[^|]*)\|\s*$", re.MULTILINE)
_BACKTICKED = re.compile(r"`([^`]+)`")
_JOB_NAME = re.compile(r"^\s+name:\s*(?P<name>\S.*?)\s*$", re.MULTILINE)


def ci_text() -> str:
    """`ci.yml` with its comments blanked — the comment under `push:` names branches."""
    return uncommented(CI.read_text(encoding="utf-8"))


def rows() -> list:
    """Every row of the pipeline table, as `(event, what runs)`."""
    text = DEVELOPMENT.read_text(encoding="utf-8")
    table = [(m.group("event").strip(), m.group("runs").strip()) for m in _ROW.finditer(text)]
    return [(event, runs) for event, runs in table if event and not set(event) <= set("- ")]


def push_rows() -> list:
    return [(event, runs) for event, runs in rows() if event.lower().startswith("push to")]


def trigger_branches() -> set:
    """The branches `ci.yml`'s `push:` trigger fires on."""
    block = re.search(r"^  push:\n(?:.*\n)*?^\s+branches:\s*\[(?P<list>[^\]]*)\]", ci_text(), re.MULTILINE)
    assert block, f"no `push:` trigger with an inline `branches:` list in {CI.name}"
    return {name.strip().strip("'\"") for name in block.group("list").split(",") if name.strip()}


def release_branch():
    """The branch the Release Please job gates itself on, or `None` if no job does.

    **Optional because the job is a supported deletion and the config is not the
    predicate.** This asserted, and the assertion was red in the one tree that
    had dropped the release job from its graph — a tree with no Release Please
    row anywhere in the table, failing a test about job *labels*.

    Gating on the release config's presence is the fix that suggests itself and
    it is wrong. Measured across four `--versioning tag` trees: all four lack the
    config and three still render the job, deliberately — `ci.yml` says why, a
    required status context that never reports blocks a pull request forever. So
    the config is absent in trees that have the job, and what this function reads
    is the job. Return `None` and let each caller say what that means for it.
    """
    ref = re.search(r"github\.ref\s*==\s*'refs/heads/(?P<branch>[^']+)'", ci_text())
    return ref.group("branch") if ref else None


def job_names() -> set:
    """Every `name:` in `ci.yml` — the labels the table is allowed to use."""
    return {m.group("name") for m in _JOB_NAME.finditer(ci_text())}


def test_the_scan_finds_the_table():
    """`least=5`: this scan feeds two filters, and a table of one row selects nothing."""
    scanned(rows(), f"pipeline table rows in {DEVELOPMENT.name}", least=5)
    scanned(push_rows(), f"push rows in {DEVELOPMENT.name}")
    scanned(job_names(), f"job names in {CI.name}", least=4)


def test_the_push_rows_name_every_branch_that_triggers_ci():
    """`docs-only.cjs` gives the full suite to any non-PR event; the trigger decides which.

    A branch in the trigger and absent here is the expensive direction: the
    reader concludes a push to it ran nothing.
    """
    documented = {branch for event, _ in push_rows() for branch in _BACKTICKED.findall(event)}
    assert documented == trigger_branches(), (
        f"the table documents pushes to {sorted(documented)} and `{CI.name}` triggers on "
        f"{sorted(trigger_branches())}. Every branch in the trigger earns the full suite — the "
        f"classifier's push rule is `if (!pr)`, which is any non-PR event, not the release branch. "
        f"Use `{{`develop` or `main`}}` rather than naming a branch, so a one-branch tree "
        f"renders one name instead of the same name twice."
    )


def test_release_please_is_claimed_for_one_branch_and_only_when_configured():
    """Two predicates, and the row welds them with a conjunction.

    The full suite runs on every long-lived branch; Release Please runs on the
    release branch alone. Widening the branch name without splitting the claim
    trades an understatement for an overstatement.
    """
    claims = [(event, runs) for event, runs in push_rows() if "Release Please" in runs]
    if not RELEASE_CONFIG.exists():
        assert not claims, (
            f"this tree has no `{RELEASE_CONFIG.name}` — it is `--versioning tag`, the release is an "
            f"annotated git tag, and no push runs Release Please. Drop the claim or put it behind a "
            f"`SCAFFOLD-IF {RELEASE_CONFIG.name}` block."
        )
        return
    assert claims, (
        f"this tree has `{RELEASE_CONFIG.name}` and no push row mentions Release Please, so the table "
        f"omits the job that makes the release."
    )
    released = release_branch()
    assert released, (
        f"this tree has `{RELEASE_CONFIG.name}` and the table claims Release Please, but no job in "
        f"`{CI.name}` gates itself on a `refs/heads/<branch>` ref — so nothing decides which branch "
        f"releases. Either the job was removed and the config should go with it, or its `if:` was."
    )
    for event, runs in claims:
        pushed = set(_BACKTICKED.findall(event))
        if pushed == {released}:
            # One long-lived branch, so the two predicates coincide and the row
            # cannot attribute the job to the wrong one. Nothing to separate.
            continue
        assert released in set(_BACKTICKED.findall(runs)), (
            f"this row documents pushes to {sorted(pushed)} and claims Release Please for all of them: "
            f"{'|' + event + '|' + runs + '|'!r}. The job is gated on "
            f"`github.ref == 'refs/heads/{released}'`, so it runs on that branch alone. Naming "
            f"`{released}` in the branch list is not enough — the branch list is the *push* "
            f"predicate, which is broader. Say which branch releases, in the cell that makes the claim."
        )


def test_every_job_the_table_names_exists():
    """A renamed job leaves the table naming something no run will ever report.

    **Branch names are excluded, and the set comes from `ci.yml`.** The runs
    column legitimately holds one — Release Please is attributed to a branch
    there, because the row's two predicates differ and the narrower one has to
    say which branch it means. Backticks cannot distinguish a job label from a
    branch, and the tree already knows which strings are branches, so the
    exclusion is derived rather than written down. A job named exactly after a
    branch would be skipped here; nothing prevents that and a list would not
    help, since a list is the thing that goes stale when the job is renamed.

    A tree shipping no Release Please job contributes nothing to the exclusion,
    and that is not a failure of this test — see `release_branch`.
    """
    branches = trigger_branches() | {branch for branch in [release_branch()] if branch}
    labels = {label for _, runs in rows() for label in _BACKTICKED.findall(runs)} - branches
    unknown = sorted(label for label in labels if not any(name.startswith(label) for name in job_names()))
    assert not unknown, (
        f"the table names {unknown}, and no job in `{CI.name}` has a `name:` starting with any of them. "
        f"The names that exist are {sorted(job_names())} — a matrix job's label is a prefix of its "
        f"`name:`, since the matrix value is appended at run time."
    )
