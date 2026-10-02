"""Every linter that walks the tree skips the scratch directory the gates write into.

`scripts/paths.py::TMP_DIR` is where this tree's gates put their reports and where
its rules send scratch work. A linter run as `<tool> .` walks it unless its own
configuration or `.gitignore` handling says otherwise — and whether it does is a
fact about the tool's behaviour, not about how a config spells an exclusion.

Dream Doll hit the gap from the adopter's side: their own `eslint.config.js`
lacked the `tmp/**` ignore the template has shipped since v0.1.0, so following
their rule — scratch goes in `tmp/` — failed `--max-warnings=0` as an ordinary
lint finding.

## Behaviour, because the first version read spelling and was wrong both ways

v0.31.0 checked config text. Dream Doll's ignore said `'tmp'`, which eslint
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
    """Tools this tree runs over the whole tree, as `dev check lint` runs them.

    Two spellings of *the whole tree*: a `run([tool, ..., "."])` in the check,
    or `<tool> .` in an npm script — and pyright's, which walks by
    `--project pyrightconfig.json` and never names a directory. stash.flow read
    that the first version matched only `"."`, so pyright was never probed and a
    widened `include` would have linted `tmp/` under a green test. This is still
    a reading of how the tools are invoked; the verdict about each one is not.
    """
    found = []
    if CHECK.exists():
        text = CHECK.read_text(encoding="utf-8")
        found += re.findall(r"""run\(\[\s*["']([\w-]+)["'][^\]]*["']\.["']""", text)
        if re.search(r"pyright[^\n]*--project", text):
            found.append("pyright")
    if PACKAGE.exists():
        scripts = json.loads(PACKAGE.read_text(encoding="utf-8")).get("scripts", {})
        walking = re.compile(r"(?:^|&&\s*)([\w-]+) \.(?:\s|$)")
        found += [match for command in scripts.values() for match in walking.findall(command)]
    return sorted(set(found))


def _python_tool(module: str, args: List[str], source: str) -> Callable[[], Tuple[Optional[bool], str]]:
    """A probe that plants `source` under scratch and runs `python -m <module> <args>`."""

    def probe() -> Tuple[Optional[bool], str]:
        (PROBE_DIR / "probe.py").write_text(source, encoding="utf-8")
        done = subprocess.run(
            [sys.executable, "-m", module, *args], cwd=str(PROJECT_ROOT), capture_output=True, text=True
        )
        # A tool that could not run did not skip scratch; it said nothing. The first
        # version read its silence as a pass — a planted `ruff` probe with no ruff
        # installed came back green — which is "I could not measure" reported as
        # "the budget is respected", the one answer these checks must never give.
        if f"No module named {module}" in done.stderr:
            return None, f"could not run `{module}` — it is not installed in {sys.executable}"
        return PROBE_DIR.name in done.stdout + done.stderr, f"ran `{module} {' '.join(args)}`"

    return probe


def _names_scratch(pattern: str) -> bool:
    """Whether a glob excludes the scratch directory itself: `tmp`, `./tmp`, `tmp/**`, `**/tmp`, `**/tmp/**`.

    **The directory has to be named.** The first version read any `**/…` entry
    as covering scratch, so `"**/node_modules"` passed a config that lints `tmp/`
    — stash.flow forced this fallback with a stub and fed it three configs. That
    is "could not ask" reported as "skips it", in the branch that exists for when
    asking is impossible.
    """
    parts = [part for part in pattern.strip().split("/") if part not in ("", ".")]
    while parts and parts[0] == "**":
        parts = parts[1:]
    while parts and parts[-1] == "**":
        parts = parts[:-1]
    return parts == SCRATCH.split("/")


def _pyright() -> Tuple[Optional[bool], str]:
    """Ask pyright which files it analysed; read `pyrightconfig.json` if it cannot answer, and say so."""
    (PROBE_DIR / "probe.py").write_text("x: int = 'not an int'\n", encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-m", "pyright", "--outputjson", "--project", "pyrightconfig.json"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    if done.stdout.lstrip().startswith("{"):
        return PROBE_DIR.name in done.stdout, "ran `pyright --outputjson --project pyrightconfig.json`"
    # JSONC: the template's own config explains itself in `//` comments, which
    # `json.loads` refuses. Whole-line comments only, which is what it carries.
    text = (PROJECT_ROOT / "pyrightconfig.json").read_text(encoding="utf-8")
    config = json.loads("\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//")))
    include = [entry.strip("./") for entry in config.get("include", ["."])]
    walks = any(entry in ("", SCRATCH) or SCRATCH.startswith(entry + "/") for entry in include)
    excluded = any(_names_scratch(entry) for entry in config.get("exclude", []))
    return walks and not excluded, "READ pyrightconfig.json — pyright could not be run here, so it was not asked"


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
    "flake8": _python_tool("flake8", ["--select=F401", "."], "import os\n"),
    "isort": _python_tool("isort", ["--check-only", "."], "import sys\nimport os\n"),
    "black": _python_tool("black", ["--check", "."], "x=1\n"),
    "pyright": _pyright,
    "eslint": _eslint,
}

#: What the template ships, captured before anything is appended. A shipped probe
#: for a tool this tree does not walk with is not stale — a python-only tree has
#: no eslint, a ruff tree has no flake8 — so only an entry YOU appended is held
#: to "something here walks with it".
_SHIPPED = frozenset(PROBES)

#: **Add your own probes as an append, in the space between the two frozen rules
#: at the end of this section — one for each tool your `check lint` walks with
#: that the table above does not know.** A probe plants a file the tool would
#: flag and reports whether its output named it:
#:
#:     PROBES["ruff"] = _python_tool("ruff", ["check", "--select=F401", "."], "import os\n")
#:
#: This used to be a table you edited, twice: mind.head's ruff tree had to add a
#: `ruff` row and delete the three it does not run, because the check held every
#: row to "something here walks with it" in both directions. That made a vendored
#: literal a permanent merge point, which is the thing an append seam exists to
#: avoid. Shipped rows are no longer held to it; yours are.


# ── Extending PROBES ─────────────────────────────────────────────────────────
#
# **Put every append to PROBES, and any comment you write about it, in the space
# between the two frozen rules at the bottom of this block.** skeletor ships that
# space empty and never adds a line to it; `scripts/paths.py` records why there
# are two rules and what the space buys.
#
# ── Nothing below this line is skeletor's ────────────────────────────────────
#
# Everything of yours goes between this rule and the closing one below: appends,
# and any prose you write about them. Both rules are frozen — skeletor does not
# rewrite either block and renders nothing between them, so your insertion point
# is never adjacent to a template line that a release might edit. The
# explanation above IS ordinary prose and does get rewritten, which is why the
# rule sits at the bottom of it rather than at the top.


# ── Skeletor's again below this line ─────────────────────────────────────────
#
# The space is bounded on both sides for the reason `scripts/paths.py` measures:
# this file carries template-owned code further down, and one rule alone would
# have certified all of it as yours.
# ── The checks ───────────────────────────────────────────────────────────────


def test_every_walker_has_a_probe_and_every_probe_a_walker():
    walkers = _walkers()
    assert walkers, f"found no tool run over the tree in {CHECK.relative_to(PROJECT_ROOT)} or package.json"
    assert not set(walkers) - set(PROBES), (
        f"these tools walk the tree and nothing here asks whether they skip `{SCRATCH}/`: "
        f"{sorted(set(walkers) - set(PROBES))}. Add a probe for each as an append, between this file's "
        f"two frozen rules — a file that tool would flag."
    )
    stale = sorted(set(PROBES) - _SHIPPED - set(walkers))
    assert not stale, f"you appended probes for tools nothing here walks with: {stale}. Delete the append."


def test_every_walking_linter_skips_scratch():
    walkers = [tool for tool in _walkers() if tool in PROBES]
    assert walkers, "no walking linter to probe, so this measured nothing"
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        verdicts = {tool: PROBES[tool]() for tool in walkers}
    finally:
        shutil.rmtree(PROBE_DIR, ignore_errors=True)
    unasked = {tool: how for tool, (walked, how) in verdicts.items() if walked is None}
    assert not unasked, (
        "these walkers could not be asked, so whether they lint scratch is unknown — which is not a pass:\n"
        + "\n".join(f"  {tool}: {how}" for tool, how in unasked.items())
    )
    lints_scratch = {tool: how for tool, (walked, how) in verdicts.items() if walked}
    assert not lints_scratch, (
        f"these linters walk into `{SCRATCH}/`, where this tree's gates write their reports and its rules "
        f"send scratch work:\n"
        + "\n".join(f"  {tool}: {how}" for tool, how in lints_scratch.items())
        + f"\nExclude `{SCRATCH}` in that tool's own configuration; scratch otherwise fails the lint gate "
        f"as an ordinary finding."
    )
