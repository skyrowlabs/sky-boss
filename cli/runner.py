"""Command transport for fleet sections.

Sections are written against a :class:`Runner`, never against ``subprocess``
directly. That is the whole point: a section that shells out on its own is
silently local-only, and the remote path would never exercise it.

``LocalRunner`` executes here; a future ``SshRunner`` executes over the tailnet
with the same interface, so no section changes.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

DEFAULT_TIMEOUT = 10


@dataclass(frozen=True)
class RunResult:
    """Outcome of one command or file read.

    Deliberately carries no stderr. Section data reaches stdout and MCP, and the
    surest way to never leak a tool's error output into the envelope is to never
    hand it to the caller. A failed probe is simply ``ok=False``.
    """

    ok: bool
    out: str = ""

    @property
    def text(self) -> str:
        return self.out.strip()

    def lines(self) -> list[str]:
        return [line for line in self.out.splitlines() if line.strip()]


@runtime_checkable
class Runner(Protocol):
    """Executes commands and reads files somewhere — locally or on a host."""

    host: str

    def run(self, args: list[str], timeout: int = DEFAULT_TIMEOUT) -> RunResult: ...

    def read(self, path: str) -> RunResult: ...

    def env(self, name: str) -> RunResult: ...


class LocalRunner:
    """Runs on this machine."""

    def __init__(self, host: str = "localhost") -> None:
        self.host = host

    def run(self, args: list[str], timeout: int = DEFAULT_TIMEOUT) -> RunResult:
        try:
            proc = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            # Missing binary or a probe that hung. Either way the caller only
            # needs to know it has no answer.
            return RunResult(False)
        return RunResult(proc.returncode == 0, proc.stdout)

    def read(self, path: str) -> RunResult:
        try:
            return RunResult(True, Path(path).read_text())
        except OSError:
            return RunResult(False)

    def env(self, name: str) -> RunResult:
        value = os.environ.get(name)
        return RunResult(value is not None, value or "")
