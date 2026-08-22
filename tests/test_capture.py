"""Capture — the deciding half, pure. See [[capture]].

The properties worth defending: a matched line is a row and its named groups
are the fields, a number-shaped value becomes a number and nothing else does,
an unmatched line is counted and sampled but never silently dropped, and
nothing matching at all is a verdict rather than an empty table. No
subprocess and no file I/O anywhere in this half.
"""

import pytest

from cli.capture import Captured, Format, capture, unmatched_warning

STATUS = Format(
    name="jam-status",
    kind="lines",
    pattern=r"(?P<pr>#\d+)\s+(?P<state>\w+)\s+(?P<title>.+)",
)


def test_a_matched_line_is_a_row_and_its_groups_are_the_fields():
    got = capture("#945 open Fix the flaky retry\n", STATUS)
    assert got.rows == [{"pr": "#945", "state": "open", "title": "Fix the flaky retry"}]
    assert got.total == 1 and got.unmatched == 0


def test_fields_arrive_in_group_order():
    got = capture("#1 open x\n", STATUS)
    assert list(got.rows[0]) == ["pr", "state", "title"]


def test_search_semantics_so_a_pattern_need_not_anchor():
    """The pattern matches where it matches; a prefix the operator did not
    care to name does not cost them the row."""
    fmt = Format(name="x", kind="lines", pattern=r"(?P<num>\d+) wide")
    assert capture("column is 42 wide today\n", fmt).rows == [{"num": 42}]


# ------------------------------------------------------------- number shape


@pytest.mark.parametrize(
    ("printed", "becomes"),
    [("42", 42), ("-3", -3), ("+7", 7), ("3.5", 3.5), ("-0.25", -0.25)],
)
def test_a_value_shaped_like_a_number_becomes_one(printed, becomes):
    fmt = Format(name="n", kind="lines", pattern=r"(?P<value>\S+)")
    value = capture(printed, fmt).rows[0]["value"]
    assert value == becomes and type(value) is type(becomes)


@pytest.mark.parametrize("printed", ["v1.2.3", "3.5.7", "1e6", "0x10", "12s", "-", ""])
def test_everything_else_stays_the_string_the_tool_printed(printed):
    """Shape, not judgment — a version string is not a float and a duration
    is not an int, whatever they start with."""
    fmt = Format(name="n", kind="lines", pattern=r"(?P<value>\S*)")
    assert capture(printed or "x", fmt).rows[0]["value"] == (printed or "x")


def test_an_optional_group_that_did_not_participate_is_none():
    fmt = Format(name="x", kind="lines", pattern=r"(?P<a>\w+)(?: (?P<b>\w+))?")
    assert capture("solo", fmt).rows == [{"a": "solo", "b": None}]


# ----------------------------------------------------------- the honest miss


def test_blank_lines_are_ignored_not_counted():
    got = capture("#1 open x\n\n   \n#2 open y\n", STATUS)
    assert got.total == 2 and got.unmatched == 0


def test_unmatched_lines_are_counted_and_the_first_is_sampled():
    text = "#1 open x\ntotal: 2 items\nnoise\n"
    got = capture(text, STATUS)
    assert got.unmatched == 2
    assert got.sample == "total: 2 items"
    warning = unmatched_warning(got, "jam-status")
    assert "2 of 3 lines did not match jam-status" in warning
    assert "total: 2 items" in warning


def test_a_clean_capture_warns_about_nothing():
    assert unmatched_warning(capture("#1 open x\n", STATUS), "jam-status") is None


def test_nothing_matching_is_a_verdict_not_an_empty_table():
    got = capture("完全 different output\nthan expected\n", STATUS)
    assert got.matched_nothing is True
    # The verdict outranks the warning: the caller fails the contract and the
    # per-line count would be noise beside it.
    assert unmatched_warning(got, "jam-status") is None


def test_zero_lines_in_is_not_a_capture_miss():
    """The tool genuinely printed nothing. Distinguishable from a miss, and
    distinguished — 'reports clear' must never collapse into 'cannot see'."""
    got = capture("", STATUS)
    assert got.matched_nothing is False
    assert got.rows == [] and got.total == 0


def test_a_pathological_line_returns_in_bounded_time():
    """200 KB with no spaces through a pattern with no catastrophic
    backtracking. The declared-pattern design leaves a catastrophic pattern
    as the operator's own foot, per the spec — this pins the shipped rules
    only."""
    got = capture("x" * 200_000, STATUS)
    assert got.unmatched == 1


def test_captured_is_a_value_the_caller_cannot_quietly_mutate():
    with pytest.raises(Exception):
        Captured([], 0, 0, None).total = 5


# ============================================================================
# The transform stage
# ============================================================================

import shutil  # noqa: E402

from cli.capture import transform  # noqa: E402

needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="no jq on PATH")


@needs_jq
def test_the_transform_is_the_operators_own_jq():
    data, error = transform([{"a": 1}, {"a": 2}], "{count: length}", "summary")
    assert error is None
    assert data == {"count": 2}


@needs_jq
def test_a_stream_of_values_becomes_a_list():
    """The `.[]` idiom plainly means the elements, so a multi-value output is
    a list rather than an error about not being one document."""
    data, error = transform([1, 2, 3], ".[]", "each")
    assert error is None
    assert data == [1, 2, 3]


@needs_jq
def test_no_output_at_all_is_null_honestly():
    data, error = transform([1], "empty", "nothing")
    assert data is None and error is None


@needs_jq
def test_a_failing_program_is_a_failed_contract_carrying_jqs_own_stderr():
    data, error = transform({"a": 1}, ".b | keys", "broken")
    assert data is None
    assert error.startswith("format 'broken':")
    # jq's own words, not a paraphrase — the operator debugs the program with
    # the message jq gave.
    assert "null" in error


def test_an_absent_jq_degrades_loudly_at_use_naming_the_format(monkeypatch, tmp_path):
    """The environment is injected the same way the operator's is — through
    child_env — so the test proves the degrade without uninstalling anything."""
    import cli.capture as capture_mod

    monkeypatch.setattr(capture_mod, "child_env", lambda: {"PATH": str(tmp_path)})
    data, error = transform({}, ".", "pr-summary")
    assert data is None
    assert "jq is not on PATH" in error and "pr-summary" in error
