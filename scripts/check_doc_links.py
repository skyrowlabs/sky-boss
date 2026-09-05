#!/usr/bin/env python3
"""Validate relative markdown links between docs — and their `#fragments`.

Runs as a **ratchet** against `scripts/doc_links_baseline.json`, not a
pass/fail: a project adopting this mid-life has dead links already, and a gate
that is red on arrival gets disabled. The baseline is the count you inherited;
it may only go down.

Why this exists as its own checker: filing a completed plan one directory deeper
invalidates every relative link *inside* it (`../reports/x.md` now needs
`../../`) **and** every link elsewhere that pointed at its old path. In the
project this was extracted from, that had silently produced 141 dead links, 128
of them inside the archive — the filing process was generating the rot at a
steady rate and nothing caught it.

**A link that leaves the repository is out of scope, in both directions.**
Whether `../sibling-repo/GUIDE.md` resolves is a fact about what is checked out
beside this tree, not about this tree — true on the machine the docs were
written on and false on a runner that cloned one repository. A ratchet cannot
carry a verdict that changes with the neighbours. They are counted and named on
every run, because an unchecked link nobody is told about is the failure this
whole checker exists to prevent.

**Repoint, never delete.** A link whose target is genuinely gone gets its
sentence rewritten to name the successor, or de-linked to a backticked path plus
the commit that removed it. These links are prose that records why the docs say
what they say.

Usage:  python scripts/check_doc_links.py [--fix] [--json] [--update-baseline]

`--json` is additive: the payload goes to stdout, the explanation to stderr.
See `scripts/output.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import detail, emit, fail, item, ok, skip  # noqa: E402
from scripts.paths import DOCS_DIR, GITHUB_DIR, PROJECT_ROOT, SCRIPTS_DIR  # noqa: E402

BASELINE = SCRIPTS_DIR / "doc_links_baseline.json"
IGNORE_FILE = GITHUB_DIR / "scripts" / ".validate-ignore"

SCAN_ROOTS = ["docs", ".claude", ".github"]

_LINK = re.compile(r"(?<!!)\[(?P<text>[^\]]*)\]\((?P<href>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
_HEADING = re.compile(r"^(#{1,6})\s+(?P<text>.+?)\s*$", re.MULTILINE)
_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
#: HTML comments hold examples and scaffolding notes. A link inside one is
#: illustrative, not a reference — checking it makes the template itself red,
#: which teaches that red is normal.
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def slugify(heading: str) -> str:
    """GitHub's heading-anchor algorithm, near enough for our purposes."""
    text = re.sub(r"`([^`]*)`", r"\1", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"[\s_]+", "-", text).strip("-")


def _ignored() -> set:
    if not IGNORE_FILE.exists():
        return set()
    return {
        line.strip()
        for line in IGNORE_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def markdown_files() -> List[Path]:
    """Every markdown file this checker is responsible for.

    The scan roots, plus **every `.md` at the top level** — discovered, not
    listed. It used to be `EXTRA_FILES = ["AGENTS.md", "CLAUDE.md", "README.md"]`,
    which is the three the template happens to ship, so a fresh tree was complete
    and every tree diverged from there the moment anybody added a fourth. The
    check then printed `0 broken links` over a document it had never opened,
    which is the worst available failure: a clean report on an unread file.

    Not hypothetical, and not only a user problem — **`CHANGELOG.md` is written
    at the repository root by Release Please**, which this template ships and
    configures. Every tree that has cut a release has had an unchecked root
    document, and it is the document most made of links.

    Reported by proto.pilot, who hit it on a `NOTES.md` their own README tells a
    reader to open first, an hour after filing a plan broke two links in it.

    The glob lives **inside this function on purpose**. Bound at module scope it
    would be evaluated at import and could not follow a patched `PROJECT_ROOT` —
    so the test fixture would need a new constant to stub, and a listed thing
    would have been replaced by a derived thing that still needed hand
    maintenance at the seam. proto.pilot found that edge too; it is the same
    lesson `scripts/paths.py` records about redirecting a tree.
    """
    out = []
    for root in SCAN_ROOTS:
        out.extend(sorted((PROJECT_ROOT / root).rglob("*.md")))
    out.extend(sorted(PROJECT_ROOT.glob("*.md")))
    return [p for p in out if "node_modules" not in p.parts]


def _mask(text: str) -> str:
    """Blank out code fences and HTML comments, **preserving offsets**.

    Blanked rather than deleted because `--fix` rewrites the original text by
    position: one scan then serves both the check and the repair, and the two
    cannot disagree about which links are real. Newlines are kept so a match
    still lands on the line it came from.
    """

    def blank(match: re.Match) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group(0))

    return _COMMENT.sub(blank, _CODE_FENCE.sub(blank, text))


