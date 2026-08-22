"""Chrome — one fact set, computed in Python, drawn twice. See [[chrome]].

The properties worth defending: the attention slot is populated by mechanics
only, the countdown reads the same interval/last_run the canvas bar reads,
no real time is consulted anywhere, and nothing chrome-shaped can reach the
envelope (that boundary has its own test at the bottom).
"""

import json
import time

from click.testing import CliRunner

from cli import cli
from cli.chrome import (
    ATTENTION,
    ROLE,
    Chrome,
    act,
    ago,
    clock,
    countdown,
    cursor,
    resident,
    snapshot,
    status_lines,
    stream,
)

NOW = 1_766_000_000.0  # an injected moment; nothing here calls time.time()


# ============================================================================
# The facts, per shape
# ============================================================================


def test_a_snapshot_wears_its_verdict_and_its_stamp():
    c = snapshot("jam-prs", ok=True, ran_at=NOW - 4, duration_s=0.4, warnings=1)
    assert c.shape == "snapshot"
    assert c.attention == "ok"
    assert c.ran_at == NOW - 4 and c.duration_s == 0.4 and c.warnings == 1


def test_partial_and_failed_are_envelope_facts_not_judgments():
    assert snapshot("x", ok=True, partial=True).attention == "partial"
    assert snapshot("x", ok=False).attention == "failed"
    # failed outranks partial — a command that could not do its job is not
    # merely degraded, whatever else it managed to warn about.
    assert snapshot("x", ok=False, partial=True).attention == "failed"


def test_an_act_is_a_snapshot_stamped_once_and_never_counted_down():
    c = act("deploy", ok=True, ran_at=NOW, duration_s=12.0)
    assert c.shape == "act"
    assert c.interval == 0
    assert countdown(c, NOW) is None


def test_a_resident_in_flight_is_running_mechanically():
    """`running` is 'the subprocess has not exited' — not a spinner's guess."""
    c = resident("jam-prs", ok=True, interval=30, last_run=NOW - 18, running_since=NOW - 2)
    assert c.attention == "running"
    idle = resident("jam-prs", ok=True, interval=30, last_run=NOW - 18)
    assert idle.attention == "ok"


def test_a_stream_is_running_until_any_exit_makes_it_dead():
    alive = stream("journalctl -f", last_line_at=NOW - 3)
    assert alive.attention == "running"
    corpse = stream("journalctl -f", exit_code=0, exited_at=NOW - 60)
    # Exit 0 is still dead: choosing `follow` asserted the process was
    # expected not to exit, so any exit is an event worth wearing.
    assert corpse.attention == "dead"
    assert corpse.exit_code == 0


def test_a_cursor_carries_the_loops_verdict_rather_than_rederiving_it():
    """The loop compared the inodes; chrome carries what it was told."""
    for state in ("quiet", "absent", "rotated"):
        assert cursor("cron.log", state=state).attention == state


def test_a_cursor_refuses_a_state_the_loop_could_not_have_reported():
    import pytest

    with pytest.raises(ValueError):
        cursor("cron.log", state="suspicious")


def test_every_attention_value_is_in_the_declared_set_with_a_role():
    """The slot the escalation ladder lands in. A value without a theme role
    would render unstyled the day a rule first sets it."""
    assert set(ROLE) == set(ATTENTION)


# ============================================================================
# The clocks — injected, never consulted
# ============================================================================


def test_the_countdown_reads_interval_and_last_run_and_nothing_else():
    """The [[canvas]] rule, inherited: time to the next refresh is the only
    thing a progress display may show."""
    c = resident("x", ok=True, interval=30, last_run=NOW - 18)
    assert countdown(c, NOW) == 12
    assert countdown(c, NOW + 100) == 0  # overdue clamps, never goes negative


def test_no_cadence_means_no_countdown():
    assert countdown(snapshot("x", ok=True), NOW) is None
    assert countdown(resident("x", ok=True, interval=30), NOW) is None  # never run


def test_ago_says_the_shortest_honest_word():
    assert ago(3) == "3s"
    assert ago(59) == "59s"
    assert ago(180) == "3m"
    assert ago(7200) == "2h"
    assert ago(200_000) == "2d"
    assert ago(-5) == "0s"  # a clock skew is not a negative age


def test_clock_is_wall_time_of_the_injected_moment():
    assert clock(NOW) == time.strftime("%H:%M:%S", time.localtime(NOW))


# ============================================================================
# The terminal bands
# ============================================================================


def test_the_two_bands_are_exactly_the_width_asked_for():
    c = resident("jam-prs · data", ok=True, interval=30, last_run=NOW - 18,
                 ran_at=NOW - 18, duration_s=0.4, warnings=1)
    top, bottom = status_lines(c, NOW, width=64)
    assert len(top) == 64 and len(bottom) == 64
    assert top.startswith("┌") and top.endswith("┐")
    assert bottom.startswith("└") and bottom.endswith("┘")


def test_the_title_band_carries_identity_left_and_liveness_right():
    c = resident("jam-prs", ok=True, interval=30, last_run=NOW - 18)
    top, _ = status_lines(c, NOW, width=60)
    assert "jam-prs" in top and "refresh 30s" in top
    assert "next in 12s" in top


def test_the_footer_carries_verdict_cost_stamp_and_warnings():
    c = snapshot("jam-prs", ok=True, ran_at=NOW - 4, duration_s=0.4, warnings=1)
    _, bottom = status_lines(c, NOW, width=60)
    assert "ok" in bottom and "0.4s" in bottom
    assert f"ran {clock(NOW - 4)}" in bottom
    assert "1 warning" in bottom and "warnings" not in bottom


