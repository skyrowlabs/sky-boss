"""Chrome — what a window knows about its output. See [[chrome]].

**The chrome is a fact set, computed once here, drawn twice.** The view
(cli/view.py) is in-band — how the data itself is drawn. The chrome is
out-of-band: everything the surface knows *about* the output that the output
does not say — the source, the temporal shape, when it ran, the countdown to
the next refresh, the liveness clock, the exit that made a stream go dead.
Both renderers — the terminal's status bands and the canvas window's title bar
and footer — draw what they are told, exactly as they do for a view. The
deciding half lives here, where pytest reaches it; neither renderer grows an
opinion.

**The attention slot is mechanical.** `running` is a process that has not
exited, `dead` is an exit code, `quiet`/`absent`/`rotated` are stat
comparisons reported by the file cursor. Nothing here reads the output or
holds a threshold; conditional states are the Rule branch's to add, and this
one field is where they will land.

**Chrome consumes the envelope; it never feeds it.** Nothing chrome-shaped
enters `data` or the envelope — `--json` output is untouched by this module
existing, byte for byte, and a test holds the line.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

# Every value the attention slot may carry, in this round. All mechanical:
# an exit code, a stat comparison, an envelope fact. The escalation ladder's
# tint and badge will key off this field when the Rule branch arrives.
ATTENTION = ("running", "ok", "partial", "failed", "dead", "quiet", "absent", "rotated")

# One mapping from attention to a theme role, shared by whoever draws the
# chrome into a terminal. The canvas maps the same words onto CSS roles; the
# words are the contract, the colours stay in cli/theme.py.
ROLE = {
    "running": "tb.accent",
    "ok": "tb.ok",
    "partial": "tb.warn",
    "failed": "tb.fail",
    "dead": "tb.fail",
    "quiet": "tb.muted",
    "absent": "tb.warn",
    "rotated": "tb.warn",
}


@dataclass(frozen=True)
class Chrome:
    """The facts one window wears. Only the fields its shape carries are set.

    Times are epoch seconds, taken from whatever clock the caller injects —
    nothing in this module calls time.time() on its own, which is what keeps
    a five-second cadence from costing five seconds of suite.
    """

    source: str
    shape: str  # snapshot | resident | stream | cursor | act
    attention: str = "ok"
    # Envelope facts.
    duration_s: float | None = None
    warnings: int = 0
    # Snapshot and resident.
    ran_at: float | None = None  # when the last run finished
    interval: int = 0
    last_run: float | None = None  # when the last run started
    running_since: float | None = None
    # Stream.
    last_line_at: float | None = None
    exit_code: int | None = None
    exited_at: float | None = None
    # File cursor.
    last_write_at: float | None = None
    size_bytes: int | None = None
    # Bounded ring, stream and cursor.
    ring_shown: int | None = None
    ring_limit: int | None = None

    def to_dict(self) -> dict:
        """The same facts for the canvas renderer, keys omitted when unset —
        the shape of a window's chrome does not carry another shape's nulls."""
        out = {"source": self.source, "shape": self.shape, "attention": self.attention}
        for key in (
            "duration_s", "warnings", "ran_at", "interval", "last_run",
            "running_since", "last_line_at", "exit_code", "exited_at",
            "last_write_at", "size_bytes", "ring_shown", "ring_limit",
        ):
            value = getattr(self, key)
            if value not in (None, 0):
                out[key] = value
        return out


def _verdict(ok: bool, partial: bool) -> str:
    if not ok:
        return "failed"
    return "partial" if partial else "ok"


def snapshot(
    source: str,
    *,
    ok: bool,
    partial: bool = False,
    warnings: int = 0,
    ran_at: float | None = None,
    duration_s: float | None = None,
) -> Chrome:
    """A one-time observe: ran once, stamped once."""
    return Chrome(
        source=source,
        shape="snapshot",
        attention=_verdict(ok, partial),
        warnings=warnings,
        ran_at=ran_at,
        duration_s=duration_s,
    )


def act(
    source: str,
    *,
    ok: bool,
    partial: bool = False,
    warnings: int = 0,
    ran_at: float | None = None,
    duration_s: float | None = None,
) -> Chrome:
    """`run`: the same stamp a snapshot gets, and never a countdown — the
    absence is the act/observe split made visible."""
    chrome = snapshot(
        source, ok=ok, partial=partial, warnings=warnings, ran_at=ran_at, duration_s=duration_s
    )
    return replace(chrome, shape="act")


def resident(
    source: str,
    *,
    ok: bool,
    partial: bool = False,
    warnings: int = 0,
    ran_at: float | None = None,
    duration_s: float | None = None,
    interval: int,
    last_run: float | None = None,
    running_since: float | None = None,
) -> Chrome:
    """A snapshot with a cadence: `--refresh` in the terminal, a pinned window
    on the canvas. While a run is in flight the attention is `running` —
    mechanical, the subprocess has not exited."""
    return Chrome(
        source=source,
        shape="resident",
        attention="running" if running_since is not None else _verdict(ok, partial),
        warnings=warnings,
        ran_at=ran_at,
        duration_s=duration_s,
        interval=interval,
        last_run=last_run,
        running_since=running_since,
    )


def stream(
    source: str,
    *,
    last_line_at: float | None = None,
    exit_code: int | None = None,
    exited_at: float | None = None,
    ring_shown: int | None = None,
    ring_limit: int | None = None,
) -> Chrome:
    """A process follow. Alive is `running`; any exit is `dead` — visibly,
    carrying the code, because restart is the operator's click and never the
    surface's initiative."""
    return Chrome(
        source=source,
        shape="stream",
        attention="dead" if exit_code is not None else "running",
        last_line_at=last_line_at,
        exit_code=exit_code,
        exited_at=exited_at,
        ring_shown=ring_shown,
        ring_limit=ring_limit,
    )


