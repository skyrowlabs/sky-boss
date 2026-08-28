"""`sb ui` — the canvas.

A command palette over a window canvas: every command opens a window, windows
tile or float, and a pinned window re-runs itself on a cadence. It replaces
`sb tui`, which proved the output contract works with a second consumer and
then ran into the ceiling of its medium — overlapping draggable windows are the
central metaphor here, and a terminal cannot do them.

**A surface, not a verb.** It renders the same envelope every command returns
rather than adding one of its own, which is why `sb run` stays the only door
that acts even with the canvas in front of it.

The window is a native webview (`cli/canvas/shell.py`), which is what makes it
frameless, resizable, and draggable by its own bar. `--browser` opens it in
Chromium instead, and `--no-browser` serves only — the mode to develop in,
since it is the one where a page reload is the whole loop.
"""

from __future__ import annotations

import contextlib
import shutil
import socket
import subprocess
import threading
import time

import rich_click as click

from cli.canvas import shell
from cli.canvas.server import Canvas, build
from cli.helpers import STATE_DIR
from cli.output import Result, emit

# In preference order, for `--browser`. The first three take `--app`, which is
# the whole reason this is not `webbrowser.open`.
BROWSERS = ("chromium", "google-chrome-stable", "google-chrome", "brave")

# A profile of the canvas's own, for `--browser`. Window geometry persists
# across launches, and a stray `--app` on the default profile hands off to the
# already-running Chrome and returns immediately, leaving nothing to wait on.
PROFILE_DIR = STATE_DIR / "browser-profile"

# Only used when nothing else says otherwise.
DEFAULT_SIZE = (1600, 1000)


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


def _parse_size(size: str | None) -> tuple[int, int]:
    if not size:
        return DEFAULT_SIZE
    try:
        width, height = (int(part) for part in size.replace("x", ",").split(","))
    except ValueError:
        raise click.BadParameter("expected WIDTH,HEIGHT") from None
    return width, height


def _launch_browser(binary: str, url: str, *, kiosk: bool, size: str | None) -> subprocess.Popen:
    """Open the surface in Chromium, with as little browser around it as it allows.

    `--app` removes the tab strip, the address bar and the bookmarks bar. What
    it cannot remove is the frame, and no flag can while leaving the window
    resizable — which is what the native shell is for. `--kiosk` drops the
    frame by going full-screen, a different thing, kept for a wall display.
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
        "--class=sb",
    ]
    if kiosk:
        argv.append("--kiosk")
    elif size or first_run:
        width, height = _parse_size(size)
        argv.append(f"--window-size={width},{height}")

    return subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@click.command()
@click.option("--port", type=int, default=None, help="Bind this port instead of a free one.")
@click.option("--no-browser", is_flag=True, help="Serve only; print the URL and wait.")
@click.option("--browser", is_flag=True, help="Open in Chromium instead of a native window.")
@click.option(
    "--kiosk",
    is_flag=True,
    help="Full-screen with no frame, for a wall display. Implies --browser.",
)
@click.option("--size", default=None, help="Window geometry as WIDTH,HEIGHT.")
@click.option(
    "--scale",
    type=float,
    default=1.15,
    show_default=True,
    help="How big the surface renders. Every size derives from this.",
)
@emit
def ui(
    port: int | None,
    no_browser: bool,
    browser: bool,
    kiosk: bool,
    size: str | None,
    scale: float,
) -> Result:
    """Open the canvas — a command palette over tiled and floating windows.

    A surface, not a verb: it renders the same envelope every command returns
    and adds none of its own, which is why `sb run` stays the only door that
    acts even with the canvas in front of it. Development mode:

        sb ui --no-browser --port 8765
    """
    import uvicorn

    result = Result()
    if scale <= 0:
        result.ok = False
        result.data = {"error": "--scale must be positive"}
        return result

    width, height = _parse_size(size)
    canvas = Canvas(scale=scale)
    port = port or _free_port()
    url = f"http://127.0.0.1:{port}/"

    use_browser = browser or kiosk
    if not use_browser and not no_browser and not shell.available():
        use_browser = True
        result.degrade("no native webview available; falling back to a browser window")

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
    # uvicorn installs signal handlers only from the main thread, and the
    # native shell demands that thread for itself. Declining them is the price
    # of the window: Ctrl-C in the launching terminal is handled below instead.
    server.install_signal_handlers = False

    started = time.monotonic()
    mode = "native"

    # Whatever else has to be torn down when the session ends. Popped rather
    # than iterated, so the two ways out — the window closing, and the
    # surface's own close button — cannot each run it.
    closers: list = []

    def stop() -> None:
        server.should_exit = True
        # And do not wait for open connections. Every session holds a stream
        # that never ends on its own, so there is nothing for a graceful
        # shutdown to wait *for* — it would sit until the heartbeat noticed a
        # socket nobody is reading.
        server.force_exit = True
        while closers:
            closers.pop()()

    # The surface's own close button, watched in every mode. It used to be
    # watched only inside the browser thread, so with `--no-browser` — the mode
    # you develop in — pressing it set the latch and nothing happened.
    threading.Thread(target=lambda: canvas.quitting.wait() and stop(), daemon=True).start()

    def wait_for_bind() -> None:
        # The window must not race the bind, or it lands on a refused
        # connection and shows an error page for a server that came up 40ms
        # later.
        while not server.started and time.monotonic() - started < 10:
            time.sleep(0.05)

    if no_browser:
        mode = "headless"
        with contextlib.suppress(KeyboardInterrupt):
            server.run()

    elif use_browser:
        mode = "kiosk" if kiosk else "browser"
        binary = _browser()
        if binary is None:
            result.degrade(f"no chromium-family browser found; serving only — open {url}")
            with contextlib.suppress(KeyboardInterrupt):
                server.run()
        else:
            proc: list[subprocess.Popen] = []

            def open_when_up() -> None:
                wait_for_bind()
                proc.append(_launch_browser(binary, url, kiosk=kiosk, size=size))
                proc[0].wait()
                # Nothing survives the last window — the same rule the watchers
                # follow, applied to the process that owns them.
                stop()

            threading.Thread(target=open_when_up, daemon=True).start()
            with contextlib.suppress(KeyboardInterrupt):
                server.run()
            if proc and proc[0].poll() is None:
                proc[0].terminate()

    else:
        # GTK owns the main thread, so the server moves to a worker — the
        # reverse of every other mode here, and the one real consequence of
        # the swap.
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        wait_for_bind()
        # The close button reaches the server, and the server has to be able to
        # reach the window. Without this the ✕ stopped serving and left the
        # window on screen.
        closers.append(shell.close_window)
        with contextlib.suppress(KeyboardInterrupt):
            shell.open_window(
                url,
                title="sky.boss",
                width=width,
                height=height,
                on_closed=stop,
            )
        stop()
        thread.join(timeout=5)

    result.data = {
        "url": url,
        "port": port,
        "scale": scale,
        "mode": mode,
        "duration_s": round(time.monotonic() - started, 1),
    }
    return result


# A surface, not an entry in its own palette. Read by `cli/canvas/catalog.py`,
# which asks the command rather than keeping a list of names to skip.
ui.sb_surface = True
