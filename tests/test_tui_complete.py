"""Tests for tab completion.

What matters is that the candidates come from the tree and the registries
rather than a list written here. A completion that drifts from the CLI is worse
than none, because it teaches a verb that does not exist.
"""

from cli.tui.complete import candidates, complete


def test_an_empty_line_offers_the_top_level_and_the_surface_verbs():
    """Surface verbs are typed like any other word, so they complete like one.

    They are not Click commands — they render something already in hand rather
    than dispatching — but a thing you can type and cannot complete is worse
    than one that does not exist.
    """
    from cli import cli
    from cli.tui.verbs import names as surface_verbs

    offered = candidates("")[1]
    assert offered == sorted(set(cli.commands) | set(surface_verbs()))
    assert set(cli.commands) <= set(offered)


def test_a_surface_verb_can_never_shadow_a_real_command():
    """The worst drift available here: typing a real command and silently
    getting something else. The tree is asked first; the verb table only sees
    words Click has no answer for."""
    from cli import cli
    from cli.tui.verbs import names as surface_verbs

    assert not (set(surface_verbs()) & set(cli.commands))


def _tree():
    """A stand-in with the shape the real tree no longer has — tb is two leaf
    commands, so a group walk has nothing to walk. `candidates` takes the same
    injectable root `dispatch` does."""
    import rich_click as click

    root = click.Group("tb")
    group = click.Group("auto")
    for name in ("list", "log", "status"):
        group.add_command(click.Command(name, short_help=name))
    log = group.commands["log"]
    log.params.append(click.Option(["--run"], help="Show one run's output."))
    root.add_command(group)
    root.add_command(click.Command("run", short_help="run"))
    return root


def test_a_group_offers_its_own_subcommands():
    tree = _tree()
    assert candidates("auto ", tree)[1] == sorted(tree.commands["auto"].commands)


def test_the_leading_tb_is_tolerated():
    assert candidates("tb check ")[1] == candidates("check ")[1]






def test_a_dash_switches_to_options():
    offered = candidates("auto log --")[1]
    assert "--help" in offered and "--json" in offered
    assert "assets" not in offered


def test_options_still_complete_after_a_positional():
    # The walk steps over anything that is not a subcommand, so a typed
    # argument value does not strand the resolution.
    assert "--run" in candidates("auto log something --", _tree())[1]


# ------------------------------------------------------------------ applying


def test_a_single_match_is_filled_in_with_a_trailing_space():
    assert complete("ru") == ("run ", [])


def test_several_matches_extend_as_far_as_they_agree():
    line, matches = complete("auto l", _tree())
    assert line == "auto l"
    assert set(matches) == {"list", "log"}


def test_an_unknown_prefix_changes_nothing():
    assert complete("zzz") == ("zzz", [])


def test_a_half_typed_quote_does_not_raise():
    # shlex would; while typing, an unbalanced quote is completely normal and
    # must not turn Tab into a dead key.
    assert complete("run 'half") == ("run 'half", [])
