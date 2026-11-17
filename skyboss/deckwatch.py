"""What deck agents leave running, gathered for the WATCHERS pane. See [[command-deck]] round 23.

**A watcher is read, never driven.** Nothing here stops, restarts or types into one: the tab
that started it owns it. A background shell's stream is its `tasks/<id>.output` file, a
daemon job's is its `timeline.jsonl`; a Monitor and a sub-agent have no stream anyone else
can read, so they are a header alone.

**A stream ends in words.** `running` and `quiet` are a stat of a live watcher's file,
`ended` is a chosen watcher no longer running, and `gone` is one whose file is gone. The
colours are `chrome.ROLE`'s for `running`, `quiet`, `dead` and `absent`.

**The choice is machine state.** `watchers.json` beside `column.json` keeps each chosen key
with enough to draw it once ended; the deck's sweep drops an ended key and counts it.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from skyboss import agents as agents_
from skyboss import background, decklaunch, helpers, shellwatch
from skyboss.chrome import ROLE, ago, clock

SHELL, MONITOR, AGENT, JOB = background.SHELL, background.MONITOR, background.AGENT, "job"
#: The owner a daemon job is grouped under: no tab started it.
DAEMON = "daemon"
FILE = "watchers.json"
#: Lines of a stream drawn under its header.
TAIL = 4
TAIL_BYTES = 64 * 1024
#: Seconds since a stream's last write after which it reads `quiet`.
QUIET_AFTER = 10.0
#: A daemon job's `state` words that mean it has finished (measured: done, stopped, blocked, working).
JOB_ENDED = frozenset({"done", "stopped", "failed", "error", "cancelled"})
#: Each word a stream ends in, and the chrome attention it borrows its colour from.
ENDS = {"running": ROLE["running"], "quiet": ROLE["quiet"], "ended": ROLE["dead"], "gone": ROLE["absent"]}
#: Terminal control sequences and other control characters, which a pane must not replay.
CONTROL = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b.|[\x00-\x08\x0b-\x1f\x7f]")
SAVE, QUIT = "save", "quit"


@dataclass(frozen=True)
class Watcher:
    key: str
    owner: str
    kind: str
    command: str
    #: Running for (a shell), since its last write (a sub-agent) or since its update (a job).
    seconds: float
    path: str = ""
    state: str = ""
    detail: str = ""
    #: The owning tab's colour slot, -1 for none.
    slot: int = -1
    ended: bool = False

    def age(self) -> str:
        if self.kind == JOB:
            return f"updated {ago(self.seconds)} ago"
        if self.kind == AGENT:
            return f"wrote {ago(self.seconds)} ago"
        return f"running {ago(self.seconds)}"

    def label(self) -> str:
        """The command, and for a job its state and detail."""
        if self.kind != JOB:
            return self.command
        said = f"{self.state}: {self.detail}" if self.detail and self.detail != self.state else self.state
        return f"{self.command} · {said}" if said else self.command

    def record(self) -> dict:
        """What `watchers.json` keeps, so an ended watcher can still be drawn."""
        return {"owner": self.owner, "kind": self.kind, "command": self.command, "path": self.path}


def tab_watchers(
    owner: str, ident: str, cwd: str, pid: int, parent_of: dict[int, int], proc: Path, projects: Path, now: float
) -> list[Watcher]:
    """The shells, Monitors and sub-agents one tab's session has running."""
    out: list[Watcher] = []
    for child, line in background.shell_lines(pid, parent_of, proc):
        kind, path = background.output_of(child, proc)
        found = background.TASK_FILE.search(path)
        start = agents_.proc_start(child, proc) or ""
        key = f"{ident}:{found.group('task')}" if found else f"{ident}:{kind}:{child}:{start}"
        seconds = shellwatch.running_seconds(child, proc)
        out.append(Watcher(key, owner, kind, background.command_of(line), seconds, path))
    for agent, wrote, label in background.subagent_records(cwd, ident, projects, now):
        out.append(Watcher(f"{ident}:agent:{agent}", owner, AGENT, label, max(0.0, now - wrote)))
    return out


def daemon_jobs(root: Path, now: float) -> tuple[list[Watcher], list[str]]:
    """Each `<root>/<id>/state.json` as a watcher, newest update first, and problems."""
    try:
        folders = sorted(path for path in root.iterdir() if path.is_dir())
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        return [], [f"could not read {root} — {exc}"]
    found: list[Watcher] = []
    for folder in folders:
        try:
            state = json.loads((folder / "state.json").read_text())
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            found.append(Watcher(f"job:{folder.name}", DAEMON, JOB, folder.name, 0.0, state=f"unreadable — {exc}"))
            continue
        if not isinstance(state, dict):
            continue
        word = str(state.get("state") or "")
        where = decklaunch.short(str(state.get("cwd") or ""))
        name = str(state.get("name") or folder.name)
        command = f"{name} · {where}" if where else name
        seconds = _since(str(state.get("updatedAt") or ""), now)
        path = str(folder / "timeline.jsonl")
        detail = " ".join(str(state.get("detail") or "").split())
        found.append(
            Watcher(f"job:{folder.name}", DAEMON, JOB, command, seconds, path, word, detail, -1, word in JOB_ENDED)
        )
    return sorted(found, key=lambda each: each.seconds), []


