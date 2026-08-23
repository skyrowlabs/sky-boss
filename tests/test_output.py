"""Tests for the output contract.

Covers the decisions that would break silently: the exit-code mapping, the
warn/degrade distinction, and stdout purity under --json.
"""

import json

import click
import pytest
from click.testing import CliRunner

from cli.output import (
    EXIT_ERROR,
    EXIT_OK,
    EXIT_PARTIAL,
    Result,
    _cell,
    emit,
    exit_code,
    render,
)


# ---------------------------------------------------------------- cell


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, "-"),
        (True, "yes"),
        (False, "no"),
        ("text", "text"),
        (42, "42"),
        ([], "-"),
        (["a", "b"], "a, b"),
        ([None], "-"),
    ],
)
def test_cell(value, expected):
    assert _cell(value) == expected


# ---------------------------------------------------------------- exit codes


def test_exit_code_ok():
    assert exit_code(Result("x")) == EXIT_OK


def test_exit_code_error_beats_partial():
    assert exit_code(Result("x", ok=False, partial=True)) == EXIT_ERROR


def test_partial_is_not_two():
    """Click exits 2 on usage errors.

    If partial were also 2, a job branching on exit codes would read a typo'd
    invocation as a degraded run. This is the whole reason partial is 3.
    """
    assert EXIT_PARTIAL == 3
    assert EXIT_PARTIAL != 2
    assert exit_code(Result("x", partial=True)) == EXIT_PARTIAL


# ---------------------------------------------------------------- warn/degrade


def test_warn_does_not_mark_partial():
    """A warning may be informational; partial must stay a deliberate claim."""
    r = Result("x")
    r.warn("heads up")
    assert r.warnings == ["heads up"]
    assert r.partial is False


def test_degrade_marks_partial():
    r = Result("x")
    r.degrade("host unreachable")
    assert r.partial is True
    assert r.warnings == ["host unreachable"]


# ---------------------------------------------------------------- rendering


def test_json_stdout_is_pure_json(capsys):
    """stdout must parse even when there are warnings — they go to stderr."""
    r = Result("fleet.status", data=[{"host": "a"}])
    r.degrade("b unreachable")
    render(r, as_json=True)

    captured = capsys.readouterr()
    envelope = json.loads(captured.out)
    assert envelope["partial"] is True
    assert envelope["warnings"] == ["b unreachable"]
    assert "unreachable" in captured.err
    assert "unreachable" not in captured.out.split('"warnings"')[0]


def _body(out: str) -> list[str]:
    """Content lines with the header and blanks dropped.

    Asserts on content rather than column positions — layout is exactly what
    the renderer is free to change.

    Header rules are decoration and are dropped too, so an index into this list
    means the same thing whether or not the table was shaped.
    """
    return [
        l.rstrip()
        for l in out.splitlines()
        if l.strip() and not l.lstrip().startswith("●") and set(l.strip()) != {"─"}
    ]


def test_columns_missing_key_renders_empty(capsys):
    """A row missing a key must render EMPTY, not shift the columns."""
    render(Result("x", data=[{"a": 1, "b": 2}, {"a": 3}]), as_json=False)
    body = _body(capsys.readouterr().out)
    assert body[0].split() == ["A", "B"]
    assert body[2].split() == ["3", "-"]


def test_booleans_render_with_glyphs(capsys):
    render(Result("x", data=[{"up": True, "down": False}]), as_json=False)
    body = _body(capsys.readouterr().out)
    assert "\u2713 yes" in body[1]
    assert "\u2717 no" in body[1]


def test_ok_field_triggers_status_list(capsys):
    """The `ok` convention: a data contract, not styling chosen by a command."""
    render(
        Result("doctor", data=[
            {"tool": "aws", "ok": True, "detail": None},
            {"tool": "bws", "ok": False, "detail": "no token"},
        ]),
        as_json=False,
    )
    body = _body(capsys.readouterr().out)
    assert body[0].startswith("\u2713 aws") or "\u2713 aws" in body[0]
    assert "\u2717 bws" in body[1] and "no token" in body[1]
    assert "1 passed" in body[-1] and "1 failed" in body[-1]


def test_unknown_status_is_neither_passed_nor_failed(capsys):
    render(Result("doctor", data=[{"tool": "aws", "ok": None, "detail": "not probed"}]), as_json=False)
    body = _body(capsys.readouterr().out)
    assert "\u00b7 aws" in body[0]
    assert "0 passed" in body[-1]
    assert "failed" not in body[-1]


