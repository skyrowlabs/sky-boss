"""sky.boss's markers on a Click command, and the one thing that can go wrong.

`sb_acts`, `sb_surface`, `sb_resident` and `sb_mcp` are this tool's extensions
to Click's `Command`. Click declares none of them, so they are written by
`setattr` and read by `getattr` with a default — and **that pairing is the
defect**: every reader spells the name as a string and supplies a fallback, so a
misspelled *write* lands as a real attribute nobody looks at and the reader goes
on returning its default forever. `job_run.sb_act = True` would leave an acting
command reachable with a refresh cadence, silently, with a green suite. The
silent path and the healthy path are the same bytes.

`helpers.mark` closes the write side by refusing an unknown name. This file
closes the read side, and it does it by **recomputing** the set of names the
tree actually reads rather than by listing the four it knows about — a list
would pin these four and stay silent on the fifth.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from skyboss.helpers import MARKERS, mark

pytestmark = [pytest.mark.unit]

PRODUCT = Path(__file__).resolve().parents[1] / "skyboss"

#: `getattr(command, "sb_acts", False)` — a marker being read off a command.
_READ = re.compile(r"""getattr\(\s*\w+\s*,\s*["'](?P<name>sb_\w+)["']""")


def markers_read() -> dict[str, list[str]]:
    """`{marker: [where it is read]}`, recomputed from the source."""
    found: dict[str, list[str]] = {}
    for path in sorted(PRODUCT.rglob("*.py")):
        for match in _READ.finditer(path.read_text(encoding="utf-8")):
            found.setdefault(match.group("name"), []).append(str(path.relative_to(PRODUCT)))
    return found


def test_the_scan_finds_markers_being_read():
    """A scan that finds nothing is a check that passed having looked at nothing."""
    assert len(markers_read()) >= 4, "the getattr idiom changed shape — this file is now blind"


def test_every_marker_read_is_a_marker_that_can_be_written():
    """The direction that catches a *reader* nobody can satisfy.

    A `getattr(command, "sb_new", …)` with no matching name in `MARKERS` is a
    switch that is permanently off: `mark` refuses to set it, so it can only
    ever return its default.
    """
    for name, sites in sorted(markers_read().items()):
        assert name in MARKERS, (
            f"{name} is read in {sorted(set(sites))} but is not in `helpers.MARKERS`, so "
            f"`mark()` refuses to set it and it is permanently its default. Add it to MARKERS."
        )


def test_every_writable_marker_is_read_by_something():
    """The other direction, which catches a marker that outlived its reader."""
    read = markers_read()
    for name in sorted(MARKERS):
        assert name in read, (
            f"{name} is in `helpers.MARKERS` but nothing in skyboss/ reads it. Either a "
            "consumer was deleted and this is dead, or the reader stopped using `getattr` "
            "and this file has gone blind on it."
        )


def test_a_misspelled_marker_is_refused_rather_than_set():
    """The whole reason `mark` exists. Plain assignment cannot do this."""

    class Fake:
        pass

    command = Fake()
    with pytest.raises(AttributeError, match="not a sky.boss marker"):
        mark(command, sb_act=True)
    assert not hasattr(command, "sb_act"), "the refusal must not have written it first"


def test_a_known_marker_is_set():
    class Fake:
        pass

    command = Fake()
    mark(command, sb_acts=True, sb_mcp=False)
    assert getattr(command, "sb_acts") is True
    assert getattr(command, "sb_mcp") is False
