"""Temp directories a killed run does not leave behind.

An agent's Bash timeout ends a run with SIGTERM, which skips every `finally`, and
a RAM-backed /tmp then holds the run's tree until reboot (jam-sense, 2026-11-10).
Two halves, because SIGKILL runs no handler at all:

* `exit_on_signal` turns SIGTERM and SIGHUP into `SystemExit`, so the caller's
  own `finally` removes what it made.
* `owned_tempdir` records the creating pid inside the directory, and
  `sweep_dead` removes a directory whose recorded owner is gone. One with no
  readable owner, or a live one, is never touched, so a common prefix is safe.

skeletor's own tools carry the same mechanism in `bin/tempdirs.py`; a tree
cannot import that, so this is the tree's copy.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any

OWNER_FILE = ".skeletor-owner-pid"
#: An owner file that is missing or does not hold a pid.
_UNREADABLE = (OSError, ValueError)


def exit_on_signal() -> None:
    """SIGTERM and SIGHUP raise `SystemExit(128 + signum)`, so `finally` blocks run."""

    def stop(signum: int, _frame: Any) -> None:
        raise SystemExit(128 + signum)

    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, stop)


def alive(pid: int) -> bool:
    """Whether `pid` names a running process; a process we may not signal is alive."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def owned_tempdir(prefix: str) -> Path:
    """`tempfile.mkdtemp`, with this process recorded as the owner."""
    made = Path(tempfile.mkdtemp(prefix=prefix))
    (made / OWNER_FILE).write_text(f"{os.getpid()}\n", encoding="utf-8")
    return made


def sweep_dead(prefix: str, root: Path | None = None, prune: Path | None = None) -> list[Path]:
    """Remove `<root>/<prefix>*` directories whose recorded owner is dead; return them.

    `prune` names a repository whose worktrees lived in those directories, and
    gets `git worktree prune` once anything is removed.
    """
    removed = []
    for candidate in sorted(Path(root or tempfile.gettempdir()).glob(f"{prefix}*")):
        try:
            pid = int((candidate / OWNER_FILE).read_text(encoding="utf-8").strip())
        except _UNREADABLE:
            continue
        if pid != os.getpid() and not alive(pid):
            shutil.rmtree(candidate, ignore_errors=True)
            removed.append(candidate)
    if removed and prune is not None:
        subprocess.run(["git", "-C", str(prune), "worktree", "prune"], capture_output=True)
    return removed
