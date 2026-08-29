"""The tools — commands the operator saved.

The properties worth defending are the three that keep operator content from
becoming a way around sky.boss's own rules: a tool expands to a sky.boss command and not a
shell command, it inherits `acts` rather than declaring it, and it may only
carry a cadence if it reads. The fourth — a builtin always wins — retired into
structure in round 2: saved commands live behind the `tools` group, where
`[tool.run]` collides with nothing. See [[tools]].

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


# ------------------------------------------------------- rule 1: a sky.boss argv


def test_a_tool_cannot_name_a_bare_executable():
    """A tool that could name any executable would be a second `sb run` — one
    that skips the read/write distinction the whole design rests on."""
    tools, problems = one({"tool": {"x": {"argv": ["docker", "ps"]}}})
    assert tools == []
    assert "must start with a sb command" in problems[0]


def test_the_refusal_names_the_way_to_do_it():
    """The mistake this catches is someone writing a shell command. Refusing
    without saying which sky.boss command would have run it wastes the trip."""
    _, problems = one({"tool": {"x": {"argv": ["docker", "ps"]}}})
    assert "data" in problems[0] and "run" in problems[0]


@pytest.mark.parametrize("argv", [[], "data", ["data", 3], None])
def test_argv_must_be_a_non_empty_list_of_strings(argv):
    _, problems = one({"tool": {"x": {"argv": argv}}})
    assert "non-empty list of strings" in problems[0]


def test_a_tool_still_saying_wrap_fails_loudly_by_name():
    """The migration path for a hard rename with no alias. A saved tool whose
    argv starts with the old word must not fall into the generic not-a-sb-command
    refusal — the operator wrote `wrap` when `wrap` was right, and the message
    owes them the new name. `sb tools` lists it; see [[refresh]]."""
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
    `sb tools run` and collides with nothing, so the validation rule became
    structure. The registration half below proves `sb run` still resolves to
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
    the tools."""
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
    not stop sky.boss running at all."""
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


# --------------------------------------------------------------- groups
# A group is a declared label the surfaces sort under. It is not inferred from
# the name and not derived from what the tool wraps — the workbench's rule that
# the contract is asserted, never inferred, governs here too. See [[tools]]
# round 5.


def test_a_group_is_carried_through():
    tools, problems = one(
        {"tool": {"prs": {"argv": ["data", "--", "x"], "group": "jam"}}}
    )
    assert problems == []
    assert tools[0].group == "jam"


def test_a_tool_with_no_group_is_ungrouped():
    tools, _ = one(GOOD)
    assert tools[0].group == ""


def test_an_empty_group_is_ungrouped_rather_than_refused():
    # A bench field left blank is the common case; refusing it would be a modal
    # for nothing.
    tools, problems = one({"tool": {"prs": {"argv": ["data", "--", "x"], "group": ""}}})
    assert problems == []
    assert tools[0].group == ""


@pytest.mark.parametrize("group", ["Jam", "jam sense", "-jam", "jam.sense", "jam/x"])
def test_a_group_that_is_not_a_key_is_refused(group):
    # A group is keyed on, not just captioned: `jam ` and `jam` would be two
    # groups that look like one.
    tools, problems = one(
        {"tool": {"prs": {"argv": ["data", "--", "x"], "group": group}}}
    )
    assert tools == []
    assert "group" in problems[0]


def test_a_non_string_group_is_refused():
    tools, problems = one({"tool": {"prs": {"argv": ["data", "--", "x"], "group": 3}}})
    assert tools == []
    assert "group must be a string" in problems[0]


def test_a_bad_group_costs_only_its_own_tool():
    tools, problems = one(
        {
            "tool": {
                "bad": {"argv": ["data", "--", "x"], "group": "No Good"},
                "good": {"argv": ["data", "--", "y"], "group": "jam"},
            }
        }
    )
    assert [t.name for t in tools] == ["good"]
    assert len(problems) == 1
    assert "bad" in problems[0]


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
        n for n, c in list(tools_group.commands.items()) if getattr(c, "sb_saved", False)
    ]:
        del tools_group.commands[name]


def test_a_tool_is_an_ordinary_command_behind_the_tools_group(saved):
    """Round 2's address: behind the group, never on the root — the
    builtin/operator line shows in `sb --help` because the tree carries it."""
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
    and the path of `sb tools deploy-thing` says nothing about the `run` inside
    it — so the canvas would offer a refresh cadence on a write, which is the
    one thing the read/write split exists to prevent."""
    saved('[tool.deploy]\nargv = ["run", "--", "true"]\n')
    entry = {e["name"]: e for e in walk(cli)}["tools deploy"]
    assert entry["acts"] is True


