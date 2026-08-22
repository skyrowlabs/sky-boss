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
envelope, and the canvas API is the machine path. `q`, `Esc` and Ctrl-C all
leave, and for a process, leaving kills — the stream *is* the window, and
[[canvas]]'s rule that nothing survives the last window is the same rule.
That is the one place this differs from a resident read, which leaves a
finished process behind, and `--help` says so rather than making a reader
infer it. See [[follow]] round 2.
"""

from __future__ import annotations

import shlex
import shutil
import time
from typing import Callable

import rich_click as click
from rich.console import Console, Group

from cli import chrome as chrome_
from cli import highlight as highlight_
from cli import resident
from cli.output import THEME, band_text
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
    help="Save this invocation as a saved command called NAME, then follow it.",
)
@click.option(
    "--highlight",
    "highlight",
    metavar="NAME",
    default=None,
    help="Also tint with the patterns you declared under [highlight.NAME] in formats.toml.",
)
def follow(
    argv: tuple[str, ...],
    cwd: str | None,
    lines: int,
    screen: bool,
    save: str | None,
    highlight: str | None,
) -> None:
    """Follow a command that streams, or a file that grows. An observe,
    resident by nature:

        tb follow -- journalctl -f

        tb follow tmp/reporting/cron.log

    One argument that names a path is the file form; anything else is a
    command. Any exit — zero included — shows as a plainly visible dead
    state; restarting is yours. Lines are kept in a bounded ring; the file
    or the scrollback remains the record.

    q, Esc or Ctrl-C to leave — and leaving a command kills it, because the
    stream is the window. A file is only let go of.

    The newest lines are drawn inline below the prompt and stay there when
    you leave; `--screen` uses the alternate screen instead, which shows the
    whole ring and hands the terminal back as it was.

    `--save` keeps the line, then follows it:

        tb follow --save cron -- journalctl -f

    Timestamps, tags, numbers, dates, paths and code are tinted by shape.
    `--highlight` adds the words that matter in *your* logs, declared once
    under `[highlight.NAME]` in formats.toml:

        tb follow --highlight jam -- jam report watch --follow
    """
    ctx = click.get_current_context()
    if (ctx.find_root().obj or {}).get("as_json"):
        # A stream has no single envelope to emit. The canvas API is the
        # machine path; --json here would be a promise nothing can keep.
        raise click.UsageError("follow is resident and emits no envelope — --json has no meaning here")

    # Saved before the stream opens, which is the only order available here: a
    # follow is resident by nature and never reaches its own exit. Announced
    # on stderr rather than in an envelope, because a stream has none — see
    # [[tools]] round 3.
    if save:
        from cli import tools as tools_
        from cli.output import saved_note

        saved_note(tools_.save_invocation(save, ctx.info_name))

    # Resolved before anything opens, so a name that is not declared is a
    # usage error rather than a stream that quietly tints nothing.
    ruleset = None
    if highlight:
        ruleset, problem = highlight_.resolve(highlight)
        if problem:
            raise click.UsageError(problem)

    if is_file_form(argv):
        # The native cursor, [[file-follow]]: tb can stat a file, so quiet
        # and dead get different words.
        from cli.filefollow import follow_file

        follow_file(argv[0], limit=lines, screen=screen, ruleset=ruleset)
    else:
        follow_process(list(argv), cwd=cwd, limit=lines, screen=screen, ruleset=ruleset)


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
    wait: Callable[[float], str | None] | None = None,
    console: Console | None = None,
    screen: bool = False,
    ticks: int | None = None,
    ruleset=None,
    spawn=ChildStream,
) -> None:
    """The process form's whole rendering: ring, chrome bands, dead state.

    The same residency `--refresh` has, drawing a ring instead of re-running
    a snapshot — inline by default since round 2, so leaving leaves the tail
    of the log you were watching. The dead state keeps drawing until you go:
    a corpse on screen is information, and clearing it would be the surface
    deciding the operator had seen enough.

    **Leaving kills.** `q`, `Esc` and Ctrl-C all end the loop, and the child
    goes with it — the terminal's window is the loop.
    """
    out = console or Console(theme=THEME, highlight=False)
    source = shlex.join(argv)

    try:
        child = spawn(argv, cwd=cwd, limit=limit)
    except FileNotFoundError:
        raise click.UsageError(f"no such command: {argv[0]}")

    exited_at: float | None = None

    def frame() -> Group:
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
        top, bottom = chrome_.status_bands(facts, clock(), out.width)
        body = resident.stream_body(kept, ruleset)
        # The tail, always: a stream's interesting end is the newest line,
        # and the ring outruns the terminal on every frame. See [[follow]] r2.
        shown = body if screen else resident.clip(body, resident.room(out), tail=True)
        return Group(band_text(top), shown, band_text(bottom))

    try:
        resident.hold(frame, console=out, screen=screen, ticks=ticks, wait=wait)
    finally:
        # Streams die with their window. The terminal's window is the loop,
        # and `q` closing it is the same act Ctrl-C was.
        child.kill()
