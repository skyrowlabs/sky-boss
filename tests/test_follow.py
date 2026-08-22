"""tb follow — one verb, two mechanisms, dispatch by shape. See [[follow]].

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
    """`tb follow new.log` before the log's first write is legitimate —
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


def test_follow_refuses_json_because_a_stream_has_no_envelope():
    result = CliRunner().invoke(cli, ["--json", "follow", "--", "sh", "-c", "true"])
    assert result.exit_code == 2
    assert "no envelope" in result.output


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

    def fake_follow_file(path, *, limit):
        calls["path"] = path
        calls["limit"] = limit

    monkeypatch.setattr("cli.filefollow.follow_file", fake_follow_file)
    result = CliRunner().invoke(cli, ["follow", "--lines", "50", "x/y.log"])
    assert result.exit_code == 0
    assert calls == {"path": "x/y.log", "limit": 50}


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
        sleep=lambda s: None,
        console=recording,
        screen=False,
        ticks=ticks,
        spawn=lambda argv, cwd=None, limit=None: child,
    )
    return recording.export_text(), child


def test_a_live_stream_shows_its_ring_and_its_last_line_clock():
    text, _ = drive(FakeChild([("line one", False), ("warn line", True)]))
    assert "line one" in text and "warn line" in text
    assert "journalctl -f" in text and "follow" in text
    assert "last line 1m ago" in text  # 160 - 100, read from the ring


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

    (tmp_path / "tools.toml").write_text('[tool.cron]\nargv = ["follow", "~/logs/cron.log"]\n')
    try:
        problems = register(cli, home=tmp_path)
        assert problems == []
        entry = {e["name"]: e for e in walk(cli)}["cron"]
        assert entry["acts"] is False and entry["resident"] is True
        assert cli.commands["cron"].tb_argv[1].startswith("/")
    finally:
        for name in [n for n, c in list(cli.commands.items()) if getattr(c, "tb_saved", False)]:
            del cli.commands[name]


def test_a_keyword_wrapping_follow_inherits_residency_and_refuses_a_cadence(tmp_path):
    """Inherited like acts: declaring refresh on a follow would load and mean
    nothing — the loader refuses it loudly instead."""
    from cli.tools import register

    (tmp_path / "tools.toml").write_text(
        '[tool.logs]\nargv = ["follow", "--", "journalctl", "-f"]\nrefresh = 30\n'
    )
    try:
        problems = register(cli, home=tmp_path)
        assert any("resident by nature" in p for p in problems)
        assert "logs" not in cli.commands

        (tmp_path / "tools.toml").write_text(
            '[tool.logs]\nargv = ["follow", "--", "journalctl", "-f"]\n'
        )
        problems = register(cli, home=tmp_path)
        assert problems == []
        from cli.canvas.catalog import walk

        entry = {e["name"]: e for e in walk(cli)}["logs"]
        assert entry["resident"] is True
        assert entry["acts"] is False
    finally:
        for name in [n for n, c in list(cli.commands.items()) if getattr(c, "tb_saved", False)]:
            del cli.commands[name]