def test_a_tool_wrapping_data_stays_pinnable(saved):
    saved('[tool.prs]\nargv = ["data", "--", "printf", "[]"]\n')
    assert {e["name"]: e for e in walk(cli)}["tools prs"]["acts"] is False


def test_a_saved_run_no_longer_collides_with_the_builtin(saved):
    """The round-2 reversal, proven structurally: `sb run` still resolves to
    the one door that writes, and the saved `run` lives at `sb tools run`."""
    before = cli.commands["run"]
    problems = saved('[tool.run]\nargv = ["data", "--", "printf", "[]"]\n')
    assert problems == []
    assert cli.commands["run"] is before
    assert "run" in tools_group.commands


def test_the_bare_group_still_lists(saved):
    """`sb tools` with no subcommand is the listing it always was — one door
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

    with unittest.mock.patch.object(capture_mod, "SB_HOME", tmp_path):
        result = CliRunner().invoke(cli, ["--json", "tools"])
    envelope = json.loads(result.stdout)
    assert envelope["data"]["formats"] == [
        {"name": "jam-status", "kind": "lines", "description": "PR, state, title"}
    ]
    assert envelope["partial"] is True
    assert any("unknown kind" in w for w in envelope["warnings"])


def test_the_listing_groups_with_the_ungrouped_last(saved):
    """Groups alphabetical, tools alphabetical within, ungrouped last."""
    from click.testing import CliRunner

    saved(
        '[tool.zebra]\nargv = ["data", "--", "printf", "[]"]\n'
        '[tool.node]\ngroup = "bbrain"\nargv = ["data", "--", "printf", "[]"]\n'
        '[tool.prs]\ngroup = "jam"\nargv = ["data", "--", "printf", "[]"]\n'
        '[tool.ci]\ngroup = "jam"\nargv = ["data", "--", "printf", "[]"]\n'
        '[tool.disk]\nargv = ["data", "--", "printf", "[]"]\n'
    )
    rows = json.loads(CliRunner().invoke(cli, ["--json", "tools"]).stdout)["data"]["tools"]
    assert [(r.get("group", ""), r["name"]) for r in rows] == [
        ("bbrain", "node"),
        ("jam", "ci"),
        ("jam", "prs"),
        ("", "disk"),
        ("", "zebra"),
    ]


def test_a_file_with_no_groups_lists_exactly_as_it_did_before_groups(saved):
    """The key is omitted rather than empty, and the column renderer takes
    every key of every row — so no group declared is no column drawn, and the
    listing is what it was before this round."""
    from click.testing import CliRunner

    saved(
        '[tool.prs]\nargv = ["data", "--", "printf", "[]"]\n'
        '[tool.disk]\nargv = ["data", "--", "printf", "[]"]\n'
    )
    rows = json.loads(CliRunner().invoke(cli, ["--json", "tools"]).stdout)["data"]["tools"]
    assert [r["name"] for r in rows] == ["disk", "prs"]
    assert all("group" not in r for r in rows)


def test_the_listing_shows_a_group_with_nothing_in_it(saved, tmp_path):
    """The reason declared groups exist at all: an empty one has to be visible
    from the terminal, or the rail and the CLI disagree about what there is."""
    from click.testing import CliRunner

    saved(
        '[group.jam]\ndescription = "jam.sense"\n'
        "[group.archive]\n"
        '[tool.prs]\ngroup = "jam"\nargv = ["data", "--", "printf", "[]"]\n'
    )
    groups = json.loads(CliRunner().invoke(cli, ["--json", "tools"]).stdout)["data"]["groups"]
    assert groups == [
        {"name": "archive", "description": "", "commands": 0, "declared": True},
        {"name": "jam", "description": "jam.sense", "commands": 1, "declared": True},
    ]


def test_a_group_named_by_a_command_lists_without_being_declared(saved):
    from click.testing import CliRunner

    saved('[tool.prs]\ngroup = "jam"\nargv = ["data", "--", "printf", "[]"]\n')
    groups = json.loads(CliRunner().invoke(cli, ["--json", "tools"]).stdout)["data"]["groups"]
    assert groups == [
        {"name": "jam", "description": "", "commands": 1, "declared": False}
    ]


def test_the_tools_table_is_unchanged_by_groups_existing(saved):
    """The envelope grows a `groups` key, always — the same shape `formats` and
    `highlights` have. What must not change is the tools table itself."""
    from click.testing import CliRunner

    saved('[tool.prs]\nargv = ["data", "--", "printf", "[]"]\n')
    data = json.loads(CliRunner().invoke(cli, ["--json", "tools"]).stdout)["data"]
    assert data["groups"] == []
    assert data["tools"] == [
        {
            "name": "prs",
            "description": "sb data -- printf '[]'",
            "runs": "sb data -- printf []",
            "acts": False,
            "refresh": 0,
        }
    ]


def test_a_malformed_group_is_reported_alongside_a_malformed_tool(saved):
    """`register` returns both kinds in one list, which is what `cli/__init__`
    extends `PROBLEMS` with at startup and what `sb tools` then reports. The
    fixture takes the return value directly, because it registers into a tree
    that is already built."""
    problems = saved(
        '[group."Bad Name"]\n'
        '[tool."Bad Tool"]\nargv = ["data", "--", "x"]\n'
        '[tool.prs]\nargv = ["data", "--", "printf", "[]"]\n'
    )
    assert any(p.startswith("group ") for p in problems)
    assert any(p.startswith("tool ") for p in problems)


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
    every token is somebody's argv, not sky.boss's."""
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
    """`sb -t --refresh 30 prs` was considered and rejected: it would teach
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
    allowed to say `~/.sky-boss/tools.toml`, because naming the default is
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


def test_the_example_is_a_tools_file_that_would_actually_load():
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


# ============================================================================
# Saving — [[tools]] round 3
# ============================================================================


def test_the_saved_argv_is_the_line_you_typed_minus_the_flag():
    from cli.tools import saved_argv

    invocation = ["--json", "data", "--cols", "a,b", "--save=prs", "--", "jam", "pr", "list"]
    assert saved_argv(invocation, "data") == ["data", "--cols", "a,b", "--", "jam", "pr", "list"]


def test_the_space_form_of_the_flag_takes_its_value_with_it():
    from cli.tools import saved_argv

    assert saved_argv(["read", "--save", "x", "--", "ls"], "read") == ["read", "--", "ls"]


def test_a_save_flag_after_the_separator_belongs_to_the_wrapped_tool():
    """Click never parsed it as ours — everything past `--` is the foreign
    command's, and rewriting it would corrupt the argv being saved."""
    from cli.tools import saved_argv

    invocation = ["read", "--save=mine", "--", "sometool", "--save=theirs"]
    assert saved_argv(invocation, "read") == ["read", "--", "sometool", "--save=theirs"]


