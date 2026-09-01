"""One palette, and nothing else allowed to name a colour.

The failure this prevents already happened next door: jam.sense's brand assets
used #38bcf7 while the app used --primary, because the hex had been written out
in two places. sky.boss had three copies of its palette — the Rich theme, the --help
config, and the TUI's stylesheet — agreeing only because they were typed the
same afternoon.
"""

import math
import re

from cli.helpers import PROJECT_ROOT
from cli.output import THEME
from cli.theme import BG, BRAND, DANGER, OK, PAINTED, STYLES, TEXT, TEXT_2, TEXT_3, WARN, css_variables

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

    `color-mix(in srgb, var(--sb-brand) 12%, transparent)` is the way to say the
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
    nothing, so a typo here is a colourless surface rather than an error.

    **A token used with a fallback is exempt, and that is the real rule.**
    `var(--sb-scale, 2)` names something the *server* injects from
    `sb ui --scale` rather than something the palette owns, and it carries a
    default precisely so a failed substitution renders at the normal size
    instead of collapsing. A bare `var(--sb-brand)` has no such safety net,
    which is why only bare uses have to be accounted for.
    """
    import re as _re

    from cli.theme import css_variables

    stylesheet = (PROJECT_ROOT / "cli/canvas/static/sb.css").read_text()
    bare = set(_re.findall(r"var\(\s*--(sb-[a-z0-9-]+)\s*\)", stylesheet))
    assert bare, "found no --sb-* tokens at all — did the stylesheet move?"

    # The stylesheet builds a few of its own from the injected roles — a tint is
    # a role plus an alpha, not a new colour — so those count as defined too.
    derived = set(_re.findall(r"^\s*--(sb-[a-z0-9-]+)\s*:", stylesheet, _re.MULTILINE))
    defined = set(css_variables()) | derived

    assert bare <= defined, f"undefined tokens: {sorted(bare - defined)}"


def test_the_scale_token_keeps_its_fallback():
    """Every size on the surface is measured in it. Without the fallback, a
    failed injection would render the whole canvas at zero."""
    import re as _re

    stylesheet = (PROJECT_ROOT / "cli/canvas/static/sb.css").read_text()
    uses = _re.findall(r"var\(\s*--sb-scale\s*(,[^)]*)?\)", stylesheet)
    assert uses, "the stylesheet no longer scales"
    assert all(use.strip() for use in uses), "a bare var(--sb-scale) has no safety net"


def test_the_stylesheet_defines_no_token_the_palette_already_owns():
    """A role redefined in the stylesheet is a second source for it, and the two
    would drift. Deriving a *new* name from an injected one is fine; that is
    what `--sb-tint` is. Shadowing `--sb-brand` is not."""
    import re as _re

    from cli.theme import css_variables

    stylesheet = (PROJECT_ROOT / "cli/canvas/static/sb.css").read_text()
    defined_here = set(
        _re.findall(r"^\s*--(sb-[a-z0-9-]+)\s*:", stylesheet, _re.MULTILINE)
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


def _oklab(colour: str) -> tuple[float, float, float]:
    """OKLab, for judging whether two *surfaces* differ — which is not a
    question the WCAG contrast ratio answers. See the painted-role test."""
    raw = colour.lstrip("#")
    red, green, blue = (
        (value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
        for value in (int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4))
    )
    long = (0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue) ** (1 / 3)
    med = (0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue) ** (1 / 3)
    short = (0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue) ** (1 / 3)
    return (
        0.2104542553 * long + 0.7936177850 * med - 0.0040720468 * short,
        1.9779984951 * long - 2.4285922050 * med + 0.4505937099 * short,
        0.0259040371 * long + 0.7827717662 * med - 0.8086757660 * short,
    )


def _oklab_distance(a: str, b: str) -> float:
    first, second = _oklab(a), _oklab(b)
    return math.sqrt(sum((first[i] - second[i]) ** 2 for i in range(3)))


#: The design system's own smallest deliberate surface step — `--bg` to
#: `--surface`, which is how every card on the site is separated from the void.
#: Used as the floor for a painted ground so the number is the system's rather
#: than one picked to make a value pass.
SURFACE_STEP = 0.03


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_the_two_renderings_cover_the_same_hues():
    """One system, two renderings — and the check that they are the same system.

    The vocabularies differ on purpose: the CLI's roles name what a value *is*
    (`sb.ok`, `sb.path`), while the canvas's tokens name what the design system
    calls it (`--sb-ok`, `--sb-brand`). What has to hold across them is that
    every hue the CLI darkens ships to the canvas undarkened, so the two are the
    same palette seen under different lighting rather than two palettes.
    """
    tokens = css_variables()
    for name, raw in (
        ("sb-brand", BRAND),
        ("sb-ok", OK),
        ("sb-warn", WARN),
        ("sb-danger", DANGER),
        ("sb-text-2", TEXT_2),
        ("sb-text-3", TEXT_3),
    ):
        assert tokens[name] == raw, f"{name} is not the design system's value"


def test_every_cli_role_survives_an_unknown_terminal_background():
    """The reason the CLI does not simply use the design system's tokens.

    Skyrow's system is dark-only by declaration and its colours are unreadable
    on white — brand measures 2.14 there, ok 1.74, warn 1.44. sky.boss renders into
    whoever's terminal, so each CLI role is the smallest darkening of its token
    that clears this floor against *both* backgrounds. If someone ever
    "corrects" one of these back to the raw token, this fails.
    """
    failures = {}
    for name in STYLES:
        if name in PAINTED:
            continue  # checked by the test below, on the right backgrounds
        colour = THEME.styles[name].color.get_truecolor().hex
        for background in (WHITE, BG):
            ratio = _contrast(colour, background)
            if ratio < FLOOR:
                failures[f"{name} on {background}"] = round(ratio, 2)
    assert not failures, f"unreadable CLI roles: {failures}"


def test_a_painted_role_is_checked_against_the_ground_it_paints():
    """**A role that paints its own background is outside the floor above, and
    that is the mark's argument rather than a new one.** Every other role is
    darkened because sky.boss renders into a terminal whose background nobody
    knows; a role that supplies its own removes the unknown.

    So it is exempt from the wrong check and held to the right two: the
    **ground** must be visible against either terminal, and the foreground must
    be legible on that ground. Skipping them outright would have let a role
    into `STYLES` that nothing checked at all, which is how the exemption for
    the mark could have quietly become an exemption for anything.
    """
    assert PAINTED, "the exemption exists; something should be using it"
    failures = {}
    for name in PAINTED:
        style = THEME.styles[name]
        ground = style.bgcolor.get_truecolor().hex
        colour = style.color.get_truecolor().hex
        # The text is text, so the text floor applies to it — on the ground it
        # actually sits on rather than on a terminal it never touches.
        ratio = _contrast(colour, ground)
        if ratio < FLOOR:
            failures[f"{name} text on its own ground"] = round(ratio, 2)
        # The ground is not text, and the text floor is the wrong instrument
        # for it: a chip on a dark terminal is visible by *hue*, and this one
        # measures 1.46 there against 13.66 on white. Judged by perceptual
        # distance instead, with a threshold taken from the design system
        # rather than invented — `--bg` to `--surface` is the smallest step it
        # treats as a visible change of surface, and every card on the site is
        # drawn with it.
        for background in (WHITE, BG):
            distance = _oklab_distance(ground, background)
            if distance < SURFACE_STEP:
                failures[f"{name} ground vs {background}"] = round(distance, 4)
    assert not failures, f"indistinct painted roles: {failures}"


def test_the_canvas_shows_the_brand_at_full_strength():
    """The canvas paints BG itself, so it is the one surface that needs no
    concession. Darkening there would dim the brand against a background that
    never required it."""
    assert css_variables()["sb-brand"] == BRAND
    assert THEME.styles["sb.accent"].color.get_truecolor().hex.lower() != BRAND


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


def test_every_mark_role_the_highlighter_can_emit_has_a_rule_in_the_stylesheet():
    """**Enumerated off the rules, because spot-checking is what missed it.**

    `cli/highlight.py` emits role names and `render.js` turns each into an
    `mk-<role>` class, applied dumbly. Nothing connected that to the stylesheet
    — so round 4's verdict roles (`ok`, `fail`, `warn`) shipped their classes
    with no rule to paint them, and every ✓, ✗, ⚠ and colour word on the canvas
    rendered in plain body text for a week while the terminal coloured them
    correctly. One vocabulary, two surfaces, and only one drawing it.

    It survived because the natural check is *did the mark land*, which reads
    class names and passes. The failure is only visible in a computed style.
    """
    from cli import highlight as highlight_

    roles = {role for _, role, _, _ in highlight_._RULES}
    roles |= set(highlight_._COLOUR_WORDS.values())
    # The positional rules, which are not in `_RULES`.
    roles |= {"sb.muted", "sb.accent"}
    css = (PROJECT_ROOT / "cli/canvas/static/sb.css").read_text()
    missing = sorted(
        role for role in roles if f".mk-{role.removeprefix('sb.')}" not in css
    )
    assert not missing, f"roles with no rule to paint them: {missing}"
    # `bold` is not a role but a weight, and composes with all of them.
    assert ".mk-bold" in css


# ------------------------------------------------- the canvas's own floor

CANVAS_FLOOR = 4.5  # WCAG AA for body text, which is what these roles carry

#: Every ground the canvas paints text on. `--sb-surface-2` is the worst of the
#: three, so it is the one a role has to survive.
CANVAS_GROUNDS = ("sb-bg", "sb-surface", "sb-surface-2")


def test_every_canvas_reading_role_clears_the_floor_on_every_ground():
    """The canvas's floor is the CLI's, minus the unknown that made it 3.5.

    Each CLI role is darkened until it clears 3.5:1 against *both* white and the
    void, because a terminal's background belongs to whoever runs it. The canvas
    paints its own, so there is no unknown to hedge against and the floor can be
    the real one: WCAG AA against the three grounds it actually uses.

    `--text-3` is deliberately absent. The design system calls it "structure, not
    reading text" and this file copies it verbatim, so it is not a role that owes
    a text floor — it is a role that owes not being used as text, which the test
    below is about.
    """
    tokens = css_variables()
    grounds = {name: tokens[name] for name in CANVAS_GROUNDS}
    reading = {"sb-text": TEXT, "sb-text-2": TEXT_2}
    too_dim = {}
    for role, colour in sorted(reading.items()):
        for ground, backdrop in grounds.items():
            ratio = _contrast(colour, backdrop)
            if ratio < CANVAS_FLOOR:
                too_dim[f"{role} on {ground}"] = round(ratio, 2)
    assert not too_dim, f"below the canvas floor of {CANVAS_FLOOR}:1: {too_dim}"


def test_the_structure_colour_is_never_used_as_text():
    """`--sb-text-3` is a border, not a tier of type.

    The design system says so — "very dim — structure, not reading text" — and
    `[[tools]]` round 5 acted on it for one element, leaving a comment in
    `sb.css` explaining that a group name is read and so takes `--text-2`. The
    other **66** `color:` uses stayed, and measured 1.70:1 on `--sb-surface` and
    1.81:1 on `--sb-bg` against a 4.5:1 requirement: the window controls, the
    stat readouts, the tool kind, the footer hints. Reported by the operator as
    the surface being hard to see. See [[canvas]] round 14.

    This is checked against the stylesheet rather than against a list of the
    styles that were measured, because only one of the three screens was — a
    list would have pinned sixteen and stayed silent on the fifty on the other
    two. The role keeps its value; what is forbidden is spending it on type.
    """
    offenders = {}
    for path in sorted(PROJECT_ROOT.rglob("*.css")):
        if "vendor" in path.parts or ".venv" in path.parts or "node_modules" in path.parts:
            continue
        found = re.findall(r"color:\s*var\(--sb-text-3\)", path.read_text())
        if found:
            offenders[str(path.relative_to(PROJECT_ROOT))] = len(found)
    assert not offenders, (
        f"rules painting text with the structure colour: {offenders} — "
        "use --sb-text-2 for text a reader reads"
    )
