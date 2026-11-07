#!/usr/bin/env python3
"""Prove a gate catches what it claims: apply a patch in a throwaway copy and require red.

A plant in the working tree risks the tree, and a plant nobody checked proves little:
one that did not land and one the gate caught look alike, and so do a gate that went
red and one that already was. So this runs in a copy of the tree as `git add -A`
would stage it, and in order: the copy must be what imports, the named thing must be
green, the patch must land, and the named thing must then go red.

Exit 0 means it went red as claimed, 1 that it stayed green, 2 that nothing was proved.
A command counts as red only on exit 1, since 2 and 3 say it could not judge.

An editable install can import the real tree from a child, so `PYTHONPATH` points at
the copy and a preflight asks a child at `/` where each package resolves. A child that
clears its environment is out of reach. A local run does not prove CI runs the gate.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
from pathlib import Path

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import (  # noqa: E402
    EXIT_GREEN,
    EXIT_NO_SUBJECT,
    EXIT_RED,
    EXIT_REFUSED,
    detail,
    fail,
    item,
    ok,
    step,
)
from scripts.paths import PROJECT_ROOT  # noqa: E402
from scripts.rehearse_scheduled import snapshot  # noqa: E402

#: A name, not a parenthesised tuple: at a 3.14 target black rewrites `except (A, B):`.
_UNREADABLE = (OSError, ElementTree.ParseError)

#: Untracked but needed to run anything, so the copy borrows them.
BORROWED = (".venv", "node_modules")

_WHERE = """
import importlib.util, json, sys
found = {}
for name in sys.argv[1:]:
    spec = importlib.util.find_spec(name)
    places = list(spec.submodule_search_locations or []) if spec else []
    found[name] = places[0] if places else (spec.origin if spec else None)
print(json.dumps(found))
"""


class Refused(Exception):
    """Nothing was proved, for the reason given."""


def packages(root: Path) -> list[str]:
    """Top-level python packages in `root`, and under its `src/`: whatever a child must import from the copy."""
    found = set()
    for parent in (root, root / "src"):
        for child in parent.glob("*") if parent.is_dir() else ():
            if child.is_dir() and not child.is_symlink() and any(child.glob("*.py")):
                found.add(child.name)
    return sorted(found)


def preflight(copy: Path, env: dict) -> int:
    """How many packages resolve inside `copy`; refuses if any does not, or none were found."""
    names = packages(copy)
    if not names:
        raise Refused(f"no python package found in {copy}, so nothing shows the copy is what runs")
    done = subprocess.run(
        [sys.executable, "-c", _WHERE, *names], cwd="/", env=env, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise Refused(f"the preflight child failed:\n{done.stderr.strip()}")
    outside = {
        name: where
        for name, where in json.loads(done.stdout).items()
        if where is None or not Path(where).resolve().is_relative_to(copy.resolve())
    }
    if outside:
        lines = "\n".join(f"  {name}: {where}" for name, where in sorted(outside.items()))
        raise Refused(f"a child would import these from outside the copy, so a red proves nothing:\n{lines}")
    return len(names)


def counts(report: Path) -> dict:
    """Totals from a junit report: `{tests, failures, errors, skipped}`, all zero if it is unreadable."""
    try:
        root = ElementTree.parse(report).getroot()
    except _UNREADABLE:
        return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    suite = root if root.tag == "testsuite" else root[0]
    return {key: int(suite.get(key, 0)) for key in ("tests", "failures", "errors", "skipped")}


def report_state(totals: dict) -> str:
    """`green`, `red`, or why the run says nothing: a skip is neither, and a crash is not the test failing."""
    if totals["tests"] == 0:
        return "nothing ran under that id"
    if totals["errors"]:
        return "it errored rather than failed"
    if totals["failures"]:
        return "red"
    return "it was skipped" if totals["skipped"] else "green"


def command_state(code: int) -> str:
    """A command's exit code the same way: only 0 and 1 are a verdict."""
    if code == EXIT_GREEN:
        return "green"
    if code == EXIT_RED:
        return "red"
    return "it could not judge (no subject)" if code == EXIT_NO_SUBJECT else f"it could not judge (exit {code})"


