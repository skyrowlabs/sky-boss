"""The taxonomy itself — that the groups keep the promises they are named for.

These are not tests of any one command. They test the property that makes the
MCP allowlist a rule instead of a maintained list: everything that can write is
reachable only through `tb run`.

The mood set was four and is now two. `info` and `check` were retired in Round 2
of the command-taxonomy feature doc, which is also where the argument for
grouping by mood at all still lives — that argument never depended on the count.
"""

import ast

from click.testing import CliRunner

from cli import cli
from cli.helpers import PROJECT_ROOT


# The moods are closed. Surfaces are not, and keeping them apart is the point:
# a new top-level word has to be argued into one of them, and only the mood set
# carries the read/write promise.
MOODS = {"run", "auto"}
SURFACES = {"tui"}  # `tb mcp serve` joins this when it lands


def test_the_top_level_is_the_moods_plus_surfaces():
    """No aliases. `doctor` was the one kept alias and it went with `check`."""
    assert set(cli.commands) == MOODS | SURFACES


def test_a_surface_adds_no_write_path():
    """A surface renders the envelope. It must never reach a mutation directly.

    The way this breaks is a convenience — a key binding that calls `run_task`
    to skip argv parsing — and the cost is the property the whole taxonomy
    exists for: that nothing changes state without a ledger entry, because
    `tb run` is the only way in. The surface's only verb is "dispatch a string".
    """
    banned = {"run_job", "run_task", "seed_inventory", "refresh_inventory", "rewrite_derived"}
    for path in sorted((PROJECT_ROOT / "cli" / "tui").glob("*.py")):
        tree = ast.parse(path.read_text())
        # Names the code actually reaches, from the AST rather than the text.
        # Grepping the source fires on prose, and the surface has good reason to
        # *discuss* run_job: that it records only after a process exits is the
        # whole argument for showing live lane state.
        reached = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                reached.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                reached.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Name):
                reached.add(node.id)
            elif isinstance(node, ast.Attribute):
                reached.add(node.attr)
        leaked = reached & banned
        assert not leaked, f"{path.name} reaches {leaked} directly"


def test_autos_read_verbs_expose_no_write_flag():
    """A write flag on a read verb is how the read-only promise dies.

    `tb assets update --apply` was exactly that, and it is why the assets split
    happened at all. `info` and `check` are gone, so `auto`'s read verbs are the
    whole read surface now — and the same rule has to hold for them.

    `install`, `uninstall` and `prune` are excluded because they are `auto`'s
    declared write verbs; the point is that the *read* ones stay read.
    """
    banned = {"--apply", "--seed", "--write", "--fix", "--force"}
    writes = {"install", "uninstall", "prune"}
    auto = cli.commands["auto"]
    for name, command in auto.commands.items():
        if name in writes:
            continue
        flags = {opt for param in command.params for opt in getattr(param, "opts", [])}
        assert not (flags & banned), f"auto {name} exposes {flags & banned}"


def test_writes_are_reachable_only_through_run():
    """Every internal task must be invocable, and only from `tb run`."""
    from cli.run import REGISTRY

    names = {t.name for t in REGISTRY}
    assert names, "there is at least one write path"

    for group_name in ("auto",):
        group = cli.commands[group_name]
        assert not (names & set(group.commands)), f"a task leaked into {group_name}"


def test_auto_no_longer_runs_jobs():
    """`tb auto run` moved to `tb run`; leaving both would be two doors to one act."""
    assert "run" not in cli.commands["auto"].commands


def test_every_group_help_renders():
    runner = CliRunner()
    for path in ([], ["run"], ["auto"], ["tui"]):
        res = runner.invoke(cli, [*path, "--help"])
        assert res.exit_code == 0, f"tb {' '.join(path)} --help failed"


def test_the_retired_moods_are_really_gone():
    """Not merely unregistered. A leftover module keeps importing, keeps passing
    its own tests, and reads to a future session as a command that exists."""
    import importlib

    for module in ("cli.info", "cli.check", "cli.doctor", "cli.unpushed", "cli.assets", "cli.watch"):
        try:
            importlib.import_module(module)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"{module} still exists")

    for word in ("info", "check", "doctor", "drift", "tools", "unpushed"):
        assert word not in cli.commands, f"`tb {word}` is still registered"
