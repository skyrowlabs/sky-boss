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

**Every consumer derives from this file** — the Rich theme in `cli/output.py`,
the `--help` styling in `cli/__init__.py`, and the canvas's stylesheet, which
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
# `docs/design/cli-header.png` drawn in half-blocks — see cli/banner.py. These
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
    # The one role that paints its own ground. See § Ground, not hue.
    "sb.ref": f"{CLI_REF} on {CLI_REF_BG}",
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
