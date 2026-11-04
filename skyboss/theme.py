"""The palette. One system, rendered two ways.

Skyrow Labs' design system, copied verbatim from its own token file — the one
that ships in the design-system bundle, not jam.sense's app tokens. Those two
are not the same thing, and an earlier version of this file took the app side
and called it the brand. The design system is dark-only by declaration: *"Every
surface is built on a deep blue-black void. There is no light theme."*

**Two renderings, because the two surfaces do not share a background.**

The TUI paints its own void and takes the tokens exactly. The CLI renders into
whoever's terminal, which may be white — and on white the tokens are not dim,
they are gone. Measured contrast against white, then against the void:

    brand   #38bdf8   2.14   9.32
    ok      #4ade80   1.74  11.46
    warn    #e6dc0e   1.44  13.89
    text    #e8edf4   1.18  16.97
    text-3  #344050  10.53   1.90     <- the reverse problem

So every CLI role is a *darkened derivation* of the token it stands for, chosen
as the smallest darkening that clears 3.5:1 on both backgrounds. Same hue, same
meaning, legible either way. Nothing here is picked by eye.

**Every consumer derives from this file** — the Rich theme in `skyboss/output.py`,
the `--help` styling in `skyboss/__init__.py`, and the canvas's stylesheet, which
gets these as CSS custom properties from `css_variables` below. A test fails if
any file outside this one names a hex, in any language.
"""

from __future__ import annotations

# ============================================================================
# Skyrow Labs design system — verbatim
# ============================================================================
# From colors_and_type.css, "single source of truth for color + type tokens
# across every Skyrow Labs surface". Do not adjust these to taste; if the
# system moves, copy the new values in.

# Backgrounds — deep blue-black, never pure #000.
BG = "#05090e"  # --bg: the void, under everything
SURFACE = "#0b1016"  # --surface: cards, forms, raised panels
SURFACE_2 = "#111820"  # --surface-2: inset wells, inputs

# Text — a cool blue-grey ramp on the blue-black.
TEXT = "#e8edf4"  # --text: headings and body
TEXT_2 = "#7a8fa8"  # --text-2: descriptions, muted
TEXT_3 = "#344050"  # --text-3: "very dim — structure, not reading text"

# Master brand accent, and the per-project hues. Each project owns one.
BRAND = "#38bdf8"  # --brand / --js: Skyrow sky blue, shared with jam.sense
WIND = "#4ade80"  # --bb: breeze.brain wind green
SIGNAL = "#e6dc0e"  # --mh: mind.head signal yellow

# Semantics. Success and warning reuse the project hues; danger is the one
# colour the marketing site had no need for.
OK = "#4ade80"  # --ok
WARN = "#e6dc0e"  # --warn
DANGER = "#f4665b"  # --danger

# ============================================================================
# Surface chrome
# ============================================================================
#
# The design system draws borders as white at 5.5% alpha. Flattened over
# --surface that is #181d22 — a fine hairline on a display, and invisible in a
# terminal where the thinnest rule available is a whole cell.
# `--text-3` is the token for structure rather than reading text, which is
# exactly what a rule is.
BORDER = TEXT_3

# ============================================================================
# The mark
# ============================================================================
#
# `docs/design/cli-header.png` drawn in half-blocks — see skyboss/banner.py. These
# are the design system's own values, undarkened, and that is deliberate: the
# mark **paints its own background**, so it is in the same position the canvas
# is in rather than the CLI's. The derivations below exist because sky.boss prints
# into a terminal whose background nobody here knows; a painted panel removes
# the unknown.
#
# It is also the only answer available. The mark's hues fail in *opposite*
# directions — the light handle disappears on white, the dark slate disappears
# on black — so there is no single colour a two-sided floor could accept for
# either. Darkening them to satisfy a rule they are outside of would dim the
# brand mark and still not make it legible on both.
#
# `SURFACE_2` rather than `BG` because that is what the PNG uses (#13171c is
# the inset-well token, not the void).
LOGO_BG = SURFACE_2
LOGO_BRAND = BRAND
LOGO_DARK = TEXT_3
LOGO_LIGHT = TEXT
# The tower is lit from the left, so its right edge needs a darker brand. Not
# `CLI_BRAND`: that is a contrast derivation for an unknown terminal, and the
# mark must stay out of STYLES. This is BRAND at 0.7 over the mark's own
# ground, the same mixing `CLI_REF_BG` uses, so it is a shadow and not a hue.
LOGO_SHADE = "#2c8bb7"  # BRAND at 0.70 over SURFACE_2
LOGO_BEACON = DANGER  # an aircraft warning light is red, and so is this one

# ============================================================================
# CLI-safe derivations
# ============================================================================
#
# The smallest darkening of each token that clears 3.5:1 against both white and
# the void. The comment on each line is (on white, on void) after derivation.

