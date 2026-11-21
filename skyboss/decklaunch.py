"""The screen `sb deck` opens with no profile: sessions, profiles and agents. See [[command-deck]] rounds 20 and 25.

Pure: rows, drawing and keys are decided here, and `deck.py` does the prompting, the writing
and the starting. The edits to `deck.toml` splice it by line and are checked by parsing the
result, as the `+` does. The profile editor is a second tick list on the same loop.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field, replace

from skyboss import deckplus, tools
from skyboss.keys import BTAB

SESSION, PROFILE, NEW_PROFILE, SAVE_DECK, FOLDER, ADD = (
    "session",
    "profile",
    "new-profile",
    "save-deck",
    "folder",
    "add",
)
#: What a key or a row asks the caller to do.
START, OPEN, FRESH, RENAME, EDIT, NEW, DELETE, SAVE, QUIT = (
    "start",
    "open",
    "fresh",
    "rename",
    "edit",
    "new",
    "delete",
    "save",
    "quit",
)
#: The three sections, in screen order: a heading, the keys its rows take, and its row kinds.
SECTIONS = (
    ("Sessions", "enter attach/resume · d delete · r rename · f fresh", (SESSION,)),
    ("Profiles", "enter new session · e edit · d delete · r rename", (PROFILE, NEW_PROFILE, SAVE_DECK)),
    ("Agents", "space tick · enter start ad hoc · s save as profile · d delete", (FOLDER, ADD)),
)
HEADER = re.compile(r"^\s*\[")
GIT_ROOTS = re.compile(r"^[ \t]*git_roots\s*=", re.MULTILINE)


@dataclass(frozen=True)
class Row:
    kind: str
    name: str
    text: str
    #: A folder's directory, for one not yet declared as an agent.
    cwd: str = ""
    #: A session row: whether its deck is running, and whether it is the deck this screen is in.
    live: bool = False
    here: bool = False


@dataclass(frozen=True)
class SessionLine:
    """What a session row says: `name` is its tmux session, `holds` what it keeps in words."""

    name: str
    label: str
    profile: str = ""
    gone: bool = False
    tabs: int = 0
    live: bool = False
    age: str = ""
    holds: str = ""
    here: bool = False


@dataclass(frozen=True)
class ProfileLine:
    name: str
    agents: tuple[str, ...]
    primary: str = ""
    sessions: int = 0


@dataclass
class Launch:
    rows: list[Row]
    ticked: set[str] = field(default_factory=set)
    at: int = 0
    #: Inside a running deck: a folder opens as a tab there, and anything else as a deck beside it.
    running: bool = False
    note: str = ""


@dataclass(frozen=True)
class Outcome:
    action: str
    row: Row | None = None
    names: tuple[str, ...] = ()


def _tabs(count: int) -> str:
    return f"{count} tab{'s' if count != 1 else ''}"


def session_text(line: SessionLine, width: int) -> str:
    """`● label   profile · 4 tabs · running · 3 todos`: a running deck is `●`, a stopped one `○`."""
    label = f"{line.label} (profile gone)" if line.gone else line.label
    parts = [line.profile] if line.profile and not line.gone else []
    parts += [_tabs(line.tabs), "here" if line.here else "running" if line.live else line.age]
    parts += [line.holds] if line.holds else []
    return f"{'●' if line.live else '○'} {label:<{width}}  {' · '.join(p for p in parts if p)}"


def profile_text(line: ProfileLine, width: int) -> str:
    agents = ", ".join(f"{a}*" if a == line.primary else a for a in line.agents)
    count = f"{line.sessions} session{'s' if line.sessions != 1 else ''}"
    return f"{line.name:<{width}}  {agents} · {count}"


def rows_of(
    sessions: list[SessionLine],
    profiles: list[ProfileLine],
    folders: list[tuple[str, str, bool]],
    running: bool = False,
) -> list[Row]:
    """The screen's rows: sessions, then profiles and `+ new profile`, then folders and `+ add a folder`.

    `folders` is `(name, directory, declared)`. Running, Profiles ends with `save this deck as a profile`.
    """
    width = max((len(s.label) + 15 * s.gone for s in sessions), default=0)
    rows = [Row(SESSION, s.name, session_text(s, width), live=s.live, here=s.here) for s in sessions]
    width = max((len(p.name) for p in profiles), default=0)
    rows += [Row(PROFILE, p.name, profile_text(p, width)) for p in profiles]
    rows.append(Row(NEW_PROFILE, "", "+ new profile"))
    if running:
        rows.append(Row(SAVE_DECK, "", "save this deck as a profile"))
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


def section_of(kind: str) -> int:
    return next(n for n, (_, _, kinds) in enumerate(SECTIONS) if kind in kinds)


def row_keys(launch: Launch) -> list[str]:
    """The keys the row under the cursor takes, in the order the hint lists them."""
    row = launch.rows[launch.at] if launch.rows else None
    if row is None:
        return []
    if row.kind == SESSION:
        return ["enter attach" if row.live else "enter resume", "d delete", "r rename", "f fresh"]
    if row.kind == PROFILE:
        return ["enter new session", "e edit", "d delete", "r rename"]
    if row.kind == NEW_PROFILE:
        return ["enter new profile"]
    if row.kind == SAVE_DECK:
        return ["enter save"]
    keys = []
    if row.kind == FOLDER:
        keys = ["space tick", "enter open tab" if launch.running else "enter start ad hoc"]
    else:
        keys = ["enter add a folder"]
    if launch.ticked:
        keys.append("s save as profile")
    if row.kind == FOLDER and not row.cwd:
        keys.append("d delete")
    return keys


def hint(launch: Launch) -> str:
    return "  ".join([*row_keys(launch), "tab section", "q quit"])


def screen(launch: Launch, width: int) -> list[tuple[str, int | None]]:
    """Each line, with the row a click on it stands for. Pure."""
    title = "sky.boss deck — manage" if launch.running else "sky.boss deck"
    lines: list[tuple[str, int | None]] = [(title, None)]
    room = max(1, width - 1)
    for heading, keys, kinds in SECTIONS:
        if heading == "Agents" and launch.running:
            keys = keys.replace("start ad hoc", "open tab")
        lines += [("", None), (f"{heading:<12}{keys}"[:room], None)]
        held = [(n, row) for n, row in enumerate(launch.rows) if row.kind in kinds]
        if not held:
            lines.append(("   none yet: a profile or ticked agents start one"[:room], None))
        for n, row in held:
            mark = tick(row.name in launch.ticked) if row.kind == FOLDER else ""
            pointer = ">" if n == launch.at else " "
            lines.append((f" {pointer} {mark}{row.text}"[:room], n))
    lines += [("", None), (hint(launch)[:room], None)]
    if launch.note:
        lines.append((launch.note[:room], None))
    return lines


def tick(ticked: bool) -> str:
    """A tick list's box, shared by every screen that ticks rows."""
    return "[x] " if ticked else "[ ] "


