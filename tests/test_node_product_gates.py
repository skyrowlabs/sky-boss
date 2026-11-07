"""`check pre-push` runs the product's npm scripts, and a declared one cannot quietly go."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import EXIT_NO_SUBJECT, EXIT_REFUSED, Declared  # noqa: E402
from tests.shell import module  # noqa: E402

check = module("check")


def rows_for(tmp_path, monkeypatch, manifest, codes=None):
    ran = []

    def fake_run(argv):
        ran.append(argv[-1])
        return SimpleNamespace(returncode=(codes or {}).get(argv[-1], 0))

    (tmp_path / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(check, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(check, "run", fake_run)
    return dict(check._node_products()), ran


def test_no_manifest_is_no_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(check, "PROJECT_ROOT", tmp_path)
    assert check._node_products() == []


def test_an_undeclared_missing_script_has_no_subject_and_only_that_passes(tmp_path, monkeypatch):
    rows, ran = rows_for(tmp_path, monkeypatch, {"scripts": {}})
    assert ran == []
    for name in check.NODE_PRODUCT_SCRIPTS:
        code = rows[f"npm {name}"]
        assert isinstance(code, Declared) and code == EXIT_NO_SUBJECT


def test_a_declared_missing_script_is_refused(tmp_path, monkeypatch):
    rows, _ = rows_for(tmp_path, monkeypatch, {"scripts": {}, "skeletor": {"requiredScripts": ["test"]}})
    assert rows["npm test"] == EXIT_REFUSED and not isinstance(rows["npm test"], Declared)


def test_a_present_script_runs_and_its_failure_is_its_own(tmp_path, monkeypatch):
    manifest = {"scripts": {"test": "x", "build": "y", "format:check": "z"}}
    rows, ran = rows_for(tmp_path, monkeypatch, manifest, {"test": 1})
    assert ran == ["format:check", "test", "build"]
    assert rows["npm test"] == 1 and rows["npm build"] == 0 and rows["prettier"] == 0


def test_a_manifest_that_cannot_be_read_is_refused(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(check, "PROJECT_ROOT", tmp_path)
    assert check._node_products() == [("package.json", EXIT_REFUSED)]


def test_the_job_helper_agrees_when_node_is_here(tmp_path):
    helper = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "node-gate.cjs"
    (tmp_path / "package.json").write_text('{"skeletor": {"requiredScripts": ["test"]}}', encoding="utf-8")
    try:
        declared = subprocess.run(["node", str(helper), "test"], cwd=tmp_path, capture_output=True, text=True)
        undeclared = subprocess.run(["node", str(helper), "build"], cwd=tmp_path, capture_output=True, text=True)
    except FileNotFoundError:
        return
    assert declared.returncode == EXIT_REFUSED
    assert undeclared.returncode == 0 and "no subject" in undeclared.stderr
