"""`dev pr land`: carry this branch to a pull request ready to merge, and stop there.

The sequence is the one trees typed by hand after every landing ruling (proto.pilot,
sky.vault): `check pre-push`, push, open the pull request as a draft and mark it
ready, wait for its checks on the head commit, read `mergeStateStatus`. It stops
before the merge and prints the pinned `gh pr merge <n> --merge --match-head-commit
<sha>`, because a merge is a person's ruling (the release skill never merges one
itself either). `--merge` is that ruling given on the command line, and after it the
base branch's push runs on the merge commit are watched too: a job a pull request
skips runs only there, so a green pull request is not yet a green base.

Checks are read once they have *registered* on the head commit and stopped changing.
Straight after `gh pr create` GitHub reports none, which a watcher reads as done
(proto.pilot #38), and the ready flip starts a second run after the draft's has
finished.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from typing import Any

import click

from scripts.output import EXIT_RED, EXIT_REFUSED

from .check import pre_push
from .helpers import PROJECT_ROOT, detail, die, fail, item, line, ok, step

SMOKE_EXECUTES = True

BASE_BRANCH = "develop"
RELEASE_BRANCH = "main"

#: A check conclusion (or a status context's state) that is not a pass.
FAILED = frozenset({"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE", "STALE"})
#: `mergeStateStatus` values GitHub merges as they stand.
MERGEABLE = frozenset({"CLEAN", "HAS_HOOKS"})
#: Values no amount of waiting changes: the branch needs work first.
STUCK = {"BEHIND": "the base branch has moved past it", "DIRTY": "it conflicts with the base branch"}
#: Seconds between reads. A module value so a test can make it zero.
POLL = 15.0


def run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(argv), cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=False)


def gh_json(*args: str) -> Any:
    """`gh <args>` parsed, or None when it failed or printed something that is not JSON."""
    done = run("gh", *args)
    try:
        return json.loads(done.stdout) if done.returncode == 0 else None
    except ValueError:
        return None


def wait(poll: Callable[[], Any], timeout: float, sleep: Callable[[float], None] = time.sleep) -> Any:
    """`poll()` until it returns something other than None, or None once `timeout` seconds pass."""
    deadline = time.monotonic() + timeout
    while True:
        found = poll()
        if found is not None or time.monotonic() >= deadline:
            return found
        sleep(POLL)


def _upper(check: dict, key: str) -> str:
    """`gh run list` spells states in lowercase and `statusCheckRollup` in uppercase."""
    return str(check.get(key) or "").upper()


def _pending(check: dict) -> bool:
    return (_upper(check, "status") or "COMPLETED") != "COMPLETED" or _upper(check, "state") in ("PENDING", "EXPECTED")


def _name(check: dict) -> str:
    return check.get("name") or check.get("context") or check.get("workflowName") or "?"


def settled(checks: list[dict], previous: list | None) -> tuple[list, bool]:
    """`(signature, done)`: done once every check has finished and the set matches the last read."""
    signature = sorted((_name(c), str(c.get("detailsUrl") or c.get("targetUrl") or c.get("url") or "")) for c in checks)
    done = bool(checks) and not any(_pending(c) for c in checks) and signature == previous
    return signature, done


def failed(checks: list[dict]) -> list[str]:
    return sorted(_name(c) for c in checks if (_upper(c, "conclusion") or _upper(c, "state")) in FAILED)


def read_pull(number: str, sha: str, timeout: float) -> tuple[dict | None, str]:
    """The pull request once its checks on `sha` have settled and GitHub has a merge state; why not, else."""
    seen: dict = {"signature": None, "why": "its checks never registered on the head commit"}

    def poll():
        pull = gh_json("pr", "view", number, "--json", "headRefOid,mergeStateStatus,statusCheckRollup,state")
        if not isinstance(pull, dict) or pull.get("headRefOid") != sha:
            seen["why"] = "GitHub never showed the pushed commit as the pull request's head"
            return None
        checks = pull.get("statusCheckRollup") or []
        seen["signature"], done = settled(checks, seen["signature"])
        if not done:
            seen["why"] = "its checks were still running" if checks else seen["why"]
            return None
        state = pull.get("mergeStateStatus")
        if failed(checks) or state in MERGEABLE or state in STUCK:
            return pull
        seen["why"] = f"GitHub read it {state}: a required review, or a required check that never reported"
        return None

    return wait(poll, timeout), seen["why"]


def watch_push_runs(sha: str, timeout: float) -> tuple[list[dict] | None, str]:
    """The base branch's push runs on `sha` once they have finished and stopped changing."""
    seen: dict = {"signature": None}

    def poll():
        runs = gh_json("run", "list", "--commit", sha, "--event", "push", "--json", "name,status,conclusion,url")
        if not isinstance(runs, list):
            return None
        seen["signature"], done = settled(runs, seen["signature"])
        return runs if done else None

    found = wait(poll, timeout)
    return found, "" if found is not None else f"no push run on {sha[:12]} finished in time"


