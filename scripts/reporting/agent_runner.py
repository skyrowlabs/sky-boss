"""Run a headless agent over collected data, and hold the rails around it.

Each job is two stages, and keeping them separate is the whole design:

* **Collection** is deterministic Python with no dependencies. It gathers facts.
  It is cheap, it is testable, and it produces the same answer twice.
* **Triage** is a headless agent that reads those facts, makes the calls a
  script cannot, and writes a report.

A job that skips the collection stage and asks an agent to go and look produces
a different answer every night, and none of them are reproducible.

The rails here exist because each was once absent:

* **A job that cannot read its tree does not guess.** It declines, records why,
  and still pings its heartbeat — an executed-and-declined job must stay
  distinguishable from a dead cron.
* **The prompt is a file, named after the module.** That is how the fix policy
  is resolved, and it means a prompt change is a reviewable diff.
* **`fix_policy` is passed to the agent explicitly.** An agent that does not
  know its blast radius will pick one.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.lanes import SOURCE_ENV  # noqa: E402
from scripts.output import line, skip, step  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402
from scripts.reporting import run_ledger, shellout  # noqa: E402
from scripts.reporting.jobs import FIX_POLICIES, JOBS_BY_KEY  # noqa: E402

PROMPTS = Path(__file__).resolve().parent / "prompts"


#: How long an agent may run before it is killed. A job that hangs holds the
#: tree, and the next job in the grid then runs against a tree somebody else is
#: mid-write in — so the timeout protects the schedule, not just this job.
AGENT_TIMEOUT_S = 900

#: The headless agent, as an argv template. `{prompt}` is replaced with the
#: whole prompt; the argv is executed directly, never through a shell.
#:
#: One invocation, and it is the tested one. Other agents run headless too —
#: `codex exec`, `cursor-agent -p`, `aider --message … --yes` — and this is
#: deliberately not a table of them, because **nothing here can test one**. An
#: adapter is only correct if it satisfies the contract below, and one that
#: quietly does not is worse than no support at all: it fails unattended, at
#: 03:15, in the one place the failure is invisible.
#: The token replaced with the prompt. Defined once and never spelled again —
#: including in the error below, where writing it literally inside an f-string
#: would double the braces and make skeletor's own renderer read it as a
#: scaffold placeholder. It refuses unknown ones, which is how this was caught.
PROMPT_TOKEN = "{prompt}"

DEFAULT_AGENT_CMD = f"claude -p {PROMPT_TOKEN} --permission-mode acceptEdits"

#: Override with a full argv template:
#:     SB_AGENT_CMD='some-agent run --yes {prompt}'
#:
#: ## The contract an adapter must satisfy
#:
#: **Exit zero if and only if the agent ran and did the work.** Not "the process
#: started", not "the model replied". `run_ledger.py` records `ok` on a zero
#: exit, and its central rail is that a job whose agent never ran must not report
#: `ok` — a collection stage that succeeded and a triage stage that never started
#: look identical from outside, and the second is a job that has quietly stopped
#: working. An agent that exits 0 after refusing the task inverts that rail, and
#: the ledger then reports health it has no evidence for.
#:
#: **It must take the whole prompt as one argument.** The prompt carries the fix
#: policy and up to 200 KB of collected data. An agent that only reads stdin, or
#: truncates a long argument, needs a wrapper script rather than an entry here.
#:
#: **It must confine itself to the fix policy in the prompt.**
#: `--permission-mode acceptEdits` is how Claude allows edits without allowing
#: everything; an adapter with no equivalent must supply one, or the blast radius
#: the prompt describes is a suggestion rather than a bound.
AGENT_CMD_VAR = "SB_AGENT_CMD"

#: Set by `dev report <key> --dry-run`. Every job then runs its deterministic
#: stage, says what its agent stage would do, and records nothing: a round can run
#: every job in every tree without spending a token or writing a ledger row.
DRY_RUN_ENV = "SB_DRY_RUN"


def dry_run() -> bool:
    return os.environ.get(DRY_RUN_ENV) == "1"


def agent_argv(prompt: str) -> list[str]:
    """The command to run, with the prompt substituted in.

    Raises rather than guessing. A template with no `{prompt}` token would run
    the agent with no instruction at all — the failure that looks most like
    success, because the process starts, exits 0, and the ledger records `ok`
    for a job that was never asked to do anything.
    """
    template = os.environ.get(AGENT_CMD_VAR) or DEFAULT_AGENT_CMD
    tokens = shlex.split(template)
    if not tokens:
        raise ValueError(f"{AGENT_CMD_VAR} is set but empty")
    if not any(PROMPT_TOKEN in token for token in tokens):
        raise ValueError(
            f"{AGENT_CMD_VAR}={template!r} has no {PROMPT_TOKEN} token — the agent "
            "would run with no instruction and still exit 0"
        )
    return [token.replace(PROMPT_TOKEN, prompt) for token in tokens]


def agent_env(job_key: str) -> dict[str, str]:
    """The agent's environment: ours, plus the job every capture it files is from.

    The capture command reads it and caps the job; the agent never types it.
    """
    return {**os.environ, SOURCE_ENV: job_key}


def heartbeat(url: str | None, status: str = "up") -> None:
    """Ping the dead-man switch.

    Pinged on `declined` as well as `ok`, on purpose. A job that executed and
    correctly chose not to answer is working; only a job that did not run at all
    should read as dead. Conflating the two means every legitimate decline pages
    somebody.
    """
    if not url:
        return
    try:
        import urllib.request

        urllib.request.urlopen(f"{url}?status={status}", timeout=10).read()
    except Exception:
        # A heartbeat that fails must never fail the job. The monitor noticing a
        # missed ping is the correct outcome here.
        pass


def current_branch() -> str | None:
    result = shellout.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(PROJECT_ROOT), capture_output=True, text=True
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def tree_is_clean() -> bool:
    return not shellout.run(
        ["git", "status", "--porcelain"], cwd=str(PROJECT_ROOT), capture_output=True, text=True
    ).stdout.strip()


def run_triage(job_key: str, collected: dict, *, base_branch: str = "develop") -> int:
    """Run one job's agent stage over already-collected data."""
    job = JOBS_BY_KEY[job_key]
    started = run_ledger.now()
    branch = current_branch() or ""

    def decline(reason: str) -> int:
        skip(f"{job.key} declined: {reason}")
        if dry_run():
            return 0
        run_ledger.record(
            run_ledger.Run(
                job=job.key,
                outcome="declined",
                started=started,
                finished=run_ledger.now(),
                branch=branch,
                agent_ran=False,
                reason=reason,
            )
        )
        # Up, not down: it executed correctly and chose not to answer.
        heartbeat(os.environ.get(job.heartbeat_var or ""), "up")
        return 0

    # ── Rails, before anything expensive ────────────────────────────────
    if branch != base_branch:
        # A job that grades whatever branch the shared tree was sitting on
        # produces a verdict about the wrong code — and the error always
        # flatters the base branch, which is the direction that ships broken.
        return decline(f"tree is on '{branch}', not '{base_branch}' — refusing to grade the wrong code")

    if job.commits and not tree_is_clean():
        # Somebody's uncommitted work is here. An unattended run that resolves
        # an anomaly by stashing or discarding it is worse than one that stops.
        return decline("the tree has uncommitted changes that belong to somebody")

    prompt_file = PROMPTS / f"{job.module}.md"
    if not prompt_file.exists():
        return decline(
            f"no prompt at {prompt_file.relative_to(PROJECT_ROOT)} — the fix policy is resolved from its name"
        )

    policy = job.fix_policy
    prompt = "\n".join(
        [
            prompt_file.read_text(encoding="utf-8"),
            "",
            "---",
            "",
            f"## Your fix policy: `{policy}` — {FIX_POLICIES[policy]}",
            "",
            "Do not exceed it. If the right fix is outside it, say so in the report and stop;",
            "an unattended change nobody authorised is worse than a finding nobody acted on.",
            "",
            "## Collected data",
            "",
            "```json",
            json.dumps(collected, indent=2, default=str)[:200_000],
            "```",
        ]
    )

    try:
        argv = agent_argv(prompt)
    except ValueError as exc:
        return decline(str(exc))
    if dry_run():
        skip(f"{job.key} (dry run, nothing recorded): would run {argv[0]} over {len(prompt)} characters of prompt")
        return 0

    head_before = _head()
    artifact_before = _artifact_hash(job)
    step(f"{job.key}: running {argv[0]} (policy: {policy})")
    try:
        result = subprocess.run(
            argv,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=AGENT_TIMEOUT_S,
            env=agent_env(job.key),
        )
    except FileNotFoundError:
        return decline(f"`{argv[0]}` is not on PATH (cron does not give you your login PATH)")
    except subprocess.TimeoutExpired:
        run_ledger.record(
            run_ledger.Run(
                job=job.key,
                outcome="failed",
                started=started,
                finished=run_ledger.now(),
                branch=branch,
                agent_ran=True,
                reason=f"agent exceeded {AGENT_TIMEOUT_S}s and was killed",
            )
        )
        heartbeat(os.environ.get(job.heartbeat_var or ""), "down")
        return 1

    agent_ran = result.returncode == 0
    head_after = _head()
    # `ok` is a claim about the artifact, not the exit code. This recorded `ok`
    # for an agent that exited 0 having written nothing, with `committed` set to
    # whatever HEAD already was, so the heartbeat said up over a report that had
    # stopped changing — measured on a fresh tree with the agent replaced by
    # `true`. HEAD and the artifact are read on both sides of the run; "wrote"
    # is one of them moving, the only thing a run can prove about itself
    # without reading its own output. A job naming no artifact has nothing to
    # prove and keeps the exit code's answer.
    wrote = head_after != head_before or _artifact_hash(job) != artifact_before
    if agent_ran and not wrote and _artifact_hash(job) is not None:
        agent_ran = False
        reason = "agent exited 0 and wrote nothing — neither HEAD nor its artifact moved"
    else:
        reason = "" if agent_ran else (result.stderr.strip()[-500:] or "agent exited non-zero")

    run_ledger.record(
        run_ledger.Run(
            job=job.key,
            outcome="ok" if agent_ran else "failed",
            started=started,
            finished=run_ledger.now(),
            branch=branch,
            agent_ran=agent_ran,
            committed=head_after if job.commits and head_after != head_before else None,
            findings=int(collected.get("finding_count", 0) or 0),
            reason=reason,
        )
    )
    heartbeat(os.environ.get(job.heartbeat_var or ""), "up" if agent_ran else "down")
    line(result.stdout[-4000:])
    return 0 if agent_ran else 1


def _head() -> str:
    return shellout.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=str(PROJECT_ROOT), capture_output=True, text=True
    ).stdout.strip()


def _artifact_hash(job) -> str | None:
    """A digest of `job.writes`, or `None` when the job names no file or it is absent."""
    if not job.writes or job.writes == "—":
        return None
    path = PROJECT_ROOT / job.writes
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()
