"""Help is the doc. See [[refresh]].

The app documents itself: every command's `--help` carries its contract and a
runnable example, and the palette inherits the same strings through the
catalog, so nothing is written twice. This test walks the live tree — the
same no-command-table rule everything else here follows — so a command added
next year is born covered or fails loudly on its first run of the suite.
"""

import click

from cli import cli

# The vocabulary a contract is stated in. One of these words appearing is not
# proof of a good sentence, but its absence is proof of a missing one — a
# command that never says whether it acts or observes, or that it is a
# surface, has not stated its contract.
CONTRACT_WORDS = ("acts", "observe", "a read", "surface", "saved command")


def leaves(command=cli, path=("tb",)):
    """Every runnable leaf, surfaces included — `tb ui` excludes itself from
    the palette, not from the documentation standard. A group that runs bare
    (`tb tools`) is runnable, so it meets the standard too."""
    if isinstance(command, click.Group):
        if command.invoke_without_command:
            yield " ".join(path), command
        for name in sorted(command.commands):
            yield from leaves(command.commands[name], path + (name,))
    else:
        yield " ".join(path), command


def test_the_walk_sees_the_whole_surface():
    """If this shrinks, the two tests below are vacuously green."""
    names = {path for path, _ in leaves()}
    assert {"tb run", "tb read", "tb data", "tb tools", "tb ui"} <= names


def test_every_command_shows_a_runnable_example():
    """An indented `tb …` line in the help body — something the reader can
    paste. `--help` is where the operator actually looks; a doc that lives
    anywhere else goes stale the day the flag changes."""
    for path, command in leaves():
        lines = [line.strip() for line in (command.help or "").splitlines()]
        assert any(line.startswith("tb ") for line in lines), (
            f"{path} --help has no runnable example"
        )


def test_every_command_states_its_contract():
    """Acts or observes, once or resident — the temporal shape is the one
    fact a reader cannot infer from a flag list."""
    for path, command in leaves():
        text = (command.help or "").lower()
        assert any(word in text for word in CONTRACT_WORDS), (
            f"{path} --help does not state its contract"
        )


def test_a_saved_tool_is_born_covered(tmp_path):
    """The generated help carries the expansion as its example and names
    itself a saved command — tools meet the standard with no code in the
    loader growing an opinion about documentation."""
    from cli.tools import register

    (tmp_path / "tools.toml").write_text('[tool.prs]\nargv = ["data", "--", "printf", "[]"]\n')
    from cli.tools import tools as tools_group

    try:
        register(cli, home=tmp_path)
        found = dict(leaves())["tb tools prs"]
        lines = [line.strip() for line in found.help.splitlines()]
        assert any(line.startswith("tb data") for line in lines)
        assert "saved command" in found.help.lower()
    finally:
        for name in [
            n for n, c in list(tools_group.commands.items()) if getattr(c, "tb_saved", False)
        ]:
            del tools_group.commands[name]
