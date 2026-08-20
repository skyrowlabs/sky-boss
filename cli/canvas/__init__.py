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


def _launch(binary: str, url: str) -> subprocess.Popen:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            binary,
            f"--app={url}",
            f"--user-data-dir={PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@click.command()
@click.option("--port", type=int, default=None, help="Bind this port instead of a free one.")
@click.option("--no-browser", is_flag=True, help="Serve only; print the URL and wait.")
@emit
def ui(port: int | None, no_browser: bool) -> Result:
    """Open the canvas — a command palette over tiled and floating windows."""
    import uvicorn

    result = Result()
    canvas = Canvas()
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

    if not no_browser:
        binary = _browser()
        if binary is None:
            result.degrade(
                "no chromium-family browser found; serving only — open " + url
            )
        else:
            def open_when_up() -> None:
                # The window must not race the bind, or it lands on a refused
                # connection and shows a browser error page for a server that
                # came up 40ms later.
                while not server.started and time.monotonic() - started < 10:
                    time.sleep(0.05)
                nonlocal browser
                browser = _launch(binary, url)
                browser.wait()
                # Closing the window ends the session. Nothing survives it —
                # that is the same rule the watchers follow, applied to the
                # process that owns them.
                server.should_exit = True

            threading.Thread(target=open_when_up, daemon=True).start()

    with contextlib.suppress(KeyboardInterrupt):
        server.run()

    if browser is not None and browser.poll() is None:
        browser.terminate()

    result.data = {
        "url": url,
        "port": port,
        "duration_s": round(time.monotonic() - started, 1),
    }
    return result


# A surface, not an entry in its own palette. Read by `cli/canvas/catalog.py`,
# which asks the command rather than keeping a list of names to skip.
ui.tb_surface = True
