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

import base64
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote

import click

from scripts.paths import GITHUB_DIR
from scripts.yaml_text import uncommented

from .helpers import PROJECT_ROOT, detail, emit, fail, ok, skip, warn

OK, PROBLEM, UNKNOWN, NOT_APPLICABLE = "ok", "problem", "unknown", "not applicable"

#: The branch work lands on, and the branch releases land on; the same branch in a one-branch tree.
BASE_BRANCH = "develop"
RELEASE_BRANCH = "main"

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

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def gh_api(path: str) -> Any:
    """`gh api <path>`, with `{owner}` and `{repo}` filled in by gh from this checkout."""
    try:
        result = subprocess.run(["gh", "api", path], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    except FileNotFoundError:
        raise Unreadable("gh is not installed") from None
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


def _secret_names() -> set[str] | None:
    """Secret names visible to this repository's Actions, or `None` if neither list could be read."""
    names: set[str] = set()
    read = False
    for path in ("repos/{owner}/{repo}/actions/secrets", "repos/{owner}/{repo}/actions/organization-secrets"):
        try:
            names |= {secret["name"] for secret in gh_api(path).get("secrets", [])}
            read = True
        except Unreadable:
            continue
    return names if read else None


def release_pull_request() -> Fact:
    name = "the release job can open its pull request"
    if not RELEASE_CONFIG.exists():
        return Fact(name, NOT_APPLICABLE, f"no {RELEASE_CONFIG.name}: this tree opens no release pull request")
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


@dataclass
class Job:
    id: str
    name: str
    matrix: bool
    #: Jobs this one `needs:`. A required check that needs an unrequired job is
    #: skipped when that job fails, and protection accepts a skip as a pass.
    needs: tuple[str, ...] = ()
    #: `if: always()` — runs whatever its needs did, so the skip above cannot happen.
    runs_regardless: bool = False


#: Present only at governed and above. A bare `@org` on every line is rejected by
#: GitHub ("Unknown owner") and requests no review; proto.pilot had five errors.
CODEOWNERS = GITHUB_DIR / "CODEOWNERS"


def workflow_jobs(texts: list[str]) -> list[Job]:
    """Every job in these workflow texts: its id, the name its check reports under, and whether it fans out."""
    jobs: list[Job] = []
    for text in texts:
        text = uncommented(text)
        start = re.search(r"^jobs:\s*$", text, re.MULTILINE)
        if not start:
            continue
        body = text[start.end() :]
        headers = list(re.finditer(r"^  ([A-Za-z_][\w-]*):\s*$", body, re.MULTILINE))
        for i, header in enumerate(headers):
            job = body[header.end() : headers[i + 1].start() if i + 1 < len(headers) else len(body)]
            named = re.search(r"^    name:\s*(.+?)\s*$", job, re.MULTILINE)
            name = named.group(1).strip("'\"") if named else header.group(1)
            condition = re.search(r"^    if:\s*(.+?)\s*$", job, re.MULTILINE)
            jobs.append(
                Job(
                    header.group(1),
                    name,
                    bool(re.search(r"^\s+matrix:", job, re.MULTILINE)),
                    tuple(_needs(job)),
                    bool(condition and "always()" in condition.group(1)),
                )
            )
    return jobs


def _needs(job: str) -> list[str]:
    """The job ids a job's `needs:` names, inline (`needs: [a, b]`, `needs: a`) or as a block list."""
    # `[ \t]*`, not `\s*`: the latter swallows the newline and reads the block list's first item as inline.
    line = re.search(r"^    needs:[ \t]*(.*?)[ \t]*$", job, re.MULTILINE)
    if not line:
        return []
    inline = line.group(1).strip()
    if inline:
        return [n.strip().strip("'\"") for n in inline.strip("[]").split(",") if n.strip()]
    out = []
    for following in job[line.end() :].splitlines()[1:]:
        item = re.match(r"^\s+-\s*(\S+)", following)
        if not item:
            break
        out.append(item.group(1).strip("'\""))
    return out


def branch_workflows(branch: str) -> list[str]:
    """The workflow files as they are on `branch`, which is what its pull requests run, not this checkout's."""
    ref = "?ref=" + quote(branch, safe="")
    texts = []
    for entry in gh_api("repos/{owner}/{repo}/contents/.github/workflows" + ref):
        if entry.get("name", "").endswith((".yml", ".yaml")):
            content = gh_api("repos/{owner}/{repo}/contents/" + entry["path"] + ref)["content"]
            texts.append(base64.b64decode(content).decode("utf-8"))
    return texts


def classify(context: str, jobs: list[Job]) -> str:
    """`job` for a check a job reports under; `leg` for one only a matrix reports; `""` for neither.

    A matrix's checks are never safe to require: skipped, it reports once under its
    unexpanded name, so a required leg waits forever (stash.flow). Require the
    job that summarises the matrix instead, as `ci.yml` does.
    """
    leg = False
    for job in jobs:
        fanned = job.name if "${{" in job.name else ""
        pattern = ".+".join(re.escape(part) for part in re.split(r"\$\{\{.*?\}\}", fanned))
        named = context in (job.name, job.id) or bool(fanned and re.fullmatch(pattern, context))
        if job.matrix and (named or context.startswith((f"{job.name} (", f"{job.id} ("))):
            leg = True
        elif named:
            return "job"
    return "leg" if leg else ""


def required_checks(branch: str) -> Fact:
    """Every check `branch` requires is reported by a job in `branch`'s own workflows, and never by a matrix leg."""
    name = f"every required check on {branch} is a job that runs"
    try:
        # Concatenated, not an f-string: doubled braces would read as a scaffold placeholder.
        found = gh_api("repos/{owner}/{repo}/branches/" + branch + "/protection/required_status_checks")
    except Unreadable as error:
        if error.status == 404:
            return Fact(name, OK, f"{branch} requires no checks, so none can wait forever")
        return Fact(name, UNKNOWN, str(error))
    contexts = list(found.get("contexts") or []) or [check["context"] for check in found.get("checks", [])]
    try:
        jobs = workflow_jobs(branch_workflows(branch))
    except Unreadable as error:
        return Fact(name, UNKNOWN, f"could not read the workflows on {branch}: {error}")
    kinds = {context: classify(context, jobs) for context in contexts}
    legs = [c for c, kind in kinds.items() if kind == "leg"]
    dangling = [c for c, kind in kinds.items() if not kind and "/" not in c]
    elsewhere = [c for c, kind in kinds.items() if not kind and "/" in c]
    if dangling or legs:
        said = [f"no job on {branch} reports {', '.join(dangling)}"] if dangling else []
        said += [f"{', '.join(legs)} is a matrix leg, which reports under another name when skipped"] if legs else []
        return Fact(name, PROBLEM, "; ".join(said) + f" — pull requests into {branch} can wait for it forever")
    if elsewhere:
        return Fact(name, UNKNOWN, f"reported by something other than {branch}'s workflows: {', '.join(elsewhere)}")
    # Every required check is a job. A job that `needs:` one nobody requires is
    # skipped when that one fails, and protection accepts the skip: mind.head
    # measured six required contexts, five needing an unrequired gate, so a gate
    # failure let a pull request merge having proven nothing (sky.boss first).
    required = {job.id for job in jobs if job.name in contexts or job.id in contexts}
    required |= {job.name for job in jobs if job.id in required}
    exposed = []
    for job in jobs:
        if job.id not in required or job.runs_regardless:
            continue
        for need in job.needs:
            if need not in required:
                exposed.append(f"{job.name} needs {need}")
    if exposed:
        return Fact(
            name,
            PROBLEM,
            "; ".join(exposed) + " — when that job fails its dependents are skipped, protection accepts a "
            f"skip, and a pull request into {branch} merges having proven nothing: require it too",
        )
    return Fact(name, OK, f"{len(contexts)} required, each reported by a job in {branch}'s workflows")


def backmerge() -> Fact:
    """Everything released on the release branch is back on the base branch."""
    name = f"{BASE_BRANCH} contains everything on {RELEASE_BRANCH}"
    if BASE_BRANCH == RELEASE_BRANCH:
        return Fact(name, NOT_APPLICABLE, "one branch, so there is nothing to merge back")
    try:
        compared = gh_api(
            "repos/{owner}/{repo}/compare/" + quote(BASE_BRANCH, safe="") + "..." + quote(RELEASE_BRANCH, safe="")
        )
    except Unreadable as error:
        return Fact(name, UNKNOWN, str(error))
    ahead = int(compared.get("ahead_by") or 0)
    if not ahead:
        return Fact(name, OK, f"{RELEASE_BRANCH} has no commit {BASE_BRANCH} lacks")
    files = compared.get("files")
    if files is None:
        return Fact(name, UNKNOWN, f"{RELEASE_BRANCH} is {ahead} commit(s) ahead and the diff could not be read")
    if not files:
        # A merge of the base branch into the release branch leaves the release
        # branch one commit ahead with nothing in the diff: the ordinary state of
        # every non-fast-forward tree, and not a missed back-merge (sky.boss).
        return Fact(name, OK, f"{RELEASE_BRANCH} is {ahead} commit(s) ahead, every one a merge that changed nothing")
    subjects = [c.get("commit", {}).get("message", "").splitlines()[0] for c in compared.get("commits", [])][:3]
    # stash.flow found this as VERSION 0.2.0 on main and 0.1.0 on develop. That
    # is their history, so it stays here and out of what every tree prints.
    return Fact(
        name,
        PROBLEM,
        f"{RELEASE_BRANCH} carries {ahead} commit(s) touching {len(files)} file(s) that {BASE_BRANCH} lacks "
        f"({'; '.join(s for s in subjects if s)}) — merge {RELEASE_BRANCH} back, or the next release "
        "re-proposes the bump",
    )


def codeowners() -> Fact:
    """Every owner CODEOWNERS names is one GitHub recognises, so a review is actually requested."""
    name = "CODEOWNERS names owners GitHub recognises"
    if not CODEOWNERS.exists():
        return Fact(name, NOT_APPLICABLE, f"no {CODEOWNERS.relative_to(PROJECT_ROOT)} in this tree")
    try:
        found = gh_api("repos/{owner}/{repo}/codeowners/errors")
    except Unreadable as error:
        return Fact(name, UNKNOWN, str(error))
    errors = found.get("errors") or []
    if errors:
        first = errors[0]
        return Fact(
            name,
            PROBLEM,
            f"{len(errors)} line(s) GitHub rejects, e.g. line {first.get('line')}: {first.get('message', '')} "
            "— no review is requested from an owner that does not resolve",
        )
    return Fact(name, OK, "every owner resolves")


def gather() -> list[Fact]:
    branches = dict.fromkeys((BASE_BRANCH, RELEASE_BRANCH))
    return [
        default_branch(),
        release_pull_request(),
        *(required_checks(branch) for branch in branches),
        backmerge(),
        codeowners(),
    ]


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
    applicable = [f for f in facts if f.state != NOT_APPLICABLE]
    if as_json:
        emit({"facts": [asdict(f) for f in facts]})
        raise SystemExit(1 if problems else 0)
    for fact in facts:
        {OK: ok, PROBLEM: fail, UNKNOWN: warn, NOT_APPLICABLE: skip}[fact.state](fact.name)
        detail(f"  {fact.detail}")
    detail()
    if problems:
        fail(f"{len(problems)} of {len(applicable)} facts are wrong")
    elif unknown:
        warn(f"nothing known to be wrong, but {len(unknown)} of {len(applicable)} facts could not be read")
    else:
        ok(f"all {len(applicable)} applicable facts checked and none is wrong")
    raise SystemExit(1 if problems else 0)