CLI_BRAND = "#2a8fbc"  # from BRAND    3.65 / 5.47
CLI_OK = "#339b59"  # from OK       3.52 / 5.68
CLI_WARN = "#938c08"  # from WARN     3.50 / 5.70
CLI_DANGER = "#e05d53"  # from DANGER   3.58 / 5.57

# The greys need no hue shift, only a level that survives both. TEXT_2 misses
# the floor on white by a hair (3.32) and TEXT_3 is legible only on the void
# (1.90), so both grey roles are derived like the hues. The near-miss is the
# reason the floor is a test rather than a judgement: 3.32 looks fine and is
# not what this file says it does.
CLI_LABEL = "#768aa2"  # from TEXT_2   3.54 / 5.64
CLI_FAINT = "#6b7787"  # 4.55 / 4.39 — the most even split available
CLI_PATH = "#698bab"  # a steel blue at the same floor   3.57 / 5.59

# ============================================================================
# Ground, not hue
# ============================================================================
#
# **The system has four hues and sky.boss spends all four**, so the next thing
# asked to stand out cannot have one: `--brand`/`--js` is one colour, `--bb`
# *is* `--ok`, `--mh` *is* `--warn`, and `--danger` is the fourth. The
# per-project tokens look like extra palette and are aliases.
#
# What the system does still hold is a token that is not a hue at all —
# `--text-on-accent`, its own answer to *louder than a colour can be*: put the
# hue in the **background**. So the axis after weight ([[highlight]] round 5)
# is **ground**, and it costs no new colour.
#
# **A painted ground is outside the two-sided floor, by the mark's own
# argument.** Every other role here is darkened because sky.boss renders into a
# terminal whose background nobody knows; a role that paints its own removes
# the unknown, which is exactly why `LOGO_*` above take their tokens at full
# strength. So the foreground here is `BRAND` undarkened — 6.37 on this
# ground — and it is the *ground* that must clear the floor against the
# terminal, which it does in both directions (1.46 on the void, 13.66 on
# white).
#
# The alpha is the design system's `--brand-ring` (0.22) rather than its
# `--brand-dim` (0.12), and that is a mapping rather than a taste: the system
# draws a chip as a 12% fill *inside* a 22% ring, and a terminal cell has no
# edge to draw. It spends the ring's weight on the fill instead. The canvas,
# which can draw an edge, uses both — see `sb.css`.
CLI_REF_BG = "#103141"  # BRAND at 0.22 over BG  —  1.46 / 13.66 vs the two
CLI_REF = BRAND  # undarkened: it sits on a ground this file chose

# ============================================================================
# Agent colours — steps along the brand
# ============================================================================
#
# The canvas's project ramp (`.pl-s0`…`.pl-s5` in `sb.css`), recomputed here
# because a terminal cannot `color-mix`: the same partners at the same weights,
# mixed in OKLab. Then each is moved in lightness only, the least distance that
# clears the CLI floor against both a white terminal and the void, because the
# messages pane draws on the operator's ground. Never a new hue, never a role.
# A test reads `sb.css` and fails if the two recipes part.

AGENT_RECIPES: tuple[tuple[str | None, float], ...] = (
    (None, 1.0),
    (TEXT, 0.62),
    (SURFACE_2, 0.46),
    (OK, 0.78),
    (TEXT, 0.34),
    (OK, 0.55),
)
CLI_FLOOR = 3.5
_WHITE = "#ffffff"
# A white terminal and the void for the messages pane; the tab row's own two grounds.
AGENT_GROUNDS = (_WHITE, BG, SURFACE, SURFACE_2)


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _gamma(channel: float) -> float:
    channel = min(1.0, max(0.0, channel))
    return channel * 12.92 if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def _rgb(colour: str) -> tuple[float, float, float]:
    raw = colour.lstrip("#")
    r, g, b = (int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return r, g, b


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(_gamma(c) * 255):02x}" for c in rgb)


def _to_oklab(colour: str) -> tuple[float, float, float]:
    r, g, b = (_linear(c) for c in _rgb(colour))
    lms = (
        0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
        0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
        0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b,
    )
    l_, m_, s_ = (v ** (1 / 3) for v in lms)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _from_oklab(lab: tuple[float, float, float]) -> str:
    big_l, a, b = lab
    l_ = big_l + 0.3963377774 * a + 0.2158037573 * b
    m_ = big_l - 0.1055613458 * a - 0.0638541728 * b
    s_ = big_l - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    return _hex(
        (
            4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
        )
    )


