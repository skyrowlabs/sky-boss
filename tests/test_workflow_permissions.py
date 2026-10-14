"""A job that checks the repository out can read it.

**An explicit `permissions:` block sets every scope it does not name to
`none`.** That is GitHub's documented rule, and it turns a block written to
*grant* something into one that also *revokes* everything else. A block naming
only `pull-requests: write` leaves the token with no `contents` scope at all.

The failure that produces is decided by a fact no file states: whether the
repository is public. A public repository's contents can be fetched without the
scope, so `actions/checkout` succeeds and the omission is invisible. A private
one answers `Repository not found`. `pr-draft-discipline.yml` shipped exactly
that block and was green in sky.boss, the one public adopter, and red on every
pull request in four private ones — found on the first `develop`→`main` pull
requests, which is the first time most of those trees had opened one.

`actionlint` does not model it, and could not settle it here anyway: what makes
it fail is the account's visibility setting, and skeletor's own verifier only
ever sees the template. So the rule is held in the tree, over every job in every
workflow, where an adopter who edits a permissions block meets it.

The predicate is narrow on purpose. No `permissions:` anywhere is the default
token and is not checked; `read-all` and `write-all` include contents; a mapping
must name `contents`. A job-level block replaces the workflow's, as GitHub
applies it, rather than merging with it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional, Union

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import GITHUB_DIR  # noqa: E402
from scripts.yaml_text import uncommented  # noqa: E402

WORKFLOWS = GITHUB_DIR / "workflows"

#: A job header: two spaces, an identifier, a colon, nothing else on the line.
_JOB = re.compile(r"^  (?P<id>[A-Za-z_][A-Za-z0-9_-]*):\s*$", re.MULTILINE)

Permissions = Union[None, str, dict]


def permissions_at(text: str, indent: int) -> Permissions:
    """The `permissions:` declared at exactly `indent` spaces in `text`.

    `None` when there is no such key; the inline value (`read-all`, `{}`) as a
    string; otherwise `{scope: level}` from the lines nested under it.
    """
    pad = " " * indent
    match = re.search(rf"^{pad}permissions:[ \t]*(?P<inline>\S.*)?$", text, re.MULTILINE)
    if not match:
        return None
    if match.group("inline"):
        return match.group("inline").strip()
    scopes = {}
    for line in text[match.end() :].splitlines()[1:]:
        if not line.strip():
            continue
        nested = re.match(rf"^{pad}  (?P<scope>[\w-]+):\s*(?P<level>\w+)\s*$", line)
        if not nested:
            break
        scopes[nested.group("scope")] = nested.group("level")
    return scopes


def reads_contents(permissions: Permissions) -> bool:
    if permissions is None:
        return True  # the default token, which this rule does not police
    if isinstance(permissions, str):
        return permissions in ("read-all", "write-all")
    return permissions.get("contents") in ("read", "write")


def job_headers(text: str) -> list:
    """`[(job id, offset)]` for the headers under `jobs:`, and nothing else.

    Matched over the whole file, `on:`'s keys read as jobs too — stash.flow
    measured `['pull_request', 'push', 'workflow_dispatch', 'gate', ...]` — and
    the last trigger's slice ran up to the first real job. That was harmless
    for `unreadable_checkouts`, since no trigger holds a checkout, which is
    exactly why its rows could not catch a revert (mind.head): both matchers
    agree on every valid workflow. So the ids are asserted here, directly.
    """
    section = re.search(r"^jobs:\s*$", text, re.MULTILINE)
    offset = section.end() if section else len(text)
    return [(m.group("id"), m.start()) for m in _JOB.finditer(text, offset)]


def unreadable_checkouts(workflow: str) -> list:
    """Job ids in `workflow` that run `actions/checkout` with no `contents` scope."""
    text = uncommented(workflow)
    top = permissions_at(text, 0)
    starts = job_headers(text)
    found = []
    for index, (job, start) in enumerate(starts):
        body = text[start : starts[index + 1][1] if index + 1 < len(starts) else len(text)]
        if not re.search(r"uses:\s*actions/checkout@", body):
            continue
        own = permissions_at(body, 4)
        if not reads_contents(own if own is not None else top):
            found.append(job)
    return found


def test_every_checkout_can_read_the_repository():
    broken = {
        path.name: jobs for path in sorted(WORKFLOWS.glob("*.yml")) if (jobs := unreadable_checkouts(path.read_text()))
    }
    assert not broken, (
        f"these jobs check the repository out under a `permissions:` block with no `contents` scope: {broken}. "
        "Naming any scope sets every unnamed one to `none`, so checkout works in a public repository and fails "
        "with `Repository not found` in a private one. Add `contents: read`."
    )


@pytest.mark.parametrize(
    "workflow, expected",
    [
        ("permissions:\n  pull-requests: write\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@v7\n", ["a"]),
        ("permissions:\n  contents: read\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@v7\n", []),
        ("jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v7\n", []),
        ("permissions: {}\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@v7\n", ["a"]),
        ("permissions: read-all\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@v7\n", []),
        (
            "permissions:\n  contents: read\njobs:\n  a:\n    permissions:\n      issues: write\n"
            "    steps:\n      - uses: actions/checkout@v7\n  b:\n    steps:\n      - uses: actions/checkout@v7\n",
            ["a"],
        ),
        ("permissions:\n  pull-requests: write\njobs:\n  a:\n    steps:\n      - run: echo hi\n", []),
        (
            "on:\n  push:\n  workflow_dispatch:\npermissions:\n  pull-requests: write\n"
            "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v7\n",
            ["a"],
        ),
    ],
    ids=[
        "names-another-scope",
        "names-contents",
        "no-block",
        "empty",
        "read-all",
        "job-replaces-top",
        "no-checkout",
        "triggers-are-not-jobs",
    ],
)
def test_the_predicate(workflow: str, expected: Optional[list]):
    """Each shape on a workflow built to have it, so the real-tree test above
    cannot pass by reading nothing — the job-level row is the one GitHub's own
    replace-not-merge rule decides, and the easiest to get backwards."""
    assert unreadable_checkouts(workflow) == expected


def test_triggers_are_not_job_headers():
    text = "on:\n  push:\n  workflow_dispatch:\njobs:\n  a:\n    steps: []\n  b:\n    steps: []\n"
    assert [job for job, _ in job_headers(text)] == ["a", "b"]
