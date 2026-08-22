"""The session loop: what a window gets while it is open, and what stops when
it is not.

Driven directly rather than over HTTP. Starlette's `TestClient` collects a whole
response body before returning, so a stream that never ends can never be opened
through it — the first version of these tests hung instead of failing.

The clock and the runner are injected. Proving a five-second cadence must not
cost five seconds of suite, and proving a watcher fires must not require
starting a subprocess.

**Every pull is bounded.** The second version of these tests hung too, for a
different reason worth remembering: a "stop after N frames" guard bounds how
many frames you accept and not how long you wait for one, so a loop that yields
nothing blocks on the first pull forever. The bound has to be a timeout.

And a property about what *does not* happen is tested against `Session.due()`
rather than the generator. Proving a negative by waiting is how a suite gets
slow, and the generator fires exactly what `due()` hands it.
"""

import asyncio
import json

import pytest

from cli.canvas.runner import Run
from cli.canvas.server import Canvas, stream_frames
from cli.canvas.watch import Session

# Generous — this bounds a hang, it does not measure anything.
PULL_TIMEOUT = 5.0


class Clock:
    """A hand-wound monotonic clock."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def fake_run(argv, **kwargs):
    return Run(argv=list(argv), exit_code=0, duration_s=0.01, envelope={"data": argv})


async def frame(generator) -> dict:
    """The next frame, or a failure. Never an indefinite wait."""
    return json.loads(await asyncio.wait_for(anext(generator), PULL_TIMEOUT))


def _session(canvas: Canvas, clock=None) -> Session:
    session = Session(id="s1") if clock is None else Session(id="s1", clock=clock)
    canvas.sessions["s1"] = session
    return session


# ---------------------------------------------------------------- the stream


async def test_the_first_frame_names_the_session():
    canvas = Canvas(token="t")
    generator = stream_frames(canvas, _session(canvas), run=fake_run, tick=0.001)
    try:
        assert await frame(generator) == {"type": "hello", "session": "s1"}
    finally:
        await generator.aclose()


async def test_a_watcher_fires_when_its_cadence_comes_round():
    clock = Clock()
    canvas = Canvas(token="t")
    session = _session(canvas, clock)
    session.set("w1", ["run", "--", "echo", "hi"], interval=5)

    generator = stream_frames(canvas, session, run=fake_run, tick=0.001, heartbeat=1e9)
    try:
        await frame(generator)  # hello
        clock.advance(5)
        fired = await frame(generator)
        assert fired["type"] == "run"
        assert fired["window"] == "w1"
        assert fired["result"]["envelope"]["data"] == ["run", "--", "echo", "hi"]
    finally:
        await generator.aclose()


async def test_a_watchers_frame_wears_resident_chrome_beside_the_envelope():
    """The [[chrome]] facts ride the transport, never the envelope. The frame
    carries shape, attention and the two numbers the bar reads — and the
    envelope inside is exactly what the runner produced, untouched."""
    clock = Clock()
    canvas = Canvas(token="t")
    session = _session(canvas, clock)
    session.set("w1", ["data", "--", "printf", "[]"], interval=30)

    generator = stream_frames(canvas, session, run=fake_run, tick=0.001, heartbeat=1e9)
    try:
        await frame(generator)  # hello
        clock.advance(30)
        fired = await frame(generator)
        chrome = fired["result"]["chrome"]
        assert chrome["shape"] == "resident"
        assert chrome["attention"] == "ok"
        assert chrome["interval"] == 30
        assert chrome["last_run"] > 0 and chrome["ran_at"] > 0
        assert "chrome" not in fired["result"]["envelope"]
        assert fired["result"]["envelope"] == {"data": ["data", "--", "printf", "[]"]}
    finally:
        await generator.aclose()


class FakeChild:
    """Enough of a ChildStream to drive follower_frames: a ring, a mark, an
    exit code, and an observable terminate."""

    def __init__(self, lines=(), exit_code=None):
        from cli.stream import Line, Ring

        self.ring = Ring(limit=10)
        for text in lines:
            self.ring.push(Line(text=text, stderr=False, at=50.0))
        self._exit = exit_code
        self.proc = type("P", (), {"terminate": lambda self_: None})()

    def fresh(self, since):
        kept = self.ring.lines()
        missed = self.ring.total - since
        out = kept[-missed:] if 0 < missed <= len(kept) else (kept if missed > 0 else [])
        return out, self.ring.total

    def lines(self):
        return self.ring.lines()

    @property
    def last_line_at(self):
        return self.ring.last_at

    @property
    def exit_code(self):
        return self._exit


def test_a_follower_frames_its_fresh_lines_with_stream_chrome():
    from cli.canvas.server import Follower, follower_frames

    session = Session(id="s1")
    session.followers["w1"] = Follower(child=FakeChild(["one", "two"]), argv=["journalctl", "-f"])

    frames = follower_frames(session, now=100.0)
    assert len(frames) == 1
    assert frames[0]["type"] == "stream" and frames[0]["window"] == "w1"
    assert [l["text"] for l in frames[0]["lines"]] == ["one", "two"]
    assert frames[0]["chrome"]["shape"] == "stream"
    assert frames[0]["chrome"]["attention"] == "running"
    # Nothing new → no frame at all, not an empty one.
    assert follower_frames(session, now=101.0) == []


def test_a_followers_death_is_announced_exactly_once():
    """Dead is an event to display; a frame per tick forever would make the
    corpse louder than the living stream ever was."""
    from cli.canvas.server import Follower, follower_frames

    session = Session(id="s1")
    session.followers["w1"] = Follower(child=FakeChild(["bye"], exit_code=143), argv=["x"])

    first = follower_frames(session, now=100.0)
    assert first[0]["chrome"]["attention"] == "dead"
    assert first[0]["chrome"]["exit_code"] == 143
    assert follower_frames(session, now=101.0) == []


async def test_a_followers_child_dies_with_its_session():
    """The watcher rule, extended to processes: closing the stream SIGTERMs
    every follower's child. Nothing survives the last window."""
    from cli.canvas.server import Follower

    killed = []
    child = FakeChild(["x"])
    child.proc = type("P", (), {"terminate": lambda self_: killed.append(True)})()

    canvas = Canvas(token="t")
    session = _session(canvas)
    session.followers["w1"] = Follower(child=child, argv=["x"])

    generator = stream_frames(canvas, session, run=fake_run, tick=0.001)
    try:
        await frame(generator)  # hello
    finally:
        await generator.aclose()
    assert killed == [True]
    assert "s1" not in canvas.sessions


