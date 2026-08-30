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


GUARDED = [
    ("/api/catalog", "get"),
    ("/api/vocabulary", "get"),
    ("/api/projects", "get"),
    ("/api/run", "post"),
    ("/api/trial", "post"),
    ("/api/shape", "post"),
    ("/api/preflight", "post"),
    ("/api/watch", "post"),
    ("/api/follow", "post"),
    ("/api/accrue", "post"),
    ("/api/tools", "post"),
    ("/api/groups", "post"),
    ("/api/prefs", "get"),
    ("/api/prefs", "post"),
    ("/api/quit", "post"),
    ("/api/stream", "get"),
]


@pytest.mark.parametrize("path,method", GUARDED)
def test_every_api_route_refuses_a_request_with_no_token(client, path, method):
    """Enumerated rather than spot-checked. A route added later without the
    guard is the whole failure mode, and this is what catches it."""
    kwargs = {"json": {}} if method == "post" else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 403


def test_the_guarded_list_names_every_api_route_there_is():
    """The list above only catches an unguarded route if someone remembers to
    add it, which is the same hazard `static/`'s inventory has — so it is
    checked the same way, against the real thing, rather than trusted."""
    live = {
        route.path
        for route in build(Canvas(token="t")).routes
        if getattr(route, "path", "").startswith("/api/")
    }
    assert live == {path for path, _ in GUARDED}


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
    assert "__SB_TOKEN__" not in body


def test_the_page_carries_the_palette(canvas, client):
    """The stylesheet may not name a colour, so it names roles and the server
    hands it values. If this substitution silently stops happening the canvas
    still renders — every role resolves to nothing and the whole surface is
    default black on default white. It failed exactly that way once."""
    from cli.theme import BRAND

    body = client.get("/").text
    assert "__SB_TOKENS__" not in body
    assert f"--sb-brand:{BRAND}" in body


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
        "sb.css",
        "main.js",
        "app.js",
        "api.js",
        "bench.js",
        "render.js",
        "schedule.js",
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
    assert "__SB_SCALE__" not in body
    assert "--sb-scale: 3.0" in body


# ---------------------------------------------------------------- the bench

def test_a_trial_run_of_an_act_is_refused_by_the_server(client):
    """Not merely a button the bench declines to draw.

    A surface that only *does not offer* something has not refused it — the
    check has to be where the request arrives, because the request can be made
    without the surface. This is the act/observe split standing up to a POST.
    See [[workbench]] round 1.
    """
    response = client.post(
        "/api/trial", headers=auth(), json={"argv": ["run", "--", "true"]}
    )
    assert response.status_code == 400
    assert "act" in response.json()["error"]


def test_a_trial_run_of_a_stream_is_refused_and_says_where_to_go(client):
    """`runner.run` would sit on a follow until the timeout and then report a
    hang as a result. A stream is held open by /api/follow like every other one
    on this surface."""
    response = client.post(
        "/api/trial", headers=auth(), json={"argv": ["follow", "--", "tail", "-f", "x"]}
    )
    assert response.status_code == 400
    assert "held open" in response.json()["error"]


