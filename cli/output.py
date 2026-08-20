"""Output contract for the tb CLI.

Command functions return a :class:`Result`; this module owns every byte that
reaches the terminal. Three consumers read command output — a human, ``tb
brief`` merging across domains, and the MCP server — so a command that formats
its own prose has to be written three times.

See the output-contract feature doc.
"""

from __future__ import annotations

import contextlib
import functools
import io
import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any

import click
from rich.console import Console
from rich.padding import Padding
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from cli.theme import STYLES, TUI_STYLES

# Rendered in place of a missing value in a table cell.
EMPTY = "-"

# The palette lives in cli/theme.py, so that this module, rich-click's --help
# styling and the TUI's CSS cannot drift apart. Style *names* are the contract
# here; no hex is written below this line.
THEME = Theme(STYLES)

# The same roles, undarkened, for a consumer that owns its background. Command
# output rendered inside the TUI goes through capture() like everything else,
# so without this the chrome would be full strength and the output beside it
# would not — one screen, two brightnesses, for no reason the viewer can see.
TUI_THEME = Theme(TUI_STYLES)

# Two consoles, and the split matters. Rich auto-detects a TTY and drops colour
# when piped, and honours NO_COLOR, so nothing here does manual detection.
#
# The JSON path deliberately does NOT go through rich: `--json` output must stay
# byte-identical and unwrapped, and a Console would soft-wrap it to the terminal
# width. json.dumps straight to click.echo is the guarantee.
console = Console(theme=THEME, highlight=False)
err_console = Console(theme=THEME, stderr=True, highlight=False)

# Where a *thread* is currently writing. Captures used to swap the two globals
# above, which was safe while only one dispatch could ever be in flight — the
# TUI's queue guaranteed it. Watches broke that guarantee: they refresh
# concurrently with whatever is being typed, on purpose, and two overlapping
# captures silently posted each other's output into the wrong buffer. Measured,
# not theorised: of four concurrent dispatches, two captured nothing at all.
_local = threading.local()


def _out() -> Console:
    return getattr(_local, "console", console)


def _err() -> Console:
    return getattr(_local, "err_console", err_console)


# ============================================================================
# Capture
# ============================================================================


class Capture:
    """The bytes one run produced, ANSI intact — and the envelopes behind them.

    Keeping the envelopes is what stops `--json` being a second trip. `emit`
    already holds the `Result` at the moment it renders it, and used to throw
    the structure away; a consumer that wanted the data had to run the command
    again, which for `tb run` means running the *job* again.

    They collect on the capture rather than in a module global so a watch
    refreshing on another thread cannot leave its envelope where the
    foreground is about to read one.
    """

    def __init__(self, buffer: io.StringIO) -> None:
        self._buffer = buffer
        self.envelopes: list[dict] = []

    @property
    def text(self) -> str:
        return self._buffer.getvalue()


@contextlib.contextmanager
def capture(width: int = 100, redirect: bool = True, theme: Theme | None = None):
    """Redirect every byte tb would print into a buffer.

    This module claims to own every byte that reaches the terminal. A surface
    that renders tb output somewhere other than a terminal — `tb tui` today —
    has to be able to take that claim up rather than route around it, which is
    why capture lives here and not in the consumer.

    Swapping the two consoles is not sufficient on its own. rich-click renders
    `--help` through a console of its own making, so the stdout/stderr redirect
    is doing real work rather than guarding against a hypothetical stray
    `print`: without it, help text escapes to the real terminal and corrupts
    whatever is drawn there.

    Both consoles share one buffer, so the transcript interleaves in written
    order — a `partial` banner on stderr stays attached to the data it
    describes instead of floating to the top.

    `force_terminal` keeps the colour, since the whole point is to render it
    again somewhere else. `width` is the consumer's, not the terminal's.

    `redirect` is the one process-global part and the only part a concurrent
    caller must decline. `sys.stdout` has no per-thread version, so two
    captures redirecting at once corrupt each other. The foreground dispatch
    keeps it, because that is the one that can render `--help`; a watch passes
    ``redirect=False`` and is safe without it, since a watch may not run
    `--help` at all — cli/watch.py refuses one at load.

    `COLUMNS` is set for the same reason the redirect exists. rich-click's own
    console is built where nothing here can reach it, so swapping the globals
    sizes every byte tb writes and none of the bytes `--help` writes — help
    came out at Rich's 80-column default whatever width was asked for. Setting
    `rich_click.WIDTH` does not take; the environment variable is the one lever
    that reaches a console constructed somewhere else. Harmless for the rest,
    which are already sized directly.
    """
    buffer = io.StringIO()
    swapped = Console(
        theme=theme or THEME, file=buffer, force_terminal=True, width=width, highlight=False
    )
    saved = (getattr(_local, "console", None), getattr(_local, "err_console", None))
    saved_columns = os.environ.get("COLUMNS")
    _local.console = _local.err_console = swapped
    saved_capture = getattr(_local, "capture", None)
    captured = Capture(buffer)
    _local.capture = captured
    os.environ["COLUMNS"] = str(width)
    try:
        with contextlib.ExitStack() as stack:
            if redirect:
                stack.enter_context(contextlib.redirect_stdout(buffer))
                stack.enter_context(contextlib.redirect_stderr(buffer))
            yield captured
    finally:
        # Restored on the exception path too. A surface that leaves this
        # swapped after one bad command goes silent for the rest of its life,
        # and a leaked COLUMNS would follow every later subprocess out.
        _local.console, _local.err_console = saved
        _local.capture = saved_capture
        if saved_columns is None:
            os.environ.pop("COLUMNS", None)
        else:
            os.environ["COLUMNS"] = saved_columns

