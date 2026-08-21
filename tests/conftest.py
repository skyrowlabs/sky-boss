"""Suite-wide fixtures.

**The suite never touches the operator's real state directory.** `STATE_DIR`
holds the surface's input history and its stall dumps; a test that read or wrote
the real one would depend on — and damage — whatever the machine happens to have.

It is resolved once at import in `cli/helpers.py`, so this has to be set before
anything imports `cli`. Module level in conftest is early enough: pytest imports
it before collecting.
"""

import os
import tempfile
from pathlib import Path

_ISOLATED = Path(tempfile.mkdtemp(prefix="tb-state-")) / "state"
os.environ["TB_STATE"] = str(_ISOLATED)

# And never the operator's real toolbox. This one matters more than STATE_DIR:
# a tool is an argv tb will *run*, so a suite that read the real home would be
# registering the operator's commands into the tree under test — and `tb
# --help` would differ between two machines running the same suite.
_ISOLATED_HOME = Path(tempfile.mkdtemp(prefix="tb-home-")) / "home"
os.environ["TB_HOME"] = str(_ISOLATED_HOME)

import pytest  # noqa: E402


@pytest.fixture
def tb_state():
    """The isolated state directory, created empty."""
    _ISOLATED.mkdir(parents=True, exist_ok=True)
    return _ISOLATED


@pytest.fixture
def tb_home():
    """The isolated operator home, created empty."""
    _ISOLATED_HOME.mkdir(parents=True, exist_ok=True)
    return _ISOLATED_HOME
