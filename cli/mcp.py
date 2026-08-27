"""The MCP surface — the tools, offered to an agent.

**The direction with value is the agent calling sb**, not sb calling an agent.
Chaining already works and needs nothing: `sb follow -- claude -p …` is a
command, and feeding sb into an agent is a shell pipe. What does not exist is an
agent being able to ask *"how are my projects"* without knowing the tool, its
flags, its working-directory quirk and how to parse what it prints. The operator
solved all four already, once, in `tools.toml`.

**The surface is what the operator curated, and that is the whole safety
argument.** The act/observe split rests on one sentence — sb cannot tell a read
from a write by inspecting an argv and does not try, so choosing `data` over
`run` is the *operator's* assertion. Hand that door to an agent and the
assertion is being made by the thing it was protecting against. An MCP tool
taking a free-form argv is a shell with a reassuring name.

So nothing here takes an argument. Every exposed tool has an **empty input
schema** — there is no string an agent can put anywhere, so the injection
surface is not small, it is absent.

**stdio, not a port.** The canvas server binds one and needs four defences to
do it safely. A second port would be a second thing to defend, defending the
same commands. Over stdio the client spawned the process and holds both ends of
the pipe, so the threat model collapses into "who may spawn `sb mcp`" — which
the operating system already answers.

**stdout is the protocol.** The purity rule that keeps `sb --json … | jq`
parseable is the same rule that keeps a session intact here; a stray `print` is
a corrupted session rather than an ugly one. See [[mcp]].
"""

from __future__ import annotations

import json
import sys
from typing import Any

import rich_click as click

from cli.output import Result, emit

# What this implements. A hand-rolled subset rather than the official SDK: that
# brings pydantic into a project which has deliberately avoided it, to save
# perhaps a hundred lines of JSON-RPC over a pipe. Revisit if the surface ever
# grows resources and prompts.
DEFAULT_PROTOCOL = "2025-06-18"

# Bounded, for the third time. A 120k-line result kills an agent's context as
# dead as it killed a browser tab and a `RichLog` before it — the substrate
# changed, the rule did not.
MAX_ROWS = 2000
MAX_CHARS = 200_000

# JSON-RPC, the three we can actually emit.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601


def exposed(root=None) -> list[dict]:
    """The tools an agent may call, read off the live tree.

    Three properties decide it, and none of them is a name written down here —
    the same rule `sb_surface` follows, for the same reason: a list in this
    module is the command table the whole design refuses to keep, and it goes
    stale the day something is renamed.

    - **`acts` → excluded.** Acting stays the operator's. An agent that needs
      something done asks them.
    - **`resident` → excluded.** A stream has no single response, which is why
      `sb follow` already refuses `--json`; a request/response protocol is the
      same shape of problem and gets the same answer.
    - **takes an argv → excluded**, which is every remaining builtin. That is
      the assertion boundary above, and it is why `data` and `read` are not
      callable tools.

    What is left is the tools — every entry an argv the operator wrote down —
    plus any builtin that opts in with `sb_mcp` because it takes nothing from
    its caller either. See [[mcp]] round 1.
    """
    from cli.canvas.catalog import catalog

    out = []
    for entry in catalog(root) if root is not None else catalog():
        if entry.get("acts") or entry.get("resident"):
            continue
        if not (entry.get("saved") or entry.get("mcp")):
            continue
        out.append(
            {
                "name": entry["name"].replace(" ", "-"),
                "description": entry.get("summary") or entry["name"],
                "argv": entry["argv"],
                # Empty, and that is the safety property rather than an
                # oversight. See the module docstring.
                "inputSchema": {"type": "object", "properties": {}},
            }
        )
    return out


def call(name: str, root=None) -> tuple[str, bool]:
    """Run one exposed tool. Returns `(text, is_error)`.

    **A failed command is an envelope, not a transport fault.** An agent asking
    "what is the state of X" is owed *"the tool failed and here is what it
    said"* as an answer — a protocol error tells it the plumbing broke, which is
    a different and less useful claim.
    """
    tools = {tool["name"]: tool for tool in exposed(root)}
    tool = tools.get(name)
    if tool is None:
        offered = ", ".join(sorted(tools)) or "nothing — no tools are saved"
        return json.dumps({"error": f"no such tool: {name}", "available": offered}), True

    from cli import cli as root_group
    from cli.output import capture

    # Through the real CLI, so a tool runs exactly as it does in a terminal —
    # `child_env()`, the operator's authentication, the same envelope.
    #
    # `capture` is doing two jobs. It keeps the envelope, so this is not a
    # second trip through `--json` and back. And it redirects `sys.stdout`,
    # which here *is the protocol stream* — a command that printed would
    # otherwise corrupt the session rather than merely look untidy. `serve`
    # holds its own reference to the real stdout, taken before any of this, so
    # the swap cannot reach the transport.
    with capture(width=100) as captured:
        try:
            (root or root_group).main(tool["argv"], standalone_mode=False)
        except SystemExit:
            pass
        except click.ClickException as exc:
            return json.dumps({"ok": False, "error": exc.format_message()}), True
        except Exception as exc:  # noqa: BLE001 — a fault must not kill the session
            return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), True

    if not captured.envelopes:
        return json.dumps({"ok": False, "error": "command produced no envelope"}), True
    envelope = captured.envelopes[-1]

    envelope = _bounded(envelope)
    return json.dumps(envelope, indent=2, default=str), not envelope.get("ok", True)


