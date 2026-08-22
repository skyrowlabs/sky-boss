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
import subprocess
import time

import rich_click as click

from cli.helpers import child_env
from cli.output import Result, emit

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
@emit
def read_(argv: tuple[str, ...], timeout: int | None, cwd: str | None) -> Result:
    """Show what a command printed, and keep showing it.

    For a tool with no `--json`. Unlike `tb run` this is declared a *read*, so a
    window may pin it and refresh it on a cadence:

        tb read --cwd ~/some/repo -- sometool status

    It shows the tool's own output verbatim. Nothing is parsed — when structure
    is wanted, ask the tool for JSON and use `tb data`.
    """
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
