"""The file cursor — stat-driven, and the suite never touches a real file.

The properties worth defending: backfill is bounded and takes the tail, a
partial line is never emitted half, rotation and truncation are announced in
the stream and recovered from, an absent file is waited for rather than
refused, and quiet is knowledge (a stat) rather than a guess (a silence).
The fs is a fake; nothing here sleeps, rotates, or writes to disk.
"""

from cli.filefollow import BACKFILL_BYTES, FileCursor, follow_file


class FakeFs:
    """A filesystem as three numbers and a string per path."""

    def __init__(self):
        self.files: dict[str, tuple[str, float, int]] = {}  # text, mtime, inode

    def put(self, path, text, mtime=100.0, inode=1):
        self.files[path] = (text, mtime, inode)

    def gone(self, path):
        self.files.pop(path, None)

    def stat(self, path):
        entry = self.files.get(path)
        if entry is None:
            return None
        text, mtime, inode = entry
        return len(text), mtime, inode

    def read(self, path, offset):
        return self.files[path][0][offset:]


def texts(cursor):
    return [line.text for line in cursor.lines()]


def make(fs, text=None, **kwargs):
    if text is not None:
        fs.put("x.log", text)
    return FileCursor("x.log", fs=fs, clock=lambda: 500.0, **kwargs)


# ============================================================================
# Backfill and advance
# ============================================================================


def test_opening_backfills_the_last_n_complete_lines():
    fs = FakeFs()
    cursor = make(fs, "one\ntwo\nthree\nfour\n", limit=2)
    assert texts(cursor) == ["three", "four"]
    assert cursor.state == "quiet"


def test_growth_emits_whole_lines_from_the_offset():
    fs = FakeFs()
    cursor = make(fs, "a\n")
    fs.put("x.log", "a\nb\nc\n", mtime=200.0)
    cursor.tick()
    assert texts(cursor) == ["a", "b", "c"]
    assert cursor.state == "running"
    assert cursor.last_write_at == 200.0


def test_a_partial_final_line_is_held_until_its_newline_arrives():
    """Never emitted half — an agent mid-sentence is not two log lines."""
    fs = FakeFs()
    cursor = make(fs, "done\nworking on it")
    assert texts(cursor) == ["done"]
    fs.put("x.log", "done\nworking on it, finished\n", mtime=200.0)
    cursor.tick()
    assert texts(cursor) == ["done", "working on it, finished"]


def test_the_backfill_is_bounded_and_takes_the_tail():
    """Following a gigabyte log opens by reading its last chunk, not the
    gigabyte; the fragment at the cut is dropped, not shown half."""
    fs = FakeFs()
    body = "x" * (BACKFILL_BYTES * 2)
    cursor = make(fs, body + "\nlast-line\n", limit=5)
    assert texts(cursor) == ["last-line"]


def test_unchanged_is_quiet_not_dead():
    """The whole argument for the native loop: the loop *knows* the file is
    untouched, because it statted it."""
    fs = FakeFs()
    cursor = make(fs, "a\n")
    cursor.tick()
    assert cursor.state == "quiet"
    assert cursor.last_write_at == 100.0  # the stat clock, not a guess


# ============================================================================
# Rotation, truncation, absence
# ============================================================================


def test_rotation_is_announced_and_the_new_file_followed():
    fs = FakeFs()
    cursor = make(fs, "old-1\nold-2\n")
    fs.put("x.log", "new-1\n", mtime=300.0, inode=2)
    cursor.tick()
    assert cursor.state == "rotated"
    shown = texts(cursor)
    assert any("rotated" in line for line in shown)
    assert "new-1" in shown
    fs.put("x.log", "new-1\nnew-2\n", mtime=310.0, inode=2)
    cursor.tick()
    assert "new-2" in texts(cursor)
    assert cursor.state == "running"


def test_truncation_is_announced_and_recovered_from():
    fs = FakeFs()
    cursor = make(fs, "aaaa\nbbbb\ncccc\n")
    fs.put("x.log", "z\n", mtime=300.0)
    cursor.tick()
    assert any("truncated" in line for line in texts(cursor))
    assert "z" in texts(cursor)


def test_an_absent_file_is_waited_for_and_read_from_zero_when_it_appears():
    """A log that has not had its first write yet is a legitimate thing to
    follow — refusing it would make the command unusable at exactly the
    moment a new job is first wired up."""
    fs = FakeFs()
    cursor = FileCursor("x.log", fs=fs, clock=lambda: 500.0)
    assert cursor.state == "absent"
    cursor.tick()
    assert cursor.state == "absent"
    fs.put("x.log", "first-ever line\n", mtime=600.0)
    cursor.tick()
    assert "first-ever line" in texts(cursor)