def test_a_cadence_is_lifted_out_of_the_argv_into_the_field():
    """A `--refresh` baked into a saved argv would make `sb tools <name>` go
    resident on its own, and residency is never ambient — see [[refresh]]."""
    from cli.tools import cadence_of, saved_argv

    for invocation in (
        ["data", "--refresh", "30", "--", "jam", "pr", "list"],
        ["data", "--refresh=30", "--", "jam", "pr", "list"],
    ):
        assert saved_argv(invocation, "data") == ["data", "--", "jam", "pr", "list"]
        assert cadence_of(invocation, "data") == 30


def test_no_cadence_is_zero_not_a_guess():
    from cli.tools import cadence_of

    assert cadence_of(["data", "--", "x"], "data") == 0


def test_saving_appends_and_never_touches_what_is_already_there(tmp_path):
    """The whole safety argument in one assertion: the operator's comments,
    spacing and hand-written tools survive byte-for-byte."""
    from cli.tools import save

    handwritten = (
        "# my tools, hand-written\n\n"
        '[tool.disk]\n# why this one acts\nargv = ["run", "--", "df", "-h"]\n'
    )
    (tmp_path / "tools.toml").write_text(handwritten)

    save("prs", ["data", "--", "jam", "pr", "list"], home=tmp_path)

    after = (tmp_path / "tools.toml").read_text()
    assert after.startswith(handwritten)
    assert '[tool.prs]' in after
    assert 'argv = ["data", "--", "jam", "pr", "list"]' in after


def test_saving_into_an_absent_home_creates_it(tmp_path):
    from cli.tools import save

    home = tmp_path / "nothing" / "here"
    path = save("prs", ["read", "--", "ls"], home=home)
    assert path.exists()
    assert path.read_text().startswith("[tool.prs]")


def test_a_name_already_declared_is_refused_and_told_what_it_runs(tmp_path):
    """No overwrite: a name that exists is an edit, and edits are $EDITOR's."""
    import rich_click as click
    import pytest

    from cli.tools import save

    save("prs", ["data", "--", "jam", "pr", "list"], home=tmp_path)
    with pytest.raises(click.UsageError) as caught:
        save("prs", ["read", "--", "ls"], home=tmp_path)
    assert "already a tool" in str(caught.value)
    assert "sb data -- jam pr list" in str(caught.value)


