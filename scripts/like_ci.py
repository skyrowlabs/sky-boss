#!/usr/bin/env python3
"""Run `ci.yml`'s unit job on this host the way the runner runs it.

Everything is read, never written down here. The unit job is the one job that
uses `.github/actions/unit-setup` and runs `-m unit`; its interpreters are that
action's `python-version`, through the job's matrix; its installs are the
action's `run:` steps; its commands are the job's own `run:` steps after the
setup. Each runs in a venv built without system site-packages, pinned to one
CPU with `taskset`. A part this host cannot reproduce refuses (exit 2) and says
which part: a partial imitation is the defect this exists to remove.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from scripts.paths import GITHUB_DIR, PROJECT_ROOT, TMP_DIR
from scripts.rehearse_scheduled import _runner_files, _take, parse_github_env

CI = GITHUB_DIR / "workflows" / "ci.yml"
UNIT_SETUP = "./.github/actions/unit-setup"
ACTION = GITHUB_DIR / "actions" / "unit-setup" / "action.yml"
VENVS = TMP_DIR / "like-ci"
#: GitHub runs a `run:` step with `shell: bash` this way.
BASH = ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c"]
_MATRIX = re.compile(r"^\$\{\{\s*matrix\.([\w-]+)\s*\}\}$")
_REQUIREMENTS = re.compile(r"-r\s+(\S+)")


class Refused(Exception):
    """This host cannot reproduce a part of the job; the message names it."""


def _steps(holder: dict) -> list[dict]:
    return [step for step in holder.get("steps") or [] if isinstance(step, dict)]


def unit_job(workflow: dict) -> tuple[str, dict]:
    """`(name, job)` for the one job that installs through unit-setup and runs `-m unit`."""
    found = [
        (name, job)
        for name, job in (workflow.get("jobs") or {}).items()
        if any(step.get("uses") == UNIT_SETUP for step in _steps(job))
        and any("-m unit" in str(step.get("run", "")) for step in _steps(job))
    ]
    if len(found) != 1:
        raise Refused(f"{CI.name}: want one job using {UNIT_SETUP} and running -m unit, found {len(found)}")
    return found[0]


def interpreters(job: dict) -> list[str]:
    """The versions the job's unit-setup step is given, its matrix expanded."""
    setup = next(step for step in _steps(job) if step.get("uses") == UNIT_SETUP)
    given = str((setup.get("with") or {}).get("python-version", ""))
    matrix = _MATRIX.match(given.strip())
    if matrix:
        legs = ((job.get("strategy") or {}).get("matrix") or {}).get(matrix.group(1))
        if not isinstance(legs, list) or not legs:
            raise Refused(f"the unit job's matrix has no `{matrix.group(1)}` list")
        return [str(leg) for leg in legs]
    if not given or "${{" in given:
        raise Refused(f"the unit job's python-version is {given!r}, which this host cannot evaluate")
    return [given]


def _runs(steps: list[dict], what: str) -> list[str]:
    lines = [str(step["run"]) for step in steps if "run" in step]
    for line in lines:
        if "${{" in line:
            raise Refused(f"a {what} step holds an expression this host cannot evaluate: {line.strip()[:80]}")
    return lines


def install_lines(action: dict) -> list[str]:
    """The unit-setup action's `run:` steps, in order."""
    return _runs(_steps(action.get("runs") or {}), "unit-setup")


def job_lines(job: dict) -> list[str]:
    """The unit job's own `run:` steps after the unit-setup step, in order."""
    steps = _steps(job)
    after = next(i for i, step in enumerate(steps) if step.get("uses") == UNIT_SETUP) + 1
    return _runs(steps[after:], "unit job")


def job_env(job: dict) -> dict[str, str]:
    env = {str(key): str(value) for key, value in (job.get("env") or {}).items()}
    held = [key for key, value in env.items() if "${{" in value]
    if held:
        raise Refused(f"the unit job's env {', '.join(held)} holds an expression this host cannot evaluate")
    return env


def cache_key(version: str, installs: list[str], root: Path = PROJECT_ROOT) -> str:
    """A digest of the interpreter and every file the installs read."""
    digest = hashlib.sha256(version.encode())
    named = {name for line in installs for name in _REQUIREMENTS.findall(line)}
    for rel in sorted(named | {"scripts/install_project.py", "pyproject.toml"}):
        path = root / rel
        digest.update(rel.encode() + (path.read_bytes() if path.is_file() else b"absent"))
    digest.update("\n".join(installs).encode())
    return digest.hexdigest()[:12]


def system_site_packages(cfg: str) -> bool:
    """Whether a `pyvenv.cfg` lets the venv see the base interpreter's packages."""
    return any(
        line.split("=", 1)[1].strip().lower() == "true"
        for line in cfg.splitlines()
        if line.split("=", 1)[0].strip() == "include-system-site-packages" and "=" in line
    )


def find_interpreter(version: str) -> str | None:
    """`pythonX.Y` on PATH, if it really is that version."""
    found = shutil.which(f"python{version}")
    if found is None:
        return None
    said = subprocess.run([found, "--version"], capture_output=True, text=True, check=False)
    return found if (said.stdout or said.stderr).split()[-1].startswith(version) else None


def environment(venv: Path, job: dict) -> dict[str, str]:
    """This host's environment, as the runner's would differ: the venv first, no PYTHONPATH."""
    env = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")}
    env.update(job_env(job))
    env.update({"VIRTUAL_ENV": str(venv), "PATH": f"{venv / 'bin'}{os.pathsep}{env.get('PATH', '')}", "CI": "true"})
    return env


