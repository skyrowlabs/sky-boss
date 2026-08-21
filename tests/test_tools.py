"""The toolbox — commands the operator saved.

The properties worth defending are the four that keep operator content from
becoming a way around tb's own rules: a tool expands to a tb command and not a
shell command, it inherits `acts` rather than declaring it, it can never shadow
a builtin, and it may only carry a cadence if it reads.

Everything here drives `parse` directly. It is a pure function over a parsed
dict, which is what makes the interesting half testable without a file.
"""

import json
import pathlib
import tomllib

import pytest

from cli.tools import load, parse

# The live tree as the validator sees it: what is runnable and whether it acts,
# plus every name on the root group. The second set is larger because a surface
# excludes itself from the first and must still not be shadowable.
COMMANDS = {"run": True, "wrap": False}
REGISTERED = {"run", "wrap", "ui"}

GOOD = {
    "tool": {
        "prs": {
            "description": "open PRs",
            "argv": ["wrap", "--", "somecli", "list", "--json"],
            "every": 30,
        }
    }
}


def one(raw):
    return parse(raw, COMMANDS, REGISTERED)


def test_a_declared_tool_becomes_a_tool():
    tools, problems = one(GOOD)
    assert problems == []
    assert tools[0].name == "prs"
    assert tools[0].every == 30
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
    assert "wrap" in problems[0] and "run" in problems[0]


@pytest.mark.parametrize("argv", [[], "wrap", ["wrap", 3], None])
def test_argv_must_be_a_non_empty_list_of_strings(argv):
    _, problems = one({"tool": {"x": {"argv": argv}}})
    assert "non-empty list of strings" in problems[0]


# ------------------------------------------------------- rule 2: acts inherits


def test_acts_is_inherited_from_the_expansion_not_declared():
    """The operator already asserted read-or-write by choosing `run` or `wrap`.
    Asking again in the TOML would invite them to contradict themselves, and a
    safety property must have exactly one source."""
    tools, _ = one({"tool": {"w": {"argv": ["wrap", "--", "x"]}}})
    assert tools[0].acts is False
    tools, _ = one({"tool": {"r": {"argv": ["run", "--", "x"]}}})
    assert tools[0].acts is True


def test_a_declared_acts_field_is_ignored_rather_than_believed():
    tools, _ = one({"tool": {"r": {"argv": ["run", "--", "x"], "acts": False}}})
    assert tools[0].acts is True


# --------------------------------------------------- rule 3: builtins win


@pytest.mark.parametrize("name", ["run", "wrap", "ui"])
def test_a_tool_can_never_shadow_a_tb_command(name):
    """A stray [tool.run] silently redefining the one door that writes is the
    worst thing this file could do. `ui` is in the set too even though it
    excludes itself from the palette."""
    tools, problems = one({"tool": {name: {"argv": ["wrap", "--", "x"]}}})
    assert tools == []
    assert "already has this name" in problems[0]


@pytest.mark.parametrize("name", ["--evil", "has space", "Caps", "a/b", "a.b", ""])
def test_a_name_that_is_not_a_command_word_is_refused(name):
    _, problems = one({"tool": {name: {"argv": ["wrap", "--", "x"]}}})
    assert "lowercase letters" in problems[0]


# ------------------------------------------------- rule 4: cadence needs a read


def test_a_tool_that_acts_may_not_carry_a_cadence():
    """The same rule the canvas enforces by hiding the pin control. Re-running
    a read is a refresh; re-running a write is a scheduler nobody asked for."""
    tools, problems = one({"tool": {"r": {"argv": ["run", "--", "x"], "every": 30}}})
    assert tools == []
    assert "not allowed on a tool that acts" in problems[0]


def test_a_tool_that_acts_is_fine_without_one():
    tools, problems = one({"tool": {"r": {"argv": ["run", "--", "x"]}}})
    assert problems == [] and tools[0].every == 0


def test_a_cadence_outside_the_surfaces_list_is_refused():
    """The surface cycles the interval through a fixed list. A window starting
    on a value outside it jumps to 0 on the first click rather than to the next
    cadence up."""
    _, problems = one({"tool": {"x": {"argv": ["wrap", "--", "y"], "every": 45}}})
    assert "every must be one of" in problems[0]


def test_a_boolean_is_not_a_cadence():
    """`True` is an int in Python and would otherwise pass as one second."""
    _, problems = one({"tool": {"x": {"argv": ["wrap", "--", "y"], "every": True}}})
    assert "integer number of seconds" in problems[0]


# ------------------------------------------------------------ degrading well


def test_one_bad_tool_does_not_cost_the_operator_the_good_ones():
    """The failure this prevents is a typo in the ninth entry silently emptying
    the toolbox."""
    tools, problems = one(
        {
            "tool": {
                "good": {"argv": ["wrap", "--", "x"]},
                "bad": {"argv": ["docker", "ps"]},
                "alsogood": {"argv": ["run", "--", "y"]},
            }
        }
    )
    assert sorted(t.name for t in tools) == ["alsogood", "good"]
    assert len(problems) == 1


def test_an_absent_home_declares_nothing_and_says_nothing(tmp_path):
    """A fresh clone has no tools. Saying so on every invocation is noise."""
    assert load(COMMANDS, REGISTERED, home=tmp_path / "nope") == ([], [])


