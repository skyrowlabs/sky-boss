"""Tests for the help pane.

The property worth defending is that nothing here describes the CLI a second
time. Everything is read off Click, so a command added next year explains
itself with no change to this module — the same rule dispatch and completion
already hold to.
"""

import rich_click as click

from cli.tui.help import ELLIPSIS, view


def test_help_names_the_resolved_command_not_the_typed_prefix():
    # `resolve` steps over a partial word, so without the prefix descent this
    # would explain the `auto` group on the keystroke where you want `status`.
    assert view("auto sta", width=60, rows=4).plain.startswith("status")


def test_an_ambiguous_prefix_explains_the_group_instead_of_guessing():
    root = click.Group("tb")
    root.add_command(click.Command("drift", short_help="one"))
    root.add_command(click.Command("drain", short_help="two"))

    # Both start with "dr"; picking either would be a coin toss shown as fact.
    from cli.tui import help as module

    text = module._descend(root, "dr")
    assert text is root


def test_a_group_lists_its_subcommands_with_their_one_liners():
    text = view("auto ", width=70, rows=8).plain
    assert "install" in text and "systemd user units" in text


def test_a_command_lists_its_options_with_their_help():
    text = view("auto log", width=70, rows=6).plain
    assert "--limit" in text and "How many runs to show" in text


def test_the_pane_is_derived_from_the_tree_not_a_table():
    """A command added to a group appears with no change to help.py."""
    from cli import cli

    group = cli.commands["auto"]
    group.add_command(click.Command("invented", short_help="not written down anywhere"))
    try:
        text = view("auto ", width=70, rows=8).plain
        assert "invented" in text and "not written down anywhere" in text
    finally:
        del group.commands["invented"]


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
