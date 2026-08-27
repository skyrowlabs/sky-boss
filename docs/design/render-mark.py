#!/usr/bin/env python3
"""Regenerate the two images of the mark from the mark itself.

Run from the repo root: `.venv/bin/python docs/design/render-mark.py`

**Neither PNG is a source.** `cli/banner.py`'s `ART` is the picture, and both
files here are renders of it — which is the only arrangement in which they
cannot disagree. They *did* disagree: the 2026-08-27 rename changed the word
the CLI prints without changing the drawing beside it, so `sb --help` greeted
you with a new name next to a picture of the old one for as long as that took
to notice. See [[header]].

- `cli-header.png` — the mark alone, one square block per art pixel.
- `readme-banner.png` — real `sb --help` captured through a pty and painted
  back, because the suite can prove the mechanism but cannot see whether the
  tower looks like a tower.

Colours come from `cli/theme.py`. Nothing here names one, which is the same
rule the hex scan enforces inside `cli/` — that scan does not reach this
directory, so this file keeps to it by hand.
"""

from __future__ import annotations

import os
import re
import select
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from cli import banner  # noqa: E402
from cli.theme import BG, BRAND, LOGO_BG, LOGO_BRAND, LOGO_DARK, LOGO_LIGHT, TEXT  # noqa: E402

INK = {"B": LOGO_BRAND, "D": LOGO_DARK, "W": LOGO_LIGHT, ".": LOGO_BG}
UPPER_HALF = "▀"
CHEVRON = "❯"   # drawn, not typed — see _draw_cell
SGR = re.compile(r"\x1b\[([0-9;]*)m")


def _font(bold: bool = False, size: int = 16):
    """A monospace face, asked for by description rather than by path.

    A hardcoded path would name a distro's font layout, which is the same class
    of thing as naming a host. Falls back to PIL's built-in rather than failing:
    a slightly wrong face is a worse render, an exception is no render.
    """
    if shutil.which("fc-match"):
        query = "monospace:bold" if bold else "monospace"
        out = subprocess.run(["fc-match", "-f", "%{file}", query],
                             capture_output=True, text=True).stdout.strip()
        if out and Path(out).exists():
            try:
                return ImageFont.truetype(out, size)
            except OSError:
                pass
    return ImageFont.load_default(size)


# ---------------------------------------------------------------- the mark


def render_mark(out: Path, scale: int = 12) -> None:
    """`ART` as squares, plus the byline, at the mark's own colours."""
    pad, cols = banner.PAD, banner.WIDTH
    art_h = len(banner.ART) * scale
    byline_h = 2 * scale                       # one terminal row = two art rows
    img = Image.new("RGB", (cols * scale, art_h + byline_h), LOGO_BG)
    draw = ImageDraw.Draw(img)

    for y, row in enumerate(banner.ART):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            px, py = (pad + x) * scale, y * scale
            draw.rectangle([px, py, px + scale - 1, py + scale - 1], fill=INK[ch])

    font = _font(size=int(scale * 1.55))
    y = art_h + (byline_h - int(scale * 1.55)) // 2 - 1
    x = 0.0
    for seg in _versionless_byline().render(_console()):
        colour = seg.style.color.get_truecolor() if seg.style and seg.style.color else None
        if seg.text.strip() and colour:
            draw.text((x, y), seg.text, font=font,
                      fill=(colour.red, colour.green, colour.blue))
        x += draw.textlength(seg.text, font=font)

    img.save(out)
    print(f"wrote {out.relative_to(ROOT)} {img.width}x{img.height}")


def _console():
    from rich.console import Console
    return Console()



# -------------------------------------------------------------- the banner


def capture(argv: list[str], cols: int = 80, rows: int = 60) -> str:
    """Run a command on a real pty so it believes it is a terminal.

    `sb --help` refuses to draw the mark down a pipe — deliberately — so a
    screenshot of it cannot be taken by reading stdout.
    """
    import fcntl
    import pty
    import struct
    import termios

    pid, fd = pty.fork()
    if pid == 0:
        os.environ.update(COLUMNS=str(cols), LINES=str(rows), TERM="xterm-256color",
                          COLORTERM="truecolor", FORCE_COLOR="1")
        os.execvp(argv[0], argv)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    chunks: list[bytes] = []
    while select.select([fd], [], [], 10)[0]:
        try:
            data = os.read(fd, 65536)
        except OSError:
            break
        if not data:
            break
        chunks.append(data)
    os.waitpid(pid, 0)
    return b"".join(chunks).decode("utf-8", "replace")


