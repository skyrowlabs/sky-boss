#!/usr/bin/env python3
"""Pyright's gate, with a pre-flight that names an environment fault as one.

`pyrightconfig.json` sets `reportMissingImports: "none"`, so an interpreter that
cannot import this project's packages does not fail the type check — it degrades
every name those packages define to `Unknown`, and only the *downstream*
consequences surface. The root cause is the suppressed one, so what you see is a
pile of plausible errors in files your commit never touched, and it reads as a
broken tree rather than a broken environment.

That is not hypothetical here. A scaffold of this template checked with an
interpreter that has no `click` reports **24 errors**: every `@group.command()`
becomes an attribute access on an undecorated function, because `click.group`
resolved to `Unknown` and stopped decorating anything. Not one of those errors
names `click`, and not one of them is a defect in the tree.

## What this does

It resolves the interpreter pyright *will* use, proves that interpreter can
import a sentinel drawn from this project's real dependencies, and only then
runs pyright — passing that same interpreter explicitly, so what was probed is
what is checked. When the probe fails it prints the interpreter, the missing
package and the fix, and **does not run pyright**: two dozen diagnostics naming
the wrong thing are worse than no diagnostics.

It fails **closed**. An interpreter that cannot be resolved at all, or that
cannot be executed, is an error and never a skip — a gate that could not run is
not a gate that passed, and this one blocks CI.

## Why the resolution order is measured rather than read

`venvPath` + `venv` **outranks** `--pythonpath`, which is the reverse of what is
easy to assume. Measured on pyright 1.1.411, same binary, same project file,
only the interpreter varied: with `.venv` present, passing a package-free
interpreter to `--pythonpath` still reported 0 errors. Resolving `PATH` before
the config venv would make this pre-flight probe an interpreter pyright ignores
— a green probe followed by a red check, which is worse than either alone.

The two flags are also mutually exclusive, so there is no invocation that both
names an interpreter and overrides the config.

## Why CI does not call this

The type-check job installs `.github/pyright-deps.txt` onto the runner's
interpreter and runs pyright against it, with no `.venv` in the checkout — so it
is outside this failure mode by construction, and every interpreter question is
already answered in the workflow. Adding a wrapper there would put a moving part
in the one caller that never had the problem.

The commit-time callers are the ones that resolve implicitly, and they are the
ones routed through here: the `pyright` pre-commit hook, and the CLI's own
re-implementations of it.

Usage:
    python scripts/lint_pyright_gate.py
    python scripts/lint_pyright_gate.py --preflight-only    # resolve, probe, print
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import detail, fail  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402

DEFAULT_CONFIG = PROJECT_ROOT / "pyrightconfig.json"

#: A whole-line `//` comment. pyright parses its config as JSONC, and this
#: template's `pyrightconfig.json` uses `//` rather than a `"//"` key
#: deliberately — see that file's own comment. Only whole-line comments are
#: stripped: a `//` inside a string would need a real JSONC parser, and adding
#: one to read three keys is not the trade. `tests/test_pyright_scope.py` reads
#: the same file the same way.
_COMMENT = re.compile(r"^\s*//")

#: The smallest set that separates a project-capable interpreter from a bare one.
#:
#: `click` is first because it is the one this template has actually been bitten
#: by: the CLI is built out of `@group.command()`, so losing `click` alone turns
#: a clean tree into 24 errors. `pytest` covers `tests/`, which
#: `pyrightconfig.json` also includes.
#:
#: HARD CONSTRAINT, pinned by `tests/test_pyright_gate_preflight.py`: every
#: sentinel must be reachable from `.github/pyright-deps.txt`. That file is what
#: CI installs, so a sentinel outside it is a gate that fails on a correctly
#: provisioned runner. Growing this tuple is a deliberate act with a test behind
#: it, never a convenience — each addition is one more way to block a commit
#: that pyright would have checked fine.
SENTINEL_IMPORTS = ("click", "pytest")

#: Where a venv keeps its interpreter, most-likely first.
_VENV_BINDIRS = (("bin", "python"), ("bin", "python3"), ("Scripts", "python.exe"))


def resolve_interpreter(config: Path) -> Tuple[Optional[Path], str]:
    """The interpreter pyright will use for `config`, and where it came from.

    Mirrors pyright's own order, measured rather than read out of the docs:

    1. `venvPath` + `venv`, when that directory exists. This outranks
       `--pythonpath` — see the module docstring.
    2. `pythonPath` from the config.
    3. `PATH`: `python3`, then `python`.

    Returns `(None, reason)` when nothing resolves, which is the fail-closed case.
    """
    root = config.parent
    try:
        text = config.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{config} could not be read ({exc})"
    try:
        parsed = json.loads("\n".join(line for line in text.splitlines() if not _COMMENT.match(line)))
    except ValueError as exc:
        return None, f"{config} did not parse as JSONC ({exc})"

    venv_path, venv = parsed.get("venvPath"), parsed.get("venv")
    if venv_path and venv:
        base = (root / venv_path / venv).resolve()
        for parts in _VENV_BINDIRS:
            candidate = base.joinpath(*parts)
            if candidate.exists():
                return candidate, f"{config.name} venvPath+venv -> {base}"

    if configured := parsed.get("pythonPath"):
        candidate = Path(configured)
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        if candidate.exists():
            return candidate, f"{config.name} pythonPath"

    for name in ("python3", "python"):
        if found := shutil.which(name):
            return Path(found), f"PATH ({name})"

    return None, "neither python3 nor python is on PATH"


def probe(interpreter: Path, module: str) -> Tuple[bool, str]:
    """Can `interpreter` import `module`? Any failure to run it is a failure."""
    try:
        proc = subprocess.run(
            [str(interpreter), "-c", f"import {module}"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"could not execute the interpreter: {exc}"
    if proc.returncode == 0:
        return True, ""
    output = (proc.stderr or proc.stdout).strip()
    return False, output.splitlines()[-1] if output else f"exited {proc.returncode} with no output"


def preflight(config: Path) -> Tuple[Optional[Path], List[str]]:
    """`(interpreter, [])` when the environment is sound, `(None, lines)` otherwise."""
    interpreter, source = resolve_interpreter(config)
    if interpreter is None:
        return None, [
            "pyright's interpreter could not be resolved — the type gate cannot run.",
            f"  {source}",
            "  This gate blocks CI, so it fails rather than pass a commit it never checked.",
            "  Fix: create this checkout's virtualenv, or set venvPath/venv in pyrightconfig.json.",
        ]

    for module in SENTINEL_IMPORTS:
        sound, why = probe(interpreter, module)
        if sound:
            continue
        return None, [
            f"pyright's interpreter cannot import '{module}' — this is an ENVIRONMENT fault,",
            "not a defect in the tree, and pyright was NOT run.",
            "",
            f"  interpreter : {interpreter}",
            f"  resolved by : {source}",
            f"  probe       : {interpreter} -c 'import {module}'",
            f"  result      : {why}",
            "",
            "  pyrightconfig.json sets reportMissingImports: 'none', so pyright would not",
            f"  have reported the missing '{module}'. It would have degraded everything that",
            "  package types to Unknown and reported the fallout as errors in files you never",
            "  touched — losing 'click' alone is 24 of them, none naming click.",
            "",
            "  Fix — put this checkout's virtualenv on PATH:",
            '      PATH="$PWD/.venv/bin:$PATH" <your command>',
            "  Or install this project's packages into the interpreter above:",
            f"      {interpreter} -m pip install -r .github/pyright-deps.txt",
            "  A checkout with no .venv of its own resolves from PATH — that is this case.",
        ]

    return interpreter, []


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--project", default=str(DEFAULT_CONFIG), help="pyright project config")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="resolve and probe the interpreter, print it to stdout, and exit without running pyright",
    )
    args = parser.parse_args(argv)

    config = Path(args.project)
    if not config.is_absolute():
        config = (Path.cwd() / config).resolve()

    interpreter, message = preflight(config)
    if interpreter is None:
        fail(message[0])
        for extra in message[1:]:
            detail(extra)
        return 1

    if args.preflight_only:
        # stdout, because this is the one thing here a caller consumes.
        print(interpreter)
        return 0

    pyright = shutil.which("pyright")
    if pyright is None:
        fail("pyright is not on PATH — the type gate cannot run.")
        detail("This gate blocks CI, so it fails rather than pass a commit it never checked.")
        detail("The pre-commit hook supplies it from its own node environment; running this")
        detail("script by hand needs the pinned version on PATH (see .pre-commit-config.yaml).")
        return 1

    # `--pythonpath` is what makes the probe binding: the interpreter proven
    # above is the interpreter checked below, rather than one resolved a second
    # time. It is inert when the config's venv pin already resolved to the same
    # path, and load-bearing in every other case.
    #
    # No `--pythonversion`, ever — the CLI flag overrides the config, and
    # `pyrightconfig.json`'s `pythonVersion` is the single source for it.
    return subprocess.run(
        [pyright, "--project", str(config), "--pythonpath", str(interpreter)],
        cwd=os.fspath(config.parent),
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
