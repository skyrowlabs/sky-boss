"""The seam between the product and the operator's content.

This repo holds what the project wrote. `TB_HOME` holds what you wrote.
`STATE_DIR` holds what the machine wrote. Mixing the first two is how a tailnet
address ends up in a public commit, which is not hypothetical — it had already
happened when this was written.
"""

import os
import re
from pathlib import Path

import pytest

from cli.helpers import PROJECT_ROOT, STATE_DIR, TB_HOME

# The directories that belong to whoever runs tb, not to this project.
OPERATOR_DIRS = ("inventory", "jobs", "watches")


def test_the_three_homes_are_distinct():
    """Each has one rule — who authored the bytes in it."""
    assert TB_HOME != PROJECT_ROOT
    assert STATE_DIR != TB_HOME
    # And the operator's content is not inside the product, which is the whole
    # point: the product can be published without publishing the operator.
    assert PROJECT_ROOT not in TB_HOME.parents


def test_no_module_looks_for_operator_content_in_the_repo():
    """The failure this prevents is silent rather than loud.

    A leftover `PROJECT_ROOT / "inventory"` keeps working perfectly on the one
    machine that still has the old directory, and reads nothing everywhere
    else — including after a move, which is the point this repo is heading for.
    """
    pattern = re.compile(
        r'PROJECT_ROOT\s*/\s*[\'"](' + "|".join(OPERATOR_DIRS) + r')[\'"]'
    )
    offenders = {}
    for path in sorted((PROJECT_ROOT / "cli").rglob("*.py")):
        found = pattern.findall(path.read_text())
        if found:
            offenders[str(path.relative_to(PROJECT_ROOT))] = found
    assert not offenders, f"operator content still read from the repo: {offenders}"


def test_the_repo_ships_no_operator_content():
    """Templates are the project's; filled-in records are not."""
    present = [name for name in OPERATOR_DIRS if (PROJECT_ROOT / name).is_dir()]
    assert not present, (
        f"{present} still in the repo — these are the operator's and belong in TB_HOME"
    )


def test_tb_home_honours_the_environment(monkeypatch, tmp_path):
    """So a test suite, a second machine, or a throwaway can point elsewhere.

    Resolved at import, so this reloads rather than reassigning — which is also
    the reason tests/conftest.py sets it before anything imports cli.
    """
    import importlib

    monkeypatch.setenv("TB_HOME", str(tmp_path / "elsewhere"))
    helpers = importlib.reload(importlib.import_module("cli.helpers"))
    try:
        assert helpers.TB_HOME == tmp_path / "elsewhere"
    finally:
        monkeypatch.delenv("TB_HOME", raising=False)
        monkeypatch.setenv("TB_HOME", os.environ.get("TB_HOME", str(TB_HOME)))
        importlib.reload(helpers)


def test_the_default_home_is_not_under_xdg_config():
    """It is a worktree you cd into and commit in, not a config file."""
    import importlib

    saved = os.environ.pop("TB_HOME", None)
    try:
        helpers = importlib.reload(importlib.import_module("cli.helpers"))
        assert helpers.TB_HOME == Path.home() / ".tackle-box"
    finally:
        if saved is not None:
            os.environ["TB_HOME"] = saved
        importlib.reload(importlib.import_module("cli.helpers"))


@pytest.mark.parametrize("loader", ["cli.jobs.load_jobs", "cli.watch.load_watches"])
def test_every_loader_survives_an_absent_home(loader, monkeypatch, tmp_path):
    """A fresh clone has no home at all. The surface asks for jobs and watches
    on its first tick, before you have written any — a raise there takes the
    whole thing down on first run."""
    import importlib

    module_name, attribute = loader.rsplit(".", 1)
    module = importlib.import_module(module_name)
    found, problems = getattr(module, attribute)(tmp_path / "does-not-exist")
    assert found == {} and problems == []


# ------------------------------------------------------------- the scaffold


def test_scaffolding_creates_a_home_that_every_loader_reads_cleanly(tmp_path):
    from cli.home import init_home
    from cli.jobs import load_jobs
    from cli.watch import load_watches

    home = tmp_path / "fresh"
    made = init_home(home)

    assert set(made["created"]) >= {
        "inventory/_template.yaml",
        "jobs/_template.yaml",
        "watches/_template.yaml",
    }
    # A scaffolded home has templates and no definitions. Both loaders must
    # read it as empty rather than as broken — the templates are skipped by the
    # leading underscore, which is the only reason a first run is quiet.
    for loader, directory in ((load_jobs, "jobs"), (load_watches, "watches")):
        found, problems = loader(home / directory)
        assert found == {} and problems == [], f"{directory}: {problems}"


def test_scaffolding_refuses_an_occupied_home_rather_than_merging(tmp_path):
    """Overwriting is the one thing here that could destroy a machine record,
    and "it was already there" does not say what the caller wanted."""
    from cli.home import init_home

    home = tmp_path / "occupied"
    (home / "inventory").mkdir(parents=True)
    record = home / "inventory" / "workstation.yaml"
    record.write_text("declared:\n  note: irreplaceable\n")

    with pytest.raises(FileExistsError):
        init_home(home)
    assert record.read_text() == "declared:\n  note: irreplaceable\n"


def test_the_scaffold_is_reachable_only_through_run(tmp_path):
    """It writes, so it is ledgered like anything else that changes the world.
    A scaffold firing from a read command would be a write with no entry."""
    from cli.run import REGISTRY

    task = next((t for t in REGISTRY if t.name == "init-home"), None)
    assert task is not None, "init-home should be a tb run task"
    assert task.lane == "committing"


def test_the_templates_the_scaffold_copies_are_shipped(tmp_path):
    """They are the project's files. If one goes missing the scaffold still
    makes the directory, and you get a silently empty home instead."""
    from cli.home import LAYOUT, TEMPLATES

    missing = [name for _dir, name in LAYOUT if not (TEMPLATES / name).exists()]
    assert not missing, f"templates missing from the repo: {missing}"
