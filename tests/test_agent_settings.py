"""The agent cannot file an issue except through a capture command.

`dev bug` and `dev task` attribute a scheduled job's filing and cap it;
a raw `gh issue create` does neither, and an issue without a source line is not
counted against any job afterwards (proto.pilot). So the shared settings do not
pre-approve it: a scheduled run is denied, and a person is asked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scanning import scanned

pytestmark = [pytest.mark.unit]

SETTINGS = Path(__file__).resolve().parents[1] / ".claude" / "settings.json"


def test_raw_issue_creation_is_not_pre_approved():
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    allow = scanned(settings["permissions"]["allow"], "allow rules")
    assert not [rule for rule in allow if "gh issue create" in rule], (
        "settings.json pre-approves `gh issue create`, which files around the capture cap; "
        "file with `dev bug` or `dev task` instead"
    )
