#!/usr/bin/env python3
"""Install the `regen-docs` merge driver into this checkout's `.git/config`.

`.gitattributes` routes the generated docs artifacts through a driver named
`regen-docs`. That name is version controlled; the **definition** lives in
`.git/config`, which is not — so a fresh clone has attributes pointing at a
driver that does not exist, and git silently falls back to a three-way text
merge of a 100k-line generated JSON. Conflict markers inside a generated file
are never a correct resolution, and hand-resolving one is how a branch's doc
edits get silently reverted.

The driver takes the **incoming** side wholesale and leaves a marker saying a
regeneration is owed. That is correct because the merged text was never the
answer: the answer is "regenerate from the merged sources", which is a command,
not a merge.

Usage:  python scripts/git/install_merge_drivers.py [--check]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.output import detail, fail, ok, warn  # noqa: E402
from scripts.paths import PROJECT_ROOT, TMP_DIR  # noqa: E402

DRIVER = "merge.regen-docs"
MARKER = TMP_DIR / ".regen-owed"

# %B is the "other" (incoming) version, %A the destination git reads back.
COMMAND = f'sh -c \'mkdir -p "{MARKER.parent}" && cp "%B" "%A" && touch "{MARKER}"\''


def _config(key: str) -> str:
    return subprocess.run(
        ["git", "config", "--local", "--get", key], cwd=str(PROJECT_ROOT), capture_output=True, text=True
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report state; change nothing")
    args = parser.parse_args()

    installed = bool(_config(f"{DRIVER}.driver"))

    if args.check:
        if not installed:
            fail("the 'regen-docs' merge driver is NOT installed in this checkout")
            detail("python scripts/git/install_merge_drivers.py")
            return 1
        ok("merge driver 'regen-docs' installed")
        if MARKER.exists():
            warn("a regeneration is owed from a previous merge — run `dev docs index`")
            return 1
        return 0

    subprocess.run(
        ["git", "config", "--local", f"{DRIVER}.name", "regenerate generated docs"], cwd=str(PROJECT_ROOT), check=True
    )
    subprocess.run(["git", "config", "--local", f"{DRIVER}.driver", COMMAND], cwd=str(PROJECT_ROOT), check=True)
    ok("installed the 'regen-docs' merge driver")
    detail("After any merge that touched docs/TODO/ or docs/implementations/: `dev docs index`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
