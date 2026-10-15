"""The autouse fixtures in `conftest.py` keep a test off the user's real state and browser."""

from __future__ import annotations

import os
import webbrowser
from pathlib import Path

import pytest

from scripts.paths import STATE_ROOT_DEFAULT, STATE_ROOT_ENV

pytestmark = [pytest.mark.unit]


def test_the_state_root_is_never_the_default(tmp_path_factory):
    root = Path(os.environ[STATE_ROOT_ENV])
    assert root != STATE_ROOT_DEFAULT and tmp_path_factory.getbasetemp() in root.parents


def test_opening_a_browser_fails_the_test():
    for name in ("open", "open_new", "open_new_tab"):
        with pytest.raises(AssertionError, match="real webbrowser"):
            getattr(webbrowser, name)("https://example.com")
