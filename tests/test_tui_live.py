"""Tests for live lane and ledger state.

The decisions worth pinning: that held-ness comes from /proc/locks rather than
from the lock file existing, that a dead holder releases, and that reading the
ledger tail survives a torn line.
"""

import json

from cli.jobs import lane_lock, lane_lock_path
from cli.tui.live import _describe, _locks_by_inode, lanes, last_run

NORMAL = "1: FLOCK  ADVISORY  WRITE 672504 00:37:3739396 0 EOF"
WAITER = "2: -> POSIX  ADVISORY  WRITE 991 08:02:4242 0 EOF"


def test_a_lock_line_yields_inode_and_pid():
    assert _locks_by_inode(NORMAL) == {3739396: 672504}


def test_a_waiter_line_is_parsed_despite_the_shifted_columns():
    # "->" pushes every field along by one, which is why the device:inode pair
    # is found by shape rather than by column index.
    assert _locks_by_inode(WAITER) == {4242: 991}


def test_junk_lines_are_ignored():
    assert _locks_by_inode("garbage\n\n1: FLOCK\n") == {}


def test_the_first_holder_of_an_inode_wins():
    both = NORMAL + "\n" + "3: FLOCK  ADVISORY  WRITE 5 00:37:3739396 0 EOF"
    assert _locks_by_inode(both)[3739396] == 672504


# ------------------------------------------------------------------- lanes


def test_lanes_are_free_when_nothing_holds_them(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert all(not lane.busy for lane in lanes())


def test_a_held_lane_reports_its_holder(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    with lane_lock("committing") as acquired:
        assert acquired
        held = {lane.name: lane.holder for lane in lanes()}
    assert held["committing"] is not None
    assert held["read-only"] is None


def test_releasing_a_lane_frees_it_immediately(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    with lane_lock("committing"):
        pass
    # The file outlives the lock. Deciding busy-ness by existence would report
    # every lane held forever after the first job ever ran.
    assert lane_lock_path("committing").exists()
    assert all(not lane.busy for lane in lanes())


def test_a_holder_label_is_a_single_short_line():
    label = _describe(1)
    assert "\n" not in label and len(label) <= 44


def test_an_unreadable_process_still_yields_a_label():
    assert _describe(999_999_999) == "pid 999999999"


# ------------------------------------------------------------------ ledger


def _write(path, entries):
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))


def test_last_run_is_the_final_entry(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    _write(ledger, [{"run_id": "a"}, {"run_id": "b"}])
    assert last_run(ledger)["run_id"] == "b"


def test_a_torn_line_is_skipped(tmp_path):
    # Seeking into the middle of the file can land mid-record; the tail read
    # must step over that rather than report nothing.
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text('{"run_id": "good"}\n{"run_id": "trunc\n')
    assert last_run(ledger)["run_id"] == "good"


def test_a_missing_ledger_is_not_an_error(tmp_path):
    assert last_run(tmp_path / "nope.jsonl") is None


def test_an_empty_ledger_is_not_an_error(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("")
    assert last_run(ledger) is None


# ---------------------------------------------------------------- estimates

RUNS = [
    {"job": "doctor", "outcome": "ok", "duration_s": 2.0},
    {"job": "doctor", "outcome": "partial", "duration_s": 4.0},
    {"job": "doctor", "outcome": "ok", "duration_s": 3.0},
    {"job": "other", "outcome": "ok", "duration_s": 99.0},
]


def test_an_estimate_is_the_median_of_past_runs():
    # Median, not mean: one pathological run should not move the estimate.
    from cli.tui.live import expected_seconds

    assert expected_seconds("run doctor", RUNS) == 3.0


def test_the_leading_tb_is_tolerated_in_an_estimate():
    from cli.tui.live import expected_seconds

    assert expected_seconds("tb run doctor", RUNS) == 3.0


def test_runs_that_never_started_do_not_drag_the_estimate_down():
    # skipped and refused record a near-zero duration because nothing ran. Left
    # in, a couple of lane collisions would make every job look instant.
    from cli.tui.live import expected_seconds

    entries = RUNS + [
        {"job": "doctor", "outcome": "skipped", "duration_s": 0.0},
        {"job": "doctor", "outcome": "refused", "duration_s": 0.0},
    ]
    assert expected_seconds("run doctor", entries) == 3.0


def test_a_job_with_no_history_has_no_estimate():
    # There is nothing to be proportional to, so the surface shows a spinner
    # rather than inventing a denominator.
    from cli.tui.live import expected_seconds

    assert expected_seconds("run brand-new", RUNS) is None


def test_only_run_lines_get_an_estimate():
    from cli.tui.live import expected_seconds

    assert expected_seconds("check", RUNS) is None
    assert expected_seconds("auto log doctor", RUNS) is None
    assert expected_seconds("run", RUNS) is None


# ------------------------------------------------------------------ recency


def test_recent_runs_are_newest_first_and_capped(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    _write(ledger, [{"run_id": str(index)} for index in range(10)])
    from cli.tui.live import recent_runs

    assert [entry["run_id"] for entry in recent_runs(3, ledger)] == ["9", "8", "7"]
