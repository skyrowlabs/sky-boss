"""The deck's agent-kept lists, todos and decisions: one per agent per book. See [[command-deck]].

A **book** is which list: `todos` for work in flight, `decisions` for what an
agent needs the operator to rule on. Both are written by the agent through
sky.boss and drawn grouped by agent, newest change first. A closed decision
carries its ruling.

**Agents keep their own lists, through sky.boss.** Claude Code's main sessions
have no todo tool to read on the version measured, so there is nothing of
Claude's to show; each agent writes its list with `sb deck todo add/done`, and
the deck's AGENT TODOs pane draws every list.

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

TODOS = "todos"
DECISIONS = "decisions"
#: Hook rows: come and go on their own, so they stay out of the numbers an agent was told.
ASKS = "asks"
CHOICE, ACTION, ASKED, PROSE, NOTICE = "choice", "action", "asked", "prose", "notice"
#: The order rows take, so a notice can never push a choice out of view.
RANK = {CHOICE: 0, ACTION: 1, ASKED: 2, PROSE: 3, NOTICE: 4}
HELD = "held"
NO_LIST = "no list kept"
NO_DECISIONS = "none recorded"
NOTHING_OPEN = "nothing open"
EMPTY = {TODOS: NO_LIST, DECISIONS: NO_DECISIONS}
#: How long an open todo goes unchecked before it is stale: `todo_stale` in deck.toml.
STALE_AFTER = 6 * 3600


@dataclass
class Item:
    text: str
    done: bool = False
    added: str = ""
    closed: str = ""
    ruling: str = ""
    # The choices a decision offers the operator, and whether its agent is still to be told a ruling.
    options: list[str] = field(default_factory=list)
    untold: bool = False
    # A decision's kind, and an action's command, folder, closing test and what that test last found.
    kind: str = CHOICE
    run: list[str] = field(default_factory=list)
    cwd: str = ""
    until: str = ""
    state: str = ""
    # When the deck last asked the agent to recheck this todo; staleness counts from the later of this and `added`.
    checked: str = ""


@dataclass
class TodoList:
    agent: str
    session: str
    items: list[Item] = field(default_factory=list)
    updated: str = ""
    book: str = TODOS

    @property
    def open(self) -> int:
        return sum(1 for item in self.items if not item.done)


def root(session: str, book: str = TODOS) -> Path:
    """Resolved at call time, so a test's `SB_STATE` is the one used."""
    return helpers.STATE_DIR / "deck" / session / book


def path_for(session: str, agent: str, book: str = TODOS) -> Path:
    return root(session, book) / f"{agent}.json"


def now_iso() -> str:
    """Microseconds, so two writes in one second still order (the pane sorts on this)."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def load(session: str, agent: str, book: str = TODOS) -> TodoList | None:
    """The agent's list, or None when it keeps none. Raises `ValueError` for an unreadable file."""
    path = path_for(session, agent, book)
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path.name} unreadable — {exc}") from exc
    items = [Item(**{k: v for k, v in i.items() if k in Item.__dataclass_fields__}) for i in raw.get("items", [])]
    return TodoList(agent=agent, session=session, items=items, updated=str(raw.get("updated") or ""), book=book)


def save(todo: TodoList) -> TodoList:
    """Write the list whole, stamped with the time, through a rename so a reader never sees half."""
    todo.updated = now_iso()
    path = path_for(todo.session, todo.agent, todo.book)
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


def add(
    session: str,
    agent: str,
    text: str,
    book: str = TODOS,
    options: tuple[str, ...] = (),
    kind: str = CHOICE,
    run: list[str] | None = None,
    cwd: str = "",
    until: str = "",
) -> TodoList:
    todo = load(session, agent, book) or TodoList(agent=agent, session=session, book=book)
    todo.items.append(
        Item(
            text=clean(text),
            added=now_iso(),
            options=[clean(option) for option in options],
            kind=kind,
            run=list(run or []),
            cwd=cwd,
            until=until,
        )
    )
    return save(todo)


def _item(todo: TodoList | None, n: int) -> Item:
    if todo is None or not 1 <= n <= len(todo.items):
        count = len(todo.items) if todo else 0
        raise IndexError(f"no item {n} — the list has {count}")
    return todo.items[n - 1]


