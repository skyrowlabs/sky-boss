"""The rehearsal planner runs what it can stand in for, and stops at what it cannot.

`scripts/rehearse_scheduled.py` is only worth anything if a job it reports green
really ran every step, so the stopping rules are tested against synthetic
workflows: an unknown action, a `${{ }}` it cannot fill, a condition it cannot
read. Each must stop the job rather than skip the step.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import rehearse_scheduled as rs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _workflow(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "nightly.yml"
    path.write_text("on:\n  schedule:\n    - cron: '0 3 * * *'\n" + body, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "expr, verdict",
    [
        ("github.event_name == 'schedule'", True),
        ("github.event_name != 'workflow_run'", True),
        ("${{ github.event_name == 'push' }}", False),
        ("github.event_name == 'workflow_run' && startsWith(github.ref, 'x')", False),
        ("github.event_name == 'schedule' && env.X == 'true'", None),
        ("github.event_name == 'push' || github.event_name == 'schedule'", None),
    ],
)
def test_a_condition_is_read_only_as_far_as_the_event_name(expr, verdict):
    assert rs.condition(expr) is verdict


def test_an_unknown_action_stops_the_job_at_that_step(tmp_path):
    jobs = rs.plan(
        _workflow(
            tmp_path,
            "jobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: actions/checkout@v7\n      - run: echo one\n"
            "      - uses: actions/upload-artifact@v5\n      - run: echo two\n",
        ),
        tmp_path,
    )
    assert [s.kind for s in jobs[0].steps] == ["checkout", "run", "stop"]
    assert jobs[0].stopped is not None and "upload-artifact" in jobs[0].stopped.reason


def test_a_step_needing_the_runner_stops_and_a_job_env_expression_stops_the_job(tmp_path):
    jobs = rs.plan(
        _workflow(
            tmp_path,
            "jobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - run: echo ${{ github.sha }}\n"
            "  b:\n    runs-on: ubuntu-latest\n    env:\n      T: ${{ secrets.T }}\n    steps:\n"
            "      - run: echo fine\n",
        ),
        tmp_path,
    )
    assert [job.stopped is not None for job in jobs] == [True, True]
    assert all(job.runs == 0 for job in jobs)


def test_a_local_composite_action_is_expanded_with_its_inputs(tmp_path):
    action = tmp_path / ".github" / "actions" / "setup"
    action.mkdir(parents=True)
    (action / "action.yml").write_text(
        "inputs:\n  extra:\n    default: base\nruns:\n  using: composite\n  steps:\n"
        "    - uses: actions/setup-python@v7\n    - run: pip install ${{ inputs.extra }}\n      shell: bash\n",
        encoding="utf-8",
    )
    jobs = rs.plan(
        _workflow(
            tmp_path,
            "jobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: ./.github/actions/setup\n        with:\n          extra: given\n",
        ),
        tmp_path,
    )
    assert [(s.kind, s.script.strip()) for s in jobs[0].steps] == [("python", ""), ("run", "pip install given")]
    assert jobs[0].stopped is None


def test_every_scheduled_workflow_this_tree_ships_reads_as_a_plan():
    for path in rs.scheduled_workflows(ROOT / ".github" / "workflows"):
        for job in rs.plan(path, ROOT):
            assert job.skipped or job.steps, f"{path.name} › {job.id} planned nothing and said nothing"


def test_a_path_and_an_env_a_step_writes_reach_the_next_step(tmp_path):
    write = (
        "mkdir -p tools && printf '#!/bin/sh\\necho from-the-path\\n' > tools/probe && chmod +x tools/probe\n"
        'echo "$PWD/tools" >> "$GITHUB_PATH"\n'
        'echo "CARRIED=yes" >> "$GITHUB_ENV"\n'
    )
    read = 'test "$(probe)" = from-the-path && test "$CARRIED" = yes\n'
    job = rs.Job("nightly.yml", "a", [rs.Step("write", "run", script=write), rs.Step("read", "run", script=read)])
    assert rs.rehearse(job, keep=False, ref="HEAD") == "passed"


def test_the_runner_env_file_reads_both_forms():
    text = "A=1\nB<<EOF\nline one\nline two\nEOF\nC=x=y\n"
    assert rs.parse_github_env(text) == {"A": "1", "B": "line one\nline two", "C": "x=y"}


def test_the_interpreter_is_the_one_the_job_asks_for():
    here = f"{sys.version_info[0]}.{sys.version_info[1]}"
    assert rs.interpreter("") == sys.executable
    assert rs.interpreter(here) == sys.executable
    assert rs.interpreter("not-a-version") is None
    assert rs.interpreter("2.1") is None


def test_a_composite_action_passes_its_python_version_to_setup_python(tmp_path):
    action = tmp_path / ".github" / "actions" / "setup"
    action.mkdir(parents=True)
    (action / "action.yml").write_text(
        "inputs:\n  python-version:\n    required: true\nruns:\n  using: composite\n  steps:\n"
        "    - uses: actions/setup-python@v7\n      with:\n        python-version: ${{ inputs.python-version }}\n",
        encoding="utf-8",
    )
    jobs = rs.plan(
        _workflow(
            tmp_path,
            "jobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: ./.github/actions/setup\n        with:\n          python-version: '3.11'\n",
        ),
        tmp_path,
    )
    assert [(s.kind, s.python) for s in jobs[0].steps] == [("python", "3.11")]
