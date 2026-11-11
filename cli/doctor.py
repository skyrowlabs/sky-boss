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
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote

import click
import yaml

from scripts import repo_settings
from scripts.lanes import job_registry
from scripts.paths import GITHUB_DIR
from scripts.yaml_text import uncommented

from .helpers import PROJECT_ROOT, detail, emit, fail, ok, skip, warn

#: tests/test_cli_smoke.py runs this module's argument-less commands for real.
SMOKE_EXECUTES = True

OK, PROBLEM, UNKNOWN, NOT_APPLICABLE = "ok", "problem", "unknown", "not applicable"

#: The branch work lands on, and the branch releases land on; the same branch in a one-branch tree.
BASE_BRANCH = "develop"
RELEASE_BRANCH = "main"

#: Present only where the release job opens a pull request (`--versioning tag` removes it).
RELEASE_CONFIG = GITHUB_DIR / "release-please-config.json"

#: The command that fixes every settings fact, held once so no wrapped line holds the CLI name.
APPLY = "`dev settings --apply`"

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
    #: `always()` or `!cancelled()` — runs whatever its needs did, so the skip above cannot happen.
    runs_regardless: bool = False


#: Present only at governed and above. A bare `@org` on every line is rejected by
#: GitHub ("Unknown owner") and requests no review; proto.pilot had five errors.
#: A tree scaffolded without `--owner` ships it with no rules, which is reported.
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
                    bool(condition and re.search(r"always\(\)|!cancelled\(\)", condition.group(1))),
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


def required_contexts(branch: str) -> list[str]:
    """The status checks `branch`'s protection requires; empty when it requires none."""
    try:
        # Concatenated, not an f-string: doubled braces would read as a scaffold placeholder.
        found = gh_api("repos/{owner}/{repo}/branches/" + branch + "/protection/required_status_checks")
    except Unreadable as error:
        if error.status == 404:
            return []
        raise
    return list(found.get("contexts") or []) or [check["context"] for check in found.get("checks", [])]


def required_checks(branch: str) -> Fact:
    """Every check `branch` requires is reported by a job in `branch`'s own workflows, and never by a matrix leg."""
    name = f"every required check on {branch} is a job that runs"
    try:
        contexts = required_contexts(branch)
    except Unreadable as error:
        return Fact(name, UNKNOWN, str(error))
    if not contexts:
        return Fact(name, OK, f"{branch} requires no checks, so none can wait forever")
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


def _branch_exists(branch: str) -> bool:
    try:
        gh_api("repos/{owner}/{repo}/branches/" + quote(branch, safe=""))
    except Unreadable:
        return False
    return True


def codeowners() -> Fact:
    """Every owner CODEOWNERS names is one GitHub recognises, so a review is actually requested."""
    name = "CODEOWNERS names owners GitHub recognises"
    if not CODEOWNERS.exists():
        return Fact(name, NOT_APPLICABLE, f"no {CODEOWNERS.relative_to(PROJECT_ROOT)} in this tree")
    rules = [line for line in CODEOWNERS.read_text(encoding="utf-8").splitlines() if line.split("#")[0].strip()]
    if not rules:
        return Fact(name, PROBLEM, "it names no owner, so no review is ever requested — add `* @user` or `* @org/team`")
    # Asked per long-lived branch: with no `ref`, GitHub reads the DEFAULT branch's
    # file, so a branch that changed its owners was judged by another's (stash.flow).
    for branch in dict.fromkeys((BASE_BRANCH, RELEASE_BRANCH)):
        try:
            found = gh_api("repos/{owner}/{repo}/codeowners/errors?ref=" + quote(branch, safe=""))
        except Unreadable as error:
            if error.status == 404 and _branch_exists(branch):
                # GitHub answers 404 for a branch with no CODEOWNERS, which is a
                # finding, not an unreadable answer (stash.flow).
                return Fact(name, PROBLEM, f"{branch}: no CODEOWNERS, so a pull request into it requests no review")
            return Fact(name, UNKNOWN, f"{branch}: {error}")
        errors = found.get("errors") or []
        if errors:
            first = errors[0]
            return Fact(
                name,
                PROBLEM,
                f"{branch}: {len(errors)} line(s) GitHub rejects, e.g. line {first.get('line')}: "
                f"{first.get('message', '')} — no review is requested from an owner that does not resolve",
            )
    return Fact(name, OK, "every owner resolves on every long-lived branch")


def setting_name(key: str) -> str:
    return f"setting {key}"


