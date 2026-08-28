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
    assert roles["⟳ next in 12s"] == "sb.accent"
    assert roles["ok"] == "sb.ok"
    assert roles[" · 1 warning"] == "sb.warn"
    for text, role in top + bottom:
        if "─" in text or text in ("┌ ", "└ ", "┐", "┘", " ┐", " ┘"):
            assert role == "sb.muted", (text, role)


def test_quiet_is_legible_not_hidden():
    """Quiet's clock wears the label role — the state the band exists to
    make legible must not be the dimmest thing on screen."""
    from cli.chrome import status_bands

    c = cursor("cron.log", state="quiet", last_write_at=NOW - 180, size_bytes=1000)
    top, _ = status_bands(c, NOW, width=72)
    roles = dict(top)
    assert roles["quiet 3m"] == "sb.label"


def test_a_death_and_a_rotation_wear_their_alarm_colors():
    from cli.chrome import status_bands

    dead = stream("x", exit_code=1, exited_at=NOW)
    top, _ = status_bands(dead, NOW, width=70)
    assert any(role == "sb.fail" and "dead" in text for text, role in top)

    rotated = cursor("x.log", state="rotated")
    top, _ = status_bands(rotated, NOW, width=70)
    assert ("rotated", "sb.warn") in top


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


# ── Round 2: late is a word the operator earns ──────────────────────────────
#
# `now` is injected throughout, for the reason the module already exists under:
# proving a fifteen-minute rule must not cost fifteen minutes of suite.

NOW = 10_000.0


def test_no_expectation_means_silence_is_neither_good_nor_bad():
    """Without `--due`, quiet is a duration and nothing else. sky.boss has no opinion
    about whether three minutes is a long time."""
    facts = cursor("cron.log", last_write_at=NOW - 180)
    assert facts.attention == "quiet"
    assert facts.due == 0


def test_within_the_expectation_is_still_quiet():
    facts = cursor("cron.log", last_write_at=NOW - 180, due=900, now=NOW)
    assert facts.attention == "quiet"


def test_past_the_expectation_is_late():
    facts = cursor("cron.log", last_write_at=NOW - 2820, due=900, now=NOW)
    assert facts.attention == "late"


def test_exactly_on_the_expectation_is_not_yet_late():
    """Strictly greater. A job that runs every fifteen minutes is not late at
    the fifteen-minute mark; it is due."""
    facts = cursor("cron.log", last_write_at=NOW - 900, due=900, now=NOW)
    assert facts.attention == "quiet"


def test_a_healthy_watcher_shows_its_own_margin():
    """`quiet 3m of 15m` — legible before it fails, not only at the moment it
    does."""
    facts = cursor("cron.log", last_write_at=NOW - 180, due=900, now=NOW)
    top, _ = status_lines(facts, NOW, 78)
    assert "quiet 3m of 15m" in top


def test_a_late_band_says_how_long_and_what_was_expected():
    """Either alone leaves the reader doing the subtraction the flag exists to
    do for them."""
    facts = cursor("cron.log", last_write_at=NOW - 2820, due=900, now=NOW)
    top, _ = status_lines(facts, NOW, 78)
    assert "late 47m" in top and "due 15m" in top


def test_a_stronger_fact_beats_late():
    """`absent` and `rotated` are things sky.boss *knows*. Late is arithmetic over an
    assertion, and it must not overwrite knowledge."""
    for state in ("absent", "rotated"):
        facts = cursor("x.log", state=state, last_write_at=NOW - 9999, due=60, now=NOW)
        assert facts.attention == state


def test_a_dead_stream_is_dead_rather_than_late():
    """The exit code is the better answer, and a dead stream being also late
    adds nothing."""
    facts = stream("job", last_line_at=NOW - 2820, exit_code=1, due=900, now=NOW)
    assert facts.attention == "dead"