def visible(lines: list[tuple[str, int | None]], launch: Launch, room: int) -> list[int]:
    """Which of `screen`'s lines fit in `room`: those around the cursor, and always the footer."""
    return around(lines, launch.at, launch.note, room)


def around(lines: list[tuple[str, int | None]], at: int, note: str, room: int) -> list[int]:
    """`visible` for any tick list whose footer is a blank, a hint and an optional note."""
    foot = 2 + bool(note)
    body = len(lines) - foot
    space = max(1, room - foot)
    cursor = next((n for n, (_, row) in enumerate(lines) if row == at), 0)
    first = deckplus.window(body, cursor, space)
    return [*range(first, min(body, first + space)), *range(body, len(lines))]


def _jump(launch: Launch, by: int) -> int:
    """The first row of the next section with rows, `by` sections on, wrapping."""
    here = section_of(launch.rows[launch.at].kind)
    for step_ in range(1, len(SECTIONS) + 1):
        kinds = SECTIONS[(here + by * step_) % len(SECTIONS)][2]
        first = next((n for n, row in enumerate(launch.rows) if row.kind in kinds), None)
        if first is not None:
            return first
    return launch.at


#: Each key a row kind takes, beyond enter, and what it asks for.
ROW_KEYS = {
    SESSION: {"d": DELETE, "r": RENAME, "f": FRESH},
    PROFILE: {"d": DELETE, "r": RENAME, "e": EDIT},
}


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
    if key in ("\t", BTAB):
        return replace(launch, at=_jump(launch, 1 if key == "\t" else -1)), None
    if key in ("q", "Q", "\x1b"):
        return launch, Outcome(QUIT)
    enter = key in ("\r", "\n")
    if key in ROW_KEYS.get(row.kind, {}):
        return launch, Outcome(ROW_KEYS[row.kind][key], row)
    if row.kind in (FOLDER, ADD):
        return _agents_step(launch, row, key)
    if enter and row.kind == NEW_PROFILE:
        return launch, Outcome(EDIT)
    if enter and row.kind == SAVE_DECK:
        return launch, Outcome(SAVE_DECK)
    if enter and row.kind == SESSION and row.here:
        return replace(launch, note="this is the deck you are in"), None
    if enter:
        return launch, Outcome(OPEN, row)
    return launch, None


