"""A job's captures are attributed, capped and deduplicated; a person's are not.

The cap is enforced by the capture command rather than asked of the filer,
because an unattended job told to count its own open issues is a rule it can
forget. `scripts/lanes.py` owns the number and the attribution line.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.lanes import LANES, SESSION, SOURCE_CAP, source_line  # noqa: E402
from tests.shell import module  # noqa: E402

capture = module("_capture")


def test_a_person_is_never_refused():
    assert capture.refusal(SESSION, "anything", None) == ""


def test_a_job_that_cannot_count_files_nothing():
    assert "cannot be checked" in capture.refusal("nightly", "t", None)


def test_a_job_is_refused_a_title_it_already_has_open():
    assert "already has this open" in capture.refusal("nightly", "t", ["t"])


def test_a_job_at_its_cap_is_refused_and_one_below_is_not():
    below = [f"t{i}" for i in range(SOURCE_CAP - 1)]
    assert capture.refusal("nightly", "new", below) == ""
    assert "at its cap" in capture.refusal("nightly", "new", below + ["one more"])


def test_the_body_names_its_source():
    body = capture.compose(LANES[0], "t", {s.name: "x" for s in LANES[0].sections}, "nightly")
    assert source_line("nightly") in body


def test_standing_counts_only_this_sources_open_captures(monkeypatch):
    def gh(args, **kwargs):
        issues = [
            {"title": "mine", "body": "...\n" + source_line("nightly")},
            {"title": "theirs", "body": "...\n" + source_line("weekly")},
            {"title": "a person's", "body": "...\n" + source_line(SESSION)},
        ]
        return subprocess.CompletedProcess(args, 0, json.dumps(issues), "")

    monkeypatch.setattr(capture.subprocess, "run", gh)
    assert capture.standing("nightly") == ["mine"] * len(LANES)


def test_standing_is_unknown_when_gh_is_absent(monkeypatch):
    def absent(args, **kwargs):
        raise FileNotFoundError(args[0])

    monkeypatch.setattr(capture.subprocess, "run", absent)
    assert capture.standing("nightly") is None


def test_a_refused_capture_is_never_filed(monkeypatch):
    filed = []
    monkeypatch.setattr(capture, "standing", lambda source: [f"t{i}" for i in range(SOURCE_CAP)])
    monkeypatch.setattr(capture, "_file_issue", lambda *a: filed.append(a))
    with pytest.raises(SystemExit):
        capture.run_capture(LANES[0], "new", {s.name: "x" for s in LANES[0].sections}, False, "nightly")
    assert not filed
