"""Suite-wide fixtures.

**The suite never touches the operator's real state directory.** `STATE_DIR`
holds the surface's input history and its stall dumps; a test that read or wrote
the real one would depend on — and damage — whatever the machine happens to have.

It is resolved once at import in `cli/helpers.py`, so this has to be set before
anything imports `cli`. Module level in conftest is early enough: pytest imports
it before collecting.
"""

import os
import tempfile
from pathlib import Path

_ISOLATED = Path(tempfile.mkdtemp(prefix="sb-state-")) / "state"
os.environ["SB_STATE"] = str(_ISOLATED)

# And never the operator's real sky.boss home. This one matters more than STATE_DIR:
# a tool is an argv sky.boss will *run*, so a suite that read the real home would be
# registering the operator's commands into the tree under test — and `sky.boss
# --help` would differ between two machines running the same suite.
_ISOLATED_HOME = Path(tempfile.mkdtemp(prefix="sb-home-")) / "home"
os.environ["SB_HOME"] = str(_ISOLATED_HOME)

import pytest  # noqa: E402


@pytest.fixture
def sb_state():
    """The isolated state directory, created empty."""
    _ISOLATED.mkdir(parents=True, exist_ok=True)
    return _ISOLATED


@pytest.fixture
def sb_home():
    """The isolated operator home, created empty."""
    _ISOLATED_HOME.mkdir(parents=True, exist_ok=True)
    return _ISOLATED_HOME


@pytest.fixture
def said():
    """A CliRunner result's text, free of how rich-click drew it.

    An error renders inside a box, wrapped to whatever width rich-click
    detects, so a phrase can be split by a newline *and* by the box border in
    the middle of a sentence. Asserting on the raw output is therefore a test
    about the terminal rather than about the message — seen failing at 40 and
    200 columns while passing at 80. This strips the drawing and normalises the
    whitespace, leaving what was actually said.
    """

    def read(result) -> str:
        text = result.output
        for glyph in "│╭╮╰╯─┌┐└┘":
            text = text.replace(glyph, " ")
        return " ".join(text.split())

    return read