def _agents_step(launch: Launch, row: Row, key: str | None) -> tuple[Launch, Outcome | None]:
    if key == " " and row.kind == FOLDER:
        return replace(launch, ticked=launch.ticked ^ {row.name}), None
    if key == "a" or (key in ("\r", "\n") and row.kind == ADD):
        return launch, Outcome(NEW)
    if key == "s":
        if not launch.ticked:
            return replace(launch, note="tick a folder or more first"), None
        return launch, Outcome(SAVE, names=_ticked(launch))
    if key == "d":
        if row.kind != FOLDER or row.cwd:
            return replace(launch, note="only a declared folder can be deleted"), None
        return launch, Outcome(DELETE, row)
    if key in ("\r", "\n"):
        names = _ticked(launch) or (row.name,)
        return launch, Outcome(START, row, names)
    return launch, None


def _ticked(launch: Launch) -> tuple[str, ...]:
    """The ticked folders, in the order the screen lists them."""
    return tuple(row.name for row in launch.rows if row.kind == FOLDER and row.name in launch.ticked)


# ============================================================================
# The profile editor: which agents, which leads, in what order, and the brief
# ============================================================================


@dataclass
class Editor:
    """A profile being edited. `rows` is every declared agent in the order a written profile lists them."""

    name: str
    rows: list[str]
    ticked: set[str] = field(default_factory=set)
    primary: str = ""
    brief: str = ""
    brief_file: str = ""
    at: int = 0
    note: str = ""


def editor_of(name: str, agents: list[str], body: dict | None = None) -> Editor:
    """The editor for profile NAME, or an empty one: the profile's agents first, primary leading."""
    body = body or {}
    primary = str(body.get("primary") or "")
    listed = [n for n in [primary, *body.get("tabs", [])] if n]
    listed = list(dict.fromkeys(listed))
    rows = [*listed, *(a for a in agents if a not in listed)]
    return Editor(
        name,
        rows,
        set(listed),
        primary or (listed[0] if listed else ""),
        str(body.get("brief") or ""),
        str(body.get("brief_file") or ""),
    )


def editor_body(editor: Editor) -> dict:
    """The profile's agent keys and brief as the editor holds them: the primary, then the ticked in row order."""
    ticked = [n for n in editor.rows if n in editor.ticked]
    primary = editor.primary if editor.primary in editor.ticked else (ticked[0] if ticked else "")
    return {
        "primary": primary,
        "tabs": [n for n in ticked if n != primary],
        "brief": editor.brief,
        "brief_file": editor.brief_file,
    }


