"""The canvas's backend: a loopback HTTP server that runs sb commands.

**This is remote code execution bound to a port, and it is treated that way.**
A page on any website you happen to have open can POST to `127.0.0.1` — it
cannot read the response, because CORS blocks that, but a blind POST that runs
a command is more than enough harm. Four things stand in the way, and none of
them is optional:

1. **Bound to loopback** on an ephemeral port. Nothing off this machine can
   reach it at all.
2. **A custom header is required on every API route.** This is the load-bearing
   one, and it works through the browser rather than around it: a cross-origin
   request carrying `X-SB-Token` stops being a "simple request", so the browser
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
import time
import uuid
from typing import NamedTuple

from cli.helpers import parse_duration
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from dataclasses import dataclass

from cli import chrome as chrome_
from cli import highlight as highlight_
from cli import stream as stream_
from cli.canvas import runner
from cli.canvas.catalog import catalog, entry_for
from cli.canvas.watch import INTERVALS, Session
from cli.theme import css_root, css_variables

STATIC = Path(__file__).resolve().parent / "static"

TOKEN_HEADER = "x-sb-token"

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

    def __init__(self, *, token: str | None = None, scale: float = 1.0) -> None:
        self.token = token or secrets.token_urlsafe(32)
        self.sessions: dict[str, Session] = {}
        # How big the surface renders. One number, injected into the page, that
        # every size in the stylesheet is measured in.
        self.scale = scale
        # Set when the page asks to quit. `sb ui` watches it, because the
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
        # that matters — `__SB_TOKENS__` has an S where `__SB_TOKEN__` has its
        # closing underscores — but ordering them makes that not need checking.
        html = html.replace("__SB_TOKENS__", css_root())
        html = html.replace("__SB_SCALE__", str(canvas.scale))
        return HTMLResponse(html.replace("__SB_TOKEN__", canvas.token))

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
            f'<rect width="32" height="32" rx="7" fill="{tokens["sb-surface"]}"/>'
            f'<rect x="3.5" y="3.5" width="25" height="25" rx="5.5" fill="none" '
            f'stroke="{tokens["sb-brand"]}" stroke-opacity=".45"/>'
            f'<path d="M9 12h14" stroke="{tokens["sb-brand"]}" stroke-width="2.5" '
            'stroke-linecap="round"/>'
            f'<path d="M9 18h9" stroke="{tokens["sb-text-2"]}" stroke-width="2.5" '
            'stroke-linecap="round"/>'
            f'<path d="M9 23h5" stroke="{tokens["sb-text-3"]}" stroke-width="2.5" '
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
        that `sb ui` is waiting on works the same in every mode and leaves the
        server in charge of its own shutdown.
        """
        if not canvas.authorised(request):
            return _denied()
        canvas.quitting.set()
        return JSONResponse({"quitting": True})

    async def get_catalog(request: Request) -> Response:
        if not canvas.authorised(request):
            return _denied()
        # `home` is where a *raw* command runs unless the operator says
        # otherwise. Neutral on purpose: the canvas inherits whatever directory
        # `sb ui` was launched in, and launching it inside any repo with a
        # `cli/` package makes `python -m cli` resolve to that one — which is
        # how running `jam` from this repo produces sky.boss's own error.
        # A home directory has no such package to shadow anything.
        return JSONResponse(
            {
                "commands": catalog(),
                "intervals": list(INTERVALS),
                "home": str(Path.home()),
            }
        )

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
        payload = result.to_dict()
        payload["chrome"] = chrome_for(argv, payload)
        return JSONResponse(payload)

    async def post_trial(request: Request) -> Response:
        """The bench's run: `/api/run` with one rule added, and the rule is the
        whole reason it is a second route.

        **An act has no trial run.** sb will not execute a write to show you
        what it would print, so the bench offers what it can check without
        running and one button that runs it for real. That refusal lives here
        rather than in a button the surface declines to draw, because a UI that
        merely does not offer something has not refused it — the check has to
        be where the request arrives.

        A separate route rather than a flag on `/api/run` because the refusal
        belongs to the *bench* and not to running: the palette must keep being
        able to open a `sb run` window, and one route that sometimes refuses
        `run` and sometimes does not is a route with two contracts.

        A resident argv is refused too, and for a different reason: a stream is
        not run to completion, so `runner.run` would sit on it until the
        timeout and report a hang as a result. A follow trial is held open by
        `/api/follow` like every other stream on this surface.

        See [[workbench]] round 1.
        """
        if not canvas.authorised(request):
            return _denied()
        body = await request.json()
        argv = [str(a) for a in (body.get("argv") or [])]
        if not argv:
            return JSONResponse({"error": "no argv"}, status_code=400)
        entry = entry_for(argv)
        if _acts(argv, entry):
            return JSONResponse(
                {
                    "error": "an act has no trial run — sb will not run a write "
                    "to show you what it would print"
                },
                status_code=400,
            )
        if entry is not None and entry["resident"]:
            return JSONResponse(
                {"error": "a stream is held open, not run to completion — follow it instead"},
                status_code=400,
            )
        timeout = body.get("timeout") or runner.DEFAULT_TIMEOUT
        result = await asyncio.to_thread(runner.run, argv, timeout=int(timeout))
        payload = result.to_dict()
        payload["chrome"] = chrome_for(argv, payload)
        return JSONResponse(payload)

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

    async def post_follow(request: Request) -> Response:
        """Start, restart, or stop one window's held-open stream.

        Re-POSTing for a window that already has one is the restart
        affordance: the corpse is killed and a fresh child spawned. The kill
        can block for the grace period, so it goes off the loop like every
        other blocking call here.
        """
        if not canvas.authorised(request):
            return _denied()
        body = await request.json()
        session = canvas.sessions.get(str(body.get("session") or ""))
        if session is None:
            return JSONResponse({"error": "no such session"}, status_code=409)
        window_id = str(body.get("window") or "")
        if not window_id:
            return JSONResponse({"error": "no window"}, status_code=400)

        existing = session.followers.pop(window_id, None)
        if existing is not None:
            await asyncio.to_thread(existing.child.kill)
        if body.get("stop"):
            return JSONResponse({"following": False})

        argv = [str(a) for a in (body.get("argv") or [])]
        try:
            kind, foreign, cwd, lines, highlight, due = resolve_follow(argv)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        ruleset = None
        if highlight:
            ruleset, problem = highlight_.resolve(highlight)
            if problem:
                return JSONResponse({"error": problem}, status_code=400)
        try:
            if kind == "file":
                from cli.filefollow import FileCursor

                path = foreign[0]
                if cwd and not path.startswith("/"):
                    path = str(Path(cwd) / path)
                child = await asyncio.to_thread(
                    lambda: FileCursor(path, limit=lines)
                )
            else:
                child = await asyncio.to_thread(
                    lambda: stream_.ChildStream(foreign, cwd=cwd, limit=lines)
                )
        except (FileNotFoundError, OSError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        session.followers[window_id] = Follower(
            child=child, argv=foreign, ruleset=ruleset, due=due
        )
        return JSONResponse({"following": True})

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
            Route("/api/trial", post_trial, methods=["POST"]),
            Route("/api/watch", post_watch, methods=["POST"]),
            Route("/api/follow", post_follow, methods=["POST"]),
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


@dataclass
class Follower:
    """One window's held-open stream — a process's or a file's — and where
    its frames left off."""

    child: object  # ChildStream or FileCursor; one interface, see [[file-follow]]
    argv: list[str]
    # The operator's declared vocabulary for this window, resolved server-side
    # when the follow opened. A page may *name* a ruleset; it may never define
    # one. See [[highlight]] round 3.
    ruleset: object | None = None
    # The operator's declared expectation for this window, in seconds. 0 is no
    # expectation — see [[file-follow]] round 2.
    due: int = 0
    shipped: int = 0
    exited_at: float | None = None
    dead_announced: bool = False
    last_state: str | None = None


class Follow(NamedTuple):
    """What a follow argv resolves to.

    A named tuple rather than a bare one because this has gained a field per
    round — `--cwd`, then `--lines`, then `--highlight`, now `--due` — and each
    time a positional tuple churned every caller that only wanted one of them.
    """

    kind: str
    foreign: list[str]
    cwd: str | None
    lines: int
    highlight: str | None
    due: int = 0


def resolve_follow(
    argv: list[str], root=None
) -> tuple[str, list[str], str | None, int, str | None]:
    """A sb-level follow argv down to what it follows.

    The client sends what the operator typed or saved — `follow -- journalctl
    -f`, `follow cron.log`, or a keyword like `logs` — and the *server*
    resolves it, because a saved command's expansion lives on the Click tree
    and nothing client-side may keep a command table. Returns
    a `Follow` by the same shape rule the CLI dispatches on; raises ValueError when the argv is not a follow at all.

    `highlight` is the name of an operator ruleset, resolved against their
    file *here* rather than sent by the client — a page may name a ruleset,
    it may never define one. See [[highlight]] round 3.
    """
    if root is None:
        from cli import cli as root_group

        root = root_group

    argv = list(argv)
    # Descend the tree while the words name groups — a saved keyword lives at
    # `tools <name>` since [[tools]] round 2, and the server resolves it off
    # the live tree exactly because nothing client-side keeps a command table.
    command = root.commands.get(argv[0]) if argv else None
    consumed = 1
    while (
        command is not None
        and hasattr(command, "commands")
        and consumed < len(argv)
        and argv[consumed] in command.commands
    ):
        command = command.commands[argv[consumed]]
        consumed += 1
    if command is not None and getattr(command, "sb_saved", False):
        argv = list(getattr(command, "sb_argv", argv))
    if not argv or argv[0] != "follow":
        raise ValueError("not a follow argv")

    cwd: str | None = None
    lines = stream_.DEFAULT_LINES
    highlight: str | None = None
    due = 0
    rest = argv[1:]
    foreign: list[str] = []
    i = 0
    while i < len(rest):
        token = rest[i]
        if token == "--":
            foreign = rest[i + 1 :]
            break
        if token == "--cwd" and i + 1 < len(rest):
            cwd = rest[i + 1]
            i += 2
            continue
        if token == "--lines" and i + 1 < len(rest):
            lines = int(rest[i + 1])
            i += 2
            continue
        if token == "--highlight" and i + 1 < len(rest):
            highlight = rest[i + 1]
            i += 2
            continue
        if token == "--due" and i + 1 < len(rest):
            # A malformed duration in a saved argv must not kill the window it
            # was pinned in. The CLI refuses it at the door; here it degrades to
            # no expectation, which is the state before anyone declared one.
            try:
                due = parse_duration(rest[i + 1])
            except ValueError:
                due = 0
            i += 2
            continue
        foreign = rest[i:]
        break
    if not foreign:
        raise ValueError("nothing to follow")

    from cli.follow import is_file_form

    kind = "file" if is_file_form(tuple(foreign)) else "process"
    return Follow(kind, foreign, cwd, lines, highlight, due)


def follower_frames(session: Session, now: float | None = None) -> list[dict]:
    """Frames for every follower with something new to say. Pure over the
    followers' state — fresh lines, or a death not yet announced."""
    frames: list[dict] = []
    moment = time.time() if now is None else now
    for window_id, follower in list(session.followers.items()):
        child = follower.child
        fresh, follower.shipped = child.fresh(follower.shipped)
        code = child.exit_code
        if code is not None and follower.exited_at is None:
            follower.exited_at = moment
        newly_dead = code is not None and not follower.dead_announced

        cursor_state = getattr(child, "state", None)
        state_changed = cursor_state is not None and cursor_state != follower.last_state
        if not fresh and not newly_dead and not state_changed:
            continue
        if newly_dead:
            follower.dead_announced = True
        follower.last_state = cursor_state

        if cursor_state is not None:
            # A file: the chrome carries what the loop statted — quiet,
            # absent and rotated are the cursor's verdicts, never re-derived.
            facts = chrome_.cursor(
                " ".join(follower.argv),
                state=cursor_state,
                last_write_at=child.last_write_at,
                size_bytes=child.size,
                ring_shown=len(child.lines()),
                ring_limit=child.ring.limit,
                due=follower.due,
                now=moment,
            )
        else:
            facts = chrome_.stream(
                " ".join(follower.argv),
                last_line_at=child.last_line_at,
                exit_code=code,
                exited_at=follower.exited_at,
                ring_shown=len(child.lines()),
                ring_limit=child.ring.limit,
                due=follower.due,
                now=moment,
            )
        frames.append(
            {
                "type": "stream",
                "window": window_id,
                "lines": [_frame_line(line, follower.ruleset) for line in fresh],
                "chrome": facts.to_dict(),
            }
        )
    return frames


def _frame_line(line, ruleset=None) -> dict:
    """One stream line for the wire. Marks ride *beside* the verbatim text,
    never instead of it — offsets into the text, computed here because the
    rules live in Python and the page applies them dumbly. A stderr line is
    the stream's own voice and is never re-tagged. See [[highlight]]."""
    out = {"text": line.text, "stderr": line.stderr}
    if getattr(line, "voice", False):
        out["voice"] = True
    if not line.stderr:
        found = highlight_.marks(line.text, ruleset)
        if found:
            out["marks"] = found
    return out


def _acts(argv: list[str], entry: dict | None = None) -> bool:
    """Whether this sb-level argv writes. Read off the catalog, never guessed.

    `entry` is passed when the caller already looked it up, so one request does
    not walk the tree twice. An argv nothing in the tree answers to is a raw
    one, and the only thing that could make it an act is being spelled `run`.
    """
    if entry is None:
        entry = entry_for(argv)
    return entry["acts"] if entry is not None else argv[:1] == ["run"]


def chrome_for(argv: list[str], run: dict, *, interval: int = 0, now: float | None = None) -> dict:
    """The [[chrome]] facts for one canvas run, assembled where the surface
    knows them — the deciding half in Python, exactly as the view's is.

    Attached beside the envelope in the transport, never inside it: the
    envelope stays byte-identical to the CLI's own, and the boundary test in
    tests/test_chrome.py holds that line.

    `last_run` is stamped in epoch seconds at result time, which is the same
    moment the page stamps `ranAt` today — the bar's numbers come from the
    contract without changing what they count. The watcher's own monotonic
    clock never ships; a monotonic reading means nothing to another process.
    """
    envelope = run.get("envelope") or {}
    ok = bool(run.get("ok")) and envelope.get("ok", True) is not False
    partial = bool(envelope.get("partial"))
    warnings = len(envelope.get("warnings") or [])
    source = " ".join(argv)
    ran_at = time.time() if now is None else now
    duration = run.get("duration_s")

    if interval:
        facts = chrome_.resident(
            source, ok=ok, partial=partial, warnings=warnings,
            ran_at=ran_at, duration_s=duration, interval=interval, last_run=ran_at,
        )
    else:
        # Inherited, never inferred from the path: a saved tool's `acts` came
        # from its expansion, and the catalog is the one place that knows it.
        build = chrome_.act if _acts(argv) else chrome_.snapshot
        facts = build(
            source, ok=ok, partial=partial, warnings=warnings,
            ran_at=ran_at, duration_s=duration,
        )
    return facts.to_dict()


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
            payload = result.to_dict()
            payload["chrome"] = chrome_for(
                list(watcher.argv), payload, interval=watcher.interval
            )
            await queue.put(
                {"type": "run", "window": watcher.window_id, "result": payload}
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
            # Followers ride the same tick the watchers do — the frame is
            # whatever arrived since the last one, and a death is announced
            # exactly once. A file cursor advances by being ticked, and its
            # stat is blocking, so it goes off the loop like every other
            # blocking call here; a process stream fills itself from its
            # pump threads and has no tick.
            for follower in list(session.followers.values()):
                advance = getattr(follower.child, "tick", None)
                if advance is not None:
                    await asyncio.to_thread(advance)
            for stream_frame in follower_frames(session):
                await queue.put(stream_frame)
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
        # A follower's child dies with the session — the same rule as
        # watchers, extended to processes. SIGTERM only, fire-and-forget:
        # this finally runs inside GeneratorExit, where a graceful wait has
        # nowhere to happen, and a child that ignores SIGTERM is reaped when
        # the server exits. The terminal form waits properly; see
        # cli/follow.py.
        for follower in session.followers.values():
            proc = getattr(follower.child, "proc", None)  # a cursor has none
            try:
                if proc is not None:
                    proc.terminate()
            except OSError:
                pass
        canvas.sessions.pop(session.id, None)
