"""The deck's saved tabs: which session each tab held, so a later `sb deck` can resume it.

The marks loop keeps this current, so a reboot finds it; `sb deck save` and `sb deck exit`
write it exactly. It holds session ids and never a transcript. See [[command-deck]] round 11.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from skyboss import helpers

FILE = "saved.json"


@dataclass(frozen=True)
class Tab:
    agent: str
    id: str
    cwd: str = ""


@dataclass(frozen=True)
class Terminal:
    """A terminal tab: its directory comes back, and its shell starts new."""

    name: str
    cwd: str = ""


@dataclass
class Saved:
    tabs: list[Tab] = field(default_factory=list)
    primary: str = ""
    profile: str = ""
    at: float = 0.0
    terminals: list[Terminal] = field(default_factory=list)


def path_for(session: str) -> Path:
    return helpers.STATE_DIR / "deck" / session / FILE


def load(session: str) -> tuple[Saved, list[str]]:
    """The save, and a problem if one exists that cannot be read. Absent is simply empty."""
    path = path_for(session)
    try:
        record = json.loads(path.read_text())
        tabs = [Tab(str(t["agent"]), str(t["id"]), str(t.get("cwd") or "")) for t in record["tabs"]]
        terminals = [Terminal(str(t["name"]), str(t.get("cwd") or "")) for t in record.get("terminals", [])]
        primary, profile = str(record.get("primary") or ""), str(record.get("profile") or "")
        return Saved(tabs, primary, profile, float(record.get("at") or 0), terminals), []
    except FileNotFoundError:
        return Saved(), []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return Saved(), [f"the deck's save {path} is unreadable, so no tab resumes — {exc}"]


def save(session: str, saved: Saved) -> None:
    """Written whole through a rename, so a reader never sees half a save."""
    path = path_for(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".saved.", suffix=".json")
    with os.fdopen(handle, "w") as out:
        json.dump(
            {
                "at": time.time(),
                "primary": saved.primary,
                "profile": saved.profile,
                "tabs": [{"agent": t.agent, "id": t.id, "cwd": t.cwd} for t in saved.tabs],
                "terminals": [{"name": t.name, "cwd": t.cwd} for t in saved.terminals],
            },
            out,
            indent=1,
        )
    os.replace(temp, path)


def clear(session: str) -> None:
    path_for(session).unlink(missing_ok=True)


def merged(saved: list[Tab], live: list[Tab]) -> list[Tab]:
    """`live` in order, then each saved tab no live one replaces.

    Never drops a tab: at shutdown the tabs die before the loop does, and it must not save that.
    """
    held = {tab.agent for tab in live}
    return [*live, *(tab for tab in saved if tab.agent not in held)]