def _repo(repo: dict | None) -> dict:
    """`repo` if the caller already fetched it, else `GET repos/{owner}/{repo}`; raises Unreadable."""
    return repo if repo is not None else gh_api("repos/{owner}/{repo}")


def repository_settings(repo: dict | None = None) -> list[Fact]:
    """One fact per setting `scripts/repo_settings.py` declares, plus the description.

    A fact's name is the setting and its detail is what GitHub reports beside what
    the profile wants, so a problem never reads as the state it is asking for.
    """
    try:
        repo = _repo(repo)
    except Unreadable as error:
        settings = repo_settings.REPOSITORY + repo_settings.PUBLIC_ONLY
        names = [setting_name(s.key) for s in settings] + ["repository description"]
        return [Fact(name, UNKNOWN, str(error)) for name in names]
    facts = []
    for row in repo_settings.compare(repo):
        name, why = setting_name(row.setting.key), row.setting.why
        have, want = repo_settings.onoff(row.have), repo_settings.onoff(row.setting.want)
        if not row.applies:
            facts.append(Fact(name, NOT_APPLICABLE, f"the repository is {repo.get('visibility', 'not public')}"))
        elif row.have is None:
            facts.append(Fact(name, UNKNOWN, "GitHub did not report it; security settings are shown to admins only"))
        elif row.have == row.setting.want:
            facts.append(Fact(name, OK, f"{have} — {why}"))
        else:
            facts.append(Fact(name, PROBLEM, f"{have}; should be {want} — {why}. {APPLY} sets it"))
    if (repo.get("description") or "").strip():
        facts.append(Fact("repository description", OK, repo["description"]))
    else:
        empty = f"empty — {APPLY} writes the tagline"
        facts.append(Fact("repository description", PROBLEM, empty))
    return facts


def dependabot_alerts(repo: dict | None = None) -> Fact:
    """On or off, judged only by a token that can see the answer.

    GitHub answers 404 both when alerts are off and when the token is not an admin,
    so the repository's own `permissions.admin` decides which of the two it was.
    """
    name = "Dependabot alerts"
    try:
        admin = bool(_repo(repo).get("permissions", {}).get("admin"))
    except Unreadable:
        admin = False
    try:
        gh_api("repos/{owner}/{repo}/vulnerability-alerts")
    except Unreadable as error:
        if error.status != 404:
            return Fact(name, UNKNOWN, str(error))
        if not admin:
            return Fact(name, UNKNOWN, "GitHub answers 404 to a token that is not an admin, on or off")
        return Fact(name, PROBLEM, f"off; should be on — {repo_settings.ALERTS_WHY}. {APPLY} turns them on")
    return Fact(name, OK, f"on — {repo_settings.ALERTS_WHY}")


def security_updates(repo: dict | None = None) -> Fact:
    """On or off, from `automated-security-fixes`, judged only by a token that can see it.

    Version updates never bump a transitive dependency, so without these a known
    vulnerability there is reported and never fixed (sky.boss's undici).
    """
    name = "Dependabot security updates"
    try:
        admin = bool(_repo(repo).get("permissions", {}).get("admin"))
    except Unreadable:
        admin = False
    try:
        answer = gh_api("repos/{owner}/{repo}/automated-security-fixes")
    except Unreadable as error:
        if error.status != 404:
            return Fact(name, UNKNOWN, str(error))
        if not admin:
            return Fact(name, UNKNOWN, "GitHub answers 404 to a token that is not an admin, on or off")
        answer = {}
    if not (answer or {}).get("enabled"):
        return Fact(name, PROBLEM, f"off; should be on — {repo_settings.SECURITY_UPDATES_WHY}. {APPLY} turns them on")
    return Fact(name, OK, f"on — {repo_settings.SECURITY_UPDATES_WHY}")


