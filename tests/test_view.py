"""Shaping foreign rows into a table.

The fixture below has the *shape* of `jam pr list --json` — fourteen fields, a
sha, a field that is null in every row, a nested dict of counters, and two
columns of prose — without its content. That is deliberate: real jam output
carries branch names and paths belonging to this operator, and nothing
operator-specific goes in a tracked file. The shape is what is under test.
"""

import copy

import pytest

from cli.view import (
    resolve,
    shape,
    summarise_mapping,
)


@pytest.fixture
def rows():
    return [
        {
            "number": 945,
            "title": "a subject line long enough to be prose rather than a label, easily past forty",
            "is_draft": True,
            "merge_state": "CLEAN",
            "head": "cbb6c29e63a51108a663391b792217ee403780bf",
            "head_ref": "topic/some-branch",
            "base_ref": "develop",
            "behind": 4,
            "labels": ["generated"],
            "marker": "absent",
            "marker_payload": None,
            "checks": {"passed": 2, "failed": 0, "skipped": 7, "pending": 0},
            "execution": "n/a",
            "next": "a second prose column, also comfortably past the forty character threshold",
        },
        {
            "number": 946,
            "title": "another subject line of the sort that would fold a terminal table apart",
            "is_draft": False,
            "merge_state": "DIRTY",
            "head": "9f2a1b7c4d8e6f0a3b5c7d9e1f2a4b6c8d0e2f4a",
            "head_ref": "topic/other-branch",
            "base_ref": "develop",
            "behind": 0,
            "labels": [],
            "marker": "present",
            "marker_payload": None,
            "checks": {"passed": 0, "failed": 3, "skipped": 1, "pending": 0},
            "execution": "n/a",
            "next": "a different second prose column, still well past the forty character mark",
        },
    ]


def keys(view):
    return [column["key"] for column in view["columns"]]


def column(view, key):
    return next(c for c in view["columns"] if c["key"] == key)


# --------------------------------------------------------------- the rules


def test_a_column_empty_in_every_row_is_hidden(rows):
    """`marker_payload` is null in both. A column that never once carried a
    value is pure width."""
    view = shape(rows)
    assert "marker_payload" not in keys(view)
    assert "marker_payload" in view["hidden"]


def test_zero_is_not_empty(rows):
    """A count of zero is an answer. `behind` is 0 in one row and must survive —
    "0 behind" is frequently the thing you opened the window to see."""
    view = shape(rows)
    assert "behind" in keys(view)


def test_an_opaque_sha_is_hidden_but_a_branch_name_survives(rows):
    """Matched on the values, never the name. `head` and `head_ref` differ by
    four characters and only one of them is a digest."""
    view = shape(rows)
    assert "head" in view["hidden"]
    assert "head_ref" in keys(view)


def test_hex_of_varying_length_is_not_an_opaque_id():
    """Uniform length is what separates a digest from a column that merely
    happens to be hex-ish. Without it, any column of hex-ish codes vanishes."""
    rows = [
        {"code": "abcdef0123456789abcdef0123456789"},
        {"code": "abcdef0123456789abcdef012345"},
    ]
    view = shape(rows)
    assert "code" in keys(view)


def test_short_hex_is_not_an_opaque_id():
    rows = [{"code": "deadbeef"}, {"code": "cafebabe"}]
    assert "code" in keys(shape(rows))


def test_a_nested_dict_is_summarised_into_one_column(rows):
    """One column, not six. Flattening to checks.passed, checks.failed, … turns
    one column into six and makes the crowding worse — the thing we are here to
    fix."""
    view = shape(rows)
    assert column(view, "checks")["summarise"] is True


def test_summarise_drops_zero_and_null_members():
    assert summarise_mapping({"passed": 2, "failed": 0, "skipped": 7}) == "passed=2 skipped=7"
    assert summarise_mapping({"a": None, "b": ""}) == "—"


def test_an_all_zero_mapping_renders_a_marker_not_an_empty_cell():
    """It would otherwise summarise to nothing at all, and an empty cell in the
    middle of a table looks like a bug rather than a fact."""
    assert summarise_mapping({"failed": 0, "pending": 0}) == "—"


def test_prose_leaves_the_row_and_becomes_a_detail(rows):
    """Round 1 tried to solve a 90-character title by *placing* it — push prose
    last, keep the first one put. Round 2 stops giving it a share of the width
    at all: a column you read gets its own line, and the columns you scan stay
    narrow and aligned above it."""
    view = shape(rows)
    assert keys(view) == [k for k in keys(view) if k not in ("title", "next")]
    assert [d["key"] for d in view["details"]] == ["title", "next"]


def test_a_short_string_column_stays_inline(rows):
    """The test is the value, not the name. A column called `title` holding
    one-word statuses is a column you scan."""
    view = shape([{"title": "CLEAN"}, {"title": "DIRTY"}])
    assert keys(view) == ["title"]
    assert view["details"] == []


def test_a_number_keeps_the_narrowest_weight(rows):
    view = shape(rows)
    assert column(view, "number")["flex"] == 1