def test_a_trial_run_of_an_observe_returns_the_envelope(client):
    """The pleasant path, once. Everything else about the bench is a refusal."""
    response = client.post(
        "/api/trial", headers=auth(), json={"argv": ["read", "--", "echo", "hello"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["envelope"]["data"].strip() == "hello"
    # The chrome rides beside the envelope, never inside it — same boundary
    # `/api/run` keeps, and tests/test_chrome.py holds the line.
    assert "chrome" not in body["envelope"]
    assert body["chrome"]["shape"] == "snapshot"


def test_a_saved_command_is_judged_by_what_it_expands_to():
    """`entry_for` matches the longest path, so a tool at `tools <name>` is
    found rather than the bare `tools` group above it.

    Matching on argv[0] alone would call every saved tool a read — including
    one wrapping `run`, which is the exact mistake the read/write split exists
    to prevent.
    """
    from cli.canvas.catalog import entry_for

    entries = [
        {"name": "tools", "argv": ["tools"], "acts": False, "resident": False},
        {"name": "tools deploy", "argv": ["tools", "deploy"], "acts": True, "resident": False},
    ]
    assert entry_for(["tools", "deploy"], entries)["acts"] is True
    assert entry_for(["tools"], entries)["acts"] is False
    assert entry_for(["nothing", "here"], entries) is None


def test_shaping_runs_nothing_and_returns_the_whole_checklist(client):
    """`/api/shape` is introspection, not execution — a pure function of the
    payload the bench already has. The `offered` set is shaped *without* the
    columns that were asked for, which is the reason the route shapes twice:
    a checklist built from the drawn view would lose a column the moment it was
    unticked. See [[workbench]] round 2.
    """
    data = [{"a": 1, "b": 2, "c": None}, {"a": 3, "b": 4, "c": None}]
    response = client.post(
        "/api/shape", headers=auth(), json={"data": data, "cols": ["a"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert [c["key"] for c in body["view"]["columns"]] == ["a"]
    # Everything remains tickable, including the one a rule would have hidden.
    assert body["offered"] == ["a", "b", "c"]


def test_shaping_reports_what_this_shaping_hid(client):
    """The warning is a fact about the shaping on screen, not about whichever
    one the trial run happened to do."""
    data = [{"a": 1, "gone": None}]
    body = client.post("/api/shape", headers=auth(), json={"data": data}).json()
    assert any("1 column hidden: gone" in w for w in body["warnings"])


def test_projects_reports_where_a_schedule_comes_from(monkeypatch, client):
    """Provenance: which argv produced these rows, and which field became which
    column. The question the screen could not answer was why one project has 31
    rows and another none. See [[schedule]] round 5."""
    from cli import rollcall

    declared = rollcall.Project(
        name="jam-sense",
        description="the grid",
        argv=["jam", "report", "status", "--json"],
        cwd="/somewhere/jam-sense",
        schedule={"rows": "jobs", "name": "job", "next": "next_run"},
    )
    bare = rollcall.Project(name="quiet", argv=["./x", "--json"])
    monkeypatch.setattr(rollcall, "load", lambda: ([declared, bare], ["a problem"]))

    body = client.get("/api/projects", headers=auth()).json()
    first, second = body["projects"]
    assert first["source"] == "jam report status --json"
    assert first["kind"] == "argv"
    assert first["schedule"]["next"] == "next_run"
    # None, not {} — no table at all is a different answer from a table that
    # named nothing, and the screen says different words for them.
    assert second["schedule"] is None
    assert body["problems"] == ["a problem"]


def test_shaping_leaves_an_authored_view_alone(client):
    """An authored view is not re-derivable, so the route must not try.

    `shape` infers from the rows. A command that chose its own columns made a
    decision the rows do not contain — inference put all seven back, which is
    how a five-column schedule window drew seven and said so. See [[schedule]]
    round 3.
    """
    data = [{"project": "p", "name": "j", "fires": "in 1h", "schedule": "0 * * * *",
             "ran": "2h ago", "next": "2026-08-30T13:00:00+00:00", "last": ""}]
    authored = {
        "columns": [{"key": k} for k in ("project", "name", "fires", "schedule", "ran")],
        "details": [],
        "hidden": ["next", "last"],
        "authored": True,
    }
    body = client.post(
        "/api/shape", headers=auth(), json={"data": data, "view": authored}
    ).json()
    assert body["view"] == authored
    # Every key stays tickable, so the two it kept can be asked back on.
    assert body["offered"] == ["project", "name", "fires", "schedule", "ran", "next", "last"]
    # No "2 columns hidden — use --cols" here: the command has no --cols, and a
    # message naming a flag that does not exist is worse than none.
    assert body["warnings"] == []


def test_asking_for_columns_overrides_an_authored_view(client):
    """Authored is a default, not a lock. The operator asking is the one thing
    that outranks the command's own choice."""
    data = [{"a": 1, "b": 2, "c": 3}]
    authored = {"columns": [{"key": "a"}], "details": [], "hidden": ["b", "c"],
                "authored": True}
    body = client.post(
        "/api/shape", headers=auth(), json={"data": data, "view": authored, "cols": ["b"]}
    ).json()
    assert [c["key"] for c in body["view"]["columns"]] == ["b"]


def test_shaping_a_payload_with_no_rows_says_why(client):
    """A named `--rows` that finds nothing is the operator's assertion being
    wrong, and saying so is the whole point of the flag."""
    body = client.post(
        "/api/shape",
        headers=auth(),
        json={"data": {"meta": 1}, "rows": "nope", "cols": ["a"]},
    ).json()
    assert body["view"] is None
    assert body["offered"] == []
    assert "--cols not applied" in body["warnings"][0]


# ------------------------------------------------ the act's checks ([[workbench]])


def test_an_act_gets_checks_instead_of_a_trial(client):
    """"We cannot run it" is not the same as "we can tell you nothing".

    Three questions have answers that cost nothing, and the third is asked of
    sky.boss's own parser rather than of a copy of its rules.
    """
    body = client.post(
        "/api/preflight",
        headers=auth(),
        json={"argv": ["run", "--cwd", "/tmp", "--", "ls", "-la"]},
    ).json()
    labels = [c["label"] for c in body["checks"]]
    assert labels == ["--cwd exists and is a directory", "ls resolves", "sb accepts the argv"]
    assert all(c["ok"] for c in body["checks"])


def test_a_bad_cwd_fails_the_directory_check_and_the_parse(client):
    """Not a duplicate — a cause and its consequence, in that order. The parse
    catches it because `--cwd` is a `click.Path(exists=True)`, which is the
    whole reason the argv goes through Click rather than through a second
    opinion about what sky.boss accepts."""
    body = client.post(
        "/api/preflight",
        headers=auth(),
        json={"argv": ["run", "--cwd", "/definitely/not/here", "--", "ls"]},
    ).json()
    assert [c["ok"] for c in body["checks"]] == [False, True, False]
    assert "does not exist" in body["checks"][-1]["detail"]


def test_an_unknown_flag_is_caught_without_running(client):
    body = client.post(
        "/api/preflight", headers=auth(), json={"argv": ["run", "--bogus", "--", "ls"]}
    ).json()
    parse = body["checks"][-1]
    assert parse["ok"] is False
    assert "--bogus" in parse["detail"]


def test_preflight_runs_nothing(client, tmp_path):
    """The whole point. A check that had side effects would be a dry run, and
    there is no dry run."""
    marker = tmp_path / "touched"
    client.post(
        "/api/preflight",
        headers=auth(),
        json={"argv": ["run", "--", "touch", str(marker)]},
    )
    assert not marker.exists()


def test_the_name_is_judged_before_the_write(client):
    """`--save` writes before it runs, so a refusal found afterwards is found
    too late — under a name that then cannot be reused."""
    body = client.post(
        "/api/preflight", headers=auth(), json={"argv": ["data", "--", "x"], "name": "Bad Name"}
    ).json()
    assert body["name"]["ok"] is False
    assert "lowercase letters" in body["name"]["reason"]


def test_the_block_is_the_bytes_save_would_have_written(client):
    """`run` cannot save by example, so it gets the block to paste — rendered
    by the same function `--save` appends with, not by a second one."""
    from cli import tools as tools_

    argv = ["run", "--cwd", "/tmp", "--", "gh", "workflow", "run", "ci.yml"]
    body = client.post(
        "/api/preflight", headers=auth(), json={"argv": argv, "name": "ci-check"}
    ).json()
    assert body["block"] == tools_.block("ci-check", argv)


# -------------------------------------------------------- the line that holds


def test_no_route_writes_the_tools_file(client, tmp_path, monkeypatch):
    """The rule [[workbench]] round 3 was ratified under, held the way
    [[canvas]]'s no-CORS assertion is held.

    Every route the bench touches, exercised with a `--save` in the argv, and
    the file must still not exist. `--save` writes — from a *subprocess*, which
    is the one writer sky.boss has — and nothing in this process does.
    """
    home = tmp_path / "home"
    monkeypatch.setattr("cli.helpers.SB_HOME", home)
    monkeypatch.setattr("cli.tools.SB_HOME", home, raising=False)

    argv = ["data", "--save", "prs", "--", "echo", "[]"]
    for path, payload in (
        ("/api/preflight", {"argv": argv, "name": "prs"}),
        ("/api/shape", {"data": [{"a": 1}], "cols": ["a"]}),
        ("/api/trial", {"argv": ["read", "--", "true"]}),
    ):
        client.post(path, headers=auth(), json=payload)

    assert not (home / "tools.toml").exists()
    assert not home.exists()


# --- [[tools]] round 4: the route that rule 4 said would never exist ---------


def test_the_tools_route_writes_and_reloads(client, tmp_path, monkeypatch):
    """The write reaches the file *and* the tree. A tool on disk that the rail
    does not list is a surface disagreeing with itself — the name is refused as
    taken while nothing shows it exists."""
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.helpers.SB_HOME", tmp_path)
    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)
    body = {"name": "probe", "argv": ["read", "--", "echo", "hi"], "description": "a probe"}
    response = client.post("/api/tools", json=body, headers=auth())
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["action"] == "created"
    assert out["problems"] == []
    assert "[tool.probe]" in (tmp_path / "tools.toml").read_text()

    # …and again, which is a replace rather than a refusal.
    body["argv"] = ["read", "--", "echo", "bye"]
    again = client.post("/api/tools", json=body, headers=auth()).json()
    assert again["action"] == "replaced"
    assert "bye" in (tmp_path / "tools.toml").read_text()

    gone = client.post("/api/tools", json={"name": "probe", "delete": True}, headers=auth())
    assert gone.status_code == 200, gone.text
    assert "[tool.probe]" not in (tmp_path / "tools.toml").read_text()


def test_the_tools_route_refuses_with_the_loaders_own_reason(client, tmp_path, monkeypatch):
    """A 400 carrying why, not a 500 and not a silent write. `write_problem`
    is asked, so the route cannot hold a second opinion."""
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.helpers.SB_HOME", tmp_path)
    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)
    response = client.post(
        "/api/tools",
        json={"name": "nope", "argv": ["ls", "-la"]},
        headers=auth(),
    )
    assert response.status_code == 400
    assert "must start with" in response.json()["error"]
    assert not (tmp_path / "tools.toml").exists(), "refused and still wrote"


def test_the_tools_route_will_not_give_a_cadence_to_a_write(client, tmp_path, monkeypatch):
    """The act/observe split holds through the new door too."""
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.helpers.SB_HOME", tmp_path)
    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)
    response = client.post(
        "/api/tools",
        json={"name": "deploy", "argv": ["run", "--", "true"], "refresh": 30},
        headers=auth(),
    )
    assert response.status_code == 400
    assert "acts" in response.json()["error"]


# ============================================================================
# The URL it promised to print — [[canvas]] round 9
# ============================================================================


def test_serving_note_names_the_url_and_the_mode(capsys):
    """`sb ui --no-browser` documented itself as 'print the URL and wait' and
    only did the second half: `emit` renders when a command returns, and every
    foreground-serving mode calls `server.run()`, which returns when the server
    stops."""
    from cli.output import serving_note

    serving_note("http://127.0.0.1:8765/", "headless")
    captured = capsys.readouterr()
    assert "8765" in captured.err
    assert "headless" in captured.err
    # stdout stays clean — this is status, not payload, exactly as saved_note is
    assert captured.out == ""


def test_ui_refuses_json_rather_than_promising_an_envelope_it_never_sends():
    """Resident, so there is no envelope. `sb follow` already refuses this; `ui`
    used to block in server.run() and print nothing, which is the same promise
    kept by silence."""
    from click.testing import CliRunner

    from cli import cli

    result = CliRunner().invoke(cli, ["--json", "ui", "--no-browser"])
    assert result.exit_code == 2
    assert "no meaning here" in result.output


# --- [[workbench]] round 5: a rename that renames ----------------------------


def test_a_rename_removes_the_old_block_rather_than_copying_it(client, tmp_path, monkeypatch):
    """The operator's report: editing a tool's name left two tools.

    The bench never told the route *which* tool it had opened, so every save
    was a create-or-replace of whatever the name box said. `was` is that
    missing identity. One tool in, one tool out.
    """
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.helpers.SB_HOME", tmp_path)
    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)

    body = {"name": "before", "argv": ["read", "--", "echo", "hi"], "description": "d"}
    assert client.post("/api/tools", json=body, headers=auth()).status_code == 200

    renamed = dict(body, name="after", was="before")
    out = client.post("/api/tools", json=renamed, headers=auth()).json()
    assert out["renamed_from"] == "before"
    assert out["problems"] == []

    text = (tmp_path / "tools.toml").read_text()
    assert "[tool.after]" in text
    assert "[tool.before]" not in text, "the old name must not survive a rename"


def test_a_save_that_does_not_rename_leaves_the_old_name_alone(client, tmp_path, monkeypatch):
    """`was` equal to the name is an edit in place, not a rename — and must not
    delete the block that was just written."""
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.helpers.SB_HOME", tmp_path)
    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)

    body = {"name": "same", "argv": ["read", "--", "echo", "hi"], "description": "d"}
    assert client.post("/api/tools", json=body, headers=auth()).status_code == 200
    out = client.post("/api/tools", json=dict(body, was="same"), headers=auth()).json()
    assert "renamed_from" not in out
    assert "[tool.same]" in (tmp_path / "tools.toml").read_text()


def test_the_preflight_calls_a_taken_name_a_replace_not_a_problem(client, tmp_path, monkeypatch):
    """The bench's question, not `--save`'s. Reporting this as `ok: false` is
    what drew a refusal in the problem style over an edit that would have
    worked — and told the operator to go and edit a file."""
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.helpers.SB_HOME", tmp_path)
    monkeypatch.setattr("cli.tools.SB_HOME", tmp_path)

    body = {"name": "taken", "argv": ["read", "--", "echo", "hi"], "description": "d"}
    assert client.post("/api/tools", json=body, headers=auth()).status_code == 200

    out = client.post(
        "/api/preflight",
        json={"argv": ["read", "--", "echo", "hi"], "name": "taken"},
        headers=auth(),
    ).json()
    assert out["name"]["ok"] is True
    assert out["name"]["reason"] is None
    assert out["name"]["replaces"] == "read -- echo hi"
