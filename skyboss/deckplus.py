"""What the deck's `+` can open, and the edit it makes to `deck.toml`.

The places are pure reads of the declarations and the `roots`. The edit splices the file by
line, as `tools.toml` is, so every other byte survives; it is checked by parsing the result.
See [[command-deck]] round 16.
"""

from __future__ import annotations

import os
import re
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from skyboss import tools

FILE = "deck.toml"
TABS = re.compile(r"^\s*tabs\s*=")


@dataclass(frozen=True)
class Place:
    """One directory a tab can start in. `declared` means `name` is an agent already."""

    name: str
    cwd: str
    source: str
    declared: bool = False
    problem: str = ""


def _folders(root: str) -> list[Path]:
    try:
        return sorted(p for p in Path(root).iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return []


def places(declared: list[tuple[str, str, str]], roots: list[str], name_ok: re.Pattern) -> list[Place]:
    """`declared` as `(name, directory, source)`, then each new folder under `roots`.

    A folder an agent already holds is that agent. One that cannot be a tab's name says why
    rather than going missing.
    """
    out = [Place(name, cwd, source, declared=True) for name, cwd, source in declared]
    held = {os.path.realpath(place.cwd) for place in out}
    names = {place.name for place in out}
    for root in roots:
        for folder in _folders(root):
            real = os.path.realpath(folder)
            if real in held:
                continue
            held.add(real)
            problem = ""
            if not name_ok.match(folder.name):
                problem = "this folder's name cannot be a tab's name"
            elif folder.name in names:
                problem = f"the name {folder.name!r} is taken by another folder"
            names.add(folder.name)
            out.append(Place(folder.name, str(folder), "roots", problem=problem))
    return out


def _string(value: str) -> str:
    return tools._toml_string(value)


def with_agent(text: str, name: str, cwd: str, role: str = "") -> str:
    """`text` with an `[agent.NAME]` block at its end."""
    block = f"[agent.{name}]\ncwd = {_string(cwd)}\n"
    if role:
        block += f"role = {_string(role)}\n"
    body = text.rstrip("\n")
    return f"{body}\n\n{block}" if body else block


def with_tab(text: str, profile: str, name: str) -> str:
    """`text` with `name` last in `[profile.PROFILE]`'s `tabs`, which may span lines."""
    found = tools.block_range(text, profile, "profile")
    if found is None:
        raise ValueError(f"no [profile.{profile}] in {FILE}")
    lines = text.splitlines(keepends=True)
    start, end = found
    at = next((i for i in range(start + 1, end) if TABS.match(lines[i])), None)
    if at is None:
        lines.insert(start + 1, f"tabs = [{_string(name)}]\n")
        return "".join(lines)
    offset = sum(len(line) for line in lines[:at])
    close = text.find("]", offset)
    if close < 0:
        raise ValueError(f"[profile.{profile}]'s tabs never closes")
    before = text[:close]
    head = before.rstrip()
    joiner = "" if head.endswith("[") else " " if head.endswith(",") else ", "
    return f"{head}{joiner}{_string(name)}{before[len(head):]}{text[close:]}"


def edited(text: str, name: str, cwd: str, role: str, profile: str) -> str:
    """`text` with the agent declared, if `cwd` is given, and in the profile, if one is.

    Raises `ValueError` unless the new text parses to exactly that change.
    """
    try:
        was = tomllib.loads(text)
        new = with_agent(text, name, cwd, role) if cwd else text
        new = with_tab(new, profile, name) if profile else new
        now = tomllib.loads(new)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{FILE} would not parse, so nothing was written — {exc}") from exc
    agents = dict(was.get("agent", {}))
    if cwd:
        agents[name] = {"cwd": cwd, **({"role": role} if role else {})}
    profiles = {key: dict(body) for key, body in was.get("profile", {}).items()}
    if profile:
        profiles[profile]["tabs"] = [*profiles[profile].get("tabs", []), name]
    if now.get("agent", {}) != agents or now.get("profile", {}) != profiles:
        raise ValueError(f"the edit to {FILE} would change more than it should, so nothing was written")
    return new


def write(path: Path, text: str) -> Path | None:
    """Back the file up, then replace it through a rename. The backup, if there was anything to keep."""
    kept = tools.keep_copy(path, "deck")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".deck.", suffix=".toml")
    with os.fdopen(handle, "w") as out:
        out.write(text)
    os.replace(temp, path)
    return kept


def window(count: int, at: int, room: int) -> int:
    """The first row to draw of `count`, so row `at` is on a screen of `room` rows."""
    return max(0, min(at - room // 2, count - room))
