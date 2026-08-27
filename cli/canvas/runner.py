"""Run one sb command and return its envelope. Out of process, on purpose.

The feature doc's Phase 1 said to lift `cli/tui/dispatch.py` and run commands
in-process. That was right for a terminal surface and is wrong for this one,
for a reason the TUI already taught at some cost: **a thread cannot be
cancelled.** The TUI could survive that because a dispatch was something you
had just typed and were watching. Here a watcher fires unattended every few
seconds, and a command that hangs — `jam pr list` does a `git fetch` and talks
to GitHub — would strand its thread forever. Six windows on a bad network and
the server accumulates stuck threads until it dies. That is the shape of the
300-second thread-join bug, rebuilt on a new substrate.

A subprocess is killable, so `--timeout` is a real guarantee rather than a
hope. It also isolates a crash, and it costs one interpreter start per run,
which against a network round-trip is noise.

**We get the envelope for free.** `sb --json` already prints exactly the
envelope `emit` built, which is the whole reason the output contract exists.
Nothing here parses human output.

Introspection stayed in-process (`cli/canvas/catalog.py`) because reading the
tree runs nothing. Reads in, execution out.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from cli.helpers import PROJECT_ROOT, child_env

# The wrapper, not `python -m cli`. It resolves its own symlink, prefers the
# venv and sets PYTHONSAFEPATH — all things this would otherwise have to
# reproduce, and one of which has already caused a silent bug once.
# See CLAUDE.md § CLI setup.
SB = PROJECT_ROOT / "sb"

# A default ceiling so a watcher can never wedge on a command with no opinion
# about how long it should take.
DEFAULT_TIMEOUT = 60


@dataclass
class Run:
    """One execution: the envelope sb produced, and how the process ended."""

    argv: list[str]
    exit_code: int
    duration_s: float
    envelope: dict | None = None
    error: str | None = None
    stderr: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None and self.exit_code == 0

    def to_dict(self) -> dict:
        return {
            "argv": self.argv,
            "exit_code": self.exit_code,
            "duration_s": self.duration_s,
            "envelope": self.envelope,
            "error": self.error,
            "stderr": self.stderr,
            "ok": self.ok,
        }


def run(
    argv: list[str],
    *,
    timeout: int | None = DEFAULT_TIMEOUT,
    sb: Path | None = None,
) -> Run:
    """Run `sb --json <argv>` and return what came back. Never raises.

    Never raising is load-bearing rather than defensive: this is called from a
    watcher on a timer, and an exception escaping would take out a scheduler
    that is also driving five other windows.
    """
    started = time.monotonic()
    binary = str(sb or SB)

    try:
        proc = subprocess.run(
            [binary, "--json", *argv],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            # Scrubbed even though this spawns `sb` itself: the wrapper sets
            # both variables again on the way in, and it *appends* to any
            # inherited PYTHONPATH, so without this a nested run accumulates
            # the repo path twice. A command's environment is then identical
            # whether it was reached from a terminal or from a watcher.
            env=child_env(),
        )
    except subprocess.TimeoutExpired:
        return Run(
            argv=argv,
            exit_code=-1,
            duration_s=round(time.monotonic() - started, 3),
            error=f"timed out after {timeout}s",
        )
    except OSError as exc:
        return Run(
            argv=argv,
            exit_code=-1,
            duration_s=round(time.monotonic() - started, 3),
            error=f"could not start sb: {exc}",
        )

    duration = round(time.monotonic() - started, 3)

    # Click's own exit code for a usage error. sb never uses 2 — which is
    # exactly why `partial` was given 3 — so seeing it here means the argv was
    # malformed and there is no envelope to find. Say so rather than reporting
    # "no JSON on stdout", which describes the symptom and not the cause.
    if proc.returncode == 2:
        return Run(
            argv=argv,
            exit_code=2,
            duration_s=duration,
            error=_first_line(proc.stderr) or "usage error",
            stderr=proc.stderr,
        )

    envelope = None
    error = None
    if proc.stdout.strip():
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError:
            # stdout under --json is guaranteed clean JSON by the output
            # contract, so this is a broken command rather than a broken parse.
            error = "command wrote non-JSON to stdout under --json"
    elif proc.returncode != 0:
        error = _first_line(proc.stderr) or f"exited {proc.returncode} with no output"

    return Run(
        argv=argv,
        exit_code=proc.returncode,
        duration_s=duration,
        envelope=envelope,
        error=error,
        stderr=proc.stderr,
        warnings=list((envelope or {}).get("warnings") or []),
    )


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""
