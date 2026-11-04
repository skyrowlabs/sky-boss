#!/usr/bin/env python3
"""Run each scheduled workflow's jobs here, before their first night does.

No pull request executes a scheduled job, so a defect in one is found by the
schedule, a night after the merge. sky.boss met it twice: a nightly deleted in
an upgrade, and a skip budget its nightly would have failed while pre-push
stayed green.

Each job runs in a throwaway worktree at HEAD with a clean venv.
`actions/checkout` is the worktree, `actions/setup-python` is the venv, a local
composite action is expanded, and each `run:` step runs under
`bash -eo pipefail` with the job's env. Anything else stops the job and is
reported as not rehearsed: another action, a `${{ }}` this cannot resolve, or a
condition other than `github.event_name`. A job that stopped is never reported
as passing.

Usage:  python scripts/rehearse_scheduled.py [--plan] [--workflow FILE] [--keep]
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import detail, fail, item, ok, step, warn  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"

#: The event a rehearsal stands in for, which is what `github.event_name` reads.
EVENT = "schedule"

#: Actions with a local equivalent. Every other action stops the job.
CHECKOUT = "actions/checkout"
SETUP_PYTHON = "actions/setup-python"

#: Lines of a failing step's output to show.
TAIL = 40

_EVENT_TEST = re.compile(r"^github\.event_name\s*(==|!=)\s*'([^']*)'$")
_INPUT = re.compile(r"\$\{\{\s*inputs\.([A-Za-z0-9_-]+)\s*\}\}")


@dataclass
class Step:
    """One thing a rehearsal does: `checkout`, `python`, `run`, or `stop`."""

    label: str
    kind: str
    script: str = ""
    env: dict = field(default_factory=dict)
    cwd: str = ""
    reason: str = ""


@dataclass
class Job:
    workflow: str
    id: str
    steps: list
    skipped: str = ""

    @property
    def stopped(self) -> Step | None:
        return next((s for s in self.steps if s.kind == "stop"), None)

    @property
    def runs(self) -> int:
        return sum(s.kind == "run" for s in self.steps)


def load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    # YAML 1.1 reads a bare `on` key as the boolean True.
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


def scheduled_workflows(directory: Path = WORKFLOWS) -> list:
    found = sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])
    return [p for p in found if isinstance(load(p).get("on"), dict) and "schedule" in load(p)["on"]]


def condition(expr: str) -> bool | None:
    """True or False when every term is a `github.event_name` test, else None."""
    expr = expr.strip()
    if expr.startswith("${{") and expr.endswith("}}"):
        expr = expr[3:-2].strip()
    if "||" in expr:
        return None
    verdicts = []
    for term in expr.split("&&"):
        match = _EVENT_TEST.match(term.strip())
        verdicts.append(None if not match else (match.group(2) == EVENT) == (match.group(1) == "=="))
    if False in verdicts:
        return False
    return None if None in verdicts else True


def _substitute(text: str, inputs: dict) -> str:
    return _INPUT.sub(lambda m: str(inputs.get(m.group(1), "")), text)


def _label(raw: dict) -> str:
    name = raw.get("name") or raw.get("uses") or str(raw.get("run", "")).strip().splitlines()[0]
    return str(name)


def _action_inputs(action: dict, given: dict, inputs: dict) -> dict:
    declared = action.get("inputs") or {}
    values = {name: str((spec or {}).get("default", "")) for name, spec in declared.items()}
    values.update({name: _substitute(str(value), inputs) for name, value in (given or {}).items()})
    return values


def expand(raw_steps: list, root: Path, inputs: dict | None = None) -> list:
    """The steps a rehearsal takes, ending at the first one it cannot take."""
    inputs = inputs or {}
    plan: list = []
    for raw in raw_steps or []:
        label = _label(raw)
        if "if" in raw:
            verdict = condition(str(raw["if"]))
            if verdict is False:
                continue
            if verdict is None:
                return [*plan, Step(label, "stop", reason=f"its condition `{raw['if']}` needs the runner")]
        uses = str(raw.get("uses", ""))
        if uses.startswith("./"):
            action = load(root / uses / "action.yml")
            if (action.get("runs") or {}).get("using") != "composite":
                return [*plan, Step(label, "stop", reason=f"`{uses}` is not a composite action")]
            values = _action_inputs(action, raw.get("with"), inputs)
            inner = expand(action["runs"].get("steps"), root, values)
            plan.extend(inner)
            if inner and inner[-1].kind == "stop":
                return plan
            continue
        if uses:
            kind = {CHECKOUT: "checkout", SETUP_PYTHON: "python"}.get(uses.split("@")[0])
            if not kind:
                return [*plan, Step(label, "stop", reason=f"`{uses}` is an action this cannot run here")]
            plan.append(Step(label, kind))
            continue
        script = _substitute(str(raw.get("run", "")), inputs)
        env = {k: _substitute(str(v), inputs) for k, v in (raw.get("env") or {}).items()}
        needs = [text for text in (script, *env.values()) if "${{" in text]
        if needs or raw.get("shell", "bash") != "bash":
            reason = "it needs a `${{ }}` the runner fills in" if needs else f"it runs under `{raw['shell']}`"
            return [*plan, Step(label, "stop", reason=reason)]
        plan.append(Step(label, "run", script=script, env=env, cwd=str(raw.get("working-directory", ""))))
    return plan


def plan(path: Path, root: Path = PROJECT_ROOT) -> list:
    data = load(path)
    shared = {k: str(v) for k, v in (data.get("env") or {}).items()}
    jobs = []
    for job_id, job in (data.get("jobs") or {}).items():
        env = {**shared, **{k: str(v) for k, v in (job.get("env") or {}).items()}}
        entry = Job(path.name, job_id, [])
        verdict = condition(str(job["if"])) if "if" in job else True
        unsupported = [key for key in ("strategy", "services", "container", "uses") if key in job]
        if verdict is False:
            entry.skipped = f"its condition `{job['if']}` is false on a schedule"
        elif verdict is None:
            entry.steps = [Step(job_id, "stop", reason=f"its condition `{job['if']}` needs the runner")]
        elif unsupported:
            entry.steps = [Step(job_id, "stop", reason=f"it declares `{unsupported[0]}:`")]
        elif any("${{" in value for value in env.values()):
            entry.steps = [Step(job_id, "stop", reason="its env needs a `${{ }}` the runner fills in")]
        else:
            entry.steps = expand(job.get("steps"), root)
            for s in entry.steps:
                s.env = {**env, **s.env}
        jobs.append(entry)
    return jobs


def _clean_env(venv: Path | None, work: Path) -> dict:
    """The caller's environment without this checkout's interpreter in it."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SB_")}
    for key in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"):
        env.pop(key, None)
    keep = [p for p in env.get("PATH", "").split(os.pathsep) if p and not Path(p).is_relative_to(PROJECT_ROOT)]
    if venv:
        keep.insert(0, str(venv / "bin"))
        env["VIRTUAL_ENV"] = str(venv)
    env.update({"PATH": os.pathsep.join(keep), "CI": "true", "GITHUB_WORKSPACE": str(work)})
    return env


