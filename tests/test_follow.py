"""`sb follow` — one verb, two mechanisms, dispatch by shape. See [[follow]].

The properties worth defending: the dispatch rule has no third shape, a
stream refuses --json because it has no envelope to promise, any exit is a
visible death and never a restart, the child dies with the loop, and a saved
keyword inherits residency the way it inherits acts.
"""

from click.testing import CliRunner

from cli import cli
from cli.follow import follow_process, is_file_form
from cli.stream import Line, Ring


# ============================================================================
# Dispatch — argument shape only
# ============================================================================


def test_anything_with_a_separator_is_the_file_form():
    assert is_file_form(("tmp/reporting/cron.log",))
    assert is_file_form(("./jam",))
    assert is_file_form(("/var/log/syslog",))


def test_a_bare_word_no_executable_answers_to_is_a_file():
    """`sb follow new.log` before the log's first write is legitimate —
    absent-then-appearing is a state the cursor owns."""
    assert is_file_form(("definitely-not-a-command-xyz.log",))


def test_a_bare_word_that_is_an_executable_is_a_command():
    assert not is_file_form(("sh",))


def test_more_than_one_word_is_always_the_process_form():
    assert not is_file_form(("journalctl", "-f"))
    assert not is_file_form(("tail", "-F", "x.log"))


# ============================================================================
# The command on the tree
# ============================================================================


def test_follow_refuses_json_because_a_stream_has_no_envelope(said):
    result = CliRunner().invoke(cli, ["--json", "follow", "--", "sh", "-c", "true"])
    assert result.exit_code == 2
    assert "no envelope" in said(result)


def test_follow_takes_no_refresh_flag():
    """Resident by nature — [[refresh]] owns the flag, on snapshot reads
    only. The absence is the contract, exactly as on `run`."""
    result = CliRunner().invoke(cli, ["follow", "--refresh", "5", "--", "sh"])
    assert result.exit_code == 2
    assert "No such option" in result.output


def test_follow_is_an_observe_and_resident_in_the_catalog():
    from cli.canvas.catalog import catalog

    entry = {e["name"]: e for e in catalog()}["follow"]
    assert entry["acts"] is False
    assert entry["resident"] is True


def test_the_file_form_dispatches_to_the_cursor(monkeypatch):
    """A path routes to the native cursor ([[file-follow]]), proven by
    intercepting it — invoking the real residency would block the suite,
    which is exactly what resident-by-nature means."""
    calls = {}

    def fake_follow_file(path, *, limit, screen, ruleset=None, due=0):
        calls.update(path=path, limit=limit, screen=screen, due=due)

    monkeypatch.setattr("cli.filefollow.follow_file", fake_follow_file)
    result = CliRunner().invoke(cli, ["follow", "--lines", "50", "x/y.log"])
    assert result.exit_code == 0
    assert calls == {"path": "x/y.log", "limit": 50, "screen": False, "due": 0}


# ============================================================================
# The process form's rendering — a fake child, no process, no real time
# ============================================================================


class FakeChild:
    """A scripted stream: lines now, death later, kill observable."""

    def __init__(self, lines, exit_code=None):
        self._ring = Ring(limit=10)
        for text, stderr in lines:
            self._ring.push(Line(text=text, stderr=stderr, at=100.0))
        self.exit_code = exit_code
        self.killed = False

    def lines(self):
        return self._ring.lines()

    @property
    def dropped(self):
        return self._ring.dropped

    @property
    def last_line_at(self):
        return self._ring.last_at

    def kill(self):
        self.killed = True


def drive(child, ticks=2):
    from rich.console import Console

    recording = Console(record=True, width=70, force_terminal=True)
    follow_process(
        ["journalctl", "-f"],
        clock=lambda: 160.0,
        wait=lambda s: None,
        console=recording,
        screen=False,
        ticks=ticks,
        spawn=lambda argv, cwd=None, limit=None, columns=None, env=None: child,
    )
    return recording.export_text(), child


def test_a_live_stream_shows_its_ring_and_its_last_line_clock():
    text, _ = drive(FakeChild([("line one", False), ("warn line", True)]))
    assert "line one" in text and "warn line" in text
    assert "journalctl -f" in text and "follow" in text
    assert "last line 1m ago" in text  # 160 - 100, read from the ring