def test_a_cadence_the_surface_cannot_cycle_to_is_refused_at_save_time(tmp_path):
    """Saving cleanly and then failing to load is the worst of both."""
    import rich_click as click
    import pytest

    from cli.tools import save

    with pytest.raises(click.UsageError) as caught:
        save("prs", ["data", "--", "x"], refresh=7, home=tmp_path)
    assert "must be one of" in str(caught.value)
    assert not (tmp_path / "tools.toml").exists()


def test_a_name_that_could_not_be_a_command_is_refused(tmp_path):
    import rich_click as click
    import pytest

    from cli.tools import save

    for bad in ("--prs", "my tool", "Prs", "a.b"):
        with pytest.raises(click.UsageError):
            save(bad, ["read", "--", "ls"], home=tmp_path)


def test_an_unparseable_file_is_not_appended_to(tmp_path):
    """Appending to a file sky.boss cannot read would bury the real problem."""
    import rich_click as click
    import pytest

    from cli.tools import save

    (tmp_path / "tools.toml").write_text("this is not toml [[[\n")
    with pytest.raises(click.UsageError) as caught:
        save("prs", ["read", "--", "ls"], home=tmp_path)
    assert "fix the file" in str(caught.value)


def test_a_saved_block_survives_a_round_trip_through_the_real_loader(tmp_path):
    """Proven by re-reading rather than by trusting the writer: quotes,
    separators and odd characters all come back as the same argv."""
    from cli.tools import load, save

    argv = ["data", "--cols", 'a,"b"', "--cwd", "/tmp/x y", "--", "jam", "pr", "list", "--json"]
    save("prs", argv, refresh=30, home=tmp_path)
    tools, problems = load({"data": False, "run": True}, home=tmp_path)
    assert problems == []
    assert [t.argv for t in tools] == [argv]
    assert tools[0].refresh == 30


# ---------------------------------------------------------- the flag on the tree


def test_run_never_takes_save():
    """The absence in `run --help` is the act/observe split made visible,
    exactly as `--refresh`'s absence is. `--save` saves by example, and the
    example ran — a write saved by having just been performed is a different
    act, and one that earns opening the file."""
    from click.testing import CliRunner

    from cli import cli

    result = CliRunner().invoke(cli, ["run", "--save", "x", "--", "true"])
    assert result.exit_code == 2
    assert "No such option" in result.output
    assert "--save" not in CliRunner().invoke(cli, ["run", "--help"]).output


def test_the_three_observes_offer_save_with_an_example():
    from click.testing import CliRunner

    from cli import cli

    for command in ("read", "data", "follow"):
        help_text = " ".join(CliRunner().invoke(cli, [command, "--help"]).output.split())
        assert "--save" in help_text, command
        # Help is the doc ([[refresh]]): the flag carries a line you can paste.
        assert f"sb {command}" in help_text and "--save" in help_text, command


def test_a_saved_read_round_trips_through_the_real_loader(tmp_path, monkeypatch):
    """The property the whole feature rests on: the registered tool's
    expansion is the line that made it. A tool that merely *looked* right
    would stay invisible until the day it ran."""
    from click.testing import CliRunner

    from cli import cli
    from cli.tools import register, tools as tools_group

    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.helpers.SB_HOME", tmp_path)
    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)

    typed = ["read", "--cwd", str(tmp_path), "--save", "greet", "--", "printf", "hi"]
    result = CliRunner().invoke(cli, typed)
    assert result.exit_code == 0

    try:
        problems = register(cli, home=tmp_path)
        assert problems == []
        saved = tools_group.commands["greet"]
        assert list(saved.sb_argv) == [t for t in typed if t not in ("--save", "greet")]
    finally:
        for name in [
            n for n, c in list(tools_group.commands.items()) if getattr(c, "sb_saved", False)
        ]:
            del tools_group.commands[name]


def test_the_envelope_carries_where_it_went_and_what_it_runs(tmp_path, monkeypatch):
    import json

    from click.testing import CliRunner

    from cli import cli

    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)
    result = CliRunner().invoke(cli, ["--json", "read", "--save", "greet", "--", "printf", "hi"])
    envelope = json.loads(result.stdout)
    assert envelope["saved"]["name"] == "greet"
    assert envelope["saved"]["runs"] == "sb read -- printf hi"
    assert envelope["saved"]["file"] == str(tmp_path / "tools.toml")


def test_an_envelope_that_saved_nothing_is_byte_identical_to_before(tmp_path, monkeypatch):
    """Same rule as `view`: omitted rather than null, so no consumer has to
    learn that null means "did not save"."""
    import json

    from click.testing import CliRunner

    from cli import cli

    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)
    envelope = json.loads(CliRunner().invoke(cli, ["--json", "read", "--", "printf", "hi"]).stdout)
    assert "saved" not in envelope