def coverage_runners_enabled() -> Fact:
    """Every workflow naming the coverage check is enabled, or held off on purpose (stash.flow).

    A disabled workflow is still on disk, so only GitHub can say it is off, and
    only `HELD_WORKFLOWS` can say somebody meant it.
    """
    from scripts import allowlist
    from scripts.check_coverage_budget import runners

    name = "the workflows that run the coverage floor are enabled"
    named = runners()
    if not named:
        return Fact(name, NOT_APPLICABLE, "no workflow names the coverage check")
    held = allowlist.read(repo_settings.HELD_WORKFLOWS)
    off: list[str] = []
    kept: list[str] = []
    stale: list[str] = []
    for workflow in named:
        try:
            state = (gh_api("repos/{owner}/{repo}/actions/workflows/" + workflow) or {}).get("state")
        except Unreadable as error:
            return Fact(name, UNKNOWN, str(error))
        if state == "active" and workflow in held:
            stale.append(f"{workflow}: held in {repo_settings.HELD_WORKFLOWS.name}, but GitHub runs it")
        elif state != "active":
            (kept if workflow in held else off).append(f"{workflow} ({state})")
    if off or stale:
        said = [f"{', '.join(off)}: GitHub runs none of it, so nothing holds the floor"] if off else []
        tail = f" {allowlist.STALE_ADVICE}" if stale else ""
        return Fact(name, PROBLEM, "; ".join(said + stale) + tail)
    if kept:
        reasons = "; ".join(f"{entry}: {held[entry.split(' ')[0]]}" for entry in kept)
        return Fact(name, NOT_APPLICABLE, f"disabled on purpose, so the floor holds only by hand — {reasons}")
    return Fact(name, OK, ", ".join(named))


def labels_exist() -> Fact:
    """Every label dependabot.yml or a workflow applies exists; Dependabot drops one that does not."""
    name = "labels Dependabot and the workflows apply exist"
    wanted = repo_settings.labels_wanted(GITHUB_DIR)
    if not wanted:
        return Fact(name, NOT_APPLICABLE, "neither .github/dependabot.yml nor a workflow applies a label")
    try:
        present = {label["name"] for label in gh_api("repos/{owner}/{repo}/labels?per_page=100")}
    except Unreadable as error:
        return Fact(name, UNKNOWN, str(error))
    missing = [label for label in wanted if label not in present]
    if missing:
        return Fact(name, PROBLEM, f"missing {', '.join(missing)} — {APPLY} creates them")
    return Fact(name, OK, ", ".join(wanted))


#: The `types` GitHub assumes when a `pull_request` trigger names none.
DEFAULT_PR_TYPES = ("opened", "synchronize", "reopened")
#: `gh` or `git` asked under cron's environment; bounded, since a prompt cron cannot answer would hang.
CRON_PROBE_TIMEOUT_S = 60
#: `crontab` missing, or hanging: either way there is no installed block to read.
_NO_CRONTAB = (OSError, subprocess.TimeoutExpired)


_GLOB = {"**": ".*", "**/": "(?:.*/)?", "*": "[^/]*", "?": "[^/]"}


def _filter_regex(pattern: str) -> re.Pattern[str]:
    """GitHub's branch and path filter glob: `**` crosses `/`, `*` and `?` do not, anything else is literal.

    A subset of GitHub's syntax. A character it does not model reads literally,
    which can only stop a match, so the error is a loud false problem, never a false pass.
    """
    out = ""
    for token in re.findall(r"\*\*/?|\*|\?|[^*?]+", pattern):
        out += _GLOB.get(token) or re.escape(token)
    return re.compile(out)


def _filtered(values: list[str], include: Any, exclude: Any) -> bool:
    """Whether any of `values` passes an include list (`!` re-excludes, last match wins) or an exclude list."""
    if include is None and exclude is None:
        return True
    patterns = [str(p) for p in (include if include is not None else ["**", *[f"!{e}" for e in exclude or []]])]
    for value in values:
        keep = False
        for pattern in patterns:
            if _filter_regex(pattern.removeprefix("!")).fullmatch(value):
                keep = not pattern.startswith("!")
        if keep:
            return True
    return False


def pr_triggers(text: str, base: str, changed: list[str]) -> bool:
    """Whether a pull request opened into `base`, changing exactly `changed`, starts this workflow."""
    data = yaml.safe_load(text) or {}
    on = data.get("on", data.get(True)) if isinstance(data, dict) else None  # YAML 1.1 reads a bare `on` as True
    if isinstance(on, str):
        return on == "pull_request"
    if isinstance(on, list):
        return "pull_request" in on
    if not isinstance(on, dict) or "pull_request" not in on:
        return False
    trigger = on["pull_request"] or {}
    types = trigger.get("types") or DEFAULT_PR_TYPES
    return (
        "opened" in ([types] if isinstance(types, str) else types)
        and _filtered([base], trigger.get("branches"), trigger.get("branches-ignore"))
        and _filtered(changed, trigger.get("paths"), trigger.get("paths-ignore"))
    )


