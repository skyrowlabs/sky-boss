"""The idle state — a place rather than an empty transcript.

Deliberately close to bare. It used to summarise jobs, lanes, the ledger and
recent runs; all of that went with the job layer on 2026-08-20, and inventing
something to fill the space would be worse than leaving it. What is left is the
host, a starting point, and the one thing the surface knows that you might not:
whether it froze last time.

Renders to a Rich `Text`, the way every other pane does, and takes what it needs
as arguments rather than reading it — so the app stays the only thing that knows
how to reach the state directory.
"""

from __future__ import annotations

import socket

from rich.text import Text

from cli.output import TUI_THEME

ACCENT = TUI_THEME.styles["tb.accent"]
LABEL = TUI_THEME.styles["tb.label"]
MUTED = TUI_THEME.styles["tb.muted"]
WARN = TUI_THEME.styles["tb.warn"]

# Indented off the left edge. The transcript starts hard against it, and the
# difference is most of what makes this read as a screen rather than output.
PAD = "   "

SUGGESTIONS = ("run -- echo hello", "run --help")


def view(*, stall_dump: str | None = None, width: int = 80) -> Text:
    """The whole screen."""
    body = Text(no_wrap=True, overflow="ellipsis")
    body.append(PAD)
    body.append(f"{socket.gethostname()}\n\n", style=ACCENT)

    if stall_dump:
        # Shown here because this is the one screen you are certainly looking at
        # after a freeze, and a diagnostic nobody knows to read is no diagnostic.
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