def editor_screen(editor: Editor, width: int) -> list[tuple[str, int | None]]:
    room = max(1, width - 1)
    title = f"Profile {editor.name}" if editor.name else "New profile"
    lines: list[tuple[str, int | None]] = [(title, None), ("", None)]
    for n, name in enumerate(editor.rows):
        pointer = ">" if n == editor.at else " "
        lead = "  primary" if name == editor.primary and name in editor.ticked else ""
        lines.append((f" {pointer} {tick(name in editor.ticked)}{name}{lead}"[:room], n))
    if not editor.rows:
        lines.append(("   no agents declared: add a folder first", None))
    if editor.brief_file:
        told = f"brief file: {editor.brief_file}"
    else:
        first = editor.brief.strip().splitlines()[0] if editor.brief.strip() else ""
        told = f"brief: {first}" if first else "brief: none"
    lines += [("", None), (told[:room], None)]
    keys = "space tick  p primary  [ ] move  b brief  B brief file  enter write  q cancel"
    lines += [("", None), (keys[:room], None)]
    if editor.note:
        lines.append((editor.note[:room], None))
    return lines


def editor_visible(lines: list[tuple[str, int | None]], editor: Editor, room: int) -> list[int]:
    return around(lines, editor.at, editor.note, room)


def editor_step(editor: Editor, key: str | None, clicked_row: int | None = None) -> tuple[Editor, str | None]:
    """A key in the editor: a new state, and `SAVE`, `QUIT`, `brief` or `brief_file` for the caller. Pure."""
    at = editor.at if clicked_row is None else clicked_row
    editor = replace(editor, at=at, note="")
    if clicked_row is not None:
        key = " "
    if key in ("q", "Q", "\x1b"):
        return editor, QUIT
    if key in ("\r", "\n"):
        if not editor.ticked:
            return replace(editor, note="tick an agent or more first"), None
        return editor, SAVE
    if key == "b":
        return editor, "brief"
    if key == "B":
        return editor, "brief_file"
    if not editor.rows:
        return editor, None
    name = editor.rows[at]
    moves = {"up": -1, "down": 1, "pgup": -10, "pgdn": 10, "home": -len(editor.rows), "end": len(editor.rows)}
    if key in moves:
        return replace(editor, at=max(0, min(len(editor.rows) - 1, at + moves[key]))), None
    if key == " ":
        ticked = editor.ticked ^ {name}
        primary = editor.primary if editor.primary in ticked else next((n for n in editor.rows if n in ticked), "")
        return replace(editor, ticked=ticked, primary=primary), None
    if key == "p":
        return replace(editor, ticked=editor.ticked | {name}, primary=name), None
    if key in ("[", "]"):
        to = at + (-1 if key == "[" else 1)
        if not 0 <= to < len(editor.rows):
            return editor, None
        rows = list(editor.rows)
        rows[at], rows[to] = rows[to], rows[at]
        return replace(editor, rows=rows, at=to), None
    return editor, None


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


#: A profile's keys in the order a written block lists them.
PROFILE_ORDER = ("primary", "tabs", "terminals", "brief", "brief_file", "session", "columns")


def _value(value) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    return tools._toml_string(str(value))


def profile_block(name: str, body: dict) -> str:
    """`[profile.NAME]` with each key of `body` that has a value, in `PROFILE_ORDER`."""
    keys = [key for key in PROFILE_ORDER if body.get(key)] + sorted(k for k in body if k not in PROFILE_ORDER)
    return f"[profile.{name}]\n" + "".join(f"{key} = {_value(body[key])}\n" for key in keys)


def body_of(names: tuple[str, ...], terminals: tuple[str, ...] = ()) -> dict:
    """A profile body: the first name primary, the rest its tabs, and any terminal directories."""
    body: dict = {"primary": names[0], "tabs": list(names[1:])}
    if terminals:
        body["terminals"] = list(terminals)
    return body


