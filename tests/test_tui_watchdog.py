"""The stall watchdog.

Every test here drives an injected clock rather than sleeping. A watchdog whose
threshold is five seconds cannot be tested by stalling a real event loop for
five seconds — that is five seconds of suite for one assertion, in a suite whose
whole run is under twenty.

The thread itself is exercised once, at the bottom, with a threshold of zero.
"""

import threading

from cli.tui.watchdog import STALL_SECONDS, Watchdog


class Clock:
    """A hand-wound monotonic clock."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _watchdog(tmp_path, clock, **kwargs):
    return Watchdog(tmp_path / "stall.txt", clock=clock, **kwargs)


def test_a_running_loop_is_never_reported(tmp_path):
    clock = Clock()
    dog = _watchdog(tmp_path, clock)

    for _ in range(20):
        clock.advance(0.5)
        dog.beat()
        assert not dog.check()

    assert not (tmp_path / "stall.txt").exists()


def test_a_stalled_loop_is_reported(tmp_path):
    clock = Clock()
    dog = _watchdog(tmp_path, clock)
    dog.beat()

    clock.advance(STALL_SECONDS + 1)

    assert dog.check()
    dump = (tmp_path / "stall.txt").read_text()
    assert "event loop stalled" in dump
    # The dump has to name the thread whose frame matters, or it is just a wall
    # of stacks. faulthandler labels the main thread for us.
    assert "Thread" in dump or "Stack" in dump


def test_a_stall_is_reported_once_not_once_per_poll(tmp_path):
    """A ten minute freeze should leave one legible file, not six hundred
    appends of the same stack."""
    clock = Clock()
    dog = _watchdog(tmp_path, clock)
    dog.beat()
    clock.advance(STALL_SECONDS + 1)

    assert dog.check()
    for _ in range(10):
        clock.advance(1)
        assert not dog.check()

    assert (tmp_path / "stall.txt").read_text().count("event loop stalled") == 1


def test_recovering_arms_it_again(tmp_path):
    """A surface that froze, recovered, and froze again is exactly the case
    worth having two entries for."""
    clock = Clock()
    dog = _watchdog(tmp_path, clock)

    dog.beat()
    clock.advance(STALL_SECONDS + 1)
    assert dog.check()

    # The loop comes back.
    dog.beat()
    assert not dog.check()

    clock.advance(STALL_SECONDS + 1)
    assert dog.check()

    assert (tmp_path / "stall.txt").read_text().count("event loop stalled") == 2


def test_an_unwritable_state_directory_does_not_crash_the_watchdog(tmp_path):
    """Diagnostics for a surface already in trouble must not add a second
    failure to the first."""
    clock = Clock()
    unwritable = tmp_path / "nope"
    unwritable.write_text("this is a file, not a directory")
    dog = Watchdog(unwritable / "stall.txt", clock=clock)

    dog.beat()
    clock.advance(STALL_SECONDS + 1)

    assert dog.check(), "it still counts as reported — it tried"


def test_the_watcher_is_a_daemon_so_it_cannot_delay_exit(tmp_path):
    """`cli/tui/app.run` leaves through os._exit when a non-daemon thread is
    alive. A non-daemon watchdog would make every ordinary exit a hard one."""
    dog = _watchdog(tmp_path, Clock(), poll=0.01)
    dog.start()
    try:
        assert dog._thread is not None
        assert dog._thread.daemon
    finally:
        dog.stop()
        dog._thread.join(timeout=2)


def test_the_thread_actually_writes_a_dump(tmp_path):
    """The one test that runs the real loop, with a threshold of zero so it
    does not have to wait for one."""
    dog = _watchdog(tmp_path, Clock(), stall_after=0.0, poll=0.01)
    dog.start()
    try:
        for _ in range(200):
            if (tmp_path / "stall.txt").exists():
                break
            threading.Event().wait(0.01)
    finally:
        dog.stop()
        dog._thread.join(timeout=2)

    assert (tmp_path / "stall.txt").exists(), "the watcher never wrote anything"


def test_starting_twice_does_not_leave_two_watchers(tmp_path):
    dog = _watchdog(tmp_path, Clock(), poll=0.01)
    dog.start()
    first = dog._thread
    dog.start()
    try:
        assert dog._thread is first
    finally:
        dog.stop()
        dog._thread.join(timeout=2)


# ------------------------------------------------- being found afterwards


def test_the_launch_screen_says_nothing_when_there_was_no_stall():
    from cli.tui.launch import view

    rendered = view(
        jobs=0, watches=[], lanes_held=[], ledger_runs=0, recent=[]
    ).plain
    assert "stalled" not in rendered


def test_the_launch_screen_points_at_the_dump_when_there_was_one():
    """A diagnostic nobody knows to read is the same as no diagnostic. The
    launch screen is the one place you are certainly looking after a freeze."""
    from cli.tui.launch import view

    rendered = view(
        jobs=0,
        watches=[],
        lanes_held=[],
        ledger_runs=0,
        recent=[],
        stall_dump="/home/someone/.local/state/tb/tui-stall.txt",
    ).plain
    assert "stalled" in rendered
    assert "/home/someone/.local/state/tb/tui-stall.txt" in rendered


def test_the_watchdog_stops_with_the_app_that_owns_it(tmp_path):
    """A daemon cannot hold the process open, which is not the same as being
    free — it wakes every second for as long as it runs. Building several apps
    in one process (the suite builds ~30) accumulated a poller per app, which
    showed up as a timing-sensitive test flaking about one run in six.
    """
    import asyncio
    import threading

    from cli.tui.app import TackleBox
    from cli.tui.history import History

    def alive():
        return sum(
            1 for t in threading.enumerate() if t.name == "tb-tui-watchdog" and t.is_alive()
        )

    before = alive()

    async def scenario():
        for _ in range(4):
            app = TackleBox(history=History(path=tmp_path / "hist"), watches={})
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                assert app.watchdog._thread is not None, "it should run while mounted"
            assert app.watchdog._stop.is_set(), "and be told to stop on unmount"

    asyncio.run(scenario())

    # Each is stopped; the last may still be inside its poll wait, so allow one.
    assert alive() <= before + 1
