"""The run ledger's path comes from the resolver, not from a second definition.

Split out of `tests/test_state_paths.py`, which now ships at **core** because
`state_dir()` and `STATE_SLUG` do. This one assertion needs
`scripts.reporting.run_ledger`, which is `agentic`, so it stays here — under its
own filename rather than as a sixth test in a replacing copy of that file.

An overlay file at the same path replaces the core one whole; adding one test
that way means carrying five duplicates of the others, which is the drift this
shell exists to prevent. A second file costs nothing and drifts from nothing.

Reported by stash.flow, who adopted at `core` and found `AGENTS.md` and
`scripts/paths.py` both citing `test_state_paths.py` — a file that shipped only
at `agentic`. The rule said *run it rather than trusting the rule*, which is good
advice a core tree could not follow.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import STATE_ROOT_ENV, STATE_SLUG  # noqa: E402
from scripts.reporting.run_ledger import ledger_path  # noqa: E402


def test_the_ledger_goes_through_the_resolver(monkeypatch, tmp_path):
    """Not merely 'is outside the repo' — actually derived from `state_dir`."""
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path))
    assert ledger_path().is_relative_to(tmp_path / STATE_SLUG)
