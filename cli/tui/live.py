"""What is happening right now — the thing a one-shot command cannot show.

`tb auto status` reads the ledger, which is a record of runs that have already
finished: `run_job` appends its entry after the process exits. A lane held at
this instant, and by what, is invisible to it. That is the gap this closes, and
it is the reason the surface exists at all.

Both reads here are cheap enough for a one-second tick — `/proc/locks` is a few
lines, and the ledger is read from its tail rather than parsed whole.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from cli.jobs import LANES, LEDGER, lane_lock_path

PROC_LOCKS = Path("/proc/locks")

# The device:inode column, e.g. "00:37:3739396" — device halves in hex, inode
# decimal. Matched by shape rather than by column index because a waiter line is
# prefixed with "->", which shifts every field along by one.
_DEVICE_INODE = re.compile(r"^[0-9a-f]+:[0-9a-f]+:(\d+)$")

# How much of a holder's argv to show. Deliberately short: an ad-hoc run is
# `tb run --lane L -- <anything>`, and "anything" is exactly where a token or a
# password would appear. Enough to recognise the job, not enough to leak one.
HOLDER_WORDS = 3

# The strip is one line tall. A holder label carrying a newline — `python -c`
# with an inline script does exactly that — would break the layout outright.
HOLDER_CHARS = 44

# Bytes of ledger to read from the end. Comfortably more than one entry, and
# bounded so the tick cost does not grow with the file.
TAIL_BYTES = 8192


@dataclass(frozen=True)
class Lane:
    name: str
    holder: str | None = None

    @property
    def busy(self) -> bool:
        return self.holder is not None


def _locks_by_inode(text: str) -> dict[int, int]:
    """Inode -> holding pid, for every advisory lock the kernel is tracking."""
    found: dict[int, int] = {}
    for line in text.splitlines():
        fields = line.split()
        for index, field in enumerate(fields):
            if index == 0:
                continue
            match = _DEVICE_INODE.match(field)
            if not match:
                continue
            # The pid is the column immediately before device:inode, wherever
            # the "->" prefix on a waiter line has pushed the pair to.
            pid = fields[index - 1]
            if pid.isdigit():
                found.setdefault(int(match.group(1)), int(pid))
            break
    return found


def _describe(pid: int) -> str:
    """A short, safe label for the process holding a lane."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        # Exited between reading /proc/locks and here, or not ours to look at.
        return f"pid {pid}"

    words = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
    if not words:
        return f"pid {pid}"

    # tb runs as `python -m cli run <job>`, so the interpreter and the module
    # are three tokens of pure noise in front of the only part worth reading.
    if Path(words[0]).name.startswith("python"):
        words = words[1:]
        if words[:1] == ["-m"]:
            words = words[2:]
    elif words:
        words[0] = Path(words[0]).name

    # split()/join() collapses any newline or tab in an inline script down to
    # single spaces before it can reach a one-line widget.
    label = " ".join(" ".join(words[:HOLDER_WORDS]).split())
    if len(label) > HOLDER_CHARS:
        label = label[: HOLDER_CHARS - 1] + "\u2026"
    return label or f"pid {pid}"


def lanes() -> tuple[Lane, ...]:
    """Every lane, and what holds it.

    Held is decided by ``/proc/locks``, never by whether the lock file exists —
    the file outlives the lock, so existence would report every lane busy
    forever after the first job ever ran.

    Nor by trying to take the lock: `lane_lock` is non-blocking, so a probe on a
    one-second tick would hold the lane for an instant and a `tb run` starting
    in that window would record `skipped`. A monitor must not be able to cause
    the condition it monitors. Reading /proc cannot.
    """
    holders = _locks_by_inode(_read(PROC_LOCKS))
    found = []
    for name in LANES:
        try:
            inode = lane_lock_path(name).stat().st_ino
        except OSError:
            found.append(Lane(name))
            continue
        pid = holders.get(inode)
        found.append(Lane(name, _describe(pid) if pid is not None else None))
    return tuple(found)


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def recent_runs(limit: int = 3, ledger: Path | None = None) -> list[dict]:
    """The most recent ledger entries, newest first, read from the tail.

    Parsing the whole ledger on every tick would make the surface slower the
    longer the machine has been in use, which is precisely backwards.
    """
    path = LEDGER if ledger is None else ledger
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - TAIL_BYTES))
            chunk = handle.read()
    except OSError:
        return []

    found: list[dict] = []
    for line in reversed(chunk.decode("utf-8", "replace").splitlines()):
        if len(found) >= limit:
            break
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            # A torn first line from seeking mid-file, or a corrupt entry.
            continue
        if isinstance(entry, dict):
            found.append(entry)
    return found


def last_run(ledger: Path | None = None) -> dict | None:
    entries = recent_runs(1, ledger)
    return entries[0] if entries else None


# Outcomes that never really ran, so their near-zero durations would drag an
# estimate down to nothing.
DID_NOT_RUN = {"skipped", "refused"}


def expected_seconds(line: str, entries: list[dict] | None = None) -> float | None:
    """How long this line has historically taken, if that is knowable.

    Only `tb run <job>` is, and only once the ledger has seen it. Everything
    else returns None, and the surface shows a spinner rather than inventing a
    denominator to be proportional to.
    """
    words = line.split()
    if words[:1] == ["tb"]:
        words = words[1:]
    if len(words) < 2 or words[0] != "run":
        return None

    if entries is None:
        from cli.jobs import read_ledger

        entries = read_ledger()

    durations = sorted(
        entry["duration_s"]
        for entry in entries
        if entry.get("job") == words[1]
        and entry.get("outcome") not in DID_NOT_RUN
        and isinstance(entry.get("duration_s"), (int, float))
    )
    if not durations:
        return None
    # Median, not mean: one pathological run should not move the estimate.
    return float(durations[len(durations) // 2])


def summarize(entry: dict) -> tuple[str, bool]:
    """A ledger entry as a strip-sized label, and whether it went well."""
    from datetime import datetime

    from cli.jobs import humanize_age

    job = entry.get("job", "?")
    outcome = entry.get("outcome", "?")
    age = ""
    try:
        age = f" {humanize_age(datetime.fromisoformat(entry['started']))}"
    except (KeyError, TypeError, ValueError):
        pass
    return f"{job} {outcome}{age}", outcome == "ok"


def ledger_size(ledger: Path | None = None) -> int:
    """How many runs have ever been recorded.

    Counted rather than kept, because the ledger is append-only and a cached
    count is a second source of truth for a number nobody needs to be fast.
    """
    ledger = ledger or LEDGER
    if not ledger.exists():
        return 0
    try:
        with ledger.open("rb") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0
