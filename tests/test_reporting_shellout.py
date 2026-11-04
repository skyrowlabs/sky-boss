"""No reporting code can be crashed by a tool that is not on PATH.

Enrolment is by discovery: every module under `scripts/reporting/`, plus any
module in the shell package that imports from it. A subprocess call there must
go through `scripts/reporting/shellout.py` or sit in a `try` that handles
`FileNotFoundError`. The set of flagged calls may be empty, which is the healthy
case, so the predicate is proven on a synthetic source instead of a floor.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanning import scanned  # noqa: E402
from scripts.paths import CLI_DIR, PROJECT_ROOT, SCRIPTS_DIR  # noqa: E402
from scripts.reporting import shellout  # noqa: E402

SPAWNERS = {"run", "call", "check_call", "check_output", "Popen"}
CATCHES = {"FileNotFoundError", "OSError", "Exception", "BaseException"}


def _catches_missing(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any((n.attr if isinstance(n, ast.Attribute) else getattr(n, "id", "")) in CATCHES for n in names)


def unguarded_calls(source: str) -> list[int]:
    """Lines of subprocess calls a missing binary would raise out of."""
    tree = ast.parse(source)
    modules = {"subprocess"} | {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "subprocess"
    }
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "subprocess"
        for alias in node.names
        if alias.name in SPAWNERS
    }
    guarded: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(_catches_missing(h) for h in node.handlers):
            guarded.update(id(inner) for stmt in node.body for inner in ast.walk(stmt))
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or id(node) in guarded:
            continue
        func = node.func
        by_module = (
            isinstance(func, ast.Attribute)
            and func.attr in SPAWNERS
            and isinstance(func.value, ast.Name)
            and func.value.id in modules
        )
        if by_module or (isinstance(func, ast.Name) and func.id in imported):
            lines.append(node.lineno)
    return sorted(lines)


def _imports_reporting(path: Path) -> bool:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("scripts.reporting"):
            return True
        if isinstance(node, ast.Import) and any(a.name.startswith("scripts.reporting") for a in node.names):
            return True
    return False


def _population() -> dict[str, Path]:
    found = {p.relative_to(PROJECT_ROOT).as_posix(): p for p in sorted((SCRIPTS_DIR / "reporting").rglob("*.py"))}
    for path in sorted(CLI_DIR.rglob("*.py")):
        if _imports_reporting(path):
            found[path.relative_to(PROJECT_ROOT).as_posix()] = path
    return found


def test_the_predicate_flags_exactly_the_unguarded_shapes():
    source = "\n".join(
        [
            "import subprocess",  # 1
            "from subprocess import check_output as co",  # 2
            "subprocess.run(['a'])",  # 3 flagged
            "try:",  # 4
            "    subprocess.run(['b'])",  # 5 guarded
            "except FileNotFoundError:",  # 6
            "    subprocess.run(['c'])",  # 7 flagged: the handler is not guarded
            "try:",  # 8
            "    subprocess.Popen(['d'])",  # 9 guarded
            "except (ValueError, OSError):",  # 10
            "    pass",  # 11
            "try:",  # 12
            "    co(['e'])",  # 13 flagged: ValueError does not catch it
            "except ValueError:",  # 14
            "    pass",  # 15
            "shellout.run(['f'])",  # 16
            "import subprocess as sp",  # 17
            "sp.check_call(['g'])",  # 18 flagged: a module alias (proto.pilot)
        ]
    )
    assert unguarded_calls(source) == [3, 7, 13, 18]


def test_every_reporting_shell_out_survives_a_missing_binary():
    population = scanned(_population(), "reporting modules")
    found = {rel: unguarded_calls(path.read_text(encoding="utf-8")) for rel, path in population.items()}
    offenders = [f"{rel}:{line}" for rel, lines in found.items() for line in lines]
    assert not offenders, (
        "These calls raise FileNotFoundError when the tool is not on PATH, which cron's PATH "
        "makes likely, skipping the caller's own unavailable branch. Use "
        f"scripts.reporting.shellout.run, or catch it: {offenders}"
    )


def test_a_missing_tool_and_a_hang_are_results():
    missing = shellout.run(["a-tool-that-does-not-exist-anywhere"], capture_output=True, text=True)
    assert (missing.returncode, missing.stdout) == (shellout.MISSING, "")
    hung = shellout.run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2)
    assert (hung.returncode, hung.stdout) == (shellout.TIMED_OUT, "")


def test_a_non_executable_tool_is_a_result(tmp_path):
    tool = tmp_path / "tool"
    tool.write_text("#!/bin/sh\n", encoding="utf-8")
    assert shellout.run([str(tool)]).returncode == shellout.CANNOT_EXECUTE


def test_a_missing_working_directory_is_not_called_a_missing_tool(tmp_path):
    with pytest.raises(FileNotFoundError):
        shellout.run([sys.executable, "-c", "pass"], cwd=tmp_path / "absent")


def test_an_unenterable_cwd_is_not_called_an_unexecutable_tool(tmp_path, monkeypatch):
    def refused(argv, **kwargs):
        raise PermissionError(13, "Permission denied", str(kwargs["cwd"]))

    monkeypatch.setattr(shellout.subprocess, "run", refused)
    monkeypatch.setattr(shellout.os, "access", lambda path, mode: False)
    with pytest.raises(PermissionError):
        shellout.run(["git", "status"], cwd=tmp_path)