def _show_tail(output: str) -> None:
    for text in output.rstrip().splitlines()[-TAIL:]:
        detail(text)


def rehearse(job: Job, keep: bool) -> bool:
    """Run a job's steps; True when every step it reached passed."""
    scratch = Path(tempfile.mkdtemp(prefix="rehearse-"))
    work, venv = scratch / "work", None
    work.mkdir()
    checked_out = False
    try:
        for number, s in enumerate(job.steps, 1):
            if s.kind == "stop":
                return True
            step(s.label)
            if s.kind == "checkout":
                add = ["git", "worktree", "add", "--detach", "-q", str(work), "HEAD"]
                subprocess.run(add, cwd=PROJECT_ROOT, check=True)
                checked_out = True
                continue
            if s.kind == "python":
                venv = scratch / "venv"
                subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
                continue
            body = scratch / f"step-{number}.sh"
            body.write_text(s.script, encoding="utf-8")
            done = subprocess.run(
                ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(body)],
                cwd=work / s.cwd,
                env={**_clean_env(venv, work), **s.env},
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if done.returncode:
                fail(f"{job.workflow} › {job.id}: `{s.label}` exited {done.returncode}")
                _show_tail(done.stdout)
                return False
        return True
    finally:
        if keep:
            detail(f"kept: {scratch}")
        else:
            if checked_out:
                subprocess.run(["git", "worktree", "remove", "--force", str(work)], cwd=PROJECT_ROOT, check=False)
            shutil.rmtree(scratch, ignore_errors=True)


def describe(job: Job) -> None:
    if job.skipped:
        item(f"{job.workflow} › {job.id}: does not run — {job.skipped}")
        return
    item(f"{job.workflow} › {job.id}: {job.runs} run step(s)")
    for s in job.steps:
        detail(f"{s.kind:<8} {s.label}" + (f" — not rehearsed: {s.reason}" if s.kind == "stop" else ""))


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--plan", action="store_true", help="print what would run, run nothing")
    parser.add_argument("--workflow", action="append", default=[], help="one workflow file name; repeatable")
    parser.add_argument("--keep", action="store_true", help="leave the worktree and venv behind")
    args = parser.parse_args(argv)

    paths = scheduled_workflows()
    if args.workflow:
        paths = [p for p in paths if p.name in args.workflow]
        missing = sorted(set(args.workflow) - {p.name for p in paths})
        if missing:
            fail(f"no scheduled workflow named {', '.join(missing)} in {WORKFLOWS.relative_to(PROJECT_ROOT)}")
            return 1
    jobs = [job for path in paths for job in plan(path)]
    if args.plan:
        for job in jobs:
            describe(job)
        return 0

    if subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, capture_output=True, text=True).stdout:
        warn("rehearsing HEAD — uncommitted changes are not in it")
    passed, failed, partial = [], [], []
    for job in (j for j in jobs if not j.skipped):
        if job.runs and rehearse(job, args.keep):
            (partial if job.stopped else passed).append(job)
        elif job.runs:
            failed.append(job)
        else:
            partial.append(job)
    for job in partial:
        stop = job.stopped
        reason = f"`{stop.label}`: {stop.reason}" if stop else "it has no run steps"
        warn(f"{job.workflow} › {job.id}: not rehearsed past {reason}")
    if failed:
        fail(f"{len(failed)} scheduled job(s) failed here, so they will fail on the schedule")
        return 1
    if passed:
        ok(f"{len(passed)} scheduled job(s) rehearsed green: " + ", ".join(f"{j.workflow} › {j.id}" for j in passed))
    else:
        warn("no scheduled job could be rehearsed in full, so nothing here says they pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
