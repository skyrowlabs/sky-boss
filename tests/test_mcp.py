"""The MCP surface — the tools, offered to an agent.

The exclusions come first. They are the whole safety argument, and they are the
part that would fail silently: a surface that offered one command too many
would work perfectly and be wrong.
"""

import io
import json

import pytest
from click.testing import CliRunner

from cli import cli
from cli.mcp import METHOD_NOT_FOUND, call, exposed, handle, serve


def names(root=None):
    return {tool["name"] for tool in exposed(root)}


# ── What an agent may not reach ─────────────────────────────────────────────


def test_nothing_that_acts_is_offered():
    """Acting stays the operator's. An agent that needs something done asks."""
    assert "run" not in names()


def test_nothing_resident_is_offered():
    """A stream has no single response, which is why `sb follow` already
    refuses `--json`. A request/response protocol is the same problem."""
    assert "follow" not in names()


def test_no_argv_taking_command_is_offered():
    """The assertion boundary. Choosing `data` over `run` is the *operator*
    saying this one is a read; an agent making that claim about its own argv is
    not a safety property, it is a shell with a reassuring name."""
    assert {"data", "read"} & names() == set()


def test_the_surface_excludes_itself():
    assert "mcp" not in names()
    assert "ui" not in names()


def test_a_saved_command_wrapping_run_is_never_offered(tmp_path, monkeypatch):
    """`acts` is inherited from a tool's first word, so the exclusion holds
    through a name that hides what it wraps."""
    from cli.tools import register

    (tmp_path / "tools.toml").write_text(
        '[tool.deploy]\nargv = ["run", "--", "./deploy.sh"]\n'
        '[tool.prs]\nargv = ["data", "--", "gh", "pr", "list", "--json", "number"]\n'
    )
    assert register(cli, home=tmp_path) == []
    try:
        assert "tools-deploy" not in names()
        assert "tools-prs" in names()
    finally:
        cli.commands["tools"].commands.pop("deploy", None)
        cli.commands["tools"].commands.pop("prs", None)


def test_every_tool_has_an_empty_input_schema():
    """The injection surface is not small, it is absent — there is no string an
    agent can put anywhere."""
    for tool in exposed():
        assert tool["inputSchema"] == {"type": "object", "properties": {}}


def test_the_list_comes_off_the_live_tree(tmp_path):
    """Adding a tool to tools.toml makes it appear with no code change here. A
    surface that kept its own list could offer something that does not exist."""
    from cli.tools import register

    before = names()
    (tmp_path / "tools.toml").write_text(
        '[tool.later]\nargv = ["data", "--", "echo", "[]"]\n'
    )
    assert register(cli, home=tmp_path) == []
    try:
        assert names() - before == {"tools-later"}
    finally:
        cli.commands["tools"].commands.pop("later", None)


# ── The protocol ────────────────────────────────────────────────────────────


def test_initialize_answers_with_capabilities():
    reply = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert reply["result"]["capabilities"] == {"tools": {}}
    assert reply["result"]["serverInfo"]["name"] == "sky-boss"


def test_initialize_agrees_on_the_clients_version():
    """This implements the core every version in use shares. A mismatch the
    client could have lived with is a worse outcome than agreeing."""
    reply = handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05"}}
    )
    assert reply["result"]["protocolVersion"] == "2024-11-05"


def test_a_notification_gets_no_reply_at_all():
    """Answering one is a protocol error in itself."""
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_an_unknown_method_is_a_proper_json_rpc_error():
    reply = handle({"jsonrpc": "2.0", "id": 7, "method": "resources/list"})
    assert reply["error"]["code"] == METHOD_NOT_FOUND
    assert reply["id"] == 7


def test_tools_list_carries_no_internal_argv():
    """The argv is how sky.boss runs it, not something the protocol describes."""
    reply = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    for tool in reply["result"]["tools"]:
        assert "argv" not in tool


def test_tools_call_without_a_name_is_an_invalid_request():
    reply = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {}})
    assert "error" in reply


# ── Calling ─────────────────────────────────────────────────────────────────


def test_calling_an_unknown_tool_is_an_answer_not_a_fault():
    text, is_error = call("no-such-tool")
    assert is_error is True
    assert "no such tool" in json.loads(text)["error"]


