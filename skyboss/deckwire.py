"""A line under the tab row, drawn from a sender's tab to its receivers' and faded. See [[command-deck]].

It lives in the row under the tabs, which is otherwise blank, so it costs no height. Corners
meet the tabs' bottom edges: down from the sender, along, and up into each receiver.

The frames are pure; `deck.py` measures the tabs and writes each frame to a tmux option,
and tmux redraws the bar on the write.
"""

from __future__ import annotations

from skyboss import theme

#: Seconds between frames.
FRAME = 0.05
#: Frames to draw the line out, to hold it whole, and how much of the hue each fading frame keeps.
DRAW_FRAMES = 8
HOLD_FRAMES = 6
FADES = (0.8, 0.6, 0.42, 0.28, 0.16, 0.07)


def glyphs(source: int, targets: list[int]) -> dict[int, str]:
    """Column → character: corners at the span's ends, `┴` at any tab tapped between them."""
    taps = {source, *targets}
    low, high = min(taps), max(taps)
    cells = {column: "─" for column in range(low, high + 1)}
    cells.update({column: "┴" for column in taps})
    cells[low], cells[high] = "╰", "╯"
    return cells


def line(cells: dict[int, str], source: int, reach: int, colour: str, ground: str) -> str:
    """The cells within `reach` of the sender, as a tmux format starting at column 0."""
    shown = [column for column in cells if abs(column - source) <= reach]
    low, high = min(shown), max(shown)
    body = "".join(cells[column] for column in range(low, high + 1))
    return f"#[{ground}]{' ' * low}#[fg={colour}]{body}#[{ground}]"


def frames(source: int, targets: list[int], colour: str, ground: str) -> list[str]:
    """Every frame in order: drawn out from the sender, held, then faded into the bar."""
    cells = glyphs(source, targets)
    span = max(abs(column - source) for column in cells)
    reaches = [-(-span * step // DRAW_FRAMES) for step in range(1, DRAW_FRAMES + 1)]
    drawn = [line(cells, source, reach, colour, ground) for reach in reaches]
    faded = [line(cells, source, span, theme.fade(colour, keep), ground) for keep in FADES]
    return [*drawn, *[drawn[-1]] * HOLD_FRAMES, *faded]
