"""One engine for both capture-lane drainers: one issue, worked on a branch, as a draft PR.

`agent_task.py` and `agent_fix.py` are a lane and a binding over this, which is
jam.sense's shape (`jam-sense@6cda3ca04`, `scripts/reporting/agent_fix.py`'s
`Drain` descriptor driving `run_drain`): a second, subtly different drainer is how
a lane gets worked by rules nobody wrote down twice. Ported as a shape, not as
code: jam.sense drains a batch under a wall-clock budget, and this takes ONE
issue per run.

Deterministic first, and that ordering is the cost model. Most nights a lane is
empty, and that is found by a `gh issue list`, never by an agent:

1. The runner's rails: the tree is on the base branch, it is clean, the prompt exists.
2. The queue: open issues under the lane's label, oldest first, minus any with
   an open pull request from this drainer and any that has failed `MAX_ATTEMPTS`
   times. Unreadable is `failed`, because "I could not look" is not "empty".
   Empty is `declined`, with a ledger row and a heartbeat, and no agent.
3. A dry run (`dev report <key> --dry-run`) stops here: it names the issue it
   would take and records nothing.
4. The agent works on `agent/<lane>/<issue>` and commits there. This module
   pushes that branch and opens the draft PR, so the agent never needs to push.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.lanes import LANES_BY_KEY, source_line  # noqa: E402
from scripts.output import line, skip, step  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402
from scripts.reporting import agent_runner, run_ledger, shellout  # noqa: E402
from scripts.reporting.jobs import FIX_POLICIES, JOBS_BY_KEY  # noqa: E402

#: Attempts before an issue is left to a person. Counted from the marker this
#: module comments on every attempt, so the count lives on the issue itself.
MAX_ATTEMPTS = 3
ATTEMPT_MARKER = "<!-- drain:attempt -->"
BRANCH_PREFIX = "agent"


@dataclass(frozen=True)
class Drain:
    job_key: str
    lane_key: str


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str
    attempts: int


def _gh(*args: str):
    return shellout.run(["gh", *args], cwd=str(PROJECT_ROOT), capture_output=True, text=True)


def _git(*args: str):
    return shellout.run(["git", *args], cwd=str(PROJECT_ROOT), capture_output=True, text=True)


def branch_for(drain: Drain, number: int) -> str:
    return f"{BRANCH_PREFIX}/{drain.lane_key}/{number}"


def queue(drain: Drain) -> list[Issue] | None:
    """The lane's workable issues, oldest first, or None when GitHub could not be read."""
    label = LANES_BY_KEY[drain.lane_key].label
    listed = _gh(
        "issue",
        "list",
        "--label",
        label,
        "--state",
        "open",
        "--limit",
        "100",
        "--json",
        "number,title,body,createdAt,comments",
    )
    prs = _gh("pr", "list", "--state", "open", "--limit", "200", "--json", "headRefName")
    if listed.returncode != 0 or prs.returncode != 0:
        return None
    open_heads = {pr["headRefName"] for pr in json.loads(prs.stdout or "[]")}
    issues = []
    for raw in sorted(json.loads(listed.stdout or "[]"), key=lambda i: i.get("createdAt", "")):
        attempts = sum(ATTEMPT_MARKER in (c.get("body") or "") for c in raw.get("comments") or [])
        if branch_for(drain, raw["number"]) in open_heads or attempts >= MAX_ATTEMPTS:
            continue
        issues.append(Issue(raw["number"], raw.get("title", ""), raw.get("body") or "", attempts))
    return issues


def prompt_for(drain: Drain, issue: Issue, branch: str) -> str | None:
    job = JOBS_BY_KEY[drain.job_key]
    prompt_file = agent_runner.PROMPTS / f"{job.module}.md"
    if not prompt_file.exists():
        return None
    return "\n".join(
        [
            prompt_file.read_text(encoding="utf-8"),
            "",
            "---",
            "",
            f"## Your fix policy: `{job.fix_policy}` — {FIX_POLICIES[job.fix_policy]}",
            "",
            f"You are on branch `{branch}`. Commit your change there, with `Fixes-issue: #{issue.number}`",
            "in the message. Do not push, open a pull request or switch branches: the job does that.",
            "",
            f"## Issue #{issue.number}: {issue.title}",
            "",
            f"Earlier attempts: {issue.attempts} of {MAX_ATTEMPTS}.",
            "",
            issue.body[:50_000],
        ]
    )


