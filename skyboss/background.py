"""What a Claude Code session has running beside it: sub-agents, shells and spawned sessions. See [[command-deck]].

**A sub-agent is read from its record, never its conversation.** `meta.json` names
its type and task; the transcript beside it is only `stat`ed. No field says one
has finished, and a transcript's last entry does not either (measured on Claude
Code 2.1.318), so a sub-agent is drawn with how long ago it wrote, never as
`running`, and leaves the list once quiet for `RECENT` seconds.

**A shell is a child process in Claude Code's shell wrapper.** Its MCP servers are
children too, so a child counts only if it sourced a shell snapshot. Its fd 1 tells
the two kinds apart: a `tasks/<id>.output` file is a Bash shell's, with a stream to
follow, and a socket is a Monitor's, whose lines reach only its session.

**A spawned session is a full session a tab started.** Its registry record goes when it
exits, so one that ended is read from its transcript's `stat`, for `RECENT` seconds.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from skyboss import agents as agents_
from skyboss.chrome import ago

AGENT, SHELL, SESSION, MONITOR = "agent", "shell", "session", "monitor"
#: A session id. Claude Code keeps a session's scratch folder under one, so a path can name its owner.
IDENT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
#: Seconds since a sub-agent last wrote, after which it is not drawn.
RECENT = 600
SNAPSHOT = "shell-snapshots"
#: Each kind and the letter `counted` gives it.
KINDS = ((AGENT, "a"), (SESSION, "c"), (SHELL, "s"), (MONITOR, "m"))
#: A background Bash's output file, which names its task.
TASK_FILE = re.compile(r"/tasks/(?P<task>[^/]+)\.output$")
#: The operator's command inside the wrapper Claude Code builds around it.
WRAPPED = re.compile(r"eval (?P<word>'(?:[^']|'\"'\"')*')", re.DOTALL)


@dataclass
class Job:
    kind: str
    label: str
    age: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "label": self.label, "age": self.age}


def subagent_records(cwd: str, ident: str, projects: Path, now: float) -> list[tuple[str, float, str]]:
    """`(agent id, last write, label)` for each sub-agent that wrote within `RECENT` seconds, newest first."""
    from skyboss.messages import slug

    found: list[tuple[str, float, str]] = []
    for meta in (projects / slug(cwd) / ident / "subagents").glob("*.meta.json"):
        try:
            wrote = meta.with_name(meta.name.replace(".meta.json", ".jsonl")).stat().st_mtime
            if now - wrote > RECENT:
                continue
            record = json.loads(meta.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(record, dict):
            kind = str(record.get("agentType") or AGENT)
            label = f"{kind}: {record.get('description') or 'no description'}"
            found.append((meta.name.removesuffix(".meta.json"), wrote, label))
    return sorted(found, key=lambda each: -each[1])


def subagents(cwd: str, ident: str, projects: Path, now: float) -> list[Job]:
    """The session's sub-agents that wrote within `RECENT` seconds, newest first."""
    return [
        Job(AGENT, label, ago(max(0.0, now - wrote))) for _, wrote, label in subagent_records(cwd, ident, projects, now)
    ]


def wrapped(cmdline: str) -> str:
    """The whole command a shell wrapper runs, empty if it cannot be found."""
    match = WRAPPED.search(cmdline)
    if match is None:
        return ""
    try:
        words = shlex.split(match.group("word"))
    except ValueError:
        return ""
    return words[0] if words else ""


def command_of(cmdline: str) -> str:
    """The first line of the command a shell wrapper runs, or `shell` if it cannot be found."""
    lines = wrapped(cmdline).strip().splitlines()
    return lines[0] if lines else SHELL


def running_for(pid: int, proc: Path) -> str:
    """How long a process has run, from its start tick and the machine's uptime; empty if unknown."""
    start = agents_.proc_start(pid, proc)
    try:
        uptime = float((proc / "uptime").read_text().split()[0])
        return ago(max(0.0, uptime - int(start or "") / os.sysconf("SC_CLK_TCK")))
    except (OSError, ValueError, IndexError):
        return ""


def shell_lines(pid: int, parent_of: dict[int, int], proc: Path) -> list[tuple[int, str]]:
    """Each shell `pid` has running, as `(pid, command line)`, oldest pid first."""
    out: list[tuple[int, str]] = []
    for child in sorted(p for p, parent in parent_of.items() if parent == pid):
        try:
            cmdline = (proc / str(child) / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if SNAPSHOT in cmdline:
            out.append((child, cmdline))
    return out


def output_of(pid: int, proc: Path) -> tuple[str, str]:
    """`(kind, path)` from a shell's fd 1: a task file is `SHELL` with its path, a socket `MONITOR`.

    Anything else, or an fd that cannot be read, is a `SHELL` with no file to follow.
    """
    try:
        target = os.readlink(proc / str(pid) / "fd" / "1")
    except OSError:
        return SHELL, ""
    if target.startswith("socket:"):
        return MONITOR, ""
    return SHELL, target if TASK_FILE.search(target) else ""


def shells(pid: int, parent_of: dict[int, int], proc: Path) -> list[Job]:
    """The shells and Monitors `pid` has running, oldest pid first."""
    return [
        Job(output_of(child, proc)[0], command_of(line), running_for(child, proc))
        for child, line in shell_lines(pid, parent_of, proc)
    ]


def ended(owners: set[str], live: set[str], projects: Path, now: float) -> dict[str, list[Job]]:
    """Owner id → sessions run from its scratch folder that wrote within `RECENT` seconds and have gone."""
    found: dict[str, list[Job]] = {}
    try:
        folders = list(projects.iterdir())
    except OSError:
        return found
    for folder in folders:
        owner = next((ident for ident in IDENT.findall(folder.name) if ident in owners), "")
        if not owner:
            continue
        where = folder.name.split(owner, 1)[1].strip("-")
        for transcript in folder.glob("*.jsonl"):
            try:
                quiet = now - transcript.stat().st_mtime
            except OSError:
                continue
            if quiet <= RECENT and transcript.stem not in live:
                found.setdefault(owner, []).append(Job(SESSION, f"{where} · ended", ago(max(0.0, quiet))))
    return found


def counted(jobs: list[Job]) -> str:
    """`2a 1c 1s 1m`: sub-agents, spawned sessions, shells and Monitors, each left out at zero."""
    tally = [(sum(1 for job in jobs if job.kind == kind), letter) for kind, letter in KINDS]
    return " ".join(f"{count}{letter}" for count, letter in tally if count)
