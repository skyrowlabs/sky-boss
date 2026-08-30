"""The roll-call — many projects, one answer.

Every test here runs against a redirected `SB_HOME` (conftest sets it before
anything imports `cli`). That matters more than usual: a project is a source sky.boss
will *run*, so a suite reading the real home would be shelling out to whatever
the operator happens to have declared.
"""

import json

import pytest
from click.testing import CliRunner

from cli import cli
from cli.rollcall import load, parse, read


def write(home, text):
    home.mkdir(parents=True, exist_ok=True)
    (home / "projects.toml").write_text(text)


# ── The registry ────────────────────────────────────────────────────────────
#
# One bad entry must not cost the operator the other five, so the malformed
# cases come first — they are what the loader exists to survive.


def test_a_malformed_project_is_named_and_skipped(tmp_path):
    write(tmp_path, """
[project.good]
argv = ["echo", "{}"]

[project.bad]
description = "declares no source at all"
""")
    projects, problems = load(tmp_path)
    assert [p.name for p in projects] == ["good"]
    assert len(problems) == 1 and "bad" in problems[0]


def test_declaring_both_a_command_and_a_file_is_refused(tmp_path):
    """Two different claims about where this project's truth lives. Picking one
    would be sky.boss guessing which the operator meant."""
    write(tmp_path, """
[project.both]
argv = ["echo"]
path = "/tmp/x.json"
""")
    projects, problems = load(tmp_path)
    assert projects == []
    assert "argv and path" in problems[0]


def test_an_unparseable_file_is_reported_rather_than_raised(tmp_path):
    write(tmp_path, "this is not toml {{{")
    projects, problems = load(tmp_path)
    assert projects == []
    assert problems and "projects.toml" in problems[0]


def test_an_absent_file_declares_nothing_and_says_nothing(tmp_path):
    """A fresh clone federates over no projects. Warning about it every
    invocation would be noise, so absence is not a problem to report."""
    projects, problems = load(tmp_path / "nowhere")
    assert projects == []
    assert problems == []


def test_a_declared_project_keeps_its_reading_options(tmp_path):
    write(tmp_path, """
[project.jam]
argv = ["jam", "report", "status", "--json"]
cwd = "~/src/jam.sense"
rows = "jobs"
cols = "job,result"
""")
    (project,) = load(tmp_path)[0]
    assert project.argv[0] == "jam"
    assert project.rows == "jobs"
    assert project.cols == "job,result"
    assert project.from_ == "json"


def test_a_typo_in_the_table_name_is_named_rather_than_silent(tmp_path):
    """The whole file used to vanish for one letter. `[projct.…]` parsed clean,
    declared nothing, and left roll-call printing the sentence a fresh clone
    gets — so the operator's evidence for "I declared this" was identical to the
    evidence for "I never did"."""
    write(tmp_path, """
[projct.jam-sense]
argv = ["jam", "report", "status", "--json"]
""")
    projects, problems = load(tmp_path)
    assert projects == []
    assert problems == ["unknown table 'projct' — ignored"]


def test_an_unknown_table_does_not_cost_the_projects_beside_it(tmp_path):
    write(tmp_path, """
[state]
root = "~/somewhere"

[project.good]
argv = ["echo", "{}"]
""")
    projects, problems = load(tmp_path)
    assert [p.name for p in projects] == ["good"]
    assert problems == ["unknown table 'state' — ignored"]


def test_a_mistyped_key_is_named_rather_than_falling_back_to_a_default(tmp_path):
    """`timout = 5` silently became the 60-second default, which is the worst
    shape a typo can take: the declaration is gone and the value it was
    overriding looks deliberate."""
    write(tmp_path, """
[project.jam-sense]
argv = ["echo", "{}"]
col = "job,result"
timout = 5
""")
    projects, problems = load(tmp_path)
    assert projects[0].timeout == 60 and projects[0].cols == ""
    assert problems == [
        "project 'jam-sense': unknown key 'col' — ignored",
        "project 'jam-sense': unknown key 'timout' — ignored",
    ]