def run(drain: Drain, *, base_branch: str = "develop") -> int:
    job = JOBS_BY_KEY[drain.job_key]
    started = run_ledger.now()
    branch = agent_runner.current_branch() or ""
    heartbeat_url = os.environ.get(job.heartbeat_var or "")
    dry = agent_runner.dry_run()

    spent: dict = {}

    def finish(outcome: str, reason: str = "", committed: str | None = None, ran: bool = False) -> int:
        if dry:
            skip(f"{job.key} (dry run, nothing recorded): {reason or outcome}")
            return 0
        run_ledger.record(
            run_ledger.Run(
                job=job.key,
                outcome=outcome,
                started=started,
                finished=run_ledger.now(),
                branch=branch,
                agent_ran=ran,
                committed=committed,
                reason=reason,
                **spent,
            )
        )
        agent_runner.heartbeat(heartbeat_url, "down" if outcome == "failed" else "up")
        (skip if outcome == "declined" else line)(f"{job.key} {outcome}: {reason or committed}")
        return 1 if outcome == "failed" else 0

    if branch != base_branch:
        return finish("declined", f"tree is on '{branch}', not '{base_branch}'")
    if not agent_runner.tree_is_clean():
        return finish("declined", "the tree has uncommitted changes that belong to somebody")
    issues = queue(drain)
    if issues is None:
        return finish("failed", "GitHub could not be read, so the lane's state is unknown")
    if not issues:
        return finish("declined", f"the {LANES_BY_KEY[drain.lane_key].label} lane has nothing workable")
    issue = issues[0]
    work_branch = branch_for(drain, issue.number)
    if dry:
        return finish("declined", f"would work #{issue.number} on {work_branch}: {issue.title}")
    return _work(drain, issue, finish, spent, base_branch)


def _work(drain: Drain, issue: Issue, finish, spent: dict, base_branch: str) -> int:
    """The agent's half: branch, run, comment the attempt, and open the draft PR."""
    job = JOBS_BY_KEY[drain.job_key]
    work_branch = branch_for(drain, issue.number)
    prompt = prompt_for(drain, issue, work_branch)
    if prompt is None:
        return finish("declined", f"no prompt for {job.module}; the fix policy is resolved from its name")
    try:
        argv = agent_runner.agent_argv(prompt)
        env = agent_runner.agent_env(job.key)
    except ValueError as error:  # SeatError included: an identity that cannot run
        return finish("declined", str(error))

    head_before = _git("rev-parse", "HEAD").stdout.strip()
    if _git("switch", "-c", work_branch).returncode != 0:
        return finish("failed", f"could not create {work_branch}")
    step(f"{job.key}: #{issue.number} on {work_branch}")
    ran = shellout.run(
        argv,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=agent_runner.AGENT_TIMEOUT_S,
        env=env,
    )
    spent.update(agent_runner.usage(ran.stdout))
    head_after = _git("rev-parse", "HEAD").stdout.strip()
    _gh(
        "issue",
        "comment",
        str(issue.number),
        "--body",
        f"{ATTEMPT_MARKER}\nAttempt {issue.attempts + 1} of {MAX_ATTEMPTS} by `{job.key}`; "
        f"agent exit {ran.returncode}, {'committed' if head_after != head_before else 'no commit'}.",
    )
    if not agent_runner.tree_is_clean():
        return finish("failed", f"the agent left uncommitted changes on {work_branch}; left for a person", ran=True)
    if ran.returncode != 0 or head_after == head_before:
        _git("switch", base_branch)
        _git("branch", "-D", work_branch)
        why = "made no commit" if ran.returncode == 0 else (ran.stderr.strip()[-300:] or "exited non-zero")
        return finish("failed", f"#{issue.number}: the agent {why}", ran=ran.returncode == 0)

    pushed = _git("push", "-u", "origin", work_branch)
    opened = (
        pushed.returncode == 0
        and _gh(
            "pr",
            "create",
            "--draft",
            "--base",
            base_branch,
            "--head",
            work_branch,
            "--title",
            issue.title,
            "--body",
            f"Closes #{issue.number}\n\n{source_line(job.key)}",
        ).returncode
        == 0
    )
    _git("switch", base_branch)
    if not opened:
        return finish(
            "failed",
            f"#{issue.number}: committed on {work_branch}, but the draft PR was not opened",
            committed=head_after[:7],
            ran=True,
        )
    return finish("ok", f"#{issue.number}: draft PR from {work_branch}", committed=head_after[:7], ran=True)
