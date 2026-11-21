"""A deck session: one deck, running or not, and the directory that holds everything it keeps.

`$SB_STATE/deck/<name>/` is the session: `session.json` names its profile and label, and its
save, todos, decisions, asks and watcher choice sit beside it, so deleting it is deleting the
directory. A profile is a template and owns none of this. See [[command-deck]] round 25.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from skyboss import decksave, deckwatch, helpers
from skyboss import todos as todos_

FILE = "session.json"
AD_HOC = "ad hoc"


@dataclass
class Record:
    name: str
    profile: str = ""
    label: str = ""
    created: float = 0.0
    last_used: float = 0.0
    # Agent → when its tab first joined this session; a message it received earlier is not this session's.
    joined: dict[str, float] = field(default_factory=dict)


def root() -> Path:
    """Resolved at call time, so a test's `SB_STATE` is the one used."""
    return helpers.STATE_DIR / "deck"


def path_for(name: str) -> Path:
    return root() / name / FILE


def load(name: str) -> Record | None:
    """The session's record, or None when it has none or it cannot be read."""
    try:
        raw = json.loads(path_for(name).read_text())
        joined = raw.get("joined") or {}
        return Record(
            name=name,
            profile=str(raw.get("profile") or ""),
            label=str(raw.get("label") or ""),
            created=float(raw.get("created") or 0),
            last_used=float(raw.get("last_used") or 0),
            joined={str(k): float(v) for k, v in joined.items()} if isinstance(joined, dict) else {},
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def write(record: Record) -> None:
    """Written whole through a rename, so a reader never sees half a record."""
    path = path_for(record.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".session.", suffix=".json")
    with os.fdopen(handle, "w") as out:
        json.dump(
            {
                "profile": record.profile,
                "label": record.label,
                "created": record.created,
                "last_used": record.last_used,
                "joined": record.joined,
            },
            out,
            indent=1,
        )
    os.replace(temp, path)


def names() -> list[str]:
    """Every session directory, sorted. Hidden entries are not sessions."""
    try:
        return sorted(p.name for p in root().iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return []


def safe(profile: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", profile)


def label_of(profile: str, n: int) -> str:
    return f"{profile or AD_HOC} {n}"


def labels() -> set[str]:
    return {r.label for r in (load(each) for each in names()) if r is not None}


def free_label(profile: str) -> str:
    """The profile's name and the first number no session's label holds."""
    taken = labels()
    return next(label_of(profile, n) for n in range(1, 10_000) if label_of(profile, n) not in taken)


def new_name(base: str, profile: str, busy: Callable[[str], bool]) -> tuple[str, str]:
    """A new session's tmux name and label: `<base>-<profile>-<n>`, or `<base>-<n>` ad hoc.

    `n` is the first with no directory, nothing `busy`, and no session of that profile labelled with it.
    """
    prefix = f"{base}-{safe(profile)}" if profile else base
    taken = labels()
    for n in range(1, 10_000):
        name = f"{prefix}-{n}"
        if not (root() / name).exists() and not busy(name) and label_of(profile, n) not in taken:
            return name, label_of(profile, n)
    raise ValueError(f"no free session name under {prefix!r}")


def create(name: str, profile: str, label: str, now: float | None = None) -> Record:
    moment = time.time() if now is None else now
    record = Record(name, profile, label, moment, moment)
    write(record)
    return record


def touch(name: str, now: float | None = None) -> None:
    """Mark the session used now. Nothing for a session with no record."""
    record = load(name)
    if record is not None:
        record.last_used = time.time() if now is None else now
        write(record)


def join(name: str, agent: str, now: float | None = None) -> None:
    """Record when `agent` first joined this session; a later join keeps the first."""
    record = load(name)
    if record is not None and agent not in record.joined:
        record.joined[agent] = time.time() if now is None else now
        write(record)


def joined_at(record: Record | None, agent: str) -> float:
    """When `agent` joined, else when the session was created: a migrated session knows no better."""
    if record is None:
        return 0.0
    return record.joined.get(agent, record.created)


def _times(directory: Path) -> tuple[float, float]:
    """The oldest and newest modification time of any file under `directory`."""
    stamps = []
    for path in directory.rglob("*"):
        try:
            if path.is_file():
                stamps.append(path.stat().st_mtime)
        except OSError:
            continue
    return (min(stamps), max(stamps)) if stamps else (0.0, 0.0)


def migrate(base: str, declared: dict[str, str], persist: bool = True) -> list[Record]:
    """A record for each session directory that has none, keeping its tmux name. The new records.

    With `persist` false they are only returned, so an observe can list a session not yet migrated.

    `declared` is profile → the `session` it named. The profile comes from the save, else from a
    profile whose `session` or default name is this one; the label is the profile and a number.
    """
    written: list[Record] = []
    taken = labels()
    for name in names():
        if path_for(name).exists():
            continue
        profile = decksave.load(name)[0].profile
        if not profile:
            profile = next(
                (p for p, session in declared.items() if name in (session, f"{base}-{safe(p)}")),
                "",
            )
        prefix = f"{base}-{safe(profile)}" if profile else base
        tail = name[len(prefix) + 1 :] if name.startswith(prefix + "-") else ""
        n = int(tail) if tail.isdigit() else 1
        while label_of(profile, n) in taken:
            n += 1
        taken.add(label_of(profile, n))
        created, used = _times(root() / name)
        record = Record(name, profile, label_of(profile, n), created, used)
        if persist:
            write(record)
        written.append(record)
    return written


@dataclass(frozen=True)
class Holds:
    tabs: int = 0
    todos: int = 0
    decisions: int = 0
    asks: int = 0
    watchers: int = 0


def holds(name: str, open_only: bool = False) -> Holds:
    """What the session keeps, by count. `open_only` counts only todos and decisions not yet done."""

    def items(book: str) -> int:
        count = 0
        for agent in todos_.stored(name, book):
            try:
                kept = todos_.load(name, agent, book)
            except ValueError:
                continue
            if kept is not None:
                count += sum(1 for item in kept.items if not (open_only and item.done))
        return count

    chosen, _, _ = deckwatch.load(name)
    return Holds(
        tabs=len(decksave.load(name)[0].tabs),
        todos=items(todos_.TODOS),
        decisions=items(todos_.DECISIONS),
        asks=items(todos_.ASKS),
        watchers=len(chosen),
    )


def counted(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def goes(held: Holds) -> str:
    """What deleting a session removes, in words."""
    parts = [
        counted(held.tabs, "tab resume link"),
        counted(held.todos, "todo"),
        counted(held.decisions, "decision"),
        counted(held.asks, "ask"),
        counted(held.watchers, "chosen watcher"),
    ]
    return ", ".join(parts)


def delete(name: str) -> None:
    """Remove the session's directory. Claude Code's transcripts are elsewhere and stay."""
    directory = root() / name
    if not directory.is_dir() or directory.parent != root():
        raise ValueError(f"no session {name!r}")
    shutil.rmtree(directory)


def relabel(name: str, label: str) -> Record:
    record = load(name)
    if record is None:
        raise ValueError(f"no session {name!r}")
    record.label = label
    write(record)
    return record


def reassign(old: str, new: str) -> list[str]:
    """Move every session of profile `old` to `new`, by its record. The sessions moved."""
    moved = []
    for name in names():
        record = load(name)
        if record is not None and record.profile == old:
            record.profile = new
            write(record)
            moved.append(name)
    return moved
