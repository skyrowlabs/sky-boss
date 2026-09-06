"""The lint pins agree everywhere they are written down.

Two versions of a formatter disagree about real formatting. When
`.pre-commit-config.yaml` and CI hold different pins, a file passes locally and
fails in CI with a diff nobody can explain from the error message — the tool
name is the same, so the version never occurs to anyone.

`.pre-commit-config.yaml` is the source of truth. Everything else mirrors it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import PROJECT_ROOT, REQUIREMENTS  # noqa: E402

PRECOMMIT = PROJECT_ROOT / ".pre-commit-config.yaml"

#: repo slug fragment -> the name it goes by in requirements.txt
TOOLS = {"flake8": "flake8", "black": "black", "isort": "isort", "pyright": "pyright"}


def _precommit_pins() -> dict:
    text = PRECOMMIT.read_text(encoding="utf-8")
    pins = {}
    # `rev:` for hosted repos; `pyright@X.Y.Z` for the local node-hosted hook.
    for repo, rev in re.findall(r"- repo: https://\S*?/([\w.-]+)\n\s+rev: v?([\d.]+)", text):
        for tool in TOOLS:
            if tool in repo.lower():
                pins[tool] = rev
    for tool, version in re.findall(r"'(\w+)@([\d.]+)'", text):
        if tool in TOOLS:
            pins[tool] = version
    return pins


def _requirements_pins() -> dict:
    pins = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([\d.]+)", line.strip())
        if match and match.group(1) in TOOLS.values():
            pins[match.group(1)] = match.group(2)
    return pins


def test_every_lint_tool_is_pinned_in_precommit():
    pins = _precommit_pins()
    missing = sorted(set(TOOLS) - set(pins))
    assert not missing, f"Unpinned in .pre-commit-config.yaml (the source of truth): {missing}"


def test_requirements_match_precommit():
    precommit, requirements = _precommit_pins(), _requirements_pins()
    mismatched = {
        tool: (precommit[tool], requirements.get(tool))
        for tool in precommit
        if requirements.get(tool) != precommit[tool]
    }
    assert not mismatched, (
        "scripts/requirements.txt disagrees with .pre-commit-config.yaml "
        f"(pre-commit, requirements): {mismatched}\n"
        ".pre-commit-config.yaml is the source of truth — update requirements.txt."
    )
