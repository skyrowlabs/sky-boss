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
the `--help` styling in `cli/__init__.py`, and the TUI's stylesheet. A test
fails if any module outside this one names a hex.
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
# TUI chrome
# ============================================================================
#
# The design system draws borders as white at 5.5% alpha. Flattened over
# --surface that is #181d22, which is a fine hairline on a display and
# invisible in a terminal, where the thinnest rule available is a whole cell.
# `--text-3` is the token for structure rather than reading text, which is
# exactly what a rule is.
BORDER = TEXT_3

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
# Style roles
# ============================================================================
#
# The names are the contract; the hexes behind them are not. Nothing outside
# this module names a colour.

STYLES: dict[str, str] = {
    "tb.accent": f"bold {CLI_BRAND}",
    "tb.label": CLI_LABEL,
    "tb.muted": CLI_FAINT,
    "tb.ok": CLI_OK,
    "tb.fail": CLI_DANGER,
    "tb.warn": CLI_WARN,
    "tb.num": CLI_BRAND,
    "tb.path": CLI_PATH,
}


# The same roles at full strength, for the one surface that knows what is
# behind them. The TUI paints `BG` itself, so the derivations above would be
# darkening against a background that never needed it — chrome dimmer than the
# system intends, on the only screen where the brand can be shown as designed.
TUI_STYLES: dict[str, str] = {
    "tb.accent": f"bold {BRAND}",
    "tb.label": TEXT_2,
    "tb.muted": TEXT_3,
    "tb.ok": OK,
    "tb.fail": DANGER,
    "tb.warn": WARN,
    "tb.num": BRAND,
    "tb.path": TEXT_2,
}