def with_profile(text: str, name: str, body: dict) -> str:
    """`text` with `[profile.NAME]` at its end."""
    stripped = text.rstrip("\n")
    block = profile_block(name, body)
    return f"{stripped}\n\n{block}" if stripped else block


def replaced_profile(text: str, name: str, body: dict) -> str:
    """`text` with `[profile.NAME]`'s block rewritten as `body`. The comment above it stays: it is the same profile."""
    found = tools.block_range(text, name, "profile")
    if found is None:
        raise ValueError(f"no [profile.{name}] in {deckplus.FILE}")
    lines = text.splitlines(keepends=True)
    start, end = found
    while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    return "".join(lines[:start]) + profile_block(name, body) + "".join(lines[end:])


def renamed_profile(text: str, old: str, new: str) -> str:
    """`text` with `[profile.OLD]`'s header reading `[profile.NEW]`; its keys and comments stay."""
    found = tools.block_range(text, old, "profile")
    if found is None:
        raise ValueError(f"no [profile.{old}] in {deckplus.FILE}")
    lines = text.splitlines(keepends=True)
    line = lines[found[0]]
    lines[found[0]] = line.replace(f"[profile.{old}]", f"[profile.{new}]", 1)
    return "".join(lines)


def with_git_roots(text: str, roots: list[str]) -> str:
    """`text` with top-level `git_roots` set: replaced where it is, else after the last key above any table."""
    line = "git_roots = [" + ", ".join(tools._toml_string(root) for root in roots) + "]\n"
    found = GIT_ROOTS.search(text)
    if found:
        close = text.find("]", found.start())
        end = text.find("\n", close)
        return text[: found.start()] + line + text[end + 1 if end >= 0 else len(text) :]
    lines = text.splitlines(keepends=True)
    head = next((n for n, each in enumerate(lines) if HEADER.match(each)), len(lines))
    keys = [n for n, each in enumerate(lines[:head]) if each.strip() and not each.lstrip().startswith("#")]
    at = keys[-1] + 1 if keys else 0
    if at and not lines[at - 1].endswith("\n"):
        lines[at - 1] += "\n"
    return "".join([*lines[:at], line, *lines[at:]])


def edited(
    text: str,
    *,
    drop_profile: str = "",
    drop_agent: str = "",
    add_profile: tuple[str, dict] | None = None,
    set_profile: tuple[str, dict] | None = None,
    rename_profile: tuple[str, str] | None = None,
    git_roots: list[str] | None = None,
) -> str:
    """`text` with one change made, raising `ValueError` unless it parses to exactly that change."""
    try:
        was = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{deckplus.FILE} does not parse, so nothing was written — {exc}") from exc
    agents = dict(was.get("agent", {}))
    profiles = {key: dict(body) for key, body in was.get("profile", {}).items()}
    rest = {key: value for key, value in was.items() if key not in ("agent", "profile")}
    if git_roots is not None:
        new = with_git_roots(text, git_roots)
        rest["git_roots"] = git_roots
    elif drop_agent:
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
        name, body = add_profile
        if name in profiles:
            raise ValueError(f"there is a profile {name!r} already")
        new = with_profile(text, name, body)
        profiles[name] = {key: value for key, value in body.items() if value}
    elif set_profile:
        name, body = set_profile
        new = replaced_profile(text, name, body)
        profiles[name] = {key: value for key, value in body.items() if value}
    elif rename_profile:
        old, name = rename_profile
        if name in profiles:
            raise ValueError(f"there is a profile {name!r} already")
        new = renamed_profile(text, old, name)
        profiles = {name if key == old else key: body for key, body in profiles.items()}
    else:
        return text
    try:
        now = tomllib.loads(new)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{deckplus.FILE} would not parse, so nothing was written — {exc}") from exc
    if (
        now.get("agent", {}) != agents
        or now.get("profile", {}) != profiles
        or {k: v for k, v in now.items() if k not in ("agent", "profile")} != rest
    ):
        raise ValueError(f"the edit to {deckplus.FILE} would change more than it should, so nothing was written")
    return new
