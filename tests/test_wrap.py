"""tb wrap — the read-only door to another CLI.

The properties worth defending are the two boundaries it draws. It must not
become a second `tb run` by quietly carrying raw output, and it must not become
passthrough by pretending to understand a tool it did not parse.
"""

import json

from click.testing import CliRunner

from cli import cli


def invoke(args):
    result = CliRunner().invoke(cli, ["--json", "wrap", *args])
    return result, json.loads(result.stdout) if result.stdout.strip() else None


def test_a_json_list_becomes_the_data_outright():
    """A window renders `data` as a table. Nesting the rows under a key nobody
    chose would put the table one level down from where it is looked for."""
    _, envelope = invoke(["--", "printf", '[{"a": 1}, {"a": 2}]'])
    assert envelope["ok"] is True
    assert envelope["data"] == [{"a": 1}, {"a": 2}]


def test_a_json_object_is_kept_as_an_object():
    _, envelope = invoke(["--", "printf", '{"host": "workstation"}'])
    assert envelope["data"] == {"host": "workstation"}


def test_output_that_is_not_json_is_a_failed_contract_not_a_payload():
    """`tb run` is the one command allowed to put a subprocess's bytes into an
    envelope. This must not become the second, so a tool that printed prose
    gets an error naming the command that *will* show it."""
    # The probe computes its output rather than echoing a literal, because the
    # argv is reported back in `command` — and it should be. What must not
    # appear is anything the *subprocess* printed.
    # The probe transforms its output rather than echoing a literal, because the
    # argv is reported back in `command` — and it should be. What must not appear
    # is anything the *subprocess* printed. Note it must also not be a bare
    # number: `333` on its own is perfectly good JSON and would be accepted.
    result, envelope = invoke(["--", "sh", "-c", "printf abc | tr a-c x-z"])
    assert envelope["ok"] is False
    assert "xyz" not in json.dumps(envelope)
    assert "tb run" in envelope["data"]["error"]
    assert result.exit_code == 1


def test_a_failing_tool_reports_why_without_carrying_what_it_printed():
    _, envelope = invoke(["--", "sh", "-c", "printf abc | tr a-c x-z; echo boom >&2; exit 3"])
    assert envelope["ok"] is False
    assert envelope["data"]["exit_code"] == 3
    assert envelope["data"]["error"] == "boom"
    # stdout is dropped entirely on a failure — a tool that failed is a tool
    # whose output should not be believed, and a probe can print a token.
    assert "xyz" not in json.dumps(envelope)


def test_a_missing_command_fails_rather_than_raising():
    _, envelope = invoke(["--", "definitely-not-a-real-command-xyz"])
    assert envelope["ok"] is False
    assert "no such command" in envelope["data"]["error"]


def test_wrap_is_a_read_so_the_canvas_may_pin_it():
    """The whole reason it is a separate command from `run`. If this flips, the
    canvas stops offering a cadence on the only kind of window that should have
    one."""
    from cli.canvas.catalog import catalog

    entries = {entry["name"]: entry for entry in catalog()}
    assert entries["wrap"]["acts"] is False
    assert entries["run"]["acts"] is True


# ============================================================================
# Shaping
# ============================================================================

# Two rows with the shapes the heuristic exists for: a column that is null in
# both, and a uniform-length hex digest.
ROWS = (
    '[{"a":1,"gone":null,"sha":"cbb6c29e63a51108a663391b792217ee403780bf"},'
    '{"a":2,"gone":null,"sha":"9f2a1b7c4d8e6f0a3b5c7d9e1f2a4b6c8d0e2f4a"}]'
)


def test_a_view_hides_columns_while_the_data_keeps_them():
    """The property the feature rests on. A machine consumer reading `data`
    gets every field; only the table is shaped."""
    _, envelope = invoke(["--", "printf", ROWS])
    assert [c["key"] for c in envelope["view"]["columns"]] == ["a"]
    assert sorted(envelope["view"]["hidden"]) == ["gone", "sha"]
    # untouched
    assert envelope["data"][0]["sha"].startswith("cbb6c29")
    assert "gone" in envelope["data"][0]


def test_hidden_columns_are_named_rather_than_silently_dropped():
    """A table that hides a column without saying so reads as complete when it
    is not."""
    _, envelope = invoke(["--", "printf", ROWS])
    assert any("gone" in w and "sha" in w for w in envelope["warnings"])


def test_hiding_a_column_does_not_make_the_result_partial():
    """`partial` means a source failed. A shaped table is a complete answer."""
    result, envelope = invoke(["--", "printf", ROWS])
    assert envelope["partial"] is False
    assert result.exit_code == 0


def test_explicit_columns_override_the_heuristic():
    _, envelope = invoke(["--cols", "sha,a", "--", "printf", ROWS])
    assert [c["key"] for c in envelope["view"]["columns"]] == ["sha", "a"]


def test_dropping_a_column_yourself_is_not_warned_back_at_you():
    """Naming a column back at someone who just asked to lose it is noise."""
    _, envelope = invoke(["--drop", "a", "--", "printf", ROWS])
    assert "a" in envelope["view"]["hidden"]
    assert not any(w.startswith("1 column hidden: a") for w in envelope["warnings"])


def test_no_shape_leaves_the_envelope_as_it_was_before_views_existed():
    """The escape hatch, and what proves the key is genuinely optional."""
    _, envelope = invoke(["--no-shape", "--", "printf", ROWS])
    assert "view" not in envelope
    assert envelope["warnings"] == []


def test_a_json_object_is_not_a_table_and_gets_no_view():
    _, envelope = invoke(["--", "printf", '{"host": "workstation"}'])
    assert "view" not in envelope


def test_a_failed_tool_carries_no_view():
    """There are no rows to shape, and the error envelope must stay the shape
    every other failure has."""
    _, envelope = invoke(["--", "sh", "-c", "echo boom >&2; exit 3"])
    assert "view" not in envelope
