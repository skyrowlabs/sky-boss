"""`check_deleted_paths.py` finds a removed path where a reader would follow it, and nowhere else."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import check_deleted_paths as gate  # noqa: E402
from scripts.output import EXIT_GREEN, EXIT_RED  # noqa: E402


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "probe"
    root.mkdir()
    git(root, "init", "-q", "-b", "develop")
    for key, value in (("user.name", "t"), ("user.email", "t@example.invalid"), ("commit.gpgsign", "false")):
        git(root, "config", key, value)
    for rel in ("scripts/old.py", "install", "docs/TODO/plan.md", "tools/moved.sh"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: root")
    return root


def push(root: Path, files: dict[str, str], *, remove=(), move=()) -> str:
    """Commit one change on top of HEAD and return the range it is."""
    base = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    for rel in remove:
        git(root, "rm", "-q", rel)
    for old, new in move:
        (root / new).parent.mkdir(parents=True, exist_ok=True)
        git(root, "mv", old, new)
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: change")
    return f"{base}..HEAD"


def listed(root: Path) -> set[str]:
    found = gate.tracked(root)
    assert found is not None
    return found


def cited(root: Path, commit_range: str) -> list[tuple[str, str]]:
    present = listed(root)
    gone = gate.gone(root, commit_range, present)
    assert gone is not None
    return [(rel, path) for rel, _, path in gate.citations(root, gone, present)]


def test_a_deleted_path_is_found_in_both_spellings_and_never_as_a_suffix(repo):
    text = "run scripts/old.py\nsee probe/scripts/old.py.\nnot myscripts/old.py, scripts/old.pyc or old.py\n"
    span = push(repo, {"README.md": text, "ci.sh": "./install\ninstall it\n"}, remove=["scripts/old.py", "install"])
    assert sorted(cited(repo, span)) == [("README.md", "scripts/old.py")] * 2 + [("ci.sh", "install")]


def test_a_renamed_path_is_its_old_name(repo):
    span = push(repo, {"Makefile": "sh tools/moved.sh\n"}, move=[("tools/moved.sh", "bin/moved.sh")])
    assert cited(repo, span) == [("Makefile", "tools/moved.sh")]


def test_history_the_manifest_and_a_path_put_back_are_out_of_scope(repo):
    names = "scripts/old.py\n"
    span = push(repo, {"docs/TODO/plan.md": names, ".skeletor.json": names}, remove=["scripts/old.py"])
    assert cited(repo, span) == []
    restored = push(repo, {"scripts/old.py": "y\n", "README.md": names}, remove=["install"])
    assert gate.gone(repo, f"{span.split('..')[0]}..HEAD", listed(repo)) == ["install"]
    assert cited(repo, restored) == []


def test_an_entry_goes_stale_when_its_citation_or_its_deletion_does(repo):
    push(repo, {"README.md": "scripts/old.py\n"}, remove=["scripts/old.py"])
    entries = {key: "kept" for key in ("README.md:scripts/old.py", "README.md:install", "gone.md:scripts/old.py")}
    found = gate.stale(repo, {**entries, "README.md:tools/moved.sh": "kept"}, listed(repo))
    assert [line.split(":")[1] for line in found] == ["install", "tools/moved.sh", "scripts/old.py"]


def test_an_allowlisted_citation_passes_and_a_bare_one_fails(repo, monkeypatch, capsys):
    span = push(repo, {"README.md": "scripts/old.py\n"}, remove=["scripts/old.py"])
    allowed = repo / "scripts" / "deleted_paths_allowlist.yaml"
    allowed.parent.mkdir(exist_ok=True)
    monkeypatch.setattr(gate, "PROJECT_ROOT", repo)
    monkeypatch.setattr(gate, "ALLOWLIST", allowed)
    monkeypatch.setattr(sys, "argv", ["check_deleted_paths.py", "--range", span])
    allowed.write_text("", encoding="utf-8")
    assert gate.main() == EXIT_RED and "README.md:1: scripts/old.py" in capsys.readouterr().err
    allowed.write_text("README.md:scripts/old.py: the changelog-style note names it on purpose\n", encoding="utf-8")
    assert gate.main() == EXIT_GREEN


def test_a_range_that_removes_nothing_has_no_subject(repo, monkeypatch, capsys):
    monkeypatch.setattr(gate, "PROJECT_ROOT", repo)
    monkeypatch.setattr(sys, "argv", ["check_deleted_paths.py", "--range", "HEAD..HEAD"])
    assert gate.main() == EXIT_GREEN and "no subject" in capsys.readouterr().err