def _since(stamp: str, now: float) -> float:
    try:
        return max(0.0, now - datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0.0


# ============================================================================
# Streams
# ============================================================================


def clean(text: str) -> str:
    """One line as a pane may draw it: a carriage return keeps what was drawn last, controls go."""
    return CONTROL.sub("", text.rsplit("\r", 1)[-1].replace("\t", "  ")).rstrip()


def tail(path: str, count: int = TAIL) -> list[str] | None:
    """The last `count` non-blank lines of `path`, cleaned; None when it is not there."""
    try:
        with open(path, "rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            handle.seek(max(0, size - TAIL_BYTES))
            raw = handle.read().decode("utf-8", errors="replace")
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError:
        return []
    lines = raw.splitlines()
    if size > TAIL_BYTES and lines:
        # The first line read began mid-line.
        lines = lines[1:]
    kept = [line for line in (clean(each) for each in lines) if line]
    return kept[-count:] if count else []


def timeline(lines: list[str]) -> list[str]:
    """A job's `timeline.jsonl` lines as `HH:MM:SS state · detail`; one that is not JSON stays as it is."""
    out: list[str] = []
    for line in lines:
        try:
            entry = json.loads(line)
            at = datetime.fromisoformat(str(entry.get("at", "")).replace("Z", "+00:00")).timestamp()
        except (ValueError, AttributeError):
            out.append(line)
            continue
        detail = " ".join(str(entry.get("detail") or "").split())
        out.append(f"{clock(at)} {entry.get('state', '')} · {detail}".rstrip(" ·"))
    return out


def ending(watcher: Watcher | None, record: dict, now: float, stat=os.stat) -> tuple[str, str]:
    """The word a chosen stream ends in, and what it adds. `watcher` is None once it has stopped running."""
    path = watcher.path if watcher is not None else str(record.get("path") or "")
    wrote = now
    if path:
        try:
            wrote = stat(path).st_mtime
        except OSError:
            return "gone", "its file is gone"
    if watcher is None:
        return "ended", "no longer running"
    if watcher.ended:
        return "ended", watcher.state
    if not path:
        return "", ""
    quiet = max(0.0, now - wrote)
    return ("running", f"wrote {ago(quiet)} ago") if quiet < QUIET_AFTER else ("quiet", f"untouched {ago(quiet)}")


# ============================================================================
# The pane
# ============================================================================


def _row(kind: str, parts: list, key: str = "", running: int = 0, chosen: int = 0) -> dict:
    return {
        "watchers": "".join(str(part[0]) for part in parts),
        "parts": parts,
        "kind": kind,
        "watcher": key,
        "running": running,
        "chosen": chosen,
    }


def rows_of(
    listed: list[Watcher],
    chosen: dict[str, dict],
    dropped: int,
    now: float,
    hint: str,
    colour=lambda watcher: None,
    stat=os.stat,
) -> list[dict]:
    """A block per chosen watcher, header then stream then its end; never no rows."""
    by_key = {watcher.key: watcher for watcher in listed}
    running = sum(1 for watcher in listed if not watcher.ended)
    order = [w.key for w in listed if w.key in chosen] + [key for key in chosen if key not in by_key]
    rows: list[dict] = []

    def add(kind: str, parts: list, key: str = "") -> None:
        rows.append(_row(kind, parts, key, running, len(order)))

    if not order:
        said = f"{running} watcher{'' if running == 1 else 's'} running" if running else "nothing running to watch"
        add("note", [[said, None], [f" · {hint}", "sb.muted"]])
    for key in order:
        watcher = by_key.get(key)
        record = chosen[key] if watcher is None else watcher.record()
        owner, kind = str(record.get("owner") or ""), str(record.get("kind") or "")
        label = watcher.label() if watcher is not None else str(record.get("command") or "")
        age = [[f" · {watcher.age()}", "sb.muted"]] if watcher is not None else []
        add("head", [[owner, colour(watcher) or "sb.accent"], [f" · {kind} ", "sb.muted"], [label, None], *age], key)
        path = watcher.path if watcher is not None else str(record.get("path") or "")
        lines = (tail(path) or []) if path else []
        for line in timeline(lines) if kind == JOB else lines:
            add("line", [[f"  {line}", None]], key)
        word, more = ending(watcher, record, now, stat)
        if word:
            add("end", [[f"  · {word}", ENDS[word]], *([[f" · {more}", "sb.muted"]] if more else [])], key)
    if order:
        rest = sum(1 for w in listed if w.key not in chosen and not w.ended)
        if rest:
            add("note", [[f"{rest} more running", None], [f" · {hint}", "sb.muted"]])
    if dropped:
        add("note", [[f"{dropped} ended and dropped since the last pick", "sb.muted"]])
    return rows


def view_of(rows: list[dict]) -> dict:
    from skyboss.view import describe

    column = describe("watchers", rows)
    column["segments"] = "parts"
    return {
        "columns": [column],
        "details": [],
        "hidden": ["parts", "kind", "watcher", "running", "chosen"],
        "authored": True,
    }


# ============================================================================
# watchers.json
# ============================================================================


def path_for(session: str) -> Path:
    return helpers.STATE_DIR / "deck" / session / FILE


def load(session: str) -> tuple[dict[str, dict], int, list[str]]:
    """The chosen keys and their records, how many the sweep has dropped, and problems. Never raises."""
    path = path_for(session)
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return {}, 0, []
    except (OSError, ValueError) as exc:
        return {}, 0, [f"{path.name} unreadable, so no watcher is chosen — {exc}"]
    chosen = raw.get("chosen") if isinstance(raw, dict) else None
    if not isinstance(chosen, dict):
        return {}, 0, [f"{path.name} has no `chosen` table, so no watcher is chosen"]
    dropped = raw.get("dropped", 0)
    return {str(k): v for k, v in chosen.items() if isinstance(v, dict)}, dropped if isinstance(dropped, int) else 0, []


def save(session: str, chosen: dict[str, dict], dropped: int = 0) -> None:
    """Written whole through a rename, so a pane never reads half a choice."""
    path = path_for(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".watchers.", suffix=".json")
    with os.fdopen(handle, "w") as out:
        json.dump({"chosen": chosen, "dropped": dropped}, out, indent=1)
    os.replace(temp, path)


def sweep(session: str, listed: list[Watcher]) -> int:
    """Drop each chosen key whose watcher has ended or gone, and count it. How many went."""
    chosen, dropped, problems = load(session)
    if problems:
        return 0
    live = {watcher.key for watcher in listed if not watcher.ended}
    gone = [key for key in chosen if key not in live]
    if gone:
        save(session, {k: v for k, v in chosen.items() if k in live}, dropped + len(gone))
    return len(gone)


# ============================================================================
# The picker: the launcher's tick list over every watcher
# ============================================================================


@dataclass
class Pick:
    rows: list[Watcher]
    ticked: set[str] = field(default_factory=set)
    at: int = 0
    note: str = ""


HINT = "space tick  a all  n none  enter save  q cancel"


def screen(pick: Pick, width: int) -> list[tuple[str, int | None]]:
    """Each line, with the row a click on it stands for: grouped by owner, as listed. Pure."""
    cut = max(1, width - 1)
    lines: list[tuple[str, int | None]] = [("watchers — tick any, or none", None)]
    if not pick.rows:
        lines += [("", None), ("  nothing is running to watch", None)]
    owner = None
    kinds = max((len(watcher.kind) for watcher in pick.rows), default=0)
    for n, watcher in enumerate(pick.rows):
        if watcher.owner != owner:
            owner = watcher.owner
            lines += [("", None), (owner, None)]
        pointer = ">" if n == pick.at else " "
        ended = "ended · " if watcher.ended else ""
        box = decklaunch.tick(watcher.key in pick.ticked)
        text = f" {pointer} {box}{watcher.kind:<{kinds}}  {ago(watcher.seconds):>3}  {ended}{watcher.label()}"
        lines.append((text[:cut], n))
    lines += [("", None), (HINT[:cut], None)]
    if pick.note:
        lines.append((pick.note[:cut], None))
    return lines


def step(pick: Pick, key: str | None, clicked_row: int | None = None) -> tuple[Pick, str | None]:
    """What a key or a click does: a new screen, and `SAVE` or `QUIT` when the caller has work. Pure."""
    if key in ("q", "Q", "\x1b"):
        return pick, QUIT
    if key in ("\r", "\n"):
        return pick, SAVE
    if not pick.rows:
        return pick, None
    at = pick.at if clicked_row is None else clicked_row
    pick = replace(pick, at=at, note="")
    if clicked_row is not None:
        key = " "
    moves = {"up": -1, "down": 1, "pgup": -10, "pgdn": 10, "home": -len(pick.rows), "end": len(pick.rows)}
    if key in moves:
        return replace(pick, at=max(0, min(len(pick.rows) - 1, at + moves[key]))), None
    if key == " ":
        return replace(pick, ticked=pick.ticked ^ {pick.rows[at].key}), None
    if key == "a":
        return replace(pick, ticked={watcher.key for watcher in pick.rows}), None
    if key == "n":
        return replace(pick, ticked=set()), None
    return pick, None


def chosen_of(pick: Pick, was: dict[str, dict]) -> dict[str, dict]:
    """The ticked keys and their records; a ticked key not listed keeps the record it had."""
    listed = {watcher.key: watcher for watcher in pick.rows}
    return {
        key: listed[key].record() if key in listed else was[key]
        for key in [*(w.key for w in pick.rows), *was]
        if key in pick.ticked and (key in listed or key in was)
    }