def test_a_project_that_cannot_load_is_reported_once(tmp_path):
    """Not twice. A project with no source is already named for that, and
    adding an unknown-key line beside it would bury the reason it failed."""
    write(tmp_path, """
[project.bad]
describtion = "no source, and a typo besides"
""")
    _, problems = load(tmp_path)
    assert len(problems) == 1 and "declares neither" in problems[0]


def test_the_known_keys_cover_every_field_a_project_can_carry():
    """The set is spelled out rather than derived, so this is what stops a new
    field becoming a declaration sky.boss silently ignores. Three fields are not
    keys: `name` is the table's own, `from_` clears the keyword, and `shade` is
    *assigned* rather than declared — it is sky.boss's own answer about which
    ramp step a project draws in, so accepting it as a key would let the file
    argue with the assignment. See [[schedule]] round 6."""
    from dataclasses import fields

    from cli.rollcall import PROJECT_KEYS, Project

    derived = {"name", "shade"}
    expected = {
        "from" if f.name == "from_" else f.name
        for f in fields(Project)
        if f.name not in derived
    }
    assert expected == set(PROJECT_KEYS)
    assert "shade" not in PROJECT_KEYS


def test_parse_reads_no_file():
    """Pure, like every other deciding half here."""
    projects, problems = parse({"project": {"a": {"path": "/tmp/a.json"}}})
    assert projects[0].path == "/tmp/a.json"
    assert problems == []


# ── One project, read ───────────────────────────────────────────────────────


from cli.rollcall import Project, ask  # noqa: E402


def test_a_command_source_is_read_by_sb_datas_own_path():
    project = Project(name="p", argv=["printf", '[{"a": 1}]'])
    result = ask(project)
    assert result.ok is True
    assert result.data == [{"a": 1}]


def test_a_file_source_is_read_by_the_same_path(tmp_path):
    """The contract accepts a file because most projects have no CLI. It must
    not become a second opinion about what `--from` means."""
    payload = tmp_path / "status.json"
    payload.write_text('{"generated": "x", "jobs": [{"job": "a", "result": "ok"}]}')
    result = ask(Project(name="p", path=str(payload), rows="jobs"))
    assert result.ok is True
    assert result.view["rows"] == "jobs"
    assert result.data["generated"] == "x"


def test_a_file_that_is_not_there_yet_reports_rather_than_raises(tmp_path):
    """A project that publishes a file and has not written one is the normal
    early state, not an exception."""
    result = ask(Project(name="p", path=str(tmp_path / "missing.json")))
    assert result.ok is False
    assert "No such file" in result.data["error"]


def test_a_project_that_prints_something_other_than_json_fails_its_contract():
    result = ask(Project(name="p", argv=["printf", "hello"]))
    assert result.ok is False
    assert "not JSON" in result.data["error"]


def test_a_projects_declared_columns_reach_the_view():
    project = Project(name="p", argv=["printf", '[{"a": 1, "b": 2}]'], cols="b")
    assert [c["key"] for c in ask(project).view["columns"]] == ["b"]


# ── The fold ────────────────────────────────────────────────────────────────
#
# The partial path first. It is the one that matters — a roll-call goes blank
# exactly when something is wrong, if it goes blank at all — and the one nobody
# exercises by hand, because by hand every project happens to be up.


def invoke(args=()):
    result = CliRunner().invoke(cli, ["--json", "roll-call", *args])
    return result, json.loads(result.stdout) if result.stdout.strip() else None


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setattr("cli.rollcall.SB_HOME", h)
    return h


def test_one_project_down_does_not_blank_the_others(home):
    write(home, """
[project.up]
argv = ["printf", "[{\\"a\\": 1}]"]

[project.down]
argv = ["false"]
""")
    result, envelope = invoke()
    assert envelope["data"]["up"] == [{"a": 1}]
    assert "error" in envelope["data"]["down"]
    assert envelope["partial"] is True
    assert any("down" in w for w in envelope["warnings"])
    assert result.exit_code == 3


