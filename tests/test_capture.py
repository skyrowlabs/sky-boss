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
# The formats file
# ============================================================================

from cli.capture import load_formats, parse_formats, resolve  # noqa: E402

GOOD = {
    "format": {
        "jam-status": {
            "description": "PR, state, title",
            "kind": "lines",
            "pattern": r"(?P<pr>#\d+)\s+(?P<state>\w+)",
        },
        "pr-summary": {
            "kind": "json",
            "jq": "{open: length}",
        },
    }
}


def test_a_declared_format_loads_with_its_kind_and_transform():
    formats, problems = parse_formats(GOOD)
    assert problems == []
    by_name = {f.name: f for f in formats}
    assert by_name["jam-status"].kind == "lines"
    assert by_name["pr-summary"].jq == "{open: length}"


def test_an_unknown_kind_fails_loudly_by_name_and_does_not_load():
    formats, problems = parse_formats({"format": {"x": {"kind": "csv"}}})
    assert formats == []
    assert "format 'x'" in problems[0] and "unknown kind" in problems[0]


def test_a_pattern_that_does_not_compile_is_refused():
    _, problems = parse_formats(
        {"format": {"x": {"kind": "lines", "pattern": "(?P<a"}}}
    )
    assert "does not compile" in problems[0]


def test_a_pattern_with_no_named_group_is_refused():
    """Fields come from named groups; a pattern without one would capture
    rows with no columns, which looks like success and is nothing."""
    _, problems = parse_formats({"format": {"x": {"kind": "lines", "pattern": r"\d+"}}})
    assert "no named group" in problems[0]


@pytest.mark.parametrize("name", ["json", "lines"])
def test_a_builtin_kind_always_wins_the_name(name):
    """A format named `json` would silently change what every `--from json`
    on the machine means — the same rule that kept a tool from shadowing
    `run` while tools lived on the root."""
    _, problems = parse_formats(
        {"format": {name: {"kind": "lines", "pattern": "(?P<a>.)"}}}
    )
    assert "builtin kind" in problems[0]


def test_a_pattern_on_a_json_format_is_refused_not_ignored():
    _, problems = parse_formats(
        {"format": {"x": {"kind": "json", "pattern": "(?P<a>.)", "jq": "."}}}
    )
    assert "means nothing" in problems[0]


def test_a_json_format_that_declares_nothing_is_refused():
    """`--from x` behaving byte-identically to `--from json` is a format
    that exists only to mislead a reader into looking for a difference."""
    _, problems = parse_formats({"format": {"x": {"kind": "json"}}})
    assert "declares nothing" in problems[0]


def test_one_bad_format_does_not_cost_the_operator_the_other_nine():
    raw = {
        "format": {
            "good": {"kind": "lines", "pattern": "(?P<a>.)"},
            "bad": {"kind": "csv"},
        }
    }
    formats, problems = parse_formats(raw)
    assert [f.name for f in formats] == ["good"] and len(problems) == 1


def test_an_absent_file_declares_nothing_and_says_nothing(tmp_path):
    assert load_formats(home=tmp_path / "nope") == ([], [])


def test_a_file_that_cannot_be_parsed_is_reported_rather_than_raised(tmp_path):
    (tmp_path / "formats.toml").write_text("not = = toml")
    formats, problems = load_formats(home=tmp_path)
    assert formats == [] and len(problems) == 1


# ------------------------------------------------------------------ resolve


def test_json_resolves_with_no_file_anywhere(tmp_path):
    fmt, problem = resolve("json", home=tmp_path / "nope")
    assert problem is None and fmt.kind == "json" and not fmt.jq


def test_bare_lines_is_refused_toward_a_declaration(tmp_path):
    fmt, problem = resolve("lines", home=tmp_path / "nope")
    assert fmt is None and "declare a format" in problem


def test_an_unknown_name_lists_what_would_have_worked(tmp_path):
    (tmp_path / "formats.toml").write_text(
        '[format.jam-status]\nkind = "lines"\npattern = "(?P<a>.)"\n'
    )
    fmt, problem = resolve("nope", home=tmp_path)
    assert fmt is None
    assert "json" in problem and "jam-status" in problem


def test_a_declared_and_refused_format_resolves_to_its_own_problem(tmp_path):
    """"No such format" about a format the operator wrote is the least
    helpful true sentence available — the resolution says why it was
    refused instead."""
    (tmp_path / "formats.toml").write_text('[format.mine]\nkind = "csv"\n')
    fmt, problem = resolve("mine", home=tmp_path)
    assert fmt is None and "unknown kind" in problem


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
