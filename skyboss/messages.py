"""`sb deck messages` — what agent sessions sent each other. See [[command-deck]].

**Read from the receiver's transcript, on the operator's ruling.** Claude Code
keeps no message ledger, but each live session's transcript records every
message it *received* as a `user` entry whose `origin.kind` is `peer`. So this
reads exactly those entries and nothing else: never a human turn, never a tool
call. `sb agents` stays out of transcripts; this command is the one exception,
and the deck pane is where it is drawn. Bodies reach the terminal and are written
nowhere.

**A transcript that cannot be read is counted**, because an empty table must
not read the same as *nobody sent anything*.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from skyboss import agents as agents_
from skyboss import theme
from skyboss.chrome import ago
from skyboss.output import Result
from skyboss.view import describe

#: The registry record's provider whose transcripts this reads.
PROVIDER = "claude"
PEER = "peer"
LIMIT = 50
PROJECTS = Path(".claude") / "projects"

INLINE = ("when", "between", "message")
HIDDEN = ("at", "from", "to", "from_agent", "to_agent", "between_parts", "msg_id", "session")


def projects_dir() -> Path:
    """Resolved at call time, so a test can redirect it."""
    return Path.home() / PROJECTS


def slug(cwd: str) -> str:
    """The projects directory Claude Code names for `cwd`: every non-alphanumeric is `-`.

    Checked on Claude Code 2.1.318 against every live session's directory.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def transcript(session: agents_.Session, projects: Path) -> Path:
    return projects / slug(session.cwd) / f"{session.id}.jsonl"


@dataclass(frozen=True)
class Message:
    at: datetime | None
    sender: str
    receiver: str
    body: str
    msg_id: str
    session: str
    key: str


def _instant(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    # A naive stamp has no instant; the transcript has always written `Z`.
    return parsed if parsed.tzinfo else None


def received(path: Path, session: agents_.Session) -> tuple[list[Message], int]:
    """The peer messages in one transcript, and how many such lines would not parse.

    Raises `OSError` when the file cannot be opened; the caller counts that.
    """
    out: list[Message] = []
    torn = 0
    receiver = session.name or session.id[:8]
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            # Cheap prefilter: transcripts run to megabytes and almost no line is a peer message.
            if '"peer"' not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                torn += 1
                continue
            origin = entry.get("origin") if isinstance(entry, dict) else None
            if entry.get("type") != "user" or not isinstance(origin, dict) or origin.get("kind") != PEER:
                continue
            msg_id = str(origin.get("msg_id") or "")
            # A subagent's handback carries no msg_id; its entry uuid is the next-best identity.
            key = msg_id or f"{session.id}:{entry.get('uuid') or len(out)}"
            out.append(
                Message(
                    at=_instant(entry.get("timestamp")),
                    sender=str(origin.get("name") or "?"),
                    receiver=receiver,
                    body=str(origin.get("body") or ""),
                    msg_id=msg_id,
                    session=session.id,
                    key=key,
                )
            )
    return out, torn


def collect(sessions: list[agents_.Session], projects: Path) -> tuple[list[Message], list[str]]:
    """Every live session's received messages: deduplicated, oldest first, the last `LIMIT`."""
    found: list[Message] = []
    problems: list[str] = []
    missing: list[str] = []
    unreadable: list[str] = []
    torn = 0
    for session in sessions:
        path = transcript(session, projects)
        try:
            messages, bad = received(path, session)
        except FileNotFoundError:
            missing.append(session.name or session.id[:8])
            continue
        except OSError:
            unreadable.append(session.name or session.id[:8])
            continue
        found.extend(messages)
        torn += bad
    if missing:
        problems.append(f"{len(missing)} session(s) have no transcript where expected: {', '.join(missing)}")
    if unreadable:
        problems.append(f"{len(unreadable)} transcript(s) could not be read: {', '.join(unreadable)}")
    if torn:
        problems.append(f"{torn} peer line(s) did not parse — skipped")

    unique: dict[str, Message] = {}
    for message in found:
        held = unique.get(message.key)
        if held is None or _sort_key(message) < _sort_key(held):
            unique[message.key] = message
    ordered = sorted(unique.values(), key=_sort_key)
    return ordered[-LIMIT:], problems


def _sort_key(message: Message) -> tuple:
    # An undated message sorts first, so it can never displace the newest at the bottom.
    stamp = message.at.timestamp() if message.at else float("-inf")
    return (stamp, message.key)


def first_line(body: str) -> str:
    lines = body.strip().splitlines()
    return lines[0].strip() if lines else ""


def rows_of(messages: list[Message], now: datetime, agents: dict[str, tuple[str, int]] | None = None) -> list[dict]:
    """One row per message. `agents` maps a session name to the deck agent it runs as, and its tab slot."""
    agents = agents or {}

    def part(name: str) -> list:
        # An agent's name in its own colour; anyone outside the deck in the plain text colour.
        placed = agents.get(name)
        return [name, theme.agent_role(placed[1]) if placed else None]

    return [
        {
            "when": ago((now - m.at).total_seconds()) if m.at else "",
            "between": f"{m.sender} → {m.receiver}",
            "message": first_line(m.body),
            "at": m.at.isoformat() if m.at else "",
            "from": m.sender,
            "to": m.receiver,
            "from_agent": agents.get(m.sender, ("", 0))[0],
            "to_agent": agents.get(m.receiver, ("", 0))[0],
            "between_parts": [part(m.sender), [" → ", "sb.muted"], part(m.receiver)],
            "msg_id": m.msg_id,
            "session": m.session,
        }
        for m in messages
    ]


def view_of(rows: list[dict]) -> dict:
    columns = [describe(key, rows) for key in INLINE]
    for column in columns:
        if column["key"] == "between":
            column["segments"] = "between_parts"
    return {
        "columns": columns,
        "details": [],
        "hidden": list(HIDDEN),
        "authored": True,
    }


def messages_result(
    adapters: list | None = None,
    projects: Path | None = None,
    now: datetime | None = None,
    place: Callable[[list], dict[str, tuple[str, int]]] | None = None,
) -> Result:
    """The envelope. Every way it could not look is a warning, so empty is never ambiguous."""
    result = Result()
    chosen = adapters if adapters is not None else agents_.providers()
    sessions, problems, tally = agents_.fold(chosen)
    for problem in problems:
        result.warn(problem)
    sessions = [s for s in sessions if s.provider == PROVIDER]

    messages, more = collect(sessions, projects or projects_dir())
    for problem in more:
        result.warn(problem)
    # By name, because a sender is named in the message and not by session id.
    placed = place(sessions) if place is not None else {}
    agents = {s.name: placed[s.id] for s in sessions if s.id in placed and s.name}
    result.data = rows_of(messages, now or datetime.now(timezone.utc), agents)
    if not result.data:
        if sessions:
            result.warn(f"no messages — {len(sessions)} live session(s) read, none received one")
        else:
            result.warn(agents_.empty_reason(tally, len(chosen)))
        return result
    result.view = view_of(result.data)
    return result
