"""The server runs commands, so the tests that matter are the ones about who
may ask it to.

Everything here is about the four things standing between a web page you did
not open and a command running on this machine. The pleasant path — a catalog
comes back, a run returns an envelope — is worth one test each; the refusals
are worth the rest of the file.
"""

import json

import pytest
from starlette.testclient import TestClient

from cli.canvas.server import TOKEN_HEADER, Canvas, build


@pytest.fixture
def canvas():
    return Canvas(token="test-token")


@pytest.fixture
def client(canvas):
    return TestClient(build(canvas))


def auth(extra=None):
    headers = {TOKEN_HEADER: "test-token"}
    headers.update(extra or {})
    return headers


# ------------------------------------------------------------------- refusals


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/catalog", "get"),
        ("/api/run", "post"),
        ("/api/watch", "post"),
        ("/api/follow", "post"),
        ("/api/quit", "post"),
        ("/api/stream", "get"),
    ],
)
def test_every_api_route_refuses_a_request_with_no_token(client, path, method):
    """Enumerated rather than spot-checked. A route added later without the
    guard is the whole failure mode, and this is what catches it."""
    kwargs = {"json": {}} if method == "post" else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 403


def test_a_wrong_token_is_refused(client):
    response = client.get("/api/catalog", headers={TOKEN_HEADER: "not-the-token"})
    assert response.status_code == 403


def test_a_foreign_origin_is_refused_even_with_the_right_token(client):
    """The token cannot leak to a page cross-origin, so this is belt and braces
    — but it is the brace that holds if the page is ever served somewhere it
    can be read."""
    response = client.get(
        "/api/catalog", headers=auth({"Origin": "https://evil.example"})
    )
    assert response.status_code == 403


def test_our_own_origin_is_accepted(client):
    response = client.get("/api/catalog", headers=auth({"Origin": "http://testserver"}))
    assert response.status_code == 200


def test_the_refusal_does_not_say_which_check_failed(client):
    """A message distinguishing "bad token" from "bad origin" is an oracle for
    whoever is guessing."""
    bad_token = client.get("/api/catalog", headers={TOKEN_HEADER: "wrong"})
    bad_origin = client.get(
        "/api/catalog", headers=auth({"Origin": "https://evil.example"})
    )
    assert bad_token.json() == bad_origin.json()


def test_no_route_hands_out_a_cors_allow_header(client):
    """Adding one to make something work would undo the preflight refusal that
    keeps a hostile page out. If it ever appears, it should appear here first."""
    response = client.get("/api/catalog", headers=auth())
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


# ------------------------------------------------------------------- the page


def test_the_page_carries_the_token_and_the_placeholder_is_gone(canvas, client):
    body = client.get("/").text
    assert canvas.token in body
    assert "__TB_TOKEN__" not in body


def test_the_page_carries_the_palette(canvas, client):
    """The stylesheet may not name a colour, so it names roles and the server
    hands it values. If this substitution silently stops happening the canvas
    still renders — every role resolves to nothing and the whole surface is
    default black on default white. It failed exactly that way once."""
    from cli.theme import BRAND

    body = client.get("/").text
    assert "__TB_TOKENS__" not in body
    assert f"--tb-brand:{BRAND}" in body


def test_the_page_itself_needs_no_token(client):
    """A top-level navigation cannot send a header. If this ever required one,
    the canvas would not open at all."""
    assert client.get("/").status_code == 200


# --------------------------------------------------------------------- routes


def test_the_catalog_comes_from_the_tree(client):
    body = client.get("/api/catalog", headers=auth()).json()
    assert "run" in [entry["name"] for entry in body["commands"]]
    assert body["intervals"][0] == 0


def test_running_a_command_returns_its_envelope(client):
    body = client.post(
        "/api/run", headers=auth(), json={"argv": ["run", "--", "echo", "canvas"]}
    ).json()
    assert body["ok"] is True
    assert body["envelope"]["data"]["stdout"].strip() == "canvas"


def test_a_failing_command_still_returns_an_envelope(client):
    """A non-zero exit is data, not an error. The window has to be able to show
    what went wrong rather than going blank."""
    body = client.post(
        "/api/run", headers=auth(), json={"argv": ["run", "--", "false"]}
    ).json()
    assert body["ok"] is False
    assert body["envelope"]["data"]["exit_code"] == 1


def test_an_empty_argv_is_rejected_before_anything_runs(client):
    assert client.post("/api/run", headers=auth(), json={"argv": []}).status_code == 400


# -------------------------------------------------------------------- session


def test_a_watcher_cannot_be_registered_without_a_live_session(client):
    """The stream is the session. A watcher with nowhere to live is a watcher
    that would outlive its window, which is the one thing this must not do."""
    response = client.post(
        "/api/watch",
        headers=auth(),
        json={"session": "nonexistent", "window": "w1", "argv": ["run"], "interval": 5},
    )
    assert response.status_code == 409


def test_the_static_directory_ships_only_what_the_page_needs():
    """Everything in `static/` is served, so anything left there is published.

    Two scratch pages lived here during the build, one of them with a live
    token baked into it. Neither was ever meant to ship and both were one
    forgotten `rm` away from doing so. A directory that is wholly public should
    have a declared inventory.
    """
    from cli.canvas.server import STATIC

    expected = {
        "index.html",
        "tb.css",
        "app.js",
        "api.js",
        "render.js",
        "vendor/preact.mjs",
        "vendor/hooks.mjs",
        "vendor/htm.mjs",
        "vendor/htm-preact.js",
    }
    found = {
        str(path.relative_to(STATIC))
        for path in STATIC.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert found == expected, f"unexpected: {found - expected}; missing: {expected - found}"


def test_static_files_must_be_revalidated_before_use():
    """Live reload operates inside the window where a browser would otherwise
    serve a file it fetched moments ago from memory. `no-cache` means "ask
    first", so the ETag still answers 304 and nothing is re-sent."""
    canvas = Canvas(token="test-token")
    client = TestClient(build(canvas))
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_the_close_button_is_guarded_like_every_other_route():
    """Ending the session is a real effect. A page you did not open must not be
    able to cause it any more than it may start a command."""
    canvas = Canvas(token="test-token")
    client = TestClient(build(canvas))

    assert client.post("/api/quit", json={}).status_code == 403
    assert client.post(
        "/api/quit", headers={TOKEN_HEADER: "test-token", "Origin": "https://evil.example"}
    ).status_code == 403
    assert not canvas.quitting.is_set()


def test_the_close_button_sets_the_latch_the_launcher_waits_on():
    """Not `window.close()`, which is only reliably permitted on a window a
    script opened — and a full-screen window is not one."""
    canvas = Canvas(token="test-token")
    client = TestClient(build(canvas))

    assert client.post("/api/quit", headers=auth(), json={}).json() == {"quitting": True}
    assert canvas.quitting.is_set()


def test_the_favicon_is_drawn_from_the_palette():
    """Without it the taskbar shows Chromium's default globe, so a surface with
    no browser chrome still announces itself as a browser. Generated rather
    than stored, because a static .svg would have to name a colour."""
    from cli.theme import BRAND

    canvas = Canvas(token="test-token")
    response = TestClient(build(canvas)).get("/favicon.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert BRAND in response.text


def test_the_page_carries_the_scale():
    """Every size in the stylesheet is measured in it, so if the substitution
    silently stops the whole surface renders at the CSS fallback instead of at
    the size that was asked for."""
    canvas = Canvas(token="test-token", scale=3.0)
    body = TestClient(build(canvas)).get("/").text
    assert "__TB_SCALE__" not in body
    assert "--tb-scale: 3.0" in body
