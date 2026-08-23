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

from cli.helpers import child_env
from cli.output import Result, band, emit
from cli.read import _width


@click.command()
@click.argument("argv", nargs=-1, required=True)
@click.option("--timeout", type=int, default=None, help="Give up after this many seconds.")
@click.option("--cwd", type=click.Path(file_okay=False, exists=True), help="Run it here.")
@emit
def run(argv: tuple[str, ...], timeout: int | None, cwd: str | None) -> Result:
    """Run a command and report what it printed. The only command that acts —
    it runs once, ever, and never takes a cadence, because re-running a write
    on a timer is a scheduler nobody asked for.

    Use `--` before any argv that has its own flags:

        tb run -- ls -la

    In a terminal, output shows while the command runs — a ten-minute build
    accrues instead of appearing all at once at exit. Under `--json` the
    envelope is still emitted once, complete, at exit.
    """
    ctx = click.get_current_context()
    if not (ctx.find_root().obj or {}).get("as_json"):
        # A Job is a stream that ends — see [[follow]]. The envelope path
        # below is what --json and every machine consumer still get.
        return _accrued(argv, timeout, cwd)
    return _once(argv, timeout, cwd)


def _accrued(argv: tuple[str, ...], timeout: int | None, cwd: str | None) -> Result:
    """Stream the lines as they arrive; stamp the act on stderr at exit. The
    stamp is chrome, so it never says a countdown — an act is stamped once."""
    from cli import chrome as chrome_
    from cli import stream as stream_
    from cli.read import _echo_line, output_width

    result = Result()
    try:
        outcome = stream_.accrue(
            list(argv), timeout=timeout, cwd=cwd, echo=_echo_line, columns=_width()
        )
    except FileNotFoundError:
        result.ok = False
        result.data = {"argv": list(argv), "error": f"no such command: {argv[0]}"}
        return result

    if outcome.timed_out:
        result.ok = False
        result.data = {"argv": list(argv), "error": f"timed out after {timeout}s",
                       "duration_s": outcome.duration_s}
        return result

    result.ok = outcome.exit_code == 0
    if outcome.stderr.strip() and result.ok:
        result.warn("wrote to stderr")

    facts = chrome_.act(
        f"run -- {shlex.join(argv)}",
        ok=result.ok,
        warnings=len(result.warnings),
        ran_at=time.time(),
        duration_s=outcome.duration_s,
    )
    _, bottom = chrome_.status_bands(facts, time.time(), width=min(80, output_width()))
    band(bottom)
    # The lines already reached the terminal, on the streams they arrived on.
    result.data = None
    return result


def _once(argv: tuple[str, ...], timeout: int | None, cwd: str | None) -> Result:
    result = Result()
    started = time.monotonic()

    try:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
            # The operator's environment, not tb's, plus the width of the
            # display its output is headed for. See [[subprocess-env]].
            env=child_env(_width()),
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