def judge(args: argparse.Namespace, copy: Path, env: dict, scratch: Path) -> str:
    """The named thing's state in `copy`."""
    if args.expect_red_cmd:
        done = subprocess.run(args.expect_red_cmd, shell=True, cwd=copy, env=env, check=False)
        return command_state(done.returncode)
    report = scratch / "junit.xml"
    report.unlink(missing_ok=True)
    pytest = [sys.executable, "-m", "pytest", args.expect_red, "-q", "-p", "no:cacheprovider", f"--junitxml={report}"]
    subprocess.run(pytest, cwd=copy, env=env, check=False)
    return report_state(counts(report))


def prove(args: argparse.Namespace, patch: Path, copy: Path, scratch: Path) -> int:
    """Everything after the checkout. Raises `Refused` when a step cannot support the claim."""
    borrowed = []
    for name in BORROWED:
        if (PROJECT_ROOT / name).exists():
            (copy / name).symlink_to((PROJECT_ROOT / name).resolve())
            borrowed.append(name)
    detail(f"borrowed from the tree: {', '.join(borrowed) or 'nothing'}")

    roots = [str(copy), *([str(copy / "src")] if (copy / "src").is_dir() else [])]
    inherited = [os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else []
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([*roots, *inherited]), "PYTHONDONTWRITEBYTECODE": "1"}

    step("the copy is what imports")
    resolved = preflight(copy, env)
    detail(f"{resolved} package(s) resolve inside the copy")

    step("green before the plant")
    before = judge(args, copy, env, scratch)
    if before != "green":
        raise Refused(f"before the plant: {before}, not green, so a red after it would prove nothing")

    step("the plant")
    apply = ["git", "apply", "--index", str(patch)]
    applied = subprocess.run(apply, cwd=copy, capture_output=True, text=True, check=False)
    if applied.returncode != 0:
        raise Refused(f"the plant did not land:\n{applied.stderr.strip()}")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=copy, check=False).returncode == 0:
        raise Refused("the plant did not land: it changed nothing")

    step("red after the plant")
    after = judge(args, copy, env, scratch)
    named = args.expect_red or args.expect_red_cmd
    if after == "red":
        ok(f"1 plant caught: {named} went red, and was green before it")
        return EXIT_GREEN
    if after == "green":
        fail(f"{named} stayed green with the plant in, so it does not catch this")
        return EXIT_RED
    raise Refused(f"after the plant: {after}, which is not the named thing going red")


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().split("\n")[0])
    parser.add_argument("patch", type=Path, help="a patch against this tree, as `git diff` writes it")
    named = parser.add_mutually_exclusive_group(required=True)
    named.add_argument("--expect-red", metavar="TEST_ID", help="the test that must go red")
    named.add_argument("--expect-red-cmd", metavar="COMMAND", help="the command that must exit 1")
    args = parser.parse_args(argv)

    patch = args.patch.resolve()
    if not patch.is_file():
        fail(f"no such patch: {patch}")
        return EXIT_REFUSED
    with tempfile.TemporaryDirectory(prefix="plant-") as held:
        scratch = Path(held)
        copy = scratch / "copy"
        commit, _ = snapshot()
        add = ["git", "worktree", "add", "--detach", "-q", str(copy), commit]
        subprocess.run(add, cwd=PROJECT_ROOT, check=True)
        try:
            return prove(args, patch, copy, scratch)
        except Refused as refusal:
            fail(str(refusal))
            return EXIT_REFUSED
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(copy)], cwd=PROJECT_ROOT, check=False)
            subprocess.run(["git", "worktree", "prune"], cwd=PROJECT_ROOT, check=False)
            item("the copy is gone")


if __name__ == "__main__":
    sys.exit(main())
