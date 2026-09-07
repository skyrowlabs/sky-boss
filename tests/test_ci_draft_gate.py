"""The draft gate's load-bearing pieces cannot be removed silently.

Two of them look like boilerplate and are not:

* `ready_for_review` in ci.yml's trigger types. Remove it and the gated jobs
  never re-run when a PR flips out of draft — they stay `skipped`, branch
  protection ACCEPTS a skipped required context, and the PR merges having run
  only the gate job.

* The shared docs-only definition. Two copies of that rule drift, and the copy
  that is wrong is the one deciding whether tests run.

* `develop` in the `push` trigger. Take it out and every commit that
  lands on this branch without a pull request runs no CI whatsoever — and
  nothing anywhere says so, because "no workflow ran" and "the workflow passed"
  are the same absence of red.
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

from scripts.paths import GITHUB_DIR  # noqa: E402
from scripts.yaml_text import read_uncommented  # noqa: E402

CI = GITHUB_DIR / "workflows" / "ci.yml"
GATE_MODULE = GITHUB_DIR / "scripts" / "docs-only.cjs"


def ci_text() -> str:
    """ci.yml as code — comments blanked.

    Every assertion below is a substring or regex over this file, and a comment
    is a substring. Deleting the `ready_for_review` trigger and leaving
    `# note: ready_for_review used to be here` kept all of these green, which is
    the precise failure this file exists to prevent, wearing the file's own
    clothes. See `scripts/yaml_text.py`.
    """
    return read_uncommented(CI)


def test_ready_for_review_is_a_trigger():
    assert "ready_for_review" in ci_text(), (
        "ci.yml no longer triggers on `ready_for_review`. Gated jobs will never re-run when a PR "
        "leaves draft — they stay `skipped`, which branch protection accepts, and the PR merges "
        "having proven nothing."
    )


def test_gate_definition_is_shared_not_inlined():
    text = ci_text()
    assert GATE_MODULE.exists(), "the shared docs-only definition is missing"
    assert "docs-only.cjs" in text, "ci.yml must require the shared definition, never re-inline the pattern"


def test_expensive_jobs_are_gated_on_the_gate_output():
    text = ci_text()
    assert "needs.gate.outputs.full_suite" in text, "no job is gated on the gate's verdict — the gate buys nothing"


def test_skipping_is_at_job_level_not_paths_ignore():
    """A required context that never REPORTS blocks a PR forever; one that
    reports `skipped` satisfies branch protection. So gating must be `if:` on
    the job, never `paths-ignore` on the trigger."""
    # The KEY, not the word: this file's own comments explain why paths-ignore
    # is wrong, and a substring check would fail on the explanation.
    text = ci_text()
    assert not re.search(r"^\s+paths-ignore:", text, re.MULTILINE), (
        "ci.yml uses `paths-ignore`. A required check skipped by a trigger filter never reports at "
        "all, and a never-reported required context blocks the PR forever. Gate at the job level."
    )


def test_push_gates_the_branch_work_lands_on():
    """`push` must cover `develop`, the branch work lands on.

    In a two-branch tree that is the point of contrast — `develop` and
    not only `main`. **This tree was scaffolded with both set, and
    if they read the same there is no contrast to draw**: one branch, and the
    requirement is that the trigger covers it. The sentence used to be phrased
    as the contrast, which in a one-branch tree interpolates to a word set
    against itself. Found by mind.head, in a rendered tree, which is the only
    place it is visible.

    A PR flow is gated by the `pull_request` trigger, so this looks redundant
    right up until somebody commits straight to `develop` — which every
    project does while it is one person, and which is exactly when nobody is
    reviewing either. The scaffold this tree came from shipped without it and a
    consumer landed three ungated commits before noticing.

    Costed rather than assumed: on a PR flow this re-runs the suite once per
    merge, which is not pure duplication either, since a squash merge is a
    commit no PR run ever saw.
    """
    text = ci_text()
    triggers = re.search(r"^on:\n(.*?)^\w", text, re.MULTILINE | re.DOTALL)
    assert triggers, "ci.yml has no `on:` block"
    push = re.search(r"^  push:\n(?:\s*#.*\n)*\s*branches:\s*\[(.*?)\]", triggers.group(1), re.MULTILINE)
    assert push, "ci.yml has no `push:` trigger with a branch list"
    branches = [b.strip() for b in push.group(1).split(",")]
    assert "develop" in branches, (
        "ci.yml's `push` trigger does not cover develop, so a commit landing there "
        f"outside a pull request runs nothing at all. Found: {branches}"
    )