def open_pull(branch: str, base: str) -> tuple[str, str]:
    """`(number, url)` of the open pull request for `branch`, opened as a draft and marked ready."""
    pull = gh_json("pr", "view", branch, "--json", "number,url,state,isDraft")
    if not isinstance(pull, dict) or pull.get("state") != "OPEN":
        created = run("gh", "pr", "create", "--draft", "--base", base, "--head", branch, "--fill")
        if created.returncode != 0:
            die(f"gh pr create failed: {created.stderr.strip()[-300:]}")
        pull = gh_json("pr", "view", branch, "--json", "number,url,state,isDraft")
        if not isinstance(pull, dict):
            die("the pull request was created and gh cannot read it back")
    number = str(pull["number"])
    if pull.get("isDraft"):
        readied = run("gh", "pr", "ready", number)
        if readied.returncode != 0:
            die(f"gh pr ready {number} failed: {readied.stderr.strip()[-300:]}")
    return number, pull.get("url") or f"#{number}"


def red(headline: str, names: list[str]) -> None:
    """`fail` with one item per name, then stop red."""
    fail(headline)
    for name in names:
        item(name)
    raise SystemExit(EXIT_RED)


def gate(ctx: click.Context, base: str) -> str:
    """The branch to land, once it is a topic branch, clean, and green under `check pre-push`."""
    branch = run("git", "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch in ("HEAD", "", base, RELEASE_BRANCH):
        die(f"on {branch or 'no branch'}: land a topic branch, not {base} or {RELEASE_BRANCH}", EXIT_REFUSED)
    if run("git", "status", "--porcelain").stdout.strip():
        die("the working tree has changes: pre-push checks the tree and a push sends commits", EXIT_REFUSED)
    step("check pre-push")
    try:
        ctx.invoke(pre_push, quick=False)
    except SystemExit as stop:
        if stop.code:
            die("check pre-push is red, so nothing was pushed", EXIT_RED)
    return branch


def merge_and_watch(number: str, command: str, base: str, timeout: int) -> None:
    """Run the pinned merge, then wait for the base branch's push runs on the merge commit."""
    merged = run(*command.split())
    if merged.returncode != 0:
        die(f"{command} failed: {merged.stderr.strip()[-300:]}")
    after = gh_json("pr", "view", number, "--json", "state,mergeCommit")
    merge_sha = ((after or {}).get("mergeCommit") or {}).get("oid") if isinstance(after, dict) else None
    if not merge_sha:
        die(f"#{number} was merged and gh does not name its merge commit, so no push run was watched")
    step(f"#{number} merged as {merge_sha[:12]}: waiting for {base}'s push runs on it")
    runs, why = watch_push_runs(merge_sha, timeout * 60)
    if runs is None:
        die(f"#{number} is merged and {why}")
    broken = failed(runs)
    if broken:
        red(f"#{number} is merged and {len(broken)} push run(s) on {merge_sha[:12]} did not pass", broken)
    ok(f"#{number} merged as {merge_sha}, and {len(runs)} push run(s) on it passed")


@click.group()
def pr() -> None:
    """Land a branch through a pull request."""


@pr.command()
@click.option("--base", default=BASE_BRANCH, show_default=True, help="the branch the pull request merges into")
@click.option("--merge", "merging", is_flag=True, help="merge once it is ready, then watch the base branch's push runs")
@click.option("--timeout", default=45, show_default=True, help="minutes to wait for each set of checks")
@click.pass_context
def land(ctx: click.Context, base: str, merging: bool, timeout: int) -> None:
    """Gate, push, open the pull request, wait for its checks, and print the pinned merge."""
    branch = gate(ctx, base)
    sha = run("git", "rev-parse", "HEAD").stdout.strip()
    pushed = run("git", "push", "-u", "origin", branch)
    if pushed.returncode != 0:
        die(f"git push refused: {pushed.stderr.strip()[-300:]}")
    number, url = open_pull(branch, base)
    step(f"{url}: waiting for its checks on {sha[:12]}")

    pull, why = read_pull(number, sha, timeout * 60)
    if pull is None:
        die(f"#{number} is not ready after {timeout} minutes: {why}")
    broken = failed(pull.get("statusCheckRollup") or [])
    if broken:
        red(f"#{number}: {len(broken)} check(s) on {sha[:12]} did not pass", broken)
    state = pull["mergeStateStatus"]
    if state in STUCK:
        die(f"#{number} cannot merge: {STUCK[state]} ({state})")

    command = f"gh pr merge {number} --merge --match-head-commit {sha}"
    if merging:
        merge_and_watch(number, command, base, timeout)
        return
    ok(f"#{number} is ready to merge: every check on {sha[:12]} passed and GitHub reads it {state}")
    detail("Merge it pinned to the commit that was checked, or rerun with --merge:")
    line(command)
