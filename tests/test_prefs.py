"""What the surface remembers about itself between launches.

The properties worth defending are the two that keep this from becoming a
config file: only declared keys are stored, and every failure degrades to
*nothing remembered* rather than to an error the operator has to read. See
[[tools]] round 5.
"""

import json

from cli.canvas import prefs


def test_nothing_remembered_is_not_an_error(tmp_path):
    assert prefs.read(tmp_path) == {}


def test_a_written_preference_comes_back(tmp_path):
    assert prefs.write({"folded": ["jam", "bbrain"]}, tmp_path) is None
    assert prefs.read(tmp_path) == {"folded": ["jam", "bbrain"]}


def test_an_unknown_key_is_dropped_rather_than_stored(tmp_path):
    """The line round 4 drew when it refused to let /api/tools become a config
    editor: this is the surface's own state, not a second config file."""
    assert prefs.write({"folded": ["jam"], "api_key": "hunter2"}, tmp_path) is None
    assert prefs.read(tmp_path) == {"folded": ["jam"]}
    assert "hunter2" not in prefs.path(tmp_path).read_text()


def test_a_wrongly_typed_value_is_refused_with_a_reason(tmp_path):
    problem = prefs.write({"folded": "jam"}, tmp_path)
    assert problem and "folded" in problem
    assert not prefs.path(tmp_path).exists()


def test_a_list_of_non_strings_is_refused(tmp_path):
    assert prefs.write({"folded": ["jam", 7]}, tmp_path) is not None


def test_an_unbounded_list_is_refused(tmp_path):
    assert prefs.write({"folded": ["x"] * (prefs.MAX_ITEMS + 1)}, tmp_path) is not None
    assert prefs.write({"folded": ["x" * (prefs.MAX_LEN + 1)]}, tmp_path) is not None


def test_a_file_that_cannot_be_parsed_degrades_to_nothing_remembered(tmp_path):
    """A raised error here would cost the rail rather than the preference —
    the surface asks this before it can draw."""
    prefs.path(tmp_path).write_text("{not json")
    assert prefs.read(tmp_path) == {}


def test_a_file_holding_the_wrong_shape_is_ignored_key_by_key(tmp_path):
    """A page from another version cannot make the rail unreadable."""
    prefs.path(tmp_path).write_text(json.dumps({"folded": {"jam": True}, "x": 1}))
    assert prefs.read(tmp_path) == {}


def test_writing_replaces_rather_than_merges(tmp_path):
    prefs.write({"folded": ["jam", "bbrain"]}, tmp_path)
    prefs.write({"folded": ["jam"]}, tmp_path)
    assert prefs.read(tmp_path) == {"folded": ["jam"]}


def test_an_empty_write_forgets_everything(tmp_path):
    prefs.write({"folded": ["jam"]}, tmp_path)
    prefs.write({"folded": []}, tmp_path)
    assert prefs.read(tmp_path) == {"folded": []}


def test_the_route_round_trips(tmp_path, monkeypatch):
    """Through the guarded routes, which is how the surface reaches it."""
    from starlette.testclient import TestClient

    from cli.canvas.server import TOKEN_HEADER, Canvas, build

    monkeypatch.setattr(prefs, "STATE_DIR", tmp_path)
    client = TestClient(build(Canvas(token="t")))
    headers = {TOKEN_HEADER: "t"}

    assert client.get("/api/prefs", headers=headers).json() == {}
    posted = client.post("/api/prefs", json={"folded": ["jam"]}, headers=headers)
    assert posted.json() == {"folded": ["jam"]}
    assert client.get("/api/prefs", headers=headers).json() == {"folded": ["jam"]}


def test_the_route_refuses_a_bad_shape_with_its_reason(tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    from cli.canvas.server import TOKEN_HEADER, Canvas, build

    monkeypatch.setattr(prefs, "STATE_DIR", tmp_path)
    client = TestClient(build(Canvas(token="t")))
    response = client.post(
        "/api/prefs", json={"folded": "jam"}, headers={TOKEN_HEADER: "t"}
    )
    assert response.status_code == 400
    assert "folded" in response.json()["error"]
