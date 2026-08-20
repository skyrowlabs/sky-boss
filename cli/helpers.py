"""Shared plumbing for the tb CLI.

Command modules call these rather than shelling out or building paths directly.
"""

import os
import subprocess
from pathlib import Path

# tb is installed via a symlink on PATH, so the current working directory is
# never a reliable anchor — you run `tb` from wherever you happen to be. Every
# path in this CLI derives from here. See CLAUDE.md § CLI setup.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Run state lives OUTSIDE the repo on purpose. A gitignored directory inside the
# repo is exactly what `git clean -xdf` destroys, and the run ledger is durable
# history. XDG state also survives a reclone or moving the repo.
STATE_DIR = Path.home() / ".local" / "state" / "tb"

# Everything *you* author, as opposed to everything the project does. Machine
# records, job definitions, watches, and any machine-local config — one home,
# outside this repo, and expected to be a git repository of its own.
#
# It is not under ~/.config because it is not configuration; it is a worktree
# you cd into and commit in, and a system of record whose diff is the
# maintenance log. XDG's config directory is an awkward place to keep one.
#
# The split it enforces is authorship: this repo holds what the project wrote,
# TB_HOME holds what you wrote, and STATE_DIR holds what the machine wrote.
# Mixing the first two is how a tailnet address ends up in a public commit.
TB_HOME = Path(os.environ.get("TB_HOME") or Path.home() / ".tackle-box")


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int | None = 30,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Run a subprocess and return the completed process.

    Never shell=True: every caller passes an argv list, so nothing here is
    exposed to shell quoting bugs. Callers inspect returncode themselves —
    a non-zero exit is usually a degraded source to warn about, not a crash.
    """
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
        check=check,
    )
