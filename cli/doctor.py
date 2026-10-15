"""``dev doctor`` — the facts about this repository's GitHub account that no file can state.

Every gate in this tree asks whether the tree agrees with itself. A release can
still fail on first use because of a setting on the account: Actions forbidden to
open pull requests with no token to fall back on, the default branch not being
the one work lands on, a required status check naming a job that never runs. A
tree that is entirely green cannot see any of those, so this asks GitHub.

It reports and never changes anything. A fact it could not read is printed as
unknown, and the summary says all is well only when every fact was answered:
"I could not check" is not the same answer as "nothing is wrong".
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from typing import Any, List, Optional, Set

import click

from scripts.paths import GITHUB_DIR
from scripts.yaml_text import read_uncommented

from .helpers import PROJECT_ROOT, detail, emit, fail, ok, warn

OK, PROBLEM, UNKNOWN = "ok", "problem", "unknown"

#: The branch work lands on, rendered at scaffold time.
BASE_BRANCH = "develop"

#: Present only where the release job opens a pull request (`--versioning tag` removes it).
RELEASE_CONFIG = GITHUB_DIR / "release-please-config.json"

#: The secrets `ci.yml`'s release job falls back on, in its order: a PAT, or a GitHub App's pair.
#: `tests/test_doctor.py` requires each name to still appear in that job.
RELEASE_TOKEN = "RELEASE_TOKEN"
APP_PAIR = ("APP_ID", "APP_PRIVATE_KEY")


@dataclass
class Fact:
    name: str
    state: str
    detail: str


class Unreadable(Exception):
    """`gh` could not answer; `status` is the HTTP status when it said one."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def gh_api(path: str) -> Any:
    """`gh api <path>`, with `{owner}` and `{repo}` filled in by gh from this checkout."""
    try:
        result = subprocess.run(["gh", "api", path], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    except FileNotFoundError:
        raise Unreadable("gh is not installed")
    if result.returncode != 0:
        said = (result.stderr or result.stdout).strip().splitlines()
        message = said[-1] if said else f"gh api {path} exited {result.returncode}"
        status = re.search(r"\(HTTP (\d+)\)", message)
        raise Unreadable(message, int(status.group(1)) if status else None)
    return json.loads(result.stdout or "null")


def default_branch() -> Fact:
    name = "default branch is the base branch"
    try:
        repo = gh_api("repos/{owner}/{repo}")
    except Unreadable as error:
        return Fact(name, UNKNOWN, str(error))
    default = repo.get("default_branch", "")
    if default == BASE_BRANCH:
        return Fact(name, OK, f"{default}")
    return Fact(
        name,
        PROBLEM,
        f"GitHub's default is {default!r} and work lands on {BASE_BRANCH!r}, so pull requests and fresh "
        "clones start on the wrong branch (Settings → General → Default branch)",
    )


def _secret_names() -> Optional[Set[str]]:
    """Secret names visible to this repository's Actions, or `None` if neither list could be read."""
    names: Set[str] = set()
    read = False
    for path in ("repos/{owner}/{repo}/actions/secrets", "repos/{owner}/{repo}/actions/organization-secrets"):
        try:
            names |= {secret["name"] for secret in gh_api(path).get("secrets", [])}
            read = True
        except Unreadable:
            continue
    return names if read else None


def release_pull_request() -> Optional[Fact]:
    if not RELEASE_CONFIG.exists():
        return None
    name = "the release job can open its pull request"
    try:
        allowed = gh_api("repos/{owner}/{repo}/actions/permissions/workflow").get("can_approve_pull_request_reviews")
    except Unreadable as error:
        return Fact(name, UNKNOWN, f"could not read the Actions permission: {error}")
    if allowed:
        return Fact(name, OK, "Actions may open pull requests here")
    names = _secret_names()
    if names is None:
        return Fact(name, UNKNOWN, "Actions may not open pull requests here, and the secrets could not be listed")
    if RELEASE_TOKEN in names:
        return Fact(name, OK, f"Actions may not open pull requests; the job uses {RELEASE_TOKEN}")
    if set(APP_PAIR) <= names:
        return Fact(name, OK, f"Actions may not open pull requests; the job uses the App ({', '.join(APP_PAIR)})")
    return Fact(
        name,
        PROBLEM,
        f"Actions may not open pull requests and neither {RELEASE_TOKEN} nor {' + '.join(APP_PAIR)} is set, "
        "so the release job will be refused its pull request (see the release-please job in ci.yml)",
    )


def workflow_job_names() -> Set[str]:
    """Every job id and job-level `name:` across the workflows, as a check context would spell it."""
    names: Set[str] = set()
    for path in sorted(GITHUB_DIR.glob("workflows/*.y*ml")):
        text = read_uncommented(path)
        jobs = re.search(r"^jobs:\s*$", text, re.MULTILINE)
        if not jobs:
            continue
        body = text[jobs.end() :]
        names |= set(re.findall(r"^  ([A-Za-z_][\w-]*):\s*$", body, re.MULTILINE))
        names |= {n.strip().strip("'\"") for n in re.findall(r"^    name:\s*(.+?)\s*$", body, re.MULTILINE)}
    return names


def resolves(context: str, names: Set[str]) -> bool:
    """A context is a job name, a matrix leg of one, or a name with `${{ }}` filled in."""
    for name in names:
        if context == name or context.startswith(f"{name} ("):
            return True
        pattern = ".+".join(re.escape(part) for part in re.split(r"\$\{\{.*?\}\}", name))
        if "${{" in name and re.fullmatch(pattern, context):
            return True
    return False


def required_checks() -> Fact:
    name = f"every required check on {BASE_BRANCH} is a job that runs"
    try:
        # Concatenated, not an f-string: doubled braces would read as a scaffold placeholder.
        found = gh_api("repos/{owner}/{repo}/branches/" + BASE_BRANCH + "/protection/required_status_checks")
    except Unreadable as error:
        if error.status == 404:
            return Fact(name, OK, f"{BASE_BRANCH} requires no checks, so none can wait forever")
        return Fact(name, UNKNOWN, str(error))
    contexts = list(found.get("contexts") or []) or [check["context"] for check in found.get("checks", [])]
    names = workflow_job_names()
    unresolved = [c for c in contexts if not resolves(c, names)]
    dangling = [c for c in unresolved if "/" not in c]
    if dangling:
        return Fact(
            name,
            PROBLEM,
            f"required but no workflow job reports it: {', '.join(dangling)} — every pull request into "
            f"{BASE_BRANCH} waits for it forever",
        )
    if unresolved:
        return Fact(name, UNKNOWN, f"reported by something other than these workflows: {', '.join(unresolved)}")
    return Fact(name, OK, f"{len(contexts)} required, all reported by a job here")


def gather() -> List[Fact]:
    facts = [default_branch(), release_pull_request(), required_checks()]
    return [fact for fact in facts if fact is not None]


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Print the facts as JSON.")
def doctor(as_json: bool) -> None:
    """Ask GitHub the facts about this repository that no file in it can state.

    \b
    Reports and never changes anything. Exits 1 when a fact is known to be
    wrong; an unreadable fact is reported as unknown and does not fail.
    """
    facts = gather()
    problems = [f for f in facts if f.state == PROBLEM]
    unknown = [f for f in facts if f.state == UNKNOWN]
    if as_json:
        emit({"facts": [asdict(f) for f in facts]})
        raise SystemExit(1 if problems else 0)
    for fact in facts:
        {OK: ok, PROBLEM: fail, UNKNOWN: warn}[fact.state](fact.name)
        detail(f"  {fact.detail}")
    detail()
    if problems:
        fail(f"{len(problems)} of {len(facts)} facts are wrong")
    elif unknown:
        warn(f"nothing known to be wrong, but {len(unknown)} of {len(facts)} facts could not be read")
    else:
        ok(f"all {len(facts)} facts checked and none is wrong")
    raise SystemExit(1 if problems else 0)
