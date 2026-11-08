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


def test_a_committing_job_that_writes_and_commits_nothing_is_failed(tree, monkeypatch):
    """stash-flow: refused the commit, the agent exited 0, and the ledger said `ok`."""
    assert JOB.commits, "the fixture's job no longer commits, so this proves nothing"
    denial = '{"permission_denials": [{"tool_name": "Bash"}, {"tool_name": "Bash"}]}'
    row = _run_with(monkeypatch, ["sh", "-c", f"echo changed >> {tree / JOB.writes}; echo '{denial}'"], tree)
    assert row["outcome"] == "failed", row
    assert "committed nothing" in row["reason"] and "refused 2 tool call(s): Bash" in row["reason"], row


def test_committed_is_the_new_head_only_when_head_moved(tree, monkeypatch):
    script = f"echo changed >> {tree / JOB.writes} && git add -A && git commit -q -m 'docs: report'"
    before = _git(tree, "rev-parse", "--short", "HEAD")
    row = _run_with(monkeypatch, ["sh", "-c", script], tree)
    assert row["outcome"] == "ok", row
    if JOB.commits:
        assert row["committed"] not in (None, before), row
    else:
        assert row["committed"] is None, row


def test_the_row_carries_what_the_agent_spent_and_null_when_unmeasured(tree, monkeypatch):
    result = '{"total_cost_usd": 0.42, "num_turns": 3, "usage": {"input_tokens": 10, "output_tokens": 5}}'
    commit = "git add -A && git commit -q -m 'docs: report'"
    write = f"echo changed >> {tree / JOB.writes} && {commit}"
    row = _run_with(monkeypatch, ["sh", "-c", f"{write}; echo '{result}'"], tree)
    assert (row["cost_usd"], row["num_turns"], row["tokens"], row["seat"]) == (0.42, 3, 15, "personal"), row
    row = _run_with(monkeypatch, ["sh", "-c", f"{write.replace('changed', 'again')}; echo plain text"], tree)
    assert (row["cost_usd"], row["num_turns"], row["tokens"]) == (None, None, None), row


COMMIT = "git add -A && git commit -q -m 'docs: report'"


@pytest.fixture
def origin(tree, tmp_path, monkeypatch):
    """A bare remote holding `main`, with this job publishing and its pre-push passing."""
    bare = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    _git(tree, "remote", "add", "origin", str(bare))
    _git(tree, "push", "-q", "origin", "main")
    monkeypatch.setattr(agent_runner, "AUTO_PUSH", {JOB.key})
    monkeypatch.setattr(agent_runner, "PRE_PUSH", ["true"])
    return bare


def _report_commit(tree: Path) -> list[str]:
    return ["sh", "-c", f"echo changed >> {tree / JOB.writes} && {COMMIT}"]


def test_a_publishing_job_pushes_its_report_commit(tree, origin, monkeypatch):
    row = _run_with(monkeypatch, _report_commit(tree), tree)
    assert row["outcome"] == "ok", row
    assert _git(origin, "rev-parse", "--short", "main") == row["committed"], row


def test_a_job_not_enrolled_pushes_nothing(tree, origin, monkeypatch):
    monkeypatch.setattr(agent_runner, "AUTO_PUSH", set())
    before = _git(origin, "rev-parse", "main")
    assert _run_with(monkeypatch, _report_commit(tree), tree)["outcome"] == "ok"
    assert _git(origin, "rev-parse", "main") == before


def test_a_red_pre_push_stops_the_push(tree, origin, monkeypatch):
    monkeypatch.setattr(agent_runner, "PRE_PUSH", ["false"])
    before = _git(origin, "rev-parse", "main")
    row = _run_with(monkeypatch, _report_commit(tree), tree)
    assert row["outcome"] == "failed" and "not pushed" in row["reason"] and row["committed"], row
    assert _git(origin, "rev-parse", "main") == before


def test_a_commit_touching_another_file_is_not_pushed(tree, origin, monkeypatch):
    before = _git(origin, "rev-parse", "main")
    script = f"echo changed >> {tree / JOB.writes} && echo x > {tree / 'other.txt'} && {COMMIT}"
    row = _run_with(monkeypatch, ["sh", "-c", script], tree)
    assert row["outcome"] == "failed" and "other.txt" in row["reason"], row
    assert _git(origin, "rev-parse", "main") == before


def test_a_remote_that_moved_refuses_the_push_and_nothing_forces_it(tree, origin, tmp_path, monkeypatch):
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(origin), str(other))
    identity = ("-c", "user.name=t", "-c", "user.email=t@example.invalid")
    _git(other, *identity, "commit", "-q", "--allow-empty", "-m", "chore: elsewhere")
    _git(other, "push", "-q", "origin", "HEAD:main")
    moved = _git(origin, "rev-parse", "main")
    row = _run_with(monkeypatch, _report_commit(tree), tree)
    assert row["outcome"] == "failed" and "not pushed" in row["reason"], row
    assert _git(origin, "rev-parse", "main") == moved


def test_an_agent_that_leaves_the_checkout_on_its_own_branch_is_failed(tree, monkeypatch):
    """sky-vault: committed on a branch it cut, and the ledger said `ok` on the base branch."""
    script = f"git checkout -q -b mine && echo changed >> {tree / JOB.writes} && {COMMIT}"
    row = _run_with(monkeypatch, ["sh", "-c", script], tree)
    assert row["outcome"] == "failed" and "'mine'" in row["reason"], row


def test_an_ok_run_still_names_what_it_was_refused(tree, monkeypatch):
    denial = '{"permission_denials": [{"tool_name": "WebFetch"}]}'
    write = f"echo changed >> {tree / JOB.writes} && {COMMIT}"
    row = _run_with(monkeypatch, ["sh", "-c", f"{write}; echo '{denial}'"], tree)
    assert row["outcome"] == "ok" and "WebFetch" in row["reason"], row