def test_a_file_that_cannot_be_parsed_is_reported_rather_than_raised(tmp_path):
    """It exists, so the operator expects it to work — but one broken file must
    not stop tb running at all."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "tools.toml").write_text("this is not = = toml")
    tools, problems = load(COMMANDS, REGISTERED, home=tmp_path)
    assert tools == []
    assert len(problems) == 1


def test_a_tilde_in_an_argv_is_expanded():
    """The whole point is that these are the operator's own paths."""
    tools, _ = one({"tool": {"x": {"argv": ["wrap", "--cwd", "~/somewhere", "--", "y"]}}})
    assert tools[0].argv[2].startswith("/")
    assert "~" not in tools[0].argv[2]


def test_a_tilde_inside_a_value_is_left_alone():
    tools, _ = one({"tool": {"x": {"argv": ["wrap", "--", "y", "a~b"]}}})
    assert tools[0].argv[-1] == "a~b"


# ============================================================================
# Registration — the half that makes the palette work for free
# ============================================================================

from cli import cli  # noqa: E402
from cli.canvas.catalog import walk  # noqa: E402
from cli.tools import register  # noqa: E402


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

    for name in [n for n, c in list(cli.commands.items()) if getattr(c, "tb_saved", False)]:
        del cli.commands[name]


def test_a_tool_is_an_ordinary_command_on_the_tree(saved):
    saved('[tool.prs]\nargv = ["wrap", "--", "printf", "[]"]\n')
    assert "prs" in cli.commands


def test_the_palette_finds_a_tool_without_the_catalog_knowing_about_tools(saved):
    """The point of registering rather than listing. `cli/canvas/catalog.py`
    walks the live tree, so a tool appears in the palette with its real summary
    and its real options and nothing there had to learn what a tool is."""
    saved('[tool.prs]\ndescription = "open PRs"\nargv = ["wrap", "--", "printf", "[]"]\n')
    entry = {e["name"]: e for e in walk(cli)}["prs"]
    assert entry["summary"] == "open PRs"
    assert entry["saved"] is True


def test_a_tool_wrapping_run_is_marked_as_acting_in_the_catalog(saved):
    """The safety property. `acts` is otherwise derived from the command path,
    and the path of `tb deploy-thing` says nothing about the `run` inside it —
    so the canvas would offer a refresh cadence on a write, which is the one
    thing the read/write split exists to prevent."""
    saved('[tool.deploy]\nargv = ["run", "--", "true"]\n')
    entry = {e["name"]: e for e in walk(cli)}["deploy"]
    assert entry["acts"] is True


def test_a_tool_wrapping_wrap_stays_pinnable(saved):
    saved('[tool.prs]\nargv = ["wrap", "--", "printf", "[]"]\n')
    assert {e["name"]: e for e in walk(cli)}["prs"]["acts"] is False


def test_a_builtin_is_never_replaced(saved):
    """The worst thing this file could do is silently redefine the one door
    that writes."""
    before = cli.commands["run"]
    problems = saved('[tool.run]\nargv = ["wrap", "--", "printf", "[]"]\n')
    assert cli.commands["run"] is before
    assert problems and "already has this name" in problems[0]


def test_running_a_tool_dispatches_to_its_expansion(saved):
    from click.testing import CliRunner

    saved('[tool.prs]\nargv = ["wrap", "--", "printf", "[{\\"a\\": 1}]"]\n')
    result = CliRunner().invoke(cli, ["--json", "prs"])
    envelope = json.loads(result.stdout)
    assert envelope["data"] == [{"a": 1}]


def test_the_envelope_names_the_tool_rather_than_what_it_expanded_to(saved):
    """The operator ran `prs`. An envelope that came back saying `wrap` would
    be describing an implementation detail they did not type."""
    from click.testing import CliRunner

    saved('[tool.prs]\nargv = ["wrap", "--", "printf", "[{\\"a\\": 1}]"]\n')
    result = CliRunner().invoke(cli, ["--json", "prs"])
    assert json.loads(result.stdout)["command"] == "prs"


def test_a_tool_takes_no_arguments(saved):
    """A tool that took arguments would be a shell function, and this is not a
    shell. Click refuses it as a usage error, which is exit 2 — not 3, which
    would say the run was degraded."""
    from click.testing import CliRunner

    saved('[tool.prs]\nargv = ["wrap", "--", "printf", "[]"]\n')
    result = CliRunner().invoke(cli, ["prs", "945"])
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
        tools, _ = parse(tomllib.load(handle), COMMANDS, REGISTERED)
    for tool in tools:
        for part in tool.argv:
            assert not part.startswith(str(pathlib.Path.home())), (tool.name, part)


def test_the_example_is_a_toolbox_that_would_actually_load():
    """An example that does not parse teaches the wrong thing twice: once when
    it is copied, and again when the operator concludes the format is broken."""
    with EXAMPLE.open("rb") as handle:
        raw = tomllib.load(handle)
    tools, problems = parse(raw, COMMANDS, REGISTERED)
    assert problems == []
    assert {t.name for t in tools} == {"prs", "containers", "disk"}


def test_the_example_demonstrates_both_sides_of_the_read_write_split():
    """Someone copying this should see a tool that acts and a tool that does
    not, because the distinction is the thing most likely to be missed."""
    with EXAMPLE.open("rb") as handle:
        tools, _ = parse(tomllib.load(handle), COMMANDS, REGISTERED)
    by_name = {t.name: t for t in tools}
    assert by_name["disk"].acts is True and by_name["disk"].every == 0
    assert by_name["prs"].acts is False and by_name["prs"].every == 30
