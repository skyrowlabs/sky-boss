"""The agent cannot file an issue except through a capture command.

`dev bug` and `dev task` attribute a scheduled job's filing and cap it;
a raw `gh issue create` does neither, and an issue without a source line is not
counted against any job afterwards (proto.pilot). So the shared settings do not
pre-approve it: a scheduled run is denied, and a person is asked. The check is
by what a rule would match, not by spelling — `Bash(gh *)` approves it too.
"""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

import pytest

from scanning import scanned

pytestmark = [pytest.mark.unit]

SETTINGS = Path(__file__).resolve().parents[1] / ".claude" / "settings.json"
COMMAND = "gh issue create --title t --body b"


def approves_raw_filing(rule: str) -> bool:
    """Whether an allow rule would pre-approve `gh issue create`."""
    if rule == "Bash":
        return True
    match = re.fullmatch(r"Bash\((.*)\)", rule)
    if not match:
        return False
    pattern = match.group(1).replace(":*", " *")
    return any(fnmatch.fnmatchcase(c, pattern) for c in (COMMAND, "gh issue create"))


def test_the_predicate_catches_every_spelling_that_approves_it():
    approving = [
        "Bash",
        "Bash(*)",
        "Bash(gh *)",
        "Bash(gh:*)",
        "Bash(gh issue *)",
        "Bash(gh issue create*)",
    ]
    benign = ["Bash(gh issue list*)", "Bash(git *)", "Bash(./zq *)", "Read", "Bash(gh pr create*)"]
    assert [r for r in approving + benign if approves_raw_filing(r)] == approving


def test_raw_issue_creation_is_not_pre_approved():
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    allow = scanned(settings["permissions"]["allow"], "allow rules")
    assert not [rule for rule in allow if approves_raw_filing(rule)], (
        "settings.json pre-approves `gh issue create`, which files around the capture cap; "
        "file with `dev bug` or `dev task` instead"
    )
