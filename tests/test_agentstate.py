"""The agent-state root — [[state-root]].

The properties worth defending are that sky.boss never invents this path, that
the two levels resolve in an order a redirected test run depends on, and that a
missing directory says which of the several possible things went wrong.
"""

from pathlib import Path

import pytest

from cli import agentstate


@pytest.fixture
def home(tmp_path):
    """A `$SB_HOME` per test, rather than the suite-wide `home` fixture.

    That one is a single directory shared by every test in the run, which is
    right for reading an empty home and wrong the moment a test *writes* a
    `projects.toml` into it — two of these do, and they polluted the tests that
    expect no root declared. Passing a home in is free here because every
    function in this module already takes one.
    """
    path = tmp_path / "sb-home"
    path.mkdir()
    return path


def test_no_root_declared_is_not_an_error(home):
    """Same rule an absent `$SB_HOME` follows. A fresh clone has no state root
    and saying so every invocation would be noise."""
    found = agentstate.root(home)
    assert found.path is None
    assert not found
    assert found.source == ""


def test_sky_boss_never_defaults_to_the_workspace_layout(home, monkeypatch):
    """The writers each default to `~/src/sl-agent-logs`. Copying that
    would bake one machine's layout into a published tool — the same class of
    leak as a host name in a tracked file."""
    monkeypatch.delenv("SL_AGENT_LOGS", raising=False)
    assert agentstate.root(home).path is None


def test_the_environment_supplies_the_root(tmp_path, home, monkeypatch):
    monkeypatch.setenv("SL_AGENT_LOGS", str(tmp_path))
    found = agentstate.root(home)
    assert found.path == tmp_path
    assert found.source == "SL_AGENT_LOGS"


def test_projects_toml_supplies_it_when_the_environment_does_not(tmp_path, home, monkeypatch):
    monkeypatch.delenv("SL_AGENT_LOGS", raising=False)
    (home / "projects.toml").write_text(f'state_root = "{tmp_path}"\n')
    found = agentstate.root(home)
    assert found.path == tmp_path
    assert found.source == "projects.toml"


def test_the_environment_wins_over_the_file(tmp_path, home, monkeypatch):
    """The case that decides the order is a redirected run. Point the env at a
    scratch directory and the producers write there; if the file won, sky.boss
    would keep reading the real root and report a ledger nothing was writing
    to — mismatched, and silently."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (home / "projects.toml").write_text('state_root = "/declared/in/the/file"\n')
    monkeypatch.setenv("SL_AGENT_LOGS", str(scratch))
    found = agentstate.root(home)
    assert found.path == scratch
    assert found.source == "SL_AGENT_LOGS"


def test_the_root_is_read_at_use_not_frozen_at_import(tmp_path, home, monkeypatch):
    """The trap `agent-state.md` names by hand, and the reason it names it: a
    root frozen at import is a root a test cannot redirect — and a pinned
    window that never sees the operator's edit."""
    monkeypatch.setenv("SL_AGENT_LOGS", str(tmp_path / "first"))
    assert agentstate.root(home).path == tmp_path / "first"
    monkeypatch.setenv("SL_AGENT_LOGS", str(tmp_path / "second"))
    assert agentstate.root(home).path == tmp_path / "second"


def test_an_empty_environment_value_falls_through_rather_than_meaning_root(home, monkeypatch):
    monkeypatch.setenv("SL_AGENT_LOGS", "   ")
    assert agentstate.root(home).path is None


def test_a_tilde_in_the_declared_root_expands(home, monkeypatch):
    monkeypatch.delenv("SL_AGENT_LOGS", raising=False)
    (home / "projects.toml").write_text('state_root = "~/logs"\n')
    assert agentstate.root(home).path == Path.home() / "logs"


# ── the derivation ───────────────────────────────────────────────────────────


def _root_with(tmp_path, monkeypatch, *slugs) -> Path:
    root = tmp_path / "state"
    root.mkdir()
    for slug in slugs:
        (root / slug).mkdir()
    monkeypatch.setenv("SL_AGENT_LOGS", str(root))
    return root


def test_a_project_directory_that_exists_is_returned(tmp_path, home, monkeypatch):
    root = _root_with(tmp_path, monkeypatch, "jam-sense")
    assert agentstate.directory("jam-sense", home).path == root / "jam-sense"


def test_a_missing_directory_names_the_ones_that_are_there(tmp_path, home, monkeypatch):
    """The whole reason to list rather than report absence. An operator who
    wrote `[project.jam]` for brevity otherwise gets *nothing to follow* — the
    exact sentence a project with no logs yet gets."""
    _root_with(tmp_path, monkeypatch, "jam-sense", "breeze-brain")
    found = agentstate.directory("jam", home)
    assert found.path is None
    assert "no state directory 'jam'" in found.problem
    assert "breeze-brain, jam-sense" in found.problem