def _bounded(envelope: dict) -> dict:
    """The caps `read` and the canvas already apply, applied again here."""
    data = envelope.get("data")
    if isinstance(data, list) and len(data) > MAX_ROWS:
        dropped = len(data) - MAX_ROWS
        envelope["data"] = data[:MAX_ROWS]
        envelope.setdefault("warnings", []).append(f"{dropped} more rows not shown")
    elif isinstance(data, str) and len(data) > MAX_CHARS:
        dropped = len(data) - MAX_CHARS
        envelope["data"] = data[:MAX_CHARS]
        envelope.setdefault("warnings", []).append(f"{dropped} more characters not shown")
    return envelope


def handle(message: dict, root=None) -> dict | None:
    """One request in, one response out. Pure — no I/O, so the whole protocol
    is testable without a pipe. `None` means *this was a notification*, which
    takes no reply at all: answering one is a protocol error in itself.
    """
    method = message.get("method")
    request_id = message.get("id")

    if request_id is None:
        return None

    if method == "initialize":
        params = message.get("params") or {}
        asked = params.get("protocolVersion")
        return _ok(
            request_id,
            {
                # Echo the client's version when it named one. This implements
                # the common core that every version in use shares, and a
                # mismatch the client could have lived with is a worse outcome
                # than agreeing on the thing we both do.
                "protocolVersion": asked if isinstance(asked, str) else DEFAULT_PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "sky-boss", "version": _version()},
            },
        )

    if method == "tools/list":
        return _ok(
            request_id,
            {"tools": [{k: v for k, v in t.items() if k != "argv"} for t in exposed(root)]},
        )

    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        if not isinstance(name, str):
            return _err(request_id, INVALID_REQUEST, "tools/call needs a tool name")
        text, is_error = call(name, root)
        return _ok(
            request_id,
            {"content": [{"type": "text", "text": text}], "isError": is_error},
        )

    return _err(request_id, METHOD_NOT_FOUND, f"method not found: {method}")


def _ok(request_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _version() -> str:
    from cli import get_version

    return get_version()


def serve(stdin=None, stdout=None, root=None) -> None:
    """The loop: newline-delimited JSON in, newline-delimited JSON out.

    Streams are injectable so the suite can drive a whole session without a
    pipe — the same reason `Session` takes a clock.
    """
    source = stdin or sys.stdin
    sink = stdout or sys.stdout

    for line in source:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            _write(sink, _err(None, PARSE_ERROR, "invalid JSON"))
            continue
        if not isinstance(message, dict):
            _write(sink, _err(None, INVALID_REQUEST, "expected an object"))
            continue
        response = handle(message, root)
        if response is not None:
            _write(sink, response)


def _write(sink, payload: dict) -> None:
    sink.write(json.dumps(payload) + "\n")
    sink.flush()


@click.command(name="mcp")
def mcp() -> None:
    """Speak MCP on stdin/stdout, offering the tools to an agent.

    The client spawns this and owns the pipe; there is no port, no token and no
    daemon. Register it with any MCP client as a stdio server:

        {"command": "sb", "args": ["mcp"]}

    **What an agent may reach: the commands you saved, and nothing else.** Every
    exposed tool is an argv you wrote in `tools.toml`, plus any builtin that
    takes nothing from its caller. Every one has an empty input schema, so there
    is no string an agent can put anywhere.

    **What it may not reach**, by rule rather than by list: anything that acts
    (`run`, and any saved command wrapping it), anything resident (`follow`),
    and anything taking a free-form argv (`data`, `read`) — because choosing
    `data` over `run` is *your* assertion that something is a read, and an
    assertion an agent makes about its own argv is not a safety property.

    sb is never in the credential path. A saved command runs with your
    environment, so an agent inherits your reach for exactly the commands you
    curated. That is the trade, stated rather than discovered.

    The boundary is written down in `docs/features/done/mcp.md`.
    """
    serve()


# This is a surface, like `sb ui`. It stays out of the palette and out of its
# own tool list — set on the command object rather than named in a skip-list,
# which is the rule that stops a module here growing a command table.
mcp.sb_surface = True
