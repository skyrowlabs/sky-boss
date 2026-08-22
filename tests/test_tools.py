"""The toolbox — commands the operator saved.

The properties worth defending are the three that keep operator content from
becoming a way around tb's own rules: a tool expands to a tb command and not a
shell command, it inherits `acts` rather than declaring it, and it may only
carry a cadence if it reads. The fourth — a builtin always wins — retired into
structure in round 2: saved commands live behind the `tools` group, where
`[tool.run]` collides with nothing. See [[toolbox]].

Everything here drives `parse` directly. It is a pure function over a parsed
dict, which is what makes the interesting half testable without a file.
"""

import json
import pathlib
import tomllib

import pytest

from cli.tools import load, parse

# The live tree as the validator sees it: what is runnable and whether it acts.
COMMANDS = {"run": True, "data": False}

GOOD = {
    "tool": {
        "prs": {
            "description": "open PRs",
            "argv": ["data", "--", "somecli", "list", "--json"],
            "refresh": 30,
        }
    }
}


def one(raw):
    return parse(raw, COMMANDS)


def test_a_declared_tool_becomes_a_tool():
    tools, problems = one(GOOD)
    assert problems == []
    assert tools[0].name == "prs"
    assert tools[0].refresh == 30
    assert tools[0].description == "open PRs"


# ------------------------------------------------------- rule 1: a tb argv


def test_a_tool_cannot_name_a_bare_executable():
    """A tool that could name any executable would be a second `tb run` — one
    that skips the read/write distinction the whole design rests on."""
    tools, problems = one({"tool": {"x": {"argv": ["docker", "ps"]}}})
    assert tools == []
    assert "must start with a tb command" in problems[0]


def test_the_refusal_names_the_way_to_do_it():
    """The mistake this catches is someone writing a shell command. Refusing
    without saying which tb command would have run it wastes the trip."""
    _, problems = one({"tool": {"x": {"argv": ["docker", "ps"]}}})
    assert "data" in problems[0] and "run" in problems[0]


@pytest.mark.parametrize("argv", [[], "data", ["data", 3], None])
def test_argv_must_be_a_non_empty_list_of_strings(argv):
    _, problems = one({"tool": {"x": {"argv": argv}}})
    assert "non-empty list of strings" in problems[0]


def test_a_tool_still_saying_wrap_fails_loudly_by_name():
    """The migration path for a hard rename with no alias. A saved tool whose
    argv starts with the old word must not fall into the generic not-a-tb-command
    refusal — the operator wrote `wrap` when `wrap` was right, and the message
    owes them the new name. `tb tools` lists it; see [[refresh]]."""
    tools, problems = one({"tool": {"prs": {"argv": ["wrap", "--", "x", "--json"]}}})
    assert tools == []
    assert "renamed" in problems[0] and "'data'" in problems[0]


# ------------------------------------------------------- rule 2: acts inherits


def test_acts_is_inherited_from_the_expansion_not_declared():
    """The operator already asserted read-or-write by choosing `run` or `data`.
    Asking again in the TOML would invite them to contradict themselves, and a
    safety property must have exactly one source."""
    tools, _ = one({"tool": {"w": {"argv": ["data", "--", "x"]}}})
    assert tools[0].acts is False
    tools, _ = one({"tool": {"r": {"argv": ["run", "--", "x"]}}})
    assert tools[0].acts is True


def test_a_declared_acts_field_is_ignored_rather_than_believed():
    tools, _ = one({"tool": {"r": {"argv": ["run", "--", "x"], "acts": False}}})
    assert tools[0].acts is True


# ------------------------------------------- rule 3, retired into structure


@pytest.mark.parametrize("name", ["run", "data", "ui"])
def test_a_builtin_name_on_a_tool_is_no_longer_a_collision(name):
    """Round 2's reversal, on the record: a saved `run` lives at
    `tb tools run` and collides with nothing, so the validation rule became
    structure. The registration half below proves `tb run` still resolves to
    the builtin."""
    tools, problems = one({"tool": {name: {"argv": ["data", "--", "x"]}}})
    assert problems == []
    assert tools[0].name == name


@pytest.mark.parametrize("name", ["--evil", "has space", "Caps", "a/b", "a.b", ""])
def test_a_name_that_is_not_a_command_word_is_refused(name):
    _, problems = one({"tool": {name: {"argv": ["data", "--", "x"]}}})
    assert "lowercase letters" in problems[0]


# ------------------------------------------------- rule 4: cadence needs a read


