"""The deck's right column: which tool panes show, in what order, and which are folded. See [[command-deck]].

**Machine state, not operator config.** The choice is a file under `$SB_STATE`
per deck session, written by the chooser; `deck.toml` may declare a starting
order with `panes`, which sky.boss reads and never writes. A role the file does
not name joins at the end, so a pane added in a later release still appears.

The chooser's moves are pure functions over `Column`, so the suite reads the
choice without a terminal; `pick` is the thin loop that draws them in a popup.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.text import Text

from skyboss import helpers, keys

QUEUE, MESSAGES, TODOS, DECISIONS = "queue", "messages", "todos", "decisions"
TOOLS = (QUEUE, MESSAGES, TODOS, DECISIONS)
LABELS = {
    QUEUE: "AGENT LIST",
    MESSAGES: "AGENT COMMUNICATIONS",
    TODOS: "AGENT TODOs",
    DECISIONS: "HUMAN DECISIONS",
}
LABEL_WIDTH = max(len(label) for label in LABELS.values())
FILE = "column.json"


@dataclass
class Column:
    order: list[str] = field(default_factory=lambda: list(TOOLS))
    hidden: set[str] = field(default_factory=set)
    collapsed: set[str] = field(default_factory=set)
    # The grid's columns, left to right; empty until the operator moves a pane.
    columns: list[list[str]] = field(default_factory=list)

    @property
    def shown(self) -> list[str]:
        return [role for role in self.order if role not in self.hidden]

    def groups(self, declared: list[list[str]] | None = None) -> list[list[str]]:
        """The shown panes by grid column: the saved columns, else `declared`, else two and two.

        A hidden pane is left out, and one no column names joins the last.
        """
        shown = self.shown
        chosen = self.columns or declared or [shown[0::2], shown[1::2]]
        out = [[role for role in column if role in shown] for column in chosen]
        out = [column for column in out if column]
        placed = {role for column in out for role in column}
        missing = [role for role in shown if role not in placed]
        if missing and out:
            out[-1] = [*out[-1], *missing]
        return out or ([missing] if missing else [])

    def folded(self, role: str) -> bool:
        return role in self.collapsed and role not in self.hidden


def known(roles: list[str]) -> list[str]:
    """`roles` that name a tool, each once, then every tool they left out, in the default order."""
    seen: list[str] = []
    for role in roles:
        if role in TOOLS and role not in seen:
            seen.append(role)
    return [*seen, *(role for role in TOOLS if role not in seen)]


def path_for(session: str) -> Path:
    return helpers.STATE_DIR / "deck" / session / FILE


def load(session: str, default: list[str] | None = None) -> tuple[Column, list[str]]:
    """The saved choice, else `default` (from `deck.toml`), else every tool. Problems, never raises."""
    path = path_for(session)
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return Column(order=known(default or [])), []
    except (OSError, ValueError) as exc:
        return Column(order=known(default or [])), [f"{path.name} unreadable, so the default column is drawn — {exc}"]
    order = known([str(role) for role in raw.get("order", [])])
    columns = [[str(role) for role in column if role in TOOLS] for column in raw.get("columns", [])]
    hidden = {str(role) for role in raw.get("hidden", [])} & set(TOOLS)
    collapsed = {str(role) for role in raw.get("collapsed", [])} & set(TOOLS)
    return Column(order=order, hidden=hidden, collapsed=collapsed, columns=columns), []


def save(session: str, column: Column) -> None:
    """Written whole through a rename, so a pane never reads half a choice."""
    path = path_for(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".column.", suffix=".json")
    with os.fdopen(handle, "w") as out:
        json.dump(
            {
                "order": column.order,
                "hidden": sorted(column.hidden),
                "collapsed": sorted(column.collapsed),
                "columns": column.columns,
            },
            out,
            indent=1,
        )
    os.replace(temp, path)


# ============================================================================
# The chooser's moves: pure, so the suite reads them without a terminal
# ============================================================================


def toggle(values: set[str], role: str) -> set[str]:
    return values - {role} if role in values else values | {role}


def move(column: Column, at: int, step: int) -> tuple[Column, int]:
    """The role at `at` moved `step` places; the cursor follows it."""
    order = list(column.order)
    to = max(0, min(len(order) - 1, at + step))
    order.insert(to, order.pop(at))
    return replace(column, order=order, hidden=set(column.hidden), collapsed=set(column.collapsed)), to


def send(groups: list[list[str]], role: str, to: str) -> list[list[str]]:
    """`role` moved ahead of `to`, in `to`'s column. Alone in its column, it swaps with `to` instead.

    A column never empties here, as a click would have nowhere left to send a pane back to.
    """
    out = [list(column) for column in groups]
    source = next((column for column in out if role in column), None)
    target = next((column for column in out if to in column), None)
    if source is None or target is None or source is target:
        return out
    at = target.index(to)
    if len(source) == 1:
        source[0], target[at] = to, role
    else:
        source.remove(role)
        target.insert(at, role)
    return out


def place(groups: list[list[str]], role: str, number: int) -> list[list[str]]:
    """`role` at the end of column `number`, counted from 1; one past the last is a new column.

    Raises `ValueError` on a column that does not exist, or a move that would empty one.
    """
    if not 1 <= number <= len(groups) + 1:
        raise ValueError(f"there are {len(groups)} columns, so {number} is not one, nor the next")
    out = [list(column) for column in groups]
    source = next((column for column in out if role in column), None)
    if source is None:
        raise ValueError(f"{role} is not showing")
    if number <= len(out) and role in out[number - 1]:
        return out
    if len(source) == 1:
        raise ValueError(f"{role} is alone in its column, and moving it would empty that")
    source.remove(role)
    if number > len(out):
        out.append([])
    out[number - 1].append(role)
    return out


def press(column: Column, at: int, key: str) -> tuple[Column, int, str | None]:
    """One key in the chooser: the new choice, the cursor, and `apply`, `cancel` or None."""
    role = column.order[at]
    if key in ("\r", "\n"):
        return column, at, "apply"
    if keys.leaves(key):
        return column, at, "cancel"
    if key == "up":
        return column, max(0, at - 1), None
    if key == "down":
        return column, min(len(column.order) - 1, at + 1), None
    if key == " ":
        hidden = toggle(column.hidden, role)
        if not set(column.order) - hidden:
            # Hiding the last pane would leave nothing to draw the column with.
            return column, at, None
        return replace(column, hidden=hidden), at, None
    if key == "c":
        return replace(column, collapsed=toggle(column.collapsed, role)), at, None
    if key in ("K", "["):
        moved, to = move(column, at, -1)
        return moved, to, None
    if key in ("J", "]"):
        moved, to = move(column, at, 1)
        return moved, to, None
    return column, at, None


def summary(role: str, rows: list, ok: bool = True, note: str = "") -> str:
    """A folded pane's one line: its label and the counts its rows add up to."""
    label = LABELS.get(role, role.upper())
    if not ok:
        return f"{label} · ✗ could not read — unfold to see why"
    rows = [row for row in rows if isinstance(row, dict)]
    if role == QUEUE:
        waiting = sum(1 for row in rows if row.get("status") == "waiting")
        deck = sum(1 for row in rows if row.get("where") == "deck")
        parts = [f"{waiting} waiting", f"{deck} in deck"]
    elif role == MESSAGES:
        parts = [f"{len(rows)} shown"]
        if rows:
            last = rows[-1]
            parts.append(f"last {last.get('when', '')} {last.get('between', '')}".rstrip())
    else:
        items = [row for row in rows if row.get("kind") == "item"]
        agents = len({row.get("agent") for row in items if not row.get("done")})
        still = sum(1 for row in items if not row.get("done"))
        parts = [f"{still} open", f"{agents} agent{'' if agents == 1 else 's'}"]
    if note:
        parts.append(note)
    return " · ".join([label, *parts])


