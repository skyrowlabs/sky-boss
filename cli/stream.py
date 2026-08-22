"""One execution mechanism — a Job is a stream that ends. See [[follow]].

The constitution's unification: output accrues as it happens and exit is just
an event that stamps a status. Duration is discovered, never declared — there
is no "job" flag, a snapshot that turns out to take eight minutes simply is
one, and the surface shows it accruing either way. This module is the
substrate `follow` is built on and `run`/`read` stream through; `data` stays
report-at-exit on purpose, because a JSON document parses only when complete.

**Reads in, execution out — and killable.** The process is a real subprocess
through `child_env()` ([[subprocess-env]]); reader threads pump its pipes into
a bounded ring. A thread cannot be cancelled, but these never need to be:
they die when the pipe closes, and the pipe closes because the *process* was
killed — SIGTERM, then SIGKILL after a grace period. The hang lives in the
child, and the child is killable.

**Bounded, always.** The ring holds the last N lines; the terminal scrollback
or the file remains the record. `keep_all` exists for `run` and `read`, whose
envelopes carry the full text by contract — and even that accumulation stops
at a cap, the same rule every surface here has had since the first 120k-line
result froze one.
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import IO, Callable

from cli.helpers import child_env

DEFAULT_LINES = 200

# The accumulation cap for keep_all, shared with `read`'s own MAX_CHARS rule:
# past this the envelope stops growing and says so.
MAX_KEEP_CHARS = 200_000

# SIGTERM first, and this long for the child to take the hint before SIGKILL.
GRACE_SECONDS = 5.0


@dataclass(frozen=True)
class Line:
    """One line as it arrived. `stderr` is a tag, never a merge — streaming
    tools talk on stderr constantly, and the tag is what lets a Rule tint
    those lines later without re-plumbing."""

    text: str
    stderr: bool
    at: float
    # tb's own announcement — a rotation, a truncation — pushed into the
    # stream because an event worth seeing belongs where the eyes are. It
    # rode the `stderr` tag until [[highlight]] round 4 made stderr grey;
    # the cursor's voice has to stay loud, so it gets a channel of its own
    # rather than borrowing one whose meaning changed underneath it.
    voice: bool = False


class Ring:
    """The last N lines, and an honest count of what scrolled off."""

    def __init__(self, limit: int = DEFAULT_LINES):
        self.limit = limit
        self._lines: deque[Line] = deque(maxlen=limit)
        self.total = 0

    def push(self, line: Line) -> None:
        self._lines.append(line)
        self.total += 1

    def lines(self) -> list[Line]:
        return list(self._lines)

    @property
    def dropped(self) -> int:
        return max(0, self.total - self.limit)

    @property
    def last_at(self) -> float | None:
        return self._lines[-1].at if self._lines else None


def pump(source: IO[str], stderr: bool, sink: Callable[[Line], None], clock=time.time) -> None:
    """Read a pipe line by line into `sink` until it closes. A thread target,
    and deliberately nothing more — all state lives behind the sink, so this
    is testable with a StringIO and no thread at all."""
    for raw in source:
        sink(Line(text=raw.rstrip("\n"), stderr=stderr, at=clock()))
    source.close()


class ChildStream:
    """A spawned process, read line by line as it speaks.

    The liveness clock here is "last line arrived" and nothing deeper — a
    process's only signal is its output, which is exactly why the file
    cursor ([[file-follow]]) is a different mechanism: a file yields to stat.
    """

    def __init__(
        self,
        argv: list[str],
        *,
        cwd: str | None = None,
        limit: int = DEFAULT_LINES,
        clock: Callable[[], float] = time.time,
    ):
        self.argv = list(argv)
        self.clock = clock
        self.ring = Ring(limit)
        self.started_at = clock()
        self._lock = threading.Lock()

        self.proc = subprocess.Popen(
            self.argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line buffered, so a line arrives when it is printed
            cwd=cwd,
            env=child_env(),
        )
        self._threads = [
            threading.Thread(target=pump, args=(self.proc.stdout, False, self._sink, clock), daemon=True),
            threading.Thread(target=pump, args=(self.proc.stderr, True, self._sink, clock), daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def _sink(self, line: Line) -> None:
        with self._lock:
            self.ring.push(line)

    # ------------------------------------------------------------- observing

    def lines(self) -> list[Line]:
        with self._lock:
            return self.ring.lines()

    def fresh(self, since_total: int) -> tuple[list[Line], int]:
        """Lines that arrived after the caller's high-water mark, and the new
        mark. If more arrived than the ring holds, the ring is what there is —
        the drop is visible through `since` jumping, never silent."""
        with self._lock:
            missed = self.ring.total - since_total
            kept = self.ring.lines()
            if missed <= 0:
                out: list[Line] = []
            elif missed >= len(kept):
                out = kept
            else:
                out = kept[-missed:]
            return out, self.ring.total

    @property
    def last_line_at(self) -> float | None:
        with self._lock:
            return self.ring.last_at

    @property
    def exit_code(self) -> int | None:
        return self.proc.poll()

    # ------------------------------------------------------------- lifecycle

    def wait(self, timeout: float | None = None) -> int:
        """Wait for exit, then for the pumps to drain the tail of the pipes.
        Raises subprocess.TimeoutExpired — the caller owns the timeout
        policy, this owns the mechanism."""
        code = self.proc.wait(timeout)
        for thread in self._threads:
            thread.join(timeout=GRACE_SECONDS)
        return code

    def kill(self) -> None:
        """SIGTERM, a grace period, then SIGKILL. Never raises — killing a
        process that already died is a success, not an error."""
        if self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


# ============================================================================
# Linear accrual — live output for run and read
# ============================================================================


@dataclass
class Outcome:
    """How a streamed execution ended. The caller maps this onto its own
    envelope — the envelope's shape is each command's contract, not ours."""

    exit_code: int
    duration_s: float
    stdout: str
    stderr: str
    timed_out: bool = False
    truncated: bool = False


def accrue(
    argv: list[str],
    *,
    timeout: float | None = None,
    cwd: str | None = None,
    echo: Callable[[Line], None],
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    poll: float = 0.05,
) -> Outcome:
    """Run an argv, handing each line to `echo` as it arrives.

    This is the black-box gap closing: `tb run -- <ten-minute build>` shows
    its output while it runs, and exit is an event that stamps a status
    rather than the moment output first exists. The full text is still
    accumulated (capped) because `run` and `read` carry it in their
    envelopes by contract — the envelope under `--json` never streams.

    Raises FileNotFoundError before anything streams if the command does not
    exist — the caller already has an envelope shape for that.

    The pending queue is unbounded on purpose: every line must reach `echo`
    exactly once, because a pipe reading tb's stdout is owed the tool's
    whole output. Memory is bounded the same way it always was — the
    buffered path held the full text too — and the *envelope's* copy is
    capped at MAX_KEEP_CHARS with the cut declared.
    """
    started = clock()
    pending: deque[Line] = deque()
    lock = threading.Lock()

    def sink(line: Line) -> None:
        with lock:
            pending.append(line)

    proc = subprocess.Popen(
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=cwd,
        env=child_env(),
    )
    threads = [
        threading.Thread(target=pump, args=(proc.stdout, False, sink, clock), daemon=True),
        threading.Thread(target=pump, args=(proc.stderr, True, sink, clock), daemon=True),
    ]
    for thread in threads:
        thread.start()

    out_lines: list[str] = []
    err_lines: list[str] = []
    timed_out = False

    def drain() -> None:
        while True:
            with lock:
                if not pending:
                    return
                line = pending.popleft()
            echo(line)
            (err_lines if line.stderr else out_lines).append(line.text)

    deadline = started + timeout if timeout else None
    while True:
        drain()
        if proc.poll() is not None:
            break
        if deadline is not None and clock() > deadline:
            proc.terminate()
            try:
                proc.wait(timeout=GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill()
            timed_out = True
            break
        sleep(poll)

    code = proc.wait()
    for thread in threads:  # the tail of the pipes, then nothing more arrives
        thread.join(timeout=GRACE_SECONDS)
    drain()

    def capped(lines: list[str]) -> tuple[str, bool]:
        text = "\n".join(lines)
        if len(text) > MAX_KEEP_CHARS:
            return text[:MAX_KEEP_CHARS], True
        return text, False

    stdout_text, cut_out = capped(out_lines)
    stderr_text, cut_err = capped(err_lines)

    return Outcome(
        exit_code=code,
        duration_s=round(clock() - started, 2),
        stdout=stdout_text,
        stderr=stderr_text,
        timed_out=timed_out,
        truncated=cut_out or cut_err,
    )
