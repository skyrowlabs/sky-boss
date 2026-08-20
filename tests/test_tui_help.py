"""Tests for the help pane.

The property worth defending is that nothing here describes the CLI a second
time. Everything is read off Click, so a command added next year explains
itself with no change to this module — the same rule dispatch and completion
already hold to.
"""

import rich_click as click

from cli.tui.help import ELLIPSIS, view


def _tree():
    """A stand-in tree with the shape the real one no longer has.

    tb is two leaf commands right now, so a walk, a descent and a subcommand
    listing have nothing to act on. `view` takes the same injectable tree
    `dispatch` and `candidates` do, for exactly this reason — the properties
    being tested are about deriving from Click, not about which commands exist
    this week.
    """
    root = click.Group("tb", help="tackle-box.")
    group = click.Group("auto", help="Homebase jobs.")
    log = click.Command("log", short_help="Recent runs of a job.")
    log.params.append(click.Option(["--limit"], default=10, help="How many runs to show."))
    group.add_command(log)
    group.add_command(click.Command("status", short_help="Last outcome per job."))
    group.add_command(click.Command("install", short_help="Generate systemd user units."))
    root.add_command(group)
    return root


def test_help_names_the_resolved_command_not_the_typed_prefix():
    # `resolve` steps over a partial word, so without the prefix descent this
    # would explain the `auto` group on the keystroke where you want `status`.
    assert view("auto sta", width=60, rows=4, tree=_tree()).plain.startswith("status")


def test_an_ambiguous_prefix_explains_the_group_instead_of_guessing():
    root = click.Group("tb")
    root.add_command(click.Command("drift", short_help="one"))
    root.add_command(click.Command("drain", short_help="two"))

    # Both start with "dr"; picking either would be a coin toss shown as fact.
    from cli.tui import help as module

    text = module._descend(root, "dr")
    assert text is root


def test_a_group_lists_its_subcommands_with_their_one_liners():
    text = view("auto ", width=70, rows=8, tree=_tree()).plain
    assert "install" in text and "systemd user units" in text


def test_a_command_lists_its_options_with_their_help():
    text = view("auto log", width=70, rows=6, tree=_tree()).plain
    assert "--limit" in text and "How many runs to show" in text


def test_the_real_tree_still_explains_its_own_commands():
    """The stand-in above proves the mechanism; this proves it is wired to the
    CLI that actually exists."""
    text = view("run", width=70, rows=6).plain
    assert "run" in text and "--timeout" in text


def test_the_pane_is_derived_from_the_tree_not_a_table():
    """A command added to the tree appears with no change to help.py."""
    from cli import cli

    cli.add_command(click.Command("invented", short_help="not written down anywhere"))
    try:
        text = view("", width=70, rows=8).plain
        assert "invented" in text and "not written down anywhere" in text
    finally:
        del cli.commands["invented"]


def test_long_lines_truncate_to_the_pane_rather_than_wrapping():
    """A wrapped description eats the rows the other options need."""
    width = 30
    for line in view("auto log", width=width, rows=5).plain.split("\n"):
        assert len(line) <= width
    assert ELLIPSIS in view("auto log", width=width, rows=5).plain


def test_the_root_group_is_called_tb_not_cli():
    # Click knows it as `cli`, the package it lives in. Nowhere the user can
    # see is it called that.
    assert view("", width=40, rows=2).plain.startswith("tb\n")


def test_a_half_typed_quote_does_not_raise():
    # shlex would reject this; the pane repaints on every keystroke and an
    # exception mid-word would read as a crash.
    assert view("run 'unbalanced", width=40, rows=3).plain