def headings(path: Path) -> List[str]:
    """Every heading slug in a file, in document order.

    A list and not a set: `--fix` reports the successor it chose, and an
    unordered "one match" is harder to check by eye than an ordered one.
    """
    body = _mask(path.read_text(encoding="utf-8"))
    return [slugify(m.group("text")) for m in _HEADING.finditer(body)]


def _suggest(target: Path) -> str:
    """Where the target probably moved to — same basename, anywhere in docs/."""
    matches = [p for p in DOCS_DIR.rglob(target.name)] if DOCS_DIR.exists() else []
    return f"  → probably {matches[0].relative_to(PROJECT_ROOT)}" if len(matches) == 1 else ""


def _walked(source: Path, path_part: str) -> Path:
    """Where a link points, **textually** — `..` collapsed, symlinks not followed.

    Deliberately not `Path.resolve()`, which is what this used to be. Resolving
    answers "which file is this", and every question below is really "where does
    this link point": whether it left the repository, and what path to name it by
    in a report. A document that is a symlink to another checkout — one file, one
    home, two repositories — is an in-repo link by that reading and was an
    out-of-repo file by the other, so `relative_to(PROJECT_ROOT)` raised on it.
    `exists()` and `read_text()` follow symlinks themselves, so nothing is lost.
    """
    return Path(os.path.normpath(os.path.join(source.parent, path_part)))


def _leaves_repo(walked: Path) -> bool:
    """Does this link walk out of the repository?"""
    root = str(PROJECT_ROOT)
    return str(walked) != root and not str(walked).startswith(root + os.sep)


def _walk() -> Iterator[Tuple[Path, Path, str, "re.Match[str]"]]:
    """Every link in the tree, once: `(source, rel_source, original, match)`.

    The check and the fix share this generator rather than each writing their
    own loop. Two definitions of "a link worth checking" would drift, and the
    fix would then rewrite something the check never looked at — which is the
    one failure mode a repair tool must not have.

    `original` is the unmasked text; the match offsets index it correctly
    because `_mask` preserves length.
    """
    for source in markdown_files():
        original = source.read_text(encoding="utf-8")
        for match in _LINK.finditer(_mask(original)):
            yield source, source.relative_to(PROJECT_ROOT), original, match


