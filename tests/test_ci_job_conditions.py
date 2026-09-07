"""A job skipped by its own `if:` reports `skipped`, and branch protection accepts it.

That is the shape this file guards. A required check that is *skipped* is not a
red run and not a missing run — it is a green PR that ran less than it looks
like it ran, and nothing on the commit says so.

It shipped. The node steps — eslint and prettier — lived at the end of the
`lint` job, which is gated on `full_suite == 'true'`, and
`.github/scripts/docs-only.cjs` returns `fullSuite: false` for a **draft**
pull request carrying code, and for any change it classifies as not earning
the full suite. A
pull request touching nothing but TypeScript ran neither check — they ran on
the eventual push to the release branch, after review and after merge, where
the answer is too late to be a gate.

**This docstring no longer spells out which changes those are, and the
omission is the fix.** It has now been wrong twice in two releases, in opposite
directions, on the same clause:

- *a code change into a **non-release** base, which exists only where
  `--base-branch` and `--release-branch` differ* — over-qualified. True when
  written; false once the classifier became reachable in a one-branch tree.
- *a ready pull request carrying code, **in every tree**; which base it targets
  is not part of the rule* — under-qualified, and worse. The base is still
  load-bearing in every two-branch tree, so that sentence told a two-branch
  reader their **release-candidate** pull requests sit those jobs out, when
  that is the one case which runs everything. A reader deciding whether a job
  needs a `FULL-SUITE-BECAUSE:` marker reasoned from a false premise, in the
  direction that understates coverage.

**The fix for a wrong qualifier was to delete the qualifier**, and the true
statement was the middle one. What that says about the sentence is that it
should not be here at all: `docs-only.cjs` owns the classification, is rendered
with this tree's own branch names, and is the only copy that cannot be wrong
about them. **A value with an owner elsewhere should not be spelled in a file
at all — the spelling is the failure, not the staleness.** That rule is
sky.boss's, and it was quoted approvingly in the commit that broke this
sentence for the second time.

Three things about how it was caught, all worth more than the correction.

**The assertions never failed.** This file kept its prose through a change to
the classifier and stayed green, so the suite reported verified while the
reason was false — twice. A stale comment is inert; **a stale docstring on a
passing test certifies itself**, because the green and the prose have nothing
to do with each other and a reader cannot tell which one the run confirmed.

**Prose adjacent to a passing assertion inherits its credibility without
inheriting its coverage.** 175 tests, all green, in this file, in this
paragraph, about this predicate — and nothing in the tree executes the script
the paragraph describes. stash.flow's framing, and their remedy is what closed
it: `bin/skeletor-verify` runs `docs-only.cjs` over every event in both branch
shapes and asserts the `reason` as well as the two booleans, because a
fail-open returns exactly what a healthy release candidate returns and only
`reason` separates them.

**And the sentence that broke states its own rule.** *a code change into a
non-release base* was phrased to name the EVENT rather than a repository
property, and `non-release base` is a repository property smuggled back into
the sentence whose entire purpose was to stop doing that. node-zero, who
supplied the original phrasing, found it in their own words.

**Steps inherit their job's condition and never restate it**, so the defect was
invisible at the site: four correct-looking steps, and the thing that decided
they would not run was forty lines above them under a different heading.

## The rule, and why it is a marker rather than a list

Every job gated on `full_suite` must say why at its own site, with a
`FULL-SUITE-BECAUSE:` line. Narrower than `docs_only` means *this job may sit
out an ordinary code change*, which is a real decision some jobs have earned
and no job should make by accident.

Both directions, because a stale exemption is the failure this repository names
everywhere else: a marker in a job that is not gated on `full_suite` has
outlived its reason, and a `full_suite` job with no marker is a decision nobody
recorded. Neither is allowed to sit.
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
from scripts.paths import GITHUB_DIR  # noqa: E402

CI = GITHUB_DIR / "workflows" / "ci.yml"

_JOB = re.compile(r"^  (?P<id>[A-Za-z0-9_-]+):$")
_FULL_SUITE = re.compile(r"^\s+if:.*full_suite", re.MULTILINE)
_MARKER = re.compile(r"FULL-SUITE-BECAUSE:\s*(?P<reason>\S.*)")


def job_blocks() -> dict:
    """`{job id: its lines, the comment block directly above it included}`.

    The heading comment belongs to the job it introduces, because that is where
    a reader writes the reason and where the next reader looks for it. So the
    block starts at the first line of the run of `  #` and blank lines directly
    above `  <id>:` and ends where the next such run begins.

    The first draft did this with `rfind("\\n\\n", previous, start)` and
    attributed every heading comment to the job ABOVE it — `lint`'s reason
    landed in `gate`'s block, and both assertions failed naming the wrong jobs
    in opposite directions. Line-walking is the version that has no boundary to
    get backwards.
    """
    lines = CI.read_text(encoding="utf-8").splitlines()
    # `(line index, job id)`, matched once. Re-matching at the bottom of the
    # loop to read the id back would be an `Optional[Match]` pyright is right
    # to refuse — and the refusal is the useful kind, since a second match is a
    # second chance for the two to disagree.
    starts = [(index, match.group("id")) for index, line in enumerate(lines) if (match := _JOB.match(line))]

    def head_of(index: int) -> int:
        first = index
        while first > 0 and (lines[first - 1].startswith("  #") or not lines[first - 1].strip()):
            first -= 1
        return first

    heads = [head_of(index) for index, _ in starts]
    blocks = {}
    for position, (_, job) in enumerate(starts):
        end = heads[position + 1] if position + 1 < len(starts) else len(lines)
        blocks[job] = "\n".join(lines[heads[position] : end])
    return blocks


def test_the_scan_finds_the_jobs():
    """`least=4`: this scan feeds a filter, and a filter over one job selects nothing."""
    scanned(job_blocks(), f"jobs in {CI.name}", least=4)


def test_every_full_suite_job_says_why():
    """A job that may sit out an ordinary code change has to have decided to."""
    unexplained = [job for job, body in job_blocks().items() if _FULL_SUITE.search(body) and not _MARKER.search(body)]
    assert not unexplained, (
        f"these jobs are gated on `full_suite` and give no reason: {unexplained}. "
        "`full_suite` is false for a DRAFT pull request carrying code, and for whatever "
        "`.github/scripts/docs-only.cjs` classifies as not earning the full suite — read the "
        "decision order there rather than a copy of it here, since it is rendered with THIS "
        "tree's branch names. Such a job does not run on those and reports `skipped`, which "
        "branch protection accepts. "
        "Add a `FULL-SUITE-BECAUSE:` line at the job, or gate it on `docs_only != 'true'` like the "
        "jobs that run this repository's own code."
    )


def test_no_reason_outlives_its_job():
    """The other direction: an exemption is checked against the thing it exempts."""
    stale = [job for job, body in job_blocks().items() if _MARKER.search(body) and not _FULL_SUITE.search(body)]
    assert not stale, (
        f"these jobs carry a `FULL-SUITE-BECAUSE:` line and are not gated on `full_suite`: {stale}. "
        "Delete the line rather than re-justifying it — a reason nothing depends on is one the next "
        "reader has to disprove before touching the job."
    )
