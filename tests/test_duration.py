"""One duration parser, shared by `--due` and `--delay`.

Two flags in two docs taking `15m` is exactly the shape that ends with `2h`
meaning two hours in one place and two minutes in another. See [[delay]] and
[[file-follow]] round 2.
"""

import pytest

from cli.helpers import parse_duration


@pytest.mark.parametrize(
    "text,seconds",
    [
        ("90s", 90),
        ("15m", 900),
        ("2h", 7200),
        ("3d", 259200),
        ("900", 900),
        ("15M", 900),
        ("  15m  ", 900),
    ],
)
def test_a_duration_is_seconds(text, seconds):
    assert parse_duration(text) == seconds


def test_a_bare_number_is_seconds_not_minutes():
    """Spelled out because it is the one that would be silently guessed, and
    guessed differently by two people."""
    assert parse_duration("900") == parse_duration("15m")


@pytest.mark.parametrize("text", ["", "m", "15 m", "1.5h", "-5m", "fifteen", "15x", "15mm", None])
def test_anything_else_is_refused_loudly(text):
    with pytest.raises(ValueError):
        parse_duration(text)


def test_zero_is_refused():
    """A watcher an hour in is the worst possible moment to discover its
    interval never meant anything."""
    with pytest.raises(ValueError):
        parse_duration("0m")


def test_the_refusal_says_what_would_have_worked():
    with pytest.raises(ValueError, match="15m"):
        parse_duration("fifteen minutes")
