"""Which files are this repository's claim, and which describe another time.

Two questions every doc check has to answer before it can assert anything, and
both were answered once, in `test_docs_name_live_code.py`, where the second gate
to need them could not see them.

## Asked of git, not walked

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

import pytest

from scripts.paths import NARRATIVE, PROJECT_ROOT  # noqa: E402

#: Every test here is host-side and needs no services up.
pytestmark = [pytest.mark.unit]


def git(*args: str, root: Path = PROJECT_ROOT) -> str:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, check=True).stdout


def present(pattern: str, root: Path = PROJECT_ROOT) -> list:
    """Files in the working tree that git does not disclaim — tracked or not.

    **The index is the wrong population, and this was named `tracked` for one
    release while being read as "what is in the tree".** Those differ for
    exactly one set of files and it is the set that matters: everything an
    upgrade has just written. `bin/skeletor-upgrade` writes and never stages, so
    a file it delivered is untracked until somebody runs `git add` — and a gate
    enrolling by `ls-files` looks straight past it, passes, and then fails on
    the adopter's commit, where it reads as their mistake rather than as a check
    that never covered them.

    That is `test_json_hook_covers_tracked_files.py`'s own documented failure,
    arriving through the enrolment instead of the exclude. sky.boss found it.

    `--others --exclude-standard` is what makes the two halves agree. The
    original reason for asking git at all was that `rglob` reads
    `.venv/lib/.../pyright/dist/README.md` and `.pytest_cache/README.md`, so the
    verdict became a function of what the dependency tree happened to ship —
    machine-dependent, and worse than a false positive everybody sees. Those are
    gitignored, so `--exclude-standard` still excludes them; what comes back is
    what `.gitignore` does **not** disclaim.

    A genuine scratch file is now in scope, and that is the right trade rather
    than a regression. A false positive is reported and fixed in the session
    that created it; a false negative is silence. `scripts/yaml_text.py` states
    that asymmetry for comment masking, and it is the same one.

    **The file above kept its name on purpose, and the reason is worth more than
    the tidiness.** `test_json_hook_covers_tracked_files.py` now describes its
    population slightly wrong, and renaming it was drafted and reverted:
    `bin/skeletor-upgrade` never deletes, so a renamed module arrives beside the
    one it replaces, and the old copy imports a helper this release removed.
    Measured — every adopter's `pytest` would have stopped at
    `ImportError: cannot import name 'tracked'`, at COLLECTION, which takes the
    whole suite rather than one test.

    So renaming a shipped module and changing a shared helper's API in one
    release are each safe and are not safe together. A cosmetic rename is never
    worth that, and where one is genuinely needed the old module has to keep
    importing successfully — which is a deprecation, not a rename.
    """
    names = git("ls-files", pattern, root=root).splitlines()
    names += git("ls-files", "--others", "--exclude-standard", pattern, root=root).splitlines()
    return [root / line for line in dict.fromkeys(names) if line.strip()]


def reference_docs(root: Path = PROJECT_ROOT) -> list:
    """Markdown in the tree that is meant to describe it as it is now."""
    narrative = tuple(str(directory.relative_to(PROJECT_ROOT)) for directory in NARRATIVE)
    return [path for path in present("*.md", root=root) if not str(path.relative_to(root)).startswith(narrative)]
