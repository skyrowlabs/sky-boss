"""tb ui — the canvas.

A command palette over a window canvas: every command opens a window, windows
tile or float, and a pinned window re-runs its command on a cadence. It
replaces `tb tui`, which proved the output contract works with a second
consumer and then ran into the ceiling of its medium — overlapping draggable
windows are the central metaphor here, and a terminal cannot do them.

**A surface, not a verb.** It renders the same envelope every command returns
rather than adding one of its own, which is why `tb run` stays the only door
that acts even with the canvas in front of it.

The browser is a launch flag rather than an architecture. `--app=` gives a
chromeless window with its own taskbar entry; swapping to a native webview
later replaces this module and nothing else, because everything the page talks
to is HTTP.
"""

from __future__ import annotations

import contextlib
import shutil
import socket
import subprocess
import threading
import time

import rich_click as click

from cli.canvas.server import Canvas, build
from cli.helpers import STATE_DIR
from cli.output import Result, emit

# In preference order. All four are on workstation; the first three take `--app`,
# which is the whole reason this is not just `webbrowser.open`.
BROWSERS = ("chromium", "google-chrome-stable", "google-chrome", "brave")

# A profile of the canvas's own. Two reasons, and the second is the real one:
# window geometry persists across launches, and a stray `--app` on the default
# profile hands off to the already-running Chrome and returns immediately,
# leaving nothing to wait on and no way to know the window ever opened.
PROFILE_DIR = STATE_DIR / "browser-profile"

# Only ever used on a first run; after that the profile remembers.
FIRST_RUN_SIZE = "1600,1000"



def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _browser() -> str | None:
    for name in BROWSERS:
        found = shutil.which(name)
        if found:
            return found
    return None


def _launch(binary: str, url: str, *, kiosk: bool, size: str | None) -> subprocess.Popen:
    """Open the surface, with as little browser around it as the mode allows.

    `--app` already removes the tab strip, the address bar and the bookmarks
    bar. What it cannot remove is the frame, which the window manager draws —
    and **there is no Chromium flag for a frameless window that is still
    resizable.** `--kiosk` drops the frame by going full-screen, which is a
    different thing and not a substitute: a full-screen window cannot be sized
    or moved. It stays available for a wall display and is not the default.

    Removing the title bar while keeping the window sizable is the window
    manager's job, not the browser's. On KDE that is a KWin rule matched on the
    window class, which is why `--class` is set here — but a rule is a change to
    the operator's own desktop and belongs to them to make.

    `--size` overrides the remembered geometry; without it the profile
    remembers, and a first run gets a sensible default rather than whatever
    Chromium would otherwise pick.
    """
    first_run = not PROFILE_DIR.exists()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    argv = [
        binary,
        f"--app={url}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        # So the window manager files it under its own name rather than
        # grouping it with every other Chromium window.
        "--class=tackle-box",
    ]
    if kiosk:
        argv.append("--kiosk")
    elif size:
        argv.append(f"--window-size={size}")
    elif first_run:
        argv.append(f"--window-size={FIRST_RUN_SIZE}")

    return subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@click.command()
@click.option("--port", type=int, default=None, help="Bind this port instead of a free one.")
@click.option("--no-browser", is_flag=True, help="Serve only; print the URL and wait.")
@click.option(
    "--kiosk",
    is_flag=True,
    help="Full-screen with no frame. Not sizable — for a wall display.",
)
@click.option(
    "--size",
    default=None,
    help="Window geometry as WIDTH,HEIGHT. Otherwise the profile remembers.",
)
@click.option(
    "--scale",
    type=float,
    default=2.0,
    show_default=True,
    help="How big the surface renders. Every size derives from this.",
)
@emit
def ui(
    port: int | None, no_browser: bool, kiosk: bool, size: str | None, scale: float
) -> Result:
    """Open the canvas — a command palette over tiled and floating windows."""
    import uvicorn

    result = Result()
    if scale <= 0:
        result.ok = False
        result.data = {"error": "--scale must be positive"}
        return result
    canvas = Canvas(scale=scale)
    port = port or _free_port()
    url = f"http://127.0.0.1:{port}/"

    config = uvicorn.Config(
        build(canvas),
        host="127.0.0.1",
        port=port,
        log_level="warning",
        # Nothing off this machine can reach the port, and the access log would
        # otherwise print a line per watcher tick into the launching terminal.
        access_log=False,
    )
    server = uvicorn.Server(config)

    # uvicorn installs signal handlers only on the main thread, so the server
    # runs there and the browser is watched from a helper. The alternative —
    # server on a thread — silently loses Ctrl-C.
    browser = None
    started = time.monotonic()

    def stop() -> None:
        server.should_exit = True

    # The surface's own close button, watched in every mode. It used to be
    # watched only inside the browser thread, so with `--no-browser` — the mode
    # you develop in — pressing it set the latch and nothing happened.
    threading.Thread(
        target=lambda: canvas.quitting.wait() and stop(), daemon=True
    ).start()

    with contextlib.suppress(KeyboardInterrupt):
        server.run()

    if browser is not None and browser.poll() is None:
        browser.terminate()

    result.data = {
        "url": url,
        "port": port,
        "scale": scale,
        "mode": "full-screen" if kiosk else "windowed",
        "duration_s": round(time.monotonic() - started, 1),
    }
    return result


# A surface, not an entry in its own palette. Read by `cli/canvas/catalog.py`,
# which asks the command rather than keeping a list of names to skip.
ui.tb_surface = True
