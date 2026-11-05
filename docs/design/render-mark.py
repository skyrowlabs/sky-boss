#!/usr/bin/env python3
"""Regenerate the images of the mark from the mark itself.

Run from the repo root: `.venv/bin/python docs/design/render-mark.py`,
adding `--install` to also write the icon into the XDG icon theme.

**No PNG here is a source.** `skyboss/banner.py`'s `ART` is the picture, and every
file this writes is a render of it — which is the only arrangement in which
they cannot disagree. They *did* disagree: the 2026-08-27 rename changed the
word the CLI prints without changing the drawing beside it, so `sb --help`
greeted you with a new name next to a picture of the old one for as long as
that took to notice. See [[header]].

- `cli-header.png` — the mark alone, one square block per art pixel.
- `hero.svg` and `ideas.svg` — the README's opening pictures, written as SVG
  from `ART` and the theme. The hero is animated, and SMIL plays inside an
  `<img>` on GitHub.
- `app-icon.png` — the tower alone on a square, for a desktop launcher. Third
  because the alternative was cropping it out of `cli-header.png`, and a crop
  is a second copy of the drawing with nothing holding it to the first.

Colours come from `skyboss/theme.py`. Nothing here names one, which is the same
rule the hex scan enforces inside `skyboss/` — that scan does not reach this
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

from skyboss import banner  # noqa: E402
from skyboss.theme import (  # noqa: E402
    BG,
    BRAND,
    DANGER,
    LOGO_BEACON,
    LOGO_BG,
    LOGO_BRAND,
    LOGO_DARK,
    LOGO_LIGHT,
    OK,
    SURFACE,
    TEXT,
    TEXT_2,
    TEXT_3,
    WARN,
)

INK = banner._INK  # one table of inks, so the PNGs cannot paint a letter differently
UPPER_HALF = "▀"
CHEVRON = "❯"  # drawn, not typed — see _draw_cell
SGR = re.compile(r"\x1b\[([0-9;]*)m")


def _font(bold: bool = False, size: int = 16):
    """A monospace face, asked for by description rather than by path.

    A hardcoded path would name a distro's font layout, which is the same class
    of thing as naming a host. Falls back to PIL's built-in rather than failing:
    a slightly wrong face is a worse render, an exception is no render.
    """
    if shutil.which("fc-match"):
        query = "monospace:bold" if bold else "monospace"
        out = subprocess.run(["fc-match", "-f", "%{file}", query], capture_output=True, text=True).stdout.strip()
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
    byline_h = 2 * scale  # one terminal row = two art rows
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
            draw.text((x, y), seg.text, font=font, fill=(colour.red, colour.green, colour.blue))
        x += draw.textlength(seg.text, font=font)

    img.save(out)
    print(f"wrote {out.relative_to(ROOT)} {img.width}x{img.height}")


def _console():
    from rich.console import Console

    return Console()


# ------------------------------------------------------------------ the icon

# Every size a desktop is likely to ask for. Rendered rather than resampled,
# so each is drawn at whole blocks instead of being a blurred copy of one.
ICON_SIZES = (256, 128, 64, 48)


def _tower() -> tuple[list[str], int, int]:
    """The left-hand drawing, cropped to its own ink.

    Found rather than measured: the tower is the first inked run of columns,
    ending at the gutter before the lettering. A hardcoded column would slice
    the mark in half the next time it is redrawn, which is the exact drift
    this file exists to prevent.
    """
    width = len(banner.ART[0])
    inked = [any(row[x] != "." for row in banner.ART) for x in range(width)]
    left = inked.index(True)
    right, gap = left, 0
    for x in range(left, width):
        if inked[x]:
            right, gap = x, 0
        else:
            gap += 1
            if gap >= 2:  # the gutter; the lettering starts past it
                break
    rows = [row[left : right + 1] for row in banner.ART]
    return rows, right - left + 1, len(rows)


def render_icon(out: Path, size: int = 256) -> None:
    """The tower on a square, at one whole block per art pixel.

    **The lettering is dropped on purpose.** It is unreadable below about
    128px, and a launcher already carries the name in its label — an icon
    keeping it would spend most of its pixels on a smear of the one thing
    the desktop has already said.

    The block is an integer, so the edges stay hard at 48px rather than
    turning to grey fringe under a smooth resample.
    """
    rows, w, h = _tower()
    margin = max(1, size // 16)
    block = max(1, (size - 2 * margin) // h)
    ox, oy = (size - w * block) // 2, (size - h * block) // 2

    img = Image.new("RGB", (size, size), LOGO_BG)
    draw = ImageDraw.Draw(img)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            px, py = ox + x * block, oy + y * block
            draw.rectangle([px, py, px + block - 1, py + block - 1], fill=INK[ch])

    img.save(out)
    try:
        where: Path | str = out.relative_to(ROOT)
    except ValueError:
        where = out  # an installed icon lives outside the repo
    print(f"wrote {where} {img.width}x{img.height}")


def install_icons() -> None:
    """Write the icon into the XDG icon theme, so a desktop entry can name it
    as `sky-boss` instead of carrying a path.

    Opt-in, because it is the only thing here that writes outside the
    repository. The destination is the freedesktop standard one — a
    convention, not a machine — which is what keeps it sayable in a tracked
    file at all.
    """
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    for size in ICON_SIZES:
        into = data / f"icons/hicolor/{size}x{size}/apps"
        into.mkdir(parents=True, exist_ok=True)
        render_icon(into / "sky-boss.png", size)


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
        os.environ.update(
            COLUMNS=str(cols), LINES=str(rows), TERM="xterm-256color", COLORTERM="truecolor", FORCE_COLOR="1"
        )
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
                elif p == "38" and parts[k + 1 : k + 2] == ["2"]:
                    fg = tuple(int(v) for v in parts[k + 2 : k + 5])
                    k += 4
                elif p == "48" and parts[k + 1 : k + 2] == ["2"]:
                    bg = tuple(int(v) for v in parts[k + 2 : k + 5])
                    k += 4
                k += 1
            i = m.end()
            continue
        ch = text[i]
        i += 1
        if ch == "\n":
            grid.append(row)
            row = []
        elif ch not in ("\r", "\x1b"):
            row.append((ch, fg, bg, bold))
    if row:
        grid.append(row)
    return grid


def _rgb(token: str) -> tuple[int, int, int]:
    """A `#rrggbb` from the palette into a triple. The literal stays in
    `theme.py`; this only reshapes it."""
    return tuple(int(token[i : i + 2], 16) for i in (1, 3, 5))


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


# ---------------------------------------------------------------- the README


MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace"
SANS = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"
DISPLAY = "'Space Grotesk', 'Segoe UI', Helvetica, Arial, sans-serif"

# The roll-call card in the hero is an illustration, so its rows are invented
# and say so in the alt text. They are deliberately nobody's real projects.
HERO_ROWS = (("api-gateway", "ok", OK), ("nightly-backup", "partial", WARN), ("edge-sensors", "unreachable", DANGER))


def _runs(rows: list[str], letter: str, cell: int) -> str:
    """One `<rect>` per horizontal run of `letter`, so a 22-row drawing is a few
    dozen elements rather than a few hundred."""
    out = []
    for y, row in enumerate(rows):
        x = 0
        while x < len(row):
            if row[x] != letter:
                x += 1
                continue
            start = x
            while x < len(row) and row[x] == letter:
                x += 1
            out.append(f'<rect x="{start * cell}" y="{y * cell}" width="{(x - start) * cell}" height="{cell}"/>')
    return "".join(out)


def render_hero(out: Path, cell: int = 8) -> None:
    """The README's first picture: `ART` as SVG, alive, beside a roll-call.

    It replaces a screenshot of `sb --help`, which went stale every time a
    command was added and showed the mark above a page of reference text. This
    is the mark and the pitch, and the motion is SMIL so it plays inside an
    `<img>` on GitHub: the warning light blinks, the cab's glass flickers in
    three panes, and a radar ring leaves the light and lights each roll-call
    row as it passes. Static fallbacks are the first frame, which is complete.
    """
    art = list(banner.ART)
    ox, oy = 40, 22
    paint = "".join(
        f'<g fill="{colour}">{_runs(art, letter, cell)}</g>'
        for letter, colour in banner._INK.items()
        if letter not in ".GR"
    )
    glass = []
    for third, begin in enumerate(("0s", "1s", "2s")):
        cols = [row[:15] for row in art]
        masked = ["".join(c if c == "G" and x // 5 == third else "." for x, c in enumerate(r)) for r in cols]
        glass.append(
            f'<g fill="{LOGO_LIGHT}"><animate attributeName="opacity" values="1;1;0.4;1" keyTimes="0;0.7;0.8;1" '
            f'dur="3s" begin="{begin}" repeatCount="indefinite"/>{_runs(masked, "G", cell)}</g>'
        )
    bx, by = next((x, y) for y, r in enumerate(art) for x, c in enumerate(r) if c == "R")
    beacon_x, beacon_y = ox + bx * cell + cell // 2, oy + by * cell + cell // 2
    blink = '<animate attributeName="opacity" values="{};{}" dur="1.2s" calcMode="discrete" repeatCount="indefinite"/>'
    word_x = ox + banner.BYLINE_INDENT * cell
    word_bottom = oy + max(y for y, r in enumerate(art) if "B" in r[banner.BYLINE_INDENT :]) * cell + cell

    ring = (
        '<circle cx="{x}" cy="{y}" r="8" fill="none" stroke="{c}" stroke-width="2" opacity="0">'
        '<animate attributeName="r" values="8;900" dur="4s" begin="{b}" repeatCount="indefinite"/>'
        '<animate attributeName="opacity" values="0.45;0" dur="4s" begin="{b}" repeatCount="indefinite"/></circle>'
    )
    rings = "".join(ring.format(x=beacon_x, y=beacon_y, c=BRAND, b=b) for b in ("0s", "2s"))

    rows = []
    for i, (name, state, colour) in enumerate(HERO_ROWS):
        y = 133 + 28 * i
        lit = f"0;{0.24 + 0.02 * i:.2f};{0.30 + 0.02 * i:.2f};1"
        rows.append(
            f'<circle cx="662" cy="{y}" r="4.5" fill="{colour}" opacity="0.3"><animate attributeName="opacity" '
            f'values="0.3;0.3;1;0.3" keyTimes="{lit}" dur="2s" repeatCount="indefinite"/></circle>'
            f'<text x="676" y="{y + 5}" font-size="14" fill="{TEXT}">{name}</text>'
            f'<text x="936" y="{y + 5}" font-size="14" fill="{colour}" text-anchor="end">{state}</text>'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 300" width="1000" height="300" role="img" aria-label="sky.boss: a pixel control tower beside the wordmark, sending a radar ring to an illustrative roll-call of three projects">
  <title>sky.boss — one CLI for watching what other tools are doing</title>
  <defs>
    <clipPath id="clip"><rect width="1000" height="300" rx="18"/></clipPath>
    <radialGradient id="glow" cx="0.12" cy="0.2" r="0.7"><stop offset="0" stop-color="{BRAND}" stop-opacity="0.12"/><stop offset="1" stop-color="{BRAND}" stop-opacity="0"/></radialGradient>
    <pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="{TEXT}" fill-opacity="0.06"/></pattern>
    <filter id="soft" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="5"/></filter>
  </defs>
  <g clip-path="url(#clip)">
    <rect width="1000" height="300" fill="{BG}"/>
    <rect width="1000" height="300" fill="url(#glow)"/>
    <rect width="1000" height="300" fill="url(#dots)"/>
    {rings}
    <g transform="translate({ox},{oy})">{paint}{"".join(glass)}
      <circle cx="{bx * cell + cell // 2}" cy="{by * cell + cell // 2}" r="9" fill="{LOGO_BEACON}" filter="url(#soft)">{blink.format("0.9", "0.15")}</circle>
      <g fill="{LOGO_BEACON}">{blink.format("1", "0.35")}{_runs(art, "R", cell)}</g>
    </g>
    <text x="{word_x}" y="{word_bottom + 28}" font-family="{MONO}" font-size="13" letter-spacing="1" fill="{TEXT_2}">by <tspan fill="{TEXT}">SKYROW.</tspan><tspan fill="{BRAND}">LABS</tspan></text>
    <text font-family="{SANS}" font-size="18" fill="{TEXT_2}"><tspan x="{ox}" y="232">One CLI for watching what other tools are doing —</tspan><tspan x="{ox}" y="258">on this machine and across the projects you keep here.</tspan></text>
    <rect x="640.5" y="40.5" width="311" height="219" rx="14" fill="{SURFACE}" stroke="{BRAND}" stroke-opacity="0.55"/>
    <g font-family="{MONO}">
      <circle cx="660" cy="62" r="4" fill="{OK}"/>
      <text x="672" y="67" font-size="13" fill="{TEXT_2}">#1</text>
      <text x="696" y="67" font-size="13" fill="{TEXT}">roll-call</text>
      <text x="896" y="67" font-size="12" fill="{TEXT_2}" text-anchor="end">2s ago</text>
      <rect x="904.5" y="54.5" width="34" height="18" rx="4" fill="none" stroke="{TEXT_3}"/>
      <text x="921.5" y="67" font-size="10" fill="{TEXT_2}" text-anchor="middle">PIN</text>
      <path d="M 641,84 H 951 M 641,216 H 951" stroke="{TEXT_3}" stroke-opacity="0.6"/>
      <text x="656" y="106" font-size="11" letter-spacing="0.8" fill="{TEXT_2}">PROJECT</text>
      <text x="936" y="106" font-size="11" letter-spacing="0.8" fill="{TEXT_2}" text-anchor="end">STATE</text>
      <path d="M 656,114 H 936" stroke="{TEXT_3}" stroke-opacity="0.6"/>
      {"".join(rows)}
      <text x="656" y="242" font-size="12" fill="{TEXT_2}">partial · 3 projects</text>
      <text x="936" y="242" font-size="12" fill="{TEXT_2}" text-anchor="end">exit 3 · 0.21s</text>
    </g>
  </g>
  <rect x="0.5" y="0.5" width="999" height="299" rx="18" fill="none" stroke="{TEXT_3}" stroke-opacity="0.6"/>
</svg>
"""
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} 1000x300")