def test_a_file_going_away_is_announced_and_waited_out():
    fs = FakeFs()
    cursor = make(fs, "a\n")
    fs.gone("x.log")
    cursor.tick()
    assert cursor.state == "absent"
    assert any("gone" in line for line in texts(cursor))
    fs.put("x.log", "back\n", mtime=700.0)
    cursor.tick()
    assert "back" in texts(cursor)


def test_announcements_are_tagged_so_the_cursors_voice_is_distinct():
    fs = FakeFs()
    cursor = make(fs, "a\n")
    fs.put("x.log", "b\n", mtime=300.0, inode=2)
    cursor.tick()
    tagged = [line for line in cursor.lines() if line.stderr]
    assert len(tagged) == 1 and "rotated" in tagged[0].text


# ============================================================================
# The follower interface — what the canvas holds
# ============================================================================


def test_a_cursor_never_exits_and_kill_is_a_no_op():
    fs = FakeFs()
    cursor = make(fs, "a\n")
    assert cursor.exit_code is None
    cursor.kill()  # nothing to kill; present so a follower needs no case


def test_fresh_hands_lines_over_once():
    fs = FakeFs()
    cursor = make(fs, "a\nb\n")
    lines, mark = cursor.fresh(0)
    assert [line.text for line in lines] == ["a", "b"]
    assert cursor.fresh(mark)[0] == []


# ============================================================================
# The terminal rendering
# ============================================================================


def test_the_terminal_bands_carry_the_stat_knowledge():
    from rich.console import Console

    fs = FakeFs()
    fs.put("x.log", "line-a\nline-b\n", mtime=320.0)
    recording = Console(record=True, width=78, force_terminal=True)
    follow_file(
        "x.log",
        clock=lambda: 500.0,
        wait=lambda s: None,
        console=recording,
        screen=False,
        ticks=2,
        fs=fs,
    )
    text = recording.export_text()
    assert "line-a" in text and "line-b" in text
    assert "x.log" in text and "follow" in text
    assert "quiet 3m" in text  # 500 - 320, from the stat — not from silence
    assert "showing last 2" in text


def test_the_cursor_body_tints_through_the_same_rules(monkeypatch):
    """Both follow bodies tint through one `spans` — two renderers holding
    their own opinions would drift the week they were written."""
    from rich.console import Console

    from cli import highlight

    seen = []
    real = highlight.spans
    monkeypatch.setattr(
        highlight, "spans", lambda t, ruleset=None: seen.append(t) or real(t, ruleset)
    )

    fs = FakeFs()
    stamped = "2026-01-01T00:00:00 [cron] ran"
    fs.put("x.log", stamped + "\n", mtime=320.0)
    recording = Console(record=True, width=78, force_terminal=True)
    follow_file(
        "x.log",
        clock=lambda: 500.0,
        wait=lambda s: None,
        console=recording,
        screen=False,
        ticks=1,
        fs=fs,
    )
    assert stamped in recording.export_text()
    assert stamped in seen


def test_an_absent_file_renders_as_waiting():
    from rich.console import Console

    recording = Console(record=True, width=78, force_terminal=True)
    follow_file(
        "never.log",
        clock=lambda: 500.0,
        wait=lambda s: None,
        console=recording,
        screen=False,
        ticks=1,
        fs=FakeFs(),
    )
    assert "waiting for it to exist" in recording.export_text()


# ============================================================================
# Leaving, and where the frame is drawn — [[follow]] round 2
# ============================================================================


def test_q_leaves_a_file_follow_before_its_ticks_are_spent():
    """One command, one way out: the cursor loop takes the same keys the
    process form does, and nothing is killed because a file owns nothing."""
    from rich.console import Console

    fs = FakeFs()
    fs.put("x.log", "line-a\n", mtime=320.0)
    pressed = iter([None, None, "q"])
    spent = []

    def wait(seconds):
        spent.append(seconds)
        return next(pressed, None)

    follow_file(
        "x.log",
        clock=lambda: 500.0,
        wait=wait,
        console=Console(record=True, width=78, force_terminal=True),
        screen=False,
        ticks=100,
        fs=fs,
    )
    assert len(spent) == 3


def test_the_inline_cursor_frame_keeps_the_newest_lines():
    """A log's interesting end is its tail. The ring outruns the terminal on
    every frame, so keeping the head would pin the oldest lines forever."""
    from rich.console import Console

    fs = FakeFs()
    fs.put("x.log", "".join(f"line {i}\n" for i in range(40)), mtime=320.0)
    recording = Console(record=True, width=78, height=12, force_terminal=True)
    follow_file(
        "x.log",
        clock=lambda: 500.0,
        wait=lambda s: "q",
        console=recording,
        screen=False,
        ticks=1,
        fs=fs,
    )
    text = recording.export_text()
    assert "line 39" in text and "line 0\n" not in text
    assert "more lines not shown" in text