def test_a_tool_that_acts_may_not_carry_a_cadence():
    """The same rule the canvas enforces by hiding the pin control. Re-running
    a read is a refresh; re-running a write is a scheduler nobody asked for."""
    tools, problems = one({"tool": {"r": {"argv": ["run", "--", "x"], "refresh": 30}}})
    assert tools == []
    assert "not allowed on a tool that acts" in problems[0]


def test_a_tool_that_acts_is_fine_without_one():
    tools, problems = one({"tool": {"r": {"argv": ["run", "--", "x"]}}})
    assert problems == [] and tools[0].refresh == 0


def test_a_cadence_outside_the_surfaces_list_is_refused():
    """The surface cycles the interval through a fixed list. A window starting
    on a value outside it jumps to 0 on the first click rather than to the next
    cadence up."""
    _, problems = one({"tool": {"x": {"argv": ["data", "--", "y"], "refresh": 45}}})
    assert "refresh must be one of" in problems[0]


def test_a_boolean_is_not_a_cadence():
    """`True` is an int in Python and would otherwise pass as one second."""
    _, problems = one({"tool": {"x": {"argv": ["data", "--", "y"], "refresh": True}}})
    assert "integer number of seconds" in problems[0]


def test_a_tool_still_saying_every_fails_loudly_by_name():
    """The field-side half of the rename migration. `every` must not be
    silently ignored as an unknown field — the tool would load and open at
    cadence 0, which is the 'wrong but looks right' failure."""
    tools, problems = one({"tool": {"x": {"argv": ["data", "--", "y"], "every": 30}}})
    assert tools == []
    assert "renamed" in problems[0] and "refresh" in problems[0]


# ------------------------------------------------------------ degrading well


def test_one_bad_tool_does_not_cost_the_operator_the_good_ones():
    """The failure this prevents is a typo in the ninth entry silently emptying
    the toolbox."""
    tools, problems = one(
        {
            "tool": {
                "good": {"argv": ["data", "--", "x"]},
                "bad": {"argv": ["docker", "ps"]},
                "alsogood": {"argv": ["run", "--", "y"]},
            }
        }
    )
    assert sorted(t.name for t in tools) == ["alsogood", "good"]
    assert len(problems) == 1


def test_an_absent_home_declares_nothing_and_says_nothing(tmp_path):
    """A fresh clone has no tools. Saying so on every invocation is noise."""
    assert load(COMMANDS, home=tmp_path / "nope") == ([], [])


def test_a_file_that_cannot_be_parsed_is_reported_rather_than_raised(tmp_path):
    """It exists, so the operator expects it to work — but one broken file must
    not stop tb running at all."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "tools.toml").write_text("this is not = = toml")
    tools, problems = load(COMMANDS, home=tmp_path)
    assert tools == []
    assert len(problems) == 1


def test_a_tilde_in_an_argv_is_expanded():
    """The whole point is that these are the operator's own paths."""
    tools, _ = one({"tool": {"x": {"argv": ["data", "--cwd", "~/somewhere", "--", "y"]}}})
    assert tools[0].argv[2].startswith("/")
    assert "~" not in tools[0].argv[2]


def test_a_tilde_inside_a_value_is_left_alone():
    tools, _ = one({"tool": {"x": {"argv": ["data", "--", "y", "a~b"]}}})
    assert tools[0].argv[-1] == "a~b"


# ============================================================================
# Registration — the half that makes the palette work for free
# ============================================================================

from cli import cli  # noqa: E402
from cli.canvas.catalog import walk  # noqa: E402
from cli.tools import register, tools as tools_group  # noqa: E402


@pytest.fixture
def saved(tmp_path):
    """Declare tools in an isolated home and put them on the real tree.

    The real tree rather than a synthetic one on purpose: the claim under test
    is that a tool becomes an ordinary command, and a stand-in group would let
    that claim be true of the stand-in only.
    """
    def declare(toml_text):
        (tmp_path / "tools.toml").write_text(toml_text)
        return register(cli, home=tmp_path)

    yield declare

    for name in [
        n for n, c in list(tools_group.commands.items()) if getattr(c, "tb_saved", False)
    ]:
        del tools_group.commands[name]


def test_a_tool_is_an_ordinary_command_behind_the_tools_group(saved):
    """Round 2's address: behind the group, never on the root — the
    builtin/operator line shows in `tb --help` because the tree carries it."""
    saved('[tool.prs]\nargv = ["data", "--", "printf", "[]"]\n')
    assert "prs" in tools_group.commands
    assert "prs" not in cli.commands


