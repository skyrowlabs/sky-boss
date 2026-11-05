"""Every file that states the oldest supported Python states the same one.

`--python` renders one number into pyright's `pythonVersion`, black's
`target-version`, the shell's `TARGET_PYTHON`, every `python-version:` step
in the workflows, and the start of the CI matrix. After the scaffold those are
static text that nothing compares — the same class as
`test_setup_blocks_agree.py`. Measured on a fresh tree: pyright at 3.11
beside black and CI at 3.12 passed every shipped gate.

Homes are discovered by pattern over the files that exist, so a tree that
dropped pyright for ruff and mypy (mind.head) is measured on those, a tree
that added `requires-python` enrols it by writing it, and `least=2` refuses
to call one home a parity. A step pinned ABOVE the floor is allowed: sky.boss
runs its gate on the newest matrix entry on purpose.
"""

from __future__ import annotations

import json
import re

import pytest

from scripts.paths import CLI_DIR, GITHUB_DIR, PROJECT_ROOT
from tests.scanning import scanned

pytestmark = pytest.mark.unit

_WORKFLOWS = GITHUB_DIR / "workflows"


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def floors() -> dict[str, str]:
    """`home -> version` for every file stating the floor, read the way each tool reads it."""
    out: dict[str, str] = {}
    pyright = PROJECT_ROOT / "pyrightconfig.json"
    if pyright.exists():
        # pyright reads JSONC; whole-line `//` comments are dropped as test_pyright_scope.py does.
        kept = [line for line in pyright.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("//")]
        out["pyrightconfig.json pythonVersion"] = json.loads("\n".join(kept)).get("pythonVersion", "")
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8")
        for home, pattern in (
            ("pyproject.toml black target-version", r'target-version\s*=\s*\[\s*"py(\d)(\d+)"'),
            ("pyproject.toml ruff target-version", r'target-version\s*=\s*"py(\d)(\d+)"'),
        ):
            found = re.search(pattern, text)
            if found:
                out[home] = f"{found.group(1)}.{found.group(2)}"
        for home, pattern in (
            ("pyproject.toml mypy python_version", r'python_version\s*=\s*"(\d+\.\d+)"'),
            ("pyproject.toml requires-python", r'requires-python\s*=\s*">=\s*(\d+\.\d+)'),
        ):
            found = re.search(pattern, text)
            if found:
                out[home] = found.group(1)
    check = CLI_DIR / "check.py"
    if check.exists():
        found = re.search(r'^TARGET_PYTHON\s*=\s*"(\d+\.\d+)"', check.read_text(encoding="utf-8"), re.MULTILINE)
        if found:
            out[f"{check.relative_to(PROJECT_ROOT)} TARGET_PYTHON"] = found.group(1)
    for workflow in sorted(_WORKFLOWS.glob("*.yml")):
        matrix = re.search(r"python:\s*\[([^\]]*)\]", workflow.read_text(encoding="utf-8"))
        if matrix:
            versions = [v.strip().strip("'\"") for v in matrix.group(1).split(",") if v.strip()]
            out[f"{workflow.name} matrix floor"] = min(versions, key=_version)
    return out


def pinned_steps() -> dict[str, set[str]]:
    """Every literal `python-version:` a workflow step pins, by file."""
    out: dict[str, set[str]] = {}
    for workflow in sorted(_WORKFLOWS.glob("*.yml")):
        found = set(re.findall(r"python-version:\s*['\"]?(\d+\.\d+)", workflow.read_text(encoding="utf-8")))
        if found:
            out[workflow.name] = found
    return out


def test_every_home_of_the_floor_agrees():
    homes = scanned(floors(), "files stating the Python floor", least=2)
    assert len(set(homes.values())) == 1, f"the Python floor disagrees across its homes: {homes}"


def test_no_workflow_step_pins_a_python_below_the_floor():
    homes = scanned(floors(), "files stating the Python floor", least=1)
    floor = _version(next(iter(homes.values())))
    for name, versions in scanned(pinned_steps(), "workflows pinning a python-version", least=1).items():
        below = sorted(v for v in versions if _version(v) < floor)
        assert not below, f"{name} pins a Python below the floor: {below}"
