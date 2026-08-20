"""The canvas's backend: a loopback HTTP server that runs tb commands.

**This is remote code execution bound to a port, and it is treated that way.**
A page on any website you happen to have open can POST to `127.0.0.1` — it
cannot read the response, because CORS blocks that, but a blind POST that runs
a command is more than enough harm. Four things stand in the way, and none of
them is optional:

1. **Bound to loopback** on an ephemeral port. Nothing off this machine can
   reach it at all.
2. **A custom header is required on every API route.** This is the load-bearing
   one, and it works through the browser rather than around it: a cross-origin
   request carrying `X-TB-Token` stops being a "simple request", so the browser
   must preflight it — and the preflight is answered with a refusal, so the
   real request is never sent. A form POST or an `img` tag cannot set a header
   at all.
3. **The token is checked**, minted fresh per launch and never written to disk.
   Point 2 stops a web page; this stops anything on the machine that guessed
   the port.
4. **`Origin` is rejected when it is not ours.** Belt and braces with 2.

The token reaches the page by being written into the HTML that the page is. A
hostile site cannot read it back out — a cross-origin read of our HTML is
exactly what the same-origin policy has always forbidden.

Note what is *not* here: no CORS allow-origin header anywhere. That absence is
a feature, and adding one to make something work would undo most of the above.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import threading
import uuid
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from cli.canvas import runner
from cli.canvas.catalog import catalog
from cli.canvas.watch import INTERVALS, Session
from cli.theme import css_root, css_variables

STATIC = Path(__file__).resolve().parent / "static"

TOKEN_HEADER = "x-tb-token"

# How often the scheduler looks for a due watcher. Finer than the shortest
# cadence so a 5s watcher is not systematically late, coarse enough that an
# idle canvas is not a busy loop.
TICK_SECONDS = 0.5

# Sent when nothing has happened, so a dead connection is noticed rather than
# lingering as a session whose watchers still fire into a socket nobody reads.
HEARTBEAT_SECONDS = 15.0

# How often the static files are checked for an edit. Nine `stat` calls on a
# local disk, so the cost is not worth tuning; this only bounds how long you
# stare at a stale page after saving.
RELOAD_POLL_SECONDS = 0.5


class Canvas:
    """One server instance. Holds the token and the live sessions."""

    def __init__(self, *, token: str | None = None, scale: float = 2.0) -> None:
        self.token = token or secrets.token_urlsafe(32)
        self.sessions: dict[str, Session] = {}
        # How big the surface renders. One number, injected into the page, that
        # every size in the stylesheet is measured in.
        self.scale = scale
        # Set when the page asks to quit. `tb ui` watches it, because the
        # window has no frame of its own and so no close button but ours.
        self.quitting = threading.Event()

    # ------------------------------------------------------------------ auth

    def authorised(self, request: Request) -> bool:
        """Header first, then origin. Both, every time, on every API route."""
        if not secrets.compare_digest(
            request.headers.get(TOKEN_HEADER, ""), self.token
        ):
            return False
        origin = request.headers.get("origin")
        if origin is not None and origin != _own_origin(request):
            return False
        return True


def _own_origin(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


def _denied() -> JSONResponse:
    # Deliberately says nothing about which check failed.
    return JSONResponse({"error": "unauthorised"}, status_code=403)


def build(canvas: Canvas | None = None) -> Starlette:
    """The ASGI app. Takes its `Canvas` so a test can pin the token."""
    canvas = canvas or Canvas()

    async def index(request: Request) -> Response:
        """The page, with the token written into it.

        Not an API route, so no header is required — a top-level navigation
        cannot send one. Its secrecy rests on the same-origin policy instead.
        """
        html = (STATIC / "index.html").read_text()
        # Palette first. Neither placeholder is a prefix of the other in a way
        # that matters — `__TB_TOKENS__` has an S where `__TB_TOKEN__` has its
        # closing underscores — but ordering them makes that not need checking.
        html = html.replace("__TB_TOKENS__", css_root())
        html = html.replace("__TB_SCALE__", str(canvas.scale))
        return HTMLResponse(html.replace("__TB_TOKEN__", canvas.token))

    async def favicon(request: Request) -> Response:
        """The window's own mark, drawn from the palette.

        Without it the taskbar and the title show Chromium's default globe, so
        a surface that has gone to the trouble of having no browser chrome
        still announces itself as a browser. It is generated rather than
        stored because a static `.svg` would have to name a colour, and nothing
        outside `cli/theme.py` may.
        """
        tokens = css_variables()
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
            f'<rect width="32" height="32" rx="7" fill="{tokens["tb-surface"]}"/>'
            f'<rect x="3.5" y="3.5" width="25" height="25" rx="5.5" fill="none" '
            f'stroke="{tokens["tb-brand"]}" stroke-opacity=".45"/>'
            f'<path d="M9 12h14" stroke="{tokens["tb-brand"]}" stroke-width="2.5" '
            'stroke-linecap="round"/>'
            f'<path d="M9 18h9" stroke="{tokens["tb-text-2"]}" stroke-width="2.5" '
            'stroke-linecap="round"/>'
            f'<path d="M9 23h5" stroke="{tokens["tb-text-3"]}" stroke-width="2.5" '
            'stroke-linecap="round"/>'
            "</svg>"
        )
        return Response(svg, media_type="image/svg+xml", headers={"cache-control": "no-cache"})

    async def post_quit(request: Request) -> Response:
        """The close button. Guarded like every other route.

        Shutting the surface down is a real effect, so it goes through the same
        token and origin checks as running a command — a page you did not open
        must not be able to end your session any more than it may start one.

        This does not call `window.close()`. That is only reliably permitted on
        a window a script opened, and a kiosk window is not one; setting a latch
        that `tb ui` is waiting on works the same in every mode and leaves the
        server in charge of its own shutdown.
        """
        if not canvas.authorised(request):
            return _denied()
        canvas.quitting.set()
        return JSONResponse({"quitting": True})

    async def get_catalog(request: Request) -> Response:
        if not canvas.authorised(request):
            return _denied()
        return JSONResponse({"commands": catalog(), "intervals": list(INTERVALS)})

    async def post_run(request: Request) -> Response:
        if not canvas.authorised(request):
            return _denied()
        body = await request.json()
        argv = [str(a) for a in (body.get("argv") or [])]
        if not argv:
            return JSONResponse({"error": "no argv"}, status_code=400)
        timeout = body.get("timeout") or runner.DEFAULT_TIMEOUT
        # to_thread, because `subprocess.run` blocks and the loop is also
        # driving every open stream. Same rule the TUI learned the hard way, in
        # a new medium: no single turn of the event loop may be unbounded.
        result = await asyncio.to_thread(runner.run, argv, timeout=int(timeout))
        return JSONResponse(result.to_dict())

    async def post_watch(request: Request) -> Response:
        """Register, re-point, or stop one window's watcher."""
        if not canvas.authorised(request):
            return _denied()
        body = await request.json()
        session = canvas.sessions.get(str(body.get("session") or ""))
        if session is None:
            # The stream died and the page has not noticed yet. Not an error
            # worth shouting about; the client reconnects and re-registers.
            return JSONResponse({"error": "no such session"}, status_code=409)
        window_id = str(body.get("window") or "")
        if not window_id:
            return JSONResponse({"error": "no window"}, status_code=400)

        interval = int(body.get("interval") or 0)
        if body.get("stop"):
            session.drop(window_id)
            return JSONResponse({"watching": False})

        argv = [str(a) for a in (body.get("argv") or [])]
        if not argv:
            return JSONResponse({"error": "no argv"}, status_code=400)
        session.set(window_id, argv, interval)
        return JSONResponse({"watching": True, "interval": interval})

    async def stream(request: Request) -> Response:
        """The session. Newline-delimited JSON for as long as the window lives.

        Not `text/event-stream` with `EventSource`, for one concrete reason:
        `EventSource` cannot set a request header, and the header is what forces
        the preflight that keeps a hostile page out. A streaming `fetch` can,
        so the auth story stays uniform across every route instead of carving
        out an exception for the one that matters most.
        """
        if not canvas.authorised(request):
            return _denied()

        session = Session(id=uuid.uuid4().hex)
        canvas.sessions[session.id] = session
        return StreamingResponse(
            stream_frames(canvas, session),
            media_type="application/x-ndjson",
            headers={"cache-control": "no-store", "x-accel-buffering": "no"},
        )

    app = Starlette(
        routes=[
            Route("/", index),
            Route("/favicon.svg", favicon),
            Route("/api/catalog", get_catalog),
            Route("/api/run", post_run, methods=["POST"]),
            Route("/api/watch", post_watch, methods=["POST"]),
            Route("/api/quit", post_quit, methods=["POST"]),
            Route("/api/stream", stream),
            Mount("/static", NoCacheStatic(directory=STATIC), name="static"),
        ]
    )
    app.state.canvas = canvas
    return app


