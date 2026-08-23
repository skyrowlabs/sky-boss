"""The streaming substrate — a Job is a stream that ends. See [[follow]].

The properties worth defending: the ring bounds memory, stderr is tagged and
never merged blind, a hung child is killable inside a bounded wait, and the
accrual's envelope facts match what the buffered path would have said. Pure
parts (Ring, pump, fresh) run with no process and no thread; the few tests
that spawn a real child bound every wait.
"""

import io
import subprocess

from cli.stream import (
    MAX_KEEP_CHARS,
    ChildStream,
    Line,
    Outcome,
    Ring,
    accrue,
    pump,
)

# Generous ceilings — they bound a hang, they measure nothing.
WAIT = 10


# ============================================================================
# The pure parts
# ============================================================================


def test_the_ring_bounds_memory_and_counts_what_scrolled_off():
    ring = Ring(limit=5)
    for n in range(12):
        ring.push(Line(text=str(n), stderr=False, at=float(n)))
    assert [line.text for line in ring.lines()] == ["7", "8", "9", "10", "11"]
    assert ring.total == 12
    assert ring.dropped == 7
    assert ring.last_at == 11.0


def test_pump_reads_a_pipe_to_its_end_with_no_thread_at_all():
    sink: list[Line] = []
    pump(io.StringIO("one\ntwo\n"), stderr=True, sink=sink.append, clock=lambda: 7.0)
    assert [line.text for line in sink] == ["one", "two"]
    assert all(line.stderr and line.at == 7.0 for line in sink)


def test_fresh_hands_over_only_what_arrived_since_the_mark():
    stream = ChildStream.__new__(ChildStream)  # the ring logic, no process
    import threading

    stream.ring = Ring(limit=3)
    stream._lock = threading.Lock()
    stream._keep = None
    for n in range(2):
        stream.ring.push(Line(str(n), False, 0.0))
    lines, mark = stream.fresh(0)
    assert [line.text for line in lines] == ["0", "1"]
    lines, mark = stream.fresh(mark)
    assert lines == []
    for n in range(2, 8):  # six more — the ring only holds three
        stream.ring.push(Line(str(n), False, 0.0))
    lines, mark = stream.fresh(mark)
    assert [line.text for line in lines] == ["5", "6", "7"]
    assert mark == 8


# ============================================================================
# A real child, every wait bounded
# ============================================================================


def test_a_child_is_read_as_it_speaks_and_stderr_is_tagged():
    child = ChildStream(["sh", "-c", "echo out; echo err >&2; echo more"])
    assert child.wait(WAIT) == 0
    texts = {(line.text, line.stderr) for line in child.lines()}
    assert ("out", False) in texts and ("more", False) in texts
    assert ("err", True) in texts


def test_a_hung_child_is_killable_inside_a_bounded_wait():
    """The whole reason execution is a subprocess: a thread cannot be
    cancelled, a process can. SIGTERM must be enough for a sleep."""
    child = ChildStream(["sleep", "100"])
    assert child.exit_code is None
    child.kill()
    assert child.exit_code is not None
    child.kill()  # killing a corpse is a success, not an error


def test_the_envelope_copy_is_capped_and_the_cut_declared():
    """Every line still reaches echo — a pipe is owed the whole output — but
    the envelope's copy stops at the cap, the same bound every surface here
    has had since the first 120k-line result froze one."""
    outcome = accrue(
        ["python3", "-c", f"print('x' * {MAX_KEEP_CHARS + 5000})"],
        echo=lambda line: None,
    )
    assert outcome.truncated is True
    assert len(outcome.stdout) == MAX_KEEP_CHARS


# ============================================================================
# Accrual
# ============================================================================


def test_accrue_hands_lines_over_while_the_process_runs():
    got: list[str] = []
    outcome = accrue(
        ["sh", "-c", "echo a; echo b >&2; echo c"],
        echo=lambda line: got.append(("!" if line.stderr else "") + line.text),
    )
    assert isinstance(outcome, Outcome)
    assert outcome.exit_code == 0
    assert sorted(got) == ["!b", "a", "c"]
    assert outcome.stdout == "a\nc" and outcome.stderr == "b"


def test_accrue_enforces_the_timeout_by_killing_the_child():
    outcome = accrue(["sh", "-c", "sleep 30"], timeout=0.2, echo=lambda line: None)
    assert outcome.timed_out is True


