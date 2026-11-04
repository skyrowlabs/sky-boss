"""`run_triage` records `ok` only when the agent left something behind.

It recorded `ok` on any zero exit and set `committed` to whatever HEAD already
was, so an agent that started, exited 0 and wrote nothing was a healthy row with
a sha in it and an `up` heartbeat, over a report that had stopped changing.
Measured on a fresh tree with the agent replaced by `true`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.reporting import agent_runner, run_ledger
from scripts.reporting.jobs import JOBS

pytestmark = pytest.mark.unit

JOB = next(job for job in JOBS if job.writes.startswith("docs/"))


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A one-commit repository on `main` holding the job's artifact, with the runner pointed at it.

    The prompt and the ledger live beside the repository, not inside it: the
    runner declines a dirty tree, and an untracked prompt directory is dirt.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    artifact = repo / JOB.writes
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# report\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: seed")
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / f"{JOB.module}.md").write_text("prompt\n", encoding="utf-8")
    ledger = tmp_path / "state" / "ledger.jsonl"
    monkeypatch.setattr(agent_runner, "PROJECT_ROOT", repo)
    monkeypatch.setattr(agent_runner, "PROMPTS", prompts)
    monkeypatch.setattr(run_ledger, "ledger_path", lambda: ledger)
    monkeypatch.delenv(JOB.heartbeat_var or "UNSET_HEARTBEAT", raising=False)
    return repo


def _run_with(monkeypatch, command: list[str], tree: Path) -> dict:
    monkeypatch.setattr(agent_runner, "agent_argv", lambda prompt: command)
    agent_runner.run_triage(JOB.key, {"finding_count": 0}, base_branch="main")
    row = run_ledger.last_run(JOB.key)
    assert row is not None, "the run recorded nothing"
    return row


def test_an_agent_that_exits_zero_and_writes_nothing_is_failed(tree, monkeypatch):
    row = _run_with(monkeypatch, ["true"], tree)
    assert row["outcome"] == "failed", row
    assert "wrote nothing" in row["reason"], row
    assert row["committed"] is None, row


def test_an_agent_that_changes_the_artifact_is_ok(tree, monkeypatch):
    artifact = tree / JOB.writes
    row = _run_with(monkeypatch, ["sh", "-c", f"echo changed >> {artifact}"], tree)
    assert row["outcome"] == "ok", row
    assert row["reason"] == "", row


def test_committed_is_the_new_head_only_when_head_moved(tree, monkeypatch):
    script = f"echo changed >> {tree / JOB.writes} && git add -A && git commit -q -m 'docs: report'"
    before = _git(tree, "rev-parse", "--short", "HEAD")
    row = _run_with(monkeypatch, ["sh", "-c", script], tree)
    assert row["outcome"] == "ok", row
    if JOB.commits:
        assert row["committed"] not in (None, before), row
    else:
        assert row["committed"] is None, row