def report_pull_request_checks(jobs: list[Any]) -> Fact:
    """Every check the base branch requires is defined by a workflow each job's report pull request starts.

    Defined is enough: GitHub counts a job skipped by its own `if:` as passing,
    measured on four trees' pull requests. What waits forever is a check that no
    started workflow defines, so auto-merge never fires.
    """
    name = f"every check {BASE_BRANCH} requires reports on a report pull request"
    try:
        contexts = required_contexts(BASE_BRANCH)
        texts = branch_workflows(BASE_BRANCH)
    except Unreadable as error:
        return Fact(name, UNKNOWN, str(error))
    if not contexts:
        return Fact(name, OK, f"{BASE_BRANCH} requires no checks, so a report pull request merges once opened")
    said = []
    try:
        for job in jobs:
            started = [text for text in texts if pr_triggers(text, BASE_BRANCH, [job.writes])]
            defined = workflow_jobs(started)
            silent = [context for context in contexts if not classify(context, defined)]
            if silent:
                said.append(f"{job.key} (changes {job.writes}): nothing it starts reports {', '.join(silent)}")
    except yaml.YAMLError as error:
        return Fact(name, UNKNOWN, f"a workflow on {BASE_BRANCH} is not YAML: {error}")
    if said:
        return Fact(name, PROBLEM, "; ".join(said) + " — its pull request waits forever and never auto-merges")
    return Fact(name, OK, f"{len(contexts)} required, each defined by a workflow every report pull request starts")


def _probe(argv: list[str], env: dict[str, str], cwd: str) -> tuple[int, str]:
    try:
        done = subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True, timeout=CRON_PROBE_TIMEOUT_S)
    except FileNotFoundError:
        return 127, f"`{argv[0]}` is not on cron's PATH"
    except subprocess.TimeoutExpired:
        return 124, f"no answer in {CRON_PROBE_TIMEOUT_S}s, which is what a prompt cron cannot answer looks like"
    return done.returncode, (done.stderr or done.stdout).strip()[-300:]


def cron_route(registry: Any) -> list[Fact]:
    """`gh` is logged in, and `origin` answers, under the environment the installed crontab gives its jobs.

    Run in the checkout that crontab names, which from a worktree is the main
    checkout: an interactive "logged in" proves nothing for cron.
    """
    names = ("gh is logged in under cron's environment", "origin answers git under cron's environment")
    main = registry.main_checkout()
    checkout = main or registry.CRON_CWD
    where = f" (measured in {checkout}, the checkout the crontab names; this is a linked worktree)" if main else ""
    try:
        listed = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=CRON_PROBE_TIMEOUT_S)
        live = listed.stdout if listed.returncode == 0 else ""
    except _NO_CRONTAB:
        live = ""
    block = registry.installed_block(live, checkout)
    if block is None:
        missing = f"no installed crontab block runs from {checkout}, so there is no cron environment to ask"
        return [Fact(name, UNKNOWN, missing + where) for name in names]
    env = registry.cron_env(block, os.path.expanduser("~"))
    probes = (["gh", "auth", "status"], ["git", "ls-remote", "--exit-code", "origin", "HEAD"])
    facts = []
    for name, argv in zip(names, probes, strict=True):
        # Never prompt: cron has no terminal, and a prompt here would only hang the probe.
        code, said = _probe(argv, {**env, "GIT_TERMINAL_PROMPT": "0", "GH_PROMPT_DISABLED": "1"}, checkout)
        facts.append(Fact(name, OK if code == 0 else PROBLEM, ("answered" if code == 0 else said) + where))
    return facts


def pr_route() -> list[Fact]:
    """The facts a job publishing through an auto-merging pull request needs, for every such job."""
    registry = job_registry()
    publishing = sorted(getattr(registry, "AUTO_PUSH", None) or ())
    if registry is None or not publishing:
        return [Fact("report pull requests can land", NOT_APPLICABLE, "no job here publishes through a pull request")]
    jobs = [registry.JOBS_BY_KEY[key] for key in publishing]
    return [report_pull_request_checks(jobs), *cron_route(registry)]


def gather() -> list[Fact]:
    branches = dict.fromkeys((BASE_BRANCH, RELEASE_BRANCH))
    try:
        repo: dict | None = gh_api("repos/{owner}/{repo}")
    except Unreadable:
        repo = None
    return [
        default_branch(),
        release_pull_request(),
        *(required_checks(branch) for branch in branches),
        backmerge(),
        codeowners(),
        *repository_settings(repo),
        dependabot_alerts(repo),
        security_updates(repo),
        coverage_runners_enabled(),
        labels_exist(),
        *pr_route(),
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
