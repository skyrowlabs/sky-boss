"""The native file cursor — `tb follow <path>`. See [[file-follow]].

**Why a native loop and not a spawned `tail -F`:** the improvements a file
follow needs are made of file knowledge a spawned tail cannot see. tb can
*stat* the file, so the liveness clock says "file untouched since 19:00"
rather than merely "no new lines arrived" — and that difference is the whole
feature, because the driving log's silences run to ninety minutes *while
everything is fine*. Rotation and truncation are detected by inode and size
rather than inherited from tail's flavor; backfill-then-follow is one
mechanism instead of a flag. The reversal from tail-F-as-sugar is recorded
in the constitution.

**The cursor owns files; the process stream ([[follow]]) owns commands.**
One verb fronts both; `cli/follow.py` owns the dispatch.

**Verbatim lines only.** No parsing, no filtering, no judgment — the
cron.log evidence is the argument: timestamped lines, untimestamped
`[isolation]` lines, blank spacers, multi-line blocks. Rotation and
truncation announcements are the one exception, pushed *into* the stream as
marked lines because an event worth seeing belongs where the eyes are.
"""

from __future__ import annotations

import os
import time
from typing import Callable

from cli.stream import DEFAULT_LINES, Line, Ring

# How far back the backfill reads. Enough for any plausible ring of lines;
# bounded so following a gigabyte log opens in milliseconds, not minutes.
BACKFILL_BYTES = 256 * 1024


class RealFs:
    """The two file operations the cursor needs, behind a seam a test can
    replace — the suite proves rotation without ever rotating a file."""

    def stat(self, path: str) -> tuple[int, float, int] | None:
        """(size, mtime, inode), or None when the file is not there."""
        try:
            st = os.stat(path)
        except (FileNotFoundError, NotADirectoryError):
            return None
        return st.st_size, st.st_mtime, st.st_ino

    def read(self, path: str, offset: int) -> str:
        """From offset to EOF. Decoded permissively — a log with one bad
        byte is still a log worth following."""
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            handle.seek(offset)
            return handle.read()


