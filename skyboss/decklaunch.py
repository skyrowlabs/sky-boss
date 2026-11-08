"""The screen `sb deck` opens with no profile: resume, a profile, or the folders ticked. See [[command-deck]] round 20.

Pure: rows, drawing and keys are decided here, and `deck.py` does the prompting, the writing
and the starting. The edits to `deck.toml` splice it by line and are checked by parsing the
result, as the `+` does.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field, replace

from skyboss import deckplus, tools

RESUME, PROFILE, FOLDER, ADD = "resume", "profile", "folder", "add"
#: What a key or a row asks the caller to do.
START, OPEN, NEW, DELETE, SAVE, QUIT = "start", "open", "new", "delete", "save", "quit"
HEADINGS = {RESUME: "Last deck", PROFILE: "Profiles", FOLDER: "Agent folders"}
HEADER = re.compile(r"^\s*\[")


@dataclass(frozen=True)
class Row:
    kind: str
    name: str
    text: str
    #: A folder's directory, for one not yet declared as an agent.
    cwd: str = ""


@dataclass
class Launch:
    rows: list[Row]
    ticked: set[str] = field(default_factory=set)
    at: int = 0
    #: Inside a running deck the screen manages; it opens nothing but a tab.
    running: bool = False
    note: str = ""


@dataclass(frozen=True)
class Outcome:
    action: str
    row: Row | None = None
    names: tuple[str, ...] = ()


def rows_of(
    resume: tuple[str, int] | None,
    profiles: dict[str, int],
    folders: list[tuple[str, str, bool]],
    running: bool = False,
) -> list[Row]:
    """The screen's rows: the last deck, each profile with its tab count, each folder, then `add`.

    `folders` is `(name, directory, declared)`. Running, there is no last deck to resume.
    """
    rows: list[Row] = []
    if resume and not running:
        rows.append(Row(RESUME, resume[0], f"resume {resume[0]}, {resume[1]} tab{'s' if resume[1] != 1 else ''}"))
    width = max((len(name) for name in profiles), default=0)
    rows += [
        Row(PROFILE, name, f"{name:<{width}}  {count} tab{'s' if count != 1 else ''}")
        for name, count in profiles.items()
    ]
    width = max((len(name) for name, _, _ in folders), default=0)
    rows += [
        Row(FOLDER, name, f"{name:<{width}}  {short(cwd)}", "" if declared else cwd) for name, cwd, declared in folders
    ]
    rows.append(Row(ADD, "", "+ add a folder"))
    return rows


def short(path: str) -> str:
    """`path` with the home directory written `~`, as the operator would type it."""
    home = os.path.expanduser("~")
    return "~" + path[len(home) :] if path == home or path.startswith(home + os.sep) else path


def hint(launch: Launch) -> str:
    row = launch.rows[launch.at] if launch.rows else None
    keys = ["space tick"] if row and row.kind == FOLDER else []
    if row and row.kind == FOLDER:
        keys.append("enter open tab" if launch.running else "enter start")
    elif row and row.kind in (RESUME, PROFILE) and not launch.running:
        keys.append("enter open")
    if launch.ticked:
        keys.append("s save as profile")
    if row and row.kind in (PROFILE, FOLDER) and not row.cwd:
        keys.append("d delete")
    return "  ".join([*keys, "a add folder", "q quit"])


def screen(launch: Launch, width: int) -> list[tuple[str, int | None]]:
    """Each line, with the row a click on it stands for. Pure."""
    title = "sky.boss deck — manage" if launch.running else "sky.boss deck"
    lines: list[tuple[str, int | None]] = [(title, None)]
    kind = ""
    for n, row in enumerate(launch.rows):
        if row.kind != kind and row.kind in HEADINGS:
            lines += [("", None), (HEADINGS[row.kind], None)]
        elif row.kind != kind:
            lines.append(("", None))
        kind = row.kind
        mark = ("[x] " if row.name in launch.ticked else "[ ] ") if row.kind == FOLDER else ""
        pointer = ">" if n == launch.at else " "
        lines.append((f" {pointer} {mark}{row.text}"[: max(1, width - 1)], n))
    lines += [("", None), (hint(launch)[: max(1, width - 1)], None)]
    if launch.note:
        lines.append((launch.note[: max(1, width - 1)], None))
    return lines


def step(launch: Launch, key: str | None, clicked_row: int | None = None) -> tuple[Launch, Outcome | None]:
    """What a key does: a new screen, and an outcome when the caller has work to do. Pure."""
    if not launch.rows:
        return launch, Outcome(QUIT)
    at = launch.at if clicked_row is None else clicked_row
    row = launch.rows[at]
    launch = replace(launch, at=at, note="")
    if clicked_row is not None:
        key = " " if row.kind == FOLDER else "\r"
    moves = {"up": -1, "down": 1, "pgup": -10, "pgdn": 10, "home": -len(launch.rows), "end": len(launch.rows)}
    if key in moves:
        return replace(launch, at=max(0, min(len(launch.rows) - 1, at + moves[key]))), None
    if key == " " and row.kind == FOLDER:
        return replace(launch, ticked=launch.ticked ^ {row.name}), None
    if key in ("q", "Q", "\x1b"):
        return launch, Outcome(QUIT)
    if key == "a" or (key in ("\r", "\n") and row.kind == ADD):
        return launch, Outcome(NEW)
    if key == "s":
        if not launch.ticked:
            return replace(launch, note="tick a folder or more first"), None
        return launch, Outcome(SAVE, names=_ticked(launch))
    if key == "d":
        if row.kind not in (PROFILE, FOLDER) or row.cwd:
            return replace(launch, note="only a profile or a declared folder can be deleted"), None
        return launch, Outcome(DELETE, row)
    if key in ("\r", "\n"):
        if row.kind == FOLDER:
            names = _ticked(launch) or (row.name,)
            return launch, Outcome(START, row, names)
        if launch.running:
            return replace(launch, note="a deck is running — exit it to open another"), None
        return launch, Outcome(OPEN, row)
    return launch, None


def _ticked(launch: Launch) -> tuple[str, ...]:
    """The ticked folders, in the order the screen lists them."""
    return tuple(row.name for row in launch.rows if row.kind == FOLDER and row.name in launch.ticked)


# ============================================================================
# deck.toml: removing a block, adding a profile
# ============================================================================


def without_block(text: str, table: str, name: str) -> str:
    """`text` without `[TABLE.NAME]` and the comment written directly above it. The next block's comment stays."""
    found = tools.block_range(text, name, table)
    if found is None:
        raise ValueError(f"no [{table}.{name}] in {deckplus.FILE}")
    lines = text.splitlines(keepends=True)
    start, end = found
    # The range runs to the next header, so comments and blanks just above that header belong to it.
    while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    while end < len(lines) and not lines[end].strip():
        end += 1
    # A comment touching the header describes this block, and would describe the next one if left.
    while start > 0 and lines[start - 1].lstrip().startswith("#"):
        start -= 1
    return "".join(lines[:start] + lines[end:])