def build(python: str, version: str, installs: list[str], job: dict, root: Path = PROJECT_ROOT) -> Path:
    """The venv for `version`, built once per cache key and reused after."""
    venv = VENVS / f"{version}-{cache_key(version, installs, root)}"
    done = venv / ".installed"
    if not done.exists():
        shutil.rmtree(venv, ignore_errors=True)
        subprocess.run([python, "-m", "venv", str(venv)], check=True)
        env = environment(venv, job)
        carried: dict = {"path": [], "env": {}}
        for line in installs:
            if step(line, env, root, carried) != 0:
                raise Refused(f"an install step failed, so the venv is not CI's: {line.strip()[:80]}")
        (venv / CARRIED).write_text(json.dumps(carried), encoding="utf-8")
        done.write_text("", encoding="utf-8")
    if system_site_packages((venv / "pyvenv.cfg").read_text(encoding="utf-8")):
        raise Refused(f"{venv / 'pyvenv.cfg'} includes system site-packages, which the runner's interpreter lacks")
    return venv


def checkout(root: Path = PROJECT_ROOT, dest: Path = VENVS / "checkout") -> Path:
    """A clone of the tree with its tracked working-tree files on top, where the installs and the run happen.

    The runner installs into a fresh checkout, and an install step that writes into
    the tree, such as `python -m venv .venv`, would otherwise rebuild this one's (sky.boss).
    It is a repository because the suite asks git about itself: a plain copy under
    `tmp/` resolved to this tree, where an ignored path lists nothing (mind.head, sky.vault).
    """
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, text=True)
    if listed.returncode != 0:
        raise Refused("git could not list the tree, so there is no checkout to copy")
    shutil.rmtree(dest, ignore_errors=True)
    cloned = subprocess.run(
        ["git", "clone", "--quiet", "--local", "--no-checkout", str(root), str(dest)], capture_output=True, text=True
    )
    if cloned.returncode != 0:
        raise Refused(f"git could not clone the tree for a fresh checkout: {cloned.stderr.strip()[:120]}")
    subprocess.run(["git", "-C", str(dest), "checkout", "--quiet", "--detach", "HEAD"], check=False)
    # The runner's checkout has no origin/HEAD, and a clone's names whatever branch
    # the tree has out, which a round branch never matches (eight trees).
    unset = ["git", "-C", str(dest), "symbolic-ref", "--delete", "refs/remotes/origin/HEAD"]
    subprocess.run(unset, capture_output=True, check=False)
    for rel in filter(None, listed.stdout.split("\0")):
        source = root / rel
        if not source.exists() and not source.is_symlink():
            (dest / rel).unlink(missing_ok=True)
        elif source.is_file() or source.is_symlink():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest / rel, follow_symlinks=False)
    return dest


def one_cpu() -> int:
    """One CPU this process may use, picked by pid so two runs at once rarely share it.

    A fixed core 0 put every concurrent run on the same one: 2m against 18s (stash.flow).
    """
    allowed = sorted(os.sched_getaffinity(0))
    return allowed[os.getpid() % len(allowed)]


#: What the install steps wrote to `$GITHUB_PATH` and `$GITHUB_ENV`, kept beside the cached venv.
CARRIED = ".runner.json"


def step(line: str, env: dict[str, str], root: Path, carried: dict, pin: tuple = ()) -> int:
    """One `run:` line with a runner's step files, folding what it wrote into `carried` for later steps.

    A step that appends to `$GITHUB_PATH` failed with the variable unset (sky.boss).
    """
    scratch = VENVS / "runner"
    scratch.mkdir(parents=True, exist_ok=True)
    files = _runner_files(scratch)
    here = {**env, **carried["env"], **files}
    here["PATH"] = os.pathsep.join([*reversed(carried["path"]), here.get("PATH", "")])
    code = subprocess.run([*pin, *BASH, line], cwd=root, env=here, check=False).returncode
    carried["path"] += [line.strip() for line in _take(files["GITHUB_PATH"]).splitlines() if line.strip()]
    carried["env"].update(parse_github_env(_take(files["GITHUB_ENV"])))
    return code


def run(lines: list[str], venv: Path, job: dict, root: Path = PROJECT_ROOT) -> int:
    """Each line on one CPU, stopping at the first that fails. Its exit code, or 0."""
    env = environment(venv, job)
    saved = venv / CARRIED
    carried = json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else {"path": [], "env": {}}
    for line in lines:
        code = step(line, env, root, carried, ("taskset", "-c", str(one_cpu())))
        if code != 0:
            return code
    return 0


def plan(version: str | None) -> tuple[dict, list[str], list[str], list[str]]:
    """`(job, versions, installs, commands)` read from this tree, or `Refused` naming what is missing."""
    if shutil.which("taskset") is None:
        raise Refused("taskset is not on PATH, so the run cannot be pinned to one CPU as the runner's is")
    _, job = unit_job(yaml.safe_load(CI.read_text(encoding="utf-8")))
    legs = interpreters(job)
    if version is not None and version not in legs:
        raise Refused(f"--python {version} is not a leg of the unit job's matrix: {', '.join(legs)}")
    installs = install_lines(yaml.safe_load(ACTION.read_text(encoding="utf-8")))
    return job, [version] if version else legs, installs, job_lines(job)
