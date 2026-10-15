"""A frozen release leaves a record of its window, reports or none.

proto.pilot froze v0.2.0 with no anchored reports: no directory was written, and
the regenerated index said no release had ever been frozen. The window is now
recorded in every edition, and the index is built from edition directories.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.docs import freeze_release as fr  # noqa: E402

CLOSING = {
    "status": "released",
    "release": "v1.0.0",
    "previous_release": "v0.9.0",
    "commit_range": "v0.9.0..v1.0.0",
    "commits": 12,
    "head_sha": "abc1234",
    "generated": "2026-10-14T00:00:00Z",
}


@pytest.fixture
def tree(monkeypatch, tmp_path):
    """A repository with one release tag and the given anchored reports."""
    releases, regular = tmp_path / "releases", tmp_path / "regular"
    regular.mkdir()
    monkeypatch.setattr(fr, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(fr, "RELEASES_DIR", releases)
    monkeypatch.setattr(fr, "REGULAR_DIR", regular)
    monkeypatch.setattr(fr.release_window, "tags", lambda: ["v0.9.0", "v1.0.0"])
    monkeypatch.setattr(fr.release_window, "window", lambda tag=None: dict(CLOSING))
    monkeypatch.setattr(fr.release_window, "apply", lambda: 0)
    monkeypatch.setattr(sys, "argv", ["freeze_release.py", "--tag", "v1.0.0"])
    return releases, regular


def test_a_release_with_no_reports_is_still_recorded(tree, monkeypatch):
    releases, _ = tree
    monkeypatch.setattr(fr.release_window, "ANCHORED_REPORTS", ())
    assert fr.main() == 0
    window = (releases / "v1.0.0" / fr.WINDOW).read_text(encoding="utf-8")
    assert "v0.9.0..v1.0.0" in window and "no report was anchored" in window
    index = (releases / "README.md").read_text(encoding="utf-8")
    assert "## v1.0.0" in index and "No releases frozen yet" not in index


def test_a_frozen_report_sits_beside_the_window_and_both_are_indexed(tree, monkeypatch):
    releases, regular = tree
    monkeypatch.setattr(fr.release_window, "ANCHORED_REPORTS", ("status.md",))
    (regular / "status.md").write_text("---\nstatus: in-flight\n---\n# Status\n", encoding="utf-8")
    assert fr.main() == 0
    assert sorted(p.name for p in (releases / "v1.0.0").iterdir()) == [fr.WINDOW, "status.md"]
    index = (releases / "README.md").read_text(encoding="utf-8")
    assert f"(v1.0.0/{fr.WINDOW})" in index and "(v1.0.0/status.md)" in index


def test_a_window_cannot_be_frozen_twice(tree, monkeypatch):
    monkeypatch.setattr(fr.release_window, "ANCHORED_REPORTS", ())
    assert fr.main() == 0
    assert fr.main() == 1