def test_resolve_follow_resolves_keywords_and_strips_the_fence():
    from cli.canvas.server import resolve_follow

    foreign, cwd, lines = resolve_follow(["follow", "--", "journalctl", "-f"])
    assert foreign == ["journalctl", "-f"] and cwd is None

    foreign, cwd, lines = resolve_follow(
        ["follow", "--cwd", "/tmp", "--lines", "50", "--", "sh", "-c", "true"]
    )
    assert foreign == ["sh", "-c", "true"] and cwd == "/tmp" and lines == 50


def test_resolve_follow_refuses_what_is_not_a_process_follow():
    import pytest

    from cli.canvas.server import resolve_follow

    with pytest.raises(ValueError):
        resolve_follow(["run", "--", "true"])  # not a follow at all
    with pytest.raises(ValueError):
        resolve_follow(["follow"])  # nothing to follow
    with pytest.raises(ValueError):
        resolve_follow(["follow", "some/path.log"])  # the file form, later


def test_chrome_for_tells_an_act_from_an_observe_through_the_catalog():
    """Inherited, never inferred from the path — the same rule the cadence
    control follows. A failed run wears failed, mechanically."""
    from cli.canvas.server import chrome_for

    ran = {"ok": True, "duration_s": 0.4, "envelope": {"ok": True, "partial": False, "warnings": []}}
    assert chrome_for(["run", "--", "true"], ran, now=1000.0)["shape"] == "act"
    assert chrome_for(["data", "--", "x"], ran, now=1000.0)["shape"] == "snapshot"
    assert chrome_for(["data", "--", "x"], ran, interval=30, now=1000.0)["shape"] == "resident"

    failed = {"ok": False, "duration_s": 0.4, "envelope": {"ok": False, "warnings": ["boom"]}}
    facts = chrome_for(["data", "--", "x"], failed, now=1000.0)
    assert facts["attention"] == "failed"
    assert facts["warnings"] == 1


async def test_a_quiet_session_still_sends_something():
    """An idle window must not be indistinguishable from one whose connection
    died — and without a write, the server never learns the socket is gone."""
    canvas = Canvas(token="t")
    generator = stream_frames(
        canvas, _session(canvas), run=fake_run, tick=0.001, heartbeat=0.002
    )
    try:
        await frame(generator)  # hello
        assert (await frame(generator))["type"] == "beat"
    finally:
        await generator.aclose()


async def test_closing_the_stream_takes_the_session_with_it():
    """`pauses when the window closes`, expressed as the session ceasing to
    exist — so there is no cleanup anybody can forget to do."""
    canvas = Canvas(token="t")
    generator = stream_frames(canvas, _session(canvas), run=fake_run, tick=0.001)
    await frame(generator)
    assert "s1" in canvas.sessions

    await generator.aclose()
    assert "s1" not in canvas.sessions


