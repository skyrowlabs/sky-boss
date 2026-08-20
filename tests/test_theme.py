"""One palette, and nothing else allowed to name a colour.

The failure this prevents already happened next door: jam.sense's brand assets
used #38bcf7 while the app used --primary, because the hex had been written out
in two places. tb had three copies of its palette — the Rich theme, the --help
config, and the TUI's stylesheet — agreeing only because they were typed the
same afternoon.
"""

import re

from cli.helpers import PROJECT_ROOT
from cli.output import THEME
from cli.theme import BG, BRAND, DANGER, OK, STYLES, TEXT_2, TEXT_3, WARN, css_variables

HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def test_no_file_outside_the_palette_names_a_colour():
    """`.css` and `.js` are in here for a reason, and it is not symmetry.

    The surface's stylesheet used to be an f-string inside `app.py`, where a
    `*.py` glob saw it. Moving it to a file so it could be reloaded took it out
    of that glob — and a stylesheet is the single most natural place for someone
    to paste a hex. It would have passed in silence.

    The canvas widens the same hole twice over: it has a `.css` file *and* a
    `.js` file, both of which can name a colour, and the mockup this is built
    from is full of `rgba()` literals that would be perfectly easy to paste in.
    So the scan follows the surface rather than the language. Tokens reach the
    page through `cli/theme.py`'s `css_root`, injected by the server.

    Vendored third-party code is exempt. It is not ours to keep a palette out
    of, and rewriting someone's minified bundle to satisfy a house rule is a
    worse idea than the rule is a good one.
    """
    offenders = {}
    for pattern in ("*.py", "*.css", "*.js", "*.tcss"):
        for path in sorted((PROJECT_ROOT / "cli").rglob(pattern)):
            if path.name == "theme.py" or "vendor" in path.parts:
                continue
            found = HEX.findall(path.read_text())
            if found:
                offenders[str(path.relative_to(PROJECT_ROOT))] = found
    assert not offenders, f"a second palette is starting: {offenders}"


def test_no_stylesheet_smuggles_a_colour_past_the_hex_scan():
    """`rgba(56, 189, 248, .12)` is `#38bdf8` with extra steps, and the scan
    above would not see it. The mockup is built out of exactly these, so this is
    the form the drift would actually take here.

    `color-mix(in srgb, var(--tb-brand) 12%, transparent)` is the way to say the
    same thing in terms of a role, which is why the stylesheet uses it.
    """
    literals = re.compile(r"\b(rgba?|hsla?)\s*\(\s*[\d.]+[\s,]", re.IGNORECASE)
    offenders = {}
    for path in sorted((PROJECT_ROOT / "cli").rglob("*.css")):
        if "vendor" in path.parts:
            continue
        found = literals.findall(path.read_text())
        if found:
            offenders[str(path.relative_to(PROJECT_ROOT))] = found
    assert not offenders, f"a colour literal outside the palette: {offenders}"


def test_every_token_the_stylesheet_uses_is_defined():
    """An undefined custom property does not raise — it silently resolves to
    nothing, so a typo here is a colourless surface rather than an error. Better
    to fail in the suite than to launch a canvas painted in default black."""
    import re as _re

    from cli.theme import css_variables

    stylesheet = (PROJECT_ROOT / "cli/canvas/static/tb.css").read_text()
    used = set(_re.findall(r"var\(\s*--(tb-[a-z0-9-]+)", stylesheet))
    assert used, "found no --tb-* tokens at all — did the stylesheet move?"

    # The stylesheet builds a few of its own from the injected roles — a tint is
    # a role plus an alpha, not a new colour — so those count as defined too.
    derived = set(_re.findall(r"^\s*--(tb-[a-z0-9-]+)\s*:", stylesheet, _re.MULTILINE))
    defined = set(css_variables()) | derived

    assert used <= defined, f"undefined tokens: {sorted(used - defined)}"


def test_the_stylesheet_defines_no_token_the_palette_already_owns():
    """A role redefined in the stylesheet is a second source for it, and the two
    would drift. Deriving a *new* name from an injected one is fine; that is
    what `--tb-tint` is. Shadowing `--tb-brand` is not."""
    import re as _re

    from cli.theme import css_variables

    stylesheet = (PROJECT_ROOT / "cli/canvas/static/tb.css").read_text()
    defined_here = set(
        _re.findall(r"^\s*--(tb-[a-z0-9-]+)\s*:", stylesheet, _re.MULTILINE)
    )
    clashes = defined_here & set(css_variables())
    assert not clashes, f"the stylesheet redefines palette roles: {sorted(clashes)}"


def test_the_injected_root_block_carries_every_token():
    from cli.theme import css_root, css_variables

    block = css_root()
    for name, value in css_variables().items():
        assert f"--{name}:{value}" in block


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


def test_the_two_renderings_cover_the_same_hues():
    """One system, two renderings — and the check that they are the same system.

    The vocabularies differ on purpose: the CLI's roles name what a value *is*
    (`tb.ok`, `tb.path`), while the canvas's tokens name what the design system
    calls it (`--tb-ok`, `--tb-brand`). What has to hold across them is that
    every hue the CLI darkens ships to the canvas undarkened, so the two are the
    same palette seen under different lighting rather than two palettes.
    """
    tokens = css_variables()
    for name, raw in (
        ("tb-brand", BRAND),
        ("tb-ok", OK),
        ("tb-warn", WARN),
        ("tb-danger", DANGER),
        ("tb-text-2", TEXT_2),
        ("tb-text-3", TEXT_3),
    ):
        assert tokens[name] == raw, f"{name} is not the design system's value"


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


def test_the_canvas_shows_the_brand_at_full_strength():
    """The canvas paints BG itself, so it is the one surface that needs no
    concession. Darkening there would dim the brand against a background that
    never required it."""
    assert css_variables()["tb-brand"] == BRAND
    assert THEME.styles["tb.accent"].color.get_truecolor().hex.lower() != BRAND


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
