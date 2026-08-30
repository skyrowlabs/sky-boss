"""Suite-wide fixtures.

**The suite never touches the operator's real state directory.** `STATE_DIR`
holds the surface's input history and its stall dumps; a test that read or wrote
the real one would depend on — and damage — whatever the machine happens to have.

It is resolved once at import in `cli/helpers.py`, so this has to be set before
anything imports `cli`. Module level in conftest is early enough: pytest imports
it before collecting.
"""

import os
import re
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

# And never the *agent-state* root, which is a third environment the suite must
# not inherit. Unlike the two above it has no sky.boss-owned default to fall back
# to — it is read straight from the operator's environment — so a suite run in a
# shell that exports it would resolve real project directories and a suite run
# without one would not. Cleared rather than redirected: an undeclared root is a
# state the tests need to exercise, and each test that wants one sets it.
os.environ.pop("SL_AGENT_LOGS", None)

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


# Every escape sequence rich can emit, not only the colour ones: a strip that
# knows about `\x1b[…m` and nothing else leaves a cursor move sitting in the
# middle of a sentence, which is the same failure wearing a different code.
_ESCAPES = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


@pytest.fixture
def said():
    """A CliRunner result's text, free of how rich-click drew it.

    An error renders inside a box, wrapped to whatever width rich-click
    detects, so a phrase can be split by a newline *and* by the box border in
    the middle of a sentence. Asserting on the raw output is therefore a test
    about the terminal rather than about the message — seen failing at 40 and
    200 columns while passing at 80. This strips the drawing and normalises the
    whitespace, leaving what was actually said.

    **Colour is part of the drawing, and leaving it in cost CI three days.**
    rich reads `GITHUB_ACTIONS` and calls a runner a terminal — deliberately,
    so an Actions log comes out coloured — so every option name in a usage
    error arrives wrapped in escapes and `--ticks needs --refresh` stops being
    a substring of itself. Nothing here has a terminal and the suite passed on
    every developer machine; the runner is the only place the drawing happens.
    That it reported *one* failure where this file reproduces three is the
    width argument above restated: the codes land in different places at
    different widths, so which assertion breaks is a coincidence and the class
    is not.
    """

    def read(result) -> str:
        text = _ESCAPES.sub("", result.output)
        for glyph in "│╭╮╰╯─┌┐└┘":
            text = text.replace(glyph, " ")
        return " ".join(text.split())

    return read


@pytest.fixture
def at_a_terminal(monkeypatch):
    """Make `cli.output._out()` report a terminal for this test.

    `--refresh` refuses without one ([[refresh]] round 3), and a `CliRunner`
    never has one. A test that drives the resident *plumbing* — that `--screen`
    reaches the loop, that `--save` writes before residency — is standing in for
    an operator at a terminal, and this is that claim made out loud rather than
    left implicit in the absence of a check.

    It does not make anything render: those tests stub `resident.reside`. It
    only gets them through the door.
    """
    from rich.console import Console

    from cli.output import THEME

    monkeypatch.setattr(
        "cli.output.console", Console(theme=THEME, highlight=False, force_terminal=True)
    )
