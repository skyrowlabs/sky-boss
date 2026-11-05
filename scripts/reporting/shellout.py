"""Shell out without letting an absent tool crash the job.

Every caller here already branches on `returncode`: a collector returns `""`, a
check reports the tool as unavailable. That branch is unreachable when the binary
is missing, because `subprocess.run` raises `FileNotFoundError` before any
`returncode` exists — and cron's `PATH` is exactly where a tool goes missing.

So the failure is translated into what callers already read: a non-zero result,
with the shell's own codes. `tests/test_reporting_shellout.py` requires every
subprocess call in the reporting code to come through here or handle the
exception itself, over a discovered population, so a job added later is covered.

Ported from jam.sense (`jam-sense@982042d7e`), where 20 of 64 call sites had it.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

#: "command not found", as a POSIX shell reports it.
MISSING = 127

#: "found but not executable", as a POSIX shell reports it.
CANNOT_EXECUTE = 126

#: What `timeout(1)` returns for a command it killed.
TIMED_OUT = 124


def run(argv: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """`subprocess.run`, except a missing or unrunnable tool, or a hang, is a result.

    The synthesized results carry `""` rather than `None` on both streams, so a
    caller's error branch can read them whether or not it asked to capture.

    A `cwd` that is missing or cannot be entered raises the same exceptions and is
    re-raised: it is the caller's bug, not the tool's, and naming the tool would
    misdirect whoever reads the result (proto.pilot, twice).
    """
    argv = list(argv)
    cwd = kwargs.get("cwd")
    try:
        return subprocess.run(argv, **kwargs)
    except (FileNotFoundError, PermissionError) as exc:
        if cwd is not None and not (Path(cwd).is_dir() and os.access(cwd, os.X_OK)):
            raise
        if isinstance(exc, PermissionError):
            return subprocess.CompletedProcess(argv, CANNOT_EXECUTE, "", f"{argv[0]}: not executable")
        return subprocess.CompletedProcess(argv, MISSING, "", f"{argv[0]}: not on PATH")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, TIMED_OUT, "", f"timed out after {kwargs.get('timeout')}s")
