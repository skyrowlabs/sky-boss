"""Output contract for the tb CLI.

Command functions return a :class:`Result`; this module owns every byte that
reaches the terminal. Three consumers read command output — a human, ``tb
brief`` merging across domains, and the MCP server — so a command that formats
its own prose has to be written three times.

"""

from __future__ import annotations

import contextlib
import functools
import io
import json
import os
import textwrap
import threading
from dataclasses import dataclass, field
from typing import Any

import click
from rich.console import Console
from rich.padding import Padding
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from cli.theme import STYLES
from cli.view import resolve, summarise_mapping

# Rendered in place of a missing value in a table cell.
EMPTY = "-"

# A shaped table is laid out by hand, so it needs its own bound. The surface has
# had one since the terminal froze on a 120k-line result; the substrate changed
# and the rule did not.
MAX_TABLE_ROWS = 2000

# The palette lives in cli/theme.py, so that this module, rich-click's --help
# styling and the canvas's CSS cannot drift apart. Style *names* are the
# contract here; no hex is written below this line.
#
# There was a second Theme here, the same roles undarkened, for a surface that
# rendered captured Rich output on a background it painted itself. The canvas
# does not: it renders from the envelope's data rather than from tb's bytes, so
# the full-strength rendering of the palette reaches it as CSS custom
# properties instead. See cli/theme.css_variables.
THEME = Theme(STYLES)

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


# `or` rather than a bare default: a thread that has finished a capture may
# carry the attribute set to None, and a present-but-None attribute never falls
# through to `getattr`'s default. See the restore in `capture`.
def _out() -> Console:
    return getattr(_local, "console", None) or console


def _err() -> Console:
    return getattr(_local, "err_console", None) or err_console


# ============================================================================
# Capture
# ============================================================================


