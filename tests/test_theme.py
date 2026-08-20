"""One palette, and nothing else allowed to name a colour.

The failure this prevents already happened next door: jam.sense's brand assets
used #38bcf7 while the app used --primary, because the hex had been written out
in two places. tb had three copies of its palette — the Rich theme, the --help
config, and the TUI's stylesheet — agreeing only because they were typed the
same afternoon.
"""

import re

from cli.helpers import PROJECT_ROOT
from cli.output import THEME, TUI_THEME
from cli.theme import BG, BRAND, OK, STYLES, TEXT_2, TEXT_3, TUI_STYLES

HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def test_no_module_outside_the_palette_names_a_colour():
    offenders = {}
    for path in sorted((PROJECT_ROOT / "cli").rglob("*.py")):
        if path.name == "theme.py":
            continue
        found = HEX.findall(path.read_text())
        if found:
            offenders[str(path.relative_to(PROJECT_ROOT))] = found
    assert not offenders, f"a second palette is starting: {offenders}"


def test_the_rich_theme_is_built_from_the_palette():
    assert set(THEME.styles) >= set(STYLES)


def test_every_style_role_resolves_to_a_colour():
    # A typo'd hex parses as a style with no colour rather than raising, so the
    # role would silently render as plain text.
    for name in STYLES:
        style = THEME.styles[name]
        assert style.color is not None, f"{name} has no colour"


# --------------------------------------------------------- the two renderings

WHITE = "#ffffff"
FLOOR = 3.5  # the smallest ratio a CLI role may have against either background


def _luminance(hex_colour: str) -> float:
    raw = hex_colour.lstrip("#")
    channels = []
    for pair in (raw[0:2], raw[2:4], raw[4:6]):
        value = int(pair, 16) / 255
        channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_the_two_renderings_cover_the_same_roles():
    """A role in one and not the other renders as plain text on that surface."""
    assert set(STYLES) == set(TUI_STYLES)


def test_every_cli_role_survives_an_unknown_terminal_background():
    """The reason the CLI does not simply use the design system's tokens.

    Skyrow's system is dark-only by declaration and its colours are unreadable
    on white — brand measures 2.14 there, ok 1.74, warn 1.44. tb renders into
    whoever's terminal, so each CLI role is the smallest darkening of its token
    that clears this floor against *both* backgrounds. If someone ever
    "corrects" one of these back to the raw token, this fails.
    """
    failures = {}
    for name in STYLES:
        colour = THEME.styles[name].color.get_truecolor().hex
        for background in (WHITE, BG):
            ratio = _contrast(colour, background)
            if ratio < FLOOR:
                failures[f"{name} on {background}"] = round(ratio, 2)
    assert not failures, f"unreadable CLI roles: {failures}"


def test_the_surface_shows_the_brand_at_full_strength():
    """The TUI paints BG itself, so it is the one place that needs no
    concession. Darkening there would dim the brand against a background that
    never required it."""
    assert TUI_THEME.styles["tb.accent"].color.get_truecolor().hex.lower() == BRAND
    assert TUI_THEME.styles["tb.ok"].color.get_truecolor().hex.lower() == OK
    assert TUI_THEME.styles["tb.muted"].color.get_truecolor().hex.lower() == TEXT_3
    assert TUI_THEME.styles["tb.label"].color.get_truecolor().hex.lower() == TEXT_2


def test_the_cli_and_the_surface_do_not_share_a_rendering():
    """If these ever converge, one of the two surfaces is wrong."""
    assert THEME.styles["tb.accent"].color != TUI_THEME.styles["tb.accent"].color


def test_the_tokens_still_match_the_design_system():
    """`theme.py` says it copied the system verbatim. This checks that it did.

    The vendored file is the system's own `colors_and_type.css`. Copying by
    hand is the right call for thirty constants — a generator would be more
    machinery than the thing it generates — but a copy with nothing checking it
    is how the palette drifted the first time.
    """
    from cli import theme

    source = (PROJECT_ROOT / "docs/design/skyrow-colors_and_type.css").read_text()
    declared = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", source))

    # Constant in theme.py -> token name in the stylesheet.
    mapping = {
        "BG": "bg",
        "SURFACE": "surface",
        "SURFACE_2": "surface-2",
        "TEXT": "text",
        "TEXT_2": "text-2",
        "TEXT_3": "text-3",
        "BRAND": "brand",
        "WIND": "bb",
        "SIGNAL": "mh",
        "OK": "ok",
        "WARN": "warn",
        "DANGER": "danger",
    }
    drifted = {
        name: (getattr(theme, name), declared.get(token))
        for name, token in mapping.items()
        if getattr(theme, name).lower() != (declared.get(token) or "").lower()
    }
    assert not drifted, f"theme.py has drifted from the design system: {drifted}"
