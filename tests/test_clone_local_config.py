"""The clone-local settings a tracked file implies are discovered and checked.

`.gitattributes` routes paths through `merge=<name>` drivers whose definitions
live in `.git/config`, and a tracked `.gitmessage` is a claim that
`commit.template` points at it. Neither survives a clone. The checker tested
one constant, so a second driver named in `.gitattributes` and defined nowhere
passed; and nothing ever set `commit.template`, which was unset in five of six
adopter clones when measured.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.git import install_merge_drivers as imd

pytestmark = pytest.mark.unit


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def clone(tmp_path, monkeypatch):
    """A fresh repository with the template's attributes and message file, nothing installed."""
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitattributes").write_text("generated/x.json merge=regen-docs\n", encoding="utf-8")
    (tmp_path / ".gitmessage").write_text("# subject\n", encoding="utf-8")
    monkeypatch.setattr(imd, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(imd, "ATTRIBUTES", tmp_path / ".gitattributes")
    monkeypatch.setattr(imd, "MESSAGE_TEMPLATE", tmp_path / ".gitmessage")
    monkeypatch.setattr(imd, "MARKER", tmp_path / "tmp" / ".regen-owed")
    return tmp_path


def _check(monkeypatch) -> int:
    monkeypatch.setattr(sys, "argv", ["install_merge_drivers.py", "--check"])
    return imd.main()


def _said(capsys) -> str:
    """Both streams: the output contract puts the explanation on stderr."""
    captured = capsys.readouterr()
    return captured.out + captured.err


def _install(monkeypatch) -> int:
    monkeypatch.setattr(sys, "argv", ["install_merge_drivers.py"])
    return imd.main()


def test_the_declared_drivers_are_read_from_gitattributes(clone):
    (clone / ".gitattributes").write_text("a merge=regen-docs\nb merge=other\n# c merge=not-this\n", encoding="utf-8")
    assert imd.declared_drivers() == {"regen-docs", "other"}


def test_a_fresh_clone_is_red_and_the_installer_makes_it_green(clone, monkeypatch, capsys):
    assert _check(monkeypatch) == 1
    assert "regen-docs" in _said(capsys)
    assert _install(monkeypatch) == 0
    assert _git(clone, "config", "--local", "commit.template") == ".gitmessage"
    assert _check(monkeypatch) == 0


def test_a_driver_named_but_not_defined_is_red(clone, monkeypatch, capsys):
    _install(monkeypatch)
    with (clone / ".gitattributes").open("a", encoding="utf-8") as handle:
        handle.write("foo.txt merge=foo\n")
    assert _check(monkeypatch) == 1
    assert "foo" in _said(capsys)


def test_an_unset_commit_template_is_red(clone, monkeypatch, capsys):
    _install(monkeypatch)
    _git(clone, "config", "--local", "--unset", "commit.template")
    assert _check(monkeypatch) == 1
    assert "commit.template" in _said(capsys)