class Capture:
    """The bytes one run produced, ANSI intact — and the envelopes behind them.

    Keeping the envelopes is what stops `--json` being a second trip. `emit`
    already holds the `Result` at the moment it renders it, and used to throw
    the structure away; a consumer that wanted the data had to run the command
    again, which for `tb run` means running the *job* again.

    They collect on the capture rather than in a module global so a background
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
    keeps it, because that is the one that can render `--help`. A caller that
    knows nothing it runs can print `--help` may pass ``redirect=False``.

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
        #
        # *Unset* rather than set-to-None where there was nothing to restore.
        # Assigning None leaves the attribute present, and `getattr(..., default)`
        # only uses its default when the attribute is absent — so the first
        # capture on a thread used to poison that thread's console for good.
        # Thread-pool workers are reused, so the second dispatch on a recycled
        # worker would crash on its first warning.
        for name, value in (("console", saved[0]), ("err_console", saved[1])):
            if value is None:
                _local.__dict__.pop(name, None)
            else:
                setattr(_local, name, value)
        if saved_capture is None:
            _local.__dict__.pop("capture", None)
        else:
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

    # How to *present* `data`, when the command has something to say about it.
    # A hint, never a filter: `data` is complete whatever this holds, so a
    # machine consumer keeps every field the table happens to hide. Only
    # commands carrying foreign data set it — see cli/view.py.
    view: Any = None

    # Where `--save` wrote this invocation, when it did. Never set by anything
    # else: a command that saved nothing carries no key at all. See [[tools]].
    saved: Any = None

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
        envelope = {
            "command": self.command,
            "ok": self.ok,
            "partial": self.partial,
            "data": self.data,
            "warnings": list(self.warnings),
        }
        # Omitted rather than sent as null, so an envelope from a command with
        # no opinion about presentation is byte-identical to one from before
        # views existed. Every consumer already has to handle the key's
        # absence; none of them should have to learn that null means default.
        if self.view is not None:
            envelope["view"] = self.view
        # Same rule as `view`, for the same reason: omitted rather than null,
        # so an envelope from a command that saved nothing is byte-identical
        # to one from before saving existed.
        if self.saved is not None:
            envelope["saved"] = self.saved
        return envelope


# ============================================================================
# Rendering
# ============================================================================


def render(result: Result, as_json: bool = False) -> None:
    """Render a result. The only function commands should reach for."""
    if as_json:
        _render_json(result)
    else:
        _render_human(result)
        # Prose only for a human: under `--json` the same fact is already in
        # the envelope, and saying it twice would put it on stdout as well.
        saved_note(result.saved)
    _render_warnings(result)


def saved_note(saved: dict | None) -> None:
    """Say what `--save` wrote, on stderr. See [[tools]] round 3.

    stderr for the reason every band uses it: this is status, not payload, and
    `tb read --save=x -- thing | grep` must still see exactly the lines the
    tool printed.

    It names the **expansion**, not just the file. The file tells you a write
    happened; the expansion is the operator's one chance to notice that the
    saved line is not the line they meant, while they still remember typing it.
    """
    if not saved:
        return
    spans = [
        ("saved ", "tb.label"),
        (saved["name"], "tb.accent"),
        (" → ", "tb.muted"),
        (saved["runs"], "tb.path"),
    ]
    if saved.get("refresh"):
        spans.append((f"  refresh {saved['refresh']}s", "tb.muted"))
    band(spans)


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

    _render_value(result.data, title=result.command or None, view=result.view)


def _header(title: str | None, subtitle: str | None = None) -> None:
    if not title:
        return
    line = Text.assemble(("● ", "tb.accent"), (title, "bold"))
    if subtitle:
        line.append("  ")
        line.append(subtitle, style="tb.muted")
    _out().print(line)
    _out().print()


def _render_value(value: Any, title: str | None = None, view: dict | None = None) -> None:
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
        _render_mapping(value, view=view)
    elif isinstance(value, (list, tuple)):
        _render_sequence(list(value), title=title, view=view)
    else:
        click.echo(str(value))


def _is_nested(mapping: dict) -> bool:
    return any(isinstance(v, dict) for v in mapping.values())


def _render_mapping(mapping: dict, indent: int = 2, view: dict | None = None) -> None:
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
        elif isinstance(value, str):
            # Verbatim, through click rather than a Console: a Console would
            # soft-wrap it to the terminal width, which is the whole bug.
            click.echo(value.rstrip("\n"))
        else:
            # The view belongs to exactly one nested list — the one shaping
            # found the rows in. Handing it to any other would draw a table
            # with another list's columns, which is the failure this whole
            # round is about. See [[table-views]] round 4.
            _render_columns(
                list(value),
                title=None,
                indent=indent,
                view=view if view and view.get("rows") == key else None,
            )
        _out().print()


def _is_block(value: Any) -> bool:
    """Does this value need its own titled block rather than one line?

    A dict, or a list of dicts — `gpus`, `disks`, `filesystems`. Without this a
    list of dicts renders as `str(dict)` inside a key/value row.

    And multi-line text. `tb run` carries a command's stdout, and folding an
    aligned table into a key/value cell wraps every row at the column edge and
    destroys the alignment that was the reason to look at it.
    """
    if isinstance(value, str):
        return "\n" in value.strip()
    if isinstance(value, dict):
        return True
    return (
        isinstance(value, (list, tuple))
        and bool(value)
        and all(isinstance(item, dict) for item in value)
    )


def _render_sequence(items: list, title: str | None = None, view: dict | None = None) -> None:
    if not items:
        return
    if not all(isinstance(item, dict) for item in items):
        _header(title, _plural(len(items), "item"))
        for item in items:
            _out().print(Text("  ").append_text(_styled_value(item)))
        return

    # A view is an explicit instruction about columns, so it outranks the
    # status-list convention even when every row happens to carry `ok`. The
    # heuristic looked at these rows; the convention only looked at one field.
    if view is None and all("ok" in item for item in items):
        _render_status_list(items, title)
    else:
        _render_columns(items, title, view=view)


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


def _render_columns(
    rows: list[dict], title: str | None, indent: int = 0, view: dict | None = None
) -> None:
    """Borderless aligned columns for rows with no single status.

    Without a view this is what it always was: every key of every row, in
    first-seen order, at equal width. That is right for data whose fields a
    person chose, and it is what tb's own commands still get.

    With one, the columns and their relative widths were decided in cli/view.py
    and this only draws them — `no_wrap` with ellipsis overflow is what stops a
    78-character title folding a one-row table into twelve lines.

    The flex weights are resolved to absolute widths *here* rather than handed
    to Rich as `ratio`. Rich's ratio distribution builds its floor from
    `column.width or 1` and ignores `min_width` completely, so a ratio column
    can be squeezed below its own header — `MERGE_STATE` rendering as `ME…`,
    which is a column you cannot identify at all. Doing the arithmetic against
    the console width costs six lines and honours the floor.
    """
    _header(title, _plural(len(rows), "row"))

    if view:
        _render_view(rows, view, indent)
        return

    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)

    table = Table(box=None, show_header=True, header_style="tb.label", pad_edge=False, padding=(0, 3, 0, 0))
    for col in columns:
        table.add_column(str(col).upper(), justify="right" if _numeric_column(rows, col) else "left")
    for row in rows:
        table.add_row(*(_styled_value(row.get(col), col) for col in columns))
    _out().print(Padding(table, (0, 0, 0, indent)) if indent else table)


# The gutter between columns in a shaped table. Two rather than three: three
# reads as generous until a foreign tool's tenth column is the one the budget
# hides to pay for it.
_COLUMN_PADDING = 2


def fit_columns(columns: list[dict], available: int) -> tuple[list[dict], list[str]]:
    """As many leading columns as fit at their floors, and the keys of the rest.

    **This is the terminal's half of [[table-views]] round 3.** `cli/view.py`
    says which columns are worth showing; how many fit is arithmetic against a
    width, and only a renderer knows its width. The canvas answers the same
    question differently *because its substrate differs* — a browser can scroll
    sideways and a terminal cannot — which is why this is not shared code.

    The first column is kept whatever its floor: a table with no columns is
    worse than one that overflows by a character, and the overflow is at least
    something you can widen the terminal to read.
    """
    kept: list[dict] = []
    used = 0
    for column in columns:
        floor = max(1, column.get("min", 1))
        gutter = _COLUMN_PADDING if kept else 0
        if kept and used + gutter + floor > available:
            break
        used += gutter + floor
        kept.append(column)
    return kept, [column["key"] for column in columns[len(kept) :]]


def _resolve_widths(columns: list[dict], available: int) -> list[int]:
    """Flex weights as absolute character widths, never below a column's floor.

    Every column starts at its floor — its own header, so no column is ever
    unidentifiable — and whatever is left over is shared out in proportion to
    the weights. If the floors alone do not fit, they are used anyway and the
    table overflows: a table too wide for the terminal is a legible thing you
    can widen, whereas a table of two-character stubs is not. The column budget
    in cli/view.py is what keeps that case rare.
    """
    floors = [max(1, column.get("min", 1)) for column in columns]
    naturals = [max(floor, column.get("max", floor)) for floor, column in zip(floors, columns)]
    gutters = _COLUMN_PADDING * max(0, len(columns) - 1)

    # If every column can have the width it actually wants, give it that and
    # leave the rest of the terminal empty. A table padded out to the full
    # width to avoid looking unfinished is how `NUMBER` ends up eighteen
    # characters wide with a three-digit number in it.
    if sum(naturals) + gutters <= available:
        return naturals

    spare = available - sum(floors) - gutters
    if spare <= 0:
        return floors

    weights = [max(1, column.get("flex", 1)) for column in columns]
    total = sum(weights)
    return [
        min(natural, floor + (spare * weight) // total)
        for floor, natural, weight in zip(floors, naturals, weights)
    ]


def _render_view(rows: list[dict], view: dict, indent: int = 0) -> None:
    """A shaped table, laid out by hand.

    Rich's `Table` cannot do this: a detail line spans every column, and there
    is no colspan. The widths were already being resolved here anyway — Rich's
    `ratio` ignores `min_width`, which is why — so the remaining cost of owning
    the layout is small and it buys the header rule, the detail lines and the
    record spacing outright.
    """
    columns, overflowed = fit_columns(view["columns"], _out().width - indent)
    details = view.get("details") or []
    widths = _resolve_widths(columns, _out().width - indent)
    pad = " " * _COLUMN_PADDING
    total = sum(widths) + _COLUMN_PADDING * max(0, len(columns) - 1)

    # Detail lines start under the second column, so the identifier in the
    # first stays the leftmost thing on the record and the prose hangs off it.
    hang = (widths[0] + _COLUMN_PADDING) if widths else 0
    body_width = max(20, _out().width - indent - hang)

    def emit(text: Text) -> None:
        _out().print(Padding(text, (0, 0, 0, indent)) if indent else text)

    header = Text()
    for i, (column, width) in enumerate(zip(columns, widths)):
        if i:
            header.append(pad)
        last = i == len(columns) - 1
        header.append(_fit(column["label"], width, column.get("align"), last), style="tb.label")
    emit(header)
    emit(Text("─" * total, style="tb.muted"))

    for index, row in enumerate(rows[:MAX_TABLE_ROWS]):
        line = Text()
        for i, (column, width) in enumerate(zip(columns, widths)):
            if i:
                line.append(pad)
            cell = _view_cell(row, column)
            last = i == len(columns) - 1
            line.append_text(_pad_text(cell, width, column.get("align"), last))
        emit(line)

        for column in details:
            value = resolve(row, column["key"])
            text = cellstr(value)
            if not text or text == EMPTY:
                continue
            for chunk in textwrap.wrap(text, body_width) or [""]:
                emit(Text(" " * hang + chunk, style="tb.muted"))

        # Only when there is something hanging off the record. Without details
        # the blank lines would be spacing a plain table apart for no reason.
        if details and index < len(rows) - 1:
            emit(Text(""))

    if len(rows) > MAX_TABLE_ROWS:
        emit(Text(f"{len(rows) - MAX_TABLE_ROWS} more rows not shown", style="tb.warn"))

    # Named, never silent — the half of the old budget rule that survives. It
    # belongs here rather than in the envelope's warnings because it is a fact
    # about *this drawing at this width*, and widening the terminal changes it.
    if overflowed:
        count = len(overflowed)
        emit(
            Text(
                f"{count} column{'' if count == 1 else 's'} did not fit: "
                f"{', '.join(overflowed)} — widen, or use --cols",
                style="tb.warn",
            )
        )


def _fit(text: str, width: int, align: str | None, last: bool = False) -> str:
    clipped = text if len(text) <= width else text[: max(0, width - 1)] + "…"
    if align == "right":
        return clipped.rjust(width)
    # The final column is not padded out: trailing spaces are invisible until
    # someone selects the line or diffs the output, and then they are noise.
    return clipped if last else clipped.ljust(width)


def _pad_text(text: Text, width: int, align: str | None, last: bool = False) -> Text:
    """Clip or pad a styled cell to exactly `width`, keeping its style."""
    plain = text.plain
    if len(plain) > width:
        out = text[: max(0, width - 1)]
        out.append("…")
        return out
    if align == "right":
        return Text(" " * (width - len(plain))).append_text(text)
    return text if last else text.append(" " * (width - len(plain)))


def cellstr(value) -> str:
    """A detail value as plain text. Styling is the caller's."""
    if value is None:
        return EMPTY
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(_cell(v) for v in value) if value else EMPTY
    return str(value)


def _view_cell(row: dict, column: dict) -> Text:
    """One cell, as the view described it.

    A dotted key only ever comes from `--cols`, so the lookup goes through
    `resolve` either way rather than branching on whether it has a dot in it.
    """
    value = resolve(row, column["key"])
    if column.get("summarise") and isinstance(value, dict):
        return Text(summarise_mapping(value), style="tb.muted")
    return _styled_value(value, column["key"])


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


def band_text(spans) -> Text:
    """Chrome band spans assembled into styled Text. The roles were decided
    in cli/chrome.py; this only applies them — neither renderer grows an
    opinion. See [[chrome]]."""
    text = Text()
    for chunk, role in spans:
        text.append(chunk, style=role)
    return text


def band(spans) -> None:
    """One chrome band line, on stderr through whichever console owns it.

    stderr, deliberately: a band is status, not payload. `tb read -- x | grep`
    must see exactly the lines the tool printed, the same purity rule that
    keeps warnings off stdout. See [[chrome]].
    """
    _err().print(band_text(spans), highlight=False)


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
