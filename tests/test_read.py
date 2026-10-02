"""`sb read` — showing what a tool printed, on a cadence.

The property that justifies the command is the one in `test_read_is_a_read`:
`sb run` already carried text and could never be pinned, so the gap was never
display.
"""

import json
import sys

import pytest
from click.testing import CliRunner

from skyboss import cli
from skyboss.read import MAX_CHARS
from skyboss.read import TRUNCATED as MAX_CHARS_NOTICE
from skyboss.read import strip_ansi

#: Every test here is host-side and needs no services up.
pytestmark = [pytest.mark.unit]


def invoke(args):
    """The result and its envelope — and the envelope is not Optional.

    `sb --json` promises an envelope on stdout, so an empty stdout is that
    promise broken. This used to return `None` for it, which made every caller
    below subscript a maybe-None: the failure arrived as `TypeError: 'NoneType'
    object is not subscriptable`, naming neither the command nor its exit code
    nor what was actually printed. Asserting here is the same rule the tool
    itself is held to — a refusal is a sentence where a silence is not.

    A Click usage error is the one case where no envelope is correct, because
    the refusal happens before any command runs. Those tests take the `refuse` fixture.
    """
    result = CliRunner().invoke(cli, ["--json", "read", *args])
    assert result.stdout.strip(), (
        f"`sb --json read {' '.join(args)}` printed no envelope on stdout "
        f"(exit {result.exit_code}).\n{result.output}"
    )
    return result, json.loads(result.stdout)


@pytest.fixture
def refuse(monkeypatch):
    """A Click usage error: exit 2 and no envelope, so the result alone — and
    **always drawn in colour**, because that is the condition CI runs under and
    the only one where an assertion about the sentence breaks.

    rich-click reads `GITHUB_ACTIONS` and calls a runner a terminal, so every
    option name in a usage error arrives wrapped in escapes and
    `--fold needs --shapes` stops being a substring of itself. That is not a
    hypothetical: it is how this file first reached `develop` red, having
    passed on 3.11 locally and failed on both runner legs. The lever is
    `HELP_CONFIG` rather than the environment variable, which a default factory
    reads at import, before any test could set it.

    Putting the condition in the helper rather than in one test is the point.
    Which assertion the escapes break depends on where the wrap lands, so a fix
    applied to the one that happened to fail leaves the class untouched.
    """
    from skyboss import HELP_CONFIG

    monkeypatch.setattr(HELP_CONFIG, "force_terminal", True)

    def go(args=()):
        result = CliRunner().invoke(cli, ["--json", "read", *args])
        # Without this the fixture is vacuous — an uncoloured render passes
        # every assertion below while proving nothing. Count the looking.
        assert "\x1b[" in result.output, "nothing was drawn in colour; the case is not reproduced"
        return result

    return go


def test_read_is_a_read_so_a_window_may_pin_it():
    """The whole reason it exists. `sb run` carries text too and acts, so its
    window can never be given a cadence."""
    from skyboss.canvas.catalog import catalog

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


def test_envelope_for_is_reads_own_and_not_shared_with_run():
    """Shared between *surfaces*, not between commands: a `read` reports a
    non-zero exit as a warning and carries its error as text, where an act
    carries a mapping. See [[follow]] round 4."""
    from skyboss.read import envelope_for
    from skyboss.stream import Outcome

    ok = envelope_for(Outcome(0, 0.1, "rows\n", ""), 60)
    assert ok.ok is True and ok.data is None and ok.warnings == []

    failed = envelope_for(Outcome(3, 0.2, "", "boom\n"), 60)
    assert failed.ok is False and failed.warnings == ["exited 3 after 0.2s"]

    late = envelope_for(Outcome(-1, 60.0, "", "", timed_out=True), 60)
    assert late.ok is False and late.data == "timed out after 60s"


# ------------------------------------------------------- --shapes (round 8)
#
# A sample of what the command printed, for writing a `[highlight.NAME]` block
# against a log nobody can read all of. See [[highlight]] round 8.