# The four ideas, as cards. The icons are 24-unit stroke paths, so they read
# at any size and carry no colour of their own.
IDEAS = (
    (
        "One command acts",
        BRAND,
        '<polygon points="6 4 20 12 6 20 6 4"/>',
        ("sb run is the only one. Everything else reads,", "so a window can re-run a read, never a write."),
    ),
    (
        "Data, never print",
        OK,
        '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18M9 9v10"/>',
        ("One envelope — ok, partial, data, warnings —", "drawn by whoever consumes it. --json hands it over."),
    ),
    (
        "Never guesses",
        WARN,
        '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5"/>',
        ("sb data takes JSON; sb read shows output verbatim", "and says so. There is no --pretty that guesses."),
    ),
    (
        "Not in the credential path",
        TEXT,
        '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
        ("External CLIs keep their own authentication.", "sky.boss never holds a key."),
    ),
)


def render_ideas(out: Path) -> None:
    """The four ideas the README opens with, as a 2×2 of cards.

    The sentences are repeated in the image's alt text in full, because an
    image of a sentence is not searchable and a screen reader is owed it.
    """
    cards = []
    for i, (title, colour, icon, lines) in enumerate(IDEAS):
        x, y = (i % 2) * 507, (i // 2) * 124
        body = "".join(f'<tspan x="{x + 84}" dy="{0 if k == 0 else 21}">{line}</tspan>' for k, line in enumerate(lines))
        cards.append(
            f'<rect x="{x + 0.5}" y="{y + 0.5}" width="492" height="111" rx="14" fill="{BG}" stroke="{TEXT_3}" stroke-opacity="0.6"/>'
            f'<rect x="{x + 22}" y="{y + 22}" width="44" height="44" rx="10" fill="{colour}" fill-opacity="0.14"/>'
            f'<g transform="translate({x + 32},{y + 32})" fill="none" stroke="{colour}" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round">{icon}</g>'
            f'<text x="{x + 84}" y="{y + 40}" font-family="{DISPLAY}" font-size="18" font-weight="700" fill="{TEXT}">{title}</text>'
            f'<text y="{y + 66}" font-family="{SANS}" font-size="14" fill="{TEXT_2}">{body}</text>'
        )
    alt = " ".join(f"{t}: {' '.join(lines)}" for t, _, _, lines in IDEAS)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 236" width="1000" height="236" role="img" '
        f'aria-label="{alt}">\n  <title>Four ideas</title>\n  {"".join(cards)}\n</svg>\n'
    )
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} 1000x236")