def test_rows_without_ok_fall_back_to_columns(capsys):
    render(Result("x", data=[{"host": "a", "load": 1}]), as_json=False)
    body = _body(capsys.readouterr().out)
    assert body[0].split() == ["HOST", "LOAD"]


def test_nested_mapping_renders_each_section(capsys):
    render(Result("fleet.describe", data={"os": {"kernel": "7.1"}, "shell": {"login": "fish"}}), as_json=False)
    out = capsys.readouterr().out
    assert "os" in out and "kernel" in out and "7.1" in out
    assert "shell" in out and "fish" in out


def test_warnings_go_to_stderr_in_human_mode(capsys):
    r = Result("x", data="body")
    r.warn("careful")
    render(r, as_json=False)
    captured = capsys.readouterr()
    assert captured.out.strip() == "body"
    assert "careful" in captured.err


# ---------------------------------------------------------------- emit


@pytest.fixture
def app():
    @click.group()
    @click.option("--json", "as_json", is_flag=True)
    @click.pass_context
    def cli(ctx, as_json):
        ctx.ensure_object(dict)
        ctx.obj["as_json"] = as_json

    @cli.group()
    def fleet():
        pass

    @fleet.command()
    @emit
    def good():
        return Result(data="fine")

    @fleet.command()
    @emit
    def degraded():
        r = Result(data="partial data")
        r.degrade("one source down")
        return r

    @fleet.command()
    @emit
    def boom():
        raise RuntimeError("something broke")

    @fleet.command()
    @emit
    def wrongtype():
        return {"not": "a Result"}

    return cli


def test_emit_exit_codes(app):
    runner = CliRunner()
    assert runner.invoke(app, ["fleet", "good"]).exit_code == EXIT_OK
    assert runner.invoke(app, ["fleet", "degraded"]).exit_code == EXIT_PARTIAL
    assert runner.invoke(app, ["fleet", "boom"]).exit_code == EXIT_ERROR


def test_emit_names_result_from_command_path(app):
    """The dotted name becomes the MCP tool name — it must match the real path."""
    res = CliRunner().invoke(app, ["--json", "fleet", "degraded"])
    assert json.loads(res.stdout)["command"] == "fleet.degraded"


def test_exception_becomes_envelope_not_traceback(app):
    res = CliRunner().invoke(app, ["--json", "fleet", "boom"])
    envelope = json.loads(res.stdout)
    assert envelope["ok"] is False
    assert envelope["data"]["type"] == "RuntimeError"
    assert "Traceback" not in res.stdout


def test_non_result_return_is_caught(app):
    res = CliRunner().invoke(app, ["--json", "fleet", "wrongtype"])
    envelope = json.loads(res.stdout)
    assert envelope["ok"] is False
    assert "expected Result" in envelope["data"]["error"]


def test_tb_debug_reraises(app, monkeypatch):
    """Without an escape hatch, tidy error envelopes make the CLI undebuggable."""
    monkeypatch.setenv("TB_DEBUG", "1")
    res = CliRunner().invoke(app, ["fleet", "boom"])
    assert isinstance(res.exception, RuntimeError)


def test_usage_error_still_belongs_to_click(app):
    """Click's own control flow must pass through emit untouched."""
    res = CliRunner().invoke(app, ["fleet", "good", "--nope"])
    assert res.exit_code == 2
    assert "No such option" in res.output


def test_humanize_bytes_uses_binary_units():
    from cli.output import humanize_bytes

    assert humanize_bytes(0) == "0 B"
    assert humanize_bytes(512) == "512 B"
    assert humanize_bytes(4000787030016) == "3.6 TiB"


def test_bytes_key_convention_humanizes_only_that_field(capsys):
    """`*_bytes` carries a raw count in the envelope, humanized only on screen."""
    render(Result("x", data={"size_bytes": 1073741824, "count": 1073741824}), as_json=False)
    out = capsys.readouterr().out
    assert "1.0 GiB" in out
    assert "1073741824" in out


# --------------------------------------------------------------- capture width


def test_help_honours_the_captured_width():
    """rich-click builds its own console, out of reach of the swap.

    Without COLUMNS set, `--help` renders at Rich's 80-column default whatever
    width the consumer asked for.

    Invoked here rather than through a surface. `cli/tui/dispatch.py` used to
    provide the invocation and went with the TUI; the property is capture's,
    not the caller's, so the test now holds it directly.
    """
    import re

    import rich_click as click

    from cli import cli
    from cli.output import capture

    for width in (46, 60, 120):
        with capture(width=width) as captured:
            try:
                cli.main(args=["--help"], prog_name="tb", standalone_mode=False, obj={})
            except click.exceptions.Exit:
                pass
        text = re.sub(r"\x1b\[[0-9;]*m", "", captured.text)
        widest = max(len(line) for line in text.split("\n"))
        assert widest <= width, f"help ran to {widest} columns at width {width}"


