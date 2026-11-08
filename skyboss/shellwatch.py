"""Shells a deck tab left running that will never end, or may not. See [[command-deck]] round 19.

**Stuck is certain.** A `while`/`until` loop waiting on `pgrep -f PATTERN` waits for the
pattern to stop matching. When nothing but the loop itself and its children matches, the
process it waited on is gone, and the loop's own command line keeps `pgrep` matching forever.

**Long is a hint.** A shell past `LONG_AFTER` in a tab whose turn is over, with nothing in its
command that bounds it.

The deck reports either in its owner's DECISIONS list and never stops a shell: the tab owns it.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import tempfile
from dataclasses import dataclass
from pathlib import Path

from skyboss import agents as agents_
from skyboss import background, helpers
from skyboss.chrome import ago

STUCK, LONG = "stuck", "long"
#: Seconds a shell runs before an unbounded one in a finished turn is worth a word.
LONG_AFTER = 1800.0
#: Registry words whose turn is over.
IDLE = ("idle", "shell")
LOOP = re.compile(r"(?:^|[;&|\s(])(?:while|until)\s")
#: What bounds a command: a time limit, a count, or a loop over a list.
BOUND = re.compile(r"\btimeout\s|\bseq\s|\bfor\s+\w+\s+in\s|\bfor\s*\(\(")
#: pgrep's options that take a value, so the word after one is not the pattern.
PGREP_VALUED = set("dgGPsuUt") | {"-F", "--pidfile"}


@dataclass
class Shell:
    pid: int
    start: str
    command: str
    seconds: float

    @property
    def key(self) -> str:
        """A shell by PID and start tick, so a reused PID is a new shell."""
        return f"{self.pid}:{self.start}"


def patterns(command: str) -> list[str]:
    """Each pattern `command` hands `pgrep -f`, in order. Empty when it has none or will not split."""
    words = _words(command)
    found: list[str] = []
    for at, word in enumerate(words):
        if word != "pgrep":
            continue
        full, skip = False, False
        for after in words[at + 1 :]:
            if skip:
                skip = False
                continue
            if after.startswith("--"):
                full = full or after == "--full"
                skip = after in PGREP_VALUED
                continue
            if after.startswith("-") and len(after) > 1:
                letters = after[1:]
                full = full or "f" in letters
                skip = letters[-1] in PGREP_VALUED
                continue
            if full:
                found.append(after)
            break
    return found


def _words(command: str) -> list[str]:
    """Shell words, with `;`, `|`, `(` and the like apart, and a `$(…)` in a word opened up.

    Double quotes nested inside a quoted `$(…)` split short; the self-match test in `verdict` holds either way.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return []
    out: list[str] = []
    for word in words:
        out += _words(word.split("$(", 1)[1]) if "$(" in word else [word]
    return out


def command_lines(proc: Path = Path("/proc")) -> dict[int, str]:
    """Every process's command line, words joined by spaces as `pgrep -f` reads them."""
    out: dict[int, str] = {}
    try:
        entries = list(proc.iterdir())
    except OSError:
        return out
    for entry in entries:
        if entry.name.isdigit():
            try:
                raw = (entry / "cmdline").read_bytes()
            except OSError:
                continue
            out[int(entry.name)] = raw.rstrip(b"\0").replace(b"\0", b" ").decode(errors="replace")
    return out


def descendants(pid: int, parent_of: dict[int, int]) -> set[int]:
    """`pid` and every process under it."""
    children: dict[int, list[int]] = {}
    for child, parent in parent_of.items():
        children.setdefault(parent, []).append(child)
    seen, todo = {pid}, [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            if child not in seen:
                seen.add(child)
                todo.append(child)
    return seen


def verdict(shell: Shell, state: str, parent_of: dict[int, int], lines: dict[int, str]) -> tuple[str, str] | None:
    """`(STUCK or LONG, why)` for a shell worth a word, else None. Pure."""
    found = patterns(shell.command) if LOOP.search(shell.command) else []
    if found:
        mine = descendants(shell.pid, parent_of)
        for pattern in found:
            try:
                match = re.compile(pattern)
            except re.error:
                return None
            # The signature: the pattern matches its own loop. A loop it does not match exits when the process goes.
            if not match.search(shell.command):
                return None
            if any(match.search(line) for pid, line in lines.items() if pid not in mine):
                return None
        return STUCK, f"its pgrep -f {found[0]!r} matches nothing but the loop itself, so it can never end"
    if shell.seconds >= LONG_AFTER and state in IDLE and not BOUND.search(shell.command):
        return LONG, "nothing in its command bounds it and the tab's turn is over"
    return None


def notice(shell: Shell, kind: str, why: str) -> str:
    """The DECISIONS notice for one shell."""
    first = (shell.command.strip().splitlines() or [""])[0]
    short = first if len(first) <= 90 else first[:89] + "…"
    age = ago(shell.seconds)
    return f"{kind} shell {shell.pid}, running {age}: `{short}`. {why[0].upper()}{why[1:]}. Ask the tab to stop or bound it."


def running_seconds(pid: int, proc: Path) -> float:
    try:
        start = int(agents_.proc_start(pid, proc) or "")
        uptime = float((proc / "uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0
    return max(0.0, uptime - start / os.sysconf("SC_CLK_TCK"))


def shells_of(pid: int, parent_of: dict[int, int], proc: Path = Path("/proc")) -> list[Shell]:
    """The shells `pid` has running, with their whole command."""
    out: list[Shell] = []
    for child, cmdline in background.shell_lines(pid, parent_of, proc):
        out.append(
            Shell(
                child,
                agents_.proc_start(child, proc) or "",
                background.wrapped(cmdline) or cmdline,
                running_seconds(child, proc),
            )
        )
    return out


def seen_path(session: str) -> Path:
    return helpers.STATE_DIR / "deck" / session / "shells.json"


def read_seen(session: str) -> dict[str, dict]:
    """Shell key → `{agent, text}` for each shell already reported."""
    try:
        raw = json.loads(seen_path(session).read_text())
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}


def write_seen(session: str, seen: dict[str, dict]) -> None:
    path = seen_path(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".shells.", suffix=".json")
    with os.fdopen(handle, "w") as out:
        json.dump(seen, out, indent=1)
    os.replace(temp, path)