def test_a_failing_command_still_saves_because_an_argv_is_not_a_result(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from cli import cli

    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)
    result = CliRunner().invoke(cli, ["read", "--save", "nope", "--", "false"])
    assert result.exit_code == 1
    assert "[tool.nope]" in (tmp_path / "tools.toml").read_text()


def test_a_resident_read_saves_before_it_goes_resident(tmp_path, monkeypatch):
    """A residency never reaches its own exit, so saving after the run would
    mean the flag silently did nothing on exactly the invocations most worth
    keeping."""
    from click.testing import CliRunner

    from cli import cli

    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)
    monkeypatch.setattr("cli.resident.reside", lambda source, interval, run_once, **kw: None)
    result = CliRunner().invoke(
        cli, ["read", "--refresh", "30", "--save", "prs", "--", "printf", "hi"]
    )
    assert result.exit_code == 0
    saved = (tmp_path / "tools.toml").read_text()
    # The cadence is lifted into the field, not left in the argv.
    assert 'argv = ["read", "--", "printf", "hi"]' in saved
    assert "refresh = 30" in saved


def test_a_follow_saves_without_opening_a_stream(tmp_path, monkeypatch):
    """Proven the way the dispatch test proves the file form — by
    intercepting the residency, because a real one would block the suite."""
    from click.testing import CliRunner

    from cli import cli

    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)
    monkeypatch.setattr("cli.filefollow.follow_file", lambda path, **kw: None)
    result = CliRunner().invoke(cli, ["follow", "--save", "cron", "x/y.log"])
    assert result.exit_code == 0
    assert 'argv = ["follow", "x/y.log"]' in (tmp_path / "tools.toml").read_text()
    assert "saved cron" in result.output


# --------------------------------------------- what the bench composes ([[workbench]])


def test_the_bench_ordering_round_trips_with_the_cadence_lifted(tmp_path, monkeypatch):
    """The bench puts `--save` and `--refresh` straight after the command word,
    ahead of `--cwd` and the view flags, and the saved tool must still be the
    line that made it.

    Two things are asserted rather than one. The argv round-trips *without*
    either flag — they asked for the save, they are not part of it. And the
    cadence lands in the tool's own field, because a `--refresh` baked into a
    saved argv would make `sb tools <name>` go resident on its own.

    The invocation is injected rather than run, which is what `save_invocation`
    takes one for: running this line goes resident, which is the whole reason
    the bench cannot compose it. See [[workbench]] round 3.
    """
    from cli.tools import cadence_of, read, save_invocation, saved_argv

    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)

    typed = [
        "data", "--save", "prs", "--refresh", "30",
        "--cwd", str(tmp_path), "--cols", "a",
        "--", "printf", '[{"a": 1}]',
    ]
    assert saved_argv(typed, "data") == [
        "data", "--cwd", str(tmp_path), "--cols", "a", "--", "printf", '[{"a": 1}]'
    ]
    assert cadence_of(typed, "data") == 30

    written = save_invocation("prs", "data", typed)
    assert written["refresh"] == 30
    declared = read(tmp_path)["tool"]["prs"]
    assert declared["refresh"] == 30
    assert declared["argv"] == saved_argv(typed, "data")


def test_a_name_is_judged_the_same_way_whoever_asks(tmp_path, monkeypatch):
    """`name_problem` is what `save` refuses on, so the bench asking it before
    the button and the CLI raising on it are one implementation. A surface with
    its own copy of the rule would disagree the day the rule changed."""
    import rich_click as click

    from cli.tools import name_problem, save

    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)

    assert name_problem("prs", tmp_path) is None
    assert "lowercase letters" in name_problem("Bad Name", tmp_path)
    assert "lowercase letters" in name_problem("", tmp_path)

    save("prs", ["data", "--", "true"], home=tmp_path)
    taken = name_problem("prs", tmp_path)
    assert "already a tool" in taken
    with pytest.raises(click.UsageError) as raised:
        save("prs", ["data", "--", "true"], home=tmp_path)
    assert str(raised.value) == taken


def test_a_refused_cadence_writes_nothing(tmp_path, monkeypatch):
    """`--save` writes before it runs, so a usage error raised further down
    fired *after* the append: `sb --json data --save prs --refresh 30` left the
    tool on disk, cadence and all, then exited 2. A name taken, a file changed,
    and a failure reported.

    Found by the workbench trying to save a cadence — which is what a surface
    that runs the real commands is for. A usage error belongs at the door,
    before any side effect.
    """
    from click.testing import CliRunner

    from cli import cli

    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.helpers.SB_HOME", tmp_path)
    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)

    result = CliRunner().invoke(
        cli, ["--json", "data", "--save", "prs", "--refresh", "30", "--", "printf", "[]"]
    )
    assert result.exit_code == 2
    assert "refuse each other" in result.output
    assert not (tmp_path / "tools.toml").exists()


