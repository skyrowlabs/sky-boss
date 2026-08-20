"""Suite-wide fixtures.

**The suite never reads the real `TB_HOME`.** Inventory, job definitions and
watches belong to whoever is running tb, not to this project, so a test that
loads them is a test whose result depends on whose machine it runs on — it
passes here and fails on a fresh clone with an empty home, or worse, passes on
both for different reasons.

`TB_HOME` is resolved once at import in `cli/helpers.py`, so this has to be set
before anything imports `cli`. Module level in conftest is early enough:
pytest imports it before collecting.
"""

import os
import tempfile
from pathlib import Path

_ISOLATED = Path(tempfile.mkdtemp(prefix="tb-home-")) / "home"
os.environ["TB_HOME"] = str(_ISOLATED)

import pytest  # noqa: E402


@pytest.fixture
def tb_home():
    """The isolated home, created empty. Populate it in the test that needs to."""
    _ISOLATED.mkdir(parents=True, exist_ok=True)
    return _ISOLATED