def test_capture_restores_columns_even_when_the_body_raises():
    """A leaked COLUMNS would follow every later subprocess out of the process."""
    import os

    from cli.output import capture

    before = os.environ.get("COLUMNS")
    with pytest.raises(RuntimeError):
        with capture(width=37):
            assert os.environ["COLUMNS"] == "37"
            raise RuntimeError("boom")
    assert os.environ.get("COLUMNS") == before


def test_concurrent_captures_do_not_post_into_each_other():
    """capture() was safe while only one dispatch could be in flight — the
    TUI's queue guaranteed it. Swapping module globals meant two concurrent
    captures silently stole each other's output: of four concurrent dispatches,
    two came back empty. Measured, not theorised.

    The consoles are thread-local now, and this is the property that says so.
    It outlived the surface that discovered it: the canvas runs commands out of
    process, but `capture` is still the mechanism any in-process consumer would
    use, and it is still reached from more than one thread at a time.

    `redirect=False` throughout — `sys.stdout` has no per-thread version, so
    the one process-global part is exactly the part a concurrent caller must
    decline.
    """
    import threading

    import rich_click as click

    from cli.output import Result, capture, emit

    @click.command()
    @emit
    def alpha():
        return Result(command="alpha", data={"who": "aaaaa"})

    @click.command()
    @emit
    def beta():
        return Result(command="beta", data={"who": "bbbbb"})

    results: dict[int, str] = {}

    def worker(index, command):
        with capture(width=100, redirect=False) as captured:
            try:
                command.main(args=[], prog_name="tb", standalone_mode=False, obj={})
            except click.exceptions.Exit:
                pass
        results[index] = captured.text

    threads = [
        threading.Thread(target=worker, args=(i, command))
        for i, command in enumerate([alpha, beta] * 4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 8
    for index, text in results.items():
        expected = "aaaaa" if index % 2 == 0 else "bbbbb"
        other = "bbbbb" if index % 2 == 0 else "aaaaa"
        assert expected in text, f"capture {index} lost its own output"
        assert other not in text, f"capture {index} received another's output"


def test_a_capture_restores_the_thread_it_was_taken_on():
    import threading

    from cli.output import _out, capture, console

    seen = {}

    def worker():
        # A capture on another thread must not have changed this one's console.
        seen["during"] = _out()

    with capture(width=50):
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

    assert seen["during"] is console, "a capture leaked across threads"


def test_a_finished_capture_leaves_the_consoles_usable():
    """The first capture on a thread used to poison that thread for good.

    `capture` saved `getattr(_local, "console", None)` — None when nothing was
    set — and then assigned it back, leaving the attribute *present and None*.
    `getattr(_local, "console", console)` only falls through to its default when
    the attribute is absent, so every later lookup returned None and the next
    warning raised `'NoneType' object has no attribute 'print'`.

    It bit in the suite first, but the real target is the surface: thread-pool
    workers are reused, so the second dispatch on a recycled worker would have
    crashed on its first warning.
    """
    from cli.output import _err, _out, capture

    before = (_out(), _err())
    with capture(width=80, redirect=False):
        pass

    assert _out() is not None and _err() is not None
    assert (_out(), _err()) == before


def test_a_nested_capture_restores_the_outer_one():
    from cli.output import _out, capture

    with capture(width=80, redirect=False):
        outer = _out()
        with capture(width=80, redirect=False):
            assert _out() is not outer
        assert _out() is outer, "the inner capture stole the outer one's console"


# ============================================================================
# The view hint
# ============================================================================


def test_an_envelope_with_no_view_does_not_carry_the_key():
    """Omitted rather than null. An envelope from a command with no opinion
    about presentation stays byte-identical to one from before views existed,
    so nothing downstream has to learn that null means default."""
    assert "view" not in Result(command="x", data=[{"a": 1}]).to_dict()


def test_a_view_rides_beside_the_data_rather_than_filtering_it():
    """The property the whole feature rests on: `data` is complete whatever the
    view says, so `--json` and any future MCP consumer keep every field."""
    rows = [{"a": 1, "b": 2}]
    envelope = Result(command="x", data=rows, view={"columns": [{"key": "a"}], "hidden": ["b"]}).to_dict()
    assert envelope["data"] == rows
    assert envelope["view"]["hidden"] == ["b"]


def test_a_view_selects_and_orders_the_columns(capsys):
    render(
        Result(
            "x",
            data=[{"a": 1, "b": 2, "c": 3}],
            view={
                "columns": [
                    {"key": "c", "label": "C", "flex": 1, "min": 1, "max": 4},
                    {"key": "a", "label": "A", "flex": 1, "min": 1, "max": 4},
                ],
                "hidden": ["b"],
            },
        ),
        as_json=False,
    )
    body = _body(capsys.readouterr().out)
    assert body[0].split() == ["C", "A"]
    assert "2" not in body[1]


def test_a_view_summarises_a_nested_dict_into_one_cell(capsys):
    render(
        Result(
            "x",
            data=[{"checks": {"passed": 2, "failed": 0, "skipped": 7}}],
            view={
                "columns": [
                    {"key": "checks", "label": "CHECKS", "flex": 3, "min": 6, "max": 24, "summarise": True}
                ],
                "hidden": [],
            },
        ),
        as_json=False,
    )
    assert "passed=2 skipped=7" in _body(capsys.readouterr().out)[1]


def test_no_view_renders_exactly_as_it_always_did(capsys):
    """tb's own commands must be untouched by any of this — their fields were
    chosen by whoever wrote the command."""
    render(Result("x", data=[{"a": 1, "b": 2}]), as_json=False)
    assert _body(capsys.readouterr().out)[0].split() == ["A", "B"]


def test_a_column_is_never_squeezed_below_its_header(capsys):
    """Rich's ratio distribution builds its floor from `column.width or 1` and
    ignores `min_width`, so a proportional column can be crushed below its own
    label — `MERGE_STATE` as `ME…`, a column you cannot identify. The widths
    are resolved here instead, and this is what says so."""
    from cli.output import capture

    with capture(width=40, redirect=False) as captured:
        render(
            Result(
                "x",
                data=[{"merge_state": "CLEAN", "title": "x" * 200}],
                view={
                    "columns": [
                        {"key": "merge_state", "label": "MERGE_STATE", "flex": 1, "min": 11, "max": 11},
                        {"key": "title", "label": "TITLE", "flex": 5, "min": 5, "max": 200},
                    ],
                    "hidden": [],
                },
            ),
            as_json=False,
        )
    assert "MERGE_STATE" in captured.text


def test_a_view_outranks_the_status_list_convention(capsys):
    """`ok` in every row normally picks the glyph rendering. An explicit view
    looked at all the rows; the convention looked at one field."""
    render(
        Result(
            "x",
            data=[{"ok": True, "name": "one"}],
            view={"columns": [{"key": "name", "label": "NAME", "flex": 1, "min": 4, "max": 6}], "hidden": ["ok"]},
        ),
        as_json=False,
    )
    assert _body(capsys.readouterr().out)[0].split() == ["NAME"]


def test_a_detail_column_gets_its_own_line_under_the_record(capsys):
    """A ninety-character title does not fit in a share of the width, and
    Round 1's answer — move it to the end of the row — only changed where it
    got clipped. It gets a line."""
    render(
        Result(
            "x",
            data=[{"number": 946, "title": "a title far too long to sit inside a shared column"}],
            view={
                "columns": [{"key": "number", "label": "NUMBER", "flex": 1, "min": 6, "max": 6,
                             "align": "right"}],
                "details": [{"key": "title", "label": "TITLE", "flex": 1, "min": 5, "max": 60}],
                "hidden": [],
            },
        ),
        as_json=False,
    )
    body = _body(capsys.readouterr().out)
    assert body[0].split() == ["NUMBER"]
    assert "946" in body[1]
    # In full, not clipped — that is the entire point of the change.
    assert "a title far too long to sit inside a shared column" in body[2]


def test_a_shaped_table_has_a_rule_under_its_header(capsys):
    render(
        Result("x", data=[{"a": 1}],
               view={"columns": [{"key": "a", "label": "A", "flex": 1, "min": 1, "max": 1}],
                     "hidden": []}),
        as_json=False,
    )
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    assert any(set(l.strip()) == {"─"} for l in lines)


def test_a_shaped_table_leaves_no_trailing_whitespace(capsys):
    """Invisible until someone selects the line or diffs the output, and then
    it is noise."""
    render(
        Result("x", data=[{"a": 1, "b": "x"}],
               view={"columns": [
                   {"key": "a", "label": "A", "flex": 1, "min": 1, "max": 3},
                   {"key": "b", "label": "BBBB", "flex": 1, "min": 4, "max": 4}],
                   "hidden": []}),
        as_json=False,
    )
    for line in capsys.readouterr().out.splitlines():
        assert line == line.rstrip(), repr(line)


def test_a_scan_column_is_not_padded_out_to_fill_the_terminal(capsys):
    """Prose left the row, so no column left in it wants to be wider than its
    own content. Spreading the spare width across four scan columns is how
    NUMBER ends up eighteen characters wide with a three-digit number in it."""
    from cli.output import _resolve_widths

    columns = [
        {"key": "number", "label": "NUMBER", "flex": 1, "min": 6, "max": 6},
        {"key": "state", "label": "STATE", "flex": 1, "min": 5, "max": 7},
    ]
    assert _resolve_widths(columns, 200) == [6, 7]


def test_columns_still_shrink_when_they_genuinely_do_not_fit(capsys):
    from cli.output import _resolve_widths

    columns = [
        {"key": "a", "label": "A", "flex": 1, "min": 1, "max": 40},
        {"key": "b", "label": "B", "flex": 1, "min": 1, "max": 40},
    ]
    widths = _resolve_widths(columns, 20)
    assert sum(widths) <= 20


# ============================================================================
# Fitting columns to the width — [[table-views]] round 3
# ============================================================================

from cli.output import _render_value, fit_columns  # noqa: E402


def _cols(*mins):
    return [{"key": f"c{i}", "label": f"C{i}", "min": m} for i, m in enumerate(mins)]


def test_every_column_fits_when_there_is_room():
    """The operator's report: ten columns whose floors summed to 98 in a
    100-column terminal, eight drawn. Nothing may be dropped while it fits."""
    kept, over = fit_columns(_cols(6, 8, 11, 8, 6, 6, 6, 14, 6, 9), 100)
    assert len(kept) == 10 and over == []


def test_the_tail_that_does_not_fit_is_dropped_and_named():
    # 6 + 2 + 8 = 16 fits in 20; the third would need 16 + 2 + 11 = 29.
    kept, over = fit_columns(_cols(6, 8, 11), 20)
    assert [c["key"] for c in kept] == ["c0", "c1"]
    assert over == ["c2"]


def test_gutters_are_counted_against_the_width():
    """Two columns of six in a width of twelve do not fit — the gutter between
    them is real width and a fit that ignored it would overflow by exactly the
    amount it forgot."""
    kept, _ = fit_columns(_cols(6, 6), 12)
    assert len(kept) == 1
    kept, _ = fit_columns(_cols(6, 6), 14)
    assert len(kept) == 2


def test_the_first_column_is_kept_however_narrow_the_terminal():
    """A table with no columns is worse than one that overflows — and an
    overflow is at least something you can widen the terminal to read."""
    kept, over = fit_columns(_cols(40, 40), 10)
    assert [c["key"] for c in kept] == ["c0"] and over == ["c1"]


def test_a_column_that_did_not_fit_is_reported_in_the_drawing(capsys):
    """Not in the envelope: it is a fact about this drawing at this width, and
    widening the terminal changes it. `hidden` stays the run's business."""
    rows = [{"a": 1, "b": 2, "c": 3}]
    # Floors wide enough that the second cannot fit beside the first in any
    # console the suite runs under.
    view = {"columns": _cols(50, 50, 50), "details": [], "hidden": []}
    for column, key in zip(view["columns"], ("a", "b", "c")):
        column["key"] = key
    _render_value(rows, title=None, view=view)
    out = capsys.readouterr().out
    assert "2 columns did not fit: b, c" in out
    # The envelope's own vocabulary stays out of the drawing's report.
    assert "hidden" not in out


def test_the_header_states_what_the_payload_is_and_how_big(capsys):
    """The row count was always here; the column count was invisible, and it is
    what says whether `--from` and `--rows` did what the operator meant."""
    render(Result(command="data", data=[{"a": 1, "b": 2}, {"a": 3, "b": 4}]))
    out = capsys.readouterr().out
    assert "2 rows" in out and "2 columns" in out


def test_a_wrapped_payload_states_its_size_beside_the_key(capsys):
    """The nested table has no title of its own, so the size would otherwise
    have nowhere to appear on exactly the shape round 4 is about."""
    render(Result(command="data", data={"generated": "x", "jobs": [{"a": 1}]}))
    out = capsys.readouterr().out
    assert "jobs" in out
    assert "1 row · 1 column" in out