def test_the_same_ordering_holds_for_read(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from cli import cli

    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.helpers.SB_HOME", tmp_path)
    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)

    result = CliRunner().invoke(
        cli, ["--json", "read", "--save", "log", "--refresh", "30", "--", "printf", "hi"]
    )
    assert result.exit_code == 2
    assert not (tmp_path / "tools.toml").exists()


def test_save_carries_env_into_the_saved_argv():
    """`saved_argv` copies the line you typed, so `--env` rides along exactly
    as `--cwd` does — no `env` field in tools.toml, one way to say it.
    See [[subprocess-env]] round 4."""
    from cli.tools import saved_argv

    line = ["read", "--env", "JAM_TRANSCRIPT_STDOUT=1", "--save", "x", "--", "jam", "status"]
    assert saved_argv(line, "read") == [
        "read", "--env", "JAM_TRANSCRIPT_STDOUT=1", "--", "jam", "status",
    ]


# --- [[tools]] round 4: the interface writes --------------------------------

SAMPLE = '''# a section heading, separated by a blank line

# describes alpha
[tool.alpha]
argv = ["read", "--", "echo", "a"]

[tool.beta]
# inside beta
argv = ["read", "--", "echo", "b"]
refresh = 30
'''


def _home(tmp_path):
    (tmp_path / "tools.toml").write_text(SAMPLE)
    return tmp_path


def test_replacing_a_block_leaves_every_other_byte_alone(tmp_path):
    """The whole argument for splicing rather than round-tripping: a write
    touches one line range and nothing else can have been reformatted."""
    from cli.tools import write_block

    home = _home(tmp_path)
    write_block("alpha", ["read", "--", "echo", "CHANGED"], home=home)
    after = (home / "tools.toml").read_text()
    assert after[after.index("[tool.beta]"):] == SAMPLE[SAMPLE.index("[tool.beta]"):]


def test_a_comment_above_a_block_survives_an_edit(tmp_path):
    """It is the operator's prose and may still be true of the tool that
    replaces this one. The range starts at the header for exactly this."""
    from cli.tools import write_block

    home = _home(tmp_path)
    write_block("alpha", ["read", "--", "echo", "x"], home=home)
    after = (home / "tools.toml").read_text()
    assert "# describes alpha" in after
    assert "# a section heading" in after


def test_a_delete_takes_the_comments_touching_it_but_not_a_heading(tmp_path):
    """Contiguous comments describe the block below them. One separated by a
    blank line is a heading for whatever follows and is not ours to remove."""
    from cli.tools import remove_block

    home = _home(tmp_path)
    remove_block("alpha", home=home)
    after = (home / "tools.toml").read_text()
    assert "[tool.alpha]" not in after
    assert "# describes alpha" not in after, "took the block, left its prose"
    assert "# a section heading" in after, "ate a heading that was not the block's"
    assert "[tool.beta]" in after


def test_separation_between_blocks_is_neither_lost_nor_doubled(tmp_path):
    from cli.tools import write_block

    home = _home(tmp_path)
    write_block("alpha", ["read", "--", "echo", "x"], home=home)
    after = (home / "tools.toml").read_text()
    assert after.count("\n\n") == SAMPLE.count("\n\n")


def test_a_write_backs_the_file_up_first(tmp_path):
    from cli.tools import write_block

    home = _home(tmp_path)
    out = write_block("alpha", ["read", "--", "echo", "x"], home=home)
    import os

    assert open(out["backup"], encoding="utf-8").read() == SAMPLE, "the backup is the file as it was"
    assert os.path.dirname(out["backup"]).endswith("backups")


def test_two_writes_in_one_second_keep_two_backups(tmp_path):
    """A second is not fine-grained enough, and the operator was promised a
    copy per write."""
    from cli.tools import backup

    home = _home(tmp_path)
    first = backup(home, stamp="20260828T000000Z")
    second = backup(home, stamp="20260828T000000Z")
    assert first != second
    assert first.exists() and second.exists()


def test_backups_are_capped(tmp_path):
    from cli.tools import BACKUPS_KEPT, backup

    home = _home(tmp_path)
    for i in range(BACKUPS_KEPT + 5):
        backup(home, stamp=f"20260828T0000{i:02d}Z")
    assert len(list((home / "backups").iterdir())) == BACKUPS_KEPT


