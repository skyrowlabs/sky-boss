"""`scripts/install_project.py` installs the project only when it is one, with every extra."""

from __future__ import annotations

import pytest

from scripts import install_project

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "text,expected",
    [
        (None, None),
        ("[tool.black]\nline-length = 88\n", None),
        ('[project]\nname = "x"\n', "."),
        ('[project]\nname = "x"\n[project.optional-dependencies]\ntest = ["a"]\ndev = ["b"]\n', ".[dev,test]"),
    ],
    ids=["no file", "no project", "bare", "every extra"],
)
def test_the_target_follows_the_project_block(tmp_path, monkeypatch, text, expected):
    pyproject = tmp_path / "pyproject.toml"
    if text is not None:
        pyproject.write_text(text, encoding="utf-8")
    monkeypatch.setattr(install_project, "PYPROJECT", pyproject)
    assert install_project.target() == expected


def test_a_malformed_file_fails_rather_than_installing_nothing(tmp_path, monkeypatch):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project\n", encoding="utf-8")
    monkeypatch.setattr(install_project, "PYPROJECT", pyproject)
    with pytest.raises(ValueError):
        install_project.target()
