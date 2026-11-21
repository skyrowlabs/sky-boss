"""The shortcuts overlay on M-/: every deck key and click, grouped, one line each. See [[command-deck]] round 26.

Pure: `deck.py` binds the keys and opens the popup. A key's line is looked up by its `SHORTCUTS`
name, so a bound key with no line raises here, and a test holds that.
"""

from __future__ import annotations

from dataclasses import dataclass

from skyboss import decklaunch

GROUPS = ("tabs", "panes", "communications", "deck")
#: Each `SHORTCUTS` name, and `exit`: its group and what it does.
LINES = {
    "previous": ("tabs", "the tab to the left"),
    "next": ("tabs", "the tab to the right"),
    "add": ("tabs", "open a new agent or terminal tab"),
    "outside": ("panes", "hide or show agents outside the deck"),
    "layout": ("panes", "the next layout: stack, grid, columns"),
    "column": ("panes", "choose, order and fold the right column"),
    "fold": ("panes", "fold or unfold the focused pane"),
    "watchers": ("panes", "choose what WATCHERS draws"),
    "older": ("communications", "scroll messages back"),
    "newest": ("communications", "back to the newest message"),
    "clear": ("communications", "clear what is done, decided or asked"),
    "launch": ("deck", "the launcher: sessions, profiles, agents"),
    "shortcuts": ("deck", "this list"),
    "exit": ("deck", "end the deck, after asking"),
}
#: What a click does, by group: where to click, and what happens.
CLICKS = (
    ("tabs", "right-click tab", "make it lead, or move it left or right"),
    ("tabs", "click +", "open a new agent or terminal tab"),
    ("panes", "click a title", "grid: pick it up, then click a column"),
    ("panes", "click WATCHERS", "its title: choose what it draws"),
    ("panes", "click AGENT LIST", "a row: unfold its sub-agents"),
    ("communications", "click a message", "open it whole"),
    ("communications", "click a decision", "its choices, or an action's command"),
    ("deck", "click ▦", "the next layout"),
    ("deck", "click ✕", "end the deck, after asking"),
)
GAP = 4


@dataclass(frozen=True)
class Entry:
    group: str
    key: str
    does: str


def entries(shortcuts: dict[str, str], exit_key: str) -> list[Entry]:
    """Every key, then every click, in group order. A key with no line in `LINES` raises KeyError."""
    named = {**shortcuts, "exit": exit_key}
    found = [Entry(LINES[name][0], key, LINES[name][1]) for name, key in named.items()]
    found += [Entry(group, where, does) for group, where, does in CLICKS]
    return sorted(found, key=lambda entry: GROUPS.index(entry.group))


def launcher_entries() -> list[Entry]:
    """The launcher's keys, by section, in its own words: they are its section headings' hints."""
    found = [Entry("deck", heading.lower(), keys) for heading, keys, _ in decklaunch.SECTIONS]
    return found + [Entry("deck", "anywhere", "tab section · q quit")]


def block(heading: str, found: list[Entry]) -> list[str]:
    """A heading, then a line per entry with the keys in one column."""
    width = max(len(e.key) for e in found)
    return [heading] + [f"  {e.key:<{width}}  {e.does}" for e in found]


def screen(found: list[Entry], columns: int, launch: str = "") -> list[str]:
    """The overlay's lines: tabs and panes beside communications and the deck when they fit, then the launcher."""
    blocks = [block(group.upper(), [e for e in found if e.group == group]) for group in GROUPS]
    left = blocks[0] + [""] + blocks[1]
    right = blocks[2] + [""] + blocks[3]
    wide = max(len(line) for line in left)
    if wide + GAP + max(len(line) for line in right) <= columns:
        right += [""] * (len(left) - len(right))
        left += [""] * (len(right) - len(left))
        body = [f"{a:<{wide + GAP}}{b}".rstrip() for a, b in zip(left, right)]
    else:
        body = left + [""] + right
    launcher = block(f"IN THE LAUNCHER{f', ON {launch}' if launch else ''}", launcher_entries())
    return ["sky.boss deck — shortcuts", "", *body, "", *launcher, "", "any key or click closes this"]


def size(found: list[Entry], columns: int, launch: str = "") -> tuple[str, str]:
    """The popup's width and height in cells for `screen` at `columns`, its border included."""
    lines = screen(found, columns, launch)
    return str(max(len(line) for line in lines) + 4), str(len(lines) + 2)