def test_the_writer_refuses_everything_the_loader_would(tmp_path):
    """One rule, asked twice. A tool that writes cleanly and then fails to load
    is on disk, absent from the tree, and evidenced only by a line in
    `sb tools`."""
    from cli.tools import write_problem

    home = _home(tmp_path)
    assert write_problem("ok-name", ["read", "--", "echo", "x"], home=home) is None
    assert "must start with" in (write_problem("x", ["ls"], home=home) or "")
    assert "acts" in (write_problem("x", ["run", "--", "true"], 30, home=home) or "")
    assert "follow" in (write_problem("x", ["follow", "--", "tail"], 30, home=home) or "")
    assert "one of" in (write_problem("x", ["read", "--", "true"], 7, home=home) or "")
    assert "cannot be a tool name" in (write_problem("Bad Name", ["read", "--", "x"], home=home) or "")


def test_replacing_an_existing_name_is_allowed_where_save_refuses_it(tmp_path):
    """Round 3's `--save` refuses a duplicate because editing was $EDITOR's.
    Round 4 made create and replace one call, because they are one intent."""
    from cli.tools import name_problem, write_block, write_problem

    home = _home(tmp_path)
    assert "already a tool" in (name_problem("alpha", home) or ""), "--save still refuses"
    assert write_problem("alpha", ["read", "--", "echo", "x"], home=home) is None
    assert write_block("alpha", ["read", "--", "echo", "x"], home=home)["action"] == "replaced"


def test_deleting_something_that_is_not_there_is_an_error(tmp_path):
    """A silent no-op on a delete reads as success and leaves the operator
    believing a command is gone."""
    import pytest
    import rich_click as click

    from cli.tools import remove_block

    with pytest.raises(click.UsageError):
        remove_block("nosuch", home=_home(tmp_path))


# --------------------------------------------------- the writer carries a group


def test_a_written_group_lands_in_the_block_and_loads_back(tmp_path):
    from cli.tools import load, write_block

    home = _home(tmp_path)
    out = write_block("gamma", ["read", "--", "echo", "x"], home=home, group="jam")
    assert out["group"] == "jam"
    assert 'group = "jam"' in (home / "tools.toml").read_text()
    tools, problems = load({"read": False, "run": True}, home=home)
    assert problems == []
    assert next(t for t in tools if t.name == "gamma").group == "jam"


def test_clearing_the_group_removes_the_line_rather_than_writing_an_empty_one(tmp_path):
    """Blank is ungrouped, so the field goes away — a `group = ""` left behind
    would load as ungrouped too, and be one more line nobody wrote on purpose."""
    from cli.tools import write_block

    home = _home(tmp_path)
    write_block("gamma", ["read", "--", "echo", "x"], home=home, group="jam")
    write_block("gamma", ["read", "--", "echo", "x"], home=home, group="")
    assert "group" not in (home / "tools.toml").read_text()


def test_the_writer_refuses_a_group_the_loader_would_refuse(tmp_path):
    """One function, asked twice. A tool that writes cleanly and then fails to
    load is the worst of both, which is round 4's rule and does not change."""
    from cli.tools import write_problem

    home = _home(tmp_path)
    assert "group" in (
        write_problem("gamma", ["read", "--", "echo", "x"], home=home, group="No Good") or ""
    )
    assert write_problem("gamma", ["read", "--", "echo", "x"], home=home, group="jam") is None


def test_a_comment_above_a_grouped_block_still_survives_an_edit(tmp_path):
    """Round 4's guarantee, with one more line inside the block."""
    from cli.tools import write_block

    home = tmp_path
    (home / "tools.toml").write_text(
        '# why this needs --cwd\n[tool.alpha]\nargv = ["read", "--", "echo", "a"]\n'
    )
    write_block("alpha", ["read", "--", "echo", "b"], home=home, group="jam")
    after = (home / "tools.toml").read_text()
    assert after.startswith("# why this needs --cwd\n")
    assert 'group = "jam"' in after


# ----------------------------------------------------- a group can be declared
# Round 6. A group exists if any command names it, or if it is declared —
# neither implies the other, which is what keeps every round-5 file working.


def _groups(raw):
    from cli.tools import parse_groups

    return parse_groups(raw)


def test_a_declared_group_is_a_group():
    groups, problems = _groups({"group": {"jam": {"description": "jam.sense"}}})
    assert problems == []
    assert groups[0].name == "jam"
    assert groups[0].description == "jam.sense"


def test_a_group_may_be_declared_with_nothing_in_it():
    """The whole point: an empty table is a group with no commands, which is
    the thing that had nowhere to exist before this round."""
    groups, problems = _groups({"group": {"archive": {}}})
    assert problems == []
    from cli.tools import Group

    assert groups[0] == Group("archive", "")