# Exit codes. `partial` gets its own code so a caller can branch on degradation
# without parsing anything — which is what makes tb commands composable inside
# job definitions.
#
# NOT 2: Click exits 2 on usage errors ("No such option"), and a caller
# branching on exit codes would read a typo'd invocation as a degraded run.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_PARTIAL = 3

def humanize_bytes(count: int) -> str:
    """Binary units — a 4 TB disk is 3.6 TiB and saying so is the honest answer."""
    value = float(count)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(value) < 1024 or unit == "PiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PiB"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


OK_GLYPH = "\u2713"
FAIL_GLYPH = "\u2717"
UNKNOWN_GLYPH = "\u00b7"


@dataclass
class Result:
    """The envelope every command returns.

    ``ok`` is False only on hard failure — the command could not do its job.
    ``partial`` means some sources failed but the output is still useful, which
    is the normal state for a fan-out across hosts that degrade gracefully.
    Without it, "3 of 6 hosts reachable" is indistinguishable from success, and
    an MCP-driven session would report all six healthy.
    """

    command: str = ""
    data: Any = None
    ok: bool = True
    partial: bool = False
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        """Record a degraded source.

        Deliberately does not set ``partial`` — a warning may be purely
        informational. Callers decide whether the result is degraded.
        """
        self.warnings.append(message)

    def degrade(self, message: str) -> None:
        """Record a degraded source AND mark the result partial."""
        self.warn(message)
        self.partial = True

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "ok": self.ok,
            "partial": self.partial,
            "data": self.data,
            "warnings": list(self.warnings),
        }


# ============================================================================
# Rendering
# ============================================================================


def render(result: Result, as_json: bool = False) -> None:
    """Render a result. The only function commands should reach for."""
    if as_json:
        _render_json(result)
    else:
        _render_human(result)
    _render_warnings(result)


def _render_json(result: Result) -> None:
    # default=str so a stray Path or datetime degrades to a string instead of
    # crashing at render time, after the command has already done its work.
    click.echo(json.dumps(result.to_dict(), indent=2, default=str))


def _render_warnings(result: Result) -> None:
    """Warnings always go to stderr, in both modes.

    This is what keeps stdout parseable: `tb --json ... | jq` gets clean JSON
    while the warnings still reach the terminal. They also remain in the JSON
    envelope, so a machine consumer sees them structurally.
    """
    for warning in result.warnings:
        _err().print(f"[yellow]⚠️  {warning}[/yellow]", highlight=False)


def _render_human(result: Result) -> None:
    if not result.ok:
        _err().print(f"[tb.fail]{FAIL_GLYPH} {result.command} failed[/tb.fail]")
    elif result.partial:
        _err().print(f"[tb.warn]{UNKNOWN_GLYPH} {result.command} — partial[/tb.warn]")

    _render_value(result.data, title=result.command or None)


def _header(title: str | None, subtitle: str | None = None) -> None:
    if not title:
        return
    line = Text.assemble(("● ", "tb.accent"), (title, "bold"))
    if subtitle:
        line.append("  ")
        line.append(subtitle, style="tb.muted")
    _out().print(line)
    _out().print()