HELP = "↑↓ · space show · c fold · J/K move · Enter apply · q cancel"


def lines(column: Column, at: int) -> list[Text]:
    """The chooser's drawing: one row per tool pane, the cursor's row marked."""
    out = [Text("right column", style="sb.accent bold")]
    for n, role in enumerate(column.order):
        shown = role not in column.hidden
        row = Text("› " if n == at else "  ", style="sb.accent")
        row.append("[x] " if shown else "[ ] ", style="sb.label" if shown else "sb.muted")
        row.append(f"{LABELS[role]:<{LABEL_WIDTH}}", style="bold" if shown else "sb.muted")
        if column.folded(role):
            row.append("  folded", style="sb.muted")
        out.append(row)
    out.append(Text(HELP, style="sb.muted"))
    return out


def pick(column: Column, console: Console, wait_for: Callable[[float], str | None]) -> Column | None:
    """Run the chooser until Enter (the new choice) or q/Esc (None)."""
    at = 0
    while True:
        console.clear()
        drawn = lines(column, at)
        for n, line in enumerate(drawn):
            # No newline after the last: the popup is exactly this tall, and one would scroll the title away.
            console.print(line, overflow="ellipsis", no_wrap=True, end="" if n == len(drawn) - 1 else "\n")
        key = wait_for(keys.TICK)
        if key is None:
            continue
        column, at, verdict = press(column, at, key)
        if verdict == "apply":
            return column
        if verdict == "cancel":
            return None
