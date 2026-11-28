"""What a unit test may reach: loopback sockets, and no secret from the environment.

And what no test may reach, in any suite: a loopback port `FORBIDDEN_LOOPBACK`
names, because a real service on this host answers there like a fake would.

`conftest.py` applies these to every test marked `unit`; they live here so a test can
exercise them directly. The guard is the socket of the test's own interpreter, so it
holds whatever client that process uses. A child process is not held: it inherits
the hidden environment and nothing else (sky.boss measured it). A name lookup is
not refused, only the connection after it, and loopback includes any local server.
From stash.flow's `_never_a_real_model`, which guarded one client and three hosts.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket

import pytest

#: A credential's shape. A unit test never needs a real one, and one it can read is one it can send.
#: A webhook URL is one: whoever holds it can post (breeze.brain's GRAFANA_DISCORD_WEBHOOK).
SECRET_NAME = re.compile(r"(?:^|_)(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIALS|WEBHOOK(?:_URL)?)$")


def is_local(address: object) -> bool:
    """Loopback, the unspecified address, or a non-IP socket such as a Unix path."""
    if not isinstance(address, tuple):
        return True
    host = str(address[0]).split("%")[0]
    if host in ("", "localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_unspecified


def hide_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [name for name in os.environ if SECRET_NAME.search(name)]:
        monkeypatch.delenv(name)


def refuse_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail a connect to anything not local. A fake transport above the socket never gets here."""
    for name in ("connect", "connect_ex"):
        real = getattr(socket.socket, name)

        def guarded(self: socket.socket, address: object, *, _real=real, _name=name):
            if not is_local(address):
                raise AssertionError(
                    f"a unit test reached the network: socket.{_name}({address!r}); "
                    "use a fake transport, or move the test to a suite that may"
                )
            return _real(self, address)

        monkeypatch.setattr(socket.socket, name, guarded)


#: Loopback ports no test may connect to, in any suite. A real service on this
#: host (a local model server, a database) answers on loopback, so `is_local`
#: cannot tell it from a test's own fake. Empty, so a fresh tree refuses nothing
#: and patches nothing (stash.flow; mind.head runs Ollama on 11434).
#:
#: **Add your own ports as an append**, in the space between the two frozen
#: rules at the end of this file:
#:
#:     FORBIDDEN_LOOPBACK += (11434,)
FORBIDDEN_LOOPBACK: tuple = ()


def refuse_forbidden_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail a connect to a local port `FORBIDDEN_LOOPBACK` names. Patches nothing while it is empty."""
    if not FORBIDDEN_LOOPBACK:
        return
    for name in ("connect", "connect_ex"):
        real = getattr(socket.socket, name)

        def guarded(self: socket.socket, address: object, *, _real=real, _name=name):
            if isinstance(address, tuple) and len(address) > 1 and is_local(address):
                if address[1] in FORBIDDEN_LOOPBACK:
                    raise AssertionError(
                        f"a test reached a forbidden local service: socket.{_name}({address!r}); "
                        "it is a real one on this host, so use a fake on another port"
                    )
            return _real(self, address)

        monkeypatch.setattr(socket.socket, name, guarded)


# ── Nothing below this line is skeletor's ────────────────────────────────────
#
# Everything of yours goes between this rule and the closing one below: appends,
# and any prose you write about them. Both rules are frozen — skeletor does not
# rewrite either block and renders nothing between them, so your insertion point
# is never adjacent to a template line that a release might edit. The
# explanation above IS ordinary prose and does get rewritten, which is why the
# rule sits at the bottom of it rather than at the top.


# ── Skeletor's again below this line ─────────────────────────────────────────
#
# Nothing of the template's follows yet. The rule is here so the space above has
# two ends, the shape every seam in this tree has (`scripts/paths.py` says why).