def _render_value(value: Any, title: str | None = None) -> None:
    if value is None:
        return
    if isinstance(value, str):
        click.echo(value)
    elif isinstance(value, bool):
        # Before int — bool is an int subclass.
        click.echo("yes" if value else "no")
    elif isinstance(value, (int, float)):
        click.echo(str(value))
    elif isinstance(value, dict):
        _header(title, _plural(len(value), "section") if _is_nested(value) else None)
        _render_mapping(value)
    elif isinstance(value, (list, tuple)):
        _render_sequence(list(value), title=title)
    else:
        click.echo(str(value))


def _is_nested(mapping: dict) -> bool:
    return any(isinstance(v, dict) for v in mapping.values())


def _render_mapping(mapping: dict, indent: int = 2) -> None:
    """Dim labels, values coloured by type, accent section headings, no borders.

    A borderless Table rather than hand-assembled lines: a long value — a PATH,
    a shell list — has to wrap *inside its column* and stay aligned. Printing
    Text directly wraps to column zero and destroys the indent.
    """
    if not mapping:
        return

    flat = {k: v for k, v in mapping.items() if not _is_block(v)}
    nested = {k: v for k, v in mapping.items() if _is_block(v)}

    if flat:
        table = Table(
            box=None,
            show_header=False,
            pad_edge=False,
            padding=(0, 3, 0, 0),
        )
        table.add_column(style="tb.label", no_wrap=True)
        table.add_column(overflow="fold")
        for key, value in flat.items():
            table.add_row(str(key), _styled_value(value, key))
        _out().print(Padding(table, (0, 0, 0, indent)))

    for key, value in nested.items():
        _out().print(Padding(Text(key, style="tb.accent"), (0, 0, 0, max(indent - 2, 0))))
        if isinstance(value, dict):
            _render_mapping(value, indent + 2)
        else:
            _render_columns(list(value), title=None, indent=indent)
        _out().print()


def _is_block(value: Any) -> bool:
    """Does this value need its own titled block rather than one line?

    A dict, or a list of dicts — `gpus`, `disks`, `filesystems`. Without this a
    list of dicts renders as `str(dict)` inside a key/value row.
    """
    if isinstance(value, dict):
        return True
    return (
        isinstance(value, (list, tuple))
        and bool(value)
        and all(isinstance(item, dict) for item in value)
    )


def _render_sequence(items: list, title: str | None = None) -> None:
    if not items:
        return
    if not all(isinstance(item, dict) for item in items):
        _header(title, _plural(len(items), "item"))
        for item in items:
            _out().print(Text("  ").append_text(_styled_value(item)))
        return

    if all("ok" in item for item in items):
        _render_status_list(items, title)
    else:
        _render_columns(items, title)


def _render_status_list(rows: list[dict], title: str | None) -> None:
    """One line per row: glyph, label, dim detail.

    Triggered by the presence of an `ok` field — a data convention, not styling
    chosen by the command. `ok` drives the glyph, the first string field is the
    label, and `detail` becomes the dim suffix.
    """
    _header(title, _plural(len(rows), "check"))

    labels = [str(_label_of(row)) for row in rows]
    width = max((len(x) for x in labels), default=0)

    passed = failed = unknown = 0
    for row, label in zip(rows, labels):
        state = row.get("ok")
        if state is True:
            glyph, style = OK_GLYPH, "tb.ok"
            passed += 1
        elif state is False:
            glyph, style = FAIL_GLYPH, "tb.fail"
            failed += 1
        else:
            glyph, style = UNKNOWN_GLYPH, "tb.muted"
            unknown += 1

        line = Text("  ")
        line.append(f"{glyph} ", style=style)
        line.append(label.ljust(width), style="bold" if state is False else "")
        detail = row.get("detail")
        line.append("   ")
        line.append(str(detail) if detail else "", style="tb.muted")
        _out().print(line)

    _out().print()
    summary = Text("  ")
    summary.append(f"{passed} passed", style="tb.muted")
    if failed:
        summary.append("   ")
        summary.append(f"{failed} failed", style="tb.fail")
    if unknown:
        # Counted explicitly: rows with no verdict must not vanish from the
        # tally, or the footer quietly under-reports what it looked at.
        summary.append("   ")
        summary.append(f"{unknown} unknown", style="tb.muted")
    _out().print(summary)


def _label_of(row: dict) -> Any:
    """First string-valued field — the thing a human calls this row."""
    for key, value in row.items():
        if isinstance(value, str) and key != "detail":
            return value
    return next(iter(row.values()), "")


