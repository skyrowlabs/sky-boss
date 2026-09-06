"""`check pre-push` runs every gate CI blocks on, or says why it cannot.

The command used to open with *"Everything CI blocks on, in the order that fails
fastest."* It was not. It omitted `check_skip_budget.py` and
`check_commit_subjects.py` — both blocking, both runnable on a host — and the
integration suite, which is blocking and is not.

proto.pilot found it the expensive way: ran `pre-push` four times across four
upgrades, watched it pass, pushed, and CI went red on the skip budget. **The
sentence was doing active work to stop them looking.** A gate that is missing
announces itself the first time something slips through; a gate that is missing
*behind a completeness claim* is the reassuring failure, and it is the one this
repository ranks worst.

## Why a partition rather than "everything is reachable"

The obvious assertion — every blocking CI step must be reachable from
`pre-push` — is red on a fresh scaffold, because the integration job is blocking
and this host has no stack to run it against. That is not an oversight; it is
the reason `pre-push` exists as a distinct thing from CI. proto.pilot proposed
it, then withdrew it on exactly that ground.

So each blocking check is in one of two sets, and **a check in neither is the
failure**. That makes it a partition rather than an allowlist, and it is the
same shape `cli/test_cmds.py` uses for `scheduled` / `UNSCHEDULED`: an exemption
has to say which kind it is, and it expires when it stops being true.

## Scope, stated because it is narrower than the docstring it guards

Two dimensions, both robust to how a command is spelled:

* **scripts** — `scripts/*.py` named in the workflows against those reachable
  from `pre_push`.
* **suites** — pytest markers CI selects against those `pre_push` selects.

Lint tools are deliberately absent: `tests/test_lint_tool_parity.py` already
holds `.pre-commit-config.yaml` and `scripts/requirements.txt` to each other,
and a second comparison of the same pair here would be the duplicate this
project refuses everywhere else.
"""

from __future__ import annotations

import ast
import functools
import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanning import scanned  # noqa: E402
from scripts.paths import CLI_DIR, GITHUB_DIR, TESTS_DIR  # noqa: E402
from scripts.yaml_text import read_uncommented  # noqa: E402

CHECK_PY = CLI_DIR / "check.py"
WORKFLOWS = GITHUB_DIR / "workflows"

_SCRIPT = re.compile(r"scripts/[a-z0-9_]+\.py")
_DASH_M = re.compile(r"-m\s+([a-z_]+)")
_JOB = re.compile(r"^  (?P<id>[A-Za-z_][A-Za-z0-9_-]*):\s*$", re.MULTILINE)
_NEEDS = re.compile(r"^\s+needs:\s*(?P<value>\S.*)$", re.MULTILINE)


@functools.lru_cache(maxsize=1)
def _markers() -> frozenset:
    """The marker names, read from `pytest.ini` rather than guessed.

    `-m` is two different flags: `python -m pytest` names a MODULE and
    `pytest -m unit` names a marker. A pattern that took whatever followed
    `-m` reported `pytest:pytest` as a blocking suite — a check that does not
    exist, in a gate whose whole job is to notice checks that are missing.
    Reading the real set makes the ambiguity unrepresentable instead of
    filtered.
    """
    ini = (TESTS_DIR / "pytest.ini").read_text(encoding="utf-8")
    block = ini.split("markers =", 1)[-1]
    found = set()
    for line in block.splitlines()[1:]:
        if not line.startswith((" ", "\t")) or ":" not in line:
            break
        found.add(line.strip().split(":", 1)[0])
    return frozenset(scanned(found, "markers declared in tests/pytest.ini", least=3))


#: A blocking check `pre-push` does not run, and the reason, which is checked
#: against the thing it exempts on every run.
#:
#: `nostack` is a fact about the check: it needs services this host does not
#: have, and that stays true however the tree changes. There is deliberately no
#: second kind — an exemption because *nobody got round to it* is the state this
#: file exists to make visible, not to license.
UNREACHABLE = {
    "pytest:integration": "needs the stack up and seeded; a host run has no services to talk to",
}


