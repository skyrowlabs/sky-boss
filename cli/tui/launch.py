"""The idle state, built as a place rather than an empty transcript.

Everything here is already loaded a second after launch — jobs, watches, lanes,
the ledger tail. The gap this closes is not knowledge, it is that none of it
was shown until asked for, so the first thing you did every session was type
something to find out where you were.

Renders to a Rich `Text`, the way every other pane on the surface does. It
takes the state it needs as arguments rather than reading it, so the app stays
the only thing that knows how to reach the ledger and `/proc/locks`.
"""

from __future__ import annotations

import socket

from rich.text import Text

from cli.output import TUI_THEME

ACCENT = TUI_THEME.styles["tb.accent"]
LABEL = TUI_THEME.styles["tb.label"]
MUTED = TUI_THEME.styles["tb.muted"]
OK = TUI_THEME.styles["tb.ok"]
FAIL = TUI_THEME.styles["tb.fail"]
WARN = TUI_THEME.styles["tb.warn"]

# Indented off the left edge. The transcript starts hard against it, and the
# difference is most of what makes this read as a screen rather than output.
PAD = "   "

# Enough of what to type to be a starting point, not a menu. These are the
# three that answer "where am I" without changing anything.
SUGGESTIONS = ("check", "auto status", "info assets")


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def view(
    *,
    jobs: int,
    watches: list[tuple[str, str, object, str, str]],
    lanes_held: list[str],
    ledger_runs: int,
    recent: list[tuple[str, str, str, bool]],
    stall_dump: str | None = None,
    width: int = 80,
) -> Text:
    """The whole screen.

    ``watches`` is (name, glyph, style, verdict, definition) — already resolved
    by the app, because deciding what a watch's exit code means belongs next to
    the code that ran it, not here.
    """
    body = Text(no_wrap=True, overflow="ellipsis")
    body.append(PAD)
    body.append(f"{socket.gethostname()}\n", style=ACCENT)

    body.append(PAD)
    held = ", ".join(lanes_held)
    summary = [
        _plural(jobs, "job"),
        _plural(len(watches), "watch").replace("watchs", "watches"),
        f"lanes {held} held" if held else "lanes clear",
        f"ledger {ledger_runs} runs",
    ]
    body.append(" · ".join(summary), style=MUTED)
    body.append("\n\n")

    if watches:
        for name, glyph, style, verdict, definition in watches:
            body.append(PAD)
            body.append(f"{glyph} ", style=style)
            body.append(f"{name:<12}", style=LABEL)
            body.append(f"{verdict:<14}", style=style)
            body.append(definition, style=MUTED)
            body.append("\n")
        body.append("\n")

    if recent:
        body.append(PAD)
        body.append("RECENT\n", style=ACCENT)
        for clock, job, outcome, went_well in recent:
            body.append(PAD)
            body.append(f"{clock:<7}", style=MUTED)
            body.append(f"{job:<18}", style=LABEL)
            body.append(outcome, style=OK if went_well else FAIL)
            body.append("\n")
        body.append("\n")

    if stall_dump:
        # Shown here rather than documented somewhere, because this is the one
        # screen you are certainly looking at after a freeze — and a diagnostic
        # nobody knows to go and read is the same as no diagnostic.
        body.append(PAD)
        body.append("⚠ ", style=WARN)
        body.append("the surface stalled at some point — stacks in ", style=WARN)
        body.append(stall_dump, style=LABEL)
        body.append("\n\n")

    body.append(PAD)
    body.append("try  ", style=MUTED)
    for index, suggestion in enumerate(SUGGESTIONS):
        if index:
            body.append("   ", style=MUTED)
        body.append(suggestion, style=LABEL)
    return body