def cursor(
    source: str,
    *,
    state: str = "quiet",
    last_write_at: float | None = None,
    size_bytes: int | None = None,
    ring_shown: int | None = None,
    ring_limit: int | None = None,
) -> Chrome:
    """A file follow. `state` comes from the cursor's own stat loop —
    quiet, absent or rotated — because the loop is the thing that compared
    the inodes. Chrome carries the verdict; it never re-derives it."""
    if state not in ("quiet", "absent", "rotated", "running"):
        raise ValueError(f"not a cursor state: {state!r}")
    return Chrome(
        source=source,
        shape="cursor",
        attention=state,
        last_write_at=last_write_at,
        size_bytes=size_bytes,
        ring_shown=ring_shown,
        ring_limit=ring_limit,
    )


# ============================================================================
# The clocks
# ============================================================================


def ago(seconds: float) -> str:
    """A duration as the shortest honest word: 3s, 4m, 2h, 3d."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def clock(epoch: float) -> str:
    """A moment as local wall-clock time. The date is the terminal's problem —
    a status band answers "when today", not "when in history"."""
    return time.strftime("%H:%M:%S", time.localtime(epoch))


def countdown(chrome: Chrome, now: float) -> int | None:
    """Seconds until the next refresh, or None when there is no cadence.

    The rule is inherited from [[canvas]], not re-decided: a bar or a label
    may show time to the next refresh and nothing else, computed from the
    same `interval` and `last_run` the canvas bar reads today.
    """
    if chrome.interval <= 0 or chrome.last_run is None:
        return None
    return max(0, int(chrome.interval - (now - chrome.last_run)))


# ============================================================================
# The terminal rendering
# ============================================================================

_MIN_FILL = 3


def _band(left: str, right: str, width: int, corners: str) -> str:
    """One box-drawing band: `┌ left ───── right ┐`.

    Exactly `width` characters when width allows; the left side gives way
    first, because the right side is the live half (a countdown, a clock) and
    a clock you cannot see is the silent failure the chrome exists to avoid.
    """
    open_c, close_c = corners
    tail = f" {right} {close_c}" if right else close_c
    room = width - len(open_c) - 1 - 1 - _MIN_FILL - len(tail)
    if len(left) > room:
        left = left[: max(0, room - 1)] + "…"
    fill = max(_MIN_FILL, width - len(open_c) - 1 - len(left) - 1 - len(tail))
    return f"{open_c} {left} {'─' * fill}{tail}"


def _top_facts(chrome: Chrome, now: float) -> tuple[str, str]:
    """The title band: identity on the left, liveness on the right."""
    left = [chrome.source]
    if chrome.shape == "resident" and chrome.interval:
        left.append(f"refresh {chrome.interval}s")
    elif chrome.shape in ("stream", "cursor"):
        left.append("follow")

    right = ""
    if chrome.shape == "resident":
        if chrome.running_since is not None:
            right = f"running {ago(now - chrome.running_since)}"
        else:
            remaining = countdown(chrome, now)
            if remaining is not None:
                right = f"⟳ next in {remaining}s"
    elif chrome.shape == "stream":
        if chrome.attention == "dead":
            right = f"dead · exited {chrome.exit_code}"
            if chrome.exited_at is not None:
                right += f" at {clock(chrome.exited_at)}"
        elif chrome.last_line_at is not None:
            right = f"last line {ago(now - chrome.last_line_at)} ago"
    elif chrome.shape == "cursor":
        if chrome.attention == "absent":
            right = "waiting for it to exist"
        elif chrome.attention == "rotated":
            right = "rotated"
        elif chrome.last_write_at is not None:
            right = f"quiet {ago(now - chrome.last_write_at)} · last write {clock(chrome.last_write_at)}"

    return " · ".join(left), right


def _bottom_facts(chrome: Chrome, now: float) -> tuple[str, str]:
    """The footer band: verdict and cost on the left, bounds on the right."""
    left: list[str] = []
    if chrome.shape in ("snapshot", "resident", "act"):
        left.append(chrome.attention if chrome.running_since is None else "running")
        if chrome.duration_s is not None:
            left.append(f"{chrome.duration_s:.1f}s")
        if chrome.ran_at is not None:
            left.append(f"ran {clock(chrome.ran_at)}")
        if chrome.warnings:
            left.append(f"{chrome.warnings} warning" + ("" if chrome.warnings == 1 else "s"))
    else:
        if chrome.size_bytes is not None:
            # The one byte-formatter the CLI already has — two of these is
            # exactly the drift this module exists to prevent.
            from cli.output import humanize_bytes

            left.append(humanize_bytes(chrome.size_bytes))
        if chrome.ring_shown is not None and chrome.ring_limit is not None:
            left.append(f"showing last {min(chrome.ring_shown, chrome.ring_limit)}")

    return " · ".join(left), ""


def status_lines(chrome: Chrome, now: float, width: int) -> tuple[str, str]:
    """The two terminal bands, as plain strings exactly `width` wide.

    Plain strings on purpose: the facts and their layout are the tested
    contract, and the caller applies the theme role (`ROLE[attention]`)
    to the whole band. No spinners, no percentages — a running subprocess
    has no percentage, and a bar that animates to look busy is decoration
    that reads as information.
    """
    top_left, top_right = _top_facts(chrome, now)
    bottom_left, bottom_right = _bottom_facts(chrome, now)
    return (
        _band(top_left, top_right, width, "┌┐"),
        _band(bottom_left, bottom_right, width, "└┘"),
    )
