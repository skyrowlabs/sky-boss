"""Which files are this repository's claim, and which describe another time.

Two questions every doc check has to answer before it can assert anything, and
both were answered once, in `test_docs_name_live_code.py`, where the second gate
to need them could not see them.

## Tracked, not walked

`rglob` reads whatever is on the disk. In a working tree that includes
`.venv/lib/.../pyright/dist/README.md` and `.pytest_cache/README.md` — files
`.gitignore` already declares are not ours. **The verdict is then
machine-dependent**: it turns on what the dependency tree happens to ship, so
one person's red cannot be reproduced by the next, which is worse than a false
positive that everybody sees. stash.flow hit it with six such files on the first
run of a gate that had shipped the day before; it had passed here only because
pyright's bundled README happens to contain no path-shaped inline code.

`git ls-files` asks the repository instead, and an untracked scratch file is not
this repository's claim.

## Narrative, excluded by role

A plan saying *"this phase takes `old_helper()` and moves it"* is correct, and
naming the dead symbol is the entire point of the sentence. The same is true of
paths: *"move `scripts/old_check.py` into `scripts/checks/`"* names a file that
must not exist once the plan is done. A resolve-check fires on the plan for
being a plan.

The set comes from `scripts.paths.NARRATIVE`, which is where an adopter extends
it — see the reason written there.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import NARRATIVE, PROJECT_ROOT  # noqa: E402


def git(*args: str, root: Path = PROJECT_ROOT) -> str:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, check=True).stdout


def tracked(pattern: str, root: Path = PROJECT_ROOT) -> list:
    """Tracked files only. An untracked scratch file is not this repo's claim."""
    return [root / line for line in git("ls-files", pattern, root=root).splitlines() if line.strip()]


def reference_docs(root: Path = PROJECT_ROOT) -> list:
    """Tracked markdown that is meant to describe the tree as it is now."""
    narrative = tuple(str(directory.relative_to(PROJECT_ROOT)) for directory in NARRATIVE)
    return [path for path in tracked("*.md", root=root) if not str(path.relative_to(root)).startswith(narrative)]
