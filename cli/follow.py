"""tb follow — hold a stream open. One verb, two mechanisms. See [[follow]].

**The dispatch rule is argument shape, and there is no third shape.** A
single argument that names a file — or that could only be a file — is the
file form, whose mechanism is the native cursor ([[file-follow]]): tb can
*stat* a file, so quiet and dead get different words. Everything else is the
process form (this module): spawn it, read lines as they arrive, and treat
exit as an event to display rather than a result to wait for. The name is
the one Unix already taught — `-f` is `--follow` in tail, journalctl, docker
and kubectl alike.

**Choosing `follow` asserts the process is expected not to exit.** That is
the one thing a flag cannot fake. Any exit — zero included — flips the
display to a plainly visible dead state carrying the code and the time;
restart is the operator's act, never the surface's initiative.

**Resident by nature.** No `--refresh` here ([[refresh]] owns that flag, on
snapshot reads only), no envelope under `--json` — a stream has no single
envelope, and the canvas API is the machine path. Ctrl-C leaves, and for a
process, kills.
"""

from __future__ import annotations

import shlex
import shutil
import time
from pathlib import Path
from typing import Callable

import rich_click as click
from rich.console import Console, Group
from rich.text import Text

from cli import chrome as chrome_
from cli.output import THEME
from cli.read import strip_ansi
from cli.stream import DEFAULT_LINES, ChildStream


def is_file_form(argv: tuple[str, ...]) -> bool:
    """One argument, and it is a path rather than a command.

    A path is anything with a separator in it, anything that exists as a
    file, or a bare word that no executable answers to — the last case is
    what makes `tb follow new.log` legal before the log's first write, which
    [[file-follow]] requires. The ambiguity left is a bare word that is both
    an executable and a file in the cwd; the executable wins, and the
    operator writes `./name` to mean the file, exactly as a shell would.
    """
    if len(argv) != 1:
        return False
    target = argv[0]
    if "/" in target:
        return True
    if shutil.which(target):
        return False
    return True


@click.command(name="follow")
@click.argument("argv", nargs=-1, required=True)
@click.option("--cwd", type=click.Path(file_okay=False, exists=True), help="Run it here.")
@click.option(
    "--lines",
    type=click.IntRange(min=1),
    default=DEFAULT_LINES,
    show_default=True,
    help="How many lines the window keeps.",
)
def follow(argv: tuple[str, ...], cwd: str | None, lines: int) -> None:
    """Follow a command that streams, or a file that grows. An observe,
    resident by nature — Ctrl-C leaves, and for a command, kills it.

        tb follow -- journalctl -f

        tb follow tmp/reporting/cron.log

    One argument that names a path is the file form; anything else is a
    command. Any exit — zero included — shows as a plainly visible dead
    state; restarting is yours. Lines are kept in a bounded ring; the file
    or the scrollback remains the record.
    """
    ctx = click.get_current_context()
    if (ctx.find_root().obj or {}).get("as_json"):
        # A stream has no single envelope to emit. The canvas API is the
        # machine path; --json here would be a promise nothing can keep.
        raise click.UsageError("follow is resident and emits no envelope — --json has no meaning here")

    if is_file_form(argv):
        # The native cursor, [[file-follow]] — built in its own round.
        raise click.UsageError(
            f"{argv[0]!r} is a file, and the file form lands with [[file-follow]] — "
            "for now: tb follow -- tail -F " + shlex.quote(argv[0])
        )
    else:
        follow_process(list(argv), cwd=cwd, limit=lines)


# Read by the catalog the way `tb_surface` and `tb_acts` are: a property on
# the command object, never a name in a list. Resident means no cadence —
# a follow re-running on a timer is a contradiction, not a feature.
follow.tb_resident = True


def follow_process(
    argv: list[str],
    *,
    cwd: str | None = None,
    limit: int = DEFAULT_LINES,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    console: Console | None = None,
    screen: bool = True,
    ticks: int | None = None,
    spawn=ChildStream,
) -> None:
    """The process form's whole rendering: ring, chrome bands, dead state.

    The same alternate-screen residency `--refresh` uses, drawing a ring
    instead of re-running a snapshot. The dead state keeps drawing until
    Ctrl-C — a corpse on screen is information, and clearing it would be the
    surface deciding the operator had seen enough.
    """
    out = console or Console(theme=THEME, highlight=False)
    source = shlex.join(argv)

    try:
        child = spawn(argv, cwd=cwd, limit=limit)
    except FileNotFoundError:
        raise click.UsageError(f"no such command: {argv[0]}")

    exited_at: float | None = None

    def draw() -> None:
        nonlocal exited_at
        code = child.exit_code
        if code is not None and exited_at is None:
            exited_at = clock()
        kept = child.lines()
        facts = chrome_.stream(
            source,
            last_line_at=child.last_line_at,
            exit_code=code,
            exited_at=exited_at,
            ring_shown=len(kept),
            ring_limit=limit,
        )
        top, bottom = chrome_.status_lines(facts, clock(), out.width)
        style = chrome_.ROLE[facts.attention]
        body = Text()
        for line in kept:
            # stderr joins the stream, tagged rather than merged blind — the
            # tag is one style today and a Rule's tint tomorrow.
            body.append(strip_ansi(line.text) + "\n", style="tb.warn" if line.stderr else None)
        out.clear()
        out.print(Group(Text(top, style=style), body, Text(bottom, style=style)))

    count = 0
    try:
        if screen:
            with out.screen():
                while ticks is None or count < ticks:
                    draw()
                    sleep(1)
                    count += 1
        else:
            while ticks is None or count < ticks:
                draw()
                sleep(1)
                count += 1
    except KeyboardInterrupt:
        pass
    finally:
        # Streams die with their window. The terminal's window is the loop.
        child.kill()