def luminance(colour: str) -> float:
    r, g, b = (_linear(c) for c in _rgb(colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _mix(partner: str | None, weight: float) -> str:
    """BRAND at `weight` with `partner`, in OKLab — `color-mix(in oklab, brand w%, partner)`."""
    if partner is None:
        return BRAND
    brand, other = _to_oklab(BRAND), _to_oklab(partner)
    return _from_oklab(tuple(weight * x + (1 - weight) * y for x, y in zip(brand, other)))  # type: ignore[arg-type]


def _legible(colour: str) -> str:
    """`colour`, moved in OKLab lightness by the least that clears the floor on every ground it meets."""

    def clears(candidate: str) -> bool:
        return all(contrast(candidate, ground) >= CLI_FLOOR for ground in AGENT_GROUNDS)

    if clears(colour):
        return colour
    big_l, a, b = _to_oklab(colour)
    for step in range(1, 200):
        for sign in (-1, 1):
            candidate = _from_oklab((big_l + sign * step * 0.002, a, b))
            if clears(candidate):
                return candidate
    return CLI_BRAND


#: One colour per agent slot: the tab row and the messages pane both read these.
AGENT_COLOURS: tuple[str, ...] = tuple(_legible(_mix(partner, weight)) for partner, weight in AGENT_RECIPES)


def agent_colour(slot: int) -> str:
    """The colour of the agent in tab position `slot`, primary first."""
    return AGENT_COLOURS[slot % len(AGENT_COLOURS)]


def agent_role(slot: int) -> str:
    return f"sb.agent.{slot % len(AGENT_COLOURS)}"


# ============================================================================
# Style roles
# ============================================================================
#
# The names are the contract; the hexes behind them are not. Nothing outside
# this module names a colour.

STYLES: dict[str, str] = {
    "sb.accent": f"bold {CLI_BRAND}",
    "sb.label": CLI_LABEL,
    "sb.muted": CLI_FAINT,
    "sb.ok": CLI_OK,
    "sb.fail": CLI_DANGER,
    "sb.warn": CLI_WARN,
    "sb.num": CLI_BRAND,
    "sb.path": CLI_PATH,
    # A link, drawn as a path. A separate name so the canvas can tell a
    # destination from a location without a regex; see [[canvas]] round 15.
    "sb.url": CLI_PATH,
    # The one role that paints its own ground. See § Ground, not hue.
    "sb.ref": f"{CLI_REF} on {CLI_REF_BG}",
    # One per deck agent, by tab order. See § Agent colours.
    **{agent_role(slot): colour for slot, colour in enumerate(AGENT_COLOURS)},
}

# Roles that paint their own background, and are therefore exempt from the
# unknown-terminal floor that governs every other one — the exemption the mark
# already has, stated as data so the contrast test can check the right thing
# rather than skip them. What a painted role owes instead is a *ground* that
# clears the floor and a foreground legible on that ground; both are asserted.
PAINTED: frozenset[str] = frozenset({"sb.ref"})


# ============================================================================
# The canvas
# ============================================================================


def css_variables() -> dict[str, str]:
    """The tokens the canvas's stylesheet reads, as CSS custom properties.

    The same move the removed Textual app made for its own stylesheet, for the
    same reason: the stylesheet has to live in a file a browser can reload, and a
    file outside this module may not name a colour. So it names roles and this
    hands it the values.

    The canvas paints `BG` itself, so like the TUI before it, it takes the
    tokens at full strength rather than the CLI's darkened derivations. Tints
    and washes are built with `color-mix` against these, never written out —
    an `rgba(56, 189, 248, .12)` in the stylesheet is a hex by another name and
    would be the start of the second palette this file exists to prevent.
    """
    return {
        "sb-bg": BG,
        "sb-surface": SURFACE,
        "sb-surface-2": SURFACE_2,
        "sb-text": TEXT,
        "sb-text-2": TEXT_2,
        "sb-text-3": TEXT_3,
        "sb-brand": BRAND,
        "sb-ok": OK,
        "sb-warn": WARN,
        "sb-danger": DANGER,
        "sb-border": BORDER,
    }


def css_root() -> str:
    """`css_variables` as a `:root` block, for injection into the page."""
    body = "".join(f"--{name}:{value};" for name, value in css_variables().items())
    return f":root{{{body}}}"


# ============================================================================
# The deck's tmux bars
# ============================================================================
#
# A tmux status bar paints its own ground, so like the canvas it takes the
# tokens at full strength. Styles are space-separated: a comma would end the
# branch of a `#{?…}` conditional the tab format puts them in.


def tmux_styles() -> dict[str, str]:
    """Role → tmux style string, for the deck's two status bars and its borders."""
    return {
        "bar": f"bg={SURFACE} fg={TEXT_2}",
        "label": f"fg={BRAND} bold",
        "tab": f"fg={TEXT_2} bg={SURFACE}",
        "tab-current": f"fg={TEXT} bg={SURFACE_2} bold",
        "working": f"fg={BRAND}",
        "needs-you": f"fg={BG} bg={WARN} bold",
        "quiet": f"fg={TEXT_2}",
        "unregistered": f"fg={TEXT_2} italics",
        "border": f"fg={TEXT_3}",
        "border-active": f"fg={BRAND}",
        "exit": f"fg={DANGER} bold",
    }
