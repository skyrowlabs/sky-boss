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
    """
    return [l.rstrip() for l in out.splitlines() if l.strip() and not l.lstrip().startswith("●")]


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
    width the consumer asked for. Invisible in a wide terminal and clipping in
    a narrow pane, since the TUI's transcript does not wrap.
    """
    import re

    from cli.tui.dispatch import dispatch

    for width in (46, 60, 120):
        text = re.sub(r"\x1b\[[0-9;]*m", "", dispatch("--help", width=width).text)
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
    TUI's queue guaranteed it. Watches deliberately broke that guarantee, and
    swapping module globals then meant two captures silently stole each other's
    output: of four concurrent dispatches, two came back empty.

    Uses a toy tree rather than real commands so the suite keeps shelling out
    to nothing.
    """
    import threading

    import rich_click as click

    from cli.output import Result, capture, emit
    from cli.tui.dispatch import dispatch

    @click.group()
    def root():
        pass

    @root.command()
    @emit
    def alpha():
        return Result(command="alpha", data={"who": "aaaaa"})

    @root.command()
    @emit
    def beta():
        return Result(command="beta", data={"who": "bbbbb"})

    results: dict[int, object] = {}

    def worker(index, line):
        results[index] = dispatch(line, root=root, redirect=False)

    threads = [
        threading.Thread(target=worker, args=(i, line))
        for i, line in enumerate(["alpha", "beta"] * 4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    for index, result in results.items():
        expected = "aaaaa" if index % 2 == 0 else "bbbbb"
        other = "bbbbb" if index % 2 == 0 else "aaaaa"
        assert expected in result.text, f"dispatch {index} lost its own output"
        assert other not in result.text, f"dispatch {index} received another's output"


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
