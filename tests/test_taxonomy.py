"""The taxonomy itself — that the groups keep the promises they are named for.

These are not tests of any one command. They are tests of the property that
makes the MCP allowlist a rule instead of a maintained list: `info` and `check`
cannot write, and everything that can write is reachable only through `tb run`.
"""

import ast

from click.testing import CliRunner

from cli import cli
from cli.helpers import PROJECT_ROOT
from cli.check import check
from cli.info import info


# The four moods are closed. The other two sets are not, and keeping them apart
# is the point: a new top-level word has to be argued into one of them, and only
# the mood set carries the read/write promise.
MOODS = {"run", "auto", "info", "check"}
SURFACES = {"tui"}  # `tb mcp serve` joins this when it lands
ALIASES = {"doctor"}


def test_the_top_level_is_the_moods_plus_surfaces_plus_the_kept_alias():
    assert set(cli.commands) == MOODS | SURFACES | ALIASES


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


def test_no_read_group_exposes_a_write_flag():
    """A write flag inside `info` or `check` is how the read-only promise dies.

    `tb assets update --apply` was exactly that, and it is the reason the split
    happened. This fails the moment someone reintroduces one.
    """
    banned = {"--apply", "--seed", "--write", "--fix", "--install", "--force"}
    for group in (info, check):
        for name, command in group.commands.items():
            flags = {opt for param in command.params for opt in getattr(param, "opts", [])}
            assert not (flags & banned), f"{group.name} {name} exposes {flags & banned}"


def test_writes_are_reachable_only_through_run():
    """Every internal task must be invocable, and only from `tb run`."""
    from cli.run import REGISTRY

    names = {t.name for t in REGISTRY}
    assert names, "there is at least one write path"

    for group_name in ("info", "check", "auto"):
        group = cli.commands[group_name]
        assert not (names & set(group.commands)), f"a task leaked into {group_name}"


def test_auto_no_longer_runs_jobs():
    """`tb auto run` moved to `tb run`; leaving both would be two doors to one act."""
    assert "run" not in cli.commands["auto"].commands


def test_check_subcommands_are_all_in_the_registry():
    """A check reachable as a subcommand but absent from the registry is invisible
    to the rollup, which is the failure mode that makes a rollup untrustworthy."""
    from cli.check import REGISTRY

    assert set(check.commands) == {entry.name for entry in REGISTRY}


def test_every_group_help_renders():
    runner = CliRunner()
    for path in ([], ["run"], ["auto"], ["info"], ["check"], ["doctor"], ["tui"]):
        res = runner.invoke(cli, [*path, "--help"])
        assert res.exit_code == 0, f"tb {' '.join(path)} --help failed"