def _blocking_checks() -> dict:
    """Every script and suite a BLOCKING job in `ci.yml` runs, keyed by check id.

    Read from `ci.yml` alone: the nightly workflow is a schedule, not a gate a
    push waits on, and holding `pre-push` to it would make a local run
    responsible for the coverage ratchet.

    **Blocking is derived, not assumed: a job is blocking when some other job
    `needs:` it.** Scanning the whole file instead reported the `ui` suite —
    a true statement about `ci.yml` and the wrong answer to the question asked,
    which is the failure this repository keeps meeting. `ci.yml` states the
    reason at the `release-please` job: `ui` is out of `needs:` deliberately,
    because it is the one job a repo with nothing marked `ui` deletes, and a
    `needs:` naming a deleted job is a `startup_failure` rather than a red job.
    So a suite outside `needs:` is one this tree has already decided must not
    hold a push up, and `pre-push` inherits that decision instead of re-making
    it. Branch protection is the real authority and lives outside the repo;
    `needs:` is the structural fact the tree holds, and
    `test_workflow_job_graph.py` already treats it as one.
    """
    text = read_uncommented(WORKFLOWS / "ci.yml")
    blocking = set()
    for match in _NEEDS.finditer(text):
        value = match.group("value").strip().strip("[]")
        blocking.update(part.strip().strip("'\"") for part in value.split(",") if part.strip())

    bounds = [(m.group("id"), m.start(), m.end()) for m in _JOB.finditer(text)]
    markers = _markers()
    found = {}
    for index, (job, _, body_start) in enumerate(bounds):
        if job not in blocking:
            continue
        body = text[body_start : bounds[index + 1][1] if index + 1 < len(bounds) else len(text)]
        found.update({f"script:{name}": job for name in _SCRIPT.findall(body)})
        found.update({f"pytest:{m}": job for m in _DASH_M.findall(body) if m in markers})
    return found


def _pre_push_reaches() -> set:
    """Scripts and markers reachable from `pre_push`, by reading the source.

    Not by running it: `pre-push` shells out to a formatter and a whole test
    suite, and a test that ran it would be measuring this machine rather than
    the command. The call graph is one level deep by construction — `pre_push`
    composes helpers defined beside it — so the walk follows plain-name calls
    within the module and stops.
    """
    tree = ast.parse(CHECK_PY.read_text(encoding="utf-8"))
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}

    seen, queue, reached = set(), ["pre_push"], set()
    while queue:
        name = queue.pop()
        if name in seen or name not in functions:
            continue
        seen.add(name)
        for node in ast.walk(functions[name]):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                queue.append(node.func.id)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                reached.update(f"script:{m}" for m in _SCRIPT.findall(node.value))
        # A marker arrives as two adjacent arguments, `"-m", "unit"`, so it is
        # read off the call rather than out of a single string.
        for node in ast.walk(functions[name]):
            if not isinstance(node, ast.Call):
                continue
            args = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            reached.update(
                f"pytest:{args[i + 1]}" for i, a in enumerate(args[:-1]) if a == "-m" and args[i + 1] in _markers()
            )
    return reached


def test_the_scan_reads_both_sides():
    """Either enumeration coming back empty would make the partition vacuous."""
    scanned(_blocking_checks(), "blocking checks in ci.yml", least=4)
    scanned(_pre_push_reaches(), "checks reachable from pre_push", least=4)


def test_every_blocking_check_is_run_or_declared():
    blocking = _blocking_checks()
    reached = _pre_push_reaches()
    orphans = sorted(set(blocking) - reached - set(UNREACHABLE))
    assert not orphans, (
        f"CI blocks on these and `check pre-push` neither runs them nor declares them: {orphans}.\n"
        "Add them to cli/check.py::pre_push, or add an entry to UNREACHABLE saying why this host "
        "cannot. A gate in neither set is one somebody finds out about from a red CI run."
    )


def test_a_declaration_still_names_a_blocking_check():
    """An exemption whose check left the workflow has outlived its reason.

    Worse than untidy: the id can come back for something else and arrive
    pre-exempted, which is an exemption nobody chose.
    """
    stale = sorted(set(UNREACHABLE) - set(_blocking_checks()))
    assert not stale, (
        f"UNREACHABLE names checks ci.yml no longer runs: {stale}. Delete the entries — "
        "do not rewrite the reasons to keep them alive."
    )


def test_a_declaration_is_not_something_pre_push_already_runs():
    """The other staleness direction, and the one that fails quietly.

    An entry that stays after the gate is wired up reads as *we still cannot do
    this*, in the file somebody consults to find out.
    """
    contradicted = sorted(set(UNREACHABLE) & _pre_push_reaches())
    assert (
        not contradicted
    ), f"UNREACHABLE claims `pre-push` cannot run these, and it does: {contradicted}. Delete them."