def test_accrue_raises_on_a_command_that_does_not_exist():
    import pytest

    with pytest.raises(FileNotFoundError):
        accrue(["definitely-not-a-real-command-xyz"], echo=lambda line: None)


# ============================================================================
# Live accrual through run and read
# ============================================================================


def test_a_human_read_streams_the_lines_pure_on_stdout():
    """`tb read -- x | grep` sees exactly what the tool printed — the chrome
    stamp is status and goes to stderr, same purity rule as warnings."""
    from click.testing import CliRunner

    from cli import cli

    result = CliRunner().invoke(cli, ["read", "--", "printf", "a\\nb\\n"])
    assert result.exit_code == 0
    assert result.stdout == "a\nb\n"
    assert "ok" in result.stderr  # the act stamp band


def test_a_human_run_streams_and_stamps_the_act():
    from click.testing import CliRunner

    from cli import cli

    result = CliRunner().invoke(cli, ["run", "--", "sh", "-c", "echo hi"])
    assert result.exit_code == 0
    assert result.stdout == "hi\n"
    assert "└" in result.stderr and "ok" in result.stderr


def test_a_failing_human_run_still_exits_nonzero_with_the_lines_shown():
    from click.testing import CliRunner

    from cli import cli

    result = CliRunner().invoke(cli, ["run", "--", "sh", "-c", "echo trouble; exit 3"])
    assert result.exit_code == 1
    assert "trouble" in result.stdout
    assert "failed" in result.stderr


def test_the_json_envelope_is_still_built_once_complete_at_exit():
    """The accrual is a surface behavior; the contract did not move. The
    envelope under --json is byte-for-byte the buffered path's."""
    import json

    from click.testing import CliRunner

    from cli import cli

    result = CliRunner().invoke(cli, ["--json", "run", "--", "sh", "-c", "echo hi"])
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["stdout"] == "hi\n"
    assert list(envelope) == ["command", "ok", "partial", "data", "warnings"]


# ============================================================================
# The display's width, handed to the child — [[subprocess-env]] round 2
# ============================================================================


def test_a_child_is_told_how_wide_the_display_is():
    """The operator's report: `tb follow -- jam report watch --follow` drew a
    different picture from `jam report watch --follow` in the same terminal.
    A tool lays out by asking its stdout how wide the terminal is; under tb
    that stdout is a pipe, so it falls back to its own default and truncates.
    Measured against the real thing: with COLUMNS the child's output is
    byte-identical to its output in a terminal, without it every long line
    loses its tail."""
    import time

    from cli.stream import ChildStream

    child = ChildStream(["sh", "-c", "echo width=$COLUMNS"], columns=150)
    child.wait(timeout=10)
    assert [line.text for line in child.lines()] == ["width=150"]


def test_a_child_is_told_nothing_when_there_is_no_display(monkeypatch):
    """Piped output has no width worth claiming — the consumer may be a file,
    and a tool wrapping to a number tb invented is worse than one using its
    own default.

    Note what is *not* claimed: that the child sees no `COLUMNS` at all. If
    the operator exports one, it passes through like every other variable —
    round 1's rule is that tb scrubs what it added to boot and nothing else.
    What this pins is that tb adds none of its own."""
    monkeypatch.delenv("COLUMNS", raising=False)
    from cli.stream import ChildStream

    child = ChildStream(["sh", "-c", "echo width=[$COLUMNS]"])
    child.wait(timeout=10)
    assert [line.text for line in child.lines()] == ["width=[]"]


def test_the_operators_own_width_still_passes_through(monkeypatch):
    """The environment is theirs. tb overrides it only when it knows better —
    which is exactly when it has a display to describe."""
    monkeypatch.setenv("COLUMNS", "99")
    from cli.helpers import child_env

    assert child_env()["COLUMNS"] == "99"
    assert child_env(150)["COLUMNS"] == "150"


def test_the_height_is_never_passed(monkeypatch):
    """A tool that thinks it knows the height may decide to paginate, and a
    pager inside a stream is a hang."""
    monkeypatch.delenv("LINES", raising=False)
    from cli.helpers import child_env

    assert "LINES" not in child_env(150)
    assert child_env(150)["COLUMNS"] == "150"
