"""Watched conditions — a `check` or `info` left standing on the rail.

`tb check drift` answers "is this machine still what its inventory says" once,
when asked. The surface exists because a one-shot command can only report in
the past tense, and that argument applies to every check, not only to lanes.

**A watch may only name a read verb.** That restriction does two jobs, and the
second is the load-bearing one:

- A watch that could invoke `run` would be a scheduler that never touches the
  ledger, which breaks the property the whole taxonomy exists for. Scheduling
  is `tb auto`'s job.
- **It is what makes the concurrency safe.** A watch has to refresh without
  queueing behind the line being typed, which means a second dispatch running
  alongside yours. That is only safe because a read verb cannot take a lane
  lock or mutate state.

Definitions live in `$TB_HOME/watches`, next to jobs and inventory, and are
versioned in the operator's own repo because the git diff is the maintenance
log. Machine divergence is a `hosts:` field, not a separate file location.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from cli.helpers import TB_HOME

WATCHES_DIR = TB_HOME / "watches"

# The read moods. `run` acts and `auto` schedules; neither belongs on a timer
# that nobody is watching the ledger for.
READ_GROUPS = ("check", "info")

DEFAULT_EVERY = 900  # 15 minutes

_EVERY = re.compile(r"^(\d+)\s*([smh])$")
_UNITS = {"s": 1, "m": 60, "h": 3600}


class WatchError(ValueError):
    """A watch definition that cannot be loaded. Always names the file."""


@dataclass(frozen=True)
class Watch:
    name: str
    command: str
    every: int = DEFAULT_EVERY
    hosts: tuple[str, ...] = ()
    source: Path | None = None

    def applies_to(self, host: str) -> bool:
        """No `hosts:` means everywhere. This is how one repo serves several."""
        return not self.hosts or host in self.hosts


def parse_every(value: object, where: str) -> int:
    if value is None:
        return DEFAULT_EVERY
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    match = _EVERY.match(str(value).strip())
    if not match:
        raise WatchError(f"{where}: every must look like 30s, 15m or 1h — got {value!r}")
    return int(match.group(1)) * _UNITS[match.group(2)]


def parse_watch(data: object, source: Path) -> Watch:
    where = source.name

    if not isinstance(data, dict):
        raise WatchError(f"{where}: expected a mapping at the top level")

    command = data.get("command")
    if not isinstance(command, str) or not command.strip():
        raise WatchError(f"{where}: command is required and must be a string")
    command = command.strip()

    words = command.split()
    if words and words[0] == "tb":
        words = words[1:]
    if not words or words[0] not in READ_GROUPS:
        # Named rather than silently dropped: a watch that quietly does nothing
        # is worse than one that refuses to load, because the rail would look
        # like it was reporting.
        raise WatchError(
            f"{where}: a watch may only name {' or '.join(READ_GROUPS)} — got {command!r}. "
            "Anything that acts is a job; see tb auto."
        )

    if "--help" in words:
        # Not pedantry: a watch runs without the process-global stdout redirect
        # that rich-click's own console needs, so a watched --help would print
        # straight through the surface it is drawn on.
        raise WatchError(f"{where}: a watch cannot run --help")

    hosts = data.get("hosts") or []
    if not isinstance(hosts, list) or any(not isinstance(h, str) for h in hosts):
        raise WatchError(f"{where}: hosts must be a list of hostnames")

    return Watch(
        name=source.stem,
        command=" ".join(words),
        every=parse_every(data.get("every"), where),
        hosts=tuple(hosts),
        source=source,
    )


def signature(directory: Path | None = None) -> tuple:
    """A cheap value that changes whenever any watch definition does.

    The surface re-reads definitions while it is open, so an edit shows up
    without a restart. Parsing every file on every tick to discover that nothing
    changed is the wrong trade for a directory edited twice a week, so the parse
    is guarded by this instead: a readdir and a stat per file, against a handful
    of files.

    A directory mtime alone is not enough. It moves when a file is added,
    removed or renamed, and **not** when an existing file's contents change —
    which is the common case, and the one that would silently keep showing the
    old definition. So each file's size and mtime are in here too.

    An absent directory is the empty signature, never an error: the surface asks
    for watches on its first tick, before any exist.
    """
    directory = directory or WATCHES_DIR
    try:
        return tuple(
            (path.name, stat.st_mtime_ns, stat.st_size)
            for path in sorted(directory.glob("*.yaml"))
            if not path.name.startswith("_")
            for stat in (path.stat(),)
        )
    except OSError:
        return ()


def load_watches(directory: Path | None = None) -> tuple[dict[str, Watch], list[str]]:
    """Every watch definition, plus one message per file that failed to load.

    A malformed file does not hide the others, for the same reason `load_jobs`
    does not: one bad definition must not blank the whole rail.
    """
    directory = directory or WATCHES_DIR
    watches: dict[str, Watch] = {}
    problems: list[str] = []

    if not directory.exists():
        return watches, problems

    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            watches[path.stem] = parse_watch(yaml.safe_load(path.read_text()), path)
        except WatchError as exc:
            problems.append(str(exc))
        except yaml.YAMLError as exc:
            problems.append(f"{path.name}: not valid YAML ({exc.__class__.__name__})")

    return watches, problems