def test_the_palette_finds_a_tool_without_the_catalog_knowing_about_tools(saved):
    """The point of registering rather than listing. `cli/canvas/catalog.py`
    walks the live tree, so a tool appears in the palette with its real summary
    and its real options and nothing there had to learn what a tool is. The
    leaf's full name is the dotted address, spaced."""
    saved('[tool.prs]\ndescription = "open PRs"\nargv = ["data", "--", "printf", "[]"]\n')
    entry = {e["name"]: e for e in walk(cli)}["tools prs"]
    assert entry["summary"] == "open PRs"
    assert entry["saved"] is True
    assert entry["argv"] == ["tools", "prs"]


def test_a_tool_wrapping_run_is_marked_as_acting_in_the_catalog(saved):
    """The safety property. `acts` is otherwise derived from the command path,
    and the path of `tb tools deploy-thing` says nothing about the `run` inside
    it — so the canvas would offer a refresh cadence on a write, which is the
    one thing the read/write split exists to prevent."""
    saved('[tool.deploy]\nargv = ["run", "--", "true"]\n')
    entry = {e["name"]: e for e in walk(cli)}["tools deploy"]
    assert entry["acts"] is True


def test_a_tool_wrapping_data_stays_pinnable(saved):
    saved('[tool.prs]\nargv = ["data", "--", "printf", "[]"]\n')
    assert {e["name"]: e for e in walk(cli)}["tools prs"]["acts"] is False


def test_a_saved_run_no_longer_collides_with_the_builtin(saved):
    """The round-2 reversal, proven structurally: `tb run` still resolves to
    the one door that writes, and the saved `run` lives at `tb tools run`."""
    before = cli.commands["run"]
    problems = saved('[tool.run]\nargv = ["data", "--", "printf", "[]"]\n')
    assert problems == []
    assert cli.commands["run"] is before
    assert "run" in tools_group.commands


def test_the_bare_group_still_lists(saved):
    """`tb tools` with no subcommand is the listing it always was — one door
    for "what did I declare", not a group that demands a subcommand. Formats
    ride in the same envelope since [[capture]] landed."""
    from click.testing import CliRunner

    saved('[tool.prs]\nargv = ["data", "--", "printf", "[]"]\n')
    result = CliRunner().invoke(cli, ["--json", "tools"])
    envelope = json.loads(result.stdout)
    assert envelope["command"] == "tools"
    assert [row["name"] for row in envelope["data"]["tools"]] == ["prs"]
    assert envelope["data"]["formats"] == []


def test_the_listing_reports_formats_beside_tools(saved, tmp_path):
    """One door: declared formats appear with their kind and description, and
    a format's load failure lands in the same degrade list a tool's does."""
    from click.testing import CliRunner

    import cli.capture as capture_mod

    (tmp_path / "formats.toml").write_text(
        '[format.jam-status]\ndescription = "PR, state, title"\nkind = "lines"\n'
        'pattern = \'(?P<pr>#\\d+) (?P<state>\\w+)\'\n'
        '[format.broken]\nkind = "nope"\n'
    )
    saved('[tool.prs]\nargv = ["data", "--", "printf", "[]"]\n')
    import unittest.mock

    with unittest.mock.patch.object(capture_mod, "TB_HOME", tmp_path):
        result = CliRunner().invoke(cli, ["--json", "tools"])
    envelope = json.loads(result.stdout)
    assert envelope["data"]["formats"] == [
        {"name": "jam-status", "kind": "lines", "description": "PR, state, title"}
    ]
    assert envelope["partial"] is True
    assert any("unknown kind" in w for w in envelope["warnings"])


def test_running_a_tool_dispatches_to_its_expansion(saved):
    from click.testing import CliRunner

    saved('[tool.prs]\nargv = ["data", "--", "printf", "[{\\"a\\": 1}]"]\n')
    result = CliRunner().invoke(cli, ["--json", "tools", "prs"])
    envelope = json.loads(result.stdout)
    assert envelope["data"] == [{"a": 1}]


def test_the_envelope_says_the_dotted_path(saved):
    """Round 1 ruled the bare name, because `data` was an implementation
    detail the operator did not type. `tools.` is something they *do* type
    now, and the dotted path is the standing convention — the round-1
    argument is superseded exactly that far and no further."""
    from click.testing import CliRunner

    saved('[tool.prs]\nargv = ["data", "--", "printf", "[{\\"a\\": 1}]"]\n')
    result = CliRunner().invoke(cli, ["--json", "tools", "prs"])
    assert json.loads(result.stdout)["command"] == "tools.prs"


