"""sb read — showing what a tool printed, on a cadence.

The property that justifies the command is the one in `test_read_is_a_read`:
`sb run` already carried text and could never be pinned, so the gap was never
display.
"""

import json

from click.testing import CliRunner

from cli import cli
from cli.read import MAX_CHARS, strip_ansi


def invoke(args):
    result = CliRunner().invoke(cli, ["--json", "read", *args])
    return result, json.loads(result.stdout) if result.stdout.strip() else None


def test_read_is_a_read_so_a_window_may_pin_it():
    """The whole reason it exists. `sb run` carries text too and acts, so its
    window can never be given a cadence."""
    from cli.canvas.catalog import catalog

    entries = {e["name"]: e for e in catalog()}
    assert entries["read"]["acts"] is False
    assert entries["run"]["acts"] is True


def test_it_carries_what_the_tool_printed_verbatim():
    """`data` is the text itself, not an object wrapping it — which is what
    lets both renderers show it without either one learning a new shape."""
    _, envelope = invoke(["--", "printf", "a  b\\nc  d\\n"])
    assert envelope["data"] == "a  b\nc  d\n"


def test_alignment_survives():
    """The reason to look at a tool's own output rather than rebuild it from
    JSON. Padding must not be collapsed or re-wrapped."""
    _, envelope = invoke(["--", "printf", "PR     STATE\\n#952   draft\\n"])
    assert "PR     STATE" in envelope["data"]


def test_ansi_is_stripped_not_carried():
    """canvas.md rejected interpreting ANSI and that still stands. What must
    not happen is an escape sitting in the middle of a cell."""
    _, envelope = invoke(["--", "printf", "\\033[32mgreen\\033[0m plain"])
    assert envelope["data"] == "green plain"
    assert "\x1b" not in json.dumps(envelope)


def test_strip_ansi_leaves_ordinary_text_alone():
    assert strip_ansi("no escapes here — ✓ ✗ ─") == "no escapes here — ✓ ✗ ─"


def test_stderr_is_shown_when_the_tool_wrote_its_output_there():
    """Plenty of tools do. An empty window because the tool picked the other
    stream is the least useful reading of "verbatim"."""
    _, envelope = invoke(["--", "sh", "-c", "printf 'to stderr' >&2"])
    assert envelope["data"] == "to stderr"


def test_a_failing_tool_still_shows_what_it_printed():
    """Unlike `wrap`, where a failed tool's output is not to be believed. Here
    the output *is* the answer, and a failure is usually visible in it."""
    result, envelope = invoke(["--", "sh", "-c", "echo trouble; exit 2"])
    assert envelope["ok"] is False
    assert "trouble" in envelope["data"]
    assert any("exited 2" in w for w in envelope["warnings"])
    assert result.exit_code == 1


def test_a_large_result_is_bounded_and_says_so():
    """A 120k-line result kills a browser tab as dead as it killed a RichLog."""
    _, envelope = invoke(["--", "python3", "-c", f"print('x' * {MAX_CHARS + 5000})"])
    assert len(envelope["data"]) == MAX_CHARS
    assert any("not shown" in w for w in envelope["warnings"])


def test_a_missing_command_fails_rather_than_raising():
    _, envelope = invoke(["--", "definitely-not-a-real-command-xyz"])
    assert envelope["ok"] is False
    assert "no such command" in envelope["data"]
