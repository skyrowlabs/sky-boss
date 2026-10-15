"""Shared fixtures and the environment-gate helper.

The one rule worth reading before writing a test: **a skip in CI is a failure**.
CI guarantees the environment, so "the service was not reachable" there means
the harness broke — and a harness that silently skips its whole suite reports
green, which is the single most expensive failure mode a test suite has.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Bootstrap only, and it runs before any test module is collected: put the
# package on sys.path so tests can import `scripts.paths`, which owns every
# path in the tree. A bare `pytest tests/` otherwise gets only `tests/`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: Set by CI and by `dev test --ci`. Under it, an env-gate skip becomes a failure.
CI_FLAG = "SB_CI"


def in_ci() -> bool:
    return os.environ.get(CI_FLAG) == "1"


def require_or_skip(condition: bool, reason: str, *, requires: str | None = None) -> None:
    """Skip locally, **fail** in CI.

    Use for anything CI guarantees — services running, seed data present, a
    toolchain installed. Raw ``pytest.skip`` stays legitimate for genuine
    cross-environment conditions CI does not guarantee (a GPU, a paid API key).

        require_or_skip(services_up, "the app is not reachable", requires="services")
    """
    if condition:
        return
    detail = f"{reason} (requires: {requires})" if requires else reason
    if in_ci():
        pytest.fail(f"environment gate failed in CI: {detail}. CI guarantees this — the harness is broken.")
    pytest.skip(detail)


@pytest.fixture(scope="session")
def repo_root():
    """The project root, from the module that owns it — never re-derived here.

    A fixture that works this out for itself is a second answer to a question
    with one owner, and it is the answer a test would trust. See
    `scripts/paths.py`.
    """
    from scripts.paths import PROJECT_ROOT

    return PROJECT_ROOT


@pytest.fixture(autouse=True)
def _never_the_users_state(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the state root at a fresh directory for every test.

    Unset, it falls back to the user's real state under the home directory, so a
    test that forgot it would write there. A test that sets its own still wins,
    because autouse fixtures run first. stash.flow's incident: `stash-flow@c5544b3`.
    """
    from scripts.paths import STATE_ROOT_ENV

    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path_factory.mktemp("state-root")))


@pytest.fixture(autouse=True)
def _never_the_users_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail a test that would open the user's real browser.

    A test that means to open one replaces it with a recorder, which wins
    because it is patched later. stash.flow's incident: `stash-flow@a2fe3b7`.
    """
    import webbrowser

    def refuse(name: str):
        def refused(*args, **kwargs):
            raise AssertionError(f"a test reached the real webbrowser.{name}{args!r}; replace it with a recorder")

        return refused

    for name in ("open", "open_new", "open_new_tab"):
        monkeypatch.setattr(webbrowser, name, refuse(name))


@pytest.fixture(autouse=True)
def _never_the_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a unit test on loopback and away from every secret-shaped variable. See `tests/guards.py`.

    Other suites may reach real services by design. A test that patches the socket
    itself still wins, because it is patched later.
    """
    if request.node.get_closest_marker("unit") is None:
        return
    from tests.guards import hide_secrets, refuse_remote

    hide_secrets(monkeypatch)
    refuse_remote(monkeypatch)


# ── Your fixtures go below this line ──────────────────────────────────────────
#
# skeletor adds its fixtures and imports above this block and renders nothing
# below it, so a release's lines and yours are never adjacent and merge cleanly.
# Keep the imports your fixtures need below this line too, or inside the fixture
# that uses them: one placed among the template's imports conflicts there.
# The block itself is frozen. Asked for by proto.pilot, whose fixtures at the end
# of this file conflicted with the template's at v0.49.0 and again at v0.51.0.

# Suite-wide isolation, sky.boss's own.
#
# **The suite never touches the operator's real state directory.** `STATE_DIR`
# holds the surface's input history and its stall dumps; a test that read or wrote
# the real one would depend on — and damage — whatever the machine happens to have.
#
# It is resolved once at import in `skyboss/helpers.py`, so this has to be set
# before anything imports `skyboss`. Module level in conftest is early enough:
# pytest imports it before collecting, and nothing above the rule imports it.

import re  # noqa: E402 - below the rule, as the block asks
import tempfile  # noqa: E402

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
    """Make `skyboss.output._out()` report a terminal for this test.

    `--refresh` refuses without one ([[refresh]] round 3), and a `CliRunner`
    never has one. A test that drives the resident *plumbing* — that `--screen`
    reaches the loop, that `--save` writes before residency — is standing in for
    an operator at a terminal, and this is that claim made out loud rather than
    left implicit in the absence of a check.

    It does not make anything render: those tests stub `resident.reside`. It
    only gets them through the door.
    """
    from rich.console import Console

    from skyboss.output import THEME

    monkeypatch.setattr("skyboss.output.console", Console(theme=THEME, highlight=False, force_terminal=True))
