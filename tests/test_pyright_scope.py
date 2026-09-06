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

from scripts.paths import PROJECT_ROOT  # noqa: E402

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
