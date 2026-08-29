"""What the surface remembers about itself between launches.

**Machine state, not operator content.** It lives under `$SB_STATE` beside the
browser profile, on the same line `cli/helpers.py` draws: `rm -rf` on that
directory is a reasonable way to reset the surface and must not touch a single
tool the operator wrote. A folded group is a surface preference; `tools.toml`
is the operator's file, and a chevron click has no business writing it — or
spending one of [[tools]] round 4's backups on it.

**Why this is a file behind a route and not `localStorage`.** `sb ui` binds an
*ephemeral port* every launch, so the page is served from
`http://127.0.0.1:<different>/` each time. Browser storage is keyed by origin,
so a value written under one launch's origin is simply not there under the
next — in every shell, native or browser, and regardless of the webview's
private mode. Round 5 checked that rather than assuming it, and this file is
what the check turned up.

**Strictly shaped, deliberately.** `KEYS` is what may be stored; anything else
is dropped rather than kept. That is the same line round 4 held when it refused
to let `/api/tools` become a config editor: this is a place for the surface's
own state, not a second config file. A missing, empty or unparseable file
degrades to *nothing remembered*, which is the honest failure — everything
open — and never an error the operator has to read.
"""

from __future__ import annotations

import json
from pathlib import Path

from cli.helpers import STATE_DIR

PREFS_FILE = "prefs.json"

# Every key the surface may persist, with the check that says a value is
# usable. A key not named here is dropped on write and ignored on read, so a
# page from a future version cannot quietly grow this file.
KEYS: dict[str, object] = {
    # Which tool groups are folded in the rail. See [[tools]] round 5.
    "folded": list,
    # How wide the rail is, in `rem`. Stored in rem rather than pixels because
    # the stylesheet is measured in them — `1rem = 4px x --sb-scale` — so a
    # pixel width would mean a different rail at every scale. See [[tools]]
    # round 7.
    "rail": int,
}

# A bound on how much the surface may remember. Not a security boundary — a
# page past the guard has `/api/run` — but a file that grows without limit
# because something appended to it in a loop is a bug that reports itself as
# a slow launch, months later.
MAX_ITEMS = 200
MAX_LEN = 64

# What a rail width may be, in rem. The floor is narrow enough to be nearly
# closed and wide enough to still show the drag handle; the ceiling stops a
# rail that has eaten the canvas. Bounds rather than a bare `int` check because
# `_usable` used to return True for any value of the right type — fine when the
# only key was a list carrying its own limits, and a way to store a width of
# 1e9 the moment a number arrived. See [[tools]] round 7.
RAIL_MIN = 18
RAIL_MAX = 160


def path(state: Path | None = None) -> Path:
    return (state or STATE_DIR) / PREFS_FILE


def read(state: Path | None = None) -> dict:
    """What was remembered, or nothing.

    Absent, empty and malformed are one answer on purpose: the surface asks
    this before it can draw, and a raised error there costs the rail rather
    than the preference.
    """
    try:
        with path(state).open("rb") as handle:
            stored = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(stored, dict):
        return {}
    return {key: value for key, value in stored.items() if _usable(key, value)}


def write(body: dict, state: Path | None = None) -> str | None:
    """Merge into what is remembered. The reason it was refused, or None.

    **Merge, not replace, and the second key is what forced it.** With one key
    a whole-file rewrite was the same thing. With two there are two writers —
    the fold control sends `folded`, the rail drag sends `rail` — and a replace
    means whichever moved last erases the other. Round 5's folds would vanish
    the first time anyone dragged the rail, silently, exactly the way a
    `highlight` field vanished on every `write_block` until [[tools]] round 6
    replaced it with a splice.

    So the rule `CLAUDE.md` states for `tools.toml` holds here too: **a rewrite
    has to know every field; a merge does not.** A caller states what it knows
    and claims nothing about the rest.

    A key is therefore *cleared* by sending its empty value, never by omitting
    it — omission means "no opinion", `[]` means "none". That distinction is
    what makes two independent writers safe.
    """
    kept = {key: value for key, value in body.items() if key in KEYS}
    for key, value in kept.items():
        if not _usable(key, value):
            return f"{key!r} is not a usable value"
    kept = {**read(state), **kept}

    target = path(state)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(kept, indent=2) + "\n")
    except OSError as exc:
        return f"{target}: {exc}"
    return None


def _usable(key: str, value) -> bool:
    if key not in KEYS or not isinstance(value, KEYS[key]):
        return False
    # `bool` is an `int` in Python, and `True` would sail through the range
    # check below as a one-rem rail. Rejected explicitly rather than left to
    # arithmetic.
    if isinstance(value, bool):
        return False
    if isinstance(value, list):
        return len(value) <= MAX_ITEMS and all(
            isinstance(item, str) and 0 < len(item) <= MAX_LEN for item in value
        )
    if key == "rail":
        return RAIL_MIN <= value <= RAIL_MAX
    return True
