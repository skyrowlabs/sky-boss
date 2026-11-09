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
from typing import Sequence

from skyboss import tools

FILE = "deck.toml"
TABS = re.compile(r"^\s*tabs\s*=")
GIT_DEPTH = 4
NOT_SEARCHED = frozenset({"node_modules"})


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


def git_projects(root: str, depth: int = GIT_DEPTH) -> list[Path]:
    """Each git checkout at or under `root`, at most `depth` levels down. A checkout is not searched inside."""
    if (Path(root) / ".git").exists():
        return [Path(root)]
    if depth == 0:
        return []
    found: list[Path] = []
    for folder in _folders(root):
        if folder.name not in NOT_SEARCHED and not folder.is_symlink():
            found += git_projects(str(folder), depth - 1)
    return found


def tab_name(folder: str) -> str:
    """A folder's name as a tab can carry it: a dot or any other mark becomes a dash."""
    return re.sub(r"[^A-Za-z0-9_-]+", "-", folder).strip("-")


def places(
    declared: list[tuple[str, str, str]], roots: list[str], name_ok: re.Pattern, git_roots: Sequence[str] = ()
) -> list[Place]:
    """`declared` as `(name, directory, source)`, then each new folder under `roots` and git project under `git_roots`.

    A folder an agent already holds is that agent. One that cannot be a tab's name says why
    rather than going missing.
    """
    out = [Place(name, cwd, source, declared=True) for name, cwd, source in declared]
    held = {os.path.realpath(place.cwd) for place in out}
    names = {place.name for place in out}
    found = [(folder, "roots") for root in roots for folder in _folders(root)]
    found += [(folder, "git_roots") for root in git_roots for folder in git_projects(root)]
    for folder, source in found:
        real = os.path.realpath(folder)
        if real in held:
            continue
        held.add(real)
        problem, name = "", tab_name(folder.name)
        if not name_ok.match(name):
            problem = "this folder's name cannot be a tab's name"
        elif name in names:
            problem = f"the name {name!r} is taken by another folder"
        names.add(name)
        out.append(Place(name, str(folder), source, problem=problem))
    return out


def browse(path: str, scanned: bool = False) -> tuple[list[str], list[str]]:
    """The folder browser at `path`: each row, and the directory it stands for. Rows 0 and 1 act on `path`."""
    parent = os.path.dirname(path)
    up = [parent] if parent != path else []
    below = _folders(path)
    scan = "✕ stop listing the git projects under here" if scanned else "⌕ list every git project under here"
    return (
        ["✓ add this folder", scan, *[".." for _ in up], *[f"{folder.name}/" for folder in below]],
        [path, path, *up, *[str(folder) for folder in below]],
    )


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