def done(session: str, agent: str, n: int, book: str = TODOS, ruling: str = "") -> TodoList:
    todo = load(session, agent, book)
    item = _item(todo, n)
    if item.kind == ACTION and item.until:
        raise ValueError(f"action {n} closes when {item.until} is observed, not on an agent's word")
    item.done, item.closed, item.ruling = True, now_iso(), clean(ruling)
    assert todo is not None
    return save(todo)


def rule(session: str, agent: str, n: int, ruling: str) -> TodoList:
    """The operator's ruling on open decision `n`, marked for telling its agent."""
    todo = load(session, agent, DECISIONS)
    item = _item(todo, n)
    if item.done:
        raise ValueError(f"decision {n} is already ruled")
    item.done, item.closed, item.ruling, item.untold = True, now_iso(), clean(ruling), True
    assert todo is not None
    return save(todo)


def close_action(session: str, agent: str, n: int, how: str) -> TodoList:
    """The operator closed action or notice `n`. An action's agent is told; a notice has no one waiting."""
    todo = load(session, agent, DECISIONS)
    item = _item(todo, n)
    item.done, item.closed, item.ruling = True, now_iso(), clean(how)
    item.untold, item.state = item.kind == ACTION, ""
    assert todo is not None
    return save(todo)


def told(session: str, agent: str, n: int) -> TodoList:
    """Decision `n`'s ruling has reached its agent."""
    todo = load(session, agent, DECISIONS)
    _item(todo, n).untold = False
    assert todo is not None
    return save(todo)


def next_untold(session: str, agent: str) -> tuple[int, Item] | None:
    """The first ruling `agent` has not been told, numbered as its list numbers it."""
    todo = load(session, agent, DECISIONS)
    for n, item in enumerate(todo.items if todo else [], start=1):
        if item.untold:
            return n, item
    return None


def is_stale(item: Item, now: datetime, after: int = STALE_AFTER) -> bool:
    """An open todo neither added nor rechecked in the last `after` seconds. Never one with no time."""
    if item.done or not after:
        return False
    try:
        since = max(datetime.fromisoformat(stamp) for stamp in (item.added, item.checked) if stamp)
    except ValueError:
        return False
    return (now - since).total_seconds() >= after


def stale(session: str, agent: str, now: datetime, after: int = STALE_AFTER) -> list[int]:
    """The numbers of `agent`'s stale todos. Raises `ValueError` for an unreadable list."""
    todo = load(session, agent)
    return [n for n, item in enumerate(todo.items if todo else [], start=1) if is_stale(item, now, after)]


def rechecked(session: str, agent: str, numbers: list[int], when: datetime) -> TodoList:
    """Todos `numbers` were put to their agent to recheck at `when`."""
    todo = load(session, agent)
    for n in numbers:
        _item(todo, n).checked = when.isoformat()
    assert todo is not None
    return save(todo)


def remove(session: str, agent: str, n: int, book: str = TODOS) -> TodoList:
    todo = load(session, agent, book)
    _item(todo, n)
    assert todo is not None
    del todo.items[n - 1]
    return save(todo)


def clear_done(session: str, book: str = TODOS) -> tuple[dict[str, int], list[str]]:
    """Drop every done item and every notice from every agent's list: agent → items removed, and unreadable lists.

    A list with nothing done is not rewritten, so its `updated` (the pane's order) holds still.
    """
    cleared: dict[str, int] = {}
    problems: list[str] = []
    for agent in stored(session, book):
        try:
            todo = load(session, agent, book)
        except ValueError as exc:
            problems.append(f"{agent}: {exc}")
            continue
        if todo is None:
            continue
        # An untold ruling stays: clearing it would leave its agent waiting on a question already answered.
        # A notice needs no ruling, so a clear takes it as read.
        kept = [item for item in todo.items if (not item.done and item.kind != NOTICE) or item.untold]
        if len(kept) == len(todo.items):
            continue
        cleared[agent] = len(todo.items) - len(kept)
        todo.items = kept
        save(todo)
    return cleared, problems


