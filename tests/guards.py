"""What a unit test may reach: loopback sockets, and no secret from the environment.

`conftest.py` applies these to every test marked `unit`; they live here so a test can
exercise them directly. The guard is the socket, so it holds whatever client a test
uses. A name lookup is not refused, only the connection after it.
From stash.flow's `_never_a_real_model`, which guarded one client and three hosts.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket

import pytest

#: A credential's shape. A unit test never needs a real one, and one it can read is one it can send.
SECRET_NAME = re.compile(r"(?:^|_)(?:API_KEY|TOKEN)$")


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