def with_profile(text: str, name: str, names: tuple[str, ...]) -> str:
    """`text` with `[profile.NAME]` at its end: the first name primary, the rest its tabs."""
    primary, *tabs = names
    block = f"[profile.{name}]\nprimary = {tools._toml_string(primary)}\n"
    block += "tabs = [" + ", ".join(tools._toml_string(tab) for tab in tabs) + "]\n"
    body = text.rstrip("\n")
    return f"{body}\n\n{block}" if body else block


def edited(
    text: str, *, drop_profile: str = "", drop_agent: str = "", add_profile: tuple[str, tuple[str, ...]] | None = None
) -> str:
    """`text` with one change made, raising `ValueError` unless it parses to exactly that change."""
    try:
        was = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{deckplus.FILE} does not parse, so nothing was written — {exc}") from exc
    agents = dict(was.get("agent", {}))
    profiles = {key: dict(body) for key, body in was.get("profile", {}).items()}
    if drop_agent:
        holding = sorted(
            p for p, body in profiles.items() if drop_agent in [body.get("primary"), *body.get("tabs", [])]
        )
        if holding:
            raise ValueError(f"{drop_agent!r} is a tab in {', '.join(holding)} — delete or edit those first")
        new = without_block(text, "agent", drop_agent)
        agents.pop(drop_agent, None)
    elif drop_profile:
        new = without_block(text, "profile", drop_profile)
        profiles.pop(drop_profile, None)
    elif add_profile:
        name, names = add_profile
        if name in profiles:
            raise ValueError(f"there is a profile {name!r} already")
        new = with_profile(text, name, names)
        profiles[name] = {"primary": names[0], "tabs": list(names[1:])}
    else:
        return text
    try:
        now = tomllib.loads(new)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{deckplus.FILE} would not parse, so nothing was written — {exc}") from exc
    rest = {key: value for key, value in was.items() if key not in ("agent", "profile")}
    if (
        now.get("agent", {}) != agents
        or now.get("profile", {}) != profiles
        or {k: v for k, v in now.items() if k not in ("agent", "profile")} != rest
    ):
        raise ValueError(f"the edit to {deckplus.FILE} would change more than it should, so nothing was written")
    return new