def test_an_empty_root_says_so_rather_than_listing_nothing(tmp_path, home, monkeypatch):
    _root_with(tmp_path, monkeypatch)
    assert "the root is empty" in agentstate.directory("jam-sense", home).problem


def test_a_root_that_is_not_there_is_a_different_sentence(tmp_path, home, monkeypatch):
    """A wrong path and a missing machine want different fixes, so the message
    names which it is — and names the level it came from."""
    monkeypatch.setenv("SL_AGENT_LOGS", str(tmp_path / "nope"))
    problem = agentstate.directory("jam-sense", home).problem
    assert "is not a directory" in problem
    assert "SL_AGENT_LOGS" in problem


def test_no_root_at_all_names_both_ways_to_declare_one(home, monkeypatch):
    monkeypatch.delenv("SL_AGENT_LOGS", raising=False)
    problem = agentstate.directory("jam-sense", home).problem
    assert "SL_AGENT_LOGS" in problem and "state_root" in problem


# ── the address form ─────────────────────────────────────────────────────────


@pytest.fixture
def declared(home, tmp_path, monkeypatch):
    """A home declaring two projects, and a root holding one of them."""
    (home / "projects.toml").write_text(
        'state_root = "{root}"\n\n'
        "[project.jam-sense]\nargv = [\"jam\", \"status\"]\n\n"
        "[project.breeze-brain]\nargv = [\"bbrain\", \"status\"]\n".format(
            root=tmp_path / "state"
        )
    )
    monkeypatch.setenv("SB_HOME", str(home))
    monkeypatch.delenv("SL_AGENT_LOGS", raising=False)
    (tmp_path / "state" / "jam-sense" / "ledger").mkdir(parents=True)
    return tmp_path / "state"


def test_a_project_reference_resolves_to_a_real_path(declared, home):
    path, problem = agentstate.resolve("jam-sense:ledger/runs.jsonl", home)
    assert problem is None
    assert path == str(declared / "jam-sense" / "ledger" / "runs.jsonl")


def test_a_bare_reference_is_the_state_directory_itself(declared, home):
    path, problem = agentstate.resolve("jam-sense:", home)
    assert (path, problem) == (str(declared / "jam-sense"), None)


def test_an_ordinary_path_passes_through_untouched(declared, home):
    """This sits on the path of every file read, so it has to be inert for the
    ordinary case."""
    assert agentstate.resolve("ledger/runs.jsonl", home) == ("ledger/runs.jsonl", None)
    assert agentstate.resolve("/var/log/syslog", home) == ("/var/log/syslog", None)


def test_an_undeclared_prefix_is_not_a_reference(declared, home):
    """The set of project names is closed and operator-authored, so a prefix
    outside it is not an address — the string stays the literal path it always
    was. This can never take an address away from someone not asking for one."""
    assert agentstate.resolve("jam:ledger/runs.jsonl", home) == ("jam:ledger/runs.jsonl", None)
    assert not agentstate.is_project_form("jam:ledger/runs.jsonl", home)


def test_a_declared_project_with_no_state_directory_names_what_is_there(declared, home):
    path, problem = agentstate.resolve("breeze-brain:ledger/runs.jsonl", home)
    assert path == "breeze-brain:ledger/runs.jsonl"
    assert "no state directory 'breeze-brain'" in problem
    assert "the root holds jam-sense" in problem


def test_an_existing_file_wins_over_the_project_reading(declared, home, tmp_path, monkeypatch):
    """Same precedence `is_file_form` applies when a bare word is both an
    executable and a file: the concrete thing wins."""
    monkeypatch.chdir(tmp_path)
    weird = tmp_path / "jam-sense:ledger"
    weird.mkdir()
    (weird / "runs.jsonl").write_text("{}\n")
    assert agentstate.resolve("jam-sense:ledger/runs.jsonl", home)[0] == "jam-sense:ledger/runs.jsonl"


def test_a_reference_with_no_separator_is_still_the_file_form(declared, home):
    """`jam-sense:runs.jsonl` has no slash and would otherwise fall through to
    the argv side and be reported as a missing command."""
    assert agentstate.is_project_form("jam-sense:runs.jsonl", home)


def test_the_hint_explains_why_the_other_reading_did_not_happen(declared, home):
    hint = agentstate.unresolved_hint("jam:log/cron.log", home)
    assert "no project 'jam' is declared" in hint
    assert "breeze-brain, jam-sense" in hint


def test_no_hint_for_a_declared_project_or_an_ordinary_path(declared, home):
    assert agentstate.unresolved_hint("jam-sense:log/cron.log", home) == ""
    assert agentstate.unresolved_hint("ledger/runs.jsonl", home) == ""
    assert agentstate.unresolved_hint("/var/log/syslog", home) == ""


def test_a_colon_after_a_slash_is_not_a_prefix(declared, home):
    """`./weird:name` is a path with a colon in its basename, not an address."""
    assert agentstate.unresolved_hint("logs/weird:name.txt", home) == ""
