"""`test like-ci` reads the unit job out of ci.yml, and refuses what it cannot reproduce."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanning import scanned  # noqa: E402
from scripts import like_ci  # noqa: E402

pytestmark = pytest.mark.unit

SETUP = {"uses": like_ci.UNIT_SETUP, "with": {"python-version": "${{ matrix.python }}"}}
JOB = {
    "strategy": {"matrix": {"python": ["3.12", "3.13"]}},
    "env": {"STRICT": "1"},
    "steps": [{"run": "before setup"}, SETUP, {"run": "python -m pytest tests/ -m unit"}, {"run": "x"}],
}


def test_this_trees_unit_job_is_found_with_its_legs_installs_and_lines() -> None:
    _, job = like_ci.unit_job(yaml.safe_load(like_ci.CI.read_text(encoding="utf-8")))
    scanned(like_ci.interpreters(job), "matrix legs")
    scanned(like_ci.job_lines(job), "unit job run lines")
    installs = scanned(like_ci.install_lines(yaml.safe_load(like_ci.ACTION.read_text(encoding="utf-8"))), "installs")
    assert any("-r " in line for line in installs), installs


def test_the_matrix_is_expanded_and_the_lines_follow_the_setup() -> None:
    assert like_ci.interpreters(JOB) == ["3.12", "3.13"]
    assert like_ci.job_lines(JOB) == ["python -m pytest tests/ -m unit", "x"]
    assert like_ci.job_env(JOB) == {"STRICT": "1"}


def test_one_unit_job_or_a_refusal() -> None:
    with pytest.raises(like_ci.Refused, match="found 2"):
        like_ci.unit_job({"jobs": {"a": JOB, "b": JOB}})
    with pytest.raises(like_ci.Refused, match="found 0"):
        like_ci.unit_job({"jobs": {"a": {"steps": [{"run": "echo"}]}}})


def test_an_expression_the_host_cannot_evaluate_is_refused() -> None:
    held = {**JOB, "steps": [SETUP, {"run": "pytest -k ${{ inputs.k }}"}]}
    with pytest.raises(like_ci.Refused, match="expression"):
        like_ci.job_lines(held)
    with pytest.raises(like_ci.Refused, match="env"):
        like_ci.job_env({"env": {"TOKEN": "${{ secrets.X }}"}})
    unmatrixed = {"steps": [{"uses": like_ci.UNIT_SETUP, "with": {"python-version": "${{ env.PY }}"}}]}
    with pytest.raises(like_ci.Refused, match="cannot evaluate"):
        like_ci.interpreters(unmatrixed)


def test_a_venv_that_sees_system_packages_is_not_the_runners() -> None:
    assert like_ci.system_site_packages("home = /usr/bin\ninclude-system-site-packages = true\n")
    assert not like_ci.system_site_packages("home = /usr/bin\ninclude-system-site-packages = false\n")


def test_the_cache_key_moves_with_a_requirements_file(tmp_path) -> None:
    (tmp_path / "req.txt").write_text("a==1\n", encoding="utf-8")
    first = like_ci.cache_key("3.12", ["pip install -r req.txt"], tmp_path)
    (tmp_path / "req.txt").write_text("a==2\n", encoding="utf-8")
    assert like_ci.cache_key("3.12", ["pip install -r req.txt"], tmp_path) != first
    assert like_ci.cache_key("3.13", ["pip install -r req.txt"], tmp_path) != first


def test_no_taskset_is_a_refusal(monkeypatch) -> None:
    monkeypatch.setattr(like_ci.shutil, "which", lambda name: None)
    with pytest.raises(like_ci.Refused, match="taskset"):
        like_ci.plan(None)


def test_a_leg_outside_the_matrix_is_a_refusal(monkeypatch) -> None:
    monkeypatch.setattr(like_ci.shutil, "which", lambda name: "/usr/bin/" + name)
    with pytest.raises(like_ci.Refused, match="not a leg"):
        like_ci.plan("2.7")


def test_the_steps_run_in_a_copy_of_the_tracked_files(tmp_path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "kept.py").write_text("x = 1\n", encoding="utf-8")
    (root / "untracked.txt").write_text("no\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "kept.py"], check=True)
    copy = like_ci.checkout(root, tmp_path / "copy")
    assert (copy / "kept.py").read_text(encoding="utf-8") == "x = 1\n"
    assert not (copy / "untracked.txt").exists()
