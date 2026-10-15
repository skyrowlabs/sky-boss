"""The autouse fixtures in `conftest.py` keep a test off the user's real state, browser and network."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path

import pytest

from scripts.paths import STATE_ROOT_DEFAULT, STATE_ROOT_ENV
from tests.guards import SECRET_NAME, hide_secrets, is_local

pytestmark = [pytest.mark.unit]


def test_the_state_root_is_never_the_default(tmp_path_factory):
    root = Path(os.environ[STATE_ROOT_ENV])
    assert root != STATE_ROOT_DEFAULT and tmp_path_factory.getbasetemp() in root.parents


def test_opening_a_browser_fails_the_test():
    for name in ("open", "open_new", "open_new_tab"):
        with pytest.raises(AssertionError, match="real webbrowser"):
            getattr(webbrowser, name)("https://example.com")


def test_a_routable_connect_fails_the_test():
    # RFC 5737's documentation range: refused before any packet, and nothing there if it were not.
    with socket.socket() as sock, pytest.raises(AssertionError, match="reached the network"):
        sock.settimeout(1)  # unguarded, this fails in a second rather than hanging
        sock.connect(("192.0.2." + "1", 80))
    with socket.socket() as sock, pytest.raises(AssertionError, match="reached the network"):
        sock.connect_ex(("example.com", 443))


def test_loopback_still_connects():
    with socket.socket() as server, socket.socket() as client:
        server.bind(("127.0.0.1", 0))
        server.listen()
        client.connect(server.getsockname())


def test_no_secret_shaped_variable_is_in_reach():
    assert not [name for name in os.environ if SECRET_NAME.search(name)]


def test_a_secret_the_shell_set_is_hidden_from_a_unit_test():
    this = f"{__file__}::test_no_secret_shaped_variable_is_in_reach"
    env = {**os.environ, "SOME_API_KEY": "k"}
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", this], env=env, capture_output=True, text=True
    )
    assert ran.returncode == 0, "the fixture left SOME_API_KEY readable:\n" + ran.stdout


def test_the_shape_names_secrets_only(monkeypatch):
    monkeypatch.setenv("SOME_API_KEY", "k")
    monkeypatch.setenv("GH_TOKEN", "t")
    monkeypatch.setenv("TOKENIZER_PATH", "kept")
    hide_secrets(monkeypatch)
    assert "SOME_API_KEY" not in os.environ and "GH_TOKEN" not in os.environ
    assert os.environ["TOKENIZER_PATH"] == "kept"


def test_local_means_loopback_or_a_unix_path():
    assert all(is_local(a) for a in (("127.0.0.1", 1), ("::1", 1, 0, 0), ("localhost", 1), "/tmp/s", b"\0abstract"))
    assert not any(is_local(a) for a in (("10.0.0." + "5", 1), ("example.com", 1)))