def test_a_call_returns_the_envelope(tmp_path):
    from cli.tools import register

    (tmp_path / "tools.toml").write_text(
        '[tool.two]\nargv = ["data", "--", "printf", "[{\\"a\\": 1}, {\\"a\\": 2}]"]\n'
    )
    assert register(cli, home=tmp_path) == []
    try:
        text, is_error = call("tools-two")
        envelope = json.loads(text)
        assert is_error is False
        assert envelope["ok"] is True
        assert envelope["data"] == [{"a": 1}, {"a": 2}]
    finally:
        cli.commands["tools"].commands.pop("two", None)


def test_a_failed_command_is_an_envelope_not_a_transport_fault(tmp_path):
    """An agent asking 'what is the state of X' is owed 'the tool failed and
    here is what it said' as an *answer*."""
    from cli.tools import register

    (tmp_path / "tools.toml").write_text(
        '[tool.broken]\nargv = ["data", "--", "sh", "-c", "echo boom >&2; exit 3"]\n'
    )
    assert register(cli, home=tmp_path) == []
    try:
        text, is_error = call("tools-broken")
        envelope = json.loads(text)
        assert is_error is True
        assert envelope["ok"] is False
        assert "error" in envelope["data"]
    finally:
        cli.commands["tools"].commands.pop("broken", None)


def test_a_result_is_bounded(tmp_path, monkeypatch):
    """A 120k-line result kills an agent's context as dead as it killed a
    browser tab. The substrate changed; the rule did not."""
    import cli.mcp as mcp_

    from cli.tools import register

    monkeypatch.setattr(mcp_, "MAX_ROWS", 5)
    # Built through json.dumps rather than an f-string: a JSON payload inside a
    # TOML string inside a Python literal is three levels of quoting and the
    # first attempt got it wrong in a way that read as a sky.boss bug.
    rows = json.dumps([{"a": i} for i in range(50)])
    argv = json.dumps(["data", "--", "printf", rows])
    (tmp_path / "tools.toml").write_text(f"[tool.big]\nargv = {argv}\n")
    assert register(cli, home=tmp_path) == []
    try:
        envelope = json.loads(call("tools-big")[0])
        assert len(envelope["data"]) == 5
        assert any("45 more rows" in w for w in envelope["warnings"])
    finally:
        cli.commands["tools"].commands.pop("big", None)


# ── The transport ───────────────────────────────────────────────────────────


def test_a_session_is_newline_delimited_json():
    lines = [
        '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}',
        '{"jsonrpc":"2.0","method":"notifications/initialized"}',
        '{"jsonrpc":"2.0","id":2,"method":"tools/list"}',
    ]
    out = io.StringIO()
    serve(stdin=io.StringIO("\n".join(lines) + "\n"), stdout=out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    # Two requests, one notification, two replies.
    assert [r["id"] for r in replies] == [1, 2]


def test_malformed_json_does_not_end_the_session():
    """A client that sends one bad line still has a working session."""
    out = io.StringIO()
    serve(stdin=io.StringIO('not json\n{"jsonrpc":"2.0","id":9,"method":"tools/list"}\n'), stdout=out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert replies[0]["error"]["code"] == -32700
    assert replies[1]["id"] == 9


def test_stdout_carries_protocol_and_nothing_else(capsys, tmp_path):
    """Over stdio the protocol *is* stdout, so a stray print is a corrupted
    session rather than an ugly one. The tool below writes to both streams."""
    from cli.tools import register

    (tmp_path / "tools.toml").write_text(
        '[tool.noisy]\nargv = ["data", "--", "sh", "-c", '
        '"echo chatter >&2; printf \'[{\\\\\\"a\\\\\\": 1}]\'"]\n'
    )
    assert register(cli, home=tmp_path) == []
    try:
        out = io.StringIO()
        serve(
            stdin=io.StringIO(
                '{"jsonrpc":"2.0","id":1,"method":"tools/call",'
                '"params":{"name":"tools-noisy"}}\n'
            ),
            stdout=out,
        )
        for line in out.getvalue().splitlines():
            json.loads(line)
        assert "chatter" not in capsys.readouterr().out
    finally:
        cli.commands["tools"].commands.pop("noisy", None)


def test_mcp_is_a_surface():
    from cli.canvas.catalog import catalog

    assert "mcp" not in {entry["name"] for entry in catalog()}
