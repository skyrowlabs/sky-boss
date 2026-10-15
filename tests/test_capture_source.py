"""A job's captures are attributed, capped and deduplicated; a person's are not.

The job comes from the environment the runner sets, never from a flag, and the
cap is enforced by the capture command rather than asked of the filer — a rule
an unattended agent must remember is one it can forget. `scripts/lanes.py` owns
the number, the variable and the attribution line.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.lanes import LANES, SESSION, SOURCE_CAP, SOURCE_ENV, source_line  # noqa: E402
from tests.shell import module  # noqa: E402

capture = module("_capture")
VALUES = {s.name: "x" for s in LANES[0].sections}


@pytest.fixture
def nightly(monkeypatch):
    """A registry holding one job, `nightly`, at any tier."""
    registry = SimpleNamespace(JOBS_BY_KEY={"nightly": object()})
    monkeypatch.setattr(capture, "job_registry", lambda: registry)


def never(*args):
    raise AssertionError("asked gh for a count the refusal did not need")


def test_unset_is_a_person_and_a_person_is_never_refused(monkeypatch):
    monkeypatch.delenv(SOURCE_ENV, raising=False)
    assert capture.capture_source() is None
    assert capture.refusal(None, "anything", never) == ""


def test_session_in_the_environment_is_a_job_key_like_any_other(monkeypatch, nightly):
    monkeypatch.setenv(SOURCE_ENV, SESSION)
    assert "not a registered job" in capture.refusal(capture.capture_source(), "t", never)


def test_the_runner_names_the_job(monkeypatch):
    monkeypatch.setenv(SOURCE_ENV, "nightly")
    assert capture.capture_source() == "nightly"


def test_a_source_that_is_not_a_job_is_refused(nightly):
    assert "not a registered job" in capture.refusal("nightlly", "t", never)


def test_a_job_that_cannot_count_files_nothing(nightly):
    assert "cannot be checked" in capture.refusal("nightly", "t", lambda: None)


def test_a_job_is_refused_a_title_it_already_has_open(nightly):
    assert "already has this open" in capture.refusal("nightly", "t", lambda: ["t"])


def test_a_job_at_its_cap_is_refused_and_one_below_is_not(nightly):
    below = [f"t{i}" for i in range(SOURCE_CAP - 1)]
    assert capture.refusal("nightly", "new", lambda: below) == ""
    assert "at its cap" in capture.refusal("nightly", "new", lambda: below + ["one more"])


def test_the_body_names_its_source():
    assert source_line("nightly") in capture.compose(LANES[0], "t", VALUES, "nightly")


def test_standing_counts_each_of_this_sources_issues_once(monkeypatch):
    def gh(args, **kwargs):
        issues = [
            {"number": 1, "title": "mine", "body": source_line("nightly")},
            {"number": 2, "title": "theirs", "body": source_line("weekly")},
        ]
        return subprocess.CompletedProcess(args, 0, json.dumps(issues), "")

    # Every lane's listing returns issue 1, as a doubly-labelled issue would.
    monkeypatch.setattr(capture.subprocess, "run", gh)
    assert capture.standing("nightly") == ["mine"]


def test_standing_is_unknown_when_gh_is_absent(monkeypatch):
    def absent(args, **kwargs):
        raise FileNotFoundError(args[0])

    monkeypatch.setattr(capture.subprocess, "run", absent)
    assert capture.standing("nightly") is None


def test_a_refused_capture_is_never_filed(monkeypatch, nightly):
    filed = []
    monkeypatch.setenv(SOURCE_ENV, "nightly")
    monkeypatch.setattr(capture, "standing", lambda source: [f"t{i}" for i in range(SOURCE_CAP)])
    monkeypatch.setattr(capture, "_file_issue", lambda *a: filed.append(a))
    with pytest.raises(SystemExit):
        capture.run_capture(LANES[0], "new", VALUES, False)
    assert not filed


def test_local_captures_keep_their_source_and_never_collide(monkeypatch, tmp_path):
    frozen = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(capture, "datetime", SimpleNamespace(now=lambda tz: frozen))
    monkeypatch.setenv(SOURCE_ENV, "nightly")
    monkeypatch.setattr(capture, "QUEUE", tmp_path)
    monkeypatch.setattr(capture, "PROJECT_ROOT", tmp_path)
    for _ in range(5):
        capture.run_capture(LANES[0], "t", VALUES, True)
    written = sorted((tmp_path / LANES[0].key).iterdir())
    assert len(written) == 5
    assert {json.loads(p.read_text(encoding="utf-8"))["source"] for p in written} == {"nightly"}