class NoCacheStatic(StaticFiles):
    """Static files that must be revalidated before use.

    `no-cache` does not mean "do not cache" — it means "ask first", so the ETag
    still answers with a 304 and nothing is re-sent. Without it the browser
    applies heuristic freshness and may serve a file it fetched moments ago
    from memory, which is exactly the window in which live reload operates.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["cache-control"] = "no-cache"
        return response


def _frame(payload: dict) -> str:
    return json.dumps(payload, default=str) + "\n"


def fingerprint(directory: Path = STATIC) -> dict[str, float]:
    """Modification times of everything the page is made of.

    Vendored code is skipped — it does not change, and it is the bulk of the
    directory.
    """
    return {
        str(path.relative_to(directory)): path.stat().st_mtime
        for path in directory.rglob("*")
        if path.is_file() and "vendor" not in path.parts
    }


def changed(before: dict[str, float], after: dict[str, float]) -> list[str]:
    """Which files differ. Additions and deletions count as changes."""
    return sorted(
        name
        for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    )


async def stream_frames(
    canvas: Canvas,
    session: Session,
    *,
    run=None,
    tick: float = TICK_SECONDS,
    heartbeat: float = HEARTBEAT_SECONDS,
    watch_files: bool = True,
):
    """One session's whole life, as frames.

    Lifted out of the route so it can be driven directly. Starlette's
    `TestClient` collects an entire response body before it returns, so a stream
    that never ends can never be opened through it — the first version of the
    test for this hung rather than failed. Everything interesting here is the
    loop rather than the HTTP framing, so the loop is what a test should get to
    hold.

    `run`, `tick` and `heartbeat` are injectable for the same reason
    `cli/tui/watchdog.py` took its clock: proving a five-second cadence should
    not cost five seconds of suite, and proving a watcher fires should not
    require actually starting a subprocess.
    """
    runner_fn = run or runner.run
    queue: asyncio.Queue = asyncio.Queue()
    tasks: set[asyncio.Task] = set()
    stamps = fingerprint() if watch_files else {}
    since_scan = 0.0

    async def fire(watcher) -> None:
        session.claim(watcher)
        try:
            result = await asyncio.to_thread(runner_fn, list(watcher.argv))
            await queue.put(
                {"type": "run", "window": watcher.window_id, "result": result.to_dict()}
            )
        finally:
            session.release(watcher)

    idle = 0.0
    try:
        # Inside the try, not before it. Suspended at a yield outside the
        # `try`, a `GeneratorExit` skips the `finally` entirely — so a window
        # that opened and closed again before its first tick used to leak its
        # session for the life of the server. Nothing else would ever remove it,
        # because removal is this `finally` and nothing else.
        yield _frame({"type": "hello", "session": session.id})
        while True:
            for watcher in session.due():
                task = asyncio.create_task(fire(watcher))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            if watch_files:
                since_scan += tick
                if since_scan >= RELOAD_POLL_SECONDS:
                    since_scan = 0.0
                    # stat() is blocking, so it goes off the loop like every
                    # other blocking call here. Nine files is fast enough that
                    # this looks like superstition, and it is the discipline
                    # that keeps the rule "no unbounded turn" true by default
                    # rather than by luck.
                    fresh = await asyncio.to_thread(fingerprint)
                    edited = changed(stamps, fresh)
                    if edited:
                        stamps = fresh
                        await queue.put({"type": "reload", "files": edited})

            drained = False
            while not queue.empty():
                yield _frame(queue.get_nowait())
                drained = True
            idle = 0.0 if drained else idle + tick
            if idle >= heartbeat:
                idle = 0.0
                yield _frame({"type": "beat"})
            await asyncio.sleep(tick)
    finally:
        # The session dies with the stream. This is the whole mechanism: no
        # watcher outlives the window that asked for it, and there is nothing to
        # clean up later because there is nothing left.
        #
        # Reached through `GeneratorExit` when the consumer goes away, rather
        # than by polling `request.is_disconnected()`. That call never returns
        # under `TestClient` — its receive channel yields no disconnect until
        # the response is drained, and a stream is never drained. The cost is
        # that a dropped connection is noticed on the next write instead of
        # immediately, which is what the heartbeat is for.
        for task in tasks:
            task.cancel()
        canvas.sessions.pop(session.id, None)
