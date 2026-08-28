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
ATTENTION = (
    "running", "ok", "partial", "failed", "dead", "quiet", "absent", "rotated", "late",
    "pending",
)

# One mapping from attention to a theme role, shared by whoever draws the
# chrome into a terminal. The canvas maps the same words onto CSS roles; the
# words are the contract, the colours stay in cli/theme.py.
ROLE = {
    "running": "sb.accent",
    "ok": "sb.ok",
    "partial": "sb.warn",
    "failed": "sb.fail",
    "dead": "sb.fail",
    "quiet": "sb.muted",
    "absent": "sb.warn",
    "rotated": "sb.warn",
    # Warn, not fail. A late log is a fact about a clock, not a verdict about a
    # job — sky.boss does not know whether the job died or the machine was asleep, and
    # colouring it as a failure would be the judgment [[file-follow]] round 2
    # refuses to make.
    "late": "sb.warn",
    # Accent, like `running`. A pending write has not gone wrong and has not
    # gone right; it is the one state where the interesting thing is that you
    # can still stop it. See [[delay]].
    "pending": "sb.accent",
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
    # The operator's declared expectation, in seconds. `0` is *no expectation*,
    # which is not the same as an expectation of nothing: without one, silence
    # is neither good nor bad and the band says only how long it has been.
    due: int = 0
    # When a delayed write fires. Distinct from `interval` and `last_run` on
    # purpose: those two mean *cadence*, and an act has none — `--delay` moves
    # when a command runs once, it does not make it run again. See [[delay]].
    fires_at: float | None = None
    # Where a parked follow is looking, 1-based among the lines the ring holds.
    # None while following, which is what keeps a band that has never been
    # scrolled identical to one from before [[follow]] round 3.
    ring_first: int | None = None
    ring_last: int | None = None
    # Whether the operator has scrolled away from the tail. Distinct from
    # having a position: a following view has one too, and says it.
    parked: bool = False
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
            "last_write_at", "size_bytes", "ring_shown", "ring_limit", "due",
            "fires_at", "ring_first", "ring_last", "parked",
        ):
            value = getattr(self, key)
            # Zero is *absent* for a count and *meaningful* for an exit code,
            # which is the one field here where "unset" and "0" are different
            # facts. Dropping it made the canvas read `dead · exited undefined`
            # for the most ordinary death there is — a command that finished.
            # Found by rendering, in [[follow]] round 4; the terminal band
            # never saw it, because it reads the dataclass rather than this.
            if value is None or (value == 0 and key != "exit_code"):
                continue
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
    running_since: float | None = None,
) -> Chrome:
    """A one-time observe: ran once, stamped once.

    `running_since` is set while the subprocess is still alive — the same
    mechanical reading `resident` has always had, arriving here because a
    window that accrues has a *before* now. It says nothing about a cadence:
    an accruing snapshot runs once, exactly as it always did. See [[follow]]
    round 4.
    """
    return Chrome(
        source=source,
        shape="snapshot",
        attention="running" if running_since is not None else _verdict(ok, partial),
        warnings=warnings,
        ran_at=ran_at,
        duration_s=duration_s,
        running_since=running_since,
    )


def act(
    source: str,
    *,
    ok: bool,
    partial: bool = False,
    warnings: int = 0,
    ran_at: float | None = None,
    duration_s: float | None = None,
    running_since: float | None = None,
) -> Chrome:
    """`run`: the same stamp a snapshot gets, and never a countdown — the
    absence is the act/observe split made visible.

    **`running_since` is not a crack in that.** What `act` refuses is a
    cadence and a countdown — a write happening again, or about to. This is
    one write happening *now*, in a window watching it, and the field is
    mechanical: the subprocess has not exited. `interval` and `fires_at` stay
    absent, which is the part the sentence above was ever about.
    """
    chrome = snapshot(
        source,
        ok=ok,
        partial=partial,
        warnings=warnings,
        ran_at=ran_at,
        duration_s=duration_s,
        running_since=running_since,
    )
    return replace(chrome, shape="act")