def test_the_body_tints_stdout_lines_and_never_retags_stderr(monkeypatch):
    """The [[highlight]] seam: stdout lines go through `spans`, stderr lines
    keep their warn tint untouched — and the text reaches the screen verbatim
    either way, because marks ride beside it, never instead of it."""
    from cli import highlight

    seen = []
    real = highlight.spans

    def recording_spans(text, ruleset=None):
        seen.append(text)
        return real(text, ruleset)

    monkeypatch.setattr(highlight, "spans", recording_spans)
    stamped = "2026-01-01T00:00:00 [job] https://example.com done"
    text, _ = drive(FakeChild([(stamped, False), ("rotated away", True)]))
    assert stamped in text  # verbatim, tint or no tint
    assert stamped in seen
    assert "rotated away" not in seen


def test_any_exit_is_a_plainly_visible_death_with_its_code():
    """Exit 0 included: choosing follow asserted the process was expected
    not to exit, so ending at all is the event."""
    text, _ = drive(FakeChild([("bye", False)], exit_code=0))
    assert "dead" in text and "exited 0" in text


def test_the_child_dies_with_the_loop():
    """The terminal's window is the loop; leaving it SIGTERMs the child —
    the same rule the canvas has for watchers, extended to processes."""
    _, child = drive(FakeChild([("x", False)]))
    assert child.killed is True


def test_a_keyword_wrapping_a_file_follow_loads_and_inherits_observe(tmp_path):
    """`[tool.cron]` over `follow <path>`: loads, observes, resident — and
    the tilde expands, because these are the operator's own paths."""
    from cli.canvas.catalog import walk
    from cli.tools import register

    from cli.tools import tools as tools_group

    (tmp_path / "tools.toml").write_text('[tool.cron]\nargv = ["follow", "~/logs/cron.log"]\n')
    try:
        problems = register(cli, home=tmp_path)
        assert problems == []
        entry = {e["name"]: e for e in walk(cli)}["tools cron"]
        assert entry["acts"] is False and entry["resident"] is True
        assert tools_group.commands["cron"].sb_argv[1].startswith("/")
    finally:
        for name in [
            n for n, c in list(tools_group.commands.items()) if getattr(c, "sb_saved", False)
        ]:
            del tools_group.commands[name]


def test_a_keyword_wrapping_follow_inherits_residency_and_refuses_a_cadence(tmp_path):
    """Inherited like acts: declaring refresh on a follow would load and mean
    nothing — the loader refuses it loudly instead."""
    from cli.tools import register, tools as tools_group

    (tmp_path / "tools.toml").write_text(
        '[tool.logs]\nargv = ["follow", "--", "journalctl", "-f"]\nrefresh = 30\n'
    )
    try:
        problems = register(cli, home=tmp_path)
        assert any("resident by nature" in p for p in problems)
        assert "logs" not in tools_group.commands

        (tmp_path / "tools.toml").write_text(
            '[tool.logs]\nargv = ["follow", "--", "journalctl", "-f"]\n'
        )
        problems = register(cli, home=tmp_path)
        assert problems == []
        from cli.canvas.catalog import walk

        entry = {e["name"]: e for e in walk(cli)}["tools logs"]
        assert entry["resident"] is True
        assert entry["acts"] is False
    finally:
        for name in [
            n for n, c in list(tools_group.commands.items()) if getattr(c, "sb_saved", False)
        ]:
            del tools_group.commands[name]


# ============================================================================
# Leaving, and where the frame is drawn — [[follow]] round 2
# ============================================================================


def keyed(child, keys_pressed, ticks=100, screen=False):
    """Drive the loop with a scripted key at every wait, and report how many
    ticks it actually spent — the same shape [[refresh]] round 2's loop tests
    use, so a key that leaves is proven by the loop *ending*, not by a bound."""
    from rich.console import Console

    pressed = iter(keys_pressed)
    spent = []

    def wait(seconds):
        spent.append(seconds)
        return next(pressed, None)

    follow_process(
        ["journalctl", "-f"],
        clock=lambda: 160.0,
        wait=wait,
        console=Console(record=True, width=70, force_terminal=True),
        screen=screen,
        ticks=ticks,
        spawn=lambda argv, cwd=None, limit=None, columns=None, env=None: child,
    )
    return len(spent)


def test_q_leaves_a_stream_before_its_ticks_are_spent():
    assert keyed(FakeChild([("x", False)]), [None, None, "q"]) == 3


