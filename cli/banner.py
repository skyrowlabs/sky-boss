"""The mark — `docs/design/cli-header.png`, drawn in half-blocks.

**The header is the PNG, not a picture of it.** A terminal cannot show an
image, but the source *is* pixel art: a 5x7 blocky face for the wordmark and a
chunky toolbox glyph, both on one grid. Sampled on that grid — one art pixel
per cell — the letters come back crisp rather than resampled to mush, which is
what any "scale the image down" approach produces at this size. The grid was
measured off the PNG (11.2px per column, 8.86px per row) rather than guessed.

**Half-blocks, so the aspect survives.** A terminal cell is about twice as tall
as it is wide, so one art pixel per *cell* would render the mark stretched to
double height. `\u2580` splits a cell into two square-ish halves — foreground on
top, background below — which puts 14 art rows into 7 terminal rows at the
proportions the designer drew.

**The mark paints its own background**, and that is what lets it use the design
system at full strength instead of the CLI's darkened derivations ([[theme]]).
The derivations exist because tb renders into a terminal whose background
nobody here knows; painting one removes the unknown, exactly as the canvas
does. It is also the only answer available: the mark's own hues fail in
*opposite* directions — the light handle disappears on white, the dark slate
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
# dark slate of the toolbox's band and latch, `W` the light handle and clasps,
# `.` the mark's own background. Edit this and the mark changes — it is the
# picture, not a cache of one.
ART: tuple[str, ...] = (
    "......WWWWWW...................................................",
    "......W....W...................................................",
    "......W....W...................................................",
    "...BBBBBBBBBBBB.......BBBBB.BBBBB.BBBBB.B.....BBBB..BBBBB.B...B",
    "..BBBBBBBBBBBBBB........B...B...B.B...B.B.....B...B.B...B..B.B.",
    "DDDBWDDDDDDDDBWDDD......B...B...B.B...B.B.....BBBBB.B...B..BBB.",
    "DDD.WDDDDDDDD.WDDD......B...B...B.B...B.B.....B...B.B...B...B..",
    "BBBBBBBBBBBBBBBBBB......B...B...B.B...B.B.....B...B.B...B..BBB.",
    "BBBBBBBBBBBBBBBBBB......B...B...B.B...B.B.....B...B.B...B..B.B.",
    "BBBBBBDDDDDDBBBBBB......B...BBBBB.BBBBB.BBBBB.BBBB..BBBBB.B...B",
    "BBBBBBDDDDDDBBBBBB.............................................",
    "BBBBBBDDDDDDBBBBBB.............................................",
    "BBBBBBBBBBBBBBBBBB.............................................",
    "BBBBBBBBBBBBBBBBBB.............................................",
)

# Room either side of the art, inside the painted panel.
PAD = 2

WIDTH = len(ART[0]) + PAD * 2

_INK = {"B": LOGO_BRAND, "D": LOGO_DARK, "W": LOGO_LIGHT, ".": LOGO_BG}

# Where the byline sits: under the wordmark, not under the icon.
BYLINE_INDENT = 22


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
    """`by SKYROW.LABS · <version> · tb --help`, on the panel.

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
        fixed = len("by SKYROW.LABS") + 2 * len(gap) + len("tb --help")
        if fixed + len(version) <= room:
            break
    else:  # both gaps too wide even before the version — trim it to fit
        gap = " · "
        fixed = len("by SKYROW.LABS") + 2 * len(gap) + len("tb --help")
    shown = version[: max(0, room - fixed)]

    line = Text()
    line.append(" " * (PAD + BYLINE_INDENT), style=Style(bgcolor=LOGO_BG))
    line.append("by ", style=dim)
    line.append("SKYROW.", style=label)
    line.append("LABS", style=brand)
    line.append(gap, style=dim)
    line.append(shown, style=label)
    line.append(gap, style=dim)
    line.append("tb --help", style=label)
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
    line.append("toolbox", style=Style(color=CLI_BRAND, bold=True))
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