def _paint(grid, out: Path, cell_w: int, cell_h: int) -> None:
    """A grid of cells onto a PNG. Shared, so two images cannot draw differently."""
    img = Image.new("RGB", (max((len(r) for r in grid), default=1) * cell_w, len(grid) * cell_h), _rgb(BG))
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
                draw.line([(px + 3, py + 4), (px + 8, mid), (px + 3, py + cell_h - 5)], fill=fg, width=2, joint="curve")
            elif ch.strip():
                draw.text((px + 1, py + 2), ch, font=heavy if bold else regular, fill=fg)
    img.save(out)
    print(f"wrote {out.relative_to(ROOT)} {img.width}x{img.height}")


def render_session(out: Path, cols: int = 88, cell_w: int = 12, cell_h: int = 21) -> None:
    """A real terminal session, captured and painted.

    The banner above is a picture of `--help`, which shows the mark and says
    nothing about what the tool *does*. This runs actual commands and paints
    what actually came back — the band under a `run`, a shaped table with its
    dimensions, and the tint, which is the one thing the README's console blocks
    cannot carry as text.

    **Isolated home and state, and a neutral path.** Same obligation
    `render-canvas.mjs` states at length: a tool is an argv sky.boss will run, and
    a checkout's path names whoever's home it sits in. The sample is copied out
    of `sample/` to a temporary directory so the argv drawn on the prompt line
    is one anybody could have typed.
    """
    import shutil
    import tempfile

    here = Path(__file__).resolve().parent
    demo = Path(tempfile.gettempdir()) / "sb-demo"
    shutil.rmtree(demo, ignore_errors=True)
    demo.mkdir(parents=True)
    for name in ("agent.log", "runs.jsonl"):
        shutil.copy(here / "sample" / name, demo / name)

    home = Path(tempfile.mkdtemp(prefix="sb-shot-home-"))
    state = Path(tempfile.mkdtemp(prefix="sb-shot-state-"))
    saved = {k: os.environ.get(k) for k in ("SB_HOME", "SB_STATE")}
    os.environ["SB_HOME"] = str(home)
    os.environ["SB_STATE"] = str(state)

    commands = [
        ["run", "--", "echo", "hello"],
        ["data", "--from", "jsonl", str(demo / "runs.jsonl")],
    ]

    try:
        grid: list = []
        for argv in commands:
            grid.append(
                [(CHEVRON, _rgb(BRAND), None, True), (" ", _rgb(TEXT), None, False)]
                + [(c, _rgb(TEXT), None, False) for c in "sb " + " ".join(argv)]
            )
            rows = _cells(capture([str(ROOT / "sb"), *argv], cols=cols))
            while rows and not any(ch.strip() for ch, *_ in rows[-1]):
                rows.pop()  # the pty's trailing blanks are not part of the answer
            grid.extend(rows)
            grid.append([])
        # The final blank row is kept, not popped: a 16px font in a 21px cell
        # puts its descenders on the image's last pixel, and the bottom row came
        # out shaved in half. Padding here rather than in `_paint`, which the
        # mark and the banner share and are pixel-exact against.
        _paint(grid, out, cell_w, cell_h)
    finally:
        for key, value in saved.items():
            os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(state, ignore_errors=True)
        shutil.rmtree(demo, ignore_errors=True)


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    render_mark(here / "cli-header.png")
    render_hero(here / "hero.svg")
    render_ideas(here / "ideas.svg")
    render_icon(here / "app-icon.png")
    render_session(here / "readme-session.png")
    if "--install" in sys.argv:
        install_icons()