def test_a_tool_takes_no_arguments(saved):
    """A tool that took arguments would be a shell function, and this is not a
    shell. Click refuses it as a usage error, which is exit 2 — not 3, which
    would say the run was degraded."""
    from click.testing import CliRunner

    saved('[tool.prs]\nargv = ["data", "--", "printf", "[]"]\n')
    result = CliRunner().invoke(cli, ["tools", "prs", "945"])
    assert result.exit_code == 2


# ============================================================================
# -t — the short spelling
# ============================================================================

from cli import expand_t  # noqa: E402


def test_dash_t_stands_where_a_command_word_could():
    assert expand_t(["-t", "prs"]) == ["tools", "prs"]
    assert expand_t(["-t"]) == ["tools"]
    assert expand_t(["--json", "-t", "prs"]) == ["--json", "tools", "prs"]


def test_a_dash_t_belonging_to_someone_else_is_never_touched():
    """The rewrite stops at the first command word or `--` — past that point
    every token is somebody's argv, not tb's."""
    assert expand_t(["read", "--", "ls", "-t"]) == ["read", "--", "ls", "-t"]
    assert expand_t(["run", "-t"]) == ["run", "-t"]
    assert expand_t(["tools", "-t"]) == ["tools", "-t"]


def test_the_rewrite_happens_once():
    assert expand_t(["-t", "-t"]) == ["tools", "-t"]


def test_dash_t_runs_a_saved_command_end_to_end(saved):
    from click.testing import CliRunner

    saved('[tool.prs]\nargv = ["data", "--", "printf", "[{\\"a\\": 1}]"]\n')
    result = CliRunner().invoke(cli, ["--json", "-t", "prs"])
    envelope = json.loads(result.stdout)
    assert envelope["command"] == "tools.prs"
    assert envelope["data"] == [{"a": 1}]


def test_bare_dash_t_is_the_listing(saved):
    from click.testing import CliRunner

    saved('[tool.prs]\nargv = ["data", "--", "printf", "[]"]\n')
    result = CliRunner().invoke(cli, ["--json", "-t"])
    assert json.loads(result.stdout)["command"] == "tools"


def test_the_prefix_form_is_a_usage_error(saved):
    """`tb -t --refresh 30 prs` was considered and rejected: it would teach
    the group a forwarded option that belongs to the leaf. It falls out as an
    ordinary usage error rather than needing a rule of its own."""
    from click.testing import CliRunner

    saved('[tool.prs]\nargv = ["data", "--", "printf", "[]"]\n')
    result = CliRunner().invoke(cli, ["-t", "--refresh", "30", "prs"])
    assert result.exit_code == 2


# ============================================================================
# The shipped example
# ============================================================================

EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / "tools.example.toml"


def test_the_example_is_shipped():
    assert EXAMPLE.exists()


def test_the_example_names_no_operator_path():
    """Operator content lives outside the repo and there is no fallback path
    into it. The last time that boundary was soft, a machine record carried a
    tailnet address into every commit and the tool could not be published
    without publishing the operator.

    Asserted against the *argvs* rather than the file text. The prose is
    allowed to say `~/.config/tb/tools.toml`, because naming the XDG default is
    documentation and not a path anything runs; what must never be tracked is a
    path some real machine actually has.
    """
    text = EXAMPLE.read_text()
    assert "/home/" not in text
    assert "skyrow" not in text.lower()

    with EXAMPLE.open("rb") as handle:
        tools, _ = parse(tomllib.load(handle), COMMANDS)
    for tool in tools:
        for part in tool.argv:
            assert not part.startswith(str(pathlib.Path.home())), (tool.name, part)


def test_the_example_is_a_toolbox_that_would_actually_load():
    """An example that does not parse teaches the wrong thing twice: once when
    it is copied, and again when the operator concludes the format is broken."""
    with EXAMPLE.open("rb") as handle:
        raw = tomllib.load(handle)
    tools, problems = parse(raw, COMMANDS)
    assert problems == []
    assert {t.name for t in tools} == {"prs", "containers", "disk"}


def test_the_example_demonstrates_both_sides_of_the_read_write_split():
    """Someone copying this should see a tool that acts and a tool that does
    not, because the distinction is the thing most likely to be missed."""
    with EXAMPLE.open("rb") as handle:
        tools, _ = parse(tomllib.load(handle), COMMANDS)
    by_name = {t.name: t for t in tools}
    assert by_name["disk"].acts is True and by_name["disk"].refresh == 0
    assert by_name["prs"].acts is False and by_name["prs"].refresh == 30
