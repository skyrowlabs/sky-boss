"""tb read — show what a tool printed, and keep showing it.

**The gap this fills is not display, it is cadence.** `tb run -- jam pr list`
already carries the bytes. But `run` acts, and only a read may be given a
refresh cadence, so that window can never be pinned — the only command that
carried text was the one command that must never be put on a timer.

**Why `data` is the text itself** and not an object wrapping it: both renderers
already do the right thing with a plain string. `cli/output.py` echoes it
verbatim, and `render.js` falls through to a `<pre>`. Wrapping it in a mapping
is what makes `tb run`'s output wrap and lose its alignment.

**It is the second exception to "raw output must not reach `data`", and the
rule was drawn in the wrong place.** That rule exists because a probe tb chose
to run can print a token. The property that makes an exception safe was never
run-ness — it is that the *operator named the argv*. `read` names it too.

**Choosing `read` asserts this argv is a read**, exactly as choosing `data`
over `run` does. tb cannot tell a read from a write by inspecting an argv and
does not try. See docs/features/done/text-reads.md — or rather [[text-reads]].
"""

from __future__ import annotations

import re
import shlex
import subprocess
import time

import rich_click as click

from cli.helpers import child_env
from cli.output import Result, band, emit

# A 120k-line result kills a browser tab as dead as it killed a RichLog. The
# substrate changed; the rule did not.
MAX_CHARS = 200_000

# CSI sequences. Stripped rather than interpreted: [[canvas]] rejected an
# ANSI-to-HTML fallback because rendering an ANSI table gives a *picture* of a
# table, and that argument still holds — this gives you a picture and says so.
# What it must not do is leave `\x1b[32m` sitting in the middle of a cell, which
# is what carrying the bytes untouched means the first time a tool decides it is
# talking to a terminal.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


@click.command(name="read")
@click.argument("argv", nargs=-1, required=True)
@click.option("--timeout", type=int, default=60, help="Give up after this many seconds.")
@click.option("--cwd", type=click.Path(file_okay=False, exists=True), help="Run it here.")
@click.option(
    "--refresh",
    type=click.IntRange(min=1),
    default=None,
    metavar="SECONDS",
    help="Stay resident and re-run every N seconds, watch(1)-style. Ctrl-C to leave.",
)
@emit
def read_(
    argv: tuple[str, ...], timeout: int | None, cwd: str | None, refresh: int | None
) -> Result:
    """Show what a command printed. An observe — a window may pin it and
    refresh it on a cadence, and `--refresh` is the same rule in the terminal:

        tb read --refresh 30 --cwd ~/some/repo -- sometool status

    For a tool with no `--json`. It shows the tool's own output verbatim.
    Nothing is parsed — when structure is wanted, ask the tool for JSON and
    use `tb data`.
    """
    if refresh is not None:
        _reside(argv, timeout, cwd, refresh)
    ctx = click.get_current_context()
    if not (ctx.find_root().obj or {}).get("as_json"):
        # Live accrual: output shows while the process runs, exit stamps the
        # status. A Job is a stream that ends — see [[follow]]. The envelope
        # path below is untouched; under --json it is still built complete,
        # once, at exit.
        return _accrued(argv, timeout, cwd, source=f"{ctx.info_name} -- {shlex.join(argv)}")
    return _once(argv, timeout, cwd)


def _accrued(
    argv: tuple[str, ...], timeout: int | None, cwd: str | None, source: str
) -> Result:
    """The streaming human rendering: lines as they arrive on the stream they
    arrived on, a chrome stamp on stderr at exit. stdout stays exactly the
    lines the tool printed, so a pipe sees what it always saw."""
    from cli import chrome as chrome_
    from cli import stream as stream_

    result = Result()
    try:
        outcome = stream_.accrue(list(argv), timeout=timeout, cwd=cwd, echo=_echo_line)
    except FileNotFoundError:
        result.ok = False
        result.data = f"no such command: {argv[0]}"
        return result

    if outcome.timed_out:
        result.ok = False
        result.data = f"timed out after {timeout}s"
        return result

    result.ok = outcome.exit_code == 0
    if outcome.truncated:
        result.warn("output truncated in the envelope; the terminal has all of it")
    if not result.ok:
        result.warn(f"exited {outcome.exit_code} after {outcome.duration_s}s")

    facts = chrome_.snapshot(
        source,
        ok=result.ok,
        warnings=len(result.warnings),
        ran_at=time.time(),
        duration_s=outcome.duration_s,
    )
    _, bottom = chrome_.status_lines(facts, time.time(), width=min(80, output_width()))
    band(bottom, chrome_.ROLE[facts.attention])
    # The lines already reached the terminal; the envelope is not re-rendered.
    result.data = None
    return result


def _echo_line(line) -> None:
    """stdout lines to stdout, stderr lines to stderr — tagged, never merged
    blind, per [[follow]]."""
    text = strip_ansi(line.text)
    click.echo(text, err=line.stderr)


def output_width() -> int:
    import shutil

    return shutil.get_terminal_size((100, 24)).columns


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
            env=child_env(),
        )
    except FileNotFoundError:
        result.ok = False
        result.data = f"no such command: {argv[0]}"
        return result
    except subprocess.TimeoutExpired:
        result.ok = False
        result.data = f"timed out after {timeout}s"
        return result

    # stdout is the answer; stderr is the answer when a tool wrote its output
    # there, which plenty do. Showing an empty window because the tool chose the
    # other stream would be the least helpful possible reading of "verbatim".
    text = strip_ansi(proc.stdout) or strip_ansi(proc.stderr)

    if len(text) > MAX_CHARS:
        dropped = len(text) - MAX_CHARS
        text = text[:MAX_CHARS]
        result.warn(f"{dropped} characters not shown")

    result.data = text
    result.ok = proc.returncode == 0
    if not result.ok:
        result.warn(f"exited {proc.returncode} after {round(time.monotonic() - started, 2)}s")

    return result


def _reside(argv: tuple[str, ...], timeout: int | None, cwd: str | None, refresh: int) -> None:
    """Go resident, or refuse. Never returns normally — the loop ends at
    Ctrl-C, and the clean Exit skips `emit`'s rendering because the last
    frame is already on the screen."""
    from cli import resident

    ctx = click.get_current_context()
    if (ctx.find_root().obj or {}).get("as_json"):
        # A resident redraw is a human rendering; under --json it would be an
        # endless stream of envelopes on a pipe that expects one. A machine
        # consumer that wants a cadence is what the canvas API is for.
        raise click.UsageError("--refresh and --json refuse each other")
    source = f"{ctx.info_name} -- {shlex.join(argv)}"
    resident.reside(source, refresh, lambda: _once(argv, timeout, cwd))
    raise click.exceptions.Exit(0)