def test_esc_leaves_and_an_ordinary_key_does_not():
    assert keyed(FakeChild([("x", False)]), ["\x1b"]) == 1
    assert keyed(FakeChild([("x", False)]), ["j"], ticks=5) == 5


def test_leaving_with_q_kills_the_child_exactly_as_ctrl_c_does():
    """The one place the two resident commands genuinely differ. A resident
    read leaves a finished process behind; `q` on a follow terminates its
    child, because the stream *is* the window."""
    child = FakeChild([("x", False)])
    keyed(child, ["q"])
    assert child.killed is True


def test_the_alternate_screen_is_no_longer_the_default_for_a_stream():
    """The reversal, asserted where it is easiest to regress: leaving should
    leave the tail of the log you were watching on the screen."""
    import inspect

    from cli.filefollow import follow_file

    assert inspect.signature(follow_process).parameters["screen"].default is False
    assert inspect.signature(follow_file).parameters["screen"].default is False


def test_an_inline_frame_shows_the_newest_lines_not_the_oldest():
    """The clip direction, end to end. The ring holds 200 lines against a
    terminal's forty, so *every* inline follow frame is clipped — a follow
    that kept the head would pin the oldest lines and never show a new one.

    Round 3 replaced the clip marker with the band's own range. The old
    `N more lines not shown` said *that* something was missing beside a band
    saying `showing last 200` while forty were drawn — two places each telling
    half the truth. `showing 33–40 of 40` says both at once."""
    from rich.console import Console

    child = FakeChild([(f"line {i}", False) for i in range(40)])
    child._ring = Ring(limit=200)
    for i in range(40):
        child._ring.push(Line(text=f"line {i}", stderr=False, at=100.0))

    recording = Console(record=True, width=70, height=12, force_terminal=True)
    follow_process(
        ["journalctl", "-f"],
        clock=lambda: 160.0,
        wait=lambda s: "q",
        console=recording,
        screen=False,
        ticks=1,
        spawn=lambda argv, cwd=None, limit=None, columns=None, env=None: child,
    )
    text = recording.export_text()
    assert "line 39" in text and "line 0" not in text
    # Round 3: the band carries the range instead of a separate marker.
    assert "showing " in text and " of " in text


def test_the_screen_flag_reaches_both_forms(monkeypatch):
    seen = {}
    monkeypatch.setattr("cli.follow.follow_process", lambda argv, **kw: seen.update(kw))
    CliRunner().invoke(cli, ["follow", "--screen", "--", "journalctl", "-f"])
    assert seen["screen"] is True
    seen.clear()
    CliRunner().invoke(cli, ["follow", "--", "journalctl", "-f"])
    assert seen["screen"] is False


def test_the_help_says_how_to_leave_and_that_leaving_kills(said):
    """Help is the doc ([[refresh]]). Leaving killing the child is the one
    thing a reader would otherwise have to infer, so it is written down."""
    help_text = said(CliRunner().invoke(cli, ["follow", "--help"]))
    assert "q, Esc or Ctrl-C to leave" in help_text
    assert "kills it" in help_text
    assert "--screen" in help_text and "alternate screen" in help_text


def test_a_real_terminal_leaves_on_q_and_kills_the_child():
    """Terminal-shaped, end to end: a real pty, a real cbreak reader, and the
    real inline rendering. Everything above drives the loop with an injected
    wait and `screen=False`, so nothing else here ever sees the path the
    operator actually runs.

    The key is pressed *after* the reader is in cbreak, because
    `tty.setcbreak` flushes the input queue (TCSAFLUSH) — a byte written
    before the residency starts is discarded, which is correct behaviour and
    was only visible from a real terminal. Bounded either way: `ticks` caps
    the wait at three seconds, and leaving on the key is proven by the loop
    ending in well under one.
    """
    import os
    import pty
    import sys
    import threading
    import time as time_

    primary, secondary = pty.openpty()
    stdin = os.fdopen(secondary, "r", buffering=1)
    screen_out = os.fdopen(os.dup(secondary), "w", buffering=1)
    real_stdin = sys.stdin
    child = FakeChild([("a line", False)])
    press = threading.Timer(0.2, lambda: os.write(primary, b"q"))
    try:
        from rich.console import Console

        sys.stdin = stdin
        press.start()
        started = time_.monotonic()
        follow_process(
            ["journalctl", "-f"],
            clock=lambda: 160.0,
            console=Console(file=screen_out, width=70, height=12, force_terminal=True),
            ticks=3,
            spawn=lambda argv, cwd=None, limit=None, columns=None, env=None: child,
        )
        assert time_.monotonic() - started < 1.0  # left on the key, not the bound
        assert child.killed is True
    finally:
        press.cancel()
        sys.stdin = real_stdin
        stdin.close()
        screen_out.close()
        os.close(primary)


