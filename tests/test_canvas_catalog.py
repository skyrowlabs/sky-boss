"""The palette is derived, never written down.

This is the invariant carried over from the TUI, and the reason it is worth a
test file of its own is that the failure is silent and confident: a hardcoded
catalog does not break, it simply starts offering a command that no longer
exists, with a description of what it used to do.
"""

import rich_click as click

from cli.canvas.catalog import catalog, walk


def _tree():
    """A tree with the shape the real one does not have.

    sky.boss is two leaf commands, one of which is the surface itself, so there is no
    group here to walk and no nesting to flatten. `catalog` takes an injectable
    root for exactly this reason.
    """
    root = click.Group("sb")
    group = click.Group("auto")
    log = click.Command("log", short_help="Recent runs of a job.")
    log.params.append(click.Option(["--limit"], default=10, help="How many."))
    log.params.append(click.Option(["--failed"], is_flag=True, help="Only failures."))
    log.params.append(click.Argument(["job"]))
    group.add_command(log)
    group.add_command(click.Command("status", short_help="Last outcome per job."))
    root.add_command(group)
    root.add_command(click.Command("run", short_help="Run a command."))
    return root


def test_a_nested_command_is_named_by_its_whole_path():
    names = [entry["name"] for entry in walk(_tree())]
    assert "auto log" in names and "auto status" in names


def test_a_group_is_not_itself_an_entry():
    """Opening a window on `auto` would run nothing and show nothing."""
    assert "auto" not in [entry["name"] for entry in walk(_tree())]


def test_a_group_that_runs_bare_is_also_a_leaf():
    """`sb tools` with no subcommand renders the tools listing, so the group
    is a runnable entry as well as a container — a window may hold the listing
    open. A plain group still is not one; the test above stands."""
    root = click.Group("sb")
    group = click.Group("tools", invoke_without_command=True)
    group.short_help = "List the tools."
    group.add_command(click.Command("prs", short_help="open PRs"))
    root.add_command(group)
    names = [entry["name"] for entry in walk(root)]
    assert "tools" in names and "tools prs" in names


def test_the_real_tree_offers_the_bare_tools_listing():
    assert "tools" in [entry["name"] for entry in catalog()]


def test_options_become_chips_and_arguments_do_not():
    """A chip inserts a flag. Inserting a positional would build an argv the
    operator never meant, in a position that changes what the command reads."""
    entry = next(e for e in walk(_tree()) if e["name"] == "auto log")
    flags = [option["flag"] for option in entry["options"]]
    assert flags == ["--limit", "--failed"]
    assert "job" not in flags


def test_help_is_not_offered_as_a_chip():
    entry = next(e for e in walk(_tree()) if e["name"] == "auto log")
    assert "--help" not in [option["flag"] for option in entry["options"]]


def test_only_run_is_marked_as_acting():
    """The rule the whole design rests on, in the one place the surface reads
    it: a read may be given a refresh cadence and a write may not."""
    entries = {e["name"]: e for e in walk(_tree())}
    assert entries["run"]["acts"] is True
    assert entries["auto log"]["acts"] is False


def test_a_surface_is_not_in_its_own_palette():
    root = click.Group("sb")
    surface = click.Command("ui", short_help="Open the canvas.")
    surface.sb_surface = True
    root.add_command(surface)
    root.add_command(click.Command("run", short_help="Run a command."))

    assert [e["name"] for e in walk(root)] == ["run"]


def test_the_real_tree_offers_run_and_not_the_canvas():
    """The stand-in above proves the mechanism; this proves it is wired to the
    CLI that actually exists."""
    names = [entry["name"] for entry in catalog()]
    assert "run" in names
    assert "ui" not in names


def test_a_command_added_to_the_tree_appears_with_no_change_here():
    from cli import cli

    cli.add_command(click.Command("invented", short_help="not written down anywhere"))
    try:
        entry = next(e for e in catalog() if e["name"] == "invented")
        assert entry["summary"] == "not written down anywhere"
    finally:
        del cli.commands["invented"]


def test_a_summary_is_a_paragraph_not_a_line():
    """A docstring is hard-wrapped by whoever wrote it, so its first *line*
    ends wherever eighty columns landed.

    The palette hid that behind an ellipsis and nobody noticed for months; the
    bench's reference rail draws it in full, where a sentence stopping
    mid-clause reads as a bug in the help rather than in the splitting.
    """

    @click.command(name="wrapped")
    def wrapped():
        """Read another CLI's output as data. An observe — a window
        may pin it and refresh it.

        A second paragraph, which is not the summary.
        """

    entry = walk(wrapped, ("wrapped",))[0]
    assert entry["summary"] == (
        "Read another CLI's output as data. An observe — a window may pin it and "
        "refresh it."
    )


def test_a_summary_never_ends_on_a_colon_it_cannot_keep():
    """A paragraph ending in a colon is introducing an example that is not in
    the summary, so the colon is a promise with nothing behind it."""

    @click.command(name="colon")
    def colon():
        """Follow a file that grows. An observe, resident by nature:

        `sb follow` build.log
        """

    assert walk(colon, ("colon",))[0]["summary"] == "Follow a file that grows."


def test_a_hidden_option_is_not_offered():
    """`--help` does not list it, so neither may a surface that claims to be
    reading the same help. `sb run --refresh` is the real case: it exists only
    to refuse an act a cadence with a readable message."""

    @click.command(name="quiet")
    @click.option("--shown", help="visible")
    @click.option("--secret", hidden=True)
    def quiet():
        """A command with something up its sleeve."""

    flags = [o["flag"] for o in walk(quiet, ("quiet",))[0]["options"]]
    assert flags == ["--shown"]


def test_the_real_run_does_not_offer_its_refusal_flag():
    from cli import cli as root

    entry = next(e for e in catalog(root) if e["name"] == "run")
    assert "--refresh" not in [o["flag"] for o in entry["options"]]
