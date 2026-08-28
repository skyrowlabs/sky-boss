"""sb data — read another CLI's structured output as data.

**This is not passthrough.** `sb gh pr list` would be strictly worse than
`gh pr list`, and CLAUDE.md rejects that on sight. The carve-out it leaves is
for a tool that does something the wrapped tool cannot express, and this one
does exactly that: it turns a foreign CLI's structured output into a sb
envelope, which is what lets a window keep it fresh, sort it, and filter it.
`jam` cannot hold itself open on a canvas and re-run itself every thirty
seconds.

**The name is the contract.** This command was born `wrap`, which named the
mechanism; `data` names what it promises — parsed data or a failed contract,
never carried bytes — and the contract is the half that matters. Renamed
2026-08-21, hard, no alias; see [[refresh]].

**Why it is a separate command from `sb run`.** `run` acts — you named an argv
and sb will execute whatever it is, so it may never be given a refresh cadence,
because re-running a write on a timer is a scheduler nobody asked for. `data` is
the operator's declaration that the argv is a *read*, which is what makes it
safe to pin. sb cannot tell the difference by inspection and does not try; the
choice of command is the assertion, exactly as the mockup encoded it before any
of this existed.

**It carries no raw output.** `run` is the one command allowed to put a
subprocess's bytes into `data`, and this does not become the second. If the
wrapped tool prints something that is not JSON, that is a failed contract rather
than a payload — this says so and points at `sb run`, which exists to show you
what a command actually printed.

**`--from` names the parsing contract** — the `json` kind, or a format the
operator declared in `$SB_HOME/formats.toml`: a per-line pattern for a tool
with no `--json`, a jq program as the pipeline's middle stage, or both. The
contract does not move: parsed data or a failed contract, never carried bytes —
a capture that misses is counted and named, and one that catches nothing is a
failure, not an empty table. See [[capture]].

**It is the only command that shapes its own table.** A foreign tool's JSON has
as many fields as its author needed, not as many as a table wants, so this
attaches a `view` describing which of them to show. sb's own commands do not:
their fields were chosen deliberately and auto-dropping one would be a bug
wearing a feature's clothes. The view never edits `data`. See cli/view.py.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time

import rich_click as click

from cli import capture as capture_
from cli.helpers import child_env
from cli.output import Result, emit, refuse_resident_json
from cli.view import find_rows, shape, warnings_for


@click.command()
@click.argument("argv", nargs=-1, required=True)
@click.option("--timeout", type=int, default=60, help="Give up after this many seconds.")
@click.option("--cwd", type=click.Path(file_okay=False, exists=True), help="Run it here.")
@click.option("--cols", help="Show exactly these columns, in this order. Dotted paths allowed.")
# Where the rows are, when the payload wraps them. Named beats inferred: sb
# infers only when exactly one value is a list of rows, and reports rather than
# guesses when two are. See [[table-views]] round 4.
@click.option("--rows", "rows_path", metavar="KEY", help="Where the rows are, if the payload wraps them. Dotted paths allowed.")
@click.option("--drop", help="Hide these columns, keeping the rest of the shaping.")
@click.option("--no-shape", "no_shape", is_flag=True, help="Every column, in the order found.")
# One option whose value is a *name*, never a flag per format. It resolves to
# a kind sb ships (`json`) or to a format the operator declared in
# `$SB_HOME/formats.toml` — complexity lives in the named declaration and the
# command line only says the name. See [[capture]]. And `data` never grows its
# own `--json` — the root owns that spelling for envelope output, and one flag
# meaning two things at two levels is a confusion trap.
@click.option(
    "--from",
    "from_",
    default="json",
    show_default=True,
    metavar="NAME",
    help="How to read what the tool prints: a kind (json) or a declared format.",
)
@click.option(
    "--refresh",
    type=click.IntRange(min=1),
    default=None,
    metavar="SECONDS",
    help="Stay resident and re-run every N seconds, watch(1)-style. q, Esc or Ctrl-C to leave.",
)
@click.option(
    "--screen",
    is_flag=True,
    help="Redraw on the alternate screen instead of inline. Restores the terminal on exit.",
)
@click.option(
    "--save",
    "save",
    metavar="NAME",
    default=None,
    help="Save this invocation as a saved command called NAME, then run it.",
)
@emit
def data(
    argv: tuple[str, ...],
    timeout: int | None,
    cwd: str | None,
    cols: str | None,
    rows_path: str | None,
    drop: str | None,
    no_shape: bool,
    from_: str,
    refresh: int | None,
    screen: bool,
    save: str | None,
) -> Result:
    """Read another CLI's structured output as data. An observe — a window may
    pin it and refresh it on a cadence, and `--refresh` is the same rule in
    the terminal:

        sb data --refresh 30 -- jam pr list --json

    The tool has to be asked for JSON itself — the flag is not guessed, because
    tools spell it differently and a wrong guess is a confusing failure:

        sb data -- jam pr list --json

    Some tools resolve their own environment against the working directory
    rather than their installed location, so `--cwd` is often required even for
    a command that is on PATH.

    Rows are shaped into a table worth reading — an empty column and an opaque
    identifier are dropped, a nested dict is summarised, and anything that does
    not fit the width is named. `--cols` overrides that outright:

        sb data --cols number,title,checks.failed -- jam pr list --json

    `--from` names a parsing contract: the `json` kind, or a format declared
    in formats.toml — a per-line pattern for a tool with no `--json`, a jq
    program reshaping the parse, or both:

        sb data --from pr-summary -- jam pr list --json

    `--save` keeps a line that took three tries to get right, then runs it —
    a `--refresh` in force becomes the saved command's own cadence:

        sb data --cols number,title --save prs -- jam pr list --json
    """
    # Resolved here so a bad name is a usage error before anything runs —
    # and resolved again on every run, so a pinned window re-reads the
    # operator's edit on its next tick. See [[capture]].
    _, problem = capture_.resolve(from_)
    if problem:
        raise click.UsageError(problem)
    # Before the write, not inside the resident path. `--save` writes first on
    # purpose, so a refusal raised further down fires after the append — and
    # this one used to, leaving a tool on disk under a name that could not be
    # reused, then reporting a usage error. See [[workbench]] round 3.
    refuse_resident_json(refresh)

    # Saved *before* the run, so a resident invocation saves at all (it never
    # reaches its own exit) and a failing one still saves. You are saving an
    # argv, not a result. See [[tools]] round 3.
    saved = None
    if save:
        from cli import tools as tools_

        saved = tools_.save_invocation(save, click.get_current_context().info_name)
    if refresh is not None:
        _reside(argv, timeout, cwd, cols, rows_path, drop, no_shape, from_, refresh, screen)
    result = _once(argv, timeout, cwd, cols, rows_path, drop, no_shape, from_)
    result.saved = saved
    return result


def _reside(
    argv: tuple[str, ...],
    timeout: int | None,
    cwd: str | None,
    cols: str | None,
    rows_path: str | None,
    drop: str | None,
    no_shape: bool,
    from_: str,
    refresh: int,
    screen: bool = False,
) -> None:
    """Go resident, or refuse. Same contract as `read`'s: never returns
    normally, ends when the operator leaves, and the clean Exit skips
    `emit`'s rendering because the last frame is already on the screen."""
    from cli import resident

    ctx = click.get_current_context()
    # Belt and braces: the caller refuses this before `--save` writes, and this
    # is the guard for any future path that reaches residency another way.
    refuse_resident_json(refresh)
    source = f"{ctx.info_name} -- {shlex.join(argv)}"
    resident.reside(
        source,
        refresh,
        lambda: _once(argv, timeout, cwd, cols, rows_path, drop, no_shape, from_),
        screen=screen,
    )
    raise click.exceptions.Exit(0)


