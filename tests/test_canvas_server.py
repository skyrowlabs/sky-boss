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
