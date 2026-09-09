"""pyright is pointed at directories that exist and hold Python.

`pyright --project pyrightconfig.json` is run by the pre-commit hook and by CI,
and both read its exit code. It exits 0 over an empty scope exactly as happily
as over a clean one, printing `0 errors, 0 warnings, 0 informations` either way.

That is the general shape rather than a quirk of this tool:

> **A negative result from a matcher means either the thing is absent or the
> matcher is blind, and nothing in the output distinguishes them.**

Which is why a check should report its **scope** beside its verdict — the way
`dev check docs` names how many docs it enumerated. pyright will do that
(`--outputjson` carries `summary.filesAnalyzed`), but only at the cost of
parsing its report in two places that today just read a status code.

So this asserts the **precondition** instead of the result, which is cheaper and
catches the realistic failure. A type checker does not quietly lose its scope by
accident; it loses it when a directory is renamed or moved and `include` is not
updated with it. Checking that every included path resolves and holds at least
one `.py` catches that, runs in the unit suite in milliseconds, and needs no
pyright installed — so it holds on a machine that has never fetched the node
package, which is where a hook is most likely to be skipped.

Reported by proto.pilot, who found the hole in a tree scaffolded from this
template. It was the third instance of that shape in that repo in one day, and
this one had been shipped to them.

## If you already have this gate, you are the one who reported it

An upgrade classifies from the manifest: a different hash is an edit, no entry is
a collision, and **neither** is a genuinely new file — so a file that is new here
and old in your tree arrives as a clean addition, backed by nothing. That is not
a rare accident; the report-and-adopt loop manufactures it. You write a gate in
your tree, report the idea, and it ships back at whatever path this repository
would have picked anyway. Both halves are right and the paths differ for no
reason at all.

No manifest can catch it — it needs a diff of *purposes*, not of bytes. What it
needs instead is the one fact only the producer has, which is that this file came
from a report, so here it is in the file rather than in a message that has to be
remembered: if your tree holds a gate asserting that pyright's ``include`` paths
resolve and hold Python, this is that gate under a new name. Keep one. Which one
does not matter; running both under two names does, because they will drift.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanning import scanned  # noqa: E402
from scripts.paths import PROJECT_ROOT, SHELL_PACKAGE  # noqa: E402
from scripts.yaml_text import uncommented  # noqa: E402

CONFIG = PROJECT_ROOT / "pyrightconfig.json"

#: A whole-line `//` comment. pyright parses its config as JSONC and this file
#: uses `//` rather than a `"//"` key deliberately — see the config's own
#: comment. Only whole-line comments are stripped: a `//` inside a string would
#: need a real JSONC parser, and adding one to read four keys is not the trade.
_COMMENT = re.compile(r"^\s*//")


def load_config() -> dict:
    kept = [line for line in CONFIG.read_text(encoding="utf-8").splitlines() if not _COMMENT.match(line)]
    return json.loads("\n".join(kept))


def test_the_config_is_readable():
    """Fail loudly here rather than in every test below.

    A config pyright cannot parse is a config it runs with defaults, which is a
    different check wearing the same name.
    """
    assert CONFIG.exists(), f"{CONFIG.name} is missing — the hook and CI both pass `--project` at it"
    assert load_config().get("include"), "pyrightconfig.json declares no `include` — pyright would check nothing"


def test_every_included_path_holds_python():
    """The scope is real, so `0 errors` means something.

    Both halves matter and they fail differently: a path that does not resolve
    is a rename nobody finished, and a path that resolves but holds no `.py` is
    a directory that emptied out. Either leaves the gate green over nothing.
    """
    empty = []
    for entry in load_config()["include"]:
        target = PROJECT_ROOT / entry
        if not target.exists():
            empty.append(f"{entry}/ — no such path (renamed, and `include` was not)")
        elif not any(target.rglob("*.py")):
            empty.append(f"{entry}/ — resolves, but holds no .py")

    assert not empty, (
        "pyright is pointed at nothing, and would report `0 errors` for it:\n  "
        + "\n  ".join(empty)
        + "\nFix the path in pyrightconfig.json, or drop the entry."
    )


# --------------------------------------------------------------------------
# The interpreter, which is a different question from the scope and fails in
# the opposite direction: the scope going empty makes pyright report nothing,
# and the interpreter going wrong makes it report a great deal.
# --------------------------------------------------------------------------

#: Files that could plausibly run pyright, recomputed by glob on every run. A
#: registry is exactly the failure being guarded against here — the defect is a
#: caller nobody remembered — so listing them would reproduce it. The shell's
#: directory comes from `scripts/paths.py` because `--shell-package` renames it.
_CALLER_GLOBS = (
    ".github/workflows/*.yml",
    "scripts/**/*.py",
    f"{SHELL_PACKAGE}/**/*.py",
    "scripts/**/*.sh",
)
_EXTRA_CALLERS = (".pre-commit-config.yaml",)

# `tests/` is deliberately not scanned, and it is the one hole worth naming: a
# test that shelled out to pyright unpinned would go unseen. The alternative is
# worse — this file argues about pyright at length, in prose containing both
# flags, so scanning `tests/` makes the gate its own first finding, and the only
# fix available then is an allowlist entry for the detector's own source.

#: How far past the word `pyright` an invocation's flags may sit. Generous
#: because a call can be spread over several lines of a list or a `run: |` block.
#: The looseness has a direction: a pinned call within this distance of an
#: unpinned one masks it. Every call site in this template is one per file, and
#: a narrower window cuts `pyright --project pyright|config.json` in half.
_WINDOW = 400

#: Above 1 because the scan feeds a filter, and a filter tested against one item
#: cannot be shown to select anything.
#:
#: A FLOOR, never an equality, and the reason is on its second demonstration.
#: This comment used to enumerate the callers — "core ships exactly three, and
#: higher tiers add `dev commit`" — and `scripts/lint_pyright_gate.py` made
#: it four at `core` without touching this line. The count was never the
#: load-bearing part, and a count copied into prose beside the constant it
#: describes is the failure this template keeps recording. The shape is what
#: holds: the pre-commit hook, CI, and every CLI command that type-checks, all
#: of them discovered by `_CALLER_GLOBS` rather than named here.
_MIN_CALLERS = 3


def _pyright_invocations() -> dict:
    """Every file that runs pyright, as `path -> every invocation in it is pinned`.

    Comments are blanked first, and the mask is load-bearing in both directions —
    measured on a fresh scaffold by planting each:

    * a comment mentioning the command in a file that runs nothing enrols that
      file, so the failure message names a caller that does not exist; and
    * `# TODO: pass --pythonpath here`, anywhere within the window of a real call,
      flips that call to **pinned** and the rule goes green over it.

    The second is `check_workflow_drift.py`'s shape exactly: the string most
    likely to appear where the thing is missing is a comment saying it should be
    there, so the silent pass is perfectly correlated with the defect.
    `scripts/yaml_text.py` owns the masking; its `#` rule is the same in YAML,
    Python and shell, which is every language scanned here.

    Occurrences within a file are combined with `and`, so one unpinned call makes
    the file unpinned however many pinned ones surround it.
    """
    paths = [PROJECT_ROOT / name for name in _EXTRA_CALLERS]
    for pattern in _CALLER_GLOBS:
        paths.extend(sorted(PROJECT_ROOT.glob(pattern)))

    found: dict = {}
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = uncommented(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        for match in re.finditer(r"pyright", text):
            window = text[match.start() : match.start() + _WINDOW]
            if "--project" not in window:
                continue  # a mention of pyrightconfig.json, not a call
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            found[rel] = found.get(rel, True) and "--pythonpath" in window
    return scanned(found, "files that invoke pyright", least=_MIN_CALLERS)


def _config_pins_the_interpreter() -> bool:
    config = load_config()
    return bool(config.get("pythonPath")) or bool(config.get("venvPath") and config.get("venv"))


def test_the_caller_scan_still_sees_callers():
    """One unconditional call, so the scan below can never go blind unnoticed.

    The rule test returns early when the config pins, which is the ordinary
    state of this tree — so on its own it would stop exercising the scan the
    moment the scan started working. `scanned()` inside the helper is what makes
    the floor non-omissible; this is what guarantees somebody calls it.
    """
    _pyright_invocations()


def test_no_pyright_caller_resolves_its_interpreter_from_path():
    """No caller may take its interpreter from `PATH`. One place may satisfy this.

    `reportMissingImports` is `none`, so an interpreter without this tree's
    packages raises no import error at all — the packages become `Unknown` and
    cascade into errors in files the commit never touched. The root cause is the
    suppressed one, so what you see is a pile of plausible consequences, and it
    reads as a broken tree rather than a broken environment.

    The size of that is worth one number. A scaffold of this template, checked on
    2026-09-07 with the same pyright and the same project file, differing only in
    which interpreter `PATH` offered first: **27 errors** unpinned, **0** pinned.
    Every one of the 27 was `click` resolving to `Unknown`, which leaves each
    `@group.command()` an attribute access on an undecorated function.

    Stated as a disjunction on purpose. Either

    * the **config** pins — `venvPath` + `venv`, or `pythonPath` — which is the
      only place that reaches every caller, because the pre-commit hook is
      `language: node` with `pass_filenames: false` and cannot name a per-machine
      path; or
    * **every** caller passes `--pythonpath`.

    The second is the fragile one and both repositories that have measured it are
    the evidence rather than the hypothesis. jam.sense had six call sites and two
    pinned, and the four that were not each failed differently: one *could* not
    pass the flag, one passed `--pythonversion` — the language level, not the
    interpreter — under a comment about interpreter resolution, one ran bare from
    cron where nobody watches, and one was the commit command everybody is told
    to use. This template shipped the degenerate case: four callers, none pinned,
    and its only pinned invocation in `bin/skeletor-verify`, which lives in the
    generator and no adopter runs.

    **A caller can half-remember and look pinned**, which is why this scans
    rather than lists. The rule does not mandate a mechanism, because a tree that
    genuinely pins at every call site is correct and a gate that forbids a
    working arrangement is one an adopter deletes.

    ## What this cannot assert, and why it is not tightened

    *Pins* is not *resolves*. `venvPath` is relative to the config file, so it
    names the **checkout**; a linked worktree gets its own copy of the config and
    no `.venv` beside it, and the pin falls through there silently. The honest
    assertion would be *the pinned virtualenv exists here*, and that is
    checkout-dependent: it would be red in CI, which correctly passes
    `--pythonpath` instead, and red in every worktree that has not been
    provisioned. A unit test cannot hold a runtime fact about the directory it
    happens to be standing in. The limit is written into `pyrightconfig.json`
    beside the pin, where somebody reading a green run will see it.
    """
    callers = _pyright_invocations()
    if _config_pins_the_interpreter():
        return

    unpinned = sorted(path for path, pinned in callers.items() if not pinned)
    assert not unpinned, (
        "pyrightconfig.json no longer pins the interpreter, and these callers resolve it from PATH:\n  "
        + "\n  ".join(unpinned)
        + '\n\nRestore the pin (`venvPath: "."` + `venv: ".venv"`) rather than adding the flag to each '
        "caller. It is safe where no virtualenv exists — pyright prints `venv .venv subdirectory not "
        "found`, falls back to PATH and leaves the exit code alone."
    )