def test_a_numeric_column_is_right_aligned(rows):
    view = shape(rows)
    assert column(view, "number")["align"] == "right"
    assert "align" not in column(view, "merge_state")


def test_prose_leaves_the_row_without_being_hidden(rows):
    """Details cost a line each rather than a share of the width. They are not
    columns and they are not hidden — they are the other half of the record."""
    view = shape(rows)
    assert [d["key"] for d in view["details"]] == ["title", "next"]
    assert "next" not in view["hidden"] and "title" not in view["hidden"]
    assert "next" not in keys(view) and "title" not in keys(view)


def test_every_column_worth_showing_survives_the_shaping(rows):
    """Round 3: there is no count here any more. `shape` says which columns
    are worth showing; how many *fit* is arithmetic against a width, and no
    width is known in this module."""
    view = shape(rows)
    assert keys(view) == [
        "number",
        "is_draft",
        "merge_state",
        "head_ref",
        "base_ref",
        "behind",
        "labels",
        "marker",
        "checks",
        "execution",
    ]


def test_hidden_means_hidden_by_rule_and_nothing_else(rows):
    """A property of the *run*, true at any width — which is what makes it
    correct in an envelope a machine consumer reads. A column that did not fit
    the window is the drawing's business, and each renderer reports its own."""
    view = shape(rows)
    assert set(view["hidden"]) == {"head", "marker_payload"}


def test_nothing_vanishes_without_being_accounted_for(rows):
    """The half of the old budget rule that survives: everything the input
    carried is a column, a detail, or named as hidden."""
    view = shape(rows)
    accounted = set(keys(view)) | {d["key"] for d in view["details"]} | set(view["hidden"])
    assert accounted == set(rows[0])


# ------------------------------------------------------------- the overrides


def test_explicit_columns_defeat_every_rule(rows):
    """The operator looked at the table and said what they wanted. A heuristic
    that argued with that would be a bug."""
    view = shape(rows, cols=["head", "marker_payload", "number"])
    assert keys(view) == ["head", "marker_payload", "number"]
    assert view["hidden"] == []


def test_explicit_columns_reach_inside_a_nested_dict(rows):
    view = shape(rows, cols=["checks.failed"])
    assert keys(view) == ["checks.failed"]
    assert column(view, "checks.failed")["align"] == "right"


def test_resolve_walks_a_dotted_path(rows):
    assert resolve(rows[0], "checks.failed") == 0
    assert resolve(rows[1], "checks.failed") == 3
    assert resolve(rows[0], "checks.nope") is None
    assert resolve(rows[0], "number.nope") is None


def test_drop_is_subtractive_and_keeps_the_heuristic(rows):
    view = shape(rows, drop=["title"])
    assert "title" not in keys(view)
    assert "title" in view["hidden"]
    # still shaped: the sha is still gone
    assert "head" in view["hidden"]


def test_no_shape_returns_nothing_to_say(rows):
    """None means render as you always did, and the envelope omits the key
    entirely — so an unshaped result stays byte-identical to one from before
    any of this existed."""
    assert shape(rows, enabled=False) is None


def test_explicit_columns_still_work_with_shaping_declined(rows):
    """--cols is an instruction, not a hint. Declining the heuristic must not
    also discard what the operator asked for by name."""
    view = shape(rows, cols=["number"], enabled=False)
    assert keys(view) == ["number"]


# ------------------------------------------------------------- what it is not


@pytest.mark.parametrize(
    "data",
    [None, "text", 3, {}, {"a": 1}, [], [1, 2, 3], [{"a": 1}, "not a row"]],
)
def test_anything_that_is_not_a_table_has_no_view(data):
    assert shape(data) is None


def test_shaping_never_touches_the_data(rows):
    """Stated twice in the doc on purpose. `--json` and any future MCP consumer
    keep every field, including the ones the table hides."""
    before = copy.deepcopy(rows)
    shape(rows)
    shape(rows, cols=["checks.failed"])
    shape(rows, drop=["title"])
    assert rows == before


def test_a_column_missing_from_some_rows_is_still_seen():
    """First-seen order across every row, not from the first row alone. For a
    table about what is wrong, a field only the broken row carries is the one
    thing that must not be lost."""
    rows = [{"a": 1}, {"a": 2, "error": "boom"}]
    assert "error" in keys(shape(rows))


def test_a_column_is_never_narrower_than_its_own_header(rows):
    """A truncated value is a readable table with a detail elided. A truncated
    header is a column you cannot identify at all — `ME…` could be merge_state
    or metadata, and no amount of squinting at the values will say which."""
    view = shape(rows)
    assert column(view, "merge_state")["min"] == len("MERGE_STATE")


def test_the_header_floor_is_capped(rows):
    """One pathologically long key must not squeeze every other column out."""
    view = shape([{"a_really_quite_long_field_name": 1, "b": 2}])
    assert column(view, "a_really_quite_long_field_name")["min"] == 14
