"""The roll-call — many projects, one answer.

Every test here runs against a redirected `TB_HOME` (conftest sets it before
anything imports `cli`). That matters more than usual: a project is a source tb
will *run*, so a suite reading the real home would be shelling out to whatever
the operator happens to have declared.
"""

import json

import pytest
from click.testing import CliRunner

from cli import cli
from cli.rollcall import load, parse, read


def write(home, text):
    home.mkdir(parents=True, exist_ok=True)
    (home / "projects.toml").write_text(text)


# ── The registry ────────────────────────────────────────────────────────────
#
# One bad entry must not cost the operator the other five, so the malformed
# cases come first — they are what the loader exists to survive.


def test_a_malformed_project_is_named_and_skipped(tmp_path):
    write(tmp_path, """
[project.good]
argv = ["echo", "{}"]

[project.bad]
description = "declares no source at all"
""")
    projects, problems = load(tmp_path)
    assert [p.name for p in projects] == ["good"]
    assert len(problems) == 1 and "bad" in problems[0]


def test_declaring_both_a_command_and_a_file_is_refused(tmp_path):
    """Two different claims about where this project's truth lives. Picking one
    would be tb guessing which the operator meant."""
    write(tmp_path, """
[project.both]
argv = ["echo"]
path = "/tmp/x.json"
""")
    projects, problems = load(tmp_path)
    assert projects == []
    assert "argv and path" in problems[0]


def test_an_unparseable_file_is_reported_rather_than_raised(tmp_path):
    write(tmp_path, "this is not toml {{{")
    projects, problems = load(tmp_path)
    assert projects == []
    assert problems and "projects.toml" in problems[0]


def test_an_absent_file_declares_nothing_and_says_nothing(tmp_path):
    """A fresh clone federates over no projects. Warning about it every
    invocation would be noise, so absence is not a problem to report."""
    projects, problems = load(tmp_path / "nowhere")
    assert projects == []
    assert problems == []


def test_a_declared_project_keeps_its_reading_options(tmp_path):
    write(tmp_path, """
[project.jam]
argv = ["jam", "report", "status", "--json"]
cwd = "~/src/jam.sense"
rows = "jobs"
cols = "job,result"
""")
    (project,) = load(tmp_path)[0]
    assert project.argv[0] == "jam"
    assert project.rows == "jobs"
    assert project.cols == "job,result"
    assert project.from_ == "json"


def test_parse_reads_no_file():
    """Pure, like every other deciding half here."""
    projects, problems = parse({"project": {"a": {"path": "/tmp/a.json"}}})
    assert projects[0].path == "/tmp/a.json"
    assert problems == []
