"""tb run — the only door that writes.

Runs an argv and reports what happened. That is the whole of it for now: the
declarative job layer, its lanes and its ledger were removed on 2026-08-20 to
start the design over, and this is the seam they will grow back through if they
do.

**Output is carried in the envelope here, and only here.** The general rule is
that raw command output must never reach `data` — a probe the CLI chose to run
can print a token, and `data` reaches stdout and MCP. That rule is about output
nobody asked for. This command exists to run the argv you named and show you
what it printed, so carrying it is the feature rather than a leak. Any command
that shells out *on its own initiative* still keeps its output out of `data`.
"""

from __future__ import annotations

import shlex
import subprocess
import time

import rich_click as click

from cli.output import Result, emit


@click.command()
@click.argument("argv", nargs=-1, required=True)
@click.option("--timeout", type=int, default=None, help="Give up after this many seconds.")
@click.option("--cwd", type=click.Path(file_okay=False, exists=True), help="Run it here.")
@emit
def run(argv: tuple[str, ...], timeout: int | None, cwd: str | None) -> Result:
    """Run a command and report what it printed.

    Use `--` before any argv that has its own flags:

        tb run -- ls -la
    """
    result = Result()
    started = time.monotonic()

    try:
        proc = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False
        )
    except FileNotFoundError:
        result.ok = False
        result.data = {"argv": list(argv), "error": f"no such command: {argv[0]}"}
        return result
    except subprocess.TimeoutExpired:
        result.ok = False
        result.data = {
            "argv": list(argv),
            "error": f"timed out after {timeout}s",
            "duration_s": round(time.monotonic() - started, 2),
        }
        return result

    result.data = {
        "argv": list(argv),
        "command": shlex.join(argv),
        "exit_code": proc.returncode,
        "duration_s": round(time.monotonic() - started, 2),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    result.ok = proc.returncode == 0
    if proc.stderr.strip() and result.ok:
        result.warn("wrote to stderr")

    return result