def test_a_project_that_could_not_answer_is_named_never_omitted(home):
    """Silence looks exactly like health, which is the one thing a roll-call
    must never let it look like."""
    write(home, '[project.gone]\nargv = ["no-such-binary-anywhere"]\n')
    _, envelope = invoke()
    assert "gone" in envelope["data"]
    assert envelope["partial"] is True


def test_every_project_answering_is_not_partial(home):
    write(home, '[project.a]\nargv = ["printf", "[{\\"x\\": 1}]"]\n')
    result, envelope = invoke()
    assert envelope["partial"] is False
    assert result.exit_code == 0


def test_each_block_carries_its_own_view(home):
    """Six independent payloads cannot share one column list — picking one
    project's would draw the other five wrong."""
    write(home, """
[project.a]
argv = ["printf", "[{\\"x\\": 1}]"]

[project.b]
argv = ["printf", "[{\\"y\\": 2}]"]
""")
    _, envelope = invoke()
    blocks = envelope["view"]["blocks"]
    assert [c["key"] for c in blocks["a"]["columns"]] == ["x"]
    assert [c["key"] for c in blocks["b"]["columns"]] == ["y"]


def test_nothing_declared_is_not_a_failure(home):
    _, envelope = invoke()
    assert envelope["ok"] is True
    assert envelope["data"] == {}
    assert any("no projects declared" in w for w in envelope["warnings"])


def test_a_malformed_entry_warns_and_the_rest_still_answer(home):
    write(home, """
[project.good]
argv = ["printf", "[{\\"a\\": 1}]"]

[project.broken]
description = "no source"
""")
    _, envelope = invoke()
    assert envelope["data"]["good"] == [{"a": 1}]
    assert any("broken" in w for w in envelope["warnings"])


def test_only_narrows_the_roll_call(home):
    write(home, """
[project.a]
argv = ["printf", "[{\\"x\\": 1}]"]

[project.b]
argv = ["printf", "[{\\"y\\": 2}]"]
""")
    _, envelope = invoke(["--only", "b"])
    assert list(envelope["data"]) == ["b"]


def test_only_naming_nothing_is_a_usage_error_not_an_empty_roll_call(home):
    write(home, '[project.a]\nargv = ["printf", "[]"]\n')
    result, _ = invoke(["--only", "nope"])
    assert result.exit_code == 2


# ── A cadence ───────────────────────────────────────────────────────────────


def test_a_roll_call_is_a_read_so_the_canvas_may_pin_it():
    """Asking six projects how they are runs each project's own status command
    and changes nothing. If this flips, the canvas stops offering a cadence on
    the window that most wants one — and starts offering it on a write."""
    from cli.canvas.catalog import catalog

    entries = {entry["name"]: entry for entry in catalog()}
    assert entries["roll-call"]["acts"] is False


def test_the_roll_call_is_in_the_palette_because_the_tree_is():
    """Nothing keeps a command table. If roll-call were registered anywhere but
    the live Click tree it would be offerable and absent, which is worse than
    not being offered."""
    from cli.canvas.catalog import catalog

    assert "roll-call" in {entry["name"] for entry in catalog()}


# ============================================================================
# The state root as a top-level key — [[state-root]] round 1
# ============================================================================


def test_state_root_is_a_declaration_not_an_unknown_table():
    projects, problems = parse({"state_root": "~/logs", "project": {}})
    assert problems == []
    assert projects == []


def test_an_unknown_top_level_key_is_named_as_a_key_not_a_table():
    """It used to say `unknown table 'staet_root'`, which sends the operator
    looking for a `[staet_root]` heading they never wrote."""
    _, problems = parse({"staet_root": "~/logs"})
    assert problems == ["unknown key 'staet_root' — ignored"]


def test_an_unknown_table_is_still_called_a_table():
    _, problems = parse({"projct": {"jam-sense": {}}})
    assert problems == ["unknown table 'projct' — ignored"]
