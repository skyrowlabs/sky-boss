"""`sb data` — the read-only door to another CLI.

The properties worth defending are the two boundaries it draws. It must not
become a second `sb run` by quietly carrying raw output, and it must not become
passthrough by pretending to understand a tool it did not parse.
"""

import json

from click.testing import CliRunner

from cli import cli


def invoke(args):
    result = CliRunner().invoke(cli, ["--json", "data", *args])
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
    """`sb run` is the one command allowed to put a subprocess's bytes into an
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
    assert "sb run" in envelope["data"]["error"]
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


def test_data_is_a_read_so_the_canvas_may_pin_it():
    """The whole reason it is a separate command from `run`. If this flips, the
    canvas stops offering a cadence on the only kind of window that should have
    one."""
    from cli.canvas.catalog import catalog

    entries = {entry["name"]: entry for entry in catalog()}
    assert entries["data"]["acts"] is False
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


# ============================================================================
# --from
# ============================================================================


def test_from_json_is_the_default_made_explicit():
    """`--from json` and no flag are the same invocation. JSON stops being an
    invisible assumption; the next format arrives as a value, not a redesign."""
    _, envelope = invoke(["--from", "json", "--", "printf", '[{"a": 1}]'])
    assert envelope["ok"] is True
    assert envelope["data"] == [{"a": 1}]


def test_an_unknown_format_is_a_usage_error_not_a_guess():
    """Exit 2 — Click's refusal — rather than a parser silently guessing. A
    speculative csv parser is how 'silently wrong' gets back in."""
    result, _ = invoke(["--from", "csv", "--", "printf", "a,b"])
    assert result.exit_code == 2


def test_the_refusal_lists_what_would_have_worked():
    result, _ = invoke(["--from", "csv", "--", "printf", "a,b"])
    assert "json" in result.output


# ============================================================================
# Declared formats, end to end — see [[capture]]
# ============================================================================

import shutil  # noqa: E402
import unittest.mock  # noqa: E402

import pytest  # noqa: E402

import cli.capture as capture_mod  # noqa: E402


def declared(tmp_path, toml_text, args):
    (tmp_path / "formats.toml").write_text(toml_text)
    with unittest.mock.patch.object(capture_mod, "SB_HOME", tmp_path):
        return invoke(args)


LINES = (
    '[format.jam-status]\nkind = "lines"\n'
    "pattern = '(?P<pr>#\\d+)\\s+(?P<state>\\w+)\\s+(?P<title>.+)'\n"
)


def test_a_lines_format_turns_prose_into_rows(tmp_path):
    _, envelope = declared(
        tmp_path,
        LINES,
        ["--from", "jam-status", "--", "printf", "#945 open Fix retry\\n#946 draft Add tags\\n"],
    )
    assert envelope["ok"] is True
    assert envelope["data"] == [
        {"pr": "#945", "state": "open", "title": "Fix retry"},
        {"pr": "#946", "state": "draft", "title": "Add tags"},
    ]


def test_rows_flow_into_the_standard_view_shaping(tmp_path):
    """No capture-specific carve-outs: one shaping contract, not two."""
    _, envelope = declared(
        tmp_path, LINES, ["--from", "jam-status", "--", "printf", "#1 open x\\n"]
    )
    assert "view" in envelope


def test_a_capture_that_misses_is_visible(tmp_path):
    _, envelope = declared(
        tmp_path,
        LINES,
        ["--from", "jam-status", "--", "printf", "#1 open x\\ntotal: 1\\n"],
    )
    assert envelope["ok"] is True
    assert envelope["data"] == [{"pr": "#1", "state": "open", "title": "x"}]
    assert any("1 of 2 lines did not match jam-status" in w for w in envelope["warnings"])


def test_nothing_matching_is_a_failed_contract_naming_both_recourses(tmp_path):
    # The probe transforms its output rather than echoing a literal, because
    # the argv is reported back in `command` — and it should be. What must
    # not appear is anything the *subprocess* printed.
    result, envelope = declared(
        tmp_path,
        LINES,
        ["--from", "jam-status", "--", "sh", "-c", "echo prose only | tr a-z A-Z"],
    )
    assert result.exit_code == 1
    assert envelope["ok"] is False
    error = envelope["data"]["error"]
    assert "fix the format" in error and "sb read" in error
    # Unmatched lines do not reach `data` — rows or a failed contract.
    assert "PROSE ONLY" not in json.dumps(envelope["data"])


def test_a_broken_format_used_by_name_fails_the_run_with_its_own_reason(tmp_path):
    result, envelope = declared(
        tmp_path,
        '[format.mine]\nkind = "csv"\n',
        ["--from", "mine", "--", "printf", "x"],
    )
    assert result.exit_code == 2
    assert "unknown kind" in result.output


needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="no jq on PATH")


@needs_jq
def test_a_jq_transform_is_the_pipelines_middle_stage(tmp_path):
    _, envelope = declared(
        tmp_path,
        '[format.summary]\nkind = "json"\njq = "{open: length}"\n',
        ["--from", "summary", "--", "printf", '[{"a": 1}, {"a": 2}]'],
    )
    assert envelope["ok"] is True
    assert envelope["data"] == {"open": 2}


@needs_jq
def test_a_jq_transform_runs_on_captured_rows_exactly_as_on_json(tmp_path):
    """After the parse stage everything is data — the transform does not
    care which kind produced it."""
    _, envelope = declared(
        tmp_path,
        LINES.replace(
            "\\s+(?P<title>.+)'\n", "\\s+(?P<title>.+)'\njq = '[.[] | .state]'\n"
        ),
        ["--from", "jam-status", "--", "printf", "#1 open x\\n#2 draft y\\n"],
    )
    assert envelope["ok"] is True
    assert envelope["data"] == ["open", "draft"]


@needs_jq
def test_a_failing_jq_program_fails_the_contract_with_jqs_words(tmp_path):
    result, envelope = declared(
        tmp_path,
        '[format.summary]\nkind = "json"\njq = ".nope | keys"\n',
        ["--from", "summary", "--", "printf", "[1]"],
    )
    assert result.exit_code == 1
    assert envelope["ok"] is False
    assert "summary" in envelope["data"]["error"]


# ============================================================================
# The warning narrows — [[table-views]] round 3
# ============================================================================


def test_the_warning_names_rule_hidden_columns_only():
    """A column hidden because it is an opaque sha is true at any width and
    belongs in the envelope. A column that did not fit the terminal is the
    drawing's business and must not degrade a machine consumer's result."""
    sha = "cbb6c29e63a51108a663391b792217ee403780bf"
    rows = json.dumps([{"n": 1, "head": sha, "empty": None, "a": "x", "b": "y"}])
    _, envelope = invoke(["--", "printf", "%s", rows])
    assert set(envelope["view"]["hidden"]) == {"head", "empty"}
    assert len(envelope["warnings"]) == 1
    assert "head" in envelope["warnings"][0] and "empty" in envelope["warnings"][0]


def test_a_wide_table_does_not_warn_merely_for_being_wide():
    """The operator's report, as an envelope property: a window with room was
    being told it was missing something."""
    rows = json.dumps([{f"c{i}": f"v{i}" for i in range(12)}])
    _, envelope = invoke(["--", "printf", "%s", rows])
    assert envelope["view"]["hidden"] == []
    assert envelope["warnings"] == []
    assert len(envelope["view"]["columns"]) == 12


def test_data_never_tells_a_tool_how_wide_the_terminal_is(monkeypatch):
    import subprocess
    """`data` parses what the tool prints. A width is an instruction to lay
    out for a display, and a tool that wrapped its JSON to 80 columns would
    hand back a corrupted document rather than a narrower one. The display
    paths — run, read, follow — pass it; this one must not.
    See [[subprocess-env]] round 2."""
    seen = {}
    real = subprocess.run

    def spy(*args, **kwargs):
        seen.update(kwargs.get("env") or {})
        return real(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    invoke(["--", "printf", '{"a": 1}'])
    assert "COLUMNS" not in seen


# ── Round 4: a payload is not always a list ─────────────────────────────────


WRAPPED = '{"generated": "2026-08-23T20:02:53+00:00", "jobs": [{"job": "sentinel", "result": "red"}]}'
AMBIGUOUS = '{"jobs": [{"a": 1}], "errors": [{"b": 2}]}'


def test_a_wrapped_payload_is_shaped_where_a_bare_list_would_be():
    """The defect, at the level it was found: every status endpoint wraps its
    rows, because status is about a moment and a bare array cannot say which."""
    _, envelope = invoke(["--cols", "job,result", "--", "printf", WRAPPED])
    assert [c["key"] for c in envelope["view"]["columns"]] == ["job", "result"]
    assert envelope["view"]["rows"] == "jobs"


def test_the_wrapper_stays_in_the_data():
    """A view describes `data`; it never edits it. The generated-at stamp is
    still there for `jq` and for any MCP consumer."""
    _, envelope = invoke(["--cols", "job", "--", "printf", WRAPPED])
    assert envelope["data"]["generated"] == "2026-08-23T20:02:53+00:00"


def test_a_bare_list_names_no_rows_key():
    """Omitted rather than null, so an envelope from a bare array stays
    byte-identical to one from before this round."""
    _, envelope = invoke(["--cols", "a", "--", "printf", '[{"a": 1}]'])
    assert "rows" not in envelope["view"]


def test_two_candidate_row_lists_are_reported_not_broken_by_a_tiebreak():
    _, envelope = invoke(["--cols", "a", "--", "printf", AMBIGUOUS])
    assert "view" not in envelope
    assert any("candidate row lists" in w for w in envelope["warnings"])


def test_a_shaping_flag_that_could_not_be_applied_is_never_silent():
    """The defect's real lesson, and it outlives the specific fix: `--cols` was
    discarded without a word whenever the payload wrapped its rows."""
    _, envelope = invoke(["--cols", "a", "--", "printf", '{"generated": "x"}'])
    assert any("--cols not applied" in w for w in envelope["warnings"])


def test_no_flag_no_warning():
    """A payload that is simply not a table is not a complaint — sky.boss has always
    rendered a mapping as a mapping."""
    _, envelope = invoke(["--", "printf", '{"generated": "x"}'])
    assert envelope.get("warnings", []) == []


def test_rows_names_where_the_rows_are():
    _, envelope = invoke(["--rows", "jobs", "--cols", "job", "--", "printf", WRAPPED])
    assert envelope["view"]["rows"] == "jobs"


def test_rows_disambiguates_what_sb_refuses_to_guess():
    _, envelope = invoke(["--rows", "errors", "--cols", "b", "--", "printf", AMBIGUOUS])
    assert envelope["view"]["rows"] == "errors"


def test_a_named_path_that_misses_fails_rather_than_falling_back():
    _, envelope = invoke(["--rows", "nope", "--cols", "job", "--", "printf", WRAPPED])
    assert envelope["ok"] is False
    assert "nope" in envelope["data"]["error"]


def test_a_shaping_warning_does_not_make_the_result_partial():
    """Same rule hidden columns already follow — a presentation complaint is
    not a failure to read the tool."""
    result, envelope = invoke(["--cols", "a", "--", "printf", '{"generated": "x"}'])
    assert envelope["partial"] is False
    assert result.exit_code == 0


def test_a_column_no_row_carries_is_named_in_a_warning():
    _, envelope = invoke(["--cols", "a,nope", "--", "printf", '[{"a": 1}]'])
    assert any("no row has this field: nope" in w for w in envelope["warnings"])


def test_the_warning_says_the_column_was_still_drawn():
    """Because it was — and because "nothing matched" is often the answer."""
    _, envelope = invoke(["--cols", "a,nope", "--", "printf", '[{"a": 1}]'])
    assert any("drawn empty" in w for w in envelope["warnings"])
    assert [c["key"] for c in envelope["view"]["columns"]] == ["a", "nope"]


def test_several_missing_columns_read_as_plural():
    _, envelope = invoke(["--cols", "a,x,y", "--", "printf", '[{"a": 1}]'])
    assert any("these fields: x, y" in w for w in envelope["warnings"])


def test_a_present_but_empty_column_is_not_warned_about():
    _, envelope = invoke(["--cols", "a,b", "--", "printf", '[{"a": 1, "b": null}]'])
    assert envelope.get("warnings", []) == []


def test_a_missing_column_does_not_make_the_result_partial():
    result, envelope = invoke(["--cols", "nope", "--", "printf", '[{"a": 1}]'])
    assert envelope["partial"] is False
    assert result.exit_code == 0


# ============================================================================
# The path form — [[jsonl-reads]] round 1
# ============================================================================


def test_the_file_form_needs_a_path_not_a_bare_word():
    """Nearly `follow`'s rule, and the difference is the point. Follow calls a
    bare unknown word a file because a log legitimately does not exist yet;
    here there is nothing to wait for, so it stays a command and the error says
    `no such command` rather than `no such file`."""
    from cli.data import is_file_form

    assert is_file_form(("ledger/runs.jsonl",))
    assert is_file_form(("/var/log/syslog",))
    assert not is_file_form(("definitely-not-a-real-command-xyz",))
    assert not is_file_form(("sh",))  # an executable wins a bare word
    assert not is_file_form(("printf", "hi"))  # more than one word is an argv


def test_a_bare_unknown_word_is_still_a_missing_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, envelope = invoke(["--", "definitely-not-a-real-command-xyz"])
    assert "no such command" in envelope["data"]["error"]


def test_an_existing_file_in_the_cwd_is_the_file_form(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs.jsonl").write_text('{"job": "release"}\n')
    _, envelope = invoke(["--from", "jsonl", "runs.jsonl"])
    assert envelope["data"] == [{"job": "release"}]


def test_a_jsonl_file_reads_as_rows(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text('{"job": "a", "rc": 0}\n\n{"job": "b", "rc": 1}\n')
    _, envelope = invoke(["--from", "jsonl", str(path)])
    assert envelope["ok"] is True
    assert envelope["data"] == [{"job": "a", "rc": 0}, {"job": "b", "rc": 1}]


def test_a_malformed_line_is_counted_and_sampled_never_dropped(tmp_path):
    """The whole reason this shares `Captured`. A silently dropped ledger row
    reads as *that job never ran*, which is the question the ledger exists to
    settle."""
    path = tmp_path / "runs.jsonl"
    path.write_text('{"job": "a"}\ntruncated{\n{"job": "b"}\n')
    _, envelope = invoke(["--from", "jsonl", str(path)])
    assert envelope["ok"] is True
    assert envelope["data"] == [{"job": "a"}, {"job": "b"}]
    assert any("1 of 3 lines not a JSON object" in w for w in envelope["warnings"])
    assert any("truncated{" in w for w in envelope["warnings"])


def test_a_line_that_is_valid_json_but_not_an_object_is_malformed(tmp_path):
    """`42` is valid JSON and is not a record. Letting one through would put a
    non-row into a list the view layer may assume is rows."""
    path = tmp_path / "x.jsonl"
    path.write_text('{"a": 1}\n42\n')
    _, envelope = invoke(["--from", "jsonl", str(path)])
    assert envelope["data"] == [{"a": 1}]
    assert any("1 of 2 lines not a JSON object" in w for w in envelope["warnings"])


def test_a_file_with_no_parseable_line_fails_rather_than_returning_empty(tmp_path):
    """`capture`'s rule. An empty table would read as *the ledger records
    nothing*, the exact lie this command exists never to tell."""
    path = tmp_path / "x.jsonl"
    path.write_text("nope\nalso nope\n")
    _, envelope = invoke(["--from", "jsonl", str(path)])
    assert envelope["ok"] is False
    assert "no line is a JSON object" in envelope["data"]["error"]


def test_an_empty_file_is_not_a_failure(tmp_path):
    """The line `capture` already draws and this round nearly erased. Lines
    that arrived and all failed is a broken contract; *no lines* is a ledger
    with nothing in it yet, and calling that a failure would make a fresh
    project unreadable until its first run."""
    path = tmp_path / "x.jsonl"
    path.write_text("")
    _, envelope = invoke(["--from", "jsonl", str(path)])
    assert envelope["ok"] is True
    assert envelope["data"] == []


def test_the_not_json_error_names_from_jsonl_when_that_is_the_fix(tmp_path):
    """A diagnostic on a failure, not inference — sky.boss still refuses to choose
    `jsonl` for you. But `not JSON` alone about a 1,000-line ledger leaves the
    operator to work out something the failure already knows."""
    path = tmp_path / "runs.jsonl"
    path.write_text('{"a": 1}\n{"a": 2}\n{"a": 3}\n')
    _, envelope = invoke([str(path)])
    assert envelope["ok"] is False
    assert "--from jsonl" in envelope["data"]["error"]


def test_a_genuinely_broken_file_does_not_get_the_jsonl_hint(tmp_path):
    path = tmp_path / "x.txt"
    path.write_text("this is\nnot json at all\n")
    _, envelope = invoke([str(path)])
    assert "--from jsonl" not in envelope["data"]["error"]
    assert "not JSON" in envelope["data"]["error"]


def test_a_missing_file_says_so(tmp_path):
    _, envelope = invoke(["--from", "jsonl", str(tmp_path / "gone.jsonl")])
    assert envelope["ok"] is False
    assert "no such file" in envelope["data"]["error"]


def test_a_directory_says_so_rather_than_permission_denied(tmp_path):
    """The failure this round removes. A path used to reach `subprocess.run`
    and come back `Permission denied` for something the operator can read."""
    _, envelope = invoke(["--from", "jsonl", str(tmp_path)])
    assert envelope["ok"] is False
    assert "is a directory" in envelope["data"]["error"]


def test_cols_and_the_view_work_unchanged_against_a_file(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text('{"job": "a", "rc": 0, "note": "x"}\n{"job": "b", "rc": 1, "note": "y"}\n')
    _, envelope = invoke(["--from", "jsonl", "--cols", "job,rc", str(path)])
    assert [c["key"] for c in envelope["view"]["columns"]] == ["job", "rc"]


def test_a_torn_tail_is_reported_on_every_read_not_once_per_file(tmp_path):
    """Per-read reporting, pinned deliberately rather than inherited from
    process lifetime.

    jam.sense's reader dedupes its equivalent warning on a module-level set
    keyed by path, so one process warns once per file and goes quiet about
    every later tear. That is right for a short-lived job and wrong for a
    resident consumer: `sb data --refresh` re-enters `_once` every tick, and a
    warning that fired only on tick 1 would tell a watcher the ledger had gone
    clean. sky.boss is on the right side of this today because nothing in the
    read path holds state — which is exactly the property that quietly changes
    when someone makes a reader long-lived for performance.

    Both invocations run in one process, so a `_WARNED` set of our own would
    survive between them and fail this. See [[jsonl-reads]] round 4."""
    path = tmp_path / "runs.jsonl"
    path.write_text('{"job": "a"}\n{"job": "b", "sta')  # cut mid-record

    for read in (1, 2, 3):
        _, envelope = invoke(["--from", "jsonl", str(path)])
        assert envelope["data"] == [{"job": "a"}], f"read {read}"
        assert any("1 of 2 lines not a JSON object" in w for w in envelope["warnings"]), (
            f"read {read} went quiet about the torn tail"
        )
