#!/usr/bin/env python3
"""Install what a clone does not inherit: the `regen-docs` merge driver and the pre-push hook.

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

The hook is the same kind of fact: `scripts/hooks/pre-push` is tracked and the
copy git runs is not. An existing hook this script did not write is left alone,
and `--check` stays red until somebody decides. Deleting the tracked file declines
the hook, which takes `tests/test_green_stamp.py` with it.

Usage:  python scripts/git/install_merge_drivers.py [--check]
"""

from __future__ import annotations

import argparse
import os
import re
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

#: Every `merge=<name>` a tracked `.gitattributes` routes a path through. The
#: set is read from the file, not listed: this checked one constant, so a
#: second driver named in `.gitattributes` and defined nowhere passed `--check`.
_MERGE_ATTR = re.compile(r"^(?!#)\S+\s+.*\bmerge=(?P<name>[A-Za-z0-9_-]+)", re.MULTILINE)
ATTRIBUTES = PROJECT_ROOT / ".gitattributes"
#: A tracked `.gitmessage` is a claim that `commit.template` points at it. It
#: shipped for the template's whole life and nothing set the key: unset in five
#: of six adopter clones, measured.
MESSAGE_TEMPLATE = PROJECT_ROOT / ".gitmessage"
#: What git cannot run from the tree, so it is copied. Absent means declined.
HOOK_SOURCE = PROJECT_ROOT / "scripts" / "hooks" / "pre-push"
#: The first line of the hook's comment, and how a copy of ours is told from anybody else's.
HOOK_MARK = "Written by scripts/git/install_merge_drivers.py"
FOREIGN_SOURCE = "`scripts/hooks/pre-push` is this tree's own hook, not the green stamp's, so it was not installed"


def declared_drivers() -> set:
    if not ATTRIBUTES.exists():
        return set()
    return {m.group("name") for m in _MERGE_ATTR.finditer(ATTRIBUTES.read_text(encoding="utf-8"))}


# %B is the "other" (incoming) version, %A the destination git reads back.
COMMAND = f'sh -c \'mkdir -p "{MARKER.parent}" && cp "%B" "%A" && touch "{MARKER}"\''


def _config(key: str) -> str:
    return subprocess.run(
        ["git", "config", "--local", "--get", key], cwd=str(PROJECT_ROOT), capture_output=True, text=True
    ).stdout.strip()


def hook_path() -> Path:
    """Where git will look, which honours `core.hooksPath` and a linked worktree's common dir."""
    asked = ["git", "rev-parse", "--git-path", "hooks/pre-push"]
    done = subprocess.run(asked, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    return PROJECT_ROOT / (done.stdout.strip() or ".git/hooks/pre-push")


def _ours(hook: Path) -> bool:
    return hook.is_file() and not hook.is_symlink() and HOOK_MARK in hook.read_text(encoding="utf-8", errors="replace")


def hook_problem() -> str | None:
    """Why this clone's push is not protected, or `None` when it is, or the tree declined the hook."""
    if not HOOK_SOURCE.exists():
        return None
    if not _ours(HOOK_SOURCE):
        return FOREIGN_SOURCE
    hook = hook_path()
    if not hook.exists() and not hook.is_symlink():
        return "`scripts/hooks/pre-push` is tracked and not installed in this clone"
    if not _ours(hook):
        return f"{hook} is a pre-push hook this tree did not write, so pushes are not checked"
    if hook.read_bytes() != HOOK_SOURCE.read_bytes() or not os.access(hook, os.X_OK):
        return f"{hook} differs from the tracked `scripts/hooks/pre-push`"
    return None


def install_hook() -> bool:
    if not HOOK_SOURCE.exists():
        return True
    if not _ours(HOOK_SOURCE):
        fail(FOREIGN_SOURCE)
        detail("Replace it with skeletor's, or rename it to decline the green stamp.")
        return False
    hook = hook_path()
    if (hook.exists() or hook.is_symlink()) and not _ours(hook):
        fail(f"{hook} already exists and this script did not write it, so it was left alone")
        detail("Remove it and run this again, or delete scripts/hooks/pre-push to decline the green stamp.")
        return False
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_bytes(HOOK_SOURCE.read_bytes())
    hook.chmod(0o755)
    ok("installed the pre-push hook")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report state; change nothing")
    args = parser.parse_args()

    if args.check:
        missing = sorted(name for name in declared_drivers() if not _config(f"merge.{name}.driver"))
        if missing:
            fail(f"merge driver(s) named in .gitattributes and NOT defined in this clone: {', '.join(missing)}")
            detail("python scripts/git/install_merge_drivers.py")
            detail("That installs regen-docs; any other driver name is yours to define.")
            return 1
        if MESSAGE_TEMPLATE.exists() and not _config("commit.template"):
            fail("`.gitmessage` is tracked but `commit.template` is unset in this clone")
            detail("python scripts/git/install_merge_drivers.py")
            return 1
        problem = hook_problem()
        if problem:
            fail(problem)
            detail("python scripts/git/install_merge_drivers.py")
            return 1
        declared = sorted(declared_drivers())
        template = ", commit.template" if MESSAGE_TEMPLATE.exists() else ""
        hook = ", pre-push hook" if HOOK_SOURCE.exists() else ""
        ok(
            f"clone-local config present: {len(declared)} merge driver(s) "
            f"{', '.join(declared) or 'none'}{template}{hook}"
        )
        if MARKER.exists():
            # Asked rather than assumed: the merge that left the marker may have
            # changed nothing a generator reads, and `regen.py` clears it when so.
            regen = PROJECT_ROOT / "scripts" / "docs" / "regen.py"
            if regen.exists():
                subprocess.run([sys.executable, str(regen), "--check"], cwd=str(PROJECT_ROOT), capture_output=True)
        if MARKER.exists():
            warn("a regeneration is owed from a previous merge — run `dev docs index`, which clears it")
            return 1
        return 0

    subprocess.run(
        ["git", "config", "--local", f"{DRIVER}.name", "regenerate generated docs"], cwd=str(PROJECT_ROOT), check=True
    )
    subprocess.run(["git", "config", "--local", f"{DRIVER}.driver", COMMAND], cwd=str(PROJECT_ROOT), check=True)
    ok("installed the 'regen-docs' merge driver")
    if MESSAGE_TEMPLATE.exists():
        subprocess.run(
            ["git", "config", "--local", "commit.template", ".gitmessage"], cwd=str(PROJECT_ROOT), check=True
        )
        ok("set commit.template to .gitmessage")
    detail("After any merge that touched docs/TODO/ or docs/implementations/: `dev docs index`")
    return 0 if install_hook() else 1


if __name__ == "__main__":
    raise SystemExit(main())