def test_both_follow_forms_take_the_expectation():
    """A long-running job that stopped printing is the same question as a log
    that stopped growing."""
    assert stream("job", last_line_at=NOW - 2820, due=900, now=NOW).attention == "late"
    assert cursor("f", last_write_at=NOW - 2820, due=900, now=NOW).attention == "late"


def test_late_is_warn_rather_than_fail():
    """A late log is a fact about a clock, not a verdict about a job — sky.boss does
    not know whether it died or the machine was asleep."""
    assert ROLE["late"] == "sb.warn"


def test_late_reaches_a_window_without_a_new_field():
    """`attention` already travels; `late` is a new value in a slot that
    exists. If this needed a wire change the round was designed wrong."""
    facts = cursor("cron.log", last_write_at=NOW - 2820, due=900, now=NOW)
    assert facts.to_dict()["attention"] == "late"


def test_due_is_omitted_when_there_is_no_expectation():
    """A shape's chrome does not carry another shape's nulls, and a follow with
    no `--due` is byte-identical to one from before this round."""
    assert "due" not in cursor("cron.log", last_write_at=NOW).to_dict()


# ── Round 3: a snapshot wears its chrome too ────────────────────────────────


def _human(args):
    """A command's human rendering, bands included. Bands go to stderr — they
    are status, not payload — so both streams are needed to see one."""
    result = CliRunner().invoke(cli, args)
    return result.output + result.stderr


def test_a_small_result_wears_no_band():
    """Two lines of chrome around four lines of content is ceremony outweighing
    what it frames, and this feature refuses a flag to turn it off."""
    out = _human(["data", "--", "printf", '[{"a": 1}, {"a": 2}]'])
    assert "┌" not in out and "└" not in out


def test_a_result_with_a_middle_wears_both_bands():
    rows = ",".join('{"a": %d}' % i for i in range(20))
    out = _human(["data", "--", "printf", f"[{rows}]"])
    assert "┌" in out and "└" in out


def test_the_terminator_says_the_output_ended():
    """Today a truncated result says so and a complete one says nothing, so
    silence means both 'that was everything' and 'it stopped early'."""
    rows = ",".join('{"a": %d}' % i for i in range(20))
    out = _human(["data", "--", "printf", f"[{rows}]"])
    assert "ok" in out.split("└")[-1]


def test_a_band_names_what_produced_it():
    """`data -- printf …` above a table is more useful than `data`, and neither
    the envelope nor a machine consumer needs to know it."""
    rows = ",".join('{"a": %d}' % i for i in range(20))
    out = _human(["data", "--", "printf", f"[{rows}]"])
    assert "data -- printf" in out


def test_a_band_never_reaches_stdout(capsys):
    """A band is status, not payload — the purity rule that keeps
    `sb read -- x | grep` seeing exactly the lines the tool printed.

    `capsys` rather than CliRunner: click 8.3 folds stderr into `.output`, so
    the runner cannot answer a question about which stream a byte went to."""
    from cli.output import Result, render

    render(Result("data", data=[{"a": i} for i in range(20)]), source="data -- x")
    captured = capsys.readouterr()
    assert "┌" not in captured.out and "└" not in captured.out
    assert "┌" in captured.err and "└" in captured.err


def test_bands_do_not_reach_the_envelope():
    """Round 1 holds this line for the resident form; it has to hold here or
    the feature has grown a field it promised not to."""
    rows = ",".join('{"a": %d}' % i for i in range(20))
    result = CliRunner().invoke(cli, ["--json", "data", "--", "printf", f"[{rows}]"])
    envelope = json.loads(result.output)
    assert set(envelope) <= {"command", "ok", "partial", "data", "warnings", "view", "saved"}
    assert "chrome" not in envelope and "ran_at" not in envelope


def test_run_keeps_its_own_single_band(capsys):
    """`run` stamps an act band itself and carries no data, so it must not also
    acquire a snapshot pair."""
    from cli.output import Result, render

    render(Result("run", data=None), source="run -- echo hello")
    captured = capsys.readouterr()
    assert "┌" not in captured.err and "└" not in captured.err
