"""The window. A native shell around the same page.

The canvas was built browser-first on purpose — DevTools and a reload loop are
worth a great deal while a surface is being designed — with the shell recorded
as *deferred, not rejected*, and the migration promised to be "the launcher
only". This is that migration, and the promise held: the server, the frontend
and every test are untouched. Everything the page talks to is still HTTP.

**Three things a browser cannot do, which is why this exists.**

A frameless window that is still resizable. `--kiosk` drops the frame by going
full-screen, which is a different thing: it cannot be sized or moved.

A page moving its own window. There is no web API for it, so the surface's own
bar could never have been the title bar in a browser. Here it can — but not the
way pywebview documents, because **the GTK backend implements no drag regions
at all.** `pywebview-drag-region` is a Cocoa and Windows feature; GTK offers
only `easy_drag`, which makes the *whole* page a drag handle and is exactly
wrong on a canvas of draggable windows: moving a window inside the canvas would
move the canvas.

So the bar asks for the move itself. `Api.start_move` hands the request to
`Gtk.Window.begin_move_drag`, which is what a real title bar does — the window
manager takes over, so the drag snaps, tiles and crosses monitors the way every
other window on the desktop does, rather than being reimplemented in
JavaScript.

And no port is exposed to the browser at all. The page loads inside this
process's own webview, so the loopback server stops being reachable from a tab
you happen to have open. The token and origin checks stay exactly as they were —
they are what makes `--no-browser` safe, and that mode is still how you develop.

**GTK rather than Qt.** WebKitGTK 4.1 and python-gobject are already installed
on this machine, so the GTK backend downloads nothing; Qt would bundle its own
Chromium at 244 MB to do the same job. The cost is that `.venv` must be able to
see the system `gi`, which is why it sets `include-system-site-packages`.

**Two environment variables, both load-bearing, both found the hard way.**
See `ENVIRONMENT` below — a native-Wayland session cannot run this at all
without the first one.
"""

from __future__ import annotations

import os

# WebKitGTK under a native Wayland session dies on startup with
# `Gdk-Message: Error 71 (Protocol error) dispatching to Wayland display` —
# before any window appears, and with no other diagnostic. A bare GTK window
# realises fine on the same session, so the fault is WebKit's rather than
# GTK's. Under XWayland it works, so that is where it runs.
#
# The DMABUF renderer then complains `Failed to create GBM buffer` on every
# resize; the window works regardless, but the messages go to the terminal the
# operator launched from, and a working surface should not narrate at them.
ENVIRONMENT = {
    "GDK_BACKEND": "x11",
    "WEBKIT_DISABLE_DMABUF_RENDERER": "1",
}


def available() -> bool:
    """Can this machine open a native window at all?

    Checked rather than assumed, because the answer is a system library and not
    a Python package: `pywebview` installs cleanly on a box with no webview
    behind it, and the failure would otherwise arrive as a stack trace at the
    moment the operator asked for a window.
    """
    try:
        import gi

        gi.require_version("WebKit2", "4.1")
        from gi.repository import WebKit2  # noqa: F401

        import webview  # noqa: F401
    except (ImportError, ValueError):
        return False
    return True


class Api:
    """What the page may ask the shell to do.

    Deliberately tiny. This is the *only* thing the surface can reach outside
    the HTTP contract, and everything else — running commands, watching,
    quitting — still goes through the server, so `--no-browser` remains a
    complete surface rather than a degraded one.
    """

    def start_move(self) -> None:
        """Begin a window-manager drag, as a title bar would.

        Swallows its own failures. This is a cosmetic affordance reached from a
        mouse event, and an exception here would surface as a broken page
        rather than as an immovable window.
        """
        try:
            from gi.repository import Gdk

            from webview.platforms.gtk import BrowserView

            window = next(iter(BrowserView.instances.values())).window
            pointer = window.get_display().get_default_seat().get_pointer()
            _screen, x, y = pointer.get_position()
            window.begin_move_drag(1, x, y, Gdk.CURRENT_TIME)
        except Exception:
            pass


WM_CLASS = "tackle-box"


def _name_the_window() -> None:
    """Give the window a class of its own. Best effort; cosmetic if it fails.

    **The version requirements are not optional.** Importing `Gdk` without
    them pins it to a default, and pywebview's own `gi.require_version('Gtk',
    '3.0')` then raises — so it concludes GTK is unavailable, falls through to
    Qt, and reports "You must have either QT or GTK with Python extensions
    installed" on a machine where GTK is installed and working. Naming the
    window cost the shell its backend, once.
    """
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, GLib

        GLib.set_prgname(WM_CLASS)
        GLib.set_application_name("tackle-box")
        Gdk.set_program_class(WM_CLASS)
    except Exception:
        pass


def close_window() -> None:
    """Close the window from another thread.

    The counterpart to `on_closed`, and it was missing. Closing the *window*
    told the server to stop; nothing told the *window* to stop when the server
    was asked to, so the surface's own close button killed the server and left
    a dead window on screen with the process still running. The browser modes
    never showed it: one has no window, and the other terminates a child
    process it can see.

    Idempotent and silent — it races the ordinary close path by design, and
    both arriving is the normal case rather than an error.
    """
    try:
        import webview

        for window in list(webview.windows):
            window.destroy()
    except Exception:
        pass


def open_window(url: str, *, title: str, width: int, height: int, on_closed) -> None:
    """Open the canvas and block until the window closes.

    Blocking is not incidental: GTK insists on owning the main thread, so this
    is what the launcher's main thread does while the server runs beside it.
    That is the reverse of the browser shell, where uvicorn held the main
    thread — and it is the one real consequence of the swap.
    """
    import webview

    from cli.theme import BG

    # Set before the toolkit initialises, and only where the operator has not
    # already made the choice themselves.
    for name, value in ENVIRONMENT.items():
        os.environ.setdefault(name, value)

    # A stable window class, so the desktop can tell this window from every
    # other WebKit one — for the taskbar, and for a window-manager rule if the
    # operator wants one. GTK derives it from the program name, which would
    # otherwise be whatever argv[0] happened to be: `python`, or `-m`.
    _name_the_window()

    window = webview.create_window(
        title,
        url,
        width=width,
        height=height,
        frameless=True,
        # Off, and the bar drives the move instead. See Api.start_move.
        easy_drag=False,
        background_color=BG,
        min_size=(640, 400),
        js_api=Api(),
    )
    window.events.closed += on_closed
    # Named rather than inferred. pywebview probes Qt first on some
    # installations, and the failure it reports then is `No module named
    # 'qtpy'` — which sends you looking for a missing Python package when the
    # backend you actually want is right there.
    webview.start(gui="gtk")
