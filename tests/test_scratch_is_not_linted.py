"""Every linter that walks the tree skips the scratch directory the gates write into.

`scripts/paths.py::TMP_DIR` is where this tree's gates put their reports and where
its rules send scratch work, and it is gitignored. A linter that walks a directory
rather than taking filenames from git does not read `.gitignore`, so it needs the
exclusion spelled in its own config — and three files agreeing on that is an
agreement nothing held.

dream.doll hit the gap from the adopter's side, which is the side that matters:
their `eslint.config.js` was their own, forked before the template's, and lacked
the `tmp/**` ignore the template has shipped since v0.1.0. Following their own
rule — scratch goes in `tmp/` — failed their lint gate at `--max-warnings=0`,
reported as an ordinary lint failure with nothing pointing at the cause, and the
cheap fix deletes the scratch file along with what it was measuring. The template
was consistent the whole time; the broken party was a config the template never
saw. So this is phrased over the tree's own configs, whoever wrote them.

**The linters are listed, and that is a known cost.** Which tools walk directories
is a fact about how `dev check` and CI invoke them — `flake8 .`, `eslint .`,
`black .` — and not something a pattern can find in a config file. What is
discovered is presence: a config that does not exist is not asserted, so a tree
without node is not told about eslint.
"""

from __future__ import annotations

import configparser
import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import PROJECT_ROOT, TMP_DIR  # noqa: E402

SCRATCH = TMP_DIR.relative_to(PROJECT_ROOT).as_posix()


def _flake8(text: str) -> bool:
    parser = configparser.ConfigParser(inline_comment_prefixes=("#",))
    parser.read_string(text)
    entries = [entry.strip() for entry in parser.get("flake8", "exclude", fallback="").replace("\n", ",").split(",")]
    return SCRATCH in entries or f"./{SCRATCH}" in entries


def _black(text: str) -> bool:
    block = re.search(r"\[tool\.black\](.*?)(?:\n\[|\Z)", text, re.S)
    return bool(block and re.search(rf"exclude\s*=.*?\b{re.escape(SCRATCH)}\b", block.group(1), re.S))


def _eslint(text: str) -> bool:
    return f"'{SCRATCH}/**'" in text or f'"{SCRATCH}/**"' in text


#: `config file -> does it exclude the scratch directory`. A walking linter per row.
WALKERS = {".flake8": _flake8, "pyproject.toml": _black, "eslint.config.js": _eslint}


def test_every_walking_linter_skips_scratch():
    present = {name: check for name, check in WALKERS.items() if (PROJECT_ROOT / name).exists()}
    assert present, "found none of the linter configs this knows about, so this checked nothing"
    lints_scratch = [name for name, check in present.items() if not check((PROJECT_ROOT / name).read_text("utf-8"))]
    assert not lints_scratch, (
        f"these configs do not exclude `{SCRATCH}/`, where this tree's gates write their reports and its "
        f"rules send scratch work: {lints_scratch}\n"
        f"The linter walks the directory and does not read .gitignore, so scratch fails the lint gate "
        f"as an ordinary finding. Add `{SCRATCH}` to its exclude (for eslint, `'{SCRATCH}/**'` in ignores)."
    )
