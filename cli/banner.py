"""The mark — a control tower and the wordmark, drawn in half-blocks.

**`ART` is the picture.** A terminal cannot show an image, but this mark never
needed one to be: it is pixel art either way — a 5x7 blocky face for the
wordmark beside a glyph, both on one grid. One art pixel per cell keeps the
letters crisp rather than resampled to mush, which is what any "scale the image
down" approach produces at this size. The PNG at `docs/design/cli-header.png`
is *rendered from this tuple*, not the other way round, which is the only
arrangement in which the two cannot disagree — and they did disagree, for the
length of the 2026-08-27 rename ([[header]]).

**Half-blocks, so the aspect survives.** A terminal cell is about twice as tall
as it is wide, so one art pixel per *cell* would render the mark stretched to
double height. `\u2580` splits a cell into two square-ish halves — foreground on
top, background below — which puts 14 art rows into 7 terminal rows at the
proportions the designer drew.

**The mark paints its own background**, and that is what lets it use the design
system at full strength instead of the CLI's darkened derivations (CLAUDE.md
§ Conventions).
The derivations exist because sb renders into a terminal whose background
nobody here knows; painting one removes the unknown, exactly as the canvas
does. It is also the only answer available: the mark's own hues fail in
*opposite* directions — the lit glass disappears on white, the dark shaft
disappears on black — so no single floor could admit both.

**It degrades rather than wrapping.** A banner wider than the terminal is worse
than no banner, and a wall of block characters down a pipe is worse still, so
anything narrow or not a terminal gets the one-line spelling instead.
"""

from __future__ import annotations

from rich.console import Console
from rich.style import Style
from rich.text import Text

from cli.theme import CLI_BRAND, CLI_FAINT, LOGO_BG, LOGO_BRAND, LOGO_DARK, LOGO_LIGHT

# One character per art pixel, two rows per rendered line. `B` brand, `D` the
# dark slate of the tower's shaft, `W` the lit glass of the cab and the mast
# above it, `.` the mark's own background. Edit this and the mark changes — it
# is the picture, not a cache of one.
ART: tuple[str, ...] = (
    "......WW.......................................................",
    "......WW.......................................................",
    "...BBBBBBBB....................................................",
    ".BBBBBBBBBBBB......BBBBB.B...B.B...B....BBBB..BBBBB.BBBBB.BBBBB",
    ".BWWDWWWWDWWB......B.....B..B..B...B....B...B.B...B.B.....B....",
    ".BWWDWWWWDWWB......B.....B.B....B.B.....B...B.B...B.B.....B....",
    "..BBBBBBBBBB.......BBBBB.BB......B......BBBB..B...B.BBBBB.BBBBB",
    ".....BBBD..............B.B.B.....B......B...B.B...B.....B.....B",
    ".....BBBD..............B.B..B....B...BB.B...B.B...B.....B.....B",
    ".....BBBD..........BBBBB.B...B...B...BB.BBBB..BBBBB.BBBBB.BBBBB",
    ".....BBBD......................................................",
    ".....BBBD......................................................",
    "...BBBBBBBB....................................................",
    ".BBBBBBBBBBBB..................................................",
)

# Room either side of the art, inside the painted panel.
PAD = 2

WIDTH = len(ART[0]) + PAD * 2

_INK = {"B": LOGO_BRAND, "D": LOGO_DARK, "W": LOGO_LIGHT, ".": LOGO_BG}

# Where the byline sits: under the wordmark, not under the tower.
BYLINE_INDENT = 19


def rows() -> list[Text]:
    """The mark as rendered lines — art first, byline last.

    Pairs of art rows become one line of `\u2580`: the top row is the glyph's
    colour, the bottom row is its background. Every cell is painted, including
    the empty ones, so the panel is a solid rectangle rather than a stencil
    over whatever the terminal happens to be.
    """
    out: list[Text] = []
    for top, bottom in zip(ART[0::2], ART[1::2]):
        line = Text()
        line.append(" " * PAD, style=Style(bgcolor=LOGO_BG))
        for upper, lower in zip(top, bottom):
            line.append("\u2580", style=Style(color=_INK[upper], bgcolor=_INK[lower]))
        line.append(" " * PAD, style=Style(bgcolor=LOGO_BG))
        out.append(line)
    return out


def byline(version: str) -> Text:
    """`by SKYROW.LABS · <version> · sb --help`, on the panel.

    The version is the real one rather than the number the mockup was drawn
    with — a header stating a version it is not is worse than one with no
    version at all. Which means the length is **not** known here: the mockup's
    `v0.4.1` happens to fill the panel exactly, and `git describe` can hand
    back `1.2.0-14-gabc1234-dirty`. So the separators narrow first, and the
    version is truncated last, before anything can spill past the panel edge
    and leave a ragged line under a straight one.
    """
    dim = Style(color=LOGO_DARK, bgcolor=LOGO_BG)
    label = Style(color=LOGO_LIGHT, bgcolor=LOGO_BG)
    brand = Style(color=LOGO_BRAND, bgcolor=LOGO_BG)
    room = WIDTH - PAD - BYLINE_INDENT

    for gap in ("   ·   ", " · "):
        fixed = len("by SKYROW.LABS") + 2 * len(gap) + len("sb --help")
        if fixed + len(version) <= room:
            break
    else:  # both gaps too wide even before the version — trim it to fit
        gap = " · "
        fixed = len("by SKYROW.LABS") + 2 * len(gap) + len("sb --help")
    shown = version[: max(0, room - fixed)]

    line = Text()
    line.append(" " * (PAD + BYLINE_INDENT), style=Style(bgcolor=LOGO_BG))
    line.append("by ", style=dim)
    line.append("SKYROW.", style=label)
    line.append("LABS", style=brand)
    line.append(gap, style=dim)
    line.append(shown, style=label)
    line.append(gap, style=dim)
    line.append("sb --help", style=label)
    line.pad_right(max(0, WIDTH - line.cell_len))
    line.stylize(Style(bgcolor=LOGO_BG))
    return line


def plain(version: str) -> Text:
    """What a surface too small for the mark gets instead.

    Not a smaller mark: a name. Anything that still tried to draw would either
    wrap — turning a rectangle into confetti — or print block characters into
    a pipe, and a header is the one thing that must never be the reason a
    command's output is unreadable.
    """
    line = Text()
    line.append("sky.boss", style=Style(color=CLI_BRAND, bold=True))
    line.append(f"  ·  {version}", style=Style(color=CLI_FAINT))
    return line


def show(console: Console, version: str) -> bool:
    """Draw the mark, or say it could not.

    Returns False without printing when the mark would not survive the
    surface — too narrow, or not a terminal at all. The caller owns the
    fallback, because what to say instead is help's business, not the mark's.
    """
    if not console.is_terminal or console.width < WIDTH:
        return False
    for line in rows():
        console.print(line, no_wrap=True, crop=False)
    console.print(byline(version), no_wrap=True, crop=False)
    return True