def pending(source: str, *, fires_at: float) -> Chrome:
    """A write that has not happened yet, and can still be stopped.

    The `act` shape, because that is what it will be — and `act` says it never
    carries a countdown, *"the absence is the act/observe split made visible"*.
    That still holds and this is not a reversal of it: what `act` refuses is a
    **cadence**, a write happening again unattended forever. This is one write
    happening once, later, in a process you are watching, and `fires_at` is a
    different field from `interval` for exactly that reason.
    """
    return Chrome(source=source, shape="act", attention="pending", fires_at=fires_at)


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
    due: int = 0,
    now: float | None = None,
    ring_first: int | None = None,
    ring_last: int | None = None,
    parked: bool = False,
) -> Chrome:
    """A process follow. Alive is `running`; any exit is `dead` — visibly,
    carrying the code, because restart is the operator's click and never the
    surface's initiative.

    Takes `--due` for the same reason the cursor does: a long-running job that
    stopped printing is the same question as a log that stopped growing, and
    answering it in one form and not the other would be an asymmetry with no
    argument behind it.
    """
    return Chrome(
        source=source,
        shape="stream",
        attention=_late(
            "dead" if exit_code is not None else "running", last_line_at, due, now
        ),
        due=due,
        ring_first=ring_first,
        ring_last=ring_last,
        parked=parked,
        last_line_at=last_line_at,
        exit_code=exit_code,
        exited_at=exited_at,
        ring_shown=ring_shown,
        ring_limit=ring_limit,
    )


def _late(state: str, since: float | None, due: int, now: float | None) -> str:
    """`late` when the operator's expectation has been exceeded, else `state`.

    **The operator asserts an interval; sky.boss subtracts.** No crontab is read, no
    next-run is computed, nothing here knows what a schedule is — the whole
    judgment was made when someone typed `--due 15m`, and this is the
    arithmetic that follows from it.

    A stronger fact wins. `dead`, `absent` and `rotated` are things sky.boss *knows*,
    and a dead stream being also late adds nothing — the exit code is the
    better answer. Only the quiet states can become late. See [[file-follow]]
    round 2.
    """
    if not due or since is None or now is None:
        return state
    if state not in ("quiet", "running"):
        return state
    return "late" if (now - since) > due else state