@pytest.mark.parametrize("name", ["Jam", "jam sense", "-jam", "jam.sense"])
def test_a_group_name_takes_the_same_shape_a_tool_name_does(name):
    groups, problems = _groups({"group": {name: {}}})
    assert groups == []
    assert "lowercase" in problems[0]


def test_one_bad_group_does_not_cost_the_others():
    groups, problems = _groups({"group": {"Bad": {}, "good": {}}})
    assert [g.name for g in groups] == ["good"]
    assert len(problems) == 1


def test_a_group_declaration_that_is_not_a_table_is_refused():
    groups, problems = _groups({"group": {"jam": "nope"}})
    assert groups == []
    assert "not a table" in problems[0]


def test_no_group_table_declares_no_groups():
    """Every file written before this round is untouched by it."""
    assert _groups(GOOD) == ([], [])


def test_a_group_exists_if_it_is_named_or_declared():
    from cli.tools import Group, sections

    tools, _ = one(
        {
            "tool": {
                "prs": {"argv": ["data", "--", "x"], "group": "jam"},
                "ci": {"argv": ["data", "--", "y"], "group": "jam"},
                "disk": {"argv": ["data", "--", "z"]},
            }
        }
    )
    out = sections(tools, [Group("archive", "old things"), Group("jam", "jam.sense")])
    assert out == [
        {"name": "archive", "description": "old things", "declared": True, "count": 0},
        {"name": "jam", "description": "jam.sense", "declared": True, "count": 2},
    ]


def test_a_group_named_but_not_declared_still_exists():
    """Round 5's files keep working — that is the whole compatibility rule."""
    from cli.tools import sections

    tools, _ = one({"tool": {"prs": {"argv": ["data", "--", "x"], "group": "jam"}}})
    assert sections(tools, []) == [
        {"name": "jam", "description": "", "declared": False, "count": 1}
    ]


def test_the_ungrouped_are_not_a_section():
    """They are the bucket every surface draws last. An entry here would make
    them a group, and a group can be deleted."""
    from cli.tools import sections

    tools, _ = one({"tool": {"disk": {"argv": ["data", "--", "z"]}}})
    assert sections(tools, []) == []


# ------------------------------------------------- every declared field survives


def test_block_serialises_every_declared_field_of_a_tool():
    """The guard, not the fix. `block()` has to know every field a tool can
    declare, and `highlight` was missing from round 4 until round 6 measured
    it: a followed tool declaring a ruleset came back without one, and the only
    evidence was a stream that stopped being tinted.

    Walking the dataclass means the next field added fails here rather than
    silently going missing from every rewrite. `acts` and `resident` are
    excluded because they are *derived* from the argv and never declared."""
    import dataclasses

    from cli.tools import Tool, block

    derived = {"name", "argv", "acts", "resident"}
    declared = [f.name for f in dataclasses.fields(Tool) if f.name not in derived]

    # `block` is a pure serialiser with no validation of its own, so it is
    # asked for a combination no *loader* would accept — a cadence and a
    # ruleset together. The question here is only whether every field can
    # reach the file.
    written = block(
        "x",
        ["follow", "--", "tail", "-f", "/tmp/x"],
        refresh=30,
        description="d",
        group="g",
        highlight="h",
    )
    for field in declared:
        assert f"{field} =" in written, f"block() does not serialise {field!r}"


def test_a_saved_highlight_survives_a_rewrite(tmp_path):
    """The bug itself, from the outside: write a tool that has one, rewrite it,
    read it back."""
    from cli.tools import load, write_block

    home = tmp_path
    write_block(
        "applog",
        ["follow", "--", "printf", "x"],
        description="app log",
        home=home,
        highlight="jam",
    )
    write_block(
        "applog",
        ["follow", "--", "printf", "y"],
        description="app log",
        home=home,
        highlight="jam",
    )
    tools, problems = load({"follow": False}, home=home, resident=frozenset({"follow"}))
    assert problems == []
    assert tools[0].highlight == "jam"


def test_the_catalog_carries_a_highlight_so_a_surface_can_restate_it(saved):
    """The half that makes the fix reach the bench: a surface rewriting a tool
    has to be able to see every field it is restating."""
    saved(
        '[tool.applog]\nargv = ["follow", "--", "printf", "x"]\nhighlight = "jam"\n'
    )
    entry = next(e for e in walk(cli) if e["name"] == "tools applog")
    assert entry["highlight"] == "jam"


def test_a_file_that_does_not_parse_is_never_spliced(tmp_path):
    """Splicing into a document whose structure is unknown is how a tool is
    lost. $EDITOR is still there."""
    from cli.tools import write_problem

    (tmp_path / "tools.toml").write_text("[tool.broken\nargv = nope")
    assert "fix the file" in (write_problem("x", ["read", "--", "y"], home=tmp_path) or "")
