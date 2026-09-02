"""`sb agents` — who is running right now. See [[agent-sessions]].

**The tower's subject, arriving early and from outside.** The `IN FLIGHT` band
was drawn for jobs sky.boss started; the jobs the operator actually wants to
watch are the ones it did not — several Claude Code sessions side by side across
sibling repos, each holding a working tree. `ps` finds the processes and can
tell you nothing about them: not which repo, not whether the session is working
or waiting, not when it started, not what it is called.

**Same fold as [[roll-call]], a different population.** roll-call asks every
declared project how it is; this asks every provider who is running. It is a
command the surfaces render, never a panel with a reader inside it.

**The record is thin, and nothing else.** `provider · id · name · cwd · status ·
started · pid`. A provider that knows more — context used, model, token spend,
the branch a session sits on — has it dropped rather than half-rendered. The
alternative was a per-provider extras bag, which is useful and is also how a
common vocabulary rots: the first consumer that reads `extras.context` has made
it part of the contract without anyone deciding to. The tower must draw a row
from an adapter it has never heard of without special-casing it, and that is
only true if there is nothing provider-shaped in a row to special-case.

**An adapter that finds nothing is silent.** Nobody has five agent CLIs
installed at once, so *not present* is the common case and prints nothing —
the rule an absent `$SB_HOME` already lives under. The **command** still states
the arithmetic when it has no rows, because otherwise *looked and saw nobody*
and *could not look* are the same empty table.

**It reads. It never touches.** `messagingSocketPath` is a live socket into
another agent's session, and a stop button would put a write into a command
built as an observe. Transcripts are out for a stronger reason: an agent's
transcript is the operator's conversation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import rich_click as click

from cli.chrome import ago
from cli.output import Result, emit
from cli.view import describe


@dataclass(frozen=True)
class Session:
    """One live agent session, in the one vocabulary every adapter answers in.

    Thin by ruling, not by omission. `status` carries a provider's own word —
    Claude says `busy` / `idle` — so the vocabulary is already one provider's
    shape in this one field. That is a debt and it is stated: the fix when a
    second adapter disagrees is to widen the *enum*, which is a decision, rather
    than to widen the *record*, which is a hole.
    """

    provider: str
    id: str
    name: str = ""
    cwd: str = ""
    status: str = ""
    started: datetime | None = None
    pid: int = 0


@dataclass
class Scan:
    """What one adapter saw, including how hard it looked.

    **`present` and `read` are the counting half.** A detector that reports only
    what it caught answers `0` for *looked and found nobody* and `0` for *never
    looked*, and those want opposite conclusions. An adapter says whether its
    registry was there at all and how many records it got through, so an empty
    table can say which kind of empty it is.
    """

    provider: str
    sessions: list[Session] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    present: bool = False
    read: int = 0
    # Records whose liveness could not be decided — no `/proc` to ask, or a
    # record that pinned no start time. Counted apart from `read` because
    # "cannot tell" is not "not running", and a row is still drawn for each.
    unverified: int = 0


class Adapter(Protocol):
    """One question: *what agent sessions are live*.

    A second provider is a day of reading and a new module, not a refactor —
    which is the whole reason the seam is decided now, with exactly one adapter
    written against a format that was actually opened.
    """

    provider: str

    def scan(self) -> Scan: ...


# ============================================================================
# Liveness
# ============================================================================


def proc_start(pid: int, proc: Path = Path("/proc")) -> str | None:
    """Field 22 of `/proc/<pid>/stat` — when this PID's process began.

    **The comm field is why this is not a `split()`.** Field 2 is the executable
    name in parentheses and may itself contain spaces and parentheses, so the
    only safe read is everything after the *last* `)`, where field 3 is index 0
    and field 22 is therefore index 19.

    Returns `None` for *cannot tell*, which is a third answer and not a false:
    no such process is a `FileNotFoundError` and returns `None` too, so callers
    read it against the record rather than treating it as a verdict.
    """
    try:
        stat = (proc / str(pid) / "stat").read_text()
    except (OSError, ValueError):
        return None
    end = stat.rfind(")")
    if end < 0:
        return None
    fields = stat[end + 2 :].split()
    return fields[19] if len(fields) > 19 else None


def alive(pid: int, started: str, proc: Path = Path("/proc")) -> bool | None:
    """Whether this record's process is still the one running under that PID.

    **Liveness is two fields, not one.** A record outlives the process that
    wrote it, so a PID alone lies twice — once for a crashed session whose file
    is still on disk, once for a PID the kernel has recycled onto something
    else. The record pins its own start tick for exactly this.

    Three answers, and the third is the point: `True` live, `False` gone or
    recycled, `None` *could not tell* — no `/proc` on this platform, or a record
    that pinned no start tick. A reader that collapsed `None` into `False` would
    report a machine it cannot inspect as a machine with nothing running.
    """
    if pid <= 0:
        return None
    if not proc.is_dir():
        return None
    mine = proc_start(pid, proc)
    if mine is None:
        # The directory exists and this PID is not in it: the process is gone.
        return False
    if not started:
        return None
    try:
        return int(mine) == int(started)
    except ValueError:
        return None


# ============================================================================
# The Claude adapter
# ============================================================================

CLAUDE_SESSIONS = Path(".claude") / "sessions"


@dataclass
class Claude:
    """`~/.claude/sessions/<pid>.json`, one file per session, written by the
    session itself.

    **An internal format with no contract.** Undocumented, versioned per record,
    free to change under a client update — and it already has: `.key` files
    appeared beside the JSON, and five fields arrived, inside three days of the
    spec being written. So the glob is narrow, every field is optional, and an
    absent, renamed or unparseable registry degrades to *nothing declared*. It
    never raises, and it never reports an empty success that reads as
    *nothing is running*, which is the same lie facing the other way.
    """

    provider: str = "claude"
    directory: Path | None = None
    proc: Path = Path("/proc")

    def where(self) -> Path:
        # Resolved at call time, never at import: a constant here is a path a
        # test cannot redirect. Same rule [[state-root]] settled.
        return self.directory or (Path.home() / CLAUDE_SESSIONS)

    def scan(self) -> Scan:
        out = Scan(provider=self.provider)
        directory = self.where()
        try:
            files = sorted(directory.glob("*.json"))
        except OSError:
            # An unreadable registry is *not present* as far as anyone can tell
            # from here, and saying so per invocation is the noise an absent
            # home already declines to make.
            return out
        if not directory.is_dir():
            return out
        out.present = True

        for path in files:
            out.read += 1
            try:
                record = json.loads(path.read_text())
            except (OSError, ValueError) as exc:
                out.problems.append(f"{self.provider}: {path.name} unreadable — {exc}")
                continue
            if not isinstance(record, dict):
                out.problems.append(f"{self.provider}: {path.name} is not a record")
                continue

            ident = str(record.get("sessionId") or "")
            pid = _int(record.get("pid"))
            if not ident or not pid:
                # Without these two a row cannot be identified or checked, so it
                # is skipped and named rather than drawn as a session nobody can
                # find.
                out.problems.append(f"{self.provider}: {path.name} names no session or pid")
                continue

            live = alive(pid, str(record.get("procStart") or ""), self.proc)
            if live is False:
                # A stale file from a session that has ended is the normal
                # aftermath, not a problem. Counted in `read`, drawn nowhere.
                continue
            if live is None:
                out.unverified += 1

            out.sessions.append(
                Session(
                    provider=self.provider,
                    id=ident,
                    name=str(record.get("name") or ""),
                    cwd=str(record.get("cwd") or ""),
                    # **A null status is a thin record, not a broken one.** One
                    # of four live records carries `null` here today, from the
                    # `sdk-cli` entrypoint. It draws as absent and raises no
                    # warning: an empty cell beside `busy` and `idle` already
                    # reads as *unknown*, and a line per invocation about a
                    # field the provider chose not to set is noise.
                    status=str(record.get("status") or ""),
                    started=epoch_ms(record.get("startedAt")),
                    pid=pid,
                )
            )
        return out


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def epoch_ms(value) -> datetime | None:
    """`startedAt` as an instant. Milliseconds since the epoch, UTC.

    **This is not the normalisation [[schedule]] refuses**, and the difference
    is worth stating because the rule looks like it should bite. There, a
    provider writes `2026-08-30T05:15:00-05:00` and the offset is part of what
    it said, so rewriting it to UTC would erase a disagreement between projects
    that ought to be visible. An epoch has no zone to erase: `1788229475837`
    means one instant and only one, and rendering it as UTC states that instant
    rather than choosing between readings of it.
    """
    ms = _int(value)
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def providers() -> list[Adapter]:
    """Every adapter this build ships.

    A list rather than a registry, and a function rather than a constant: it is
    what a test replaces, and it is where round 2 will put the question of
    *which* are enabled if that turns out to be operator content.
    """
    return [Claude()]


# ============================================================================
# The fold
# ============================================================================


def fold(adapters: list[Adapter]) -> tuple[list[Session], list[str], Scan]:
    """Every adapter's answer, in one order, with one tally.

    Pure with respect to the filesystem — it asks the adapters it is handed and
    nothing else, which is what makes the ordering and the tally testable with
    no registry on disk.
    """
    sessions: list[Session] = []
    problems: list[str] = []
    tally = Scan(provider="")
    for adapter in adapters:
        scan = adapter.scan()
        sessions.extend(scan.sessions)
        problems.extend(scan.problems)
        tally.present = tally.present or scan.present
        tally.read += scan.read
        tally.unverified += scan.unverified
    return order(sessions), problems, tally


def order(sessions: list[Session]) -> list[Session]:
    """Oldest first, so the session that has been going longest is at the top —
    which is the one whose context is nearest the bottom.

    A session with no start time sorts after every one that has one, for
    [[schedule]]'s reason: among rows ordered by time, a row with no time has
    nowhere honest to sit, and putting it first makes the least certain thing
    look the most imminent."""
    dated = sorted((s for s in sessions if s.started), key=lambda s: s.started)
    undated = [s for s in sessions if not s.started]
    return dated + undated


# What the table draws, in order, and what it keeps but does not draw. Hidden
# rather than dropped: a machine reading the envelope still gets the identity
# and the pid. A view describes; it never filters.
INLINE = ("provider", "name", "status", "up", "cwd")
HIDDEN = ("id", "pid", "started")


def rows_of(sessions: list[Session], now: datetime) -> list[dict]:
    """The envelope's rows. `up` is arithmetic on two instants, which is the
    thing [[schedule]] round 1 licensed — sky.boss may order and may subtract;
    only a provider may judge."""
    return [
        {
            "provider": s.provider,
            "name": s.name,
            "status": s.status,
            "up": ago((now - s.started).total_seconds()) if s.started else "",
            "cwd": s.cwd,
            "id": s.id,
            "pid": s.pid,
            "started": s.started.isoformat() if s.started else "",
        }
        for s in sessions
    ]


def view_of(rows: list[dict]) -> dict:
    """Authored, not inferred — these five keys are sky.boss's own vocabulary,
    so there is nothing to infer, only an order to state and three columns to
    keep out of the way. Widths still come from `cli/view.py`, or flex grows a
    second opinion. See [[table-views]] and [[schedule]] round 3."""
    return {
        "columns": [describe(key, rows) for key in INLINE],
        "details": [],
        "hidden": list(HIDDEN),
        "authored": True,
    }


def empty_reason(tally: Scan, consulted: int) -> str:
    """Why there are no rows — the sentence that keeps an empty table honest.

    Three endings, and they are three different facts. No registry anywhere is
    *nothing to look at*; records read and none surviving is *looked, and they
    have all ended*; neither is *this machine has no agents running*, which is
    what a bare empty table would have implied for all three.
    """
    providers = f"{consulted} provider{'s' if consulted != 1 else ''} consulted"
    if not tally.present:
        return f"no sessions — {providers}, no registry present"
    if tally.read:
        return f"no sessions — {providers}, {tally.read} record(s) read, none live"
    return f"no sessions — {providers}, registry present and empty"


@click.command(name="agents")
@click.option("--only", metavar="NAMES", help="Ask only these providers, comma-separated.")
@emit
def agents(only: str | None) -> Result:
    """Which agent sessions are running right now, across every provider.

        sb agents
        sb agents --only claude

    An observe — a window may pin it and refresh it on a cadence. It reads what
    each session published about itself and never starts, stops, or messages
    one.
    """
    result = Result()
    adapters = providers()

    wanted = {n.strip() for n in only.split(",")} if only else None
    if wanted:
        missing = wanted - {a.provider for a in adapters}
        if missing:
            raise click.UsageError(f"no such provider: {', '.join(sorted(missing))}")
        adapters = [a for a in adapters if a.provider in wanted]

    sessions, problems, tally = fold(adapters)
    for problem in problems:
        result.warn(problem)

    if tally.unverified:
        # Counted out loud, because a row sky.boss could not verify looks
        # exactly like one it did. This is the same distinction `present` and
        # `read` exist for, one row down.
        result.warn(
            f"{tally.unverified} session(s) drawn unverified — "
            "no /proc to confirm the process is still the one that wrote the record"
        )

    now = datetime.now(timezone.utc)
    result.data = rows_of(sessions, now)
    if not result.data:
        result.warn(empty_reason(tally, len(adapters)))
        return result
    result.view = view_of(result.data)
    return result