def cursor(
    source: str,
    *,
    state: str = "quiet",
    last_write_at: float | None = None,
    size_bytes: int | None = None,
    ring_shown: int | None = None,
    ring_limit: int | None = None,
    due: int = 0,
    now: float | None = None,
    ring_first: int | None = None,
    ring_last: int | None = None,
    parked: bool = False,
) -> Chrome:
    """A file follow. `state` comes from the cursor's own stat loop —
    quiet, absent or rotated — because the loop is the thing that compared
    the inodes. Chrome carries the verdict; it never re-derives it.

    The one exception is `late`, which is arithmetic rather than a verdict: the
    loop cannot know it because only the operator declared the expectation, and
    `now` is injected so proving a fifteen-minute rule costs no wall clock.
    """
    if state not in ("quiet", "absent", "rotated", "running"):
        raise ValueError(f"not a cursor state: {state!r}")
    return Chrome(
        source=source,
        shape="cursor",
        attention=_late(state, last_write_at, due, now),
        due=due,
        ring_first=ring_first,
        ring_last=ring_last,
        parked=parked,
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

# One span of a band: text plus the theme role it wears, None for the
# terminal's default. The frame — corners and fills — is always muted: it is
# furniture, and furniture that competes with facts is the round-1 mistake
# this layer exists to not repeat.
Span = tuple[str, str | None]

_FRAME = "sb.muted"


def _top_spans(chrome: Chrome, now: float) -> tuple[list[Span], list[Span]]:
    """The title band: identity on the left, liveness on the right.

    The source is the strongest thing in the band; the shape words stay
    muted. On the right, only a state-bearing fact takes the attention
    color — the countdown in accent, a death in danger, a rotation in warn —
    while quiet's clock wears the label role: readable and calm, because
    quiet is the state the band exists to make legible, not to hide.
    """
    left: list[Span] = [(chrome.source, "bold")]
    if chrome.attention == "pending":
        left.append((" · pending", _FRAME))
    elif chrome.shape == "resident" and chrome.interval:
        left.append((f" · refresh {chrome.interval}s", _FRAME))
    elif chrome.shape in ("stream", "cursor"):
        left.append((" · follow", _FRAME))

    right: list[Span] = []
    if chrome.attention == "pending":
        # What is left, and how to stop it. The second half is not decoration:
        # a countdown you cannot see a way out of is a countdown you watch
        # helplessly. See [[delay]].
        remaining = max(0, int((chrome.fires_at or 0) - now))
        return left, [(f"runs in {ago(remaining)}", ROLE["pending"]), (" · q cancels", "sb.label")]
    if chrome.running_since is not None and chrome.shape in ("snapshot", "act", "resident"):
        # One reading for all three: the subprocess has not exited. A resident
        # window swaps its countdown for it, and an accruing one has no
        # countdown to swap. See [[follow]] round 4.
        right = [(f"running {ago(now - chrome.running_since)}", "sb.accent")]
    elif chrome.shape == "resident":
        remaining = countdown(chrome, now)
        if remaining is not None:
            right = [(f"⟳ next in {remaining}s", "sb.accent")]
    elif chrome.shape == "stream":
        if chrome.attention == "dead":
            text = f"dead · exited {chrome.exit_code}"
            if chrome.exited_at is not None:
                text += f" at {clock(chrome.exited_at)}"
            right = [(text, "sb.fail")]
        elif chrome.attention == "late":
            right = _overdue("last line", chrome.last_line_at, chrome, now)
        elif chrome.last_line_at is not None:
            right = [(f"last line {ago(now - chrome.last_line_at)} ago", "sb.label")]
            if chrome.due:
                right.append((f" of {ago(chrome.due)}", "sb.label"))
    elif chrome.shape == "cursor":
        if chrome.attention == "absent":
            right = [("waiting for it to exist", "sb.warn")]
        elif chrome.attention == "rotated":
            right = [("rotated", "sb.warn")]
        elif chrome.attention == "late":
            right = _overdue("late", chrome.last_write_at, chrome, now)
        elif chrome.last_write_at is not None:
            right = [
                (f"quiet {ago(now - chrome.last_write_at)}", "sb.label"),
                # `quiet 3m of 15m` — the expectation beside the elapsed time,
                # so a healthy watcher shows its own margin rather than only
                # becoming legible at the moment it fails.
                (f" of {ago(chrome.due)}" if chrome.due else "", "sb.label"),
                (f" · last write {clock(chrome.last_write_at)}", "sb.label"),
            ]

    return left, right


def _overdue(word: str, since: float | None, chrome: Chrome, now: float) -> list[Span]:
    """`late 47m, due 15m` — how long, and what was expected. Both, because
    either alone leaves the reader doing the subtraction the flag exists to do
    for them."""
    elapsed = ago(now - since) if since is not None else "?"
    return [(f"{word} {elapsed}", ROLE["late"]), (f", due {ago(chrome.due)}", "sb.label")]


def _bottom_spans(chrome: Chrome, now: float) -> tuple[list[Span], list[Span]]:
    """The footer band: verdict and cost on the left, nothing on the right.
    The verdict word wears its verdict's color; clocks and stamps take the
    label role, counts the number role, warnings the warn role."""
    left: list[Span] = []
    if chrome.attention == "pending":
        return [("nothing has run yet", "sb.label")], []
    if chrome.shape in ("snapshot", "resident", "act"):
        word = chrome.attention if chrome.running_since is None else "running"
        left.append((word, ROLE.get(word, "sb.label")))
        if chrome.duration_s is not None:
            left.append((f" · {chrome.duration_s:.1f}s", "sb.num"))
        if chrome.ran_at is not None:
            left.append((f" · ran {clock(chrome.ran_at)}", "sb.label"))
        if chrome.warnings:
            plural = "" if chrome.warnings == 1 else "s"
            left.append((f" · {chrome.warnings} warning{plural}", "sb.warn"))
    else:
        lead = ""
        if chrome.size_bytes is not None:
            # The one byte-formatter the CLI already has — two of these is
            # exactly the drift this module exists to prevent.
            from cli.output import humanize_bytes

            left.append((humanize_bytes(chrome.size_bytes), "sb.num"))
            lead = " · "
        if chrome.ring_shown is not None and chrome.ring_limit is not None:
            shown = min(chrome.ring_shown, chrome.ring_limit)
            if chrome.ring_first is None:
                left.append((f"{lead}showing last {shown}", "sb.label"))
            elif chrome.ring_last - chrome.ring_first + 1 >= shown:
                # Everything held is on screen, which is what "showing last N"
                # always meant and the one case where it was not lying. Kept
                # word for word — [[chrome]]'s own sketch uses this phrasing.
                left.append((f"{lead}showing last {shown}", "sb.label"))
            else:
                # A scrollbar, written out: position and extent. [[refresh]]
                # round 2 rejected scrolling partly because "it owes the
                # operator a scrollbar", and this is the band paying that debt
                # in the slot [[chrome]] already built.
                #
                # Reported while *following* too, not only while parked. The
                # old band said "showing last 200" while drawing forty of them
                # and relied on a separate clip marker to admit it — two places
                # telling half the truth each. See [[follow]] round 3.
                left.append(
                    (f"{lead}showing {chrome.ring_first}\u2013{chrome.ring_last} of {shown}",
                     "sb.label")
                )
            if chrome.parked:
                left.append((" \u00b7 parked", ROLE["pending"]))

    return left, []


def _clip(spans: list[Span], room: int) -> list[Span]:
    """Truncate a span list to `room` characters, ellipsis included, keeping
    each surviving character's role."""
    total = sum(len(text) for text, _ in spans)
    if total <= room:
        return list(spans)
    budget = max(0, room - 1)
    out: list[Span] = []
    for text, role in spans:
        if budget <= 0:
            break
        take = text[:budget]
        out.append((take, role))
        budget -= len(take)
    out.append(("…", out[-1][1] if out else None))
    return out


def _assemble(left: list[Span], right: list[Span], width: int, corners: str) -> list[Span]:
    """One box-drawing band as spans: `┌ left ───── right ┐`.

    Exactly `width` characters when width allows; the left side gives way
    first, because the right side is the live half (a countdown, a clock) and
    a clock you cannot see is the silent failure the chrome exists to avoid.
    """
    open_c, close_c = corners
    right_len = sum(len(text) for text, _ in right)
    tail_len = (right_len + 3) if right else 1
    room = width - 1 - 1 - 1 - _MIN_FILL - tail_len
    left = _clip(left, room)
    left_len = sum(len(text) for text, _ in left)
    fill = max(_MIN_FILL, width - 1 - 1 - left_len - 1 - tail_len)

    spans: list[Span] = [(f"{open_c} ", _FRAME), *left, (" " + "─" * fill, _FRAME)]
    if right:
        spans.append((" ", None))
        spans.extend(right)
        spans.append((f" {close_c}", _FRAME))
    else:
        spans.append((close_c, _FRAME))
    return spans


def status_bands(chrome: Chrome, now: float, width: int) -> tuple[list[Span], list[Span]]:
    """The two terminal bands as `(text, role)` spans — the deciding half of
    the round-2 polish, where pytest reaches it. Renderers assemble these
    into styled text and add nothing. No spinners, no percentages — a
    running subprocess has no percentage, and a bar that animates to look
    busy is decoration that reads as information."""
    top_left, top_right = _top_spans(chrome, now)
    bottom_left, bottom_right = _bottom_spans(chrome, now)
    return (
        _assemble(top_left, top_right, width, "┌┐"),
        _assemble(bottom_left, bottom_right, width, "└┘"),
    )


def status_lines(chrome: Chrome, now: float, width: int) -> tuple[str, str]:
    """The same bands as plain strings — the spans joined, byte-identical to
    what round 1 drew, which is what keeps every width and truncation
    property proven once proven."""
    top, bottom = status_bands(chrome, now, width)
    return "".join(text for text, _ in top), "".join(text for text, _ in bottom)