def _cells(text: str):
    """ANSI into a grid of (char, fg, bg, bold). Truecolor SGR only, which is
    all rich emits here."""
    default = _rgb(TEXT)
    grid, row = [], []
    fg, bg, bold = default, None, False
    i = 0
    while i < len(text):
        m = SGR.match(text, i)
        if m:
            parts = m.group(1).split(";") or [""]
            k = 0
            while k < len(parts):
                p = parts[k] or "0"
                if p == "0":
                    fg, bg, bold = default, None, False
                elif p == "1":
                    bold = True
                elif p == "22":
                    bold = False
                elif p == "39":
                    fg = default
                elif p == "49":
                    bg = None
                elif p == "38" and parts[k + 1:k + 2] == ["2"]:
                    fg = tuple(int(v) for v in parts[k + 2:k + 5]); k += 4
                elif p == "48" and parts[k + 1:k + 2] == ["2"]:
                    bg = tuple(int(v) for v in parts[k + 2:k + 5]); k += 4
                k += 1
            i = m.end()
            continue
        ch = text[i]
        i += 1
        if ch == "\n":
            grid.append(row); row = []
        elif ch not in ("\r", "\x1b"):
            row.append((ch, fg, bg, bold))
    if row:
        grid.append(row)
    return grid


def _rgb(token: str) -> tuple[int, int, int]:
    """A `#rrggbb` from the palette into a triple. The literal stays in
    `theme.py`; this only reshapes it."""
    return tuple(int(token[i:i + 2], 16) for i in (1, 3, 5))


def _versionless_byline():
    """The mark's byline with the version segment removed.

    The CLI prints the real `git describe` because a header stating a version it
    is not is worse than one with no version — but a README is read long after
    any hash means anything, and `36927d9-dirty` in the first thing a reader sees
    is that same lie in a louder place. So the derived image drops the segment
    rather than freezing one. What is left cannot go stale.
    """
    from rich.style import Style
    from rich.text import Text

    dim = Style(color=LOGO_DARK, bgcolor=LOGO_BG)
    label = Style(color=LOGO_LIGHT, bgcolor=LOGO_BG)
    brand = Style(color=LOGO_BRAND, bgcolor=LOGO_BG)
    line = Text()
    line.append(" " * (banner.PAD + banner.BYLINE_INDENT), style=Style(bgcolor=LOGO_BG))
    line.append("by ", style=dim)
    line.append("SKYROW.", style=label)
    line.append("LABS", style=brand)
    line.append("   ·   ", style=dim)
    line.append("sb --help", style=label)
    line.pad_right(max(0, banner.WIDTH - line.cell_len))
    line.stylize(Style(bgcolor=LOGO_BG))
    return line


def render_banner(out: Path, cell_w: int = 12, cell_h: int = 21) -> None:
    text = capture([str(ROOT / "sb"), "--help"])
    grid = _cells(text)

    # The byline is the row directly under the art. Swap it for the
    # version-free one before the prompt row shifts every index by one.
    art_rows = len(banner.ART) // 2
    grid[art_rows] = [
        (ch, (c.red, c.green, c.blue) if (c := seg.style.color.get_truecolor()
                                          if seg.style and seg.style.color else None) else _rgb(TEXT),
         (b.red, b.green, b.blue) if (b := seg.style.bgcolor.get_truecolor()
                                      if seg.style and seg.style.bgcolor else None) else None,
         False)
        for seg in _versionless_byline().render(_console()) for ch in seg.text
    ]

    grid.insert(0, [(CHEVRON, _rgb(BRAND), None, True), (" ", _rgb(TEXT), None, False)]
                + [(c, _rgb(TEXT), None, False) for c in "sb"])

    img = Image.new("RGB", (max(len(r) for r in grid) * cell_w, len(grid) * cell_h),
                    _rgb(BG))
    draw = ImageDraw.Draw(img)
    regular, heavy = _font(size=16), _font(bold=True, size=16)
    for y, row in enumerate(grid):
        for x, (ch, fg, bg, bold) in enumerate(row):
            px, py = x * cell_w, y * cell_h
            if bg:
                draw.rectangle([px, py, px + cell_w - 1, py + cell_h - 1], fill=bg)
            if ch == UPPER_HALF:
                # Drawn, not typed: the half-block is the mark's pixel, and a
                # font's idea of its metrics would leave hairlines between rows.
                draw.rectangle([px, py, px + cell_w - 1, py + cell_h // 2 - 1], fill=fg)
            elif ch == CHEVRON:
                # Also drawn, for a duller reason: whatever `fc-match monospace`
                # resolves to on this machine may not carry U+276F, and a
                # missing glyph renders as tofu in the top-left of the banner.
                mid = py + cell_h // 2
                draw.line([(px + 3, py + 4), (px + 8, mid), (px + 3, py + cell_h - 5)],
                          fill=fg, width=2, joint="curve")
            elif ch.strip():
                draw.text((px + 1, py + 2), ch, font=heavy if bold else regular, fill=fg)
    img.save(out)
    print(f"wrote {out.relative_to(ROOT)} {img.width}x{img.height}")


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    render_mark(here / "cli-header.png")
    render_banner(here / "readme-banner.png")