def _render_columns(rows: list[dict], title: str | None, indent: int = 0) -> None:
    """Borderless aligned columns for rows with no single status."""
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)

    _header(title, _plural(len(rows), "row"))

    table = Table(box=None, show_header=True, header_style="tb.label", pad_edge=False, padding=(0, 3, 0, 0))
    for col in columns:
        table.add_column(str(col).upper(), justify="right" if _numeric_column(rows, col) else "left")
    for row in rows:
        table.add_row(*(_styled_value(row.get(col), col) for col in columns))
    _out().print(Padding(table, (0, 0, 0, indent)) if indent else table)


def _numeric_column(rows: list[dict], column: str) -> bool:
    values = [r.get(column) for r in rows]
    present = [v for v in values if v is not None]
    return bool(present) and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in present
    )


def _styled_value(value: Any, key: str | None = None) -> Text:
    """One value as rich Text, coloured by type.

    Text rather than markup on purpose: a value containing square brackets — a
    hostname, a desktop-file name, an error string — would otherwise be parsed
    as rich markup and either vanish or raise.
    """
    if value is None:
        return Text(EMPTY, style="tb.muted")
    if isinstance(value, bool):
        return (
            Text(f"{OK_GLYPH} yes", style="tb.ok")
            if value
            else Text(f"{FAIL_GLYPH} no", style="tb.fail")
        )
    if isinstance(value, (list, tuple)):
        if not value:
            return Text(EMPTY, style="tb.muted")
        return Text(", ".join(_cell(v) for v in value), style="tb.muted")
    if isinstance(value, (int, float)):
        # Convention, like `ok`: a field named `*_bytes` carries a raw byte count
        # in the envelope and is humanized only here. Machines get the number,
        # humans get the unit.
        if key and str(key).endswith("_bytes"):
            return Text(humanize_bytes(int(value)), style="tb.num")
        return Text(str(value), style="tb.num")
    text = str(value)
    if text.startswith("/"):
        return Text(text, style="tb.path")
    return Text(text)


def _cell(value: Any) -> str:
    """One value as a plain string, for joining inside a cell."""
    if value is None:
        return EMPTY
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(_cell(v) for v in value) if value else EMPTY
    return str(value)


# ============================================================================
# Wiring
# ============================================================================


def exit_code(result: Result) -> int:
    """Map a result onto its process exit code."""
    if not result.ok:
        return EXIT_ERROR
    if result.partial:
        return EXIT_PARTIAL
    return EXIT_OK


def _command_path(ctx: click.Context) -> str:
    """Click's "tb fleet status" as the dotted "fleet.status".

    This is the canonical command name: it goes in the envelope and becomes the
    MCP tool name, so deriving it from the actual command path means the two can
    never drift apart.
    """
    parts = ctx.command_path.split()
    return ".".join(parts[1:]) if len(parts) > 1 else ctx.info_name


def emit(func):
    """Wrap a command that returns a :class:`Result`.

    Handles the whole tail of every command: pulling ``--json`` off the root
    context, naming the result, rendering it, and exiting with the right code.
    A command body therefore does no I/O at all — it computes and returns.
    """

    @click.pass_context
    @functools.wraps(func)
    def wrapper(ctx: click.Context, *args, **kwargs):
        root = ctx.find_root()
        as_json = bool((root.obj or {}).get("as_json"))
        name = _command_path(ctx)

        try:
            result = func(*args, **kwargs)
            if not isinstance(result, Result):
                raise TypeError(
                    f"{name} returned {type(result).__name__}, expected Result — "
                    "commands must return a Result, never print"
                )
        except (click.ClickException, click.Abort, click.exceptions.Exit):
            # Click's own control flow (usage errors, --help, ctx.exit) has its
            # own handling; swallowing it here would break both.
            raise
        except Exception as exc:
            # TB_DEBUG=1 re-raises so you get the real traceback. Without an
            # escape hatch, turning every exception into a tidy envelope makes
            # the CLI undebuggable.
            if os.environ.get("TB_DEBUG"):
                raise
            result = Result(
                command=name,
                ok=False,
                data={
                    "error": str(exc) or exc.__class__.__name__,
                    "type": exc.__class__.__name__,
                },
            )

        if not result.command:
            result.command = name

        # Hand the structure to whoever is capturing, before rendering throws
        # it away. Cheap, and it is the only moment it exists.
        active = getattr(_local, "capture", None)
        if active is not None:
            active.envelopes.append(result.to_dict())

        render(result, as_json)
        ctx.exit(exit_code(result))

    return wrapper
