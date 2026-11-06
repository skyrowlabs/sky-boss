"""What a Claude Code session has running beside it: sub-agents and shells. See [[command-deck]].

**A sub-agent is read from its record, never its conversation.** `meta.json` names
its type and task; the transcript beside it is only `stat`ed. No field says one
has finished, and a transcript's last entry does not either (measured on Claude
Code 2.1.318), so a sub-agent is drawn with how long ago it wrote, never as
`running`, and leaves the list once quiet for `RECENT` seconds.

**A shell is a child process in Claude Code's shell wrapper.** Its MCP servers are
children too, so a child counts only if it sourced a shell snapshot.
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

AGENT, SHELL = "agent", "shell"
#: Seconds since a sub-agent last wrote, after which it is not drawn.
RECENT = 600
SNAPSHOT = "shell-snapshots"
#: The operator's command inside the wrapper Claude Code builds around it.
WRAPPED = re.compile(r"eval (?P<word>'(?:[^']|'\"'\"')*')", re.DOTALL)


@dataclass
class Job:
    kind: str
    label: str
    age: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "label": self.label, "age": self.age}


def subagents(cwd: str, ident: str, projects: Path, now: float) -> list[Job]:
    """The session's sub-agents that wrote within `RECENT` seconds, newest first."""
    from skyboss.messages import slug

    found: list[tuple[float, Job]] = []
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
            found.append((wrote, Job(AGENT, label, ago(max(0.0, now - wrote)))))
    return [job for _, job in sorted(found, key=lambda pair: -pair[0])]


def command_of(cmdline: str) -> str:
    """The first line of the command a shell wrapper runs, or `shell` if it cannot be found."""
    match = WRAPPED.search(cmdline)
    if match is None:
        return SHELL
    try:
        words = shlex.split(match.group("word"))
    except ValueError:
        return SHELL
    lines = (words[0] if words else "").strip().splitlines()
    return lines[0] if lines else SHELL


def running_for(pid: int, proc: Path) -> str:
    """How long a process has run, from its start tick and the machine's uptime; empty if unknown."""
    start = agents_.proc_start(pid, proc)
    try:
        uptime = float((proc / "uptime").read_text().split()[0])
        return ago(max(0.0, uptime - int(start or "") / os.sysconf("SC_CLK_TCK")))
    except (OSError, ValueError, IndexError):
        return ""


def shells(pid: int, parent_of: dict[int, int], proc: Path) -> list[Job]:
    """The shells `pid` has running, oldest pid first."""
    out: list[Job] = []
    for child in sorted(p for p, parent in parent_of.items() if parent == pid):
        try:
            cmdline = (proc / str(child) / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if SNAPSHOT in cmdline:
            out.append(Job(SHELL, command_of(cmdline), running_for(child, proc)))
    return out


def counted(jobs: list[Job]) -> str:
    """`2a 1s`: sub-agents and shells, each left out at zero."""
    agents = sum(1 for job in jobs if job.kind == AGENT)
    held = len(jobs) - agents
    return " ".join(part for part in (f"{agents}a" if agents else "", f"{held}s" if held else "") if part)
