"""tb wrap — read another CLI's structured output as data.

**This is not passthrough.** `tb gh pr list` would be strictly worse than
`gh pr list`, and CLAUDE.md rejects that on sight. The carve-out it leaves is
for a tool that does something the wrapped tool cannot express, and this one
does exactly that: it turns a foreign CLI's JSON into a tb envelope, which is
what lets a window keep it fresh, sort it, and filter it. `jam` cannot hold
itself open on a canvas and re-run itself every thirty seconds.

**Why it is a separate command from `tb run`.** `run` acts — you named an argv
and tb will execute whatever it is, so it may never be given a refresh cadence,
because re-running a write on a timer is a scheduler nobody asked for. `wrap` is
the operator's declaration that the argv is a *read*, which is what makes it
safe to pin. tb cannot tell the difference by inspection and does not try; the
choice of command is the assertion, exactly as the mockup encoded it before any
of this existed.

**It carries no raw output.** `run` is the one command allowed to put a
subprocess's bytes into `data`, and this does not become the second. If the
wrapped tool prints something that is not JSON, that is a failed contract rather
than a payload — this says so and points at `tb run`, which exists to show you
what a command actually printed.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time

import rich_click as click

from cli.output import Result, emit


@click.command()
@click.argument("argv", nargs=-1, required=True)
@click.option("--timeout", type=int, default=60, help="Give up after this many seconds.")
@click.option("--cwd", type=click.Path(file_okay=False, exists=True), help="Run it here.")
@emit
def wrap(argv: tuple[str, ...], timeout: int | None, cwd: str | None) -> Result:
    """Read another CLI's JSON output as data.

    The wrapped tool has to be asked for JSON itself — the flag is not guessed,
    because tools spell it differently and a wrong guess is a confusing failure:

        tb wrap -- jam pr list --json

    Some tools resolve their own environment against the working directory
    rather than their installed location, so `--cwd` is often required even for
    a command that is on PATH.
    """
    result = Result()
    started = time.monotonic()

    try:
        proc = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False
        )
    except FileNotFoundError:
        result.ok = False
        result.data = {"error": f"no such command: {argv[0]}"}
        return result
    except subprocess.TimeoutExpired:
        result.ok = False
        result.data = {"error": f"timed out after {timeout}s"}
        return result

    meta = {
        "command": shlex.join(argv),
        "exit_code": proc.returncode,
        "duration_s": round(time.monotonic() - started, 2),
    }

    if proc.returncode != 0:
        result.ok = False
        # The first line of stderr, not the whole of stdout. A tool that failed
        # is a tool whose output should not be believed, and reporting the
        # reason is not the same as carrying the payload.
        result.data = {**meta, "error": _first_line(proc.stderr) or "exited non-zero"}
        return result

    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result.ok = False
        result.data = {
            **meta,
            "error": "not JSON — ask the tool for JSON, or use `tb run` to see "
            "what it printed",
        }
        return result

    # A list of rows becomes the data outright, so a window renders a table
    # rather than a table nested one level down under a key nobody chose.
    result.data = parsed
    if isinstance(parsed, list):
        result.warnings = []
    return result


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""
