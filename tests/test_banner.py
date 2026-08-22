"""The mark — `docs/design/cli-header.png`, drawn in half-blocks. See [[header]].

The properties worth defending: the art stays a rectangle of known inks, every
painted line is exactly the panel's width whatever the version string does, the
mark refuses to draw rather than wrap or spill block characters into a pipe,
and its colours are the design system's own — undarkened, on purpose, which is
the one place a tested invariant is deliberately stepped around.
"""

from click.testing import CliRunner
from rich.console import Console

from cli import banner, cli
from cli.theme import BRAND, STYLES, SURFACE_2, TEXT, TEXT_3


# ============================================================================
# The picture
# ============================================================================


def test_the_art_is_a_rectangle_of_known_inks():
    """It is hand-editable by design, so the shape is what a test holds."""
    assert len(banner.ART) % 2 == 0, "half-blocks pair rows; an odd count loses one"
    assert len({len(row) for row in banner.ART}) == 1, "ragged art would print ragged"
    assert set("".join(banner.ART)) <= {"B", "D", "W", "."}


def test_every_painted_line_is_exactly_the_panel_wide():
    """A panel one cell short on any line reads as a broken rectangle, and the
    byline is the line that can vary — the version is not known here."""
    lines = banner.rows()
    assert len(lines) == len(banner.ART) // 2
    for line in lines:
        assert line.cell_len == banner.WIDTH


def test_the_byline_fits_whatever_git_describe_says():
    """The mockup's `v0.4.1` fills the panel exactly; a real describe can be
    three times that. Separators narrow first, the version truncates last."""
    for version in ("", "v0.4.1", "a0b4b6d-dirty", "1.2.0-14-gabc1234-dirty" * 3):
        assert banner.byline(version).cell_len == banner.WIDTH


def test_the_byline_shows_the_version_it_was_given():
    assert "v0.4.1" in banner.byline("v0.4.1").plain
    assert "SKYROW.LABS" in banner.byline("v0.4.1").plain


# ============================================================================
# Refusing to draw
# ============================================================================


def test_a_narrow_terminal_gets_no_mark_and_no_wrapping():
    console = Console(force_terminal=True, width=banner.WIDTH - 1, record=True)
    assert banner.show(console, "v1") is False
    assert console.export_text() == ""


def test_a_pipe_gets_no_block_characters():
    """Not a terminal, so not a picture — a wall of ▀ down a pipe is worse
    than no header at all."""
    console = Console(width=200, record=True)
    assert console.is_terminal is False
    assert banner.show(console, "v1") is False
    assert console.export_text() == ""


def test_the_fallback_is_a_name_not_a_smaller_mark():
    assert banner.plain("v0.4.1").plain == "toolbox  ·  v0.4.1"


# ============================================================================
# The colours, and why they are outside the floor
# ============================================================================


def test_the_mark_takes_the_design_system_undarkened():
    """The mark paints its own background, so it is in the canvas's position
    rather than the CLI's. If someone "corrects" these to the CLI derivations
    to satisfy the contrast floor, the brand mark dims for no reader."""
    assert banner._INK["B"] == BRAND
    assert banner._INK["D"] == TEXT_3
    assert banner._INK["W"] == TEXT
    assert banner._INK["."] == SURFACE_2


def test_the_mark_is_not_a_style_role():
    """`test_every_cli_role_survives_an_unknown_terminal_background` sweeps
    everything in STYLES and would fail on these. They are deliberately not in
    it: the mark's hues fail in *opposite* directions — the light handle on
    white, the dark slate on black — so no single floor could admit both, and
    the panel removes the question by painting a background."""
    for value in banner._INK.values():
        assert value not in {style.split()[-1] for style in STYLES.values()}


# ============================================================================
# Where it shows
# ============================================================================


def test_only_the_root_wears_the_mark(monkeypatch):
    """`tb read --help` is a reference page you may read three times a day; a
    banner over every one of them is a banner nobody sees."""
    drawn = []
    monkeypatch.setattr(banner, "show", lambda console, version: drawn.append(version) or True)
    CliRunner().invoke(cli, ["--help"])
    assert len(drawn) == 1
    CliRunner().invoke(cli, ["read", "--help"])
    assert len(drawn) == 1


def test_json_asks_for_an_envelope_and_gets_no_paint(monkeypatch):
    drawn = []
    monkeypatch.setattr(banner, "show", lambda console, version: drawn.append(version) or True)
    CliRunner().invoke(cli, ["--json"])
    assert drawn == []
