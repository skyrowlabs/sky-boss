"""The deck's todo lists: one per agent, kept by the agent itself. See [[command-deck]].

**Agents keep their own lists, through sky.boss.** Claude Code's main sessions
have no todo tool to read on the version measured, so there is nothing of
Claude's to show; each agent writes its list with `sb deck todo add/done`, and
the deck's TODOS pane draws every list.

**Machine state, not operator config.** A list is a file under `$SB_STATE`, keyed
by deck session and agent name so a restarted tab keeps its list, and it is
never under `$SB_HOME` or any repo. Who may write a list is the deck's to decide
(by the caller's pane); this module only stores and draws.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from skyboss import helpers, theme
from skyboss.chrome import ago
from skyboss.output import Result
from skyboss.view import describe

NO_LIST = "no list kept"
NOTHING_OPEN = "nothing open"


@dataclass
class Item:
    text: str
    done: bool = False
    added: str = ""
    closed: str = ""


@dataclass
class TodoList:
    agent: str
    session: str
    items: list[Item] = field(default_factory=list)
    updated: str = ""

    @property
    def open(self) -> int:
        return sum(1 for item in self.items if not item.done)


def root(session: str) -> Path:
    """Resolved at call time, so a test's `SB_STATE` is the one used."""
    return helpers.STATE_DIR / "deck" / session / "todos"


def path_for(session: str, agent: str) -> Path:
    return root(session) / f"{agent}.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(session: str, agent: str) -> TodoList | None:
    """The agent's list, or None when it keeps none. Raises `ValueError` for an unreadable file."""
    path = path_for(session, agent)
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path.name} unreadable — {exc}") from exc
    items = [Item(**{k: v for k, v in i.items() if k in Item.__dataclass_fields__}) for i in raw.get("items", [])]
    return TodoList(agent=agent, session=session, items=items, updated=str(raw.get("updated") or ""))


def save(todo: TodoList) -> TodoList:
    """Write the list whole, stamped with the time, through a rename so a reader never sees half."""
    todo.updated = now_iso()
    path = path_for(todo.session, todo.agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{todo.agent}.", suffix=".json")
    with os.fdopen(handle, "w") as out:
        json.dump(
            {
                "agent": todo.agent,
                "session": todo.session,
                "updated": todo.updated,
                "items": [asdict(item) for item in todo.items],
            },
            out,
            indent=1,
        )
    os.replace(temp, path)
    return todo


def clean(text: str) -> str:
    """One line: a todo is a row in a pane."""
    return " ".join(text.split())


def add(session: str, agent: str, text: str) -> TodoList:
    todo = load(session, agent) or TodoList(agent=agent, session=session)
    todo.items.append(Item(text=clean(text), added=now_iso()))
    return save(todo)


def _item(todo: TodoList | None, n: int) -> Item:
    if todo is None or not 1 <= n <= len(todo.items):
        count = len(todo.items) if todo else 0
        raise IndexError(f"no item {n} — the list has {count}")
    return todo.items[n - 1]


def done(session: str, agent: str, n: int) -> TodoList:
    todo = load(session, agent)
    item = _item(todo, n)
    item.done, item.closed = True, now_iso()
    assert todo is not None
    return save(todo)


def remove(session: str, agent: str, n: int) -> TodoList:
    todo = load(session, agent)
    _item(todo, n)
    assert todo is not None
    del todo.items[n - 1]
    return save(todo)


def stored(session: str) -> list[str]:
    """Every agent with a list file in this deck, by name."""
    try:
        return sorted(path.stem for path in root(session).glob("*.json"))
    except OSError:
        return []


def _age(updated: str, now: datetime) -> str:
    try:
        return ago((now - datetime.fromisoformat(updated)).total_seconds())
    except (TypeError, ValueError):
        return ""


def rows_of(
    session: str, order: list[tuple[str, int]], now: datetime, paint: bool = False, only: str | None = None
) -> tuple[list[dict], list[str]]:
    """One heading row per agent, then its items; in `order` (tab order, primary first), then any
    list whose agent has no tab, unless `only` names one agent. A heading is the agent's name in its
    tab colour, when painted."""
    rows: list[dict] = []
    problems: list[str] = []
    tabbed = [name for name, _ in order]
    rest = [] if only else [(name, -1) for name in stored(session) if name not in tabbed]
    for name, slot in [*order, *rest]:
        try:
            todo = load(session, name)
        except ValueError as exc:
            problems.append(f"{name}: {exc}")
            todo = None
        colour = theme.agent_role(name, max(slot, 0)) if paint and slot >= 0 else None
        heading = [[name, colour or "sb.accent"]]
        if slot < 0:
            heading.append([" (no tab)", "sb.muted"])
        age = _age(todo.updated, now) if todo else ""
        if age:
            heading.append([f"  updated {age} ago", "sb.muted"])
        rows.append(_row(name, "agent", heading, todo, None, None))
        if todo is None:
            rows.append(_row(name, "empty", [[f"  {NO_LIST}", "sb.muted"]], None, None, None))
            continue
        if not todo.open:
            rows.append(_row(name, "empty", [[f"  {NOTHING_OPEN}", "sb.muted"]], todo, None, None))
        for n, item in enumerate(todo.items, start=1):
            # Done items stay, dimmed and ticked, so the operator sees what moved.
            parts = (
                [[f"  {n}. ", "sb.muted"], ["✓ " + item.text, "sb.muted"]]
                if item.done
                else [
                    [f"  {n}. ", "sb.muted"],
                    [item.text, None],
                ]
            )
            rows.append(_row(name, "item", parts, todo, n, item))
    return rows, problems


def _row(agent: str, kind: str, parts: list, todo: TodoList | None, n: int | None, item: Item | None) -> dict:
    return {
        "todos": "".join(str(part[0]) for part in parts),
        "parts": parts,
        "agent": agent,
        "kind": kind,
        "n": n or "",
        "text": item.text if item else "",
        "done": bool(item.done) if item else "",
        "updated": todo.updated if todo else "",
    }


def view_of(rows: list[dict]) -> dict:
    column = describe("todos", rows)
    column["segments"] = "parts"
    return {
        "columns": [column],
        "details": [],
        "hidden": ["parts", "agent", "kind", "n", "text", "done", "updated"],
        "authored": True,
    }


def result_of(session: str, order: list[tuple[str, int]], paint: bool = False, only: str | None = None) -> Result:
    result = Result()
    rows, problems = rows_of(session, order, datetime.now(timezone.utc), paint, only)
    for problem in problems:
        result.warn(problem)
    result.data = rows
    if not rows:
        result.warn(f"no deck agents and no lists kept in deck {session!r}")
        return result
    result.view = view_of(rows)
    return result
