"""Tests for the TUI's dispatch layer.

The whole risk of the surface lives here, and none of it needs a terminal.
What would break silently: an exit code that stops surviving the trip, a usage
error that escapes and kills the app, help text that leaks past the capture and
corrupts the screen, and a capture that fails to restore the globals — which
would leave the surface silent for the rest of its life.

The fake tree exists so the exit-code tests stay fast. Dispatching real `check`
here would walk ~/src and shell out to half a dozen CLIs.
"""

import json

import pytest
import rich_click as click

from cli import output
from cli.output import EXIT_ERROR, EXIT_OK, EXIT_PARTIAL, Result, capture, emit
from cli.tui.dispatch import EXIT_USAGE, dispatch, split


@click.group()
@click.pass_context
def fake(ctx):
    ctx.ensure_object(dict)


@fake.command()
@emit
def okay():
    return Result(data={"answer": 42})


@fake.command()
@emit
def degraded():
    result = Result(data={"answer": 42})
    result.degrade("one source went away")
    return result


@fake.command()
@emit
def broken():
    return Result(ok=False, data={"error": "could not"})


@fake.command()
@click.option("--count", type=int)
@emit
def counted(count):
    return Result(data={"count": count})


# ---------------------------------------------------------------- exit codes


@pytest.mark.parametrize(
    "line,expected",
    [
        ("okay", EXIT_OK),
        ("degraded", EXIT_PARTIAL),
        ("broken", EXIT_ERROR),
    ],
)
def test_exit_codes_survive_the_trip(line, expected):
    # standalone_mode=False must return the code rather than exit the process.
    # If this regresses, every caller reads success.
    assert dispatch(line, root=fake).exit_code == expected


def test_ok_is_exactly_zero_not_merely_truthy():
    # partial is a successful run of a degraded thing; it is not ok.
    assert dispatch("okay", root=fake).ok
    assert not dispatch("degraded", root=fake).ok


# ---------------------------------------------------------------- bad input


def test_unknown_command_is_text_not_an_exception():
    result = dispatch("nope", root=fake)
    assert result.exit_code == EXIT_USAGE
    assert "nope" in result.text


def test_unknown_option_is_text_not_an_exception():
    result = dispatch("okay --bogus", root=fake)
    assert result.exit_code == EXIT_USAGE
    assert "--bogus" in result.text


def test_bad_option_value_is_text_not_an_exception():
    result = dispatch("counted --count banana", root=fake)
    assert result.exit_code == EXIT_USAGE
    assert result.text


def test_usage_errors_point_at_the_right_help():
    assert "Try 'tb counted --help'." in dispatch("counted --count banana", root=fake).text


def test_unbalanced_quote_is_a_usage_error():
    # shlex rejects this before Click ever sees it.
    result = dispatch("okay 'unclosed", root=fake)
    assert result.exit_code == EXIT_USAGE
    assert result.text


def test_a_crashing_command_does_not_escape():
    @fake.command()
    def explodes():
        raise RuntimeError("boom")

    result = dispatch("explodes", root=fake)
    assert result.exit_code == EXIT_ERROR
    assert "boom" in result.text


# ---------------------------------------------------------------- the line


def test_leading_tb_is_optional():
    assert dispatch("tb okay", root=fake).text == dispatch("okay", root=fake).text


def test_blank_line_is_a_noop():
    result = dispatch("   ", root=fake)
    assert result.exit_code == EXIT_OK
    assert result.text == ""


def test_split_only_strips_tb_in_first_position():
    assert split("run tb") == ["run", "tb"]


# ---------------------------------------------------------------- capture


def test_help_does_not_leak_to_the_real_stdout(capsys):
    # rich-click renders --help through its own console, so the console swap
    # alone does not catch it. Without the stdout redirect this escapes and
    # corrupts whatever the surface has drawn.
    result = dispatch("--help", root=fake)
    assert capsys.readouterr().out == ""
    assert "Usage:" in result.text


def test_json_stays_parseable_through_the_capture():
    # The real tree, because --json is a root-group flag. `auto list` reads a
    # registry and touches nothing.
    result = dispatch("--json auto list")
    payload = json.loads(result.text)
    assert payload["command"] == "auto.list"
    assert payload["ok"] is True


# The capture swaps a thread-local rather than the module globals, so that two
# concurrent dispatches — a watch and whatever is being typed — cannot post
# into each other's buffer. What these assert is unchanged; where it is stored
# is not. See test_output.test_concurrent_captures_do_not_post_into_each_other.


def test_capture_restores_the_consoles():
    before = (output._out(), output._err())
    with capture():
        assert output._out() is not before[0]
    assert (output._out(), output._err()) == before


def test_capture_restores_the_consoles_after_an_exception():
    # The failure this prevents: one bad command leaves the console swapped and
    # the surface prints into a dead buffer forever after.
    before = (output._out(), output._err())
    with pytest.raises(RuntimeError):
        with capture():
            raise RuntimeError("boom")
    assert (output._out(), output._err()) == before


def test_both_streams_land_in_one_transcript_in_order():
    # The partial banner goes to stderr and the data to stdout; they must stay
    # attached, or a reader cannot tell which result was degraded.
    text = dispatch("degraded", root=fake).text
    assert text.index("partial") < text.index("42")
