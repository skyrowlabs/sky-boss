"""`sb run` — the only door that writes.

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

from rich.console import Console
import rich_click as click

from cli.helpers import child_env, parse_duration
from cli.output import Result, band, emit
from cli.read import _width


@click.command()
@click.argument("argv", nargs=-1, required=True)
@click.option("--timeout", type=int, default=None, help="Give up after this many seconds.")
@click.option("--cwd", type=click.Path(file_okay=False, exists=True), help="Run it here.")
@click.option(
    "--delay",
    metavar="WHEN",
    default=None,
    help="Run it once, later: 5m, 90s, 2h. A countdown you can cancel; it does not survive.",
)
# Hidden, and it exists only to refuse well. [[refresh]] rules that `run` never
# takes a cadence, and without this Click answers `--refresh` with a bare usage
# error that names no reason — which teaches nothing to the person whose next
# instinct is that `--delay` is the same thing wearing a coat.
@click.option("--refresh", hidden=True, default=None)
@emit
def run(
    argv: tuple[str, ...],
    timeout: int | None,
    cwd: str | None,
    delay: str | None,
    refresh: str | None,
) -> Result:
    """Run a command and report what it printed. The only command that acts —
    it runs once, ever, and never takes a cadence, because re-running a write
    on a timer is a scheduler nobody asked for.

    Use `--` before any argv that has its own flags:

        sb run -- ls -la

    In a terminal, output shows while the command runs — a ten-minute build
    accrues instead of appearing all at once at exit. Under `--json` the
    envelope is still emitted once, complete, at exit.

    `--delay` runs it once, later, behind a countdown you can watch:

        sb run --delay 5m -- ./deploy.sh

    `q`, `Esc` or Ctrl-C cancels and nothing runs; so does closing the
    terminal. There is no queue, no state file and no unit written — **a
    command that must outlive this window wants systemd**, and sky.boss will not
    generate the unit for you. Cancelling exits non-zero, so a script can tell
    the difference between "you changed your mind" and "it ran and succeeded".
    """
    ctx = click.get_current_context()
    if refresh is not None:
        raise click.UsageError(
            "run does not take --refresh: a cadence re-runs a write forever, which is a "
            "scheduler nobody asked for. To run it once, later, use --delay."
        )

    if delay:
        try:
            seconds = parse_duration(delay)
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc
        if not _await(argv, seconds):
            # Nothing ran, and a script that could not tell would deploy on a
            # keystroke.
            raise click.exceptions.Exit(1)

    if not (ctx.find_root().obj or {}).get("as_json"):
        # A Job is a stream that ends — see [[follow]]. The envelope path
        # below is what --json and every machine consumer still get.
        return _accrued(argv, timeout, cwd)
    return _once(argv, timeout, cwd)


def _await(
    argv: tuple[str, ...],
    seconds: int,
    *,
    clock=time.time,
    console=None,
    ticks: int | None = None,
    **kw,
) -> bool:
    """Draw the countdown. True if it fired, False if the operator left.

    **Cancellation is not a flag — it is the clock.** `hold` returns when the
    operator leaves *and* when its tick budget runs out, and it does not say
    which. Rather than thread a sentinel back out of a closure, this asks the
    only question that matters afterwards: did we reach the moment. Time is
    already the source of truth, and a flag would be a second one.

    Nothing here survives the surface. Closing the terminal ends the process
    and the pending command with it, which is what keeps this a *view of a
    pending action* rather than a scheduler.
    """
    from rich.console import Group

    from cli import chrome as chrome_
    from cli import keys, resident
    from cli.output import THEME, band_text

    out = console or Console(theme=THEME, highlight=False, stderr=True)
    fires_at = clock() + seconds
    source = f"run -- {shlex.join(argv)}"

    def frame() -> Group:
        facts = chrome_.pending(source, fires_at=fires_at)
        top, bottom = chrome_.status_bands(facts, clock(), min(out.width, 100))
        return Group(band_text(top), band_text(bottom))

    # One tick a second, for the whole delay. The band is drawn on *stderr*
    # like every other band: status, not payload, so `--json` still puts one
    # envelope and nothing else on stdout when the command finally runs.
    resident.hold(
        frame,
        console=out,
        ticks=int(seconds / keys.TICK) + 1 if ticks is None else ticks,
        # The countdown's last frame says "nothing has run yet" and the thing
        # that just ran is about to print beneath it.
        transient=True,
        **kw,
    )
    return clock() >= fires_at


def envelope_for(argv, outcome, timeout: int | None) -> Result:
    """An `Outcome` onto `run`'s envelope. One place, deliberately.

    Both surfaces accrue now ([[follow]] round 4) and the canvas must not
    re-decide ok, the stderr warning or the timed-out shape beside this. Round
    2's caution — that a shared helper can be *"correct for its first caller
    and silently wrong for its second"* — is the argument for sharing **on
    purpose** rather than against sharing, exactly as `clip`'s direction was:
    one function that both callers state their case to, instead of two that
    drift.

    `data` is None on success because the lines already reached the surface, on
    the streams they arrived on. Nothing is delivered twice.
    """
    result = Result()
    if outcome.timed_out:
        result.ok = False
        result.data = {
            "argv": list(argv),
            "error": f"timed out after {timeout}s",
            "duration_s": outcome.duration_s,
        }
        return result

    result.ok = outcome.exit_code == 0
    if outcome.stderr.strip() and result.ok:
        result.warn("wrote to stderr")
    result.data = None
    return result


def _accrued(argv: tuple[str, ...], timeout: int | None, cwd: str | None) -> Result:
    """Stream the lines as they arrive; stamp the act on stderr at exit. The
    stamp is chrome, so it never says a countdown — an act is stamped once."""
    from cli import chrome as chrome_
    from cli import stream as stream_
    from cli.read import _echo_line, output_width

    try:
        outcome = stream_.accrue(
            list(argv), timeout=timeout, cwd=cwd, echo=_echo_line, columns=_width()
        )
    except FileNotFoundError:
        missing = Result()
        missing.ok = False
        missing.data = {"argv": list(argv), "error": f"no such command: {argv[0]}"}
        return missing

    result = envelope_for(argv, outcome, timeout)
    if outcome.timed_out:
        return result

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
            # The operator's environment, not sky.boss's, plus the width of the
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
