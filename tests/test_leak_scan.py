"""`leak_scan.py` proves the pin through pre-commit's database, and any miss takes the old failure."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import leak_scan  # noqa: E402
from scripts.output import EXIT_REFUSED  # noqa: E402

PIN = "8.30.1"


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """A pre-commit cache holding one built gitleaks at the pinned rev."""
    monkeypatch.setenv("PRE_COMMIT_HOME", str(tmp_path))
    binary = tmp_path / "repoabc" / "golangenv-default" / "bin" / "gitleaks"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    record(tmp_path, f"v{PIN}", tmp_path / "repoabc")
    return tmp_path


def record(home: Path, ref: str, path: Path) -> None:
    with sqlite3.connect(home / "db.db") as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS repos (repo TEXT, ref TEXT, path TEXT)")
        connection.execute("DELETE FROM repos")
        connection.execute("INSERT INTO repos VALUES (?, ?, ?)", (leak_scan.GITLEAKS_REPO, ref, str(path)))
    connection.close()


def test_the_binary_built_at_the_pinned_rev_is_found(cache):
    assert leak_scan.prebuilt_binary(PIN) == str(cache / "repoabc" / "golangenv-default" / "bin" / "gitleaks")


def test_another_rev_is_a_miss_even_with_the_binary_there(cache):
    assert leak_scan.prebuilt_binary("8.99.0") is None
    record(cache, "v8.29.0", cache / "repoabc")
    assert leak_scan.prebuilt_binary(PIN) is None


def test_a_database_of_another_shape_is_a_miss(cache):
    (cache / "db.db").unlink()
    with sqlite3.connect(cache / "db.db") as connection:
        connection.execute("CREATE TABLE repos (other TEXT)")
    connection.close()
    assert leak_scan.prebuilt_binary(PIN) is None


def test_no_database_and_a_path_with_no_binary_are_misses(cache):
    record(cache, f"v{PIN}", cache / "gone")
    assert leak_scan.prebuilt_binary(PIN) is None
    (cache / "db.db").unlink()
    assert leak_scan.prebuilt_binary(PIN) is None


def test_the_query_never_writes_the_database(cache):
    before = (cache / "db.db").read_bytes()
    leak_scan.prebuilt_binary(PIN)
    assert (cache / "db.db").read_bytes() == before


def test_any_miss_with_nothing_on_path_refuses(cache, monkeypatch):
    (cache / "db.db").unlink()
    monkeypatch.setattr(leak_scan.shutil, "which", lambda name: None)
    monkeypatch.setattr(sys, "argv", ["leak_scan.py", "--range", "HEAD"])
    assert leak_scan.main() == EXIT_REFUSED


def test_the_run_says_which_binary_and_rev_it_used(cache, monkeypatch, capsys):
    monkeypatch.setattr(leak_scan, "pinned_version", lambda: PIN)
    monkeypatch.setattr(leak_scan, "scan", lambda binary, commit_range: (0, [], ""))
    monkeypatch.setattr(sys, "argv", ["leak_scan.py", "--range", "HEAD"])
    assert leak_scan.main() == 0
    said = capsys.readouterr().err
    assert f"v{PIN}, by pre-commit" in said and "repoabc" in said


def test_a_green_scan_counts_the_commits_it_read(cache, monkeypatch, capsys):
    monkeypatch.setattr(leak_scan, "commits_in", lambda commit_range: 3)
    monkeypatch.setattr(leak_scan, "scan", lambda binary, commit_range: (0, [], ""))
    monkeypatch.setattr(sys, "argv", ["leak_scan.py", "--range", "a..b"])
    assert leak_scan.main() == 0
    assert "no secrets in 3 commit(s) of a..b" in capsys.readouterr().err


def test_an_empty_range_scans_nothing_and_says_so(monkeypatch, capsys):
    monkeypatch.setattr(leak_scan.shutil, "which", lambda name: None)
    monkeypatch.setattr(leak_scan, "prebuilt_binary", lambda version: None)
    monkeypatch.setattr(sys, "argv", ["leak_scan.py", "--range", "HEAD..HEAD", "--json"])
    assert leak_scan.main() == 0
    captured = capsys.readouterr()
    assert "no subject" in captured.err and json.loads(captured.out)["scanned"] is False


def test_a_range_git_cannot_resolve_is_refused(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["leak_scan.py", "--range", "no-such-ref..HEAD"])
    assert leak_scan.main() == EXIT_REFUSED