def stored(session: str, book: str = TODOS) -> list[str]:
    """Every agent with a list file in this deck, by name."""
    try:
        return sorted(path.stem for path in root(session, book).glob("*.json"))
    except OSError:
        return []


def _age(updated: str, now: datetime) -> str:
    try:
        return ago((now - datetime.fromisoformat(updated)).total_seconds())
    except (TypeError, ValueError):
        return ""


def _best(todo: TodoList | None, asks: TodoList | None) -> int:
    """The highest-ranked open row an agent has, so an agent holding a choice sorts above a notice."""
    items = [*(todo.items if todo else []), *(asks.items if asks else [])]
    return min((RANK.get(item.kind, 0) for item in items if not item.done), default=len(RANK))


def _ordered(items: list[Item]) -> list[tuple[int, Item]]:
    """Open items by rank then closed ones, each keeping the number its list gave it."""
    numbered = list(enumerate(items, start=1))
    return sorted(numbered, key=lambda pair: (pair[1].done, RANK.get(pair[1].kind, 0)))


def _open_parts(n: int, item: Item) -> list:
    number = [f"  {n}. ", "sb.muted"]
    if item.kind == ACTION:
        state = [[f"  · {item.state}", "sb.warn"]] if item.state else []
        return [number, ["▶ ", "sb.accent"], [item.text, None], *state]
    if item.kind == NOTICE:
        return [number, [item.text, "sb.muted"]]
    return [number, [item.text, None], *([[f"  · {len(item.options)} choices", "sb.muted"]] if item.options else [])]


def _ask_parts(item: Item) -> list:
    if item.kind == ASKED:
        return [["  ", None], ["waiting: ", "sb.warn"], [item.text, None]]
    return [["  ", None], ["asked: ", "sb.muted"], [item.text, "sb.muted"]]


def _recency(todo: TodoList | None) -> tuple[bool, float]:
    """Sort key: kept lists newest first, then agents with none; stable within each."""
    try:
        return (False, -datetime.fromisoformat(todo.updated).timestamp()) if todo else (True, 0.0)
    except ValueError:
        return (False, 0.0)


def rows_of(
    session: str,
    order: list[tuple[str, int]],
    now: datetime,
    paint: bool = False,
    only: str | None = None,
    book: str = TODOS,
    held: dict | None = None,
    stale_after: int = STALE_AFTER,
) -> tuple[list[dict], list[str]]:
    """One heading row per agent, then its items, unless `only` names one agent.

    Lists come newest update first, so a change lifts its agent to the top; agents
    with no list follow in `order` (tab order, primary first). A list whose agent
    has no tab is included. A heading is the agent's name in its tab colour, when painted.
    """
    rows: list[dict] = []
    problems: list[str] = []
    tabbed = [name for name, _ in order]
    deciding = book == DECISIONS
    kept = [*stored(session, book), *(stored(session, ASKS) if deciding else [])]
    rest = [] if only else [(name, -1) for name in dict.fromkeys(kept) if name not in tabbed]
    entries: list[tuple[str, int, TodoList | None, TodoList | None]] = []
    for name, slot in [*order, *rest]:
        try:
            entries.append((name, slot, load(session, name, book), load(session, name, ASKS) if deciding else None))
        except ValueError as exc:
            problems.append(f"{name}: {exc}")
            entries.append((name, slot, None, None))
    entries.sort(key=lambda entry: (_best(entry[2], entry[3]) if deciding else 0, *_recency(entry[2] or entry[3])))
    for name, slot, todo, asks in entries:
        waiting = asks.items if asks else []
        if todo is None and not waiting and (deciding or not only):
            # Most agents keep none; ten empty rows would bury the one that did. Asked alone, a tab is told.
            continue
        if todo is not None and not todo.items and not waiting and not only:
            # Emptied, most often by a clear: the pane drops it rather than keep a heading over nothing.
            continue
        colour = theme.agent_role(name, max(slot, 0)) if paint and slot >= 0 else None
        heading = [[name, colour or "sb.accent"]]
        if slot < 0:
            heading.append([" (no tab)", "sb.muted"])
        latest = todo or asks
        age = _age(latest.updated, now) if latest else ""
        if age:
            heading.append([f"  updated {age} ago", "sb.muted"])
        rows.append(_row(book, name, "agent", heading, todo, None, None))
        if todo is None and not waiting:
            rows.append(_row(book, name, "empty", [[f"  {EMPTY[book]}", "sb.muted"]], None, None, None))
            continue
        for item in sorted(waiting, key=lambda item: RANK.get(item.kind, 0)):
            rows.append(_row(book, name, "ask", _ask_parts(item), asks, None, item))
        if todo is None:
            continue
        if not todo.open and not waiting:
            rows.append(_row(book, name, "empty", [[f"  {NOTHING_OPEN}", "sb.muted"]], todo, None, None))
        for n, item in _ordered(todo.items) if deciding else enumerate(todo.items, start=1):
            # Done items stay, dimmed and ticked, so the operator sees what moved.
            closed = (
                "✓ " + item.text + (f" → {item.ruling}" if item.ruling else "") + (" · untold" if item.untold else "")
            )
            parts = [[f"  {n}. ", "sb.muted"], [closed, "sb.muted"]] if item.done else _open_parts(n, item)
            if not deciding and is_stale(item, now, stale_after):
                parts.append(["  · stale", "sb.warn"])
            rows.append(_row(book, name, "item", parts, todo, n, item))
    if deciding and not only and held is not None:
        rows += _held_rows(held, now)
    return rows, problems