def _once(
    argv: tuple[str, ...],
    timeout: int | None,
    cwd: str | None,
    cols: str | None,
    rows_path: str | None,
    drop: str | None,
    no_shape: bool,
    from_: str = "json",
) -> Result:
    result = Result()
    started = time.monotonic()

    # Re-resolved on every run rather than closed over: the resident loop and
    # the canvas both re-enter here, and the operator editing formats.toml
    # under a pinned window is the REPL. A name that resolved at startup and
    # broke since fails this run loudly and recovers on the next.
    fmt, problem = capture_.resolve(from_)
    if problem:
        result.ok = False
        result.data = {"error": problem}
        return result

    try:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
            # The operator's environment, not sb's. See [[subprocess-env]].
            env=child_env(),
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

    return parse_text(
        proc.stdout, meta, fmt, result, cols, rows_path, drop, no_shape, timeout
    )


def parse_text(
    text: str,
    meta: dict,
    fmt,
    result: Result,
    cols: str | None,
    rows_path: str | None,
    drop: str | None,
    no_shape: bool,
    timeout: int | None = None,
) -> Result:
    """Text through a format, into a shaped envelope.

    Split out of `_once` so a source that is a *file* rather than a command
    goes through exactly this path — [[roll-call]] reads both kinds and must not
    grow a second opinion about what `--from` means or when a view is attached.
    Everything above this point in `_once` is about running a subprocess;
    everything below is about what came back, whoever produced it.
    """
    if fmt.kind == "json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            result.ok = False
            result.data = {
                **meta,
                "error": "not JSON — ask the tool for JSON, or use `sb run` to see "
                "what it printed",
            }
            return result
    else:
        # The lines kind. ANSI is stripped before matching for the same
        # reason `read` strips it: the first time a tool decides it is
        # talking to a terminal, `\x1b[32m` in the middle of a field is not
        # what the operator's pattern was written against.
        from cli.read import strip_ansi

        captured = capture_.capture(strip_ansi(text), fmt)
        if captured.matched_nothing:
            result.ok = False
            result.data = {
                **meta,
                "error": f"nothing matched {fmt.name} — fix the format, or use "
                "`sb read` to see what the tool printed",
            }
            return result
        warning = capture_.unmatched_warning(captured, fmt.name)
        if warning:
            result.warn(warning)
        parsed = captured.rows

    if fmt.jq:
        parsed, error = capture_.transform(parsed, fmt.jq, fmt.name, timeout=timeout)
        if error:
            result.ok = False
            result.data = {**meta, "error": error}
            return result

    # A list of rows becomes the data outright, so a window renders a table
    # rather than a table nested one level down under a key nobody chose.
    result.data = parsed

    requested = _split(cols)
    dropped = _split(drop)
    found = find_rows(parsed, rows_path)

    # Named and wrong must not quietly become named and ignored. `--rows` is
    # the operator asserting where the rows are; if they are not there, the
    # assertion is what is wrong and saying so is the whole point of this
    # round. An *inferred* miss is not an error — the payload simply is not a
    # table, which is how sb has always rendered it.
    if rows_path and found.rows is None:
        result.ok = False
        result.data = {**meta, "error": found.reason}
        return result

    result.view = shape(
        parsed, cols=requested, drop=dropped, enabled=not no_shape, rows_path=rows_path
    )

    # What this shaping is owed a word about. Three warnings, all decided in
    # cli/view.py rather than here — the bench asks the same question of the
    # same payload without re-running the tool ([[workbench]] round 2), and two
    # copies of "which columns went quiet" would drift the week after they were
    # written. An *inferred* miss is not an error, so the reason is passed only
    # when there was an assertion to be wrong about.
    for warning in warnings_for(
        result.view,
        reason=found.reason if found.rows is None else None,
        requested=requested,
        dropped=dropped,
    ):
        result.warn(warning)

    return result


def _split(value: str | None) -> list[str]:
    """A comma-separated option as a list. Blank entries dropped, so a trailing
    comma is a typo rather than a request for a nameless column."""
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""