# ----------------------------------------------------------------- the clock


def test_a_watcher_with_no_cadence_never_becomes_due():
    """Interval 0 is pinned-but-manual. A window that refreshed anyway would
    re-run a command the operator deliberately said not to."""
    clock = Clock()
    session = Session(id="s1", clock=clock)
    session.set("w1", ["run"], interval=0)

    clock.advance(3600)
    assert session.due() == []


def test_a_slow_command_does_not_stack_up_behind_itself():
    """An 8-second command on a 5-second cadence would otherwise queue runs
    forever, each tick falling further behind the one before."""
    clock = Clock()
    session = Session(id="s1", clock=clock)
    watcher = session.set("w1", ["run"], interval=5)

    clock.advance(5)
    assert session.due() == [watcher]

    session.claim(watcher)
    clock.advance(500)
    assert session.due() == []

    session.release(watcher)
    clock.advance(5)
    assert session.due() == [watcher]


def test_changing_the_cadence_does_not_fire_once_more_on_the_way_past():
    """Going 5s -> 300s measures from now. Measuring from the last run would
    make the window refresh immediately as you slowed it down."""
    clock = Clock()
    session = Session(id="s1", clock=clock)
    session.set("w1", ["run"], interval=5)
    clock.advance(4)

    session.set("w1", ["run"], interval=300)
    clock.advance(10)
    assert session.due() == []


def test_re_registering_the_same_window_does_not_add_a_second_watcher():
    """The client re-registers on every chip toggle. Two watchers on one window
    would double the request rate invisibly."""
    session = Session(id="s1")
    session.set("w1", ["run", "a"], interval=5)
    session.set("w1", ["run", "b"], interval=5)

    assert len(session.watchers) == 1
    assert session.watchers["w1"].argv == ["run", "b"]


def test_dropping_a_watcher_stops_it():
    session = Session(id="s1")
    session.set("w1", ["run"], interval=5)
    session.drop("w1")
    assert session.watchers == {}


# --------------------------------------------------------------- live reload


def test_an_edited_file_is_noticed(tmp_path):
    from cli.canvas.server import changed, fingerprint

    (tmp_path / "tb.css").write_text("a{}")
    before = fingerprint(tmp_path)

    (tmp_path / "tb.css").write_text("a{color:red}")
    assert changed(before, fingerprint(tmp_path)) == ["tb.css"]


def test_a_new_file_and_a_deleted_one_both_count_as_changes(tmp_path):
    """A file appearing is the common case while building a page, and one
    disappearing is how a rename looks from here."""
    from cli.canvas.server import changed, fingerprint

    (tmp_path / "a.js").write_text("1")
    before = fingerprint(tmp_path)

    (tmp_path / "b.js").write_text("2")
    (tmp_path / "a.js").unlink()
    assert changed(before, fingerprint(tmp_path)) == ["a.js", "b.js"]


def test_vendored_code_is_not_watched(tmp_path):
    """It does not change, and it is most of the directory."""
    from cli.canvas.server import fingerprint

    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "preact.mjs").write_text("x")
    (tmp_path / "app.js").write_text("y")
    assert list(fingerprint(tmp_path)) == ["app.js"]


async def test_editing_a_file_pushes_a_reload_frame(monkeypatch):
    """The whole point: the page learns about the edit without being asked."""
    from cli.canvas import server as module

    stamps = {"tb.css": 1.0}
    monkeypatch.setattr(module, "fingerprint", lambda *a, **k: dict(stamps))

    canvas = Canvas(token="t")
    generator = stream_frames(
        canvas, _session(canvas), run=fake_run, tick=0.001, heartbeat=1e9
    )
    try:
        await frame(generator)  # hello
        stamps["tb.css"] = 2.0
        pushed = await frame(generator)
        assert pushed == {"type": "reload", "files": ["tb.css"]}
    finally:
        await generator.aclose()


async def test_an_unchanged_directory_pushes_nothing(monkeypatch):
    """Otherwise the page would reload every half second forever."""
    from cli.canvas import server as module

    monkeypatch.setattr(module, "fingerprint", lambda *a, **k: {"tb.css": 1.0})

    canvas = Canvas(token="t")
    generator = stream_frames(
        canvas, _session(canvas), run=fake_run, tick=0.001, heartbeat=0.05
    )
    try:
        await frame(generator)  # hello
        # The next thing to arrive is the heartbeat, not a reload.
        assert (await frame(generator))["type"] == "beat"
    finally:
        await generator.aclose()
