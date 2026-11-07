"""A pytest plugin that moves this process's clock forward before collection.

Loaded with `-p`, because a plugin imported that early is the only way to shift the
clock before a test module computes a date at import time. `dev test clock-ahead`
sets `CLOCK_AHEAD_DAYS` and is the caller. `time-machine` patches this process only,
so a child a test spawns keeps the real clock.
"""

from __future__ import annotations

import datetime
import os

import pytest
import time_machine

_shift = time_machine.travel(
    datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=int(os.environ["CLOCK_AHEAD_DAYS"])), tick=True
)
_shift.start()


def pytest_unconfigure(config: pytest.Config) -> None:
    _shift.stop()
