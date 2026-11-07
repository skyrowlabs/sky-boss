"""What a run has to show before `test plant` will count it, read from its report."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import plant  # noqa: E402


def totals(**given: int) -> dict:
    return {"tests": 1, "failures": 0, "errors": 0, "skipped": 0, **given}


@pytest.mark.parametrize(
    ("given", "state"),
    [
        ({}, "green"),
        ({"failures": 1}, "red"),
        ({"tests": 0}, "nothing ran under that id"),
        ({"errors": 1}, "it errored rather than failed"),
        ({"skipped": 1}, "it was skipped"),
    ],
)
def test_only_a_pass_is_green_and_only_a_failure_is_red(given, state):
    assert plant.report_state(totals(**given)) == state


def test_a_command_is_red_on_exit_one_alone():
    assert plant.command_state(0) == "green"
    assert plant.command_state(1) == "red"
    for code in (2, 3, 127):
        assert "could not judge" in plant.command_state(code)


def test_an_unreadable_report_reads_as_nothing_ran(tmp_path):
    assert plant.report_state(plant.counts(tmp_path / "absent.xml")) == "nothing ran under that id"


def test_packages_are_found_at_the_root_and_under_src(tmp_path):
    for rel in ("one/__init__.py", "src/two/x.py", "docs/a.md"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("", encoding="utf-8")
    assert plant.packages(tmp_path) == ["one", "two"]