def _contains_run(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    """Is `needle` a contiguous run of tokens inside `haystack`?"""
    if not needle or len(needle) > len(haystack):
        return False
    return any(list(haystack[i : i + len(needle)]) == list(needle) for i in range(len(haystack) - len(needle) + 1))


def _successor(anchor: str, available: Sequence[str]) -> Optional[str]:
    """The one heading this dead fragment obviously became, or `None`.

    A heading edit breaks an anchor in one of two ways: the heading grew
    (`#why-this-exists` → `#why-this-exists-as-its-own-checker`) or it shrank.
    Either way the shorter slug survives as a contiguous run of tokens inside
    the longer — which is a narrow rule on purpose, because the alternative is
    guessing.

    **Ambiguity is the entire safety mechanism.** Two candidates means a human
    chooses: a fragment repointed to the wrong section is worse than a dead one,
    because a dead link announces itself on the next run and a wrong one never
    does. Same for zero candidates — that heading did not move, it went, and
    `--fix` has nothing to say about a sentence that needs rewriting.
    """
    want = [token for token in anchor.split("-") if token]
    if not want:
        return None
    hits = set()
    for slug in available:
        tokens = slug.split("-")
        if _contains_run(tokens, want) or _contains_run(want, tokens):
            hits.add(slug)
    return sorted(hits)[0] if len(hits) == 1 else None


def scan() -> Tuple[List[str], List[str], List[str]]:
    ignore = _ignored()
    dead_paths: List[str] = []
    dead_anchors: List[str] = []
    outside: List[str] = []
    heading_cache: Dict[Path, List[str]] = {}

    for source, rel_source, _original, match in _walk():
        href = match.group("href")
        if href.startswith(("http://", "https://", "mailto:", "#")):
            # Same-file fragments are checked against this file's headings.
            if href.startswith("#"):
                anchor = href[1:]
                if f"{rel_source}{href}" in ignore:
                    continue
                if anchor and anchor not in heading_cache.setdefault(source, headings(source)):
                    dead_anchors.append(f"{rel_source}: '{href}' matches no heading here")
            continue

        path_part, _, anchor = href.partition("#")
        if not path_part:
            continue
        if f"{rel_source}#{anchor}" in ignore or path_part in ignore:
            continue
        target = _walked(source, path_part)
        if _leaves_repo(target):
            outside.append(f"{rel_source}: '{href}'")
            continue
        if not target.exists():
            dead_paths.append(f"{rel_source}: '{path_part}' does not exist{_suggest(Path(path_part))}")
            continue
        if anchor and target.suffix == ".md":
            if anchor not in heading_cache.setdefault(target, headings(target)):
                dead_anchors.append(f"{rel_source}: '{href}' — no such heading in {target.relative_to(PROJECT_ROOT)}")

    return dead_paths, dead_anchors, outside


def repoint_fragments() -> List[str]:
    """Rewrite every dead fragment that has exactly one obvious successor.

    Deliberately narrower than the check. It touches **fragments only** — a
    broken *path* is never rewritten, because where a file went is a judgement
    call and `_suggest` offers it as a hint for a person rather than an edit.
    That asymmetry is the point: a wrong `#section` is invisible, and a wrong
    path is a lie about which document says something.

    Commits nothing. Read the diff.
    """
    ignore = _ignored()
    heading_cache: Dict[Path, List[str]] = {}
    edits: Dict[Path, List[Tuple[int, int, str]]] = {}
    repointed: List[str] = []

    for source, rel_source, original, match in _walk():
        href = match.group("href")
        if href.startswith(("http://", "https://", "mailto:")):
            continue

        path_part, sep, anchor = href.partition("#")
        if not sep or not anchor:
            continue
        if f"{rel_source}#{anchor}" in ignore or path_part in ignore:
            continue
        if path_part:
            target = _walked(source, path_part)
            if _leaves_repo(target):
                continue
            # A fragment on a path that does not resolve is not a fragment
            # problem. Repointing it would paper over the broken path.
            if not target.exists() or target.suffix != ".md":
                continue
        else:
            target = source

        available = heading_cache.setdefault(target, headings(target))
        if anchor in available:
            continue
        replacement = _successor(anchor, available)
        if replacement is None:
            continue

        span = match.span("href")
        edits.setdefault(source, []).append((span[0], span[1], f"{path_part}#{replacement}"))
        repointed.append(f"{rel_source}: '#{anchor}' → '#{replacement}' in {target.relative_to(PROJECT_ROOT)}")

    for source, spans in edits.items():
        text = source.read_text(encoding="utf-8")
        # Right to left, so an earlier edit cannot shift a later one's offsets.
        for start, stop, replacement in sorted(spans, reverse=True):
            text = text[:start] + replacement + text[stop:]
        source.write_text(text, encoding="utf-8")

    return sorted(repointed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="repoint fragments with exactly one matching heading")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--update-baseline", action="store_true", help="record the current counts as the new ceiling")
    args = parser.parse_args()

    # Before the scan, so the counts below describe the tree as it now is —
    # reporting a ceiling breach the same run just repaired would send somebody
    # to fix a link that is already fixed.
    repointed: List[str] = []
    if args.fix:
        repointed = repoint_fragments()
        if repointed:
            ok(f"repointed {len(repointed)} fragment(s) — nothing was committed, read the diff")
            for entry in repointed:
                item(entry)
        else:
            ok("no dead fragment had exactly one obvious successor — nothing changed")
            detail("A fragment with two candidates, or none, is a sentence for a human to rewrite.")

    dead_paths, dead_anchors, outside = scan()
    if outside:
        skip(f"{len(outside)} link(s) leave this repository — not checked")
        detail("Whether they resolve depends on what is checked out beside this tree.")
        for entry in outside[:10]:
            item(entry)
        if len(outside) > 10:
            detail(f"… and {len(outside) - 10} more")

    baseline = (
        json.loads(BASELINE.read_text(encoding="utf-8"))
        if BASELINE.exists()
        else {"max_broken": 0, "max_dead_anchors": 0}
    )

    if args.update_baseline:
        BASELINE.write_text(
            json.dumps(
                {
                    "_comment": "Ratchet ceiling for scripts/check_doc_links.py. These may only go DOWN.",
                    "max_broken": len(dead_paths),
                    "max_dead_anchors": len(dead_anchors),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if args.json:
            emit(
                {
                    "broken": dead_paths,
                    "dead_anchors": dead_anchors,
                    "outside": outside,
                    "repointed": repointed,
                    "baseline_updated": True,
                }
            )
        ok(f"baseline set to {len(dead_paths)} broken / {len(dead_anchors)} dead anchors")
        return 0

    if args.json:
        emit(
            {
                "broken": dead_paths,
                "dead_anchors": dead_anchors,
                "outside": outside,
                "repointed": repointed,
                "baseline": baseline,
            }
        )

    status = 0
    for label, found, ceiling in (
        ("broken links", dead_paths, baseline.get("max_broken", 0)),
        ("dead anchors", dead_anchors, baseline.get("max_dead_anchors", 0)),
    ):
        if len(found) > ceiling:
            fail(f"{len(found)} {label} (ceiling {ceiling}) — repoint them, never delete:")
            for entry in found[:40]:
                item(entry)
            if len(found) > 40:
                detail(f"… and {len(found) - 40} more")
            status = 1
        elif len(found) < ceiling:
            ok(f"{len(found)} {label} — below the {ceiling} ceiling. Lower it in this commit:")
            detail("  python scripts/check_doc_links.py --update-baseline")
        else:
            ok(f"{label}: {len(found)} (at the ceiling)")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