# ── Round 2: --due, on both forms ───────────────────────────────────────────


def test_due_reaches_the_file_form(monkeypatch):
    calls = {}

    def fake_follow_file(path, *, limit, screen, ruleset=None, due=0):
        calls.update(due=due)

    monkeypatch.setattr("cli.filefollow.follow_file", fake_follow_file)
    result = CliRunner().invoke(cli, ["follow", "--due", "15m", "x/y.log"])
    assert result.exit_code == 0
    assert calls["due"] == 900


def test_due_reaches_the_process_form(monkeypatch):
    """Both forms, because a long-running job that stopped printing is the same
    question as a log that stopped growing."""
    calls = {}

    def fake_follow_process(argv, **kwargs):
        calls.update(due=kwargs.get("due"))

    monkeypatch.setattr("cli.follow.follow_process", fake_follow_process)
    result = CliRunner().invoke(cli, ["follow", "--due", "2h", "--", "journalctl", "-f"])
    assert result.exit_code == 0
    assert calls["due"] == 7200


def test_a_malformed_due_is_refused_at_the_door(monkeypatch):
    """Not at the first tick. A watcher an hour in is the worst possible moment
    to discover its interval never meant anything."""
    monkeypatch.setattr("cli.filefollow.follow_file", lambda *a, **k: None)
    result = CliRunner().invoke(cli, ["follow", "--due", "fortnightly", "x/y.log"])
    assert result.exit_code == 2
    assert "not a duration" in result.output


def test_no_due_is_no_expectation(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        "cli.filefollow.follow_file",
        lambda path, **kwargs: calls.update(due=kwargs.get("due")),
    )
    CliRunner().invoke(cli, ["follow", "x/y.log"])
    assert calls["due"] == 0


# ── Round 3: a follow you can look back through ─────────────────────────────


def _scrolling(keys_pressed, ticks=None):
    """Drive a follow through a scripted keyboard and record what it drew.

    Keys are the *names* `wait` returns, not the bytes a terminal sends —
    decoding is `cli/keys.py`'s job and is tested there against a fake stream.
    """
    from rich.console import Console

    child = FakeChild([])
    child._ring = Ring(limit=200)
    for i in range(40):
        child._ring.push(Line(text=f"line {i}", stderr=False, at=100.0))

    pressed = iter([*keys_pressed, "q"])
    recording = Console(record=True, width=70, height=12, force_terminal=True)
    follow_process(
        ["journalctl", "-f"],
        clock=lambda: 160.0,
        wait=lambda s: next(pressed, "q"),
        console=recording,
        screen=False,
        ticks=ticks if ticks is not None else len(keys_pressed) + 2,
        spawn=lambda *a, **k: child,
    )
    return recording.export_text()


def test_a_following_follow_shows_the_newest_lines():
    text = _scrolling([])
    assert "line 39" in text and "parked" not in text


def test_scrolling_up_parks_and_the_band_says_so():
    text = _scrolling(["pgup"])
    assert "parked" in text


def test_a_parked_follow_shows_older_lines():
    text = _scrolling(["home"])
    assert "line 0" in text


def test_end_returns_to_the_tail():
    text = _scrolling(["home", "end"])
    # The last frame drawn is the following one, so the newest line is back.
    assert text.rstrip().count("line 39") >= 1


def test_the_band_carries_the_position_while_following_too():
    """The old band said `showing last 200` while drawing forty of them and
    leaned on a separate clip marker to admit it."""
    text = _scrolling([])
    assert "showing " in text and " of " in text


def test_a_movement_key_does_not_close_the_window():
    """Round 2 drained arrow keys precisely so Up could not quit. Round 3
    decodes them, and the loop must still not treat one as leaving."""
    text = _scrolling(["up", "up"])
    assert "line" in text
