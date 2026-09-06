#!/usr/bin/env python3
"""Regenerate every derived docs artifact, in dependency order.

Order is not cosmetic: the READMEs are built from the JSON indexes, so a README
rebuilt before its index describes the previous scan. Running them out of order
produces a plausible, wrong file — the worst kind, because nobody reviews a
generated artifact closely.

Usage:  python scripts/docs/regen.py [--check]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(HERE.parents[1]))

from scripts.output import fail, step  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402

#: (script, human label). Frontmatter first — both indexes read it.
PIPELINE = [
    ("add_frontmatter.py", "frontmatter backfill"),
    ("gen_todo_index.py", "docs/todo_index.json"),
    ("rebuild_todo_readme.py", "docs/TODO/README.md"),
    ("gen_impl_index.py", "docs/implementation_index.json"),
    ("rebuild_impl_readme.py", "docs/implementations/README.md"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report staleness; write nothing")
    args = parser.parse_args()

    status = 0
    for script, label in PIPELINE:
        # The backfill has no --check: it is the input to the checks, not a
        # generated artifact, and running it in a check would mutate the tree.
        if args.check and script == "add_frontmatter.py":
            continue
        cmd = [sys.executable, str(HERE / script)] + (["--check"] if args.check else [])
        step(label)
        if subprocess.run(cmd, cwd=PROJECT_ROOT).returncode != 0:
            status = 1

    if args.check and status:
        fail("generated docs are stale — run `dev docs index`")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
