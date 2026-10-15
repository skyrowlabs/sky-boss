"""Every ignore in `.github/actionlint.yaml` still concerns something in the file it names.

actionlint never reports an unused ignore, so nothing else would notice one outlive
its step. Whether actionlint still emits the message is the template's question and
is checked where it is shipped; this asks the half only the tree can: does the file
still exist, and does it still use the action the ignore is about.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import GITHUB_DIR, PROJECT_ROOT  # noqa: E402

CONFIG = GITHUB_DIR / "actionlint.yaml"
_PATH = re.compile(r"^  (\S[^:]*):\s*$")
_IGNORE = re.compile(r"^\s+- ['\"](.*)['\"]\s*$")
_ACTION = re.compile(r'action "([^"@]+)@')


def ignores() -> dict[str, list[str]]:
    """`{path: [pattern, ...]}` from the config's `paths:` map; empty when there is no config."""
    found: dict[str, list[str]] = {}
    current = None
    for line in CONFIG.read_text(encoding="utf-8").splitlines() if CONFIG.exists() else []:
        if header := _PATH.match(line):
            current = header.group(1).strip("'\"")
            found[current] = []
        elif (pattern := _IGNORE.match(line)) and current is not None:
            found[current].append(pattern.group(1))
    return found


def test_every_ignore_concerns_a_step_that_is_still_there():
    stale = []
    for path, patterns in ignores().items():
        target = PROJECT_ROOT / path
        if not target.exists():
            stale.append(f"{path}: no such file")
            continue
        text = target.read_text(encoding="utf-8")
        for pattern in patterns:
            action = _ACTION.search(pattern)
            if action and f"uses: {action.group(1)}@" not in text:
                stale.append(f"{path}: ignores a message about {action.group(1)}, which it no longer uses")
    assert not stale, "stale actionlint ignores — delete them:\n" + "\n".join(stale)
