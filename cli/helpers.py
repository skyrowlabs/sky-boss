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

# Machine-written state lives OUTSIDE the repo on purpose. A gitignored
# directory inside the repo is exactly what `git clean -xdf` destroys, and this
# holds things worth keeping across one — the surface's input history, and a
# stall dump if it ever freezes. XDG state also survives a reclone or a move.
STATE_DIR = Path(os.environ.get("TB_STATE") or Path.home() / ".local" / "state" / "tb")

# What the *operator* authored, as opposed to what the machine generated.
# Separate from STATE_DIR on purpose: `rm -rf ~/.local/state/tb` is a reasonable
# thing to do to reset the surface, and it must not also delete every tool the
# operator wrote. Config rather than state, so XDG puts it under ~/.config.
#
# Outside the repo, and with no fallback path into it. Operator content used to
# live in the tree and a machine record carried a tailnet address into every
# commit, so the tool could not be published without publishing the operator.
# An absent home degrades to nothing declared rather than raising.
TB_HOME = Path(os.environ.get("TB_HOME") or Path.home() / ".config" / "tb")


# What tb's own wrapper exports so that `python -m cli` resolves against this
# repo rather than against whatever directory you are standing in. Both are
# load-bearing for tb — see CLAUDE.md § CLI setup — and neither is any business
# of a command tb spawns.
#
# `PATH` is deliberately absent. The wrapper prepends its venv's bin to it, and
# stripping that would be tb deciding which `python3` a foreign tool finds,
# which is the operator's business. Scrub what tb added to boot, nothing else.
BOOTSTRAP = ("PYTHONPATH", "PYTHONSAFEPATH")


def child_env() -> dict[str, str]:
    """The environment a spawned command should see: the operator's, not tb's.

    Without this, `tb run -- python3 -c "import cli"` imports *this* package
    from anywhere on the machine, because `subprocess` inherits the parent
    environment and tb's wrapper put the repo on `PYTHONPATH`.

    It was found by manually testing something else: `tb data -- jam …`
    succeeded from inside this repo when running `jam` directly there fails, and
    the leak was what made it work. See [[subprocess-env]].
    """
    return {k: v for k, v in os.environ.items() if k not in BOOTSTRAP}


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
        env=child_env(),
    )
