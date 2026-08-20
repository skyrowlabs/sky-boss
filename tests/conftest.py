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

import pytest  # noqa: E402


@pytest.fixture
def tb_state():
    """The isolated state directory, created empty."""
    _ISOLATED.mkdir(parents=True, exist_ok=True)
    return _ISOLATED
