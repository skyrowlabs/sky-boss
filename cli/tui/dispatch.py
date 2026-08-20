"""A typed line in, rendered output out.

The TUI keeps no command table of its own. It hands the line to Click and
renders whatever `cli/output.py` wrote, so a command added next year appears
in the surface with its real help, its real usage errors and its real exit
code, with no change here.

That is the same move the taxonomy made for the MCP allowlist: a hand-kept
mirror of the command surface is a list somebody forgets to update, and driving
the real tree makes it a property instead.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

import rich_click as click
from rich.text import Text

from cli import cli, output
from cli.output import EXIT_ERROR, EXIT_OK, capture

# Click's code for a usage error, not tb's. tb never exits 2 — that collision is
# precisely why `partial` was given 3. See cli/output.py.
EXIT_USAGE = 2


@dataclass(frozen=True)
class Dispatch:
    """One line's outcome: what it printed, and how it ended."""

    line: str
    text: str
    exit_code: int
    # The envelopes the commands produced, as `--json` would have printed
    # them. Present without a second run; see cli/output.Capture.
    envelopes: tuple[dict, ...] = ()

    @property
    def ok(self) -> bool:
        return self.exit_code == EXIT_OK


def split(line: str) -> list[str]:
    """A typed line to argv, with an optional leading ``tb``.

    Typing the program name is muscle memory and refusing it would be pedantic.
    """
    args = shlex.split(line)
    if args and args[0] == "tb":
        args = args[1:]
    return args


def dispatch(
    line: str,
    *,
    root: click.Group | None = None,
    width: int = 100,
    redirect: bool = True,
    theme: object | None = None,
) -> Dispatch:
    """Run one line against the command tree. Never raises.

    ``root`` exists for tests, which need commands with known exit codes that do
    not walk the filesystem or shell out. The surface always passes the real one.
    """
    root = root or cli

    try:
        args = split(line)
    except ValueError as exc:
        # An unbalanced quote. shlex is the only thing here that can reject a
        # line before Click ever sees it.
        with capture(width=width, redirect=redirect, theme=theme) as captured:
            _complain(str(exc))
        return Dispatch(line, captured.text, EXIT_USAGE, tuple(captured.envelopes))

    if not args:
        return Dispatch(line, "", EXIT_OK)

    with capture(width=width, redirect=redirect, theme=theme) as captured:
        code = _invoke(root, args)
    return Dispatch(line, captured.text, code, tuple(captured.envelopes))


def _invoke(root: click.Group, args: list[str]) -> int:
    """Drive the real tree and turn every exit path into a code.

    ``standalone_mode=False`` is the whole trick: Click returns the exit code
    rather than calling ``sys.exit``, and raises its usage errors rather than
    printing them and killing the process.

    Every complaint goes back out through ``output.err_console``, which capture
    has swapped by the time this runs. Rendering an error any other way would
    open the second output path this feature exists to avoid.
    """
    try:
        result = root.main(args=args, prog_name="tb", standalone_mode=False, obj={})
    except click.exceptions.Exit as exc:
        # ctx.exit() — the normal ending for every @emit command.
        return int(exc.exit_code)
    except click.UsageError as exc:
        _complain(_usage_message(exc))
        return int(exc.exit_code or EXIT_USAGE)
    except click.ClickException as exc:
        _complain(exc.format_message())
        return int(exc.exit_code or EXIT_ERROR)
    except click.Abort:
        _complain("aborted")
        return EXIT_ERROR
    except SystemExit as exc:
        # Something called sys.exit directly. Honour it; do not let it out.
        return int(exc.code or EXIT_OK)
    except Exception as exc:
        # A crash must not take the surface down with it. `emit` already turns a
        # command's own exceptions into a failed envelope, so anything arriving
        # here escaped that net — show it rather than die.
        _complain(f"{type(exc).__name__}: {exc}")
        return EXIT_ERROR

    return result if isinstance(result, int) else EXIT_OK


def _usage_message(exc: click.UsageError) -> str:
    message = exc.format_message()
    if exc.ctx is not None:
        message = f"{message}\nTry '{exc.ctx.command_path} --help'."
    return message


def _complain(message: str) -> None:
    # Text() rather than markup: a message quoting an option like [foo] would
    # otherwise be eaten as a style tag.
    output._err().print(Text(message, style="tb.fail"))