def _held_rows(held: dict, now: datetime) -> list[dict]:
    """One foot line for what is held, then a row per item. A pane shows the rows on a click."""
    if not held:
        return [_row(DECISIONS, "", HELD, [["HELD ", "sb.accent"], ["not read yet", "sb.muted"]], None, None, None)]
    repos = held.get("repos") or []
    count = sum(len(repo.get("rows") or []) for repo in repos)
    unread = sum(1 for repo in repos if repo.get("unread"))
    words = [f"{count}" if count else "none" if repos else "no repo read"]
    if unread:
        words.append(f"{unread} could not be read")
    age = _age(str(held.get("checked") or ""), now)
    if age:
        words.append(f"read {age} ago")
    rows = [_row(DECISIONS, "", HELD, [["HELD ", "sb.accent"], [" · ".join(words), "sb.muted"]], None, None, None)]
    for repo in repos:
        name = str(repo.get("repo") or "")
        for text in repo.get("rows") or []:
            rows.append(
                _row(DECISIONS, name, "held-row", [[f"  {name}  ", "sb.muted"], [text, None]], None, None, None)
            )
        for text in repo.get("unread") or []:
            parts = [[f"  {name}  ", "sb.muted"], [f"could not read {text}", "sb.warn"]]
            rows.append(_row(DECISIONS, name, "held-row", parts, None, None, None))
    return rows


def _row(
    book: str, agent: str, kind: str, parts: list, todo: TodoList | None, n: int | None, item: Item | None
) -> dict:
    return {
        book: "".join(str(part[0]) for part in parts),
        "parts": parts,
        "agent": agent,
        "kind": kind,
        "n": n or "",
        "text": item.text if item else "",
        "done": bool(item.done) if item else "",
        "ruling": item.ruling if item else "",
        "updated": todo.updated if todo else "",
        "ask": item.kind if item else "",
    }


def view_of(rows: list[dict], book: str = TODOS) -> dict:
    column = describe(book, rows)
    column["segments"] = "parts"
    return {
        "columns": [column],
        "details": [],
        "hidden": ["parts", "agent", "kind", "n", "text", "done", "ruling", "updated", "ask"],
        "authored": True,
    }


def result_of(
    session: str,
    order: list[tuple[str, int]],
    paint: bool = False,
    only: str | None = None,
    book: str = TODOS,
    held: dict | None = None,
    stale_after: int = STALE_AFTER,
) -> Result:
    result = Result()
    rows, problems = rows_of(session, order, datetime.now(timezone.utc), paint, only, book, held, stale_after)
    for problem in problems:
        result.warn(problem)
    if not rows:
        noun = "a decision" if book == DECISIONS else "a todo"
        parts = [[f"no agent in deck {session!r} has recorded {noun}", "sb.muted"]]
        rows = [_row(book, "", "empty", parts, None, None, None)]
    result.data = rows
    result.view = view_of(rows, book)
    return result
