#!/usr/bin/env python3
"""No tracked file still names a path this push deletes or renames away.

A deletion is checked by nothing else: `check_source_doc_refs.py` reads `docs/**`
citations and `test_docs_name_live_code.py` reads callables, so a script removed
or moved stays named in a README, a workflow or another script until a reader
runs it (breeze-brain). The range is `check_commit_subjects.default_range`'s,
so a path deleted at an earlier push never fires again; a hit is the push that
made it, and the tree decides it then.

The needle is the old path, repo-relative or as `<repo-dir>/<path>`. A root file's
bare name is not one: `install` matches prose everywhere. Renames are git's own
`--find-renames`. Out of scope by role: the narrative stages (`paths.NARRATIVE`)
and the changelog, as `test_docs_name_live_code.py` reads them, since history
naming an old path is correct; and `.skeletor.json`, which records deletions.

A citation kept on purpose goes in `scripts/deleted_paths_allowlist.yaml` as
`<file>:<old path>: reason`, and an entry whose file no longer names the path,
or whose path is back, is stale.

Usage:  python scripts/check_deleted_paths.py [--range A..B] [--json]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import allowlist  # noqa: E402
from scripts.check_commit_subjects import default_range  # noqa: E402
from scripts.output import EXIT_REFUSED, detail, emit, fail, item, no_subject, ok  # noqa: E402
from scripts.paths import NARRATIVE, PROJECT_ROOT, SCAFFOLD_MANIFEST, SCRIPTS_DIR, changelogs, is_foreign  # noqa: E402

ALLOWLIST = SCRIPTS_DIR / "deleted_paths_allowlist.yaml"
ALLOWLIST_REL = ALLOWLIST.relative_to(PROJECT_ROOT).as_posix()

#: A name rather than a parenthesised tuple in the `except`; see
#: `check_source_doc_refs.py` for why black needs it.
_UNREADABLE = (UnicodeDecodeError, OSError)


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def tracked(root: Path) -> set[str] | None:
    listed = git(root, "ls-files", "-z")
    return {name for name in listed.stdout.split("\0") if name} if listed.returncode == 0 else None


def gone(root: Path, commit_range: str, present: set[str]) -> list[str] | None:
    """Paths the range deletes or renames away that HEAD does not track; None if git cannot read it."""
    listed = git(root, "log", "--diff-filter=DR", "--find-renames", "--name-status", "--format=", commit_range)
    if listed.returncode != 0:
        return None
    old = {line.split("\t")[1] for line in listed.stdout.splitlines() if line[:1] in ("D", "R") and "\t" in line}
    return sorted(path for path in old if path not in present)


def needle(path: str, repo_dir: str) -> re.Pattern:
    """The old path as a citation: whole, never a suffix of a longer path or a bare root name."""
    prefix = rf"(?:\.\./)?{re.escape(repo_dir)}/"
    head = f"(?:{prefix}|\\./)" if "/" not in path else f"(?:{prefix}|\\./)?"
    return re.compile(rf"(?<![\w./-]){head}{re.escape(path)}(?![\w/-]|\.\w)")


#: Files that name removed paths by design, and the history stages, root-relative.
_RECORDS = (SCAFFOLD_MANIFEST.name, ALLOWLIST_REL)
_STAGES = tuple(stage.relative_to(PROJECT_ROOT) for stage in NARRATIVE)


def in_scope(rel: str, generated: set[str]) -> bool:
    if rel in generated or rel in _RECORDS or is_foreign(rel):
        return False
    return not any(Path(rel).is_relative_to(stage) for stage in _STAGES)


def citations(root: Path, paths: list[str], present: set[str]) -> list[tuple[str, int, str]]:
    """`(file, line, old path)` for each tracked in-scope file naming one of `paths`."""
    patterns = {path: needle(path, root.name) for path in paths}
    generated = changelogs(root)
    found = []
    for rel in sorted(present):
        if not in_scope(rel, generated) or not (root / rel).is_file():
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except _UNREADABLE:
            continue
        for path, pattern in patterns.items():
            for lineno, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    found.append((rel, lineno, path))
    return found


def stale(root: Path, entries: dict[str, str], present: set[str]) -> list[str]:
    def still_needed(key: str) -> str | None:
        rel, _, path = key.partition(":")
        if not path:
            return "it is not `<file>:<old path>`"
        if path in present:
            return f"{path} is tracked again"
        if rel not in present:
            return f"{rel} is not tracked"
        if not needle(path, root.name).search((root / rel).read_text(encoding="utf-8", errors="replace")):
            return f"{rel} no longer names {path}"
        return None

    return allowlist.stale(entries, still_needed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--range", dest="commit_range", help="git range (default: what a push would send)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    commit_range = args.commit_range or default_range()

    present = tracked(PROJECT_ROOT)
    paths = gone(PROJECT_ROOT, commit_range, present) if present is not None else None
    if present is None or paths is None:
        if args.json:
            emit({"range": commit_range, "deleted": [], "cited": [], "stale": []})
        fail(f"git cannot read {commit_range} here, so no deletion was checked")
        return EXIT_REFUSED

    entries = allowlist.read(ALLOWLIST)
    found = citations(PROJECT_ROOT, paths, present)
    cited = [(rel, lineno, path) for rel, lineno, path in found if f"{rel}:{path}" not in entries]
    old = stale(PROJECT_ROOT, entries, present)
    if args.json:
        rows = [f"{rel}:{lineno}: {path}" for rel, lineno, path in cited]
        emit({"range": commit_range, "deleted": paths, "cited": rows, "stale": old})

    if old:
        fail(f"{len(old)} stale entr(y/ies) in {ALLOWLIST_REL}:")
        for entry in old:
            item(entry)
        detail(allowlist.STALE_ADVICE)
    if cited:
        fail(f"{len(cited)} citation(s) of a path {commit_range} deletes or renames away:")
        for rel, lineno, path in cited:
            item(f"{rel}:{lineno}: {path}")
        detail()
        detail(f"Repoint each one, or record why it stays in {ALLOWLIST_REL}")
        detail("as `<file>:<old path>: reason`.")
    if old or cited:
        return 1
    if not paths:
        no_subject(f"{commit_range} deletes and renames no tracked path, so there is nothing to look for")
        return 0
    ok(f"{len(paths)} path(s) {commit_range} deletes or renames away, and no tracked file names one")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
