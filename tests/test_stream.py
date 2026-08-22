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
