"""A killed run's temp directory goes: SIGTERM runs the cleanup, a dead owner's is swept.

`scripts/tempdirs.py` serves `rehearse_scheduled.py`, which agents run under Bash
timeouts that end a run with SIGTERM.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import tempdirs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _dead_pid() -> int:
    finished = subprocess.Popen(["true"])
    finished.wait()
    return finished.pid


def _owned(root: Path, name: str, owner: str | None) -> Path:
    made = root / name
    made.mkdir()
    if owner is not None:
        (made / tempdirs.OWNER_FILE).write_text(f"{owner}\n", encoding="utf-8")
    return made


def test_only_a_dead_owners_directory_is_swept(tmp_path):
    dead = str(_dead_pid())
    _owned(tmp_path, "probe-dead", dead)
    _owned(tmp_path, "probe-live", str(os.getpid()))
    _owned(tmp_path, "probe-unowned", None)
    _owned(tmp_path, "probe-garbled", "x")
    _owned(tmp_path, "other-dead", dead)
    swept = tempdirs.sweep_dead("probe-", root=tmp_path)
    assert [path.name for path in swept] == ["probe-dead"]
    left = sorted(path.name for path in tmp_path.iterdir())
    assert left == ["other-dead", "probe-garbled", "probe-live", "probe-unowned"]


def test_a_swept_directorys_worktree_is_pruned_from_its_repository(tmp_path):
    repo = tmp_path / "repo"
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "chore: seed"], check=True)
    scratch = _owned(tmp_path, "probe-dead", str(_dead_pid()))
    subprocess.run([*git, "worktree", "add", "-q", "--detach", str(scratch / "work")], check=True)
    tempdirs.sweep_dead("probe-", root=tmp_path, prune=repo)
    listed = subprocess.run([*git, "worktree", "list"], capture_output=True, text=True, check=True).stdout
    assert str(scratch) not in listed, listed


def test_sigterm_runs_the_callers_cleanup(tmp_path):
    child = textwrap.dedent(f"""
        import shutil, sys, time
        sys.path.insert(0, {str(ROOT)!r})
        from scripts.tempdirs import exit_on_signal, owned_tempdir
        exit_on_signal()
        made = owned_tempdir("probe-")
        try:
            # Printed inside the try: the parent signals on this line, and must find the finally armed.
            print(made, flush=True)
            time.sleep(60)
        finally:
            shutil.rmtree(made)
        """)
    env = {**os.environ, "TMPDIR": str(tmp_path)}
    run = subprocess.Popen([sys.executable, "-c", child], stdout=subprocess.PIPE, text=True, env=env)
    assert run.stdout is not None
    made = Path(run.stdout.readline().strip())
    assert made.is_dir(), made
    run.send_signal(signal.SIGTERM)
    assert run.wait(timeout=30) == 128 + signal.SIGTERM
    assert not made.exists(), made
