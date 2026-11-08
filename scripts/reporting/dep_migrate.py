#!/usr/bin/env python3
"""`dep-migrate` — carry one held runtime-major Dependabot PR to a draft migration.

`dependabot-auto-merge.yml` merges patches, minors and dev-tool majors, and labels
a runtime major it holds `RUNTIME_MAJOR_LABEL`. This job takes the oldest such
pull request per run, so a person sees each runtime major with a migration
already drafted:

1. The rails `drain.py` keeps: base branch, clean tree, a readable queue. Empty
   is `declined` without an agent; unreadable is `failed`.
2. A branch from the Dependabot head, and the agent migrates the code there,
   bounded by `MAX_TURNS`.
3. The job runs the unit suite itself, so the verdict is not the agent's word.
   Green opens a draft PR that links the Dependabot PR, which stays open. Red
   comments the agent's notes on it and labels it `FAILED_LABEL`, and opens
   nothing. Green with no commit labels it `NOT_NEEDED_LABEL`. Either label
   takes the PR out of the queue, so a person decides what happens next.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.lanes import source_line  # noqa: E402
from scripts.output import line, skip, step  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402
from scripts.reporting import agent_runner, run_ledger, shellout  # noqa: E402
from scripts.reporting.jobs import FIX_POLICIES, JOBS_BY_KEY  # noqa: E402

JOB_KEY = "dep-migrate"
#: Written by dependabot-auto-merge.yml on a runtime major it holds.
RUNTIME_MAJOR_LABEL = "dependabot-runtime-major"
FAILED_LABEL = "migration-failed"
NOT_NEEDED_LABEL = "migration-not-needed"
BRANCH_PREFIX = "agent/migrate"
#: The tree's CLI wrapper; a constant, so no line's width depends on the CLI's name.
WRAPPER = PROJECT_ROOT / "dev"
#: Passed as `--max-turns` to the default agent; a custom command must bound itself.
MAX_TURNS = 40


def _gh(*args: str):
    return shellout.run(["gh", *args], cwd=str(PROJECT_ROOT), capture_output=True, text=True)


def _git(*args: str):
    return shellout.run(["git", *args], cwd=str(PROJECT_ROOT), capture_output=True, text=True)


def branch_for(number: int) -> str:
    return f"{BRANCH_PREFIX}/{number}"


def queue() -> list[dict] | None:
    """Held runtime majors not yet decided, oldest first; None when GitHub could not be read."""
    listed = _gh(
        "pr",
        "list",
        "--label",
        RUNTIME_MAJOR_LABEL,
        "--state",
        "open",
        "--limit",
        "100",
        "--json",
        "number,title,body,headRefName,labels,createdAt",
    )
    prs = _gh("pr", "list", "--state", "open", "--limit", "200", "--json", "headRefName")
    if listed.returncode != 0 or prs.returncode != 0:
        return None
    open_heads = {pr["headRefName"] for pr in json.loads(prs.stdout or "[]")}
    decided = {FAILED_LABEL, NOT_NEEDED_LABEL}
    return [
        pr
        for pr in sorted(json.loads(listed.stdout or "[]"), key=lambda p: p.get("createdAt", ""))
        if branch_for(pr["number"]) not in open_heads and not decided & {lab["name"] for lab in pr.get("labels") or []}
    ]


def prompt_for(pr: dict, branch: str) -> str | None:
    job = JOBS_BY_KEY[JOB_KEY]
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
            f"You are on branch `{branch}`, which is Dependabot's head for #{pr['number']}. Commit your",
            "migration there. Do not push, open a pull request or switch branches: the job does that.",
            "",
            f"## #{pr['number']}: {pr.get('title', '')}",
            "",
            (pr.get("body") or "")[:50_000],
        ]
    )


def suite() -> tuple[bool, str]:
    """The unit suite on the migrated branch, run by the job rather than reported by the agent."""
    ran = shellout.run([str(WRAPPER), "test", "unit"], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    return ran.returncode == 0, (ran.stdout + ran.stderr)[-3000:]


def run(*, base_branch: str = "develop") -> int:
    job = JOBS_BY_KEY[JOB_KEY]
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
    held = queue()
    if held is None:
        return finish("failed", "GitHub could not be read, so the held majors are unknown")
    if not held:
        return finish("declined", f"no open pull request is labelled {RUNTIME_MAJOR_LABEL} and undecided")
    pr = held[0]
    number, work_branch = pr["number"], branch_for(pr["number"])
    if dry:
        return finish("declined", f"would migrate #{number} on {work_branch}: {pr.get('title', '')}")
    return _migrate(pr, finish, spent, base_branch)


def _migrate(pr: dict, finish, spent: dict, base_branch: str) -> int:
    """The agent's half: branch, migrate, run the suite, and leave the verdict on GitHub."""
    job = JOBS_BY_KEY[JOB_KEY]
    number, work_branch = pr["number"], branch_for(pr["number"])
    prompt = prompt_for(pr, work_branch)
    if prompt is None:
        return finish("declined", f"no prompt for {job.module}")
    try:
        argv = agent_runner.agent_argv(prompt) + agent_runner.tool_grants(job.key)
        env = agent_runner.agent_env(job.key)
    except ValueError as error:  # SeatError included: an identity that cannot run
        return finish("declined", str(error))
    if not os.environ.get(agent_runner.AGENT_CMD_VAR):
        argv += ["--max-turns", str(MAX_TURNS)]

    if _git("fetch", "origin", pr["headRefName"]).returncode != 0:
        return finish("failed", f"could not fetch #{number}'s head, {pr['headRefName']}")
    if _git("switch", "-c", work_branch, "FETCH_HEAD").returncode != 0:
        return finish("failed", f"could not create {work_branch}")
    head_before = _git("rev-parse", "HEAD").stdout.strip()
    step(f"{job.key}: #{number} on {work_branch}")
    ran = shellout.run(
        argv,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=agent_runner.AGENT_TIMEOUT_S,
        env=env,
    )
    spent.update(agent_runner.usage(ran.stdout))
    notes = agent_runner.said(ran.stdout).strip()[-4000:] or "(the agent said nothing)"
    head_after = _git("rev-parse", "HEAD").stdout.strip()
    if not agent_runner.tree_is_clean():
        return finish("failed", f"the agent left uncommitted changes on {work_branch}; left for a person", ran=True)
    green, output = suite()

    def leave(label: str, comment: str) -> None:
        _gh("pr", "comment", str(number), "--body", f"{comment}\n\n{source_line(job.key)}")
        _gh("pr", "edit", str(number), "--add-label", label)
        _git("switch", base_branch)
        _git("branch", "-D", work_branch)

    if not green:
        leave(FAILED_LABEL, f"`{job.key}` could not migrate this: the suite is red.\n\n{notes}\n\n```\n{output}\n```")
        return finish("declined", f"#{number}: the suite is red after migration; labelled {FAILED_LABEL}", ran=True)
    if head_after == head_before:
        leave(NOT_NEEDED_LABEL, f"`{job.key}`: the suite is green on this head with no migration.\n\n{notes}")
        return finish("ok", f"#{number}: green with no migration; labelled {NOT_NEEDED_LABEL}", ran=True)

    pushed = _git("push", "-u", "origin", work_branch)
    body = f"Migrates the runtime major in #{number}, which stays open.\n\n{notes}\n\n{source_line(job.key)}"
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
            f"Migrate: {pr.get('title', '')}",
            "--body",
            body,
        ).returncode
        == 0
    )
    _git("switch", base_branch)
    if not opened:
        return finish("failed", f"#{number}: migrated on {work_branch}, but the draft PR was not opened", ran=True)
    return finish("ok", f"#{number}: draft migration from {work_branch}", committed=head_after[:7], ran=True)


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