class FileCursor:
    """Open, stat, seek — the loop [[file-follow]] specs, pure over an
    injected clock and filesystem.

    Each tick stats and compares: grown → emit whole lines from the offset;
    same → the quiet clock advances; shrunk or a different inode → say so in
    the stream and start over from the new tail; absent → wait for it to
    exist, and begin at zero when it appears. A partial final line is held
    until its newline arrives — never emitted half.
    """

    def __init__(
        self,
        path: str,
        *,
        limit: int = DEFAULT_LINES,
        fs: RealFs | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.path = path
        self.fs = fs or RealFs()
        self.clock = clock
        self.ring = Ring(limit)
        self.state = "absent"  # the chrome attention word: see cli/chrome.py
        self.size: int | None = None
        self.last_write_at: float | None = None
        self._inode: int | None = None
        self._offset = 0
        self._partial = ""
        self.tick()

    # -------------------------------------------------------------- the loop

    def tick(self) -> None:
        st = self.fs.stat(self.path)

        if st is None:
            if self._inode is not None:
                self._event("file is gone — waiting for it to return")
            self.state = "absent"
            self._inode = None
            self._offset = 0
            self._partial = ""
            self.size = None
            return

        size, mtime, inode = st
        self.size = size
        self.last_write_at = mtime

        if self._inode is None:
            # First sighting — either at open, or the absent file appearing.
            # At open, backfill the tail; a file that appeared under a
            # waiting cursor is read from its start, which for a fresh log
            # *is* the tail — unless it arrived already huge, where the
            # bounded backfill applies as it does everywhere.
            self._inode = inode
            if (self.ring.total == 0 and size > 0) or size > BACKFILL_BYTES:
                self._backfill(size)
            else:
                self._offset = 0
                self._advance(size)
            self.state = "quiet"
            return

        if inode != self._inode:
            # Rotation. An event worth seeing, not a condition to paper over.
            self._event("rotated — following the new file")
            self._inode = inode
            self._offset = 0
            self._partial = ""
            self._backfill(size)
            self.state = "rotated"
            return

        if size < self._offset:
            self._event("truncated — starting over")
            self._offset = 0
            self._partial = ""
            self._backfill(size)
            self.state = "rotated"
            return

        if size > self._offset:
            self._advance(size)
            self.state = "running"
        else:
            self.state = "quiet"

    # -------------------------------------------------------- reading pieces

    def _advance(self, size: int) -> None:
        text = self._partial + self.fs.read(self.path, self._offset)
        self._offset = size
        *whole, self._partial = text.split("\n")
        now = self.clock()
        for line in whole:
            self.ring.push(Line(text=line, stderr=False, at=now))

    def _backfill(self, size: int) -> None:
        """The last N complete lines, from a bounded read of the tail."""
        start = max(0, size - BACKFILL_BYTES)
        text = self.fs.read(self.path, start)
        self._offset = size
        lines = text.split("\n")
        if start > 0 and lines:
            lines = lines[1:]  # a read that began mid-line drops the fragment
        self._partial = lines.pop() if lines else ""
        now = self.clock()
        for line in lines[-self.ring.limit :]:
            self.ring.push(Line(text=line, stderr=False, at=now))

    def _event(self, message: str) -> None:
        """An announcement in the stream — the cursor's own voice, distinct
        from the file's. It carries `voice` as well as `stderr`: round 4 of
        [[highlight]] made an ordinary stderr line grey, because a second
        channel is not a severity, and these must stay loud."""
        self.ring.push(Line(text=f"— {message} —", stderr=True, voice=True, at=self.clock()))

    # ---------------------------------------------- the follower's interface

    def lines(self) -> list[Line]:
        return self.ring.lines()

    def fresh(self, since_total: int) -> tuple[list[Line], int]:
        kept = self.ring.lines()
        missed = self.ring.total - since_total
        if missed <= 0:
            out: list[Line] = []
        elif missed >= len(kept):
            out = kept
        else:
            out = kept[-missed:]
        return out, self.ring.total

    @property
    def last_line_at(self) -> float | None:
        return self.ring.last_at

    @property
    def exit_code(self) -> None:
        """A file never exits. Absent is a state, not a death — the cursor
        keeps waiting, which is the point of following a log that has not
        had its first write yet."""
        return None

    def kill(self) -> None:
        """Nothing to kill: the offset dies with the window, and reopening
        backfills fresh. Present so a follower needs no special case."""


def follow_file(
    path: str,
    *,
    limit: int = DEFAULT_LINES,
    clock: Callable[[], float] = time.time,
    wait: Callable[[float], str | None] | None = None,
    console=None,
    screen: bool = False,
    ticks: int | None = None,
    fs: RealFs | None = None,
    ruleset=None,
    due: int = 0,
) -> None:
    """The terminal rendering: the same residency the process form has, with
    the cursor's stat knowledge in the bands — quiet and dead are different
    words because the loop stats the file.

    **Leaving leaves nothing behind here.** `q`, `Esc` and Ctrl-C all end the
    loop, and a file has nothing to kill — the offset dies with the window
    and reopening backfills fresh. The process form's `q` terminates its
    child; both are "close the window", and the commands differ in what a
    window owns rather than in what the key means. See [[follow]] round 2.
    """
    from rich.console import Console, Group

    from cli import chrome as chrome_
    from cli import resident
    from cli.output import THEME, band_text

    out = console or Console(theme=THEME, highlight=False)
    cursor = FileCursor(path, limit=limit, fs=fs, clock=clock)

    def frame() -> Group:
        kept = cursor.lines()
        facts = chrome_.cursor(
            path,
            state=cursor.state,
            last_write_at=cursor.last_write_at,
            size_bytes=cursor.size,
            ring_shown=len(kept),
            ring_limit=limit,
            due=due,
            now=clock(),
        )
        top, bottom = chrome_.status_bands(facts, clock(), out.width)
        body = resident.stream_body(kept, ruleset)
        # The tail: the newest lines are the ones a log is followed for.
        shown = body if screen else resident.clip(body, resident.room(out), tail=True)
        return Group(band_text(top), shown, band_text(bottom))

    resident.hold(frame, tick=cursor.tick, console=out, screen=screen, ticks=ticks, wait=wait)
