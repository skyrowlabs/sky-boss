"""The native shell, as far as a machine with no GTK can see it.

`open_window` blocks on a real toolkit, so these stand a fake `webview` in
`sys.modules` and read back what the shell asked for. That is enough for the
one thing here worth pinning: a keyword argument whose library default quietly
changes the page.
"""

import os
import sys
import types

import pytest

from skyboss import helpers
from skyboss.canvas import shell

#: Every test here is host-side and needs no services up.
pytestmark = [pytest.mark.unit]


def test_the_native_window_leaves_text_selectable(monkeypatch):
    """pywebview's `text_select` defaults to False, and on False it injects
    `body { user-select: none }` into the page — so the native window was the
    one shell where nothing could be selected, with a stylesheet that never
    said so. See [[canvas]] round 15."""
    asked = {}

    class Hook:
        def __iadd__(self, handler):
            return self

    class Window:
        events = types.SimpleNamespace(closed=Hook())

    def create_window(*args, **kwargs):
        asked.update(kwargs)
        return Window()

    fake = types.SimpleNamespace(create_window=create_window, start=lambda **_: None, windows=[])
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(shell, "ENVIRONMENT", {})
    monkeypatch.setattr(shell, "_name_the_window", lambda: None)

    shell.open_window("http://127.0.0.1:1/", title="t", width=640, height=400, on_closed=lambda: None)

    assert asked["text_select"] is True


def _open_with(monkeypatch, environment):
    """Open a fake native window with `environment` as the shell's table."""

    class Hook:
        def __iadd__(self, handler):
            return self

    window = types.SimpleNamespace(events=types.SimpleNamespace(closed=Hook()))
    fake = types.SimpleNamespace(create_window=lambda *a, **k: window, start=lambda **_: None, windows=[])
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(shell, "ENVIRONMENT", environment)
    monkeypatch.setattr(shell, "_name_the_window", lambda: None)
    shell.open_window("http://127.0.0.1:1/", title="t", width=640, height=400, on_closed=lambda: None)


def test_the_window_never_asks_networkmanager_whether_loopback_is_up():
    """WebKit waits on NetworkManager before loading a page; GLib's own monitor does not wait."""
    assert shell.ENVIRONMENT["GIO_USE_NETWORK_MONITOR"] == "base"


def test_the_window_records_what_it_set_and_leaves_the_operators_own(monkeypatch):
    """A name the operator set keeps their value and is not recorded as sky.boss's."""
    monkeypatch.setattr(helpers, "ADDED", set())
    monkeypatch.setenv("FX_SET", "x")
    monkeypatch.delenv("FX_SET")
    monkeypatch.setenv("FX_KEPT", "mine")

    _open_with(monkeypatch, {"FX_SET": "1", "FX_KEPT": "1"})

    assert os.environ["FX_SET"] == "1" and os.environ["FX_KEPT"] == "mine"
    assert helpers.ADDED == {"FX_SET"}


def test_a_command_the_canvas_runs_does_not_inherit_the_windows_environment(monkeypatch):
    """What the window set is dropped from a child; what the operator set reaches it."""
    monkeypatch.setattr(helpers, "ADDED", set())
    monkeypatch.setenv("FX_SET", "x")
    monkeypatch.delenv("FX_SET")
    monkeypatch.setenv("FX_KEPT", "mine")

    _open_with(monkeypatch, {"FX_SET": "1", "FX_KEPT": "1"})
    env = helpers.child_env()

    assert "FX_SET" not in env
    assert env["FX_KEPT"] == "mine"
