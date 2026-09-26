"""The native shell, as far as a machine with no GTK can see it.

`open_window` blocks on a real toolkit, so these stand a fake `webview` in
`sys.modules` and read back what the shell asked for. That is enough for the
one thing here worth pinning: a keyword argument whose library default quietly
changes the page.
"""

import sys
import types

import pytest

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
