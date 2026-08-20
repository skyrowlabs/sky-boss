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