def test_a_dead_stream_wears_its_exit_code_and_when():
    c = stream("journalctl -f", exit_code=143, exited_at=NOW - 60)
    top, _ = status_lines(c, NOW, width=70)
    assert "dead" in top and "143" in top and clock(NOW - 60) in top


def test_a_cursor_band_tells_quiet_from_dead_because_it_can_stat():
    """The whole argument for the native loop: 'file untouched since 19:00'
    is knowledge a spawned tail cannot have."""
    c = cursor("cron.log", state="quiet", last_write_at=NOW - 180,
               size_bytes=202_752, ring_shown=200, ring_limit=200)
    top, bottom = status_lines(c, NOW, width=72)
    assert "quiet 3m" in top and f"last write {clock(NOW - 180)}" in top
    assert "198.0 KiB" in bottom and "showing last 200" in bottom


def test_an_absent_file_is_a_legitimate_thing_to_follow():
    top, _ = status_lines(cursor("new.log", state="absent"), NOW, width=60)
    assert "waiting for it to exist" in top


def test_a_long_source_gives_way_to_the_live_half():
    """The right side is a clock; a clock you cannot see is the silent
    failure the chrome exists to avoid."""
    c = resident("data -- " + "x" * 100, ok=True, interval=30, last_run=NOW - 18)
    top, _ = status_lines(c, NOW, width=60)
    assert len(top) == 60
    assert "next in 12s" in top
    assert "…" in top


def test_a_running_resident_shows_running_not_a_stale_countdown():
    c = resident("jam-prs", ok=True, interval=30, last_run=NOW - 30,
                 running_since=NOW - 2)
    top, bottom = status_lines(c, NOW, width=60)
    assert "running 2s" in top
    assert "next in" not in top
    assert "running" in bottom


def test_the_spans_join_to_exactly_the_plain_lines():
    """The round-2 contract: status_lines is the spans joined, so every
    width and truncation property proven against the strings holds for the
    styled rendering by construction."""
    from cli.chrome import status_bands

    c = resident("jam-prs", ok=True, interval=30, last_run=NOW - 18,
                 ran_at=NOW - 18, duration_s=0.4, warnings=1)
    top_spans, bottom_spans = status_bands(c, NOW, width=64)
    top, bottom = status_lines(c, NOW, width=64)
    assert "".join(t for t, _ in top_spans) == top
    assert "".join(t for t, _ in bottom_spans) == bottom


def test_the_frame_is_furniture_and_the_facts_wear_their_roles():
    """Corners and fills always muted; the source bold; the countdown in
    accent; the verdict word in its verdict's color; warnings in warn. One
    color per band was the round-1 mistake this round retires."""
    from cli.chrome import status_bands

    c = resident("jam-prs", ok=True, interval=30, last_run=NOW - 18,
                 ran_at=NOW - 18, duration_s=0.4, warnings=1)
    top, bottom = status_bands(c, NOW, width=64)

    roles = dict(top + bottom)
    assert roles["jam-prs"] == "bold"
    assert roles["⟳ next in 12s"] == "tb.accent"
    assert roles["ok"] == "tb.ok"
    assert roles[" · 1 warning"] == "tb.warn"
    for text, role in top + bottom:
        if "─" in text or text in ("┌ ", "└ ", "┐", "┘", " ┐", " ┘"):
            assert role == "tb.muted", (text, role)


def test_quiet_is_legible_not_hidden():
    """Quiet's clock wears the label role — the state the band exists to
    make legible must not be the dimmest thing on screen."""
    from cli.chrome import status_bands

    c = cursor("cron.log", state="quiet", last_write_at=NOW - 180, size_bytes=1000)
    top, _ = status_bands(c, NOW, width=72)
    roles = dict(top)
    assert roles["quiet 3m"] == "tb.label"


def test_a_death_and_a_rotation_wear_their_alarm_colors():
    from cli.chrome import status_bands

    dead = stream("x", exit_code=1, exited_at=NOW)
    top, _ = status_bands(dead, NOW, width=70)
    assert any(role == "tb.fail" and "dead" in text for text, role in top)

    rotated = cursor("x.log", state="rotated")
    top, _ = status_bands(rotated, NOW, width=70)
    assert ("rotated", "tb.warn") in top


def test_no_band_animates_to_look_busy():
    """No spinners, no percentages. A running subprocess has no percentage,
    and decoration that reads as information is the rejected thing."""
    c = resident("x", ok=True, interval=30, last_run=NOW - 1, running_since=NOW - 1)
    top, bottom = status_lines(c, NOW, width=60)
    for glyph in ("%", "⠋", "⣾", "◐"):
        assert glyph not in top and glyph not in bottom


# ============================================================================
# The envelope boundary
# ============================================================================


def test_an_envelope_is_byte_identical_to_one_from_before_chrome_existed():
    """Chrome consumes the envelope; it never feeds it. The exact keys, in
    the exact order, that the envelope carried before cli/chrome.py existed."""
    result = CliRunner().invoke(cli, ["--json", "data", "--", "printf", '[{"a": 1}]'])
    envelope = json.loads(result.stdout)
    assert list(envelope) == ["command", "ok", "partial", "data", "warnings", "view"]
    result = CliRunner().invoke(cli, ["--json", "read", "--", "printf", "hi"])
    envelope = json.loads(result.stdout)
    assert list(envelope) == ["command", "ok", "partial", "data", "warnings"]
    assert not any("chrome" in key for key in envelope)