def test_shapes_returns_rows_and_not_verbatim_text():
    _, env = invoke(["--shapes", "--", "printf", "a 1\\na 2\\nb 3\\n"])
    rows = env["data"]
    assert isinstance(rows, list)
    assert {r["shape"] for r in rows} == {"a «num»", "b «num»"}
    assert sorted(r["lines"] for r in rows) == [1, 2]


def test_shapes_authors_its_view_so_an_inference_cannot_widen_it():
    """Three columns sky.boss chose. An inferred view would round-trip through
    `/api/shape` and come back with whatever it found. See [[schedule]] round 3."""
    _, env = invoke(["--shapes", "--", "printf", "a 1\\n"])
    assert env["view"]["authored"] is True
    assert [c["key"] for c in env["view"]["columns"]] == ["lines", "shape"]


def test_shapes_says_how_many_lines_it_sampled():
    """Seven rows must not read as seven lines. The count of the *looking*, not
    only of the finding — the rule this repo keeps arriving at."""
    _, env = invoke(["--shapes", "--", "printf", "a 1\\na 2\\nb 3\\n"])
    assert any("3 non-blank lines" in w for w in env["warnings"])


def test_shapes_has_no_cadence(refuse, said):
    """A sample is one pass over a whole output. Accepting `--refresh` and
    ignoring it is the wrong-but-looks-right failure."""
    result = refuse(["--shapes", "--refresh", "5", "--", "true"])
    assert result.exit_code == 2
    assert "no cadence" in said(result)


def test_fold_without_shapes_is_refused_rather_than_ignored(refuse, said):
    """The `--ticks` case one flag over: a modifier with nothing to modify
    reads as a request that was honoured."""
    result = refuse(["--fold", "--", "true"])
    assert result.exit_code == 2
    assert "--fold needs --shapes" in said(result)


def test_shapes_cannot_be_saved_because_save_saves_by_example(refuse, said):
    result = refuse(["--shapes", "--save", "x", "--", "true"])
    assert result.exit_code == 2
    assert "cannot be saved" in said(result)


def test_the_three_empties_are_three_different_sentences():
    """A failed command, a command that printed nothing, and output that is all
    blank lines want different conclusions. See [[agent-sessions]] round 1."""
    _, failed = invoke(["--shapes", "--", "false"])
    _, silent = invoke(["--shapes", "--", "true"])
    _, blank = invoke(["--shapes", "--", "printf", "\\n\\n"])

    reasons = [" ".join(e["warnings"]) for e in (failed, silent, blank)]
    assert all(e["data"] == [] for e in (failed, silent, blank))
    assert "the command failed" in reasons[0]
    assert "printed nothing at all" in reasons[1]
    assert "are blank" in reasons[2]
    assert len(set(reasons)) == 3


def _floods(line: str) -> list[str]:
    """An argv that *prints* more than `MAX_CHARS`, rather than carrying it.

    Passing the text as an argument is `E2BIG` at about 128k on Linux, which
    fails the command instead of truncating its output — so the first draft of
    these two tests was measuring the argument limit and not the sampler.
    """
    n = MAX_CHARS // len(line) + 200
    return [sys.executable, "-c", f"import sys; sys.stdout.write({line!r} * {n})"]


def test_a_truncated_read_says_its_sample_is_partial():
    """`N characters not shown` reads as a display cap. For a sample it means
    every count describes a prefix of the log, which is a different and much
    more misleading claim if nobody says it."""
    _, env = invoke(["--shapes", "--"] + _floods("run 1 ok\n"))
    assert any(MAX_CHARS_NOTICE in w for w in env["warnings"])
    assert any("counts are partial" in w for w in env["warnings"])


def test_a_truncated_read_drops_its_half_line():
    """The last surviving line is cut mid-line, and half a line is a shape that
    exists nowhere in the log."""
    _, env = invoke(["--shapes", "--"] + _floods("run 1 ok\n"))
    assert [r["shape"] for r in env["data"]] == ["run «num» ok"]
