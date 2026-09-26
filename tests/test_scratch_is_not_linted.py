"""Every linter that walks the tree skips the scratch directory the gates write into.

`scripts/paths.py::TMP_DIR` is where this tree's gates put their reports and where
its rules send scratch work. A linter run as `<tool> .` walks it unless its own
configuration or `.gitignore` handling says otherwise — and whether it does is a
fact about the tool's behaviour, not about how a config spells an exclusion.

dream.doll hit the gap from the adopter's side: their own `eslint.config.js`
lacked the `tmp/**` ignore the template has shipped since v0.1.0, so following
their rule — scratch goes in `tmp/` — failed `--max-warnings=0` as an ordinary
lint finding.

## Behaviour, because the first version read spelling and was wrong both ways

v0.31.0 checked config text. dream.doll's ignore said `'tmp'`, which eslint
honours — they planted a file with errors and it was skipped — and the check
failed them anyway, on the tree whose incident it was written for, after the fix.
mind.head's tree runs ruff and mypy, measured both skipping `tmp/`, and was failed
because `pyproject.toml` existing was read as black being configured. Here,
black skips `tmp/` because it honours `.gitignore`, so the `extend-exclude` line
v0.31.0 required is not what decides it either. Three readings of a declaration,
three wrong answers, with the deciding value one call away each time — the shape
`least=2` and the lint-parity check were fixed for.

So each walker is **run**: a probe file it would flag is planted under
`tmp/`, the tool walks the tree the way `dev check lint` runs it, and the
question is whether its output names the probe.

## Which tools walk is discovered; how to probe one is written down

The walkers are read from `cli/check.py` — a `run([tool, ..., "."])`
call — and from `package.json`'s scripts. A probe is per-tool by nature (what
each would flag differs), so `PROBES` is a table, and it is checked against the
discovered set in both directions: a walker with no probe fails, and so does a
probe for a tool nothing walks with any more.

eslint is measured only where it is installed. A python CI job has no
`node_modules`, and "could not ask" is reported as exactly that rather than
passed: the verdict falls back to reading the config, **named as a reading** in
the result, and accepts every spelling eslint's flat config treats as the
directory.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import PROJECT_ROOT, SHELL_PACKAGE, TMP_DIR  # noqa: E402

SCRATCH = TMP_DIR.relative_to(PROJECT_ROOT).as_posix()
PROBE_DIR = TMP_DIR / "_scratch_lint_probe"
CHECK = PROJECT_ROOT / SHELL_PACKAGE / "check.py"
PACKAGE = PROJECT_ROOT / "package.json"


def _walkers() -> List[str]:
    """Tools this tree runs over the whole directory: `run(["tool", ..., "."])`, and `<tool> .` in npm scripts."""
    found = []
    if CHECK.exists():
        found += re.findall(r"""run\(\[\s*["']([\w-]+)["'][^\]]*["']\.["']""", CHECK.read_text(encoding="utf-8"))
    if PACKAGE.exists():
        scripts = json.loads(PACKAGE.read_text(encoding="utf-8")).get("scripts", {})
        walking = re.compile(r"(?:^|&&\s*)([\w-]+) \.(?:\s|$)")
        found += [match for command in scripts.values() for match in walking.findall(command)]
    return sorted(set(found))


def _python_tool(module: str, args: List[str], source: str) -> Callable[[], Tuple[Optional[bool], str]]:
    def probe() -> Tuple[Optional[bool], str]:
        (PROBE_DIR / "probe.py").write_text(source, encoding="utf-8")
        done = subprocess.run(
            [sys.executable, "-m", module, *args, "."], cwd=str(PROJECT_ROOT), capture_output=True, text=True
        )
        return PROBE_DIR.name in done.stdout + done.stderr, f"ran `{module} {' '.join(args)} .`"

    return probe


def _eslint() -> Tuple[Optional[bool], str]:
    """Ask eslint when it is installed; otherwise read the config, and say so."""
    if shutil.which("node") and (PROJECT_ROOT / "node_modules" / "eslint").is_dir():
        script = (
            "const {ESLint}=require('eslint');"
            f"new ESLint().isPathIgnored('{SCRATCH}/{PROBE_DIR.name}/probe.js')"
            ".then(i=>{process.stdout.write(i?'ignored':'linted')})"
        )
        (PROBE_DIR / "probe.js").write_text("var unused = 1;\n", encoding="utf-8")
        done = subprocess.run(["node", "-e", script], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        if done.stdout in ("ignored", "linted"):
            return done.stdout == "linted", "asked eslint (isPathIgnored)"
    config = PROJECT_ROOT / "eslint.config.js"
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    spellings = re.findall(r"""["'](?:\./)?(?:\*\*/)?([\w.-]+)(?:/(?:\*\*)?)?["']""", text)
    return SCRATCH not in spellings, "READ eslint.config.js — eslint is not installed here, so it could not be asked"


#: How to find out whether one walker lints scratch. Returns (walks it?, how that was established).
PROBES: Dict[str, Callable[[], Tuple[Optional[bool], str]]] = {
    "flake8": _python_tool("flake8", ["--select=F401"], "import os\n"),
    "isort": _python_tool("isort", ["--check-only"], "import sys\nimport os\n"),
    "black": _python_tool("black", ["--check"], "x=1\n"),
    "eslint": _eslint,
}


def test_every_walker_has_a_probe_and_every_probe_a_walker():
    walkers = _walkers()
    assert walkers, f"found no tool run over `.` in {CHECK.relative_to(PROJECT_ROOT)} or package.json"
    assert not set(walkers) - set(PROBES), (
        f"these tools walk the tree and nothing here asks whether they skip `{SCRATCH}/`: "
        f"{sorted(set(walkers) - set(PROBES))}. Add a probe to PROBES — a file that tool would flag."
    )
    # A probe for a tool the tree never runs is only stale when that tool is the
    # template's own; a python-only tree simply has no eslint to walk.
    stale = sorted(set(PROBES) - set(walkers) - {"eslint"})
    assert not stale, f"PROBES names tools nothing here walks with: {stale}. Delete the entry."


def test_every_walking_linter_skips_scratch():
    walkers = [tool for tool in _walkers() if tool in PROBES]
    assert walkers, "no walking linter to probe, so this measured nothing"
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        verdicts = {tool: PROBES[tool]() for tool in walkers}
    finally:
        shutil.rmtree(PROBE_DIR, ignore_errors=True)
    lints_scratch = {tool: how for tool, (walked, how) in verdicts.items() if walked}
    assert not lints_scratch, (
        f"these linters walk into `{SCRATCH}/`, where this tree's gates write their reports and its rules "
        f"send scratch work:\n"
        + "\n".join(f"  {tool}: {how}" for tool, how in lints_scratch.items())
        + f"\nExclude `{SCRATCH}` in that tool's own configuration; scratch otherwise fails the lint gate "
        f"as an ordinary finding."
    )
